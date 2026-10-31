#!/usr/bin/env python3
"""census_aggregate_v31 — C4 口径修复新档（血统=tools/census_aggregate.py 68ea12c4 逐字+增量）。

**C4 建制（2026-10-16）**：本件=既有 census_aggregate.py 的**新增档**（该件零改动原位
保留=判读线冻结；法源=032-PLAN C4 行「census_aggregate 口径改法」+R1-HOSTPROF-20261011
§四.1「原 S2 三角的『宿主残差』算法把 GPU 侧集合自旋误记为宿主（census P1 法只减 attn
族内核时间）」）。增量=输出增 `attribution_p1fix` 归因块（预登记式新增，上文既有字段与
取值零改动）+本文件 `--selftest` 离线判别力电池（教义 #15）。

**P1 法缺陷与改法（一句）**：旧残差=wall−attn 族内核时间 ⇒ 把 nccl.* 集合核（GPU 侧
peer-wait 定向等待）整段记进「宿主成本」；新口径=wall(池化步差中位)−Σ**全核**时间=宿主
残差，并把「集合自旋」单列（`gpu_collective_wait_ms_per_step`）；旧减法值保留为
`legacy_wall_minus_attn_only_ms_per_step` **缺陷对照位**（deprecated；禁作归因输入）。
连带纪律（S-RES-EXT2 §二 S9）：GPU 分项**不可相加/不可做 Amdahl**（核时间可跨流重叠；
host_residual 允许为负=重叠量，字段注已明示）。

以下为原件（68ea12c4）逐字头注——保留：

census v3 跨窗聚合器：N 个窗口账 JSON → census_stream 兼容终件。

census v3 分窗流式采集（INC-20261004-UMA 重构）的聚合端。输入=census_window.py
产出的 `census_v3_window/1` 窗口账（精确 ns 整数账），输出=与现行
`*_census_*.json` / `*_arpeaks.json` 字段兼容的终件（下游 G2/p12 判据读数不改
即可用），另加 `windows` 段与分布读数（教义 #14）。

合并数学（全部整数，舍入前精确）：
  - steps            = Σ 窗 steps
  - 族 us_avg        = Σ sum_ns / Σ n            （按调用次数加权）
  - 族 ms_per_step   = Σ sum_ns / Σ steps / 1e6  （按步数加权）
  - 族 calls_per_step= Σ n / Σ steps
  - 族 us_max        = max 窗 max_ns
  - 族 share_pct     = Σ sum_ns / Σ total_kernel_ns
  - wall_ms_per_step = median(heapq.merge 各窗排序步差))  ← 池化中位，
                       与「整窗直读」逐位相等（离线测试对拍项）
  - v2_host_accounting: prb/sync 均值按 Σsteps 加权；sync_breakdown_us=
                       逐名 Σ 总量（census_stream 同口径，非 per-step）
  - attribution_p1fix: C4 归因块（wall/全核/集合自旋/宿主残差/缺陷对照位；
                       集合族=族名 nccl* 前缀集；全整数账同式）
  - decode_span_ms   = Σ 窗 span_ns / 1e6（仅计被采集时间；与整窗直读差
                       边界项 ≤ 每边界一个中位步时，见设计卡 §测试）
  - p50/p99          = 合并 log2 直方图（18 桶）桶内线性插值（近似读数，
                       桶界同报 `*_bucket` 字段；教义 #14 分布读）
  - arpeaks          = 逐窗累积拼接（量小），每条附 window 溯源；epoch 换算
                       与 census_stream 同式 off = base_ns/1000 - first_prb_ts

判别力自检（教义 #15，离线测试 tests/test_offline_aggregate.py 执行）：
  - 窗内不变量：Σ族 sum_ns == total_kernel_ns；Σ族 n == n_kernels；
    len(step_diffs_ns) == steps-1；每族 Σ直方图 == n → 违者拒聚（exit 47）
  - 窗身份唯一：window.id / trace_path 重复 → 拒聚（exit 46）
  - 权重敏感性：steps 是加权分母，喂错窗权重时对拍必红（测试 N3 合成案证明
    「朴素均值」与「加权均值」在本数据上可判别）

v31 增量判别力电池（`--selftest`，本文件内；教义 #15）：
  - S1 归因数学逐项断言；S2 缺陷对照位恒等 legacy−host==全核−attn 族；
  - S3 集合族大小写不敏感；S4 负残差（跨流重叠）如实报+无集合族 coll=0；
  - S5 池化中位语义（≠算术均）；S6 原档 md5 冻结线零改动+旧档输出无
    attribution_p1fix 节（新增性反证）+除新节与 aggregator tag 外逐键零改动。

退出码：46=窗身份重复；47=窗内不变量破坏；48=无窗/短窗；49=窗数与预期不符。
"""
import argparse
import glob
import heapq
import json
import sys

