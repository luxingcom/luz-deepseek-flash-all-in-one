"""Hyper-connection mix statistics for prefill-size batches in one K walk (DSV41_HC_FUSED=1).

The engine computes the hc pre/post/comb coefficients with a split-K Triton kernel
(`_hc_mix_stats_partial_kernel`: 80 K slices of 256, one CTA per slice and row block, every
slice's [rows, 24] partial written to memory) and a reduce+sinkhorn kernel that sums the 80
partials in slice order. At prefill size (4096 rows) that is 1.48 ms per call on GB10, 86 calls
per forward: the partial round trip is 63 MB of extra traffic next to the 168 MB of activations.

Here one CTA walks all of K for its rows and keeps a running total, so no partials are stored.
It reproduces the stock result bit for bit:
  * each slice's partial starts from zero and accumulates the same 64-wide chunks in order;
    the slice totals are added in slice order starting from zero, which is the stock reduce;
  * tf32x3 on a bf16 activation: Triton splits both operands into tf32 big+small and issues
    dot(a_small, b_big, 0) -> dot(a_big, b_small, .) -> dot(a_big, b_big, .) + acc. A bf16 value
    is exactly representable in tf32, so a_small is 0 and the first dot is exactly +0; this kernel
    issues the other two dots in the same order (two MMAs per chunk instead of three);
  * the row sum of squares follows the stock kernel's reduction tree (lanes hold k % 32, xor
    butterfly 16..1, then the two warps holding k // 32), spelled out with length-2 sums so the
    layout Triton picks here does not matter;
  * sinkhorn is the stock `_hc_mix_reduce_sinkhorn_kernel`, fed one "slice" (the total).

Measured on GB10, CUDA graph of 43 layers, cold weights (rows: stock -> this, us per call):
512: 167 -> 161, 1024: 370 -> 250, 2048: 744 -> 421, 4096: 1482 -> 824. Below ~512 rows a
single CTA per row block is latency-bound (K walk of 320 chunks), so smaller batches (decode,
verify, draft) keep the stock kernels; DSV41_HC_FUSED_MIN_ROWS moves the cut.

Drift guard: the stock kernel sources, the slice/tile constants and the Triton version are
checked at install; any change raises (the exactness argument depends on all of them). The
first fused call in a process (outside CUDA graph capture) also runs the stock path on the same
inputs and permanently falls back to stock, loudly, if a single bit differs.
"""
import hashlib
import inspect
import logging
import os

import torch
import triton
import triton.language as tl

logger = logging.getLogger(__name__)

ENABLED = os.environ.get("DSV41_HC_FUSED", "0").strip() not in ("0", "", "off", "false")
MIN_ROWS = int(os.environ.get("DSV41_HC_FUSED_MIN_ROWS", "512"))

# sha256[:16] of the stock sources this kernel reproduces, Triton 3.7.1
# repinned 2026-10-01 for main-79cafece (H1 boot refusal ca7ec34b!=869788ff was the pin
# working as designed): drift = file moved to kernels/ops/layernorm/mhc.py + dormant
# part_mix_residual_ptr param (wrapper never passes it on CUDA; if a caller ever does the
# wrapper pin re-fires) + _is_hip branch. CUDA no-residual path bit-identical to old base;
# runtime first-call self-check vs stock remains the production-pair net.
_EXPECTED = {
    "_hc_mix_stats_partial_kernel": "ca7ec34b9be7abd7",
    "_hc_mix_reduce_sinkhorn_kernel": "8e9e13a25eb9885e",
    "hc_mix_stats_sinkhorn": "8ed53dab69e71a3d",
    "_num_slices_for": "23e78e75dc040b8e",
}
_TRITON = "3.7.1"
_K, _MIX, _HC, _BLOCK_K, _NUM_SLICES = 20480, 24, 4, 64, 80

_state = {"checked": False, "disabled": False}


@triton.jit
def _tf32_rna(x):
    # the rounding Triton's tf32x3 lowering uses for the "big" operand
    return tl.inline_asm_elementwise(
        "cvt.rna.tf32.f32 $0, $1;", "=r,r", [x], dtype=tl.float32, is_pure=True, pack=1
    )


