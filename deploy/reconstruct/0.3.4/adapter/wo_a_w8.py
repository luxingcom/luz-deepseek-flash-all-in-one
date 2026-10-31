"""wo_a from its fp8 checkpoint bytes instead of the bf16 copy, same Triton tiling. Gate DSV41_WO_A_W8.

v2 (D2, 2026-09-30) on top of the fin2 adapter ``wo_a_w8.py`` (knapcio's logic, ported verbatim):

1. ``_KERNEL_MODULES`` gains the main-79cafec0 location ``sglang.kernels.ops.gemm.dsv4_wo_a``
   (the wo_a kernels moved out of ``sglang.kernels.ops.attention.dsv4``; without this the
   adapter raises "engine drifted" the moment it is armed).
2. NEW M=1 GEMV W8 twin: SPEC=0 decode calls ``wo_a_bf16_gemv`` 39.9x/step at 70.4 us
   (16.8 MB bf16 pure DRAM wall, 2.811 ms/step = the bulk of the wo_a family). The twin
   ``_wo_a_gemv_w8_kernel`` keeps the stock kernel's tiling (one output row per CTA, grid
   (R, G), BN=1, fp32 math, ``enable_fp_fusion=False``) and rebuilds each bf16 weight in
   registers from the e4m3 byte and its ue8m0 exponent exactly the way the load-time
   dequant did: ``w = (w8.to(f32) * exp2(e - 127)).to(bf16)``. ``make_twin`` only accepts a
   twin whose dequantized copy is bit-identical to the engine's bf16 weight, so the in-register
   bf16 equals the stock kernel's loaded bf16 bit-for-bit and the fp32 sum runs the identical
   arithmetic on identical operands -> bit-exact output (same contract as the M2-8/MID twins).
   ``DSV41_WO_A_W8_GEMV=0`` disables just this arm (A/B during integration); default on.

Only shapes the twins reproduce exactly leave the stock path; every other shape and any
layer whose twin is not exact stays on bf16 (made/kept accounting in build_twins).
"""
import importlib
import os

import torch
import triton
import triton.language as tl

ENABLED = os.environ.get("DSV41_WO_A_W8", "0").strip() not in ("0", "", "off", "false")
GEMV = os.environ.get("DSV41_WO_A_W8_GEMV", "1").strip() not in ("0", "", "off", "false")
_TWINS = {}          # bf16 weight data_ptr -> (e4m3 [2,1024,4096], exponent uint8 [2,32,128])
_KERNEL_MODULES = ("sglang.kernels.ops.attention.dsv4.wo_a_bf16_small_batch",
                   "sglang.kernels.ops.attention.dsv4.wo_a_bf16",
                   "sglang.kernels.ops.gemm.dsv4_wo_a")


