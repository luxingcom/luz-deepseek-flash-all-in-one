"""mm_lifecycle_glue — L0 MM 部署窗 件6/件7 引擎接线 glue（adapter 形；键控 install）。

法源：docs/taskcards/L0-MMDEPLOY-WINCARD-20261006.md（本窗）+
dev/mm-impl/（件6 mm_feature_lifecycle.py 0aac0402+件7 mm_alloc_hygiene.py
c4eb9300——两件=纯 stdlib 策略/账本库，**引擎接线面=本 glue**；其
design/item6-feature-lifecycle-design.diff.md 的 hunk 路线在 L0 落为
**方法界包装形**：挂点语义等价表见模块尾 §锚点等价表）+
docs/incidents/INCIDENT-20261006-C24VL-OPEN26-MMSTAGING-CRUSH.md §五翻案裁定
（件6 账本只计 host 驻留=复现本窗不跳门；件7 账本计设备侧足迹=复现必跳门，
两门 _add_request_to_queue 同 funnel 串联）。

部署位：~/migrate-assets/dsv41/adapter/mm_lifecycle_glue.py（容器内
PYTHONPATH=/opt/dsv41/adapter 解析，engram_backend 同律先例）。
挂钩：sitecustomize.l0-mm.diff（scheduler 分支+mm_schedule 分支+finder 增名；
tl_segment/admission_segment 键控分派同形制）。

== 键面（全部沿件6/件7 自有键，本 glue 零新键；缺省=stock/off）================
DSV41_MM_FEATURE_LIFECYCLE            件6 主键（缺省 stock=逐字节既有行为；
                                      账本+门照常在役=观察面独立律）
DSV41_MM_FEATURE_RESIDENT_WARN/_LIMIT_BYTES  4GiB/8GiB（host 门）
DSV41_MM_ALLOC_HYGIENE                件7 主键（缺省 off=零 CUDA 调用；
                                      after_batch=mm 批完成回调挂 empty_cache）
DSV41_MM_DEVICE_FOOTPRINT_WARN/_LIMIT/_JUMP_BYTES、DSV41_MM_LEDGER_SAMPLE_EVERY、
DSV41_MM_LEDGER_OOM_GUARD、DSV41_MM_LEDGER_OOM_SCORE_ADJ  件7 账本面（4G/8G/4G/1/on/-1000）
键缺零惰性直证：两主键缺省 stock/off ⇒ 未设键的靴 wrapper 逐字节透传
（stock 释放点/调度序零改；账本仅记数=纯观察面，见自测 T1）。

== fail-closed 锚点核（install 时逐锚；漂移=REFUSED 横幅+零 patch）==========
锚核对象=在役 overlay 树版本（~/migrate-assets/v4vl/sglang-overlay.v4vl-79cafec0/
scheduler.py md5 34e68983；VL 靴影子挂载后即运行面）：
  A1 Scheduler._add_request_to_queue(self, req, is_retracted=False) 存在
  A2 Scheduler.abort_request(self, recv_req) 存在且源含 waiting_queue.pop
  A3 Scheduler._maybe_clear_mm_inputs(self, batch) 存在且源含 release_features()
  A4 Scheduler.run_batch(self, batch, ...) 存在（batch=首位置参）
  A5 Scheduler.process_batch_result(self, batch, result) 存在且尾部调
     _maybe_clear_mm_inputs（overlay :4807 实锚）
  A6 模块级 _make_abort_req(req, finished_reason=None) 存在（reject idiom=
     _abort_on_queued_limit 同形：ipc_channels.send_to_tokenizer.send_output）
  B1 mm_schedule._batch_encode_per_image_misses / B2 _get_chunked_embedding_by_item
     存在（belt 面；encode_guard 前置）
任一缺失/漂移 → print REFUSED（flush=True）+ 返回 False + 不 patch 任何属性
（sparse_local/admission_r1 拒装同律：产线 boot 不因此死，MM 观察面缺席可
由 boot 横幅判读）。

== 件7 CUDA 面（惰性 arm）====================================================
arm 点=首个 run_batch wrapper 调用（lazy）：此时引擎初始化/图捕获/预热已毕
（overlay scheduler :1860「Engine init (graph capture, warmups) is done」先于
event_loop 首批）⇒ 基线语义=design 锚 scheduler.py:1943 同面（捕获后取基=
段增长不污染）。arm 动作：import torch（调度器进程本就持有）→ 六方法 CUDA
适配器 → mm_alloc_hygiene.build_from_env（账本恒建+卫生策略+expandable 红线
断言〔boot COMMON_ENV expandable_segments:False 合法〕）→
try_apply_oom_score_adj（fail-open）→ ledger.arm()。import/构造任一异常=
记 REFUSED 横幅+件7 面降级观察缺席（件6 面不受染；fail-open 律=观察件不杀
伺服，与 oom 防护位同律）。

== 挂点-语义等价表（hunk 路线 ↔ 本 wrapper 路线）============================
| design hunk | 锚（基树） | 本 glue 等价挂点 | 语义等价注记 |
|---|---|---|---|
| hunk1 admit+host 门 | scheduler.py:3223 _add_request_to_queue 头 | 同方法 wrapper 前段 | 逐字节同 funnel；retract 重排（:4264 is_retracted=True）幂等 0 增 |
| hunk1+件7 门串联 | :3223（同 funnel） | 同 wrapper 前段 device.would_admit_mm | 两门串联=裁定原文 |
| hunk1b abort 出账 | scheduler abort_request 等待队列 pop 分支 | abort_request wrapper：pre 记 (rid,items) 快照，post 对已 pop 者 host_ledger.release | pop 分支不可界包⇒快照差分等价（release 幂等防重） |
| hunk2 段A | :2772 _maybe_clear_mm_inputs 扩段 | 同方法 wrapper：pre 快照 finished 非 session mm reqs 的 items，orig 后对快照 apply_release('A') | stock :2746 已 release_features（finish 门内）⇒ 段A 增量=账本出账+段A 计数；two_stage 不改 stock 段A 语义（设计原文：段A 两模式同置） |
| hunk3 段B | brp:328 set_prefill_finished_time 处 | process_batch_result wrapper 后扫：req.time_stats.prefill_finished_time>0 且未 finished 且 mm 在持 ⇒ lifecycle.apply_release(req,'B')（幂等） | brp:328 在 scheduler.process_batch_result 委托链内（overlay :4765→brp）⇒ 批后扫=同批边界、μs 级 python 后扫不跨批；「末 chunk」belt=inflight_middle_chunks<=0（policy 同源） |
| hunk3b 段A 第二点 | brp:1189-1191 | 同上后扫的 finished 分支（段A） | brp:1189=finished 面，与 _maybe_clear 同语义 ⇒ 后扫统一 apply_release('A')，幂等 |
| hunk4 retract abort | schedule_batch.py:3151 beam 同律 | _add_request_to_queue wrapper is_retracted=True 分支：retract_decision→abort 则 _reject 不重排队 | retract 重排唯一再入口=overlay :4264（grep 实证）⇒ 单点收编；beam 判例语义保真 |
| hunk5 原语零改 | schedule_batch.py:682-698 | 不触碰（分层律：策略不入运输面） | 引擎面 stock 原语经 orig 调用；案头复刻仅供 fake 面 |
| hunk6 encode belt | mm_schedule.py:379/:456 | install_mm_schedule：两函数 wrapper 前置 encode_guard | 同 fail-loud 语义；函数界=模块属性 patch（sparse_wire.install_scoring 同法） |
| 件7 四挂点 | :1943/:4255/:4599/:3223 | arm=首批 run_batch 惰性；批前=run_batch wrapper 前段；批后+卫生=process_batch_result wrapper 前段；门=:3223 同 wrapper | arm 语义=捕获/预热后基线（见上「件7 CUDA 面」） |
诚实注记：hunk3 段B 后扫与 hunk1b 快照差分为**边界外等价**（批边界不变、
调用序 orig→glue 后段）；μs 级时序差（同批内后置）不触任何引擎不变式
（释放原语幂等+特征此后无读者：末 chunk 后=decode 相，特征仅 retract 重编码
再访=retract 面已 fail-closed 收编）。

== 组合律（沿卡）=============================================================
件1/2a/2b=overlay 件内 env 门控（本 glue 零交互）；4.8M 池/T61 拒入正交维持；
mm 停飞解除前置=本窗绿判另裁（本 glue 不主张解除）。
"""
from __future__ import annotations

