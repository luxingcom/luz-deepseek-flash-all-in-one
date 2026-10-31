"""fi_r1: R1-FP4KV fork python shell (LuZ-0.3.1 W3; design card
docs/research/R1-FP4KV-DESIGN-20261011.md sec 3.2-A / sec 3.8).

JIT module ``sparse_mla_sm120_fp4`` — an independent JitSpec over the fork's
two .cu sources, so:

  * the installed production flashinfer package is never touched (its
    data/include tree is consumed READ-ONLY as the stock-header provider,
    md5-anchored to the 0.6.16 reference set);
  * the JIT cache namespace is isolated (module name != ``sparse_mla_sm120``);
  * key-off makes the whole path disappear (bridge never imports this module).

Entry: ``r1_fp4kv_prefill`` — prefill-shaped DSV4 dual-cache call whose extra
cache is the raw 288B V41_FP4 pool + the ORIGINAL extra_indices /
extra_topk_length (no repack, no slicing, no identity indices). Outputs and
LSE are bit-equal to the in-service repack+stock-kernel path (V-A requant
replica; construction argument + host bit-equality matrix in t_r1_equiv.py).

Desk-boundary honesty: import of this module is host-safe (no CUDA touched);
the actual JIT build+load requires the production image (nvcc + tvm-ffi +
sm120 device), first build is minute-scale (design card sec 6-5).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

_logger = logging.getLogger(__name__)

_MODULE_NAME = "sparse_mla_sm120_fp4"
_HERE = Path(__file__).resolve().parent
_FORK_CSRC = [_HERE / "csrc" / "sparse_mla_sm120_fp4_jit_binding.cu",
              _HERE / "csrc" / "sparse_mla_sm120_prefill_fp4.cu"]

# Stock-header providers (read-only): the installed flashinfer package's
# data dirs. fi016 (0.6.16) anchors: sparse_mla_sm120_prefill.cu
# 561e114b..., prefill_kernel.cuh 03b668b3..., kv_cache_traits.cuh
# c15583ac... (T0 verified). The fork dir comes FIRST so the forked
# prefill_kernel_fp4.cuh + fp4_extra_traits.cuh win over any same-named
# stock file (there is none, but the order is load-bearing for future edits).
_FORK_INCLUDE = _HERE / "include"

_spec = None
_module = None
_load_error: Optional[str] = None


def _stock_include_roots():
    """(include_root, csrc_root) of the installed flashinfer package."""
    from flashinfer.jit import env as jit_env

    return jit_env.FLASHINFER_INCLUDE_DIR, jit_env.FLASHINFER_CSRC_DIR


def get_spec():
    """The JitSpec (constructed lazily; host-safe)."""
    global _spec
    if _spec is not None:
        return _spec
    from flashinfer.jit.core import gen_jit_spec
    from flashinfer.jit import env as jit_env
    # 布局漂移勘误（R1 窗 ae726e8）：容器 0.6.18 与案头 0.6.16 模块布局不同，
    # current_compilation_context 所在子模块以两形容错取用（皆无则 ImportError 直红）。
    try:
        from flashinfer.jit.core import current_compilation_context  # 0.6.18 容器布局
    except ImportError:
        from flashinfer.jit.compiler import current_compilation_context  # 0.6.16 案头锚布局

    # nvcc flag recipe = jit/mla.py:35-49 gen_sparse_mla_sm120_module
    # (supported_major_versions=[12] -> sm_120 family codegen).
    nvcc_flags = current_compilation_context.get_nvcc_flags_list(
        supported_major_versions=[12]
    )
    inc_root, csrc_root = _stock_include_roots()
    _spec = gen_jit_spec(
        _MODULE_NAME,
        list(_FORK_CSRC),
        extra_cuda_cflags=nvcc_flags,
        extra_include_paths=[
            _FORK_INCLUDE,
            inc_root,
            inc_root / "flashinfer" / "attention" / "sparse_mla_sm120",
            csrc_root,  # tvm_ffi_utils.h
        ],
    )
    return _spec


def get_module():
    """Build-and-load the fork module once (device host only); fail-loud."""
    global _module, _load_error
    if _module is not None:
        return _module
    if _load_error is not None:
        raise RuntimeError(_load_error)
    try:
        _module = get_spec().build_and_load()
        _logger.info(
            "fi_r1: fork module %s loaded (R1 fp4-extra in-kernel path armed)",
            _MODULE_NAME,
        )
        return _module
    except Exception as exc:  # noqa: BLE001 - caller falls back to the bridge
        _load_error = (
            f"fi_r1: fork JIT module {_MODULE_NAME} build/load failed: "
            f"{type(exc).__name__}: {exc}"
        )
        _logger.error(_load_error)
        raise RuntimeError(_load_error) from exc


def r1_fp4kv_prefill(
    q,                      # [num_tokens, num_heads, 512] bf16
    kv_cache,               # main V4 584B paged view (pbs=64 form)
    indices,                # [num_tokens, topk] int32 (-1 = skip)
    output,                 # [num_tokens, num_heads, 512] bf16, in-place
    out_lse,                # [num_tokens, num_heads] f32, in-place
    sm_scale: float,
    *,
    topk_length: Optional[object] = None,
    attn_sink: Optional[object] = None,
    extra_kv_cache=None,    # REQUIRED: 288B V41_FP4 pool view (pages, pbs, 1, 288)
    extra_indices=None,     # REQUIRED: [num_tokens, extra_topk] int32
    extra_topk_length: Optional[object] = None,
):
    """Prefill-shaped DSV4 dual-cache attention with the fp4 pool read in-kernel.

    Mirrors the stock ``_sparse_mla_sm120_paged_attention`` prefill call
    (flash_mla_sm120.py:246-260) with the extra tensors passed RAW (the
    binding derives pbs/stride from tensor metadata). Mutates ``output`` and
    ``out_lse`` in place.
    """
    if extra_kv_cache is None or extra_indices is None:
        raise ValueError("r1_fp4kv_prefill requires extra_kv_cache + extra_indices")
    mod = get_module()
    mod.sparse_mla_sm120_fp4_paged_attention(
        q,
        kv_cache,
        indices,
        output,
        out_lse,
        sm_scale,
        topk_length,
        attn_sink,
        extra_kv_cache,
        extra_indices,
        extra_topk_length,
    )


def summary() -> str:
    """Banner fact line (host-safe, no build)."""
    return (
        f"module={_MODULE_NAME} sources={len(_FORK_CSRC)}cu "
        f"fork_include={os.path.relpath(_FORK_INCLUDE, _HERE)} "
        f"state={'loaded' if _module is not None else ('error' if _load_error else 'unbuilt')}"
    )
