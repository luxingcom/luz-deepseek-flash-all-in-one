"""Prefetch the next dense weights into L2 while a collective runs (decode only).

PORTED from knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4 @ 9df6ffe
(adapter/l2_prefetch.py sha256=996dc24ea31c6aa3), retargeted from their RoCE one-shot
collectives to this stack's NCCL ring. Same mechanism, same gate, same guarantee.

Why it transfers. This stack's decode step is 65.96 ms wall, of which NCCL is 12.28 ms
(88 all-reduce launches/step at 139.6 us each, c1 profile 2026-09-25). Measured on this
fleet: "NCCL union = 658.8 ms" and "all-busy minus non-NCCL-busy = 658.8 ms" are exactly
equal, i.e. comm and compute have ZERO overlap. The all-reduce kernel is
ncclDevKernel_AllReduce_Sum_bf16_RING_LL with grid [2,1,1] / block [288] -- two CTAs, so
the SMs and DRAM sit idle through every window. That is precisely the premise the
upstream adapter relies on (their grid is 1-8 CTAs for the same reason). The kernel that
follows each window is a dense MXFP8 GEMM (post-MoE AR -> next layer's wqkv_a) or the
router, all weight-bound at M<=16. Issuing cp.async.bulk.prefetch.L2 for the first
DSV41_L2_PREFETCH_MB of those weights right before the collective moves that DRAM read
into the idle window. Weights are static and a prefetch is only a cache hint, so outputs
are bit-identical BY CONSTRUCTION -- there is no numerical path through this file.

Which weights follow which collective is learned, not hard-coded: during the eager
warm-up forwards SGLang runs before capturing each CUDA graph (this stack captures decode
for bs<=16, CUDA_GRAPH_MAX_BS_DECODE=16), collectives are numbered per forward and every
MXFP8 dense linear records itself under the last collective. The capture pass (the same
Python sequence) then forks the prefetch right before the collective, so it becomes a
graph branch. A forward whose signature was never learned prefetches nothing; a stale plan
can only waste bandwidth, never change a result.

Gates: DSV41_L2_PREFETCH=1 (off by default), DSV41_L2_PREFETCH_MB budget per window
(default 6), DSV41_L2_PREFETCH_AG=0 skips all-gather windows.

Port notes (three hooks; only #2 differs from upstream):
  1. install_fp8_utils  -- IDENTICAL. This stack's MXFP8 dense seam is the same symbol
     (flashinfer_mxfp8_blockscaled_linear), already wrapped by adapter/mxfp8_b12x.py, so
     the hook chains after it (see sitecustomize.py ordering).
  2. install_collectives -- replaces upstream install_roce. This stack runs NCCL, not
     RoCE: LD_PRELOAD=/opt/libncclpin.so /opt/nccl-ringonly/libnccl.so.2 with
     NCCL_ALGO=RING. The collective entry points are plain functions imported by name into
     sglang.srt.layers.communicator (lines 24-28), which is the per-layer hot path, and
     defined in sglang.srt.distributed.communication_op. Both module namespaces are
     patched: from-import binds the function object into the consumer, so patching only
     the defining module would miss communicator entirely. Unlike upstream's
     should_allreduce() predicate there is nothing to filter -- each patched call is one
     launch. Coverage is best-effort: an unhooked site only means a missed window, never
     a wrong result, and the per-forward count is logged so it can be checked against the
     profiler's 88 AR/step.
  3. install_model -- IDENTICAL target (DeepseekV4Model.forward; this stack calls it from
     DeepseekV4ForCausalLM.forward at models/deepseek_v4.py:4722).
  install_router -- retargeted: tiny_gemm_bf16 is a function-local import in this tree
     (models/deepseek_v2.py:238), so the module attribute is patched on
     sglang.kernels.ops.gemm.tiny_gemm with a fallback to deepseek_v2.

Yields quoted from upstream are THEIRS (decode step -1 ms at c1, prose c1 84.5->87.6,
c8 +2%, c16 flat on their fleet) and are not a claim about this stack; the pre-registered
judgement for here is step wall and DE prose measured in-window.

Self-check: `python3 l2_prefetch.py` runs selftest(), which needs no GPU -- it exercises
the gate, the segment budget (including a zero budget, which MUST yield no prefetch: the
"feed it a bad input and watch it go red for the right reason" case), the past-the-plan
guard, and that the compiled kernel is loadable.
"""
import ctypes as C
import logging
import os
import subprocess
import sys
from pathlib import Path

