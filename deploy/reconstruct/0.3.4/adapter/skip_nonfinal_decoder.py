"""skip_nonfinal_decoder -- C0b opt1 port to the new base (DESIGN + IMPL DRAFT).

0. WHAT (from the 0.2.9 fin2 production engine, /tmp/fin2-files)
--------------------------------------------------------------------------------
DSV41_SKIP_NONFINAL_DECODER=1 made the old engine skip, for extend chunks that
do NOT finish their request, the late-layer tail forward that decoder SWA
bounded replay would otherwise run over the chunk's last SWA_WINDOW rows
(old backend :2486-2494 late_layer_tail_skip / final_req_mask). Old-verdict
expectation: another -5~9% prefill on top of bounded replay. The new base
(main-79cafec0) has bounded replay natively (PR +57~70%, A15-DBR adopted) but
NO equivalent of the non-final-chunk skip (grep SKIP_NONFINAL /
late_layer_tail_skip / skip_nonfinal: zero hits, re-verified 2026-10-02) --
this adapter ports it.

1. NEW-BASE MOUNT POINTS (measured on main-79cafec0, md5 of the two files in
   opt1-dev/newbase-extract/)
--------------------------------------------------------------------------------
  M1  deepseek_v4_backend.py:2314-2337  DeepseekV4AttnBackend.init_forward_metadata
      builds self.tail_forward_metadata = self._build_late_layer_tail_metadata(
      forward_batch) iff enable_decoder_swa_bounded_replay and
      forward_mode.is_extend_without_speculative(). Our port REPLACES this
      short method (24 lines) with the opt1-aware version below.
  M2  deepseek_v4_backend.py:1511-1610   _build_late_layer_tail_metadata
      (subset-free; per-request tail = last min(SWA_WINDOW, extend_len) rows;
      window floored at the tail start). Phase 2 ports the old base's
      final_req_mask subsetting on top of it (_build_late_layer_tail_metadata_opt1).
  M3  deepseek_v4.py:4381-4553           DeepseekV4Model._forward_layers_hc_pre_from_prev
      `tail = attn_backend.tail_forward_metadata.late_layer_tail` (unconditional
      attribute read -> we may NOT set tail_forward_metadata=None) and the
      per-layer switch `if tail is not None and i == self.late_layer_start:`
      with enter/exit_late_layer_tail. Our port WRAPS the method: when the
      backend stamped late_layer_tail_skip, self.end_layer is temporarily cut
      to self.late_layer_start so the loop `for i in range(self.start_layer,
      self.end_layer)` never reaches the late layers -- exactly the old base's
      `if skip_late_layers and i >= self.late_layer_start: break`, without
      copying the 170-line method body.
  M4  deepseek_v4.py:4359-4378   _check_late_layer_tail_readers (unchanged;
      the C0c replay_guard keeps its raisers from ever firing).
  M5  deepseek_v4.py:4468-4475   capture_dspark aux capture
      (`if capture_dspark and i in self.dspark_layers_to_capture: ... append
      (aux.mean(dim=1))`) -- under the cut, layers >= late_layer_start never
      run, so the wrapper republishes mean stand-ins to keep the aux list
      shape (old base fin2 deepseek_v4.py:3990-4001 standin port).
  M6  deepseek_v4_backend.py:2543 init_forward_metadata_for_breakable_
      cuda_graph_capture / :2586 prepare_forward_metadata_for_breakable_
      cuda_graph_replay -- the breakable-cuda-graph (BCG) entry points do NOT
      run our replaced eager init, so both are wrapped to reset
      late_layer_tail_skip=False; without this, an extend running as a BCG
      replay could read the flag left by a previous eager middle-chunk forward
      and wrongly cut. The model wrapper additionally refuses to cut while
      is_in_breakable_cuda_graph() (defense in depth; import at
      deepseek_v4.py:151). Capture batches are dummies -> never skippable.

2. HOW THE NEW BASE SAYS "REQUEST'S LAST CHUNK" (the key design question)
--------------------------------------------------------------------------------
The old base had a scheduler-computed ForwardBatch.extend_last_chunk_mask; the
new base has no such field (zero grep hits). But it carries, per row:
    seq_lens_cpu[i]     = req.extend_range.end          (schedule_batch.py:2739)
    orig_seq_lens[i]    = max(req.extend_range.end,
                              len(req.origin_input_ids)) (schedule_batch.py:2740,
                                                        int32 tensor, on FB)
so for a mid-prefill chunk (no output tokens yet, no DLLM block)
    orig_seq_lens[i] == len(origin_input_ids) == len(full_untruncated_fill_ids)
is the request's total fill length E, and e_i = seq_lens_cpu[i] is how far the
current chunk reaches. "Final chunk" <=> e_i == E. Scheduler-side truthtable
(PrefillAdder, schedule_policy.py:1338-1354 / 1571-1577): new_chunked_req is
stamped only when tokens REMAIN after the chunk -- the same predicate.

KEEP/SKIP RULE (with a safety margin the old base did not have -- see 3):
    keep row i  iff  NOT (e_i + SWA_WINDOW <= orig_i)
i.e. skip only when at least a full window of tokens remains after this chunk.
Whole batch skippable -> late_layer_tail_skip=True (phase 1, ships first).
Mixed batches (some keep, some skip) -> phase 2 row restriction, separately
gated, default OFF.

3. WHY SKIPPING IS SOUND ON THE NEW BASE (swa_out_cache_loc write path)
--------------------------------------------------------------------------------
Writes: under bounded replay only the tail rows (last SWA_WINDOW of the chunk)
run late layers and write late-layer KV via metadata.core_attn_metadata.
swa_out_cache_loc (= request_window_layout.write_loc, dsv41_request_window.
window_layout, capacity=256 >= window=128) -- non-tail rows never write late
layers at all (nothing changes for them under opt1).
Reads of a mid-chunk tail region [e-128, e):
  a) the NEXT chunk's tail attention: floored (floor=swa_replay_start =
     seq_lens - tail_lens, late_layer_tail_layout) at the next chunk's OWN tail
     start -- cannot read chunk k's rows (verified: make_core_attn_metadata
     passes floor into window_layout; build_causal_swa_page_indices masks
     offsets < swa_replay_start; "Slots below the floor are -1").
  b) dspark draft readers: only a request that finished prefill drafts; its
     final chunk republishes real aux values before any reader runs (old-base
     contract, standins keep the list shape meanwhile).
  c) decode after prefill: decode has NO floor (floor=None on decode paths),
     so its window [p-127, p] does reach back into prefill-written rows for
     the FIRST 128 positions -- but only down to E-127. Rows at absolute
     position < E-127 are never read by any later forward.
     => skip is provably safe iff e_i + SWA_WINDOW <= E_i (all of chunk i's
     tail rows sit at positions <= e_i-1 <= E-129 < E-127).
     THE OLD BASE SKIPPED WITHOUT THIS MARGIN ("later chunks overwrite their
     window slots" -- not true in general on the ring layout: with capacity
     256 > window 128 and slot = pos % capacity, a short FINAL chunk
     (len(prompt) % chunk_size < 128) leaves chunk k's tail rows as the live
     values that early decode steps read). Our port therefore adds the
     SWA_WINDOW margin: the only rows still kept are the last middle chunk
     before a short final fragment -- at most one 128-row window per request,
     negligible vs the saved (num_chunks-1)-ish windows.
  d) radix/prefix reuse: SWA/late-layer KV lives in the per-request window,
     never in the radix tree (schedule_batch comments; swa_reprefill_tail
     re-prefills the tail on reuse) -- no cross-request reader.
  e) logits: only the final chunk's last row feeds sampling; non-final chunk
     forwards' logits are discarded by the scheduler (chunked_req results are
     cached away via cache_unfinished_req); CaptureHiddenMode.FULL and prompt
     logprobs are rejected upstream (M4 + C0c).

4. WHAT THE ADAPTER INSTALLS (two wraps + one ported builder; engine files
   are NEVER edited -- the sitecustomize EngramFinder fires these at import)
--------------------------------------------------------------------------------
  install_backend(module)  on 'sglang.srt.layers.attention.deepseek_v4_backend'
      - drift guard: source anchors of init_forward_metadata must match
      - replaces init_forward_metadata with the port below (faithful copy of
        new base 2314-2337 + the opt1 decision block)
      - adds _dsv41_opt1_keep_rows(forward_batch) and, for phase 2,
        _build_late_layer_tail_metadata_opt1 (port of old fin2 :1604-1720
        masked builder onto the new base's post-processing)
  install_model(module)    on 'sglang.srt.models.deepseek_v4'
      - drift guard: source anchors + parameter names of
        _forward_layers_hc_pre_from_prev must match
      - wraps it: late_layer_tail_skip -> cut self.end_layer to
        self.late_layer_start for the duration of the call (finally-restore),
        then republishes dspark stand-ins for captured layers >= late_layer_start

  Gates: DSV41_SKIP_NONFINAL_DECODER (default OFF -- opt-in per campaign
  discipline; =0 one-switch rollback, same env name as the 0.2.9 production
  engine). Phase 2: DSV41_SKIP_NONFINAL_MIXED (default OFF).

5. RISK LIST / [U] UNVERIFIED (honest)
--------------------------------------------------------------------------------
  [U1] next_combined boundary nuance: cutting end_layer changes the
       `i + 1 < self.end_layer` decision for the LAST executed layer only
       (may skip building a collapsed hand-off the base would have built);
       downstream consumers after the method should be form-agnostic but this
       was not proven on-GPU. Deployment acceptance: opt1-on vs opt1-off
       fixed-prompt multi-chunk greedy decode must be token-identical.
  [U2] phase-2 low_ratio re-key: old base's "full-batch-keyed tail lens with 0
       at dropped requests" contract vs the new base's _low_ratio_index_topk_
       dense consumers -- ported per old comments, not re-derived against
       every new consumer. Default OFF mitigates.
  [U3] SPLIT_PREFILL forwards: is_extend_without_speculative() includes them;
       the mask predicate stays row-consistent under slicing (seq/orig sliced
       together in init_new), but the split machinery was only read, not run.
  [U4] DP attention shapes: mask is computed in the row space of
       extend_seq_lens_cpu (same space the base tail builder uses), but DP
       attention was not exercised (production is TP4/EP4, attn-DP off).
  [U5] DLLM_EXTEND: excluded explicitly from the mask (conservative; DLLM
       fill ids include a mask block the orig_seq_lens proxy does not model).
  [U6] Waste kept on purpose: in all-skip forwards the unrestricted tail
       metadata is still built (model reads .late_layer_tail unconditionally
       at M3). Metadata-only cost (page tables over <=128*bs rows), vs the
       saved 19-layer compute over (chunk-128) rows.
  [R1] Engine drift: any image bump that moves init_forward_metadata /
       _forward_layers_hc_pre_from_prev trips the anchor guard -> adapter
       refuses to install and logs ERROR (fail-safe to base behavior).
"""
import inspect
import logging
import os

