"""IH (B-R6 blade): hoist the indexer decode preprocessing shared by every
ratio-1/2 index layer of one forward step (C8-ELEMENTWISE-DEEPDIVE, 2026-10-01).

What the census found (c8, 757 steps): elementwise(tiny) 63.33 ms/step is one
~6.5 ms candidate/page-table preprocessing block executed by EACH of the 8
indexer layers per step (config.index_source_layer_ids = [2, 8, 14, 20, 24,
28, 32, 36]: three ratio-2 layers through full_topk + one ratio-1 publish +
four ratio-1 consumes). Source-of-truth note: the census card cites the ctx600k
OVERLAY line numbers, but production boots the IMAGE tree (r3-boot mounts only
the adapter; no overlay volume). On the image, the block is
sglang.srt.layers.attention.dsv4.v41_indexer.scoring.decode_scores (:374), and
its per-step layer-invariant prefix is exactly:

    lens  = (pos + 1) // ratio                                    [bs]
    lmax  = min(metadata.max_compressed_seq_len, req_to_token.shape[1] // ratio)
    j     = torch.arange(lmax)                                    [lmax]
    valid = j[None, :] < lens[:, None]                            [bs, lmax]
    slots = req_to_token[req[:, None], (j * ratio)[None, :]].to(torch.int64) // ratio
    slots = slots.masked_fill(~valid, 0)                          [bs, lmax]

-- census kernels #1 (index_elementwise 14.97 ms/step), #3 (masked_fill 12.14),
#4 (div_floor 11.34), #6 (bitwise_not 1.42), #7 (CompareFunctor 0.97) plus the
int64 copies of #2/#5. Every input of that prefix (pos, req content,
req_to_token, the metadata bound) is per-STEP state, never per-layer state: the
8 layers differ only in x/q_lora/weights/k-cache, none of which the prefix
reads. A grep of the image backend/model/v41_indexer shows req_to_token is
only written between forwards (alloc / write_req_to_token_pool at batch prep),
never inside model forward, so the prefix is constant across the layers of one
forward. This adapter computes it once per (forward, ratio) and hands every
layer of that ratio the same tensors: 8x -> 2x per step.

Sub-features, independently fail-closed per (device-type, ratio) group:
  hoist -- share lens/slots across the layers of the step. Verified in-engine
          at the first eligible EAGER step: (a) call 1 dual-runs the stock
          int64 prefix and the slim int32 prefix, bit-compares the slot VALUES
          and the scoring kernel's fp32 logits; (b) call 2 (first cache hit)
          recomputes the prefix stock-style from the live tensors and
          bit-compares with the shared ones -- this is the layer-invariance
          check; a mid-forward req_to_token/positions mutation falsifies it,
          logs a loud error and permanently reverts the group to stock.
  slim  -- compute slots without the int64 promotion (`.to(torch.int64)`
          dropped; `// ratio` runs in the req_to_token dtype, int32 here).
          Values are physical KV pool slot ids bounded by the pool size
          (9.6M-class slots on this fleet, ~200x below 2^31), so int64 and
          int32 hold identical values; the kernel parity above catches any
          residual dtype sensitivity bit-for-bit. Any mismatch -> slim off
          permanently for the group, hoist unaffected.

expand_index_page_table (sglang.srt.layers.attention.dsv4.metadata:412) is
slimmed the same way: its input page_table is built `.to(torch.int32)` by the
metadata kernels (dsv4_attn_metadata_kernels: page_table = (pt // page_size)
.to(torch.int32)), its output is int32, and the stock body round-trips through
int64 (`.to(torch.int64) * blocks_per_page` + int64 arange + final
`.to(torch.int32)`) -- census #132 (add(long) 7.2M) and #137 (unrolled
int64->int32 copy). The slim body computes int32 end to end (page ids ~150k *
blocks_per_page 12 + 11 = 1.8M-class max, ~1000x below int32 overflow),
bit-identical output, first eager call dual-checked. The census's proposed
cross-STEP cache for it is REJECTED here: for graph-carried decode the
expansion runs INSIDE the captured graph (decode_cuda_graph_runner
capture_one_shape -> run_once -> init_forward_metadata_in_graph ->
make_forward_metadata_from_raw_decode -> init_forward_metadata_indexer), so
host-side content-conditional caching cannot gate replays, and the eager
residue is 2.17 ms/step total (census appendix) -- not worth a pool-allocation
hook seam. Recorded as 证伪 (cross-step part) in the task card.

Doors (fail-safe; unset/off/0/false = ZERO wrappers installed, engine modules
byte-identical):
  DSV41_INDEXER_HOIST   1 = this file. Any other value = refuse the boot.

CUDA-graph correctness (the load-bearing premise): the wrap only changes which
python objects the per-layer calls see at CAPTURE time. Layer A (first of its
ratio in the captured forward) computes the prefix; its kernels are captured
writing the shared tensors, and the strong refs the step cache holds keep
those addresses from being recycled mid-capture. Layers B..H bind the SAME
tensor objects, so their captured kernels read the same addresses; replay
re-executes layer A's kernels first (capture order = replay order, single main
stream -- DenseBlocks and full_topk._torch_decode run on the main stream in
decode; SparseTable's alt_stream synchronises with wait_stream before reading),
so the shared buffers are refreshed before every later reader. No host sync,
no data-dependent allocation. The first-call dual verifications run only
OUTSIDE capture (each graph capture is preceded by two eager warmups,
full_cuda_graph_backend.capture_one: "Two warmups so kernels are loaded"), so
torch.equal never runs under capture; if a capture ever arrives before the
eager verification (no warmup), the wrap plays pure stock inside it and that
graph simply keeps the stock shape -- zero drift, no correctness exposure.
The step cache is scoped to one DeepseekV4Model.forward bracket (try/finally)
and never survives a step, so the id()-based cache key is collision-free (an
id is unique among live objects, and the keyed tensors are referenced by the
engine for the whole forward).
"""

