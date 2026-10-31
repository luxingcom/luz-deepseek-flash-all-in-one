"""A23 replacement forms: the three switchable transports behind the MODE key.

Routing verdict source (docs/research/COMMUNITY-R2-BLOCKED-FACES-20261006.md,
主会话路由裁定 2026-10-06, face 3): if the A23 E0 wash hypothesis confirms,
the hedge order is  two-shot -> FlashInfer quantized_all_reduce FP8 two-shot
-> TBO compute overlap  -- the one-shot unilateral route structurally yields
on the ring topology.  The wiring here therefore makes all three forms
switchable keys (DSV41_PREFILL_AR_MODE=off/nccl/oneshot/twoshot/fi_fp8 in
a23_prefill_ar.py), not just the original one-shot.

Form registry (every executor: (coord, input_, *, out=None) -> tensor):

    oneshot  the v1 form: the SECOND b12x RoCEnante runtime (independent
             instance, max_size=band max, created by a23_prefill_ar's pynccl
             face) serves the in-band tensor.  Fixed rank order, fp32
             accumulate, single rounding (B-face deterministic form).
    twoshot  two-step RS+AG: torch.distributed.reduce_scatter_tensor then
             all_gather_into_tensor on the coordinator's device group.
             Byte tax per rank = 2*(R-1)/R*N = 1.5N -- same as the ring AR,
             but the collective is split into two calls: the stepping stone
             for TBO (RS | local compute | AG overlap) and the mount where a
             future per-shard direct kernel (b12x per-shard reduce) slots in.
             HONESTY NOTE: on the NCCL transport each leg is still
             ring-chunked (3+3 steps for R=4); the "6->2 rounds" claim of the
             hedge order is realized only on a direct per-shard transport.
             E0 times the composed form on the live fabric either way.
    fi_fp8   flashinfer.comm.quantized_all_reduce(inp, group, ...): native
             FP8 two-shot over symmetric memory, the only open-source path
             below the 1.5N byte floor (halved payload).  FI API verification
             (desk, 2026-10-06): `import flashinfer` is NOT importable on the
             desk python; the API is absent from the srt 0.2.8 tree (grep
             quantized_all_reduce = zero hits) but present and IDENTICAL in
             the local FI sources w6-kit/fi016-src (version.py 0.6.16) and
             w6-kit/fi-main (main): module flashinfer.comm.quantized_allreduce
             :478, lazy export flashinfer/comm/__init__.py:85-88.  In-service
             version = 0.6.18 (dsv41 BUILD-IDENTITY.md:114; JIT cache
             ~/.cache/flashinfer/0.6.18/121a proves the 0.6.18+SM121 pairing).
             SIGNATURE_PIN below is transcribed from those sources verbatim;
             the 0.6.18 import surface itself stays a WINDOW-VERIFY item, as
             does symm-mem rendezvous over the 4-node RoCE fabric (the FI
             docstring assumes NVSwitch; failure there fails LOUD here).

Numerics regime per form (win card G4 / DESIGN.md §4):
    oneshot  B-face bit-equal (vs canonical fixed-order reference) + A-face
             pre-registered ulp band vs NCCL.
    twoshot  still NCCL reduction orders -> A-face band applies; B-face vs
             canonical reference does NOT (cross-backend); determinism /
             cross-rank faces (b2/b3) still apply.
    fi_fp8   FP8 E4M3 with per-block scales is a LOSSY quantization form:
             NEITHER the B-face nor the 3-ulp A-face band applies.  Its gate
             is the C-face semantic window (accept [3.0,3.5] / GSM8K >=0.97 /
             needle) plus record-only diff telemetry.  Do not feed it fp32.

Desk skeleton: no torch/flashinfer at import; executors import lazily and
the fake tests drive them against stub modules.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

# ---------------------------------------------------------------------------
# FlashInfer API pin (window-verify surface; transcribed from the 0.6.16 and
# main sources, which are byte-identical at this function):
#
#   @register_custom_op("flashinfer::quantized_all_reduce", mutates_args=["output"])
#   def quantized_all_reduce(
#       inp: torch.Tensor,
#       group: dist.ProcessGroup,
#       *,
#       scale_group: int = 256,          # SCALE_GROUP_DEFAULT
#       block_size: int | None = None,   # auto: 4096 (<=64MB) / 16384
#       num_warps: int | None = None,    # auto: 16
#       max_num_blocks: int | None = None,
#       p2p_phase3: bool | None = None,  # auto: True for >= 32MiB bf16
#       output: torch.Tensor | None = None,
#   ) -> torch.Tensor
#
# Constraints asserted by the API: bf16 only, contiguous, numel % 8 == 0,
# SM90+ (SM121 qualifies), world size a power of two <= 16 (must divide
# block_size), first call allocates the symmetric-memory buffer collectively
# (call once with the largest expected tensor during warmup).
# ---------------------------------------------------------------------------
FI_OP_NAME = "flashinfer::quantized_all_reduce"
FI_ATTR = "quantized_all_reduce"
FI_MODULE = "flashinfer.comm.quantized_allreduce"
FI_LAZY_EXPORT = "flashinfer/comm/__init__.py:85-88"
FI_SIGNATURE_PIN = (
    "quantized_all_reduce(inp, group, *, scale_group=256, block_size=None, "
    "num_warps=None, max_num_blocks=None, p2p_phase3=None, output=None)",
)
FI_VERIFIED_AGAINST = "w6-kit fi016-src 0.6.16 + fi-main (identical); in-service 0.6.18"


def resolve_fi_quantized_all_reduce() -> Callable:
    """Import and pin flashinfer.comm.quantized_all_reduce, fail-loud.

    Raises RuntimeError (never returns None) when the in-service flashinfer
    lacks the attribute -- that is a window-verification failure of the
    fi_fp8 form and must stop the arm, not silently fall back to NCCL.
    """
    import flashinfer.comm as fic

    fn = getattr(fic, FI_ATTR, None)
    if fn is None:
        raise RuntimeError(
            f"flashinfer.comm has no '{FI_ATTR}' (op {FI_OP_NAME}); the fi_fp8 "
            f"form is unavailable on this FI build. Verified against "
            f"{FI_VERIFIED_AGAINST}; signature pin {FI_SIGNATURE_PIN}. "
            "Refusing to arm fi_fp8 (fail-loud; do not silently route NCCL)."
        )
    return fn


# ---------------------------------------------------------------------------
# form executors
# ---------------------------------------------------------------------------

def exec_oneshot(coord, input_, *, out: Optional = None):
    """v1 form: the second b12x runtime carries the band tensor.

    The runtime lives on coord.pynccl_comm.a23_roce (created by
    a23_prefill_ar.install_pynccl_face under the tp group window); a missing
    runtime means eligibility already said no.  check_health() raises on a
    poisoned runtime: a failed collective is fatal, never a fallback.
    """
    runtime = coord.pynccl_comm.a23_roce
    runtime.check_health()
    return runtime.all_reduce(input_, out=out, stream=None)


def exec_twoshot(coord, input_, *, out: Optional = None):
    """Two-step RS+AG on the coordinator's device group (1.5N byte tax).

    In-place contract: with out=None the gathered result lands in input_
    (the H-A in-place semantics); H-B callers pass out=<fresh tensor>.
    Divisibility (numel % world == 0) is checked by the router, group-
    consistently, before this executor runs.
    """
    import torch
    import torch.distributed as dist

    group = coord.device_group
    world = int(dist.get_world_size(group))
    flat = input_.view(-1)
    shard = torch.empty(flat.numel() // world, dtype=input_.dtype,
                        device=input_.device)
    dist.reduce_scatter_tensor(shard, flat, group=group)
    target = out.view(-1) if out is not None else flat
    dist.all_gather_into_tensor(target, shard, group=group)
    return out if out is not None else input_


def exec_fi_fp8(coord, input_, *, out: Optional = None):
    """FlashInfer FP8 two-shot over symmetric memory (lossy quantized form).

    bf16-only by API contract -- the router must never send fp32 here.
    output= is the in-place variant (mutates_args=["output"]).
    """
    fn = resolve_fi_quantized_all_reduce()
    if out is not None:
        return fn(input_, coord.device_group, output=out)
    return fn(input_, coord.device_group)


def warm_fi_fp8(coord, nbytes: int) -> None:
    """Boot-time warmup: pin the symmetric buffer at the band's max size.

    FI's first call allocates the symmetric-memory buffer collectively (it
    sizes to the largest tensor seen); warming with the band max at TP
    coordinator construction makes the buffer cost a boot-time line item and
    surfaces any rendezvous failure (e.g. symm mem over RoCE without
    NVSwitch) at the CHEAPEST failure point.  Any exception propagates: the
    win card treats key-set-but-cannot-arm as a red stop (A5 discipline),
    never a silent NCCL degrade.
    """
    import torch

    fn = resolve_fi_quantized_all_reduce()
    numel = max(nbytes // 2, 8)          # bf16 element count, %8-safe floor
    warm = torch.empty(numel, dtype=torch.bfloat16, device=coord.device)
    fn(warm, coord.device_group)


# router-facing registry: MODE -> executor (a23_prefill_ar.resolve_mode keys)
FORMS: Dict[str, Callable] = {
    "oneshot": exec_oneshot,
    "twoshot": exec_twoshot,
    "fi_fp8": exec_fi_fp8,
}


__all__ = [
    "FORMS", "exec_oneshot", "exec_twoshot", "exec_fi_fp8", "warm_fi_fp8",
    "resolve_fi_quantized_all_reduce",
    "FI_OP_NAME", "FI_ATTR", "FI_MODULE", "FI_LAZY_EXPORT",
    "FI_SIGNATURE_PIN", "FI_VERIFIED_AGAINST",
]
