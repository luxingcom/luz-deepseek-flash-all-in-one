#!/usr/bin/env python3
"""SCHED_STATS_V1 -- T33-03 Phase 1 只读调度账本（0 靴纯开发件，2026-10-23）。

法源
  * 任务书 `033-TASKBOOK-V2-20261023.md` §T33-03 目标 2（Phase 1）：
    overlay `scheduler.py` 增加 `SCHED_STATS_V1` 只读 JSON 行（默认关），
    每 40 步或 2s emit；字段：step type、step_us p50/p99、batch size、graph_bs、
    KV 使用率、d_gen_tokens/d_accepted/d_verified/d_accept_len/d_accept_rate/
    d_committed_tps/d_full_accept_equiv_tps、prefill uncached tps、defer/skip 计数。
    验收门：开启时 step p50 开销 <1%、日志体积 <1MB/分钟；默认关闭时产线
    行为/延迟/日志逐字节无变化；回退=env 一行关闭，不改镜像。
  * 设计稿 `033-INVESTIGATIONS/INV-02-BENCH-OBSERVABILITY.md` §6.2/§6.3/§6.4
    （字段表、采样窗口、接线点；env 键名 SGLANG_SCHED_STATS 三键）。
  * 口径正典 `docs/registry/BENCHMARK-SOURCE.md` §七：新统计面须带口径标签，
    数字不自算入正典；本面只产原始 JSON 行，判读归窗档报告。

性质与红线
  * 纯 stdlib（json/math/os/time），不 import sglang/torch -- CPU-only 可测。
  * 只读：不改变任何调度决策；默认关（env 无键=关）；关时对象不构造
    （接线层 `is None` 单分支检查）或构造后所有入口立即返回（零时钟/零输出）。
  * 输出面损坏/半写不崩主流程：emit 全程 try/except，连续 3 次失败自动熔断
    （enabled=False），窗口照常复位，主调度路径永不见异常。

canonical 类与 overlay 补丁的一致性
  下方 `SchedStatsV1` 类（sentinel 注释之间）是唯一权威实现；
  `tools/patches/sched_stats_v1.overlay-scheduler.patch`（呈裁件，未应用）
  向 `deploy/overlay/o12c1-prod/scheduler.py` 插入的类体与 sentinel 段逐字一致，
  由 tests/unit/test_sched_stats_v1.py 在测试里强制核对（漂移即红）。

字段口径（速查）
  d_* = decode 步聚合；p_* = prefill 步聚合；γ = nextn（DSPARK 静态 5）。
  d_accepted = d_gen - d_batch（含 golden token；gen = accepted + b 恒等式）；
  accept 三项在 SPEC=1 且存在非 target_verify decode 步时改用 verify 子集
  （d_accept_base="spec"，另记 d_spec_batch_sum/d_spec_gen_tokens）；
  γ=0 或无 verify 子集时 rate/verified_len/full_accept_equiv 置 null
  （SPEC=0 臂不参与双口径判读）。full_accept_equiv 是副标签，禁止作主口径。
  分位 nearest-rank：P_q = sorted[ceil(q/100*n)-1]（与 de_c48_bench 同定义，
  小样本不外插）；窗内样本 >64 时 ring 只保留最近 64 步（有界内存）。
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "SchedStatsV1",
    "ENV_ENABLE",
    "ENV_INTERVAL",
    "ENV_TAG",
    "DEFAULT_INTERVAL",
    "validate_record",
    "main",
]

ENV_ENABLE = "SGLANG_SCHED_STATS"  # 默认 "0"（关）；"1"/"true"/"on" 开
ENV_INTERVAL = "SGLANG_SCHED_STATS_INTERVAL"  # 默认 40 步/窗
ENV_TAG = "SGLANG_SCHED_STATS_TAG"  # 臂标签（缺省 ""）
DEFAULT_INTERVAL = 40


# ---- patch-canonical: begin（插入类体与 overlay 补丁逐字一致，单测强制同步）----
class SchedStatsV1:
    """SCHED_STATS_V1 只读调度账本（T33-03 Phase 1；默认关，零副作用）。

    热路径入口 on_step/on_skip/on_defer 在 enabled=False 时第一行返回，
    不读时钟、不分配、不输出。emit 每 interval 步（默认 40）或窗墙钟
    >= 2.0s（步边界评估，无定时器线程）产出一行
    ``SCHED_STATS_V1 {json}``（compact separators，allow_nan=False）。
    """

    SCHEMA = "sched-stats-v1"
    LINE_PREFIX = "SCHED_STATS_V1"
    WINDOW_MAX_SEC = 2.0
    RING_SLOTS = 64
    MAX_EMIT_FAILURES = 3
    DEFAULT_INTERVAL = 40
    ENV_ENABLE = "SGLANG_SCHED_STATS"
    ENV_INTERVAL = "SGLANG_SCHED_STATS_INTERVAL"
    ENV_TAG = "SGLANG_SCHED_STATS_TAG"
    _OFF_VALUES = ("", "0", "false", "off")

    def __init__(
        self,
        env: Optional[Dict[str, str]] = None,
        gamma: int = 0,
        interval: Optional[int] = None,
        tag: Optional[str] = None,
        sink: Optional[Callable[[str], None]] = None,
        clock: Optional[Callable[[], float]] = None,
        get_running: Optional[Callable[[], int]] = None,
        get_waiting: Optional[Callable[[], int]] = None,
        get_kv: Optional[Callable[[], Tuple[int, int]]] = None,
        get_graph_bs: Optional[Callable[[], Any]] = None,
        get_rank: Optional[Callable[[], int]] = None,
    ) -> None:
        if env is None:
            env = os.environ
        self.enabled = (
            str(env.get(self.ENV_ENABLE, "0")).strip().lower()
            not in self._OFF_VALUES
        )
        self.gamma = int(gamma or 0)
        if interval is None:
            interval = self._parse_interval(env.get(self.ENV_INTERVAL))
        self.interval = interval
        if tag is None:
            tag = str(env.get(self.ENV_TAG, "") or "")
        self.tag = tag
        self._sink = sink
        self._clock = clock if clock is not None else time.monotonic
        self._get_running = get_running
        self._get_waiting = get_waiting
        self._get_kv = get_kv
        self._get_graph_bs = get_graph_bs
        self._get_rank = get_rank
        self._reset_window()
        self._reset_totals()

    # -- 配置解析 ---------------------------------------------------------
    @classmethod
    def _parse_interval(cls, raw: Any) -> int:
        try:
            v = int(str(raw).strip())
        except (TypeError, ValueError):
            return cls.DEFAULT_INTERVAL
        return v if v > 0 else cls.DEFAULT_INTERVAL

    # -- 窗口/累计状态 ----------------------------------------------------
    def _reset_window(self) -> None:
        self._win_steps = 0
        self._win_start: Optional[float] = None
        self._p_steps = 0
        self._p_busy_us = 0
        self._p_uncached_tokens = 0
        self._p_ring = [0] * self.RING_SLOTS
        self._p_ring_n = 0
        self._d_steps = 0
        self._d_busy_us = 0
        self._d_batch_sum = 0
        self._d_gen_tokens = 0
        self._d_us_max = 0
        self._d_ring = [0] * self.RING_SLOTS
        self._d_ring_n = 0
        self._d_spec_steps = 0
        self._d_spec_batch_sum = 0
        self._d_spec_gen_tokens = 0
        self._mixed_steps = 0
        self._prefill_defer = 0
        self._skip_noncontig = 0
        self._skip_health = 0
        self._skip_range = 0

    def _reset_totals(self) -> None:
        self._tot_windows = 0
        self._tot_win_steps = 0
        self._tot_d_gen_tokens = 0
        self._tot_d_batch_sum = 0
        self._tot_d_spec_batch_sum = 0
        self._tot_d_spec_gen_tokens = 0
        self._tot_p_uncached_tokens = 0
        self._emit_fail_tot = 0

    # -- 热路径入口（关=零开销） ------------------------------------------
    def on_step(
        self,
        is_prefill: bool,
        step_us: int,
        batch_size: int = 0,
        gen_tokens: int = 0,
        extend_num_tokens: int = 0,
        is_target_verify: bool = False,
        is_mixed: bool = False,
    ) -> None:
        if not self.enabled:
            return
        now = self._clock()
        if self._win_steps == 0:
            self._win_start = now
        self._win_steps += 1
        if is_prefill:
            self._p_steps += 1
            self._p_busy_us += step_us
            self._p_uncached_tokens += extend_num_tokens
            self._p_ring[self._p_ring_n % self.RING_SLOTS] = step_us
            self._p_ring_n += 1
            if is_mixed:
                self._mixed_steps += 1
        else:
            self._d_steps += 1
            self._d_busy_us += step_us
            self._d_batch_sum += batch_size
            self._d_gen_tokens += gen_tokens
            self._d_ring[self._d_ring_n % self.RING_SLOTS] = step_us
            self._d_ring_n += 1
            if step_us > self._d_us_max:
                self._d_us_max = step_us
            if is_target_verify:
                self._d_spec_steps += 1
                self._d_spec_batch_sum += batch_size
                self._d_spec_gen_tokens += gen_tokens
        if self._win_steps >= self.interval or (
            now - self._win_start >= self.WINDOW_MAX_SEC
        ):
            self.emit(now=now)

    def on_skip(self, kind: str) -> None:
        """早退分支计数（未被计入窗口的步）：health / noncontig / range。"""
        if not self.enabled:
            return
        if kind == "health":
            self._skip_health += 1
        elif kind == "noncontig":
            self._skip_noncontig += 1
        elif kind == "range":
            self._skip_range += 1

    def on_defer(self) -> None:
        """_should_defer_prefill 返回 True 的次数（只计数，不改调度）。"""
        if not self.enabled:
            return
        self._prefill_defer += 1

    # -- 产出面（损坏/半写不崩主流程） ------------------------------------
    def emit(self, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            if now is None:
                now = self._clock()
            rec = self._build_record(now)
            line = self.LINE_PREFIX + " " + json.dumps(
                rec, separators=(",", ":"), allow_nan=False
            )
            if self._sink is not None:
                self._sink(line)
        except Exception:
            rec = None
        if rec is not None:
            self._tot_windows += 1
            self._tot_win_steps += self._win_steps
            self._tot_d_gen_tokens += self._d_gen_tokens
            self._tot_d_batch_sum += self._d_batch_sum
            self._tot_d_spec_batch_sum += self._d_spec_batch_sum
            self._tot_d_spec_gen_tokens += self._d_spec_gen_tokens
            self._tot_p_uncached_tokens += self._p_uncached_tokens
        else:
            self._emit_fail_tot += 1
            if self._emit_fail_tot >= self.MAX_EMIT_FAILURES:
                # 输出面连续损坏：熔断（永不再 emit），调度主流程不受影响。
                self.enabled = False
        self._reset_window()
        return rec

    # -- 记录构造 ---------------------------------------------------------
    def _build_record(self, now: float) -> Dict[str, Any]:
        d_busy_s = self._d_busy_us / 1e6
        p_busy_s = self._p_busy_us / 1e6
        base_b = base_g = None
        accept_base = None
        if self.gamma > 0 and self._d_spec_batch_sum > 0:
            base_b, base_g, accept_base = (
                self._d_spec_batch_sum,
                self._d_spec_gen_tokens,
                "spec",
            )
        elif self._d_batch_sum > 0:
            base_b, base_g, accept_base = self._d_batch_sum, self._d_gen_tokens, "all"
        d_accepted = base_g - base_b if base_b is not None else None
        if accept_base == "spec":
            d_verified = self.gamma * base_b
        else:
            d_verified = None  # γ=0 或窗内无 verify 子集：置 null，不参与判读
        d_accept_len = (
            self._fin(base_g / base_b) if base_b is not None and base_b > 0 else None
        )
        d_accept_rate = (
            self._fin(d_accepted / d_verified)
            if d_verified is not None and d_verified > 0 and d_accepted is not None
            else None
        )
        d_verified_len = self.gamma if accept_base == "spec" and self.gamma > 0 else None
        d_committed = (
            self._fin(self._d_gen_tokens / d_busy_s) if d_busy_s > 0 else None
        )
        d_full = (
            self._fin(d_committed * (1 + self.gamma) / d_accept_len)
            if self.gamma > 0
            and d_committed is not None
            and d_accept_len is not None
            and d_accept_len > 0
            else None  # γ=0（SPEC=0 臂）不参与双口径判读
        )
        p_uncached_tps = (
            self._fin(self._p_uncached_tokens / p_busy_s) if p_busy_s > 0 else None
        )
        kv_free, kv_total = self._snap_kv()
        kv_used = kv_total - kv_free if kv_total is not None and kv_free is not None else None
        rec: Dict[str, Any] = {
            "schema": self.SCHEMA,
            "tag": self.tag,
            "rank": self._snap_int(self._get_rank),
            "gamma": self.gamma,
            "interval": self.interval,
            "win_steps": self._win_steps,
            "win_wall_us": (
                int((now - self._win_start) * 1e6)
                if self._win_start is not None
                else 0
            ),
            "ident_ok": self._ident_ok(base_b, base_g, d_accepted, d_accept_len, d_accept_rate, d_verified),
            "p_steps": self._p_steps,
            "p_busy_us": self._p_busy_us,
            "p_uncached_tokens": self._p_uncached_tokens,
            "p_uncached_tps": p_uncached_tps,
            "p_step_us_p50": self._pctl(self._ring_values(self._p_ring, self._p_ring_n), 50),
            "p_step_us_p99": self._pctl(self._ring_values(self._p_ring, self._p_ring_n), 99),
            "d_steps": self._d_steps,
            "d_spec_steps": self._d_spec_steps,
            "d_spec_batch_sum": self._d_spec_batch_sum,
            "d_spec_gen_tokens": self._d_spec_gen_tokens,
            "d_batch_sum": self._d_batch_sum,
            "d_batch_mean": self._fin(self._d_batch_sum / self._d_steps) if self._d_steps else None,
            "d_gen_tokens": self._d_gen_tokens,
            "d_accepted": d_accepted,
            "d_verified": d_verified,
            "d_accept_len": d_accept_len,
            "d_accept_rate": d_accept_rate,
            "d_verified_len": d_verified_len,
            "d_accept_base": accept_base,
            "d_committed_tps": d_committed,
            "d_full_accept_equiv_tps": d_full,
            "d_step_us_p50": self._pctl(self._ring_values(self._d_ring, self._d_ring_n), 50),
            "d_step_us_p99": self._pctl(self._ring_values(self._d_ring, self._d_ring_n), 99),
            "d_step_us_max": self._d_us_max if self._d_steps else None,
            "d_busy_us": self._d_busy_us,
            "mixed_steps": self._mixed_steps,
            "graph_bs_max": self._snap_graph_bs(),
            "running_after": self._snap_int(self._get_running),
            "waiting_after": self._snap_int(self._get_waiting),
            "kv_used": kv_used,
            "kv_free": kv_free,
            "kv_total": kv_total,
            "kv_usage_pct": (
                self._fin(kv_used / kv_total * 100.0)
                if kv_used is not None and kv_total
                else None
            ),
            "prefill_defer": self._prefill_defer,
            "skip_noncontig": self._skip_noncontig,
            "skip_health": self._skip_health,
            "skip_range": self._skip_range,
            "tot_windows": self._tot_windows + 1,
            "tot_win_steps": self._tot_win_steps + self._win_steps,
            "tot_d_gen_tokens": self._tot_d_gen_tokens + self._d_gen_tokens,
            "tot_d_batch_sum": self._tot_d_batch_sum + self._d_batch_sum,
            "tot_d_spec_batch_sum": self._tot_d_spec_batch_sum + self._d_spec_batch_sum,
            "tot_d_spec_gen_tokens": self._tot_d_spec_gen_tokens + self._d_spec_gen_tokens,
            "tot_p_uncached_tokens": self._tot_p_uncached_tokens + self._p_uncached_tokens,
            "emit_fail_tot": self._emit_fail_tot,
        }
        return rec

    def _ident_ok(self, base_b, base_g, d_accepted, d_accept_len, d_accept_rate, d_verified):
        """每窗账目闭合自检（INV-02 §6.6 硬门；不成立=接线/计数有 bug）。"""
        if base_b is None or base_g is None:
            return True
        ok = base_g == d_accepted + base_b
        if d_accept_len is not None and d_accept_rate is not None:
            ok = ok and abs(d_accept_len - (1 + self.gamma * d_accept_rate)) <= 1e-6
        if d_verified is not None:
            ok = ok and d_verified == self.gamma * base_b
        return ok

    # -- 快照（emit 时一次性调用；任何异常→null，绝不抛进调度） ------------
    def _snap_int(self, fn):
        try:
            v = fn() if fn is not None else None
            return int(v) if v is not None else None
        except Exception:
            return None

    def _snap_kv(self):
        try:
            if self._get_kv is None:
                return None, None
            free, total = self._get_kv()
            free = int(free)
            total = int(total)
            if total <= 0 or free < 0 or free > total:
                return None, None
            return free, total
        except Exception:
            return None, None

    def _snap_graph_bs(self):
        try:
            if self._get_graph_bs is None:
                return None
            v = self._get_graph_bs()
            if v is None:
                return None
            if isinstance(v, (list, tuple, set)):
                ints = [int(x) for x in v if x is not None]
                return max(ints) if ints else None
            return int(v)
        except Exception:
            return None

    # -- 工具 -------------------------------------------------------------
    @staticmethod
    def _fin(x):
        """非有限浮点→None（保 allow_nan=False 的 dumps 永不抛）。"""
        if x is None:
            return None
        try:
            xf = float(x)
        except (TypeError, ValueError):
            return None
        return xf if math.isfinite(xf) else None

    @staticmethod
    def _pctl(xs, q):
        """nearest-rank 分位：P_q = sorted[ceil(q/100*n)-1]；小样本不外插。"""
        ys = sorted(xs)
        n = len(ys)
        if n == 0:
            return None
        i = math.ceil(q * n / 100.0) - 1
        if i < 0:
            i = 0
        if i >= n:
            i = n - 1
        return ys[i]

    @staticmethod
    def _ring_values(ring, n):
        return ring[: n] if n <= len(ring) else ring[:]
# ---- patch-canonical: end -------------------------------------------------


def snapshot_totals(stats: SchedStatsV1) -> Dict[str, int]:
    """累计总量（Σ窗=cum 闭合用；窗复位后仍保留）。"""
    return {
        "tot_windows": stats._tot_windows,
        "tot_win_steps": stats._tot_win_steps,
        "tot_d_gen_tokens": stats._tot_d_gen_tokens,
        "tot_d_batch_sum": stats._tot_d_batch_sum,
        "tot_d_spec_batch_sum": stats._tot_d_spec_batch_sum,
        "tot_d_spec_gen_tokens": stats._tot_d_spec_gen_tokens,
        "tot_p_uncached_tokens": stats._tot_p_uncached_tokens,
        "emit_fail_tot": stats._emit_fail_tot,
    }


def validate_record(rec: Dict[str, Any], gamma: Optional[int] = None) -> List[str]:
    """离线闭合校验（窗档判读用；返回违例列表，空=通过）。

    覆盖 INV-02 §6.6 硬门：schema 标签、gen=accepted+b 恒等式、
    accept_len=1+γ·rate 恒等式（γ>0 且 base="spec" 时）、verified=γ·b、
    tps 非负、JSON 可序列化且无 NaN。
    """
    bad: List[str] = []
    if rec.get("schema") != "sched-stats-v1":
        bad.append("schema")
    g = rec.get("gamma") if gamma is None else gamma
    b = rec.get("d_batch_sum")
    gen = rec.get("d_gen_tokens")
    sb = rec.get("d_spec_batch_sum")
    sgen = rec.get("d_spec_gen_tokens")
    base = rec.get("d_accept_base")
    if b is None or gen is None:
        bad.append("missing d_batch_sum/d_gen_tokens")
        return bad
    if (gen - b) < 0:
        bad.append("d_gen_tokens < d_batch_sum")
    if base == "spec":
        if sb is None or sgen is None:
            bad.append("base=spec but d_spec_* missing")
        else:
            if sgen - sb < 0:
                bad.append("d_spec_gen_tokens < d_spec_batch_sum")
            acc, alen = rec.get("d_accepted"), rec.get("d_accept_len")
            if acc != sgen - sb:
                bad.append("d_accepted != d_spec_gen - d_spec_batch")
            if alen is not None and sb:
                bad_alen = abs(alen - sgen / sb) > 1e-6
                if bad_alen:
                    bad.append("d_accept_len != d_spec_gen/d_spec_batch")
            ver = rec.get("d_verified")
            if g and ver is not None and ver != g * sb:
                bad.append("d_verified != gamma*d_spec_batch")
    if rec.get("d_accept_len") is not None and rec.get("d_accept_rate") is not None:
        if abs(rec["d_accept_len"] - (1 + (g or 0) * rec["d_accept_rate"])) > 1e-6:
            bad.append("accept_len != 1+gamma*rate")
    for k in ("d_committed_tps", "d_full_accept_equiv_tps", "p_uncached_tps"):
        v = rec.get(k)
        if v is not None and v < 0:
            bad.append(f"{k}<0")
    try:
        json.dumps(rec, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        bad.append("not-json-serializable-or-nan")
    return bad


def _selfcheck() -> int:
    """--selfcheck：合成场景走查（负对照=关/坏输出必须被正确处置）。"""
    lines: List[str] = []
    checks = 0

    def need(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise SystemExit(f"SELFCHK SCHED_STATS_V1 FAIL: {what}")

    # 1) 默认关：零输出、零时钟读。
    clock_calls = [0]

    def clock() -> float:
        clock_calls[0] += 1
        return 100.0

    off = SchedStatsV1(env={}, gamma=5, clock=clock, sink=lines.append)
    for _ in range(100):
        off.on_step(False, 1000, batch_size=8, gen_tokens=40, is_target_verify=True)
    off.on_skip("health")
    off.on_defer()
    need(off.emit() is None and not lines and clock_calls[0] == 0, "off=零输出零时钟")

    # 2) 40 步窗口 + 恒等式（γ=5：rate=0.8 → accept_len=5.0）。
    t = [0.0]

    def tclock() -> float:
        return t[0]

    on = SchedStatsV1(env={ENV_ENABLE: "1"}, gamma=5, tag="selfchk",
                      clock=tclock, sink=lines.append,
                      get_running=lambda: 8, get_waiting=lambda: 2,
                      get_kv=lambda: (1000, 9600), get_graph_bs=lambda: [1, 2, 4, 8])
    gens = [6, 5, 4, 6, 3, 6, 5, 4, 6, 5] * 4  # Σ=200, b=40 → rate=0.8
    for i, g in enumerate(gens):
        t[0] = i * 0.001
        on.on_step(False, 1000, batch_size=1, gen_tokens=g, is_target_verify=True)
    need(len(lines) == 1 and lines[0].startswith("SCHED_STATS_V1 "), "一行前缀")
    rec = json.loads(lines[0][len("SCHED_STATS_V1 "):])
    need(rec["win_steps"] == 40 and rec["d_steps"] == 40, "40 步窗")
    need(rec["d_gen_tokens"] == 200 and rec["d_batch_sum"] == 40, "计数")
    need(rec["d_accepted"] == 160 and rec["d_verified"] == 200, "accepted/verified")
    need(abs(rec["d_accept_len"] - 5.0) < 1e-9 and abs(rec["d_accept_rate"] - 0.8) < 1e-9,
         "accept_len/rate")
    need(rec["ident_ok"] is True, "ident_ok")
    need(rec["graph_bs_max"] == 8 and rec["kv_usage_pct"] is not None, "快照")
    need(not validate_record(rec), "validate_record")
    # committed=200tok/40ms*1e3 → 5000 tps；full=5000*6/5=6000（副标签）。
    need(abs(rec["d_committed_tps"] - 5000.0) < 1e-6, "committed_tps")
    need(abs(rec["d_full_accept_equiv_tps"] - 6000.0) < 1e-6, "full_accept_equiv")

    # 3) 2s 窗（间隔调大 → 墙钟触发）。
    on2 = SchedStatsV1(env={ENV_ENABLE: "1", ENV_INTERVAL: "100000"}, gamma=5,
                       clock=tclock, sink=lines.append)
    for i in range(50):
        t[0] = i * 0.05  # 第 41 步过 2.0s
        on2.on_step(False, 900, batch_size=2, gen_tokens=8, is_target_verify=True)
    need(len(lines) == 2, "2s 窗触发")

    # 4) 坏输出面：sink 抛异常 → 不崩、3 次熔断、窗口复位。
    def bad_sink(line: str) -> None:
        raise OSError("half-written log device")

    on3 = SchedStatsV1(env={ENV_ENABLE: "1", ENV_INTERVAL: "1"}, gamma=5,
                       clock=tclock, sink=bad_sink)
    for _ in range(5):
        on3.on_step(False, 500, batch_size=1, gen_tokens=3, is_target_verify=True)
    need(on3.enabled is False and on3._win_steps == 0 and on3._emit_fail_tot == 3,
         "坏输出熔断")
    need(snapshot_totals(on3)["tot_windows"] == 0, "失败窗不计入累计")

    # 5) SPEC=0（γ=0）：rate/verified_len/full 置 null。
    on4 = SchedStatsV1(env={ENV_ENABLE: "1", ENV_INTERVAL: "4"}, gamma=0,
                       clock=tclock, sink=lines.append)
    for _ in range(4):
        on4.on_step(False, 500, batch_size=1, gen_tokens=1)
    last = json.loads(lines[-1][len("SCHED_STATS_V1 "):])
    need(last["d_accept_rate"] is None and last["d_verified_len"] is None
         and last["d_full_accept_equiv_tps"] is None and last["d_accept_len"] == 1.0,
         "gamma=0 置 null")

    print(f"SELFCHK SCHED_STATS_V1 ok checks={checks} lines={len(lines)}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selfcheck":
        return _selfcheck()
    print(__doc__.splitlines()[0])
    print("usage: sched_stats_v1.py --selfcheck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
