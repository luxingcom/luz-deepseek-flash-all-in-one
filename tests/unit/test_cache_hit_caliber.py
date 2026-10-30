"""cache_hit_caliber CPU 单测（UPSTREAM-45119 监控侧规避件；0 靖，mock 数据驱动，2026-10-30）.

法源: 上游 sgl-project/sglang issue #45119（sglang:cache_hit_rate gauge 空/无命中
      prefill 报告发布 0.0）+ 修复 PR #45122（open 未合，仅 total_tokens==0 跳写守卫）；
      在役镜像 /metrics 实测快照（计数器健康+gauge 归零同页）= 缺陷签名直证。
被测件: tools/obs/cache_hit_caliber.py（canonical；战役仓 tools/obs/ 同件双面）。
性质: 纯 stdlib；不 import sglang/torch/GPU/prometheus、零网络、零引擎接触；单次 <10s。
运行（仓根）: python3 tests/unit/test_cache_hit_caliber.py
      或 pytest -q tests/unit/test_cache_hit_caliber.py（tests 非包，勿用 -m unittest 点路径）
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(REPO, "tools", "obs", "cache_hit_caliber.py")

_spec = importlib.util.spec_from_file_location("cache_hit_caliber", MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

# 在役引擎 /metrics 实测数（2026-10-29 快照，缺陷签名现势铁证）
LIVE_INPUT = 1.068429e+07
LIVE_DEVICE_HIT = 910336.0
LIVE_RATE = LIVE_DEVICE_HIT / (LIVE_INPUT + LIVE_DEVICE_HIT)


def snap(input_tok, hit_tok, gauge):
    return m.parse_prom_text(
        "sglang:prefill_effective_tokens_total{mode=\"input\"} %r\n"
        "sglang:prefill_effective_tokens_total{mode=\"device_hit\"} %r\n"
        "sglang:cache_hit_rate{tp_rank=\"0\"} %r\n" % (input_tok, hit_tok, gauge))


class TestParser(unittest.TestCase):
    def test_help_type_lines_skipped_and_labels_kept(self):
        fam = m.parse_prom_text(
            "# HELP sglang:cache_hit_rate The prefix cache hit rate.\n"
            "# TYPE sglang:cache_hit_rate gauge\n"
            "sglang:cache_hit_rate{tp_rank=\"1\"} 0.5\n"
            "\n")
        self.assertEqual(fam, {"sglang:cache_hit_rate": [({"tp_rank": "1"}, 0.5)]})

    def test_braceless_line_family_name(self):
        fam = m.parse_prom_text("sglang:cache_hit_rate 0.25\n")
        self.assertIn("sglang:cache_hit_rate", fam)

    def test_bad_value_line_skipped_not_raised(self):
        fam = m.parse_prom_text("sglang:cache_hit_rate oops\n")
        self.assertEqual(fam, {})


class TestCounterCaliber(unittest.TestCase):
    def test_live_replay_single_snapshot_cumulative(self):
        v = m.judge([snap(LIVE_INPUT, LIVE_DEVICE_HIT, 0.0)])
        self.assertEqual(v["caliber"], "counter-cumulative/prefill_effective")
        self.assertIsNotNone(v["hit_rate"])
        self.assertAlmostEqual(v["hit_rate"], LIVE_RATE, places=4)
        self.assertTrue(v["defect_signature"])
        self.assertEqual(v["gauge_raw_last"], 0.0)

    def test_windowed_two_snapshots(self):
        v = m.judge([snap(900000, 100000, 0.9576), snap(1000000, 120000, 0.0)])
        self.assertEqual(v["caliber"], "counter-windowed/prefill_effective")
        self.assertAlmostEqual(v["hit_rate"], 20000.0 / 120000.0, places=6)
        self.assertEqual(v["total_tokens"], 120000)
        self.assertEqual(v["gauge_filtered_last"], 0.9576)
        self.assertEqual(v["gauge_zero_samples_dropped"], 1)
        self.assertTrue(v["defect_signature"])

    def test_counter_reset_falls_back_cumulative(self):
        v = m.judge([snap(1000000, 120000, 0.0), snap(900000, 100000, 0.9)])
        self.assertEqual(v["caliber"], "counter-cumulative/prefill_effective")
        self.assertTrue(any("reset" in n for n in v["notes"]))

    def test_fallback_family(self):
        fam = m.parse_prom_text(
            "sglang:cached_tokens_total{cache_source=\"device\"} 4000\n"
            "sglang:cached_tokens_total{cache_source=\"host\"} 1000\n"
            "sglang:prompt_tokens_total{tp_rank=\"0\"} 10000\n")
        v = m.judge([fam])
        self.assertEqual(v["caliber"], "counter-cumulative/cached_over_prompt")
        self.assertEqual(v["hits_tokens"], 5000)
        self.assertAlmostEqual(v["hit_rate"], 0.5, places=6)

    def test_insufficient_traffic(self):
        v = m.judge([snap(40, 10, 0.2)])
        self.assertIsNone(v["hit_rate"])
        self.assertTrue(any("insufficient_traffic" in n for n in v["notes"]))

    def test_min_traffic_env_contract(self):
        v = m.judge([snap(40, 10, 0.2)], min_traffic=50)
        self.assertAlmostEqual(v["hit_rate"], 0.2, places=6)


class TestGaugeFilter(unittest.TestCase):
    def test_keep_last_valid_and_count_dropped(self):
        kept, dropped = m.filter_gauge_series([0.96, 0.0, 0.0, 0.95])
        self.assertEqual(kept, 0.95)
        self.assertEqual(dropped, 2)

    def test_all_zero_series_has_no_readout(self):
        self.assertEqual(m.filter_gauge_series([0.0, 0.0]), (None, 2))

    def test_gauge_only_downgrade_note(self):
        v = m.judge([m.parse_prom_text("sglang:cache_hit_rate 0.31\n"),
                     m.parse_prom_text("sglang:cache_hit_rate 0.0\n")])
        self.assertEqual(v["caliber"], "gauge-filtered-only")
        self.assertEqual(v["hit_rate"], 0.31)
        self.assertTrue(any("fallback" in n for n in v["notes"]))


class TestLintFace(unittest.TestCase):
    def test_bare_read_refused_and_waiver_passes(self):
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "bad_tool.py")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("rate = float(row['sglang:cache_hit_rate'])\n")
            ok = os.path.join(td, "ok_tool.py")
            with open(ok, "w", encoding="utf-8") as f:
                f.write("MET_KEYS = (\"cache_hit_rate\",)  # cache-hit-caliber: raw-snapshot\n")
            viol, files = m.lint_paths([td])
            self.assertEqual(len(files), 2)
            self.assertEqual(len(viol), 1)
            self.assertEqual(viol[0][0], bad)

    def test_recent_cache_hit_rate_identifier_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "win_tool.py")
            with open(p, "w", encoding="utf-8") as f:
                f.write("v = scheduler.recent_cache_hit_rate\n")
            viol, _ = m.lint_paths([td])
            self.assertEqual(viol, [])

    def test_repo_tools_and_deploy_clean(self):
        viol, _ = m.lint_paths([os.path.join(REPO, "tools"), os.path.join(REPO, "deploy")])
        self.assertEqual(viol, [])

    def test_module_self_dir_clean(self):
        viol, _ = m.lint_paths([os.path.dirname(MODULE_PATH)])
        self.assertEqual(viol, [])


class TestSelfcheckCLI(unittest.TestCase):
    def test_selfcheck_subprocess_exit_zero(self):
        r = subprocess.run([sys.executable, MODULE_PATH, "--selfcheck"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("13/13 checks PASS", r.stdout)

    def test_lint_subprocess_exit_zero_on_repo(self):
        r = subprocess.run([sys.executable, MODULE_PATH, "--lint",
                            os.path.join(REPO, "tools")],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("[lint] PASS", r.stdout)

    def test_cli_json_verdict_on_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "metrics.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("sglang:prefill_effective_tokens_total{mode=\"input\"} %r\n"
                        "sglang:prefill_effective_tokens_total{mode=\"device_hit\"} %r\n"
                        "sglang:cache_hit_rate 0.0\n" % (LIVE_INPUT, LIVE_DEVICE_HIT))
            r = subprocess.run([sys.executable, MODULE_PATH, "--metrics-file", p],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('"defect_signature": true', r.stdout)
            self.assertIn('"counter-cumulative/prefill_effective"', r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
