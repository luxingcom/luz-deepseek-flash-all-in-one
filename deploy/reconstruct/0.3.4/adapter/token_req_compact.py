"""S1b (R4) landmine 2: compact ragged-verify x token_req_indices equal-block fix.

The engine's dsv41_sparse.token_req_indices maps each token row to its owning
request. Its target-verify branch assumes one equal [bs, draft_token_num]
block per request and asserts that shape through repeat_interleave's
output_size (main-79cafec0 dsv41_sparse.py:66):

    return torch.repeat_interleave(
        req, int(forward_batch.spec_info.draft_token_num), output_size=num_tokens
    )

SGLANG_RAGGED_VERIFY_MODE=compact feeds the low-ratio source path a
token-bucket ragged window instead: per-request verify_lens vary in [1, width]
and the window is padded to the graph tier (A9R: tier 84 for 16 slots of
width 6 = bs*draft 96), so at graph capture

    RuntimeError: repeat_interleave: Invalid output_size, expected 96 but got 84

fires at decode_cuda_graph_runner.capture_one_shape -> ... -> backend
forward_low_ratio_sources (:2731) -> token_req_indices. Even where the shape
happens to align, t // draft_token_num is the wrong row attribution under
ragged lens -- the fix must map rows from the layout, not relax the shape.

Adapter-side fix (the engine mirror is read-only): wrap
dsv41_sparse.token_req_indices. On a compact verify batch
(spec_info.ragged_verify_layout present, mode compact) attribute each row t
via the layout's verify_lens (inclusive cumsum + searchsorted right=True --
the same mapping as the engine's own compact_row_index /
expand_prefill_causally helpers) and gather req_pool_indices by that row.
Pad rows (t >= sum(lens), which only exist to fill the captured tier) clamp
to the last request, exactly the engine's own pad convention
(expand_prefill_causally's triton kernel: "r = tl.where(is_real, r, bs - 1)"):
their outputs are discarded downstream -- the compressor masks rows whose
raw_out_loc == 0 and the window builder zeroes pad positions/locs.

CUDA-graph correctness: the computation is a fixed-shape op chain
(cumsum / arange / searchsorted / clamp / gather) over num_tokens, which the
caller pins to the tier (positions.shape[0]) and which is the graph key
invariant. Under replay the only live input it reads is
layout.verify_lens -- the one tensor decode_cuda_graph_runner
_stage_ragged_verify_layout refreshes IN PLACE -- plus the staged
req_pool_indices buffer, so the captured ops recompute the live mapping.
It never reads layout.extend_start_loc / total_verify_tokens on the graph
path (both stale under replay; total only feeds the num_tokens=None eager
shape). No data-dependent allocation, no host sync.

Arm gate: installed only when SGLANG_RAGGED_VERIFY_MODE=compact at import
(read through the engine's own envs). Any other boot keeps the engine
function byte-identical -- no wrapper is installed at all.

Double-module trap: deepseek_v4_backend.py:65 does
`from ...dsv41_sparse import token_req_indices`, so the from-import binds a
private reference at exec. install_sparse wraps the defining module;
install_backend rebinds the backend's module-level name (all three call
sites -- :2086 decode-gated, :2731 verify, :2767 CP extend -- resolve through
that binding). install_backend may run before or after the sparse module
exec'd; it imports and arms the sparse side itself so every order converges.
"""

import inspect
import logging
import os

import torch

logger = logging.getLogger(__name__)

_MARKER = "_dsv41_token_req_compact"
# Engine seams this adapter rides; a drift here must refuse the boot, not
# silently no-op (an inert wrap would put the A9R repeat_interleave crash
# right back on the next compact graph capture).
_SEAMS = ("token_req_indices",)

_state = {"armed": False, "sparse": None, "orig": None}


def summary() -> str:
    env = os.environ.get("SGLANG_RAGGED_VERIFY_MODE")
    return (f"armed={_state['armed']} mode={env} "
            f"seams={'+'.join(_SEAMS)} rebound=backend")


def _compact_layout(forward_batch):
    """The batch's ragged verify layout, or None when this is not a compact
    verify batch. Layout presence is exclusive to the compact path on
    TARGET_VERIFY batches (the non-compact runner attaches no layout), and
    the env mode is re-checked so a future non-compact layout can never be
    remapped."""
    mode = getattr(forward_batch, "forward_mode", None)
    if mode is None or not mode.is_target_verify():
        return None
    spec = getattr(forward_batch, "spec_info", None)
    layout = getattr(spec, "ragged_verify_layout", None)
    if layout is None:
        return None
    try:
        from sglang.srt.environ import envs
        from sglang.srt.speculative.ragged_verify import RaggedVerifyMode
        if envs.SGLANG_RAGGED_VERIFY_MODE.get() != RaggedVerifyMode.COMPACT.value:
            return None
    except Exception:
        return None
    return layout


