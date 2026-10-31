"""R1 键控接缝：DenseBlocks 消费面 → 候选内 gather 打分（缺省关 = 零加载，零漂移）。

挂点纪律与 sparse_wire.py 同源（campaign adapter 模式）：本模块只被 sitecustomize 侧的
finder 分派调用（部署时挂 ~/migrate-assets/dsv41/adapter/ —— **本段只交付代码与设计，
不做部署侧写入**）；镜像树不动。

== 键 =========================================================================
- ``DSV41_SPARSE_LOCAL_CONSUME``：总门。缺省关（不在 _ON 集合 = 不安装任何钩、不
  import 任何本目录模块——「零加载」即此义：关态下本模块对进程的全部副作用 = 一次布尔判断）。
- ``DSV41_SPARSE_LOCAL_CONSUME_TIER``：``triton``（缺省，生产档）或 ``torch``（参考档，
  供靴上 A/B 与对拍）。tier 键只在总门开时才被读。
- ``DSV41_SPARSE_LOCAL_PREFILL``：第二段（prefill 消费面 gather 化）。缺省关 = 只换
  decode 消费面（census 5 发射中的 4）；=1 时 eager prefill 的消费面同样 gather 化
  （torch 档走引擎 ``indexer.scores`` 同链，triton 档走 gather 内核）。captured-prefill
  图内接缝 = 靴上判别项（FIRE-READINESS.md），本键不辖图捕获面。
- ``DSV41_SPARSE_LOCAL_DUMP``：Selection 落盘开关（VERIFICATION.md 判别①引擎级扩展；
  路径空/键缺=关）。见 selection_dump.py。

== 形式探针（admission_r1 的 FC2 供源）=======================================
``engaged()`` = gather 消费面在引擎实况中上岗（install 成功且能力探针过）。形式感知
准入门（admission_r1.evaluate）每请求惰性读本探针——配置开而探针未过 = 门坍缩 dense
限额，这正是 R1 与「抬 TL_BUDGET」的本质差。

== 安装纪律（已定谳 bug 类规避——教义）======================================
**禁 class 级 ``hasattr`` 探 instance 属性**：``DenseBlocksBackend`` 的
``token_to_kv_pool / req_to_token / topk_blocks / block_size / use_deep_gemm_prefill``
全部是 ``__init__`` 内绑定的**实例**属性；安装时刻手上只有类对象，
``hasattr(DenseBlocksBackend, "token_to_kv_pool")`` 恒 False，会把「锚在」误判成「缺件」
而静默走回退臂——该 bug 类已定谳（战役判例），必须用 **``__init__`` 源探针**：
读 ``inspect.getsource(cls.__init__)`` 文本，确认全部依赖属性名都在赋值面出现
（``_init_source_probe``）。unit_xcheck.py 第 5 节带反向标本：hasattr 探针必须在标本上
变红、源探针必须变绿，否则「绿」与「瞎」同形。

== 能力探针（安装时一次）====================================================
总门开 ⇒ import 依赖（reference_impl / triton_kernel）+ （CUDA 在场时）微型干跑 gather
内核（1 行 × 8 候选）。成功 = ``[sparse_local_consume] gather consumer ENGAGED`` 横幅 +
返回 ``GatherConsumeDenseBlocks`` 对；失败 = ``REFUSED -> stock DenseBlocks pair`` 横幅 +
原对原样返回（现网行为零漂移，回退不需要状态清理——本件不新建池/缓存）。

== 图捕获纪律（R1-FIX，2026-10-03/04 根因修复）==============================
``consume_decode`` 进入引擎 decode CUDA graph capture 路径（崩溃链：
``decode_cuda_graph_runner.run_once → … → _low_ratio_index_topk → consume_decode``）。
该面**结构性禁数据依赖同步算子**（``nonzero``/``.item()``/``.tolist()`` 等需宿主
同步或输出形状随数据定形的算子=``cudaErrorStreamCaptureUnsupported``，R1STDFORM 认证火
四机同靴同错根因）。修复=写回槽按列追踪 gather（``topk_among_candidates_cols``），
全静态形状张量算子；**CUDA 图 replay 读 replay 时刻 buffer**——topk/argsort 在 replay
期重算，位置-槽配对由共享索引张量在执行时刻建立，不依赖捕获期数据（等价性逐行论证
见 R1-FIX-CAPTURESAFE-20261004.md）。``consume_prefill``=eager 面（宿主循环合法），
captured-prefill × 二段键共存=靴上判别项（FIRE-READINESS §五），不在本修复辖内。
host 侧静态断言=unit_xcheck 第 4f 节（AST 禁表+红标本+eager 面分界）；动态实证=容器
冒烟 p12（真捕获+replay 读数+拔件红例）；变异杀手=M17。

== R1-FIX-2（2026-10-04；R1FIX2-ADJUDICATION 实施授权；本工作副本=新世系候选）====
**FIX-A（prefill 槽双包装）**：R1RECERT 取证定谳——旧 ``return prefill,
_ConsumesAs(gather, decode, stage2)`` 把 pair 的 prefill 槽原样返回 stock 对象，
而引擎 prefill 分派打的是 prefill 槽（backend.py:3115/:3118），``decode_candidates
.consume_prefill`` 引擎树零调用点 ⇒ stage2 结构性死代码（横幅 prefill_consume=gather
与运行期背离）。修法=两槽都过 ``_ConsumesAs`` + 补 ``publish_prefill`` 透传（旧行下
不需要；包装后不补=publish 断链=新错值面）。gather.consume_prefill 只读
``published.blocks``，对 stock publish_prefill 两种产物（DeepGEMM flattened-K /
torch per-request，皆 BlockIds）同构。capture 面不对称的正当性：引擎 captured-prefill
路径（backend.py:2744→3122）结构性绕开 candidates（直调 full_topk），gather 的
consume_prefill（宿主循环 .tolist()/.item()）结构性不进捕获——eager-only 面接线修复，
R1-FIX 的 decode 面 capture-safe 论证原样继承（FIX-A 不动 decode 执行路径）。
**FIX-A2（消费面共轭完备，教义 #27）**：stock 消费者读 ``published.blocks`` 前等待
publish 的 ``ready`` 事件（sparse_table.py:305）；生产路径 publish_decode 的块选择链
在 **alt_stream** 产出（:206-226）。旧世系 gather 消费面缺此等待=潜伏跨流竞态——
既往窗口 filtered 图从未 dispatch 故未显形；第三认证火长 ctx 窗=filtered 图首次上
热路径，不补=图内两分支无依赖边的静默错值面（#12）。修法=``getattr(published,
"ready", None)`` 有则 ``wait_event``（捕获兼容：落为图依赖边，与 stock 同机制）；
BlockIds 产物无 ready→跳过。
**FIX-C（捕获期早退 fail-loud，教义 #12）**：捕获期 ``bs==0``/``lmax==0`` 不再静默
return，改 raise（图内零消费内核+replay 期 out 停 reset 态且无崩溃信号=静默错值原型；
R1RECERT 已证本 boot 捕获期 lmax=容量上界≠0，本守卫零改变已验证行为，只把假想静默
跳过变成捕获期硬红）。eager 面保留良性早退（stock decode_scores:391-401 同款）。
``is_current_stream_capturing()`` 为宿主侧查询（无设备同步），捕获兼容。
判据三层化（FIX-D）与长 ctx 断言见本目录 p12_assertion_graph_gather.py +
FIXD-CRITERIA-LAYERS-20261004.md；位等三对照同构臂门设计（#21）随 RE-CERT-CARD-3
草案交付。

== 红线 ======================================================================
不触碰任何准入门（admission_gate / sparse_wire 预算门 / needle_probe）；
publish 面不动（论文「retaining the initial full-range pass」）；
本模块不写任何文件系统路径。
"""

