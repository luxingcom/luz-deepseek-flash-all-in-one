"""The verify_cap dead-row remap folded into the router kernel (DSV41_ROUTER_LIVE=1, needs DSV41_VERIFY_CAP).

verify_cap copies the anchor row's router ids/weights over every dead verify row with a separate
kernel after the router (40 launches, ~0.21 ms/step at c1). Here the router kernel itself loads the
ANCHOR row's scores (and token id) for dead rows, so it computes the anchor's ids and weights for
them: the same values the copy produced, one launch fewer per layer. Built from the engine's own
module source with text substitutions; any drift in that source disables the patch at import.

Re-anchored 2026-10-01 on main-79cafec0 (sglang.kernels.ops.moe.moe_fused_gate): the wrapper grew
``sqrtsoftplus_log1p`` after ``packed_out``, and a K3 radix-select fast path now bypasses the
triton kernel (gated off when live= is passed so the remap cannot be skipped). packed_out itself
is transparent to the wrap: the kernel's HAS_PACKED store emits the anchor's packed ids/weights
for dead rows, exactly what remapping the packed tensor would produce.
"""
import importlib.util
import inspect
import os
import tempfile

import torch

ENABLED = os.environ.get("DSV41_ROUTER_LIVE", "0").strip() not in ("0", "", "off", "false")

_SUBS = [
    # kernel signature: the live-length buffer and the verify stride
    ("    stride_pk,\n) -> None:\n",
     "    stride_pk,\n    live_ptr,\n    LIVE: tl.constexpr,\n    LIVE_STRIDE: tl.constexpr,\n) -> None:\n"),
    # dead rows read the anchor row (first row of their request)
    ("    live_m = mask_m\n",
     "    live_m = mask_m\n"
     "    src_m = offs_m\n"
     "    if LIVE:\n"
     "        req = offs_m // LIVE_STRIDE\n"
     "        lv = tl.load(live_ptr + req, mask=mask_m, other=LIVE_STRIDE)\n"
     "        src_m = tl.where((offs_m % LIVE_STRIDE) >= lv, req * LIVE_STRIDE, offs_m)\n"),
    ("    row_ptr = scores_ptr + offs_m[:, None] * stride_sm + offs_n[None, :] * stride_sn\n",
     "    row_ptr = scores_ptr + src_m[:, None] * stride_sm + offs_n[None, :] * stride_sn\n"),
    ("        input_ids = tl.load(\n            input_ids_ptr + offs_m * stride_input_ids, mask=live_m, other=0\n        )\n",
     "        input_ids = tl.load(\n            input_ids_ptr + src_m * stride_input_ids, mask=live_m, other=0\n        )\n"),
    # python wrapper: accept live=, stride= and pass them on. Anchor re-anchored on
    # main-79cafec0: packed_out is no longer the last kw-only param (sqrtsoftplus_log1p
    # was added after it); our extras append after it, so engine kwargs still flow.
    ("    packed_out: Optional[torch.Tensor] = None,\n    sqrtsoftplus_log1p: bool = False,\n) -> Tuple[torch.Tensor, torch.Tensor]:\n",
     "    packed_out: Optional[torch.Tensor] = None,\n    sqrtsoftplus_log1p: bool = False,\n"
     "    live: Optional[torch.Tensor] = None,\n    live_stride: int = 6,\n) -> Tuple[torch.Tensor, torch.Tensor]:\n"),
    # main-79cafec0 K3 radix-select fast path returns without launching the triton
    # kernel, which would silently skip the dead-row remap; never take it with live=
    ("        and packed_out is None\n        and bias.stride(0) == 1\n    ):\n",
     "        and packed_out is None\n        and live is None\n        and bias.stride(0) == 1\n    ):\n"),
]


def build(module):
    """Exec a patched copy of sglang.kernels.ops.moe.moe_fused_gate; return its moe_fused_gate."""
    src = inspect.getsource(module)
    for a, b in _SUBS:
        if src.count(a) != 1:
            raise RuntimeError(f"router_live: engine source drifted ({a.strip()[:40]!r})")
        src = src.replace(a, b)
    tail = "        stride_pk=packed_out.stride(1) if packed_out is not None else 0,\n"
    if src.count(tail) != 1:
        raise RuntimeError("router_live: engine launch drifted")
    src = src.replace(tail, tail + "        live_ptr=live if live is not None else _unused_i32,\n"
                      "        LIVE=live is not None,\n        LIVE_STRIDE=live_stride,\n")
    # Triton reads @jit sources from a real file
    path = os.path.join(tempfile.gettempdir(), f"dsv41_router_live_{os.getpid()}.py")
    with open(path, "w") as f:
        f.write(src)
    spec = importlib.util.spec_from_file_location("dsv41_router_live", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.moe_fused_gate
