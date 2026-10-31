"""G3: DSV4.1 sparse 索引器真接线（SM121 断线修复 + 能力探针 + T×L 预算门）。

挂点 = 战役 adapter 的 sitecustomize（EngramFinder → 本模块 install_* 分派）；
镜像（main-79cafec0）不动。总门 = DSV41_DG_SPARSE_SM121（沿用 deep_gemm_sm121
的键）；门关时本模块完全惰性（不改任何引擎符号）。

== 三断线（doc102 G1）与修法 ==============================================
#1 根门 configurer.py:57 ``DEEPGEMM_BLACKWELL = ... is_sm100`` → SM121 整门关。
   修：复用 deep_gemm_sm121.install（只开 DEEPGEMM_PAGED_SPARSE_MQA_LOGITS，
   BLACKWELL 不动）。
#1b 页钉：sparse 门开 ⇒ main 把 indexer 池页翻到 128（dsv41_index_page_size），
   但 SM121 dense paged 核硬律 block_kv==64（_C.so: "arch_major == 12 and
   block_kv == 64"，引用者=fp8_fp4_paged_mqa_logits）⇒ 必须把池页钉回 64。
   deep_gemm_sm121.install_memory_pool 原型把钉挂错模块（configurer 无
   DSV41_INDEX_PAGE_SIZE 锚）；本模块以 memory_pool 模块为锚重做。
#2 sparse_table.py:191-197 非 chunked publish_decode 无条件内联
   topk_transform_paged_v2、传 metadata.topk_metadata——use_topk_v2=False 时
   那是 CPU 空哑元（metadata.py:290 torch.empty((0,))）→ 核面必炸。
   修：改走 topk_transform_paged_from_metadata（其内部按 use_topk_v2 分派
   v1/v2；patch 形式=整方法重绑，语义 diff 恰为上游 2 行）。
#3 full_topk.py:60/129 topk_decode 不查 metadata.deep_gemm_metadata is None
   → None 落 _deep_gemm_decode 把 None 塞给核。
   修：dispatch 处 None 即转 _torch_decode（覆盖两处调用面）。

== 能力探针（G3 首门前置结论的运行期化）====================================
离线静态审计【实证】：镜像内 sgl-deep-gemm 0.2.0 的 sparse 面
（fp8_fp4_paged_sparse_mqa_logits / get_paged_sparse_mqa_logits_metadata）
在绑定层硬断 ``jit->device.get_arch_major() == 10``，且唯一实现
sm100_sparse_mqa_logits.cuh 是 tcgen05/TMEM（SM121 无此 ISA）；512B 页步长律
（stride(0)%512==0）也在 sparse 面——64×68=4352B 不满足（见 geo_check.py）。
⇒ SM121 今日"开门即用 sparse 核"不可能；本模块在 make_candidate_indexer
返回 sparse 对之前做一次廉价干跑探针（真实页几何 1 行 4 块），失败 =
boot log 横幅 + 回退 DenseBlocksBackend 对（#40352 的 int32 块表候选语义，
fork 生产同构：source 发布 2048×8 块表，consumer 只在候选内 top-k——
这就是"回到论文近似方案"在 SM121 上的可实现形态）。探针成功（未来
deep_gemm 出 sm12x sparse）则原生 sparse_table 对直接上岗，无需改代码。

== 运行期 T×L 预算门（用户点名）===========================================
稠密打分唯一咽喉 = index_logits.deep_gemm_fp4_paged_mqa_logits（full_topk
decode / sparse&dense publish / captured prefill 全走它）。包一层
rows×cols 预算断言：默认律 T×L ≲ 2.0e8 元素（fork dense-indexer 律，
fp32 4B ⇒ 单瞬态 ~800MB×3 传导 ≈ 2.4G，262k 档 dense 超此 10.7×=13:26
四机事故的机制），DSV41_TL_BUDGET_ELEMS 可调，"off"/"0" 关。已按行分块
的调用（每块 T 已切小）天然过门，不误伤。

部署：拷本文件至 ~/migrate-assets/dsv41/adapter/，并按
patches/0003-sitecustomize-g3-hook-delta.patch 给 sitecustomize.py 加 4 个
finder 模块名 + 4 个分派分支（adapter 目录属宿主资产，非镜像）。
"""
from __future__ import annotations

import logging
import os

_logger = logging.getLogger(__name__)