import torch

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_STATE = {"lib": None, "learning": {}, "plans": {}, "sig": None, "idx": 0, "side": {},
          "pending": None, "stats": [0, 0], "installed": set(), "logged": set(),
          "frozen": set(), "keepalive": []}
_CHUNK = 16384


def enabled():
    """Fail-safe: anything that is not an explicit truthy token leaves it off."""
    return os.environ.get("DSV41_L2_PREFETCH", "0").strip() in ("1", "on", "true")


def _budget():
    return int(float(os.environ.get("DSV41_L2_PREFETCH_MB", "6")) * (1 << 20))


def _lib():
    if _STATE["lib"] is None:
        # Baked at image-build time (Dockerfile bakes l2pf.cu -> this name); dev fallback
        # compiles the same .cu, so there is only ever one copy of the kernel source.
        so = _HERE / "libdsv41_l2pf.so"
        if not so.exists():
            cu = _HERE / "l2pf.cu"
            if not cu.exists():
                raise RuntimeError(f"DSV41_L2_PREFETCH: neither {so} nor {cu} exists")
            tmp = _HERE / f".libdsv41_l2pf.{os.getpid()}.so"
            subprocess.run(["nvcc", "-O3", "-arch=sm_121a", "-shared", "-Xcompiler", "-fPIC",
                            "-o", str(tmp), str(cu)], check=True)
            os.replace(tmp, so)
        lib = C.CDLL(str(so))
        lib.dsv41_l2pf.argtypes = [C.c_void_p, C.c_int, C.c_longlong, C.c_void_p]
        lib.dsv41_l2pf.restype = C.c_int
        _STATE["lib"] = lib
    return _STATE["lib"]


# -- forward bracketing -------------------------------------------------------------------------

def _begin_forward(sig):
    """Every eager forward of a shape that has not been captured yet re-learns its plan.

    The first eager forward of a shape can be a dummy/profiling run outside the graph-capture
    communicator state. The warm-up forwards SGLang runs right before each capture are what the
    capture replays, so the latest eager observation wins, and a shape is frozen once captured.
    """
    _STATE["sig"], _STATE["idx"] = sig, 0
    _STATE["stats"][1] = 0
    if sig not in _STATE["frozen"] and not torch.cuda.is_current_stream_capturing():
        _STATE["learning"][sig] = {}


def _join():
    pending = _STATE["pending"]
    if pending is not None:
        torch.cuda.current_stream().wait_stream(pending)
        _STATE["pending"] = None


def _side_stream():
    dev = torch.cuda.current_device()
    if dev not in _STATE["side"]:
        _STATE["side"][dev] = torch.cuda.Stream(device=dev)
    return _STATE["side"][dev]


def _end_forward():
    _join()
    sig = _STATE["sig"]
    capturing = torch.cuda.is_current_stream_capturing()
    rec = _STATE["learning"].pop(sig, None) if sig is not None else None
    if rec is not None and not capturing:
        n = _STATE["idx"]
        key = (n, tuple((i, tuple(v)) for i, v in sorted(rec.items())))
        old = _STATE["plans"].get(sig)
        if n == 0:
            # no collective seen (unhooked path): keep any earlier plan, never learn "nothing"
            if old is None and ("zero",) + sig[1:] not in _STATE["logged"]:
                _STATE["logged"].add(("zero",) + sig[1:])
                logger.warning("DSV41_L2_PREFETCH eager forward tokens=%d mode=%s saw no hooked "
                               "collective; not learned, waiting for the capture warm-up",
                               sig[1], sig[2])
        elif old is None or old[2] != key:
            plan = _make_plan(rec)
            _STATE["plans"][sig] = (n, plan, key)
            _side_stream()  # created eagerly, never first inside a graph capture
            nbytes = sum(int(t[1::2].sum()) for t, _ in plan.values())
            logger.warning("DSV41_L2_PREFETCH plan tokens=%d mode=%s collectives=%d windows=%d "
                           "prefetch=%.1f MB/forward%s", sig[1], sig[2], n, len(plan),
                           nbytes / 2**20,
                           "" if old is None else f" (relearned; was {old[0]} collectives)")
    elif sig is not None and capturing:
        _STATE["frozen"].add(sig)
        key = ("capture",) + sig[1:]
        if key not in _STATE["logged"]:
            _STATE["logged"].add(key)
            entry = _STATE["plans"].get(sig)
            learned = entry[0] if entry else 0
            ok = entry is not None and learned == _STATE["idx"] and _STATE["stats"][1] > 0
            logger.warning("DSV41_L2_PREFETCH captured tokens=%d mode=%s branches=%d collectives=%d "
                           "(learned %d)%s", sig[1], sig[2], _STATE["stats"][1], _STATE["idx"],
                           learned, "" if ok else " MISMATCH: this graph runs without prefetch")
    _STATE["sig"] = None


