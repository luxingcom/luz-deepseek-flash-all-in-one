"""P-SP: prefill sequence parallel -- P0 (comm face) + stage1 (bf16 row split)
+ stage2 (MXFP8 gather, MoE face).

Prefill-SP family (P-PREFILL-GROUP-DESIGN-20261001 §2.2: P0 通信面换法 ->
stage1 bf16 行分片 -> stage2 fp8 gather). P0 swaps the plain TP all-reduce
leaves on the prefill forward path for reduce-scatter + all-gather on the
SAME group/communicator. Wire bytes are identical (byte neutral); the value
of the swap is the comm-form change: census nccl.AR call count drops in the
PR window and nccl.RS/AG families appear (A4 gate ③), and stage1's row-split
data flow slots onto the exposed RS+AG seam. P1-SPcomm verdict (2026-10-01):
on a ring fabric NCCL AR IS RS+AG (same ring, same chunk order), so the
comm swap alone measures zero -- stage1's benefit face is the SHARDED
COMPUTE (each rank works 1/world of the rows), not the communication.

STAGE1 (this segment; DSV41_PREFILL_SP=1|shard + _EXACT=1 + _MIN_ROWS>=2048)
implements the row-split MAIN PATH: the SP section executor `sp_section` --
for one plain-AR leaf site whose post-AR work is row-wise (per-token),
     stock:   z = rowwise(AR(partial))        [full rows on every rank]
     stage1:  z = AG(rowwise(RS(partial)))    [rowwise runs on rank r's
                                               shard only: 1/world the rows]
Row = token row; the shard of rank r IS the r-th reduce-scatter output chunk
(contiguous rows [r*E, (r+1)*E), E=ceil(rows/world), zero-padded), so no row
is ever split across ranks and the assembly is plain concatenation.

EXACT bit-preservation (the load-bearing premise), argument + dual-check:
  (a) reduction phase: NCCL ring AR == RS on the same ring with the same
      chunk order, so per output element the rank-order partial sum is
      identical (P0's theorem, P1-boot-verified on this cluster);
  (b) row-wise phase: rowwise mixes no rows, so rowwise(shard_r) equals the
      same rows of rowwise(full) BITWISE -- provided rowwise is row-count
      invariant (the community's sp_logical_rows() law: kernels whose
      selection depends on x.shape[0] -- e.g. an hc_norm_prefill gated on
      4096<=rows -- would re-tile at 1/world rows and can drift bf16 ulps);
  (c) assembly phase: all-gather concatenates the same rows in rank order.
  (b) is NOT assumed: the first call per (site, dtype, size-bucket) dual-runs
  the stock full-rows path on a clone alongside the sharded path and compares
  bitwise (torch.equal); any mismatch (reduction-order drift OR row-count
  dependent section behavior) flips that bucket to a permanent stock fallback
  with a loud error and returns the verified stock reference (fail-safe
  direction = the verified path, QA-GATE G5 / design card R4).

Consumer-form contract (hard requirement: read moe_b12x_next.py BEFORE
writing): the MoE consumer face is ZERO code for stage1 -- PREQUANT_WARM
stays false unless DSV41_PREFILL_SP_FP8_MOE=1 (moe_b12x_next.py:109-111
reads DSV41_PREFILL_SP in {1,on,true,shard} ONLY together with _FP8_MOE),
so the MoE consumes a plain full-rows bf16 [rows, K] hidden_states:
  * the executor's AG output is exactly that: full rows, original dtype,
    contiguous, no pad rows -- bitwise the stock AR output;
  * the shard block convention is the contiguous rank chunk -- the same
    token-major [m, K] per-shard row block moe_b12x_next.prequant_views()
    exposes (pin[:m], stage2's MXFP8 gather destination), so stage2's
    quantize-shard-then-gather slots onto this layout unchanged.

STAGE2 (this segment; DSV41_PREFILL_SP=1|shard + _EXACT=1 +
DSV41_PREFILL_SP_FP8_MOE=1) implements the fp8 gather, MoE face (the
sending half of the design card's item 2): the stage1 AG's payload goes
from bf16 to MXFP8 (E4M3 payload + UE8M0 per-32-element power-of-two
scale), wire bytes (K + K/32) / 2K = 1/1.94 of bf16. The quantizer is a
bit-exact replica of b12x's in-kernel front-end quantizer (every constant
and rounding rule field-checked against the runtime tree, see
mxfp8_quantize's docstring), so the b12x MoE consumes the gathered rows
without re-quantization loss: same bytes -> same FC1 inputs (the design
card R4 premise is a RUNTIME check here, not an assumption).
Delivery forms (one of two, decided by consumer presence):
  * dequant-at-destination (the implemented leaf-seam form): AG the fp8
    bytes, dequantize to bf16, hand the engine the full-rows tensor.
    Consumer-agnostic -- works with or without the b12x prequant patch;
    on the MoE-input face the consumer's own quantizer reproduces the
    same values (MXFP8 roundtrip idempotence: payload bytes are E4M3, so
    dequant is exact in bf16 and re-quantizing lands back on the same
    grid), while NON-quantizing consumers of the same tensor (router /
    residual) see the roundtripped bf16 -- a value-bounded, QA-gated
    change, NOT bit-preserving: that is why fp8 sites must be explicitly
    registered by the face owner.
  * direct-view delivery (sp_section_fp8_views, the API for the
    layer-carry card): copy the gathered fp8 rows straight into
    moe_b12x_next.prequant_views(m) (pin[:m] / psc[:m*K/32]) -- zero
    dequant; the b12x front-end variant launched by forward_prequant
    (moe_b12x_next.py:620-639, guarded by the _dsv41_b12x_rows marker
    :952-963) reads packed_input / packed_input_scale directly. NOT
    wireable at the plain-AR leaf seam: the dispatch must carry
    hidden_states_pre_quant into the MoE call (engine-native channel,
    fused_moe_triton/layer.py:1520-1526 forward(pre_quant_input=...) ->
    :1618), which only the MoE-layer hook can do -- deliberately left to
    the layer-carry protocol card, same deferral as stage1's engine
    sections.
Stage2 gates: an fp8 site must be registered with fp8=True
(register_section); unregistered sites keep the verified bf16 gather even
when _FP8_MOE=1 (an unowned fp8 face is refused, never shipped blind --
the same constructive-safety law as unowned sections). The dual check for
fp8 sites verifies BOTH premises bitwise on the first call per bucket:
(a) the bf16 sharded path still equals stock (the fine-grained guard: E4M3
rounding is coarse enough to MASK a bf16 ulp drift, so the reduction-order
check must ride bf16), and (b) the fp8 gather equals the oracle
quantize-dequantize of the stock full-rows reference. Either failing ->
loud error + permanent bf16-gather fallback for the bucket (design card
§5.1 "failure = the bf16 gather path stays in place").

The ATTENTION-input face (DSV41_PREFILL_SP_FP8) stays tolerated-WARNING-
ignored on this tree: its bit-identity premise FAILS (see _parse_fp8_keys'
warning for the mirror evidence) -- do NOT ship a non-bit-identical face.

Section registry: `register_section(site, fn, fp8=False)` binds a site's
row-wise section (shard in -> shard out; must be per-row pure AND
row-count invariant; pad rows may be present and stay isolated per-row).
fp8=True additionally owns the stage2 face for that site: the site owner
proves the AG output feeds the MXFP8-consuming face (the MoE input), so
gathering fp8 bytes is value-preserving for the consumer; the router /
residual faces of the same tensor see the roundtripped bf16, which is a
QA-gated numerics change, never a silent one. Sites without a registered
section run the IDENTITY section: byte-neutral P0 semantics (verified
RS+AG swap) -- constructive safety: an unowned section is refused (stock
flow), never a masked re-implementation (doc60 §2#5 law, "consume 分支拒走
自研路径"), and an unowned fp8 face keeps the bf16 gather.

STAGE1 ENGINE SECTIONS (this file, the layer-carry protocol; PREFILLSP-
STAGE1-DEV-20261002.md §缺口定谳). On the production prefill path of this
tree (DeepseekV41Config sets hc_pre_from_prev_sublayer=True, configs/
deepseek_v41.py:47 -> DeepseekV4Model.forward :4672 dispatching at :4748
-> _forward_layers_hc_pre_from_prev :4381 (per-layer kwargs call :4531)
-> per-layer forward_hc_pre_from_prev :3505) the
plain-AR seam and its following per-row work are:
  site dsv4.attn_ar = attn_tp_all_reduce (deepseek_v4.py:2531, the
      mhc overlap_only prefill form; leaf = dp_attention.py:1142)
      section = the post-attention hc consumption `_hc_post_with_combine`
      (deepseek_v4.py:3446): fused mhc_post_combine_norm_prefill (:3497
      import / :3501 call, kernels .../mhc_post_combine_norm_prefill.py:33)
      / mhc_post_combine (:3503, kernels .../mhc_post_combine.py:38) /
      hc_post (:2922) -- chosen by the engine's G predicate at the
      FULL row count.
  site dsv4.ffn_ar = the MoE post-experts AR moe_tensor_model_parallel_
      all_reduce (communication_op.py:132; called once from post_experts_
      all_reduce, layers/moe/utils.py:811/:838, at DeepseekV2MoE.
      forward_normal deepseek_v2.py:1377 -- the FusedMoE-internal
      fused_moe_triton/layer.py:1597 AR does NOT fire for this model:
      DeepseekV2MoE constructs FusedMoE with its reduce_results=False
      default, layer.py:336; the b12x_next runner swap replaces the fused
      expert function, not this seam) -- section = the same hc consumption
      for the FFN sublayer (deepseek_v4.py:3728-3738, norm = next_norm,
      hc_post-direct form when next_combined is None). The FFN stats are
      started before this AR by the engine itself (deepseek_v2.py:
      1369-1376, current_mhc_post_fusion().start_stats_before_all_reduce),
      exactly as on the attention side.
The protocol: a frame wrap on DeepseekV4DecoderLayer.forward_hc_pre_from_
prev pushes (layer, forward_batch, next_norm, next_combined); a wrap of
mhc_post_fusion.use_mhc_post_fusion publishes, per overlap_only sublayer
context, the carry {residual, MhcPostFusion (stats via its record_stats
partial), norm, consumption form}; the AR leaf whose name matches the
carry (the moe leaf has exactly ONE consumer in the MoE frame, so a
pending ffn carry cannot misroute; a shared-expert AR cannot occur --
the shared MLP is reduce_results=False, deepseek_v2.py:770) runs RS ->
replica section on the shard -> AG of every section output; the returned
full-rows `updated` plus the gathered (combined, normalized) are stashed,
and the engine's own post-AR consumption (_hc_post_with_combine / hc_post
wraps) is SUPPRESSED by tensor identity (x is stash.updated -- the engine
passes the leaf's return straight through), so the section runs exactly
once. The dual check compares the
sharded section against the ENGINE'S OWN full-rows method (the unwrapped
originals), not against the replica -- so BOTH premises are runtime-
checked: row-split fidelity AND replica fidelity; any mismatch flips the
(site, dtype, bucket) to a permanent stock path whose return values are
the engine's own full-rows computation (stash-fed, still suppressed --
no double-apply). Sections deliberately NOT on this seam (PREFILLSP-
STAGE1-DEV §缺口): the dense replicated projections wq_a/wkv/engram.wkv
(row-split would collide with the armed DSV41_REPLICATED_SPLIT column
split of the same GEMMs -- unowned face, refused), the router gate
(full-rows consumer, deferred), the Engram retrieval段 and the hc mix
stats段 (stats input is the residual, not an AR output -- already
side-stream overlapped in stock). fp8 is NOT registered for either carry
site: the gathered `updated` is the residual stream consumed by every
face, not an MXFP8-only consumer (stage2 law).

Laws carried from the lineage (spark_prefill_split.py / doc60, stage1-
relevant subset): eligibility law (plain eager extend prefill, rows >=
MIN_ROWS, CUDA, graph-capture excluded); NO collective of any kind at
init/install time (W21 b1 post-mortem); unowned sections refuse the self-
built path (constructive safety). int32 block tables / FIX-D width buckets
are indexer-lineage (P4 overlay arm, DSV41_SPARK_PREFILL_TP_SPLIT) and out
of scope here.

Bit-equality argument (the load-bearing premise): NCCL's ring
allreduce(SUM) IS reduce-scatter followed by all-gather on the same ring
with the same chunk order, so per output element the rank-order partial
sum is identical and RS+AG is bit-identical to AR -- same communicator,
same op, same accumulation order. The premise can break only if NCCL
picks different algorithms for the two ops at a given size (e.g. tree for
AR, ring for RS: ((r0+r1)+(r2+r3)) vs ((r0+r1)+r2)+r3 differ in bf16
ulps). That is therefore NOT assumed: the first swapped call per
(site, dtype, size-bucket) dual-runs stock AR on a clone alongside the
RS+AG result and compares bitwise (torch.equal); any mismatch flips that
bucket to a permanent stock fallback with a loud error (fail-safe
direction = the verified stock path, QA-GATE G5 / design card R4).

Scope -- exactly the plain-SUM TP AR leaves the deepseek_v4 prefill path
reaches (mirror main-79cafec0, docker-verified):
  sglang.srt.distributed.communication_op
      tensor_model_parallel_all_reduce          -> get_tp_group().all_reduce
          (RowParallelLinear linear.py:1690; vocab embedding :589;
           engram :778. NOT the MoE AR on this model: see the moe leaf)
      attention_tensor_model_parallel_all_reduce -> get_attn_tp_group().all_reduce
          (layernorm.py:255)
      moe_tensor_model_parallel_all_reduce      -> get_moe_tp_group().all_reduce
          (the MoE post-experts AR, deepseek_v2.py:1368 via
           post_experts_all_reduce layers/moe/utils.py:838 -- the FFN
           section site dsv4.ffn_ar; CORRECTION of the P0 scope note that
           put the MoE AR at fused_moe_triton/layer.py:1597: that inner AR
           needs FusedMoE.reduce_results=True, but DeepseekV2MoE builds it
           with the False default, so :1597 never fires for this model)
  sglang.srt.layers.dp_attention
      attn_tp_all_reduce -> get_parallel().attn_tp_group.all_reduce (:1142)
          (deepseek_v4.py:2531/:2565 attention-o AR; vocab :586)
Deliberately NOT wrapped (byte-neutral discipline, left stock):
  quant_all_reduce variants (quantized comm, NOT byte-neutral), the fused
  AR+norm helpers, the mhc all_reduce_mhc_norm/combine kernels (fused AR),
  moe_expert_parallel_all_reduce (EP group; world 1 at EP1 anyway), and
  GroupCoordinator.all_reduce itself (would mix DP/EP/TP groups).

Engagement: a forward bracket on DeepseekV4Model.forward arms a module
flag only when the batch is a plain eager prefill (forward_mode.
is_extend_without_speculative()), rows >= DSV41_PREFILL_SP_MIN_ROWS, CUDA,
and not under CUDA-graph capture (family eligibility law, doc60 §2#6 /
spark_prefill_split.py:80-88). Eligibility inputs (rows, mode, world) are
SPMD-uniform across TP ranks, so every rank takes the same branch and the
collective order stays consistent -- and NO collective of any kind runs at
init (W21 b1 post-mortem law, doc60 §2#7).

Doors (fail-safe; unset/off/0/false = zero wrappers installed, the engine
functions keep their byte-identical bindings):
  DSV41_PREFILL_SP            unset|0|off|false = inert
                              comm = P0 (comm swap only)
                              1|shard|on|true = stage1 -- REQUIRES
                                DSV41_PREFILL_SP_EXACT=1 (below); without
                                it a WARNING fires and the adapter stays
                                inert (the non-EXACT +20% form is not
                                implemented; fail-closed)
                              anything else = refuse the boot at import
  DSV41_PREFILL_SP_EXACT      1|on|true = EXACT bit-preserving stage1
                              (the only implemented form); unset/0 = WARNING
                              + inert
  DSV41_PREFILL_SP_FP8        attention-input face: boolean; NOT implemented
                              on this tree (bit-identity premise fails --
                              mirror evidence in the boot WARNING); any =on
                              value is tolerated with that WARNING and
                              ignored, never fatal
  DSV41_PREFILL_SP_FP8_MOE    MoE face fp8 gather: boolean; arms ONLY under
                              stage1+EXACT (stage2 rides the stage1 row
                              split, exactly the grouping moe_b12x_next.py:
                              109-110 demands of PREQUANT_WARM); elsewhere
                              tolerated with a WARNING and ignored;
                              gathers stay bf16 on every site NOT registered
                              with register_section(..., fp8=True)
  DSV41_PREFILL_SP_DEBUG      compare = dual-run stock vs shard on EVERY
                              swapped call (community _DEBUG=compare form;
                              default off = first call per bucket only);
                              under deep-carry also Layer-2 of the EXACT
                              gate: beside every forced-kernel (divergence
                              band) path, stock full-rows reference on
                              AG'd operands, torch.equal + mismatch naming
                              dump[:DIR] = Layer-1 capture: per-chunk
                              segB/exit torch.save (the harness pairs the
                              two boots by (rank, chunk, tag)); on an
                              unarmed boot installs the pure loop-exit
                              observer (the stock side of the A/B pair);
                              any other value: WARNING + ignored
  DSV41_PREFILL_SP_WKV        shard (DEFAULT) | full -- the engram seam
                              form (mia `_WKV` key family): shard = the v1
                              mia seam (lookup AR boundary-reduced, wkv
                              GEMM + gate on 1/world rows, per-(layer,M)
                              bit self-check with permanent island
                              fallback); full = the v0 gather-island form
                              on every engram layer; any other value
                              refuses the boot
  DSV41_PREFILL_SP_MIN_ROWS   >=1, default 2048 (community key/value,
                              moe_b12x_next.py:111)

Anti-drift (correctness-sensitive件 law, design card §七): install-time
seam fingerprints (inspect.getsource of each leaf must still show its
one-line group dispatch) refuse the boot loudly when the engine seam
moved -- an inert wrap would silently keep AR and the arm would look
green (挂点漂移双死法). The from-import trap (L2PF lesson,
l2pf-dev/QUALIFY.md §2): the leaves are wrapped at the DEFINING module's
exec inside sitecustomize's EngramLoader, so every consumer's from-import
(linear/layer/vocab/layernorm/engram via the sglang.srt.distributed
package re-export; deepseek_v4.py:88 via dp_attention) binds the wrapped
object; install_model additionally rebinds deepseek_v4's own from-imported
attn_tp_all_reduce defensively (token_req_compact dual-module pattern).

REANCHOR 2026-10-02 (main-79cafec0; the 12:19/12:43 refusals post-mortem).
The 0607ad2e boot refusals ("DeepseekV4DecoderLayer.self_attn missing;
refusing to boot (layer-carry seam moved)") were NOT a moved seam: the
attention module is still `self_attn` on this base -- deepseek_v4.py:2624
`self.self_attn = self._build_self_attn(...)`, an INSTANCE attribute of
DeepseekV4DecoderLayer (class def :2604). The refusal fired because the
install guard probed `hasattr(layer_cls, "self_attn")` at CLASS level,
which is False for any nn.Module instance attribute on ANY base -- the
guard could never have passed; every engine needle it guarded with
(_hc_post_with_combine :3446, forward_hc_pre_from_prev :3505, hc_post
:2922 with its needles, use_mhc_post_fusion's "_current", the comm-op /
dp_attention leaf dispatches, post_experts_all_reduce -> moe leaf
utils.py:838) is intact on main-79cafec0, several at the very line
numbers this file already cited. The reanchor keeps the fail-stop
philosophy and fixes the probe LEVEL: class-level hasattr for METHODS
(_hc_mix_stats, _run_moe_ffn_dp_sync, _build_self_attn), and
`_need_init_source` source needles on `DeepseekV4DecoderLayer.__init__`
for the INSTANCE-attribute seams (self.self_attn / self.mlp /
self.input_layernorm / self.post_attention_layernorm / self.hc_attn_fn /
self.hc_ffn_fn) -- a missing symbol still refuses the boot BY NAME.
The cascade "four modules, same sentence" is import-chain, not four
seams: dspark (:39), nextn (:33) and multimodal.processors.deepseek_v41
(:15) all `from sglang.srt.models.deepseek_v4 import ...`, so the one
raise during deepseek_v4's exec surfaces in each importer.

DEEPCARRY 2026-10-02 (T60, doc104 W2; the mia form, M7 red-flag removal).
The per-site stage1 form above is wire-NEGATIVE: every carry site
all-gathers the section outputs (updated [M,4,5120] + combined + normalized
~= 5x [M,5120]) back to full rows each sublayer, ~=3x stock AR bytes/site
(MIA-PREFILL21-DEEPDIVE §3b/§5-0, +4.9 GiB/chunk). The deep-carry form
replaces the ENGINE LAYER LOOP instead: `DeepseekV4Model.
_forward_layers_hc_pre_from_prev` (mirror deepseek_v4.py:4381-4552) is
replaced by a hash-pinned copy `_dc_forward_layers` whose residual R and
prev_pre stay SHARDED across the whole 0..late_layer_start-1 region:
  segment A (0..20 deep-carry region): entry split R = hidden[lo:hi]
      ([E,4,5120], E = ceil(M/world)); the engine's own per-layer
      forward_hc_pre_from_prev runs ON THE SHARD; at each sublayer
      boundary the attention/MoE INPUT is all-gathered (AG-in, [M,5120]),
      the stock full-rows core runs (attention: MQALayer.forward on the
      gathered x -- wo_b already skips its AR under the overlap mhc
      context, deepseek_v4.py:2529 -- the boundary AR leaf then runs
      AR+slice (EXACT) / RS (shard) -> [E,5120] back on the shard; MoE:
      _run_moe_ffn_dp_sync on the gathered x, post-experts AR leaf same
      boundary reduction). Row-local segments (entry combine, hc mix
      stats, hc post/combine/norm, gate) run on 1/world rows; every
      row-count-keyed kernel branch is decided at the FULL row count
      (the sp_logical_rows law; see the _hc_* wrappers -- mia §1b/1c).
      Wire bytes per boundary = AG-in (N-1)/N*S + boundary reduction
      (N-1)/N*S (shard) or 2(N-1)/N*S (EXACT) -- ring-neutral vs stock
      AR in the shard form (P1-SPcomm theorem), 1.5x in EXACT.
  segment B (layer-21 boundary): enter_late_layer_tail (engine metadata
      switch), plan retired (all SP hooks go inert), R/prev_pre gathered
      back to full rows, then tail.rows() applied exactly as stock
      (mirror :4432-4445); combined_attn/normalized_attn reset to None
      exactly as stock (:4433-4434).
  segment C (21..end stock tail): the stock loop body verbatim on tail
      rows; exit_late_layer_tail + the stock return triple.
Engram layers (1, 14) inside the region take the _dc_engram seam. v1
(the DEFAULT, day-2; the mia form): the lookup stays FULL-ROW (the
row-cache prefetch sees stock's hash ids), its wkv-partial AR -- the emb
reassembly over [M, n_hash_cols(24), head_dim(256)] -- becomes the
boundary reduction (EXACT: stock AR + rank-row slice; shard: RS), and the
second stage (wkv GEMM -> [E, 25600] + gate) runs on the shard through
the engine's own Engram.forward structure; the wkv GEMM's row-count
invariance is SELF-CHECKED per (layer, M) (first block dual-runs the
full-rows reference, torch.equal + a TP agreement vote, `del` of the
[M,25600] reference BEFORE the vote collective -- mia :586-606/:595) with
a PERMANENT gather-island fallback; DSV41_PREFILL_SP_WKV=full forces the
island form everywhere (the mia `_WKV=full` escape). v0/island (the day-1
skeleton form): AG R -> stock full-row engram -> row slice (+120 MiB
send/layer at M=4096; ag_byte_account.py models both forms -- v1 wires
RS(emb) replacing AR(emb), ~-36 MiB/layer, and NO residual gather).
Batches with no late-layer tail (tail=None) take the day-2 no-tail exit
(mia :731-733): no late-layer switch exists in stock for them, so the
region exit is a pure full-row gather of R/prev_pre and the stock return
triple carries None. DSpark capture rows inside the region (day-2) run
the mean(shard)-then-AG path: mean(dim=1) is row-pure and tail.rows is
row selection, so AG(shard means) then tail.rows selects bitwise the
same rows/values as stock's tail.rows-then-mean (stock :4467-4472).
Boundary-reduction correctness (EXACT): the boundary input IS the
full-rows partial (the cores just ran full rows), so EXACT runs the
STOCK collective and slices rank rows -- bitwise stock by construction;
drift risk lives only in the row-local sections, guarded by the
logical-rows wrappers + the T61 EXACT gate harness (see
EXACT-GATE-HARNESS.md) and, per bucket, the existing section dual-check
pattern (shard section vs the engine's own full-rows method).
Doors: DSV41_PREFILL_SP=1|shard (deep-carry is now the DEFAULT stage1
form) + DSV41_PREFILL_SP_EXACT=1 (boundary = AR+keep-1/4 rows, the T61
bit-equal fallback); EXACT unset under deep-carry = the T62 production
shard form (RS boundary; NOT bit-equal -- qeval/needle 背书 per mia
precedent; loud WARNING at import). DSV41_PREFILL_SP_DEEPCARRY=0 rolls
back to the reanchor per-site form (EXACT-only, fail-closed).
DSV41_PREFILL_SP_WKV=shard(default)|full selects the engram seam form.
DSV41_PREFILL_SP_DEBUG=compare (Layer-2 白盒: forced-kernel shard output
vs stock full-rows slice, per segment) | dump[:DIR] (Layer-1 capture:
per-chunk segB/exit dumps; an UNARMED boot with dump installs the pure
loop-exit observer -- the stock side of the A/B pair). Any
DSV41_PREFILL_SP off/unset value = zero wrappers, zero load (STAGE key
closed = zero-load rollback; DEBUG=dump alone installs an observer that
changes no behavior).
T62 trap (min_rows silent stock, doc104 T62 card): the plan builder
REFUSES ineligible batches with an explicit loud log line (reason-tagged,
once per reason) -- never silently stock inside an armed boot.
Seam probes: the reanchor's corrected two-level law is carried over
VERBATIM -- METHOD seams at class level (hasattr), INSTANCE-attribute
seams via _need_init_source's 6 needles on DeepseekV4DecoderLayer.
__init__ (the 0607ad2e class-vs-instance scope-bug class, second
convicted instance of the day; never again).

T61 DAY-3 (2026-10-02 post-abort; docs/verdicts/T61-ABORT-STACKWALL-
20261002.md §三.2, the stack-level install-order wall). Root cause: the
sitecustomize install order wo_a_w8 -> skip_nonfinal_decoder -> l2pf ->
prefill_sp -> ih puts FOREIGN adapter wrappers on our needle-checked
seams BEFORE us; skip_nonfinal_decoder.install_model (:443) is UNGATED
and ALWAYS wraps DeepseekV4Model._forward_layers_hc_pre_from_prev (its
marker _dsv41_skip_nonfinal_model is a DIFFERENT name than ours, so the
double-exec early-return never fired) -- inspect.getsource on the
wrapper returned the WRAPPER source (skip_nonfinal_decoder.py:473), the
14 loop needles missed the engine text (engine true source fb87a7f0
:4391 DOES contain them), and every armed head refused to boot (the
12:18Z A23-delta + 18:44Z T61 boots, same site same signature; no armed
SP boot ever succeeded after skip_nonfinal landed). Two day-3 fixes:
  (1) wrapper-aware seam probes: _need_source / _need_init_source /
      _fingerprint unwrap the wrap chain (__wrapped__, closure cells,
      default-arg bindings -- the three shapes this stack's adapters
      actually use) and needle-check the chain TERMINAL only; unwrap
      failure keeps the refusal (fail-closed semantics preserved --
      feeding a wrapper source still refuses);
  (2) skip_nonfinal semantic integration: with the loop replaced by
      _dc_forward_layers the foreign wrapper's end_layer cut can no
      longer fire on plan-active chunks, so the plan reads the
      wrapper's own decision inputs (backend late_layer_tail_skip stamp
      + the dllm/BCG guards, adapter :477-483 verbatim) and reproduces
      the cut IN-SEGMENT: segment A + full-row gather exit + dspark
      stand-ins + the None return triple (stock-with-skip engine
      :4426/:4549-4552 form). Without this, an armed
      DSV41_SKIP_NONFINAL_DECODER=1 boot (the A24 31-key production
      form carries the key) would run segments B/C on non-final chunks
      where the stock boot cuts at late_layer_start -- a behavior
      difference the EXACT gate would misread as OUR divergence.
      Key off = the stamp never exists = zero effect.
"""

import inspect
import logging
import os
import sys
import types

import torch

logger = logging.getLogger(__name__)

_MARKER = "_dsv41_prefill_sp"
_MODEL_MARKER = "_dsv41_prefill_sp_model"
_DC_DUMP_MODEL_MARKER = "_dsv41_prefill_sp_dump_model"
# day-8: the layer-face observer's class-level double-exec guard (same law
# as _DC_DUMP_MODEL_MARKER: read at CLASS level, set at CLASS level)
_DC_DUMP_LAYER_MARKER = "_dsv41_prefill_sp_dump_layer"
# REANCHOR 2026-10-02: identifies the seam-probe fix in boot logs (the
# 0607ad2e build refused on a class-level hasattr of an instance attr).
_REANCHOR_TAG = "reanchor-20261002/main-79cafec0"
# DEEPCARRY 2026-10-02: identifies the layer-loop replacement build.
_DEEPCARRY_TAG = "deepcarry-20261002/T60"
_DC_MODEL_MARKER = "_dsv41_prefill_sp_dc_model"
_DC_ATTN_MARKER = "_dsv41_prefill_sp_dc_attn"

# T61 day-3 (stackwall fix): marker attribute -> adapter name for the
# FOREIGN wrappers this stack's sitecustomize install order
# (wo_a_w8 -> skip_nonfinal_decoder -> l2pf -> prefill_sp -> ih) can put
# on our needle-checked seams before us. Used ONLY to (a) license the
# unwrap descent (an unmarked/unknown wrapper is NOT descended into --
# fail-closed) and (b) name the adapter in the one-line unwrap-depth log.
#   skip_nonfinal_decoder.py: _MARKER_M/_MARKER_B (:171-172); model side
#     is UNGATED and always wraps _forward_layers_hc_pre_from_prev
#     (install_model :443-516) -- the T61 wall itself.
#   l2_prefetch.py: `_dsv41_l2_prefetch` on the collective-leaf wrappers
#     (_patch_collectives :300-307, default-arg `_original` shape).
#   l2pf_attn.py: `_dsv41_l2pf_attn` on dp_attention.attn_tp_all_reduce
#     (:50/:71-77, same default-arg shape).
#   wo_a_w8.py: `_dsv41_wo_a_w8` (its deepseek_v4 face wraps load-time
#     pieces, not a needle-checked seam today -- listed for shape
#     recognition if that ever changes).
_ADAPTER_MARKERS = (
    ("_dsv41_skip_nonfinal_model", "skip_nonfinal_decoder"),
    ("_dsv41_skip_nonfinal_backend", "skip_nonfinal_decoder"),
    ("_dsv41_l2_prefetch", "l2_prefetch"),
    ("_dsv41_l2pf_attn", "l2pf_attn"),
    ("_dsv41_wo_a_w8", "wo_a_w8"),
)

_OFF = ("", "0", "off", "false")
_ON = ("1", "on", "true")
_STAGE1 = ("1", "shard", "on", "true")
_COMM = "comm"

# Size buckets for the first-call dual verification: NCCL picks algorithms
# per message size, so one verification point per bucket, not one global.
_BUCKET_BYTES = (4 << 20, 64 << 20)
_DTYPES = (torch.bfloat16, torch.float16, torch.float32)


def _parse_mode():
    raw = os.environ.get("DSV41_PREFILL_SP", "").strip().lower()
    if raw in _OFF:
        return "off"
    if raw == _COMM:
        return "comm"
    if raw in _STAGE1:
        return "stage1"
    raise RuntimeError(
        f"prefill_sp: DSV41_PREFILL_SP={raw!r} is not one of "
        "(unset|0|off|false|comm|1|shard); refusing to boot -- remedy: "
        "unset the key (default off) or set it to a listed value "
        "(check the arm env / EXTRA_DOCKER_ENV spelling)"
    )


def _parse_exact():
    """DSV41_PREFILL_SP_EXACT=1 is the ONLY implemented stage1 form: the
    sharded section is bit-preserving (bf16, rows never split across ranks).
    Without it: WARNING + inert (fail-closed; the non-EXACT +20% community
    form allows different reduction/quantization shapes and is out of scope
    for this segment)."""
    raw = os.environ.get("DSV41_PREFILL_SP_EXACT", "").strip().lower()
    if raw in _ON:
        return True
    if raw in _OFF:
        return False
    raise RuntimeError(
        f"prefill_sp: DSV41_PREFILL_SP_EXACT={raw!r} is not a boolean "
        "(legal domain: unset|1|on|true|0|off|false); refusing to boot "
        "-- remedy: set it to 1 (bit-equal T61 form) or 0 (T62 shard "
        "form, needs the quality gates); check for stray quoting/whitespace"
    )


def _parse_fp8_keys():
    """DSV41_PREFILL_SP_FP8 / DSV41_PREFILL_SP_FP8_MOE as booleans; a
    non-boolean value refuses the boot (fail-closed, same law as _EXACT).
    What the booleans ARM is decided by the mode: the MoE face arms only
    under stage1+EXACT (see the module init below); the attention face is
    never armed on this tree."""
    out = {}
    for key in ("DSV41_PREFILL_SP_FP8", "DSV41_PREFILL_SP_FP8_MOE"):
        raw = os.environ.get(key, "").strip().lower()
        if raw in _OFF:
            out[key] = False
        elif raw in _ON:
            out[key] = True
        else:
            raise RuntimeError(
                f"prefill_sp: {key}={raw!r} is not a boolean (legal "
                "domain: unset|1|on|true|0|off|false); refusing to boot "
                "-- remedy: unset the key (default off) or fix the value"
            )
    return out["DSV41_PREFILL_SP_FP8"], out["DSV41_PREFILL_SP_FP8_MOE"]


def _parse_min_rows():
    raw = os.environ.get("DSV41_PREFILL_SP_MIN_ROWS", "").strip() or "2048"
    try:
        rows = int(raw)
    except ValueError:
        raise RuntimeError(
            f"prefill_sp: DSV41_PREFILL_SP_MIN_ROWS={raw!r} is not an "
            "integer (legal domain: decimal integer >= 1; community "
            "default 2048); refusing to boot -- remedy: unset the key or "
            "set an integer"
        ) from None
    if rows < 1:
        raise RuntimeError(
            f"prefill_sp: DSV41_PREFILL_SP_MIN_ROWS={rows} < 1 (legal "
            "domain: >= 1; community default 2048); refusing to boot -- "
            "remedy: unset the key or set a positive integer"
        )
    if rows < 2048:
        logger.warning(
            "prefill_sp: DSV41_PREFILL_SP_MIN_ROWS=%s below the community default "
            "2048 (same key as moe_b12x_next.py:111)", rows,
        )
    return rows


def _parse_deepcarry():
    """DSV41_PREFILL_SP_DEEPCARRY: boolean, DEFAULT ON (unset = on) -- the
    deep-carry layer-loop replacement is the default stage1 form (T60/T61/
    T62); =0|off|false rolls back to the reanchor per-site stage1 form
    (which stays EXACT-only, fail-closed). A non-boolean value refuses the
    boot (fail-closed, same law as _EXACT)."""
    raw = os.environ.get("DSV41_PREFILL_SP_DEEPCARRY", "").strip().lower()
    if raw in ("",) + _ON:
        return True
    if raw in _OFF:
        return False
    raise RuntimeError(
        f"prefill_sp: DSV41_PREFILL_SP_DEEPCARRY={raw!r} is not a boolean "
        "(legal domain: unset|1|on|true|0|off|false; unset = ON); "
        "refusing to boot -- remedy: unset the key (deep-carry default) "
        "or set 0 (legacy per-site EXACT-only form)"
    )


def _parse_boundary():
    """DSV41_PREFILL_SP_BOUNDARY (T62-2, the boundary A/B key; T62-F1
    verdict §三): the boundary-reduction FORM selector for the shard form.
      unset (missing key) = fail-closed follow the CURRENT form -- the
        boundary rides EXACT exactly as before the key existed (EXACT=1
        -> AR+slice, the T61 bit-equal law; shard form [EXACT off] ->
        RS, the T62-F1 fired form: byte-reproducible, F1 comparability
        preserved);
      "ar_slice" = under the shard form FORCE the transparent AR+slice
        boundary (stock collective + rank-row slice -- the T61-proven
        reduction, AR vs RS wire差 ~31MB/chunk≈0.1ms 级); the key owns
        ONLY the boundary-reduction leaves (_dc_boundary / the attn/moe/
        engram boundary dispatch): every row-band site (hcpostc and the
        rest) KEEPS the shard-decomposed route unchanged;
      anything else refuses the boot (fail-closed, same law as _EXACT)."""
    raw = os.environ.get("DSV41_PREFILL_SP_BOUNDARY", "").strip().lower()
    if raw in ("",):
        return ""
    if raw in ("ar_slice",):
        return "ar_slice"
    raise RuntimeError(
        f"prefill_sp: DSV41_PREFILL_SP_BOUNDARY={raw!r} is not one of "
        "(unset|ar_slice); refusing to boot -- remedy: unset the key "
        "(fail-closed current form: boundary rides EXACT) or set "
        "ar_slice (T62b transparent AR+slice boundary; shard form only)"
    )