GATE_ENV = "DSV41_DG_SPARSE_SM121"      # 总门（与 deep_gemm_sm121 同键）
BUDGET_ENV = "DSV41_TL_BUDGET_ELEMS"    # T×L 预算门（元素数）
DEFAULT_TL_BUDGET = 2 * 10**8           # fork 律 T×L ≲ 2.0e8
_OFF = ("", "0", "off", "false", "no")
_INSTALLED: set = set()

# 探针几何：真实池页（SM121=钉 64）、1 行、4 块（num_max_sparse_blocks%4==0 且>0）。
_PROBE_PAGES = 4
_PROBE_BLOCKS = 4
_PROBE_HEADS = 32                        # config.json index_n_heads


def enabled() -> bool:
    return os.environ.get(GATE_ENV, "").strip().lower() not in _OFF


def _budget_elems():
    """预算门元素上限；None=关。未设 env = 缺省律 2.0e8（fork T×L 律）。"""
    raw = os.environ.get(BUDGET_ENV)
    if raw is None:
        return DEFAULT_TL_BUDGET
    raw = raw.strip().lower()
    if raw in _OFF:
        return None
    return int(float(raw))


class SparseWireBudgetGate(RuntimeError):
    """dense 打分 T×L 超预算——在分配前拒绝（C13 律的运行期化）。"""


# ─────────────────────────── 模块挂点 ─────────────────────────────────────


def install_configurer(module) -> bool:
    """断线#1：开 sparse 门（复用 deep_gemm_sm121，探针纪律同源）。"""
    key = module.__name__ + "#sparse_wire.configurer"
    if key in _INSTALLED or not enabled():
        return False
    try:
        from deep_gemm_sm121 import install as _dg_install

        ok = _dg_install(module)
    except Exception as exc:  # pragma: no cover - adapter 同目录缺件
        _logger.warning("sparse_wire: deep_gemm_sm121 unavailable: %s", exc)
        return False
    _INSTALLED.add(key)
    return ok


def install_memory_pool(module) -> bool:
    """断线#1b：sparse 门开 ⇒ 池页钉 64（SM121 dense block_kv 铁律）。

    锚=memory_pool 模块自身（DSV41_INDEX_PAGE_SIZE 常量与 dsv41_index_page_size()
    都在此；configurer 无此锚——deep_gemm_sm121.install_memory_pool 的原型挂错
    了模块）。exec_module 后重绑仍有效：池构造在更晚的时刻读模块全局。
    """
    key = module.__name__ + "#sparse_wire.memory_pool"
    if key in _INSTALLED or not enabled():
        return False
    if not hasattr(module, "DSV41_INDEX_PAGE_SIZE"):
        _logger.warning("sparse_wire: memory_pool anchor missing; no page pin")
        return False
    page = int(getattr(module, "DSV41_INDEX_PAGE_SIZE", 128))
    module.DSV41_INDEX_PAGE_SIZE = 64
    module.dsv41_index_page_size = lambda: 64
    _INSTALLED.add(key)
    _logger.info(
        "sparse_wire: indexer-K pool page %d -> 64 (SM121 dense block_kv iron "
        "law; sparse 512B-stride law needs 128 and is moot until an sm12x "
        "sparse kernel exists -- see geo_check.py)",
        page,
    )
    return True


def install_v41_indexer(module) -> bool:
    """能力探针：make_candidate_indexer 选 sparse 对前干跑 sparse 核面。"""
    key = module.__name__ + "#sparse_wire.v41_indexer"
    if key in _INSTALLED or not enabled():
        return False
    if not hasattr(module, "make_candidate_indexer"):
        _logger.warning("sparse_wire: v41_indexer anchor missing; no probe")
        return False
    _orig_make = module.make_candidate_indexer
    state = {"probed": False, "ok": None, "why": ""}

    def make_candidate_indexer(*, token_to_kv_pool, req_to_token, page_size,
                               candidate_topk_blocks, candidate_block_size):
        prefill, decode = _orig_make(
            token_to_kv_pool=token_to_kv_pool,
            req_to_token=req_to_token,
            page_size=page_size,
            candidate_topk_blocks=candidate_topk_blocks,
            candidate_block_size=candidate_block_size,
        )
        if candidate_topk_blocks <= 0:
            return prefill, decode  # dense 绕行臂，与探针无关
        from sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks import (
            DenseBlocksBackend,
        )
        dense = DenseBlocksBackend(
            token_to_kv_pool=token_to_kv_pool,
            req_to_token=req_to_token,
            candidate_topk_blocks=candidate_topk_blocks,
            candidate_block_size=candidate_block_size,
            use_deep_gemm_prefill=module._use_deep_gemm_prefill(),
        )
        is_sparse_pair = type(decode).__name__ == "SparseTableBackend"
        if not is_sparse_pair:
            return prefill, decode
        if not state["probed"]:
            state["probed"] = True
            state["ok"], state["why"] = _probe_sparse_capability()
        if state["ok"]:
            print(
                f"[sparse_wire] sparse-table pair ENGAGED (probe ok: "
                f"get_paged_sparse_mqa_logits_metadata + "
                f"fp8_fp4_paged_sparse_mqa_logits on this build)",
                flush=True,
            )
            return prefill, decode
        print(
            f"[sparse_wire] sparse-table pair REFUSED -> DenseBlocksBackend pair "
            f"(candidate semantics kept: int32 block tables, consumers top-k "
            f"among candidates). why: {state['why']}",
            flush=True,
        )
        return dense, dense

    module.make_candidate_indexer = make_candidate_indexer
    _INSTALLED.add(key)
    return True


