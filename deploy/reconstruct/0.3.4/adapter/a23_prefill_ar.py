"""A23: prefill-band selective AR routing face, v2 -- FIVE switchable modes.

Design source: dev/a23-prefill-ar/DESIGN.md (2026-10-06) + the routing
verdict of docs/research/COMMUNITY-R2-BLOCKED-FACES-20261006.md (主会话路由
裁定, face 3): if the E0 wash hypothesis confirms on the ring topology, the
hedge order is two-shot -> FlashInfer quantized_all_reduce FP8 two-shot ->
TBO -- one-shot is no longer the only form the wiring may assume.  v2 makes
the transport a ROUTING KEY instead:

    DSV41_PREFILL_AR_MODE = off | nccl | oneshot | twoshot | fi_fp8
                            (default/missing = off = stock, byte-for-byte)

    off       nothing wraps; the module is inert (zero-behavior key rule).
    nccl      wrapper installed, banners/stats live, but EVERY tensor takes
              the original path: the wrapper-neutrality control arm.
    oneshot   the v1 form: a SECOND, independent b12x RoCEnante runtime
              (created on the TP pynccl communicator, max_size = band max)
              serves in-band tensors.  Decode runtime (comm.roce, 256K cap,
              A22B face) is never touched.
    twoshot   two-step RS+AG composition (torch.distributed
              .reduce_scatter_tensor + all_gather_into_tensor on the
              coordinator's device group): 1.5N byte tax, the TBO stepping
              stone -- see overlay/a23_forms.exec_twoshot for the honest
              rounds note.
    fi_fp8    flashinfer.comm.quantized_all_reduce (FP8 two-shot over
              symmetric memory): the only open-source path below the 1.5N
              floor; LOSSY quantized form -- B/A parity faces do not apply,
              its gate is the C-face semantic window (win card §四).

Layering: this module owns the gates, the mode resolution, the byte band and
the second-runtime face; the GroupCoordinator wraps live in the overlay/
subtree (overlay.install_overlay: H-2 dispatch + H-A in-place + H-B
out-place, parallel_state.py:645/:1018/:973) and the form executors live in
overlay/a23_forms.py.

Key discipline (fail-loud, never guess):
    - bad MODE value                    -> RuntimeError at install
    - MODE form set but SGLANG_ROCE_PREFILL_AR!=1 (总门)  -> RuntimeError
    - MODE=oneshot without the A22B pair (DSV41_ROCE_RING /
      SGLANG_ROCE_ALLREDUCE)            -> RuntimeError
    - band overlapping the A22B decode cap 262144 -> RuntimeError (the two
      bands must stay disjoint; assertion re-run in the overlay install)
    - legacy SGLANG_ROCE_PREFILL_AR=1 with no MODE: stays stock with a loud
      banner (v1 implicitly-oneshot arming no longer exists)

Band keys (unchanged): SGLANG_ROCE_PREFILL_MIN_BYTES (default 8 MiB),
SGLANG_ROCE_PREFILL_MAX_BYTES (default 42 MiB -- covers the 4096x5120x2B =
40 MiB chunk AR; decode ARs max ~1MB << 8MiB, so the bands never overlap).

Routing predicate (group-consistent: dtype/shape/size/world only, never the
pointer -- every TP rank decides identically):  eligible_for_mode().
"""
from __future__ import annotations

import json
import logging
import os
import weakref

logger = logging.getLogger(__name__)

A23_VERSION = "a23-prefill-ar-2"

DEFAULT_MIN_BYTES = 8 * 1024 * 1024     # 8 MiB (>=819-token chunks enter the band)
DEFAULT_MAX_BYTES = 42 * 1024 * 1024    # 42 MiB (covers 4096x5120x2B = 40 MiB)

MODE_KEY = "DSV41_PREFILL_AR_MODE"
MODES = ("off", "nccl", "oneshot", "twoshot", "fi_fp8")
REPLACEMENT_MODES = ("oneshot", "twoshot", "fi_fp8")   # forms that reroute bytes
DECODE_CAP_BYTES = 262144                              # A22B decode cap (C29)

STATS = {
    "communicators": 0,       # PyNcclCommunicator constructions seen
    "a23_made": 0,            # prefill-band runtimes created (oneshot, TP group)
    "prefill_routed": 0,      # in-band ARs rerouted at H-A
    "dispatch_routed": 0,     # in-band ARs rerouted at the H-2 dispatch
    "outplace_routed": 0,     # out-of-place ARs rerouted (H-B)
    "nccl_kept": 0,           # ARs left on the original NCCL path
    "routed_oneshot": 0,      # per-mode reroute counters (banner/census face)
    "routed_twoshot": 0,
    "routed_fi_fp8": 0,
    "fi_warmed": 0,           # fi_fp8 boot-time warmups (TP construction)
    "mode": "off",            # last resolved DSV41_PREFILL_AR_MODE
}

_a23_runtimes = weakref.WeakSet()   # health walks + banner accounting
_group_name_stack: list = []        # own stack; composable with roce_ar's
_ar_dtypes = None                   # (bf16, fp32) resolved at install
_bf16 = None