import inspect
import logging
import os

import torch

logger = logging.getLogger(__name__)

_MARKER = "_dsv41_indexer_hoist"
_MODEL_MARKER = "_dsv41_indexer_hoist_model"

# Engine seams this adapter rides; a drift must refuse the boot, not silently
# no-op (an inert wrap would keep the 8x block silently and the arm would look
# green -- 挂点漂移双死法).
_SCORING_SEAMS = ("decode_scores", "DecodeScores", "fp4_index_logits_decode")
_METADATA_SEAMS = ("expand_index_page_table", "PagedIndexerMetadata")

_OFF = ("", "0", "off", "false")


def _parse_gate():
    raw = os.environ.get("DSV41_INDEXER_HOIST", "").strip().lower()
    if raw in _OFF:
        return False
    if raw == "1":
        return True
    raise RuntimeError(
        f"indexer_hoist: DSV41_INDEXER_HOIST={raw!r} is not one of "
        "(unset|0|off|false|1); refusing to boot"
    )


ENABLED = _parse_gate()

# Per-group feature state: _state["ratio"][key] = {"mode": ..., "slim": bool}
#   key      -- (kind, device-type, ratio) with kind "decode"/"expand"
#   mode     -- "unverified" -> stock until the first eager dual-check
#               "armed"      -> hoist (+slim if flagged) active
#               "failed"     -> permanent stock for this boot (loud)
_state = {
    "step": None,          # dict while a decode/verify forward bracket runs
    "ratio": {},
    "stats": {
        "steps": 0,        # decode/verify forwards bracketed
        "calls": 0,        # decode_scores calls through the wrap
        "reused": 0,       # calls served from the shared prefix
        "verify_pass": 0,  # groups whose first-call dual-check passed
        "verify_fail": 0,  # groups falsified (permanent stock)
        "expand": 0,       # expand_index_page_table calls
        "expand_slim": 0,  # of which served by the int32 body
        "expand_fail": 0,
    },
    "installed": [],
    "modules": {},
}

_milestones = {"steps": 0, "inv_checked": set(), "armed_seen": set(),
               "expand_logged": set()}


class _Inv:
    """The per-(step, ratio) layer-invariant prefix of decode_scores."""

    __slots__ = ("bs", "lmax", "lens", "slots", "slim")

    def __init__(self, bs, lmax, lens, slots, slim):
        self.bs = bs
        self.lmax = lmax
        self.lens = lens
        self.slots = slots
        self.slim = slim


def summary() -> str:
    s = _state["stats"]

    def _fmt(item):
        (k, v) = item
        label = k[0] + (f"/r{k[2]}" if len(k) == 3 else "")
        return f"{label}:{v['mode'][:2]}{'+slim' if v.get('slim') else ''}"

    groups = ",".join(_fmt(kv) for kv in sorted(_state["ratio"].items()))
    return (
        f"gate={os.environ.get('DSV41_INDEXER_HOIST', '(unset)')} "
        f"installed={'+'.join(_state['installed']) or '(none)'} "
        f"groups[{groups}] steps={s['steps']} calls={s['calls']} "
        f"reused={s['reused']} expand={s['expand']}/{s['expand_slim']} "
        f"verify={s['verify_pass']}pass/{s['verify_fail']}fail/"
        f"{s['expand_fail']}efail"
    )


