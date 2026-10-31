"""spark_prefill_split -- prefill dense-indexer TP row split (main-79cafec0 port).

Ports the community SPARK_PREFILL_TP_SPLIT (knapcio indexer_chunked_v3 +
spark_prefill_dense, rhys101 SG18 partition) onto this tree's
DeepseekV4AttnBackend._low_ratio_index_topk. Each attn-TP rank scores only its
slice of the query rows against the full visible compressed context; the
selected int32 top-k ids -- plus, on the candidate source layer, the candidate
block ids -- are all-gathered and reassembled. No floating-point collective
ever runs.

Re-anchor onto main-79cafec0 (2026-10-02; the A19 arm died on the old guard's
six module hooks, which this base dissolved when the indexer moved into
srt/layers/attention/dsv4/v41_indexer/ and kernels/ops/attention/dsv4/):
  1. the hook is the renamed backend method _low_ratio_index_topk (the old
     _low_ratio_index_topk_dense); its signature gained req and the CP-only
     rows_per_request kwarg, and it now dispatches to the native indexers
     (prefill_candidates / full_topk_indexer) instead of inlining the scorer.
  2. DSV41_IDX_PROTOCOL is GONE as an env: the int32 block-table candidate
     form (upstream #40352) is structural now -- BlockIds in
     v41_indexer/dense_blocks.py, published through _publish_candidate_metadata
     (which also owns the late-layer tail cut; the old #40217 publish-row
     resolution is the base's own code path now). The adapter does NOT read
     the dead key; the old "refuse unless protocol on" boot check became the
     structural check that the native candidate indexer is the DeepGEMM
     DenseBlocksBackend pair (sparse_wire keeps SM121 on it).
  3. _dense_fp4_mqa_logits + the FIX-D width bucket (_DENSE_LOGITS_WIDTH_*)
     were replaced by flat_index_logits_tiles: the base now bounds each fp32
     logits tile by budget_bytes alone (width only 4-aligned), so the split
     passes its own budget and keeps no bucketing of its own.
  4. DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES has no stock consumer on this
     base (scoring.py hardcodes 2 GiB); the adapter reads it as the budget
     for the split's rank-local tiles -- the one real consumer left.
  5. consumer layers (uses_candidates and not source) still fall back to the
     stock path instead of a re-implemented consume branch; a CP call
     (rows_per_request is not None) also declines: rank rows are an
     interleaved subset there and the partition math is void.

Wrapper form: the stock method is captured and called unchanged whenever the
split does not engage, so the door-closed image is behaviourally identical to
the base (the guard asserts the stock anchors are present and untouched).

Doors (read once at install; cross-rank consistency is structural -- all ranks
read the same ENV_FILE, whose md5 the three-in-one gate pins; NO init-time
collective, see the W21 b1 post-mortem note at the __init__ wrap):
  DSV41_SPARK_PREFILL_TP_SPLIT   0/1 (default 0)
  DSV41_SPARK_PREFILL_TP_MIN_CONTEXT  >=32768 (default 32768)
  DSV41_SPARK_PREFILL_TP_MIN_ROWS     >=1024  (default 1024)
  DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES  bytes (default: the base's
      v41_indexer.scoring._DEEP_GEMM_SCORE_BUDGET_BYTES, floored at 1 MiB)
"""
import logging
import os

import torch

logger = logging.getLogger(__name__)

OFF = ("", "0", "off", "false")


def _flag(name):
    return os.environ.get(name, "0").strip().lower() not in OFF


def _int(name, default):
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _unwrap_dense_backend(obj, dbb_cls, max_depth=4):
    """Drill through the seam_mount _ConsumesAs facade to the dense backend.

    The facade is an appearance keeper that proxies NO attributes (reading
    use_deep_gemm_prefill on the wrapper itself is an AttributeError), so the
    dense-form guards walk the _orig/_gather chain instead of testing the
    wrapper (A23ALPHA r2 semantics; WCBOOT69 root cause / G0 §6.1). Only
    these two attributes are ever read -- never an arbitrary facade
    attribute (G0 §6.3). The live chain is exactly one level deep; the bound
    is defensive against deeper wraps. Returns the first dbb_cls instance
    found, else None.
    """
    stack = [(obj, 0)]
    while stack:
        x, depth = stack.pop()
        if isinstance(x, dbb_cls):
            return x
        if depth >= max_depth:
            continue
        for attr in ("_gather", "_orig"):  # LIFO: _orig branch is walked first
            nxt = getattr(x, attr, None)
            if nxt is not None and nxt is not x:
                stack.append((nxt, depth + 1))
    return None


