"""FP4->V4 repack bridge, ported from the fin2 fork (0.2.9-ep1q2-fin2,
kernels/ops/attention/dsv4/repack_fp4_to_v4.py) onto main 79cafec0 as an
adapter-overlay file. See 96-FP4KV-PORT-DESIGN-20260929.md for the port map.

Under SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4 the ratio-1/2 compressed pools are
stored as 288 B/token V41_FP4 (e2m1 payload + per-16 e4m3 scales), but the
SM120/SM121 FlashInfer sparse-MLA kernel only reads the 584-byte V4 layout
(448 e4m3 nope + 64 bf16 rope + 7 ue8m0 scales + 1 pad, 64-token pages of
37440 B). Before the kernel call the batch's top-k slots are gathered out of
the fp4 pool, dequantized exactly (an e2m1 code times an e4m3 scale has at
most 6 significant bits, exact in fp32) and re-quantized into the V4 layout
in a persistent scratch. The bridged indices are the identity over the
gathered rows, so the FlashInfer call itself is unchanged.

Bit-exactness with the pre-fork fp8 pool: the production V4 writers
(``fused_store_flashmla_cache`` in store.cuh / the c1/c2 decode stores)
requant the fp4-round-tripped latent with, per 64-value nope tile,
``scale = 2^ceil(log2(max(amax, 1e-4) / 448))`` (ue8m0) and payload
``cvt.rn.satfinite.e4m3(x * inv_scale)``, rope cast to bf16. This kernel
reproduces that arithmetic bit-for-bit from the fp4 pool bytes -- for the
ratio-1/2 latents these pools hold, the scratch rows equal the bytes the
pre-fork fp8 pool would have held, so the fp4 boot is indistinguishable from
the fp8 baseline at the KV level. (It says nothing about the ratio-4/128
caches, which stay V4 either way.)

PORT DEVIATIONS from the fin2 file (both deliberate, both logged in the
design card):
  * env reads go through os.environ directly (main's Envs class does not
    declare SGLANG_DSV4_FP4_BRIDGE_SCRATCH_MB / DSV41_FP4_BRIDGE_STATS;
    kv_fp4.install_environ_keys registers them best-effort for discoverability,
    but this module must stay import-order safe).
  * everything else (kernel, scratch lifecycle, slicing, telemetry, the
    pure-torch reference) is a verbatim port; bit-equality with the fork is
    pinned by t44_fp4kv_port.py against both images.

Scratch lifecycle: one grow-only buffer per device under
``get_resources().buffers`` (the ``flash_mla_sm120_split`` pattern), reused
across layers (sequential stream-ordered consumption) and steps, allocated
outside inference mode so CUDA-graph capture can mutate it. Batches whose
``tokens x topk`` exceeds the row budget are query-sliced by the caller; the
per-query softmax makes slicing exact.
"""

import logging
import os
from typing import List, Optional, Tuple

import torch
import triton
import triton.language as tl

from sglang.kernels.ops.attention.dsv4.dequant_k_cache import (
    _e2m1_code_to_fp32,
    fp8_dtype,
)

# V41_FP4 source layout (KVLayout.V41_FP4): 256 B payload + 32 B scales.
_SRC_DATA_BYTES = 256
_SRC_SCALE_BYTES = 32
_SRC_TILE = 16
# V4 destination layout at 64-token pages: footer-format pages, byte-identical
# to what _split_kv_pages_to_64 emits (its DST_SCALE_OFF / DATA_PER_SUB
# constants are the layout the FlashInfer FFI actually reads): data rows at a
# 576 B stride (448 fp8 nope + 128 B bf16 rope), then a contiguous per-page
# scale block at offset 64*576, 8 B/token (7 ue8m0 + 1 pad), page padded to
# 576 alignment. The 584-pitch as_strided view the wrapper returns is only
# the FFI passing form, NOT the byte layout.
_DST_PAGE_SIZE = 64
_DST_DATA_STRIDE = 576  # 448 fp8 nope + 128 B bf16 rope
_DST_DATA_BYTES = 448 + 128
_DST_SCALE_STRIDE = 8  # 7 ue8m0 + 1 pad
_DST_SCALE_OFF = _DST_PAGE_SIZE * _DST_DATA_STRIDE  # 36864
_DST_PAGE_BYTES = (
    _DST_PAGE_SIZE * (_DST_DATA_STRIDE + _DST_SCALE_STRIDE) + 575
) // 576 * 576  # 37440
_DST_BPT = _DST_DATA_STRIDE + _DST_SCALE_STRIDE  # 584
_NOPE_TILE = 64  # values per ue8m0 scale in the V4 layout
_NOPE_VALUES = 448
_NOPE_BYTES = _NOPE_VALUES // 2  # 224 packed bytes
_ROPE_BYTES = 32  # 64 rope values, packed

