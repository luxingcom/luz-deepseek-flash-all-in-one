"""The DSpark draft's LM head from an fp8 copy of the (shared) target LM head. Default OFF.

TP4 variant of adapter/draft_head_fp8.py, selected with DSV41_DRAFT_HEAD_FP8=1 plus
DSV41_DRAFT_HEAD_FP8_IMPL=tp4 (the TP4 production profile). Same fp8 copy, row tiles sized to the
batch (see _TILES below); without the IMPL switch adapter/draft_head_fp8.py is used unchanged.

DSV41_DRAFT_HEAD_FP8=1. The draft borrows the target's vocab-parallel lm_head (bf16, 32320 x 5120
per rank at TP4) and reads it every step for its 5 block rows. Only the DRAFT gets the fp8 copy
(e4m3 + one power-of-two scale per 32x32 block): the target's logits, and therefore every accepted
token, are untouched. Offline the draft's acceptance moved 3.0882 -> 3.0875 tokens/step.
"""
import os

import torch
import triton
import triton.language as tl

ENABLED = os.environ.get("DSV41_DRAFT_HEAD_FP8", "0").strip() not in ("0", "", "off", "false")
# Draft head rows = DSPARK_BLOCK_SIZE (5) x decode bs: 5..80 on the bs <= 16 graph list. Row tiles cover
# the whole batch so the fp8 head is streamed once per call (16-row tiles re-read it per tile, which
# made M >= 40 slower than the bf16 head). Measured on Spark_04 (real head shard 32320 x 5120, us per
# call, CUDA graph; diagnostics/dsv41-moe-plan-table): M=5 721 (bf16 1374); M=40 16-row 2087 -> 794
# (bf16 1627); M=60 2824 -> 797 (bf16 1559); M=80 16-row 3593 -> 1138 (bf16 1566, today's fallback).
# Every tiling gives bit-identical fp32 logits per row (same K order, one tl.dot chain per row).
# Rows above 64 (bs 14 and 16) stay on the bf16 head as before: moving them to the fp8 copy changes the
# draft proposals there, and a fleet A/B showed no gain at c16 (the gain is at c4-c12, where the retiled
# kernel is bit-identical to the old one). DSV41_DRAFT_HEAD_FP8_MAX_M raises it (<= 128).
MAX_M = min(128, int(os.environ.get("DSV41_DRAFT_HEAD_FP8_MAX_M", "64")))
_TILES = ((16, 16, 256, 4, 3), (64, 64, 128, 4, 3), (128, 128, 64, 8, 3))   # max M, BM, BK, warps, stages
_TWIN = {}          # lm_head weight data_ptr -> (e4m3, exponent)


@triton.jit
def _head_fp8_kernel(X, W8, S, Y, M, N, K: tl.constexpr, BM: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr):
    pid = tl.program_id(0)
    m = tl.program_id(1) * BM + tl.arange(0, BM)
    n = pid * BN + tl.arange(0, BN)
    nmask = n < N
    acc = tl.zeros((BM, BN), tl.float32)
    for k0 in range(0, K, BK):
        k = k0 + tl.arange(0, BK)
        x = tl.load(X + m[:, None] * K + k[None, :], m[:, None] < M, 0.0)
        w8 = tl.load(W8 + n[None, :] * K + k[:, None], nmask[None, :], 0.0)
        e = tl.load(S + (n[None, :] // 32) * (K // 32) + k[:, None] // 32, nmask[None, :], 127)
        w = (w8.to(tl.float32) * tl.exp2(e.to(tl.float32) - 127.0)).to(tl.bfloat16)
        acc += tl.dot(x, w)
    tl.store(Y + m[:, None] * N + n[None, :], acc, (m[:, None] < M) & nmask[None, :])


def make_twin(w: torch.Tensor):
    """bf16 [N, K] -> (e4m3 [N, K], exponent uint8 [ceil(N/32), K/32]); lossy, draft-only."""
    n, k = w.shape
    pad = (-n) % 32
    wf = torch.nn.functional.pad(w.float(), (0, 0, 0, pad)).view((n + pad) // 32, 32, k // 32, 32)
    amax = wf.abs().amax(dim=(1, 3)).clamp_min(2.0 ** -126)
    e = torch.ceil(torch.log2(amax / 448.0)).clamp(-127, 127)
    q = (wf / torch.exp2(e)[:, None, :, None]).to(torch.float8_e4m3fn)
    return q.view(n + pad, k)[:n].contiguous(), (e + 127).to(torch.uint8).contiguous()


def head_fp8(x: torch.Tensor, twin) -> torch.Tensor:
    """x [M, K] bf16 (M <= MAX_M) -> fp32 logits [M, N]."""
    w8, s = twin
    m, k = x.shape
    n = w8.shape[0]
    y = torch.empty((m, n), dtype=torch.float32, device=x.device)
    # BN 32; M <= 16 keeps the M=5 tuning (BK 256, 4 warps, 3 stages = 230 GB/s of fp8)
    _, bm, bk, warps, stages = next(t for t in _TILES if m <= t[0])
    _head_fp8_kernel[(triton.cdiv(n, 32), triton.cdiv(m, bm))](x.contiguous(), w8, s, y, m, n, k, bm, 32, bk,
                                                              num_warps=warps, num_stages=stages)
    return y


def install(dspark_module):
    """sglang.srt.models.deepseek_v4_dspark: fp8 twin built when the target's lm_head is attached,
    used by _logits_from_x_post_hc for up to MAX_M rows; everything else is the stock path."""
    if not ENABLED:
        return
    cls = dspark_module.DeepseekV4ForCausalLMDSpark
    for name in ("attach_shared_modules", "_logits_from_x_post_hc"):
        if not hasattr(cls, name):
            raise RuntimeError(f"DSV41_DRAFT_HEAD_FP8: DeepseekV4ForCausalLMDSpark.{name} is gone; engine drifted")
    if getattr(cls, "_dsv41_draft_head_fp8", False):
        return
    cls._dsv41_draft_head_fp8 = True
    orig_attach = cls.attach_shared_modules
    orig_logits = cls._logits_from_x_post_hc
    gather = getattr(dspark_module, "gather_and_crop_vocab")

    def attach_shared_modules(self, *a, **kw):
        out = orig_attach(self, *a, **kw)
        w = getattr(self.lm_head, "weight", None)
        if w is not None and w.dtype == torch.bfloat16 and w.dim() == 2 and w.shape[1] % 32 == 0:
            _TWIN[w.data_ptr()] = make_twin(w.data)
            torch.cuda.empty_cache()          # the fp32 temporaries must not shrink the KV pool
            print(f"[draft_head_fp8] fp8 twin of the draft LM head {tuple(w.shape)}", flush=True)
        return out

    def _logits_from_x_post_hc(self, x_post_hc):
        w = getattr(self.lm_head, "weight", None)
        twin = None if w is None else _TWIN.get(w.data_ptr())
        if twin is None or x_post_hc.shape[0] > MAX_M or x_post_hc.shape[0] == 0:
            return orig_logits(self, x_post_hc)
        x = self.stages[-1].norm(x_post_hc)
        local = head_fp8(x.to(torch.bfloat16), twin).to(w.dtype)
        if self._opt_markov_w2_tp_shard:
            return local
        return gather(local, self.lm_head)

    cls.attach_shared_modules = attach_shared_modules
    cls._logits_from_x_post_hc = _logits_from_x_post_hc
    print("[draft_head_fp8] armed", flush=True)
