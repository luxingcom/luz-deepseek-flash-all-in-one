"""Route SGLang's block-fp8-as-MXFP8 dense linears to a FlashInfer backend that
suits GB10 (SM121).

SGLang's --fp8-gemm-backend only knows the cutlass / cute-dsl / trtllm MXFP8
kernels. The CUTLASS SM120 kernel uses a 128x32x128 tile: at M=6 (DSpark verify
at batch 1) it pads M to 128 and streams 32 weight columns per tile, which the
2026-09-10 profile measured at 50-75 GB/s on every projection (52 ms of a 118 ms
decode step, the same as the Triton kernel it replaced). FlashInfer's b12x
warp-level MMA kernel has 16|32 x 64|128 tiles for small M and is what
mm_mxfp8's own 'auto' heuristic prefers on SM120/121; 'cudnn' is the other
SM12x option. DSV41_MXFP8_BACKEND selects it (default b12x; 'cutlass' or ''
restores SGLang's choice). A shape the chosen backend rejects falls back to
cutlass for the rest of the process, logged once.
"""
import logging
import os

import torch

logger = logging.getLogger(__name__)

_REJECTED = set()


def install(module):
    want = os.environ.get('DSV41_MXFP8_BACKEND', 'b12x').strip()
    if want in ('', 'cutlass', 'off', '0'):
        return
    original = module.flashinfer_mxfp8_blockscaled_linear

    def linear(input, weight, weight_scale, input_scale=None, bias=None,
               output_dtype=None, backend='cutlass', pin_tactic=False):
        key = (int(weight.shape[0]), int(weight.shape[1]))
        if backend == 'cutlass' and key not in _REJECTED:
            try:
                return original(input, weight, weight_scale, input_scale, bias,
                                output_dtype, backend=want, pin_tactic=pin_tactic)
            except Exception as exc:  # shape/backend rejection: keep serving
                _REJECTED.add(key)
                logger.warning('DSV41 MXFP8 backend %r rejected N=%s K=%s (%s); '
                               'cutlass for this shape', want, key[0], key[1], exc)
        return original(input, weight, weight_scale, input_scale, bias,
                        output_dtype, backend=backend, pin_tactic=pin_tactic)

    module.flashinfer_mxfp8_blockscaled_linear = linear

    # TP=3 pads heads 64->96 and o_groups 8->12, so rank 2's wq_b / wo_b shards are
    # entirely padding: zero weights with zero block scales. A zero scale is not a
    # power of two, so block_fp8_scale_to_mxfp8_e8m0 raised and those 86 layers stayed
    # on the Triton kernel (22 ms/step on rank 2, the slowest rank). The fp8 values in
    # such blocks are zero, so any scale gives the same product; use 1.0 (e8m0 code 127).
    original_encode = module.block_fp8_scale_to_mxfp8_e8m0

    def encode(weight_scale, weight_shape, weight_block_size):
        scale = weight_scale.detach()
        if scale.numel() and bool((scale <= 0).any()):
            scale = torch.where(scale > 0, scale, torch.ones_like(scale))
        return original_encode(scale, weight_shape, weight_block_size)

    module.block_fp8_scale_to_mxfp8_e8m0 = encode
    logger.warning('DSV41 MXFP8 dense linears routed to FlashInfer backend %r '
                   '(zero block scales of padded shards encoded as 1.0)', want)


def _repair_padded_scales(layer, block_size):
    """Set every block scale that is not a positive power of two to 1.0 when its
    weight block is entirely zero (a TP-padded shard). Returns a diagnostic string
    for anything that was, or could not be, repaired; None when nothing was wrong."""
    ws = getattr(layer, 'weight_scale_inv', None)
    w = getattr(layer, 'weight', None)
    if ws is None or w is None or ws.data.ndim != 2:
        return None
    s = ws.data
    if s.dtype != torch.float32:
        return f'scale dtype {s.dtype} (not float32), left alone'
    f = s.contiguous()
    bits = f.view(torch.int32)
    bad = ~(((bits & 0x7FFFFF) == 0) & (f > 0))
    if not bool(bad.any()):
        return None
    n, k = w.shape
    bn, bk = block_size
    sn, sk = f.shape
    if n % bn or k % bk or sn != n // bn or sk != k // bk:
        return (f'{int(bad.sum())} bad scales but shape {tuple(w.shape)} / {tuple(f.shape)} '
                f'does not tile by {block_size}, left alone')
    zero = ((w.data.view(torch.uint8) & 0x7F) == 0).view(n // bn, bn, k // bk, bk).all(3).all(1)
    fix = bad & zero
    vals = f[bad][:4].tolist()
    if bool(fix.any()):
        f[fix] = 1.0
        s.copy_(f)
    return (f'{int(bad.sum())} invalid scales (e.g. {vals}), {int(fix.sum())} on all-zero '
            f'weight blocks set to 1.0, {int((bad & ~zero).sum())} on non-zero blocks left alone')


def install_fp8(module):
    """Hook Fp8LinearMethod._prepare_block_fp8_as_mxfp8 so padded shards pass the e8m0
    check whatever their (never written) scale memory holds, and log what was found."""
    if os.environ.get('DSV41_MXFP8_BACKEND', 'b12x').strip() in ('', 'cutlass', 'off', '0'):
        return
    cls = getattr(module, 'Fp8LinearMethod', None)
    if cls is None or not hasattr(cls, '_prepare_block_fp8_as_mxfp8'):
        logger.warning('DSV41: Fp8LinearMethod._prepare_block_fp8_as_mxfp8 not found; no scale repair')
        return
    original = cls._prepare_block_fp8_as_mxfp8

    def prepare(self, layer):
        try:
            note = _repair_padded_scales(layer, self.weight_block_size)
        except Exception as exc:  # never let diagnostics break loading
            note = f'repair failed: {exc}'
        if note:
            logger.warning('DSV41 block scales for %s: %s', getattr(layer, 'prefix', layer.__class__.__name__), note)
        return original(self, layer)

    cls._prepare_block_fp8_as_mxfp8 = prepare
    logger.warning('DSV41 padded-shard block-scale repair installed')