_logger = logging.getLogger("skip_nonfinal_decoder")

ENV = "DSV41_SKIP_NONFINAL_DECODER"      # same name as 0.2.9 production engine
MIXED_ENV = "DSV41_SKIP_NONFINAL_MIXED"  # phase 2: mixed-batch row restriction
_MARKER_B = "_dsv41_skip_nonfinal_backend"
_MARKER_M = "_dsv41_skip_nonfinal_model"

# Substrings that must appear in the CURRENT engine source before we replace
# anything. If an image bump changes these methods, install refuses (R1).
BACKEND_ANCHORS = (
    "def init_forward_metadata(self, forward_batch: ForwardBatch) -> None:",
    "self._build_late_layer_tail_metadata(forward_batch)",
    "self.init_forward_metadata_in_graph(forward_batch)",
)
MODEL_ANCHORS = (
    "def _forward_layers_hc_pre_from_prev(",
    "self._check_late_layer_tail_readers(forward_batch)",
    "tail = attn_backend.tail_forward_metadata.late_layer_tail",
)
MODEL_PARAMS = (  # parameter names of _forward_layers_hc_pre_from_prev
    "self", "positions", "hidden_states", "forward_batch", "input_ids",
    "input_ids_global", "capture_dspark", "dspark_aux_hidden_states",
)