def _flag(name: str) -> bool:
    return os.environ.get(name, "0").strip() == "1"


# ---------------------------------------------------------------------------
# mode resolution (single source; the overlay and both install faces ask here)
# ---------------------------------------------------------------------------

def resolve_mode():
    """Resolve DSV41_PREFILL_AR_MODE -> None (=off/stock) or a mode string.

    Fail-loud on a bad key or key combination (a wrong routing key must stop
    the boot, not quietly run stock); loud-but-inert on the legacy v1 arming.
    """
    raw = os.environ.get(MODE_KEY)
    if raw is None or raw.strip() == "" or raw.strip().lower() == "off":
        if _flag("SGLANG_ROCE_PREFILL_AR"):
            # v1 armed implicitly-oneshot on this key alone; v2 does not.
            _banner(
                "SGLANG_ROCE_PREFILL_AR=1 without " + MODE_KEY + ": staying "
                "stock (v2 routes by MODE; oneshot = " + MODE_KEY + "=oneshot)"
            )
        STATS["mode"] = "off"
        return None
    mode = raw.strip().lower()
    if mode not in MODES:
        raise RuntimeError(
            f"bad {MODE_KEY}={raw!r}: valid values are {'/'.join(MODES)} "
            "(fail-loud: refusing to guess a transport form)"
        )
    if not _flag("SGLANG_ROCE_PREFILL_AR"):
        raise RuntimeError(
            f"{MODE_KEY}={mode} but SGLANG_ROCE_PREFILL_AR!=1: a form was "
            "selected while the A23 total gate is closed -- wiring defect, "
            "refusing to silently run stock"
        )
    if mode == "oneshot" and not (
        _flag("DSV41_ROCE_RING") and _flag("SGLANG_ROCE_ALLREDUCE")
    ):
        raise RuntimeError(
            "DSV41_PREFILL_AR_MODE=oneshot needs the A22B face keys "
            "DSV41_ROCE_RING=1 and SGLANG_ROCE_ALLREDUCE=1 (the b12x runtime "
            "mount); refusing to arm oneshot half-keyed"
        )
    STATS["mode"] = mode
    return mode


def gates_on() -> bool:
    """v2 gate face: some non-off mode resolves (may raise on a bad key)."""
    return resolve_mode() is not None


def stats() -> dict:
    return dict(STATS, runtimes=len(_a23_runtimes), version=A23_VERSION)


def note_stat(key: str, delta: int = 1) -> None:
    """Counter bump used by the overlay wraps (unknown keys start at 0)."""
    STATS[key] = STATS.get(key, 0) + delta


def _banner(line: str) -> None:
    # print (boot-log acceptance reads stdout, sitecustomize convention) + logger
    print(f"[a23_prefill_ar] {line}", flush=True)
    logger.info("A23_PREFILL_AR %s", line)


# ---------------------------------------------------------------------------
# group-name window (pushed by the overlay __init__ wrap; read by the pynccl
# face while the TP communicator constructs inside it)
# ---------------------------------------------------------------------------

def push_group_name(name) -> None:
    _group_name_stack.append(name)


def pop_group_name() -> None:
    _group_name_stack.pop()


def current_group_name():
    return _group_name_stack[-1] if _group_name_stack else None


# ---------------------------------------------------------------------------
# band predicate (mirror of a23_parity_core.in_prefill_band; kept local so the
# adapter is a single self-contained file on the machine side)
# ---------------------------------------------------------------------------

def band_from_env() -> tuple:
    min_b = int(os.environ.get("SGLANG_ROCE_PREFILL_MIN_BYTES", str(DEFAULT_MIN_BYTES)))
    max_b = int(os.environ.get("SGLANG_ROCE_PREFILL_MAX_BYTES", str(DEFAULT_MAX_BYTES)))
    if min_b <= 0 or max_b <= min_b:
        raise RuntimeError(
            f"invalid A23 prefill band: min={min_b} max={max_b} "
            "(need 0 < min < max; refuse to arm a nonsense band)"
        )
    if min_b <= DECODE_CAP_BYTES:
        raise RuntimeError(
            f"A23 prefill band min={min_b} overlaps the A22B decode cap "
            f"{DECODE_CAP_BYTES}; the decode face must stay untouched "
            "(A22B verdict; two bands, zero intersection)"
        )
    return min_b, max_b


# kept v1 name (tests + probe import it)
_band = band_from_env


def _in_prefill_band(nbytes: int, band: tuple) -> bool:
    min_b, max_b = band
    return min_b <= nbytes <= max_b and nbytes % 16 == 0


def ensure_dtypes():
    """Resolve (bf16, fp32) via torch once (engine imports torch long before)."""
    global _ar_dtypes, _bf16
    if _ar_dtypes is None:
        import torch

        _bf16 = torch.bfloat16
        _ar_dtypes = (torch.bfloat16, torch.float32)
    return _ar_dtypes


