"""Draft confidence head in static verify mode, so a ``DSV41_VERIFY_PRUNE=conf:...`` policy can arm.

Gated on ``DSV41_VERIFY_PRUNE=conf:...``: for any other value (or unset) ``install()`` patches
nothing and the engine is the unpatched one.

Why the key was inert on 0.2.9-ep1c
-----------------------------------
``deepseek_v4_dspark.build_dspark_v4_confidence_head`` returns None when
``read_ragged_verify_mode() is RaggedVerifyMode.STATIC``, and production -- and both EP1 arm
boots of 2026-09-25 -- run ``SGLANG_RAGGED_VERIFY_MODE=static``. That single line takes out the
whole confidence path without saying so:

* ``DSparkVerifyPlanner.carries_confidence`` is literally "the head exists"
  (``dspark_planner.py:210``), so ``dspark_worker_v2._maybe_build_draft_sampler`` builds the
  folded draft sampler with ``confidence_fn=None``;
* ``DsparkDraftSampler`` therefore never allocates its ``confidence_out`` buffer
  (``dspark_draft_sampler.py:70-76``), so a folded proposal carries ``confidence=None``
  (``dspark_draft.py:322-323``) -- and the planner's own fallback returns None too, since its
  first statement is ``if self._confidence_head is None: return None``;
* everything downstream of the confidence tensor is then inert. On the 0.2.9-ep1c EP1 arm the
  boot log has both halves of that failure 20 s apart: "verify-prune: **已武装（conf）**" at
  13:09:15 and "verify-prune: 已关闭 —— conf 模式写 live 失败：confidence 缺失或形状不对：
  <class 'NoneType'>" at 13:09:35. Two boots ran ``conf:0.1`` with no effect at all.

knapcio's ``adapter/verify_cap.py::install_dspark`` patches the same function for the same
reason; their measured effect with the policy armed and working is the -6 ms/step that holds
prose at 69.3 t/s instead of 66.1 (docs/history.md, two boots each).

What the patch does
-------------------
For the head-construction call only, ``read_ragged_verify_mode()`` reports CAP_ACCEPT. That is
the only mode check inside either builder, and nothing reads the mode again afterwards -- the
attribute is restored in a ``finally`` and asserted restored by the CPU gate, including on the
exception path.

The head it returns is a real submodule -- ``nn.Linear(hidden_size [+ markov_rank], 1,
bias=False)`` fed by the checkpoint's ``mtp.2.confidence_head.proj.weight`` -- built before
``load_weights``, so that weight is loaded and ``_assert_confidence_head_loaded`` still refuses
a checkpoint without trained confidence weights. That guard matters: a head with random weights
would not fail, it would cut verify rows on noise.

Both call sites that reach the head supply ``confidence_tap``: the folded sampler's own
``self.model.compute_base_logits(...)`` (``dspark_draft_sampler.py:125``) and the eager path's
``dspark_draft.py:326``. So the planner's own assertion (``confidence_tap is not None``) holds
on both proposal paths; if a future engine ever reached ``compute_confidence`` without a tap
this would raise rather than silently reuse a stale one.
"""
import os

POLICY = os.environ.get("DSV41_VERIFY_PRUNE", "").strip()
ENABLED = POLICY.startswith("conf:")

# Both builders carry the same STATIC check and the same seam; the V4 draft uses the first,
# and patching the second costs nothing (it is a no-op unless this draft family is in play).
BUILDERS = ("build_dspark_v4_confidence_head", "build_confidence_head")
_PATCHED = []


def _wrap(module, name, mode_cls):
    """Swap the module-global mode getter for the duration of one builder call."""
    original = getattr(module, name)
    if getattr(original, "_dsv41_verify_cap_static", False):
        return False

    def build(*args, **kwargs):
        previous = module.read_ragged_verify_mode
        module.read_ragged_verify_mode = lambda: mode_cls.CAP_ACCEPT
        try:
            head = original(*args, **kwargs)
        finally:
            module.read_ragged_verify_mode = previous
        print(
            f"[verify-cap-static] {module.__name__}.{name}: "
            f"{'confidence head built' if head is not None else 'None'}",
            flush=True,
        )
        return head

    build._dsv41_verify_cap_static = True
    build.__wrapped__ = original
    setattr(module, name, build)
    _PATCHED.append(f"{module.__name__}.{name}")
    return True


def install(module) -> bool:
    """Patch the confidence-head builders of ``module``. Returns whether anything was patched.

    Refuses loudly (rather than silently patching nothing) when the policy is armed but the
    module no longer exposes the seam this was written against: an armed-but-inert key is the
    exact failure this adapter exists to remove, and it is invisible in a DE measurement.
    """
    if not ENABLED:
        return False
    names = [n for n in BUILDERS if callable(getattr(module, n, None))]
    if not names:
        return False
    if getattr(module, "read_ragged_verify_mode", None) is None:
        raise RuntimeError(
            f"verify-cap-static: {module.__name__} has {names} but no read_ragged_verify_mode; "
            "the seam moved and the static-mode head would stay unbuilt"
        )
    try:
        from sglang.srt.speculative.ragged_verify import RaggedVerifyMode
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"verify-cap-static: cannot import RaggedVerifyMode: {exc}") from exc
    patched = [name for name in names if _wrap(module, name, RaggedVerifyMode)]
    print(
        f"[verify-cap-static] {module.__name__}: patched {patched or 'nothing (already patched)'}"
        f" policy={POLICY}",
        flush=True,
    )
    return bool(patched)


def summary() -> str:
    return f"policy={POLICY or '(unset)'} armed={ENABLED} patched={_PATCHED or '[]'}"
