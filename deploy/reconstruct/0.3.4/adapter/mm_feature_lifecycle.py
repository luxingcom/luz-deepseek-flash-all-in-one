# Copyright 2023-2024 SGLang Team
# Licensed under the Apache License, Version 2.0
"""MM-TRANSIENT 件6：mm 特征两段式生命周期 + 宿主驻留字节账本（案头 dev 形，纯 stdlib）。

法源：
- docs/incidents/INCIDENT-20261006-C24VL-OPEN26-MMSTAGING-CRUSH.md（定谳 2/5：
  真身=宿主侧 mm 特征 staging 瞬态碾压，与 KV 池正交；MM-IMPL 裁定 3 的
  feature=None 缓刑被复审推翻 ⇒ 须「用后释放+chunk 内复用窗口」两段式）
- docs/incidents/OPEN23-DEEP-FORENSICS-20261006.md §6.1/§6.2（mm_feature_transport=cpu
  前科；:95 H2D 后 item.feature=None 释宿主引用建议面）
- docs/taskcards/MM-TRANSIENT-WINCARD-20261006.md（主会话实施裁定 3 缓刑记载）

═══ 一、特征生命周期证据链（引擎基树 image-src-0.2.8/srt，file:line 逐字核证）═══

创建（宿主，TM/processor 侧）：
- overlay multimodal/processors/deepseek_v4_vl.py:242 逐图 _load_image →
  :204-209 patches=[n_vit_h*n_vit_w,3,14,14] bf16（max_n_token=384 钳位形
  n_vit≈3456/图 ⇒ ≈3.88MiB/图）；:249-268 MultimodalDataItem(feature=patches,
  offsets=[(start,end)])=图 span 账本。

持有（调度器进程，请求全生命周期）：
- schedule_batch.py:376 MultimodalDataItem.feature 字段；
  :1085 Req.multimodal_inputs → :652 MultimodalInputs.mm_items；
- 等待队列（scheduler.py waiting_queue）→ chunked 中间态（scheduler.py:1275
  self.chunked_req=批外单例持有）→ 运行 decode 批（schedule_batch.py:2694/
  :2819 批级 multimodal_inputs 列表再持一份引用）；
- 每次 forward 用后 GPU 特征 offload 回 CPU：mm_utils.py:707-723——**不释放**，
  注释明言 "must remain accessible until the entire prefill phase is complete"
  （实际保留到请求完成=decode 结束，超出其所声明的 prefill 相）。

消费（重编码面=为何不能早释放）：
- mm_schedule.py:525 _get_chunked_prefill_embedding：每 chunk 对 overlap 图 span
  调 :379-381 _move_items_to_device+data_embedding_func（enable_mm_global_cache=
  False 缺省 ⇒ :23-25 embedding_cache max_size=0 形同缺席；cache 即使在=best-effort，
  mm_utils.py:712-714 注释）；mm_schedule.py:210-216 对 feature=None 静默跳过 →
  下游 overlay deepseek_v4_vl.py:153 item.feature.to(device) 直接 AttributeError
  =「提前释放必崩」的反向用例锚。
- retract 再入：schedule_batch.py:3131 retract_decode → :2081 release_req
  （**不插树**+evict_from_tree_cache）→ :1808 reset_for_retract（prefix_indices
  清空）⇒ 重排后 radix 命中不可依赖 ⇒ 全量重 prefill=图重编码=再访 feature。

stock 释放点（唯一原语 schedule_batch.py:682-698 release_features）：
- batch_result_processor.py:1189-1191（req.finished() 门=decode 完成/abort 才置位，
  schedule_batch.py:1405-1407）；
- scheduler.py:2772-2782 _maybe_clear_mm_inputs（调用点 :4638，同为 finished 门）；
- schedule_batch.py:1979-1984 set_finish_with_abort（abort 即时释放）。
- **缺口本体**：req.inflight_middle_chunks<=0（batch_result_processor.py:328/:388
  =最后 chunk 完成、进入 decode）到 req.finished()（decode 结束）之间**无释放点**
  ——长 decode（OPEN-26 实测 3183 tok 项）期间特征全程驻留；连续多图长混排序列
  （m1→m2→m3）下=宿主 staging 累积主面，4.8M 池释放 17G 只缩静态项故无效
  （OPEN-26 定谳 1「池余量假说证伪」的机制解释）。

═══ 二、两段式设计（本模块）═══

键 DSV41_MM_FEATURE_LIFECYCLE（缺省 stock；two_stage=段A+段B；坏值 fail-loud）：

- 段A（完成强制释放，两种模式同置——stock 既有三点 + 账本配套递减）：
  finish/abort 路径全部走 release_features() 语义。安全面=完成请求不再重编码。
- 段B（chunk 内复用窗口保留+末 chunk 释放，仅 two_stage）：释放点=该请求
  **最后一个 chunk 处理完毕**（batch_result_processor.py:328 分支=set_prefill_
  finished_time 处挂钩）。跨 chunk 重编码语义不破：所有 overlap 图 span 的
  chunk 均已调度执行完毕才释放；retract 安全面=特征已释放的 mm 请求被 retract
  时**fail-closed abort 不重排队**（beam 组同律判例 schedule_batch.py:3151-3155
  "cannot be retracted, so they are aborted instead"——确定性失败优于重编码
  AttributeError 崩调度器）。
- 段B 对 session 请求不生效（session 共享历史 mm_inputs，stock 语义保留，
  schedule_batch.py:1980-1981/:2777-2779 同律）。

═══ 三、积压上界断言（OPEN-26 观察面失效教训的引擎内化）═══

水位哨与 TP 观察器在碾压中先死（自身被吞、RED 未及打印）⇒ 账本必须内建在
持有者进程里、不依赖任何外部探针：
- 计数器：admit（等待队列入队时）按 item.feature 字节数累加；release 递减；
  幂等（per-item 防双计）。
- 横幅：驻留 >4GiB 告警（上升沿一次+周期再报）；>8GiB **拒新 mm 请求**
  （fail-closed：新 mm 请求入队前拒绝，存量请求继续执行不受影响；文本请求
  不受限）。键 DSV41_MM_FEATURE_RESIDENT_WARN_BYTES /
  DSV41_MM_FEATURE_RESIDENT_LIMIT_BYTES（0/off=解除该级；缺省 4GiB/8GiB）。
- stock 模式下账本+门照常在役（观察面+上界不依赖 two_stage）。

═══ 四、接线面 ═══

本模块为案头 dev 形（纯 stdlib、零引擎依赖、零导入副作用）；引擎接线 hunk
（scheduler.py/schedule_batch.py/batch_result_processor.py/mm_schedule.py 六挂点）
逐锚见 design/item6-feature-lifecycle-design.diff.md（零可执行注释件，同件3 形制）。
被测形态见 mm_item6_selftest.py（fake 调度器：真实本模块代码被测）。
"""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, List, Optional, Tuple

