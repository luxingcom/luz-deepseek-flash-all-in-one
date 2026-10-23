"""SCHED_STATS_V1 CPU unit tests (T33-03 Phase 1; 0 靴, mock 数据驱动).

法源: 033-TASKBOOK-V2-20261023.md §T33-03 目标2/验收门; INV-02 §6.2-§6.6.
被测件: tools/obs/sched_stats_v1.py（canonical 类）与
        tools/patches/sched_stats_v1.overlay-scheduler.patch（呈裁接线件）。
不 import sglang/torch/GPU；单次 <60s。运行:
  /tmp/w0venv/bin/python -m pytest -q tests/unit/test_sched_stats_v1.py -o cache_dir=/tmp/w0cache
"""

import importlib.util
import json
import math
import os
import subprocess
import sys
import tempfile

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(REPO, "tools", "obs", "sched_stats_v1.py")
PATCH_PATH = os.path.join(REPO, "tools", "patches", "sched_stats_v1.overlay-scheduler.patch")
OVERLAY_SCHED = os.path.join(REPO, "deploy", "overlay", "o12c1-prod", "scheduler.py")

_spec = importlib.util.spec_from_file_location("sched_stats_v1", MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
SchedStatsV1 = m.SchedStatsV1

BEGIN_MARK = "# ---- patch-canonical: begin"
END_MARK = "# ---- patch-canonical: end"
PREFIX = "SCHED_STATS_V1 "


def make(env=None, **kw):
    kw.setdefault("env", {} if env is None else env)
    lines = []
    kw.setdefault("sink", lines.append)
    stats = SchedStatsV1(**kw)
    return stats, lines


def parse(line):
    assert line.startswith(PREFIX), line[:40]
    return json.loads(line[len(PREFIX):])


def decoded_lines(lines):
    return [parse(ln) for ln in lines]


class Clock:
    def __init__(self, t=0.0):
        self.t = t
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.t


# ── 负路径 1：键未开 = 零开销零输出 ─────────────────────────────────────────
def test_disabled_by_default_zero_output_zero_cost():
    clk = Clock()
    stats, lines = make(env={}, gamma=5, clock=clk)
    assert stats.enabled is False
    for _ in range(50):
        stats.on_step(False, 1000, batch_size=4, gen_tokens=20, is_target_verify=True)
    stats.on_skip("health")
    stats.on_skip("noncontig")
    stats.on_skip("range")
    stats.on_defer()
    assert stats.emit() is None
    assert lines == [] and clk.calls == 0  # 不读时钟、不输出、不触碰任何面


@pytest.mark.parametrize("val", ["", "0", "false", "off", "FALSE", " Off "])
def test_disabled_env_variants(val):
    stats, _ = make(env={m.ENV_ENABLE: val}, gamma=5)
    assert stats.enabled is False


@pytest.mark.parametrize("val", ["1", "true", "on", "YES"])
def test_enabled_env_variants(val):
    stats, _ = make(env={m.ENV_ENABLE: val}, gamma=5)
    assert stats.enabled is True


def test_interval_env_parsing():
    assert SchedStatsV1(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "7"}).interval == 7
    for bad in ["abc", "0", "-3", None]:
        env = {m.ENV_ENABLE: "1"}
        if bad is not None:
            env[m.ENV_INTERVAL] = bad
        assert SchedStatsV1(env=env).interval == 40, bad


# ── 窗口触发：40 步 / 2s ────────────────────────────────────────────────────
def test_emit_exactly_at_40_steps_and_reset():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1"}, gamma=5, clock=clk,
                        get_running=lambda: 8, get_waiting=lambda: 3,
                        get_kv=lambda: (600, 9600), get_graph_bs=lambda: [1, 2, 8])
    for i in range(39):
        stats.on_step(False, 1000, batch_size=1, gen_tokens=5, is_target_verify=True)
    assert lines == []  # 第 40 步前不 emit
    stats.on_step(False, 1000, batch_size=1, gen_tokens=5, is_target_verify=True)
    assert len(lines) == 1
    rec = parse(lines[0])
    assert rec["win_steps"] == 40 and rec["d_steps"] == 40
    assert rec["win_wall_us"] == 0  # 时钟静止
    assert rec["running_after"] == 8 and rec["waiting_after"] == 3
    assert rec["kv_total"] == 9600 and rec["kv_free"] == 600 and rec["kv_used"] == 9000
    assert rec["kv_usage_pct"] == pytest.approx(93.75)
    assert rec["graph_bs_max"] == 8
    assert stats._win_steps == 0  # 窗复位