# ---------------------------------------------------------------- predicates


def _device_ok(tensor) -> bool:
    """Engine path: CUDA only -- the census win is CUDA; CPU/HIP engine paths
    keep stock. (Indirection exists so the CPU unit tests can engage.)"""
    return tensor.device.type == "cuda"


def _capturing() -> bool:
    try:
        return (
            torch.cuda.is_available()
            and torch.cuda.is_current_stream_capturing()
        )
    except Exception:
        return False


def _group(inputs):
    return ("decode", inputs.positions.device.type, inputs.compress_ratio)


def _cache_key(inputs, req_to_token, lmax, bs):
    """Identity key, valid only inside one forward bracket (module docstring):
    the keyed tensors are live engine objects for the whole forward, so id()
    collisions are impossible while the bracket holds them."""
    return (
        inputs.compress_ratio,
        id(inputs.positions),
        id(inputs.paged_metadata),
        id(req_to_token),
        int(lmax),
        int(bs),
    )


def _stock_prefix(inputs, req_to_token, lens, lmax):
    """The engine's invariant prefix, verbatim (int64 slots)."""
    req, pos, ratio = inputs.req_rows, inputs.positions, inputs.compress_ratio
    j = torch.arange(lmax, device=pos.device)
    valid = j[None, :] < lens[:, None]
    slots = req_to_token[req[:, None], (j * ratio)[None, :]].to(
        torch.int64
    ) // ratio
    slots = slots.masked_fill(~valid, 0)
    return slots


def _slim_prefix(inputs, req_to_token, lens, lmax):
    """Same prefix without the int64 promotion: the advanced-index output
    keeps req_to_token's dtype (int32 on this engine) and `// ratio` runs in
    int32. Values are physical pool slot ids << 2^31 (module docstring)."""
    req, pos, ratio = inputs.req_rows, inputs.positions, inputs.compress_ratio
    j = torch.arange(lmax, device=pos.device)
    valid = j[None, :] < lens[:, None]
    slots = req_to_token[req[:, None], (j * ratio)[None, :]] // ratio
    slots = slots.masked_fill(~valid, 0)
    return slots


# ------------------------------------------------------- decode_scores wrap


def _decode_scores_wrap(*, inputs, token_to_kv_pool, req_to_token, candidate_mask):
    scoring = _state["modules"]["scoring"]
    stats = _state["stats"]
    req, pos = inputs.req_rows, inputs.positions
    metadata = inputs.paged_metadata
    bs = req.shape[0]
    # 520d6d0 新合同：decode_scores 无 out 参，写回面在 inputs.out_page_indices
    # （stock scoring.py:392/:400/:432 全路径 reset_outputs——wrap 在入口同覆盖）。
    inputs.reset_outputs()
    assert pos.shape[0] == bs, (
        f"decode expects one token per request, {pos.shape=} {bs=}"
    )
    if bs == 0:
        return None
    lens = (pos + 1) // inputs.compress_ratio
    lmax = min(
        metadata.max_compressed_seq_len,
        req_to_token.shape[1] // inputs.compress_ratio,
    )
    if lmax == 0:
        return None

    cache = _state["step"]
    gkey = _group(inputs)
    group = _state["ratio"].get(gkey, {"mode": "unverified", "slim": False})
    key = _cache_key(inputs, req_to_token, lmax, bs)
    inv = cache.get(key)
    stats["calls"] += 1

    if inv is not None and group["mode"] == "armed" and _reuse_ok(
        inputs, req_to_token, inv, gkey, group
    ):
        stats["reused"] += 1
        if gkey not in _milestones["armed_seen"]:
            _milestones["armed_seen"].add(gkey)
            logger.warning(
                "DSV41 indexer hoist engaged %s: decode prefix shared across "
                "the step's layers (8x -> 2x/step), slim=%s, reuse verified "
                "bitwise", gkey, inv.slim,
            )
    else:
        cacheable = False
        if group["mode"] == "unverified" and not _capturing():
            slots, slim = _verify_or_compute(
                inputs, req_to_token, lens, lmax, token_to_kv_pool
            )
            cacheable = True
        elif group["mode"] == "armed":
            # A verified group in a fresh step (or inside a later capture --
            # the graph binds this shape): compute per the recorded slim flag,
            # share with the later layers of the step, no dual-run.
            slim = group["slim"]
            slots = (
                _slim_prefix(inputs, req_to_token, lens, lmax)
                if slim
                else _stock_prefix(inputs, req_to_token, lens, lmax)
            )
            cacheable = True
        else:
            # "failed", or a capture that arrived before any eager
            # verification: pure stock, nothing cached -- zero drift.
            slim = False
            slots = _stock_prefix(inputs, req_to_token, lens, lmax)
        inv = _Inv(bs, lmax, lens, slots, slim)
        if cacheable:
            cache[key] = inv

    # Per-layer tail -- the stock code path on the shared tensors.
    q = inputs.indexer.queries(inputs.q_lora, inputs.freqs_cis[pos])
    weights = inputs.indexer.head_weights(inputs.x)
    table = token_to_kv_pool.get_index_k_with_scale_buffer(inputs.layer_id)
    scores = scoring.fp4_index_logits_decode(
        q, weights, inv.slots, inv.lens, table, table.shape[1] // 68
    )
    return scoring.DecodeScores(
        bs=inv.bs, lmax=inv.lmax, lens=inv.lens, slots=inv.slots, scores=scores
    )


