"""KV_RECALL_C11 CPU 单测（C11 量具开发批；0 靴，mock 数据驱动，2026-10-24）.

法源: 033-TASKBOOK-V2-20261023.md :1310（C11 召回量具）/§T33-08 验收门（F6-A）;
      032-MASTER-TASKLIST C11/C12 行（EV-07-007）; INV-07 §4.4/§4.6;
      032-ADDENDUM-NETWORK-20261015.md C11/F6 行（EV-07-028，负表#15）.
被测件: tools/obs/kv_recall_c11.py（canonical 判读量具）。
不 import sglang/torch/GPU；单次 <60s。运行:
  /tmp/w0venv/bin/python -m pytest -q tests/unit/test_kv_recall_c11.py -o cache_dir=/tmp/w0cache
"""

import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(REPO, "tools", "obs", "kv_recall_c11.py")

_spec = importlib.util.spec_from_file_location("kv_recall_c11", MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def sha(key, value):
    return m.record_key_sha256(key, value)


def green_bundle(**overrides):
    """112/112 全绿合成 bundle（可选注入负对照）。"""
    records = []
    for s in range(16):
        for i, t in enumerate((1, 10, 25, 50, 75, 90, 99)):
            exp = sha(f"k{s}-{i}", f"value-{s}-{i}".encode())
            records.append({
                "stream": s, "position": i, "depth_target_pct": t,
                "key_hash": f"k{s}-{i}", "expected_sha256": exp,
                "got_sha256": exp,
                "backing_sample": {"bytes": 1024, "sha256": exp},
                "session_epoch": 1,
            })
    barriers = []
    for phase in ("before", "plateau", "after-query", "closed"):
        for rank in range(4):
            barriers.append({
                "phase": phase, "rank": rank,
                "kv_used": 9504000, "kv_total": 9600000,
                "swa_free": 3328, "swa_total": 125440,
                "evictable": 113920, "protected": 4096,
                "session_tail": 4096, "full_committed_tokens": 9551288,
                "full_pages": 37312,
                "slots_after_close": 0 if phase == "closed" else None,
                "request_rows_after_close": 16,
            })
    rebuilds = [{
        "rank": r, "page_seq_sha256": sha("page-seq", f"rank{r}".encode()),
        "pages_full": 37312, "alias_conflicts": 0, "free_list_conflicts": 0,
        "sha_match_expected": True,
    } for r in range(4)]
    notes = {
        "arm_tag": "F6A-UNIT",
        "streaming_caliber": "streaming-session off（本窗未启用，负表#15 声明）",
        "control_plane_fingerprints": {"ignite.sh": "md5:a"},
        "run_module_fingerprints": {"scheduler.py": "md5:b"},
        "water_watch": {"min_memavailable_mb": 6000, "stops": 0},
    }
    boot = {
        "server_info": {"max_total_num_tokens": 9600000,
                        "max_running_requests": 16, "context_length": 600000},
        "expected": {"max_total_num_tokens": 9600000,
                     "max_running_requests": 16, "context_length": 600000},
    }
    bundle = {
        "recall_records": records, "barriers": barriers,
        "page_rebuilds": rebuilds, "attempt_notes": notes,
        "boot_expectations": boot,
    }
    for k, v in overrides.items():
        if v is None:
            bundle.pop(k, None)
        else:
            bundle[k] = v
    return bundle


def failed_keys(items):
    return [k for k, v, _ in items if not v]


# ---- 全绿走查 ----------------------------------------------------------------
def test_green_bundle_all_pass():
    ok, items, summary = m.judge_bundle(green_bundle())
    assert ok, failed_keys(items)
    assert summary["total_checks"] >= 20
    assert "external_baseline_e4_reference_only" in summary
    assert summary["external_baseline_e4_reference_only"]["recall"] == "112/112"


def test_counts_and_constants():
    assert m.TOTAL_RECORDS == 112 and m.N_STREAMS == 16
    assert m.DEPTH_TARGETS == (1, 10, 25, 50, 75, 90, 99)
    assert len(m.BARRIER_PHASES) == 4
    assert m.SIGNING_POOL_PCT == 99.0
    assert m.BACKING_SAMPLE_MAX_BYTES == 1024


# ---- 召回面负对照 -------------------------------------------------------------
def test_recall_miss_detected():
    b = green_bundle()
    b["recall_records"][56]["got_sha256"] = sha("zzz", b"absent")
    ok, items, _ = m.judge_bundle(b)
    assert not ok and "recall.hits" in failed_keys(items)


def test_cross_session_bleed_detected():
    b = green_bundle()
    # 同 key 跨 session epoch 异值：epoch2 召回拿回 epoch1 的值 = 串值。
    pair = [r for r in b["recall_records"] if r["stream"] == 1][:2]
    key = "ksplit"
    e1, e2 = sha(key, b"session-one"), sha(key, b"session-two")
    pair[0].update({"key_hash": key, "expected_sha256": e1,
                    "got_sha256": e1, "session_epoch": 1})
    pair[1].update({"key_hash": key, "expected_sha256": e2,
                    "got_sha256": e1, "session_epoch": 2})
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any("bleed" in k for k in failed_keys(items))


def test_backing_sample_oversize_detected():
    b = green_bundle()
    b["recall_records"][0]["backing_sample"]["bytes"] = 2048
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any("backing-sample" in k for k in failed_keys(items))


def test_missing_depth_target_detected():
    b = green_bundle()
    b["recall_records"] = [r for r in b["recall_records"]
                           if r["depth_target_pct"] != 99]
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any("position16/16@depth99" in k for k in failed_keys(items))
    assert "recall.count==112" in failed_keys(items)


# ---- 屏障面负对照 -------------------------------------------------------------
def test_barrier_phase_missing_detected():
    b = green_bundle()
    b["barriers"] = [s for s in b["barriers"] if s["phase"] != "plateau"]
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    fk = failed_keys(items)
    assert any(k.startswith("barrier.4phase") for k in fk)
    assert any("pool>=" in k for k in fk)


def test_barrier_pool_below_signing_detected():
    b = green_bundle()
    for s in b["barriers"]:
        if s["phase"] == "plateau":
            s["kv_used"] = 8640000  # 90% < 99% 签收线
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any("pool>=" in k for k in failed_keys(items))


def test_barrier_closed_slot_not_zero_detected():
    b = green_bundle()
    for s in b["barriers"]:
        if s["phase"] == "closed":
            s["slots_after_close"] = 3
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert "barrier.closed-slot-zero" in failed_keys(items)


# ---- 页重建面负对照 -----------------------------------------------------------
def test_page_rebuild_sha_drift_detected():
    b = green_bundle()
    b["page_rebuilds"][2]["sha_match_expected"] = False
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert "pages.sha-match" in failed_keys(items)


def test_page_rebuild_alias_conflict_detected():
    b = green_bundle()
    b["page_rebuilds"][1]["alias_conflicts"] = 2
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert "pages.zero-alias-conflicts" in failed_keys(items)


def test_page_rebuild_cross_rank_inequal_detected():
    b = green_bundle()
    b["page_rebuilds"][3]["pages_full"] = 37311
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert "pages.full-pages-cross-rank-equal" in failed_keys(items)


# ---- attempt-notes / 负表#15 / C12 三期望 -------------------------------------
def test_streaming_caliber_declaration_hard_gate():
    b = green_bundle()
    del b["attempt_notes"]["streaming_caliber"]
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any("streaming-caliber" in k for k in failed_keys(items))


def test_fingerprint_split_gate():
    b = green_bundle()
    del b["attempt_notes"]["control_plane_fingerprints"]
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any("fingerprint-split" in k for k in failed_keys(items))


def test_water_watch_stop_gate():
    b = green_bundle()
    b["attempt_notes"]["water_watch"]["stops"] = 1
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert "notes.water-watch-no-stop" in failed_keys(items)


def test_boot_expectations_mismatch_detected():
    b = green_bundle()
    b["boot_expectations"]["server_info"]["max_running_requests"] = 8
    ok, items, _ = m.judge_bundle(b)
    assert not ok
    assert any(k.startswith("boot.mrr==") for k in failed_keys(items))


def test_missing_attempt_notes_fails():
    ok, items, _ = m.judge_bundle(green_bundle(attempt_notes=None))
    assert not ok and "notes.present" in failed_keys(items)


def test_non_dict_bundle_fails_cleanly():
    ok, items, _ = m.judge_bundle([1, 2])
    assert not ok and failed_keys(items) == ["bundle.present"]


# ---- CLI / selfcheck ----------------------------------------------------------
def test_canonical_selfcheck():
    r = subprocess.run([sys.executable, MODULE_PATH, "--selfcheck"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SELFCHK KV_RECALL_C11 ok" in r.stdout


def test_judge_cli_green_bundle(tmp_path):
    p = tmp_path / "bundle.json"
    p.write_text(json.dumps(green_bundle(), ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, MODULE_PATH, "judge", str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "GREEN" in r.stdout