def test_emit_at_2s_wall_clock():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "100000"},
                        gamma=5, clock=clk)
    for i in range(41):  # 0.05s/步 → 第 41 步 2.0s 整
        clk.t = i * 0.05
        stats.on_step(False, 900, batch_size=2, gen_tokens=8, is_target_verify=True)
    assert len(lines) == 1
    rec = parse(lines[0])
    assert rec["win_steps"] == 41
    assert rec["win_wall_us"] == 2_000_000
    assert rec["tot_windows"] == 1 and rec["tot_win_steps"] == 41
    # 复位后续步重新计窗
    clk.t = 2.5
    stats.on_step(False, 900, batch_size=2, gen_tokens=8, is_target_verify=True)
    assert len(lines) == 1 and stats._win_steps == 1


# ── 任务书字段逐项 + 恒等式（γ=5, rate=0.8 → accept_len=5） ────────────────
def test_dual_caliber_identity_gamma5():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1"}, gamma=5, tag="t33-03",
                        clock=clk)
    gens = [6, 5, 4, 6, 3, 6, 5, 4, 6, 5] * 4  # Σgen=200, Σb=40
    for g in gens:
        stats.on_step(False, 1000, batch_size=1, gen_tokens=g, is_target_verify=True)
    rec = parse(lines[0])
    # 任务书字段逐项
    assert rec["schema"] == "sched-stats-v1" and rec["tag"] == "t33-03"
    assert rec["d_gen_tokens"] == 200 and rec["d_batch_sum"] == 40
    assert rec["d_accepted"] == 160            # gen = accepted + b 恒等式
    assert rec["d_verified"] == 200            # γ·b（静态）
    assert rec["d_accept_len"] == pytest.approx(5.0)   # = 1 + γ·rate
    assert rec["d_accept_rate"] == pytest.approx(0.8)
    assert rec["d_accept_base"] == "spec"
    assert rec["d_spec_batch_sum"] == 40 and rec["d_spec_gen_tokens"] == 200
    assert rec["d_committed_tps"] == pytest.approx(200 / 0.040)
    assert rec["d_full_accept_equiv_tps"] == pytest.approx(5000 * 6 / 5)
    assert rec["d_step_us_p50"] == 1000 and rec["d_step_us_p99"] == 1000
    assert rec["d_step_us_max"] == 1000 and rec["d_busy_us"] == 40000
    assert rec["ident_ok"] is True
    assert m.validate_record(rec) == []


def test_gamma0_spec_off_null_fields():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "4"},
                        gamma=0, clock=clk)
    for _ in range(4):
        stats.on_step(False, 500, batch_size=1, gen_tokens=1)
    rec = parse(lines[0])
    # INV-02 注：γ=0 臂不参与双口径判读
    assert rec["d_accept_rate"] is None and rec["d_verified_len"] is None
    assert rec["d_full_accept_equiv_tps"] is None and rec["d_verified"] is None
    assert rec["d_accept_len"] == pytest.approx(1.0)  # 无 draft：恒为 1
    assert rec["d_accept_base"] == "all" and rec["ident_ok"] is True


def test_nonverify_decode_steps_use_spec_subset():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "15"},
                        gamma=5, clock=clk)
    for g in [6, 5, 4, 3, 6]:  # 5 个 verify 步（b=1）
        stats.on_step(False, 1000, batch_size=1, gen_tokens=g, is_target_verify=True)
    for _ in range(10):        # 10 个无 draft 的 decode 步（b=1, gen=1）
        stats.on_step(False, 1000, batch_size=1, gen_tokens=1, is_target_verify=False)
    rec = parse(lines[0])
    assert rec["d_steps"] == 15 and rec["d_batch_sum"] == 15 and rec["d_gen_tokens"] == 34
    assert rec["d_spec_steps"] == 5 and rec["d_spec_batch_sum"] == 5
    assert rec["d_spec_gen_tokens"] == 24
    assert rec["d_accept_base"] == "spec"       # accept 三项取 verify 子集
    assert rec["d_accepted"] == 19 and rec["d_verified"] == 25
    assert rec["d_accept_len"] == pytest.approx(24 / 5)
    assert rec["d_accept_rate"] == pytest.approx(19 / 25)
    # committed 仍用全部 decode 步（INV-02 注）
    assert rec["d_committed_tps"] == pytest.approx(34 / 0.015)
    assert m.validate_record(rec) == []