from __future__ import annotations

import inspect
import logging
import os

_logger = logging.getLogger(__name__)

GATE_ENV = "DSV41_SPARSE_LOCAL_CONSUME"          # 总门，缺省关
TIER_ENV = "DSV41_SPARSE_LOCAL_CONSUME_TIER"     # triton（缺省）| torch
PREFILL_ENV = "DSV41_SPARSE_LOCAL_PREFILL"       # 第二段 prefill 消费面，缺省关
_ON = ("1", "true", "yes", "on")
_INSTALLED: set = set()
# 形式探针状态：True 仅在 install() 走完（锚在+源探针过+能力探针过+钩已换）后置位。
# admission_r1 FC2 每请求读它；REFUSED 任何一步 = False（门坍缩 dense）。
_ENGAGEMENT = {"gather": False}

# GatherConsumeDenseBlocks 依赖的 DenseBlocksBackend 实例属性（__init__ 绑定面）。
_REQUIRED_INSTANCE_ATTRS = (
    "token_to_kv_pool",
    "req_to_token",
    "topk_blocks",
    "block_size",
    "use_deep_gemm_prefill",
)


def enabled() -> bool:
    return os.environ.get(GATE_ENV, "").strip().lower() in _ON


def _tier() -> str:
    t = os.environ.get(TIER_ENV, "triton").strip().lower()
    return t if t in ("triton", "torch") else "triton"


