"""C1_ACCEPT_CALIBER CPU 单测（C1③④ 判读侧计算器开发批；0 靴，2026-10-24）.

法源: 032-MASTER-TASKLIST C1 行（EV-07-007：③记录级补采/④DSPARK σ 采样）;
      任务书 §T33-03 验收（恒等式/闭合）; W4 §5.6 C1④ 数据基座行;
      W5 §5（D17 容差 |raw-visible|<=60+n·k、Σ窗=cum、转移窗/稳态窗分解）;
      033-W1/SCHED-STATS-IF-ERRATA-20261024.md（spec 三列结构性空载口径）.
被测件: tools/obs/c1_accept_caliber.py。
真实数据基座（skipif 门控）: W4 913 窗 TP0 面（md5 pin ad740fffd4eca6c0f400a17d27455593）。
不 import sglang/torch/GPU；单次 <60s。运行:
  /tmp/w0venv/bin/python -m pytest -q tests/unit/test_c1_accept_caliber.py -o cache_dir=/tmp/w0cache
"""

import importlib.util
import json
import math
import os
import subprocess
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(REPO, "tools", "obs", "c1_accept_caliber.py")
REAL_DATA = "/home/liuxiaoya/luz030-opt-campaign/logs/S-W4-20261024/bench/sched-stats-tp0-lines.txt"
REAL_MD5 = "ad740fffd4eca6c0f400a17d27455593"