def test_spec1_window_without_verify_steps_nulls_rate():
    # SPEC=1 但窗内只有无 draft 的 decode 步：rate 不可算 → null，不得用全步稀释
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "3"},
                        gamma=5, clock=clk)
    for _ in range(3):
        stats.on_step(False, 500, batch_size=1, gen_tokens=1, is_target_verify=False)
    rec = parse(lines[0])
    assert rec["d_accept_base"] == "all"
    assert rec["d_accept_rate"] is None and rec["d_verified"] is None
    assert rec["d_accept_len"] == pytest.approx(1.0)


# ── 分位（nearest-rank，与 de_c48 同定义；ring>64 留最近 64） ────────────────
def test_percentile_nearest_rank_and_ring_wrap():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "100000"},
                        gamma=5, clock=clk)
    for i in range(130):
        stats.on_step(False, i + 1, batch_size=1, gen_tokens=3, is_target_verify=True)
    stats.emit()  # 强制收窗
    rec = parse(lines[0])
    expect = list(range(67, 131))  # ring 只留最近 64 步
    assert rec["d_step_us_p50"] == m.SchedStatsV1._pctl(expect, 50)
    assert rec["d_step_us_p99"] == m.SchedStatsV1._pctl(expect, 99)
    assert rec["d_step_us_max"] == 130
    # 独立复算（de_c48_bench.pctl_nearest_rank 同式：sorted[ceil(q/100*n)-1]）
    s = sorted(expect)
    assert rec["d_step_us_p50"] == s[math.ceil(0.50 * len(s)) - 1]
    assert rec["d_step_us_p99"] == s[math.ceil(0.99 * len(s)) - 1]


def test_percentile_small_sample_no_extrapolation():
    clk = Clock()
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "4"},
                        gamma=0, clock=clk)
    for us in [10, 20, 30, 40]:
        stats.on_step(False, us, batch_size=1, gen_tokens=1)
    rec = parse(lines[0])
    assert rec["d_step_us_p99"] == 40  # n=4 → P99 取最大，不外插
    assert rec["d_step_us_p50"] == 20


def test_empty_window_decode_fields_null():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "2"}, gamma=5)
    stats.on_step(True, 1500, extend_num_tokens=4096)
    stats.on_step(True, 1500, extend_num_tokens=4096)
    rec = parse(lines[0])
    assert rec["d_steps"] == 0 and rec["d_accept_len"] is None
    assert rec["d_step_us_p50"] is None and rec["d_step_us_max"] is None
    assert rec["p_steps"] == 2 and rec["p_uncached_tokens"] == 8192
    assert rec["p_uncached_tps"] == pytest.approx(8192 / 0.003)
    assert rec["p_step_us_p50"] == 1500 and rec["p_step_us_p99"] == 1500


# ── prefill 面 / mixed / defer / skip ──────────────────────────────────────
def test_prefill_mixed_defer_skip_counters():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "6"}, gamma=5)
    stats.on_step(True, 1000, extend_num_tokens=100, is_mixed=True)
    stats.on_step(True, 1000, extend_num_tokens=100)
    stats.on_step(False, 800, batch_size=2, gen_tokens=9, is_target_verify=True)
    stats.on_defer(); stats.on_defer(); stats.on_defer()
    stats.on_skip("health"); stats.on_skip("noncontig"); stats.on_skip("noncontig")
    stats.on_skip("range")
    stats.on_step(True, 1000, extend_num_tokens=100)
    stats.on_step(False, 800, batch_size=2, gen_tokens=9, is_target_verify=True)
    stats.on_step(True, 1000, extend_num_tokens=100)
    rec = parse(lines[0])
    assert rec["p_steps"] == 4 and rec["mixed_steps"] == 1
    assert rec["d_steps"] == 2 and rec["d_gen_tokens"] == 18 and rec["d_batch_sum"] == 4
    assert rec["prefill_defer"] == 3
    assert rec["skip_health"] == 1 and rec["skip_noncontig"] == 2 and rec["skip_range"] == 1
    assert m.validate_record(rec) == []