def eligible_for_mode(coord, tensor, mode: str) -> bool:
    """Group-consistent per-mode eligibility (dtype/shape/size/world only).

    oneshot: bf16|fp32 + band + the armed second runtime (a poisoned runtime
             RAISES here: a failed collective is fatal, never a fallback).
    twoshot: bf16|fp32 + band + numel % world == 0 (reduce-scatter splits).
    fi_fp8:  bf16 ONLY (FI API contract) + band + numel % 8 == 0.
    """
    ensure_dtypes()
    if tensor.dtype not in _ar_dtypes or not tensor.is_cuda:
        return False
    if not tensor.is_contiguous():
        return False
    nbytes = tensor.numel() * tensor.element_size()
    if not _in_prefill_band(nbytes, band_from_env()):
        return False
    world = int(getattr(coord, "world_size", 0) or 0)
    numel = tensor.numel()
    if mode == "oneshot":
        comm = getattr(coord, "pynccl_comm", None)
        runtime = getattr(comm, "a23_roce", None) if comm is not None else None
        if runtime is None:
            return False
        runtime.check_health()          # poisoned => raises (fail-loud)
        return True
    if mode == "twoshot":
        return world > 1 and numel % world == 0
    if mode == "fi_fp8":
        return tensor.dtype == _bf16 and numel % 8 == 0
    return False                        # "nccl" reroutes nothing by design


# ---------------------------------------------------------------------------
# face 1: pynccl -- create the second runtime on the TP communicator
# (oneshot only; the other modes need no b12x runtime)
# ---------------------------------------------------------------------------

def install_pynccl_face(module) -> bool:
    """Wrap PyNcclCommunicator.__init__ to arm the prefill-band runtime.

    With MODE=oneshot (installed AFTER c1-dev/roce_ar.install on the same
    class) the TP communicator gets the SECOND, independent runtime
    (comm.a23_roce, max_size = band max); the A22B decode runtime (comm.roce,
    256K) is created by c1-dev/roce_ar.py and never touched.  Other non-off
    modes need no runtime: the face arms banner-only.  Inert when off.
    """
    mode = resolve_mode()
    if mode is None:
        return False
    band = band_from_env()
    ensure_dtypes()

    if mode != "oneshot":
        _banner(
            f"armed pynccl face (mode={mode}; second b12x runtime not "
            f"required; decode face untouched) version={A23_VERSION}"
        )
        return True

    cls = module.PyNcclCommunicator
    orig_init = cls.__init__

    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self.a23_roce = None
        self.a23_band = band
        STATS["communicators"] += 1
        if not _group_name_stack or _group_name_stack[-1] != "tp":
            return  # only the TP group arms the prefill face
        if self.world_size == 1:
            return
        if self.world_size != 4:
            raise RuntimeError(
                f"A23 prefill face needs the TP4 group, got world={self.world_size}"
            )
        import importlib

        mod_name = (
            "b12x.comm.roce_ring"
            if os.environ.get("DSV41_ROCE_RING", "0") == "1"
            else "b12x.comm.roce"
        )
        roce_mod = importlib.import_module(mod_name)
        self.a23_roce = roce_mod.AllReduce.from_exchange_group(
            exchange_group=self.group,
            device=self.device,
            max_size=band[1],
            max_gather_bytes=0,           # AR only; the AG face is not A23's
        )
        self.a23_roce.prepare(_ar_dtypes)
        _a23_runtimes.add(self.a23_roce)
        STATS["a23_made"] += 1
        ready = f"ROCE_A23_PREFILL_READY {json.dumps(self.a23_roce.stats())} band={band}"
        _banner(ready)

    cls.__init__ = __init__
    _banner(
        f"armed pynccl face (mode=oneshot prefill band {band[0]}..{band[1]} "
        f"bytes; decode face untouched) version={A23_VERSION}"
    )
    return True


# ---------------------------------------------------------------------------
# face 2: parallel_state -- route in-band ARs (mounts H-2/H-A/H-B via overlay/)
# ---------------------------------------------------------------------------

def install_group_face(module) -> bool:
    """Wrap GroupCoordinator: H-2 dispatch + H-A in-place + H-B out-place.

    The wraps themselves live in the overlay/ subtree (install_overlay); this
    entry keeps the v1 install surface and routes through the mode resolver.
    Inert when off; raises on a bad mode key (fail-loud).
    """
    if resolve_mode() is None:
        return False
    from overlay import install_overlay   # lazy: adapter dir on sys.path

    return install_overlay(module)


def synchronize_and_check_a23() -> None:
    """Health hook for the scheduler wiring (I14-C face, same as roce_ar)."""
    for runtime in tuple(_a23_runtimes):
        runtime.check_health()


__all__ = [
    "A23_VERSION", "DEFAULT_MIN_BYTES", "DEFAULT_MAX_BYTES",
    "MODE_KEY", "MODES", "REPLACEMENT_MODES", "DECODE_CAP_BYTES",
    "STATS", "stats", "gates_on", "note_stat", "resolve_mode",
    "band_from_env", "ensure_dtypes", "eligible_for_mode",
    "push_group_name", "pop_group_name", "current_group_name",
    "install_pynccl_face", "install_group_face", "synchronize_and_check_a23",
]