def _select_segments(segs, budget):
    """Take a 16B-aligned prefix of each weight, in consumption order, up to budget bytes."""
    out, left = [], budget
    for ptr, nbytes in segs:
        if left <= 0:
            break
        take = min(nbytes, left) & ~15
        if take > 0:
            out.append((ptr, take))
            left -= take
    return out


def _make_plan(rec):
    """rec: {collective idx: [(ptr, bytes), ...] in consumption order} -> device segment tables."""
    budget = _budget()
    plan = {}
    for idx, segs in rec.items():
        out = _select_segments(segs, budget)
        if out:
            t = torch.tensor([v for s in out for v in s], dtype=torch.int64, device="cuda")
            plan[idx] = (t, len(out))
            _STATE["keepalive"].append(t)  # a captured graph keeps reading this address
    return plan


# -- hooks --------------------------------------------------------------------------------------

def _record_weight(*tensors):
    sig = _STATE["sig"]
    if sig is None or sig not in _STATE["learning"]:
        return
    rec = _STATE["learning"][sig].setdefault(_STATE["idx"], [])
    for t in tensors:
        if t is not None and t.is_cuda:
            rec.append((t.data_ptr(), t.numel() * t.element_size()))


def _launch(t, n, side):
    """Issue the prebuilt segment table on the side stream. A separate seam so selftest can
    prove the launch decision (fires inside the plan, silent past it / at zero budget)
    without a device."""
    rc = _lib().dsv41_l2pf(t.data_ptr(), n, _CHUNK, side.cuda_stream)
    if rc:
        raise RuntimeError(f"DSV41_L2_PREFETCH launch failed: cuda error {rc}")


def _before_collective(kind, stream):
    sig = _STATE["sig"]
    if sig is None:
        return
    _join()
    _STATE["idx"] += 1
    idx = _STATE["idx"]
    if kind == "ag" and os.environ.get("DSV41_L2_PREFETCH_AG", "1") == "0":
        return
    entry = _STATE["plans"].get(sig)
    if entry is None:
        return
    if idx > entry[0]:
        return  # more collectives than learned: sequence differs, launch nothing past the plan
    item = entry[1].get(idx)
    if item is None:
        return
    t, n = item
    main = stream if isinstance(stream, torch.cuda.Stream) else torch.cuda.current_stream()
    side = _side_stream()
    side.wait_stream(main)
    _launch(t, n, side)
    _STATE["pending"] = side
    _STATE["stats"][0] += 1
    _STATE["stats"][1] += 1


def install_fp8_utils(module):
    """Wrap the MXFP8 dense linear (after mxfp8_b12x) so each call records its weight + scales."""
    if not enabled() or ("fp8", id(module)) in _STATE["installed"]:
        return
    _STATE["installed"].add(("fp8", id(module)))
    original = module.flashinfer_mxfp8_blockscaled_linear

    def linear(input, weight, weight_scale, *args, **kwargs):
        _record_weight(weight, weight_scale)
        return original(input, weight, weight_scale, *args, **kwargs)

    module.flashinfer_mxfp8_blockscaled_linear = linear
    logger.warning("DSV41_L2_PREFETCH: MXFP8 linears recorded (budget %.1f MB/window)",
                   _budget() / 2**20)


def install_router(*modules):
    """Record the bf16 router weight (tiny_gemm_bf16), read right after the post-attention AR."""
    if not enabled():
        return
    for module in modules:
        if ("router", id(module)) in _STATE["installed"]:
            continue
        original = getattr(module, "tiny_gemm_bf16", None)
        if original is None:
            continue
        _STATE["installed"].add(("router", id(module)))

        def tiny_gemm_bf16(hidden_states, weight, _original=original, *args, **kwargs):
            _record_weight(weight)
            return _original(hidden_states, weight, *args, **kwargs)

        module.tiny_gemm_bf16 = tiny_gemm_bf16


_AR_NAMES = ("tensor_model_parallel_all_reduce",
             "attention_tensor_model_parallel_all_reduce",
             "moe_tensor_model_parallel_all_reduce")
_AG_NAMES = ("tensor_model_parallel_all_gather",)
_COLLECTIVE_MODULES = ("sglang.srt.layers.communicator",
                       "sglang.srt.distributed.communication_op")


