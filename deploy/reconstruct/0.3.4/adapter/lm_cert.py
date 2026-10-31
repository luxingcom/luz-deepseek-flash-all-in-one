"""Certified target LM head for DSpark verify: a 1-byte screen of the head, exact logits only
where the argmax can be. ADAPTER PORT DRAFT -- banner prefix [lm_cert].

STATUS: REVIEWED 2026-10-06 (dev/f6-impl/certhead_review_memo.md -- PASS, findings F-1..F-5),
pending main-session install authorization. Produced verbatim from d7-dev/cert_head_port.py by
dev/f6-impl/lm_cert_overlay.py (only this STATUS paragraph rewritten; the copy purity of the
remainder is asserted by sha256 at overlay time). knapcio's name: cert_head.py.
T4PW-20261007 AMENDMENT (C3A' gauge fix; L1F5-VERDICT-20261007 §3.3/§五): the DSV41_CERT_HEAD_DEBUG
first-fail tallies below are layered ON TOP of the reviewed 93496119 file; every numerical /
serve / table path is byte-identical (red-green tested in dev/t4-patch/test_lmcert_diag.py).
NOTE: regenerating via lm_cert_overlay.py --apply would revert this amendment (blueprint purity
asserts against d7-dev/cert_head_port.py); deploy this file whole or from .bak-pre-t4diag.
F5PRIME-20261007 AMENDMENT (PORT DELTA c; base a9891db3): the one serve-gate condition
`head_no_quant` is re-anchored from knapcio's `quant_method is None` to the engine's own
should_apply_lm_head_quant_method (logits_processor.py:135, captured at install; fail-loud on
drift). Root cause chain: main-79cafec0 VocabParallelEmbedding always sets quant_method =
UnquantizedEmbeddingMethod() on a plain bf16 head (vocab_parallel_embedding.py:299-318), so the
verbatim gate rejects EVERY head on this engine -- T4PW C3A' measured head_no_quant x6 with
M=6 + weight-ptr + all shapes passing (the only failing cond), i.e. the check-mode counters
are structurally unreachable with the verbatim gate. The delta serves exactly when stock
_compute_lm_head takes the plain torch.matmul branch the cert oracle replaces; numerics /
tables / predicate / all other conds byte-identical. Red-green: dev/f5prime/test_delta_c.py.

LINEAGE: knapcio v2.3 adapter/cert_head.py (github.com/knapcio/DeepSeek-V4.1-Flash-4x-DGX-
Spark-TP4 @ HEAD, raw-fetched 2026-09-30), re-targeted onto main-79cafec0. The table builder
carries the R1' corrections by lineage (knapcio's predicate + f64->f32->f16 up-rounding were
always correct; the flawed variants lived only in d7-dev/lm_cert.py and are fixed there --
docs/verdicts/B3-CERTHEAD-R1P-20261002.md, rechecked by d7-dev/r1_fix_recheck.py: unsafe 0
rows, rt 100% >= the float64 truth on the real rank-0 shard).

HOOK VERIFICATION (read-only docker inspect of 192.168.5.187:5000/lmsysorg/sglang:
main-79cafec0, 2026-10-02). Design-card (DESIGN.md §2) line numbers CONFIRMED -- ZERO DRIFT:

  layers/logits_processor.py:861   LogitsProcessor._get_logits(self, hidden_states, lm_head,
                                   logits_metadata: LogitsMetadata, embedding_bias=None,
                                   use_logits_buffer=True) -> torch.Tensor
      [PORT DELTA a: main passes a LogitsMetadata (class at :295, field forward_mode: ForwardMode
       :296; ForwardMode.is_target_verify at model_executor/forward_batch_info.py:255), not the
       fork's (forward_batch, return_logprob, ...) tuple]
  layers/logits_processor.py:955   LogitsProcessor._compute_lm_head(self, hidden_states,
                                   lm_head, embedding_bias=None); stock normal path is
                                   torch.matmul(hidden_states.to(w.dtype), w.T) (:1017-1019),
                                   fp32-head branch at :969/:1008, rl_on_policy_target at :996
  layers/logits_processor.py:135   should_apply_lm_head_quant_method(lm_head, quant_method)
  layers/logits_processor.py:450/453/458/469/480  logit_scale / use_fp32_lm_head /
                                   do_tensor_parallel_all_gather / final_logit_softcapping /
                                   rl_on_policy_target attributes (all read fail-closed below)
  models/deepseek_v4.py:4835/:5356 DeepseekV4ForCausalLM / load_weights(weights, is_nextn=False)
                                   [the is_nextn=True draft load must NOT trigger the build]
  models/deepseek_v4.py:4882-4893  self.lm_head (tied embed_tokens or ParallelLMHead) and
                                   self.logits_processor = LogitsProcessor(config)
  speculative/dspark_components/dspark_verify.py:105  class TargetVerifyExecutor
      :226 run_idle_participation(self, *, batch, idle_layout)
      :277 run_non_compact(self, *, batch, draft_input, verify_ids_2d, verify_window,
          sampling_info)   [keyword-only; the extra params ride the wrap's **kw]
      :436 run_compact(self, *, batch, layout, ...)   [keyword-only]
      :171/:752 fused_argmax consumption of the gathered logits (UNTOUCHED consumer face)
  layers/sampler.py:193            torch.argmax(logits, -1)  (UNTOUCHED consumer face)
  distributed/parallel_state.py:248/:666  GroupCoordinator / all_reduce
      [CORRECTION of DESIGN PORT DELTA b: main DOES carry cpu_group (:320/:423, asserted :427)
       -- the design card grepped for the fork's `cpu_comm` and found none. But main's
       GroupCoordinator.all_reduce is SUM-semantics on EVERY path (the shm branch hardcodes
       REDUCE_OP_SUM at :673; the pynccl / custom-AR / flashinfer tails take no ReduceOp at
       all), so the [failed, hash, -hash] agreement below must be an explicit
       torch.distributed.all_reduce(..., ReduceOp.MAX): gloo cpu_group with a CPU buffer
       (knapcio verbatim), NCCL device_group fallback with a CUDA buffer]

Mechanism (identical to d7-dev/lm_cert.py; the desk oracle + unit test live there):

  xnorm   per verify row x: ||x_g|| per 128-column group, ||x||, a non-finite flag; resets the
          row threshold T to the mapped-domain minimum.
  screen  s^ = x . D^T from an MXINT8 copy D of the shard (int8 + a power-of-two scale byte per
          32 weights of a row, ~173 MB/rank at 32320x5120) plus the rigorous bound
          B = (sum_g R_g ||x_g||) INFL_Q + 2 c_acc(K) ||x|| nv, with R_g = ||W_vg - D_vg||
          (table rt, rounded UP through f64->f32->f16) and nv = max(||W_v||, ||D_v||) rounded
          up; hi = rn_bf16(s^ + B + slop), lo = rn_bf16(s^ - B - slop); per-row T = max lo
          accumulated with an atomic max over the MONOTONE int mapping of fp32.
  refine  one CTA per 16 head rows: if the tile holds a token with hi >= T in ANY row (or the
          full flag is set, or a row is non-finite, or the token is a min_new_tokens stop id)
          the tile's logits are computed for every row with the exact kernel -- fp32 dot over
          the bf16 weights, K walked in one fixed order, one bf16 round at the end, claimed
          bit-identical to the stock matmul [U: never compiled on this stack; the check mode
          and the load-time gpu test are the verification]; every other token stays -inf.

The output replaces torch.matmul(x, W.T) inside LogitsProcessor._compute_lm_head: same shape,
same dtype, so the vocab all-gather, the fp32 logits buffer and the in-graph greedy accept run
unchanged. No host sync, graph-capturable; the collective sequence is the stock one on every
rank whatever each rank's candidates are.

Why the argmax is exact (four legs; desk-verified in d7-dev/test_lmcert_bitexact.py):
  [1] lo_v <= l_v <= hi_v (every rounding inflated up; the final bf16 cast is monotone RNE).
  [2] T = max lo <= max l; pruned tokens are STRICTLY below the max; maximisers always have
      hi >= T (equality possible on exact ties -- the reason the test is >=, not >).
  [3] masked argmax == stock argmax, ties included (first-occurrence semantics both sides).
  [4] per-TP-shard certificates compose through the stock all-gather.

Modes (tri-state gate, fail-closed):
  DSV41_CERT_HEAD=0|off   stock everywhere (default; the sitecustomize branch does not even
                          import this file unless the env is set)
  DSV41_CERT_HEAD=check   stock is served; the certified logits are ALSO computed (both flag
                          modes) and compared on device; FOUR mismatch counters -- argmax,
                          value-at-argmax, computed-tile, full-mode -- printed cumulatively
                          every DSV41_CERT_HEAD_LOG_EVERY verify steps (one host sync then)
  DSV41_CERT_HEAD=1       the certified (masked) logits are served on armed verify steps
  DSV41_CERT_HEAD_M=6     qualified verify row counts (fail-closed whitelist; default "6" =
                          SPEC=1 c1, stride 6 x bs 1; c8 is M=48 and deliberately absent)
  DSV41_CERT_HEAD_GROUP=128  residual-norm group width
  DSV41_CERT_HEAD_TILE=64,128,4,3    screen BN,BK,warps,stages (BM = next pow2 >= M, >= 16)
  DSV41_CERT_HEAD_EXACT=16,128,4,3   exact kernel BV,BK,warps,stages (BMX likewise)
  DSV41_CERT_HEAD_LOG_EVERY=200      check-mode counter print cadence (verify steps)
  DSV41_CERT_HEAD_DEBUG=1            C3A' diagnostic only (T4PW-20261007): when on, the serve
                          gate counts its FIRST failing condition (and the _get_logits entry
                          gate its first reject reason) and appends the tallies to every
                          LOG_EVERY counter line. Zero effect on any return value / serve
                          decision; NOT part of the TP config hash (print-only key).
All DSV41_CERT_HEAD* values must be identical on every TP rank (config hash MAX-all-reduced at
build; any difference or failed build disables the feature on every rank). Every unmet
precondition anywhere falls back to the untouched stock path (fail-closed).
"""
from __future__ import annotations

