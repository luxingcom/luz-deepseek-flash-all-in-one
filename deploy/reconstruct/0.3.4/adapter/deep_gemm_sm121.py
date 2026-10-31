"""Sparse-MQA DeepGEMM gate for SM120/121 (GB10) on main.

main-79cafec0's ``deep_gemm_wrapper.configurer`` computes::

    DEEPGEMM_BLACKWELL = ENABLE_JIT_DEEPGEMM and get_platform().is_sm100
    DEEPGEMM_PAGED_SPARSE_MQA_LOGITS = ... if not DEEPGEMM_BLACKWELL: False

so on GB10 (SM121) the DSV4.1 candidate indexer refuses to boot
(v41_indexer raises) even though the image's deep_gemm 0.2.0 exposes the
paged sparse MQA logits kernels -- SM120/121 support is exactly what
configurer's own ``_sm120_deep_gemm_apis_available()`` probe (DeepGEMM#324)
exists to vet. The fork's wrapper never had this gap.

This patch re-computes ONLY ``DEEPGEMM_PAGED_SPARSE_MQA_LOGITS`` with the
SM120/121 branch (same probe discipline as the stock function).
``DEEPGEMM_BLACKWELL`` itself is deliberately NOT touched: other consumers
key genuinely SM100-only behavior (TMEM paths) off it.

Gate: DSV41_DG_SPARSE_SM121=1 (off by default). Inert when the stock gate
already resolves True.
"""

import logging
import os

_logger = logging.getLogger(__name__)

GATE_ENV = "DSV41_DG_SPARSE_SM121"
_ON = ("1", "on", "true", "yes")
_INSTALLED = set()

_REQUIRED_APIS = (
    "get_paged_sparse_mqa_logits_metadata",
    "fp8_fp4_paged_sparse_mqa_logits",
)


def enabled() -> bool:
    return os.environ.get(GATE_ENV, "").strip().lower() in _ON


def _sm121_paged_sparse_ok(module) -> bool:
    """The stock _supports_paged_sparse_mqa_logits with the 120/121 branch."""
    if not getattr(module, "ENABLE_JIT_DEEPGEMM", False):
        return False
    try:
        sm = module.get_device_sm()
        if module.get_platform().is_sm100:
            gate = True
        elif sm in (120, 121):
            gate = module._sm120_deep_gemm_apis_available()
        else:
            gate = False
    except Exception as exc:  # probe failure == not available, same as stock
        _logger.warning("deep_gemm_sm121: platform probe failed: %s", exc)
        return False
    if not gate:
        return False
    try:
        import deep_gemm  # noqa: WPS433 (stock does the same)
    except (ImportError, OSError, RuntimeError):
        return False
    return all(callable(getattr(deep_gemm, name, None)) for name in _REQUIRED_APIS)


def install_memory_pool(module) -> bool:
    """Pin the indexer-K pool page to 64 once the sparse gate is open.

    main couples the pool page to the gate (dsv41_index_page_size: 128 when
    DEEPGEMM_PAGED_SPARSE_MQA_LOGITS else 64), but the dense metadata builder
    the boot path calls (metadata.py __post_init__ -> get_paged_mqa_logits_
    metadata) hard-asserts block_kv == 64 -- the fork's iron law. Opening the
    gate therefore also requires re-pinning the page, or every warmup/autotune
    forward dies at attention.hpp:438."""
    if not enabled() or module.__name__ in _INSTALLED:
        return False
    if not hasattr(module, "DSV41_INDEX_PAGE_SIZE"):
        _logger.warning("deep_gemm_sm121: memory_pool anchor missing; no pin")
        return False
    module.DSV41_INDEX_PAGE_SIZE = 64
    module.dsv41_index_page_size = lambda: 64
    _INSTALLED.add(module.__name__)
    _logger.info(
        "deep_gemm_sm121: indexer-K pool page pinned to 64 (block_kv iron law; "
        "main's gate-coupled 128 trips the dense metadata assert)"
    )
    return True


def install(module) -> bool:
    """Patch configurer.DEEPGEMM_PAGED_SPARSE_MQA_LOGITS for SM120/121."""
    if not enabled() or module.__name__ in _INSTALLED:
        return False
    if not all(
        hasattr(module, attr)
        for attr in (
            "DEEPGEMM_PAGED_SPARSE_MQA_LOGITS",
            "_sm120_deep_gemm_apis_available",
            "get_device_sm",
            "get_platform",
        )
    ):
        _logger.warning("deep_gemm_sm121: configurer anchors missing; no patch")
        return False
    orig = module.DEEPGEMM_PAGED_SPARSE_MQA_LOGITS
    if not orig:
        patched = _sm121_paged_sparse_ok(module)
        if patched:
            module.DEEPGEMM_PAGED_SPARSE_MQA_LOGITS = True
            _logger.info(
                "deep_gemm_sm121: DEEPGEMM_PAGED_SPARSE_MQA_LOGITS opened for "
                "SM120/121 (stock gate is sm100-only; kernels probed present)"
            )
        else:
            _logger.warning(
                "deep_gemm_sm121: SM121 probe found no sparse-MQA kernels; "
                "gate left at stock False (refusing to fake capability)"
            )
    _INSTALLED.add(module.__name__)
    return True


def summary() -> str:
    return (
        f"gate={os.environ.get(GATE_ENV, '(off)')} "
        f"installed={','.join(sorted(_INSTALLED)) or '(none)'}"
    )