def prefill_enabled() -> bool:
    return os.environ.get(PREFILL_ENV, "").strip().lower() in _ON


def engaged() -> bool:
    """gather 消费面是否在引擎实况中上岗（admission_r1 FC2 的形式供源）。

    True 的充要条件：install() 完整走完一次（含能力探针干跑）。REFUSED/锚缺/键关
    ⇒ False。探针态在 install 期一次性求值（引擎侧 mount 发生在模型构建期，晚于
    admission 的武装；admission 惰性重估保证「晚到/晚拒都跟得上」）。
    """
    return bool(_ENGAGEMENT["gather"])


def _init_source_probe(cls: type, attrs: tuple) -> tuple:
    """``__init__`` 源探针：返回 (ok, why)。ok = cls.__init__ 源文本含全部属性赋值名。

    教义注：这里**禁止**退化成 ``hasattr(cls, a)``——那是「探类找实例属性」，恒 False，
    已定谳 bug 类（见模块 docstring）。源文本出现 ``self.<a> =`` 才算锚在。
    """
    try:
        src = inspect.getsource(cls.__init__)
    except (OSError, TypeError) as exc:
        return False, f"{cls.__name__}.__init__ source unreadable: {exc}"
    missing = [a for a in attrs if f"self.{a}" not in src]
    if missing:
        return False, f"__init__ does not bind {missing}"
    return True, "ok"


def install(module) -> bool:
    """挂点 = ``sglang...v41_indexer`` 模块（与 sparse_wire.install_v41_indexer 同锚）：
    包 ``make_candidate_indexer``，把返回对的消费面换成 GatherConsumeDenseBlocks。

    关态：立即 False，不 import 任何重件（零加载）。锚缺/探针拒：False + 横幅（不静默）。
    """
    key = module.__name__ + "#sparse_local_consume"
    if key in _INSTALLED or not enabled():
        return False
    if not hasattr(module, "make_candidate_indexer"):
        _logger.warning("sparse_local_consume: v41_indexer anchor missing; no mount")
        return False

    from sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks import (
        BlockIds,
        DenseBlocksBackend,
    )

    ok, why = _init_source_probe(DenseBlocksBackend, _REQUIRED_INSTANCE_ATTRS)
    if not ok:
        print(
            f"[sparse_local_consume] gather consumer REFUSED -> stock DenseBlocks "
            f"pair. why: init-source probe: {why}",
            flush=True,
        )
        return False

    tier = _tier()
    ok, why = _capability_probe(tier)
    if not ok:
        print(
            f"[sparse_local_consume] gather consumer REFUSED -> stock DenseBlocks "
            f"pair. why: tier '{tier}' probe: {why}",
            flush=True,
        )
        return False

    cls = _make_gather_class(DenseBlocksBackend, BlockIds, tier)
    stage2 = prefill_enabled()
    print(
        f"[sparse_local_consume] gather consumer ENGAGED (tier={tier}; "
        f"prefill_consume={'gather' if stage2 else 'stock'}; consume "
        f"face scores only the {2048 * 8}-slot candidate pool, publish keeps the "
        f"full-range pass; launch width lmax -> 16384)",
        flush=True,
    )

    _orig_make = module.make_candidate_indexer

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
            return prefill, decode  # dense 绕行臂，与 gather 无关
        gather = cls(
            token_to_kv_pool=token_to_kv_pool,
            req_to_token=req_to_token,
            candidate_topk_blocks=candidate_topk_blocks,
            candidate_block_size=candidate_block_size,
            use_deep_gemm_prefill=module._use_deep_gemm_prefill(),
        )
        # 只换消费面：publish 语义（全量打分 + amax 块选择）原样保留——论文首层全扫。
        # 第二段（PREFILL_ENV=1）连 eager prefill 消费面一起换；decode 对先行。
        # [R1-FIX-2 FIX-A] R1RECERT 取证定谳：旧写法把 pair 的 prefill 槽原样返回
        # stock 对象，而引擎 prefill 分派打的是 prefill 槽（deepseek_v4_backend.py:3118
        # self.prefill_candidates.consume_prefill；对装配见 :1128），_ConsumesAs.consume_prefill 无任何
        # 引擎调用者 ⇒ stage2 结构性死代码（横幅 prefill_consume=gather 与运行期背离）。
        # 修法=两个槽都过 _ConsumesAs（publish_prefill/publish_decode 均原样透传，
        # 消费面按 stage2 分派）；gather.consume_prefill 只读 published.blocks，
        # 对 BlockIds/_SparsePrefillTable 两种 publish 产物同构。
        return (
            _ConsumesAs(gather, prefill, stage2),
            _ConsumesAs(gather, decode, stage2),
        )

    module.make_candidate_indexer = make_candidate_indexer
    _INSTALLED.add(key)
    _ENGAGEMENT["gather"] = True   # 形式探针置位（admission FC2 供源）
    return True


