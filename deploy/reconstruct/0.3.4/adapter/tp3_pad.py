"""Pad DeepSeek-V4.1 so TP=3 / EP=3 can load on 3 Sparks.

Checkpoint dims that do not divide 3:
  vocab 129280, heads 64, o_groups 8, dspark experts 128.
Pads: vocab via embedding pad_to=lcm(64,tp); heads 64→96 and groups 8→12
so local heads=32 (FlashInfer SM120 sparse-MLA only instantiates 8/16/32/64/128);
draft experts 128→129.
Checkpoint tensors are smaller; loaders copy the real slice and zero-pad.
"""
from __future__ import annotations

import logging
import math
import os

import torch

logger = logging.getLogger(__name__)


def _tp() -> int:
    return int(os.environ.get('TP_SIZE', os.environ.get('TP', '3')))


def enabled() -> bool:
    if os.environ.get('DSV41_TP_PAD', '1') in ('0', 'false', 'off'):
        return False
    return _tp() > 1


def _ceil_to(n: int, d: int) -> int:
    return ((n + d - 1) // d) * d


def _pad_fill(param) -> float:
    """Fill value for padded slices: 1.0 for fp32 block scales, 0 for weights."""
    return 1.0 if param.dtype == torch.float32 else 0.0


def pad_dsv41_hf_config(hf) -> None:
    if hf is None:
        return
    text = getattr(hf, 'text_config', None) or hf
    tp = _tp()
    heads = int(getattr(text, 'num_attention_heads', 0) or 0)
    groups = int(getattr(text, 'o_groups', 0) or 0)
    if heads and groups:
        per = max(heads // groups, 1)
        new_heads, new_groups = heads, groups
        if new_heads % tp:
            new_groups = _ceil_to(groups, tp)
            new_heads = new_groups * per
        # SM120 sparse-MLA kernels only exist for local head counts in this set.
        legal_local = (8, 16, 32, 64, 128)
        local = new_heads // tp
        if local not in legal_local:
            target_local = next((h for h in legal_local if h >= local), legal_local[-1])
            new_heads = target_local * tp
            new_groups = new_heads // per
            if new_groups * per != new_heads:
                new_groups = _ceil_to(new_groups, tp)
                new_heads = new_groups * per
        if new_heads != heads or new_groups != groups:
            text.o_groups = new_groups
            text.num_attention_heads = new_heads
            if hasattr(hf, 'num_attention_heads'):
                hf.num_attention_heads = new_heads
            logger.warning(
                'DSV41 TP pad: num_attention_heads %s→%s, o_groups %s→%s '
                '(tp=%s, local_heads=%s)',
                heads, new_heads, groups, new_groups, tp, new_heads // tp,
            )
    draft = int(getattr(text, 'dspark_n_routed_experts', 0) or 0)
    if draft and draft % tp:
        new_draft = _ceil_to(draft, tp)
        text.dspark_n_routed_experts = new_draft
        logger.warning(
            'DSV41 TP pad: dspark_n_routed_experts %s→%s (tp=%s)',
            draft, new_draft, tp,
        )
    vis = getattr(hf, 'vision_config', None)
    if vis is not None:
        vh = int(getattr(vis, 'num_attention_heads', 0) or getattr(vis, 'num_heads', 0) or 0)
        if vh and vh % tp:
            nv = _ceil_to(vh, tp)
            if hasattr(vis, 'num_attention_heads'):
                vis.num_attention_heads = nv
            if hasattr(vis, 'num_heads'):
                vis.num_heads = nv
            logger.warning('DSV41 TP pad: vision heads %s→%s', vh, nv)


def _install_vocab_pad() -> None:
    import sglang.srt.layers.vocab_parallel_embedding as vpe
    orig = vpe.pad_vocab_size

    def pad_vocab_size(vocab_size: int, pad_to: int = vpe.DEFAULT_VOCAB_PADDING_SIZE) -> int:
        tp = _tp()
        if tp > 1:
            pad_to = math.lcm(int(pad_to), tp)
        return orig(vocab_size, pad_to)

    vpe.pad_vocab_size = pad_vocab_size


def _install_config_pad() -> None:
    from sglang.srt.configs.model_config import ModelConfig
    orig = ModelConfig.__init__

    def wrapped(self, *args, **kwargs):
        orig(self, *args, **kwargs)
        try:
            pad_dsv41_hf_config(getattr(self, 'hf_config', None))
            text = getattr(getattr(self, 'hf_config', None), 'text_config', None)
            if text is not None:
                pad_dsv41_hf_config(text)
                if hasattr(self, 'hf_text_config') and self.hf_text_config is not None:
                    self.hf_text_config.num_attention_heads = int(text.num_attention_heads)
                    if hasattr(self.hf_text_config, 'o_groups'):
                        self.hf_text_config.o_groups = int(text.o_groups)
                if hasattr(self, 'num_attention_heads'):
                    self.num_attention_heads = int(text.num_attention_heads)
        except Exception:
            logger.exception('DSV41 TP config pad failed')

    ModelConfig.__init__ = wrapped


def _install_column_pad() -> None:
    from sglang.srt.layers.utils import pad_or_narrow_weight
    from sglang.srt.layers.parameter import _ColumnvLLMParameter
    from sglang.srt.layers.linear import ColumnParallelLinear

    orig_col = _ColumnvLLMParameter.load_column_parallel_weight

    def load_column_parallel_weight(self, loaded_weight, tp_rank, use_presharded_weights=False):
        if use_presharded_weights:
            return orig_col(self, loaded_weight, tp_rank, use_presharded_weights)
        shard_size = self.data.shape[self.output_dim]
        start = tp_rank * shard_size
        end = start + shard_size
        dim = self.output_dim
        if end > loaded_weight.shape[dim] or start >= loaded_weight.shape[dim]:
            real = max(0, loaded_weight.shape[dim] - start)
            loaded_weight = pad_or_narrow_weight(loaded_weight, dim, start, shard_size)
            if loaded_weight.dtype == torch.float32 and real < loaded_weight.shape[dim]:
                # block scales: the padded region must stay a positive power of two
                loaded_weight = loaded_weight.clone()
                loaded_weight.narrow(dim, real, loaded_weight.shape[dim] - real).fill_(1.0)
        else:
            loaded_weight = loaded_weight.narrow(dim, start, shard_size)
        if self.data.shape != loaded_weight.shape:
            # Padded rows of a weight are zero; padded rows of a block scale
            # (fp32) are 1.0 so they stay positive powers of two and the
            # MXFP8 re-encoding accepts the layer (0 * 1 is still 0).
            self.data.fill_(_pad_fill(self.data))
            # overlap copy if pad_or_narrow returned a short tensor
            slices = tuple(slice(0, min(a, b)) for a, b in zip(self.data.shape, loaded_weight.shape))
            self.data[slices].copy_(loaded_weight[slices])
            return
        self.data.copy_(loaded_weight)

    _ColumnvLLMParameter.load_column_parallel_weight = load_column_parallel_weight

    orig_lin = ColumnParallelLinear.weight_loader

    def column_weight_loader(self, param, loaded_weight):
        output_dim = getattr(param, 'output_dim', None)
        if (
            output_dim is not None
            and not getattr(param, 'use_bitsandbytes_4bit', False)
            and not getattr(self, 'use_presharded_weights', False)
        ):
            shard_size = param.data.shape[output_dim]
            start = self.tp_rank * shard_size
            end = start + shard_size
            if end > loaded_weight.shape[output_dim]:
                real = loaded_weight.shape[output_dim] - start
                loaded_weight = pad_or_narrow_weight(
                    loaded_weight, output_dim, start, shard_size
                )
                if loaded_weight.dtype == torch.float32 and 0 <= real < shard_size:
                    # block scales: padded region must stay a power of two
                    loaded_weight.narrow(output_dim, real, shard_size - real).fill_(1.0)
                if param.data.shape == loaded_weight.shape:
                    param.data.copy_(loaded_weight)
                    return
        return orig_lin(self, param, loaded_weight)

    ColumnParallelLinear.weight_loader = column_weight_loader


def _install_default_loader_pad() -> None:
    import sglang.srt.model_loader.weight_utils as wu
    orig = wu.default_weight_loader

    def default_weight_loader(param, loaded_weight):
        try:
            return orig(param, loaded_weight)
        except AssertionError:
            pdata = param.data
            pdata.zero_()
            if loaded_weight.numel() == 0:
                return
            slices = tuple(
                slice(0, min(a, b)) for a, b in zip(pdata.shape, loaded_weight.shape)
            )
            pdata[slices].copy_(loaded_weight[slices])

    wu.default_weight_loader = default_weight_loader


def _install_moe_padded_loading() -> None:
    try:
        from sglang.srt.layers.moe.fused_moe_triton.layer import FusedMoE
    except Exception:
        return
    orig = FusedMoE.use_padded_loading.fget if hasattr(FusedMoE.use_padded_loading, 'fget') else None

    def use_padded_loading(self) -> bool:
        if orig is not None and orig(self):
            return True
        return True

    try:
        FusedMoE.use_padded_loading = property(use_padded_loading)
    except Exception:
        logger.warning('could not force FusedMoE.use_padded_loading')


def install() -> None:
    if not enabled():
        return
    _install_vocab_pad()
    _install_config_pad()
    _install_column_pad()
    _install_default_loader_pad()
    _install_moe_padded_loading()
    logger.warning('DSV41 TP pad installed (tp=%s)', _tp())