def _patch_collectives(module, names, kind):
    n = 0
    for name in names:
        original = getattr(module, name, None)
        if original is None or getattr(original, "_dsv41_l2_prefetch", False):
            continue

        def wrapper(input_, _original=original, _kind=kind, *args, **kwargs):
            _before_collective(_kind, kwargs.get("stream"))
            return _original(input_, *args, **kwargs)

        wrapper._dsv41_l2_prefetch = True
        wrapper.__name__ = name
        setattr(module, name, wrapper)
        n += 1
    return n


def install_collectives(*modules):
    """Patch this stack's NCCL collective entry points: prefetch right before each launch."""
    if not enabled():
        return
    total = 0
    for module in modules:
        total += _patch_collectives(module, _AR_NAMES, "ar")
        total += _patch_collectives(module, _AG_NAMES, "ag")
    if total:
        _lib()  # fail fast at serve time, not on the first decode step
    logger.warning("DSV41_L2_PREFETCH: %d collective entry point(s) prefetch the next weights "
                   "into L2", total)


def install_roce(module):
    """Patch b12x.comm.roce(_ring).roce_oneshot: prefetch right before each RoCEnante collective.

    Coexists with install_collectives (the NCCL hook): the RoCEnante arms import these
    b12x modules and the NCCL arms never do, so exactly one of the two is live per boot.
    Same shape as upstream's install_roce (which this port originally dropped)."""
    if not enabled():
        return
    cls = module.RoceOneshotAllReduce
    if getattr(cls, "_dsv41_l2_prefetch", False):
        return
    cls._dsv41_l2_prefetch = True
    ar, ag = cls.all_reduce, cls.all_gather

    def all_reduce(self, inp, *args, **kwargs):
        if self.should_allreduce(inp):
            _before_collective("ar", kwargs.get("stream"))
        return ar(self, inp, *args, **kwargs)

    def all_gather(self, inp, *args, **kwargs):
        _before_collective("ag", kwargs.get("stream"))
        return ag(self, inp, *args, **kwargs)

    cls.all_reduce, cls.all_gather = all_reduce, all_gather
    _lib()
    logger.warning("DSV41_L2_PREFETCH: RoCE collectives prefetch the next weights into L2")


def install_model(module):
    """Bracket DeepseekV4Model.forward (decode / target-verify only; prefill is compute-bound)."""
    if not enabled():
        return
    cls = module.DeepseekV4Model
    if getattr(cls, "_dsv41_l2_prefetch", False):
        return
    cls._dsv41_l2_prefetch = True
    original = cls.forward

    def forward(self, input_ids, positions, forward_batch, *args, **kwargs):
        mode = getattr(forward_batch, "forward_mode", None)
        decode_like = mode is not None and any(
            getattr(mode, f, lambda: False)() for f in ("is_decode", "is_target_verify", "is_draft_extend"))
        if not decode_like:
            return original(self, input_ids, positions, forward_batch, *args, **kwargs)
        sig = (id(self), int(input_ids.shape[0]), str(mode))
        _begin_forward(sig)
        try:
            return original(self, input_ids, positions, forward_batch, *args, **kwargs)
        finally:
            _end_forward()

    cls.forward = forward
    logger.warning("DSV41_L2_PREFETCH: model forward bracketed (decode/verify only)")


# -- self-check (no GPU required) ---------------------------------------------------------------

