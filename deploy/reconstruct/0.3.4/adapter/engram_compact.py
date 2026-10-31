"""S1b (R4): compact ragged-verify x engram target-verify equal-block fix.

The engine's EngramHasher.forward asserts a target-verify batch is one equal
[bs, draft_token_num] block per request ("engram target-verify expects one
equal block per request", main-79cafec0 engram.py:300). SGLANG_RAGGED_VERIFY_
MODE=compact feeds the hasher a token-bucket ragged window instead: per-request
verify_lens vary in [1, width] and the window is padded to the graph tier
(A9: 84 tokens for 16 requests of 6), so the assert fires on the first compact
verify forward -- graph capture and eager alike (logs/A9-SPS2D-compact-spec1).

Adapter-side fix (the engine mirror is read-only): wrap EngramHasher.forward.
On a compact verify batch (spec_info.ragged_verify_layout present and mode
compact) hash through the hash kernel's existing MODE_EXTEND row/offset
machinery with row/starts derived from the layout's verify_lens. The
predecessor semantics of one request's verify run (anchor + drafts, per-request
history row before it) are identical to an extend run, so each real row's hash
is bit-identical to what the equal-block path computes for the same run laid
out uniformly. Verify never commits history in the forward (commit happens in
commit_after_verify), and the compact path keeps that property.

Arm gate: installed only when SGLANG_RAGGED_VERIFY_MODE=compact at import
(read through the engine's own envs). Any other boot keeps the class's forward
byte-identical -- no wrapper is installed at all.

CUDA-graph correctness: row/starts are derived inside the forward by torch ops
(cumsum / searchsorted / arange) reading the layout's verify_lens tensor.
Under replay that tensor is the one decode_cuda_graph_runner stages in place
(_stage_ragged_verify_layout copies verify_lens and qo_indptr_device), so the
captured ops recompute from the live lens. extend_start_loc and
total_verify_tokens on the captured layout are NOT staged and are never read
here: starts is recomputed from verify_lens, and total_verify_tokens only
feeds num_real where a stale capture-time value (= the tier, capture layouts
sum to the tier) is safe -- see the pad-row proof in ENGRAIN-COMPACT-FIX.md.
"""

import logging
import os

import torch

logger = logging.getLogger(__name__)

_MARKER = "_dsv41_engram_compact"
# Engine seams this adapter reuses; a drift here must refuse the boot, not
# silently no-op (an inert wrap would put the A9 assert back invisibly).
_SEAMS = ("EngramHasher", "engram_hash_ids", "MODE_EXTEND", "MM_PAD_SHIFT_VALUE")

_state = {"armed": False, "module": None, "orig": None}


def summary() -> str:
    env = os.environ.get("SGLANG_RAGGED_VERIFY_MODE")
    return (f"armed={_state['armed']} mode={env} "
            f"seams={'+'.join(_SEAMS)}")


def _compact_layout(forward_batch):
    """The batch's ragged verify layout, or None when this is not a compact
    verify batch. Layout presence is exclusive to the compact path on
    TARGET_VERIFY batches (run_non_compact attaches no layout), and the env
    mode is re-checked so a future non-compact layout can never be remapped."""
    mode = getattr(forward_batch, "forward_mode", None)
    if mode is None:
        return None
    is_verify = mode.is_target_verify() or mode.is_idle()
    if not is_verify:
        return None
    spec = getattr(forward_batch, "spec_info", None)
    layout = getattr(spec, "ragged_verify_layout", None)
    if layout is None:
        return None
    try:
        module = _state["module"]
        from sglang.srt.speculative.ragged_verify import RaggedVerifyMode
        if module.envs.SGLANG_RAGGED_VERIFY_MODE.get() != RaggedVerifyMode.COMPACT.value:
            return None
    except Exception:
        return None
    return layout