# The images' Triton forbids plain-int globals inside @jit bodies; mirror the
# constants the kernel reads as tl.constexpr instances (host code keeps the
# plain ints above).
C_SRC_DATA_BYTES = tl.constexpr(_SRC_DATA_BYTES)
C_SRC_SCALE_BYTES = tl.constexpr(_SRC_SCALE_BYTES)
C_NOPE_BYTES = tl.constexpr(_NOPE_BYTES)
C_NOPE_VALUES = tl.constexpr(_NOPE_VALUES)
C_DST_PAGE_BYTES = tl.constexpr(_DST_PAGE_BYTES)
C_DST_DATA_STRIDE = tl.constexpr(_DST_DATA_STRIDE)
C_DST_DATA_BYTES = tl.constexpr(_DST_DATA_BYTES)
C_DST_BPT = tl.constexpr(_DST_BPT)
C_DST_SCALE_OFF = tl.constexpr(_DST_SCALE_OFF)
C_DST_SCALE_STRIDE = tl.constexpr(_DST_SCALE_STRIDE)

_logger = logging.getLogger(__name__)
_logged_activation = False

# Env keys (same names/defaults as the fin2 fork; main does not declare them,
# so read the process env directly -- see the port-deviation note above).
ENV_BRIDGE_SCRATCH_MB = "SGLANG_DSV4_FP4_BRIDGE_SCRATCH_MB"
ENV_BRIDGE_STATS = "DSV41_FP4_BRIDGE_STATS"
# Repack kernel backend: triton (the verified reference), cuda (the
# librepack_cuda.so port, bit-exact by the tests/test_repack_cuda.py gate) or
# auto (default: HYBRID per-call dispatch on n -- cuda for n >=
# DSV41_FP4KV_REPACK_CUDA_MIN_N (default 2048), triton below; the .so failing
# to load degrades the whole bridge to triton). A6 census 2026-10-01: at
# in-engine clock state the Triton grid=(n,) spread wins the small-n regime
# (3.4us vs 5.2us avg) while the CUDA port keeps its >=2x edge from n>=2048
# (isolated bench), so auto takes the best of both. Explicit triton/cuda
# forces a single backend for arm reproducibility. Fail-safe direction is
# ALWAYS back to the verified Triton path, with one loud log line.
ENV_REPACK_BACKEND = "DSV41_FP4KV_REPACK_BACKEND"
ENV_REPACK_CUDA_MIN_N = "DSV41_FP4KV_REPACK_CUDA_MIN_N"

_cuda_repack_mod = None
_cuda_repack_error = None
_active_backend = None


