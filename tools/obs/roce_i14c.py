#!/usr/bin/env python3
"""ROCE_I14C -- I14-C 案 A 低频采样核心 + 案 B 四 gauge 读出面（0 靴纯开发件，2026-10-24）。

法源
  * 任务书 `033-TASKBOOK-V2-20261023.md` §T33-08 目标 3 / 实施步骤 3 / 验收门：
    "I14-C：案 B 四 gauge（roce_routed/nccl_kept/roce_made/communicators）到 /metrics；
    案 A 只收低频采样 + copy_done.query() 门控；四 gauge 可见且与路由横幅一致；
    采样开销 <1%；逐 batch sync 不存在"；回退="I14-C env 关闭"。
  * INV-07 §1.3/§4.2/§4.3（案 A/B 机制、失败模式：注册抛异常致 boot/metrics 失败、
    采样退化为逐 batch synchronize、读数与日志口径不一致）；R36-b（A+B 合并单臂）。
  * W4-WINDOW-REPORT-20261024.md §5.6（I14-C 案 A/B 受阻=本件关闭的前置）＋
    §3.3/§七-10 主会话裁定（overlay 接线补丁标准门=AST 名覆盖检查）。
  * P0 冻结件 `033-W1/I14C-C11-P0-FREEZE-20261024.md`（gauge 名/采样率/日志口径冻结）。

性质与红线
  * 纯 stdlib（json/re），不 import sglang/torch/prometheus -- CPU-only 可测。
  * 默认关：案 A 由 `DSV41_ROCE_SYNC_SAMPLE`（int；0/未设=关）门控，案 B 由
    `DSV41_ROCE_METRICS=1` 门控；两键全无=零注册零行为（回退=去键）。
  * fail-safe：采样/刷新/注册任何异常只计数/打 REFUSED，绝不进入调度主流程；
    绝不逐 batch synchronize（INV-07 N3 反例）。
  * 测量专用：只读计数与守恒检查，不改任何路由/调度决策。

与呈裁补丁的一致性（漂移即红，单测强制）
  * 下方面一 `RoceSyncSampler` 类（sentinel 注释之间）逐字插入
    `deploy/overlay/o12c1-prod/scheduler.py`（tools/patches/i14c-scheduler-roc-sync.patch）。
  * `SCHEDULER_FACE_SOURCE` 常量 = 同补丁插入的 `_make_roce_i14c_sampler` 函数源
    （scheduler 专属接线：logger/惰性 import），单测 exec 求值直证。
  * `ADAPTER_GAUGES_SOURCE` 常量 = 插入 `deploy/adapter/roce_ar.py` 的 `gauges()` 函数源
    （tools/patches/i14c-adapter-gauges.patch）。

判读口径（速查）
  * gauge 名（INV-07 §4.2 建议名，P0 冻结）：roce_ar_communicators / roce_ar_roce_made /
    roce_ar_roce_routed / roce_ar_nccl_kept；均为单调不减计数器（进程生命周期内）。
  * 引擎 /metrics 走 prometheus_client 多进程模式：gauge 以 multiprocess_mode="all"
    注册（样本带 pid 标签=每 TP 秩一行），refresh 由案 A 采样点低频 set()
    （R36-b 合并单臂；案 A 关则案 B 无刷新源，两键同开为冻结臂形）。
  * 对拍：scrape 值 vs `ROCE_I14C_SAMPLE`/`ROCE_POST_RESULT_HEALTH` 日志由
    cross_check() 离线对表；可观测门=单调、无 NaN、与日志一致（INV-07 §6）。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence

__all__ = [
    "RoceSyncSampler",
    "ENV_SAMPLE",
    "ENV_METRICS",
    "DEFAULT_EVERY",
    "GAUGE_NAMES",
    "GAUGE_STATS_KEYS",
    "gauges_from_stats",
    "validate_gauges",
    "GaugeAudit",
    "render_prometheus",
    "parse_scrape",
    "cross_check",
    "SCHEDULER_FACE_SOURCE",
    "ADAPTER_GAUGES_SOURCE",
    "main",
]

ENV_SAMPLE = "DSV41_ROCE_SYNC_SAMPLE"  # int；0/未设=关；N>=1 每 N 个 batch result 一次
ENV_METRICS = "DSV41_ROCE_METRICS"  # "1"=注册四 gauge；0/未设=关
DEFAULT_EVERY = 64

GAUGE_NAMES = (
    "roce_ar_communicators",
    "roce_ar_roce_made",
    "roce_ar_roce_routed",
    "roce_ar_nccl_kept",
)
# STATS 键（roce_ar.py）→ gauge 名（INV-07 §4.2 建议名）映射
GAUGE_STATS_KEYS = {
    "communicators": "roce_ar_communicators",
    "roce_made": "roce_ar_roce_made",
    "roce_routed": "roce_ar_roce_routed",
    "nccl_kept": "roce_ar_nccl_kept",
}

GAUGE_DOCS = {
    "roce_ar_communicators": "RoCE AR communicators seen (I14-C case B, readonly).",
    "roce_ar_roce_made": "RoCE AR runtimes made (I14-C case B, readonly).",
    "roce_ar_roce_routed": "AR calls routed to the RoCE one-shot kernel (I14-C case B).",
    "roce_ar_nccl_kept": "AR calls kept on NCCL (I14-C case B, readonly).",
}


# ---- i14c-canonical: begin（插入 scheduler.py 的类体与此逐字一致，单测强制同步）----
class RoceSyncSampler:
    """I14-C 案 A 低频采样核心（每 N 个结果一次；query() 门控；异常吞掉计数）。

    热路径（observe 非采样迭代）= 一次自增 + 一次取模比较，零 IO 零时钟。
    采样迭代：先 `copy_done.query()`，未完成即跳过（skipped_busy），绝不
    synchronize 阻塞（INV-07 N3 反例）；完成才调 check_fn（其内部
    synchronize 在事件已完成时立即返回）与 refresh_fn（案 B gauge set()），
    并产一行 `ROCE_I14C_SAMPLE {json}` 低频日志（周期 stats 口径）。
    """

    LOG_PREFIX = "ROCE_I14C_SAMPLE"

    def __init__(
        self,
        every: int,
        check_fn: Optional[Callable[[Any], None]] = None,
        refresh_fn: Optional[Callable[[], None]] = None,
        log_fn: Optional[Callable[..., None]] = None,
        stats_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        self.every = int(every)
        if self.every <= 0:
            raise ValueError("RoceSyncSampler: every must be >= 1")
        self.check_fn = check_fn
        self.refresh_fn = refresh_fn
        self.log_fn = log_fn
        self.stats_fn = stats_fn
        self.observations = 0
        self.checked = 0
        self.skipped_busy = 0
        self.no_copy_done = 0
        self.errors = 0
        self.last_payload: Optional[Dict[str, Any]] = None

    def observe(self, result: Any) -> Optional[Dict[str, Any]]:
        """对每个 batch result 调用；每 every 个做一次 query() 门控健康检查。"""
        self.observations += 1
        if self.observations % self.every != 0:
            return None
        copy_done = getattr(result, "copy_done", None)
        if copy_done is None:
            self.no_copy_done += 1
            return None
        try:
            done = bool(copy_done.query())
        except Exception:
            self.errors += 1
            return None
        if not done:
            # 未完成即跳过：绝不等待（逐 batch synchronize = INV-07 N3 反例）。
            self.skipped_busy += 1
            return None
        self.checked += 1
        if self.check_fn is not None:
            try:
                self.check_fn(copy_done)
            except Exception:
                self.errors += 1
        if self.refresh_fn is not None:
            try:
                self.refresh_fn()
            except Exception:
                self.errors += 1
        payload: Dict[str, Any] = {
            "observations": self.observations,
            "checked": self.checked,
            "skipped_busy": self.skipped_busy,
            "no_copy_done": self.no_copy_done,
            "errors": self.errors,
        }
        if self.stats_fn is not None:
            try:
                payload["roce_ar"] = self.stats_fn()
            except Exception:
                pass
        self.last_payload = payload
        if self.log_fn is not None:
            try:
                self.log_fn(
                    "%s %s",
                    self.LOG_PREFIX,
                    json.dumps(payload, separators=(",", ":"), sort_keys=True),
                )
            except Exception:
                self.errors += 1
        return payload
# ---- i14c-canonical: end ---------------------------------------------------


def gauges_from_stats(stats: Optional[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """roce_ar.stats() 快照 → 四 gauge 值（缺键/非整型 → None，判读侧可见）。"""
    out: Dict[str, Optional[int]] = {}
    if not isinstance(stats, dict):
        return {name: None for name in GAUGE_NAMES}
    for stats_key, gauge in GAUGE_STATS_KEYS.items():
        raw = stats.get(stats_key)
        try:
            out[gauge] = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            out[gauge] = None
    return out


def validate_gauges(gauges: Optional[Dict[str, Any]]) -> List[str]:
    """单快照校验（INV-07 可观测门：四名齐、无 NaN、非负整型）。"""
    bad: List[str] = []
    if not isinstance(gauges, dict):
        return ["gauges-not-a-dict"]
    for name in GAUGE_NAMES:
        v = gauges.get(name)
        if v is None:
            bad.append(f"{name}:missing")
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            bad.append(f"{name}:not-int")
            continue
        if iv < 0:
            bad.append(f"{name}:negative")
    return bad


class GaugeAudit:
    """跨快照审计（单调不减 + 无回退；INV-07 可观测门"四 gauge 单调"）。"""

    def __init__(self) -> None:
        self.prev: Dict[str, int] = {}
        self.violations: List[str] = []

    def feed(self, gauges: Optional[Dict[str, Any]]) -> List[str]:
        bad = validate_gauges(gauges)
        if bad:
            self.violations.extend(bad)
            return bad
        for name in GAUGE_NAMES:
            v = int(gauges[name])  # validate_gauges 已保证可整型化
            if name in self.prev and v < self.prev[name]:
                msg = f"{name}:regressed {self.prev[name]}->{v}"
                self.violations.append(msg)
                bad.append(msg)
            self.prev[name] = v
        return bad


def render_prometheus(
    gauges: Dict[str, Any],
    docs: Optional[Dict[str, str]] = None,
) -> str:
    """四 gauge 的 Prometheus 文本暴露形态（adapter 侧同格式；离线审计同源）。"""
    docs = docs or GAUGE_DOCS
    lines: List[str] = []
    for name in GAUGE_NAMES:
        doc = docs.get(name, name + " (I14-C case B).")
        lines.append(f"# HELP {name} {doc}")
        lines.append(f"# TYPE {name} gauge")
        v = gauges.get(name)
        lines.append(f"{name} {v if v is not None else 'NaN'}")
    return "\n".join(lines) + "\n"


_SCRAPE_RE = re.compile(
    r"^(?P<name>[A-Za-z_:][A-Za-z0-9_:]*)(?:\{(?P<labels>[^}]*)\})?\s+"
    r"(?P<value>[^\s]+)\s*$"
)


def parse_scrape(text: str) -> Dict[str, Optional[float]]:
    """从 /metrics 文本中取四 gauge 值（支持 {pid="..."} 标签变体；多 pid 取最大）。"""
    out: Dict[str, Optional[float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _SCRAPE_RE.match(line)
        if not m or m.group("name") not in GAUGE_NAMES:
            continue
        try:
            v = float(m.group("value"))
        except ValueError:
            v = None
        name = m.group("name")
        if not (v is None or v >= 0):
            v = None
        prev = out.get(name)
        if prev is None or (v is not None and v > prev):
            out[name] = v
    for name in GAUGE_NAMES:
        out.setdefault(name, None)
    return out


def cross_check(
    gauge_values: Optional[Dict[str, Any]],
    log_stats: Optional[Dict[str, Any]],
) -> List[str]:
    """scrape 值 vs 日志 stats() 对拍（INV-07 可观测门"与日志口径一致"）。

    gauge 面单调计数器在任意时刻 ≥ 采样日志快照（日志在前、计数在后），
    故只判 gauge < log 为不一致；gauge ≥ log 且差值非负为一致（随刷新节奏滞后）。
    """
    bad: List[str] = []
    if not isinstance(gauge_values, dict) or not isinstance(log_stats, dict):
        return ["inputs-not-dicts"]
    for stats_key, gauge in GAUGE_STATS_KEYS.items():
        g = gauge_values.get(gauge)
        l = log_stats.get(stats_key)
        if g is None or l is None:
            continue
        try:
            g_i, l_i = int(g), int(l)
        except (TypeError, ValueError):
            bad.append(f"{gauge}:non-int")
            continue
        if g_i < l_i:
            bad.append(f"{gauge}:{g_i}<log:{l_i}")
    return bad


SCHEDULER_FACE_SOURCE = '''\
def _make_roce_i14c_sampler():
    """I14-C 案 A 低频采样 + 案 B gauge 刷新（R36-b A+B 合并单臂；env 默认关 → None）。

    法源: 任务书 §T33-08 目标 3；INV-07 §4.2/§4.3；W4 §5.6 阻清单。
    DSV41_ROCE_SYNC_SAMPLE=N（N>=1 每 N 个 batch result 一次；0/未设=关）。
    check_fn 取自 pynccl 面 synchronize_and_check_roce（NCCL 臂无该面 → REFUSED
    返回 None）；query() 门控、未完成即跳过，绝不逐 batch synchronize。
    案 B gauge 刷新（adapter roce_metrics_gauge.refresh_gauges，自带
    DSV41_ROCE_METRICS 门控）随同点低频执行；缺面=静默降级（案 A 单独成立）。
    """
    try:
        every = int(str(os.environ.get("DSV41_ROCE_SYNC_SAMPLE", "0")).strip() or "0")
    except ValueError:
        every = 0
    if every <= 0:
        return None
    check_fn = None
    try:
        from sglang.srt.distributed.device_communicators import (
            pynccl as _roce_i14c_pynccl,
        )
        check_fn = getattr(_roce_i14c_pynccl, "synchronize_and_check_roce", None)
    except Exception:
        check_fn = None
    if check_fn is None:
        logger.info(
            "ROCE_I14C REFUSED pynccl face has no synchronize_and_check_roce"
        )
        return None
    refresh_fn = None
    try:
        from roce_metrics_gauge import refresh_gauges as refresh_fn
    except Exception:
        refresh_fn = None
    try:
        from roce_ar import stats as _roce_ar_stats
    except Exception:
        _roce_ar_stats = None
    sampler = RoceSyncSampler(
        every=every,
        check_fn=check_fn,
        refresh_fn=refresh_fn,
        log_fn=logger.info,
        stats_fn=_roce_ar_stats,
    )
    logger.info(
        "ROCE_I14C ARMED every=%d metrics_refresh=%s",
        every,
        "on" if refresh_fn is not None else "off",
    )
    return sampler.observe
'''

ADAPTER_GAUGES_SOURCE = '''\
def gauges():
    """I14-C 案 B four-gauge readout (INV-07 §4.2 suggested names; readonly).

    Frozen caliber: names roce_ar_communicators / roce_ar_roce_made /
    roce_ar_roce_routed / roce_ar_nccl_kept (P0 freeze, 2026-10-24). Values are
    monotonic counters over the process lifetime; missing key -> 0 is NOT
    coerced (the dict carries exactly the four STATS keys)."""
    return {
        "roce_ar_communicators": int(STATS["communicators"]),
        "roce_ar_roce_made": int(STATS["roce_made"]),
        "roce_ar_roce_routed": int(STATS["roce_routed"]),
        "roce_ar_nccl_kept": int(STATS["nccl_kept"]),
    }
'''


def _selfcheck() -> int:
    """--selfcheck：合成场景走查（负对照=关/坏面必须被正确处置）。"""
    checks = 0

    def need(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise SystemExit(f"SELFCHK ROCE_I14C FAIL: {what}")

    # 1) gauges_from_stats：齐键/缺键/坏键。
    g = gauges_from_stats(
        {"communicators": 1, "roce_made": 1, "roce_routed": 10, "nccl_kept": 5,
         "runtimes": 1, "version": "x"}
    )
    need(g == {"roce_ar_communicators": 1, "roce_ar_roce_made": 1,
               "roce_ar_roce_routed": 10, "roce_ar_nccl_kept": 5}, "stats→gauge 映射")
    need(gauges_from_stats(None) == {n: None for n in GAUGE_NAMES}, "非 dict→全 None")
    need(gauges_from_stats({"communicators": "x"})["roce_ar_communicators"] is None,
         "坏键→None")
    need("roce_ar_nccl_kept:negative" in validate_gauges({"roce_ar_nccl_kept": -1}),
         "负值检出")

    # 2) 采样器：每 3 个一次；query 门控；异常吞掉。
    class FakeEvent:
        def __init__(self, done=True, boom=False):
            self.done, self.boom = done, boom
            self.checks = 0

        def query(self):
            if self.boom:
                raise RuntimeError("query boom")
            return self.done

    class Result:
        def __init__(self, ev):
            self.copy_done = ev

    evs = []
    checks_log = []

    def check_fn(cd):
        cd.checks += 1
        evs.append(cd)

    sampler = RoceSyncSampler(every=3, check_fn=check_fn, log_fn=None)
    for _ in range(9):
        sampler.observe(Result(FakeEvent(done=True)))
    need(sampler.observations == 9 and sampler.checked == 3, "每 3 个一次")
    need(all(e.checks == 1 for e in evs) and len(evs) == 3, "check_fn 执行数")

    busy = RoceSyncSampler(every=1, check_fn=check_fn)
    for _ in range(4):
        busy.observe(Result(FakeEvent(done=False)))
    need(busy.checked == 0 and busy.skipped_busy == 4, "query 未完成跳过")

    boom = RoceSyncSampler(every=1, check_fn=check_fn)
    for _ in range(2):
        boom.observe(Result(FakeEvent(boom=True)))
    need(boom.checked == 0 and boom.errors == 2, "query 异常吞掉计数")

    nocd = RoceSyncSampler(every=1)
    nocd.observe(object())
    need(nocd.no_copy_done == 1 and nocd.checked == 0, "无 copy_done 计数")

    try:
        RoceSyncSampler(every=0)
        need(False, "every=0 必须 raise")
    except ValueError:
        need(True, "every=0 raise")

    # 3) 日志 payload 形态 + stats 注入。
    logs = []
    s2 = RoceSyncSampler(every=1, log_fn=lambda fmt, *a: logs.append(fmt % a),
                         stats_fn=lambda: {"roce_routed": 7, "nccl_kept": 3})
    pay = s2.observe(Result(FakeEvent(done=True)))
    need(len(logs) == 1 and logs[0].startswith("ROCE_I14C_SAMPLE {"), "日志前缀")
    need(pay["roce_ar"]["roce_routed"] == 7, "payload stats")

    # 4) GaugeAudit：单调审计 + 回退检出。
    aud = GaugeAudit()
    need(aud.feed(g) == [], "首喂绿")
    g2 = dict(g, roce_ar_roce_routed=11)
    need(aud.feed(g2) == [], "递增绿")
    g3 = dict(g2, roce_ar_roce_routed=9)
    need(any("regressed" in x for x in aud.feed(g3)), "回退检出")

    # 5) Prometheus 渲染/解析往返（含 pid 标签变体）。
    text = render_prometheus(g)
    got = parse_scrape(text)
    need(all(abs((got[n] or 0) - g[n]) < 1e-9 for n in GAUGE_NAMES), "渲染解析往返")
    pid_text = 'roce_ar_roce_routed{pid="1"} 10\nroce_ar_roce_routed{pid="2"} 12\n'
    need(parse_scrape(pid_text)["roce_ar_roce_routed"] == 12.0, "多 pid 取最大")

    # 6) 对拍：gauge ≥ log 一致；gauge < log 检出。
    need(cross_check(g, {"roce_routed": 10, "nccl_kept": 5}) == [], "对拍一致")
    need(any("roce_ar_roce_routed" in x for x in
             cross_check(g, {"roce_routed": 11, "nccl_kept": 5})), "对拍检出")

    # 7) scheduler face 源：exec 求值（stub 环境）直证 默认关/开/缺面 REFUSED。
    ns = {"os": __import__("os"), "json": json, "logger": _FakeLogger()}
    exec(compile(SCHEDULER_FACE_SOURCE, "<i14c-scheduler-face>", "exec"), ns)
    make = ns["_make_roce_i14c_sampler"]
    saved = dict(__import__("os").environ)
    try:
        __import__("os").environ.pop(ENV_SAMPLE, None)
        need(make() is None, "face 默认关→None")
        __import__("os").environ[ENV_SAMPLE] = "64"
        need(make() is None, "face 缺 pynccl 面→REFUSED None")
    finally:
        __import__("os").environ.clear()
        __import__("os").environ.update(saved)

    # 8) ADAPTER_GAUGES_SOURCE：语法编译 + STATS 桩求值直证。
    tree = compile(ADAPTER_GAUGES_SOURCE, "<i14c-adapter-gauges>", "exec")
    ans = {"communicators": 2, "roce_made": 2, "roce_routed": 20, "nccl_kept": 9}
    ns2 = {"STATS": ans, "int": int}
    exec(tree, ns2)
    need(ns2["gauges"]() == {
        "roce_ar_communicators": 2, "roce_ar_roce_made": 2,
        "roce_ar_roce_routed": 20, "roce_ar_nccl_kept": 9,
    }, "adapter gauges() 求值")

    print(f"SELFCHK ROCE_I14C ok checks={checks}")
    return 0


class _FakeLogger:
    def info(self, *a, **k):
        return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selfcheck":
        return _selfcheck()
    print(__doc__.splitlines()[0])
    print("usage: roce_i14c.py --selfcheck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