def _hash_compact(hasher, input_ids, forward_batch, layout):
    """Hash a compact verify window through the kernel's MODE_EXTEND path.

    Row r of token t and its offset inside the run come from the layout's
    verify_lens (inclusive cumsum), matching BuildRaggedVerifyWindow's
    compact_row_index mapping (searchsorted right=True over the cumsum). Rows
    past the live total clamp to the last request: they only exist to fill the
    captured tier and their hashes are discarded downstream.
    """
    module = _state["module"]
    num_tokens = input_ids.shape[0]
    device = input_ids.device
    req_slots = forward_batch.req_pool_indices
    verify_lens = layout.verify_lens.to(device=device, dtype=torch.int64)
    # Replay-staged verify_lens is the only live source of run boundaries;
    # never layout.extend_start_loc (stale under replay -- not staged).
    incl = torch.cumsum(verify_lens, dim=0)
    starts = incl - verify_lens
    t = torch.arange(num_tokens, device=device)
    row = torch.searchsorted(incl, t, right=True)
    row = torch.clamp(row, max=min(int(verify_lens.shape[0]),
                                   max(int(req_slots.shape[0]), 1)) - 1)
    total = layout.total_verify_tokens
    num_real = num_tokens if total is None else min(int(total), num_tokens)
    positions = forward_batch.positions
    if input_ids.is_cuda and torch.version.cuda is not None:
        hash_ids, _tokens = module.engram_hash_ids(
            input_ids,
            positions,
            mode=module.MODE_EXTEND,
            history=hasher.history,
            token_map=hasher.token_map,
            multipliers=hasher.multipliers,
            primes=hasher.primes,
            offsets=hasher.offsets,
            pad_id=hasher.pad_id,
            num_real=num_real,
            req_slots=req_slots,
            block=1,
            row=row,
            starts=starts,
            image_token_id=hasher.image_token_id,
            mm_pad_shift=module.MM_PAD_SHIFT_VALUE,
        )
        return hash_ids
    history = hasher.history
    if history is not None and req_slots is not None:
        history = history[req_slots.to(history.device)]
    # The torch fallback walks t = arange(num_real), so row must have exactly
    # num_real entries there; the CUDA kernel masks t >= num_real itself and
    # takes the full-length row.
    hash_ids, _tokens = hasher._torch_hash_ids(
        input_ids, positions, module.MODE_EXTEND, history,
        num_real, 1, row[:num_real], starts,
    )
    return hash_ids


def install(module) -> bool:
    """Wrap EngramHasher.forward for compact boots; refuse loudly on drift."""
    if getattr(module, "EngramHasher", None) is None or any(
        not hasattr(module, name) for name in _SEAMS
    ):
        raise RuntimeError(
            f"engram-compact: seam moved (need {', '.join(_SEAMS)} on "
            "sglang.srt.layers.engram); refusing to boot -- the compact "
            "verify fix would otherwise silently no-op and crash at the "
            "engine's equal-block assert"
        )
    if getattr(module.EngramHasher, _MARKER, False):
        return False  # already installed (double exec of the module)
    try:
        mode = module.envs.SGLANG_RAGGED_VERIFY_MODE.get()
    except Exception:
        mode = None
    if mode != "compact":
        # static / cap-accept / unset: leave the engine class untouched.
        return False

    orig_forward = module.EngramHasher.forward

    def forward(self, input_ids, forward_batch):
        layout = _compact_layout(forward_batch)
        if layout is None:
            return orig_forward(self, input_ids, forward_batch)
        return _hash_compact(self, input_ids, forward_batch, layout)

    module.EngramHasher.forward = forward
    setattr(module.EngramHasher, _MARKER, True)
    _state.update(armed=True, module=module, orig=orig_forward)
    logger.warning(
        "DSV41 Engram compact-verify wrap ARMED: target-verify hashes via the "
        "ragged layout (MODE_EXTEND rows), equal-block assert bypassed"
    )
    return True