def _parse_wkv():
    """DSV41_PREFILL_SP_WKV: shard (DEFAULT, unset = shard) | full -- the
    mia key (MIA-PREFILL21 §1a `_WKV`, mia main value family). shard = the
    v1 engram seam: lookup full-row with its AR boundary-reduced, the wkv
    GEMM + gate on 1/world rows (per-(layer, M) bit self-checked, permanent
    island fallback). full = NEVER run the wkv GEMM on the shard: every
    engram layer takes the v0 gather-island form (AG R -> stock full-row
    engram -> row slice). Any other value refuses the boot (fail-closed)."""
    raw = os.environ.get("DSV41_PREFILL_SP_WKV", "").strip().lower()
    if raw in ("", "shard", "1", "on", "true"):
        return "shard"
    if raw in ("full",):
        return "full"
    raise RuntimeError(
        f"prefill_sp: DSV41_PREFILL_SP_WKV={raw!r} is not one of "
        "(unset|shard|full); refusing to boot -- remedy: unset the key "
        "(default shard: v1 mia seam with per-(layer,M) bit self-check) "
        "or set full (gather-island escape form)"
    )


def _parse_tap_layers():
    """T61 day-9 (R8 layer-verdict fire, R7 verdict §四): the tap layer
    list, env-driven -- DSV41_PREFILL_SP_TAP_LAYERS="0,1,2,...,10" = dump
    a face AFTER each listed region layer. unset (None) = the R7 two-face
    form (after start_layer -> tag F1, after the layer-order midpoint ->
    tag F2) -- byte-for-byte the day-8 behavior. A listed layer equal to
    start_layer keeps the F1 tag (FULL volume, R7 caliber); equal to the
    midpoint keeps F2 (FULL volume); every OTHER listed layer becomes a
    dense tap "L<layer>" tag that dumps FIRST-BLOCKS ONLY (the pure-seed
    law: a first block carries no cross-chunk KV pollution). Non-integer
    or negative entries REFUSE THE BOOT (fail-closed, same law as
    _MIN_ROWS); range validity ([start, late)) is checked against the
    model at window time with a LOUD drop banner (a dropped tap surfaces
    as an absent face in the harness = visible delta, never silent)."""
    raw = os.environ.get("DSV41_PREFILL_SP_TAP_LAYERS", "").strip()
    if not raw:
        return None
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            layer = int(part)
        except ValueError:
            raise RuntimeError(
                f"prefill_sp: DSV41_PREFILL_SP_TAP_LAYERS entry {part!r} is "
                "not an integer; refusing to boot"
            ) from None
        if layer < 0:
            raise RuntimeError(
                f"prefill_sp: DSV41_PREFILL_SP_TAP_LAYERS entry {layer} is "
                "negative; refusing to boot"
            )
        if layer not in out:
            out.append(layer)
    if not out:
        return None
    return tuple(out)


def _parse_tail_gather():
    """W5 (COMMUNITY-GAP-VERDICT-20261010 §2.4): DSV41_PREFILL_SP_TAIL_
    GATHER as a STRICT boolean (unset|0|off|false|1|on|true); any other
    value refuses the boot (fail-closed, the _EXACT family law). What the
    boolean arms: the deep-carry region-exit gather (use_tail AND skip
    branches) carries ONLY the tail rows (owner-local direct gather,
    world*n_tail rows instead of M rows -- ~15x less wire at M=4096/
    n_tail~128) instead of the full-row AG + tail.rows slice. The no-tail
    branch (a legal full-row consumer) NEVER changes. The degenerate gate
    (world*n_tail >= rows) falls back to the full-row AG per chunk. The
    key is INDEPENDENT of DSV41_PREFILL_SP_FP8 so a W5 boot can
    differential the two faces (stage2 key + exit key as separate arms)."""
    raw = os.environ.get("DSV41_PREFILL_SP_TAIL_GATHER", "").strip().lower()
    if raw in _ON:
        return True
    if raw in _OFF:
        return False
    raise RuntimeError(
        f"prefill_sp: DSV41_PREFILL_SP_TAIL_GATHER={raw!r} is not a "
        "boolean (legal domain: unset|1|on|true|0|off|false); refusing to "
        "boot -- remedy: unset the key (default off, full-row exit AG) or "
        "set it to a listed value; check the arm env / EXTRA_DOCKER_ENV "
        "spelling"
    )


def _parse_debug():
    """DSV41_PREFILL_SP_DEBUG: unset | compare | dump[:DIR] (day-2, the
    EXACT-gate faces, EXACT-GATE-HARNESS.md §2.2/§2.3).
      compare = Layer-2: beside every forced-kernel (logical-rows
        divergence band) path, run the stock full-rows method on AG'd
        operands and torch.equal the rank's sliced rows -- the AG is paid
        ONLY in this mode (定位面).
      dump[:DIR] = Layer-1 capture: per-chunk torch.save at the segment-B
        tail and the loop exit (the harness pairs stock vs deepcarry boots
        by (rank, chunk, tag)); DIR defaults to the process cwd.
    Any other value: tolerated with one WARNING and ignored (the family's
    DEBUG-key law; never fatal, never silently active)."""
    raw = os.environ.get("DSV41_PREFILL_SP_DEBUG", "").strip()
    low = raw.lower()
    if low in ("", "compare"):
        return low, None
    if low == "dump":
        return "dump", os.getcwd()
    if low.startswith("dump:"):
        return "dump", (raw[5:].strip() or os.getcwd())
    if raw:
        logger.warning(
            "prefill_sp: DSV41_PREFILL_SP_DEBUG=%r is not one of "
            "(unset|compare|dump[:DIR]); tolerated and ignored", raw,
        )
    return "", None


MODE = _parse_mode()
MIN_ROWS = _parse_min_rows()
EXACT = _parse_exact()
FP8_ATTN, FP8_MOE = _parse_fp8_keys()
DEEPCARRY = _parse_deepcarry()
WKV = _parse_wkv()
BOUNDARY = _parse_boundary()
TAP_LAYERS = _parse_tap_layers()
TAIL_GATHER = _parse_tail_gather()
_DEBUG_MODE, DEBUG_DUMP_DIR = _parse_debug()
DEBUG_COMPARE = _DEBUG_MODE == "compare"
if MODE == "stage1":
    if DEEPCARRY:
        # T60 deep-carry form: EXACT selects the boundary reduction --
        #   _EXACT=1  -> AR + keep rank's 1/4 rows (bit-equal, T61 form);
        #   _EXACT=0  -> reduce-scatter (the T62 production shard form;
        #                NOT bit-equal: reduction order changes; qeval/
        #                needle 背书 per mia production precedent);
        #   T62-2 (T62-F1 §三 boundary A/B): _BOUNDARY=ar_slice flips
        #                ONLY the boundary leaves back to the transparent
        #                AR+slice reduction (the row-band sites stay
        #                shard-decomposed: still NOT bit-equal overall).
        if not EXACT and BOUNDARY == "ar_slice":
            logger.warning(
                "prefill_sp: DEEPCARRY armed WITHOUT DSV41_PREFILL_SP_EXACT=1 "
                "and DSV41_PREFILL_SP_BOUNDARY=ar_slice -- the boundary "
                "reduction is the TRANSPARENT AR+slice form (T62-2a fire: "
                "stock collective + rank-row slice, the T61-proven "
                "reduction); the row-band sites KEEP the shard-decomposed "
                "route (mode=shard-decomposed unchanged): NOT bit-equal "
                "with stock outside the boundary leaves; quality gates "
                "(qeval + needle) before any performance verdict"
            )
        elif not EXACT:
            logger.warning(
                "prefill_sp: DEEPCARRY armed WITHOUT DSV41_PREFILL_SP_EXACT=1 "
                "-- the boundary reduction is reduce-scatter (T62 production "
                "shard form): NOT bit-equal with stock (reduction order), "
                "needs the T62 quality gates (qeval + needle) before any "
                "performance verdict; EXACT=1 is the bit-equal T61 fallback"
            )
        # F10 (PROD-RS-WHITEBOX-QA-20261003, feedback-only observability):
        # EXACT=1 + a set BOUNDARY key is a REDUNDANT combination -- the key
        # owns only the shard form's boundary (EXACT already forces AR+slice)
        # -- and that inertness was previously silent. One census-visible
        # line so an A/B readout never wonders which mechanism owned the
        # boundary on this boot (pure observation; zero form change).
        if EXACT and BOUNDARY:
            logger.warning(
                "prefill_sp: DSV41_PREFILL_SP_EXACT=1 with "
                f"DSV41_PREFILL_SP_BOUNDARY={BOUNDARY!r} -- the BOUNDARY key "
                "is INERT under EXACT (EXACT already forces the AR+slice "
                "boundary); recorded for census clarity, no form change, no "
                "action needed (unset the key to silence this line)"
            )
    elif not EXACT:
        logger.warning(
            "prefill_sp: DSV41_PREFILL_SP is a stage1 (bf16 row-split) value "
            "but DSV41_PREFILL_SP_EXACT is not 1; the non-EXACT form is NOT "
            "implemented -- adapter stays inert (door closed, zero drift)"
        )
if FP8_MOE and MODE == "stage1" and EXACT:
    # W5 DEPRECATION (COMMUNITY-GAP-VERDICT-20261010 §2.3 step 1): the
    # torch-replica stage2 quantizer below (mxfp8_quantize & friends,
    # :1237-1350 of the 0497e566 base) is DEPRECATED -- its deep
    # subnormal / saturation boundary diverges from the flashinfer
    # reference bytes (subnormal mant<=0x400000 no-carry / 0xFE saturation
    # keeping 254), and the verdict's six-step method mandates the
    # CONSUMER'S OWN quantizer (flashinfer_mxfp8_quantize, the new
    # _dc_mxfp8_quantize in the W5 section below) on every production
    # quantization face. The functions stay IN TREE (structure tests and
    # the A23-beta C-2 comparator fix lineage still reference them) but
    # NO production path may call them; the MoE-face fp8 gather needs a
    # registered owner (register_section(..., fp8=True)) that does not
    # exist, so this key remains effectively unowned -- kept parsing-only
    # for boot-shape compatibility of legacy arm envs.
    logger.warning(
        "prefill_sp: DSV41_PREFILL_SP_FP8_MOE=1 -- DEPRECATED (W5, gap-"
        "verdict §2.3): the torch-replica MXFP8 quantizer is retired from "
        "production paths (flashinfer-boundary byte divergence); no "
        "fp8-registered section exists, the MoE gather stays bf16; the "
        "production MXFP8 face is now the deep-carry attention AG-in "
        "(DSV41_PREFILL_SP_FP8=1)"
    )
elif FP8_MOE:
    logger.warning(
        "prefill_sp: DSV41_PREFILL_SP_FP8_MOE=1 but DSV41_PREFILL_SP is not "
        "a stage1 (1|shard)+EXACT value; stage2 rides the stage1 row split "
        "(same grouping moe_b12x_next.py:109-110 demands of PREQUANT_WARM) "
        "-- key tolerated, gather stays bf16 (fail-closed)"
    )
if FP8_ATTN:
    # W5 (COMMUNITY-GAP-VERDICT-20261010 §2.3): the attention-input face is
    # NOW IMPLEMENTED -- the 2026-10-02 "NOT implemented" verdict is
    # SUPERSEDED by the gap-verdict's end-to-end absorption-chain audit
    # (no breakpoint): the engine's own x_quant formal parameter
    # (deepseek_v4.py:1417/:1431: x_linear = x_quant if x_quant is not None
    # else x -> wqkv_a(x_linear)) consumes a Mxfp8SwizzledInput tuple
    # constructed sender-side with the CONSUMER'S OWN quantizer
    # (flashinfer_mxfp8_quantize, is_sf_swizzled_layout=True,
    # alignment=32 -- fp8.py:1205-1213 unpacks, the b12x cutlass wrapper
    # passes input_scale through), and the receiver gate
    # accepts_mxfp8_swizzled_input (:1225-1253) evaluates TRUE on the
    # production FLASHINFER_CUTLASS + block_fp8_mxfp8_ready form. The old
    # failure reasons (aiter gfx95 fused_rms / decode-tile mhc paths /
    # the mhc fused AR) named OTHER quantization seams this face never
    # touches. Bit law: wqkv_a(pre-quantized bytes) == wqkv_a(bf16) -- the
    # engine quantizes the bf16 input with the SAME function in-kernel --
    # proven per size per boot by the first-chunk triple check
    # (_dc_fp8_input), permanent bf16 fallback on any mismatch (A23-beta
    # proved the fallback safe).
    if MODE == "stage1" and DEEPCARRY:
        logger.warning(
            "prefill_sp: DSV41_PREFILL_SP_FP8=1 -- W5 stage2 MXFP8 AG-in "
            "armed (deep-carry attention AG-in carries E4M3 bytes + ue8m0 "
            "scales, ~1/1.94 the bf16 bytes); eligible layers only (no "
            "compressor/indexer + fuse_wqa_wkv + accepts_mxfp8_swizzled_"
            "input -- the kv/index source layers 2/8/14/20 stay bf16, 17/21 "
            "region layers on the production form); first chunk per size "
            "runs the triple bit check, any mismatch = PERMANENT bf16 for "
            "that size (fail-safe)"
        )
    else:
        logger.warning(
            "prefill_sp: DSV41_PREFILL_SP_FP8=1 but DSV41_PREFILL_SP is "
            "not a deep-carry stage1 form (1|shard + the DEEPCARRY "
            "default) -- the attention-input face rides the deep-carry "
            "AG-in seam only; key tolerated, the attention face stays "
            "bf16 (fail-closed)"
        )
if TAIL_GATHER and not (MODE == "stage1" and DEEPCARRY):
    logger.warning(
        "prefill_sp: DSV41_PREFILL_SP_TAIL_GATHER=1 but DSV41_PREFILL_SP "
        "is not a deep-carry stage1 form -- the exit tail-row direct "
        "gather rides the deep-carry region-exit seams only; key "
        "tolerated, the exit keeps the full-row AG (fail-closed)"
    )

# Stage1 arms only in EXACT form; comm always arms; everything else inert.
# DEEPCARRY relaxes the EXACT-only law for stage1: under deep-carry the
# boundary form is EXACT (AR+slice) when _EXACT=1, ar_slice (AR+slice, the
# T62-2 boundary key) when _BOUNDARY=ar_slice, and RS (T62 shard) otherwise
# -- the legacy per-site form (_DEEPCARRY=0) stays EXACT-only.
def _armed() -> bool:
    if MODE == "comm":
        return True
    return MODE == "stage1" and (EXACT or DEEPCARRY)


def _deepcarry_armed() -> bool:
    """The layer-loop replacement engages: stage1 form + DEEPCARRY (default
    on). Legacy per-site stage1 (_DEEPCARRY=0) keeps the reanchor path."""
    return MODE == "stage1" and DEEPCARRY


def _boundary_ar_slice() -> bool:
    """The boundary reduction runs the AR+slice (transparent) form: EXACT
    (the T61 bit-equal law, plan["exact"]) or the T62-2 boundary key. A
    missing key on the shard form keeps RS -- the T62-F1 fired form
    (fail-closed along the current form, T62-F1 §三)."""
    return EXACT or BOUNDARY == "ar_slice"


def _boundary_form(exact, key_ar_slice, long_form=False):
    """Three-way readable boundary-reduction form (the T62-2 banner law):
    the T61 EXACT form / the T62-2 boundary-key form (ar_slice) / the T62
    production RS form. long_form is the installed-banner spelling
    (AR+slice(EXACT) / RS(T62)); the engaged/ENTER/summary banners use
    the short spelling and keep the pre-T62-2 bytes on the two legacy
    forms (F1 reproducibility)."""
    if exact:
        return "AR+slice(EXACT)" if long_form else "AR+slice"
    if key_ar_slice:
        return "AR+slice(T62b)"
    return "RS(T62)" if long_form else "RS"


def _fp8_armed() -> bool:
    """The fp8 gather will actually engage: key on AND stage1+EXACT (the
    same grouping moe_b12x_next.py:109-110 demands of PREQUANT_WARM).
    W5 DEPRECATION (gap-verdict §2.3): the replica-based MoE-face gather
    is retired -- this now returns False unconditionally so NO code path
    can route a section through the deprecated torch-replica quantizer
    (mxfp8_quantize, :1237-1350 of the 0497e566 base) even if a legacy
    tree registers an fp8 section; the production MXFP8 face is the
    deep-carry attention AG-in (_dc_fp8_input). Fail-safe direction: the
    MoE gather falls back to bf16 (the always-stock-equivalent route)."""
    return False

# Registered per-site row-wise sections (stage1). Missing site -> identity,
# i.e. the byte-neutral P0 swap (constructive safety: an unowned section is
# refused, never re-implemented blind). _SECTIONS_FP8: sites whose AG payload
# may go MXFP8 (stage2) -- the site owner has proven the gathered tensor
# feeds the MXFP8-consuming face; every other site keeps the bf16 gather.
_SECTIONS = {}
_SECTIONS_FP8 = set()


def register_section(site, fn, fp8=False):
    """Bind a site's row-wise section for stage1: fn(shard)->shard, applied
    between the reduce-scatter and the all-gather. Contract: per-row pure
    (never mixes rows), row-count invariant (sp_logical_rows law: no
    x.shape[0]-gated kernel selection -- the first-call dual-check enforces
    this at runtime with a permanent fallback), tolerant of zero pad rows
    (isolated per row, sliced at AG). The section REPLACES work the caller
    owns and has suppressed from the engine flow -- the engine must not also
    run it on the returned full tensor (double-apply). Must be called at
    install time, before the first eligible forward. Sites without a
    registered section refuse the self-built path and run identity
    (byte-neutral P0 semantics; constructive safety).

    fp8=True (stage2, requires DSV41_PREFILL_SP_FP8_MOE=1 at boot) moves
    this site's GATHER to MXFP8 bytes: the section output rows are
    quantized on the shard (E4M3 + UE8M0 per-32 power-of-two scale, b12x
    front-end format), all-gathered as fp8 bytes (wire 1/1.94 of bf16),
    dequantized to bf16 at the destination. The registrant owns the proof
    that the gathered tensor feeds the MXFP8-consuming face (the MoE
    input): the consumer re-quantizes to the same grid, so its inputs keep
    their values, while any NON-quantizing consumer of the same tensor
    (router / residual stream) sees the roundtripped bf16 -- a QA-gated
    numerics change that must be a deliberate arm decision, never a
    silent default. Direct delivery into moe_b12x_next.prequant_views(m)
    (zero dequant) is sp_section_fp8_views, for the layer-carry card."""
    _SECTIONS[site] = fn
    if fp8:
        _SECTIONS_FP8.add(site)
    else:
        _SECTIONS_FP8.discard(site)


# Runtime state. "active" is set only inside an eligible prefill bracket
# (single-threaded engine forward; l2_prefetch uses the same module-global
# law). "verified"/"failed" key the per-(site, dtype, bucket) dual checks.
# Layer-carry state (stage1 engine sections): "frames" is the
# forward_hc_pre_from_prev frame stack, "carry" the pending sublayer carry
# (consumable once, by the matching AR leaf), "stash" the section outputs
# awaiting the engine's identity-matched consumption.
_state = {
    "active": False,
    "installed": [],
    "verified": set(),
    "failed": set(),
    "engaged_logged": set(),
    "frames": [],
    "carry": None,
    "stash": None,
    "carry_sites": [],
    "carry_dropped": 0,
}

# DEEPCARRY runtime context (single-slot module-global, same law as _state;
# TBO is refused by the plan builder so no interleaved micro-batches):
#   plan    -- the active region plan dict, or None (hooks inert)
#   inner   -- True while a gathered full-rows core (attention / MoE) runs:
#              the boundary AR leaf must reduce, the AG-in wrappers must
#              not re-enter (mia's _Ctx.inner)
#   sublayer-- "attn" / "moe" / "engram": which core the boundary AR
#              belongs to (the engram lookup AR fires with inner=False --
#              it is the ONLY boundary outside a gathered core)
#   refusals-- reason -> count of plan refusals (T62 min_rows trap: every
#              refusal is LOGGED, never a silent stock chunk)
#   chunk_idx-- per-process deep-carry chunk counter (DEBUG=dump pairing key)
#   compare_mismatches -- name -> count of DEBUG=compare mismatches (Layer-2)
#   obs_faces -- day-8 stock-observer face window: while an eligible chunk's
#              stock loop runs, {"f1","f2","rank","M","E","world"} so the
#              layer-face observer can dump F1/F2 rank-slices at exactly the
#              armed side's face iterations; None outside the window (the
#              window law: a layer forward outside the window NEVER dumps)
_dc_ctx = {"plan": None, "inner": False, "sublayer": None, "refusals": {},
           "engaged_logged": False, "enter_logged": False,
           "engram_logged": False, "skip_logged": False, "chunk_idx": 0,
           "compare_mismatches": {}, "obs_faces": None}

# Engram v1 wkv self-check state (mia :586-606 law): the (layer, M) keys
# that passed / permanently failed the shard-wkv bit check. A failure flips
# that (layer, M) to the gather-island form FOREVER (never re-tried), the
# direction mia chose: fail-safe = the full-row path.
_DC_WKV_CHECKED = set()
_DC_WKV_FAILED = set()


def _dc_refusals_fmt() -> str:
    """census-readable refusal table (day-2 #5): reason:count, sorted."""
    if not _dc_ctx["refusals"]:
        return "none"
    return ",".join(
        f"{k}:{v}" for k, v in sorted(_dc_ctx["refusals"].items()))


def summary() -> str:
    sections = ",".join(sorted(_SECTIONS)) or "identity"
    fp8_sites = ",".join(sorted(_SECTIONS_FP8)) or "none"
    if _deepcarry_armed():
        agin = (f" agin_fp8={FP8_ATTN and MODE == 'stage1'}"
                f"[_dc_fp8_input]"
                if FP8_ATTN else "")
        _fp8_on = [m for m, s in _FP8_M.items() if s and s[0]]
        _fp8_off = [m for m, s in _FP8_M.items() if s and not s[0]]
        if FP8_ATTN:
            agin += (f" fp8_sizes_on={_fp8_on or 'none'}"
                     f" fp8_sizes_bf16={_fp8_off or 'none'}")
        agin += f" tail_gather={TAIL_GATHER and MODE == 'stage1'}[_dc_tail_rows]"
        dc = (
            f" deepcarry={_deepcarry_armed()}[{_DEEPCARRY_TAG}]"
            f" boundary={_boundary_form(EXACT, BOUNDARY == 'ar_slice')}"
            f" engram=wkv:{WKV}[v1-mia]"
            f" wkv_checked={len(_DC_WKV_CHECKED)}"
            f" wkv_failed={len(_DC_WKV_FAILED) or 'none'}"
            f" refusals={_dc_refusals_fmt()}"
            f"{agin}"
        )
        if DEBUG_COMPARE:
            dc += f" compare_mismatches={_dc_ctx['compare_mismatches'] or 'none'}"
        if DEBUG_DUMP_DIR:
            dc += f" dump={DEBUG_DUMP_DIR}"
    else:
        dc = ""
    return (
        f"stage={MODE} gate={os.environ.get('DSV41_PREFILL_SP', '(unset)')} "
        f"exact={EXACT} armed={_armed()} min_rows={MIN_ROWS} "
        f"fp8_moe_armed={_fp8_armed()} (key={FP8_MOE}, DEPRECATED W5) "
        f"fp8_attn={FP8_ATTN}(W5 AG-in face) fp8_sites={fp8_sites} "
        f"tail_gather={TAIL_GATHER}(W5 exit face) "
        f"sections={sections}{dc} "
        f"carry_sites={'+'.join(_state['carry_sites']) or 'none'} "
        f"installed={'+'.join(_state['installed']) or '(none)'} "
        f"verified={len(_state['verified'])} failed={sorted(_state['failed']) or 0}"
    )


# C1 (REFDIFF-BUGHUNT-20261003, high-confidence latent-armed): the PUBLIC
# logical-row helper. The module docstring's EXACT premise (b) has always
# NAMED the community's sp_logical_rows() law; the co-installed hc_fused
# keys its row gates on this import (hc_fused.py:160-164
# `from prefill_sp import sp_logical_rows`) and every prefill_sp build so
# far (065d158b AND 6dae6ba6) EXPORTED NOTHING -- hc_fused's ImportError
# fallback (x.shape[0]) was permanently active, so a MIN_ROWS/key change
# that put E below hc_fused's own cut would silently disqualify the fused
# kernel on the SP boot only (A/B misread; ~2-3%/chunk perf drift with no
# census line). This export restores the knapcio-reference form
# (58f2321 :358-367): the row count a kernel gate must use for x is the
# FULL chunk row count M when x is this rank's shard of a sequence-
# parallel chunk, else x.shape[0]. Zero behavior difference at the
# deployed keys: hc_fused's cut is 512, our plans require M >= MIN_ROWS
# (2048 default) so E = M/4 >= 512 whenever a plan is live -- eligible(E)
# and eligible(M) are the same truth value, and outside a live plan this
# returns n (exactly the old fallback). The co-install REFUSAL that
# enforcement-side pairs with it lives in _check_hc_fused_coinstall.
def sp_logical_rows(x):
    """Row count a kernel gate must use for `x`: the full chunk row count
    M when `x` is this rank's shard of a sequence-parallel chunk, else
    x.shape[0]. Cheap and safe to call when the adapter is off."""
    n = x.shape[0]
    p = _dc_ctx.get("plan")
    if p is None or _dc_ctx.get("inner") or n != p["E"]:
        return n
    return p["M"]


def _check_hc_fused_coinstall():
    """C1 enforcement half (the knapcio :505-513 co-install law, our
    tree's form): with deep-carry installed, an armed DSV41_HC_FUSED boot
    MUST resolve hc_fused's logical-rows helper to THIS module's export.
    hc_fused imports it at its own module exec (sitecustomize installs it
    on the mhc module's exec, which precedes the deepseek_v4 exec that
    installs us), so by the time we run, an armed boot either already
    holds the binding or the fallback is live -- the identity check
    cannot miss. Import failure or fallback-active both REFUSE the boot
    (fail-loud: the two key-value drift classes that used to be silent
    become boot-stopping with the key name, current value, reason and
    remedy spelled out)."""
    key = "DSV41_HC_FUSED"
    raw = os.environ.get(key, "0").strip()
    if raw in ("0", "", "off", "false"):
        return
    try:
        import hc_fused
    except Exception as exc:
        raise RuntimeError(
            f"prefill_sp: co-install law broken: key {key}={raw!r} "
            f"(legal domain: 0|off|false = disarmed, anything else = armed) "
            f"but importing hc_fused failed ({exc!r}); refusing to boot -- "
            "with deep-carry armed, hc_fused keys its row gates on "
            "prefill_sp.sp_logical_rows and a missing hc_fused leaves the "
            "key a DEAD ARM; remedy: deploy adapter/hc_fused.py "
            "(md5 59df1cc97a8dda2f6fb8377b728363e0) or unset "
            f"{key}") from None
    got = getattr(hc_fused, "_logical_rows", None)
    if got is not sp_logical_rows:
        raise RuntimeError(
            f"prefill_sp: co-install law broken: key {key}={raw!r} but "
            "hc_fused resolved its FALLBACK _logical_rows "
            "(x.shape[0]) instead of prefill_sp.sp_logical_rows -- the "
            "shard-vs-stock kernel-gate drift the community law refuses "
            "(a MIN_ROWS change would silently disqualify the fused "
            "kernel on SP boots only); refusing to boot; remedy: "
            "redeploy the adapter PAIR (prefill_sp.py + hc_fused.py) as "
            "one unit -- a stale prefill_sp without the export, or an "
            "hc_fused imported against one, is not a bootable "
            "combination") from None


# ---------------------------------------------------------------- helpers

# one-time log markers for the would-be-silent fallback readers (用户令④;
# the PROD-RS-WHITEBOX-QA §3 "no-observation-plane" census rows).
_STATE_ONCE = {}


def _device_ok(tensor) -> bool:
    """Engine path: CUDA only. (Indirection exists for the CPU unit tests.)"""
    return tensor.device.type == "cuda"


def _capturing() -> bool:
    try:
        return torch.cuda.is_available() and torch.cuda.is_current_stream_capturing()
    except Exception as exc:
        # 用户令④ (no-observation-plane census, PROD-RS-WHITEBOX-QA §3 row
        # 3): the introspection failure itself was silent; treating it as
        # "not capturing" is the fail-open direction whose worst case is a
        # LOUD NCCL error, but the misread deserves its one census line.
        if not _STATE_ONCE.get("capturing_unreadable"):
            _STATE_ONCE["capturing_unreadable"] = True
            logger.warning(
                "DSV41 prefill SP: torch capture introspection unreadable "
                f"(%r) -- read as NOT capturing (fail-open; a capture in "
                "flight would surface as a loud NCCL/collective error, "
                "first failure only is logged)",
                exc,
            )
        return False


def _bucket(tensor) -> int:
    nbytes = tensor.numel() * tensor.element_size()
    if nbytes < _BUCKET_BYTES[0]:
        return 0
    if nbytes < _BUCKET_BYTES[1]:
        return 1
    return 2


def _call_eligible(tensor, group) -> bool:
    """门内查形: per-AR-call shape/group checks inside the armed bracket."""
    return (
        group.world_size >= 2
        and tensor.dim() >= 1
        and tensor.shape[0] >= 1
        and tensor.is_contiguous()
        and tensor.dtype in _DTYPES
        and _device_ok(tensor)
        and not _capturing()
    )