def _token_req_compact(forward_batch, layout, num_tokens):
    """Per-token request indices from the ragged layout.

    Row r of token t comes from the layout's verify_lens (inclusive cumsum,
    searchsorted right=True -- BuildRaggedVerifyWindow's compact_row_index
    mapping). Rows past the live total clamp to the last request: they only
    exist to fill the captured tier and their outputs are discarded
    downstream (out_cache_loc == 0 / position == 0 pads). Zero-length pad
    requests are skipped naturally by searchsorted right=True.
    """
    req = forward_batch.req_pool_indices.to(torch.int64)
    if num_tokens is None:
        total = getattr(layout, "total_verify_tokens", None)
        num_tokens = int(total) if total is not None else int(
            layout.graph_num_tokens
        )
    verify_lens = layout.verify_lens.to(device=req.device, dtype=torch.int64)
    # Replay-staged verify_lens is the only live source of run boundaries;
    # never layout.extend_start_loc (stale under replay -- not staged).
    incl = torch.cumsum(verify_lens, dim=0)
    t = torch.arange(int(num_tokens), device=req.device)
    row = torch.searchsorted(incl, t, right=True)
    row = torch.clamp(row, max=min(int(verify_lens.shape[0]),
                                   max(int(req.shape[0]), 1)) - 1)
    return req[row]


def _seam_check(module) -> None:
    func = getattr(module, "token_req_indices", None)
    if not callable(func):
        raise RuntimeError(_refuse("token_req_indices missing on dsv41_sparse"))
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        raise RuntimeError(_refuse("token_req_indices signature unreadable"))
    param = sig.parameters.get("num_tokens")
    if param is None or param.kind not in (
        inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD
    ):
        raise RuntimeError(_refuse(
            "token_req_indices lost its num_tokens parameter"))
    try:
        source = inspect.getsource(func)
    except OSError:
        source = ""
    if "draft_token_num" not in source or "repeat_interleave" not in source:
        # The engine equal-block branch we bypass has moved or been rewritten
        # (possibly fixed upstream): stacking a wrap on an unknown shape is
        # not ours to decide -- refuse the boot loudly.
        raise RuntimeError(_refuse(
            "token_req_indices no longer shows the equal-block verify branch"))
    try:
        from sglang.srt.environ import envs  # noqa: F401
        from sglang.srt.speculative.ragged_verify import RaggedVerifyMode  # noqa: F401
    except Exception as exc:
        raise RuntimeError(_refuse(f"ragged_verify seams unavailable: {exc}"))


def _refuse(reason: str) -> str:
    return (f"token-req-compact: seam moved ({reason}); refusing to boot -- "
            "the compact verify fix would otherwise silently no-op and crash "
            "at the engine's repeat_interleave equal-block check")


def install_sparse(module) -> bool:
    """Wrap dsv41_sparse.token_req_indices for compact boots; refuse loudly
    on drift. Non-compact boots leave the engine function untouched."""
    if any(not hasattr(module, name) for name in _SEAMS):
        raise RuntimeError(_refuse("dsv41_sparse seam missing"))
    if getattr(module, _MARKER, False):
        return False  # already installed (double exec of the module)
    try:
        from sglang.srt.environ import envs
        mode = envs.SGLANG_RAGGED_VERIFY_MODE.get()
    except Exception:
        mode = None
    if mode != "compact":
        # static / cap-accept / unset: leave the engine function untouched.
        return False
    _seam_check(module)

    orig = module.token_req_indices

    def token_req_indices(forward_batch, *, num_tokens=None):
        layout = _compact_layout(forward_batch)
        if layout is None:
            return orig(forward_batch, num_tokens=num_tokens)
        return _token_req_compact(forward_batch, layout, num_tokens)

    module.token_req_indices = token_req_indices
    setattr(module, _MARKER, True)
    _state.update(armed=True, sparse=module, orig=orig)
    logger.warning(
        "DSV41 token_req_indices compact-verify wrap ARMED: target-verify "
        "rows map through the ragged layout, equal-block repeat_interleave "
        "bypassed"
    )
    return True


def install_backend(module) -> bool:
    """Rebind deepseek_v4_backend's from-imported token_req_indices to the
    wrap. Covers every exec order: arms the sparse side first (a no-op when
    already armed or when the boot is not compact), then points the backend
    module-level name at whatever the defining module now exports. On a
    non-compact boot the name keeps pointing at the original function."""
    import sglang.srt.layers.attention.dsv4.dsv41_sparse as sparse
    install_sparse(sparse)
    if _state["armed"] and module.token_req_indices is not sparse.token_req_indices:
        module.token_req_indices = sparse.token_req_indices
        logger.warning(
            "DSV41 token_req_indices backend binding rebound to the compact wrap"
        )
    return _state["armed"]