def selftest():
    """Discriminating checks: each one is fed an input that must make it fail for a real reason."""
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
        if not cond:
            fails.append(name)

    saved = os.environ.get("DSV41_L2_PREFETCH")
    try:
        for v, want in (("1", True), ("on", True), ("true", True), ("0", False),
                        ("", False), ("yes", False), ("TRUE ", False)):
            os.environ["DSV41_L2_PREFETCH"] = v
            check(f"gate {v!r} -> {want}", enabled() is want, f"got {enabled()}")

        os.environ.pop("DSV41_L2_PREFETCH_MB", None)
        check("budget default 6 MiB", _budget() == 6 << 20, str(_budget()))
        os.environ["DSV41_L2_PREFETCH_MB"] = "0"
        check("budget 0 honoured", _budget() == 0, str(_budget()))

        # The load-bearing negative case: a zero budget MUST select nothing. If this ever
        # returns segments, a mis-set budget silently turns into unbounded prefetch traffic.
        segs = [(0x1000, 1 << 20), (0x2000, 1 << 20)]
        check("zero budget selects nothing", _select_segments(segs, 0) == [],
              str(_select_segments(segs, 0)))
        check("negative budget selects nothing", _select_segments(segs, -1) == [],
              str(_select_segments(segs, -1)))

        got = _select_segments(segs, (1 << 20) + 4096)
        check("budget honoured across segments",
              got == [(0x1000, 1 << 20), (0x2000, 4096)], str(got))
        got = _select_segments([(0x1000, 17)], 4096)
        check("16B alignment truncates", got == [(0x1000, 16)], str(got))
        got = _select_segments([(0x1000, 8)], 4096)
        check("sub-16B segment skipped", got == [], str(got))

        # The load-bearing decision test, with the device seams stubbed so it stays CPU-only.
        # A positive control comes FIRST: when a segment is present and within the plan the
        # code must attempt a launch. Only against that does silence mean anything -- a
        # "never launches" implementation would otherwise pass every negative case.
        launches = []
        saved_globals = {k: globals()[k] for k in ("_launch", "_side_stream")}
        real_current_stream = torch.cuda.current_stream

        class _FakeStream:
            cuda_stream = 0

            def wait_stream(self, other):
                pass

        os.environ["DSV41_L2_PREFETCH_MB"] = "0"
        check("zero budget builds no plan at all",
              _make_plan({1: [(0x1000, 1 << 20)]}) == {}, "non-empty plan at budget 0")

        globals()["_launch"] = lambda t, n, side: launches.append((t, n))
        globals()["_side_stream"] = lambda: _FakeStream()
        torch.cuda.current_stream = lambda: _FakeStream()
        try:
            st = _STATE["stats"]
            # The plan is given a key PAST the learned count (4, with entry[0]=3) on purpose.
            # In production _make_plan can never emit one -- keys come from the collectives
            # that were actually seen, so entry[1].get(idx) already returns None past the
            # count and the entry[0] guard is a redundant belt-and-braces check. A test built
            # from a production-shaped plan would therefore still pass with that guard
            # deleted (verified: it did). Only this synthetic key makes the guard load-bearing,
            # so only this plan can tell us whether the guard works.
            _STATE["plans"]["guard"] = (3, {2: (object(), 5), 4: (object(), 7)}, ("test",))
            _STATE["sig"] = "guard"
            _STATE["idx"] = 1
            _before_collective("ar", None)      # -> idx 2 : segment present, MUST launch
            check("in-plan window launches", len(launches) == 1, str(launches))
            check("  and counts as a branch", st[1] == 1, str(st[1]))
            _before_collective("ar", None)      # -> idx 3 : in plan, no segments recorded
            check("in-plan windowless index is silent", len(launches) == 1, str(len(launches)))
            _before_collective("ar", None)      # -> idx 4 : KEY PRESENT but past the count
            check("past-the-plan is silent even with a key present", len(launches) == 1,
                  str(len(launches)))
            _before_collective("ar", None)      # -> idx 5 : past it, no key
            check("  index still advances", _STATE["idx"] == 5, str(_STATE["idx"]))

            os.environ["DSV41_L2_PREFETCH_AG"] = "0"
            _before_collective("ag", None)      # -> idx 6 : counted, then suppressed
            check("AG=0 counts but silences",
                  len(launches) == 1 and _STATE["idx"] == 6, f"{len(launches)}/{_STATE['idx']}")

            _STATE["sig"] = "never-learned"
            _STATE["idx"] = 0
            _before_collective("ar", None)
            check("unlearned signature launches nothing", len(launches) == 1 and _STATE["idx"] == 1,
                  f"{len(launches)}/{_STATE['idx']}")
        finally:
            globals().update(saved_globals)
            torch.cuda.current_stream = real_current_stream
            _STATE["plans"].pop("guard", None)
            _STATE["sig"] = None
            _STATE["pending"] = None
            _STATE["stats"] = [0, 0]
            _STATE["idx"] = 0
            os.environ.pop("DSV41_L2_PREFETCH_AG", None)

        check("l2pf.cu present", (_HERE / "l2pf.cu").is_file(), str(_HERE / "l2pf.cu"))
        try:
            _lib()
            check("kernel .so loadable and dsv41_l2pf resolvable", True)
        except Exception as e:  # noqa: BLE001 - report whatever went wrong, verbatim
            check("kernel .so loadable and dsv41_l2pf resolvable", False, repr(e))
    finally:
        if saved is None:
            os.environ.pop("DSV41_L2_PREFETCH", None)
        else:
            os.environ["DSV41_L2_PREFETCH"] = saved
        for k in ("DSV41_L2_PREFETCH_MB",):
            os.environ.pop(k, None)

    print(f"\n  selftest: {len(fails)} failure(s)" if fails else "\n  selftest: all checks pass")
    return 1 if fails else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(selftest())