def rs_ag_all_reduce(group, input_):
    """reduce-scatter + all-gather on `group`, replacing all-reduce.

    Byte-neutral by ring-order equivalence (see module docstring); rows not
    divisible by world are zero-padded along dim0 -- pad rows are separate
    elements, never mixed into real rows, so every real element keeps its
    rank-order partial sum and the pad is sliced off before returning.
    Stock GroupCoordinator.all_reduce mutates its input in place and returns
    it; when no padding is needed the all-gather writes into input_ itself,
    preserving that contract exactly.
    """
    world = group.world_size
    rows = input_.shape[0]
    pad = (-rows) % world
    if pad:
        x = torch.cat(
            [input_, input_.new_zeros((pad,) + tuple(input_.shape[1:]))], dim=0
        )
        out = torch.empty_like(x)
    else:
        x = input_
        out = input_
    shard = x.new_empty((x.shape[0] // world,) + tuple(x.shape[1:]))
    group.reduce_scatter_tensor(shard, x)
    group.all_gather_into_tensor(out, shard)
    return out[:rows] if pad else out


# ------------------------------------------------- stage1 row-split core
#
# Row split = contiguous chunks, rank r owns rows [r*E, (r+1)*E) clipped to
# the real row count, E = ceil(rows/world); the group's reduce-scatter chunks
# zero-padded inputs to exactly E*world rows, so the shard of rank r IS the
# r-th RS output chunk -- no row is ever split across ranks, and assembly is
# plain concatenation. This layout is also the consumer contract: the shard
# is the token-major [E, K] row block moe_b12x_next.prequant_views() exposes
# (stage2's MXFP8 gather destination), and the AG output is the plain
# full-rows bf16 [rows, K] the MoE consumes in stage1.


def shard_extent(rows, world) -> int:
    """Per-rank padded row count E (rows are zero-padded to E*world)."""
    return -(-rows // world)


def shard_bounds(rows, world, rank):
    """(start, end) of rank's REAL rows inside the full row layout."""
    start = rank * shard_extent(rows, world)
    return start, min(rows, start + shard_extent(rows, world))


def _padded_chunk(input_, world, rank):
    """Zero-pad input_ along dim0 to E*world and return rank r's padded view
    row range (the exact slice reduce_scatter_tensor will hand back)."""
    rows = input_.shape[0]
    extent = shard_extent(rows, world)
    pad = extent * world - rows
    if pad:
        x = torch.cat(
            [input_, input_.new_zeros((pad,) + tuple(input_.shape[1:]))], dim=0
        )
    else:
        x = input_
    lo, hi = rank * extent, (rank + 1) * extent
    return x, lo, hi


def rs_shard(group, input_):
    """Reduce-scatter a rank-local partial to THIS rank's shard: the padded
    r-th chunk of the rank-order sum, [E, ...] (may carry zero pad rows).
    Same collective inputs as P0's rs_ag_all_reduce (the verified seam)."""
    world = group.world_size
    x, lo, hi = _padded_chunk(input_, world, group.rank_in_group)
    shard = x.new_empty((x.shape[0] // world,) + tuple(x.shape[1:]))
    group.reduce_scatter_tensor(shard, x)
    return shard


def ag_rows(group, shard, rows):
    """All-gather the per-rank shards back to the full [rows, ...] tensor:
    plain concatenation in rank order; zero pad rows sliced off."""
    world = group.world_size
    out = shard.new_empty((shard.shape[0] * world,) + tuple(shard.shape[1:]))
    group.all_gather_into_tensor(out, shard)
    return out[:rows] if out.shape[0] != rows else out


def sp_section(group, partial, rowwise):
    """Stage1 main path for one plain-AR site: RS -> rowwise on the shard ->
    AG. `rowwise(shard)->shard` is the site's registered section (identity
    when unregistered = P0 comm semantics). Returns the full-rows tensor,
    bitwise stock when the EXACT premises hold (module docstring (a)(b)(c));
    the caller (_verified_sp_section) dual-checks the first call per
    (site, dtype, bucket) and owns the permanent fallback."""
    rows = partial.shape[0]
    shard = rs_shard(group, partial)
    shard = rowwise(shard)
    return ag_rows(group, shard, rows)


# ------------------------------------------------- stage2 MXFP8 core
#
# The sending half of the fp8 gather: a bit-exact torch replica of b12x's
# in-kernel front-end quantizer, every constant and rounding rule lifted
# from the runtime tree (read-only, ~/migrate-assets/b12x/b12x_next):
#   * _lib/intrinsics.py:6209-6234 quantize_block_fp8_mx -- 32 float32
#     values -> E4M3 payload + one UE8M0 byte: scale = pow2_ceil(max_abs /
#     448); payload = cvt_e4m3(value * 2^(127-byte)); an all-zero block is
#     scale byte 0 + zero payload;
#   * :5589-5636 pow2_ceil_ue8m0 -- INTEGER mantissa-bump rounding (no
#     lg2.approx): mant!=0 -> (bits + 0x00800000) & 0x7F800000; the byte is
#     the exponent field (bits >> 23) & 0xFF;
#   * :5687-5719 ue8m0_to_output_scale -- the inverse 2^(127-byte), 0.0 at
#     byte 0;
#   * :223-265 pow2_ceil_ue8m0_torch / _ue8m0_output_scale_torch /
#     quant_dequant_mxfp8_torch -- the package's OWN torch replicas,
#     documented "Matches the in-kernel quantize_block_fp8_mx numerics
#     bit-for-bit ... UE8M0 ceil block scale, E4M3 RN-saturating payload"
#     (the offline byte-equality test runs against exactly these);
#   * moe/fused_moe/_impl.py:2147-2167 prequantized_input() + :10856-10867
#     -- the patched front-end specialization that SKIPS its own
#     quantization and reads the caller-written rows: "E4M3, [token, K],
#     row stride K" and "UE8M0 scales ([token, K/32])";
#   * dsv41/adapter/moe_b12x_next.py:573-587 prequant_views -- the
#     destination layout: pin[:m] (uint8 [m, K], token-major contiguous)
#     and psc[: m*K/32].view(m, K/32).
# The replica below is written from the device-side semantics (integer
# exponent arithmetic only -- no lg2, no transcendentals), so it is
# CPU/GPU-portable and the container unit test proves byte equality
# against the package's replicas on random + adversarial inputs.

_E4M3_MAX = 448.0  # FLOAT8_E4M3_MAX, intrinsics.py:42
_MX_BLOCK = 32     # MX_SF_VEC_SIZE, intrinsics.py:219 (UE8M0 scale block)


def mxfp8_quantize(x):
    """Quantize [m, K] float rows to MXFP8: per 32-element block, amax in
    float32 -> UE8M0 scale byte = pow2_ceil(amax / 448) (integer
    mantissa-bump, FlashInfer-bit-exact rule) -> E4M3 RN-saturating payload
    of value * 2^(127-byte). Returns (payload uint8 [m, K] token-major
    contiguous, scale uint8 [m, K/32]) -- field-for-field the bytes
    moe_b12x_next.prequant_views(m) exposes and b12x's patched front-end
    reads (packed_input / packed_input_scale). Row-pure by construction:
    blocks never cross rows and every block's scale is computed inside the
    block, so quantize(shard_r) == quantize(full) restricted to rank r's
    rows, bitwise (the load-bearing stage2 premise, dual-checked at
    runtime). All-zero rows -> zero payload + zero scale bytes.
    DEPRECATED (W5, gap-verdict §2.3): the deep-subnormal / saturation
    boundary of this torch replica DIVERGES from the flashinfer reference
    bytes (subnormal mant<=0x400000 no-carry / 0xFE saturation keeping
    254) -- production quantization now calls the consumer's own
    flashinfer_mxfp8_quantize (_dc_mxfp8_quantize below). This function
    stays in tree for the structure tests and the A23-beta C-2 comparator
    lineage ONLY; no production path may call it (_fp8_armed() is pinned
    False)."""
    if x.dim() != 2 or x.shape[-1] % _MX_BLOCK != 0:
        raise ValueError(
            f"mxfp8_quantize: need a 2D [m, K] tensor with K % 32 == 0, got "
            f"{tuple(x.shape)}"
        )
    m, k = x.shape
    blocked = x.to(torch.float32).reshape(m, k // _MX_BLOCK, _MX_BLOCK)
    block_max = blocked.abs().amax(dim=-1, keepdim=True)  # max_abs_32
    # pow2_ceil_ue8m0(max_abs * (1/448)): integer rounding, no fp divide.
    bits = (block_max * (1.0 / _E4M3_MAX)).contiguous().view(torch.int32)
    mant = bits & 0x007FFFFF
    bumped = torch.where(mant != 0, (bits + 0x00800000) & 0x7F800000, bits)
    scale_byte = ((bumped >> 23) & 0xFF).to(torch.uint8)
    # ue8m0_to_output_scale: 2^(127-byte); byte 0 decodes to a zero scale.
    inv_bits = ((254 - scale_byte.to(torch.int32)).clamp(min=0) << 23)\
        .view(torch.float32)
    inv = torch.where(scale_byte == 0, torch.zeros_like(inv_bits), inv_bits)
    payload = (blocked * inv).clamp(-_E4M3_MAX, _E4M3_MAX).to(
        torch.float8_e4m3fn)
    return (payload.reshape(m, k).contiguous().view(torch.uint8),
            scale_byte.reshape(m, k // _MX_BLOCK).contiguous())


def mxfp8_dequantize(payload, scale, dtype=torch.bfloat16):
    """Inverse of mxfp8_quantize: payload uint8 [m, K] + scale uint8
    [m, K/32] -> [m, K] `dtype`. value = e4m3(payload) * 2^(byte-127)
    (byte 0 -> +0.0); exact in bf16 (an E4M3 significand is 4 bits, the
    product with a power of two loses nothing), so the roundtrip is
    lossless in VALUE space and re-quantizing the result lands back on the
    same payload grid (MXFP8 roundtrip idempotence -- why the
    dequant-at-destination form keeps the b12x consumer's inputs at their
    stock-quantized values).
    DEPRECATED (W5, gap-verdict §2.3) with mxfp8_quantize -- see that
    docstring; in-tree for the A23-beta C-2 comparator lineage only. The
    idempotence sentence above is a VALUE-space statement and is NOT a
    byte-idempotence claim: at the 224 boundary ~7% of blocks FLIP bytes
    on a dequant-requantize roundtrip (two-element counterexample
    {230.0, 1.0}); no W5 face relies on byte idempotence (the banned
    narrative, gap-verdict §2.3 step 6)."""
    if payload.dim() != 2 or scale.shape != (payload.shape[0],
                                             payload.shape[1] // _MX_BLOCK):
        raise ValueError(
            f"mxfp8_dequantize: payload {tuple(payload.shape)} / scale "
            f"{tuple(scale.shape)} are not [m, K] + [m, K/32]"
        )
    m, k = payload.shape
    scale_bits = (scale.to(torch.int32) << 23).view(torch.float32)
    val = (payload.contiguous().view(torch.float8_e4m3fn).to(torch.float32)
           .reshape(m, k // _MX_BLOCK, _MX_BLOCK)
           * scale_bits.reshape(m, k // _MX_BLOCK, 1))
    return val.reshape(m, k).to(dtype)


def mxfp8_oracle(x, dtype=torch.bfloat16):
    """Reference quantize-dequantize of the FULL-rows tensor: what the
    fp8 gather must reproduce bitwise (the stage2 dual check). Equal to
    b12x's quant_dequant_mxfp8_torch(x) on equal inputs (container test).
    DEPRECATED (W5) with mxfp8_quantize -- see that docstring."""
    return mxfp8_dequantize(*mxfp8_quantize(x), dtype=dtype)


def sp_section_fp8(group, partial, rowwise):
    """Stage2 MoE-face main path: RS -> rowwise on the shard -> MXFP8-
    quantize the shard's rows -> all-gather the fp8 BYTES -> dequantize to
    the full-rows tensor. Wire bytes per rank: E*(K + K/32) payload+scale
    vs stage1's 2*E*K bf16 -> (1 + 1/32)/2 = 1/1.94 (design card §1.3).
    Row purity: quantize(shard_r) is bitwise quantize(full) on rank r's
    rows (blocks never cross rows), the AG is plain concatenation, pad
    rows are all-zero blocks (byte 0 + zero payload) sliced off with the
    row range -- row count is conserved exactly. The caller
    (_verified_sp_section) dual-checks the first call per bucket and owns
    the permanent bf16 fallback.
    DEPRECATED (W5, gap-verdict §2.3): unreachable by construction
    (_fp8_armed() pinned False -- the replica quantizer's byte divergence
    from flashinfer retires it from every production path). Kept in tree
    for the structure-test lineage; the production MXFP8 face is the
    attention AG-in (_dc_fp8_input)."""
    rows = partial.shape[0]
    shard = rowwise(rs_shard(group, partial))
    q, s = mxfp8_quantize(shard)
    q_full = ag_rows(group, q, rows)
    s_full = ag_rows(group, s, rows)
    return mxfp8_dequantize(q_full, s_full, dtype=partial.dtype)


def sp_section_fp8_views(group, partial, rowwise, q_dst, sf_dst):
    """Direct-delivery form (consumer half in place): the SAME sending
    half, but the gathered fp8 rows are copied into the consumer's prequant
    views and NO dequantize runs -- moe_b12x_next.prequant_views(m)
    exposes exactly (q uint8 [m, K], sf uint8 [m, K/32]) token-major, and
    the patched b12x front-end (moe_b12x_next.py:620-639 forward_prequant,
    marker enforced :952-963) reads packed_input / packed_input_scale
    directly. The dispatch must still carry hidden_states_pre_quant into
    the MoE call (engine channel: fused_moe_triton/layer.py:1520-1526 ->
    :1618) -- that wiring belongs to the layer-carry card, which is why
    this stays an API and not a leaf behavior. Returns (q_dst, sf_dst).
    Refuses (ValueError) on any shape mismatch: refuse, never mask.
    DEPRECATED (W5) with mxfp8_quantize -- see that docstring."""
    rows = partial.shape[0]
    kb = partial.shape[-1] // _MX_BLOCK
    if (q_dst.dim() != 2 or tuple(q_dst.shape) != (rows, partial.shape[-1])
            or sf_dst.shape != (rows, kb) or q_dst.dtype != torch.uint8
            or sf_dst.dtype != torch.uint8):
        raise ValueError(
            f"sp_section_fp8_views: destination views must be uint8 "
            f"[{rows}, {partial.shape[-1]}] + [{rows}, {kb}], got "
            f"{tuple(q_dst.shape)}/{q_dst.dtype} and "
            f"{tuple(sf_dst.shape)}/{sf_dst.dtype}"
        )
    shard = rowwise(rs_shard(group, partial))
    q, s = mxfp8_quantize(shard)
    q_dst.copy_(ag_rows(group, q, rows))
    sf_dst.copy_(ag_rows(group, s, rows))
    return q_dst, sf_dst


def _fp8_call_ok(tensor) -> bool:
    """Stage2 shape gate: the fp8 face needs 2D [rows, K] with K % 32 == 0
    (the b12x front-end's token-major layout). Anything else keeps the
    verified bf16 gather (fail-safe direction)."""
    return tensor.dim() == 2 and tensor.shape[-1] % _MX_BLOCK == 0


# ------------------------------------------------- W5 stage2 MXFP8 AG-in
#
# (COMMUNITY-GAP-VERDICT-20261010 §2.3, the six-step method; the community
# reference is knapcio adapter/prefill_sp.py:784-863 -- read-only.)
#
# The deep-carry attention AG-in today all-gathers the bf16 shard [E, 5120]
# to full rows [M, 5120] (M-2 in the A23B pre-study census: 10MiB in /
# 40MiB out per boundary at M=4096). This face instead quantizes the SHARD
# with the CONSUMER'S OWN quantizer -- flashinfer_mxfp8_quantize, the very
# function the wqkv_a blockscaled linear runs in-kernel (community :800-
# 802 production form; our deprecated torch replica above is retired
# precisely because its deep-subnormal / saturation boundary diverges from
# these bytes) -- all-gathers the E4M3 BYTES plus the LINEAR ue8m0 scale
# bytes, swizzles the GATHERED scales into FlashInfer's 128x4 tile layout,
# and hands the stock core a Mxfp8SwizzledInput tuple through the engine's
# own x_quant formal (deepseek_v4.py:1417/:1431). Wire bytes per boundary:
# E*(K + K/32) vs 2*E*K -> 1/1.94 of the bf16 face.
#
# ROW-LOCAL LAW (the constructive premise; step 2/3 of the six-step
# method): one ue8m0 scale covers a 32-COLUMN block INSIDE ONE ROW and is
# derived only from that block's own 32 values, so for any row-local
# quantizer Q:
#     Q(shard_r) == Q(full) restricted to rank r's rows, bitwise,
# i.e. quantize-then-gather == gather-then-quantize as an IDENTITY OF THE
# LAYOUT -- the AG concatenates whole rows and whole rows are exactly the
# quantizer's independence units. This is why the gather can carry u8
# payload + u8 scales (mxfp8_gather) instead of bf16. The law is
# dual-checked at runtime per size (check 1 below), never assumed.
#
# BANNED NARRATIVE (step 6): "dequantize-requantize byte idempotence" is
# mathematically FALSE at the 224 boundary (~7% of blocks flip; the
# two-element counterexample {230.0, 1.0}). NOTHING in this section
# relies on it: every comparison below runs the CONSUMER'S OWN quantizer
# on the gathered rows, never a quantize-dequantize roundtrip.
#
# Checked-not-assumed (step 4): the FIRST chunk of every size M runs the
# triple bit check; any mismatch -> that size is PERMANENTLY bf16 for the
# boot (fail-safe marker; the A23-beta line proved the bf16-gather
# fallback safe). The checks are immune to flashinfer device-kernel vs
# host-reference drift because both sides call the same device function.

_FP8_M = {}          # M -> (ok, sf_shape, sf_dtype), TP-agreed, permanent


def _dc_mxfp8_quantize(x, swizzled):
    """The consumer's own quantizer: flashinfer_mxfp8_quantize(x,
    is_sf_swizzled_layout=swizzled, alignment=32) -- the community
    production call (knapcio :800-802). Resolved LAZILY per call so a tree
    without the symbol falls back to bf16 through the probe below
    (fail-safe), never crashes a boot. Host structure tests swap this
    module global for a stand-in (the stand-in's bytes are NOT flashinfer
    bytes -- device-level byte equality is the in-window check 1)."""
    from sglang.srt.layers.quantization.fp8_utils import flashinfer_mxfp8_quantize
    return flashinfer_mxfp8_quantize(
        x, is_sf_swizzled_layout=swizzled, alignment=32)


_FP8_PROBE = {}       # "" -> boot-uniform availability of the import pair


def _dc_fp8_quantize_ok():
    """Boot-uniform probe (collective-order law): resolve the quantizer
    symbol + the Mxfp8SwizzledInput class ONCE per process, BEFORE any
    collective decision -- the adapter/engine filesystem is identical on
    every rank, so the probe result is uniform by construction and the
    fp8 branch can never interleave different AG sequences across ranks.
    An unavailable symbol = the face is off for the whole boot (loud,
    one line, fail-safe bf16)."""
    if not _FP8_PROBE:
        try:
            from sglang.srt.layers.quantization import fp8_utils as _fu
            from sglang.srt.layers.quantization.mxfp8_input import (
                Mxfp8SwizzledInput as _Cls,
            )
            ok = callable(getattr(_fu, "flashinfer_mxfp8_quantize", None)) \
                and _Cls is not None
        except Exception as exc:  # noqa: BLE001
            ok = False
            logger.warning(
                "DSV41 prefill SP deepcarry AG-in fp8: the consumer's own "
                "quantizer (flashinfer_mxfp8_quantize / Mxfp8SwizzledInput) "
                "is not resolvable on this tree (%s: %s) -- the attention "
                "AG-in stays bf16 for the whole boot (fail-safe)",
                type(exc).__name__, exc,
            )
        _FP8_PROBE[""] = ok
    return _FP8_PROBE[""]


def _dc_swizzle_128x4(s_lin):
    """[M, G] linear ue8m0 scale bytes -> FlashInfer's 128x4 tiled layout
    (community swizzle_128x4, knapcio :805-813): rows zero-padded to a
    multiple of 128; tile (m // 128, g // 4) in row-tile-major order,
    inside one tile the element order is [m % 32][(m % 128) // 32][g % 4].
    Pure index permutation of uint8 bytes -- value-safe by construction
    (the padded rows are ZERO bytes; the consumer's kernel addresses the
    same layout it would have produced itself)."""
    m, g = s_lin.shape
    assert g % 4 == 0
    mt = (m + 127) // 128
    if mt * 128 != m:
        s_lin = torch.cat([s_lin, s_lin.new_zeros((mt * 128 - m, g))])
    return (s_lin.view(mt, 4, 32, g // 4, 4)
            .permute(0, 3, 2, 1, 4).contiguous().view(-1))


def _dc_mxfp8_input_cls():
    """Mxfp8SwizzledInput (sglang.srt.layers.quantization.mxfp8_input):
    the NamedTuple(data E4M3 bytes, scales ue8m0 128x4-swizzled) the
    engine's x_quant formal carries to the blockscaled linear."""
    from sglang.srt.layers.quantization.mxfp8_input import Mxfp8SwizzledInput
    return Mxfp8SwizzledInput


def _dc_mxfp8_shard(x):
    """bf16 [S, K] shard -> (E4M3 payload bytes [S, K] uint8, LINEAR ue8m0
    scales [S, K/32] uint8, fp8 dtype): the sending half. The scales are
    requested in LINEAR layout (is_sf_swizzled_layout=False) because the
    gather CONCATENATES rows while the 128x4 tile is a whole-tensor
    layout (one tile spans 128 consecutive rows) -- the swizzle can only
    be applied AFTER the gather (step 3). flashinfer's linear scale
    output may carry alignment padding; slice to exactly S*(K//32) bytes.
    The deprecated replica above is NOT called (step 1/2: production
    quantization is the consumer's own function only)."""
    s_rows, k = x.shape
    q, sf = _dc_mxfp8_quantize(x.contiguous(), False)
    sf = (sf.view(torch.uint8).reshape(-1)[: s_rows * (k // _MX_BLOCK)]
          .view(s_rows, k // _MX_BLOCK))
    return q.view(torch.uint8), sf, q.dtype


def _dc_mxfp8_gather(plan, x):
    """This rank's bf16 shard [E, K] -> the whole chunk's (fp8 [M, K],
    linear scales [M, K/32]): the AG carries the u8 payload and the u8
    scales as SEPARATE byte collectives (row-local law above) -- half the
    wire bytes of the bf16 gather it replaces."""
    q, sf, dt = _dc_mxfp8_shard(x)
    qg = ag_rows(plan["group"], q, plan["M"]).view(dt)
    sg = ag_rows(plan["group"], sf, plan["M"])
    return qg, sg


def _dc_fp8_agree_min(plan, local):
    """TP int32 MIN over the attn-TP group (the community _agree_min,
    knapcio :171-175): every rank must agree the local checks passed --
    a single disagreeing rank flips the size to bf16 EVERYWHERE (a
    rank-divergent payload dtype would desynchronize the AG itself)."""
    import torch.distributed as dist
    flag = torch.tensor(
        [1 if local else 0], dtype=torch.int32,
        device=torch.cuda.current_device(),
    )
    dist.all_reduce(flag, op=dist.ReduceOp.MIN,
                    group=plan["group"].device_group)
    return bool(flag.item())


def _dc_fp8_eligible_attn(attn):
    """fp8_eligible_attn equivalent (community knapcio :784-797; the
    attribute names read off OUR engine tree, read-only: compressor /
    indexer deepseek_v4.py:1116-1117, fuse_wqa_wkv :834, wqkv_a consumed
    as x_linear :1431-1435, receiver gate accepts_mxfp8_swizzled_input
    :1225-1253): a region attention whose prefill path reads x ONLY
    through wqkv_a(x_quant) -- no compressor, no indexer (the kv / index
    source layers 2/8/14/20 read x themselves and stay bf16), the fused
    wqkv_a projection present, and the engine's own receiver gate TRUE
    (FLASHINFER_CUTLASS + block_fp8_mxfp8_ready on the production form).
    On the production shape that leaves 17 of the 21 region layers
    eligible (step 5). Cached on the module; anything unreadable =
    ineligible (fail-safe bf16)."""
    v = getattr(attn, "_dsv41_sp_agin_fp8", None)
    if v is None:
        try:
            v = bool(getattr(attn, "compressor", None) is None
                     and getattr(attn, "indexer", None) is None
                     and getattr(attn, "fuse_wqa_wkv", False)
                     and getattr(attn, "wqkv_a", None) is not None
                     and attn.accepts_mxfp8_swizzled_input())
        except Exception:  # noqa: BLE001
            v = False
        attn._dsv41_sp_agin_fp8 = v
    return v


def _dc_fp8_input(plan, attn, x):
    """Pre-quantized attention input for this chunk as a
    Mxfp8SwizzledInput tuple, or (None, bf16 full rows) when the size is
    on its permanent fallback / the first-chunk triple check failed /
    the consumer's quantizer is unresolvable at probe time. Returns
    (xq, None) / (None, xb) / (None, None).
    checked-not-assumed, per SIZE M, decided ONCE (community _fp8_input,
    knapcio :837-863):
      (1) gather the shard to bf16 (xb), run the consumer's quantizer on
          the GATHERED rows with the SWIZZLED layout and torch.equal both
          payload and scale bytes against quantize-shard-then-gather +
          our swizzle -- the row-local law + the swizzle construction,
          proven per size per boot (never assumed, never a roundtrip);
      (2) attn.wqkv_a(xb)[0] vs attn.wqkv_a(xq)[0] torch.equal -- the
          dual-INPUT dual-OUTPUT bit law: the engine's internal quantize
          of the bf16 path vs our pre-quantized tuple must land on the
          same wqkv_a output bytes;
      (3) TP int32 MIN agreement (_dc_fp8_agree_min) -- all ranks concur.
    Any red -> _FP8_M[M] = (False, ...) for the boot + a rank-0 census
    line; the caller reuses the already-gathered xb (no second bf16 AG).
    COLLECTIVE-ORDER LAW (why there is NO try/except around the gather
    sequence): a rank-divergent fallback would interleave different
    collectives on the same NCCL communicator and hang the TP group, so
    the fp8 branch decision must be UNIFORM before the first AG. It is,
    by construction: (a) the import probe (_dc_fp8_quantize_ok) resolves
    once per boot from the shared adapter/engine filesystem -- rank-
    uniform; (b) eligibility is a pure function of the shared model;
    (c) _FP8_M is uniform after the first chunk's MIN vote; (d) on the
    first chunk EVERY rank unconditionally runs the same three AGs (byte
    payload, byte scales, bf16 reference) BEFORE any branch, and the
    per-rank check exceptions are folded into the MIN vote (post-
    collectives, pre-branch). A mid-sequence engine fault stays a
    fail-stop crash, never a divergent fallback (the file's
    boundary-did-not-fire law)."""
    if not _dc_fp8_quantize_ok():
        return None, None            # boot-uniform unavailability (probe)
    state = _FP8_M.get(plan["M"])
    if state is not None and not state[0]:
        return None, None                    # permanent bf16 for this size
    qg, sg = _dc_mxfp8_gather(plan, x)       # AG #1 payload, AG #2 scales
    sw = _dc_swizzle_128x4(sg)
    if state is None:
        # first chunk of this size: the triple check (step 4). The bf16
        # reference AG (#3) runs UNCONDITIONALLY on every rank before any
        # branch; the checks themselves are collective-free (wqkv_a may
        # carry stock AR leaves -- sublayer is None here, so they route
        # stock, symmetrically on every rank).
        xb = ag_rows(plan["group"], x, plan["M"])
        local = False
        sf_shape = sf_dtype = None
        try:
            rq, rs = _dc_mxfp8_quantize(xb.contiguous(), True)
            rs_u8 = rs.view(torch.uint8).reshape(-1)
            local = bool(
                rq.shape == qg.shape
                and torch.equal(rq.view(torch.uint8), qg.view(torch.uint8))
                and rs_u8.numel() == sw.numel()
                and torch.equal(rs_u8, sw))
            if local:
                xq = _dc_mxfp8_input_cls()(
                    qg, sw.view(rs.dtype).view(rs.shape))
                # wqkv_a dual run: sublayer is None here, so the engine's
                # own AR leaves inside (if any) route stock (dispatch
                # returns _NOT_OURS with sublayer None)
                local = bool(
                    torch.equal(attn.wqkv_a(xb)[0], attn.wqkv_a(xq)[0]))
            sf_shape, sf_dtype = tuple(rs.shape), rs.dtype
        except Exception as exc:  # noqa: BLE001
            local = False
            logger.error(
                "DSV41 prefill SP deepcarry AG-in fp8 first-chunk check "
                "(M=%s) raised (%s: %s) -- voting bf16", plan["M"],
                type(exc).__name__, exc,
            )
        ok = _dc_fp8_agree_min(plan, local)
        _FP8_M[plan["M"]] = state = (ok, sf_shape, sf_dtype)
        if plan["rank"] == 0:
            logger.warning(
                "DSV41 prefill SP deepcarry AG-in fp8 (M=%s): MXFP8 bytes "
                "+ scales and wqkv_a output %s the stock bf16 path on "
                "every rank -> %s (rank 0 local %s)",
                plan["M"],
                "equal" if ok else "DIFFER from",
                "MXFP8 byte AG ON" if ok
                else "bf16 gather (PERMANENT for this size, fail-safe)",
                local,
            )
        if not ok:
            return None, xb
    return _dc_mxfp8_input_cls()(
        qg, sw.view(state[2]).view(state[1])), None


def _verified_rs_ag(site, stock, group, input_):
    """Swap with the per-(site, dtype, bucket) first-call dual bit-check.

    First call in a bucket: run stock AR on a clone (the reference) and the
    RS+AG swap on the live input, compare bitwise. Equal -> bucket verified,
    engaged line logged once per site (A4 activation evidence). Unequal ->
    bucket flipped to permanent stock fallback, loud error (never a silent
    ulp drift). Verified buckets run RS+AG only.
    """
    key = (site, str(input_.dtype), _bucket(input_))
    if key in _state["failed"]:
        return stock(input_)
    if key in _state["verified"]:
        return rs_ag_all_reduce(group, input_)
    ref = input_.clone()
    stock(ref)
    res = rs_ag_all_reduce(group, input_)
    if torch.equal(ref, res):
        _state["verified"].add(key)
        if site not in _state["engaged_logged"]:
            _state["engaged_logged"].add(site)
            logger.warning(
                "DSV41 prefill SP comm engaged site=%s rank=%s world=%s rows=%s "
                "dtype=%s pad=%s (AR -> RS+AG, byte-checked)",
                site, group.rank_in_group, group.world_size, input_.shape[0],
                input_.dtype, (-input_.shape[0]) % group.world_size,
            )
        return res
    _state["failed"].add(key)
    logger.error(
        "DSV41 prefill SP comm BIT-MISMATCH site=%s key=%s: RS+AG differs from "
        "stock AR (reduction-order drift, e.g. NCCL algo split by size); bucket "
        "falls back to stock AR permanently for this boot",
        site, key,
    )
    return ref


def _verified_sp_section(site, stock, group, input_, allow_fp8=True):
    """Stage1 swap with the per-(site, dtype, bucket) first-call dual
    bit-check -- the 对拍 half of the EXACT guarantee.

    First call in a bucket (or EVERY call under DSV41_PREFILL_SP_DEBUG=
    compare): run the stock full-rows path on a clone -- stock AR followed
    by the site's rowwise section over ALL rows, the exact semantics the
    engine would get without us -- and the sharded path (RS -> rowwise on
    the rank's shard -> AG) on the live input, compare bitwise. Equal ->
    bucket verified, stage1 engaged line logged once per site (A4
    activation evidence). Unequal (NCCL algo split by size, or a section
    that is not row-count invariant -- the sp_logical_rows hazard) ->
    bucket flipped to permanent stock fallback, loud error, and the STOCK
    REFERENCE is what this call returns (fail-safe direction = the
    verified path). Verified buckets run the sharded path only.

    allow_fp8=False is the stage2 fallback entry: the bf16 gather for a
    bucket whose fp8 premise failed (it must NOT route back into the fp8
    wrapper -- that would loop).
    """
    rowwise = _SECTIONS.get(site)
    if rowwise is None:
        def rowwise(x):
            return x  # identity section: byte-neutral P0 semantics
    if (allow_fp8 and FP8_MOE and _fp8_armed()
            and site in _SECTIONS_FP8 and _fp8_call_ok(input_)):
        # W5 deprecation guard: _fp8_armed() is False unconditionally, so
        # this branch is DEAD by construction -- kept visible so the
        # replica-based gather (_verified_sp_section_fp8) cannot be
        # re-armed by a stray register_section(fp8=True) without touching
        # this line (the gap-verdict retires the replica bytes).
        return _verified_sp_section_fp8(site, stock, group, input_, rowwise)
    key = (site, str(input_.dtype), _bucket(input_))
    check = DEBUG_COMPARE or key not in _state["verified"]
    if key in _state["failed"] and not DEBUG_COMPARE:
        out = stock(input_)  # in-place like the engine contract; alias kept
        return rowwise(out)
    if not check:
        return sp_section(group, input_, rowwise)
    ref = input_.clone()
    stock(ref)
    ref = rowwise(ref)
    res = sp_section(group, input_, rowwise)
    if torch.equal(ref, res):
        _state["verified"].add(key)
        if site not in _state["engaged_logged"]:
            _state["engaged_logged"].add(site)
            logger.warning(
                "DSV41 prefill SP shard engaged site=%s rank=%s world=%s "
                "rows=%s dtype=%s pad=%s section=%s (RS -> shard rowwise -> "
                "AG, bit-checked vs full-rows stock)",
                site, group.rank_in_group, group.world_size, input_.shape[0],
                input_.dtype, (-input_.shape[0]) % group.world_size,
                _SECTIONS.get(site).__name__ if site in _SECTIONS else "identity",
            )
        return res
    _state["failed"].add(key)
    logger.error(
        "DSV41 prefill SP shard BIT-MISMATCH site=%s key=%s: sharded section "
        "differs from the full-rows stock path (reduction-order drift or a "
        "row-count dependent section -- sp_logical_rows law); bucket falls "
        "back to stock permanently for this boot",
        site, key,
    )
    return ref


def _verified_sp_section_fp8(site, stock, group, input_, rowwise):
    """Stage2 swap with the per-(site, dtype, bucket) first-call dual
    bit-check -- TWO premises, both checked (R4: the quantizer's byte
    equality is a runtime check, not an assumption):
      (a) the stage1 EXACT premise, on bf16: the sharded path RS ->
          rowwise(shard) -> AG equals the full-rows stock path bitwise.
          This is the fine-grained guard and it MUST ride bf16: E4M3
          rounding is coarse enough to MASK a bf16-ulp reduction-order
          drift, so checking only the fp8 result would weaken stage1's
          bit-equality gate;
      (b) the stage2 premise: the fp8 gather RS -> rowwise(shard) ->
          MXFP8 quantize -> AG fp8 bytes -> dequant equals the ORACLE
          quantize-dequantize of the stock full-rows reference bitwise
          (row purity of the quantizer + pure-concatenation assembly +
          row-count conservation; catches scale-block, layout, pad-leak
          and row-mapping drift that (a) cannot see).
    First call in a bucket (or EVERY call under DSV41_PREFILL_SP_DEBUG=
    compare) dual-runs; either mismatch -> loud error and the bucket flips
    to a PERMANENT bf16-gather fallback (which runs its own dual check and
    owns the stock fallback underneath; design card §5.1: failure = the
    bf16 gather path stays in place). Verified buckets run fp8 only."""
    key = ("fp8", site, str(input_.dtype), _bucket(input_))
    if key in _state["failed"]:
        return _verified_sp_section(site, stock, group, input_,
                                    allow_fp8=False)
    if key in _state["verified"] and not DEBUG_COMPARE:
        return sp_section_fp8(group, input_, rowwise)
    ref = input_.clone()
    stock(ref)
    ref = rowwise(ref)
    bf16 = sp_section(group, input_, rowwise)
    res = sp_section_fp8(group, input_, rowwise)
    if torch.equal(bf16, ref) and torch.equal(res, mxfp8_oracle(ref,
                                                               input_.dtype)):
        _state["verified"].add(key)
        if site not in _state["engaged_logged"]:
            _state["engaged_logged"].add(site)
            logger.warning(
                "DSV41 prefill SP fp8 gather engaged site=%s rank=%s "
                "world=%s rows=%s K=%s dtype=%s section=%s (RS -> shard "
                "rowwise -> MXFP8 E4M3+UE8M0/32 quantize -> all-gather fp8 "
                "bytes, wire 1/1.94 of bf16 -> dequant %s; bit-checked: "
                "bf16 shard == stock AND fp8 == oracle(quant(stock)))",
                site, group.rank_in_group, group.world_size, input_.shape[0],
                input_.shape[-1], input_.dtype,
                _SECTIONS.get(site).__name__ if site in _SECTIONS
                else "identity", input_.dtype,
            )
        return res
    _state["failed"].add(key)
    logger.error(
        "DSV41 prefill SP fp8 gather BIT-MISMATCH site=%s key=%s: the fp8 "
        "gather differs from the oracle-quantized stock reference, or the "
        "bf16 sharded path drifted (reduction order / row purity / row "
        "count / quantizer layout); bucket falls back to the verified bf16 "
        "gather permanently for this boot",
        site, key,
    )
    return _verified_sp_section(site, stock, group, input_,
                                allow_fp8=False)


# F5 (PROD-RS-WHITEBOX-QA-20261003 §3 "no-observation-plane" census): the
# per-site one-time marker for a throwing group getter -- every later call
# on the site runs stock QUIETLY (the fallback direction is fail-safe, the
# SILENCE was the bug: census could not tell an engine-API-drifted boot
# from an engaged arm without this line).
_GROUP_GETTER_FAILED = set()


def _log_group_getter_failure(site, exc):
    """One ERROR per (leaf site) per boot when its group getter throws:
    names the site, the exception, the consequence (stock AR on every
    call of this site) and the census reading (installed!=engaged)."""
    if site in _GROUP_GETTER_FAILED:
        return
    _GROUP_GETTER_FAILED.add(site)
    logger.error(
        "DSV41 prefill SP leaf group getter FAILED site=%s exc=%r -- every "
        "AR call on this site runs the STOCK collective for this boot "
        "(installed != engaged: check the engine parallel-state API this "
        "getter reads; site stays fail-safe stock, first failure only is "
        "logged)",
        site, exc,
    )


def _make_stage1_ar_leaf(site, stock, group_of):
    """Wrap one plain-AR leaf for stage1; stock unless the prefill bracket
    armed it. Same shape/gate law as the P0 leaf; the swapped path runs the
    site's registered section inside the shard; a pending layer-carry for
    this leaf's semantic site runs the engine section instead (below)."""

    def leaf(input_):
        if not _state["active"]:
            return stock(input_)
        try:
            group = group_of()
        except Exception as exc:
            # F5 (PROD-RS-WHITEBOX-QA-20261003): a persistently throwing
            # group getter used to fall back to stock with ZERO log -- the
            # "banner present != arm engaged" window (a drifted engine API
            # would silently run every AR on this site stock while the boot
            # banner claims installed). One ERROR per site per boot (the
            # _dc_refuse first-time law), with the exception for context.
            _log_group_getter_failure(site, exc)
            return stock(input_)
        if _deepcarry_armed():
            # DEEPCARRY: the ONLY swap on this leaf is the region boundary
            # reduction (plan active + inner + site match); everything else
            # -- region-local ARs, stock-loop ARs under a refused plan, the
            # engram island's lookup AR -- runs the STOCK leaf. The legacy
            # per-site RS->section->AG form is the M7 red-flag form and is
            # not installed under deep-carry.
            got = _dc_boundary_dispatch(site, stock, group, input_)
            return got if got is not _NOT_OURS else stock(input_)
        if not _call_eligible(input_, group):
            return stock(input_)
        got = _carry_dispatch(site, stock, group, input_)
        if got is not _NOT_OURS:
            return got
        return _verified_sp_section(site, stock, group, input_)

    leaf.__name__ = getattr(stock, "__name__", site)
    setattr(leaf, _MARKER, True)
    return leaf


# ------------------------------------------------- stage1 layer-carry core
#
# The engine sections (module docstring "STAGE1 ENGINE SECTIONS"): the hc
# consumption that follows each plain-AR site on the production prefill
# path, sharded onto the RS+AG seam. Protocol, end to end:
#   * _wrap_forward_hc_pre_from_prev pushes the layer frame (layer,
#     forward_batch, next_norm, next_combined) for the sublayer contexts.
#   * the use_mhc_post_fusion wrap publishes the carry of each overlap_only
#     sublayer (residual + MhcPostFusion + norm + consumption form) while
#     its context is active.
#   * the AR leaf whose semantic site matches runs RS -> _replica_hc_section
#     on the shard -> AG of every output, stashes (updated, combined,
#     normalized), and returns `updated` as the AR value.
#   * the engine's own consumption (_hc_post_with_combine / hc_post wraps)
#     is suppressed by tensor identity (x is stash.updated) -- the engine
#     passes the leaf's return straight through -- so the section runs
#     exactly once and the layer receives bitwise stock-form values.
#   * the first call per (site, dtype, bucket) dual-runs the SHARDED
#     section against the ENGINE'S OWN full-rows methods (the unwrapped
#     originals) -- checking row-split fidelity AND replica fidelity in one
#     bit-check; any mismatch flips the bucket to a permanent stock path
#     whose returned values are the engine's own computation.

_CARRY_MARKER = "_dsv41_prefill_sp_carry"
_LAYERCLS_MARKER = "_dsv41_prefill_sp_layercls"
_NOT_OURS = object()

# Engine symbols bound at install time (never at module import: the file
# must import without sglang for the offline unit tests).
_ENGINE = {}


def _norm_prefill_ok(norm) -> bool:
    """The engine's fused-norm preconditions (deepseek_v4.py:3484-3490),
    evaluated on the norm module -- shape/alignment parts are row-count
    independent, so they hold for the shard slices too."""
    w = norm.weight
    return (
        not norm.cast_x_before_out_mul
        and norm.variance_size_override is None
        and w.dtype == torch.bfloat16
        and tuple(w.shape) == (5120,)
        and w.is_contiguous()
        and w.data_ptr() % 16 == 0
    )


# T61 day-6 (R4 kernel-row wall): the row-band faces of the engine's two
# prefill norm kernels. The engine WRAPPERS carry [4096, 65536] dispatch
# asserts (hc_norm_prefill: mhc_post_combine.py:79; hc_combine_norm:
# hc_combine_norm.py:60, band (0,96]u[4096,65536]) but the KERNELS are
# row-per-program with no row limit -- the bands are one-CTA-per-row
# dispatch choices for the full-prefill row counts the wrappers were
# built for. The deep-carry region hands these kernels SHARD rows
# (E = M/world; [1024, 4096) at world 4 for M in [4096, 16384)), so the
# wrappers assert and the fused mhcpcn kernel itself CHECK_HOST-aborts
# (.cuh:167, the R4 crash). Resolved once at install with source needles
# and fail-closed (family law: an unreadable or drifted kernel face
# refuses the boot rather than route blindly).
_ROWFREE_NORM_NEEDLES = (
    # pins the kernel symbol AND that the row band lives in the WRAPPER
    # (a band moving INTO the kernel = the premise of this route dies)
    "def _hc_norm_prefill(",
    "assert 4096 <= combined.shape[0] <= 65536",
    "tl.program_id(0)",
)
_ROWFREE_COMBINE_NORM_NEEDLES = (
    "def _hc_combine_norm_prefill(",
    "assert (0 < m <= 96 or 4096 <= m <= 65536)",
    "if m >= 4096:",
    "tl.program_id(0)",
)


def _need_module_source(module, name, needles):
    """Needle-check an engine MODULE's source (fail-closed): the day-6
    decomposed routes call engine triton kernels directly, so the kernel
    symbol, its row-per-program shape and the WRAPPER-side location of the
    row band are pinned to the module text exactly like the seam needles
    pin the class seams (_need_source law)."""
    try:
        source = inspect.getsource(module)
    except (OSError, TypeError) as exc:
        raise RuntimeError(
            f"prefill_sp: engine module {name} unreadable ({exc}); "
            "refusing to boot (day-6 decomposed-route kernel face)"
        ) from None
    for needle in needles:
        if needle not in source:
            raise RuntimeError(
                f"prefill_sp: engine module {name} no longer contains "
                f"{needle!r}; refusing to boot -- the day-6 row-free "
                "kernel route is pinned to this face (row band moved or "
                "kernel drifted)"
            )


def _load_rowfree_norm_faces():
    """Resolve the two row-band-free kernel launchers (install time,
    fail-closed). Each returned callable replicates the engine wrapper's
    m>=4096 launch VERBATIM minus the row-band assert -- every other
    wrapper check (shape/dtype/contiguity) is kept, so a bad operand
    still fails loudly at our face."""
    import sglang.kernels.ops.layernorm.hc_combine_norm as _hcn_mod
    import sglang.kernels.ops.layernorm.mhc_post_combine as _mpc_mod
    _need_module_source(_mpc_mod, "mhc_post_combine",
                        _ROWFREE_NORM_NEEDLES)
    _need_module_source(_hcn_mod, "hc_combine_norm",
                        _ROWFREE_COMBINE_NORM_NEEDLES)
    norm_kern = getattr(_mpc_mod, "_hc_norm_prefill", None)
    combine_kern = getattr(_hcn_mod, "_hc_combine_norm_prefill", None)
    if norm_kern is None or combine_kern is None:
        raise RuntimeError(
            "prefill_sp: row-free norm kernels missing "
            f"(_hc_norm_prefill={'ok' if norm_kern else 'MISSING'}, "
            f"_hc_combine_norm_prefill="
            f"{'ok' if combine_kern else 'MISSING'}); refusing to boot "
            "(day-6 decomposed-route kernel face)"
        )

    def norm_prefill_rows(combined, weight, eps):
        # hc_norm_prefill (mhc_post_combine.py) minus the row band: the
        # engine's own launch for the m>=4096 dispatch, verbatim.
        assert combined.shape[1] == 5120
        assert weight.shape == (5120,)
        assert combined.dtype == weight.dtype == torch.bfloat16
        assert combined.is_contiguous() and weight.is_contiguous()
        output = torch.empty_like(combined)
        norm_kern[(combined.shape[0],)](
            combined, weight, output, eps, num_warps=4)
        return output

    def combine_norm_prefill_rows(x_flat, pre, weight, eps):
        # hc_combine_norm's m>=4096 dispatch (hc_combine_norm.py) minus
        # the row band: the prefill-variant kernel the engine launches
        # for the [4096, 65536] rows stock runs -- the same launch, so
        # the shard rows get the identical per-row program.
        m = x_flat.shape[0]
        assert x_flat.shape == (m, 20480)
        assert pre.shape == (m, 4) and pre.stride(1) == 1
        assert weight.shape == (5120,) and weight.is_contiguous()
        assert x_flat.dtype == weight.dtype == torch.bfloat16
        assert x_flat.stride(1) == 1
        y = torch.empty((m, 5120), dtype=x_flat.dtype, device=x_flat.device)
        combine_kern[(m,)](
            x_flat, pre, weight, y, x_flat.stride(0), pre.stride(0),
            eps, num_warps=4)
        return y

    return norm_prefill_rows, combine_norm_prefill_rows


def _carry_call_ok(carry, input_, group) -> bool:
    """门内查形 for a carry site: the AR input must be this sublayer's
    attention/MoE output tensor ([rows, 5120] bf16, rows == the carry's
    residual rows). Any mismatch = not ours -> the generic leaf path."""
    return (
        group.world_size >= 2
        and input_.dim() == 2
        and input_.shape[0] == carry["rows"]
        and input_.shape[1] == 5120
        and input_.shape[0] >= MIN_ROWS
        and input_.dtype == torch.bfloat16
        and input_.is_contiguous()
        and input_.is_cuda
    )


def _tbo_active() -> bool:
    """Engine two-batch overlap interleaves two micro-batches inside one
    forward; the layer-carry state (frames / carry / stash) is single-slot
    module-global, so interleaved publish/consume would mismatch sublayers.
    Read the engine's own flag (get_exec().overlap, the runtime-context bag
    every engine site reads); unreadable -> refuse the carry (fail-closed,
    same law as batch_invariant below)."""
    try:
        return bool(_ENGINE["get_exec"]().overlap.enable_two_batch_overlap)
    except Exception as exc:
        # 用户令④ (no-observation-plane census, PROD-RS-WHITEBOX-QA §3 row
        # 2): unreadable -> refuse (fail-closed direction, harmless), but
        # the refusal cause was silent -- one census line names it.
        if not _STATE_ONCE.get("tbo_unreadable"):
            _STATE_ONCE["tbo_unreadable"] = True
            logger.warning(
                "DSV41 prefill SP: two-batch-overlap flag unreadable "
                f"(%r) -- read as ACTIVE (the carry refuses; fail-closed, "
                "first failure only is logged)",
                exc,
            )
        return True


def _sync_stats(mhc):
    """Materialize the sublayer's hc stats exactly as stock's overlap path
    does (start_stats_before_all_reduce: stats_stream waits the main stream,
    then the recorded partial launches on the side stream), then join. The
    attention site has already run this at deepseek_v4.py:2530; the FFN site
    runs it here (stock defers it to :3716 -- a pure reorder of the same
    kernels on the same stream, values identical, and the layer's own later
    materialize_stats() becomes the idempotent no-op)."""
    mhc.start_stats_before_all_reduce()
    if mhc.stats_stream is not None:
        torch.cuda.current_stream().wait_stream(mhc.stats_stream)
    return mhc.pre, mhc.post, mhc.comb


def _decide_branch(carry) -> str:
    """Decide the section's kernel branch from the FULL-row operands BEFORE
    any collective runs: the branch fixes how many outputs the section AGs,
    so it must be a function of SPMD-uniform state only (rows, form, the
    engine tensors' dtypes -- identical across ranks because the stats
    kernels are deterministic on identical inputs). Mirrors the engine's G
    predicate (deepseek_v4.py:3446-3503) evaluated at the full row count;
    drift here is caught by the dual check against the engine's own
    methods (a wrong branch = different values = permanent stock)."""
    if carry["form"] == "hpc":
        carry["branch"] = "hc_post"
        return carry["branch"]
    pre, post, comb = _sync_stats(carry["mhc"])
    residual = carry["residual"]
    g = carry["g_prefill"]
    rows = carry["rows"]
    branch = "hc_post"
    if (
        g
        and 4096 <= rows <= 65536
        and residual.dtype == torch.bfloat16
        and post.dtype == comb.dtype == pre.dtype == torch.float32
        and residual.shape[0] == post.shape[0] == comb.shape[0] == pre.shape[0]
        and all(t.is_contiguous() for t in (residual, post, comb, pre))
        and all(t.data_ptr() % 16 == 0
                for t in (residual, post, comb, pre))
        # F4 legacy-face twin: the engine's inner fused gate also aligns
        # the SECTION INPUT (deepseek_v4.py:3487-3490 (x, residual,
        # norm.weight)); the AR input is full-row SPMD-uniform state, so
        # the demotion stays rank-uniform (the AG count never forks).
        and carry.get("input_aligned", True)
    ):
        norm = carry["norm"]
        if norm is not None and _norm_prefill_ok(norm):
            branch = "mhc_post_combine_norm_prefill"
        else:
            branch = "mhc_post_combine"
    carry["branch"] = branch
    return branch


def _replica_hc_section(carry, xs, lo, hi):
    """The site's row-wise section on this rank's REAL shard rows
    xs = full[lo:hi]: the hc consumption the engine would run on the full
    rows after its AR, taking the branch decided (uniformly) by
    _decide_branch -- the same kernel the stock full-rows path takes.
    Returns (updated, combined, normalized) -- the exact triple form of
    the engine's consumption seam."""
    layer, mhc = carry["layer"], carry["mhc"]
    pre, post, comb = _sync_stats(mhc)
    residual = carry["residual"]
    rs, ps, cs, prs = (residual[lo:hi], post[lo:hi], comb[lo:hi], pre[lo:hi])
    branch = carry.get("branch") or _decide_branch(carry)
    if branch == "mhc_post_combine_norm_prefill":
        norm = carry["norm"]
        upd, nrm = _ENGINE["mhcpcn"](
            xs, rs, ps, cs, prs, norm.weight, norm.variance_epsilon)
        return upd, None, nrm
    if branch == "mhc_post_combine":
        upd, combd = _ENGINE["mhcpc"](xs, rs, ps, cs, prs)
        return upd, combd, None
    return _ENGINE["hcpost_orig"](layer, xs, rs, ps, cs), None, None


def _engine_truth(carry, x_full):
    """The engine's OWN full-rows computation for this sublayer -- the
    dual-check reference and the failed-bucket return value. Calls the
    unwrapped originals, so replica drift is caught by the same bit-check
    that guards the row split (never replica-vs-replica)."""
    layer, mhc, norm = carry["layer"], carry["mhc"], carry["norm"]
    pre, post, comb = _sync_stats(mhc)
    if carry["form"] == "pcwc":
        return _ENGINE["hcpc_orig"](
            layer, x_full, carry["residual"], post, comb, pre,
            carry["forward_batch"], norm=norm)
    return _ENGINE["hcpost_orig"](
        layer, x_full, carry["residual"], post, comb), None, None


def _sp_carry_section(carry, group, input_):
    """RS -> replica section on the shard -> AG of every section output
    (updated first; combined/normalized gathered on the same seam). The
    branch (and so the AG count) is decided from full-row state BEFORE the
    RS, keeping the collective sequence SPMD-uniform. Pad rows are computed
    on (isolated, per-row) and sliced off at each AG."""
    # F4: publish the section-input alignment BEFORE the branch decision
    # is consumed (full-row SPMD-uniform state -- see _decide_branch's
    # input_aligned conjunct; set once, read by the decision).
    try:
        carry["input_aligned"] = input_.data_ptr() % 16 == 0
    except Exception:
        carry["input_aligned"] = False
    _decide_branch(carry)
    rows = input_.shape[0]
    world = group.world_size
    extent = shard_extent(rows, world)
    lo, hi = shard_bounds(rows, world, group.rank_in_group)
    n_real = max(0, hi - lo)  # degenerate shards (rows << world) stay empty
    shard = rs_shard(group, input_)
    triple = _replica_hc_section(carry, shard[:n_real], lo, hi)
    out = []
    for t in triple:
        if t is None:
            out.append(None)
            continue
        if t.shape[0] != extent:
            t = torch.cat(
                [t, t.new_zeros((extent - t.shape[0],) + tuple(t.shape[1:]))],
                dim=0)
        out.append(ag_rows(group, t, rows))
    return tuple(out)


def _drop_stash(reason):
    """Fail-stop: an unconsumed stash means the engine's consumption seam did
    not run on the tensor the leaf returned -- the install-time needle checks
    cannot structurally guarantee the identity pass-through, so continuing
    would let the engine apply the hc consumption a second time on the
    section's output (wrong values online). The forward is refused, never
    logged past; re-audit the wraps before the next boot."""
    _state["stash"] = None
    _state["carry_dropped"] += 1
    logger.critical(
        "DSV41 prefill SP layer-carry: section stash dropped (%s) -- the "
        "engine did not consume the section output through the expected "
        "seam; engine-flow drift, re-audit the wraps before trusting this "
        "boot", reason,
    )
    raise RuntimeError(
        f"prefill_sp: layer-carry stash unconsumed ({reason}): continuing "
        "would let the engine apply the hc consumption twice on the "
        "section's output; refusing to continue (fail-stop, wrong values "
        "must not go online)"
    )


def _stash_section(carry, triple):
    if _state["stash"] is not None:
        _drop_stash("superseded by a new sublayer before consumption")
    _state["stash"] = {
        "site": carry["site"],
        "updated": triple[0],
        "combined": triple[1],
        "normalized": triple[2],
    }


def _consume_stash(x):
    """The suppression half: the engine hands back exactly the tensor the
    leaf returned, so identity (not equality) proves the section already
    ran for this call. Returns the stash or None (recompute stock)."""
    st = _state["stash"]
    if st is not None and x is st["updated"]:
        _state["stash"] = None
        return st
    return None


def _verified_carry_section(carry, stock, group, input_):
    """The carry-site swap with the per-(site, dtype, bucket) first-call
    dual bit-check against the engine's own full-rows methods. Fallback =
    stock AR followed by the engine's own computation (stash-fed, still
    suppressed) -- bitwise stock, zero recompute, zero double-apply."""
    site = carry["site"]
    key = (site, str(input_.dtype), _bucket(input_))
    if key in _state["failed"] and not DEBUG_COMPARE:
        triple = _engine_truth(carry, stock(input_))
        _stash_section(carry, triple)
        return triple[0]
    if key in _state["verified"] and not DEBUG_COMPARE:
        triple = _sp_carry_section(carry, group, input_)
        _stash_section(carry, triple)
        return triple[0]
    ref = input_.clone()
    stock(ref)
    ref_triple = _engine_truth(carry, ref)
    res_triple = _sp_carry_section(carry, group, input_)
    ok = all(
        (a is None and b is None)
        or (a is not None and b is not None and torch.equal(a, b))
        for a, b in zip(ref_triple, res_triple)
    )
    if ok:
        _state["verified"].add(key)
        if site not in _state["engaged_logged"]:
            _state["engaged_logged"].add(site)
            logger.warning(
                "DSV41 prefill SP layer-carry engaged site=%s rank=%s "
                "world=%s rows=%s form=%s kernel=%s (RS -> shard hc section "
                "-> AG, bit-checked vs the engine's full-rows method)",
                site, group.rank_in_group, group.world_size,
                input_.shape[0], carry["form"],
                carry.get("branch") or carry["kernel_hint"],
            )
        _stash_section(carry, res_triple)
        return res_triple[0]
    _state["failed"].add(key)
    logger.error(
        "DSV41 prefill SP layer-carry BIT-MISMATCH site=%s key=%s: the "
        "sharded section differs from the engine's own full-rows path "
        "(reduction-order drift, row purity, or section replica drift); "
        "bucket falls back to the engine's stock path permanently for "
        "this boot", site, key,
    )
    _stash_section(carry, ref_triple)
    return ref_triple[0]


def _carry_dispatch(site, stock, group, input_):
    """Leaf-side routing: run the engine section when THIS leaf's semantic
    site has a pending carry and the call is the sublayer's AR tensor.
    Returns _NOT_OURS for the generic leaf path (identity section / P0)."""
    if not _state["carry_sites"]:
        return _NOT_OURS
    carry = _state["carry"]
    if carry is None or carry["leaf_site"] != site:
        return _NOT_OURS
    if not _carry_call_ok(carry, input_, group):
        return _NOT_OURS
    return _verified_carry_section(carry, stock, group, input_)


def _build_carry(mhc, frame):
    """Publish-time gates + carry construction from the MhcPostFusion the
    engine just entered (overlap_only prefill form) and the layer frame.
    Every gate here is SPMD-uniform (config/batch/rows/platform) so all
    ranks publish or refuse together -- a divergent carry would desync the
    collective sequence. Returns None (no section, generic leaf path) on
    any refusal."""
    import functools

    rec = mhc.record_stats
    if not isinstance(rec, functools.partial):
        return None
    layer = getattr(getattr(rec, "func", None), "__self__", None)
    if layer is None or not frame or frame.get("layer") is not layer:
        return None
    args = rec.args
    if len(args) < 2:
        return None
    hidden, hc_fn = args[0], args[1]
    if hc_fn is getattr(layer, "hc_attn_fn", None):
        site, leaf_site, form = "dsv4.attn_ar", "attn_tp_all_reduce", "pcwc"
        norm = getattr(layer, "post_attention_layernorm", None)
    elif hc_fn is getattr(layer, "hc_ffn_fn", None):
        site = "dsv4.ffn_ar"
        leaf_site = "moe_tensor_model_parallel_all_reduce"
        form = "pcwc" if frame.get("next_combined") is not None else "hpc"
        norm = frame.get("next_norm") if form == "pcwc" else None
        if getattr(getattr(layer, "mlp", None), "_shared_expert_tp1", False):
            return None  # post-AR `+= shared` (deepseek_v2.py:1370) would hit
            #              our composed output -- refuse the face entirely
    else:
        return None
    cfg = getattr(layer, "config", None)
    attn = getattr(layer, "self_attn", None)
    fb = frame.get("forward_batch")
    try:
        mode_ok = fb is not None and fb.forward_mode.is_extend_without_speculative()
    except Exception:
        mode_ok = False
    rows = hidden.shape[0] if hidden.dim() == 3 else 0
    if (
        not mode_ok
        or cfg is None
        or attn is None
        or getattr(cfg, "model_type", None) != "deepseek_v41"
        or getattr(layer, "hc_mult", None) != 4
        or tuple(hidden.shape) != (rows, 4, 5120)
        or rows < MIN_ROWS
        or rows > 65536
        or not hidden.is_cuda
        or hidden.dtype != torch.bfloat16
        or not hidden.is_contiguous()
        or not _ENGINE["platform_ok"]
        or _ENGINE["get_parallel"]().attn_dp_size != 1
        or bool(getattr(_ENGINE["get_forward"](), "sp_active", False))
        or _tbo_active()  # single-slot carry/frames/stash: no interleaved micro-batches
        or bool(getattr(layer, "dsa_enable_prefill_cp", False))
        or not _ENGINE["g_env"]()
    ):
        return None
    if site == "dsv4.attn_ar":
        parallel = _ENGINE["get_parallel"]()
        if attn.attn_tp_size != parallel.tp_size:
            return None  # :2565's second AR would reduce our composed output
        if not getattr(attn.wo_b, "reduce_results", False):
            return None
    kernel_hint = "hc_post"
    if (form == "pcwc" and 4096 <= rows <= 65536 and norm is not None
            and _norm_prefill_ok(norm)):
        kernel_hint = "mhc_post_combine_norm_prefill"
    elif form == "pcwc" and 4096 <= rows <= 65536:
        kernel_hint = "mhc_post_combine"
    return {
        "site": site,
        "leaf_site": leaf_site,
        "layer": layer,
        "mhc": mhc,
        "residual": mhc.residual,
        "norm": norm,
        "form": form,
        "forward_batch": fb,
        "rows": rows,
        "g_prefill": True,
        "kernel_hint": kernel_hint,
    }


# ------------------------------------------------- layer-carry wraps

def _make_use_mhc_wrapper(stock_use):
    def use_mhc_post_fusion(state):
        import contextlib

        ctx = stock_use(state)
        if (
            not _state["active"]
            or not _state["carry_sites"]
            or state is None
            or not getattr(state, "overlap_only", False)
        ):
            return ctx
        carry = _build_carry(
            state, _state["frames"][-1] if _state["frames"] else None)
        if carry is None:
            return ctx

        @contextlib.contextmanager
        def _bracket():
            _state["carry"] = carry
            try:
                with ctx:
                    yield
            finally:
                if _state["carry"] is carry:
                    _state["carry"] = None

        return _bracket()

    use_mhc_post_fusion.__name__ = getattr(
        stock_use, "__name__", "use_mhc_post_fusion")
    setattr(use_mhc_post_fusion, _CARRY_MARKER, True)
    return use_mhc_post_fusion


def _make_layer_hcprev_wrapper(stock):
    def forward_hc_pre_from_prev(self, *args, **kwargs):
        if not _state["active"] or not _state["carry_sites"]:
            return stock(self, *args, **kwargs)
        fb = kwargs.get("forward_batch")
        if fb is None and len(args) >= 4:
            fb = args[3]
        _state["frames"].append({
            "layer": self,
            "forward_batch": fb,
            "next_norm": kwargs.get("next_norm"),
            "next_combined": kwargs.get("next_combined"),
        })
        try:
            return stock(self, *args, **kwargs)
        finally:
            _state["frames"].pop()
            if _state["stash"] is not None:
                _drop_stash("layer frame ended before the engine consumed it")

    forward_hc_pre_from_prev.__name__ = getattr(
        stock, "__name__", "forward_hc_pre_from_prev")
    setattr(forward_hc_pre_from_prev, _CARRY_MARKER, True)
    return forward_hc_pre_from_prev


def _make_hcpc_wrapper(stock):
    def _hc_post_with_combine(self, x, residual, post, comb, pre,
                              forward_batch, norm=None):
        st = _consume_stash(x)
        if st is not None:
            return st["updated"], st["combined"], st["normalized"]
        return stock(self, x, residual, post, comb, pre, forward_batch,
                     norm=norm)

    _hc_post_with_combine.__name__ = getattr(
        stock, "__name__", "_hc_post_with_combine")
    setattr(_hc_post_with_combine, _CARRY_MARKER, True)
    return _hc_post_with_combine


def _make_hcpost_wrapper(stock):
    def hc_post(self, x, residual, post, comb):
        st = _consume_stash(x)
        if st is not None:
            return st["updated"]  # the section already hc_post'd these rows
        return stock(self, x, residual, post, comb)

    hc_post.__name__ = getattr(stock, "__name__", "hc_post")
    setattr(hc_post, _CARRY_MARKER, True)
    return hc_post


def _identify_adapters(chain):
    """Name the foreign wrappers in `chain` by their marker attribute (the
    _ADAPTER_MARKERS table) -- for the unwrap-depth log line only."""
    names = []
    for f in chain:
        for marker, adapter in _ADAPTER_MARKERS:
            if getattr(f, marker, False):
                if adapter not in names:
                    names.append(adapter)
                break
    return names


def _unwrap_seam(func, name):
    """T61 day-3 (stackwall fix): walk the foreign wrap chain below `func`
    to its TERMINAL. Descent follows the three shapes this stack's adapters
    actually use:
      * functools.wraps' __wrapped__ (by construction the wrapped original);
      * closure cells (skip_nonfinal_decoder's `orig`, :485/:494);
      * default-argument bindings (l2_prefetch's `_original=original`,
        l2pf_attn's `_original`, :300-307/:71-77).
    Descent is licensed ONLY from a level that carries a KNOWN adapter
    marker (or an explicit __wrapped__): an unknown/unmarked foreign
    wrapper is NOT descended into -- the terminal stays the wrapper, and
    the boot refuses either on the needle miss or, if the wrapper EMBEDS
    needle text in its own body, on _need_terminal_file's foreign-file
    law (fail-closed: unwrap failure must keep the refusal, never guess
    -- the T61 wall cannot re-enter through this door). The license also
    protects the CLEAN engine functions (no marker, no __wrapped__) from
    false descent into unrelated closure/default helpers. Only plain
    functions are followed (inspect.isfunction), each visited once.

    Returns (chain, adapters): chain[0] is `func`, chain[-1] the terminal;
    adapters names the identified foreign wrappers."""
    chain = [func]
    seen = {id(func)}
    cur = func
    while True:
        marked = any(getattr(cur, m, False) for m, _ in _ADAPTER_MARKERS)
        wrapped = getattr(cur, "__wrapped__", None)
        if not (marked or wrapped is not None):
            return chain, _identify_adapters(chain)
        cands = []
        if wrapped is not None:
            cands.append(wrapped)
        for cell in getattr(cur, "__closure__", None) or ():
            try:
                cands.append(cell.cell_contents)
            except ValueError:                    # empty cell
                continue
        cands.extend(getattr(cur, "__defaults__", None) or ())
        cands.extend((getattr(cur, "__kwdefaults__", None) or {}).values())
        nxt = None
        for cand in cands:
            if inspect.isfunction(cand) and id(cand) not in seen:
                nxt = cand
                break
        if nxt is None:
            return chain, _identify_adapters(chain)
        seen.add(id(nxt))
        chain.append(nxt)
        cur = nxt


def _unwrap_log(name, chain, adapters):
    """One log line per seam that carried foreign wraps (T61 day-3): the
    unwrap depth and the identified adapter(s), so a boot log states
    WHICH adapter's wrapper was seen through -- census-readable evidence
    the needles were verified on the engine source, not wrapper text."""
    if len(chain) > 1 or adapters:
        logger.warning(
            "prefill_sp: seam %s carries %d foreign wrap level(s) [%s] -- "
            "needles verified on the UNWRAPPED chain terminal (engine "
            "source), not the wrapper text (T61 stackwall fix; an "
            "unidentifiable wrapper would have refused the boot)",
            name, len(chain) - 1, "+".join(adapters) or "unidentified",
        )


def _owner_source_file(owner):
    """Defining file of a needle-probe owner: the module itself for module
    owners, else the owner CLASS's defining module file. None when not
    resolvable (the foreign-file law below then simply does not fire)."""
    mod = owner if isinstance(owner, types.ModuleType) else \
        sys.modules.get(getattr(owner, "__module__", ""), None)
    return getattr(mod, "__file__", None)


def _need_terminal_file(owner, name, terminal, chain):
    """T61 day-3 law (iv), the smuggler case: the needles must pin the
    ENGINE implementation -- a terminal whose source lives in a FOREIGN
    file (an unknown wrapper embedding engine-looking text, e.g. a needle
    string inside its own body) is NOT the engine seam even when every
    needle substring matches its text: an unidentified adapter around the
    loop is exactly the 读数混入行为差 hazard the abort card names (the
    known ones are unwrapped through and, for skip_nonfinal, explicitly
    integrated). Refuse unless the terminal's co_filename basename equals
    the owner's defining file basename."""
    owner_file = _owner_source_file(owner)
    code = getattr(terminal, "__code__", None)
    term_file = getattr(code, "co_filename", None)
    if (owner_file and term_file
            and os.path.basename(owner_file) != os.path.basename(term_file)):
        raise RuntimeError(
            f"prefill_sp: layer-carry seam moved ({name} needle source is "
            f"a FOREIGN file {term_file!r}, not the owner's "
            f"{os.path.basename(owner_file)!r}); refusing to boot -- the "
            "needles must pin the ENGINE implementation, never an "
            "unidentified wrapper's embedded copy (fail-closed; a known "
            "adapter wrapper is unwrapped through instead)"
        )


def _need_source(owner, name, needles):
    """Anti-drift for the layer-carry seams (design card §七 law): the
    seam must still be the engine implementation the protocol was built
    against, or the boot refuses (a silently-drifted wrap would misroute
    sections or double-apply them). Returns None on our own marker.

    T61 day-3: the needle check reads the UNWRAPPED chain TERMINAL
    (_unwrap_seam) and returns the CURRENT attribute (the chain top), so
    wrapping it keeps every earlier adapter's semantics live on the
    stock-route calls (install-order coexistence; e.g. skip_nonfinal's
    cut still fires when our plan refuses the chunk).

    REVERSE DISCRIMINATION, per needle (the loop below applies one law to
    every needle):
      (i)   a WRAPPER source can never satisfy a needle: if unwrap cannot
            descend (unknown marker, exotic original binding) `source` IS
            the wrapper's own text and the miss refuses -- feeding the
            wrapper source still refuses (fail-closed semantics preserved;
            this is exactly the T61 refusal, now reachable only for
            wrappers we cannot see through);
      (ii)  the TRUE engine source (the unwrapped terminal) passes -- the
            only new acceptances this fix admits;
      (iii) a MUTATED terminal (engine edited, or a drifted splice under
            the wrappers) misses and refuses with the same signature --
            unwrapping never weakens the pin (mock-smoke p6b/p6c both
            directions);
      (iv)  a foreign-file terminal (a wrapper EMBEDDING needle text in
            its own body, unwrap dead-ended) passes the substring check
            but is refused by _need_terminal_file: needle text in a
            foreign file is not the engine seam (the smuggler case --
            mock-smoke p6c fixture family)."""
    func = getattr(owner, name, None)
    if getattr(func, _CARRY_MARKER, False) or getattr(func, _MARKER, False):
        return None  # already wrapped (double exec)
    if not callable(func):
        raise RuntimeError(
            f"prefill_sp: layer-carry seam moved ({name} missing or not "
            f"callable on {getattr(owner, '__name__', owner)}); refusing "
            "to boot"
        )
    chain, adapters = _unwrap_seam(func, name)
    terminal = chain[-1]
    try:
        source = inspect.getsource(terminal)
    except (OSError, TypeError) as exc:
        raise RuntimeError(
            f"prefill_sp: layer-carry seam unreadable ({name}: {exc}); "
            "refusing to boot"
        ) from None
    for needle in needles:
        if needle not in source:
            raise RuntimeError(
                f"prefill_sp: layer-carry seam moved ({name} no longer "
                f"contains {needle!r}); refusing to boot -- stacking the "
                "section protocol on an unknown implementation is not "
                "ours to decide"
            )
    _need_terminal_file(owner, name, terminal, chain)
    _unwrap_log(name, chain, adapters)
    return func


def _need_init_source(layer_cls, needles):
    """REANCHOR 2026-10-02: fail-stop probe for the INSTANCE-attribute
    seams of the layer-carry protocol (self.self_attn / self.mlp / the
    two RMSNorm sublayers / the hc fn pair). These live in
    DeepseekV4DecoderLayer.__init__ (deepseek_v4.py:2624 `self.self_attn
    = self._build_self_attn(...)`, :2641 `self.mlp = deepseek_v2.
    DeepseekV2MoE(`, :2662/:2663 the RMSNorm pair, :2669-2677 the hc fn
    tuple), NOT on the class -- a class-level hasattr is structurally
    False for them (the 0607ad2e bug: the guard refused every boot with
    "self_attn missing" although the seam was intact). The fix keeps the
    fail-stop philosophy at the correct level: the __init__ source must
    still bind every symbol, or the boot refuses naming the symbol.
    getsource of a bound __init__ rides the class's file, so a re-exec'd
    deepseek_v4 module is verified against ITS OWN fresh class source.

    T61 day-3: same wrapper-aware law as _need_source -- the needles are
    checked on the UNWRAPPED chain terminal (no adapter wraps __init__
    on this stack today; the law is uniform so one landing there is
    handled, and an unknown wrapper still refuses)."""
    init = getattr(layer_cls, "__init__", None)
    if init is None or not callable(init):
        raise RuntimeError(
            "prefill_sp: DeepseekV4DecoderLayer.__init__ missing or not "
            "callable; refusing to boot (layer-carry seam moved)"
        )
    chain, adapters = _unwrap_seam(init, "__init__")
    terminal = chain[-1]
    try:
        source = inspect.getsource(terminal)
    except (OSError, TypeError) as exc:
        raise RuntimeError(
            f"prefill_sp: DeepseekV4DecoderLayer.__init__ unreadable "
            f"({exc}); refusing to boot (layer-carry seam moved)"
        ) from None
    for needle in needles:
        if needle not in source:
            symbol = needle.split("=", 1)[0].replace("self.", "").strip()
            raise RuntimeError(
                f"prefill_sp: DeepseekV4DecoderLayer.{symbol} missing from "
                f"__init__ (needle {needle!r} not in source); refusing to "
                "boot (layer-carry seam moved)"
            )
    _need_terminal_file(layer_cls, "__init__", terminal, chain)
    _unwrap_log("DeepseekV4DecoderLayer.__init__", chain, adapters)
    return True


def _install_layer_carry(module) -> bool:
    """Install the stage1 engine sections (hc段) on the deepseek_v4 module's
    classes. Arms ONLY under stage1+EXACT; any seam drift refuses the boot
    (fail-closed: an inert layer-carry would silently keep the sections
    unsharded and the arm would look green)."""
    layer_cls = getattr(module, "DeepseekV4DecoderLayer", None)
    if layer_cls is None:
        raise RuntimeError(
            "prefill_sp: DeepseekV4DecoderLayer missing from the "
            "deepseek_v4 module; refusing to boot (layer-carry seam moved)"
        )
    if getattr(layer_cls, _LAYERCLS_MARKER, False):
        return False  # already installed (double exec of the module)
    hcprev = _need_source(layer_cls, "forward_hc_pre_from_prev",
                          ("record_stats=attn_stats", "record_stats=ffn_stats",
                           "prefill_overlap", "overlap_only=True",
                           "_hc_post_with_combine",
                           # REANCHOR: pin the stats-partial construction
                           # (args[0]=hidden, args[1]=hc_fn is _build_carry's
                           # routing premise) and the attn-TP gate the carry
                           # mirrors -- both verified on main-79cafec0.
                           "self._hc_mix_stats", "wo_b.reduce_results"))
    hcpc = _need_source(layer_cls, "_hc_post_with_combine",
                        ("mhc_post_combine_norm_prefill", "mhc_post_combine",
                         "hc_post(x, residual, post, comb)",
                         "4096 <= x.shape[0] <= 65536"))
    hcpost = _need_source(layer_cls, "hc_post", ("hc_post_torch_impl",))
    # REANCHOR 2026-10-02: METHOD seams stay class-level hasattr; the
    # INSTANCE-attribute seams move to _need_init_source (source needles
    # on __init__). The 0607ad2e loop probed all of them with class-level
    # hasattr, which is structurally False for instance attrs -- it
    # refused every boot ("self_attn missing") on an INTACT seam.
    for attr in ("_hc_mix_stats", "_run_moe_ffn_dp_sync", "_build_self_attn"):
        if not hasattr(layer_cls, attr):
            raise RuntimeError(
                f"prefill_sp: DeepseekV4DecoderLayer.{attr} missing; "
                "refusing to boot (layer-carry seam moved)"
            )
    _need_init_source(layer_cls, (
        "self.self_attn = self._build_self_attn(",
        "self.mlp = deepseek_v2.DeepseekV2MoE(",
        "self.input_layernorm = RMSNorm(",
        "self.post_attention_layernorm = RMSNorm(",
        "self.hc_attn_fn",
        "self.hc_ffn_fn",
    ))
    try:
        from sglang.kernels.ops.layernorm.mhc_post_combine_norm_prefill import (
            mhc_post_combine_norm_prefill as kern_fused)
        from sglang.kernels.ops.layernorm.mhc_post_combine import (
            mhc_post_combine as kern_pc)
        import sglang.srt.layers.moe.mhc_post_fusion as mhf
        from sglang.srt.environ import envs as engine_envs
        from sglang.srt.runtime_context import (
            get_exec as engine_get_exec,
            get_forward as engine_get_forward,
            get_parallel as engine_get_parallel,
            get_platform as engine_get_platform,
        )
        try:
            from sglang.srt.batch_invariant_ops import (
                is_batch_invariant_mode_enabled as batch_invariant)
        except Exception:
            def batch_invariant():
                return True  # unreadable -> refuse the fused faces
    except Exception as exc:
        raise RuntimeError(
            f"prefill_sp: layer-carry engine anchor import failed "
            f"({exc!r}); refusing to boot"
        ) from None
    use_mhc = _need_source(mhf, "use_mhc_post_fusion", ("_current",))
    # Class seams are fresh objects on every exec of deepseek_v4 (a re-exec
    # rebuilds the classes) -> they must never come back pre-wrapped; the
    # MODULE seam (mhc_post_fusion) survives in sys.modules, so a marker
    # there means our own earlier wrap -- keep it.
    if hcprev is None or hcpc is None or hcpost is None:
        raise RuntimeError(
            "prefill_sp: layer-carry class seams already carry a foreign "
            "wrap; refusing to boot"
        )
    _ENGINE.update(
        hcpc_orig=hcpc,
        hcpost_orig=hcpost,
        mhcpcn=kern_fused,
        mhcpc=kern_pc,
        get_exec=engine_get_exec,
        get_forward=engine_get_forward,
        get_parallel=engine_get_parallel,
        platform_ok=bool(engine_get_platform().is_blackwell),
        g_env=lambda: (
            engine_envs.SGLANG_OPT_USE_TILELANG_MHC_POST.get()
            and not engine_envs.SGLANG_OPT_USE_FLASHINFER_MHC.get()
            and not batch_invariant()
        ),
    )
    layer_cls._hc_post_with_combine = _make_hcpc_wrapper(hcpc)
    layer_cls.hc_post = _make_hcpost_wrapper(hcpost)
    layer_cls.forward_hc_pre_from_prev = _make_layer_hcprev_wrapper(hcprev)
    if use_mhc is not None:
        mhf.use_mhc_post_fusion = _make_use_mhc_wrapper(use_mhc)
    setattr(layer_cls, _LAYERCLS_MARKER, True)
    _state["carry_sites"] = ["dsv4.attn_ar", "dsv4.ffn_ar"]
    _state["installed"].append("layercarry:attn_ar+ffn_ar")
    logger.warning(
        "DSV41 prefill SP stage1 layer-carry sections installed "
        "[reanchor=%s]: dsv4.attn_ar (deepseek_v4.py:2531 attn_tp_all_reduce "
        "-> _hc_post_with_combine :3446) + dsv4.ffn_ar "
        "(moe_tensor_model_parallel_all_reduce via post_experts_all_reduce "
        "deepseek_v2.py:1377 -> hc consumption deepseek_v4.py:3728-3738); "
        "sections sharded onto the RS+AG seam, first-call bit-check vs the "
        "engine's own full-rows methods, permanent stock fallback",
        _REANCHOR_TAG,
    )
    return True


# ------------------------------------------------- deep-carry core (T60)
#
# The mia-form layer-loop replacement (module docstring "DEEPCARRY"):
# DeepseekV4Model._forward_layers_hc_pre_from_prev (mirror deepseek_v4.py:
# 4381-4552) is replaced by the hash-pinned copy `_dc_forward_layers`
# below. Three segments, exactly as the T60 card:
#   A. 0..20 deep-carry region -- R/prev_pre sharded [E,4,5120] across the
#      WHOLE region; per-layer forward_hc_pre_from_prev runs on the shard;
#      attention/MoE cores run full rows behind AG-in wrappers; the two
#      boundary AR leaves run AR+slice (EXACT) / RS (shard); row-local hc
#      sections run on 1/world rows with kernel branches keyed at the FULL
#      row count (sp_logical_rows law).
#   B. layer-21 boundary -- enter_late_layer_tail, plan retired, R/prev_pre
#      gathered to full rows, tail.rows() exactly as stock (:4432-4445).
#   C. 21..end stock tail -- the stock loop body verbatim, hooks inert.
# Wire bytes (ag_byte_account.py): shard form = stock (ring AR=RS+AG);
# EXACT = 1.5x stock (mia §3b EXACT row); the v0 engram island adds
# +AG[R,4,5120] per engram layer (modeled + flagged; v1 removes it).


def _dc_refuse(reason, **kv):
    """T62 trap (min_rows silent stock, doc104 T62 card): every plan
    refusal inside an armed boot is LOUD -- logged once per reason (then
    counted, with a census recount line every 64th occurrence), never a
    silent stock chunk that a census would misread as an engaged SP arm."""
    n = _dc_ctx["refusals"].get(reason, 0) + 1
    _dc_ctx["refusals"][reason] = n
    if n == 1:
        logger.warning(
            "DSV41 prefill SP deepcarry plan REFUSED (%s) %s -- chunk runs "
            "STOCK (refusal #%s; armed boots never fall back silently)",
            reason, kv or "", n,
        )
    elif n % 64 == 0:
        # day-2: periodic recount so a long-running boot's census can read
        # the refusal totals without importing the module (summary() has
        # them too; this is the log-line face of the same table).
        logger.warning(
            "DSV41 prefill SP deepcarry plan refusal tally (%s): %s chunks "
            "ran STOCK for this reason so far", reason, n,
        )


def _dc_mm_inputs_present(forward_batch) -> bool:
    """The engine's OWN runtime multimodal condition (the
    DeepseekV4ForCausalLM.forward form, mirror :5082-5085): mm_inputs
    is not None AND at least one per-request entry is not None.
    SPMD-uniform across TP ranks (scheduler-set before the forward).
    Unreadable shapes count as PRESENT (fail-closed: refuse, never
    silently run an unproven VL face through the EXACT region)."""
    mm = getattr(forward_batch, "mm_inputs", None)
    if mm is None:
        return False
    try:
        return any(x is not None for x in mm)
    except Exception:
        return True


def _dc_a2a_moe() -> bool:
    """Day-5 audit: an a2a MoE backend is structurally incompatible with
    the MoE boundary premise (the post-experts reduction becomes the a2a
    combine; _run_moe_ffn_dp_sync scatters rows per attn-tp rank first,
    deepseek_v4.py:3809-3821). The backend getter is resolved at install
    from the engine module (deepseek_v4 imports get_moe_a2a_backend);
    unreadable = True (fail-closed: the plan refuses, the chunk runs
    stock -- never an unproven boundary face)."""
    getter = _ENGINE.get("get_moe_a2a")
    if getter is None:
        return True
    try:
        backend = getter()
    except Exception:
        return True
    try:
        return not backend.is_none()
    except Exception:
        return True


def _dc_compile_or_deterministic():
    """C2/C3 plan-gate helper (REFDIFF-BUGHUNT-20261003): returns a refusal
    reason string when the boot carries a collective-semantics breaker --
    torch.compiler.is_compiling() (a compiled region must not fork against
    the transcribed eager loop; knapcio _plan :596-597 parity) or
    SGLANG_ENABLE_DETERMINISTIC_INFERENCE (base parallel_state.py:1103-
    1113: reduce_scatter_tensor BECOMES all_reduce+slice there, so the RS
    boundary's semantics silently change class; knapcio _static_check
    :552-553 parity). Returns None when neither is active. Unreadable
    state counts as refusing (fail-closed)."""
    try:
        if torch.compiler.is_compiling():
            return "torch_compiling"
    except Exception:
        return "torch_compiling_unreadable"
    # the engine's envs object reads the SAME process env var
    # (sglang.srt.environ: SGLANG_ENABLE_DETERMINISTIC_INFERENCE is an
    # env-backed setting; parallel_state.py:1103 consumes it), so the
    # os.environ read is the boot-truth face of the key.
    raw = os.environ.get("SGLANG_ENABLE_DETERMINISTIC_INFERENCE",
                         "").strip().lower()
    if raw not in ("", "0", "off", "false", "no"):
        return "deterministic_inference"
    return None


def _dc_cp_or_bcg_active(forward_batch):
    """F3 plan-gate helper (PROD-RS-WHITEBOX-QA-20261003): returns a
    refusal reason string when stock's engram hash face would fork from
    the transcribed plain hasher -- CP live (stock: whole-prompt hash +
    attn-cp rank stride, engine :4394-4403; NOTE the layer-attribute gate
    above refuses dsa_enable_prefill_cp, this reads the RUNTIME
    is_cp_active(forward_batch) the stock loop actually keys on) or a
    breakable cuda graph in flight (stock: bcg_deepseek_v4_engram_hash_
    ids, engine :4406-4411). Both predicates resolved from the SAME
    module objects the model code uses (getattr on the wrapped
    deepseek_v4 module at install); unreadable = refuse. Returns None
    when neither is active."""
    cp_getter = _ENGINE.get("dv4_is_cp_active")
    try:
        if cp_getter is None:
            return "cp_unreadable"
        if cp_getter(forward_batch):
            return "cp_active"
    except Exception:
        return "cp_unreadable"
    bcg = _ENGINE.get("dv4_is_in_bcgraph")
    try:
        if bcg is None:
            return "bcg_unreadable"
        if bcg():
            return "bcg_active"
    except Exception:
        return "bcg_unreadable"
    return None


def _dc_moe_group_world_ok() -> bool:
    """F12/C5 plan-gate helper: the post-experts boundary rides the moe-TP
    leaf, so the moe group's world must equal the attn/TP world the plan's
    E=M/world arithmetic assumes; EP>1 with a2a-none (if the engine ever
    allows it) widens the moe group and the AG would produce E*w rows that
    the [:M] slice silently truncates. Unreadable = refuse (fail-closed)."""
    try:
        group = _ENGINE["get_moe_group"]()
        return group.world_size == _ENGINE["get_parallel"]().tp_size
    except Exception:
        return False


def _dc_build_plan(model, forward_batch, hidden_states, capture_dspark):
    """SPMD-uniform eligibility for the deep-carry region (mia's static
    refusal list + the reanchor _build_carry gates). Every gate reads
    config/batch/shape state identical on all TP ranks, so every rank
    builds the same plan and the collective sequence never forks. Returns
    the plan dict or None (refusal logged via _dc_refuse). capture_dspark
    no longer refuses (day-2: the in-region mean(shard)-then-AG path is
    implemented); the parameter stays for signature stability."""
    try:
        parallel = _ENGINE["get_parallel"]()
        exec_ = _ENGINE["get_exec"]()
    except Exception as exc:
        _dc_refuse("runtime_context_unreadable", exc=exc)
        return None
    reason = None
    cd_reason = _dc_compile_or_deterministic()
    cb_reason = _dc_cp_or_bcg_active(forward_batch)
    rows = hidden_states.shape[0] if hidden_states.dim() == 3 else 0
    world = parallel.tp_size
    layer0 = model.layers[model.start_layer]
    attn = getattr(layer0, "self_attn", None)
    late = getattr(model, "late_layer_start", None)
    fb_mode = getattr(forward_batch, "forward_mode", None)
    try:
        mode_ok = fb_mode is not None and fb_mode.is_extend_without_speculative()
    except Exception:
        mode_ok = False
    if not mode_ok:
        reason = "not_plain_extend_prefill"          # decode/verify/draft never enter
    elif model.pp_group.world_size != 1:
        reason = "pp_gt_1"
    elif parallel.attn_dp_size != 1:
        reason = "attn_dp_gt_1"
    elif parallel.attn_tp_group.world_size != world or world < 2:
        reason = "tp_ne_world"
    elif world != 4:
        reason = "tp_ne_4"                          # the engine's mhc overlap
        #  form hard-gates tp_size == attn_tp_size == 4
        #  (deepseek_v4.py:3607) AND the boundary slice semantics need the
        #  attn-TP group == the TP group (same rank order). Day-5 note:
        #  the boundary itself is now DUAL-FORM (see _dc_boundary_dispatch)
        #  -- the mhc overlap context lighting is NOT a plan premise any
        #  more; the tp4 gate stays as the engine-form + group-identity pin.
    elif getattr(attn, "attn_tp_size", None) != world:
        reason = "attn_tp_ne_tp"
    elif not getattr(attn, "wo_b", None) or not attn.wo_b.reduce_results:
        reason = "wo_b_not_rowparallel_reduce"
    elif getattr(getattr(layer0, "mlp", None), "_shared_expert_tp1", False):
        reason = "shared_expert_tp1"                 # post-AR `+=` (deepseek_v2.py:1370)
    elif getattr(layer0, "use_fused_mhc_post_pre", False):
        reason = "fused_mhc_post_pre"
    elif _dc_a2a_moe():
        reason = "a2a_moe"                           # day-5 audit: under an
        #  a2a backend _run_moe_ffn_dp_sync SCATTERS hidden_states per
        #  attn-tp rank before the experts (deepseek_v4.py:3809-3821) and
        #  the post-experts reduction is the a2a combine, NOT the
        #  moe_tensor_model_parallel_all_reduce leaf -- the MoE boundary
        #  premise (:2553 family) is structurally void. knapcio refuses
        #  the same face (_static_check "_enable_a2a_moe"); production
        #  runs a2a none (EP1 + flashinfer_mxfp4), so this gate is
        #  dormant there (fail-closed, never a runtime guard whack).
    elif getattr(layer0, "hc_mult", None) != 4:
        reason = "hc_mult_ne_4"
    elif getattr(getattr(layer0, "config", None), "model_type", None) != "deepseek_v41":
        reason = "model_type"
    elif _dc_mm_inputs_present(forward_batch):
        reason = "vision_batch"                      # actual multimodal rows
        #  refused (fail-closed). T60 day-4 (R2 zero-activation root
        #  cause): the OLD gate here read config.vision_n_layers -- but
        #  the deployed DeepSeek-V4.1-Flash checkpoint ships
        #  vision_config.num_hidden_layers=32, and the engine's
        #  normalize_deepseek_v41_config (configs/deepseek_v41.py
        #  _VISION_FIELDS setdefault) folds it into
        #  config.vision_n_layers=32 even for TEXT-ONLY serving, so the
        #  static gate refused EVERY chunk of EVERY boot -- activation
        #  structurally 0, the R2 compare "zero-activation red". The
        #  stock image-token torch.where (mirror :4458-4466) is now
        #  TRANScribed row-exactly in segment A (row-pure select, EXACT
        #  rows never split across ranks), so text traffic activates and
        #  stays bit-equal; VL traffic (mm inputs actually present) stays
        #  out of the EXACT comparison domain until a VL-domain needle
        #  boot proves the seam -- knapcio/mia alignment: their
        #  production _plan (knapcio prefill_sp.py :592-620) has NO
        #  vision gate at all and transcribes the where verbatim
        #  (:732) on the same checkpoint family.
    elif getattr(layer0, "dsa_enable_prefill_cp", False):
        reason = "prefill_cp"
    elif bool(getattr(exec_.overlap, "enable_two_batch_overlap", False)):
        reason = "two_batch_overlap"                 # single-slot _dc_ctx
    elif not _ENGINE["platform_ok"]:
        reason = "not_blackwell"
    elif not _ENGINE["g_env"]():
        reason = "fused_env_gate"
    elif late is None or late <= model.start_layer or late > model.end_layer:
        reason = "late_layer_start"                  # the region must exist
        #  (tail may be None: day-2 no-tail exit = the mia :731-733 form,
        #   a pure full gather of R/prev_pre at the region exit;
        #   F2 note: late == end_layer is NOT refused -- the segment-B
        #   switch is stock-isomorphic and classifies it as the no-tail
        #   exit, one census line per boot)
    elif rows < MIN_ROWS:
        reason = "min_rows"                          # the T62 trap gate: LOUD
    elif rows > 65536:
        reason = "rows_gt_65536"
    elif rows % world != 0:
        reason = "rows_not_divisible"                # mia eligible_rows law
    elif tuple(hidden_states.shape) != (rows, 4, 5120):
        reason = "hidden_shape"
    elif hidden_states.dtype != torch.bfloat16 or not hidden_states.is_cuda \
            or not hidden_states.is_contiguous():
        reason = "hidden_dtype_device"
    elif cd_reason:
        # C2/C3 (REFDIFF-BUGHUNT-20261003, knapcio _static_check/_plan
        # parity): the shard boundary is reduce-scatter-or-AR+slice -- a
        # compiled region (torch.compiler.is_compiling) or the
        # deterministic-inference key (base parallel_state.py:1103-1113
        # turns reduce_scatter_tensor into all_reduce+slice) changes the
        # collective semantics this plan was proven under; both refuse
        # (fail-closed, feedback-only on the production arms which are
        # eager + keyless). Unreadable state counts as refusing.
        reason = cd_reason
    elif cb_reason:
        # F3 (PROD-RS-WHITEBOX-QA-20261003): stock's hash faces fork from
        # our transcribed plain hasher when CP is live (stock hashes the
        # whole prompt + rank-strides, engine :4394-4403) or inside a
        # breakable cuda graph (stock uses bcg_deepseek_v4_engram_hash_
        # ids, engine :4406-4411) -- the engram lookup input would differ
        # chunk-wide; refuse (the plan gate reads the engine's own
        # predicates; unreadable = refuse).
        reason = cb_reason
    elif not _dc_moe_group_world_ok():
        # F12/C5 (PROD-RS-WHITEBOX-QA F12 + REFDIFF C5): the post-experts
        # boundary rides the moe-TP leaf -- a moe group wider than the
        # attn-TP group would AG E*w rows and silently truncate to a
        # wrong-shape [M] (the runtime out-rows!=E fail-stop fires only
        # AFTER the MoE cores ran); refusing here is the one-line
        # fail-closed front door. Production EP1+a2a-none keeps
        # moe_tp == tp == world == 4, so this gate is dormant there.
        reason = "moe_group_world"
    if reason is not None:
        _dc_refuse(reason, rows=rows, world=world, min_rows=MIN_ROWS)
        return None
    from sglang.srt.model_executor.forward_context import get_attn_backend
    try:
        # stock :4423 fidelity: the engine checks the late-layer-tail
        # readers before touching the tail metadata -- same call, same
        # order (a raise here is the engine's own refusal, not ours).
        model._check_late_layer_tail_readers(forward_batch)
        attn_backend = get_attn_backend()
        tail = attn_backend.tail_forward_metadata.late_layer_tail
    except Exception as exc:
        _dc_refuse("tail_metadata_unreadable", exc=exc)
        return None
    # tail is None -> the day-2 no-tail plan (mia :731-733): the region
    # exit is a full-row gather, no late-layer switch, stock return triple
    # with None. v0 refused this shape ("tail_none"); the refusal is
    # REMOVED now that the no-tail path is implemented.
    #
    # T61 day-3 -- skip_nonfinal_decoder semantic integration (DEEPCARRY-
    # DESIGN §五-12). The sitecustomize chain wraps THIS loop before us
    # (ungated model-side install); with the loop replaced by
    # _dc_forward_layers the foreign wrapper's end_layer cut can no longer
    # fire on plan-active chunks, so an armed DSV41_SKIP_NONFINAL_DECODER=1
    # boot (the A24 31-key production form carries the key) would run
    # segments B/C on non-final chunks where the stock boot cuts at
    # late_layer_start -- a behavior difference the EXACT gate would
    # misread as OUR divergence. The plan therefore reads the WRAPPER'S
    # OWN decision inputs -- the backend's late_layer_tail_skip stamp plus
    # the wrapper's three guards (extend-without-speculative, not dllm,
    # not inside a breakable cuda graph; adapter skip_nonfinal_decoder.py
    # :477-483 verbatim) -- and _dc_forward_layers reproduces the cut
    # in-segment. Key off = the stamp attribute never exists = False =
    # zero effect on this face. Guards unreadable under an ARMED stamp ->
    # refuse the plan (the stock route keeps the foreign wrapper's own
    # cut): never guess the cut away.
    skip_late_tail = bool(getattr(attn_backend, "late_layer_tail_skip", False))
    if skip_late_tail:
        try:
            skip_late_tail = (
                fb_mode is not None
                and fb_mode.is_extend_without_speculative()
                and not fb_mode.is_dllm_extend()
                and not _ENGINE["dv4_is_in_bcgraph"]()
            )
        except Exception as exc:
            _dc_refuse("skip_flag_unreadable", exc=exc)
            return None
        if skip_late_tail and not _dc_ctx.get("skip_logged"):
            _dc_ctx["skip_logged"] = True
            logger.warning(
                "DSV41 prefill SP deepcarry skip_nonfinal cut REPRODUCED "
                "in-segment (backend late_layer_tail_skip stamp read with "
                "the wrapper's own guards; segment A + full-row gather "
                "exit + dspark standins + None triple; subsequent skip "
                "chunks run quiet)"
            )
    # W5 stage2 layer gate census (gap-verdict §2.3 step 5): one line per
    # boot naming HOW MANY region layers take the MXFP8 AG-in -- the
    # predicate itself (per-call, cached on the attn module) owns the
    # routing; on the production form this reads 17/21 (the kv / index
    # source layers 2/8/14/20 fail compressor/indexer and stay bf16).
    # Unreadable model shape -> the per-call gate still decides (the line
    # is observability, never control).
    if FP8_ATTN and MODE == "stage1" and not _dc_ctx.get("agin_fp8_logged"):
        _dc_ctx["agin_fp8_logged"] = True
        try:
            _n_el = sum(
                1 for _i in range(model.start_layer, late)
                if _dc_fp8_eligible_attn(model.layers[_i].self_attn)
            )
            logger.warning(
                "DSV41 prefill SP deepcarry AG-in fp8 layer gate: %d/%d "
                "region layers eligible (no compressor/indexer + "
                "fuse_wqa_wkv + accepts_mxfp8_swizzled_input; the kv/index "
                "source layers stay bf16)", _n_el, late - model.start_layer,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "DSV41 prefill SP deepcarry AG-in fp8 layer gate: model "
                "shape unreadable (%s: %s) -- the per-call gate decides",
                type(exc).__name__, exc,
            )
    extent = rows // world
    rank = parallel.attn_tp_group.rank_in_group
    return {
        "M": rows,
        "E": extent,
        "world": world,
        "rank": rank,
        "lo": rank * extent,                         # rows % world == 0 (gate)
        "hi": (rank + 1) * extent,
        "exact": bool(EXACT),
        "boundary_ar_slice": _boundary_ar_slice(),    # T62-2 key law (plan face)
        "region_end": late,
        "tail": tail,
        "skip_late_tail": skip_late_tail,
        "attn_backend": attn_backend,
        "group": parallel.attn_tp_group,             # boundary/AG-in group (attn-TP)
        "moe_group": _ENGINE["get_moe_group"](),     # post-experts leaf group
    }


def _dc_boundary(plan, stock_leaf, group, x, site=""):
    """The boundary reduction at an AR leaf while the gathered full-rows
    core is running (inner): the input IS the full-rows partial, so
      EXACT: run the STOCK collective then slice rank rows -- bitwise
             stock by construction (mia :383-384 all_reduce+keep 1/4);
      ar_slice (T62-2 key, shard form): the SAME transparent reduction,
             forced by DSV41_PREFILL_SP_BOUNDARY=ar_slice (T62-F1 §三
             boundary A/B arm -- the T61-proven AR+slice leaves);
      shard (default): reduce-scatter -- the T62 production form (NOT
             bit-equal: reduction order changes).
    site names the leaf that fired (day-5 forensics: attn boundary =
    attn_tp_all_reduce [mhc overlap ON] / tensor_model_parallel_all_
    reduce [OFF, wo_b self-reduce]; moe = the moe leaf; engram = the
    lookup AR) -- the engaged log prints it so a boot's census can tell
    WHICH world every chunk ran in.
    """
    ar_slice = bool(plan.get("exact") or plan.get("boundary_ar_slice"))
    if not _dc_ctx.get("engaged_logged") and _dc_ctx["sublayer"] != "engram":
        _dc_ctx["engaged_logged"] = True
        logger.warning(
            "DSV41 prefill SP deepcarry boundary engaged rank=%s world=%s "
            "M=%s E=%s form=%s leaf=%s (segment-A sublayer boundary: "
            "AG-in + %s)",
            plan["rank"], plan["world"], plan["M"], plan["E"],
            _boundary_form(plan.get("exact"), plan.get("boundary_ar_slice")),
            site or "?",
            "AR+keep-1/4-rows" if ar_slice else "RS",
        )
    if ar_slice:
        full = stock_leaf(x)                          # the verified stock AR
        return full[plan["lo"]:plan["hi"]]
    return rs_shard(group, x)


def _dc_boundary_dispatch(site, stock_leaf, group, x):
    """Leaf-side routing (called from the AR leaf wraps): a boundary
    reduction fires only when a deep-carry plan is active AND the call is
    the current sublayer's boundary site. The attn/moe boundaries fire
    INSIDE the gathered full-rows core (inner=True); the engram lookup
    boundary (day-2, the v1 mia seam) fires with inner=False -- the lookup
    runs on FULL hash ids outside any gathered core, and its AR input is
    the 3-d emb partial [M, n_hash_cols, head_dim] (engine engram.py
    _lookup), which is how it is told apart from every 2-d [M, 5120]
    boundary. Everything else (region-local ARs, stock-loop ARs under a
    refused plan, the island form's own lookup AR with sublayer None) runs
    the stock leaf -- under deep-carry the legacy per-site RS->section->AG
    form is NOT installed (it is the M7 red-flag form)."""
    plan = _dc_ctx["plan"]
    sublayer = _dc_ctx["sublayer"]
    if plan is None or sublayer is None:
        return _NOT_OURS
    if sublayer == "attn":
        if not _dc_ctx["inner"]:
            return _NOT_OURS
        # T61 day-5 (R3 premise fix, the boundary DUAL-FORM): which AR
        # leaf the stock attention core reaches is a RUNTIME form, not a
        # config key. The engine lights the mhc overlap context at the
        # LAYER level (:3604-3617: prefill_overlap = stats_stream is not
        # None -> tp_size==attn_tp_size==4 -> wo_b.reduce_results), and
        # stats_stream (:3423-3430) requires the LAYER's own hidden rows
        # in [4096, 65536] -- but inside this region the layer runs on
        # the SHARD (E = M/world), so the context lights only for
        # M >= 16384 (E >= 4096). On every smaller chunk (the R3 chunk:
        # M=4096, E=1024) the context is OFF: MQALayer.forward calls
        # wo_b with skip_all_reduce=False (:2525-2528, mhc None) and the
        # reduction runs INSIDE RowParallelLinear.forward through ITS
        # leaf (linear.py:1690 -> tensor_model_parallel_all_reduce) --
        # deepseek_v4 :2531 never executes. BOTH leaves receive the same
        # full-rows partial [M, 5120] over the same 4-rank set (the plan
        # gates tp_ne_world / attn_tp_ne_tp pin tp == attn_tp), so the
        # EXACT boundary (stock collective + [lo, hi) slice) is bitwise
        # stock per row in EITHER world -- the knapcio/mia production
        # posture: their wrapper never depends on the mhc context either
        # (knapcio _hook_wo_b forces skip_all_reduce and their
        # _reduce_rows does exactly all_reduce + keep-1/4, mia :383-384).
        sites = ("attn_tp_all_reduce",
                 "tensor_model_parallel_all_reduce")
    elif sublayer == "moe":
        if not _dc_ctx["inner"]:
            return _NOT_OURS
        sites = ("moe_tensor_model_parallel_all_reduce",)
    elif sublayer == "engram":
        if _dc_ctx["inner"]:
            return _NOT_OURS                          # a gathered core's AR
            #  is never the engram lookup (no engram call runs under
            #  inner=True -- the AG-in cores are attention/MoE only)
        sites = ("tensor_model_parallel_all_reduce",)  # engram.py:34/:804
    else:
        return _NOT_OURS
    if site not in sites:
        return _NOT_OURS
    # F9 (PROD-RS-WHITEBOX-QA-20261003): the 2-D boundary face now
    # carries the dtype conjunct too (the family's 门内查形 law: the
    # engram 3-D face below already did) -- a non-bf16 [M, .] AR inside a
    # gathered core is NOT a boundary of this plan even when its shape
    # matches; values would be correct (AR/RS are dtype-agnostic) but the
    # routing law stays one law. Zero effect on the production payloads
    # (every boundary operand is bf16).
    if x.dim() == 2:
        shape_ok = (x.shape[0] == plan["M"]
                    and x.dtype == torch.bfloat16)
    elif sublayer == "engram" and x.dim() == 3:
        # the lookup emb partial: [M, n_hash_cols(=24), head_dim(=256)]
        # bf16 (model config: engram_max_ngram_size 4 / n_heads 8 /
        # head_dim 256 -> 6144 widened elements per row)
        shape_ok = (x.shape[0] == plan["M"]
                    and x.dtype == torch.bfloat16)
    else:
        shape_ok = False
    if not (shape_ok and x.is_contiguous()):
        return _NOT_OURS
    return _dc_boundary(plan, stock_leaf, group, x, site)


def _dc_core_in_ok(plan, x) -> bool:
    """The AG-in gate: the shard input of a region sublayer core."""
    return (
        x.dim() == 2
        and x.shape[0] == plan["E"]
        and x.shape[1] == 5120
        and x.dtype == torch.bfloat16
        and x.is_contiguous()
        and x.is_cuda
    )


def _dc_compare_ref(name, plan, got, ref):
    """DEBUG=compare (day-2 #2, Layer-2 of EXACT-GATE-HARNESS §2.3): the
    白盒定位面. Beside every forced-kernel (logical-rows divergence-band)
    path, run the STOCK full-rows method on AG'd operands -- the reference
    AGs are paid ONLY in this mode -- and torch.equal the rank's sliced
    rows. A mismatch names the segment + output index and is counted into
    _dc_ctx["compare_mismatches"] (summary-readable); it NEVER changes the
    returned value (the forced path's result stands; the harness/tuning
    decides). Layer-1's end-to-end A/B remains the gate; this is the
    segment-level forensics that pinpoints WHICH kernel band drifted."""
    try:
        ref_out = ref()
    except Exception as exc:
        logger.warning(
            "DSV41 prefill SP deepcarry compare[%s]: stock reference run "
            "failed (%s) -- no verdict for this call", name, exc,
        )
        return
    got_t = got if isinstance(got, tuple) else (got,)
    ref_t = ref_out if isinstance(ref_out, tuple) else (ref_out,)
    for idx, (g, r) in enumerate(zip(got_t, ref_t)):
        if not isinstance(g, torch.Tensor) or not isinstance(r, torch.Tensor):
            continue
        rs = (r[plan["lo"]:plan["hi"]]
              if (r.dim() >= 1 and r.shape[0] == plan["M"]) else r)
        if not torch.equal(g, rs):
            n = _dc_ctx["compare_mismatches"].get(name, 0) + 1
            _dc_ctx["compare_mismatches"][name] = n
            logger.error(
                "DSV41 prefill SP deepcarry compare[%s] MISMATCH #%d: "
                "forced-kernel shard output #%d %s != stock full-rows "
                "slice %s (rank rows [%s,%s))", name, n, idx,
                tuple(g.shape), tuple(rs.shape), plan["lo"], plan["hi"],
            )


def _make_dc_attn_wrapper(stock):
    """AG-in wrap of MQALayer.forward (deepseek_v4.py:2098): inside the
    region, the layer forward hands the attention its SHARD x [E,5120];
    the stock core needs full rows -- AG on the attn-TP group, run the
    stock forward under inner=True. The boundary reduction back to the
    shard fires on EITHER stock AR leaf (day-5 dual-form, see
    _dc_boundary_dispatch): mhc overlap ON -> wo_b skips its AR
    (:2529) and the :2531 boundary leaf reduces; OFF (the layer's shard
    rows sit below the engine's 4096-row stats_stream gate, :3423-3430)
    -> wo_b self-reduces through its own leaf (linear.py:1690) and THAT
    call reduces. Positions/forward_batch pass through untouched
    (full-row quantities already).
    W5 (gap-verdict §2.3): on an ELIGIBLE layer with the face armed, the
    AG carries MXFP8 bytes + ue8m0 scales instead of bf16
    (_dc_fp8_input; the x_quant formal feeds wqkv_a the pre-quantized
    tuple) -- the eligibility gate + the per-size triple check own every
    bit-safety premise; every fallback route is the bf16 AG above."""

    def forward(self, x, positions, forward_batch, x_quant=None):
        plan = _dc_ctx["plan"]
        if (plan is None or _dc_ctx["inner"] or x_quant is not None
                or not _dc_core_in_ok(plan, x)):
            return stock(self, x, positions, forward_batch, x_quant=x_quant)
        xq = None
        if FP8_ATTN and MODE == "stage1" and _dc_fp8_eligible_attn(self):
            xq, xb = _dc_fp8_input(plan, self, x)
            x_full = xb
        else:
            x_full = ag_rows(plan["group"], x, plan["M"])
        if xq is not None:
            # NaN canary (community :1291-1294): x is now SHAPE/DTYPE ONLY
            # -- an eligible layer's prefill path reads x solely through
            # wqkv_a(x_quant) (the eligibility predicate), so any stray
            # read would poison the output with NaN instead of passing
            # silently; the first-chunk wqkv_a bit check (and every
            # downstream quality gate) catches it loud.
            x_full = x.new_full((1, 1), float("nan")).expand(
                plan["M"], x.shape[1])
        elif x_full is None:
            x_full = ag_rows(plan["group"], x, plan["M"])  # permanent bf16
        _dc_ctx["inner"] = True
        _dc_ctx["sublayer"] = "attn"
        try:
            out = stock(self, x_full, positions, forward_batch, x_quant=xq)
        finally:
            _dc_ctx["inner"] = False
            _dc_ctx["sublayer"] = None
        if out.shape[0] != plan["E"]:
            # The boundary never fired in EITHER form (mhc overlap ON ->
            # the :2531 attn_tp_all_reduce leaf; OFF -> wo_b's internal
            # RowParallelLinear AR leaf, linear.py:1690) -- e.g. an
            # unknown AR route took the reduction (quant-AR, a foreign
            # wrapper swallowing the leaf, a fuse-flag skip). Continuing
            # would hand the layer a full-rows tensor where every
            # downstream consumer expects the shard. Fail-stop, never a
            # silent form change (the _drop_stash law).
            raise RuntimeError(
                f"prefill_sp deepcarry: attention boundary did not fire "
                f"(out rows {out.shape[0]} != shard E {plan['E']}); the "
                "boundary rides the stock AR leaves in BOTH mhc overlap "
                "forms (deepseek_v4.py:2531 / wo_b self-reduce "
                "linear.py:1690) -- refusing to continue"
            )
        return out

    forward.__name__ = getattr(stock, "__name__", "forward")
    setattr(forward, _DC_ATTN_MARKER, True)
    return forward


def _make_dc_moefn_wrapper(stock):
    """AG-in wrap of DeepseekV4DecoderLayer._run_moe_ffn_dp_sync
    (deepseek_v4.py:3749): same form as the attention -- AG the shard x on
    the MoE-TP group, stock MoE on full rows (router gate included, mia
    law: router stays full-rows), the post-experts AR leaf
    (moe_tensor_model_parallel_all_reduce via post_experts_all_reduce,
    deepseek_v2.py:1377) does the boundary reduction back to the shard.
    The dp-gather / CP / a2a branches inside are dead under the plan gates
    (attn_dp==1, cp off, a2a none)."""

    def _run_moe_ffn_dp_sync(self, hidden_states, forward_batch, *,
                             input_ids, input_ids_global):
        plan = _dc_ctx["plan"]
        if (plan is None or _dc_ctx["inner"]
                or not _dc_core_in_ok(plan, hidden_states)):
            return stock(self, hidden_states, forward_batch,
                         input_ids=input_ids, input_ids_global=input_ids_global)
        group = plan["moe_group"]
        x_full = ag_rows(group, hidden_states, plan["M"])
        _dc_ctx["inner"] = True
        _dc_ctx["sublayer"] = "moe"
        try:
            out = stock(self, x_full, forward_batch, input_ids=input_ids,
                        input_ids_global=input_ids_global)
        finally:
            _dc_ctx["inner"] = False
            _dc_ctx["sublayer"] = None
        if out.shape[0] != plan["E"]:
            raise RuntimeError(
                f"prefill_sp deepcarry: MoE boundary did not fire (out "
                f"rows {out.shape[0]} != shard E {plan['E']}); the "
                "post-experts AR leaf (moe_tensor_model_parallel_all_reduce "
                "via post_experts_all_reduce, deepseek_v2.py:1377) is a plan "
                "premise -- refusing to continue"
            )
        return out

    _run_moe_ffn_dp_sync.__name__ = getattr(
        stock, "__name__", "_run_moe_ffn_dp_sync")
    setattr(_run_moe_ffn_dp_sync, _CARRY_MARKER, True)
    return _run_moe_ffn_dp_sync


# ---- logical-rows wrappers (sp_logical_rows law, mia §1b/1d-2) --------
#
# The engine's row-count-keyed kernel gates read x.shape[0]; on a 1/world
# shard they would re-tile at E rows and pick a DIFFERENT branch than
# stock at M rows -> silent bf16-ulp drift even under EXACT. Law: the
# branch is decided at the FULL row count; when the M-branch and the
# E-branch coincide the stock method is called as-is (no replica drift
# surface); when they diverge the M-branch's kernel is called DIRECTLY on
# the shard operands (all these kernels are row-pure; the row-count
# invariance of the chosen kernel is the residual premise, dual-checked
# by the T61 EXACT gate harness and DEBUG=compare, same law as stage1).
#
# Divergence band analysis (world=4, MIN_ROWS>=2048):
#   _hc_combine fused gate  4096<=rows<=65536: diverges for M in
#     [4096, 16384) (stock fused hc_combine_norm / hc_norm_prefill, shard
#     would take the unfused norm(hc_combine(...)));
#   _hc_mix_stats bf16x3 gate 4096<=rows<=65536 (>=128 gate agrees: E>=512):
#     same band (stock bf16x3, shard deepgemm parts);
#   hc_post's split-h gate x.shape[0]<=384: E=M/4<=384 iff M<=1536 <
#     MIN_ROWS -> branches ALWAYS agree on eligible plans (no wrapper
#     needed; documented, asserted by the plan gate).


def _make_dc_hc_combine_wrapper(stock):
    def _hc_combine(self, x, apply_pre, norm, stats_stream=None,
                    quantized=None, normalized=None, precomputed=None,
                    combined=None):
        plan = _dc_ctx["plan"]
        if (plan is None or _dc_ctx["inner"] or quantized is not None
                or precomputed is not None or normalized is not None):
            # plan inactive / full-rows core / branch-free or unowned
            # faces: stock verbatim
            return stock(self, x, apply_pre, norm, stats_stream=stats_stream,
                         quantized=quantized, normalized=normalized,
                         precomputed=precomputed, combined=combined)
        M, E = plan["M"], x.shape[0]
        dsv41 = getattr(self.config, "model_type", "") == "deepseek_v41"
        fused_stock = dsv41 and 4096 <= M <= 65536
        fused_shard = dsv41 and 4096 <= E <= 65536
        # On an eligible plan fused_shard => fused_stock (E = M/world,
        # M <= 65536 gate), so the only divergence is stock-fused /
        # shard-unfused (M in [4096, 16384) at world 4) -- the band where
        # delegation would silently flip the kernel.
        if combined is not None:
            norm_ok = (norm.weight.dtype == torch.bfloat16
                       and not norm.cast_x_before_out_mul
                       and norm.variance_size_override is None)
            if not fused_stock or not norm_ok or fused_stock == fused_shard:
                return stock(self, x, apply_pre, norm, stats_stream=stats_stream,
                             combined=combined)
            if 4096 <= combined.shape[0] <= 65536:
                from sglang.kernels.ops.layernorm.mhc_post_combine import (
                    hc_norm_prefill)
                ret = hc_norm_prefill(combined, norm.weight,
                                      norm.variance_epsilon)
            else:
                # T61 day-6 (R4 kernel-row wall audit, C3): the divergence
                # band is exactly combined rows below the wrapper's
                # [4096, 65536] dispatch assert (shard rows E = M/world) --
                # run the SAME triton kernel directly (row-per-program;
                # _load_rowfree_norm_faces pins the band to the wrapper):
                # identical per-row arithmetic to the engine's full-rows
                # launch, so the slice stays bitwise stock.
                _dc_rowband_note("hc_combine_combined", combined.shape[0])
                ret = _ENGINE["norm_prefill_rows"](
                    combined, norm.weight, norm.variance_epsilon)
            if DEBUG_COMPARE:
                gr = plan["group"]
                full = {
                    "x": ag_rows(gr, x.contiguous(), plan["M"]),
                    "apply_pre": (ag_rows(gr, apply_pre.contiguous(), plan["M"])
                                  if apply_pre is not None else None),
                    "combined": ag_rows(gr, combined.contiguous(), plan["M"]),
                }
                _dc_compare_ref(
                    "hc_combine:combined", plan, ret,
                    lambda: stock(self, full["x"], full["apply_pre"], norm,
                                  stats_stream=stats_stream,
                                  combined=full["combined"]))
                del full
            return ret
        if apply_pre is None or not fused_stock:
            return stock(self, x, apply_pre, norm, stats_stream=stats_stream)
        x_flat = x.flatten(1)
        # T61 day-10 (R8 dual-onset forensics, T61-DAY10-FORENSIC-20261003
        # §修复一): the apply_pre fused gate must mirror the ENGINE's own
        # predicate conjunct-for-conjunct (deepseek_v4.py :3238-3254) --
        # x.is_cuda + get_platform().is_blackwell + not
        # is_batch_invariant_mode_enabled(). The day-6 wrapper omitted the
        # platform/batch-invariant conjuncts, so on a platform whose
        # is_blackwell reads False (the fleet's SM121 arch-major-12 GPUs:
        # the deepgemm sparse-wire refusal in the boot log is the arch
        # evidence) the SHARD side would launch the fused
        # _hc_combine_norm_prefill kernel on a batch the STOCK side never
        # fuses (stock takes norm(hc_combine(...)) there) -- a
        # same-math-different-kernel pair the EXACT law forbids arming.
        # platform_ok is the install-time is_blackwell read the other hc
        # wrappers already key on (_ENGINE["platform_ok"]); the batch-
        # invariant flag is read LIVE, exactly as the engine reads it at
        # every call.
        from sglang.srt.batch_invariant_ops import (
            is_batch_invariant_mode_enabled as _bi_mode)
        side = (x.is_cuda
                and _ENGINE["platform_ok"]
                and not _bi_mode()
                and self.hc_mult == 4 and x_flat.shape[1] == 20480
                and x.dtype == norm.weight.dtype == torch.bfloat16
                and apply_pre.stride(1) == 1
                and not norm.cast_x_before_out_mul
                and norm.variance_size_override is None)
        gate_stock = side and (0 < M <= 96 or fused_stock)
        gate_shard = side and (0 < E <= 96 or fused_shard)
        if gate_stock == gate_shard:
            return stock(self, x, apply_pre, norm, stats_stream=stats_stream)
        if 4096 <= x_flat.shape[0] <= 65536:
            from sglang.kernels.ops.layernorm.hc_combine_norm import (
                hc_combine_norm)
            ret = hc_combine_norm(x_flat, apply_pre, norm.weight,
                                  norm.variance_epsilon)
        else:
            # T61 day-6 (C2): hc_combine_norm's WRAPPER asserts rows in
            # (0, 96] or [4096, 65536]; the shard sits below 4096 in the
            # divergence band -- run the engine's m>=4096 dispatch kernel
            # directly (_hc_combine_norm_prefill, one CTA per row, launch
            # verbatim via _load_rowfree_norm_faces): the same per-row
            # program stock's full-rows call runs, bitwise on the slice.
            _dc_rowband_note("hc_combine_apply_pre", x_flat.shape[0])
            ret = _ENGINE["combine_norm_prefill_rows"](
                x_flat, apply_pre, norm.weight, norm.variance_epsilon)
        if DEBUG_COMPARE:
            gr = plan["group"]
            full = {
                "x": ag_rows(gr, x.contiguous(), plan["M"]),
                "apply_pre": ag_rows(gr, apply_pre.contiguous(), plan["M"]),
            }
            _dc_compare_ref(
                "hc_combine:apply_pre", plan, ret,
                lambda: stock(self, full["x"], full["apply_pre"], norm,
                              stats_stream=stats_stream))
            del full
        return ret

    _hc_combine.__name__ = getattr(stock, "__name__", "_hc_combine")
    setattr(_hc_combine, _CARRY_MARKER, True)
    return _hc_combine


def _make_dc_hc_mix_stats_wrapper(stock):
    def _hc_mix_stats(self, x, hc_fn, hc_scale, hc_base, stats_stream=None):
        plan = _dc_ctx["plan"]
        if plan is None or _dc_ctx["inner"]:
            return stock(self, x, hc_fn, hc_scale, hc_base,
                         stats_stream=stats_stream)
        M, E = plan["M"], x.shape[0]
        # The production (blackwell bf16) path; the plan gate already
        # refuses non-blackwell boots, so the fallback branches are stock.
        if not (x.is_cuda and torch.version.cuda is not None
                and x.dtype == torch.bfloat16 and _ENGINE["platform_ok"]):
            return stock(self, x, hc_fn, hc_scale, hc_base,
                         stats_stream=stats_stream)
        x_flat = x.flatten(1)
        if not (x_flat.is_contiguous() and _ENGINE["deepgemm_hc_prenorm"]()):
            return stock(self, x, hc_fn, hc_scale, hc_base,
                         stats_stream=stats_stream)      # parts None on both
        parts = bf16_parts = None
        if hc_fn is self.hc_attn_fn:
            parts = getattr(self, "_hc_attn_tf32_parts", None)
            bf16_parts = getattr(self, "_hc_attn_bf16_parts", None)
        elif hc_fn is self.hc_ffn_fn:
            parts = getattr(self, "_hc_ffn_tf32_parts", None)
            bf16_parts = getattr(self, "_hc_ffn_bf16_parts", None)
        # F1 (PROD-RS-WHITEBOX-QA-20261003, P2): the ENGINE's own
        # bf16x3/deepgemm population gate (deepseek_v4.py:3318-3336)
        # requires get_platform().is_sm100 on TOP of parts being populated
        # (population at :2740-2760 only needs ENABLE_JIT_DEEPGEMM + a
        # callable deep_gemm.tf32_hc_prenorm_gemm + model_type -- NOT
        # sm100). On a parts-populated non-sm100 platform (deepgemm
        # exists, JIT usable) the OLD gate keyed big_stock=True at M in
        # [4096,65536] while the stock full-row side (is_sm100 False)
        # took hc_mix_stats_sinkhorn -- exactly the same-math-different-
        # kernel EXACT break day-10 removed from _hc_combine's apply_pre
        # gate (three-conjugate law); this is the residual hole of that
        # family. sm100_ok is the install-time is_sm100 read (mirrors
        # platform_ok); missing key reads False (fail-closed: refuse the
        # forced kernel, never arm it unproven). The env + live batch-
        # invariant conjuncts of the engine gate are already carried by
        # _ENGINE["deepgemm_hc_prenorm"]() above.
        sm100 = _ENGINE.get("sm100_ok", False)
        big_stock = (bf16_parts is not None and sm100
                     and 4096 <= M <= 65536)
        big_shard = (bf16_parts is not None and sm100
                     and 4096 <= E <= 65536)
        if big_stock == big_shard:
            return stock(self, x, hc_fn, hc_scale, hc_base,
                         stats_stream=stats_stream)
        if not big_stock:
            return stock(self, x, hc_fn, hc_scale, hc_base,
                         stats_stream=stats_stream)
        # M-branch bf16x3, E-branch deepgemm-parts: force bf16x3 on the
        # shard, transcribing stock's stream dance (deepseek_v4.py:3300-3370)
        # with the kernel choice keyed at M. T61 day-6 (C6): the engine
        # wrapper asserts rows in [4096, 65536] (mhc.py
        # hc_mix_stats_sinkhorn_bf16x3) -- below the floor the shard is
        # ZERO-PADDED up to 4096 rows and the real rows sliced back out
        # (the kernel is row-pure: the split-K GEMM reduces over k per
        # row, the sinkhorn stage is one program per row; padded rows
        # compute isolated zero-derived values that the slice discards;
        # bit law: each real row's outputs depend only on that row's
        # inputs). Dead on the production platform (SM121 never
        # populates bf16_parts -- sm100-only), kept complete so no latent
        # row assert survives the day-6 audit.
        _dc_rowband_note("hc_mix_stats_bf16x3", x_flat.shape[0])
        from sglang.kernels.ops.layernorm.mhc import hc_mix_stats_sinkhorn_bf16x3
        main_stream = torch.cuda.current_stream()
        kernel_rows = x_flat
        if not 4096 <= x_flat.shape[0] <= 65536:
            kernel_rows = torch.zeros(
                (4096, x_flat.shape[1]), dtype=x_flat.dtype,
                device=x_flat.device)
            kernel_rows[: x_flat.shape[0]] = x_flat
        if stats_stream is not None:
            x.record_stream(stats_stream)
            if kernel_rows is not x_flat:
                kernel_rows.record_stream(stats_stream)
        import contextlib
        with (torch.cuda.stream(stats_stream) if stats_stream is not None
              else contextlib.nullcontext()):
            pre, post, comb = hc_mix_stats_sinkhorn_bf16x3(
                kernel_rows, bf16_parts, hc_scale, hc_base,
                self.hc_sinkhorn_iters, self.rms_norm_eps, self.hc_eps)
            if kernel_rows is not x_flat:
                n = x_flat.shape[0]
                pre, post, comb = pre[:n], post[:n], comb[:n]
        if stats_stream is not None:
            for coefficient in (pre, post, comb):
                coefficient.record_stream(main_stream)
        if DEBUG_COMPARE:
            gr = plan["group"]
            x_full = ag_rows(gr, x.contiguous(), plan["M"])
            _dc_compare_ref(
                "hc_mix_stats:bf16x3", plan, (pre, post, comb),
                lambda: stock(self, x_full, hc_fn, hc_scale, hc_base,
                              stats_stream=stats_stream))
            del x_full
        return pre, post, comb

    _hc_mix_stats.__name__ = getattr(stock, "__name__", "_hc_mix_stats")
    setattr(_hc_mix_stats, _CARRY_MARKER, True)
    return _hc_mix_stats


_HCPOSTC_FUSED_FLOOR = 4096   # the fused band floor (.cuh:167 band low)


def _hcpostc_exact_pad(x, residual, post, comb, pre, norm):
    """T61 day-7 P1 fix helper: the EXACT-mode pad-to-band call. Zero-pads
    every row-keyed operand (x [E,5120] bf16 / residual [E,4,5120] bf16 /
    post [E,4], comb [E,4,4], pre [E,4] fp32 stats) to the 4096-row fused
    floor, runs the SAME fused mhcpcn kernel the stock full-row call runs,
    and slices both outputs back to [0,E). Row-pure law: one CTA per row
    => the padded call's [0,E) rows equal the stock full-row call's [lo,hi)
    rows bitwise (see the wrapper's day-7 comment). Transient memory: the
    padded copies live only inside this call (the EXACT boundary's known
    1.47x byte-account form; the shard/T62 form keeps the decomposed
    route and pays nothing)."""
    floor = _HCPOSTC_FUSED_FLOOR
    e = x.shape[0]

    def _pad(t):
        padded = t.new_zeros((floor,) + tuple(t.shape[1:]))
        padded[:e].copy_(t)
        return padded

    upd_p, nrm_p = _ENGINE["mhcpcn"](
        _pad(x), _pad(residual), _pad(post), _pad(comb), _pad(pre),
        norm.weight, norm.variance_epsilon)
    return upd_p[:e], nrm_p[:e]


def _make_dc_hcpostc_wrapper(stock):
    """Consumption seam (_hc_post_with_combine, deepseek_v4.py:3446): the
    engine G predicate's fused gate `4096 <= x.shape[0] <= 65536` is keyed
    at the FULL row count, then the chosen kernel runs on the shard -- the
    reanchor's _decide_branch/_replica_hc_section pattern, moved from the
    per-site carry into the deep-carry consumption seam."""

    def _hc_post_with_combine(self, x, residual, post, comb, pre,
                              forward_batch, norm=None):
        plan = _dc_ctx["plan"]
        if plan is None or _dc_ctx["inner"]:
            return stock(self, x, residual, post, comb, pre, forward_batch,
                         norm=norm)
        M = plan["M"]
        g = (
            getattr(self.config, "model_type", "") == "deepseek_v41"
            and x.is_cuda and _ENGINE["platform_ok"]
            and 4096 <= M <= 65536
            and forward_batch.forward_mode.is_extend_without_speculative()
            and x.shape[1] == 5120 and self.hc_mult == 4
            and x.dtype == residual.dtype == torch.bfloat16
            and post.dtype == comb.dtype == pre.dtype == torch.float32
            and all(t.is_contiguous() for t in (x, residual, post, comb, pre))
            and _ENGINE["get_parallel"]().attn_dp_size == 1
            and not getattr(_ENGINE["get_forward"](), "sp_active", False)
            and not self.dsa_enable_prefill_cp
            and _ENGINE["g_env"]()
        )
        if not g:
            return stock(self, x, residual, post, comb, pre, forward_batch,
                         norm=norm)          # hc_post branch: gates agree (law)
        # F4 (PROD-RS-WHITEBOX-QA-20261003) / C6 (REFDIFF-BUGHUNT): the
        # engine's INNER fused gate (deepseek_v4.py:3487-3490) requires
        # 16-byte alignment on the WHOLE operand triple
        # (x, residual, norm.weight) -- _norm_prefill_ok covers only the
        # norm module. Shard x/residual are [lo,hi) slices at 40960-byte
        # multiples (fresh allocations elsewhere) so this conjunct is
        # live-never-today, but a future misaligned operand must fall to
        # the engine's own non-fused branch HERE (same gate both sides),
        # not reach the fused launcher and die in its CHECK_HOST.
        operands_aligned = (x.data_ptr() % 16 == 0
                            and residual.data_ptr() % 16 == 0)
        if norm is not None and _norm_prefill_ok(norm) and operands_aligned:
            if 4096 <= x.shape[0] <= 65536:
                upd, nrm = _ENGINE["mhcpcn"](x, residual, post, comb, pre,
                                             norm.weight,
                                             norm.variance_epsilon)
            elif plan.get("exact") and x.shape[0] < 4096:
                # T61 day-7 (R5 compare adjudication, population P1): the
                # R5 first-unequal forensics -- 24/56 pairs at [7,0,0] with
                # stock a=-0.05859375 vs dc b=-0.05126953125 (~2 bf16 ulp),
                # bit-identical across every first-of-prompt chunk and all
                # four ranks -- is the CONSTRUCTIVE ASYMMETRY the day-6
                # decomposed route bought: the A boot's stock loop runs the
                # fused mhcpcn on the full M=4096 rows while the B boot's
                # armed region hands the SAME rows to the engine's
                # decomposed pair (mhcpc + hc_norm_prefill kernel) -- same
                # mathematics, DIFFERENT implementations (CUDA fused vs
                # Triton pair), ulp-level divergence exactly where the
                # audit's C4 residual premise said the two would part. EXACT
                # mode must not constructively break its own domain, so an
                # EXACT plan below the band PADS: zero-pad every row-keyed
                # operand to the 4096 fused floor, run the SAME fused kernel
                # stock runs, slice back [0,E). Row-pure argument (the .cuh
                # header's own contract): the fused kernel assigns ONE CTA
                # PER ROW in all three stages and ports the original Triton
                # per-row reduction with the original BF16 intermediates --
                # row i's outputs are a function of row i's inputs alone
                # (row-count independent, the day-6 law the decomposed pair
                # rides). Both calls are then 4096-row calls of the SAME
                # kernel with identical rows in the compared band (the dc
                # shard's [0,E) rows ARE stock's [lo,hi) rows) => the
                # padded call's [0,E) outputs are BITWISE the stock call's
                # [lo,hi) outputs -- same kernel, same launch config, same
                # per-row arithmetic; the [E,4096) zero rows' own outputs
                # are finite (post*0+comb*0 collapses to 0; rsqrt(0+eps)*0
                # = 0) and discarded by the slice-back. The engine-level
                # bit law is adjudicated by the T61 EXACT harness (R6)
                # exactly as for every forced-kernel path. plan.get("exact")
                # (not plan["exact"]): a plan without the key (day-6-era
                # mock plans, any malformed build) reads as the shard form
                # and keeps the decomposed route -- fail-closed to the
                # proven day-6 arm. The decomposed route below stays for
                # the shard/T62 form (quality gate there does not ride
                # bit-equality); the (upd, None, nrm) triple form is
                # unchanged on both arms.
                _dc_rowband_note("hcpostc", x.shape[0], mode="exact-pad")
                upd, nrm = _hcpostc_exact_pad(x, residual, post, comb, pre,
                                              norm)
            else:
                # T61 day-6 (R4 kernel-row wall, the crash point): the
                # fused kernel's CUDA launcher hard-asserts its input rows
                # in [4096, 65536] (mhc_post_combine_norm_prefill.cuh:167
                # CHECK_HOST "prefill rows must be in [4096, 65536]") --
                # the M-keyed gate above passes at the FULL row count but
                # the kernel receives the SHARD (E = M/world < 4096 for
                # M in [4096, 16384); R4 died at E=1024). Decomposed
                # route = the engine's own non-fused pair: mhc_post_combine
                # (row-free triton wrapper) then the hc_norm_prefill KERNEL
                # (row-per-program; the [4096, 65536] assert lives in the
                # engine's hc_norm_prefill WRAPPER only -- a dispatch
                # band, not a kernel limit). Per-row bit law: the .cuh
                # header documents the fused kernel as a port preserving
                # "the original Triton prefill normalization reduction and
                # PTX arithmetic" with "the original BF16 intermediates",
                # and its stage-1 fma/rounding chain is
                # mhc_post_combine's contraction order -- the pair IS the
                # engine's decomposition of the fused kernel, row-count
                # independent (one CTA per row in all three stages), so
                # the shard rows get bitwise what the fused kernel
                # computes on those rows; residual premise dual-checked by
                # the T61 EXACT harness / DEBUG=compare like every
                # forced-kernel path. Same (updated, None, normalized)
                # triple form as the fused arm -- every consumer face
                # (ffn_normalized flow, next_combined) is unchanged.
                _dc_rowband_note("hcpostc", x.shape[0])
                upd, combd = _ENGINE["mhcpc"](x, residual, post, comb, pre)
                nrm = _ENGINE["norm_prefill_rows"](
                    combd, norm.weight, norm.variance_epsilon)
            ret = (upd, None, nrm)
        else:
            upd, combd = _ENGINE["mhcpc"](x, residual, post, comb, pre)
            ret = (upd, combd, None)
        if DEBUG_COMPARE:
            gr = plan["group"]
            full = [ag_rows(gr, t.contiguous(), plan["M"])
                    for t in (x, residual, post, comb, pre)]
            _dc_compare_ref(
                "hc_post_with_combine:fused", plan, ret,
                lambda: stock(self, full[0], full[1], full[2], full[3],
                              full[4], forward_batch, norm=norm))
            del full
        return ret

    _hc_post_with_combine.__name__ = getattr(
        stock, "__name__", "_hc_post_with_combine")
    setattr(_hc_post_with_combine, _CARRY_MARKER, True)
    return _hc_post_with_combine


def _dc_engram_island(plan, engram, R, hash_ids, forward_batch):
    """v0 / fallback Engram seam (layers 1/14, inside the region):
    gather-island -- AG the shard residual to full rows, run the STOCK
    engram on full rows on every rank (its internal lookup AR fires
    stock-identically on all ranks: sublayer is None here, so the leaf
    dispatch passes it through to the stock AR; the row-cache prefetch
    sees the full hash rows, mia's "lookup unchanged so the prefetch still
    matches" premise), then each rank keeps its own row slice (free -- the
    engram output is complete per row, NOT a partial: no RS here, a row
    slice). Extra wire = one AG of [M,4,5120] per engram layer
    (ag_byte_account.py models it; the v1 mia seam below removes it).
    This is the permanent per-(layer, M) fallback for a failed wkv bit
    check and the DSV41_PREFILL_SP_WKV=full escape form."""
    R_full = ag_rows(plan["group"], R.contiguous(), plan["M"])
    hidden = engram(
        R_full,
        hash_ids[:, engram.layer_hash_index],
        forward_batch,
        cp_all_tokens=False,
    )
    return hidden[plan["lo"]:plan["hi"]]


def _dc_wkv_shard_ok(plan, engram, emb, kv):
    """Per-(engram layer, M) first-block bitwise self-check of the shard
    wkv GEMM (mia :586-606 law: checked, not assumed). The lookup's bit
    equality is by construction (EXACT runs the stock collective then
    slices); the residual premise of the v1 seam is the wkv GEMM's (and
    the gate's) ROW-COUNT invariance -- a GEMM kernel that re-tiles at E
    rows could drift bf16 ulps, so the first block of every (layer, M)
    dual-runs the full-rows reference: one AG of the emb shard (DEBUG-
    grade wire, paid ONCE per (layer, M)), the engine's own wkv on the
    full emb, torch.equal of the rank's sliced rows -- then a TP-group
    agreement vote; any disagreement permanently flips this (layer, M) to
    the island form. The [M, 25600] reference is deleted BEFORE the vote
    collective (mia :595 `del full` law: never hold it across a
    collective). Returns True iff every rank's shard rows are bitwise the
    full-GEMM rows."""
    emb_full = ag_rows(plan["group"], emb.contiguous(), plan["M"])
    kv_full, _ = engram.wkv(emb_full.flatten(-2))
    # F6 (PROD-RS-WHITEBOX-QA-20261003): the compare is wrapped so a
    # SINGLE-rank failure (shape/device raise out of torch.equal) becomes
    # ok=False and flows into the vote -- without the wrap the failing
    # rank skips the all_reduce and the other ranks hang until the
    # watchdog. A disagreement vote = the island fallback (fail-safe).
    try:
        ok = bool(torch.equal(kv_full[plan["lo"]:plan["hi"]], kv))
    except Exception as exc:
        ok = False
        if not _STATE_ONCE.get("wkv_compare_error"):
            _STATE_ONCE["wkv_compare_error"] = True
            logger.error(
                "DSV41 prefill SP wkv shard self-check COMPARE raised "
                f"(layer_hash_index={engram.layer_hash_index}, M="
                f"{plan['M']}, exc={exc!r}) -- voted ok=0 (island fallback "
                "for this (layer, M); first failure only is logged)",
            )
    del kv_full, emb_full
    # F6 capacity census: the [M, 25600] bf16 reference peaks ~3.4 GiB at
    # the 65536 ceiling; one rowband-style line per boot above half the
    # ceiling keeps the transient account census-readable.
    if plan["M"] > 32768:
        _dc_rowband_note("wkv_ref_bigM", plan["M"], mode="decomposed")
    # TP agreement (mia's _agree_min): a SUM vote over the TP group equals
    # the world size iff every rank voted 1 -- for 0/1 flags MIN-agree and
    # SUM==N are the same predicate, and SUM rides the coordinator's own
    # all_reduce (no MIN-op plumbing through an API face we do not own).
    flag = kv.new_zeros((1,), dtype=torch.int32)
    flag.fill_(1 if ok else 0)
    plan["group"].all_reduce(flag)
    return int(flag.item()) == plan["world"]


def _dc_engram(plan, engram, R, hash_ids, forward_batch):
    """v1 mia-form Engram seam (day-2 #1, the头号欠账; layers 1/14 inside
    the region). The lookup stays FULL-ROW -- hash_ids are full rows on
    every rank (the loop hashes the full input_ids), so the row-cache
    prefetch sees exactly stock's ids ("lookup unchanged so the prefetch
    still matches", MIA §1b). The lookup AR -- the wkv-partial reassembly
    over the emb [M, n_hash_cols, head_dim] -- becomes the boundary
    reduction (EXACT: stock AR + rank-row slice; shard: RS), and the
    SECOND stage runs on the shard: wkv GEMM [E, n_hash_cols*head_dim] ->
    [E, hidden*(hc_mult+1)=25600] + gate, both row-local, driven through
    the engine's OWN methods (EngramEmbedding.forward -> _lookup -> the
    wrapped leaf -> _dc_boundary_dispatch sublayer "engram"; engram.wkv;
    the module-level engram_gate on the shard residual R -- the engine-
    image form b97918f4, NOT the overlay copy's apply_gate method form).
    Bit law: lookup = stock
    collective sliced (EXACT, by construction); wkv+gate row-count
    invariance = self-checked per (layer, M) by _dc_wkv_shard_ok with a
    PERMANENT island fallback; the end-to-end face belongs to the T61
    EXACT gate harness. Wire (ag_byte_account.py --engram-form mia): one
    RS of the emb payload replaces the stock AR -- (N-1)/N*S vs
    2(N-1)/N*S, ~-36 MiB/layer at M=4096/N=4; NO residual gather (the
    gate consumes the shard)."""
    key = (engram.layer_hash_index, plan["M"])
    if WKV == "full" or key in _DC_WKV_FAILED:
        return _dc_engram_island(plan, engram, R, hash_ids, forward_batch)
    if not _dc_ctx.get("engram_logged"):
        _dc_ctx["engram_logged"] = True
        logger.warning(
            "DSV41 prefill SP deepcarry engram v1 (mia form) engaged "
            "rank=%s M=%s E=%s exact=%s wkv=shard (lookup full-row, AR->%s, "
            "wkv GEMM+gate on the shard; per-(layer,M) bit self-check with "
            "permanent island fallback; subsequent engram layers run quiet)",
            plan["rank"], plan["M"], plan["E"], plan["exact"],
            _boundary_form(plan.get("exact"), plan.get("boundary_ar_slice")),
        )
    _dc_ctx["sublayer"] = "engram"
    try:
        emb = engram.embed(
            hash_ids[:, engram.layer_hash_index],
            forward_batch,
            cp_all_tokens=False,
        )
    finally:
        _dc_ctx["sublayer"] = None
    if emb.shape[0] != plan["E"]:
        # The lookup boundary never fired (e.g. the engram module's
        # from-imported AR is not the wrapped leaf, or the embed took a
        # non-_lookup branch): downstream would run the wkv GEMM on full
        # rows and hand the gate a [M, ...] kv against an [E, ...] x --
        # fail-stop, never a silent form change (the family law).
        raise RuntimeError(
            f"prefill_sp deepcarry: engram lookup boundary did not fire "
            f"(emb rows {emb.shape[0]} != shard E {plan['E']}); the "
            "EngramEmbedding._lookup -> tensor_model_parallel_all_reduce "
            "route (engram.py:34/:804) is a seam premise -- refusing to "
            "continue"
        )
    kv, _ = engram.wkv(emb.flatten(-2))              # shard GEMM [E,25600]
    if key not in _DC_WKV_CHECKED:
        if _dc_wkv_shard_ok(plan, engram, emb, kv):
            _DC_WKV_CHECKED.add(key)
        else:
            _DC_WKV_FAILED.add(key)
            logger.error(
                "DSV41 prefill SP deepcarry engram wkv SELF-CHECK FAILED "
                "(layer_hash_index=%s M=%s): shard wkv GEMM rows are not "
                "bitwise the full-rows GEMM rows (or a TP rank disagreed) "
                "-- this (layer, M) PERMANENTLY falls back to the "
                "gather-island form (full-row wkv+gate, bit-safe)",
                key[0], key[1],
            )
            return _dc_engram_island(plan, engram, R, hash_ids,
                                     forward_batch)
    # Engine-image form (b97918f4, mock-smoke 20261002): the gate is the
    # MODULE-LEVEL engram_gate(x, kv, q_weight, k_weight, eps, clamp_value)
    # that the engine's own Engram.forward tail calls -- the overlay copy's
    # `self.apply_gate(x, kv)` method form is NOT the engine source (that
    # class has no apply_gate method; calling it would AttributeError in
    # every engram layer of the first armed forward).
    return _ENGINE["engram_gate"](
        R, kv, engram.q_weight, engram.k_weight, engram.eps,
        engram.clamp_value)


def _dc_rowband_note(site, e_rows, mode="decomposed"):
    """day-6 census face (R5-readable), day-7 two-mode split: the first
    below-band route per site AND per mode, once per boot each (quiet
    like the engram v1 banner). mode="decomposed" = the day-6 law (the
    shard/T62 form below the band routes the engine's own non-fused
    pair / row-free kernels); mode="exact-pad" = the T61-R5 P1 fix (an
    EXACT plan below the band PADS rows to the fused floor and keeps
    the SAME fused kernel stock runs, so the A/B pair is same-kernel
    and the EXACT domain is not constructively broken). The two modes
    log distinct banners so the R6 census can verify per site WHICH
    form fired (the p9/p10 law, live) -- not just that the boot
    survived."""
    key = f"rowband_logged_{site}_{mode}"
    if not _dc_ctx.get(key):
        _dc_ctx[key] = True
        if mode == "exact-pad":
            logger.warning(
                "DSV41 prefill SP deepcarry kernel row-band routed rank=%s "
                "site=%s shard_rows=%s below the fused band [4096,65536] -> "
                "EXACT pad-to-band route (zero-pad rows to the 4096 floor + "
                "the SAME fused mhcpcn kernel + slice back [0,E); row-pure "
                "one-CTA-per-row => padded [0,E) rows == the stock full-row "
                "call's rows; mode=exact-pad, decomposed stays for the "
                "shard/T62 form; subsequent routes run quiet)",
                _dc_ctx["plan"]["rank"] if _dc_ctx.get("plan") else -1,
                site, e_rows,
            )
        else:
            logger.warning(
                "DSV41 prefill SP deepcarry kernel row-band routed rank=%s "
                "site=%s shard_rows=%s below the fused band [4096,65536] -> "
                "decomposed route (engine non-fused pair / row-free kernel; "
                "mode=shard-decomposed; subsequent routes run quiet)",
                _dc_ctx["plan"]["rank"] if _dc_ctx.get("plan") else -1,
                site, e_rows,
            )


def _dc_tap_map(start, late):
    """T61 day-9 (R8 layer-verdict fire): the {layer: (tags...)} tap ladder
    for ONE region [start, late). The R7 legacy faces keep their tags and
    calibers: layer == start -> "F1", layer == start + (late - start)//2
    -> "F2" (both FULL volume, dumped for every eligible chunk; a span<=2
    region owns BOTH tags at the same iteration, the day-8 law); every
    other configured layer (TAP_LAYERS) -> "L<layer>" (FIRST-BLOCK only).
    TAP_LAYERS unset -> the R7 two-face map. Layers outside [start, late)
    are DROPPED with a loud once-per-boot banner (an absent tap face then
    surfaces in the harness as pairs=0 = the visible delta branch, never
    a silent miss). Both boots compute the map from the same formula, so
    the two sides agree on WHICH iterations own the taps (the day-8 law)."""
    f1 = start
    f2 = start + (late - start) // 2
    layers = TAP_LAYERS if TAP_LAYERS is not None else (f1, f2)
    out = {}
    dropped = []
    for layer in layers:
        if not (start <= layer < late):
            dropped.append(layer)
            continue
        tags = []
        if layer == f1:
            tags.append("F1")
        if layer == f2:
            tags.append("F2")
        if not tags:
            tags.append(f"L{layer}")
        # a listed layer may already be present (f1 listed explicitly);
        # keep ONE tag tuple per layer (dedup by set semantics).
        if layer not in out:
            out[layer] = tuple(tags)
    if dropped and not _dc_ctx.get("tap_dropped_logged"):
        _dc_ctx["tap_dropped_logged"] = True
        logger.error(
            "DSV41 prefill SP deepcarry TAP_LAYERS out of region: dropped "
            "layers %s (region [start=%s, late=%s)) -- those tap faces will "
            "be ABSENT (visible as pairs=0 in the harness report, the delta "
            "branch; never silently skipped)",
            sorted(dropped), start, late,
        )
    return out


def _dc_first_block(forward_batch):
    """T61 day-9 first-block selection law (R8): True iff EVERY request in
    this extend batch carries NO prefix (seq_lens == extend_seq_lens per
    request) -- a pure first block, the only chunk form with zero
    cross-chunk KV pollution (the R7 verdict: localization must read on
    first blocks; continuation chunks mix their own seed with carried
    state through both the KV and prev_pre channels). Unreadable batch
    fields -> False (fail-closed: no tap dump; the missing face shows in
    the harness rather than a wrong-window face)."""
    try:
        seq = getattr(forward_batch, "seq_lens", None)
        ext = getattr(forward_batch, "extend_seq_lens", None)
        if seq is None or ext is None:
            return False
        seq_l = seq.tolist() if hasattr(seq, "tolist") else list(seq)
        ext_l = ext.tolist() if hasattr(ext, "tolist") else list(ext)
        if not seq_l or len(seq_l) != len(ext_l):
            return False
        return all(s == e for s, e in zip(seq_l, ext_l))
    except Exception:
        return False


def _dc_dump(tag, plan, hidden, prev_pre, face_form=None):
    """DEBUG=dump[:DIR] hook (day-2 #2, EXACT-GATE-HARNESS.md §2.2/§3):
    per-chunk torch.save at the segment-B tail (tag "segB", the values
    entering segment C) and the loop exit (tag "exit"). File contract:
    dc_dump_{rank}_{chunk}_{tag}.pt holding {"tag","chunk","rank","M","E",
    "exact","boundary","hidden","prev_pre"} -- the stock boot's pairing
    face is the dump-only loop bracket (_install_dump_only_loop), same
    tags, same contract; the harness pairs by (rank, chunk, tag). Never
    fatal: a dump failure logs and the forward continues (the hook must
    not change the measured boot).
    T61 day-8 (R6 seed-misattribution verdict, R7 localization fire):
    the tag set grows to the four-face ladder F0/F1/F2/exit -- F0 = the
    region ENTRY (the first region layer's forward input), F1 = after
    the FIRST region layer, F2 = after the MID region layer, and F3 =
    the EXISTING exit face (tag "exit", caliber unchanged). The F0/F1/
    F2 tensors are SHARD-form [E,4,5120] on BOTH boots (the stock
    observer dumps its rank's slice [lo,hi) of the same math point --
    EXACT rows never split across ranks), so face_form="shard" marks
    the contract; segB/exit stay full-row form (face_form None). All
    four faces dump UNCONDITIONALLY per chunk (the gamma-branch ladder
    needs every face's magnitude even when F0 is already unequal)."""
    if DEBUG_DUMP_DIR is None:
        return
    # T61 day-9 serialization law (R8): the dense tap faces (tags "L*")
    # dump a COMPACT CLONE. The R7 F-face files measured 160 MiB for a
    # [1024,4,5120] logical tensor -- torch.save serializes a slice's
    # ENTIRE underlying storage, and .contiguous() is a NO-OP on a rank
    # slice (a row slice of a contiguous tensor is already "contiguous",
    # so rank 0's [lo,hi) view keeps the [M,4,5120] storage riding; the
    # p12 smoke measured this live). .clone() is the true compact copy
    # on EVERY rank. Nine new tap faces at the storage form would add
    # ~65G per fire; cloned they add ~18G. Values are bit-identical (a
    # clone is value-pure); the F0/F1/F2/exit calibers keep the day-8
    # byte form (R7<->R8 continuity of the full-volume faces).
    if tag.startswith("L"):
        hidden = hidden.clone()
        if prev_pre is not None:
            prev_pre = prev_pre.clone()
    try:
        os.makedirs(DEBUG_DUMP_DIR, exist_ok=True)
        path = os.path.join(
            DEBUG_DUMP_DIR,
            f"dc_dump_{plan['rank']}_{_dc_ctx['chunk_idx']}_{tag}.pt",
        )
        torch.save(
            {
                "tag": tag,
                "chunk": _dc_ctx["chunk_idx"],
                "rank": plan["rank"],
                "M": plan["M"],
                "E": plan["E"],
                "exact": plan["exact"],
                "boundary": _boundary_form(plan.get("exact"),
                                           plan.get("boundary_ar_slice")),
                "face_form": face_form,
                "hidden": hidden,
                "prev_pre": prev_pre,
            },
            path,
        )
    except Exception as exc:
        logger.warning(
            "DSV41 prefill SP deepcarry dump (%s) failed: %s", tag, exc,
        )


# ------------------------------------------------- W5 exit tail-row direct
# gather (COMMUNITY-GAP-VERDICT-20261010 §2.4)
#
# The region exit (use_tail AND skip branches) today all-gathers the FULL
# carried R/prev_pre (M-3 in the A23B pre-study census: [1024,4,5120] in /
# [4096,4,5120] out = 40MiB in / 160MiB out per chunk at M=4096, measured
# 6.0ms/chunk) and then -- on the use_tail branch -- slices ~128 tail rows
# out of it. This face gathers ONLY the tail rows: each rank contributes
# its OWN tail rows, the AG carries world*n_tail rows (~13MiB vs 200MiB,
# ~15x), and each tail row is read back from its OWNER's block.
#
# VALUE EQUIVALENCE (the construction the unit test asserts):
#     tail.real_rows(ag_rows(R))  ==  owner-local tail AG
# -- both sides select the SAME row set and produce the SAME bytes per
# row: the full AG concatenates rank blocks in rank order, so
# full[idx] == R_{idx // E}[idx - (idx // E) * E], and that is exactly
# buf[owner, j]. Same row set, same per-row values -- bitwise.
#
# The no-tail branch (a LEGAL full-row consumer: segment C runs full rows
# and the return triple feeds the caller's norm/head over every row) is
# NEVER touched by this face.


def _dc_tail_plan(rows, world, n_tail):
    """Degenerate gate (community tail_plan, knapcio prefill_sp.py:387-
    389): 'full' when gathering all rows is no more traffic than gathering
    world * n_tail rows -- world*n_tail >= rows -> keep the plain full-row
    AG (the tail face would not save wire and only adds the owner
    scatter). Per-chunk decision, collective-uniform (same plan + same
    tail on every rank)."""
    return "full" if world * n_tail >= rows else "owners"


def _dc_tail_owner_local(idx, plan):
    """Owner table RE-DERIVED from THIS file's row partition (verdict
    §2.4 method point 2: do NOT copy the community formula). Our law
    (_dc_build_plan): the plan gate REFUSES rows % world != 0, so
    E = M // world exactly, lo = rank*E, hi = (rank+1)*E, NO zero padding
    -- global row idx lives on rank idx // E at local offset
    idx - (idx // E) * E. The community owner_local computes the same
    integer from ITS shard_range law (s = rows // world with an
    eligible_rows divisibility gate) -- same arithmetic, DIFFERENT
    derivation; ours is derived from plan["E"]/plan["lo"] so it stays
    true to the plan that actually sharded the rows. If a plan ever
    violates the exact-split law (E*world != M), return None and the
    caller falls back to the full-row AG (refuse, never guess)."""
    e = plan["E"]
    if plan["M"] != e * plan["world"]:
        return None
    owner = torch.div(idx, e, rounding_mode="floor")
    return owner, idx - owner * e


def _dc_tail_real_rows(plan, tail, t):
    """tail.real_rows(concat of every rank's shard t) as a byte copy:
    each rank sends ONLY its own tail rows (world*n_tail rows total);
    the gathered buffer is read per row from its OWNER's slot, so the
    out-of-owner slots a rank fills with clamp garbage are never read.
    Degenerate gate / unreadable owner law / n_tail == 0 -> the plain
    full-row AG + slice (the stock form, fail-safe)."""
    if tail.contiguous_start is not None:
        start, idx = int(tail.contiguous_start), None
        n_tail = plan["M"] - start
    else:
        start, idx = None, tail.token_indices
        n_tail = int(idx.shape[0])
    if n_tail == 0 or _dc_tail_plan(plan["M"], plan["world"], n_tail) == "full":
        full = ag_rows(plan["group"], t.contiguous(), plan["M"])
        return full[start:] if idx is None else full[idx]
    if idx is None:
        idx = torch.arange(start, plan["M"], device=t.device)
    ol = _dc_tail_owner_local(idx.to(torch.int64), plan)
    if ol is None:
        full = ag_rows(plan["group"], t.contiguous(), plan["M"])
        return full[start:] if idx is None else full[idx]
    owner, local = ol
    mine = t.contiguous()[local.clamp(0, plan["E"] - 1)].contiguous()
    buf = t.new_empty((plan["world"] * n_tail,) + tuple(t.shape[1:]))
    plan["group"].all_gather_into_tensor(buf, mine)
    buf = buf.view(plan["world"], n_tail, *t.shape[1:])
    return buf[owner, torch.arange(n_tail, device=t.device)]


def _dc_tail_rows(plan, tail, t):
    """tail.rows(...) shape fidelity: real rows + the CP zero pad rows
    (LateLayerTail.rows, deepseek_v4_backend.py:890-896). pad_rows is a
    prefill-CP-only field and CP batches are plan-refused
    (_dc_cp_or_bcg_active -> cd_reason), so it is 0 on every plan that
    reaches here; kept so the tensor shape matches the stock tail.rows
    contract exactly if that ever changes."""
    rows = _dc_tail_real_rows(plan, tail, t)
    if tail.pad_rows:
        rows = torch.cat(
            [rows, rows.new_zeros((tail.pad_rows,) + tuple(rows.shape[1:]))]
        )
    return rows


def _dc_tail_gather_ok(plan):
    """Arm gate for the exit face: key on + deep-carry stage1 + a live
    tail (a None tail has no row set to gather -- the no-tail exit keeps
    its full-row AG)."""
    return bool(TAIL_GATHER and MODE == "stage1" and DEEPCARRY
                and plan.get("tail") is not None)


def _dc_forward_layers(self, positions, hidden_states, forward_batch,
                       input_ids, input_ids_global, capture_dspark,
                       dspark_aux_hidden_states):
    """The hash-pinned layer-loop replacement (segment A/B/C). Transcribed
    from the engine's DeepseekV4Model._forward_layers_hc_pre_from_prev
    (mirror deepseek_v4.py:4381-4552; the install-time needles pin that
    source) with exactly the deep-carry transforms of the T60 card:
    segment A carries R/prev_pre sharded through 0..late_layer_start-1,
    segment B gathers at the late-layer boundary (or at the region exit
    when no tail exists -- mia :731-733), segment C is stock.
    Loop-level row-count gates (next_combined / next_norm) are keyed at
    the FULL row count plan["M"] -- the loop copy owns them, which is the
    whole point of replacing the loop (mia §1c).
    T61 day-3 fourth exit: plan["skip_late_tail"] (the skip_nonfinal
    stamp, _dc_build_plan) takes segment A + the no-tail-style gather
    exit + dspark stand-ins + the None triple -- the wrapper's cut
    reproduced in-segment (see the skip branch below and DEEPCARRY-
    DESIGN §五-12)."""
    from sglang.srt.eplb.expert_distribution import (
        get_global_expert_distribution_recorder,
    )

    assert self.pp_group.world_size == 1, "pre-mix hand-off across PP is not wired"
    plan = _dc_ctx["plan"]
    group = plan["group"]
    tail = plan["tail"]
    _dc_ctx["chunk_idx"] = _dc_ctx.get("chunk_idx", 0) + 1
    # stock hash_ids (mirror :4392-4417): the cp_extend and breakable-graph
    # branches are dead under the plan gates (cp refused, capture refused)
    # -- only the plain engram_hasher branch is live; transcribed verbatim.
    hash_ids = None
    if self.engram_hasher is not None:
        hash_ids = self.engram_hasher(input_ids, forward_batch)

    precomputed_attn = None
    combined_attn = None
    normalized_attn = None
    prev_pre = None
    R = hidden_states[plan["lo"]:plan["hi"]]           # entry split (segment A)

    # T61 day-8 four-face taps (R7 seed-localization fire; DEEPCARRY-DESIGN
    # §十一). F0 = the region ENTRY: the first region layer's forward input
    # (the nearest faithful seam to the ideal "post AG-in" point -- the
    # stock observer has NO equivalent post-AG-in seam without wrapping the
    # stock cores, and the AG-in is a pure rank-order concatenation of the
    # same rows, so the layer-entry tensor IS the same math point for both
    # forms; declared deviation). F1 = after the FIRST region layer
    # (i == start_layer); F2 = after the MID region layer (layer-order
    # midpoint i == start + span//2); F3 = the existing loop-exit face
    # (tag "exit", caliber unchanged). Every face dumps UNCONDITIONALLY --
    # no comparison, no early exit between taps (the gamma ladder needs the
    # per-face magnitudes even when F0 already differs).
    # T61 day-9 (R8 layer-verdict fire, R7 §四): the ladder is PARAMETERIZED
    # (_dc_tap_map / DSV41_PREFILL_SP_TAP_LAYERS) -- the F1/F2 legacy tags
    # keep their full-volume caliber, every other configured layer becomes
    # a dense "L<layer>" tap that dumps FIRST BLOCKS ONLY (the pure-seed
    # law: a first block has no cross-chunk KV pollution; R7 read its
    # localization off faces that mixed both channels).
    _tap_tags = _dc_tap_map(self.start_layer, plan["region_end"])
    _tap_first = _dc_first_block(forward_batch)
    _dc_dump("F0", plan, R, None, face_form="shard")

    # ---------------- segment A: 0..late_layer_start-1 deep-carry region
    for i in range(self.start_layer, plan["region_end"]):
        engram = self.layers[i].engram
        if engram is not None:
            precomputed_attn = None
            combined_attn = None
            normalized_attn = None
            before_engram = R
            R = _dc_engram(plan, engram, R, hash_ids, forward_batch)
            # stock :4458-4466 verbatim, row-translated to the carried
            # shard (T60 day-4, the R2 zero-activation fix): the where
            # selects PER ROW (image-token rows keep before_engram), and
            # EXACT rows never split across ranks, so slicing the
            # condition to [lo, hi) applies the same selection stock
            # applies to exactly those rows -- bitwise equal. The old
            # code omitted this branch and refused the whole plan on
            # config.vision_n_layers>0 ("vision_model"), which the
            # deployed V4.1-Flash checkpoint carries (32) even for
            # text-only serving -- on text rows this where is an
            # identity, on image rows it is stock fidelity.
            if (
                self.config.model_type == "deepseek_v41"
                and self.config.vision_n_layers > 0
            ):
                R = torch.where(
                    (input_ids[plan["lo"]:plan["hi"]]
                     == self.config.image_token_id)[:, None, None],
                    before_engram,
                    R,
                )
        if capture_dspark and i in self.dspark_layers_to_capture:
            # day-2 #4: the in-region dspark capture (stock :4467-4472
            # appends mean over hc copies of the TAIL-ROW slice of the
            # FULL hidden). mean(dim=1) is row-pure (a 4-element hc-copy
            # reduction per (row, col)) and tail.rows is row selection,
            # so mean-then-select == select-then-mean PER ROW, bitwise:
            # each rank means its own shard rows, ONE AG reassembles the
            # [M, 5120] mean, the same tail.rows picks the same rows --
            # equal per row to stock's tail.rows-then-mean (the day-1
            # design note's row-purity argument, now the live path; the
            # plan-gate refusal dspark_capture_in_region is REMOVED).
            aux = ag_rows(group, R.mean(dim=1).contiguous(), plan["M"])
            if tail is not None:
                aux = tail.rows(aux)
            dspark_aux_hidden_states.append(aux)
        ctx = get_global_expert_distribution_recorder().with_current_layer(i)
        next_norm = None
        next_input = []
        # Loop-level collapsed-input gate, keyed at the FULL row count
        # (stock :4482-4498 reads hidden_states.shape[0] -- the shard would
        # re-tile it at E rows). Under a live tail this gate is False in
        # stock too (stock requires tail is None), so the collapsed path
        # stays dead exactly as in stock; on a no-tail plan (day-2 #3) it
        # goes live exactly as in stock -- transcribed for fidelity.
        next_combined = (
            []
            if (
                self.config.model_type == "deepseek_v41"
                and (
                    128 <= plan["M"] <= 384
                    or (
                        4096 <= plan["M"] <= 65536
                        and forward_batch.forward_mode.is_extend_without_speculative()
                    )
                )
                and i + 1 < self.end_layer
                and tail is None
                and self.layers[i + 1].engram is None
            )
            else None
        )
        if next_combined is not None and plan["M"] >= 4096:
            next_norm = self.layers[i + 1].input_layernorm
        # stock :4501-4529 (decode/verify mxfp8 next_norm path): dead on
        # this tree (accepts_mxfp8 false) and in our region by mode; the
        # plan gate (plain extend prefill) keeps it dead -- omitted, see
        # DEEPCARRY-DESIGN §omitted-branches.
        with ctx:
            R, prev_pre = self.layers[i].forward_hc_pre_from_prev(
                positions=positions,        # FULL positions: the AG-in cores
                hidden_states=R,            # run full rows (deep-carry shard
                input_ids=input_ids,        #  residual + full-row metadata)
                forward_batch=forward_batch,
                input_ids_global=input_ids_global,
                prev_pre=prev_pre,          # shard [E,4] or None (region law)
                precomputed_attn=precomputed_attn,
                next_norm=next_norm,
                next_input=next_input,
                combined_attn=combined_attn,
                normalized_attn=normalized_attn,
                next_combined=next_combined,
            )
        precomputed_attn = next_input[0] if next_input else None
        combined_attn, normalized_attn = (
            next_combined[0] if next_combined else (None, None)
        )
        # day-8/day-9 face taps (both guards independent: span<=2 layers
        # dump F1 and F2 at the same iteration, mirroring the stock
        # observer's per-layer face window -- the two boots must agree on
        # WHICH iterations own the faces, never on whether they dump).
        # day-9 law: F1/F2 full volume; every other tap FIRST BLOCK only.
        for _tap_tag in _tap_tags.get(i, ()):
            if _tap_tag in ("F1", "F2") or _tap_first:
                _dc_dump(_tap_tag, plan, R, prev_pre, face_form="shard")

    # ---------------- segment B: layer-21 boundary (mirror :4432-4445)
    if plan.get("skip_late_tail"):
        # T61 day-3 -- the skip_nonfinal cut reproduced IN-SEGMENT (the
        # foreign wrapper cannot fire inside our replacement). Stock-with-
        # skip (adapter wrapper :488-509) temporarily cuts self.end_layer
        # to late_layer_start, so the engine loop runs [start_layer,
        # late_layer_start) only: the tail switch never fires (saved_full
        # stays at its :4426 None), NO enter/exit_late_layer_tail, NO
        # tail.rows row selection, and the return triple carries None
        # (engine :4549-4552, the saved_full-is-None arm); dspark captured
        # layers >= late_layer_start then get full-row mean stand-ins
        # appended after the call (:499-508, the 0.2.9 list-shape
        # contract). The deep-carry equivalent IS the day-2 no-tail exit
        # machinery: full-row gather of the carried R/prev_pre at the
        # region exit, no late-layer switch, None triple -- plus the
        # stand-in republish over the wrapper's [late_layer_start,
        # end_layer) range (self.end_layer is NEVER cut here; the cut was
        # the wrapper's temporary mutation, and the stand-in range must
        # read the UNcut value exactly as the wrapper's saved_end did).
        # next_combined fidelity: stock-with-skip keeps it dead through
        # the `tail is None` conjunct (tail is NOT None under skip -- the
        # backend still builds the metadata, adapter [U6]); segment A's
        # gate carries the same conjunct, and the wrapper's cut-end_layer
        # only ever differed on that conjunct's dead branch -- no
        # divergence. In-region dspark captures keep the tail.rows
        # selection (segment A code above applies it iff tail is not
        # None -- stock :4470-4472 same predicate, i < late always true
        # inside the region).
        _dc_ctx["plan"] = None               # SP hooks retire (nothing follows)
        # W5 §2.4 (exit tail-row direct gather): the skip exit's only
        # row-value consumers are DEAD by contract (the 0.2.9 stand-in
        # law: "Dead values for non-final chunks -- the chunk that
        # finishes the request republishes real values before any
        # drafting reader runs", skip_nonfinal_decoder.py:501-504) and
        # the caller's own continuation -- so the gather carries ONLY
        # the tail rows and the triple carries the tail OBJECT: the
        # engine's own _scatter_tail_rows (deepseek_v4.py:4820-4827,
        # gated on `tail is not None and not capture_dspark`) then
        # rebuilds the full extend layout the logits processor indexes
        # (rows outside the tail are NEVER read --
        # _check_late_layer_tail_readers ran at plan build; non-tail
        # rows are uninitialized bytes exactly as on every stock
        # use_tail chunk). The stand-in means ride the tail-row tensor
        # -- dead values, and the [n_tail] aux-entry shape is the same
        # family stock's use_tail captures publish. Mechanical safety:
        # the caller already handles BOTH row counts from this seam
        # (stock use_tail chunks return [n_tail] with the tail object;
        # no-tail chunks return [M]) -- the skip branch now returns the
        # use_tail-shaped pair instead of the no-tail-shaped one.
        if _dc_tail_gather_ok(plan):
            hidden_states = _dc_tail_rows(plan, plan["tail"], R)
            prev_pre = (_dc_tail_rows(plan, plan["tail"], prev_pre)
                        if prev_pre is not None else None)
            triple = plan["tail"]
        else:
            hidden_states = ag_rows(group, R.contiguous(), plan["M"])
            prev_pre = (ag_rows(group, prev_pre.contiguous(), plan["M"])
                        if prev_pre is not None else None)
            triple = None
        _dc_dump("segB", plan, hidden_states, prev_pre)
        if capture_dspark and self.dspark_layers_to_capture:
            standin = hidden_states.mean(dim=1)
            for j in self.dspark_layers_to_capture:
                if self.late_layer_start <= j < self.end_layer:
                    dspark_aux_hidden_states.append(standin)
        _dc_dump("exit", plan, hidden_states, prev_pre)
        return hidden_states, prev_pre, triple
    # F2 (PROD-RS-WHITEBOX-QA-20261003, P2 -- UNSURE resolved): the
    # backend builds tail_forward_metadata whenever bounded replay is on
    # and the batch is extend-without-speculative (deepseek_v4_backend.py
    # :2326-2331) -- INDEPENDENT of late_layer_start vs end_layer. Stock's
    # window switch is `tail is not None AND i == self.late_layer_start`
    # inside range(start, end) (mirror :4432), so at late == end_layer
    # stock NEVER enters the tail window: saved_full stays None, no
    # enter/exit, full rows throughout, and the return triple carries
    # None (the saved_full-is-None arm, mirror :4549-4552). The old copy
    # keyed the window on `tail is not None` ALONE -- at late == end_layer
    # it entered the window, tail.rows'd the rows and returned the tail
    # object: a double divergence (row count AND triple). The switch is
    # now isomorphic: the window fires iff stock's own `i == late` would
    # fire inside the loop, i.e. tail is not None AND region_end <
    # end_layer; late == end_layer classifies as the day-2 no-tail exit
    # (full-row gather, None triple) with a one-time census line. The
    # in-region dspark tail.rows selection and the next_combined
    # `tail is None` conjunct stay verbatim-stock (at late == end both
    # sides agree on them: i < late always true / dead).
    use_tail = tail is not None and plan["region_end"] < self.end_layer
    if tail is not None and not use_tail:
        if not _dc_ctx.get("late_eq_end_logged"):
            _dc_ctx["late_eq_end_logged"] = True
            logger.warning(
                "DSV41 prefill SP deepcarry late_layer_start == end_layer "
                "(late=%s end=%s) with a live tail metadata -- classified "
                "as the NO-TAIL exit (stock-isomorphic: stock's i == late "
                "never fires inside [start, end), saved_full stays None, "
                "full-row return triple); enter/exit_late_layer_tail NOT "
                "called; subsequent chunks run quiet",
                plan["region_end"], self.end_layer,
            )
    if use_tail:
        combined_attn = None
        normalized_attn = None
        saved_full = plan["attn_backend"].enter_late_layer_tail(forward_batch)
        _dc_ctx["plan"] = None               # SP hooks retire: segment C is stock
        # W5 §2.4 (exit tail-row direct gather): gather ONLY the tail rows
        # (owner-local AG, world*n_tail rows) instead of the full M-row AG
        # + tail.rows slice -- value-equivalent by construction (same row
        # set, same per-row bytes; the unit test asserts it bitwise), the
        # segment C consumers are tail-row consumers by stock design.
        # Degenerate gate (world*n_tail >= M) falls back to the full AG
        # inside _dc_tail_rows. prev_pre's gather routes through the SAME
        # gate (same plan, same tail -> same route on both tensors).
        if _dc_tail_gather_ok(plan):
            hidden_states = _dc_tail_rows(plan, tail, R)
            prev_pre = (_dc_tail_rows(plan, tail, prev_pre)
                        if prev_pre is not None else None)
        else:
            R_full = ag_rows(group, R.contiguous(), plan["M"])
            pre_full = (ag_rows(group, prev_pre.contiguous(), plan["M"])
                        if prev_pre is not None else None)
            hidden_states, prev_pre = tail.rows(R_full), tail.rows(pre_full)
        input_ids, input_ids_global = tail.rows(input_ids), tail.rows(input_ids_global)
        positions = tail.positions
        if hash_ids is not None:
            hash_ids = tail.rows(hash_ids)
    else:
        # day-2 #3 -- the no-tail exit (mia :731-733): stock runs NO
        # late-layer switch when tail is None (mirror :4432 is gated on
        # `tail is not None`), so the boundary is a pure full-row gather
        # of the carried shard at the region exit; the accumulator state
        # (precomputed/combined/normalized) flows into segment C exactly
        # as it flows across iterations inside stock's single loop.
        _dc_ctx["plan"] = None               # SP hooks retire: segment C is stock
        hidden_states = ag_rows(group, R.contiguous(), plan["M"])
        prev_pre = (ag_rows(group, prev_pre.contiguous(), plan["M"])
                    if prev_pre is not None else None)
    _dc_dump("segB", plan, hidden_states, prev_pre)

    # ---------------- segment C: 21..end stock tail (mirror :4446-4548)
    for i in range(plan["region_end"], self.end_layer):
        engram = self.layers[i].engram
        if engram is not None:
            precomputed_attn = None
            combined_attn = None
            normalized_attn = None
            before_engram = hidden_states
            hidden_states = engram(
                hidden_states,
                hash_ids[:, engram.layer_hash_index],
                forward_batch,
                cp_all_tokens=False,
            )
            if (
                self.config.model_type == "deepseek_v41"
                and self.config.vision_n_layers > 0
            ):
                hidden_states = torch.where(
                    (input_ids == self.config.image_token_id)[:, None, None],
                    before_engram,
                    hidden_states,
                )
        if capture_dspark and i in self.dspark_layers_to_capture:
            # stock-verbatim (:4467-4472): segment C runs on tail rows (or
            # full rows on a no-tail plan) already -- the `i < late`
            # tail.rows branch of stock is dead here by construction.
            aux = hidden_states
            dspark_aux_hidden_states.append(aux.mean(dim=1))
        ctx = get_global_expert_distribution_recorder().with_current_layer(i)
        next_norm = None
        next_input = []
        next_combined = (
            []
            if (
                self.config.model_type == "deepseek_v41"
                and (
                    128 <= hidden_states.shape[0] <= 384
                    or (
                        4096 <= hidden_states.shape[0] <= 65536
                        and forward_batch.forward_mode.is_extend_without_speculative()
                    )
                )
                and i + 1 < self.end_layer
                and tail is None
                and self.layers[i + 1].engram is None
            )
            else None
        )
        if next_combined is not None and hidden_states.shape[0] >= 4096:
            next_norm = self.layers[i + 1].input_layernorm
        with ctx:
            hidden_states, prev_pre = self.layers[i].forward_hc_pre_from_prev(
                positions=positions,
                hidden_states=hidden_states,
                input_ids=input_ids,
                forward_batch=forward_batch,
                input_ids_global=input_ids_global,
                prev_pre=prev_pre,
                precomputed_attn=precomputed_attn,
                next_norm=next_norm,
                next_input=next_input,
                combined_attn=combined_attn,
                normalized_attn=normalized_attn,
                next_combined=next_combined,
            )
        precomputed_attn = next_input[0] if next_input else None
        combined_attn, normalized_attn = (
            next_combined[0] if next_combined else (None, None)
        )
    _dc_dump("exit", plan, hidden_states, prev_pre)
    # F2: the return keys on the SAME isomorphic predicate (stock keys on
    # saved_full is not None, which is True exactly when the window fired).
    if use_tail:
        plan["attn_backend"].exit_late_layer_tail(saved_full, forward_batch)
        return hidden_states, prev_pre, tail
    return hidden_states, prev_pre, None                # stock :4552 verbatim


def _make_dc_loop_wrapper(stock_loop):
    """The DeepseekV4Model._forward_layers_hc_pre_from_prev bracket: build
    the plan (loud refusal on ineligibility -- T62 trap), run the
    replacement copy under the plan context, retire it on exit."""

    def _forward_layers_hc_pre_from_prev(self, *args, **kwargs):
        if not _state["active"] or not _deepcarry_armed():
            return stock_loop(self, *args, **kwargs)
        capture_dspark = kwargs.get("capture_dspark")
        if capture_dspark is None and len(args) >= 6:
            capture_dspark = args[5]
        hidden_states = kwargs.get("hidden_states")
        if hidden_states is None and len(args) >= 2:
            hidden_states = args[1]
        forward_batch = kwargs.get("forward_batch")
        if forward_batch is None and len(args) >= 3:
            forward_batch = args[2]
        plan = _dc_build_plan(self, forward_batch, hidden_states,
                              bool(capture_dspark))
        if plan is None:
            return stock_loop(self, *args, **kwargs)
        _dc_ctx["plan"] = plan
        if not _dc_ctx.get("enter_logged"):
            _dc_ctx["enter_logged"] = True
            logger.warning(
                "DSV41 prefill SP deepcarry region ENTER rank=%s M=%s E=%s "
                "layers=[%s,%s) exact=%s [%s] (segments A/B/C; boundary=%s; "
                "engram=v1 mia-form wkv=%s; tail=%s; skip_late_tail=%s; "
                "subsequent chunks run quiet)",
                plan["rank"], plan["M"], plan["E"], self.start_layer,
                plan["region_end"], plan["exact"], _DEEPCARRY_TAG,
                _boundary_form(plan.get("exact"),
                               plan.get("boundary_ar_slice")), WKV,
                "yes" if plan["tail"] is not None else "none (exit gather)",
                "cut" if plan.get("skip_late_tail") else "no",
            )
        try:
            return _dc_forward_layers(
                self,
                kwargs.get("positions") if "positions" in kwargs else (
                    args[0] if args else None),
                hidden_states,
                forward_batch,
                kwargs.get("input_ids") if "input_ids" in kwargs else (
                    args[3] if len(args) > 3 else None),
                kwargs.get("input_ids_global") if "input_ids_global" in kwargs else (
                    args[4] if len(args) > 4 else None),
                bool(capture_dspark),
                kwargs.get("dspark_aux_hidden_states") if "dspark_aux_hidden_states" in kwargs else (
                    args[6] if len(args) > 6 else None),
            )
        finally:
            _dc_ctx["plan"] = None

    _forward_layers_hc_pre_from_prev.__name__ = getattr(
        stock_loop, "__name__", "_forward_layers_hc_pre_from_prev")
    setattr(_forward_layers_hc_pre_from_prev, _DC_MODEL_MARKER, True)
    return _forward_layers_hc_pre_from_prev


# Deep-carry needles: every seam the replacement stacks on is pinned to
# the engine source at install (fail-stop on drift, the family law). All
# needles verified present in mirror main-79cafec0 (REANCHOR-NOTES §2).
_DC_LOOP_NEEDLES = (
    "assert self.pp_group.world_size == 1",
    "self.engram_hasher(input_ids, forward_batch)",
    "self._check_late_layer_tail_readers(forward_batch)",
    "attn_backend.tail_forward_metadata.late_layer_tail",
    "saved_full = attn_backend.enter_late_layer_tail(forward_batch)",
    "tail.rows(hidden_states)",
    "tail.rows(hash_ids)",
    "dspark_aux_hidden_states.append(aux.mean(dim=1))",
    "128 <= hidden_states.shape[0] <= 384",
    "next_norm = self.layers[i + 1].input_layernorm",
    "forward_hc_pre_from_prev(",
    "precomputed_attn = next_input[0] if next_input else None",
    "attn_backend.exit_late_layer_tail(saved_full, forward_batch)",
    "return hidden_states, prev_pre, None",
    # F3 (PROD-RS-WHITEBOX-QA-20261003): pin the two loop branches our
    # transcription REPLACED with the plain form -- the bcg hash face
    # (engine :4406-4411; the plan gate now refuses a live bcg) and the
    # TC_PIECEWISE nullcontext ctx (engine :4473-4476; we always run the
    # recorder ctx -- a base bump that moves either face refuses the
    # boot instead of silently forking the hash/recorder semantics).
    "bcg_deepseek_v4_engram_hash_ids(",
    "check_cuda_graph_backend(Phase.PREFILL, Backend.TC_PIECEWISE)",
)
_DC_MOEFN_NEEDLES = (
    "_use_tp_moe_gather",
    "mlp_reduce_scatter = _use_cp or _use_reduce_scatterv or _use_reduce_scatter",
    "dp_gather_replicate(hidden_states, local_hidden_states, forward_batch)",
)
_DC_COMBINE_NEEDLES = (
    "hc_combine_norm",
    "hc_norm_prefill",
    "apply_pre.stride(1) == 1",
)
_DC_STATS_NEEDLES = (
    "hc_mix_stats_sinkhorn_bf16x3",
    "hc_mix_stats_sinkhorn_deepgemm",
    "x_flat.shape[0] >= 128",
)
_DC_ATTN_NEEDLES = (
    "skip_all_reduce=mhc is not None",
    "o = attn_tp_all_reduce(o)",
    "mhc.start_stats_before_all_reduce()",
    "if self.attn_tp_size > 1 and self.attn_tp_size < get_parallel().tp_size:",
)
# day-2: the engram v1 seam rides Engram.forward's three-line structure
# (embed -> wkv -> gate) and EngramEmbedding._lookup's owned-rows +
# module-global AR. NEEDLE SOURCE CORRECTED (mock-smoke 20261002, T61
# pre-boot): the ENGINE IMAGE's sglang/srt/layers/engram.py (md5
# b97918f4547f0df3f226dd0740171634) is the source every boot executes --
# sitecustomize's EngramLoader WRAPS the image module's exec, it does not
# load the overlay. The overlay copy (f51e4311, four-machine aligned) is
# an OLDER variant whose self.apply_gate(x, kv) METHOD-form tail does
# NOT exist on the engine class (engine tail = module-level engram_gate
# dispatch). F3 repinned to the engine's gate-argument line; see
# mirror/engram-ref/ENGRAM-NEEDLE-REF-20261002.md (erratum).
_DC_ENGRAM_FWD_NEEDLES = (
    "emb = self.embed(hash_ids, forward_batch, cp_all_tokens=cp_all_tokens)",
    "kv, _ = self.wkv(emb.flatten(-2))",
    "x, kv, self.q_weight, self.k_weight, self.eps, self.clamp_value",
)
_DC_ENGRAM_LOOKUP_NEEDLES = (
    "values = self._owned_rows(indices)",
    "values = tensor_model_parallel_all_reduce(values)",
)


def _install_deep_carry(module) -> bool:
    """Install the deep-carry form (T60): the layer-loop replacement + the
    AG-in wrappers + the logical-rows hc wrappers, on the deepseek_v4
    module's classes. Arms ONLY under stage1+DEEPCARRY; any seam drift
    refuses the boot (fail-stop). The METHOD seams are probed at class
    level and the INSTANCE-attribute seams via _need_init_source -- the
    reanchor's corrected two-level probe law, carried over verbatim."""
    model_cls = getattr(module, "DeepseekV4Model", None)
    layer_cls = getattr(module, "DeepseekV4DecoderLayer", None)
    attn_cls = getattr(module, "MQALayer", None)
    if model_cls is None or layer_cls is None or attn_cls is None:
        raise RuntimeError(
            "prefill_sp: deep-carry seam moved (DeepseekV4Model / "
            "DeepseekV4DecoderLayer / MQALayer missing from the "
            "deepseek_v4 module); refusing to boot"
        )
    if getattr(model_cls, _DC_MODEL_MARKER, False):
        return False  # already installed (double exec of the module)
    # C1: the co-install law runs FIRST (before any seam wrap): an armed
    # DSV41_HC_FUSED boot whose hc_fused cannot import or resolved its
    # fallback logical-rows helper refuses here, with the key/reason/
    # remedy spelled out (see _check_hc_fused_coinstall).
    _check_hc_fused_coinstall()
    loop = _need_source(model_cls, "_forward_layers_hc_pre_from_prev",
                        _DC_LOOP_NEEDLES)
    moefn = _need_source(layer_cls, "_run_moe_ffn_dp_sync",
                         _DC_MOEFN_NEEDLES)
    combine = _need_source(layer_cls, "_hc_combine", _DC_COMBINE_NEEDLES)
    stats = _need_source(layer_cls, "_hc_mix_stats", _DC_STATS_NEEDLES)
    hcpostc = _need_source(layer_cls, "_hc_post_with_combine",
                           ("mhc_post_combine_norm_prefill",
                            "mhc_post_combine",
                            "hc_post(x, residual, post, comb)",
                            "4096 <= x.shape[0] <= 65536"))
    attn_fwd = _need_source(attn_cls, "forward", _DC_ATTN_NEEDLES)
    # day-2 #1: the engram v1 seam stacks on the ENGINE's engram module
    # (already imported by deepseek_v4.py:105 by this exec). Pin its
    # structure fail-stop: Engram.forward's three lines are the seam's
    # structure (embed -> boundary-reduced emb -> wkv -> engram_gate on
    # the shard) and EngramEmbedding._lookup's owned-rows + module-global
    # AR is the route the boundary dispatch's "engram" slot rides. Needle
    # source = the ENGINE IMAGE's module (b97918f4; the overlay copy
    # f51e4311 is an older variant -- mock-smoke 20261002 erratum, see
    # mirror/engram-ref/ENGRAM-NEEDLE-REF-20261002.md); nothing is
    # wrapped on the engram module -- the seam rides the stock path and
    # the already-installed AR leaf wrap. The GATE itself resolves at
    # install (fail-closed): the engine-image form is the module-level
    # engram_gate(x, kv, q_weight, k_weight, eps, clamp_value); the
    # overlay's apply_gate METHOD does not exist on the engine class.
    try:
        import sglang.srt.layers.engram as engram_module
    except Exception as exc:
        raise RuntimeError(
            f"prefill_sp: sglang.srt.layers.engram import failed ({exc!r}); "
            "refusing to boot (the deep-carry engram v1 seam stacks on it)"
        ) from None
    engram_cls = getattr(engram_module, "Engram", None)
    embed_cls = getattr(engram_module, "EngramEmbedding", None)
    if engram_cls is None or embed_cls is None:
        raise RuntimeError(
            "prefill_sp: engram seam moved (Engram / EngramEmbedding "
            "missing from sglang.srt.layers.engram); refusing to boot"
        )
    _need_source(engram_cls, "forward", _DC_ENGRAM_FWD_NEEDLES)
    _need_source(embed_cls, "_lookup", _DC_ENGRAM_LOOKUP_NEEDLES)
    _dc_engram_gate = getattr(engram_module, "engram_gate", None)
    if not callable(_dc_engram_gate):
        raise RuntimeError(
            "prefill_sp: engram seam moved (module-level engram_gate "
            "missing from sglang.srt.layers.engram -- the engine-image "
            "gate dispatch; an apply_gate METHOD form is a non-engine "
            "source); refusing to boot"
        )
    # C11 (REFDIFF-BUGHUNT-20261003, high-confidence fact / low impact):
    # the MoE boundary premise is "the post-experts AR leaf always fires"
    # -- enforced at runtime by the out-rows!=E fail-stop, but the CALL
    # SITE itself had no install-time pin. Upstream #42301/#42312 are
    # refactoring exactly this face (stage-boundary as sole sum executor,
    # reduction-skip family removed); this needle makes a base bump that
    # moves the call refuse the BOOT instead of waiting for the runtime
    # tripwire (fail-closed front door, zero effect on this base).
    try:
        import sglang.srt.models.deepseek_v2 as _v2mod
    except Exception as exc:
        raise RuntimeError(
            f"prefill_sp: sglang.srt.models.deepseek_v2 import failed "
            f"({exc!r}); refusing to boot (the MoE boundary premise pin)"
        ) from None
    _v2moe_cls = getattr(_v2mod, "DeepseekV2MoE", None)
    if _v2moe_cls is None:
        raise RuntimeError(
            "prefill_sp: DeepseekV2MoE missing from "
            "sglang.srt.models.deepseek_v2; refusing to boot (the MoE "
            "boundary premise pin)"
        )
    _need_source(_v2moe_cls, "forward_normal", (
        "final_hidden_states = post_experts_all_reduce(final_hidden_states)",
    ))
    # METHOD seams stay class-level hasattr (the reanchor law); the
    # INSTANCE-attribute seams move to _need_init_source (6 needles).
    for attr in ("_hc_mix_stats", "_run_moe_ffn_dp_sync", "_build_self_attn",
                 "_hc_combine"):
        if not hasattr(layer_cls, attr):
            raise RuntimeError(
                f"prefill_sp: DeepseekV4DecoderLayer.{attr} missing; "
                "refusing to boot (deep-carry seam moved)"
            )
    _need_init_source(layer_cls, (
        "self.self_attn = self._build_self_attn(",
        "self.mlp = deepseek_v2.DeepseekV2MoE(",
        "self.input_layernorm = RMSNorm(",
        "self.post_attention_layernorm = RMSNorm(",
        "self.hc_attn_fn",
        "self.hc_ffn_fn",
    ))
    try:
        import sglang.srt.distributed.communication_op as comm_op
        from sglang.srt.environ import envs as engine_envs
        from sglang.srt.runtime_context import (
            get_exec as engine_get_exec,
            get_forward as engine_get_forward,
            get_parallel as engine_get_parallel,
            get_platform as engine_get_platform,
        )
        try:
            from sglang.srt.batch_invariant_ops import (
                is_batch_invariant_mode_enabled as batch_invariant)
        except Exception:
            def batch_invariant():
                return True  # unreadable -> refuse the fused faces
        deepgemm_prenorm = lambda: bool(
            engine_envs.SGLANG_OPT_DEEPGEMM_HC_PRENORM.get()
            and not batch_invariant())
    except Exception as exc:
        raise RuntimeError(
            f"prefill_sp: deep-carry engine anchor import failed ({exc!r}); "
            "refusing to boot"
        ) from None
    if loop is None or moefn is None or combine is None or stats is None \
            or hcpostc is None or attn_fwd is None:
        raise RuntimeError(
            "prefill_sp: deep-carry class seams already carry a foreign "
            "wrap; refusing to boot"
        )
    _ENGINE.update(
        hcpc_orig=hcpostc,
        get_exec=engine_get_exec,
        get_forward=engine_get_forward,
        get_parallel=engine_get_parallel,
        platform_ok=bool(engine_get_platform().is_blackwell),
        # F1: the engine's deepgemm/bf16x3 population gate reads
        # is_sm100 LIVE per call (deepseek_v4.py:3323); resolved once at
        # install like platform_ok (the arch cannot change under a boot).
        sm100_ok=bool(engine_get_platform().is_sm100),
        get_moe_group=comm_op.get_moe_tp_group,
        # day-5: the a2a refusal gate's engine face (deepseek_v4 imports
        # get_moe_a2a_backend at its top; resolved from the SAME module
        # object the model code uses, never a re-import)
        get_moe_a2a=getattr(module, "get_moe_a2a_backend", None),
        deepgemm_hc_prenorm=deepgemm_prenorm,
        engram_gate=_dc_engram_gate,
        # T61 day-3: the skip_nonfinal cut predicate's engine faces,
        # resolved from the SAME module objects the foreign adapter's
        # wrapper uses (deepseek_v4 imports both, :139-/:151) -- the plan
        # builder reproduces the wrapper's guards verbatim with them.
        dv4_is_in_bcgraph=getattr(module, "is_in_breakable_cuda_graph", None),
        # F3: the runtime CP predicate the stock loop keys its hash face
        # on (deepseek_v4 imports is_cp_active; the plan gate reads it
        # through the SAME module object the model code uses)
        dv4_is_cp_active=getattr(module, "is_cp_active", None),
        g_env=lambda: (
            engine_envs.SGLANG_OPT_USE_TILELANG_MHC_POST.get()
            and not engine_envs.SGLANG_OPT_USE_FLASHINFER_MHC.get()
            and not batch_invariant()
        ),
    )
    if "mhcpcn" not in _ENGINE or "mhcpc" not in _ENGINE:
        from sglang.kernels.ops.layernorm.mhc_post_combine_norm_prefill import (
            mhc_post_combine_norm_prefill as kern_fused)
        from sglang.kernels.ops.layernorm.mhc_post_combine import (
            mhc_post_combine as kern_pc)
        _ENGINE.update(mhcpcn=kern_fused, mhcpc=kern_pc)
    if "norm_prefill_rows" not in _ENGINE:
        # T61 day-6 (R4 kernel-row wall): the row-band-free launch faces
        # for the two prefill norm kernels -- resolved with module source
        # needles and fail-closed (_load_rowfree_norm_faces). The
        # decomposed routes read them from _ENGINE only (offline unit
        # tests stub the slots, never the import).
        norm_rows, combine_norm_rows = _load_rowfree_norm_faces()
        _ENGINE.update(norm_prefill_rows=norm_rows,
                       combine_norm_prefill_rows=combine_norm_rows)
    layer_cls._hc_combine = _make_dc_hc_combine_wrapper(combine)
    layer_cls._hc_mix_stats = _make_dc_hc_mix_stats_wrapper(stats)
    layer_cls._hc_post_with_combine = _make_dc_hcpostc_wrapper(hcpostc)
    layer_cls._run_moe_ffn_dp_sync = _make_dc_moefn_wrapper(moefn)
    attn_cls.forward = _make_dc_attn_wrapper(attn_fwd)
    model_cls._forward_layers_hc_pre_from_prev = _make_dc_loop_wrapper(loop)
    setattr(model_cls, _DC_MODEL_MARKER, True)
    _state["installed"].append(
        "deepcarry:loop+attn_agin+moe_agin+hc_logical_rows+engram_v1+"
        "no_tail_exit+dspark_mean_ag+dump/compare_hooks")
    logger.warning(
        "DSV41 prefill SP DEEPCARRY installed [%s/%s]: layer-loop "
        "replacement on DeepseekV4Model._forward_layers_hc_pre_from_prev "
        "(mirror :4381-4552, %d needles) + AG-in wraps (MQALayer.forward "
        ":2098, _run_moe_ffn_dp_sync :3749) + logical-rows hc wraps "
        "(_hc_combine :3192, _hc_mix_stats :3279, _hc_post_with_combine "
        ":3446) + _need_init_source 6 needles; boundary=%s; engram=v1 "
        "(mia form: wkv=%s, per-(layer,M) bit self-check, island fallback; "
        "seam needles %d+%d) + no-tail exit gather (mia :731-733) + "
        "in-region dspark mean-then-AG + DEBUG faces (%s); STAGE key off "
        "= zero load",
        _DEEPCARRY_TAG, _REANCHOR_TAG, len(_DC_LOOP_NEEDLES),
        _boundary_form(EXACT, BOUNDARY == "ar_slice", long_form=True), WKV,
        len(_DC_ENGRAM_FWD_NEEDLES), len(_DC_ENGRAM_LOOKUP_NEEDLES),
        (f"dump={DEBUG_DUMP_DIR}" if DEBUG_DUMP_DIR
         else "compare" if DEBUG_COMPARE else "off"),
    )
    # T61 day-3 coexistence banner (stackwall fix; DEEPCARRY-DESIGN §五-12):
    # states, per boot, how the install-order foreign wrappers are handled
    # -- needle verification face + both runtime routes. Census-readable.
    logger.warning(
        "DSV41 prefill SP deepcarry skip_nonfinal coexistence [%s/T61-day3]: "
        "install-order foreign wraps unwrapped for the seam needles "
        "(chain TERMINAL source; an unidentifiable wrapper refuses the "
        "boot); refused-plan chunks route through the foreign wrapper "
        "verbatim (its end_layer cut + key semantics preserved on the "
        "stock route); plan-active chunks reproduce the skip_nonfinal cut "
        "in-segment (segment A + full-row gather exit + dspark standins; "
        "DSV41_SKIP_NONFINAL_DECODER off = zero effect)",
        _DEEPCARRY_TAG,
    )
    # 用户令④ self-check boot segment: the invariant matrix runs AFTER
    # the wraps land (so its engine-anchor and co-install rows read the
    # installed state); any red row REFUSES the boot (fail-closed -- the
    # matrix is the consolidated-v2 certificate, never advisory).
    _sc_ok, _sc_rows = self_check(report=logger.warning)
    if not _sc_ok:
        _bad = "; ".join(f"{n} -> {r}" for n, g, r in _sc_rows if not g)
        raise RuntimeError(
            f"prefill_sp: boot invariant SELF-CHECK RED ({_bad}); "
            "refusing to boot -- run `python3 prefill_sp.py --self-check` "
            "on the deployed file for the full matrix and red examples"
        )
    logger.warning(
        "DSV41 prefill SP deepcarry boot invariant SELF-CHECK PASS "
        "(%d/%d rows: key-combo table/boundary parity/rowband purity/"
        "C1 export+co-install/F2 tail isomorphism/F1 sm100 conjugate/"
        "parse vocabulary/row arithmetic/engine anchors)",
        sum(1 for _r in _sc_rows if _r[1]), len(_sc_rows),
    )
    return True


def _make_ar_leaf(site, stock, group_of):
    """Wrap one plain-AR leaf; stock unless the prefill bracket armed it."""

    def leaf(input_):
        if not _state["active"]:
            return stock(input_)
        try:
            group = group_of()
        except Exception as exc:
            # F5 (comm-leaf twin of the stage1 face): the silent-stock
            # window gets its one ERROR per site per boot (see
            # _make_stage1_ar_leaf).
            _log_group_getter_failure(site, exc)
            return stock(input_)
        if not _call_eligible(input_, group):
            return stock(input_)
        return _verified_rs_ag(site, stock, group, input_)

    leaf.__name__ = getattr(stock, "__name__", site)
    setattr(leaf, _MARKER, True)
    return leaf


def _fingerprint(module, name, needle):
    """Install-time seam fingerprint: the leaf must still be the engine's
    one-line group dispatch. A drifted seam refuses the boot (fail-closed:
    an inert wrap would keep AR silently and the arm would look green).
    Returns None when the seam already carries our marker (double exec of
    the module -- the family's quiet-idempotency law).

    T61 day-3: same wrapper-aware law as _need_source -- the needle is
    checked on the UNWRAPPED chain terminal (sitecustomize installs
    l2_prefetch's collective-leaf wrappers and l2pf_attn's
    dp_attention.attn_tp_all_reduce wrapper BEFORE ours on their armed
    boots), and the CURRENT chain top is returned so the stock-route
    calls keep the foreign wrapper's prefetch alive. Reverse
    discrimination per needle: wrapper source (unwrap failed) still
    refuses; true engine terminal passes; mutated terminal refuses."""
    func = getattr(module, name, None)
    if getattr(func, _MARKER, False):
        return None  # already wrapped (double exec of the module)
    if not callable(func):
        raise RuntimeError(
            f"prefill_sp: seam moved ({name} missing or not callable on "
            f"{getattr(module, '__name__', module)}); refusing to boot -- the "
            "comm swap would otherwise silently no-op"
        )
    chain, adapters = _unwrap_seam(func, name)
    terminal = chain[-1]
    try:
        source = inspect.getsource(terminal)
    except (OSError, TypeError) as exc:
        raise RuntimeError(
            f"prefill_sp: seam unreadable ({name}: {exc}); refusing to boot"
        ) from None
    if needle not in source:
        raise RuntimeError(
            f"prefill_sp: seam moved ({name} no longer dispatches through "
            f"{needle!r}); refusing to boot -- stacking a comm swap on an "
            "unknown AR implementation is not ours to decide"
        )
    _need_terminal_file(module, name, terminal, chain)
    _unwrap_log(name, chain, adapters)
    return func


# ------------------------------------------------------------- installers


def _leaf_factory():
    """mode-selected leaf: comm = P0 swap; stage1 = row-split section path."""
    return _make_ar_leaf if MODE == "comm" else _make_stage1_ar_leaf


def install_communication_op(module) -> int:
    """Wrap the two plain TP-AR leaves of sglang.srt.distributed.
    communication_op (EngramLoader exec-time hook). Inert modes touch
    nothing; comm/stage1(+EXACT) refuse on seam drift."""
    if not _armed():
        return 0
    wrapped = []
    for name, needle, getter in (
        ("tensor_model_parallel_all_reduce", "get_tp_group().all_reduce",
         "get_tp_group"),
        ("attention_tensor_model_parallel_all_reduce",
         "get_attn_tp_group().all_reduce", "get_attn_tp_group"),
        # The MoE post-experts AR this model actually reaches: DeepseekV2MoE
        # constructs FusedMoE with reduce_results=False (deepseek_v2.py:663-
        # 681, layer.py:336 default), so fused_moe_triton/layer.py:1597 never
        # fires; the reduction is post_experts_all_reduce (layers/moe/
        # utils.py:838) -> this leaf (deepseek_v2.py:1368). EP1 + a2a none:
        # reduce_ep False, the merged tensor-AR branch never taken.
        ("moe_tensor_model_parallel_all_reduce", "get_moe_tp_group().all_reduce",
         "get_moe_tp_group"),
    ):
        stock = _fingerprint(module, name, needle)
        if stock is None:
            continue  # already wrapped (double exec)
        if not hasattr(module, getter):
            raise RuntimeError(
                f"prefill_sp: {getter} missing on {module.__name__}; refusing to boot"
            )
        setattr(module, name, _leaf_factory()(name, stock,
                                              getattr(module, getter)))
        wrapped.append(name)
    if wrapped:
        _state["installed"].append(f"comm_op:{'+'.join(wrapped)}")
        logger.warning(
            "DSV41 prefill SP %s wraps installed on %s: %s (gate=%s exact=%s "
            "min_rows=%s)", MODE, module.__name__, wrapped,
            os.environ.get("DSV41_PREFILL_SP"), EXACT, MIN_ROWS,
        )
    return len(wrapped)


def install_dp_attention(module) -> int:
    """Wrap dp_attention.attn_tp_all_reduce (attention-o AR leaf). The group
    is resolved per call through get_parallel().attn_tp_group, exactly the
    group the stock leaf reduces over."""
    if not _armed():
        return 0
    stock = _fingerprint(module, "attn_tp_all_reduce", "attn_tp_group.all_reduce")
    if stock is None:
        return 0  # already wrapped (double exec)
    if not hasattr(module, "get_parallel"):
        raise RuntimeError(
            "prefill_sp: get_parallel missing on dp_attention; refusing to boot"
        )

    def _group():
        return module.get_parallel().attn_tp_group

    module.attn_tp_all_reduce = _leaf_factory()(
        "attn_tp_all_reduce", stock, _group)
    _state["installed"].append("dp_attention:attn_tp_all_reduce")
    logger.warning(
        "DSV41 prefill SP %s wrap installed on dp_attention.attn_tp_all_reduce "
        "(gate=%s exact=%s min_rows=%s)", MODE,
        os.environ.get("DSV41_PREFILL_SP"), EXACT, MIN_ROWS,
    )
    return 1


def _install_dump_only_loop(module) -> bool:
    """DEBUG=dump stock-side bracket (day-2 #2, the A-boot face of the
    EXACT-gate harness): a PURE-OBSERVER wrap of DeepseekV4Model.
    _forward_layers_hc_pre_from_prev that dumps the loop-exit tensors
    after the STOCK loop ran verbatim -- zero behavior change, zero
    collectives, no plan, no seam swap. Eligibility mirrors the deep-carry
    plan's SPMD-uniform basics (plain extend prefill, rows >= MIN_ROWS,
    rows % world == 0, the [rows,4,5120] bf16 shape) so the two boots of
    an A/B pair dump the same chunk sequence; a chunk one boot refuses is
    simply absent from that boot's dump set and shows up as unpaired in
    the harness report (never silently compared). The segB tag exists
    only on the deep-carry boot (a stock loop has no equivalent seam
    without replacing it -- the harness pairs exits and uses the DC-side
    segB dumps as forensics; see EXACT-GATE-HARNESS §2.2 note).
    T61 day-8 (R7 localization fire): the observer grows the four-face
    ladder's stock side -- F0 = the loop-entry hidden_states' RANK SLICE
    [lo,hi) (the first region layer's forward input, the same math point
    the armed side's entry split R holds), and a per-LAYER pure observer
    on DeepseekV4DecoderLayer.forward_hc_pre_from_prev dumps the tap
    ladder faces (F1/F2 at their owning layers, plus the day-9 dense
    "L<layer>" taps) rank-sliced inside the eligible-chunk window only.
    The stock loop and every layer forward still run VERBATIM (call
    stock, dump the returned tensors, return)."""
    model_cls = getattr(module, "DeepseekV4Model", None)
    if model_cls is None:
        raise RuntimeError(
            "prefill_sp: DeepseekV4Model missing from the deepseek_v4 "
            "module; refusing the dump-only install (seam moved)"
        )
    if getattr(model_cls, _DC_DUMP_MODEL_MARKER, False):
        return False  # already installed (double exec of the module)
    stock_loop = getattr(model_cls, "_forward_layers_hc_pre_from_prev", None)
    if getattr(stock_loop, _DC_MODEL_MARKER, False):
        return False  # the deep-carry bracket owns this seam already
    if not callable(stock_loop):
        raise RuntimeError(
            "prefill_sp: DeepseekV4Model._forward_layers_hc_pre_from_prev "
            "missing or not callable; refusing the dump-only install"
        )

    def _dump_rank():
        # rank resolution on an UNARMED boot: _ENGINE is not populated (no
        # deep-carry install ran), so fall back to torch.distributed (sglang
        # TP workers are always initialized) -- the filename must differ per
        # rank or the four ranks overwrite each other's dumps.
        try:
            return _ENGINE["get_parallel"]().tp_rank
        except Exception:
            pass
        try:
            import torch.distributed as dist
            if dist.is_initialized():
                return dist.get_rank()
        except Exception:
            pass
        return 0

    def _dump_world():
        try:
            return _ENGINE["get_parallel"]().tp_size
        except Exception:
            pass
        try:
            import torch.distributed as dist
            if dist.is_initialized():
                return dist.get_world_size()
        except Exception:
            pass
        return 4

    def _forward_layers_hc_pre_from_prev(self, *args, **kwargs):
        # day-8: F0 + the face window are set BEFORE the stock loop runs
        # (the entry tensor is the loop's INPUT -- dumping it after the
        # call would rely on no in-place mutation; dumping before is the
        # semantically exact point and stays pure observation).
        obs = False
        obs_plan = None
        try:
            forward_batch = kwargs.get("forward_batch")
            if forward_batch is None and len(args) > 2:
                forward_batch = args[2]
            hidden_states = kwargs.get("hidden_states")
            if hidden_states is None and len(args) > 1:
                hidden_states = args[1]
            world = _dump_world()
            mode = getattr(forward_batch, "forward_mode", None)
            rows = (hidden_states.shape[0]
                    if hidden_states is not None and hidden_states.dim() == 3
                    else 0)
            if (
                mode is not None
                and mode.is_extend_without_speculative()
                and rows >= MIN_ROWS
                and rows % world == 0
                and tuple(hidden_states.shape) == (rows, 4, 5120)
                and hidden_states.dtype == torch.bfloat16
                and hidden_states.is_cuda
            ):
                obs = True
                _dc_ctx["chunk_idx"] = _dc_ctx.get("chunk_idx", 0) + 1
                rank = _dump_rank()
                e = rows // world
                lo = rank * e
                obs_plan = {"rank": rank, "M": rows, "E": e,
                            "world": world, "exact": True}
                _dc_dump("F0", obs_plan, hidden_states[lo:lo + e], None,
                         face_form="shard")
                # the face window: WHICH layer indices own the taps -- the
                # armed side's formula (_dc_tap_map, day-9 parameterized;
                # day-8 read F1/F2 from the model's own attributes), so the
                # two boots agree on the owning iterations. An unreadable
                # region (late None / out of [start,end]) leaves taps={}
                # and the layer observer stays inert (the armed plan would
                # have refused the same chunk -- the missing faces then
                # surface as stock_only unpaired in the harness, never a
                # silent compare).
                taps = {}
                start = getattr(self, "start_layer", None)
                late = getattr(self, "late_layer_start", None)
                end = getattr(self, "end_layer", None)
                if (isinstance(start, int) and isinstance(late, int)
                        and isinstance(end, int) and start < late <= end):
                    taps = _dc_tap_map(start, late)
                _dc_ctx["obs_faces"] = dict(
                    obs_plan, taps=taps,
                    first=_dc_first_block(forward_batch))
        except Exception as exc:
            logger.warning(
                "DSV41 prefill SP dump-only bracket: F0/face-window "
                "capture failed (%s) -- the stock forward itself is "
                "unaffected", exc,
            )
        out = stock_loop(self, *args, **kwargs)
        try:
            if obs:
                _dc_dump("exit", obs_plan,
                         out[0], out[1] if len(out) > 1 else None)
        except Exception as exc:
            logger.warning(
                "DSV41 prefill SP dump-only bracket: capture failed (%s) "
                "-- the stock forward itself is unaffected", exc,
            )
        finally:
            if obs:
                _dc_ctx["obs_faces"] = None
        return out

    _forward_layers_hc_pre_from_prev.__name__ = getattr(
        stock_loop, "__name__", "_forward_layers_hc_pre_from_prev")
    # mock-smoke 20261002 fix: the double-exec guard (:3324) reads the
    # marker at CLASS level -- setting it on the function left the guard
    # dead (a module re-exec would wrap the wrapper and double-dump every
    # chunk). Class-level, same law as install_model's _MODEL_MARKER.
    setattr(model_cls, _DC_DUMP_MODEL_MARKER, True)
    model_cls._forward_layers_hc_pre_from_prev = \
        _forward_layers_hc_pre_from_prev
    _state["installed"].append("dump_only:loop_exit_observer")

    # ---- day-8: the per-LAYER pure observer (the stock side of F1/F2) --
    # Wraps DeepseekV4DecoderLayer.forward_hc_pre_from_prev: call stock,
    # then -- ONLY while an eligible chunk's window is open and ONLY for
    # the face-owning layer indices -- dump the returned (hidden, prev_pre)
    # rank-sliced [lo,hi) with the same file contract as the armed taps.
    # Layer identity rides the engine's own self.layer_id (deepseek_v4.py
    # :2623); an unreadable layer_id dumps nothing (never a wrong-window
    # face). A missing layer seam is LOUD but not fatal (F0/exit still
    # pair; the harness then shows F1/F2 stock_only unpaired = visible
    # red, not a silent compare).
    layer_cls = getattr(module, "DeepseekV4DecoderLayer", None)
    stock_layer = getattr(layer_cls, "forward_hc_pre_from_prev", None)
    if getattr(layer_cls, _DC_DUMP_LAYER_MARKER, False):
        pass  # already installed (double exec of the module)
    elif layer_cls is None or not callable(stock_layer):
        logger.warning(
            "DSV41 prefill SP dump-only layer-face observer NOT installed "
            "(DeepseekV4DecoderLayer.forward_hc_pre_from_prev seam "
            "missing) -- F1/F2 stock-side faces will be absent (visible "
            "as unpaired in the harness, never silently compared)",
        )
    else:
        def _layer_forward_hc_pre_from_prev(self, *args, **kwargs):
            out = stock_layer(self, *args, **kwargs)
            try:
                obs = _dc_ctx.get("obs_faces")
                if obs:
                    lid = getattr(self, "layer_id", None)
                    taps = obs.get("taps") or {}
                    if lid is not None and lid in taps:
                        lo = obs["rank"] * obs["E"]
                        sl = slice(lo, lo + obs["E"])
                        plan = {"rank": obs["rank"], "M": obs["M"],
                                "E": obs["E"], "world": obs["world"],
                                "exact": True}
                        h, pp = out[0], (out[1] if len(out) > 1 else None)
                        # day-9 law (mirror of the armed loop's): F1/F2
                        # dump for every eligible chunk (R7 full-volume
                        # caliber); the dense L<layer> taps dump FIRST
                        # BLOCKS ONLY (the pure-seed selection law).
                        for tag in taps[lid]:
                            if tag in ("F1", "F2") or obs.get("first"):
                                _dc_dump(tag, plan, h[sl],
                                         pp[sl] if pp is not None else None,
                                         face_form="shard")
            except Exception as exc:
                logger.warning(
                    "DSV41 prefill SP dump-only layer-face observer: "
                    "capture failed (%s) -- the stock layer forward "
                    "itself is unaffected", exc,
                )
            return out

        _layer_forward_hc_pre_from_prev.__name__ = getattr(
            stock_layer, "__name__", "forward_hc_pre_from_prev")
        setattr(layer_cls, _DC_DUMP_LAYER_MARKER, True)
        layer_cls.forward_hc_pre_from_prev = \
            _layer_forward_hc_pre_from_prev
        _state["installed"].append("dump_only:layer_face_observer")
        logger.warning(
            "DSV41 prefill SP dump-only layer-face observer installed "
            "[deepcarry-20261002/T61-day9]: stock layer forwards run "
            "VERBATIM; the tap ladder faces (F1/F2 full volume; L<layer> "
            "dense taps FIRST BLOCKS ONLY, TAP_LAYERS=%s) dumped to %s "
            "inside the eligible-chunk window (no behavior change, no "
            "collectives added)",
            ",".join(str(x) for x in TAP_LAYERS) if TAP_LAYERS is not None
            else "unset=R7(F1,F2)", DEBUG_DUMP_DIR,
        )
    logger.warning(
        "DSV41 prefill SP dump-only loop-exit observer installed "
        "[deepcarry-20261002/T60-day2]: stock loop runs VERBATIM; exit "
        "tensors dumped to %s for the EXACT-gate A/B pair (no behavior "
        "change, no collectives added)", DEBUG_DUMP_DIR,
    )
    return True


def install_model(module) -> bool:
    """Bracket DeepseekV4Model.forward: arm the leaf swaps only for plain
    eager prefill batches (mode law + MIN_ROWS + no capture). Also rebind
    this module's from-imported attn_tp_all_reduce (deepseek_v4.py:88) to
    the dp_attention wrap -- the L2PF dual-module lesson, defensive on top
    of the exec-time defining-module wrap."""
    if not _armed():
        # day-2: an unarmed boot with DEBUG=dump[:DIR] still gets the pure
        # observer bracket -- the stock side of the EXACT-gate A/B pair.
        if DEBUG_DUMP_DIR is not None:
            _install_dump_only_loop(module)
        return False
    cls = getattr(module, "DeepseekV4Model", None)
    if cls is None or not hasattr(cls, "forward"):
        raise RuntimeError(
            "prefill_sp: DeepseekV4Model.forward seam moved; refusing to boot"
        )
    if getattr(cls, _MODEL_MARKER, False):
        return False  # already installed (double exec of the module)
    if not hasattr(module, "attn_tp_all_reduce"):
        raise RuntimeError(
            "prefill_sp: deepseek_v4 no longer from-imports attn_tp_all_reduce "
            "(consumer binding moved); refusing to boot"
        )
    original = cls.forward

    def forward(self, input_ids, positions, forward_batch, *args, **kwargs):
        if not _bracket_eligible(input_ids, forward_batch):
            return original(self, input_ids, positions, forward_batch, *args, **kwargs)
        prev = _state["active"]
        _state["active"] = True
        try:
            return original(self, input_ids, positions, forward_batch, *args, **kwargs)
        finally:
            _state["active"] = prev

    cls.forward = forward
    setattr(cls, _MODEL_MARKER, True)
    _state["installed"].append("model:DeepseekV4Model.forward")
    # Defensive rebind of the from-imported consumer name (dual-module law).
    try:
        import sglang.srt.layers.dp_attention as _dpa
        wrapped = getattr(_dpa, "attn_tp_all_reduce", None)
        if (wrapped is not None and getattr(wrapped, _MARKER, False)
                and module.attn_tp_all_reduce is not wrapped):
            module.attn_tp_all_reduce = wrapped
            logger.warning(
                "DSV41 prefill SP: deepseek_v4.attn_tp_all_reduce rebound to the "
                "dp_attention wrap"
            )
    except Exception as exc:  # rebind is belt-and-braces; never fatal
        logger.warning("DSV41 prefill SP: consumer rebind skipped (%s)", exc)
    if _fp8_armed() and not _SECTIONS_FP8:
        logger.warning(
            "DSV41 prefill SP: fp8 gather armed (DSV41_PREFILL_SP_FP8_MOE=1) "
            "but no section is registered with fp8=True; every gather stays "
            "on the verified bf16 path this boot. The fp8 face must be owned "
            "by the site that proves its gathered tensor feeds the "
            "MXFP8-consuming face (register_section(..., fp8=True)); "
            "moe_b12x_next's PREQUANT_WARM compile at load is the only "
            "effect of this key until then (harmless, visible in its banner)"
        )
    if MODE == "stage1":
        if _deepcarry_armed():
            # T60: the layer-loop replacement (deep-carry). The per-site
            # layer-carry install is NOT run -- its per-site AG form is the
            # M7 red-flag form; rollback = DSV41_PREFILL_SP_DEEPCARRY=0.
            _install_deep_carry(module)
        elif EXACT:
            # Legacy reanchor per-site form (EXACT-only, fail-closed).
            _install_layer_carry(module)
    logger.warning(
        "DSV41 prefill SP %s forward bracket installed on DeepseekV4Model "
        "(extend-without-speculative, min_rows=%s, capture-excluded, "
        "sections=%s, fp8_sites=%s, carry_sites=%s)", MODE, MIN_ROWS,
        ",".join(sorted(_SECTIONS)) or "identity",
        ",".join(sorted(_SECTIONS_FP8)) or "none",
        "+".join(_state["carry_sites"]) or "none",
    )
    return True


def _bracket_eligible(input_ids, forward_batch) -> bool:
    """Eligibility law (doc60 §2#6 family): plain eager extend prefill,
    rows >= MIN_ROWS, CUDA, not under graph capture. Inputs are
    SPMD-uniform across TP ranks, so every rank takes the same branch."""
    mode = getattr(forward_batch, "forward_mode", None)
    if mode is None:
        return False
    try:
        if not mode.is_extend_without_speculative():
            return False
    except Exception:
        return False
    if input_ids.shape[0] < MIN_ROWS:
        return False
    if not _device_ok(input_ids):
        return False
    return not _capturing()


# ------------------------------------------------- consolidated v2 (2026-10-03)
#
# 用户令④ self-check (PROD-RS-WHITEBOX-QA-20261003 + REFDIFF-BUGHUNT
# dispositions): the BOOT-TIME INVARIANT SELF-CHECK MATRIX. Two faces:
#   * standalone: `python3 prefill_sp.py --self-check` (imports without
#     sglang; engine-anchor section self-skips with its reason printed);
#   * boot segment: _install_deep_carry runs it after the wraps land and
#     REFUSES the boot on any red row (fail-closed; every row carries the
#     reverse red example it exists to catch).
def self_check(report=None):
    """Run the boot invariant matrix; returns (ok, rows) where each row is
    (name, ok, red_example). Never raises -- callers decide (the boot
    segment converts any False row into a refusal; the standalone entry
    prints the table and exits 0/1)."""
    rows = []

    def ck(name, cond, red):
        rows.append((name, bool(cond), red))

    try:
        with open(__file__, "r", errors="replace") as _f:
            own_src = _f.read()
    except OSError:
        own_src = ""

    # M1 -- three-key legal combination table (MODE/EXACT/BOUNDARY/
    # DEEPCARRY): the derived boundary form must be exactly the table
    # row for the armed combination (F10 redundancy noted, not refused).
    form = _boundary_form(EXACT, BOUNDARY == "ar_slice", long_form=True)
    want_form = ("AR+slice(EXACT)" if EXACT else
                 "AR+slice(T62b)" if BOUNDARY == "ar_slice" else "RS(T62)")
    ck("key-combo: derived boundary form matches the three-key table",
       form == want_form and BOUNDARY in ("", "ar_slice"),
       "an armed boot whose banners claim a boundary form the keys do not "
       "select (EXACT/BOUNDARY disagreement) -- the A/B readout attributes "
       "one arm's numbers to the other")

    # M2 -- boundary predicate parity: the plan-face predicate must equal
    # the independent recomputation from the parsed keys.
    ck("boundary/rowband: _boundary_ar_slice() == (EXACT or key==ar_slice)",
       _boundary_ar_slice() == (EXACT or BOUNDARY == "ar_slice"),
       "the plan face and the banner face disagree on the boundary form "
       "(leaf reduces RS while every banner claims AR+slice)")

    # M3 -- row-band purity: the BOUNDARY key owns ONLY the boundary
    # leaves; the hcpostc row-band source may not read it.
    hcpostc_src = ""
    if own_src:
        try:
            hcpostc_src = inspect.getsource(
                sys.modules[__name__]._make_dc_hcpostc_wrapper)
        except Exception:
            hcpostc_src = ""
    ck("row-band purity: hcpostc wrapper never reads boundary_ar_slice",
       "boundary_ar_slice" not in hcpostc_src,
       "the ar_slice key flips the row-band route too -- the boundary A/B "
       "changes two mechanisms at once and its verdict is void")

    # M4 -- C1 export existence + off-state behavior (plan None -> n).
    class _Scalar:
        shape = (7, 3)
    _saved_plan, _saved_inner = _dc_ctx.get("plan"), _dc_ctx.get("inner")
    _dc_ctx["plan"], _dc_ctx["inner"] = None, False
    try:
        _n_off = sp_logical_rows(_Scalar())
    finally:
        _dc_ctx["plan"], _dc_ctx["inner"] = _saved_plan, _saved_inner
    ck("export: callable(sp_logical_rows) and plan-None returns x.shape[0]",
       callable(globals().get("sp_logical_rows")) and _n_off == 7,
       "hc_fused's `from prefill_sp import sp_logical_rows` resolves to the "
       "silent fallback (x.shape[0]) -- the latent SP-vs-stock kernel-gate "
       "drift C1 exists to remove")

    # M5 -- co-install completeness (only when the arm key is set; the
    # boot path already refused on failure, this is the table row).
    _hc_key = os.environ.get("DSV41_HC_FUSED", "0").strip()
    _hc_armed = _hc_key not in ("0", "", "off", "false")
    _coin_ok, _coin_note = True, "key off"
    if _hc_armed:
        try:
            import hc_fused
            # resolve through sys.modules so the identity is module-object
            # true even under the __main__ standalone entry (a direct
            # `python3 prefill_sp.py` run is __main__; hc_fused's import
            # binds the sys.modules["prefill_sp"] copy -- the boot face
            # compares the one and only module object).
            _psp = sys.modules.get("prefill_sp", sys.modules[__name__])
            _coin_ok = (getattr(hc_fused, "_logical_rows", None)
                        is getattr(_psp, "sp_logical_rows", None))
            _coin_note = ("bound to prefill_sp.sp_logical_rows"
                          if _coin_ok else "FALLBACK active")
        except Exception as exc:
            _coin_ok, _coin_note = False, f"import failed: {exc!r}"
    ck(f"co-install: DSV41_HC_FUSED={_hc_key!r} -> {_coin_note}",
       _coin_ok,
       "an armed hc_fused boot whose row gates key on shard rows -- the "
       "fused kernel silently disqualifies on SP boots only (A/B misread)")

    # M6 -- F2 isomorphism predicate pinned in the shipped source (the
    # late==end_layer classification rides this exact conjunct).
    ck("F2: segment-B window keys on region_end < end_layer (isomorphic)",
       "use_tail = tail is not None and plan[\"region_end\"] < self.end_layer"
       in own_src,
       "the window fires on `tail is not None` alone: at late==end_layer "
       "the armed side enters the tail window while stock never does -- "
       "row count AND return triple fork")

    # M7 -- F1 conjugate pinned in the shipped source.
    ck("F1: _hc_mix_stats big-band gate carries the sm100 conjugate",
       "_ENGINE.get(\"sm100_ok\", False)" in own_src,
       "on a parts-populated non-sm100 platform the wrapper forces bf16x3 "
       "on the shard while stock takes hc_mix_stats_sinkhorn -- a same-math-"
       "different-kernel EXACT break")

    # M8 -- parse vocabulary coherence (the fail-closed family law).
    ck("parse: EXACT/DEEPCARRY bool, WKV in (shard|full), MIN_ROWS >= 1",
       isinstance(EXACT, bool) and isinstance(DEEPCARRY, bool)
       and WKV in ("shard", "full") and isinstance(MIN_ROWS, int)
       and MIN_ROWS >= 1,
       "a non-boolean or out-of-domain parse slipping through silently "
       "changes the armed form under the banners")

    # M9 -- boundary/rowband arithmetic coherence: the row partition the
    # plan promises (E=M/world, contiguous rank blocks) is what the pure
    # helpers compute, for a representative world-4 grid.
    _arith_ok = True
    for _m in (2048, 4096, 6144, 16384, 32768, 65536):
        if shard_extent(_m, 4) != _m // 4:
            _arith_ok = False
        for _r in range(4):
            _lo, _hi = shard_bounds(_m, 4, _r)
            if (_lo, _hi) != (_r * (_m // 4), (_r + 1) * (_m // 4)):
                _arith_ok = False
    ck("arithmetic: shard_extent/shard_bounds partition M into world=4 "
       "contiguous rank blocks (grid 2048..65536)",
       _arith_ok,
       "an off-by-one or ceil/floor drift in the row partition splits a "
       "token row across ranks or drops rows at the boundary")

    # M11 -- W5 tail-gather owner law: the owner table is RE-DERIVED from
    # the plan's exact-split law (E = M//world, plan gate refuses
    # rows%world) and REFUSES (full-row AG) when a plan violates it --
    # never guesses a partition it was not derived from.
    _tg_ok = isinstance(TAIL_GATHER, bool)
    for _m2 in (2048, 4096, 65536):
        _p2 = {"M": _m2, "E": _m2 // 4, "world": 4}
        _idx2 = torch.arange(_m2)
        _ol2 = _dc_tail_owner_local(_idx2, _p2)
        _tg_ok = _tg_ok and _ol2 is not None and bool(
            torch.equal(_ol2[0] * (_m2 // 4) + _ol2[1], _idx2))
        _p2bad = {"M": _m2 + 2, "E": _m2 // 4, "world": 4}
        _tg_ok = _tg_ok and _dc_tail_owner_local(_idx2, _p2bad) is None
        _tg_ok = _tg_ok and _dc_tail_plan(_m2, 4, 128) == "owners" \
            and _dc_tail_plan(512, 4, 128) == "full"
    ck("W5 tail-gather: owner table round-trips the plan split law and "
       "refuses non-exact plans (E*M check); degenerate gate fires at "
       "world*n_tail >= rows",
       _tg_ok,
       "an owner table derived from a foreign partition law (e.g. the "
       "community shard_range copied instead of re-derived) reads another "
       "rank's rows -- silent cross-rank row corruption at every exit")

    # M12 -- W5 AG-in bit-narrative law: the fp8 face's shipped source
    # compares the consumer's own quantizer against itself (gathered rows
    # vs shard rows) and must never lean on a dequantize-requantize
    # roundtrip (banned narrative, gap-verdict §2.3 step 6: ~7% of blocks
    # flip at the 224 boundary, counterexample {230.0, 1.0}).
    ck("W5 AG-in: _dc_fp8_input compares quantizer-vs-quantizer, no "
       "mxfp8_oracle/roundtrip in the fp8 path",
       ("mxfp8_oracle" not in inspect.getsource(_dc_fp8_input)
        and "_dc_mxfp8_quantize(xb.contiguous(), True)" in
        inspect.getsource(_dc_fp8_input)),
       "the first-chunk check quietly swaps in a roundtrip oracle -- a "
       "false-green bit check ships byte-divergent quantization to "
       "wqkv_a")

    # M13 -- W5 replica deprecation is airtight: no production route can
    # reach the deprecated torch-replica gather (_fp8_armed pinned False
    # and the dispatch carries the guard).
    ck("W5 deprecation: replica fp8 gather unreachable (_fp8_armed() "
       "False and dispatch guarded)",
       _fp8_armed() is False
       and "_fp8_armed()" in inspect.getsource(_verified_sp_section),
       "a stray register_section(fp8=True) re-arms the byte-divergent "
       "torch replica on a legacy boot -- quantization bytes silently "
       "differ from the consumer's expectation")

    # M14 -- W5 parse vocabulary: the new key obeys the strict-boolean
    # family law (illegal values already refused the boot at import).
    ck("parse: TAIL_GATHER is a bool (strict-boolean family law)",
       isinstance(TAIL_GATHER, bool),
       "a non-boolean TAIL_GATHER parse slips the exit face on under a "
       "banner that claims it off")

    # M10 -- engine anchor completeness (installed boots only; standalone
    # self-skips with its reason in the row name).
    if _ENGINE:
        ck("engine anchors: platform_ok+sm100_ok+bcg+cp getters resolved",
           all(k in _ENGINE for k in ("platform_ok", "sm100_ok",
                                      "dv4_is_in_bcgraph",
                                      "dv4_is_cp_active")),
           "a wrapper reading a missing engine anchor silently takes its "
           "fail-closed branch on every call (armed!=engaged at gate "
           "granularity)")
    else:
        ck("engine anchors: SKIPPED (standalone -- _ENGINE empty)",
           True, "n/a (standalone profile)")

    ok = all(r[1] for r in rows)
    if report is not None:
        for name, good, red in rows:
            report("prefill_sp SELF-CHECK [%s] %s (%s)",
                   "OK" if good else "RED", name,
                   "" if good else f"red example: {red}")
    return ok, rows


if __name__ == "__main__":  # pragma: no cover (operator entry)
    # `python3 prefill_sp.py [--self-check] [--json]` -- the standalone
    # face of the boot invariant matrix (imports without sglang).
    import argparse
    import json as _json
    _ap = argparse.ArgumentParser(
        description="prefill_sp consolidated-v2 boot invariant self-check "
                    "(the same matrix _install_deep_carry runs at boot)")
    _ap.add_argument("--self-check", action="store_true",
                     help="accepted for discoverability; the matrix is "
                          "always what this entry runs")
    _ap.add_argument("--json", action="store_true",
                     help="print the matrix as JSON")
    _ns = _ap.parse_args()
    _ok, _rows = self_check()
    if _ns.json:
        print(_json.dumps(
            [{"check": n, "ok": g, "red_example": r}
             for n, g, r in _rows], indent=1))
    else:
        for _n, _g, _r in _rows:
            print(f"[{'OK' if _g else 'RED'}] {_n}"
                  + ("" if _g else f"\n       red example: {_r}"))
    print("PREFILL_SP SELF-CHECK " + ("PASS" if _ok else "FAIL")
          + f" ({sum(1 for _r in _rows if _r[1])}/{len(_rows)})")
    sys.exit(0 if _ok else 1)
