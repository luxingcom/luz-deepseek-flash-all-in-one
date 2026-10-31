"""The DSpark draft's LM head from an fp8 copy of the (shared) target LM head. Default OFF.

Ported 2026-09-25 from knapcio's ``adapter/draft_head_fp8.py`` (public repo snapshot), logic
verbatim. Their measurement, GB10 at M=5: bf16 cuBLAS 1405 us -> 721 us for the draft's block
logits; offline acceptance moved 3.0882 -> 3.0875 tokens/step (draft-only, lossy by construction).

``DSV41_DRAFT_HEAD_FP8=1``. The draft borrows the target's vocab-parallel lm_head (bf16, 32320 x
5120 per rank at TP4) and reads it every step for its 5 block rows. Only the DRAFT gets the fp8
copy (e4m3 + one power-of-two scale per 32x32 block): the target's logits, and therefore every
accepted token, are untouched.

Our tree's seam, checked at bake time: ``deepseek_v4_dspark.DeepseekV4ForCausalLMDSpark`` with
``attach_shared_modules`` (line 1069), ``_logits_from_x_post_hc`` (1169, whose body reads
``self.stages[-1].norm`` and returns ``gather_and_crop_vocab(local_logits, self.lm_head)``, exactly
as this override assumes), the module-level ``gather_and_crop_vocab`` import (line 51) and
``self._opt_markov_w2_tp_shard`` (1061).
"""
import os

import torch
import triton
import triton.language as tl

ENABLED = os.environ.get("DSV41_DRAFT_HEAD_FP8", "0").strip() not in ("0", "", "off", "false")
MAX_M = 64
_TWIN = {}          # lm_head weight data_ptr -> (e4m3, exponent)
_COUNT = {"twin": None}


@triton.jit
def _head_fp8_kernel(X, W8, S, Y, M, N, K: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr):
    pid = tl.program_id(0)
    m = tl.program_id(1) * 16 + tl.arange(0, 16)
    n = pid * BN + tl.arange(0, BN)
    nmask = n < N
    acc = tl.zeros((16, BN), tl.float32)
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
    """x [M, K] bf16 (M <= 16) -> fp32 logits [M, N]."""
    w8, s = twin
    m, k = x.shape
    n = w8.shape[0]
    y = torch.empty((m, n), dtype=torch.float32, device=x.device)
    # tuned on GB10 at M=5: BN 32 / BK 256 / 4 warps / 3 stages = 230 GB/s of fp8 (bf16 cuBLAS: 1405 us -> 721 us)
    _head_fp8_kernel[(triton.cdiv(n, 32), triton.cdiv(m, 16))](x.contiguous(), w8, s, y, m, n, k, 32, 256,
                                                              num_warps=4, num_stages=3)
    return y


def install(dspark_module) -> bool:
    """sglang.srt.models.deepseek_v4_dspark: fp8 twin built when the target's lm_head is attached,
    used by _logits_from_x_post_hc for up to MAX_M rows; everything else is the stock path."""
    if not ENABLED:
        return False
    cls = dspark_module.DeepseekV4ForCausalLMDSpark
    for name in ("attach_shared_modules", "_logits_from_x_post_hc"):
        if not hasattr(cls, name):
            raise RuntimeError(f"DSV41_DRAFT_HEAD_FP8: DeepseekV4ForCausalLMDSpark.{name} is gone; engine drifted")
    if getattr(cls, "_dsv41_draft_head_fp8", False):
        return False
    cls._dsv41_draft_head_fp8 = True
    orig_attach = cls.attach_shared_modules
    orig_logits = cls._logits_from_x_post_hc
    gather = getattr(dspark_module, "gather_and_crop_vocab")

    def attach_shared_modules(self, *a, **kw):
        out = orig_attach(self, *a, **kw)
        w = getattr(self.lm_head, "weight", None)
        if w is not None and w.dtype == torch.bfloat16 and w.dim() == 2 and w.shape[1] % 32 == 0:
            _TWIN[w.data_ptr()] = make_twin(w.data)
            _COUNT["twin"] = tuple(w.shape)
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
    return True


def summary() -> str:
    return f"gate={os.environ.get('DSV41_DRAFT_HEAD_FP8', '(unset)')} armed={ENABLED} twin={_COUNT['twin']}"