def _probe_sparse_capability(page: int = 64, heads: int = _PROBE_HEADS):
    """1 行干跑两个 sparse 入口。返回 (ok, 诊断)。

    在 make_candidate_indexer 调用点执行（模型装载后、服务前；CUDA 已初始化）。
    覆盖三层拒因：API 缺失 / arch 硬断（arch==10）/ 512B 页步长律（page×68）。
    异常文本进横幅，拒因可从 boot log 直接读出。
    """
    try:
        import torch
        import deep_gemm

        if not torch.cuda.is_available():
            return False, "cuda unavailable"
        dev = torch.device("cuda")
        k_cache = torch.zeros(page * _PROBE_PAGES, page, 1, 68,
                              dtype=torch.uint8, device=dev)
        blocks = torch.zeros(1, _PROBE_BLOCKS, dtype=torch.int32, device=dev)
        page_table = torch.arange(
            _PROBE_PAGES, dtype=torch.int32, device=dev).unsqueeze(0)
        seq_lens = torch.full((1,), page, dtype=torch.int32, device=dev)
        request_ids = torch.zeros(1, dtype=torch.int32, device=dev)
        sched = deep_gemm.get_paged_sparse_mqa_logits_metadata(
            seq_lens, page_table, request_ids, page, blocks,
            torch.int8, 8)  # q_dtype=fp4 载荷 dtype；sparse_block_kv=8
        q = torch.zeros(1, 1, heads, 64, dtype=torch.int8, device=dev)
        q_sf = torch.zeros(1, 1, heads, dtype=torch.int32, device=dev)
        w = torch.zeros(1, heads, dtype=torch.bfloat16, device=dev)
        deep_gemm.fp8_fp4_paged_sparse_mqa_logits(
            (q, q_sf), k_cache, w, sched, _PROBE_BLOCKS, 8)
        torch.cuda.synchronize()
        return True, "ok"
    except Exception as exc:  # TORCH_CHECK/DGException/缺失符号一律=拒
        text = " ".join(str(exc).split())[:300]
        return False, f"{type(exc).__name__}: {text}"