@triton.jit
def _sq_tree(v, BLOCK_M: tl.constexpr):
    """Row sums of a [BLOCK_M, 64] tile in the stock reduction tree (see module docstring)."""
    t = tl.reshape(v, [BLOCK_M, 2, 2, 2, 2, 2, 2])  # k bits 5..0
    t = tl.sum(t, axis=2)  # xor 16
    t = tl.sum(t, axis=2)  # xor 8
    t = tl.sum(t, axis=2)  # xor 4
    t = tl.sum(t, axis=2)  # xor 2
    t = tl.sum(t, axis=2)  # xor 1
    return tl.sum(t, axis=1)  # the two warps


@triton.jit
def _hc_mix_fullk_kernel(
    x_ptr, w_ptr, mix_ptr, sq_ptr, M, x_stride_m, w_stride_n,
    K: tl.constexpr, MIX: tl.constexpr, MIX_PAD: tl.constexpr, NUM_SLICES: tl.constexpr,
    BLOCK_M: tl.constexpr, BLOCK_K: tl.constexpr,
):
    pid = tl.program_id(0)
    offs_m = pid * BLOCK_M + tl.arange(0, BLOCK_M)
    offs_n = tl.arange(0, MIX_PAD)
    mask_m = offs_m < M
    mask_n = offs_n < MIX
    KB: tl.constexpr = K // NUM_SLICES // BLOCK_K  # chunks per slice
    NCH: tl.constexpr = K // BLOCK_K
    acc = tl.zeros([BLOCK_M, MIX_PAD], dtype=tl.float32)
    tot = tl.zeros([BLOCK_M, MIX_PAD], dtype=tl.float32)
    sq = tl.zeros([BLOCK_M], dtype=tl.float32)
    sqt = tl.zeros([BLOCK_M], dtype=tl.float32)
    for i in range(NCH):
        offs_k = i * BLOCK_K + tl.arange(0, BLOCK_K)
        x_tile = tl.load(
            x_ptr + offs_m[:, None] * x_stride_m + offs_k[None, :],
            mask=mask_m[:, None], other=0.0,
        ).to(tl.float32)
        w_tile = tl.load(
            w_ptr + offs_n[None, :] * w_stride_n + offs_k[:, None],
            mask=mask_n[None, :], other=0.0,
        )
        w_big = _tf32_rna(w_tile)
        w_small = w_tile - w_big
        d = tl.dot(x_tile, w_small, input_precision="tf32")
        d = tl.dot(x_tile, w_big, d, input_precision="tf32")
        acc = acc + d
        sq += _sq_tree(x_tile * x_tile, BLOCK_M)
        last = (i % KB) == KB - 1
        tot = tl.where(last, tot + acc, tot)
        sqt = tl.where(last, sqt + sq, sqt)
        acc = tl.where(last, 0.0, acc)
        sq = tl.where(last, 0.0, sq)
    tl.store(mix_ptr + offs_m[:, None] * MIX + offs_n[None, :], tot,
             mask=mask_m[:, None] & mask_n[None, :])
    tl.store(sq_ptr + offs_m, sqt, mask=mask_m)


def _config_for(m):
    """(BLOCK_M, num_warps, num_stages), tuned on GB10; any choice gives the same bits."""
    if m <= 2048:
        return 16, 4, 4
    if m <= 3072:
        return 16, 4, 3
    return 32, 4, 3


def fused_mix_stats_sinkhorn(mod, x_flat, hc_fn, hc_scale, hc_base, hc_mult, sinkhorn_iters,
                             rms_eps, hc_eps):
    m, k = x_flat.shape
    mix = hc_fn.shape[0]
    dev = x_flat.device
    pre = torch.empty(m, hc_mult, dtype=torch.float32, device=dev)
    post = torch.empty(m, hc_mult, dtype=torch.float32, device=dev)
    comb = torch.empty(m, hc_mult, hc_mult, dtype=torch.float32, device=dev)
    mixes = torch.empty((1, m, mix), dtype=torch.float32, device=dev)
    sq = torch.empty((1, m), dtype=torch.float32, device=dev)
    block_m, num_warps, num_stages = _config_for(m)
    _hc_mix_fullk_kernel[(triton.cdiv(m, block_m),)](
        x_flat, hc_fn, mixes, sq, m, x_flat.stride(0), hc_fn.stride(0),
        K=k, MIX=mix, MIX_PAD=32, NUM_SLICES=_NUM_SLICES, BLOCK_M=block_m, BLOCK_K=_BLOCK_K,
        num_warps=num_warps, num_stages=num_stages,
    )
    mod._hc_mix_reduce_sinkhorn_kernel[(m,)](
        mixes, sq, hc_scale.float().contiguous(), hc_base.float().contiguous(),
        pre, post, comb, m, 1.0 / k, rms_eps,
        MIX=mix, HC=hc_mult, NUM_SLICES=1, ITERS=sinkhorn_iters, EPS=hc_eps, num_warps=1,
    )
    return pre, post, comb