# ── 快照面：只在 emit 调用；损坏→null 不崩 ────────────────────────────────
def test_snapshot_providers_called_once_per_emit_only():
    calls = {"kv": 0, "run": 0, "wait": 0, "graph": 0, "rank": 0}

    def bump(key, fn):
        def w():
            calls[key] += 1
            return fn()
        return w

    stats, lines = make(
        env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "3"}, gamma=5,
        get_kv=bump("kv", lambda: (1, 2)),
        get_running=bump("run", lambda: 5),
        get_waiting=bump("wait", lambda: 6),
        get_graph_bs=bump("graph", lambda: [8]),
        get_rank=bump("rank", lambda: 0),
    )
    for _ in range(3):
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    assert calls == {"kv": 1, "run": 1, "wait": 1, "graph": 1, "rank": 1}
    assert parse(lines[0])["rank"] == 0
    for _ in range(3):  # 第二窗再核一次
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    assert calls["kv"] == 2 and calls["graph"] == 2


def test_broken_providers_degrade_to_null_no_crash():
    def boom():
        raise RuntimeError("provider broken")

    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "2"}, gamma=5,
                        get_kv=boom, get_running=boom, get_waiting=boom,
                        get_graph_bs=boom, get_rank=boom)
    for _ in range(2):
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    rec = parse(lines[0])
    for k in ("kv_used", "kv_free", "kv_total", "kv_usage_pct", "graph_bs_max",
              "running_after", "waiting_after", "rank"):
        assert rec[k] is None, k


def test_bad_kv_sanity_degrades_to_null():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "2"}, gamma=5,
                        get_kv=lambda: (99999, 100))  # free>total（损坏面）
    for _ in range(2):
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    rec = parse(lines[0])
    assert rec["kv_total"] is None and rec["kv_usage_pct"] is None


# ── 输出面损坏/半写：不崩主流程、熔断 ─────────────────────────────────────
def test_sink_failure_breaker_after_three():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "1"}, gamma=5)
    stats._sink = lambda line: (_ for _ in ()).throw(OSError("half-written"))
    for i in range(5):
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    assert stats.enabled is False           # 连续 3 次失败熔断
    assert stats._emit_fail_tot == 3 and stats._win_steps == 0
    assert stats._tot_windows == 0
    assert lines == []                      # 从未成功输出半行


def test_emit_failure_does_not_lose_prior_totals():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "2"}, gamma=5)
    for _ in range(4):  # 两个完整成功窗（每窗 2 步 × gen4 = 8）
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    assert len(lines) == 2 and stats._tot_windows == 2
    stats._sink = lambda line: (_ for _ in ()).throw(ValueError("disk full"))
    stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    assert stats._tot_windows == 2 and stats._emit_fail_tot == 1
    assert m.snapshot_totals(stats)["tot_d_gen_tokens"] == 16  # 只累计成功窗
    assert stats.enabled is True             # 未到 3 次不熔断


def test_every_emitted_line_is_strict_json_no_nan():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "3"},
                        gamma=5, get_kv=lambda: (0, 9_600_000))
    for i in range(9):
        stats.on_step(False, 100, batch_size=1, gen_tokens=i % 6, is_target_verify=True)
    assert len(lines) == 3
    for ln in lines:
        body = ln[len(PREFIX):]
        assert " " not in body.split('"tag"', 1)[0]  # compact separators（schema 段无空格）
        rec = json.loads(body)
        json.dumps(rec, allow_nan=False)             # 无 NaN/Inf
        assert rec["schema"] == "sched-stats-v1"