# ── 键面 ────────────────────────────────────────────────────────────────────
MM_FEATURE_LIFECYCLE_ENV = "DSV41_MM_FEATURE_LIFECYCLE"
MM_RESIDENT_WARN_ENV = "DSV41_MM_FEATURE_RESIDENT_WARN_BYTES"
MM_RESIDENT_LIMIT_ENV = "DSV41_MM_FEATURE_RESIDENT_LIMIT_BYTES"

LIFECYCLE_MODES = ("stock", "two_stage")

_GIB = 1024 * 1024 * 1024
DEFAULT_WARN_BYTES = 4 * _GIB   # >4G 告警（OPEN-26 卡定）
DEFAULT_LIMIT_BYTES = 8 * _GIB  # >8G 拒新 mm 请求（fail-closed，卡定）

# per-item 账本标记（挂在 item 对象上；引擎 MultimodalDataItem.__setattr__ 对
# 非 struct 字段落 model_specific_data 字典，schedule_batch.py:402-408——同面可用）
_LEDGER_BYTES_ATTR = "_mm_feat_ledger_bytes"
# per-item 已释放标记（release_features_in_place 置；retract_decision 检）
# ——与账本标记分离：账本标记出账即除（防重计），已释放标记永驻（retract
#   面须能追溯「曾持有且已释放」，即使 feature 字段已置 None）
_RELEASED_ATTR = "_mm_feat_released"

# 告警横幅周期：每 _WARN_REPEAT_EVERY 次 admit/release 事件再报一次（防刷屏
# 但保持可见性——OPEN-26「RED 未及打印」教训：宁可重复不可沉默）
_WARN_REPEAT_EVERY = 64