from census_window import BUCKET_LABELS, N_BINS, THRESH_NS, median_sorted_ints

EXIT_DUP = 46
EXIT_INCONSISTENT = 47
EXIT_NOWINDOW = 48
EXIT_COUNT = 49


def load_windows(paths):
    wins = []
    seen_ids = {}
    seen_paths = {}
    for p in paths:
        with open(p) as f:
            w = json.load(f)
        if w.get("schema") != "census_v3_window/1":
            raise SystemExit("census_aggregate: %s: 非 census_v3_window/1（got %r）"
                             % (p, w.get("schema")))
        wid = w["window"]["id"]
        tpath = w["window"].get("trace_path", "")
        if wid in seen_ids:
            print("census_aggregate: REFUSE(46) 窗 id 重复: %d (%s 与 %s)"
                  % (wid, seen_ids[wid], p), file=sys.stderr)
            sys.exit(EXIT_DUP)
        if tpath and tpath in seen_paths:
            print("census_aggregate: REFUSE(46) 窗 trace_path 重复: %s (%s 与 %s)"
                  % (tpath, seen_paths[tpath], p), file=sys.stderr)
            sys.exit(EXIT_DUP)
        seen_ids[wid] = p
        seen_paths[tpath] = p
        w["_path"] = p
        wins.append(w)
    if not wins:
        print("census_aggregate: REFUSE(48) 无输入窗", file=sys.stderr)
        sys.exit(EXIT_NOWINDOW)
    wins.sort(key=lambda w: w["window"]["id"])
    return wins


def check_window(w):
    """窗内不变量。返回问题列表（空=通过）。全部整数精确比较。"""
    probs = []
    fam_sum = sum(e["sum_ns"] for e in w["families"].values())
    fam_n = sum(e["n"] for e in w["families"].values())
    raw_sum = sum(e["sum_ns"] for e in w["raw"].values())
    raw_n = sum(e["n"] for e in w["raw"].values())
    if fam_sum != w["total_kernel_ns"]:
        probs.append("families sum_ns=%d != total_kernel_ns=%d (Δ=%d)"
                     % (fam_sum, w["total_kernel_ns"], fam_sum - w["total_kernel_ns"]))
    if fam_n != w["n_kernels"]:
        probs.append("families n=%d != n_kernels=%d" % (fam_n, w["n_kernels"]))
    if raw_sum != w["total_kernel_ns"]:
        probs.append("raw sum_ns=%d != total_kernel_ns=%d" % (raw_sum, w["total_kernel_ns"]))
    if raw_n != w["n_kernels"]:
        probs.append("raw n=%d != n_kernels=%d" % (raw_n, w["n_kernels"]))
    if len(w["step_diffs_ns"]) != w["steps"] - 1:
        probs.append("len(step_diffs_ns)=%d != steps-1=%d"
                     % (len(w["step_diffs_ns"]), w["steps"] - 1))
    for f, e in w["families"].items():
        if sum(e["hist"]) != e["n"]:
            probs.append("family %s: Σhist=%d != n=%d" % (f, sum(e["hist"]), e["n"]))
        if e["max_ns"] > e["sum_ns"] and e["n"] > 0:
            probs.append("family %s: max_ns>sum_ns" % f)
    return probs


def hist_quantile(hist, q):
    """合并直方图 → 分位数（us）。桶内线性插值；返回 (est_us, bucket_label)。"""
    n = sum(hist)
    if n == 0:
        return None, None
    rank = q * (n - 1)  # 0-based，与「排序数组取值」定义一致
    cum = 0
    for b, c in enumerate(hist):
        if c == 0:
            continue
        if cum + c > rank or b == len(hist) - 1:
            frac = (rank - cum) / c if c else 0.0
            lo = 0.0 if b == 0 else THRESH_NS[b - 1] / 1000.0
            hi = THRESH_NS[b] / 1000.0 if b < len(THRESH_NS) else THRESH_NS[-1] * 2 / 1000.0
            return round(lo + frac * (hi - lo), 1), BUCKET_LABELS[b]
        cum += c
    return None, None