def enabled() -> bool:
    raw = os.environ.get(ENV, "")
    return raw is not None and raw.strip().lower() in ("1", "on", "true", "yes")


def mixed_enabled() -> bool:
    raw = os.environ.get(MIXED_ENV, "")
    return raw is not None and raw.strip().lower() in ("1", "on", "true", "yes")


def _ints(x):
    """list<int> from a list/tuple or a torch CPU tensor (mock-friendly)."""
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [int(v) for v in x]
    return [int(v) for v in x.tolist()]


def keep_mask(seq_ends, orig_lens, window):
    """Pure predicate (unit-tested): per-row keep decision.

    seq_ends[i]  = extend_range.end of row i (e_i)
    orig_lens[i] = max(e_i, len(origin_input_ids)) (>= e_i; == E mid-prefill)
    Skip row i iff e_i + window <= orig_i: everything this chunk's tail would
    write sits at absolute positions <= e_i - 1 <= E - window - 1, and no
    later reader ever reads below E - (window - 1) (decode window reach).
    """
    keep = []
    for e, o in zip(seq_ends, orig_lens):
        if o < e:  # inconsistent (retract edge) -> keep, base behavior
            keep.append(True)
            continue
        keep.append(not (e + window <= o))
    return keep


# --------------------------------------------------------------------------
# backend side
# --------------------------------------------------------------------------
def install_backend(module) -> bool:
    if not enabled():
        return False
    cls = getattr(module, "DeepseekV4AttnBackend", None)
    orig = getattr(cls, "init_forward_metadata", None) if cls else None
    if orig is None:
        _logger.warning("skip_nonfinal_decoder: DeepseekV4AttnBackend."
                        "init_forward_metadata anchor missing; not installed")
        return False
    if getattr(orig, _MARKER_B, False):
        return False
    try:
        src = inspect.getsource(orig)
    except OSError:
        src = ""
    for anchor in BACKEND_ANCHORS:
        if anchor not in src:
            _logger.error("skip_nonfinal_decoder: init_forward_metadata "
                          "drifted (anchor %r missing); refusing to install "
                          "-- base bounded-replay behavior kept", anchor)
            return False

    def _get_logical_mode(fb):
        return module._get_logical_forward_mode(fb)

    def _opt1_keep_rows(self, forward_batch):
        """None when opt1 is inactive for this forward; else per-row keep."""
        if not getattr(self, "_dsv41_skip_nonfinal_on", False):
            return None
        if not self.enable_decoder_swa_bounded_replay:
            return None
        mode = forward_batch.forward_mode
        if not mode.is_extend_without_speculative():
            return None
        if mode.is_dllm_extend():  # [U5]
            return None
        if module.is_cp_active(forward_batch):
            return None
        seq = _ints(forward_batch.seq_lens_cpu)
        orig = _ints(forward_batch.orig_seq_lens)
        if seq is None or orig is None or len(seq) != len(orig) or not seq:
            return None
        return keep_mask(seq, orig, int(module.SWA_WINDOW))

    def _build_late_layer_tail_metadata_opt1(self, forward_batch, keep):
        """Phase 2 (DSV41_SKIP_NONFINAL_MIXED): port of the 0.2.9 fin2 masked
        builder -- restrict the tail to kept rows, indices in full row space.
        [U2] low_ratio re-key per old-base contract; default OFF."""
        extend_lens_cpu = _ints(forward_batch.extend_seq_lens_cpu)
        seq_lens_cpu = _ints(forward_batch.seq_lens_cpu)
        keep_idx = [i for i, m in enumerate(keep) if m]
        sub_extend = [int(extend_lens_cpu[i]) for i in keep_idx]
        sub_seq = [int(seq_lens_cpu[i]) for i in keep_idx]
        device = forward_batch.out_cache_loc.device
        token_indices, tail_lens_cpu, swa_replay_start = (
            module.late_layer_tail_layout(
                extend_lens_cpu=sub_extend,
                seq_lens_cpu=sub_seq,
                tail_len=int(module.SWA_WINDOW),
                device=device,
            )
        )
        # Shift the subset's concatenated rows into full-batch row space so
        # LateLayerTail.rows() gathers from full-batch tensors.
        full_starts, acc = [0], 0
        for n in extend_lens_cpu[:-1]:
            acc += n
            full_starts.append(acc)
        sub_starts, acc = [0], 0
        for n in sub_extend[:-1]:
            acc += n
            sub_starts.append(acc)
        import torch  # engine-side only (phase 2 path)
        shifts = torch.tensor(
            [full_starts[i] - s for i, s in zip(keep_idx, sub_starts)],
            device=device).to(token_indices.dtype)
        req_of_row = torch.repeat_interleave(
            torch.arange(len(keep_idx), device=device),
            torch.tensor(tail_lens_cpu, device=device),
            output_size=token_indices.shape[0])
        token_indices = token_indices + shifts[req_of_row]
        full_tail_lens = [0] * len(extend_lens_cpu)
        for i, n in zip(keep_idx, tail_lens_cpu):
            full_tail_lens[i] = n
        keep_t = torch.tensor(keep_idx, device=device, dtype=torch.long)
        sub_req_pool_indices = forward_batch.req_pool_indices[keep_t]
        sub_seq_lens_t = forward_batch.seq_lens[keep_t].to(torch.int32)
        out_cache_loc = module._tail_rows(
            forward_batch.out_cache_loc, token_indices=token_indices,
            contiguous_start=None)
        tail_lens = torch.tensor(tail_lens_cpu, dtype=torch.int32,
                                 device=device)
        metadata = self.init_forward_metadata_prefill(
            max_seq_len=max(sub_seq),
            req_pool_indices=sub_req_pool_indices,
            seq_lens=sub_seq_lens_t,
            seq_lens_cpu=sub_seq,
            out_cache_loc=out_cache_loc,
            num_tokens=sum(tail_lens_cpu),
            extend_seq_lens=tail_lens,
            extend_seq_lens_cpu=tail_lens_cpu,
            extend_start_loc=torch.cumsum(tail_lens, dim=0) - tail_lens,
            swa_replay_start=swa_replay_start,
            forward_batch=None,
            cp_metadata=None,
        )
        swa_out_cache_loc = (
            metadata.core_attn_metadata.request_window_layout.write_loc
            if self.token_to_kv_pool.request_window is not None
            else self.token_to_kv_pool.translate_loc_from_full_to_swa(
                out_cache_loc).to(torch.int32))
        metadata.core_attn_metadata.swa_out_cache_loc = swa_out_cache_loc
        # Full-batch-keyed repeats: dropped requests repeat 0 times (t_len==0
        # branch downstream), sum == subset row count. [U2]
        metadata.low_ratio_req_indices = torch.repeat_interleave(
            forward_batch.req_pool_indices.to(torch.int64),
            torch.tensor(full_tail_lens, device=device,
                         dtype=torch.int64))
        positions = module._tail_rows(
            forward_batch.positions, token_indices=token_indices,
            contiguous_start=None)
        metadata.low_ratio_pos_i64 = positions.to(torch.int64)
        metadata.late_layer_tail = module.LateLayerTail(
            token_indices=token_indices,
            positions=positions,
            extend_seq_lens=tail_lens,
            extend_seq_lens_cpu=tail_lens_cpu,
            swa_out_cache_loc=swa_out_cache_loc,
            contiguous_start=None)
        return metadata

    # M6: BCG capture/replay never skip; also kills stale-flag reads on
    # extend forwards served as BCG replays. MultiStepBackend delegates to
    # the leaf class, so wrapping here covers both.
    for graph_entry in ("init_forward_metadata_for_breakable_cuda_graph_capture",
                        "prepare_forward_metadata_for_breakable_cuda_graph_replay"):
        g_orig = getattr(cls, graph_entry, None)
        if g_orig is None or getattr(g_orig, _MARKER_B, False):
            if g_orig is None:
                _logger.warning("skip_nonfinal_decoder: %s missing on this "
                                "image; BCG paths rely on the model-side "
                                "is_in_breakable_cuda_graph gate only",
                                graph_entry)
            continue

        def _reset_wrapper(self, *args, __orig=g_orig, **kwargs):
            ret = __orig(self, *args, **kwargs)
            self.late_layer_tail_skip = False
            return ret

        setattr(_reset_wrapper, _MARKER_B, True)
        setattr(cls, graph_entry, _reset_wrapper)

    def init_forward_metadata(self, forward_batch) -> None:
        # Faithful port of new base deepseek_v4_backend.py:2314-2337 with the
        # opt1 decision block inserted (the only deltas are the three lines
        # between the markers).
        logical_forward_mode = _get_logical_mode(forward_batch)
        if self.mtp_enabled and logical_forward_mode.is_idle():
            self.online_c128_mtp.clear()
            return
        self.encoder_replay = forward_batch.encoder_swa_replay
        self.forward_metadata = self._build_forward_metadata(forward_batch)
        self.init_forward_metadata_in_graph(forward_batch)
        # --- opt1 begin ---------------------------------------------------
        keep = _opt1_keep_rows(self, forward_batch)
        self.late_layer_tail_skip = False
        build_tail = (
            self.enable_decoder_swa_bounded_replay
            and forward_batch.forward_mode.is_extend_without_speculative()
        )
        if build_tail and keep is not None and not any(keep):
            # No row reads its late-layer output this chunk. The tail metadata
            # is still built (the model reads .late_layer_tail unconditionally
            # [U6]) but the model wrapper cuts the layer loop short.
            self.tail_forward_metadata = (
                self._build_late_layer_tail_metadata(forward_batch))
            self.late_layer_tail_skip = True
        elif (build_tail and mixed_enabled() and keep is not None
              and not all(keep)):
            self.tail_forward_metadata = (
                _build_late_layer_tail_metadata_opt1(self, forward_batch, keep))
        elif build_tail:
            self.tail_forward_metadata = (
                self._build_late_layer_tail_metadata(forward_batch))
        else:
            self.tail_forward_metadata = None
        # --- opt1 end -----------------------------------------------------
        if self.token_to_kv_pool.request_window is not None:
            self.token_to_kv_pool.request_window.activate(
                self.forward_metadata.core_attn_metadata.request_window_layout)

    def _arm(self):
        # class-level default; instances see it via attribute lookup
        type(self)._dsv41_skip_nonfinal_on = True

    setattr(init_forward_metadata, _MARKER_B, True)
    cls.init_forward_metadata = init_forward_metadata
    cls._dsv41_opt1_keep_rows = _opt1_keep_rows
    cls._build_late_layer_tail_metadata_opt1 = _build_late_layer_tail_metadata_opt1
    cls._dsv41_opt1_arm = _arm
    cls._dsv41_skip_nonfinal_on = True
    _logger.info("skip_nonfinal_decoder: backend armed (init_forward_metadata "
                 "replaced; %s margin-guarded keep rule; mixed phase %s)",
                 ENV, "ON" if mixed_enabled() else "OFF")
    return True