try:  # prefill sequence parallel: row gates key on the full chunk row count (prefill_sp.py)
    from prefill_sp import sp_logical_rows as _logical_rows
except ImportError:  # pragma: no cover
    def _logical_rows(x):
        return x.shape[0]


def eligible(x_flat, hc_fn, hc_mult, min_rows=None):
    return (
        x_flat.dim() == 2
        and _logical_rows(x_flat) >= (MIN_ROWS if min_rows is None else min_rows)
        and x_flat.shape[1] == _K and x_flat.dtype == torch.bfloat16 and x_flat.stride(1) == 1
        and x_flat.is_cuda and hc_mult == _HC
        and hc_fn.shape == (_MIX, _K) and hc_fn.dtype == torch.float32 and hc_fn.stride(1) == 1
    )


def check_engine(mod):
    """Raise if anything the exactness argument relies on differs from the audited engine."""
    for name, want in _EXPECTED.items():
        obj = getattr(mod, name, None)
        if obj is None:
            raise RuntimeError(f"hc_fused: engine has no {name}")
        src = inspect.getsource(getattr(obj, "fn", obj))
        got = hashlib.sha256(src.encode()).hexdigest()[:16]
        if got != want:
            raise RuntimeError(f"hc_fused: engine source drifted ({name} {got} != {want})")
    consts = (mod._HC_MIX_BLOCK_K, mod._HC_MIX_DOT_PRECISION, mod._HC_MIX_NUM_WARPS,
              mod._num_slices_for(_K))
    if consts != (_BLOCK_K, "tf32x3", 4, _NUM_SLICES):
        raise RuntimeError(f"hc_fused: engine constants drifted {consts}")
    if triton.__version__ != _TRITON:
        raise RuntimeError(f"hc_fused: Triton {triton.__version__} != {_TRITON}; lowering unaudited")


def _self_check(stock, args):
    """First fused call: compare against stock on the same inputs; fall back for good on any bit."""
    _state["checked"] = True
    ref = stock(*args)
    got = fused_mix_stats_sinkhorn(_state["mod"], *args)
    if not all(torch.equal(a, b) for a, b in zip(ref, got)):
        _state["disabled"] = True
        logger.error("hc_fused: fused hc stats differ from stock on live inputs; using stock")
        print("DSV41 hc_fused: MISMATCH vs stock on first call, disabled", flush=True)
    else:
        print(f"DSV41 hc_fused: first call ({args[0].shape[0]} rows) bit-identical to stock", flush=True)
    return ref


def install(mod):
    """Patch sglang.kernels.ops.layernorm.mhc.hc_mix_stats_sinkhorn (callers import it per call)."""
    if not ENABLED:
        return
    check_engine(mod)
    stock = mod.hc_mix_stats_sinkhorn
    _state["mod"] = mod

    def hc_mix_stats_sinkhorn(x_flat, hc_fn, hc_scale, hc_base, hc_mult, sinkhorn_iters,
                              rms_eps, hc_eps):
        args = (x_flat, hc_fn, hc_scale, hc_base, hc_mult, sinkhorn_iters, rms_eps, hc_eps)
        if _state["disabled"] or not eligible(x_flat, hc_fn, hc_mult):
            return stock(*args)
        if not _state["checked"]:
            if torch.cuda.is_current_stream_capturing():
                return stock(*args)  # never capture an unchecked kernel
            return _self_check(stock, args)
        return fused_mix_stats_sinkhorn(mod, *args)

    hc_mix_stats_sinkhorn.__wrapped__ = stock
    mod.hc_mix_stats_sinkhorn = hc_mix_stats_sinkhorn
    print(f"DSV41 hc_fused: hc mix stats for >= {MIN_ROWS} rows in one K walk", flush=True)