class _ConsumesAs:
    """decode/prefill 对的外观保持 = 原对（publish/元数据面全同），仅消费面分派到
    gather 实现。避免整类替换引入未审计面（class 级 monkey-patch 的教训同前）。"""

    def __init__(self, gather_backend, orig_backend, stage2: bool = False):
        self._gather = gather_backend
        self._orig = orig_backend
        self._stage2 = stage2

    def publish_decode(self, inputs):
        return self._orig.publish_decode(inputs)

    def consume_decode(self, inputs, published):
        self._gather.consume_decode(inputs, published)

    # [R1-FIX-2 FIX-A] prefill 槽的 publish 透传（原实现缺此方法——旧行下
    # prefill 槽未包装故不需要；两槽都包装后必须补，否则 publish_prefill 断链）。
    def publish_prefill(self, inputs):
        return self._orig.publish_prefill(inputs)

    def consume_prefill(self, inputs, published):
        if self._stage2:
            self._gather.consume_prefill(inputs, published)
        else:
            self._orig.consume_prefill(inputs, published)


def _make_gather_class(base, _block_ids_cls, tier: str):
    """构造 GatherConsumeDenseBlocks（base=DenseBlocksBackend）。覆写 consume_decode；
    PREFILL_ENV=1 时连 consume_prefill（eager 面）一起覆写。"""

    if tier == "triton":
        from triton_kernel import gather_index_logits_decode as _score
    else:
        from reference_impl import gathered_decode_logits as _score
    from reference_impl import (
        candidate_positions,
        candidate_slots,
        topk_among_candidates_cols,
    )

    class GatherConsumeDenseBlocks(base):
        """consume_decode[/consume_prefill] = 候选内 gather 打分（reference_impl
        语义，tier 决定载体）。publish_* 继承 stock（论文首层全扫）。"""

        def consume_decode(self, inputs, published) -> None:
            req, pos = inputs.req_rows, inputs.positions
            bs = req.shape[0]
            inputs.reset_outputs()
            # [R1-FIX-2 FIX-C] 捕获期早退=静默错值面（教义 #12）：若 bs==0/lmax==0
            # 在 stream capture 中早退，图内将永久记录「零消费内核」，replay 期
            # out 停在 reset 状态且无崩溃信号——比 R1STDFORM 的捕获期崩溃（fail-loud）
            # 更难抓。R1RECERT 取证已证本 boot 捕获期 lmax=容量上界≠0（grid 直读），
            # 本守卫不改变已验证行为，只把「假想中的静默跳过」变成捕获期硬红。
            # eager 面（含 idle 批）保留良性早退（stock decode_scores:352-360 同款语义）。
            import torch as _t

            _capturing = _t.cuda.is_current_stream_capturing()
            if bs == 0:
                if _capturing:
                    raise RuntimeError(
                        "sparse_local_consume: bs==0 during graph capture — "
                        "refusing to capture an empty consumer (silent-wrong-"
                        "value guard, doctrine #12; see FORENSICS-R1FIX2-20261004)"
                    )
                return
            ratio = inputs.compress_ratio
            indexer = inputs.indexer
            lens = (pos + 1) // ratio
            metadata = inputs.paged_metadata
            # 与 decode_scores:358 同源的可见性上界（replay 界在 metadata，不做 capture 期读长）
            lmax = min(metadata.max_compressed_seq_len, self.req_to_token.shape[1] // ratio)
            if lmax == 0:
                if _capturing:
                    raise RuntimeError(
                        "sparse_local_consume: lmax==0 during graph capture — "
                        "refusing to capture an empty consumer (silent-wrong-"
                        "value guard, doctrine #12; see FORENSICS-R1FIX2-20261004)"
                    )
                return
            assert published is not None and published.blocks.shape[0] == bs
            # [R1-FIX-2 FIX-A2] 共轭完备（教义 #27）：stock 消费者在读 blocks 前等待
            # publish 的 ready 事件（sparse_table.py:305 `current_stream().wait_event
            # (published.ready)`）——生产路径 SparseTableBackend.publish_decode 的
            # 块选择链在 **alt_stream** 上产出 blocks（sparse_table.py:200-222，
            # ready.record(self.alt_stream)），跨流无执行序保证；gather 消费面若不
            # 等待=第三认证火 filtered 图 replay 窗的静默错值面（#12：图内两分支
            # 无依赖边，replay 乱序 → gather 读未就绪 blocks → Selection 错值无崩溃
            # 信号）。本守卫 6dbdf2d2 世系缺失=潜伏缺陷（既往窗口 filtered 图从未
            # dispatch 故未显形——R1RECERT 全绿不构成反证）。captured/wait 均为图
            # 捕获合法原语（cudaStreamWaitEvent 在捕获中落为图依赖边，与 stock 同
            # 机制）；BlockIds 产物无 ready 属性（getattr None）→ 跳过，同
            # dense_blocks 语义。prefill 面 ready 记录在当前流（_build_prefill_table
            # :358-359）→ wait 平凡成立，仅合同对称。
            _ready = getattr(published, "ready", None)
            if _ready is not None:
                _t.cuda.current_stream().wait_event(_ready)
            q = indexer.queries(inputs.q_lora, inputs.freqs_cis[pos])
            weights = indexer.head_weights(inputs.x)
            blocks = published.blocks
            cand_pos = candidate_positions(blocks, lens, self.block_size)
            cand_slot = candidate_slots(
                blocks, lens, req, self.req_to_token, ratio, self.block_size
            )
            table = self.token_to_kv_pool.get_index_k_with_scale_buffer(inputs.layer_id)
            page_size = table.shape[1] // 68
            cand_logits = _score(q, weights, cand_slot, table, page_size)
            k = min(indexer.index_topk, lmax)
            # write_decode 合同（scoring.py:465-471）：-1→lmax → 位置升序 → reach → 双写。
            # 槽随选点走列（R1-FIX capture-safe，2026-10-03/04 根因修复；选路 (c)
            # 静态形状替代，全论证见 R1-FIX-CAPTURESAFE-20261004.md §三/§四）：
            # 位置↔槽的配对由**同一 top.indices / argsort 张量**在同一执行时刻建立
            # ——decode CUDA 图捕获路径禁数据依赖同步算子（nonzero 需宿主同步定形
            # =四机同靴同错根因），本路径全静态形状张量算子（topk/argsort/gather/
            # masked_fill/where=stock write_decode 同族，捕获兼容性有崩溃链前段
            # 执行证据+容器 p12 实证）。replay 期 topk/argsort 对 replay 时刻
            # buffer 重算，位置-槽配对在 replay 时刻重建。
            # 语义等价（对旧 nonzero 散射路径）：活选点 p 的槽 = cand_slot[列 c:
            # cand_pos[c]=p]（行内活候选位置互异 ⇒ 位置↔列单射）= 旧 slot_by_pos[p]
            # 同值；死选点 posx=lmax ⇒ reach=False 槽被 -1 掩蔽（旧路径读
            # slot_by_pos[lmax-1] 同被掩蔽）——零语义差。
            import torch as _torch

            picked, pick_cols = topk_among_candidates_cols(cand_logits, cand_pos, k)
            slot_pick = cand_slot.gather(1, pick_cols)
            posx = picked.masked_fill(picked < 0, lmax)
            order = posx.argsort(dim=-1)
            pos_s = posx.gather(1, order)
            slot_s = slot_pick.gather(1, order)
            reach = pos_s < lens[:, None]
            inputs.out_page_indices[:bs, :k] = _torch.where(
                reach, slot_s, _torch.full_like(slot_s, -1)
            ).to(_torch.int32)
            # raw 面=新合同 decode 无 raw（types.py DecodeInputs 仅 out_page_indices）。
            try:
                import selection_dump as _sd

                _sd.maybe_dump(
                    "decode", inputs.layer_id,
                    page=inputs.out_page_indices[:bs, :k], raw=None,
                )
            except Exception:
                pass  # 量具面失败不扰产径（dump 自身 fail-closed 于键）

        def consume_prefill(self, inputs, published) -> None:
            """第二段：eager prefill 消费面 gather 化（每请求只对候选位置打分）。

            torch 链与 stock ``_torch_consume_prefill`` 同源（prefill_requests 的
            q/weights/dequant 三件套 + write_prefill 合同），仅把「全宽 scores」换成
            「候选宽 scores」（宽度 8n ≤ 16,384，与 lc 无关）；triton 档复用 decode 的
            gather 内核（行维 = 该请求 chunk 行）。
            """
            import torch as _torch

            from reference_impl import topk_among_candidates as _topk_cand

            assert published is not None
            # [R1-FIX-2 FIX-A2] 同 decode 面：读 blocks 前等待 publish 的 ready
            # （若有）——_SparsePrefillTable 继承 _SparseTable 带 ready 事件
            # （prefill 面记录于当前流=sparse_table.py:358-359，wait 平凡成立；
            # BlockIds 无该属性→跳过）。合同对称，防未来产物换流。
            _ready = getattr(published, "ready", None)
            if _ready is not None:
                _torch.cuda.current_stream().wait_event(_ready)
            inputs.reset_outputs()
            pool = self.token_to_kv_pool
            ratio = inputs.compress_ratio
            indexer = inputs.indexer
            req, pos = inputs.req_rows, inputs.positions
            assert req is not None, "gather prefill consume needs req_rows"
            q = indexer.queries(inputs.q_lora, inputs.freqs_cis[pos])
            weights = indexer.head_weights(inputs.x)
            compress_lens = (pos + 1) // ratio
            topk = indexer.index_topk
            for r in _torch.unique_consecutive(req).tolist():
                tok = (req == r).nonzero().squeeze(1)
                lens_r = compress_lens[tok]
                lc = int(lens_r.max().item())
                if lc == 0:
                    continue
                k = min(topk, lc)
                blocks = published.blocks[tok]
                cand_pos = candidate_positions(blocks, lens_r, self.block_size)
                safe = cand_pos.clamp_min(0) * ratio
                cand_slot = self.req_to_token[r].to(_torch.int64)[safe] // ratio
                cand_slot = cand_slot.masked_fill(cand_pos < 0, -1)
                if tier == "triton":
                    table = pool.get_index_k_with_scale_buffer(inputs.layer_id)
                    page_size = table.shape[1] // 68
                    logits = _score(q[tok], weights[tok], cand_slot, table, page_size)
                else:
                    flat = cand_slot.reshape(-1).clamp_min(0)
                    index_k = pool.get_low_ratio_index_k_dequant(
                        inputs.layer_id, flat
                    ).view(cand_slot.shape[0], cand_slot.shape[1], -1)
                    s = indexer.scores(
                        q[tok], index_k.flatten(0, 1), weights[tok]
                    ).view(index_k.shape[0], index_k.shape[1])
                    logits = s.masked_fill(cand_slot < 0, float("-inf"))
                picked = _topk_cand(logits, cand_pos, k)
                # write_prefill 合同（scoring.py:339-353）：位置升序 → reach → 槽查表。
                # 槽按位置索引查（候选列槽先散成位置槽表——列/位混用 bug 同 decode 面）。
                idx = picked.sort(dim=-1).values
                reach = idx < lens_r[:, None]
                width = max(int(lens_r.max().item()), 1)
                slot_by_pos = _torch.zeros(
                    (tok.numel(), width), dtype=cand_slot.dtype,
                    device=cand_slot.device)
                live = cand_pos >= 0
                b_idx, c_idx = live.nonzero(as_tuple=True)
                slot_by_pos[b_idx, cand_pos[b_idx, c_idx]] = cand_slot[b_idx, c_idx]
                slot_of = slot_by_pos.gather(1, idx.clamp_min(0).clamp_max(width - 1))
                # 新合同（types.py PrefillInputs）：out_page_indices 可选、out_raw_indices
                # 必在（stock write_prefill scoring.py:348-352 同序同守卫）。
                if inputs.out_page_indices is not None:
                    inputs.out_page_indices[tok, :k] = _torch.where(
                        reach, slot_of, _torch.full_like(slot_of, -1)
                    ).to(_torch.int32)
                inputs.out_raw_indices[tok, :k] = _torch.where(
                    reach, idx, _torch.full_like(idx, -1)
                ).to(_torch.int32)
            try:
                import selection_dump as _sd

                _sd.maybe_dump(
                    "prefill", inputs.layer_id,
                    page=inputs.out_page_indices, raw=inputs.out_raw_indices,
                )
            except Exception:
                pass

    return GatherConsumeDenseBlocks


def _capability_probe(tier: str) -> tuple:
    """安装期一次干跑：依赖可 import + （CUDA 在场时）1 行 × 8 候选的微型 gather。"""
    try:
        import torch

        from reference_impl import candidate_positions, gathered_decode_logits

        if tier == "triton":
            from triton_kernel import gather_index_logits_decode
        if not torch.cuda.is_available():
            # 无 CUDA（如纯 CPU 审计机）：import 面通过即可，ENGAGED 只在靴上成立；
            # census 判别（VERIFICATION.md 判别②）才是上岗证据，本探针只挡 import 断线。
            return True, "imports ok (no cuda; on-boot probe decides)"
        dev = torch.device("cuda")
        table = torch.zeros(2 * 64, 64 * 64 + 64 * 4, dtype=torch.uint8, device=dev)
        q = torch.zeros(1, 32, 128, dtype=torch.bfloat16, device=dev)
        w = torch.zeros(1, 32, dtype=torch.bfloat16, device=dev)
        blocks = torch.zeros(1, 1, dtype=torch.int32, device=dev)
        lens = torch.tensor([8], dtype=torch.int64, device=dev)
        from reference_impl import candidate_slots

        req = torch.zeros(1, dtype=torch.int64, device=dev)
        r2t = torch.zeros((1, 64), dtype=torch.int32, device=dev)
        slots = candidate_slots(blocks, lens, req, r2t, ratio=1)
        if tier == "triton":
            gather_index_logits_decode(q, w, slots, table, page_size=64)
        else:
            gathered_decode_logits(q, w, slots, table, page_size=64)
        torch.cuda.synchronize()
        return True, "dry run ok"
    except Exception as exc:  # import 断线/探针炸一律=拒（诚实拒，不静默）
        return False, f"{type(exc).__name__}: {' '.join(str(exc).split())[:200]}"


def summary() -> str:
    return (
        f"gate={os.environ.get(GATE_ENV, '(off)')} tier={_tier()} "
        f"prefill={os.environ.get(PREFILL_ENV, '(off)')} "
        f"installed={len(_INSTALLED)} hooks engaged={engaged()}"
    )