# --------------------------------------------------------------------------
# model side
# --------------------------------------------------------------------------
def install_model(module) -> bool:
    cls = getattr(module, "DeepseekV4Model", None)
    orig = getattr(cls, "_forward_layers_hc_pre_from_prev", None) if cls else None
    if orig is None:
        _logger.warning("skip_nonfinal_decoder: DeepseekV4Model."
                        "_forward_layers_hc_pre_from_prev anchor missing; "
                        "not installed")
        return False
    if getattr(orig, _MARKER_M, False):
        return False
    try:
        src = inspect.getsource(orig)
    except OSError:
        src = ""
    for anchor in MODEL_ANCHORS:
        if anchor not in src:
            _logger.error("skip_nonfinal_decoder: _forward_layers_hc_pre_from_"
                          "prev drifted (anchor %r missing); refusing to "
                          "install -- base behavior kept", anchor)
            return False
    try:
        params = tuple(inspect.signature(orig).parameters)
    except (TypeError, ValueError):
        params = ()
    if params != MODEL_PARAMS:
        _logger.error("skip_nonfinal_decoder: _forward_layers_hc_pre_from_prev "
                      "signature drifted %s != %s; refusing to install",
                      params, MODEL_PARAMS)
        return False

    def _forward_layers_hc_pre_from_prev(
        self, positions, hidden_states, forward_batch, input_ids,
        input_ids_global, capture_dspark, dspark_aux_hidden_states,
    ):
        skip = False
        if (self.late_layer_start is not None
                and forward_batch.forward_mode.is_extend_without_speculative()
                and not forward_batch.forward_mode.is_dllm_extend()
                and not module.is_in_breakable_cuda_graph()):
            backend = module.get_attn_backend()
            skip = bool(getattr(backend, "late_layer_tail_skip", False))
        if not skip:
            return orig(self, positions, hidden_states, forward_batch,
                        input_ids, input_ids_global, capture_dspark,
                        dspark_aux_hidden_states)
        # opt1: run [start_layer, late_layer_start) only -- the loop in orig
        # never reaches the tail switch, so saved_full stays None and orig
        # returns (hidden, prev_pre, None) on its normal exit path.
        saved_end = self.end_layer
        try:
            self.end_layer = min(saved_end, self.late_layer_start)
            ret = orig(self, positions, hidden_states, forward_batch,
                       input_ids, input_ids_global, capture_dspark,
                       dspark_aux_hidden_states)
        finally:
            self.end_layer = saved_end
        if capture_dspark and self.dspark_layers_to_capture:
            # Keep the aux capture list shape (one entry per captured layer):
            # publish the last full-sequence hidden mean as a stand-in for the
            # layers we skipped. Dead values for non-final chunks -- the chunk
            # that finishes the request republishes real values before any
            # drafting reader runs (0.2.9 contract, fin2 :3990-4001).
            standin = ret[0].mean(dim=1)
            for j in self.dspark_layers_to_capture:
                if self.late_layer_start <= j < saved_end:
                    dspark_aux_hidden_states.append(standin)
        return ret

    setattr(_forward_layers_hc_pre_from_prev, _MARKER_M, True)
    cls._forward_layers_hc_pre_from_prev = _forward_layers_hc_pre_from_prev
    _logger.info("skip_nonfinal_decoder: model armed "
                 "(_forward_layers_hc_pre_from_prev wrap; end_layer cut on "
                 "late_layer_tail_skip + dspark standins)")
    return True


def summary() -> str:
    return (f"gate={'on' if enabled() else 'off'} "
            f"mixed={'on' if mixed_enabled() else 'off'} "
            f"envs={ENV}/{MIXED_ENV}")