def aggregate(wins, top=45):
    steps = sum(w["steps"] for w in wins)
    total_ns = sum(w["total_kernel_ns"] for w in wins)
    n_kernels = sum(w["n_kernels"] for w in wins)
    span_ns = sum(w["span_ns"] for w in wins)
    prb_sum = sum(w["prb_sum_ns"] for w in wins)
    sync_sum = sum(w["sync_sum_ns"] for w in wins)
    sync_by_name = {}
    for w in wins:
        for k, v in w["sync_by_name_ns"].items():
            sync_by_name[k] = sync_by_name.get(k, 0) + v

    fams = {}
    for w in wins:
        for f, e in w["families"].items():
            m = fams.get(f)
            if m is None:
                m = fams[f] = {"sum_ns": 0, "n": 0, "max_ns": 0,
                               "hist": [0] * N_BINS}
            m["sum_ns"] += e["sum_ns"]
            m["n"] += e["n"]
            m["max_ns"] = max(m["max_ns"], e["max_ns"])
            for i in range(N_BINS):
                m["hist"][i] += e["hist"][i]
    raws = {}
    for w in wins:
        for nm, e in w["raw"].items():
            r = raws.get(nm)
            if r is None:
                r = raws[nm] = {"sum_ns": 0, "n": 0}
            r["sum_ns"] += e["sum_ns"]
            r["n"] += e["n"]

    pooled = list(heapq.merge(*(w["step_diffs_ns"] for w in wins)))
    med_ns = median_sorted_ints(pooled)
    span_ms = span_ns / 1e6

    prb_avg = prb_sum / steps / 1000.0
    sync_avg = sync_sum / steps / 1000.0

    # ── C4/P1 法归因（2026-10-16 预登记新增；上文既有字段零改动）───────────────
    # 法源=R1-HOSTPROF §四.1：旧「宿主残差」=wall−attn 族（缺陷：nccl.* 集合核=GPU 侧
    # peer-wait 被整段误记宿主）。新口径分列：全核时间 / 集合自旋 / 宿主残差=wall−Σ全核；
    # 旧减法值留缺陷对照位（deprecated，禁作归因输入）。集合族判定=族名小写前缀 "nccl"。
    coll_fams = sorted(f for f in fams if f.lower().startswith("nccl"))
    coll_ns = sum(fams[f]["sum_ns"] for f in coll_fams)
    attn_fams = sorted(f for f in fams if "attn" in f.lower())
    attn_ns = sum(fams[f]["sum_ns"] for f in attn_fams)
    wall_ns = med_ns  # 池化步差中位（既有 wall 口径，整数）
    kern_ms = total_ns / steps / 1e6
    coll_ms = coll_ns / steps / 1e6
    host_ms = (wall_ns - total_ns / steps) / 1e6
    legacy_ms = (wall_ns - attn_ns / steps) / 1e6

    rows = []
    for f, e in sorted(fams.items(), key=lambda kv: -kv[1]["sum_ns"])[:top]:
        p50, p50_b = hist_quantile(e["hist"], 0.50)
        p99, p99_b = hist_quantile(e["hist"], 0.99)
        rows.append({
            "family": f,
            "ms_per_step": round(e["sum_ns"] / steps / 1e6, 3),
            "calls_per_step": round(e["n"] / steps, 1),
            "us_avg": round(e["sum_ns"] / e["n"] / 1000.0, 1),
            "us_max": round(e["max_ns"] / 1000.0, 1),
            "share_pct": round(e["sum_ns"] / total_ns * 100, 1) if total_ns else 0.0,
            # 教义 #14 分布读（log2 直方图插值，桶界同报；直方图本档 18 桶）
            "us_p50": p50, "p50_bucket": p50_b,
            "us_p99": p99, "p99_bucket": p99_b,
        })

    out = {
        "steps": steps,
        "decode_span_ms": round(span_ms, 1),
        "wall_ms_per_step": round(med_ns / 1e6, 2),
        "span_over_steps_ms": round(span_ms / steps, 2),
        "gpu_busy_ms_per_step": round(total_ns / steps / 1e6, 2),
        "gpu_busy_pct": round(total_ns / span_ns * 100, 1) if span_ns else 0.0,
        "n_kernels_per_step": round(n_kernels / steps, 0),
        "n_families": len(fams),
        "v2_host_accounting": {
            "prb_annotation_avg_us": round(prb_avg, 1),
            "sync_wait_avg_us": round(sync_avg, 1),
            "net_bookkeeping_avg_us": round(prb_avg - sync_avg, 1),
            "note": "prb-sync=net bookkeeping (doc13 s1: sync is designed wait)",
            "sync_breakdown_us": {k: round(v / 1000.0, 1)
                                  for k, v in sorted(sync_by_name.items(),
                                                     key=lambda kv: -kv[1])[:5]},
        },
        # ── C4：P1 法归因块（新档增量；引用一切宿主/归因读数须走本块）──
        "attribution_p1fix": {
            "schema": "census_p1attr/1",
            "wall_ms_per_step": round(wall_ns / 1e6, 2),
            "kernel_sum_ms_per_step": round(kern_ms, 2),
            "gpu_collective_wait_ms_per_step": round(coll_ms, 2),
            "gpu_collective_families": coll_fams,
            "gpu_collective_pct_of_kernel": (round(coll_ns / total_ns * 100, 1)
                                             if total_ns else 0.0),
            "host_residual_ms_per_step": round(host_ms, 2),
            "attn_family_ms_per_step": round(attn_ns / steps / 1e6, 2),
            "attn_families": attn_fams,
            "legacy_wall_minus_attn_only_ms_per_step": round(legacy_ms, 2),
            "legacy_note": ("DEPRECATED 缺陷对照位（原 S2 三角旧减法 wall−attn 族；"
                            "把 nccl 集合自旋误记宿主）——只为可追溯保留，禁作归因输入"),
            "host_residual_def": ("wall(池化步差中位) − Σ全核时间/步；核时间可跨流重叠"
                                  "⇒允许为负（负值=重叠量）；集合自旋属 GPU 侧 peer-wait"
                                  " 定向等待，禁记宿主"),
            "discipline_note": ("GPU 分项不可相加/不可做 Amdahl（S-RES-EXT2 §二 S9 同律）；"
                                "跨栈引用外部读数同律"),
        },
        "base_time_nanoseconds": wins[0]["base_time_nanoseconds"],
        "ar_peaks_n": sum(len(w["ar"]) for w in wins),
        "rows": rows,
        "raw_rows": [{"name": nm, "ms_per_step": round(e["sum_ns"] / steps / 1e6, 4),
                      "calls_per_step": round(e["n"] / steps, 1)}
                     for nm, e in sorted(raws.items(), key=lambda kv: -kv[1]["sum_ns"])[:60]],
        "windows": {
            "n": len(wins),
            "items": [{
                "id": w["window"]["id"], "label": w["window"].get("label", ""),
                "phase": w["window"].get("phase", ""),
                "req_num_steps": w["window"].get("req_num_steps", 0),
                "steps": w["steps"],
                "decode_span_ms": round(w["span_ns"] / 1e6, 1),
                "net_mem_mb": w["window"].get("meta", {}).get("net_mb", ""),
                "mem_pre_mb": w["window"].get("meta", {}).get("mem_pre_mb", ""),
                "mem_post_mb": w["window"].get("meta", {}).get("mem_post_mb", ""),
                "truncated": w["window"].get("meta", {}).get("truncated", "0"),
                "trace_mb": round(w["window"].get("trace_bytes", 0) / 1e6, 1),
                "source": w["_path"],
            } for w in wins],
        },
        "census_v3": {
            "aggregator": "census_aggregate_v31.py/1",
            "window_schema": "census_v3_window/1",
            "merge_math": ("整数 ns 账：us_avg 按 Σn 加权；ms_per_step/calls_per_step "
                           "按 Σsteps 加权；wall_ms_per_step=池化步差中位；"
                           "us_max=跨窗 max；直方图逐桶整数合并"),
            "quantile_method": ("log2 直方图 18 桶（<1us,1..131072us,≥131072us）"
                                "桶内线性插值，近似读数，桶界见 *_bucket 字段"),
            "span_semantics": ("decode_span_ms=Σ各窗被采集跨度（窗间未采集间隙不计）；"
                               "与整窗直读差边界项≤每边界一个中位步时"),
        },
    }
    return out