_spec = importlib.util.spec_from_file_location("c1_accept_caliber", MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def rec(win, gen, bs, p_steps=0, gamma=5, spec=0, tot=None, tw=None):
    acc = gen - bs
    ver = gamma * bs if gamma > 0 else None
    r = {
        "schema": "sched-stats-v1", "gamma": gamma, "win_steps": win,
        "p_steps": p_steps, "d_steps": win - p_steps,
        "d_gen_tokens": gen, "d_batch_sum": bs, "d_accepted": acc,
        "d_verified": ver, "d_accept_len": (gen / bs) if bs else None,
        "d_accept_rate": (acc / ver) if (ver and spec > 0) else None,
        "d_accept_base": "all" if spec == 0 else "spec",
        "d_spec_steps": spec, "ident_ok": acc >= 0,
        "kv_usage_pct": 99.0, "kv_free": 10000, "emit_fail_tot": 0,
    }
    if tw is not None:
        r["tot_windows"] = tw
        r["tot_d_gen_tokens"] = tot
    return r


# ---- 提取器 -------------------------------------------------------------------
def test_extract_records_prefix_and_malformed():
    text = (
        "[2026-10-24 02:34:52 TP0] SCHED_STATS_V1 "
        + json.dumps(rec(4, 8, 4)) + "\n"
        "[2026-10-24 02:35:00 TP3] SCHED_STATS_V1 "
        + json.dumps(rec(4, 8, 4)) + "\n"
        "SCHED_STATS_V1 not-json\n"
        "SCHED_STATS_V1 {\"schema\":\"other\"}\n"
        "irrelevant line\n"
    )
    recs, st = m.extract_records(text)
    assert len(recs) == 2 and st["malformed"] == 2
    assert recs[0]["_log_prefix_tp"] == 0 and recs[1]["_log_prefix_tp"] == 3
    assert st["prefix_groups"] == {"0": 1, "3": 1}


def test_extract_real_w4_line_form():
    line = ('[2026-10-24 02:34:52 TP0] SCHED_STATS_V1 {"schema":"sched-stats-v1",'
            '"gamma":6,"d_accept_len":2.0,"d_accept_rate":null,'
            '"d_accept_base":"all","d_spec_steps":0}')
    recs, _ = m.extract_records(line)
    assert len(recs) == 1 and recs[0]["gamma"] == 6
    assert recs[0]["d_accept_rate"] is None


# ---- summarize（C1③④ 指标）---------------------------------------------------
def test_summarize_accept_face_and_derived_rate():
    rs = [rec(4, 8, 4, gamma=6), rec(4, 8, 4, gamma=6), rec(4, 16, 4, gamma=6)]
    s = m.summarize(rs, gamma=5)
    assert s["n_records"] == 3 and s["n_decode_windows"] == 3
    assert abs(s["accept_face"]["mean"] - (2.0 * 2 + 4.0) / 3) < 1e-9
    # 派生 rate=(alen-1)/γ：0.2/0.2/0.6 → mean 1/3
    dr = s["derived_accept_rate_face_c1_4"]
    assert dr["n"] == 3 and abs(dr["mean"] - (0.2 + 0.2 + 0.6) / 3) < 1e-9
    assert dr["gammas_used"] == [5]
    assert "不作验收线" in dr["note"]
    assert s["gamma_caliber"] == "override gamma=5"


def test_summarize_sigma_math():
    rs = [rec(4, 8, 4), rec(4, 16, 4), rec(4, 24, 4)]  # alen 2,4,6
    s = m.summarize(rs)
    mean = 4.0
    var_p = ((2 - mean) ** 2 + 0 + (6 - mean) ** 2) / 3
    assert abs(s["accept_face"]["sigma_population"] - math.sqrt(var_p)) < 1e-9
    assert abs(s["accept_face"]["sigma_sample"]
               - math.sqrt(var_p * 3 / 2)) < 1e-9
    assert s["accept_face"]["p50"] == 4.0 and s["accept_face"]["min"] == 2.0
    assert s["accept_face"]["max"] == 6.0


def test_summarize_spec_structural_null_declared():
    s = m.summarize([rec(4, 8, 4), rec(4, 8, 4, spec=0)])
    assert s["spec_subset"].startswith("structurally-null")
    assert "SCHED-STATS-IF-ERRATA" in s["spec_subset"]
    s2 = m.summarize([rec(4, 8, 4, spec=4)])
    assert s2["spec_subset"] == "present"


def test_summarize_window_class_split():
    rs = [rec(4, 16, 4, p_steps=1), rec(4, 8, 4, p_steps=0)]
    s = m.summarize(rs)
    wc = s["window_class_split"]
    assert wc["transition_windows(p_steps>0)"] == 1
    assert wc["transition_gen_per_step"] == 4.0
    assert wc["steady_windows"] == 1 and wc["steady_gen_per_step"] == 2.0


def test_summarize_warm_state_exclusion():
    rs = [rec(4, 8, 4), rec(4, 16, 4)]
    for i, r in enumerate(rs):
        r["tot_windows"] = i + 1
        r["tot_d_gen_tokens"] = 0
    s = m.summarize(rs, warm_after_window=1)
    assert s["warm_state"]["windows_excluded"] == 1
    assert s["warm_state"]["windows_in_sigma_face"] == 1
    # 只剩 alen=4.0 → σ=0
    assert s["sigma_face_c1_4"] == 0.0
    s2 = m.summarize(rs)
    assert s2["warm_state"]["warm_after_window"] is None


def test_summarize_totals_closure():
    rs = [rec(4, 8, 4, tot=8, tw=1), rec(4, 8, 4, tot=16, tw=2)]
    s = m.summarize(rs)
    assert s["totals_closure"]["equal"] is True
    rs2 = [rec(4, 8, 4, tot=8, tw=1), rec(4, 8, 4, tot=17, tw=2)]
    s2 = m.summarize(rs2)
    assert s2["totals_closure"]["equal"] is False


def test_summarize_ident_and_gamma_distinct():
    bad = rec(4, 8, 4)
    bad["ident_ok"] = False
    s = m.summarize([rec(4, 8, 4, gamma=6), bad])
    assert s["ident_ok_false_count"] == 1
    assert s["gamma_distinct"] == [5, 6]
    assert s["emit_fail_tot_max"] == 0


def test_summarize_caliber_note_carries_errata_pointer():
    s = m.summarize([rec(4, 8, 4)])
    assert "SCHED-STATS-IF-ERRATA-20261024" in s["caliber"]


# ---- closure_check（D17 容差）-------------------------------------------------
def test_closure_w5_live_values_in_band():
    c = m.closure_check(24231, 23940, 60)  # W5 §5 实测复算
    assert c["diff_raw_minus_visible"] == 291
    assert c["band"] == pytest.approx(60 + 60 * 6.15)
    assert c["band_ok"] is True
    assert c["k_measured_per_req"] == pytest.approx(291 / 60)


def test_closure_w4_old_tolerance_red():
    c = m.closure_check(24309, 23940, 60, k=0, base=60)  # W4 +369 vs 旧 ±60
    assert c["diff_raw_minus_visible"] == 369
    assert c["band_ok"] is False


def test_closure_zero_client_guard():
    c = m.closure_check(100, 0, 10)
    assert c["diff_pct"] is None  # 客户端 0 → 百分比不可算
    assert c["band_ok"] is True   # 带宽算术照常（|100|<=60+10*6.15）
    c2 = m.closure_check(100, 0, 10, k=0, base=0)
    assert c2["band_ok"] is False


# ---- 真实 913 窗数据基座复算（skipif 门控 + md5 pin）--------------------------
def _real_ok():
    if not os.path.isfile(REAL_DATA):
        return False
    import hashlib
    h = hashlib.md5()
    with open(REAL_DATA, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() == REAL_MD5


@pytest.mark.skipif(not _real_ok(), reason="W4 913 窗数据基座不在档或 md5 不符")
def test_real_913_window_replay_w4_face():
    text = open(REAL_DATA, encoding="utf-8").read()
    recs, st = m.extract_records(text)
    assert st["malformed"] == 0 and len(recs) == 913
    # W4 旧接线面：gamma 字段=6（verify 长度）、spec 三列全空、ident 全真。
    s = m.summarize(recs, gamma=5)
    assert s["n_decode_windows"] == 900
    assert s["gamma_distinct"] == [6]
    assert s["ident_ok_false_count"] == 0
    assert s["spec_subset"].startswith("structurally-null")
    af = s["accept_face"]
    assert af["n"] == 900 and af["mean"] == pytest.approx(3.156, abs=0.01)
    assert af["sigma_population"] == pytest.approx(0.304, abs=0.01)
    dr = s["derived_accept_rate_face_c1_4"]
    assert dr["n"] == 900 and dr["mean"] == pytest.approx(0.431, abs=0.01)
    wc = s["window_class_split"]
    assert wc["transition_windows(p_steps>0)"] == 219
    assert wc["steady_windows"] == 681
    assert s["totals_closure"]["equal"] is True


# ---- CLI / selfcheck ----------------------------------------------------------
def test_canonical_selfcheck():
    r = subprocess.run([sys.executable, MODULE_PATH, "--selfcheck"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SELFCHK C1_ACCEPT_CALIBER ok" in r.stdout


def test_cli_closure():
    r = subprocess.run(
        [sys.executable, MODULE_PATH, "closure", "--engine-total", "24231",
         "--client-total", "23940", "--n-req", "60"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["diff_raw_minus_visible"] == 291


def test_cli_summarize_synthetic(tmp_path):
    p = tmp_path / "lines.txt"
    p.write_text("SCHED_STATS_V1 " + json.dumps(rec(4, 8, 4, gamma=6)) + "\n",
                 encoding="utf-8")
    r = subprocess.run(
        [sys.executable, MODULE_PATH, "summarize", str(p), "--gamma", "5"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["n_records"] == 1 and out["gamma_caliber"] == "override gamma=5"