@triton.jit
def _wo_a_partial_w8(X, W8, S, P, M: tl.constexpr, SX: tl.constexpr):
    tile, group, split = tl.program_id(0), tl.program_id(1), tl.program_id(2)
    m = tl.arange(0, 16)
    n = tile * 64 + tl.arange(0, 64)
    k = split * 512 + tl.arange(0, 128)
    acc = tl.zeros((16, 64), tl.float32)
    for i in range(4):
        offsets = k + i * 128
        x = tl.load(
            X + m[:, None] * SX + group * 4096 + offsets[None, :], m[:, None] < M, 0
        )
        w8 = tl.load(W8 + (group * 1024 + n[None, :]) * 4096 + offsets[:, None])
        e = tl.load(S + (group * 32 + n[None, :] // 32) * 128 + offsets[:, None] // 32)
        w = (w8.to(tl.float32) * tl.exp2(e.to(tl.float32) - 127.0)).to(tl.bfloat16)
        acc += tl.dot(x, w)
    tl.store(
        P + ((split * M + m[:, None]) * 2 + group) * 1024 + n[None, :],
        acc,
        m[:, None] < M,
    )


@triton.jit
def _wo_a_gemv_w8_kernel(X, W8, S, Y, R: tl.constexpr, D: tl.constexpr, BN: tl.constexpr):
    """M=1 twin of dsv4_wo_a._wo_a_bf16_gemv_kernel: same grid (R, G), same BN=1 row/CTA tiling,
    same fp32 math and enable_fp_fusion=False; W is rebuilt in registers from e4m3 + ue8m0
    with the load-time dequant's exact rounding, so the arithmetic is bit-identical.

    The max_contiguous/multiple_of(8) hint on the column range is LOAD-BEARING for bit
    exactness, not a tuning knob: it caps the fp8/scale loads at 8 elements/thread, which is
    the vector width the stock kernel's bf16 row load gets (16B/thread). Without it the fp8
    row vectorizes to 16/thread and tl.sum switches to a 16-wide serial accumulation
    (TTGIR #blocked sizePerThread [1,16] vs the stock [1,8]) -- same values, different
    summation order, 1-ulp output flips (~17% of weights; see d2-dev/diag_variants.py).
    """
    group = tl.program_id(1)
    rows = tl.program_id(0) * BN + tl.arange(0, BN)
    columns = tl.max_contiguous(tl.multiple_of(tl.arange(0, D), 8), 8)
    x = tl.load(X + group * D + columns).to(tl.float32)
    # rows are always in [0, R): grid axis 0 == R with BN == 1, so the weight loads need no
    # mask (a masked fp8 load cannot take other=0 anyway; the M2-8 twin loads unmasked too).
    w8 = tl.load(W8 + (group * R + rows[:, None]) * D + columns[None, :])
    e = tl.load(
        S + (group * (R // 32) + rows[:, None] // 32) * (D // 32) + columns[None, :] // 32
    )
    w = (w8.to(tl.float32) * tl.exp2(e.to(tl.float32) - 127.0)).to(tl.bfloat16)
    result = tl.sum(w.to(tl.float32) * x[None, :], axis=1)
    tl.store(Y + group * R + rows, result, rows < R)


def _gemv_w8(x, twin):
    """x [1, G, D] bf16, twin (w8 e4m3 [G, R, D], exponent uint8 [G, R/32, D/32]) -> [1, G, R]."""
    w8, s = twin
    groups, rows, dim = w8.shape
    result = torch.empty((1, groups, rows), dtype=x.dtype, device=x.device)
    _wo_a_gemv_w8_kernel[(rows, groups)](
        x, w8, s, result, rows, dim, 1, num_warps=4, enable_fp_fusion=False
    )
    return result


def make_twin(w: torch.Tensor):
    """bf16 [2, 1024, 4096] -> (e4m3, exponent) or None if the twin does not reproduce w exactly."""
    g, r, d = w.shape
    wf = w.float().view(g, r // 32, 32, d // 32, 32)
    amax = wf.abs().amax(dim=(2, 4)).clamp_min(2.0 ** -126)
    e = torch.ceil(torch.log2(amax / 448.0)).clamp(-127, 127)
    scale = torch.exp2(e)[:, :, None, :, None]
    q = (wf / scale).to(torch.float8_e4m3fn)
    back = (q.float() * scale).to(torch.bfloat16).view(g, r, d)
    if not torch.equal(back, w):
        return None
    return q.view(g, r, d).contiguous(), (e + 127).to(torch.uint8).contiguous()


def _partial_w8(x, twin, m):
    w8, s = twin
    partial = torch.empty((8, m, 2, 1024), dtype=torch.float32, device=x.device)
    _wo_a_partial_w8[(16, 2, 8)](x, w8, s, partial, m, x.stride(0), num_warps=4, num_stages=3)
    return partial


MID = os.environ.get("DSV41_WO_A_W8_MID", "0").strip() not in ("0", "", "off", "false")
# tuned on GB10 with 43 distinct layers (DRAM-bound, not L2): rows -> (split_k, BM, BN, warps)
_MID_CFG = ((16, (4, 16, 64, 8)), (32, (2, 32, 32, 4)), (64, (1, 64, 32, 4)), (128, (1, 32, 64, 4)),
            (192, (1, 64, 32, 4)))


@triton.jit
def _wo_a_mid_kernel(X, W8, S, Y, M, SXM, SPLIT_K: tl.constexpr, BM: tl.constexpr, BN: tl.constexpr,
                     BK: tl.constexpr):
    pid_n = tl.program_id(0)
    g = tl.program_id(1)
    pid_mk = tl.program_id(2)
    pid_m = pid_mk // SPLIT_K
    pid_k = pid_mk % SPLIT_K
    m = pid_m * BM + tl.arange(0, BM)
    n = pid_n * BN + tl.arange(0, BN)
    KC: tl.constexpr = 4096 // SPLIT_K
    acc = tl.zeros((BM, BN), tl.float32)
    for k0 in range(pid_k * KC, (pid_k + 1) * KC, BK):
        k = k0 + tl.arange(0, BK)
        x = tl.load(X + m[:, None] * SXM + g * 4096 + k[None, :], m[:, None] < M, 0.0)
        w8 = tl.load(W8 + g * 1024 * 4096 + n[None, :] * 4096 + k[:, None])
        e = tl.load(S + g * 32 * 128 + (n[None, :] // 32) * 128 + k[:, None] // 32)
        w = (w8.to(tl.float32) * tl.exp2(e.to(tl.float32) - 127.0)).to(tl.bfloat16)
        acc += tl.dot(x, w)
    if SPLIT_K == 1:
        tl.store(Y + m[:, None] * 2048 + g * 1024 + n[None, :], acc.to(tl.bfloat16), m[:, None] < M)
    else:
        # per-split partials, summed in a fixed order afterwards (atomics made the order random)
        tl.store(Y + pid_k * M * 2048 + m[:, None] * 2048 + g * 1024 + n[None, :], acc, m[:, None] < M)


def wo_a_mid(o, twin):
    """o [M, 2, 4096] (stride (>=8192, 4096, 1)) bf16, 9 <= M <= 192 -> bf16 [M, 2, 1024]."""
    w8, s = twin
    m = o.shape[0]
    sk, bm, bn, warps = next(cfg for lim, cfg in _MID_CFG if m <= lim)
    grid = (1024 // bn, 2, triton.cdiv(m, bm) * sk)
    if sk == 1:
        y = torch.empty((m, 2, 1024), dtype=torch.bfloat16, device=o.device)
        _wo_a_mid_kernel[grid](o, w8, s, y, m, o.stride(0), 1, bm, bn, 128, num_warps=warps, num_stages=3)
        return y
    y = torch.empty((sk, m, 2, 1024), dtype=torch.float32, device=o.device)
    _wo_a_mid_kernel[grid](o, w8, s, y, m, o.stride(0), sk, bm, bn, 128, num_warps=warps, num_stages=3)
    return y.sum(dim=0).to(torch.bfloat16)


DROP = os.environ.get("DSV41_WO_A_W8_DROP", "0").strip() not in ("0", "", "off", "false")
_REFS = {}
_DROPPED = set()          # tag data_ptrs of wo_a weights whose bf16 storage was released
_COUNT = {"twins": 0, "kept": 0, "released": 0, "mid_armed": False, "gemv_calls": 0, "gemv_twin_calls": 0}


@triton.jit
def _dequant_kernel(W8, S, OUT):
    g = tl.program_id(0)
    rb = tl.program_id(1)
    cb = tl.program_id(2)
    r = rb * 32 + tl.arange(0, 32)
    c = cb * 32 + tl.arange(0, 32)
    off = g * 1024 * 4096 + r[:, None] * 4096 + c[None, :]
    e = tl.load(S + g * 32 * 128 + rb * 128 + cb)
    w = tl.load(W8 + off).to(tl.float32) * tl.exp2(e.to(tl.float32) - 127.0)
    tl.store(OUT + off, w.to(tl.bfloat16))


def dequant_into_scratch(twin, device):
    # a fresh buffer per call: the caching allocator orders reuse per stream, so target and draft
    # work on different streams never share it (one shared scratch raced)
    buf = torch.empty((2, 1024, 4096), dtype=torch.bfloat16, device=device)
    _dequant_kernel[(2, 32, 128)](twin[0], twin[1], buf)
    return buf


def drop_bf16(model):
    """After the twins exist: release the bf16 storage of every exactly-twinned wo_a. The weight
    becomes a zero-stride view of a 1-element tag (unique data_ptr, correct shape), and every call
    is served from the twin by the wrapper in install_mid."""
    freed = mismatched = 0
    for mod in model.modules():
        wo_a = getattr(mod, "wo_a", None)
        w = getattr(wo_a, "weight", None)
        if w is None or w.dtype != torch.bfloat16 or w.numel() != 2 * 1024 * 4096:
            continue
        old_ptr = w.data.view(2, 1024, 4096).data_ptr()
        twin = _TWINS.get(old_ptr)
        if twin is None:
            continue
        if not torch.equal(dequant_into_scratch(twin, w.device), w.data.view(2, 1024, 4096)):
            mismatched += 1
            continue                   # the stock path must see the identical bf16 weight
        del _TWINS[old_ptr]            # the freed address may be reused by another tensor
        tag = torch.zeros(1, dtype=torch.bfloat16, device=w.device)
        w.data = tag.as_strided(tuple(w.shape), (0,) * w.dim())
        _TWINS[tag.data_ptr()] = twin
        _DROPPED.add(tag.data_ptr())
        freed += 1
    torch.cuda.empty_cache()
    _COUNT["released"] = freed
    print(f"[wo_a_w8] released the bf16 copy of {freed} wo_a weights ({freed * 16.8:.0f} MB); "
          f"{mismatched} kept (dequantized copy not bit-identical)", flush=True)


def install_mid(dsv4_module):
    """deepseek_v4._apply_wo_a_bf16_matmul: 9..192 rows (verify/draft at c2..c32) from the fp8 twin."""
    if not (ENABLED and (MID or DROP)) or getattr(dsv4_module, "_dsv41_wo_a_mid", False):
        return
    dsv4_module._dsv41_wo_a_mid = True
    orig = dsv4_module._apply_wo_a_bf16_matmul

    swizzled = getattr(dsv4_module, "Mxfp8SwizzledInput", None)

    def _dropped_path(o, wo_a, twin, m, a, kw):
        std = (o.dtype == torch.bfloat16 and o.shape[1:] == (2, 4096) and o.stride(2) == 1
               and o.stride(1) == 4096 and o.stride(0) >= 8192)
        if std and m == 1 and GEMV:
            return _gemv_w8(o, twin)
        if std and 2 <= m <= 8:
            p = _partial_w8(o, twin, m)
            if kw.get("fuse_mxfp8_quant", False) and swizzled is not None:
                return swizzled(*_REFS["quantize_partial"](p))
            result = torch.empty((m, 2, 1024), dtype=o.dtype, device=o.device)
            _REFS["reduce_k"][(triton.cdiv(m * 2048, 256),)](p, result, m * 2048, num_warps=4)
            return result
        if std and 9 <= m <= 192 and kw.get("is_target_verify", False) and not kw.get("is_prefill", False):
            return wo_a_mid(o, twin)
        return orig(o, dequant_into_scratch(twin, o.device), *a, **kw)   # bit-identical bf16 weight

    def _apply_wo_a_bf16_matmul(o, wo_a, *a, **kw):
        m = o.shape[0]
        if _DROPPED and wo_a.data_ptr() in _DROPPED:
            return _dropped_path(o, wo_a, _TWINS[wo_a.data_ptr()], m, a, kw)
        if not MID:
            return orig(o, wo_a, *a, **kw)
        # verify/draft graphs only: prefill keeps the stock kernel (identical prefill numerics)
        if 9 <= m <= 192 and kw.get("is_target_verify", False) and not kw.get("is_prefill", False):
            twin = _TWINS.get(wo_a.data_ptr())
            if (twin is not None and o.dtype == torch.bfloat16 and o.shape[1:] == (2, 4096)
                    and o.stride(2) == 1 and o.stride(1) == 4096 and o.stride(0) >= 8192):
                return wo_a_mid(o, twin)
        return orig(o, wo_a, *a, **kw)

    dsv4_module._apply_wo_a_bf16_matmul = _apply_wo_a_bf16_matmul
    _COUNT["mid_armed"] = True
    print("[wo_a_w8] mid path armed: 9..192 rows from the fp8 twin", flush=True)


def _kernel_module():
    errors = []
    for name in _KERNEL_MODULES:
        try:
            return importlib.import_module(name)
        except ImportError as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("DSV41_WO_A_W8: no wo_a small-batch kernel module found; engine drifted ("
                       + "; ".join(errors) + ")")


def _patch_kernels(dsv4_module, kernel_module):
    for name in ("wo_a_bf16_small_batch", "wo_a_bf16_small_batch_mxfp8", "_wo_a_reduce", "_quantize_partial"):
        if not hasattr(kernel_module, name):
            raise RuntimeError(f"DSV41_WO_A_W8: {kernel_module.__name__}.{name} is gone; engine drifted")
    orig_small = kernel_module.wo_a_bf16_small_batch
    orig_mx = kernel_module.wo_a_bf16_small_batch_mxfp8
    reduce_k = kernel_module._wo_a_reduce
    quantize_partial = kernel_module._quantize_partial
    _REFS["reduce_k"], _REFS["quantize_partial"] = reduce_k, quantize_partial

    def small(x, weight):
        twin = _TWINS.get(weight.data_ptr())
        if twin is None:
            return orig_small(x, weight)
        m = x.shape[0]
        result = torch.empty((m, 2, 1024), dtype=x.dtype, device=x.device)
        reduce_k[(triton.cdiv(m * 2048, 256),)](_partial_w8(x, twin, m), result, m * 2048, num_warps=4)
        return result

    def small_mx(x, weight):
        twin = _TWINS.get(weight.data_ptr())
        if twin is None:
            return orig_mx(x, weight)
        return quantize_partial(_partial_w8(x, twin, x.shape[0]))

    kernel_module.wo_a_bf16_small_batch = small
    kernel_module.wo_a_bf16_small_batch_mxfp8 = small_mx
    # deepseek_v4 imported both names into its own namespace
    if getattr(dsv4_module, "wo_a_bf16_small_batch", None) is not orig_small or \
            getattr(dsv4_module, "wo_a_bf16_small_batch_mxfp8", None) is not orig_mx:
        raise RuntimeError("DSV41_WO_A_W8: deepseek_v4 no longer imports the wo_a small-batch kernels by name")
    dsv4_module.wo_a_bf16_small_batch = small
    dsv4_module.wo_a_bf16_small_batch_mxfp8 = small_mx

    # v2: the M=1 decode GEMV twin (SPEC=0 decode, 39.9 calls/step). The main tree moved the
    # kernel to this module and deepseek_v4.py imports it by name; rebind both, same pattern.
    orig_gemv = getattr(kernel_module, "wo_a_bf16_gemv", None)
    if orig_gemv is None:
        raise RuntimeError("DSV41_WO_A_W8: wo_a_bf16_gemv is gone from "
                           f"{kernel_module.__name__}; engine drifted")

    def gemv(x, weight):
        _COUNT["gemv_calls"] += 1
        twin = _TWINS.get(weight.data_ptr())
        if twin is None:
            return orig_gemv(x, weight)
        _COUNT["gemv_twin_calls"] += 1
        return _gemv_w8(x, twin)

    kernel_module.wo_a_bf16_gemv = gemv
    if hasattr(dsv4_module, "wo_a_bf16_gemv"):
        if dsv4_module.wo_a_bf16_gemv is not orig_gemv:
            raise RuntimeError("DSV41_WO_A_W8: deepseek_v4 no longer imports wo_a_bf16_gemv by name")
        dsv4_module.wo_a_bf16_gemv = gemv


def build_twins(model: torch.nn.Module) -> tuple[int, int]:
    made = kept = 0
    for mod in model.modules():
        w = getattr(getattr(mod, "wo_a", None), "weight", None)
        if w is None or w.dtype != torch.bfloat16 or w.numel() != 2 * 1024 * 4096:
            continue
        w3 = w.data.view(2, 1024, 4096)
        twin = make_twin(w3)
        if twin is None:
            kept += 1
            continue
        _TWINS[w3.data_ptr()] = twin
        made += 1
    _COUNT["twins"], _COUNT["kept"] = made, kept
    print(f"[wo_a_w8] fp8 twins for {made} wo_a weights, {kept} left on bf16", flush=True)
    return made, kept


def _wrap_load(cls):
    if getattr(cls, "_dsv41_wo_a_w8", False):
        return
    cls._dsv41_wo_a_w8 = True
    orig = cls.load_weights

    def load_weights(self, *a, **kw):
        out = orig(self, *a, **kw)
        build_twins(self)
        if DROP:
            drop_bf16(self)
        return out

    cls.load_weights = load_weights


def install_model(dsv4_module):
    """sglang.srt.models.deepseek_v4 (target model; also owns the wo_a dispatch the draft uses)."""
    if not ENABLED:
        return
    if getattr(dsv4_module, "_dsv41_wo_a_w8_installed", False):
        return
    dsv4_module._dsv41_wo_a_w8_installed = True
    _patch_kernels(dsv4_module, _kernel_module())
    install_mid(dsv4_module)
    _wrap_load(dsv4_module.DeepseekV4ForCausalLM)


def install_dspark(dspark_module):
    """sglang.srt.models.deepseek_v4_dspark: twins for the draft's three wo_a as well."""
    if ENABLED:
        _wrap_load(dspark_module.DeepseekV4ForCausalLMDSpark)


def summary() -> str:
    return (f"gate={os.environ.get('DSV41_WO_A_W8', '(unset)')} armed={ENABLED}"
            f" gemv={GEMV}(calls={_COUNT['gemv_calls']},twin={_COUNT['gemv_twin_calls']})"
            f" mid={MID} drop={DROP} twins={_COUNT['twins']} kept={_COUNT['kept']}"
            f" released={_COUNT['released']} mid_armed={_COUNT['mid_armed']}")
