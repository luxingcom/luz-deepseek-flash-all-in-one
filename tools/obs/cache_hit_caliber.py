#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cache_hit_caliber — sglang:cache_hit_rate gauge 归零缺陷的 host 侧监控规避件（UPSTREAM-45119）。

缺陷与法源
  * 上游缺陷：sgl-project/sglang issue #45119——`sglang:cache_hit_rate` gauge 在
    空/无命中 prefill 报告时发布 0.0，健康缓存（真实 ~0.96）在 Grafana 上来回跳 0。
    修复 PR #45122（open，未合）只做窄修：`total_tokens==0` 时跳过 gauge 写、保留
    最后有效值；与本仓早前 decode 路径修复（#12459/PR #24427）不同源。
  * 引擎内缺陷位（在役镜像树实读，本件只读不改镜像）：
    `sglang/srt/managers/scheduler_components/metrics_reporter.py` report_prefill_stats
    内 `cache_hit_rate = effective_hit/total if total>0 else 0.0` 后
    `self.stats.cache_hit_rate = cache_hit_rate` 直发 gauge；
    `sglang/srt/observability/metrics_collector.py` `Gauge(name="sglang:cache_hit_rate")`
    经 log_stats 每报告发布。
  * 在役实测铁证（2026-10-29 引擎 /metrics 快照）：同页
    `sglang:prefill_effective_tokens_total{mode="input"}=1.068429e+07` 与
    `{mode="device_hit"}=910336`（计数器证明有真实流量与命中）而
    `sglang:cache_hit_rate = 0.0`——缺陷签名现势在档。

规避口径（正典，与镜像内计数器 HELP 自述一致）
  1. **主口径（计数器）**：`sglang:prefill_effective_tokens_total` 族
     （mode=input/device_hit/host_hit/storage_hit；该族 HELP 原文即
     "Windowed prefix cache hit rate = rate(sum of *_hit) / rate(sum of all modes)"）：
     hits = Σ(*_hit)，total = hits + input；两快照取窗（Δhits/Δtotal，Prometheus
     rate 的离散等价），单快照取累计比。计数器回绕/重启（Δ≤0）自动降级累计比并注记。
  2. **备用口径**：`sglang:cached_tokens_total` / `sglang:prompt_tokens_total`
     （主口径族缺位时；--enable-cache-report 面的 API 侧计数）。
  3. **gauge 兜底（!= 0 过滤）**：`sglang:cache_hit_rate` gauge 样本 0.0 一律
     视为缺陷伪值丢弃、保留最后非零值（issue 建议的过滤法）。注意：真 0% 冷缓存
     命中会被该过滤误持旧值——故 gauge 兜底只在计数器全缺位时使用，且 verdict
     恒同时给出 gauge 原始值与过滤值，判读以计数器口径为准。

工具面（env 旋钮，host 侧本件自用，不进引擎 env 面）
  * `CACHE_HIT_CALIBER_MIN_TRAFFIC`（缺省 1000）：窗口/累计 total 低于该 token 数
    时 hit_rate 置 None 并注记 insufficient_traffic（防小样本伪率）。

lint 面（守卫）
  * `--lint <路径…>`（.py/.sh；目录递归，跳 __pycache__）：扫裸 `cache_hit_rate` /
    `sglang:cache_hit_rate` 消费行；同行带 `# cache-hit-caliber:` 豁免标记（裸快照
    记录用）或文件内引用本件（cache_hit_caliber）即过。出口 0=过门 1=REFUSE 2=用法错
    （同 env-lint 制式）。防新增工具裸读 gauge 判据。

自测：python3 tools/obs/cache_hit_caliber.py --selfcheck（离线、零网络、零引擎接触；
内嵌缺陷重放=计数器健康+gauge 归零必判 defect_signature=True）。

双面律：本件在公开面（tools/obs/）与战役仓正典面（tools/obs/）逐字节同件；
锚点登记=战役仓 docs/TOOL-ANCHORS.md。改件须双面同批同改并重钉锚。
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request