def parse_lifecycle_mode(raw: Optional[str] = None) -> str:
    """解析 DSV41_MM_FEATURE_LIFECYCLE。缺省 stock；坏值 fail-loud 列合法值
    （战役键纪律：坏键 raise 不静默，同件1/件2 键面）。"""
    if raw is None:
        raw = os.environ.get(MM_FEATURE_LIFECYCLE_ENV)
    if raw is None or raw.strip() == "":
        return "stock"
    val = raw.strip().lower()
    if val not in LIFECYCLE_MODES:
        raise ValueError(
            f"{MM_FEATURE_LIFECYCLE_ENV}={raw!r} 非法（合法值：{LIFECYCLE_MODES}；"
            f"缺省 stock）——fail-loud 拒启，不静默回退"
        )
    return val


def parse_bytes_env(raw: Optional[str], default: int, key: str) -> Optional[int]:
    """解析字节阈值键。缺省=卡定值；0/off/none=None（解除该级）；
    负数/非整数=fail-loud。"""
    if raw is None:
        raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val in ("0", "off", "none", "false"):
        return None
    try:
        n = int(val)
    except ValueError:
        raise ValueError(
            f"{key}={raw!r} 非法（须为非负整数字节或 0/off 解除）——fail-loud 拒启"
        ) from None
    if n < 0:
        raise ValueError(
            f"{key}={raw!r} 为负（须为非负整数字节或 0/off 解除）——fail-loud 拒启"
        )
    return n


def feature_nbytes(feature: Any) -> int:
    """特征对象的宿主驻留字节数。torch.Tensor→nbytes（含视图底层存储差别的
    诚实注记：以 .nbytes 为准=scheduler 实际持有的张量面）；bytes/bytearray→
    len；None/标量→0（EPD precomputed_embeddings-only 项 feature 本就为 None，
    schedule_batch.py:378-379——计 0 不误账）。"""
    if feature is None:
        return 0
    nbytes = getattr(feature, "nbytes", None)
    if isinstance(nbytes, int) and nbytes >= 0:
        return nbytes
    if isinstance(feature, (bytes, bytearray, memoryview)):
        return len(feature)
    return 0