def _reuse_ok(inputs, req_to_token, inv, gkey, group):
    """Gate a cache hit: the first hit of a group in EAGER mode recomputes the
    prefix stock-style and bit-compares with the shared tensors (the in-engine
    layer-invariance check). Later hits (and every hit under capture) trust
    it. A mismatch falsifies the claim: loud error + permanent stock."""
    if gkey in _milestones["inv_checked"] or _capturing():
        return True
    _milestones["inv_checked"].add(gkey)
    lens = (inputs.positions + 1) // inputs.compress_ratio
    fresh = _stock_prefix(inputs, req_to_token, lens, inv.lmax)
    shared = inv.slots.to(torch.int64) if inv.slim else inv.slots
    if torch.equal(fresh, shared) and torch.equal(lens, inv.lens):
        return True
    group["mode"] = "failed"
    _state["stats"]["verify_fail"] += 1
    logger.error(
        "DSV41 indexer hoist: layer-invariance FALSIFIED for %s -- "
        "req_to_token/positions changed mid-forward; loud fallback to stock "
        "decode_scores for the rest of this boot", gkey,
    )
    return False


def _verify_or_compute(inputs, req_to_token, lens, lmax, token_to_kv_pool):
    """First eligible EAGER call of a group: dual-run stock int64 and slim
    int32 prefixes, bit-compare the slot values and the scoring kernel's fp32
    logits, record the group armed with the slim verdict. Eager only."""
    scoring = _state["modules"]["scoring"]
    gkey = _group(inputs)
    stock_slots = _stock_prefix(inputs, req_to_token, lens, lmax)
    slim_slots = _slim_prefix(inputs, req_to_token, lens, lmax)

    slim_ok = torch.equal(stock_slots, slim_slots.to(torch.int64))
    if slim_ok:
        q = inputs.indexer.queries(
            inputs.q_lora, inputs.freqs_cis[inputs.positions]
        )
        weights = inputs.indexer.head_weights(inputs.x)
        table = token_to_kv_pool.get_index_k_with_scale_buffer(inputs.layer_id)
        ref = scoring.fp4_index_logits_decode(
            q, weights, stock_slots, lens, table, table.shape[1] // 68
        )
        got = scoring.fp4_index_logits_decode(
            q, weights, slim_slots, lens, table, table.shape[1] // 68
        )
        slim_ok = torch.equal(ref, got)
        del ref, got

    _state["ratio"][gkey] = {"mode": "armed", "slim": slim_ok}
    _state["stats"]["verify_pass"] += 1
    if not slim_ok:
        logger.error(
            "DSV41 indexer hoist: slim int32 slots failed the first-call bit "
            "check on %s; int64 slots kept (hoist unaffected)", gkey,
        )
    return (slim_slots if slim_ok else stock_slots), slim_ok


# --------------------------------------------- expand_index_page_table wrap