GAUGE_FAMILY = "sglang:cache_hit_rate"
COUNTER_FAMILY = "sglang:prefill_effective_tokens_total"
FALLBACK_HIT_FAMILY = "sglang:cached_tokens_total"
FALLBACK_TOTAL_FAMILY = "sglang:prompt_tokens_total"
HIT_MODES = ("device_hit", "host_hit", "storage_hit")
INPUT_MODE = "input"
WAIVER_MARK = "cache-hit-caliber:"
MODULE_MARK = "cache_hit_caliber"
LINT_SUFFIXES = (".py", ".sh")
DEFAULT_MIN_TRAFFIC = 1000

_BARE_TOKEN = re.compile(r"(?<![A-Za-z0-9_:])cache_hit_rate(?![A-Za-z0-9_])")


# ---------------- Prometheus exposition 解析 ----------------

def parse_prom_text(text):
    """解析 Prometheus exposition 文本 → {family: [({"label": v, …}, value), …]}。

    跳过 # HELP/# TYPE 与空行；值取行尾首浮点（忽略可选时间戳）；坏行跳过不抛
    （metrics 面损坏不崩判读，与 SCHED_STATS_V1 红线同律）。
    """
    families = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, labels, rest = line, {}, None
        if "{" in line:
            head, _, tail = line.partition("{")
            name = head.strip()
            lbl_text, _, rest = tail.partition("}")
            for kv in re.findall(r'([A-Za-z_][A-Za-z0-9_]*)="((?:[^"\\]|\\.)*)"', lbl_text):
                labels[kv[0]] = kv[1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        else:
            name, _, rest = line.partition(" ")
            name = name.strip()
        fields = (rest or "").split()
        if not fields:
            continue
        try:
            value = float(fields[0])
        except ValueError:
            continue
        families.setdefault(name, []).append((labels, value))
    return families


def _sum_family(families, name, modes=None):
    """族内求和；modes 给定时按 label mode 过滤（无 mode 标签的行不计入过滤和）。"""
    if name not in families:
        return None
    total = 0.0
    for labels, value in families[name]:
        if modes is None:
            total += value
        elif labels.get("mode") in modes:
            total += value
    return total


def counter_totals(families):
    """(hits, total, caliber) —— 主口径优先，备用口径次之；全缺位返回 (None, None, None)。"""
    if COUNTER_FAMILY in families:
        hits = _sum_family(families, COUNTER_FAMILY, HIT_MODES) or 0.0
        inputs = _sum_family(families, COUNTER_FAMILY, (INPUT_MODE,)) or 0.0
        return hits, hits + inputs, "prefill_effective"
    if FALLBACK_HIT_FAMILY in families and FALLBACK_TOTAL_FAMILY in families:
        hits = _sum_family(families, FALLBACK_HIT_FAMILY) or 0.0
        total = _sum_family(families, FALLBACK_TOTAL_FAMILY) or 0.0
        return hits, total, "cached_over_prompt"
    return None, None, None


# ---------------- gauge != 0 过滤（issue 建议的兜底） ----------------

def filter_gauge_series(values):
    """gauge 样本序列的 != 0 过滤：返回 (最后有效值或 None, 丢弃的 0.0 样本数)。"""
    dropped = sum(1 for v in values if v == 0.0)
    kept = [v for v in values if v != 0.0]
    return (kept[-1] if kept else None), dropped


# ---------------- 判读 ----------------

def judge(snapshot_list, min_traffic=None):
    """多快照判读 → verdict dict（稳定 JSON 契约，见模块头）。

    snapshot_list=[families_dict, …]（parse_prom_text 产物，时序升序）。
    """
    min_traffic = DEFAULT_MIN_TRAFFIC if min_traffic is None else min_traffic
    notes = []
    verdict = {
        "ts": round(time.time(), 1),
        "n_snapshots": len(snapshot_list),
        "caliber": None,
        "hit_rate": None,
        "hits_tokens": None,
        "total_tokens": None,
        "gauge_raw_last": None,
        "gauge_filtered_last": None,
        "gauge_zero_samples_dropped": 0,
        "defect_signature": False,
        "min_traffic": min_traffic,
        "notes": notes,
    }
    if not snapshot_list:
        notes.append("no snapshots")
        return verdict

    gauge_series = []
    for fam in snapshot_list:
        rows = fam.get(GAUGE_FAMILY) or []
        gauge_series.append(rows[-1][1] if rows else None)
    raw_gauges = [v for v in gauge_series if v is not None]
    if raw_gauges:
        verdict["gauge_raw_last"] = raw_gauges[-1]
        filtered, dropped = filter_gauge_series(raw_gauges)
        verdict["gauge_filtered_last"] = filtered
        verdict["gauge_zero_samples_dropped"] = dropped

    totals = [counter_totals(fam) for fam in snapshot_list]
    hits_first, total_first, fam_name = totals[0]
    hits_last, total_last, _ = totals[-1]

    if fam_name is None:
        verdict["caliber"] = "gauge-filtered-only"
        if verdict["gauge_filtered_last"] is not None:
            verdict["hit_rate"] = verdict["gauge_filtered_last"]
            notes.append("counter families absent; gauge !=0 filter fallback "
                         "(true-0% cold cache would be held stale — caliber downgrade)")
        else:
            notes.append("counter families absent and gauge empty; no readout")
    else:
        verdict["hits_tokens"] = int(hits_last)
        verdict["total_tokens"] = int(total_last)
        windowed = len(totals) >= 2
        if windowed and (total_last - total_first) > 0 and hits_last >= hits_first:
            hits_delta = hits_last - hits_first
            total_delta = total_last - total_first
            verdict["caliber"] = "counter-windowed/" + fam_name
            if total_delta >= min_traffic:
                verdict["hit_rate"] = round(hits_delta / total_delta, 6)
                verdict["hits_tokens"] = int(hits_delta)
                verdict["total_tokens"] = int(total_delta)
            else:
                notes.append("insufficient_traffic: window total %d < %d" % (total_delta, min_traffic))
        else:
            if windowed and hits_last < hits_first:
                notes.append("counter reset/restart detected (hits decreased); "
                             "fell back to cumulative caliber")
            verdict["caliber"] = "counter-cumulative/" + fam_name
            if total_last >= min_traffic:
                verdict["hit_rate"] = round(hits_last / total_last, 6) if total_last > 0 else None
            else:
                notes.append("insufficient_traffic: cumulative total %d < %d" % (total_last, min_traffic))

    # 缺陷签名：gauge 归零（或被过滤丢过 0.0）而计数器口径有真实流量
    has_traffic = verdict["total_tokens"] is not None and verdict["total_tokens"] > 0
    if has_traffic and (verdict["gauge_raw_last"] == 0.0
                        or verdict["gauge_zero_samples_dropped"] > 0):
        verdict["defect_signature"] = True
        notes.append("upstream #45119 signature: gauge published 0.0 while counters "
                     "carried real traffic; read hit_rate from the counter caliber")
    return verdict


# ---------------- 采集 ----------------

def fetch_url(url, timeout=10):
    with urllib.request.urlopen(url.rstrip("/") + "/metrics", timeout=timeout) as r:
        return parse_prom_text(r.read().decode("utf-8", "replace"))


def load_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_prom_text(f.read())


# ---------------- lint 面（守卫：禁裸读 gauge 判据） ----------------

def lint_paths(paths):
    """返回 (violations, scanned_files)：violations=[(path, lineno, line), …]。"""
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for n in names:
                    if n.endswith(LINT_SUFFIXES):
                        files.append(os.path.join(root, n))
        elif p.endswith(LINT_SUFFIXES) and os.path.isfile(p):
            files.append(p)
    violations = []
    for path in sorted(set(files)):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        file_mitigated = MODULE_MARK in content
        for i, line in enumerate(content.splitlines(), 1):
            if _BARE_TOKEN.search(line) or GAUGE_FAMILY in line:
                if WAIVER_MARK in line or file_mitigated:
                    continue
                violations.append((path, i, line.strip()))
    return violations, sorted(set(files))


# ---------------- selfcheck（离线自证） ----------------

_LIVE_SNAPSHOT = """\
# HELP sglang:prefill_effective_tokens_total Effective prefill tokens with retracted-request re-counts excluded, updated on each log interval. mode: device_hit, host_hit, storage_hit, input. Windowed prefix cache hit rate = rate(sum of *_hit) / rate(sum of all modes); per-tier rate uses a single *_hit mode in the numerator.
# TYPE sglang:prefill_effective_tokens_total counter
sglang:prefill_effective_tokens_total{engine_type="unified",mode="input",model_name="m",moe_ep_rank="0",pp_rank="0",tp_rank="0"} 1.068429e+07
sglang:prefill_effective_tokens_total{engine_type="unified",mode="device_hit",model_name="m",moe_ep_rank="0",pp_rank="0",tp_rank="0"} 910336.0
sglang:prefill_effective_tokens_total{engine_type="unified",mode="host_hit",model_name="m",moe_ep_rank="0",pp_rank="0",tp_rank="0"} 0.0
sglang:prefill_effective_tokens_total{engine_type="unified",mode="storage_hit",model_name="m",moe_ep_rank="0",pp_rank="0",tp_rank="0"} 0.0
# HELP sglang:cache_hit_rate The prefix cache hit rate.
# TYPE sglang:cache_hit_rate gauge
sglang:cache_hit_rate{engine_type="unified",model_name="m",moe_ep_rank="0",pp_rank="0",tp_rank="0"} 0.0
"""


def _selfcheck():
    ok = [0]

    def check(name, cond):
        if not cond:
            print("[selfcheck][FAIL] %s" % name)
            return False
        ok[0] += 1
        print("[selfcheck][PASS] %s" % name)
        return True

    # ① 解析：HELP/TYPE 跳过、标签行入族
    fam = parse_prom_text(_LIVE_SNAPSHOT)
    check("parse: 2 families, 5 rows",
          len(fam) == 2 and len(fam[COUNTER_FAMILY]) == 4 and len(fam[GAUGE_FAMILY]) == 1)
    check("parse: mode labels kept",
          fam[COUNTER_FAMILY][1][0].get("mode") == "device_hit")

    # ② 在役实测重放（单快照累计口径）：计数器健康而 gauge=0.0 → 必须判缺陷签名
    v = judge([fam])
    exp = 910336.0 / (10684290.0 + 910336.0)
    check("live replay: cumulative hit_rate ≈ %.4f" % exp,
          v["caliber"] == "counter-cumulative/prefill_effective"
          and v["hit_rate"] is not None and abs(v["hit_rate"] - exp) < 1e-4)
    check("live replay: defect_signature=True (gauge 0.0 vs real traffic)",
          v["defect_signature"] is True and v["gauge_raw_last"] == 0.0)

    # ③ 分块 prefill 缺陷重放（两快照窗）：健康 0.96 gauge 跳 0，计数器稳增
    s1 = parse_prom_text(
        "sglang:prefill_effective_tokens_total{mode=\"input\"} 900000\n"
        "sglang:prefill_effective_tokens_total{mode=\"device_hit\"} 100000\n"
        "sglang:cache_hit_rate 0.9576\n")
    s2 = parse_prom_text(
        "sglang:prefill_effective_tokens_total{mode=\"input\"} 1000000\n"
        "sglang:prefill_effective_tokens_total{mode=\"device_hit\"} 120000\n"
        "sglang:cache_hit_rate 0.0\n")
    v2 = judge([s1, s2])
    check("chunked replay: windowed rate = 20000/120000",
          v2["caliber"] == "counter-windowed/prefill_effective"
          and v2["hit_rate"] == round(20000.0 / 120000.0, 6)
          and v2["total_tokens"] == 120000)
    check("chunked replay: gauge filter keeps last valid 0.9576",
          v2["gauge_filtered_last"] == 0.9576
          and v2["gauge_zero_samples_dropped"] == 1
          and v2["defect_signature"] is True)

    # ④ 计数器回绕（重启）→ 降级累计比并注记
    v3 = judge([s2, s1])
    check("counter reset: falls back to cumulative with note",
          v3["caliber"] == "counter-cumulative/prefill_effective"
          and any("reset" in n for n in v3["notes"]))

    # ⑤ 备用口径族 + gauge 兜底 + 小流量
    fb = parse_prom_text(
        "sglang:cached_tokens_total{cache_source=\"device\"} 4000\n"
        "sglang:prompt_tokens_total{model_name=\"m\"} 10000\n"
        "sglang:cache_hit_rate 0.0\n")
    v4 = judge([fb])
    check("fallback family: cached/prompt cumulative 0.4",
          v4["caliber"] == "counter-cumulative/cached_over_prompt" and v4["hit_rate"] == 0.4)
    tiny = parse_prom_text(
        "sglang:prefill_effective_tokens_total{mode=\"input\"} 40\n"
        "sglang:prefill_effective_tokens_total{mode=\"device_hit\"} 10\n")
    v5 = judge([tiny])
    check("insufficient_traffic: hit_rate None + note",
          v5["hit_rate"] is None and any("insufficient_traffic" in n for n in v5["notes"]))
    only_gauge = [parse_prom_text("sglang:cache_hit_rate 0.31\n"),
                  parse_prom_text("sglang:cache_hit_rate 0.0\n")]
    v6 = judge(only_gauge)
    check("gauge-only fallback: filtered 0.31 with downgrade note",
          v6["caliber"] == "gauge-filtered-only" and v6["hit_rate"] == 0.31
          and any("fallback" in n for n in v6["notes"]))

    # ⑥ gauge 过滤器本证：真 0% 会被持旧值（诚实边界，判读以计数器为准）
    kept, dropped = filter_gauge_series([0.96, 0.0, 0.0, 0.95])
    check("filter: keeps 0.95, drops 2", kept == 0.95 and dropped == 2)

    # ⑦ lint 面：裸读判红、豁免标记与 mitigated 件过门
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "bad_tool.py")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("rate = float(metrics['sglang:cache_hit_rate'])\n")
        waived = os.path.join(td, "waived_tool.py")
        with open(waived, "w", encoding="utf-8") as f:
            f.write("MET_KEYS = (\"cache_hit_rate\",)  # cache-hit-caliber: raw-snapshot\n")
        viol, files = lint_paths([td])
        check("lint: bare read flagged, waiver passes (scanned %d files)" % len(files),
              len(files) == 2 and len(viol) == 1 and viol[0][0] == bad)
        module_dir = os.path.dirname(os.path.abspath(__file__))
        mviol, mfiles = lint_paths([module_dir])
        check("lint: caliber module itself clean (%d files scanned)" % len(mfiles),
              not mviol)

    print("[selfcheck] %d/13 checks PASS" % ok[0])
    return ok[0] == 13


