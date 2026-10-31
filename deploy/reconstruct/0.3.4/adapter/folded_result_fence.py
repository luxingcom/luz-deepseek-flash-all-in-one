"""Detach folded DSpark verify results from the verify graph's persistent buffers. Default OFF.

Ported 2026-09-25 from knapcio's ``adapter/folded_result_fence.py`` (public repo snapshot), logic
verbatim. Their reference is sglang#40919; the race it closes is this stack's own class of failure:
with overlap scheduling the scheduler copies the verify results to host on its copy stream while the
next step already runs, and the next verify replay can overwrite those persistent buffers before the
copy finishes. A wrong token copied here is exactly the ``verify/重采样共享段`` signature we have
been chasing as the output-degeneration bug, so this is both a correctness fix and a candidate root
cause.

DSV41_FOLDED_FENCE=1. On the folded path (all-greedy batches replayed from the verify CUDA graph),
accept_and_finalize returns views of DsparkVerifyEpilogue's persistent buffers (out_tokens_buf,
commit_lens_buf, ...). Cloning them on the forward stream right after the verify, before anything
else is queued, gives the copy its own memory; later replays cannot touch it. Six tensors of bs x 6
ints: negligible. Sampled batches take the eager path, which already allocates fresh tensors, and
are left alone.

Our tree's seam, checked at bake time: ``dspark_verify.TargetVerifyExecutor`` (line 84) with
``accept_and_finalize``, ``AcceptOuts`` (line 488) carrying all six fields, and the ``folded_accept``
keyword the wrapper keys on.
"""
import os

ENABLED = os.environ.get("DSV41_FOLDED_FENCE", "0").strip() not in ("0", "", "off", "false")
# EP1h (adapter/eager_glue.py): with DSV41_EAGER_GLUE=fence the six copies go out as ONE kernel.
_GLUE = "fence" in os.environ.get("DSV41_EAGER_GLUE", "") or os.environ.get(
    "DSV41_EAGER_GLUE", "").strip().lower() in ("1", "on", "true", "all")
FIELDS = ("correct_len", "bonus", "cap_trim_lens", "commit_lens", "new_seq_lens", "out_tokens")
_COUNT = {"cloned": 0, "fused": 0}


def install(module):
    """sglang.srt.speculative.dspark_components.dspark_verify"""
    if not ENABLED:
        return False
    cls = getattr(module, "TargetVerifyExecutor", None)
    outs_cls = getattr(module, "AcceptOuts", None)
    if cls is None or outs_cls is None or not hasattr(cls, "accept_and_finalize"):
        raise RuntimeError("DSV41_FOLDED_FENCE: TargetVerifyExecutor.accept_and_finalize / AcceptOuts gone; engine drifted")
    missing = [f for f in FIELDS if not hasattr(outs_cls, f)]
    if missing:
        raise RuntimeError(f"DSV41_FOLDED_FENCE: AcceptOuts lost {missing}; engine drifted")
    if getattr(cls, "_dsv41_folded_fence", False):
        return False
    cls._dsv41_folded_fence = True
    orig = cls.accept_and_finalize

    def accept_and_finalize(self, *a, **kw):
        outs = orig(self, *a, **kw)
        if not kw.get("folded_accept", False):
            return outs
        _COUNT["cloned"] += 1
        if _GLUE:
            # EP1h: one cat + slice instead of six .clone() launches; bytes identical, still
            # fresh memory off the persistent buffers. fused_clone declines (returns None) for
            # any dtype/contiguity it does not handle and the six clones run as before.
            from eager_glue import fused_clone
            fresh = fused_clone([getattr(outs, f) for f in FIELDS])
            if fresh is not None:
                _COUNT["fused"] += 1
                return outs_cls(**dict(zip(FIELDS, fresh)))
        return outs_cls(**{f: getattr(outs, f).clone() for f in FIELDS})

    cls.accept_and_finalize = accept_and_finalize
    print("[folded_fence] folded DSpark results cloned off the persistent verify buffers", flush=True)
    return True


def summary() -> str:
    return (f"gate={os.environ.get('DSV41_FOLDED_FENCE', '(unset)')} armed={ENABLED} "
            f"cloned={_COUNT['cloned']} fused={_COUNT['fused']}")