def install_sparse_table(module) -> bool:
    """断线#2：非 chunked publish_decode 改走 topk_transform_paged_from_metadata。"""
    key = module.__name__ + "#sparse_wire.sparse_table"
    if key in _INSTALLED or not enabled():
        return False
    cls = getattr(module, "SparseTableBackend", None)
    if cls is None or not hasattr(cls, "publish_decode"):
        _logger.warning("sparse_wire: sparse_table anchor missing; no fix #2")
        return False
    from sglang.srt.layers.attention.dsv4.indexer import (
        topk_transform_paged_from_metadata,
    )

    def publish_decode(self, inputs):
        # = stock publish_decode（520d6d0 版，r032b 镜像内 sparse_table.py:171）
        # 除标注处外逐行同源；上游化 = 删除本重绑，树内 2 行替换（见 patches/0001）。
        import torch

        data = module.get_deep_gemm_decode_data(inputs, self.token_to_kv_pool)
        metadata = inputs.paged_metadata
        seq_lens = metadata.compressed_seq_lens.reshape(-1)
        if isinstance(metadata.deep_gemm_metadata, list):
            return self._publish_decode_chunked(inputs, data, seq_lens)
        logits = module.deep_gemm_fp4_paged_mqa_logits(
            (data.q_fp4, data.q_sf),
            data.k_cache,
            data.weights,
            metadata.compressed_seq_lens,
            metadata.page_table,
            metadata.deep_gemm_metadata,
            metadata.max_compressed_seq_len,
        )
        main_stream = torch.cuda.current_stream()
        self.alt_stream.wait_stream(main_stream)
        # The block-selection chain reads logits after the main stream moves on.
        logits.record_stream(self.alt_stream)
        # ---- 断线#2 修复（2 行语义差，520d6d0 上游仍直调 v2 传
        # metadata.topk_metadata——use_topk_v2=False 时那是 CPU 空哑元
        # metadata.py:290 torch.empty((0,))）。
        # 改走 from_metadata：其按 metadata.use_topk_v2 分派 v1/v2 计划；
        # decode 新合同无 raw（from_metadata raw 缺省 None）。----
        topk_transform_paged_from_metadata(
            logits, metadata, inputs.out_page_indices
        )
        # per row: block count for the block top-k, sparse-row length for the
        # consumers
        with torch.cuda.stream(self.alt_stream):
            nblocks, row_valid_lens = module.candidate_row_lens(
                seq_lens, self.topk_blocks)
            blocks = module.amax_topk_blocks(
                logits, seq_lens, nblocks, self.topk_blocks)
            # in place: ascending, INT32_MAX padded, plus the blocks as pool
            # slots / 8
            phys_blocks = module.sort_candidate_blocks(
                blocks, seq_lens, metadata.page_table,
                metadata.compressed_page_size)
            schedule = module.build_sparse_indexer_schedule(
                blocks, seq_lens, metadata.page_table,
                metadata.compressed_page_size, data.q_fp4.dtype,
                self._get_request_ids(inputs, data.q_fp4.shape[0], blocks.device),
            )
            # consume_decode reads these on the main stream
            for t in (blocks, schedule, phys_blocks, row_valid_lens):
                t.record_stream(main_stream)
            ready = torch.cuda.Event()
            ready.record(self.alt_stream)
            return module._SparseTable(
                blocks=blocks, schedule=schedule, phys_blocks=phys_blocks,
                valid_lens=row_valid_lens, ready=ready,
            )

    cls.publish_decode = publish_decode
    _INSTALLED.add(key)
    _logger.info("sparse_wire: sparse_table.publish_decode rewired "
                 "(non-chunked topk via from_metadata; upstreamable 2-line)")
    return True


def install_full_topk(module) -> bool:
    """断线#3：topk_decode 对 deep_gemm_metadata=None 转 torch 路径。"""
    key = module.__name__ + "#sparse_wire.full_topk"
    if key in _INSTALLED or not enabled():
        return False
    cls = getattr(module, "FullTopKIndexer", None)
    if cls is None:
        _logger.warning("sparse_wire: full_topk anchor missing; no fix #3")
        return False
    _orig = cls.topk_decode

    def topk_decode(self, inputs):
        md = inputs.paged_metadata
        if self.use_deep_gemm_decode and getattr(md, "deep_gemm_metadata", "x") is None:
            # 上游化（patches/0002）：None = 本 forward 被指到 torch 面
            # （HIP/XPU/FORCE_TORCH），stock dispatch 会把 None 塞给核。
            return self._torch_decode(inputs)
        return _orig(self, inputs)

    cls.topk_decode = topk_decode
    _INSTALLED.add(key)
    _logger.info("sparse_wire: full_topk.topk_decode None-metadata guard in")
    return True