def partition(rows, world, rank, tile=128):
    """Community partition, verbatim: tile-aligned extents, start=rank*extent."""
    if rows < 0 or world < 1 or not 0 <= rank < world or tile < 1:
        raise ValueError((rows, world, rank, tile))
    extent = ((rows + world * tile - 1) // (world * tile)) * tile
    start = rank * extent
    return start, min(rows, start + extent), extent


class PrefillTPSplit:
    def __init__(self, group, rank, world, minimum_context, minimum_rows, budget):
        self.group = group
        self.rank = rank
        self.world = world
        self.minimum_context = minimum_context
        self.minimum_rows = minimum_rows
        self.budget = budget
        self._logged = set()

    def eligible(self, rows, width_max, forward_batch, device, is_draft_runner):
        return (
            rows >= self.minimum_rows
            and width_max >= self.minimum_context
            and device.type == "cuda"
            and not is_draft_runner
            and forward_batch.forward_mode.is_extend_without_speculative()
            and not torch.cuda.is_current_stream_capturing()
        )


_STATE = {}


def make_split_dense(module):
    """Bind the stock method + this base's native helpers, return the wrapper."""
    _as_int_list = module._as_int_list
    stock = module.DeepseekV4AttnBackend._low_ratio_index_topk

    from sglang.kernels.ops.attention.dsv4 import topk_transform_ragged_v2
    from sglang.kernels.ops.attention.dsv4.candidate_blocks import (
        select_candidate_block_ids,
    )
    from sglang.kernels.ops.attention.dsv4.index_logits import flat_index_logits_tiles
    from sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks import (
        BlockIds,
        DenseBlocksBackend,
    )
    from sglang.srt.layers.attention.dsv4.v41_indexer.scoring import (
        get_deep_gemm_prefill_data,
    )

    def _run_split(
        self, tp, layer, x, q_lora, req, pos, forward_batch, rows_per_request
    ):
        """True = handled (split path ran); False = caller must run stock."""
        # doc60 §2#5: consumer layers defer to the stock path (never eligible
        # on this architecture, but refusing is cheaper than a masked path).
        indexer = layer.indexer
        source = bool(indexer.is_candidate_source)
        if indexer.uses_candidates and not source:
            return False
        # CP prefill: rank rows are an interleaved subset, not a contiguous
        # extent -- the partition below is void, so the stock path keeps it.
        if rows_per_request is not None:
            return False
        # The split is the DeepGEMM dense form only: a torch prefill indexer
        # (SGLANG_DSV41_TORCH_PREFILL_INDEXER) scores per request, and a
        # sparse-table publish (a build where the SM121 probe passes) is a
        # different metadata form -- both belong to the stock path.
        if not self.full_topk_indexer.use_deep_gemm_prefill:
            return False
        if source:
            # G0 §6.2: face-aware decline. The seam _ConsumesAs facade hides a
            # dense pair behind a non-DenseBlocksBackend wrapper; the old bare
            # isinstance silently routed every source layer to stock while the
            # init banner said engaged. Unwrap first; still refuse genuinely
            # non-dense forms (torch prefill / sparse publish -> stock path).
            dense_candidate = _unwrap_dense_backend(
                self.prefill_candidates, DenseBlocksBackend
            )
            if dense_candidate is None or not dense_candidate.use_deep_gemm_prefill:
                return False

        inputs = self._make_low_ratio_prefill_indexer_inputs(
            layer, x, q_lora, req, pos, forward_batch, rows_per_request
        )
        data = get_deep_gemm_prefill_data(inputs, self.req_to_token)
        if data is None:  # empties: stock publishes the empty candidate form
            return False
        kv = self.token_to_kv_pool.get_low_ratio_index_k_fp4(layer.layer_id, data.k_slots)
        device = pos.device
        topk = indexer.index_topk
        num_rows = data.num_rows
        width_max = max(data.lens_per_request, default=0)
        block_size = indexer.candidate_block_size
        blocks = (
            min(indexer.candidate_topk_blocks, -(-width_max // block_size))
            if source
            else 0
        )
        bounds, offset = [], 0
        for count, width in zip(data.rows_per_request, data.lens_per_request):
            bounds.append((offset, offset + count, width))
            offset += count
        assert offset == num_rows

        # ---- this rank's partition (doc60 §4) ----
        start_r, end_r, extent = partition(num_rows, tp.world, tp.rank)
        packed = torch.full(
            (extent, topk + blocks), -1, dtype=torch.int32, device=device
        )
        sub = slice(start_r, end_r)
        # The base's tile generator bounds each fp32 logits tile by the budget
        # (flat_index_logits_tiles); context_lengths stays the full batch so
        # every rank computes the same 4-aligned width.
        if start_r < end_r:
            arange_width = None
            for tile, logits in flat_index_logits_tiles(
                q=(data.q_fp4[sub], data.q_sf[sub]),
                kv=kv,
                weights=data.weights[sub],
                starts=data.request_starts[sub],
                lengths=data.compress_lens[sub],
                context_lengths=data.lens_per_request,
                budget_bytes=tp.budget,
            ):
                g0, g1 = start_r + tile.start, start_r + tile.stop
                if source:
                    for lo_r, hi_r, width in bounds:
                        lo, hi = max(g0, lo_r), min(g1, hi_r)
                        if not width or lo >= hi:
                            continue
                        take = slice(lo - g0, hi - g0)
                        scores = logits[take, :width]
                        if arange_width is None or arange_width.shape[0] < width:
                            arange_width = torch.arange(width, device=device)
                        row_lens = data.compress_lens[lo:hi, None]
                        scores.masked_fill_(
                            arange_width[None, :width] >= row_lens, -torch.inf
                        )
                        nblocks = min(
                            indexer.candidate_topk_blocks, -(-width // block_size)
                        )
                        packed[
                            lo - start_r : hi - start_r, topk : topk + nblocks
                        ] = select_candidate_block_ids(
                            scores, row_lens, nblocks, block_size
                        )
                    # consumer branch: unreachable (refused at entry)
                selected = torch.empty(
                    (g1 - g0, topk), dtype=torch.int32, device=device
                )
                topk_transform_ragged_v2(
                    logits,
                    data.compress_lens[g0:g1],
                    out_offsets=data.request_starts[g0:g1],
                    out_indices=selected,
                )
                packed[g0 - start_r : g1 - start_r, :topk] = selected
                del logits
        gathered = tp.group.all_gather(packed, dim=0)[:num_rows]

        # ---- publish: the base's own outputs / BlockIds forms ----
        # 520d6d0 新合同：write_selection 收 inputs（页槽写回内部走
        # inputs.out_page_indices/out_raw_indices），无 Selection 池取用面。
        inputs.reset_outputs()
        data.write_selection(selected=gathered[:, :topk], inputs=inputs)
        if source:
            self._publish_candidate_metadata(
                BlockIds(
                    blocks=gathered[:, topk : topk + blocks],
                    rows_per_request=data.rows_per_request,
                )
            )

        key = (layer.compress_ratio, source)
        if key not in tp._logged:
            tp._logged.add(key)
            logger.warning(
                "DSV41 prefill TP split engaged rank=%s layer=%s ratio=%s source=%s "
                "rows=%s width=%s extent=%s budget=%s",
                tp.rank, layer.layer_id, layer.compress_ratio, source, num_rows,
                width_max, extent, tp.budget,
            )
        return True

    def dense_with_split(
        self, layer, x, q_lora, req, pos, forward_batch, *, rows_per_request=None
    ):
        tp = _STATE.get("tp")
        if tp is not None:
            seq_lens_cpu = _as_int_list(forward_batch.seq_lens_cpu)
            if seq_lens_cpu:
                ratio = layer.compress_ratio
                width_max = max(s // ratio for s in seq_lens_cpu)
                if tp.eligible(
                    pos.shape[0], width_max, forward_batch, pos.device,
                    self.is_draft_runner,
                ) and _run_split(
                    self, tp, layer, x, q_lora, req, pos, forward_batch,
                    rows_per_request,
                ):
                    return None
        return stock(
            self, layer, x, q_lora, req, pos, forward_batch,
            rows_per_request=rows_per_request,
        )

    return dense_with_split


def install(module):
    """EngramFinder hook: wrap __init__ (group resolution) + the index method."""
    if not _flag("DSV41_SPARK_PREFILL_TP_SPLIT"):
        return
    from importlib import import_module

    cls = getattr(module, "DeepseekV4AttnBackend", None)
    missing = []
    if cls is None or not hasattr(cls, "_low_ratio_index_topk"):
        missing.append("_low_ratio_index_topk")
    # _as_int_list is a module-level helper (backend:303), not a class attribute
    if not hasattr(module, "_as_int_list"):
        missing.append("_as_int_list")
    # The six old hooks dissolved into the v41_indexer package and the dsv4
    # kernel ops; each anchor is pinned at its new home so the next rename
    # still refuses to boot instead of half-engaging.
    homes = (
        ("sglang.kernels.ops.attention.dsv4", "topk_transform_ragged_v2"),
        ("sglang.kernels.ops.attention.dsv4.candidate_blocks", "select_candidate_block_ids"),
        ("sglang.kernels.ops.attention.dsv4.index_logits", "flat_index_logits_tiles"),
        ("sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks", "BlockIds"),
        ("sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks", "DenseBlocksBackend"),
        ("sglang.srt.layers.attention.dsv4.v41_indexer.scoring", "get_deep_gemm_prefill_data"),
        ("sglang.srt.layers.attention.dsv4.v41_indexer.scoring", "_DEEP_GEMM_SCORE_BUDGET_BYTES"),
    )
    native = {}
    for home, name in homes:
        try:
            part = import_module(home)
        except ImportError:
            missing.append(f"{home}:{name}")
            continue
        if not hasattr(part, name):
            missing.append(f"{home}:{name}")
        else:
            native[name] = getattr(part, name)
    if missing:
        raise RuntimeError(
            f"spark_prefill_split: backend drifted (missing {missing}); refusing to boot"
        )
    _DBB = native["DenseBlocksBackend"]

    budget = max(
        1 << 20, _int("DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES", 0)
        or native["_DEEP_GEMM_SCORE_BUDGET_BYTES"]
    )
    from sglang.srt.distributed.parallel_state import get_attn_tp_group

    original_init = cls.__init__

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if _STATE.get("tp") is None and not self.is_draft_runner:
            # DSV41_IDX_PROTOCOL has no reader on this base; its semantics
            # (int32 block-table candidates) are structural, so the old
            # protocol door became this structural refusal: the split
            # publishes BlockIds, which only the DeepGEMM DenseBlocksBackend
            # pair consumes.
            # G0 §6.1 / A23ALPHA r2: the live prefill slot is a seam_mount
            # _ConsumesAs facade over a dense pair (sparse_wire REFUSED path),
            # so unwrap the _orig/_gather chain before the isinstance +
            # use_deep_gemm_prefill judgment -- the facade itself proxies no
            # attributes (G0 §6.3). The full_topk slot keeps its attribute-only
            # test: FullTopKIndexer is never a DenseBlocksBackend, and adding
            # an isinstance there mis-killed legal boots once already
            # (A23ALPHA RED2).
            dense_candidate = _unwrap_dense_backend(self.prefill_candidates, _DBB)
            if not (
                dense_candidate is not None
                and dense_candidate.use_deep_gemm_prefill
                and self.full_topk_indexer.use_deep_gemm_prefill
            ):
                raise RuntimeError(
                    "spark_prefill_split: the native candidate indexer is not the "
                    "DeepGEMM dense block-id form (sparse table or torch prefill "
                    "active); refusing to boot"
                )
            group = get_attn_tp_group()
            world = group.world_size
            if world not in (4, 8):
                raise RuntimeError(
                    f"spark_prefill_split: attn TP world={world} not in (4, 8); refusing to boot"
                )
            if not (torch.cuda.is_available() and torch.cuda.get_device_capability() == (12, 1)):
                raise RuntimeError("spark_prefill_split: not SM121; refusing to boot")
            min_context = _int("DSV41_SPARK_PREFILL_TP_MIN_CONTEXT", 32768)
            min_rows = _int("DSV41_SPARK_PREFILL_TP_MIN_ROWS", 1024)
            if min_context < 32768 or min_rows < 1024:
                raise RuntimeError(
                    f"spark_prefill_split: thresholds too low ({min_context}, {min_rows})"
                )
            # W21 b1 post-mortem: the community's cross-rank all_gather_object
            # consistency check ran BEFORE the RoCE mesh served its first op and
            # every subsequent group collective fell back to NCCL RING_LL
            # (census: nccl.AR 29.7ms x 8.8/step, 42.6% of step time; anchor has
            # zero nccl families) -- a uniform ~2x prefill/DE regression with the
            # split itself engaging on one layer per chunk. Cross-rank settings
            # consistency here is structural instead: all four ranks read the
            # same ENV_FILE (start.sh) and the three-in-one gate pins its md5.
            # NO collective of any kind runs at init.
            _STATE["tp"] = PrefillTPSplit(
                group, group.rank_in_group, world, min_context, min_rows, budget
            )
            logger.warning(
                # G0 §6.2 (2): print the UNWRAPPED candidate type so the boot
                # log itself disproves the silent-stock trap (banner engaged +
                # layers declining). cand= is the post-unwrap class name.
                "DSV41 prefill TP split initialized cand=%s rank=%s world=%s "
                "min_ctx=%s min_rows=%s budget=%s (no init collective)",
                type(dense_candidate).__name__, group.rank_in_group, world,
                min_context, min_rows, budget,
            )

    cls.__init__ = __init__
    cls._low_ratio_index_topk = make_split_dense(module)