def _expand_slim(page_table, *, full_page_size, compress_ratio, index_page_size):
    """Stock expansion with int32 intermediates (module docstring); first
    eager call dual-checked against stock, fail-closed per device type."""
    slots_per_page = full_page_size // compress_ratio
    assert slots_per_page % index_page_size == 0, (
        f"{full_page_size = } / {compress_ratio = } must be a multiple of "
        f"{index_page_size = }"
    )
    blocks_per_page = slots_per_page // index_page_size
    if blocks_per_page == 1:
        return page_table
    stats = _state["stats"]
    stats["expand"] += 1
    gkey = ("expand", page_table.device.type)

    def _stock():
        return _state["orig_expand"](
            page_table,
            full_page_size=full_page_size,
            compress_ratio=compress_ratio,
            index_page_size=index_page_size,
        )

    group = _state["ratio"].get(gkey, {"mode": "unverified", "slim": False})
    if group["mode"] == "failed" or _capturing():
        return _stock()

    bs, n = page_table.shape
    base = page_table.to(torch.int32) * blocks_per_page
    offsets = torch.arange(
        blocks_per_page, device=page_table.device, dtype=torch.int32
    )
    slim = (base.unsqueeze(-1) + offsets).reshape(bs, n * blocks_per_page)

    if group["mode"] != "armed":
        ref = _stock()
        if torch.equal(ref, slim) and ref.dtype == slim.dtype:
            _state["ratio"][gkey] = {"mode": "armed", "slim": True}
        else:
            _state["ratio"][gkey] = {"mode": "failed", "slim": False}
            stats["expand_fail"] += 1
            logger.error(
                "DSV41 indexer hoist: expand int32 slim failed the first-call "
                "bit check on %s; stock int64 expansion kept for this boot",
                gkey,
            )
            return ref
    stats["expand_slim"] += 1
    if gkey not in _milestones["expand_logged"]:
        _milestones["expand_logged"].add(gkey)
        logger.warning(
            "DSV41 indexer hoist expand engaged %s: page-table expansion runs "
            "int32 end to end (int64 round-trip dropped), blocks_per_page=%s",
            gkey, blocks_per_page,
        )
    return slim


# ------------------------------------------------------------ model bracket


def _bracket_eligible(forward_batch) -> bool:
    mode = getattr(forward_batch, "forward_mode", None)
    if mode is None:
        return False
    try:
        return mode.is_decode() or mode.is_target_verify()
    except Exception:
        return False


def _make_model_forward(orig_forward):
    def forward(self, input_ids, positions, forward_batch, *args, **kwargs):
        if not _bracket_eligible(forward_batch):
            return orig_forward(self, input_ids, positions, forward_batch,
                                *args, **kwargs)
        prev = _state["step"]
        _state["step"] = {}
        _state["stats"]["steps"] += 1
        try:
            return orig_forward(self, input_ids, positions, forward_batch,
                                *args, **kwargs)
        finally:
            _state["step"] = prev
            n = _state["stats"]["steps"]
            if n - _milestones["steps"] >= 512:
                _milestones["steps"] = n
                logger.warning("DSV41 indexer hoist heartbeat: %s", summary())

    return forward


# ------------------------------------------------------------- installers


def _fingerprint(module, name, needles):
    func = getattr(module, name, None)
    if not callable(func):
        raise RuntimeError(
            f"indexer_hoist: seam moved ({name} missing or not callable on "
            f"{getattr(module, '__name__', module)}); refusing to boot -- the "
            "hoist would otherwise silently no-op and the arm would look green"
        )
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError) as exc:
        raise RuntimeError(
            f"indexer_hoist: seam unreadable ({name}: {exc}); refusing to boot"
        ) from None
    for needle in needles:
        if needle not in source:
            raise RuntimeError(
                f"indexer_hoist: seam moved ({name} no longer shows "
                f"{needle!r}); refusing to boot -- stacking a hoist on an "
                "unknown preprocessing shape is not ours to decide"
            )
    return func


def _rebind(consumers, attr, value):
    """Defensively repoint consumer modules' from-imported name (the
    token_req_compact dual-module law). A cold import binds through the
    wrapped defining module; a pre-bound consumer gets repointed here."""
    import sys

    for consumer in consumers:
        mod = sys.modules.get(consumer)
        if mod is not None and getattr(mod, attr, None) is not None:
            setattr(mod, attr, value)