def install_index_logits(module) -> bool:
    """T×L 预算门：dense paged 打分唯一咽喉处 rows×cols 断言。

    2026-09-30 用户裁定改：预算门独立于 sparse 总门**常开**（缺省 2.0e8 元素律；
    DSV41_TL_BUDGET_ELEMS=off/0 才关）——dense 绕行态恰是危险态，防线必须全时在位。
    """
    key = module.__name__ + "#sparse_wire.index_logits"
    if key in _INSTALLED or _budget_elems() is None:
        return False
    orig = getattr(module, "deep_gemm_fp4_paged_mqa_logits", None)
    if orig is None:
        _logger.warning("sparse_wire: index_logits anchor missing; no budget gate")
        return False
    _seen = {"warned": 0}

    def deep_gemm_fp4_paged_mqa_logits(q_fp4, k_cache, weights, seq_lens,
                                       page_table, deep_gemm_metadata,
                                       max_seq_len):
        budget = _budget_elems()
        if budget is not None:
            rows = q_fp4[0].shape[0] if isinstance(q_fp4, (tuple, list)) \
                else q_fp4.shape[0]
            elems = rows * int(max_seq_len)
            if elems > budget:
                raise SparseWireBudgetGate(
                    f"dense paged indexer logits {rows}x{int(max_seq_len)}="
                    f"{elems:.3g} elems > {BUDGET_ENV}={budget:.3g} "
                    f"(fork T*L<=2.0e8 law; ~{elems * 4 / 2**30:.1f}GiB fp32 "
                    f"x~3 transients; C13). Fix: row-chunk the forward "
                    f"(PagedIndexerMetadata rows_per_chunk) or lower "
                    f"--chunked-prefill-size, or set {BUDGET_ENV}=off to disarm."
                )
            if _seen["warned"] < 3 and elems * 10 > budget:
                _seen["warned"] += 1
                _logger.warning(
                    "sparse_wire: dense paged logits %dx%d=%.3g elems within "
                    "10x of %s budget", rows, int(max_seq_len), elems, BUDGET_ENV)
        return orig(q_fp4, k_cache, weights, seq_lens, page_table,
                    deep_gemm_metadata, max_seq_len)

    module.deep_gemm_fp4_paged_mqa_logits = deep_gemm_fp4_paged_mqa_logits
    _INSTALLED.add(key)
    _logger.info("sparse_wire: T*L budget gate armed at "
                 "index_logits.deep_gemm_fp4_paged_mqa_logits "
                 "(default %s elems; %s=off disarms)", DEFAULT_TL_BUDGET, BUDGET_ENV)
    return True


# ── scoring 行块预算（fork 变更 #16 血统，2026-09-30 点3 采纳）─────────────
# main 树 scoring.py 硬编码 _DEEP_GEMM_SCORE_BUDGET_BYTES=2GiB / _TORCH 1GiB
# （行块上限）。fork 生产把它收到 128MiB（变更 #16：2GiB→512MiB→128MiB
# 2026-09-23 定板）并带 env 键 DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES。此处
# 把同键接到 main 树：缺省=134217728（fork 定板），off/0=回 stock 2GiB。
SCORE_BUDGET_ENV = "DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES"
DEFAULT_SCORE_BUDGET = 134217728           # 128MiB，fork 定板值


def _score_budget():
    """行块打分工作区预算（字节）；None=关（回 stock）。"""
    raw = os.environ.get(SCORE_BUDGET_ENV)
    if raw is None:
        return DEFAULT_SCORE_BUDGET
    raw = raw.strip().lower()
    if raw in _OFF:
        return None
    return int(float(raw))


def install_scoring(module) -> bool:
    """scoring 行块预算 env 化：缩 _DEEP_GEMM/_TORCH 两个常量（常开）。"""
    key = module.__name__ + "#sparse_wire.scoring_budget"
    if key in _INSTALLED:
        return False
    budget = _score_budget()
    if budget is None:
        return False
    dg = getattr(module, "_DEEP_GEMM_SCORE_BUDGET_BYTES", None)
    tw = getattr(module, "_TORCH_SCORE_BUDGET_BYTES", None)
    if dg is None and tw is None:
        _logger.warning("sparse_wire: scoring budget anchors missing; skipped")
        return False
    if dg is not None:
        module._DEEP_GEMM_SCORE_BUDGET_BYTES = budget
    if tw is not None:
        module._TORCH_SCORE_BUDGET_BYTES = max(budget, 64 << 20)
    _INSTALLED.add(key)
    _logger.info(
        "sparse_wire: scoring row-chunk budgets <- %s=%d (deep_gemm %s->%d, "
        "torch %s->%d); %s=off restores stock 2GiB",
        SCORE_BUDGET_ENV, budget,
        format(dg, ","), module._DEEP_GEMM_SCORE_BUDGET_BYTES,
        format(tw, ","), module._TORCH_SCORE_BUDGET_BYTES, SCORE_BUDGET_ENV)
    return True


def summary() -> str:
    budget = _budget_elems()
    sb = _score_budget()
    return (
        f"gate={os.environ.get(GATE_ENV, '(off)')} "
        f"installed={len(_INSTALLED)} hooks "
        f"tl_budget={'off' if budget is None else format(budget, ',')} "
        f"score_budget={'off' if sb is None else format(sb, ',')}"
    )