# ── 累计总量 Σ窗=cum ───────────────────────────────────────────────────────
def test_cumulative_totals_across_windows():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "3"},
                        gamma=5)
    steps = [(1, 4), (1, 5), (1, 6), (2, 7), (2, 8), (2, 9)]  # (batch, gen) 全 verify
    for b, g in steps:
        stats.on_step(False, 100, batch_size=b, gen_tokens=g, is_target_verify=True)
    assert len(lines) == 2
    r1, r2 = decoded_lines(lines)
    assert r1["win_steps"] == 3 and r2["win_steps"] == 3
    assert r2["tot_windows"] == 2 and r2["tot_win_steps"] == 6
    assert r2["tot_d_gen_tokens"] == r1["d_gen_tokens"] + r2["d_gen_tokens"] == 39
    assert r2["tot_d_batch_sum"] == 9
    tot = m.snapshot_totals(stats)
    assert tot["tot_d_gen_tokens"] == 39 and tot["tot_windows"] == 2
    # Σ窗 = cum 恒等
    assert r1["d_gen_tokens"] + r2["d_gen_tokens"] == tot["tot_d_gen_tokens"]
    assert r1["d_batch_sum"] + r2["d_batch_sum"] == tot["tot_d_batch_sum"]


# ── 离线闭合校验器：好记录绿、坏记录按正确理由红 ────────────────────────────
def test_validate_record_negative_controls():
    stats, lines = make(env={m.ENV_ENABLE: "1", m.ENV_INTERVAL: "2"}, gamma=5)
    for _ in range(2):
        stats.on_step(False, 100, batch_size=1, gen_tokens=4, is_target_verify=True)
    good = parse(lines[0])
    assert m.validate_record(good) == []

    def corrupt(**over):
        r = dict(good)
        r.update(over)
        return r

    assert "schema" in m.validate_record(corrupt(schema="other"))
    assert any("d_accepted" in v for v in m.validate_record(corrupt(d_accepted=99)))
    bad_len = m.validate_record(corrupt(d_accept_len=good["d_accept_len"] + 0.5))
    assert any("accept_len" in v for v in bad_len)
    nan_rec = corrupt(d_committed_tps=float("nan"))
    assert "not-json-serializable-or-nan" in m.validate_record(nan_rec)
    neg = m.validate_record(corrupt(d_committed_tps=-1.0))
    assert "d_committed_tps<0" in neg


# ── canonical 类与呈裁补丁的一致性/可应用性 ────────────────────────────────
def _canonical_block_from_module():
    lines = open(MODULE_PATH, encoding="utf-8").read().splitlines()
    start = end = None
    for k, ln in enumerate(lines):
        if ln.startswith(BEGIN_MARK):
            start = k
        if ln.startswith(END_MARK) and start is not None:
            end = k
            break
    assert start is not None and end is not None
    body = [ln for ln in lines[start:end] if not ln.startswith("# ---- patch-canonical")]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def test_patch_class_identity():
    body = _canonical_block_from_module()
    assert body[0].startswith("class SchedStatsV1")
    patch_text = open(PATCH_PATH, encoding="utf-8").read()
    assert "class SchedStatsV1" in patch_text
    # 补丁中 + 行里还原插入类体（class 行起，至类体最后一行止）
    plus = [ln[1:] for ln in patch_text.splitlines() if ln.startswith("+")
            and not ln.startswith("+++")]
    text = "\n".join(plus)
    i = text.index("class SchedStatsV1")
    last = body[-1]
    j = text.index(last, i) + len(last)
    inserted = text[i:j].splitlines()
    assert inserted == body, "patch 内类体与模块 canonical 段漂移"


def test_patch_dryrun_applies_clean():
    with tempfile.TemporaryDirectory() as td:
        rel = os.path.join("deploy", "overlay", "o12c1-prod")
        os.makedirs(os.path.join(td, rel))
        with open(os.path.join(td, rel, "scheduler.py"), "wb") as f:
            f.write(open(OVERLAY_SCHED, "rb").read())
        r = subprocess.run(
            ["patch", "-p1", "--dry-run", "-i", PATCH_PATH],
            cwd=td, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stdout + r.stderr


def test_module_selfcheck_green():
    r = subprocess.run(
        [sys.executable, MODULE_PATH, "--selfcheck"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip().startswith("SELFCHK SCHED_STATS_V1 ok")