import hashlib
import os
import sys

import torch

_OFF = ("", "0", "off", "false", "no")
GROUP = int(os.environ.get("DSV41_CERT_HEAD_GROUP", "128"))
LOG_EVERY = int(os.environ.get("DSV41_CERT_HEAD_LOG_EVERY", "200") or 0)
# C3A' diagnostic (T4PW-20261007): print-only key -- counts the serve gate's FIRST failing
# condition and the _get_logits entry gate's first reject reason. Never gates any serve
# decision, never joins CONFIG_KEYS (the TP agreement hash), so a rank-symmetric boot with it
# set behaves exactly like one without (zero behavior change; asserted by the red-green test).
DEBUG = os.environ.get("DSV41_CERT_HEAD_DEBUG", "").strip().lower() not in _OFF
_st = [int(v) for v in os.environ.get("DSV41_CERT_HEAD_TILE", "64,128,4,3").split(",")]
SBN, SBK, SWARPS, SSTAGES = _st
_ex = [int(v) for v in os.environ.get("DSV41_CERT_HEAD_EXACT", "16,128,4,3").split(",")]
XBV, XBK, XWARPS, XSTAGES = _ex
MAX_M = 128
NSTOP = 64        # stop-id slots (min_new_tokens masks); more distinct stop ids -> full mode
CONFIG_KEYS = ("DSV41_CERT_HEAD", "DSV41_CERT_HEAD_M", "DSV41_CERT_HEAD_GROUP",
               "DSV41_CERT_HEAD_TILE", "DSV41_CERT_HEAD_EXACT")

# certificate constants (knapcio v2.3 verbatim; do not tune -- rounding inflators, not knobs)
INFL_Q = 1.0 + 2.0 ** -18
INFL_B = 1.0 + 2.0 ** -20
INFL_X = 1.0 + 2.0 ** -16
SLOP_REL = 2.0 ** -22
SLOP_ABS = 2.0 ** -126
X_ABS = 2.0 ** -59


def mode() -> str:
    """'0' | '1' | 'check' (tri-state; read once at import -- no in-boot A/B on this stack)."""
    v = str(os.environ.get("DSV41_CERT_HEAD", "0") or "0").strip().lower()
    if v in _OFF:
        return "0"
    return "check" if v == "check" else "1"


MODE = mode()


def enabled_anywhere() -> bool:
    """Install/build gate (the sitecustomize branch also checks the env before importing)."""
    return os.environ.get("DSV41_CERT_HEAD", "0").strip().lower() not in _OFF


def parse_m(spec: str) -> frozenset:
    out = set()
    for part in filter(None, (p.strip() for p in (spec or "").split(","))):
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if not 1 <= lo <= hi <= MAX_M:
            raise ValueError(f"DSV41_CERT_HEAD_M: bad entry {part!r} (1..{MAX_M})")
        out.update(range(lo, hi + 1))
    return frozenset(out)


# fail-closed M gate: default "6" = SPEC=1 c1 (stride 6, bs 1). c8 (M=48) is deliberately NOT
# qualified (upstream ">c8 slows down"); widen only per-M after a census A/B (QUALIFY.md).
QUALIFIED_M = parse_m(os.environ.get("DSV41_CERT_HEAD_M", "6"))


def c_acc(K: int) -> float:
    """ASSUMED tensor-core accumulation bound per unit of ||W_v|| ||x|| (Fasi et al. 2021)."""
    return (K / 16.0) * 17.0 * 2.0 ** -23


def config_hash(environ=None) -> int:
    environ = os.environ if environ is None else environ
    s = "|".join(f"{k}={environ.get(k, '')}" for k in CONFIG_KEYS)
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:7], "little")


def _log(msg: str) -> None:
    sys.stderr.write(f"[lm_cert] {msg}\n")
    sys.stderr.flush()


def next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