# ---------------- CLI ----------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="sglang:cache_hit_rate 归零缺陷（上游 #45119）监控侧口径规避件")
    ap.add_argument("--metrics-file", action="append", default=[],
                    help="Prometheus exposition 快照文件（可重复；≥2 份取窗口口径）")
    ap.add_argument("--metrics-url", action="append", default=[],
                    help="引擎 metrics 基址（可重复，自动拼 /metrics；只读 GET）")
    ap.add_argument("--sleep", type=float, default=2.0,
                    help="多 URL 采集间隔秒（缺省 2.0；仅 URL 面）")
    ap.add_argument("--min-traffic", type=int,
                    default=int(os.environ.get("CACHE_HIT_CALIBER_MIN_TRAFFIC",
                                               DEFAULT_MIN_TRAFFIC)),
                    help="判率最小 token 流量（env CACHE_HIT_CALIBER_MIN_TRAFFIC 同源）")
    ap.add_argument("--lint", nargs="+", metavar="PATH",
                    help="lint 面：扫 .py/.sh 裸读 cache_hit_rate（守卫）")
    ap.add_argument("--selfcheck", action="store_true", help="离线自证（零网络零引擎）")
    args = ap.parse_args(argv)

    if args.selfcheck:
        return 0 if _selfcheck() else 1

    if args.lint:
        violations, files = lint_paths(args.lint)
        print("[lint] scanned %d files (.py/.sh)" % len(files))
        for path, lineno, line in violations:
            print("[lint][REFUSE] %s:%d: bare cache_hit_rate read: %s" % (path, lineno, line))
        if violations:
            print("[lint] REFUSE: %d violation(s)——裸 gauge 判据禁用；改走计数器口径"
                  "（tools/obs/cache_hit_caliber.py）或加同行豁免标记 '# %s raw-snapshot'"
                  % (len(violations), WAIVER_MARK))
            return 1
        print("[lint] PASS")
        return 0

    snapshots = []
    for path in args.metrics_file:
        snapshots.append(load_file(path))
    for i, url in enumerate(args.metrics_url):
        if i and args.sleep > 0:
            time.sleep(args.sleep)
        try:
            snapshots.append(fetch_url(url))
        except Exception as e:  # noqa: BLE001
            print("[warn] fetch %s failed: %s" % (url, str(e)[:120]), file=sys.stderr)
    if not snapshots:
        ap.error("需要 --metrics-file/--metrics-url/--lint/--selfcheck 之一")
    verdict = judge(snapshots, min_traffic=args.min_traffic)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
