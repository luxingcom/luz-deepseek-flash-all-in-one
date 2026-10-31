"""A23 group overlay: the GroupCoordinator wiring piece (mount H-2 + H-A + H-B).

This is the overlay/ subtree piece the v2 task card asked for: the two-method
(-plus-dispatch) wrapper at the H-A mount region.  Design anchors
(DESIGN.md §1.1, container source image-src-0.2.8/srt/distributed/
parallel_state.py):

    H-2  GroupCoordinator.all_reduce            :645-759  user dispatch
        (signature: all_reduce(self, input_) -> input_; SUM is implicit --
         there is no op parameter at this layer, so no op gate is needed)
    H-A  GroupCoordinator._all_reduce_in_place  :1018-1030 eager prefill
        fallthrough = torch.distributed.all_reduce(device_group)  (main mount)
    H-B  GroupCoordinator._all_reduce_out_place :973-1016 piecewise/pynccl
        form; only method in (None, "pynccl") is intercepted -- "ca"/"qr"/
        "torch_symm_mem"/"pymscclpp" keep their accelerated paths

Wiring semantics:

    all_reduce (dispatch face)   in-band eligible tensor -> execute the MODE
        form in place and return input_ (stock contract); anything else ->
        the original dispatch verbatim.  This is where the eager prefill AR
        is captured before it can fan into symm-mem/custom-AR plumbing.
    _all_reduce_in_place (H-A)   the same decision again: catches tensors
        that reach the private in-place method without passing our dispatch
        (compiled paths call the inplace custom op directly).  Idempotent
        with the dispatch decision -- same predicate, same mode -- so a
        tensor that fell through dispatch falls through here too; a routed
        tensor never reaches the original path.
    _all_reduce_out_place (H-B)  out-of-place variant for the pynccl-owned
        branches only (returns a NEW tensor, as the H-B contract requires).

Routing decision is group-consistent by construction (dtype/shape/size/world
only, never the pointer), so every TP rank takes the same branch
(a23_prefill_ar.eligible_for_mode).  A poisoned oneshot runtime RAISES inside
eligibility (b12x rule: a failed collective is fatal, never a silent NCCL
fallback).  mode=nccl installs the wrapper but routes nothing: the wrapper-
neutrality control arm (E2E A/B against off proves the wiring itself is
byte-neutral).  mode=off (or unset) installs nothing at all.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:               # adapter dir on path (machine side
    sys.path.insert(0, _PARENT)           # is the sitecustomize convention)


def install_overlay(module) -> bool:
    """Wrap GroupCoordinator.{__init__, all_reduce, _all_reduce_in_place,
    _all_reduce_out_place} per the resolved DSV41_PREFILL_AR_MODE.

    Inert (returns False, touches nothing) when the mode resolves to off;
    raises on a bad mode key or key combination (fail-loud, resolved inside
    a23_prefill_ar.resolve_mode).  Import of a23_prefill_ar happens HERE, at
    call time, so a reload of the adapter module is picked up (fake tests
    reload per arm).
    """
    import a23_prefill_ar as a23
    from overlay.a23_forms import FORMS, warm_fi_fp8

    mode = a23.resolve_mode()
    if mode is None:
        return False                      # off: stock verbatim, zero behavior
    band = a23.band_from_env()            # decode-disjoint assertion re-run

    cls = module.GroupCoordinator
    orig_init = cls.__init__
    orig_dispatch = cls.all_reduce                        # H-2 (:645)
    orig_inplace = cls._all_reduce_in_place               # H-A (:1018)
    orig_outplace = cls._all_reduce_out_place             # H-B (:973)

    # ids of tensors currently falling through the wrapped dispatch into the
    # original plumbing: their H-A hop is the SAME AR call, so nccl_kept must
    # only be counted once (at the dispatch), never twice.
    _in_dispatch = set()

    def __init__(self, *args, **kwargs):
        # own group-name window (composable with c1-dev roce_ar's stack):
        # the pynccl face reads it to arm the second runtime on "tp" only.
        a23.push_group_name(kwargs.get("group_name"))
        try:
            orig_init(self, *args, **kwargs)
            # capture BEFORE the pop: the stack is empty again afterwards
            is_tp = a23.current_group_name() == "tp"
        finally:
            a23.pop_group_name()
        # tag the TP coordinator: every mode routes on the tp group only.
        self._a23_is_tp = is_tp
        if mode == "fi_fp8" and self._a23_is_tp and int(getattr(
                self, "world_size", 0) or 0) > 1:
            # boot-time collective: pin the FI symmetric buffer at band max
            # and surface rendezvous failures at the cheapest point.
            warm_fi_fp8(self, band[1])
            a23.note_stat("fi_warmed", 1)

    def _fresh_like(self, input_):
        """H-B contract: the out-of-place branches return a NEW tensor."""
        import torch

        return torch.empty_like(input_)

    def _route(self, input_):
        """-> form executor or None.  Same decision on every rank."""
        if not getattr(self, "_a23_is_tp", False):
            return None
        if int(getattr(self, "world_size", 0) or 0) <= 1:
            return None
        if not a23.eligible_for_mode(self, input_, mode):
            return None
        return FORMS[mode]

    def all_reduce(self, input_):
        # stock early paths stay verbatim: world==1 bypass and CPU/shm path
        # (:668-676) -- the band is a CUDA band by construction anyway.
        if int(getattr(self, "world_size", 0) or 0) <= 1 or getattr(
                input_, "is_cpu", False):
            return orig_dispatch(self, input_)
        form = _route(self, input_)
        if form is None:
            a23.note_stat("nccl_kept", 1)
            tid = id(input_)
            _in_dispatch.add(tid)
            try:
                return orig_dispatch(self, input_)
            finally:
                _in_dispatch.discard(tid)
        a23.note_stat("dispatch_routed", 1)
        a23.note_stat("routed_" + mode, 1)
        form(self, input_, out=input_)
        return input_                     # stock dispatch returns input_

    def _all_reduce_in_place(self, input_):
        form = _route(self, input_)
        if form is not None:
            a23.note_stat("prefill_routed", 1)
            a23.note_stat("routed_" + mode, 1)
            form(self, input_, out=input_)
            return None                   # H-A contract: returns None
        if id(input_) not in _in_dispatch:
            # direct H-A entries count here; dispatch fall-throughs were
            # already counted once at the dispatch (same AR call).
            a23.note_stat("nccl_kept", 1)
        return orig_inplace(self, input_)

    def _all_reduce_out_place(self, input_, method):
        # H-B: only the branches that would otherwise land on pynccl/NCCL.
        if method in (None, "pynccl"):
            form = _route(self, input_)
            if form is not None:
                a23.note_stat("outplace_routed", 1)
                a23.note_stat("routed_" + mode, 1)
                return form(self, input_, out=_fresh_like(self, input_))
        return orig_outplace(self, input_, method)

    cls.__init__ = __init__
    cls.all_reduce = all_reduce
    cls._all_reduce_in_place = _all_reduce_in_place
    cls._all_reduce_out_place = _all_reduce_out_place
    a23._banner(
        f"armed overlay face (mode={mode} band {band[0]}..{band[1]} bytes; "
        f"H-2 dispatch + H-A in-place + H-B outplace) version={a23.A23_VERSION}"
    )
    return True


__all__ = ["install_overlay"]