def _repack_cuda_lib():
    """Lazily import adapter lib/librepack_cuda.so; raises on failure (cached)."""
    global _cuda_repack_mod, _cuda_repack_error
    if _cuda_repack_mod is not None:
        return _cuda_repack_mod
    if _cuda_repack_error is not None:
        raise RuntimeError(_cuda_repack_error)
    import importlib.machinery
    import importlib.util

    lib = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "lib", "librepack_cuda.so"
    )
    try:
        loader = importlib.machinery.ExtensionFileLoader("repack_cuda", lib)
        spec = importlib.util.spec_from_loader("repack_cuda", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 - any failure falls back to triton
        _cuda_repack_error = f"{type(e).__name__}: {e}"
        raise
    _cuda_repack_mod = mod
    return mod


def _repack_backend():
    """Resolve the repack backend mode: ("cuda"|"triton"|"auto", requested).
    "auto" means the hybrid n-threshold dispatch (caller decides per call);
    it is only returned when the .so actually loads. Never raises; a
    broken/unloadable cuda backend degrades to triton after one loud log."""
    global _active_backend
    requested = (os.environ.get(ENV_REPACK_BACKEND) or "auto").strip().lower()
    if requested not in ("triton", "cuda", "auto"):
        _logger.warning(
            "invalid %s=%r, using auto", ENV_REPACK_BACKEND, requested
        )
        requested = "auto"
    if requested == "triton":
        return "triton", requested
    try:
        _repack_cuda_lib()
    except Exception as e:  # noqa: BLE001
        # AUD-3 S1-1: one-shot only -- the bridge calls this every repack
        # (~38/step), a per-call ERROR here would log ~1400 lines/s/rank.
        global _logged_backend_fallback
        if not _logged_backend_fallback:
            _logged_backend_fallback = True
            _logger.error(
                "DSV41 fp4->V4 repack CUDA backend unavailable (%s lib/librepack_cuda.so: %s); "
                "FALLING BACK TO TRITON (verified path, logged once). Backend request was %r.",
                os.path.dirname(os.path.abspath(__file__)),
                e,
                requested,
            )
        return "triton", requested
    return requested, requested

_logged_backend_fallback = False


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _logger.warning("invalid %s=%r, using default %d", name, raw, default)
        return default


# --- measurement (DSV41_FP4_BRIDGE_STATS>0; inert when off) -----------------
# The bridge is pure overhead: it moves the batch's top-k rows from the 288 B
# fp4 pool into the 584 B V4 scratch so the FlashInfer kernel can read them.
# Cost is O(rows) with rows = tokens x topk ALWAYS, regardless of how many of
# those slots are real (a token whose history is shorter than topk still gets
# its tail repacked as zero rows). These counters exist to price the three
# candidate fixes from data instead of arithmetic: (1) a bigger scratch (= fewer
# query slices), (2) compaction to the real topk length, (3) reading the fp4
# pool in-kernel (upstream FlashInfer #5197) which deletes the write entirely.
# N == 1 is the only value that also enables per-call CUDA-event timing: that
# path needs a host sync, which serializes the pipeline and inflates wall clock.
# The counters (rows / real rows / slices) are sync-free and valid at any N, and
# timings are only taken OUTSIDE graph capture (decode runs inside a CUDA graph,
# where events are not valid).
_bridge_stats = {
    "calls": 0, "prefill_calls": 0, "rows": 0, "real_rows": 0,
    "tokens": 0, "prefill_tokens": 0, "slices": 0, "extra_slices": 0,
    "us": 0.0, "attn_us": 0.0, "timed_calls": 0,
}


def bridge_stats_period() -> int:
    """Log every N calls; 0 disables both counting and logging."""
    return _env_int(ENV_BRIDGE_STATS, 0)


def bridge_time_enabled() -> bool:
    """Per-call CUDA-event timing is opt-in (STATS == 1): it forces a host sync."""
    return bridge_stats_period() == 1


def bridge_note_slices(n_slices: int) -> None:
    if not bridge_stats_period():
        return
    _bridge_stats["slices"] += 1
    _bridge_stats["extra_slices"] += max(0, n_slices - 1)


def bridge_note_call(
    num_tokens: int, topk: int, real_rows: int, bridge_us: float, attn_us: float
) -> None:
    """One (possibly sliced) bridge+attention step.

    real_rows and the two timings are only meaningful for eager (prefill) calls:
    summing the kernel's topk_lengths needs a device sync, which is illegal
    inside graph capture. Pass real_rows=-1 for decode/verify.
    """
    period = bridge_stats_period()
    if not period:
        return
    s = _bridge_stats
    s["calls"] += 1
    s["tokens"] += num_tokens
    s["rows"] += num_tokens * topk
    if real_rows >= 0:
        s["prefill_calls"] += 1
        s["prefill_tokens"] += num_tokens
        s["real_rows"] += real_rows
        s["us"] += bridge_us
        s["attn_us"] += attn_us
        s["timed_calls"] += 1
    if period > 0 and s["calls"] % period == 0:
        rows, real = s["rows"], s["real_rows"]
        timed = max(1, s["timed_calls"])
        _logger.info(
            "DSV41 fp4 bridge stats: calls=%d (prefill=%d, extra_slices=%d) "
            "rows=%d real_rows=%d real=%.1f%% | tokens=%d (prefill=%d) | "
            "bridge_us/call=%.1f attn_us/call=%.1f | GB_moved=%.2f",
            s["calls"], s["prefill_calls"], s["extra_slices"], rows, real,
            100.0 * real / rows if rows else 0.0, s["tokens"],
            s["prefill_tokens"], s["us"] / timed, s["attn_us"] / timed,
            rows * (_SRC_DATA_BYTES + _SRC_SCALE_BYTES + _DST_DATA_BYTES
                    + _DST_SCALE_STRIDE) / 2 ** 30,
        )


@triton.jit
def _repack_fp4_to_v4_kernel(
    src_ptr,  # uint8 base of the (num_pages, page_bytes) fp4 pool
    src_fp8_ptr,  # same storage viewed as fp8 (for the e4m3 scale loads)
    idx_ptr,  # (N,) int32 flat top-k slot ids; -1 -> zero row
    dst_ptr,  # uint8 base of the (ceil(N/64), 37440) V4 scratch
    SRC_PAGE_BYTES,
    SRC_PAGE_BITS: tl.constexpr,
):
    pid = tl.program_id(0).to(tl.int64)
    idx = tl.load(idx_ptr + pid)
    valid = idx >= 0
    # Stale slots hold -1 (never a loc past the pool: the indexer only ever
    # writes in-pool locs); clamp so the gather reads a real row and gate the
    # values to zero, leaving a deterministic zero pad row.
    loc = tl.maximum(idx, 0).to(tl.int64)
    src_page = loc >> SRC_PAGE_BITS
    src_slot = loc & ((1 << SRC_PAGE_BITS) - 1)
    # src_page is int64, so the page-stride multiply promotes to int64 (pools
    # can exceed 2 GiB of byte offsets at the fork pin sizes).
    src_base = src_page * SRC_PAGE_BYTES
    data_base = src_base + src_slot * C_SRC_DATA_BYTES
    scale_base = src_base + ((1 << SRC_PAGE_BITS) * C_SRC_DATA_BYTES) + src_slot * C_SRC_SCALE_BYTES
    gate = tl.where(valid, 1.0, 0.0)

    # ---- nope: 224 packed bytes -> 448 values -> 7 fp8/ue8m0 tiles ----
    boffs = tl.arange(0, 256)
    pmask = boffs < C_NOPE_BYTES
    packed = tl.load(src_ptr + data_base + boffs, mask=pmask, other=0)
    # Byte b holds values 2b (low nibble) and 2b + 1; both lie in fp4 tile
    # (2b) // 16 == b // 8, so one scale load serves both.
    soffs = boffs // 8
    scale = tl.load(src_fp8_ptr + scale_base + soffs, mask=pmask, other=0.0).to(tl.float32)
    vlo = _e2m1_code_to_fp32(packed & 0xF) * scale * gate
    vhi = _e2m1_code_to_fp32(packed >> 4) * scale * gate

    # V4 requant, per 64-value tile t = b // 32 (tile 7 is the rope region,
    # masked out of the amax and not stored in the footer).
    abslo = tl.where(pmask, tl.abs(vlo), 0.0)
    abshi = tl.where(pmask, tl.abs(vhi), 0.0)
    amax = tl.max(
        tl.maximum(tl.reshape(abslo, (8, 32)), tl.reshape(abshi, (8, 32))), axis=1
    )
    # store.cuh: scale_raw = max(amax, 1e-4) / 448 (IEEE division), ue8m0 byte
    # = biased exponent + (mantissa != 0); the scale is a power of two so the
    # reciprocal multiply below is exact.
    scale_raw = tl.fdiv(tl.maximum(amax, 1e-4), 448.0, ieee_rounding=True)
    u = scale_raw.to(tl.int32, bitcast=True)
    ue8m0 = ((u >> 23) & 0xFF) + tl.where((u & 0x7FFFFF) != 0, 1, 0)
    inv_scale8 = ((254 - ue8m0) << 23).to(tl.float32, bitcast=True)
    inv32 = tl.reshape(tl.broadcast_to(inv_scale8[:, None], (8, 32)), (256,))

    plo = (vlo * inv32).to(tl.float8e4nv)
    phi = (vhi * inv32).to(tl.float8e4nv)
    # Data rows at 576-pitch inside the page (footer-format; see constants).
    dst_base = (pid >> 6) * C_DST_PAGE_BYTES + (pid & 63) * C_DST_DATA_STRIDE
    tl.store(dst_ptr + dst_base + 2 * boffs, plo.to(tl.uint8, bitcast=True), mask=pmask)
    tl.store(dst_ptr + dst_base + 2 * boffs + 1, phi.to(tl.uint8, bitcast=True), mask=pmask)

    # ---- rope: 32 packed bytes -> 64 bf16 values ----
    roffs = tl.arange(0, 32)
    rpacked = tl.load(src_ptr + data_base + C_NOPE_BYTES + roffs)
    # Rope value k (k in [448, 512)) has fp4 scale index k // 16; packed byte
    # j holds values k = 448 + 2j and 448 + 2j + 1, whose group is
    # (448 + 2j) // 16 = 28 + j // 8 (both nibbles share the group).
    rscale = tl.load(src_fp8_ptr + scale_base + 28 + roffs // 8).to(tl.float32)
    rlo = (_e2m1_code_to_fp32(rpacked & 0xF) * rscale * gate).to(tl.bfloat16)
    rhi = (_e2m1_code_to_fp32(rpacked >> 4) * rscale * gate).to(tl.bfloat16)
    dst_bf16 = dst_ptr.to(tl.pointer_type(tl.bfloat16))
    rope_base = (dst_base + C_NOPE_VALUES) // 2
    tl.store(dst_bf16 + rope_base + 2 * roffs, rlo)
    tl.store(dst_bf16 + rope_base + 2 * roffs + 1, rhi)

    # ---- footer: 7 ue8m0 bytes + 1 zero pad, in the per-page scale block ----
    toffs = tl.arange(0, 8)
    sbytes = tl.where(toffs < 7, ue8m0, 0).to(tl.uint8)
    dst_scale_base = (
        (pid >> 6) * C_DST_PAGE_BYTES
        + C_DST_SCALE_OFF
        + (pid & 63) * C_DST_SCALE_STRIDE
    )
    tl.store(dst_ptr + dst_scale_base + toffs, sbytes)


def _persistent_buffer(key: str, shape: Tuple[int, ...], dtype: torch.dtype, device) -> torch.Tensor:
    """Grow-only buffer under get_resources().buffers; retired allocations are
    kept referenced so CUDA graphs captured against them stay valid."""
    from sglang.srt.runtime_context import get_resources

    buffers = get_resources().buffers
    buf = buffers.get(key)
    if buf is not None and buf.shape[0] >= shape[0]:
        return buf[: shape[0]]
    # The first allocation can happen under inference mode (autotune), but the
    # buffer is written again during CUDA graph capture outside inference mode,
    # where an inference tensor cannot be mutated.
    with torch.inference_mode(False):
        new_buf = torch.empty(shape, dtype=dtype, device=device)
    if buf is not None:
        retired = buffers.get(key + ":retired")
        if retired is None:
            retired = []
        buffers[key + ":retired"] = retired
        retired.append(buf)
    buffers[key] = new_buf
    return new_buf


def bridge_max_rows() -> int:
    """Row budget of the scratch: SGLANG_DSV4_FP4_BRIDGE_SCRATCH_MB MiB worth
    of 585 B/row V4 pages (37440 B per 64 rows)."""
    budget_bytes = max(16, _env_int(ENV_BRIDGE_SCRATCH_MB, 512)) * 1024 * 1024
    return budget_bytes // _DST_PAGE_BYTES * _DST_PAGE_SIZE


def bridge_slice_bounds(num_tokens: int, topk: int, max_rows: Optional[int] = None) -> List[int]:
    """Token boundaries of the query slices that keep one bridge gather within
    the scratch row budget. Always returns [0, num_tokens] (a single slice) for
    decode/verify-sized batches."""
    if max_rows is None:
        max_rows = bridge_max_rows()
    step = max(1, max_rows // max(1, topk))
    if step >= num_tokens:
        return [0, num_tokens]
    bounds = list(range(0, num_tokens, step))
    if bounds[-1] != num_tokens:
        bounds.append(num_tokens)
    return bounds


def repack_fp4_extra_to_v4(
    fp4_cache: torch.Tensor,
    indices: torch.Tensor,
    src_page_size: int,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Gather the batch's top-k slots of a V41_FP4 pool into a V4 scratch.

    Args:
        fp4_cache: the pool viewed (pages, src_page_size, 1, 288) uint8 (any
            view whose stride(0) is the padded page stride works).
        indices: (..., topk) int32/int64 slot ids into the pool. -1 (and any
            stale slot the kernel masks via topk_length) yields a zero row.
        src_page_size: tokens per pool page (256 for ratio-1, 128 for ratio-2).

    Returns:
        (scratch, bridged): ``scratch`` is a persistent (P, 64, 1, 584) uint8
        view, ``bridged`` the identity indices in ``indices``' shape; pass them
        to the attention kernel in place of the pool and its indices.
    """
    # The pool hands its uint8 buffer back as a model-dtyped (fp8) view;
    # same item size, so re-viewing is free.
    if fp4_cache.dtype != torch.uint8:
        assert fp4_cache.element_size() == 1, fp4_cache.dtype
        fp4_cache = fp4_cache.view(torch.uint8)
    assert src_page_size in (128, 256), f"unexpected fp4 pool page size {src_page_size}"
    assert indices.dtype in (torch.int32, torch.int64)
    num_pages = fp4_cache.shape[0]
    src_page_bytes = fp4_cache.stride(0)
    assert src_page_bytes >= src_page_size * (_SRC_DATA_BYTES + _SRC_SCALE_BYTES)

    flat_idx = indices.reshape(-1)
    if not flat_idx.is_contiguous():
        flat_idx = flat_idx.contiguous()
    if flat_idx.dtype != torch.int32:
        flat_idx = flat_idx.to(torch.int32)
    n = flat_idx.shape[0]
    assert n > 0

    dev = fp4_cache.device
    num_dst_pages = (n + _DST_PAGE_SIZE - 1) // _DST_PAGE_SIZE
    scratch = _persistent_buffer(
        f"dsv4_fp4_bridge_scratch:{dev}",
        (num_dst_pages, _DST_PAGE_BYTES),
        torch.uint8,
        dev,
    )
    # Identity bridged indices: gathered row j is addressed as slot j of the
    # pbs=64 scratch, for every (masked or not) slot position. Filled once at
    # allocation; CUDA graphs capture the buffer, not the fill.
    #
    # Keyed by device only, and used as a *prefix* of a grow-only buffer. The
    # fork's earlier version keyed it by (dev, n) and pushed one arange per
    # distinct row count into `resources.buffers`, which is never cleared; with
    # ragged batches n = tokens*topk takes a new value most steps, so every
    # distinct prefix shape (4096*512 = 2M rows => 8 MiB at int32) was retained
    # forever. A prefix of arange is arange, so one buffer + a prefix view is
    # exact.
    from sglang.srt.runtime_context import get_resources

    buffers = get_resources().buffers
    ids_key = f"dsv4_fp4_bridge_ids:{dev}"
    ids = _persistent_buffer(ids_key, (n,), torch.int32, dev)
    # `< n` holds only right after a (re)allocation -- the one moment the
    # contents need rebuilding; a cached prefix is already correct because that
    # fill covered the whole buffer.
    if buffers.get(ids_key + ":filled", 0) < n:
        torch.arange(n, dtype=torch.int32, device=dev, out=ids)
        buffers[ids_key + ":filled"] = n

    src_2d = fp4_cache
    if src_2d.ndim == 4:
        src_2d = torch.as_strided(
            fp4_cache,
            (num_pages, src_page_bytes),
            (src_page_bytes, 1),
            fp4_cache.storage_offset(),
        )
    src_u8 = src_2d.reshape(-1)
    src_fp8 = src_2d.view(fp8_dtype).reshape(-1)

    global _logged_activation, _active_backend
    mode, _requested = _repack_backend()
    if mode == "auto":
        min_n = _env_int(ENV_REPACK_CUDA_MIN_N, 2048)
        backend = "cuda" if n >= min_n else "triton"
    else:
        backend = mode
    _active_backend = backend
    src_page_bits = src_page_size.bit_length() - 1
    if not _logged_activation:
        _logged_activation = True
        shown = (
            f"auto(hybrid: cuda@n>={_env_int(ENV_REPACK_CUDA_MIN_N, 2048)}, else triton)"
            if mode == "auto"
            else backend
        )
        _logger.info(
            "DSV41 fp4->V4 repack bridge active (backend=%s, %s=%s): %d slots "
            "(%d pbs-64 pages, %.1f MiB scratch) from a %d-token-page fp4 pool",
            shown,
            ENV_REPACK_BACKEND,
            _requested,
            n,
            num_dst_pages,
            num_dst_pages * _DST_PAGE_BYTES / 2**20,
            src_page_size,
        )
    if backend == "cuda":
        _repack_cuda_lib().repack_fp4_to_v4(
            src_u8, src_fp8, flat_idx, scratch, src_page_bytes, src_page_bits
        )
    else:
        _repack_fp4_to_v4_kernel[(n,)](
            src_u8,
            src_fp8,
            flat_idx,
            scratch,
            src_page_bytes,
            SRC_PAGE_BITS=src_page_bits,
        )
    scratch_view = scratch.as_strided(
        (num_dst_pages, _DST_PAGE_SIZE, 1, _DST_BPT),
        (_DST_PAGE_BYTES, _DST_BPT, _DST_BPT, 1),
    )
    return scratch_view, ids.view(indices.shape)


def repack_fp4_extra_to_v4_ref(
    fp4_cache: torch.Tensor,
    indices: torch.Tensor,
    src_page_size: int,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Pure-torch reference of :func:`repack_fp4_extra_to_v4` for tests: same
    bytes, computed with vectorized indexing instead of the Triton kernel.
    Device-agnostic (CPU tensors work), which is what t44 uses offline."""
    assert fp4_cache.dtype == torch.uint8
    u8 = fp4_cache
    if u8.ndim == 4:
        u8 = torch.as_strided(
            fp4_cache,
            (u8.shape[0], u8.stride(0)),
            (u8.stride(0), 1),
            u8.storage_offset(),
        )
    page_bytes = u8.stride(0)
    scale_off = src_page_size * _SRC_DATA_BYTES

    loc = indices.reshape(-1).to(torch.int64)
    valid = loc >= 0
    safe = loc.clamp(min=0)
    page = safe // src_page_size
    slot = safe % src_page_size
    page_base = page * page_bytes
    data_base = page_base + slot * _SRC_DATA_BYTES
    scale_base = page_base + scale_off + slot * _SRC_SCALE_BYTES

    flat_u8 = u8.reshape(-1)
    flat_fp8 = u8.view(fp8_dtype).reshape(-1)

    def gather_rows(bases, count):
        offs = bases[:, None] + torch.arange(count, device=u8.device)[None, :]
        return flat_u8[offs]

    e2m1_lut = torch.tensor(
        [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0], dtype=torch.float32, device=u8.device
    )
    # Sign bit from bit 3 of the code, applied to the LUT magnitude.
    def decode(codes):  # codes: (N, 512) uint8 codes in [0, 16)
        vals = e2m1_lut[(codes & 7).to(torch.int64)]
        return vals * torch.where(codes >= 8, -1.0, 1.0)

    n = loc.shape[0]
    packed = gather_rows(data_base, _SRC_DATA_BYTES)  # (N, 256)
    codes = torch.empty((n, 512), dtype=torch.uint8, device=u8.device)
    codes[:, 0::2] = packed & 0xF
    codes[:, 1::2] = packed >> 4
    scales = (
        gather_rows(scale_base, _SRC_SCALE_BYTES)
        .view(fp8_dtype)
        .to(torch.float32)
        .repeat_interleave(_SRC_TILE, dim=1)
    )  # (N, 512)
    vals = decode(codes) * scales * valid[:, None].to(torch.float32)

    # V4 requant per production store.cuh.
    nope = vals[:, :_NOPE_VALUES]
    rope = vals[:, _NOPE_VALUES:]
    tiles = nope.view(n, _NOPE_VALUES // _NOPE_TILE, _NOPE_TILE)
    amax = tiles.abs().amax(dim=2)  # (N, 7)
    scale_raw = torch.maximum(amax, torch.full_like(amax, 1e-4)) / 448.0
    u = scale_raw.view(torch.int32)
    ue8m0 = ((u >> 23) & 0xFF) + (u & 0x7FFFFF != 0).to(torch.int32)  # (N, 7)
    inv = ((254 - ue8m0) << 23).view(torch.float32)  # exact powers of two
    fp8 = (tiles * inv[:, :, None]).reshape(n, _NOPE_VALUES).to(fp8_dtype)

    # Footer-format rows: 576 B data (448 fp8 nope + 128 B bf16 rope); the
    # ue8m0 footer lives in the per-page scale block, not inline.
    data = torch.zeros((n, _DST_DATA_BYTES), dtype=torch.uint8, device=u8.device)
    data[:, :_NOPE_VALUES] = fp8.view(torch.uint8)
    data[:, _NOPE_VALUES:] = rope.to(torch.bfloat16).view(torch.uint16).view(torch.uint8)

    # Scatter into footer-format pages: data at 576-pitch, contiguous scale
    # block at page offset 36864 (byte-identical to _split_kv_pages_to_64).
    num_dst_pages = (n + _DST_PAGE_SIZE - 1) // _DST_PAGE_SIZE
    scratch = torch.zeros(
        (num_dst_pages, _DST_PAGE_BYTES), dtype=torch.uint8, device=u8.device
    )
    rows = torch.arange(n, device=u8.device)
    dst_page = rows // _DST_PAGE_SIZE
    dst_slot = rows % _DST_PAGE_SIZE
    dst_data = dst_page * _DST_PAGE_BYTES + dst_slot * _DST_DATA_STRIDE
    scratch.view(-1)[
        dst_data[:, None] + torch.arange(_DST_DATA_BYTES, device=u8.device)[None, :]
    ] = data
    sfoot = torch.zeros((n, _DST_SCALE_STRIDE), dtype=torch.uint8, device=u8.device)
    sfoot[:, :7] = ue8m0.to(torch.uint8)
    dst_scale = (
        dst_page * _DST_PAGE_BYTES + _DST_SCALE_OFF + dst_slot * _DST_SCALE_STRIDE
    )
    scratch.view(-1)[
        dst_scale[:, None] + torch.arange(_DST_SCALE_STRIDE, device=u8.device)[None, :]
    ] = sfoot
    scratch_view = scratch.as_strided(
        (num_dst_pages, _DST_PAGE_SIZE, 1, _DST_BPT),
        (_DST_PAGE_BYTES, _DST_BPT, _DST_BPT, 1),
    )
    ids = torch.arange(n, dtype=torch.int32, device=u8.device).view(indices.shape)
    return scratch_view, ids


def summary() -> str:
    """One-line banner fact sheet (no GPU, no sglang import beyond this file)."""
    return (
        f"scratch_mb={_env_int(ENV_BRIDGE_SCRATCH_MB, 512)} "
        f"stats={_env_int(ENV_BRIDGE_STATS, 0)} "
        f"max_rows={bridge_max_rows()} "
        f"repack_backend={os.environ.get(ENV_REPACK_BACKEND) or 'auto'} "
        f"cuda_min_n={_env_int(ENV_REPACK_CUDA_MIN_N, 2048)} "
        f"src=288B dst=584B page=37440B"
    )