def merge_arpeaks(wins):
    entries = []
    for w in wins:
        base_ns = w["base_time_nanoseconds"]
        off = (base_ns / 1000.0 - w["first_prb_ts_us"]) if base_ns else 0.0
        for t, d in w["ar"]:
            entries.append({"mono_ts": t, "epoch_est_us": t + off,
                            "dur_us": round(d, 1), "window": w["window"]["id"]})
    entries.sort(key=lambda e: e["epoch_est_us"])
    return entries


def selftest():
    """C4 判别力电池（教义 #15）：合成窗喂器，看它因正确理由绿/红。

    S0 合成窗过窗内不变量；S1 归因数学（nccl 集合族/attn 族/宿主残差）逐项
    断言；S2 缺陷对照位代数恒等 legacy−host == 集合自旋（旧减法把 nccl 记进
    宿主的价值差=集合自旋量）；S3 宿主残差负值（核时间跨流重叠）不拒聚；
    S4 无集合族窗 coll=0/legacy==host；S5 原档（census_aggregate.py）md5 冻结
    线零改动+旧档可跑对照；S6 新增性反证：旧档输出无 attribution_p1fix 节，
    且 v31 输出除该节+census_v3.aggregator 外与旧档逐键相等（既有字段零改动）。
    """
    import hashlib
    import os
    import subprocess
    import tempfile

    from census_window import bucket

    ok = True

    def chk(name, cond, detail=""):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name, ("——" + detail) if detail else "")
        ok = ok and cond

    def mkwin(wid, steps, fams, step_ns=40_000_000, prb_ns=1000):
        """合成窗（全整数账；结构=test_offline_aggregate.py mkwin 同形）。"""
        diffs = [step_ns] * (steps - 1)
        fam_block, raw_block = {}, {}
        tot = nk = 0
        for f, (s, n) in fams.items():
            h = [0] * N_BINS
            h[bucket(s // n)] = n
            fam_block[f] = {"sum_ns": s, "n": n, "max_ns": s // n, "hist": h}
            raw_block["syn_%s" % f] = {"sum_ns": s, "n": n}
            tot += s
            nk += n
        return {
            "schema": "census_v3_window/1",
            "window": {"id": wid, "label": "syn", "phase": "decode",
                       "req_num_steps": steps, "profile_stages": "",
                       "trace_path": "/syn/%d" % wid, "trace_bytes": 0, "meta": {}},
            "steps": steps, "n_events": nk, "n_kernels": nk,
            "total_kernel_ns": tot,
            "first_ts_ns": 0, "last_ts_ns": 0,
            "span_ns": steps * step_ns, "step_diffs_ns": diffs,
            "prb_sum_ns": steps * prb_ns, "sync_sum_ns": 0, "sync_by_name_ns": {},
            "base_time_nanoseconds": 0, "first_prb_ts_us": 0.0, "last_prb_ts_us": 0.0,
            "families": fam_block, "raw": raw_block, "ar": [],
            "hist_bins": N_BINS, "hist_thresholds_ns": THRESH_NS,
        }

    wd = tempfile.mkdtemp(prefix="census_v31_selftest_")

    def agg_one(w, tag):
        p = os.path.join(wd, "%s.win.json" % tag)
        with open(p, "w") as f:
            json.dump(w, f)
        return aggregate(load_windows([p]))

    # ── 合成窗三枚 ──────────────────────────────────────────────────────
    wa = mkwin(100, 10, {"nccl_allreduce": (5_000_000, 10),
                         "flash_attn_fwd": (30_000_000, 10),
                         "gemm": (20_000_000, 5)})
    wb = mkwin(101, 5, {"NCCL_AllGather": (2_000_000, 5),
                        "attn": (18_000_000, 5)}, step_ns=30_000_000)
    wc = mkwin(102, 6, {"big_gemm": (300_000_000, 6)})  # 全核>wall ⇒ 负残差
    for w in (wa, wb, wc):
        probs = check_window(w)
        chk("S0 合成窗不变量全过(#%d)" % w["window"]["id"], not probs, str(probs))

    # ── S1：归因数学（win100：wall 40ms/步；全核 5.5；nccl 0.5；attn 3.0）──
    A = agg_one(wa, "A")
    a = A["attribution_p1fix"]
    chk("S1.wall==40.0（池化步差中位）", a["wall_ms_per_step"] == 40.0,
        str(a["wall_ms_per_step"]))
    chk("S1.kernel_sum==5.5", a["kernel_sum_ms_per_step"] == 5.5,
        str(a["kernel_sum_ms_per_step"]))
    chk("S1.collective==0.5 且族=[nccl_allreduce]",
        a["gpu_collective_wait_ms_per_step"] == 0.5
        and a["gpu_collective_families"] == ["nccl_allreduce"],
        str(a["gpu_collective_families"]))
    chk("S1.host_residual==wall−全核=34.5", a["host_residual_ms_per_step"] == 34.5,
        str(a["host_residual_ms_per_step"]))
    chk("S1.attn 族=3.0 且族=[flash_attn_fwd]",
        a["attn_family_ms_per_step"] == 3.0
        and a["attn_families"] == ["flash_attn_fwd"])
    chk("S1.collective_pct_of_kernel==9.1", a["gpu_collective_pct_of_kernel"] == 9.1,
        str(a["gpu_collective_pct_of_kernel"]))
    # ── S2：缺陷对照位代数恒等 legacy−host == 全核−attn 族（误记量）──
    # 旧减法把 attn 之外全部核（含 nccl 集合自旋 0.5 + 非 attn 普通核 2.0）记进宿主
    chk("S2.legacy−host==全核−attn 族==2.5（缺陷量=非 attn 全部核）",
        round(a["legacy_wall_minus_attn_only_ms_per_step"]
              - a["host_residual_ms_per_step"], 2) == 2.5,
        "legacy=%s" % a["legacy_wall_minus_attn_only_ms_per_step"])
    chk("S2.legacy!=host（两口径可判别，判别力非空洞）",
        a["legacy_wall_minus_attn_only_ms_per_step"] != a["host_residual_ms_per_step"])

    # ── S3：大小写不敏感集合族判定（NCCL_AllGather）──────────────────
    B = agg_one(wb, "B")
    b = B["attribution_p1fix"]
    chk("S3.大写 NCCL_* 族被识别", b["gpu_collective_families"] == ["NCCL_AllGather"],
        str(b["gpu_collective_families"]))
    chk("S3.B 面 host==26.0/legacy==26.4（wall30−全核4 / wall30−attn3.6）",
        b["host_residual_ms_per_step"] == 26.0
        and b["legacy_wall_minus_attn_only_ms_per_step"] == 26.4)

    # ── S4：负残差（全核>wall=跨流重叠）不红；无集合族 coll=0 ─────────
    C = agg_one(wc, "C")
    c = C["attribution_p1fix"]
    chk("S4.全核>wall ⇒ host 负值如实报= −10.0",
        c["host_residual_ms_per_step"] == -10.0 and c["kernel_sum_ms_per_step"] == 50.0,
        "host=%s" % c["host_residual_ms_per_step"])
    chk("S4.无 nccl 族 ⇒ coll=0/族=[]/pct=0",
        c["gpu_collective_wait_ms_per_step"] == 0.0
        and c["gpu_collective_families"] == []
        and c["gpu_collective_pct_of_kernel"] == 0.0)
    chk("S4.无 attn 族 ⇒ legacy==wall==40.0 而 host==−10（两减法分离）",
        c["legacy_wall_minus_attn_only_ms_per_step"] == 40.0
        and c["attn_families"] == [])

    # ── S5：池化中位语义（win100+win101：池化中位 40 ≠ 算术均 36.9）───
    pa, pb = (os.path.join(wd, t) for t in ("A.win.json", "B.win.json"))
    D = aggregate(load_windows([pa, pb]))
    d = D["attribution_p1fix"]
    chk("S5.池化中位=40.0（≠均 36.92 ⇒ 非均值的判别力）",
        d["wall_ms_per_step"] == 40.0, str(d["wall_ms_per_step"]))
    chk("S5.跨窗归因 host==35.0（40−75/15）",
        d["host_residual_ms_per_step"] == 35.0, str(d["host_residual_ms_per_step"]))

    # ── S6：原档零改动冻结线 + 新增性反证（旧档输出无本新节）──────────
    old = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "census_aggregate.py")
    md5 = hashlib.md5(open(old, "rb").read()).hexdigest()
    chk("S6.原档 census_aggregate.py md5 冻结线零改动",
        md5 == "68ea12c4d7e3ca52f70cca0b5408bd9e", md5)
    oldout = os.path.join(wd, "oldA.json")
    r = subprocess.run([sys.executable, old, pa, "--json", oldout],
                       capture_output=True, text=True)
    chk("S6.旧档同输入可跑（对照面）", r.returncode == 0, r.stderr.strip()[-160:])
    if r.returncode == 0:
        oldj = json.load(open(oldout))
        chk("S6.新增性反证：旧档输出无 attribution_p1fix", "attribution_p1fix" not in oldj)
        chk("S6.v31 输出有 attribution_p1fix", "attribution_p1fix" in A)

        def strip(doc):
            doc = json.loads(json.dumps(doc))
            doc.pop("attribution_p1fix", None)
            doc["census_v3"].pop("aggregator", None)
            return doc

        chk("S6.既有字段逐键零改动（除新节+census_v3.aggregator 外全等）",
            strip(A) == strip(oldj))

    for p in glob.glob(os.path.join(wd, "*")):
        os.unlink(p)
    os.rmdir(wd)
    print("[census_aggregate_v31][selftest] %s" % ("ALL-GREEN" if ok else "RED"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(prog="census_aggregate_v31.py")
    ap.add_argument("--selftest", action="store_true",
                    help="离线判别力电池（合成窗+旧档零改动反证；无需输入窗）")
    ap.add_argument("window_jsons", nargs="*",
                    help="窗口账 JSON（census_window.py 产出；支持 glob）")
    ap.add_argument("--json", default="", help="聚合终件（census 兼容格式）")
    ap.add_argument("--arpeaks", default="", help="聚合 arpeaks 终件")
    ap.add_argument("--top", type=int, default=45)
    ap.add_argument("--expect-windows", type=int, default=0,
                    help="预期窗数（不一致拒聚 exit 49）")
    ap.add_argument("--min-steps", type=int, default=3,
                    help="每窗最小 prb 步数（短窗拒聚 exit 48；0=放宽）")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if not a.window_jsons or not a.json:
        ap.error("需要 window_jsons 与 --json（或 --selftest）")

    paths = []
    for pat in a.window_jsons:
        hit = sorted(glob.glob(pat))
        paths.extend(hit if hit else [pat])  # 无 glob 命中按字面路径（缺失时 open 报错）
    wins = load_windows(paths)

    for w in wins:
        if a.min_steps and w["steps"] < a.min_steps:
            print("census_aggregate: REFUSE(48) 窗 %d 步数 %d < %d（%s）"
                  % (w["window"]["id"], w["steps"], a.min_steps, w["_path"]),
                  file=sys.stderr)
            sys.exit(EXIT_NOWINDOW)
        probs = check_window(w)
        if probs:
            print("census_aggregate: REFUSE(47) 窗 %d 不变量破坏（%s）:"
                  % (w["window"]["id"], w["_path"]), file=sys.stderr)
            for p in probs:
                print("  - %s" % p, file=sys.stderr)
            sys.exit(EXIT_INCONSISTENT)

    if a.expect_windows and len(wins) != a.expect_windows:
        print("census_aggregate: REFUSE(49) 窗数 %d != 预期 %d" % (len(wins), a.expect_windows),
              file=sys.stderr)
        sys.exit(EXIT_COUNT)

    out = aggregate(wins, top=a.top)
    with open(a.json, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    if a.arpeaks:
        with open(a.arpeaks, "w") as f:
            json.dump(merge_arpeaks(wins), f, ensure_ascii=False)

    print("AGG windows=%d steps=%d wall=%.2fms/step gpu_busy=%.2fms/step (%.1f%%) "
          "kernels/step=%d families=%d AR>1ms=%d -> %s"
          % (out["windows"]["n"], out["steps"], out["wall_ms_per_step"],
             out["gpu_busy_ms_per_step"], out["gpu_busy_pct"],
             int(out["n_kernels_per_step"]), out["n_families"], out["ar_peaks_n"],
             a.json))
    for w in out["windows"]["items"]:
        print("  win#%d %-7s steps=%-4d span=%-8.1fms trace=%-7.1fMB net_mem=%sMB"
              % (w["id"], w["phase"], w["steps"], w["decode_span_ms"],
                 w["trace_mb"], w["net_mem_mb"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
