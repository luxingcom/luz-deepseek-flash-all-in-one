"""Give a long prefill's transient memory back after every chunk.

Each 2048-token chunk of a DeepSeek-V4 prefill scores its queries against the whole
prefix so far: the indexer logits are a [chunk, prefix] fp32 buffer per low-ratio
source layer (deepseek_v4_backend: _dense_fp4_mqa_logits with max_seqlen_k = the
longest compressed length), plus candidate masks and top-k scratch of the same shape.
They are freed after the layer, but PyTorch's native caching allocator cannot serve
the next chunk's slightly larger request from the smaller cached block, so it
cudaMallocs a new one every chunk and reserved memory grows with the SQUARE of the
prompt (logs/profile-2026-09-10/REPORT.md sections 15 and 17). On a Spark that
reserved memory is host memory: a 34k-token prompt kept 1-1.5 GB, 64k exhausted the
head. expandable_segments would coalesce it but produces NaN logits on this stack.

This hook calls torch.cuda.empty_cache() after every extend forward whose longest
sequence is at least DSV41_PREFILL_EMPTY_CACHE_TOKENS (default 0 = disabled since
0.2.7; set 8192 to re-arm the pre-0.2.7 behaviour): the unused
cached blocks go back to the driver, the next chunk allocates fresh, and the peak is
one chunk's live set instead of the sum over chunks. Decode CUDA graphs live in
private pools and are untouched. Cost: one device sync and a few cudaMalloc/cudaFree
per long-prefill chunk (milliseconds against a 300-800 ms chunk). 0 disables it.
"""
import logging
import os

import torch

logger = logging.getLogger(__name__)


def install(module):
    # Default flipped to 0 in 0.2.7 (2026-09-21): on GB10's unified memory the
    # re-cudaMalloc tax costs ~2x on long-prefill tiers (F6 verdict), so the
    # hook is now opt-in. Prod sets the env explicitly in .env.tp4; the old
    # default '8192' silently re-armed it whenever EXTRA_DOCKER_ENV went missing.
    threshold = int(os.environ.get('DSV41_PREFILL_EMPTY_CACHE_TOKENS', '0'))
    if threshold <= 0:
        return
    cls = module.ModelRunner
    original = cls.forward

    def forward(self, forward_batch, *args, **kwargs):
        output = original(self, forward_batch, *args, **kwargs)
        try:
            if forward_batch.forward_mode.is_extend_without_speculative():
                lens = forward_batch.seq_lens_cpu
                longest = int(lens.max()) if lens is not None and lens.numel() else 0
                if longest >= threshold:
                    torch.cuda.empty_cache()
        except Exception as exc:  # bookkeeping must never break a forward
            logger.warning('DSV41 prefill empty_cache hook: %s', exc)
        return output

    cls.forward = forward
    logger.warning('DSV41 prefill empty_cache hook installed (extend forwards with a '
                   'sequence >= %d tokens)', threshold)