# ---------------------------------------------------------------------------------------------------
# tables (pure torch: CPU self-tests build them too). R1'-correct by lineage (knapcio verbatim):
# predicate = bf16-cast exactness of the raw int8*2^e product (0 unsafe rows on ANY weights),
# rt/nv rounded UP through f64 -> f32 -> f16 so every entry covers the float64 truth.
# ---------------------------------------------------------------------------------------------------
def _round_up_f32(x64: torch.Tensor) -> torch.Tensor:
    """float64 (>= 0 or inf) -> smallest fp32 >= x."""
    f = x64.float()
    bump = f.double() < x64
    return torch.where(bump, (f.view(torch.int32) + 1).view(torch.float32), f)


def _round_up_f16(x32: torch.Tensor) -> torch.Tensor:
    """fp32 (>= 0 or inf) -> smallest fp16 >= x (inf above the fp16 range)."""
    h = x32.half()
    bump = h.float() < x32
    return torch.where(bump, (h.view(torch.int16) + 1).view(torch.float16), h)


def make_mxint8(w: torch.Tensor, chunk_rows: int = 2048):
    """bf16 [V, K] -> (int8 [V, K], exponent byte uint8 [V, K/32]); scale 2**(e-127) >= amax/127."""
    V, K = w.shape
    q = torch.empty((V, K), dtype=torch.int8, device=w.device)
    e = torch.empty((V, K // 32), dtype=torch.uint8, device=w.device)
    for r0 in range(0, V, chunk_rows):
        r1 = min(V, r0 + chunk_rows)
        wf = w[r0:r1].float().view(r1 - r0, K // 32, 32)
        amax = wf.abs().amax(-1)
        ex = torch.where(amax > 0, torch.ceil(torch.log2(amax.clamp_min(1e-38) / 127.0)),
                         torch.zeros_like(amax))
        eb = (ex + 127.0).clamp(1.0, 254.0)
        qq = torch.round(wf / torch.exp2(eb - 127.0)[..., None]).clamp(-127, 127)
        q[r0:r1] = qq.view(r1 - r0, K).to(torch.int8)
        e[r0:r1] = eb.to(torch.uint8)
    return q, e


def deq_rows(q: torch.Tensor, e: torch.Tensor, r0: int, r1: int):
    """Rows r0:r1 of the screening copy as the screen kernel builds them: (bf16 values as fp32,
    raw fp32 products). The unsafe predicate compares exactly these two."""
    K = q.shape[1]
    qf = q[r0:r1].float()
    eb = e[r0:r1].to(torch.int32)
    sc = (eb << 23).view(torch.float32).repeat_interleave(32, dim=1)
    raw = qf * sc[:, :K]
    return raw.to(torch.bfloat16).float(), raw


class State:
    def __init__(self, **kw):
        self.__dict__.update(kw)


@torch.inference_mode()
def build_tables(W: torch.Tensor, group: int = GROUP) -> State:
    """State for one rank's head shard W [V, K] bf16. Raises ValueError on shape/dtype
    misfit or non-finite weights (the install layer catches both and stays on stock)."""
    V, K = W.shape
    if W.dtype != torch.bfloat16 or K % group or group % 32 or group & (group - 1) \
            or K % SBK or K % XBK:
        raise ValueError(f"head shard {tuple(W.shape)} {W.dtype} does not fit "
                         f"GROUP={group} / BK={SBK},{XBK}")
    q, e = make_mxint8(W)
    NG = K // group
    rt = torch.empty((NG, V), dtype=torch.float16, device=W.device)
    nv = torch.empty((V,), dtype=torch.float32, device=W.device)
    n_unsafe = 0
    for r0 in range(0, V, 1024):
        r1 = min(V, r0 + 1024)
        d_bf, d_raw = deq_rows(q, e, r0, r1)
        unsafe = (d_bf != d_raw).any(dim=1)  # the kernel's bf16 cast of a dequantised weight
        w64 = W[r0:r1].double()              # must be exact (always true: int8 fits 8 sig bits)
        res = (w64 - d_bf.double()).view(r1 - r0, NG, group)
        rg = _round_up_f32(res.pow(2).sum(-1).sqrt() * (1.0 + 2.0 ** -40))
        rg[unsafe] = float("inf")
        rt[:, r0:r1] = _round_up_f16(rg).t()
        nrm = torch.maximum(w64.norm(dim=1), d_bf.double().norm(dim=1)) * (1.0 + 2.0 ** -40)
        nv[r0:r1] = _round_up_f32(nrm)
        n_unsafe += int(unsafe.sum())
    if not bool(torch.isfinite(W).all()):
        raise ValueError("head shard has non-finite weights")
    d0, _ = deq_rows(q, e, 0, min(V, 4096))
    w0 = W[:d0.shape[0]].float()
    eps = float(((w0 - d0).norm(dim=1) / w0.norm(dim=1).clamp_min(1e-30)).mean())
    return State(W=W, q=q, e=e, rt=rt, nv=nv, V=V, K=K, group=group, n_unsafe=n_unsafe,
                 eps=eps, vstart=0)


# ---------------------------------------------------------------------------------------------------
# torch reference of the device pipeline (CPU self-tests)
# ---------------------------------------------------------------------------------------------------
def _bf16_down(x32: torch.Tensor) -> torch.Tensor:
    return x32.to(torch.bfloat16).float()


def reference_bounds(st: State, x: torch.Tensor, screen_acc=None, stop_ids=()):
    """-> (hi [M,V] fp32 holding bf16 values, T [M], bad [M]) exactly as xnorm + screen define."""
    M, K = x.shape
    G, NG = st.group, K // st.group
    xf = x.float()
    xg = xf.view(M, NG, G).pow(2).sum(-1).sqrt() * INFL_X + X_ABS
    xn = xg.pow(2).sum(-1).sqrt() * INFL_X
    bad = ~torch.isfinite(xn)
    if screen_acc is None:
        d_bf, _ = deq_rows(st.q, st.e, 0, st.V)
        screen_acc = xf @ d_bf.t()
    qb = xg @ st.rt.float()
    B = (qb * INFL_Q + 2.0 * c_acc(K) * (xn[:, None] * st.nv[None, :])) * INFL_B
    B = torch.where(torch.isnan(B), torch.full_like(B, float("inf")), B)
    slop = (screen_acc.abs() + B) * SLOP_REL + SLOP_ABS
    lo = _bf16_down(screen_acc - B - slop)
    hi = _bf16_down(screen_acc + B + slop)
    nonfin = ~torch.isfinite(screen_acc)
    lo = torch.where(nonfin | torch.isnan(lo), torch.full_like(lo, float("-inf")), lo)
    hi = torch.where(nonfin | torch.isnan(hi), torch.full_like(hi, float("inf")), hi)
    loc = [i - st.vstart for i in stop_ids if 0 <= i - st.vstart < st.V]
    if loc:
        lo[:, loc] = float("-inf")
        hi[:, loc] = float("inf")
    T = lo.max(dim=1).values
    return hi, T, bad


def reference_needed_tiles(hi, T, bad, full: bool, bv: int = XBV) -> torch.Tensor:
    """bool [ceil(V / bv)]: tiles the refine kernel computes (>= on purpose -- exact ties)."""
    M, V = hi.shape
    nt = (V + bv - 1) // bv
    if full or bool(bad.any()):
        return torch.ones(nt, dtype=torch.bool)
    cand = (hi >= T[:, None]).any(dim=0)
    pad = nt * bv - V
    if pad:
        cand = torch.cat([cand, torch.zeros(pad, dtype=torch.bool)])
    return cand.view(nt, bv).any(dim=1)


def reference_masked(exact_logits_bf16: torch.Tensor, needed: torch.Tensor,
                     bv: int = XBV) -> torch.Tensor:
    """The refine output given the exact logits [M, V] (bf16): exact on needed tiles."""
    M, V = exact_logits_bf16.shape
    col = needed.repeat_interleave(bv)[:V]
    out = exact_logits_bf16.clone()
    out[:, ~col] = float("-inf")
    return out


# ---------------------------------------------------------------------------------------------------
# Triton kernels (built on first use on the GPU; knapcio verbatim -- [U] never compiled here)
# ---------------------------------------------------------------------------------------------------
_K: dict = {}
_INTERP = os.environ.get("TRITON_INTERPRET", "0") == "1"


def _kernels():
    if _K:
        return _K
    import triton
    import triton.language as tl

    sqrt_rn = getattr(tl, "sqrt_rn", None)
    RN = sqrt_rn is not None

    @triton.jit
    def _xnorm_kernel(X, sx, XG, XN, BAD, THR, FLAG, K: tl.constexpr, G: tl.constexpr,
                      NGP: tl.constexpr, INFL: tl.constexpr, XABS: tl.constexpr,
                      RN: tl.constexpr):
        m = tl.program_id(0)
        if tl.load(FLAG) == 0:      # full mode: nothing to screen
            return
        NG: tl.constexpr = K // G
        gi = tl.arange(0, NGP)
        gok = gi < NG
        x = tl.load(X + m * sx + gi[:, None] * G + tl.arange(0, G)[None, :],
                    mask=gok[:, None], other=0.0).to(tl.float32)
        s = tl.sum(x * x, axis=1)
        if RN:
            xg = tl.sqrt_rn(s) * INFL + XABS
        else:
            xg = tl.sqrt(s) * INFL + XABS
        xg = tl.where(gok, xg, 0.0)
        tl.store(XG + m * NG + gi, xg, mask=gok)
        t = tl.sum(xg * xg, axis=0)
        if RN:
            xn = tl.sqrt_rn(t) * INFL
        else:
            xn = tl.sqrt(t) * INFL
        tl.store(XN + m, xn)
        bad = (xn != xn) | (xn == float("inf"))
        tl.store(BAD + m, bad.to(tl.int32))
        tl.store(THR + m, float("-inf"))

    @triton.jit
    def _screen_kernel(X, sx, Q, E, RT, NV, XG, XN, HI, THR, FLAG, STOP, vstart, M, V,
                       K: tl.constexpr, G: tl.constexpr, BM: tl.constexpr, BN: tl.constexpr,
                       BK: tl.constexpr, CACC2: tl.constexpr, INFL_Q: tl.constexpr,
                       INFL_B: tl.constexpr, SLOP_REL: tl.constexpr, SLOP_ABS: tl.constexpr,
                       NSTOP: tl.constexpr, IP: tl.constexpr):
        pid = tl.program_id(0)
        if tl.load(FLAG) == 0:
            return
        m = tl.arange(0, BM)
        n = pid * BN + tl.arange(0, BN)
        mok = m < M
        nok = n < V
        n64 = n.to(tl.int64)
        acc = tl.zeros((BM, BN), dtype=tl.float32)
        for k0 in range(0, K, BK):
            k = k0 + tl.arange(0, BK)
            x = tl.load(X + m[:, None] * sx + k[None, :], mask=mok[:, None], other=0.0)
            w = tl.load(Q + n64[None, :] * K + k[:, None], mask=nok[None, :], other=0)
            eb = tl.load(E + n64[None, :] * (K // 32) + k[:, None] // 32, mask=nok[None, :],
                         other=127)
            sc = (eb.to(tl.int32) << 23).to(tl.float32, bitcast=True)
            wd = (w.to(tl.float32) * sc).to(tl.bfloat16)
            if IP:   # Triton interpreter (CPU smoke): its bf16 dot is wrong; fp32 same values
                acc = tl.dot(x.to(tl.float32), wd.to(tl.float32), acc)
            else:
                acc = tl.dot(x, wd, acc)
        NG: tl.constexpr = K // G
        qb = tl.zeros((BM, BN), dtype=tl.float32)
        for g in range(0, NG):
            r = tl.load(RT + g * V + n, mask=nok, other=0.0).to(tl.float32)
            xg = tl.load(XG + m * NG + g, mask=mok, other=0.0)
            qb += xg[:, None] * r[None, :]
        nv = tl.load(NV + n, mask=nok, other=0.0)
        xn = tl.load(XN + m, mask=mok, other=0.0)
        B = (qb * INFL_Q + CACC2 * (xn[:, None] * nv[None, :])) * INFL_B
        B = tl.where(B != B, float("inf"), B)
        slop = (tl.abs(acc) + B) * SLOP_REL + SLOP_ABS
        lo = (acc - B - slop).to(tl.bfloat16).to(tl.float32)
        hi = (acc + B + slop).to(tl.bfloat16).to(tl.float32)
        nonfin = (acc != acc) | (tl.abs(acc) == float("inf"))
        lo = tl.where(nonfin | (lo != lo), float("-inf"), lo)
        hi = tl.where(nonfin | (hi != hi), float("inf"), hi)
        # stop ids (min_new_tokens may mask them after the head): never raise T, always exact
        gid = vstart + n
        isstop = tl.zeros((BN,), dtype=tl.int32)
        for j in tl.static_range(NSTOP):
            isstop = isstop | (gid == tl.load(STOP + j)).to(tl.int32)
        lo = tl.where(isstop[None, :] != 0, float("-inf"), lo)
        hi = tl.where(isstop[None, :] != 0, float("inf"), hi)
        ok = mok[:, None] & nok[None, :]
        tl.store(HI + m[:, None] * V + n[None, :], hi.to(tl.bfloat16), mask=ok)
        lof = tl.where(ok, lo, float("-inf"))
        tl.atomic_max(THR + m, tl.max(lof, axis=1), mask=mok)

    @triton.jit
    def _refine_kernel(X, sx, W, HI, THR, BAD, FLAG, OUT, so, NEED, M, V,
                       K: tl.constexpr, BV: tl.constexpr, BMX: tl.constexpr,
                       BK: tl.constexpr, IP: tl.constexpr):
        pid = tl.program_id(0)
        j = pid * BV + tl.arange(0, BV)
        ok = j < V
        mm = tl.arange(0, BMX)
        mok = mm < M
        full = tl.load(FLAG) == 0
        # in full mode xnorm / screen did not run: BAD / HI / THR hold stale values, `full`
        # decides alone
        bad = tl.max(tl.load(BAD + mm, mask=mok, other=0), axis=0)
        h = tl.load(HI + mm[:, None] * V + j[None, :], mask=mok[:, None] & ok[None, :],
                    other=float("-inf")).to(tl.float32)
        T = tl.load(THR + mm, mask=mok, other=float("inf"))
        hit = tl.max(tl.max((h >= T[:, None]).to(tl.int32), axis=1), axis=0)
        need = full | (hit > 0) | (bad > 0)
        if need:
            j64 = j.to(tl.int64)
            acc = tl.zeros((BV, BMX), dtype=tl.float32)
            for k0 in range(0, K, BK):
                k = k0 + tl.arange(0, BK)
                w = tl.load(W + j64[:, None] * K + k[None, :], mask=ok[:, None], other=0.0)
                xt = tl.load(X + mm[None, :] * sx + k[:, None], mask=mok[None, :], other=0.0)
                if IP:
                    acc = tl.dot(w.to(tl.float32), xt.to(tl.float32), acc)
                else:
                    acc = tl.dot(w, xt, acc)
            tl.store(OUT + mm[None, :] * so + j[:, None], acc.to(tl.bfloat16),
                     mask=ok[:, None] & mok[None, :])
            tl.atomic_add(NEED, 1)
        else:
            ninf = tl.full((BV, BMX), float("-inf"), tl.float32).to(tl.bfloat16)
            tl.store(OUT + mm[None, :] * so + j[:, None], ninf,
                     mask=ok[:, None] & mok[None, :])

    _K.update(triton=triton, xnorm=_xnorm_kernel, screen=_screen_kernel, refine=_refine_kernel,
              RN=RN)
    return _K


class Buffers:
    """Per-device persistent buffers, allocated outside any graph capture."""

    def __init__(self, device, max_m: int):
        self.flag = torch.zeros((1,), dtype=torch.int32, device=device)      # 0 full, 1 cert
        self.flag_host = 0
        self.stop = torch.full((NSTOP,), -1, dtype=torch.int32, device=device)  # -1 padded
        self.stop_host = ()
        self.need = torch.zeros((1,), dtype=torch.int32, device=device)      # tiles computed
        self.counters = torch.zeros((8,), dtype=torch.int64, device=device)  # check mode


def certified_logits(st: State, bufs: Buffers, x: torch.Tensor) -> torch.Tensor:
    """x [M, K] bf16 -> bf16 [M, V]: masked (flag 1) or full exact logits (flag 0). No host
    sync, graph-capturable."""
    k = _kernels()
    triton = k["triton"]
    x = x.contiguous()
    M, K = x.shape
    V = st.V
    dev = x.device
    NG = K // st.group
    xg = torch.empty((M, NG), dtype=torch.float32, device=dev)
    xn = torch.empty((M,), dtype=torch.float32, device=dev)
    bad = torch.empty((M,), dtype=torch.int32, device=dev)
    thr = torch.empty((M,), dtype=torch.float32, device=dev)
    hi = torch.empty((M, V), dtype=torch.bfloat16, device=dev)
    out = torch.empty((M, V), dtype=torch.bfloat16, device=dev)
    BM = max(16, next_pow2(M))
    k["xnorm"][(M,)](x, x.stride(0), xg, xn, bad, thr, bufs.flag, K=K, G=st.group,
                     NGP=next_pow2(NG), INFL=INFL_X, XABS=X_ABS, RN=k["RN"])
    k["screen"][(triton.cdiv(V, SBN),)](
        x, x.stride(0), st.q, st.e, st.rt, st.nv, xg, xn, hi, thr, bufs.flag, bufs.stop,
        st.vstart, M, V, K=K, G=st.group, BM=BM, BN=SBN, BK=SBK, CACC2=2.0 * c_acc(K),
        INFL_Q=INFL_Q, INFL_B=INFL_B, SLOP_REL=SLOP_REL, SLOP_ABS=SLOP_ABS, NSTOP=NSTOP,
        IP=_INTERP, num_warps=SWARPS if BM <= 32 else max(SWARPS, 8), num_stages=SSTAGES)
    k["refine"][(triton.cdiv(V, XBV),)](
        x, x.stride(0), st.W, hi, thr, bad, bufs.flag, out, out.stride(0), bufs.need, M, V,
        K=K, BV=XBV, BMX=max(16, next_pow2(M)), BK=XBK, IP=_INTERP, num_warps=XWARPS,
        num_stages=XSTAGES)
    return out


def _check(bufs: Buffers, stock: torch.Tensor, cert: torch.Tensor) -> None:
    """DSV41_CERT_HEAD=check: device-side comparison (graph-capturable, no host sync).
    counters: [steps, cert steps, ARGMAX mismatches, VALUE-at-argmax mismatches, TILE (computed
    logit) mismatches, FULL-mode logit mismatches, rows, -]. The four mismatch counters are the
    bit-equality gate of legs [2]/[3]/R2/R3; a nonzero count after soak = disable + verdict."""
    a = stock.float()
    b = cert.float()
    full = bufs.flag.to(torch.int64)[0] == 0
    ia, ib = a.argmax(dim=-1), b.argmax(dim=-1)
    va, vb = a.gather(-1, ia[:, None]), b.gather(-1, ib[:, None])
    arg_bad = (ia != ib).sum()
    val_bad = (va != vb).sum()
    computed = b != float("-inf")
    diff = (a != b) & computed
    comp_bad = diff.sum()
    full_bad = torch.where(full, (a != b).sum(), torch.zeros_like(comp_bad))
    one = torch.ones((), dtype=torch.int64, device=a.device)
    upd = torch.stack([one, (~full).to(torch.int64), arg_bad, val_bad, comp_bad, full_bad,
                       torch.full_like(one, a.shape[0]), torch.zeros_like(one)])
    bufs.counters.add_(upd)


# ---------------------------------------------------------------------------------------------------
# engine integration (three hook points; sitecustomize wiring drafted in DESIGN.md §8)
# ---------------------------------------------------------------------------------------------------
_S = {"st": None, "bufs": None, "lp": None, "why": "not built", "calls": 0, "verify_calls": 0,
      "armed_calls": 0, "logged_modes": set(),
      "entry_fail_first": {}, "serve_fail_first": {}}


def _rank() -> int:
    try:
        from sglang.srt.distributed import get_tensor_model_parallel_rank
        return int(get_tensor_model_parallel_rank())
    except Exception:  # noqa: BLE001
        return 0


def tp_agree(ok: bool):
    """(ok, why): MAX-all-reduce of (failed, hash, -hash) over the TP group; every rank calls it
    exactly once. MAIN CORRECTION (parallel_state.py:666 inspect 2026-10-02): GroupCoordinator
    .all_reduce is SUM on every path, so the reduce is issued explicitly with ReduceOp.MAX --
    on the gloo cpu_group with a CPU buffer (knapcio verbatim; main carries cpu_group at
    parallel_state.py:423/:427), falling back to the NCCL device_group with a CUDA buffer."""
    try:
        import torch.distributed as dist
        from sglang.srt.distributed import get_tp_group
        grp = get_tp_group()
        if grp.world_size == 1:
            return ok, "tp=1"
        h = config_hash()
        cpu_group = getattr(grp, "cpu_group", None)
        if cpu_group is not None:
            t = torch.tensor([0 if ok else 1, h, -h], dtype=torch.int64)
            dist.all_reduce(t, op=dist.ReduceOp.MAX, group=cpu_group)
        else:
            dev_group = getattr(grp, "device_group", None)
            if dev_group is None:
                return False, "TP coordinator has neither cpu_group nor device_group"
            t = torch.tensor([0 if ok else 1, h, -h], dtype=torch.int64, device="cuda")
            dist.all_reduce(t, op=dist.ReduceOp.MAX, group=dev_group)
        failed, hmax, hneg = (int(v) for v in t.tolist())
        if failed:
            return False, "a TP rank failed to build its tables"
        if hmax != -hneg:
            return False, "DSV41_CERT_HEAD* settings differ between TP ranks"
        return ok, "agreed"
    except Exception as e:  # noqa: BLE001
        return False, f"agreement failed: {e!r}"


def _build_for_model(model):
    """-> State or a human-readable refusal (fail-closed: every check below is a stock path)."""
    lm_head = getattr(model, "lm_head", None)
    lp = getattr(model, "logits_processor", None)
    W = getattr(lm_head, "weight", None)
    if lp is None or W is None:
        return "no lm_head / logits_processor"
    if W.dtype != torch.bfloat16 or W.dim() != 2 or not W.is_contiguous() or not W.is_cuda:
        return f"lm_head.weight is not a contiguous bf16 CUDA matrix ({W.dtype}, {tuple(W.shape)})"
    from sglang.srt.layers import logits_processor as lpm
    qm = getattr(lm_head, "quant_method", None)
    if lpm.should_apply_lm_head_quant_method(lm_head, qm):
        return f"lm_head uses a quant method ({type(qm).__name__})"
    if hasattr(lm_head, "set_lora"):
        return "LoRA lm_head"
    if getattr(lp, "use_fp32_lm_head", False):
        return "fp32 lm_head path"
    if getattr(lp, "rl_on_policy_target", None) is not None:
        return "rl-on-policy lm_head path (logits_processor.py:996 branch)"
    if getattr(lp, "logit_scale", None) is not None or \
            getattr(lp, "final_logit_softcapping", None) is not None:
        return "logit scale / softcapping"
    if not QUALIFIED_M:
        return "DSV41_CERT_HEAD_M is empty: stock everywhere"
    try:
        st = build_tables(W.data)
    except ValueError as e:
        return str(e)
    st.lm_head = lm_head
    st.lp = lp
    st.w_ptr = W.data_ptr()          # staleness tripwire: a swapped weight fails the serve gate
    si = getattr(lm_head, "shard_indices", None)
    st.vstart = int(getattr(si, "org_vocab_start_index", 0)) if si is not None else 0
    return st


def install_model(dsv4_module):
    """Hook 1 -- sglang.srt.models.deepseek_v4: tables built after the TARGET's weights load.
    Install AFTER wo_a_w8's wrap of the same method (sitecustomize order: this file's branch
    entry goes at the END of the deepseek_v4 elif, so this wrapper is OUTERMOST and its build
    reads the final post-load weights). Each wrap keeps its own marker; they compose."""
    if not enabled_anywhere():
        return
    cls = getattr(dsv4_module, "DeepseekV4ForCausalLM", None)
    if cls is None:
        raise RuntimeError("lm_cert: DeepseekV4ForCausalLM is gone; engine drifted")
    if getattr(cls, "_dsv41_lm_cert", False):
        return
    cls._dsv41_lm_cert = True
    orig = cls.load_weights

    def load_weights(self, *a, **kw):
        out = orig(self, *a, **kw)
        # only the TARGET instance, once; the is_nextn=True draft load never builds
        if type(self) is not cls or _S["lp"] is not None or kw.get("is_nextn") \
                or (len(a) >= 2 and a[1]):
            return out
        try:
            st = _build_for_model(self)
        except Exception as e:  # noqa: BLE001  never take the boot down; stock stays
            st = f"build failed: {e!r}"
        ok, why = tp_agree(isinstance(st, State))
        if not ok:
            _S["why"] = st if isinstance(st, str) else f"disabled on every rank: {why}"
            _log(f"DISABLED ({_S['why']})")
            torch.cuda.empty_cache()
            return out
        _S["st"], _S["lp"] = st, st.lp
        _S["bufs"] = Buffers(st.W.device, MAX_M)
        _S["bufs"].need_per_full = (st.V + XBV - 1) // XBV
        torch.cuda.empty_cache()
        mb = (st.q.numel() + st.e.numel() + st.rt.numel() * 2 + st.nv.numel() * 4) / 1e6
        _log(f"built on rank {_rank()}: MXINT8 copy of the {st.V} x {st.K} head shard "
             f"({mb:.1f} MB read per step vs {st.V * st.K * 2 / 1e6:.1f} MB bf16), "
             f"eps {st.eps * 100:.3f}%, unsafe rows {st.n_unsafe}, "
             f"qualified M {sorted(QUALIFIED_M)} ({why})")
        return out

    cls.load_weights = load_weights
    _log(f"armed (mode {MODE}, qualified M {sorted(QUALIFIED_M) or 'none'})")


_SERVE_CONDS = (
    # The reviewed 93496119 boolean chain, one named predicate per line, SAME order / SAME
    # short-circuit semantics (C3A' T4PW-20261007): the loop below evaluates them in order and
    # stops at the first False -- exactly the original `and` chain -- so the return value is
    # bit-identical; only the first failure now becomes observable (DEBUG-gated count).
    ("st_built",       lambda ctx: ctx["st"] is not None),
    ("mark_on",        lambda ctx: ctx["mark_on"]),
    ("bias_none",      lambda ctx: ctx["embedding_bias"] is None),
    ("mode_on",        lambda ctx: MODE != "0"),
    ("m_qualified",    lambda ctx: ctx["M"] in QUALIFIED_M),
    ("hs_2d",          lambda ctx: ctx["hidden_states"].dim() == 2),
    ("head_w_ptr",     lambda ctx: ctx["w"] is not None and ctx["w"].data_ptr() == ctx["st"].w_ptr),
    ("head_w_bf16c",   lambda ctx: ctx["w"] is not None and ctx["w"].dtype == torch.bfloat16
                       and ctx["w"].is_contiguous()),
    ("hs_bf16",        lambda ctx: ctx["hidden_states"].dtype == torch.bfloat16),
    ("hs_k",           lambda ctx: ctx["hidden_states"].shape[1] == ctx["st"].K),
    ("hs_stride1",     lambda ctx: ctx["hidden_states"].stride(-1) == 1),
    ("lp_do_tp_ag",    lambda ctx: bool(getattr(ctx["lp"], "do_tensor_parallel_all_gather", False))),
    ("lp_not_ag_dpattn", lambda ctx: not getattr(ctx["lp"], "do_tensor_parallel_all_gather_dp_attn", False)),
    ("lp_not_tpmhead_a2a", lambda ctx: not getattr(ctx["lp"], "use_tp_lm_head_all_to_all", False)),
    ("lp_not_fp32head",   lambda ctx: not getattr(ctx["lp"], "use_fp32_lm_head", False)),
    ("lp_no_rl_on_policy", lambda ctx: getattr(ctx["lp"], "rl_on_policy_target", None) is None),
    ("lp_no_logit_scale",  lambda ctx: getattr(ctx["lp"], "logit_scale", None) is None),
    ("lp_no_softcap",      lambda ctx: getattr(ctx["lp"], "final_logit_softcapping", None) is None),
    # PORT DELTA c (F5PRIME-20261007): knapcio's `quant_method is None` is structurally
    # unsatisfiable on main-79cafec0 -- VocabParallelEmbedding.__init__ ALWAYS sets
    # quant_method (UnquantizedEmbeddingMethod() for a plain bf16 head,
    # vocab_parallel_embedding.py:299-318), and T4PW C3A' measured exactly this:
    # head_no_quant x6 with M=6 + weight-ptr + all shapes passing. The stock
    # _compute_lm_head dispatches on should_apply_lm_head_quant_method
    # (logits_processor.py:135), which whitelists Unquantized* method names and so
    # takes the plain torch.matmul branch the cert replaces. Serve iff stock would
    # NOT apply a quant method -- read off the engine's own predicate, captured at
    # install; missing symbol = engine drift = refuse boot (fail-loud family law).
    ("head_no_quant",      lambda ctx: not _stock_quant_applies(ctx["lm_head"])),
    ("head_no_lora",       lambda ctx: not hasattr(ctx["lm_head"], "set_lora")),
)


def _stock_quant_applies(lm_head) -> bool:
    """PORT DELTA c: True iff the STOCK LogitsProcessor._compute_lm_head would dispatch to
    quant_method.apply(lm_head, ...) instead of the plain weight matmul the cert replaces
    (LoRA / no-weight / GGUF corners are covered by the neighbouring conds + stock's own
    ordering). Uses the engine's own should_apply_lm_head_quant_method captured at install;
    not captured (self-test without engine) -> fail-closed True (never serve)."""
    fn = _S.get("sqm")
    if fn is None:
        return True
    qm = getattr(lm_head, "quant_method", None)
    return bool(fn(lm_head, qm))


def _serve_ok(lp, hidden_states, lm_head, embedding_bias, M) -> bool:
    """The fail-closed gate of the server wrap (kept standalone so the self-test can drive
    every branch without an engine): marked target-verify + registered head + plain bf16
    contiguous shapes + the stock gather path + M on the whitelist. Anything else -> stock."""
    st = _S["st"]
    w = getattr(lm_head, "weight", None)
    ctx = {"st": st, "mark_on": _MARK["on"], "embedding_bias": embedding_bias, "M": M,
           "hidden_states": hidden_states, "w": w, "lp": lp, "lm_head": lm_head}
    for name, fn in _SERVE_CONDS:
        if not fn(ctx):
            if DEBUG:            # C3A' gauge: first-fail tally, cumulative, never a decision
                c = _S["serve_fail_first"]
                c[name] = c.get(name, 0) + 1
            return False
    return True


_MARK = {"on": False}


def _diag_entry_fail(st, lp, lm_head, fm) -> str:
    """C3A' gauge (T4PW-20261007, DEBUG-gated caller): name the FIRST failing condition of the
    _get_logits entry gate -- the L1-F5 window's certified-serve count was an unexplained empty
    set and the leading suspects (§3.3) live exactly here (identity / fm.is_target_verify)."""
    if st is None:
        return "st_built"
    if lp is not _S["lp"]:
        return "lp_instance"
    if lm_head is not getattr(st, "lm_head", None):
        return "head_mismatch"
    if fm is None:
        return "fm_none"
    return "fm_not_target_verify"


def install_logits(lp_module):
    """Hook 2 -- sglang.srt.layers.logits_processor (main-79cafec0): _get_logits:861 MARKS
    target-verify forwards on the registered head (PORT DELTA a: mode read off
    logits_metadata.forward_mode, LogitsMetadata class at :295); _compute_lm_head:955 SERVES
    the certified screen when marked, every gate condition holds and M in QUALIFIED_M --
    otherwise the stock body runs untouched (fail-closed). Check mode: stock returned, cert
    computed on the side, four on-device mismatch counters."""
    if not enabled_anywhere():
        return
    cls = getattr(lp_module, "LogitsProcessor", None)
    if cls is None:
        raise RuntimeError("lm_cert: LogitsProcessor is gone; engine drifted")
    if getattr(cls, "_dsv41_lm_cert", False):
        return
    cls._dsv41_lm_cert = True
    # PORT DELTA c: capture the engine's own stock dispatch predicate (fail-loud on drift).
    _S["sqm"] = getattr(lp_module, "should_apply_lm_head_quant_method", None)
    if _S["sqm"] is None:
        raise RuntimeError("lm_cert: should_apply_lm_head_quant_method is gone; engine drifted")
    orig_get, orig_head = cls._get_logits, cls._compute_lm_head   # missing attr -> refuse boot

    def _get_logits(self, hidden_states, lm_head, logits_metadata, *a, **kw):
        st = _S["st"]
        fm = getattr(logits_metadata, "forward_mode", None)
        if (st is None or self is not _S["lp"] or lm_head is not getattr(st, "lm_head", None)
                or fm is None or not fm.is_target_verify()):
            if DEBUG:            # C3A' gauge: first-reject tally at the entry gate
                name = _diag_entry_fail(st, self, lm_head, fm)
                c = _S["entry_fail_first"]
                c[name] = c.get(name, 0) + 1
            _MARK["on"] = False
            return orig_get(self, hidden_states, lm_head, logits_metadata, *a, **kw)
        _MARK["on"] = True
        try:
            return orig_get(self, hidden_states, lm_head, logits_metadata, *a, **kw)
        finally:
            _MARK["on"] = False

    def _compute_lm_head(self, hidden_states, lm_head, embedding_bias=None):
        M = int(hidden_states.shape[0])
        if not _serve_ok(self, hidden_states, lm_head, embedding_bias, M):
            return orig_head(self, hidden_states, lm_head, embedding_bias)
        if (MODE, M) not in _S["logged_modes"] and _rank() == 0:
            _S["logged_modes"].add((MODE, M))
            cap = ""
            try:
                if torch.cuda.is_available() and torch.cuda.is_current_stream_capturing():
                    cap = " [capture]"
            except Exception:  # noqa: BLE001
                pass
            _log(f"verify head M={M}: {'certified' if MODE == '1' else 'check (stock returned)'}"
                 f"{cap}")
        x = hidden_states.to(torch.bfloat16) if hidden_states.dtype != torch.bfloat16 \
            else hidden_states
        cert = certified_logits(_S["st"], _S["bufs"], x)
        if MODE == "1":
            return cert
        stock = orig_head(self, hidden_states, lm_head, embedding_bias)
        _check(_S["bufs"], stock, cert)
        return stock

    cls._get_logits = _get_logits
    cls._compute_lm_head = _compute_lm_head


def set_flag(armed: bool) -> None:
    """Host side, before the verify forward is launched: stream-ordered, written only when it
    changes (the graph replays read the buffer)."""
    bufs = _S["bufs"]
    if bufs is None:
        return
    v = 1 if armed else 0
    if bufs.flag_host != v:
        bufs.flag.fill_(v)
        bufs.flag_host = v


def _req_stop_ids(req):
    """The stop ids min_new_tokens masks for this request (cached on the request). Deliberately
    a SUPERSET of what BatchedMinNewTokensPenalizer._prepare will actually mask: force-
    qualifying extra ids only costs a few tiles, never correctness."""
    got = getattr(req, "_dsv41_lm_cert_stop", None)
    if got is None:
        tok = getattr(req, "tokenizer", None)
        ids = set(req.sampling_params.stop_token_ids or set()) \
            | set(getattr(req, "eos_token_ids", None) or set())
        if tok is not None:
            ids |= set(getattr(tok, "additional_stop_token_ids", None) or set())
            if getattr(tok, "eos_token_id", None) is not None:
                ids.add(tok.eos_token_id)
        got = frozenset(int(i) for i in ids if i is not None)
        try:
            req._dsv41_lm_cert_stop = got
        except Exception:  # noqa: BLE001
            pass
    return got


def step_armed(executor, batch):
    """-> (armed, stop ids). Certified (masked) logits are safe when every consumer of the
    verify logits is the greedy argmax: all rows greedy, no logprobs, no grammar, no custom
    logit processor, no logit bias, and no penalizer other than min_new_tokens (its -inf stop
    ids are handled by the stop-id rule of the screen). Everything read here is per-batch
    scheduler state, identical on every TP rank. Conservative reads: anything absent = off."""
    del executor
    if getattr(batch, "return_logprob", False) or getattr(batch, "has_grammar", False):
        return False, ()
    si = getattr(batch, "sampling_info", None)
    if si is None:
        return True, ()
    if (not getattr(si, "is_all_greedy", False)
            or getattr(si, "has_custom_logit_processor", False)
            or getattr(si, "logit_bias", None) is not None
            or getattr(si, "grammar_mask", None) is not None):
        return False, ()
    stops = set()
    pen = getattr(si, "penalizer_orchestrator", None)
    if pen is not None and getattr(pen, "is_required", False):
        for p in getattr(pen, "penalizers", {}).values():
            if type(p).__name__ != "BatchedMinNewTokensPenalizer":
                return False, ()
        for req in getattr(batch, "reqs", ()):      # superset: harmless, always safe
            stops |= _req_stop_ids(req)
        if len(stops) > NSTOP:
            return False, ()
    return True, tuple(sorted(stops))


def set_stop(ids) -> None:
    """Host side, before the forward: the stop-id slots, rewritten only when the set changes
    (rare). A superset left from earlier steps is harmless -- those ids are simply computed."""
    bufs = _S["bufs"]
    if bufs is None or bufs.stop_host == ids:
        return
    t = torch.full((NSTOP,), -1, dtype=torch.int32)
    if ids:
        t[:len(ids)] = torch.tensor(ids, dtype=torch.int32)
    bufs.stop.copy_(t.to(bufs.stop.device), non_blocking=False)
    bufs.stop_host = ids


def _log_stats():
    """Check-mode report, printed every DSV41_CERT_HEAD_LOG_EVERY verify steps (the single
    permitted host sync): the FOUR mismatch counters are the bit-equality gate."""
    bufs = _S["bufs"]
    if bufs is None:
        return
    c = [int(v) for v in bufs.counters.tolist()]
    need = int(bufs.need.item())
    msg = (f"rank {_rank()} verify steps {_S['verify_calls']} (armed {_S['armed_calls']}), "
           f"tiles computed {need} (all-tile steps = {bufs.need_per_full or '?'} each)")
    if c[0]:
        msg += (f"; check: steps {c[0]} (certified {c[1]}), argmax mismatches {c[2]}, "
                f"value mismatches {c[3]}, tile mismatches {c[4]}, full-mode mismatches {c[5]}, "
                f"rows {c[6]}")
    elif _rank() == 0 and _S["verify_calls"]:
        # C3A' two-state fix (L1F5-VERDICT §五.3): c[0]==0 is an OBSERVED zero-comparison
        # empty set, not an unparseable reading -- say so on the line itself.
        msg += "; check: 0 certified comparisons (empty set -- certified serve never ran)"
    if DEBUG and _rank() == 0:
        if _S["entry_fail_first"]:
            msg += f"; entry-reject {_S['entry_fail_first']}"
        if _S["serve_fail_first"]:
            msg += f"; serve-reject {_S['serve_fail_first']}"
    if _rank() == 0 or any(c[2:6]):
        _log(msg)


def install_verify(verify_module):
    """Hook 3 -- sglang.srt.speculative.dspark_components.dspark_verify (main :226/:277/:436):
    flip the device flag around every verify forward -- set(1) + stop ids before
    run_non_compact's forward, 0 (full exact) for the compact and idle-participation paths.
    Chained AFTER spec_sync_free / folded_result_fence / verify_cap on run_non_compact
    (sitecustomize order: appended at the END of the dspark_verify branch; disjoint concerns,
    each keeps its own marker)."""
    if not enabled_anywhere():
        return
    ex = getattr(verify_module, "TargetVerifyExecutor", None)
    if ex is None:
        raise RuntimeError("lm_cert: TargetVerifyExecutor is gone; engine drifted")
    if getattr(ex, "_dsv41_lm_cert", False):
        return
    ex._dsv41_lm_cert = True
    orig_nc, orig_c, orig_idle = (ex.run_non_compact, ex.run_compact,
                                  ex.run_idle_participation)

    def run_non_compact(self, *, batch, **kw):
        armed, stops = step_armed(self, batch)
        if armed and stops:
            set_stop(stops)
        set_flag(armed)
        _S["verify_calls"] += 1
        _S["armed_calls"] += int(armed)
        try:
            return orig_nc(self, batch=batch, **kw)
        finally:
            if LOG_EVERY and _S["verify_calls"] % LOG_EVERY == 0:
                _log_stats()

    def run_compact(self, *a, **kw):
        set_flag(False)
        return orig_c(self, *a, **kw)

    def run_idle_participation(self, *a, **kw):
        set_flag(False)
        return orig_idle(self, *a, **kw)

    ex.run_non_compact = run_non_compact
    ex.run_compact = run_compact
    ex.run_idle_participation = run_idle_participation


def summary() -> str:
    """Boot-banner line, sitecustomize style: [lm_cert] gate=... armed=... ..."""
    st = _S["st"]
    c = _S.get("bufs")
    counters = ""
    if c is not None:
        cc = [int(v) for v in c.counters.tolist()]
        counters = (f" steps={cc[0]} argmax_mism={cc[2]} value_mism={cc[3]} tile_mism={cc[4]}"
                    f" full_mism={cc[5]}")
    return (f"gate={os.environ.get('DSV41_CERT_HEAD', '(unset)')} armed={st is not None}"
            f" mode={MODE} M={sorted(QUALIFIED_M) or 'none'}"
            f" tables={'yes' if st is not None else 'no'}"
            f"{' why=' + _S['why'] if st is None else ''}{counters}")