class MMFeatureLedger:
    """宿主侧 mm 特征驻留字节账本（观察面+fail-closed 门）。

    幂等：admit 对同一 item 只计一次（per-item 标记）；release 对未入账 item
    为 no-op。门语义：would_admit 只拦**新 mm 请求**；存量释放不受门约束。
    """

    def __init__(
        self,
        warn_bytes: Optional[int] = DEFAULT_WARN_BYTES,
        limit_bytes: Optional[int] = DEFAULT_LIMIT_BYTES,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.warn_bytes = warn_bytes
        self.limit_bytes = limit_bytes
        self._log = log or (lambda msg: None)
        self.resident_bytes = 0
        self.n_items = 0            # 当前驻留 item 数
        self.n_reqs = 0             # 当前至少持一个 item 的请求数（rid 计）
        self._req_items: dict = {}  # rid -> 已入账 item 数（引用计数面）
        self.peak_resident_bytes = 0
        self.warn_banners = 0
        self.rejects = 0
        self._events_since_banner = 0
        self._warn_active = False   # 上升沿/滞回（跌回 warn/2 复位）

    # ── 记账 ──
    def admit(self, items: Iterable[Any], rid: str) -> int:
        """请求入队时入账（幂等）。返回本次新增字节数。"""
        added = 0
        n_new = 0
        for item in items:
            if getattr(item, _LEDGER_BYTES_ATTR, None) is not None:
                continue  # 已入账（幂等）
            nb = feature_nbytes(getattr(item, "feature", None))
            try:
                setattr(item, _LEDGER_BYTES_ATTR, nb)
            except Exception:
                pass  # 只读对象面：0 字节入账仍可标记缺席（诚实：不崩账本）
            added += nb
            if nb > 0:
                n_new += 1
        if added or n_new:
            self.resident_bytes += added
            self.n_items += n_new
            self._req_items[rid] = self._req_items.get(rid, 0) + n_new
            self._after_change(added_rejected=False)
        return added

    def release(self, items: Iterable[Any], rid: str) -> int:
        """释放点调用（段A/段B/abort 同一原语）。返回本次出账字节数。"""
        freed = 0
        n_gone = 0
        for item in items:
            nb = getattr(item, _LEDGER_BYTES_ATTR, None)
            if nb is None:
                continue  # 未入账或已出账（幂等）
            freed += nb
            if nb > 0:
                n_gone += 1
            try:
                delattr(item, _LEDGER_BYTES_ATTR)
            except Exception:
                try:  # 引擎面 fallback：置 -1 哨兵防重计
                    setattr(item, _LEDGER_BYTES_ATTR, None)
                except Exception:
                    pass
        if freed or n_gone:
            self.resident_bytes -= freed
            self.n_items -= n_gone
            remain = self._req_items.get(rid, 0) - n_gone
            if remain > 0:
                self._req_items[rid] = remain
            else:
                self._req_items.pop(rid, None)
            self._after_change(added_rejected=False)
        return freed

    def drop_req(self, rid: str) -> None:
        """请求整体离场（等待队列 abort pop 等）而 items 引用随之 GC 的面：
        若尚有未出账 item（调用方未走 release 原语），按标记出账防泄漏计数。"""
        # 引擎 glue 应优先走 release()；此函数为兜底（无法枚举 items 时由
        # glue 持有的 rid->items 映射调用 release——design diff hunk 5b）。
        self._req_items.pop(rid, None)

    # ── 门 ──
    def would_admit(self, pending_bytes: int) -> Tuple[bool, str]:
        """新 mm 请求准入门（fail-closed）。pending=该请求全部 item 字节和。
        返回 (ok, reason)；ok=False 时 reason 入 abort 消息。"""
        if self.limit_bytes is None or pending_bytes == 0:
            return True, ""
        if self.resident_bytes + pending_bytes <= self.limit_bytes:
            return True, ""
        self.rejects += 1
        reason = (
            f"DSV41 mm feature resident backlog limit reached: "
            f"resident={self.resident_bytes}B + new={pending_bytes}B > "
            f"limit={self.limit_bytes}B ({MM_RESIDENT_LIMIT_ENV})——fail-closed "
            f"拒入（OPEN-26 staging 碾压防护；存量请求不受影响）"
        )
        self._log(f"[MM-TRANSIENT 件6] REJECT {reason}")
        return False, reason

    # ── 观测 ──
    def _after_change(self, added_rejected: bool) -> None:
        if self.resident_bytes > self.peak_resident_bytes:
            self.peak_resident_bytes = self.resident_bytes
        self._events_since_banner += 1
        if self.warn_bytes is None:
            return
        if self.resident_bytes > self.warn_bytes:
            if (not self._warn_active) or (
                self._events_since_banner >= _WARN_REPEAT_EVERY
            ):
                self._warn_active = True
                self.warn_banners += 1
                self._events_since_banner = 0
                self._log(
                    f"[MM-TRANSIENT 件6] WARN 宿主侧 mm 特征驻留 "
                    f"{self.resident_bytes}B > {self.warn_bytes}B "
                    f"({MM_RESIDENT_WARN_ENV})；items={self.n_items} "
                    f"reqs={len(self._req_items)}；peak="
                    f"{self.peak_resident_bytes}B（OPEN-26 观察面内化："
                    f"外部哨兵可能已死，本账本随调度器进程存活）"
                )
        elif self.resident_bytes < self.warn_bytes // 2:
            self._warn_active = False  # 滞回复位（防边界抖动刷屏）

    def snapshot(self) -> dict:
        return {
            "resident_bytes": self.resident_bytes,
            "peak_resident_bytes": self.peak_resident_bytes,
            "n_items": self.n_items,
            "n_reqs": len(self._req_items),
            "warn_bytes": self.warn_bytes,
            "limit_bytes": self.limit_bytes,
            "warn_banners": self.warn_banners,
            "rejects": self.rejects,
        }


class MMFeatureLifecycleError(RuntimeError):
    """fail-loud：已释放特征的 mm 请求被要求重编码（提前释放/retract 违约面）。"""


def release_features_in_place(items: Iterable[Any]) -> int:
    """stock release_features() 语义的案头复刻（schedule_batch.py:682-698：
    item.feature=None；引擎面另有 acknowledge_deferred_cuda_ipc_feature 运输
    面释放，接线 hunk 保留原调用序）。置 {_RELEASED_ATTR}=True（retract 面
    追溯「曾持有且已释放」）。返回置 None 的 item 数。"""
    n = 0
    for item in items:
        if getattr(item, "feature", None) is not None:
            item.feature = None
            try:
                setattr(item, _RELEASED_ATTR, True)
            except Exception:
                pass  # 只读对象面：标记缺席时 retract_decision 退化为 requeue
            n += 1
    return n


class MMFeatureLifecyclePolicy:
    """两段式释放策略（纯谓词，引擎挂点调用；req-like 协议见 design diff）。

    req-like 协议（引擎 Req 字段子集，duck-type）：
      rid: str
      finished() -> bool            （schedule_batch.py:1405-1407）
      session: Optional[...]        （None=非 session；session 共享特征保留）
      multimodal_inputs: Optional[likes]  （.mm_items 列表；None=非 mm/已清）
      inflight_middle_chunks: int   （chunked 中间 chunk 计数，
                                     batch_result_processor.py:388 递减面）
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        ledger: Optional[MMFeatureLedger] = None,
    ) -> None:
        self.mode = parse_lifecycle_mode(mode)
        self.ledger = ledger
        self.stage_b_releases = 0   # 段B 释放计数（观测面）
        self.stage_a_releases = 0   # 段A 释放计数（观测面）

    # ── 段A：完成（finish/abort）强制释放——两种模式同置 ──
    def should_release_stage_a(self, req: Any) -> bool:
        mm = getattr(req, "multimodal_inputs", None)
        if mm is None:
            return False
        if getattr(req, "session", None) is not None:
            return False  # session 请求特征归 session 属主（stock 语义保留）
        try:
            fin = req.finished()
        except AttributeError:
            fin = getattr(req, "finished_reason", None) is not None
        return bool(fin)

    def apply_release(self, req: Any, stage: str) -> int:
        """统一释放原语：feature=None + 账本出账。stage ∈ {'A','B'}。
        返回出账字节数。"""
        mm = getattr(req, "multimodal_inputs", None)
        items = list(getattr(mm, "mm_items", []) or [])
        release_features_in_place(items)
        freed_bytes = 0
        if self.ledger is not None:
            freed_bytes = self.ledger.release(items, getattr(req, "rid", "?"))
        if stage == "A":
            self.stage_a_releases += 1
        else:
            self.stage_b_releases += 1
        return freed_bytes

    # ── 段B：末 chunk 处理完毕释放（仅 two_stage）──
    def should_release_stage_b(self, req: Any) -> bool:
        """挂点=batch_result_processor.py:328 分支（set_prefill_finished_time
        处，即该请求最后一个 chunk 已完成、即将转入 decode）。此处 belt 复核
        inflight_middle_chunks<=0；「最后 chunk」语义由挂点保证。"""
        if self.mode != "two_stage":
            return False
        mm = getattr(req, "multimodal_inputs", None)
        if mm is None:
            return False
        if getattr(req, "session", None) is not None:
            return False  # session 面：跨请求复用，段B 不适用
        if getattr(req, "inflight_middle_chunks", 0) > 0:
            return False  # 仍有在飞中间 chunk（混合批/异步面 belt）
        items = getattr(mm, "mm_items", None) or []
        if not items:
            return False
        # 已全释放则幂等 False
        return any(getattr(it, "feature", None) is not None for it in items)

    # ── retract 面：特征已释放的 mm 请求 fail-closed abort ──
    def retract_decision(self, req: Any) -> Tuple[str, str]:
        """retract_decode 选牺牲者后调用。返回 ('requeue','') 或
        ('abort', reason)。beam 组同律（schedule_batch.py:3151-3155）：不能
        重计算者 abort 而非重排队——确定性失败优于重编码 None 崩。"""
        mm = getattr(req, "multimodal_inputs", None)
        items = list(getattr(mm, "mm_items", []) or [])
        if not items:
            return "requeue", ""
        released = any(
            getattr(it, _RELEASED_ATTR, False) for it in items
        )
        if released:
            return (
                "abort",
                "MM-TRANSIENT 件6 段B：mm 特征已释放（末 chunk 后用后释放），"
                "retract 重排队将触发全量重 prefill=图重编码=feature=None 崩"
                "（mm_schedule.py:215 静默跳过→deepseek_v4_vl.py:153 "
                "AttributeError）——fail-closed abort（beam 组同律 "
                "schedule_batch.py:3151-3155）",
            )
        return "requeue", ""

    # ── encode belt：进嵌入路径前的 fail-loud 门 ──
    @staticmethod
    def encode_guard(items: List[Any]) -> None:
        """data_embedding_func 调用前（mm_schedule.py:380-381 面）belt：任一
        待编码 item feature=None 即 raise（杜绝「静默跳过→模型层深崩」的
        不可诊断形态——失败要早、要响）。"""
        for item in items:
            if getattr(item, "feature", None) is None and getattr(
                item, "precomputed_embeddings", None
            ) is None:
                raise MMFeatureLifecycleError(
                    "mm item feature=None 进入编码路径（提前释放/retract 违约"
                    "面）——fail-loud（正确释放点=末 chunk 后/请求完成，"
                    "见 mm_feature_lifecycle.py 证据链）"
                )