def install_scoring(module) -> bool:
    """Wrap v41_indexer.scoring.decode_scores. Installs only when the gate is
    on; every other boot leaves the engine function untouched."""
    if not ENABLED:
        return False
    if getattr(module, _MARKER, False):
        return False  # already installed (double exec of the module)
    if any(not hasattr(module, name) for name in _SCORING_SEAMS):
        raise RuntimeError(
            "indexer_hoist: scoring seam missing (need "
            f"{', '.join(_SCORING_SEAMS)}); refusing to boot"
        )
    orig = _fingerprint(
        module,
        "decode_scores",
        (
            "req_to_token[req[:, None], (j * ratio)[None, :]]",
            ".to(torch.int64) // ratio",
            "masked_fill(~valid, 0)",
            "fp4_index_logits_decode",
            "get_index_k_with_scale_buffer",
        ),
    )
    _state["modules"]["scoring"] = module
    _state["orig_decode_scores"] = orig

    def decode_scores(*, inputs, token_to_kv_pool, req_to_token,
                      candidate_mask=None):
        if (
            _state["step"] is None
            or not _device_ok(req_to_token)
            or inputs.compress_ratio not in (1, 2)
        ):
            return orig(inputs=inputs,
                        token_to_kv_pool=token_to_kv_pool,
                        req_to_token=req_to_token,
                        candidate_mask=candidate_mask)
        return _decode_scores_wrap(
            inputs=inputs, token_to_kv_pool=token_to_kv_pool,
            req_to_token=req_to_token, candidate_mask=candidate_mask,
        )

    module.decode_scores = decode_scores
    setattr(module, _MARKER, True)
    _state["installed"].append("scoring:decode_scores")
    _rebind(
        (
            "sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks",
            "sglang.srt.layers.attention.dsv4.v41_indexer.full_topk",
            "sglang.srt.layers.attention.dsv4.v41_indexer.sparse_table",
        ),
        "decode_scores",
        decode_scores,
    )
    logger.warning(
        "DSV41 indexer hoist scoring wrap installed on %s.decode_scores "
        "(gate=1): per-step prefix sharing + int32 slim, verified at the "
        "first eager step, fail-closed", module.__name__,
    )
    return True


def install_metadata(module) -> bool:
    """Wrap metadata.expand_index_page_table with the int32 body. Installs
    only when the gate is on."""
    if not ENABLED:
        return False
    if getattr(module, _MARKER, False):
        return False
    if any(not hasattr(module, name) for name in _METADATA_SEAMS):
        raise RuntimeError(
            "indexer_hoist: metadata seam missing (need "
            f"{', '.join(_METADATA_SEAMS)}); refusing to boot"
        )
    orig = _fingerprint(
        module,
        "expand_index_page_table",
        ("to(torch.int64) * blocks_per_page",),
    )
    _state["modules"]["metadata"] = module
    _state["orig_expand"] = orig

    def expand_index_page_table(page_table, *, full_page_size,
                                compress_ratio, index_page_size):
        return _expand_slim(
            page_table, full_page_size=full_page_size,
            compress_ratio=compress_ratio, index_page_size=index_page_size,
        )

    module.expand_index_page_table = expand_index_page_table
    setattr(module, _MARKER, True)
    _state["installed"].append("metadata:expand_index_page_table")
    _rebind(
        (
            "sglang.srt.layers.attention.deepseek_v4_backend",
            "sglang.srt.layers.attention.dsv4.v41_indexer.sparse_table",
        ),
        "expand_index_page_table",
        expand_index_page_table,
    )
    logger.warning(
        "DSV41 indexer hoist expand wrap installed on %s."
        "expand_index_page_table (int32 body, first-call bit-checked)",
        module.__name__,
    )
    return True


def install_model(module) -> bool:
    """Bracket DeepseekV4Model.forward: open the per-step prefix cache for
    decode / target-verify forwards. The bracket is the cache's lifetime
    boundary -- nothing survives the forward, so the identity cache key can
    never go stale."""
    if not ENABLED:
        return False
    cls = getattr(module, "DeepseekV4Model", None)
    if cls is None or not hasattr(cls, "forward"):
        raise RuntimeError(
            "indexer_hoist: DeepseekV4Model.forward seam moved; refusing to boot"
        )
    if getattr(cls, _MODEL_MARKER, False):
        return False  # already installed (double exec of the module)
    cls.forward = _make_model_forward(cls.forward)
    setattr(cls, _MODEL_MARKER, True)
    _state["installed"].append("model:DeepseekV4Model.forward")
    logger.warning(
        "DSV41 indexer hoist forward bracket installed on DeepseekV4Model "
        "(decode/target-verify scoped; cache dies at forward exit)"
    )
    return True