import inspect
import logging
import os
import time
from typing import Any, List, Optional, Tuple

logger = logging.getLogger("mm_lifecycle_glue")

_MM_GLUE_BANNER_PREFIX = "[mm_lifecycle_glue]"


# ─────────────────────────── 状态单例（每调度器进程一枚） ───────────────────


class _GlueState:
    """件6+件7 装配态。构造零 CUDA 依赖（host 面即刻在役；device 面惰性 arm）。"""

    def __init__(self) -> None:
        from mm_feature_lifecycle import (  # adapter PYTHONPATH 面
            DEFAULT_LIMIT_BYTES,
            DEFAULT_WARN_BYTES,
            MMFeatureLedger,
            MMFeatureLifecyclePolicy,
            MM_RESIDENT_LIMIT_ENV,
            MM_RESIDENT_WARN_ENV,
            parse_bytes_env,
        )

        def _warn(msg: str) -> None:
            logger.warning(msg)

        self.host_ledger = MMFeatureLedger(
            warn_bytes=parse_bytes_env(
                None, DEFAULT_WARN_BYTES, MM_RESIDENT_WARN_ENV
            ),
            limit_bytes=parse_bytes_env(
                None, DEFAULT_LIMIT_BYTES, MM_RESIDENT_LIMIT_ENV
            ),
            log=_warn,
        )
        # 键面 fail-loud 前移：坏 lifecycle 值在装配点 raise（装死优于装瞎）
        self.lifecycle = MMFeatureLifecyclePolicy(
            mode=None, ledger=self.host_ledger
        )
        # 件7 面（惰性 arm；None=未 arm/降级缺席）
        self.device: Optional[Any] = None
        self.hygiene: Optional[Any] = None
        self.oom_adj_applied: Optional[bool] = None
        self.device_refused: Optional[str] = None
        # 观测面（boot 横幅/READINGS 用）
        self.n_gate_rejects_host = 0
        self.n_gate_rejects_device = 0
        self.n_retract_aborts = 0
        self.n_batches = 0

    # ── 件7 惰性 arm（首个 run_batch；锚语义=scheduler.py:1943 捕获/预热后）──
    def ensure_device_armed(self) -> None:
        if self.device is not None or self.device_refused is not None:
            return
        try:
            import torch  # 调度器进程本就持有；迟到导入=boot 轻量律

            cuda_api = _TorchCudaApi(torch)
            from mm_alloc_hygiene import build_from_env, try_apply_oom_score_adj

            ledger, hygiene, adj, guard = build_from_env(
                cuda_api=cuda_api,
                log=lambda m: logger.warning(m),
                environ=dict(os.environ),
            )
            if guard and adj is not None:
                # fail-open：写失败只记档（防护位失败不杀伺服）
                adj_ok, adj_why = try_apply_oom_score_adj(adj)
                self.oom_adj_applied = adj_ok
                if not adj_ok:
                    logger.warning(
                        "%s oom_score_adj 防护位未落（fail-open）：%s",
                        _MM_GLUE_BANNER_PREFIX,
                        adj_why,
                    )
            ledger.arm()
            self.device = ledger
            self.hygiene = hygiene
            print(
                f"{_MM_GLUE_BANNER_PREFIX} 件7 arm：device ledger 在役 "
                f"(hygiene={hygiene.mode}, oom_adj={self.oom_adj_applied})",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 —— 观察件不杀伺服（fail-open）
            self.device_refused = f"{type(exc).__name__}: {exc}"
            print(
                f"{_MM_GLUE_BANNER_PREFIX} 件7 arm REFUSED（降级=设备面观察"
                f"缺席，件6 host 面不受染）：{self.device_refused}",
                flush=True,
            )

    def snapshot(self) -> dict:
        snap: dict = {
            "lifecycle_mode": self.lifecycle.mode,
            "host_ledger": self.host_ledger.snapshot(),
            "stage_a_releases": self.lifecycle.stage_a_releases,
            "stage_b_releases": self.lifecycle.stage_b_releases,
            "n_gate_rejects_host": self.n_gate_rejects_host,
            "n_gate_rejects_device": self.n_gate_rejects_device,
            "n_retract_aborts": self.n_retract_aborts,
            "n_batches": self.n_batches,
            "device_armed": self.device is not None,
            "device_refused": self.device_refused,
            "oom_adj_applied": self.oom_adj_applied,
        }
        if self.device is not None:
            snap["device_ledger"] = self.device.snapshot()
        if self.hygiene is not None:
            snap["hygiene"] = self.hygiene.snapshot()
        return snap


_STATE: Optional[_GlueState] = None


def _state() -> _GlueState:
    global _STATE
    if _STATE is None:
        _STATE = _GlueState()
    return _STATE


def get_state() -> Optional[_GlueState]:
    """观测面入口（boot-checks/READINGS 采样用；未装配=None）。"""
    return _STATE


def reset_state_for_tests() -> None:
    """自测专用：重置单例（产线路径零调用）。"""
    global _STATE
    _STATE = None


class _TorchCudaApi:
    """件7 六方法 CUDA 适配器（mm_alloc_hygiene 协议；惰性绑定 torch）。"""

    def __init__(self, torch_mod: Any) -> None:
        self._t = torch_mod

    def mem_get_info(self) -> Tuple[int, int]:
        return self._t.cuda.mem_get_info()

    def memory_allocated(self) -> int:
        return self._t.cuda.memory_allocated()

    def memory_reserved(self) -> int:
        return self._t.cuda.memory_reserved()

    def memory_stats(self) -> dict:
        try:
            return self._t.cuda.memory_stats()
        except Exception:  # noqa: BLE001 —— 缺面容错（peak=None 不杀采样）
            return {}

    def empty_cache(self) -> None:
        self._t.cuda.empty_cache()

    def is_current_stream_capturing(self) -> bool:
        try:
            return bool(self._t.cuda.is_current_stream_capturing())
        except Exception:  # noqa: BLE001 —— 旧 torch 缺面=按未捕获处理（fire）
            return False


# ─────────────────────────── 工具（req/items 面） ───────────────────────────


def _mm_items(req: Any) -> List[Any]:
    mm = getattr(req, "multimodal_inputs", None)
    if mm is None:
        return []
    return list(getattr(mm, "mm_items", []) or [])


def _pending_bytes(items: List[Any]) -> int:
    from mm_feature_lifecycle import feature_nbytes

    return sum(feature_nbytes(getattr(it, "feature", None)) for it in items)


def _reject_incoming(module: Any, sched: Any, req: Any, reason: str) -> None:
    """拒入 idiom=_abort_on_queued_limit 同形（引擎自身在役拒绝路径）。

    _make_abort_req(req, finished_reason={"type": "abort",
    "status_code": HTTPStatus.SERVICE_UNAVAILABLE, "message": ...}) +
    ipc_channels.send_to_tokenizer.send_output(abort_req, req)。
    """
    from http import HTTPStatus

    make_abort = getattr(module, "_make_abort_req", None)
    if make_abort is None:  # 锚核已保证在；防御面=不可达
        raise RuntimeError("mm_lifecycle_glue: _make_abort_req 缺（锚漂移）")
    abort_req = make_abort(
        req,
        finished_reason={
            "type": "abort",
            "status_code": HTTPStatus.SERVICE_UNAVAILABLE,
            "message": reason,
        },
    )
    sched.ipc_channels.send_to_tokenizer.send_output(abort_req, req)
    try:  # trace 面（引擎 idiom；缺面不致拒失败）
        req.time_stats.trace_ctx.abort(abort_info={"reason": reason})
    except Exception:  # noqa: BLE001
        pass


# ─────────────────────────── 锚点核（fail-closed） ──────────────────────────


def _src_of(fn: Any) -> str:
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ""


def _verify_scheduler_anchors(module: Any) -> List[str]:
    bad: List[str] = []
    Scheduler = getattr(module, "Scheduler", None)
    if Scheduler is None:
        return ["module.scheduler.Scheduler 缺"]
    for name in (
        "_add_request_to_queue",
        "abort_request",
        "_maybe_clear_mm_inputs",
        "run_batch",
        "process_batch_result",
    ):
        if not callable(getattr(Scheduler, name, None)):
            bad.append(f"Scheduler.{name} 缺")
    src_ab = _src_of(getattr(Scheduler, "abort_request", None))
    if "waiting_queue.pop" not in src_ab:
        bad.append("abort_request 源无 waiting_queue.pop（hunk1b 锚漂移）")
    src_mc = _src_of(getattr(Scheduler, "_maybe_clear_mm_inputs", None))
    if "release_features()" not in src_mc:
        bad.append("_maybe_clear_mm_inputs 源无 release_features()（段A 锚漂移）")
    src_pbr = _src_of(getattr(Scheduler, "process_batch_result", None))
    if "_maybe_clear_mm_inputs" not in src_pbr:
        bad.append("process_batch_result 源无 _maybe_clear_mm_inputs（段B 链锚漂移）")
    if not callable(getattr(module, "_make_abort_req", None)):
        bad.append("模块级 _make_abort_req 缺（reject idiom 锚漂移）")
    return bad


def _verify_mm_schedule_anchors(module: Any) -> List[str]:
    bad: List[str] = []
    for name in ("_batch_encode_per_image_misses", "_get_chunked_embedding_by_item"):
        if not callable(getattr(module, name, None)):
            bad.append(f"{name} 缺（hunk6 belt 锚漂移）")
    return bad


# ─────────────────────────── install（scheduler 面） ────────────────────────


def install(module: Any) -> bool:
    """sitecustomize scheduler 分派入口（sglang.srt.managers.scheduler exec 后）。

    返回 True=已装；False=REFUSED（零 patch，产线 boot 不死）。
    """
    bad = _verify_scheduler_anchors(module)
    if bad:
        print(
            f"{_MM_GLUE_BANNER_PREFIX} REFUSED → stock 调度器逐字节原样。"
            f"why: {'; '.join(bad)}",
            flush=True,
        )
        return False

    Scheduler = module.Scheduler
    st = _state()  # 装配即建（host 面即刻在役；键坏值在此 raise=装死优于装瞎）

    # ── A. _add_request_to_queue：件6 admit+host 门+件7 设备门+retract 收编 ──
    _orig_arq = Scheduler._add_request_to_queue

    def _add_request_to_queue(self, req, is_retracted=False, *a, **kw):
        items = _mm_items(req)
        if is_retracted:
            # retract 重排唯一再入口（overlay scheduler.py:4264）⇒ hunk4 单点
            # 收编：特征已释者 fail-closed abort 不重排队（beam 组同律判例）。
            decision, reason = st.lifecycle.retract_decision(req)
            if decision == "abort":
                st.n_retract_aborts += 1
                logger.warning(
                    "%s retract→abort（件6 段B 已释）：%s",
                    _MM_GLUE_BANNER_PREFIX,
                    reason,
                )
                _reject_incoming(module, self, req, reason)
                return
            return _orig_arq(self, req, is_retracted, *a, **kw)
        if items:
            pending = _pending_bytes(items)
            if pending:
                # 两门串联（裁定原文：host 门+设备门同 funnel）
                ok, reason = st.host_ledger.would_admit(pending)
                if not ok:
                    st.n_gate_rejects_host += 1
                elif st.device is not None and st.device.armed:
                    ok, reason = st.device.would_admit_mm()
                    if not ok:
                        st.n_gate_rejects_device += 1
                if not ok:
                    logger.warning(
                        "%s 拒新 mm 请求（fail-closed 门）：%s",
                        _MM_GLUE_BANNER_PREFIX,
                        reason,
                    )
                    _reject_incoming(module, self, req, reason)
                    return
        r = _orig_arq(self, req, is_retracted, *a, **kw)
        if items:
            st.host_ledger.admit(items, getattr(req, "rid", "?"))
        return r

    Scheduler._add_request_to_queue = _add_request_to_queue

    # ── B. abort_request：等待队列 pop 出账（hunk1b；快照差分=边界外等价）──
    _orig_abort = Scheduler.abort_request

    def abort_request(self, recv_req, *a, **kw):
        snap = {
            id(r): (getattr(r, "rid", "?"), _mm_items(r))
            for r in list(getattr(self, "waiting_queue", []) or [])
        }
        r = _orig_abort(self, recv_req, *a, **kw)
        still = {id(x) for x in list(getattr(self, "waiting_queue", []) or [])}
        for obj_id, (rid, items) in snap.items():
            if obj_id not in still and items:
                # 已被 pop（等待队列离场，items 引用随 GC）⇒ 出账防门虚高
                st.host_ledger.release(items, rid)
        return r

    Scheduler.abort_request = abort_request

    # ── C. _maybe_clear_mm_inputs：段A 账本配套（hunk2）────────────────────
    _orig_clear = Scheduler._maybe_clear_mm_inputs

    def _maybe_clear_mm_inputs(self, batch, *a, **kw):
        # pre 快照：orig 会置 req.multimodal_inputs=None（:2747）⇒ 事后不可从
        # req 再枚举 items（快照=唯一出账素材面）。
        pre = []
        for req in getattr(batch, "reqs", []) or []:
            if st.lifecycle.should_release_stage_a(req):
                pre.append((req, _mm_items(req)))
        r = _orig_clear(self, batch, *a, **kw)
        for req, items in pre:
            if items:
                # orig 已执行 stock 释放原语（release_features()+mm=None——
                # :2746/:2747）⇒ 此处只补账本出账+段A 计数（apply_release 的
                # req 再枚举面在 orig 后不可用，故直取账本原语）。
                st.host_ledger.release(items, getattr(req, "rid", "?"))
                st.lifecycle.stage_a_releases += 1
        return r

    Scheduler._maybe_clear_mm_inputs = _maybe_clear_mm_inputs

    # ── D. run_batch：件7 arm（首批惰性）+批前采样 ──────────────────────────
    _orig_run = Scheduler.run_batch

    def run_batch(self, *a, **kw):
        st.ensure_device_armed()
        st.n_batches += 1
        batch = a[0] if a else kw.get("batch")
        has_mm = batch is not None and (
            getattr(batch, "multimodal_inputs", None) is not None
        )
        if st.device is not None:
            fwd = getattr(batch, "forward_iter", None) if batch is not None else None
            st.device.begin_batch(has_mm, forward_iter=fwd)
        return _orig_run(self, *a, **kw)

    Scheduler.run_batch = run_batch

    # ── E. process_batch_result：件7 批后+卫生；件6 段B/段A 第二点后扫 ──────
    _orig_pbr = Scheduler.process_batch_result

    def process_batch_result(self, batch, result, *a, **kw):
        has_mm = getattr(batch, "multimodal_inputs", None) is not None
        r = _orig_pbr(self, batch, result, *a, **kw)
        # 件7 批后采样+差分入账（mm/text 分账）+卫生 fire（after_batch 模式）
        if st.device is not None:
            try:
                st.device.end_batch(has_mm)
            except Exception as exc:  # noqa: BLE001 —— 账本面异常不杀批路径
                logger.warning(
                    "%s device end_batch 异常（继续服役，记档）：%r",
                    _MM_GLUE_BANNER_PREFIX,
                    exc,
                )
        if st.hygiene is not None:
            try:
                st.hygiene.after_batch(has_mm, ts=time.time())
            except Exception as exc:  # noqa: BLE001 —— 卫生面异常不杀批路径
                logger.warning(
                    "%s hygiene after_batch 异常（继续服役，记档）：%r",
                    _MM_GLUE_BANNER_PREFIX,
                    exc,
                )
        # 件6 段B/段A 第二点（brp:328/:1189 同批边界后扫；幂等标记防重）
        try:
            for req in getattr(batch, "reqs", []) or []:
                if getattr(req, "multimodal_inputs", None) is None:
                    continue
                ts = getattr(req, "time_stats", None)
                if (getattr(ts, "prefill_finished_time", 0.0) or 0.0) <= 0.0:
                    continue  # 未到 decode 相（末 chunk 未完）
                if st.lifecycle.should_release_stage_b(req):
                    st.lifecycle.apply_release(req, "B")
                elif st.lifecycle.should_release_stage_a(req):
                    # brp:1189 finished 面（orig _maybe_clear 已清者不达此处；
                    # 达此者=orig 未清的 finished 残留面）
                    st.lifecycle.apply_release(req, "A")
        except Exception as exc:  # noqa: BLE001 —— 释放面异常不杀批路径（记档）
            logger.warning(
                "%s 段B/段A 后扫异常（继续服役，记档）：%r",
                _MM_GLUE_BANNER_PREFIX,
                exc,
            )
        return r

    Scheduler.process_batch_result = process_batch_result

    print(
        f"{_MM_GLUE_BANNER_PREFIX} armed：lifecycle={st.lifecycle.mode} "
        f"host_ledger(warn={st.host_ledger.warn_bytes} limit="
        f"{st.host_ledger.limit_bytes})；device 面首批 run_batch 惰性 arm；"
        f"五方法包装在役（_add_request_to_queue/abort_request/"
        f"_maybe_clear_mm_inputs/run_batch/process_batch_result）",
        flush=True,
    )
    return True


# ─────────────────────────── install（mm_schedule belt 面） ─────────────────


def install_mm_schedule(module: Any) -> bool:
    """sitecustomize mm_schedule 分派入口（hunk6 encode belt）。"""
    bad = _verify_mm_schedule_anchors(module)
    if bad:
        print(
            f"{_MM_GLUE_BANNER_PREFIX} belt REFUSED → stock mm_schedule 原样。"
            f"why: {'; '.join(bad)}",
            flush=True,
        )
        return False

    from mm_feature_lifecycle import MMFeatureLifecyclePolicy

    guard = MMFeatureLifecyclePolicy.encode_guard  # 静态方法（双 None 即 raise）

    def _collect_items(args: Tuple[Any, ...]) -> List[Any]:
        found: List[Any] = []
        for arg in args:
            if isinstance(arg, (list, tuple)):
                for e in arg:
                    item = getattr(e, "item", e)  # PerImageRequestInfo 解包
                    if hasattr(item, "feature"):
                        found.append(item)
        return found

    _orig_bepi = module._batch_encode_per_image_misses

    def _batch_encode_per_image_misses(*a, **kw):
        items = _collect_items(a)
        if items:
            guard(items)
        return _orig_bepi(*a, **kw)

    module._batch_encode_per_image_misses = _batch_encode_per_image_misses

    _orig_gebi = module._get_chunked_embedding_by_item

    def _get_chunked_embedding_by_item(*a, **kw):
        items = _collect_items(a)
        if items:
            guard(items)
        return _orig_gebi(*a, **kw)

    module._get_chunked_embedding_by_item = _get_chunked_embedding_by_item

    print(
        f"{_MM_GLUE_BANNER_PREFIX} belt armed：encode_guard 前置于 "
        "_batch_encode_per_image_misses+_get_chunked_embedding_by_item"
        "（fail-loud：feature 与 precomputed 双 None 即 raise）",
        flush=True,
    )
    return True
