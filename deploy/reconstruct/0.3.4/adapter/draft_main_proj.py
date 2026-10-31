"""The DSpark draft's main_proj, column-split over the TP group. Default OFF.

Ported 2026-09-25 from knapcio's ``adapter/draft_main_proj.py`` (public repo snapshot), logic
verbatim. Their measurement, GB10 N=1280 K=20480: 124 us at M=6 against the stock replicated MXFP8
path's 430 us, i.e. -0.28 ms per step.

``DSV41_DRAFT_MAIN_PROJ_SPLIT=1``. stage0.main_proj (hidden*4 -> hidden, MXFP8) is a
ReplicatedLinear: every rank streams the whole 105 MB weight to compute the same [M, 5120] output.
Here each rank keeps only its 1280 output columns (e4m3 with the original per-row 32-element
power-of-two scales, so the weight bytes are the same values) and the columns are all-gathered.
Differences to the stock path: the activation stays bf16 instead of MXFP8, and the reduction order
is the Triton kernel's. Only the DRAFT changes, so every accepted token stays exact; acceptance is
what to watch. Rows above MAX_M (prefill extends) take the stock path.

The dequantized weight is read out of the layer itself (main_proj applied to identity rows is
exact), so nothing depends on the MXFP8 scale layout of the installed backend.

Our tree's seam, checked at bake time: ``deepseek_v4_dspark.DeepseekV4ForCausalLMDSpark`` with
``project_target_hidden`` (line 1077, body ``stage0.main_proj(main_hidden)`` + ``stage0.main_norm``)
and ``stages[0].main_proj`` built as a ReplicatedLinear (line 783).
"""
import os

import torch
import triton
import triton.language as tl

ENABLED = os.environ.get("DSV41_DRAFT_MAIN_PROJ_SPLIT", "0").strip() not in ("0", "", "off", "false")
MAX_M = int(os.environ.get("DSV41_DRAFT_MAIN_PROJ_MAX_M", "16"))
_S = {"twin": None, "shape": None}


@triton.jit
def _gemv_rowscale_kernel(X, W8, S, Y, M, N, K: tl.constexpr, BN: tl.constexpr, BK: tl.constexpr):
    n = tl.program_id(0) * BN + tl.arange(0, BN)
    m = tl.program_id(1) * 16 + tl.arange(0, 16)
    nmask = n < N
    acc = tl.zeros((16, BN), tl.float32)
    for k0 in range(0, K, BK):
        k = k0 + tl.arange(0, BK)
        x = tl.load(X + m[:, None] * K + k[None, :], m[:, None] < M, 0.0)
        w8 = tl.load(W8 + n[None, :] * K + k[:, None], nmask[None, :], 0.0)
        e = tl.load(S + n[None, :] * (K // 32) + k[:, None] // 32, nmask[None, :], 127)
        w = (w8.to(tl.float32) * tl.exp2(e.to(tl.float32) - 127.0)).to(tl.bfloat16)
        acc += tl.dot(x, w)
    tl.store(Y + m[:, None] * N + n[None, :], acc.to(tl.bfloat16), (m[:, None] < M) & nmask[None, :])


def gemv(x, twin):
    w8, s = twin
    m, k = x.shape
    n = w8.shape[0]
    y = torch.empty((m, n), dtype=torch.bfloat16, device=x.device)
    # GB10, N=1280 K=20480: BN 8 / BK 256 / 2 warps = 124 us at M=6 (stock replicated MXFP8: 430 us)
    _gemv_rowscale_kernel[(triton.cdiv(n, 8), triton.cdiv(m, 16))](x.contiguous(), w8, s, y, m, n, k, 8, 256,
                                                                  num_warps=2, num_stages=3)
    return y


def quant_rowscale(w):
    """bf16 [N, K] (values already on an e4m3 x 2^e grid per 32-block) -> (e4m3, biased exponent)."""
    n, k = w.shape
    wf = w.float().view(n, k // 32, 32)
    amax = wf.abs().amax(-1).clamp_min(2.0 ** -126)
    e = torch.ceil(torch.log2(amax / 448.0)).clamp(-127, 127)
    q = (wf / torch.exp2(e)[..., None]).to(torch.float8_e4m3fn)
    return q.view(n, k).contiguous(), (e + 127).to(torch.uint8).contiguous()


def _build(layer, group):
    k = layer.input_size if hasattr(layer, "input_size") else None
    w = getattr(layer, "weight", None)
    n = layer.output_size if hasattr(layer, "output_size") else w.shape[0]
    k = k or w.shape[1]
    world, rank = group.world_size, group.rank_in_group
    if n % world or k % 32:
        raise RuntimeError(f"main_proj {n}x{k} does not split over {world} ranks")
    dev = torch.device("cuda", torch.cuda.current_device())
    per = n // world
    cols = []
    step = 1024
    for k0 in range(0, k, step):
        c = min(step, k - k0)
        eye = torch.zeros((c, k), dtype=torch.bfloat16, device=dev)
        eye[torch.arange(c, device=dev), k0 + torch.arange(c, device=dev)] = 1.0
        out = layer(eye)
        out = out[0] if isinstance(out, tuple) else out
        cols.append(out[:, rank * per:(rank + 1) * per].to(torch.bfloat16))   # W[cols, k0:k0+c]^T
        del eye, out
    local = torch.cat(cols, 0).t().contiguous()                # [per, k]
    del cols
    twin = quant_rowscale(local)
    back = (twin[0].float().view(per, k // 32, 32) * torch.exp2(twin[1].float() - 127)[..., None]).view(per, k)
    exact = torch.equal(back.to(torch.bfloat16), local)
    del local, back
    torch.cuda.empty_cache()
    print(f"[draft_main_proj] rank {rank}: column shard {per}x{k} fp8 (weight bytes exact: {exact})", flush=True)
    return twin


def install(dspark_module) -> bool:
    """sglang.srt.models.deepseek_v4_dspark: DeepseekV4ForCausalLMDSpark.project_target_hidden."""
    if not ENABLED:
        return False
    cls = dspark_module.DeepseekV4ForCausalLMDSpark
    if not hasattr(cls, "project_target_hidden"):
        raise RuntimeError("DSV41_DRAFT_MAIN_PROJ_SPLIT: project_target_hidden is gone; engine drifted")
    if getattr(cls, "_dsv41_draft_main_proj", False):
        return False
    cls._dsv41_draft_main_proj = True
    orig = cls.project_target_hidden

    def project_target_hidden(self, main_hidden):
        m = main_hidden.shape[0]
        if m == 0 or m > MAX_M or main_hidden.dim() != 2:
            return orig(self, main_hidden)
        from sglang.srt.distributed import get_tp_group
        group = get_tp_group()
        if _S["twin"] is None:
            if torch.cuda.is_current_stream_capturing():
                return orig(self, main_hidden)
            # no per-rank fallback: a rank on the stock path would skip the all-gather and hang the
            # others, so a failed build fails the boot
            _S["twin"] = _build(self.stages[0].main_proj, group)
            _S["shape"] = tuple(_S["twin"][0].shape)
        local = gemv(main_hidden.to(torch.bfloat16), _S["twin"])
        projected = group.all_gather(local, dim=-1) if group.world_size > 1 else local
        return self.stages[0].main_norm(projected)

    cls.project_target_hidden = project_target_hidden
    print(f"[draft_main_proj] armed (rows <= {MAX_M})", flush=True)
    return True


def summary() -> str:
    return (f"gate={os.environ.get('DSV41_DRAFT_MAIN_PROJ_SPLIT', '(unset)')} armed={ENABLED}"
            f" shard={_S['shape']}")
