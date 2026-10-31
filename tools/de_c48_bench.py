#!/usr/bin/env python3
"""de_c48_bench.py — DE prose c1/c4/c8 三档正典量测件（用户令六量具面建设；S-DE48TOOL）

【为什么存在】台账 §二十六-5：判读主面=DE prose **c1/c4/c8 三档取最佳**（mt400 正典口径），
  现役量具仅 c1（电池卡 D3 四型）+ 同窗 A/B 临时 c8/c16（E16B1/B2/E11/L2OFF 卡 9a 内联段）——
  无正典件、无跨靴锚列、无流级公平性面。本件=c4/c8 正典化 + 三档统一阶梯。

【口径（c1 同法同语料同口径，零新造）】
  - 底层探针 = 交付仓 `luz-deepseek-flash-all-in-one/tools/bench/sd_bench.py`
    （md5 钉 410f543d…；T33-03 Phase 0 双口径版，2026-10-23 重钉。钉史：
    f0dd91c4…=W-G 冻结件〔旧默认仓 ~/dsv41-flash-dgxsparks，该仓现已无 bench/sd_bench.py，
    只剩 logs/〕→ 84ff45b1…=033 P5 real-filler 版前身 → 410f543d…=现役。默认请求体
    逐字节不变由 sd_bench --selfcheck 断言；SD_MD5_OVERRIDE 显式重钉通道保留）——
    本件 importlib 直载其 `run_de/Client/de_prompt`：语料（prose=hash-map
    essay 逐字节）、greedy（temp 0/top_p 1/thinking off）、stream+include_usage、
    per=(completion−1)/(t_last−t_first)、agg=Σ(completion−1)/(max t_last−min t_first)、
    warmups 2（32-token 热身）、c>1 非code型 "(stream i/n)" 后缀——**与 c1 电池卡同一函数同一实现**。
  - T33-03 Phase 0 双口径：--capture-spec 开时 run_de 行带 committed_decode_tps/
    full_accept_equiv_tps/accept_rate/avg_verified_len/reasoning_tokens/cached_tokens +
    per_request 闭合行（Σ(completion−1)=Σgenerated、gen=accepted+b）；tier_metrics 池出
    accept_len_med/p95、accept_rate_med、verified_len_med、full_accept_equiv_agg_med、
    committed_agg_med、reasoning_tokens_sum；capture off ⇒ 这些面=None 不造数（不与 spec 臂混比）。
  - 调用形 = 电池卡 D3/E16B1 卡 9a 同形：--mode de --type prose --concurrency N --runs 5
    --max-tokens 400 --warmups 2，直连 8899（mt400 直连正典；DE 报数必带 maxTokens——
    83 系=旧权重 mt400、73 系=mt64 仪表盘，互不可比；DE-CALIBER-VERIFY §2/§6 口径律）。
  - **c1 时 agg≡per**（单流 max/min 退化同式）⇒ 三档统一主量=agg_med 与现锚 prose c1 88.06
    （A6-ANCHOR-7 列）同量同义直接可比；c4/c8=NEW-TIER 首跑建锚（DE-48 列扩展）。

【三步法（pr_ladder6 同构；位置敏感纪律）】
  A 首发   = 三档串行各 1 cell（冷位形态在档）
  B 暖重   = 每档单独 1 cell（暖位对表）
  C 仲裁×R = R 轮（默认 3）、每轮每档 1 cell、**轮间档序左旋换位**（位置偏差在仲裁中位处对消）；
  锚值/主量 = C 各 cell 的 run 级统计池（每 cell 内含 runs 个 run 样本）。

【报数规范（防单流饿死假读数；每档必带）】
  arb_med（agg_med 主量+spread）+ per_med（流级中位）+ **P95/P99**（流级速率池化分位，
  nearest-rank）+ **流级公平性三件**：jain 公平指数（(Σx)²/(n·Σx²)，全等=1）取跨 run
  min/med、slow_ratio（run 内最慢流/中位流）min/med、completion 完整性（early_stop 计数：
  greedy prose mt400 正典形应写满 400，早停=内容窗位移注记位）。
  半速律（DE-CALIBER-VERIFY §3：任何一条并发流把 c1 减半）⇒ c4/c8 采窗互斥纪律同 c1：
  测者一次只留一侧在跑+Mac 侧 rgw 巡检流量零撞窗（§4 对时法）。

【三档合成判（口径规范操作定义，详 S-DE48TOOL-RESULT §三）】
  每档 Δ%=（agg_med−锚）/锚；合成=有锚档取 max(Δ)（三档取最佳）+ 任一有锚档 ≤−band%=红 +
  NEW-TIER 档只建锚不参赛；硬守门（KV 池/上下文/GSM8K/位等）优先级高于本面（用户令六-4）。

【护栏】md5 钉死（漂移=口径漂移必须显式 SD_MD5_OVERRIDE 重钉）；--dry-run 只打印 cell 计划
  零发包；--selfcheck 纯离线（mock 客户端，零网络零产线触）：参数校验/口径断言/公式与分位
  单测/输出 schema/坏输入必红（判别力纪律：新量具必须喂坏输入看它因正确理由变红）。

【用法】
  python3 tools/de_c48_bench.py --arm-tag <TAG>                    # 真跑（引擎须 8899 在役）
  python3 tools/de_c48_bench.py --dry-run --arm-tag demo           # 干跑：打印 cell 计划
  python3 tools/de_c48_bench.py --selfcheck                        # 离线自检
  运维包络（水位看护/互斥检查/日志）用 tools/de_c48_ladder.sh（runbook）。
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
import time
import uuid

SD_MD5_PIN = "410f543d4cc363defa66ffd54d190c9a"  # T33-03 Phase 0 双口径版（2026-10-23 重钉；
# 钉史：f0dd91c4cb413c671912927a6e0bea2a=W-G 冻结件 → 84ff45b10582f24213f648f00f1f213d=P5 前身；
# 漂移须显式 SD_MD5_OVERRIDE 重钉并在窗档注记旧/新 md5）
SD_MD5_PIN_OLD = "f0dd91c4cb413c671912927a6e0bea2a"  # W-G 冻结件（R5 §一在案；summary 窗档留史）
DE_TYPE = "prose"           # 用户令六判读面=prose（本正典件钉死；四型 c1 电池面归 D3 卡）
CANON_TIERS = (1, 4, 8)     # 三档（c16 同窗 A/B 观察位归 E16 lineage 卡，不入本件）
SCHEMA_VERSION = "de48-v1"  # 输出行不改旧键（--legacy-csv 裁回）；双口径键为新增面
NEXTN_DEFAULT = 5           # 投机 γ（DSPARK 静态 nextn=5；与 sd_bench.NEXTN_DEFAULT 同源）
# summary TSV 列面：legacy=历史窗档逐字节（--legacy-csv）；默认=legacy+双口径 8 列（T33-03）
TSV_LEGACY_HEADER = ("tier\tagg_med\tspread%\tper_med\tP95\tP99\tstream_min\tjain_min\t"
                     "slow_ratio_min\tearly_stop\tanchor\tΔ%\tverdict")
TSV_DUAL_EXTRA = ("\tcommitted_agg_med\tfull_accept_agg_med\taccept_len_med\taccept_len_p95\t"
                  "accept_rate_med\tverified_len_med\treasoning_sum\tclosure_ok/checked")


# ── sd_bench 直载（单一事实源：语料/客户端/公式零复制）──────────────────────
def load_sd(bench_repo, quiet=False):
    path = os.path.join(os.path.expanduser(bench_repo), "bench", "sd_bench.py")
    if not os.path.isfile(path):
        raise SystemExit(f"ABORT: 缺 {path}（BENCH_REPO 指错或探针件不在）")
    md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
    override = os.environ.get("SD_MD5_OVERRIDE", "").strip()
    if md5 != SD_MD5_PIN and md5 != override:
        raise SystemExit(f"ABORT: sd_bench md5={md5} ≠ 钉 {SD_MD5_PIN}（口径漂移）；"
                         f"确需新版请 SD_MD5_OVERRIDE={md5} 显式重钉并在窗档注记")
    if not quiet:
        print(f"[caliber] sd_bench={path} md5={md5}（pin={SD_MD5_PIN}）"
              + (" [OVERRIDE]" if md5 != SD_MD5_PIN else ""))
    spec = importlib.util.spec_from_file_location("sd_bench_canon", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, md5


# ── 统计量（口径件：定义钉死，判读线归各窗 desk 事前冻结）──────────────────
def pctl_nearest_rank(xs, q):
    """nearest-rank 分位：P_q = sorted[ceil(q/100·n)−1]。与 E16 系报告的 P95/P99 语义一致，
    小样本不外插（c1 池 15 样本时 P99=第 15 位=最大值，如实不藏尾）。"""
    s = sorted(xs)
    if not s:
        return None
    k = max(1, math.ceil(q / 100.0 * len(s)))
    return round(s[k - 1], 2)


def jain(xs):
    """Jain 公平指数 (Σx)²/(n·Σx²)：全等=1.0，单流饿死→显著<1。速率向量专用（全正）。"""
    n = len(xs)
    if n == 0:
        return None
    sx, sx2 = sum(xs), sum(x * x for x in xs)
    if sx2 <= 0:
        return None
    return round(sx * sx / (n * sx2), 4)


def slow_ratio(xs):
    """run 内最慢流/中位流（防饿死直读：1=全等，0.5=最慢流腰斩，→0=饿死）。"""
    if not xs:
        return None
    med = statistics.median(xs)
    return None if med <= 0 else round(min(xs) / med, 4)


def spread_pct(vals):
    if len(vals) < 2:
        return None
    med = statistics.median(vals)
    return None if med == 0 else round(100.0 * (max(vals) - min(vals)) / med, 1)


def tier_metrics(cells, max_tokens):
    """从仲裁 cell 池出每档报数（cells=[run_de 行列表/行]；行 schema=sd_bench run_de 原样
    + Phase 0 双口径面）。旧形 cell（无新键）⇒ 双口径面=None 不造数（不与 spec 臂混比）。"""
    rows = [r for cell in cells for r in cell]           # run 级池
    aggs = [r["agg"] for r in rows]
    pers = [r["per"] for r in rows]                       # run 内流级中位
    streams = [x for r in rows for x in r["per_all"]]     # 流级池（公平性/分位面）
    comps = [c for r in rows for c in r["completion"]]
    jains = [jain(r["per_all"]) for r in rows if len(r["per_all"]) > 1]
    slows = [slow_ratio(r["per_all"]) for r in rows if len(r["per_all"]) > 1]
    # ── T33-03 Phase 0 双口径池（capture-spec 臂才有值；INV-02 §6.2 字段名）──
    fae = [r["full_accept_equiv_tps"] for r in rows
           if r.get("full_accept_equiv_tps") is not None]
    rates = [r["accept_rate"] for r in rows if r.get("accept_rate") is not None]
    vlens = [r["avg_verified_len"] for r in rows if r.get("avg_verified_len") is not None]
    alens = [q["accept_len"] for r in rows for q in (r.get("per_request") or [])
             if q.get("accept_len") is not None]
    rrows = [r for r in rows if r.get("reasoning_tokens") is not None]
    closures = [(r.get("closure") or {}) for r in rows if r.get("closure")]
    id_checked = [c for c in closures if c.get("identity_sum_completion_eq_generated") is not None]
    id_ok = [c for c in id_checked if c["identity_sum_completion_eq_generated"] is True]
    gen_ok = [c for c in closures if c.get("identity_gen_eq_accepted_plus_b") is True]
    return {
        "runs_n": len(rows), "stream_n": len(streams),
        "agg_all": [round(a, 2) for a in aggs],
        "agg_med": round(statistics.median(aggs), 2) if aggs else None,
        "agg_spread_pct": spread_pct(aggs),
        "per_med": round(statistics.median(pers), 2) if pers else None,   # c1 时≡agg_med
        "stream_p95": pctl_nearest_rank(streams, 95),
        "stream_p99": pctl_nearest_rank(streams, 99),
        "stream_min": round(min(streams), 2) if streams else None,
        "jain_min": round(min(jains), 4) if jains else None,              # c1 恒 None（单流无公平性面）
        "jain_med": round(statistics.median(jains), 4) if jains else None,
        "slow_ratio_min": round(min(slows), 4) if slows else None,
        "slow_ratio_med": round(statistics.median(slows), 4) if slows else None,
        "completion_min": min(comps) if comps else None,
        "early_stop_count": sum(1 for c in comps if c < max_tokens),
        "max_tokens": max_tokens,
        # 双口径面（旧形 cell 全 None；附录 D：committed 与 full-accept 分列不得互推）
        "committed_agg_med": round(statistics.median(aggs), 2) if aggs else None,  # =agg_med 同式（口径标签）
        "full_accept_equiv_agg_med": round(statistics.median(fae), 2) if fae else None,
        "accept_len_med": round(statistics.median(alens), 4) if alens else None,
        "accept_len_p95": pctl_nearest_rank(alens, 95) if alens else None,
        "accept_rate_med": round(statistics.median(rates), 4) if rates else None,
        "verified_len_med": round(statistics.median(vlens), 4) if vlens else None,
        "reasoning_tokens_sum": sum(r["reasoning_tokens"] for r in rrows)
        if len(rrows) == len(rows) and rows else None,
        "closure_rows_checked": len(id_checked),
        "closure_rows_ok": len(id_ok),
        "closure_gen_eq_ok": len(gen_ok),
    }


def verdict_of(delta_pct, anchor, band):
    """带判（电池卡 D3/C16-1 同语义）：无锚=NEW-TIER（首跑建锚，DE-48 列扩展位）；
    有锚 |Δ|≤band=IN-BAND、正向超带=OUT-POS、负向超带=RED；有锚无读数=MISSING。"""
    if anchor is None:
        return "NEW-TIER(首跑建锚)"
    if delta_pct is None:
        return "MISSING(判卡记缺口)"
    if abs(delta_pct) <= band:
        return "IN-BAND(±%.0f%%)" % band
    return "OUT-POS(>+%)" if delta_pct > 0 else "RED(<-band)"


# ── 量测主体（真跑才触网；dry/selfcheck 零网络）────────────────────────────
def ladder_plan(tiers, arb_rounds, first_warm):
    """cell 计划（dry 与真跑同源）：A 首发（可选）+B 暖重（可选）+C 仲裁×R 轮间档序左旋。"""
    n = len(tiers)
    phases = []
    if first_warm:
        phases.append(("first", tiers))
        for t in tiers:
            phases.append(("warm", [t]))
    for r in range(1, arb_rounds + 1):
        rot = (r - 1) % n
        phases.append((f"arb{r}", list(tiers[rot:]) + list(tiers[:rot])))
    return phases


def cell_name(arm, phase, tier):
    return f"{arm}-de48-prose-c{tier}-{phase}"


def measure(args, sd=None, md5=None):
    if sd is None:
        sd, md5 = load_sd(args.bench_repo)
    elif md5 is None:
        md5 = SD_MD5_PIN
    tiers = args.tiers
    print(f"[plan] tiers={tiers} runs={args.runs}/cell warmups={args.warmups} "
          f"mt={args.max_tokens} arb_rounds={args.arb_rounds} first_warm={args.first_warm} "
          f"anchors={args.anchors} band=±{args.band_pct}%")
    phases = ladder_plan(tiers, args.arb_rounds, args.first_warm)
    for tag, order in phases:
        print(f"[plan] {tag}: 档序={order}")
    if args.dry_run:
        print("[dry-run] cell 计划如上，零发包（每 cell = sd_bench run_de 同法：warmups×32t 热身 + "
              f"runs×{args.runs} 并发流 burst；主量取自 arb cell 池）")
        return 0

    outdir = args.out_dir or os.path.join(args.campaign, "logs", args.arm_tag, "dec48",
                                          time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(outdir, exist_ok=True)
    log_path = os.path.join(outdir, "de_c48.log")

    def log(msg):
        line = "[%s] %s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)
        print(line)
        with open(log_path, "a") as fp:
            fp.write(line + "\n")

    log(f"== de_c48_bench 启动 arm={args.arm_tag} outdir={outdir} base_url={args.base_url} ==")
    log("纪律注: 直连 8899=mt400 正典；半速律互斥（测者一次只留一侧跑+Mac rgw 零撞窗对时）")
    client = sd.Client(args.base_url, "", timeout_s=max(120, args.max_tokens * 8))
    raw = {}   # (phase, tier) -> rows
    arb_cells = {t: [] for t in tiers}
    for tag, order in phases:
        for tier in order:
            name = cell_name(args.arm_tag, tag, tier)
            raw_path = os.path.join(outdir, f"de48_prose_c{tier}_{tag}.json")
            log(f"[{tag}] c{tier} 起（{name}）")
            t0 = time.time()
            rows = sd.run_de(client, DE_TYPE, tier, args.max_tokens, args.warmups, args.runs,
                             capture_spec=args.capture_spec, nextn=args.nextn)
            payload = {"label": name, "de": rows}
            with open(raw_path, "w") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=1)
            raw[(tag, tier)] = rows
            if tag.startswith("arb"):
                arb_cells[tier].append(rows)
            log(f"[{tag}] c{tier} 完 ({time.time()-t0:.0f}s) agg_all={[r['agg'] for r in rows]} -> {raw_path}")
    summarize(outdir, tiers, arb_cells, raw, args, md5, log, legacy_csv=args.legacy_csv)
    return 0


def summarize(outdir, tiers, arb_cells, raw, args, md5, log, legacy_csv=False):
    anchors = {}
    for kv in args.anchors.split():
        k, _, v = kv.partition(":")
        anchors[int(k)] = float(v) if v not in ("-", "") else None
    tier_rows = []
    for t in tiers:
        m = tier_metrics(arb_cells[t], args.max_tokens)
        anchor = anchors.get(t)
        delta = (round(100.0 * (m["agg_med"] - anchor) / anchor, 1)
                 if (m["agg_med"] is not None and anchor is not None) else None)
        m.update({"tier": t, "anchor": anchor, "delta_pct": delta,
                  "verdict": verdict_of(delta, anchor, args.band_pct),
                  "cells_arb": len(arb_cells[t]),
                  "first_agg": ([r["agg"] for r in raw.get(("first", t), [])] or None),
                  "warm_agg": ([r["agg"] for r in raw.get(("warm", t), [])] or None)})
        tier_rows.append(m)
    # 三档合成判（操作定义见件首；有锚档取最佳+任一红即红；NEW-TIER 只建锚不参赛）
    judged = [r for r in tier_rows if r["anchor"] is not None and r["delta_pct"] is not None]
    new_tier = [r["tier"] for r in tier_rows if r["anchor"] is None]
    best = max(judged, key=lambda r: r["delta_pct"]) if judged else None
    any_red = any(r["verdict"].startswith("RED") for r in tier_rows)
    tri = {"tiers_with_anchor": [r["tier"] for r in judged],
           "deltas_pct": {str(r["tier"]): r["delta_pct"] for r in judged},
           "best_tier": best["tier"] if best else None,
           "best_delta_pct": best["delta_pct"] if best else None,
           "any_red": any_red,
           "new_tier_tiers": new_tier,
           "composite": (("RED(任一有锚档负向超带)" if any_red else
                          ("BEST=c%d %+.1f%%（三档取最佳）" % (best["tier"], best["delta_pct"])
                           if best else "无有锚档"))),
           "note": ("硬守门（KV 池/上下文/GSM8K/位等）优先级高于本面（用户令六-4）；"
                    "判读带数值归各窗 desk 事前冻结，本件只出操作定义与读数")}
    summary = {"schema": SCHEMA_VERSION, "arm_tag": args.arm_tag,
               "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "caliber": {"probe": "sd_bench.run_de（importlib 直载，同一实现）", "sd_md5": md5,
                           "md5_pin": SD_MD5_PIN, "sd_md5_old": SD_MD5_PIN_OLD,
                           "type": DE_TYPE, "max_tokens": args.max_tokens,
                           "runs_per_cell": args.runs, "warmups": args.warmups,
                           "arb_rounds": args.arb_rounds, "base_url": args.base_url,
                           "nextn": args.nextn, "capture_spec": bool(args.capture_spec),
                           "method": ("greedy stream+include_usage；per=(completion−1)/(t_last−t_first)；"
                                      "agg=Σ(completion−1)/(max t_last−min t_first)；c1 时 agg≡per；"
                                      "committed=同式真实提交 token；full_accept_equiv=committed×"
                                      "(1+nextn)/accept_len（副标签，仅与官方/旧表可比）"),
                           "half_speed_law": "DE-CALIBER-VERIFY §3：+1 并发流⇒前台 c1 减半⇒采窗互斥纪律"},
               "band_pct": args.band_pct, "anchors": {str(k): v for k, v in anchors.items()},
               "tiers": tier_rows, "tri_tier": tri,
               "report_rule": ("每档必带 arb_med(agg_med)+spread+per_med+P95/P99+jain/slow_ratio+"
                               "completion 完整性（防单流饿死假读数）；DE 报数必带 maxTokens=400；"
                               "capture-spec 臂另带 accept_len/rate/verified_len/full-accept/committed "
                               "双口径面与 closure 恒等式（附录 D：两口径分列不得互推）")}
    tsv_legacy = (TSV_LEGACY_HEADER, False)
    tsv_dual = (TSV_LEGACY_HEADER + TSV_DUAL_EXTRA, True)
    header, dual = tsv_legacy if legacy_csv else tsv_dual
    tsv = [header]
    for r in tier_rows:
        f = lambda v: "-" if v is None else v
        line = [str(x) for x in (
            r["tier"], f(r["agg_med"]), f(r["agg_spread_pct"]), f(r["per_med"]),
            f(r["stream_p95"]), f(r["stream_p99"]), f(r["stream_min"]),
            f(r["jain_min"]), f(r["slow_ratio_min"]), f(r["early_stop_count"]),
            f(r["anchor"]), f(r["delta_pct"]), r["verdict"])]
        if dual:
            line += [str(x) for x in (
                f(r["committed_agg_med"]), f(r["full_accept_equiv_agg_med"]),
                f(r["accept_len_med"]), f(r["accept_len_p95"]), f(r["accept_rate_med"]),
                f(r["verified_len_med"]), f(r["reasoning_tokens_sum"]),
                "{}/{}".format(r["closure_rows_ok"], r["closure_rows_checked"]))]
        tsv.append("\t".join(line))
    table = "\n".join(tsv)
    print(table)
    with open(os.path.join(outdir, "de48_summary.json"), "w") as fp:
        json.dump(summary, fp, ensure_ascii=False, indent=1)
    with open(os.path.join(outdir, "de48_summary.tsv"), "w") as fp:
        fp.write(table + "\n")
    log(f"summary json/tsv -> {outdir}/de48_summary.{{json,tsv}}；合成判={tri['composite']}"
        + (f"；NEW-TIER 建锚档={new_tier}" if new_tier else ""))
    print("DE48-DONE", outdir)


# ── 自检（纯离线：mock 客户端，零网络零产线触）─────────────────────────────
class FakeClient:
    """确定性假客户端（离线复刻 Client.stream 契约）。速率由 token_step 控制：
    completion=max_tokens（除非 early_stop_for 指定流提前停）。
    T33-03：with_spec=True 时随流返回内部自洽 sglext（γ=5：prop=5·b、
    accepted=gen−b ⇒ accept_len=1+5·rate 恒等成立）。"""

    def __init__(self, rates, base=100.0, early_stop_for=(), with_spec=False):
        self.rates = list(rates)      # 每流速率 t/s（按流序循环取用）
        self.base = base              # t_first 基准
        self.early_stop_for = set(early_stop_for)
        self.with_spec = with_spec    # T33-03 双口径合成面（capture 臂离线自检）

    def stream(self, prompt, max_tokens, temperature=0.0, top_p=1.0,
               extra_body=None, capture_spec=False):
        FakeClient.seq += 1
        # 流序由提示后缀反解 " (stream i/n)"（run_de 的 work(i) 不传线程名）
        idx = None
        if prompt.endswith(")") and " (stream " in prompt:
            tail = prompt.rsplit(" (stream ", 1)[1]
            idx, _ = [int(x) for x in tail[:-1].split("/")]
        rate = self.rates[(idx - 1) % len(self.rates)] if idx is not None \
            else self.rates[(FakeClient.seq - 1) % len(self.rates)]
        completion = 32 if max_tokens == 32 else max_tokens
        if idx is not None and (idx - 1) in self.early_stop_for and max_tokens != 32:
            completion = max_tokens // 2
        t_first = self.base + idx * 0.001 if idx is not None else self.base
        dur = (completion - 1) / rate
        out = {"t_first": t_first, "t_last": t_first + dur, "completion": completion,
               "prompt_tokens": 64, "t_req": t_first - 0.05,
               "reasoning_tokens": 0, "cached_tokens": 0}
        if self.with_spec:
            gen = completion - 1
            b = 100 if completion >= 399 else 8
            out["spec"] = {"spec_verify_ct": b, "spec_num_correct_drafts": gen - b,
                           "spec_num_proposed_drafts": 5 * b,
                           "spec_accept_length": gen / b,
                           "spec_accept_rate": (gen - b) / (5 * b)}
        return out


FakeClient.seq = 0


class BadUsageClient(FakeClient):
    """坏输入：usage 缺失（completion=None）——量具必须因正确理由红。"""

    def stream(self, prompt, max_tokens, temperature=0.0, top_p=1.0):
        if max_tokens == 32:
            return FakeClient.stream(self, prompt, max_tokens, temperature, top_p)
        raise RuntimeError("no visible delta or usage (first=False, completion=None)")


def selfcheck():
    ok = True
    n = {"ran": 0, "fail": 0}   # 计数口径：n=实际执行断言数（权威），W0 手工注记歧义由本行消除

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        n["ran"] += 1
        if not cond:
            n["fail"] += 1
        ok = ok and cond

    sd, md5 = load_sd(os.environ.get("BENCH_REPO", "~/luz-deepseek-flash-all-in-one/tools"), quiet=True)
    need(md5 == SD_MD5_PIN, f"sd_bench md5 钉死（{md5}；钉史 {SD_MD5_PIN_OLD[:8]}…→现钉）")

    # ── 1. 参数校验 ──
    need(set(CANON_TIERS) == {1, 4, 8}, "正典三档=(1,4,8)")
    need(all(t in sd.ALLOWED_CONC for t in CANON_TIERS), "三档均在 sd_bench ALLOWED_CONC 内")
    need(all(t in sd.ALLOWED_CONC for t in (2, 16)) and 7 not in sd.ALLOWED_CONC,
         "ALLOWED_CONC 门语义（16 在、7 不在=扩展位有界）")
    # argparse 级校验在 parse 时执行；此处校验 ladder_plan 纯函数
    plan = ladder_plan([1, 4, 8], 3, 1)
    need([p[0] for p in plan] == ["first", "warm", "warm", "warm", "arb1", "arb2", "arb3"],
         "三步法计划形（A 首发+B 暖重×3+C 仲裁×3）")
    need(plan[4][1] == [1, 4, 8] and plan[5][1] == [4, 8, 1] and plan[6][1] == [8, 1, 4],
         "仲裁轮间档序左旋换位（位置偏差对消）")
    need(ladder_plan([4, 8], 2, 0) == [("arb1", [4, 8]), ("arb2", [8, 4])],
         "免首暖形+两档换位（可裁剪位）")

    # ── 2. 口径断言（c1 同法同语料；importlib 单一事实源）──
    need(sd.DE_PROSE_PROMPT.startswith("Write a detailed step-by-step explanation of how a hash map works"),
         "prose 语料=hash-map essay（c1 正典逐字节，直载 sd_bench 零复制）")
    need(sd.de_prompt("prose", 1) == [sd.DE_PROSE_PROMPT], "prose c1=精确原文（无后缀）")
    need(sd.de_prompt("prose", 4) == [f"{sd.DE_PROSE_PROMPT} (stream {i}/4)" for i in (1, 2, 3, 4)],
         "c4 后缀形态 (stream i/4)（c>1 非code型律）")
    need(len(set(sd.de_prompt("prose", 8))) == 8, "c8 八流互异提示（防前缀缓存共享）")
    need(all(p1 != p2 for p1 in sd.de_prompt("prose", 4) for p2 in sd.de_prompt("prose", 8)),
         "c4/c8 提示集互斥（跨档前缀零共享）")
    need(sd.de_prompt("code", 16) and len(set(sd.de_prompt("code", 16))) == 16,
         "code 型 c16=16 不同任务（同法佐证，本件 prose 钉死不展开）")

    # ── 3. 公式单测（run_de 同一实现直跑：per/agg/c1 恒等）──
    FakeClient.seq = 0
    rows = sd.run_de(FakeClient([80.0]), "prose", 1, 400, 0, 2)
    need(all(abs(r["per"] - 80.0) < 0.01 and abs(r["agg"] - 80.0) < 0.01 for r in rows),
         "c1：per=agg=80（同式退化恒等⇒agg_med 与现锚 88.06 同量同义）")
    FakeClient.seq = 0
    rows4 = sd.run_de(FakeClient([60.0, 60.0, 60.0, 60.0]), "prose", 4, 400, 0, 2)
    need(all(abs(r["per"] - 60.0) < 0.01 for r in rows4) and all(abs(r["agg"] - 240.0) < 0.5 for r in rows4),
         "c4 全等流：per=60/流、agg≈240=4×60（agg=Σct/共同窗）")
    FakeClient.seq = 0
    rows8 = sd.run_de(FakeClient([40.0] * 7 + [20.0]), "prose", 8, 400, 0, 2)
    # 最慢流 20：run 内 per_all=[40×7,20]；agg=Σct/(max t_last − min t_first)=慢流定窗
    exp_agg = round((7 * 399 + 399) / (399 / 20.0 + 0.007), 2)
    need(all(abs(r["agg"] - exp_agg) < 0.5 for r in rows8),
         "c8 含饿死流：agg=慢流定窗（≠流级均值，假读数陷阱在档）")
    need(all(sorted(r["per_all"])[0] == 20.0 for r in rows8), "c8 流级读数保留最慢流（per_all 面）")

    # ── 4. 统计量单测（分位/Jain/slow_ratio/带判）──
    need(pctl_nearest_rank(list(range(1, 101)), 95) == 95 and
         pctl_nearest_rank(list(range(1, 101)), 99) == 99, "nearest-rank P95/P99（100 样本=第 95/99 位）")
    need(pctl_nearest_rank([10, 20, 30, 40], 95) == 40, "小样本 P99/P95 不外插（如实取最大）")
    need(jain([30.0] * 8) == 1.0, "Jain 全等=1.0")
    need(abs(jain([30.0] * 7 + [15.0]) - (7.5 ** 2) / (8 * 7.25)) < 1e-3,
         "Jain 半速单流≈0.9698（手算对表）")
    need(jain([30.0] * 7 + [3.0]) < 0.91, "Jain 饿死流显著<1（判别力）")
    need(slow_ratio([30.0] * 8) == 1.0 and abs(slow_ratio([30.0] * 7 + [15.0]) - 0.5) < 1e-3,
         "slow_ratio：全等=1、半速流=0.5")
    need(verdict_of(0.0, 88.06, 3) == "IN-BAND(±3%)" and verdict_of(-3.0, 88.06, 3) == "IN-BAND(±3%)"
         and verdict_of(3.0, 88.06, 3) == "IN-BAND(±3%)", "带边界含端点（|Δ|=3 仍在带内=电池卡同语义）")
    need(verdict_of(-3.1, 88.06, 3) == "RED(<-band)" and verdict_of(3.1, 88.06, 3) == "OUT-POS(>+%)",
         "超带红/正向出带（红=负向超带）")
    need(verdict_of(None, None, 3) == "NEW-TIER(首跑建锚)", "无锚=NEW-TIER 建锚位")

    # ── 5. 端到端 schema（mock 全管道；零网络）──
    FakeClient.seq = 0
    cells = {t: [sd.run_de(FakeClient([80.0] * t), "prose", t, 400, 0, 2) for _ in range(3)]
             for t in (1, 4, 8)}
    m1, m4, m8 = (tier_metrics(cells[t], 400) for t in (1, 4, 8))
    keys = ("runs_n", "stream_n", "agg_all", "agg_med", "agg_spread_pct", "per_med",
            "stream_p95", "stream_p99", "stream_min", "jain_min", "jain_med",
            "slow_ratio_min", "slow_ratio_med", "completion_min", "early_stop_count")
    need(all(k in m8 and m8[k] is not None for k in keys), "输出 schema 键全（报数规范件）")
    need(m1["jain_min"] is None and m1["slow_ratio_min"] is None,
         "c1 无公平性面（单流恒 None，不造数）")
    need(m8["stream_n"] == 3 * 2 * 8 and m4["stream_n"] == 3 * 2 * 4, "流级池计数（cell×run×流）")
    need(m8["stream_p99"] >= m8["stream_p95"] >= m8["stream_min"], "分位单调 P99≥P95≥min")
    need(m8["early_stop_count"] == 0 and m8["completion_min"] == 400, "completion 完整性（mt400 写满）")
    FakeClient.seq = 0
    starve = [sd.run_de(FakeClient([30.0] * 7 + [3.0]), "prose", 8, 400, 0, 2) for _ in range(3)]
    ms = tier_metrics(starve, 400)
    need(ms["slow_ratio_min"] == 0.1 and ms["jain_min"] < 0.9,
         "饿死形直读：slow_ratio=0.1/Jain<0.9（防单流饿死假读数的判别力面）")
    FakeClient.seq = 0
    estop = [sd.run_de(FakeClient([80.0] * 4, early_stop_for={0}), "prose", 4, 400, 0, 2)]
    me = tier_metrics(estop, 400)
    need(me["early_stop_count"] == 2 and me["completion_min"] == 200,
         "早停计数面（内容窗位移注记位，2 run×1 流=2）")

    # ── 5b. T33-03 Phase 0 双口径（importlib 同源直跑；零网络）──
    FakeClient.seq = 0
    rows_sp = sd.run_de(FakeClient([80.0] * 4, with_spec=True), "prose", 4, 400, 0, 2,
                        capture_spec=True, nextn=5)
    need(all(r["closure"]["identity_sum_completion_eq_generated"] is True
             and r["closure"]["identity_gen_eq_accepted_plus_b"] is True for r in rows_sp),
         "capture 臂闭合：Σ(completion−1)=Σgenerated 且 gen=accepted+b（逐 run）")
    need(all(abs(q["accept_len"] - 3.99) < 1e-6 for r in rows_sp for q in r["per_request"]),
         "合成 accept_len=3.99=1+5×0.598（γ 恒等式同源对表）")
    need(all(abs(r["full_accept_equiv_tps"] - r["committed_decode_tps"] * 6 / 3.99) <= 0.02
             for r in rows_sp),
         "full_accept_equiv=committed×(1+γ)/accept_len（副标签，不得当真实吞吐）")
    m4s = tier_metrics([rows_sp], 400)
    dual_keys = ("committed_agg_med", "full_accept_equiv_agg_med", "accept_len_med",
                 "accept_len_p95", "accept_rate_med", "verified_len_med",
                 "reasoning_tokens_sum", "closure_rows_ok")
    need(all(m4s[k] is not None for k in dual_keys)
         and m4s["closure_rows_ok"] == m4s["closure_rows_checked"] == 2,
         "tier_metrics 双口径键全且闭合 2/2（INV-02 §6.2 字段名）")
    need(m4s["committed_agg_med"] == m4s["agg_med"], "committed_agg_med=agg_med 同式（口径标签面）")
    need(abs(m4s["accept_len_med"] - 3.99) < 1e-6 and abs(m4s["accept_rate_med"] - 0.598) < 1e-6,
         "档级 accept_len/rate 池化对表")
    FakeClient.seq = 0
    rows_old = sd.run_de(FakeClient([80.0] * 4), "prose", 4, 400, 0, 2)
    mo = tier_metrics([rows_old], 400)
    need(all(mo[k] is None for k in ("full_accept_equiv_agg_med", "accept_len_med",
                                     "accept_rate_med", "verified_len_med")),
         "旧形 cell（capture off）：双口径面 None 不造数（不与 spec 臂混比）")
    try:  # capture on 而流不带 sglext = 必红（sd_bench 契约；缺字段不静默）
        FakeClient.seq = 0
        sd.run_de(FakeClient([80.0]), "prose", 1, 400, 0, 1, capture_spec=True)
        need(False, "capture on 缺 sglext 必须红")
    except RuntimeError as e:
        need("sglext" in str(e), f"缺 sglext 红不静默（{str(e)[:40]}…）")
    # --legacy-csv 列面=历史窗档逐字节（有历史档时对拍）
    need(TSV_LEGACY_HEADER.split("\t") == ["tier", "agg_med", "spread%", "per_med", "P95",
                                           "P99", "stream_min", "jain_min", "slow_ratio_min",
                                           "early_stop", "anchor", "Δ%", "verdict"],
         "legacy TSV 头=旧 13 列（冻结形）")
    old_tsv = os.environ.get("DE48_OLD_TSV", "")
    if old_tsv and os.path.isfile(old_tsv):
        first = open(old_tsv).readline().rstrip("\n")
        need(first == TSV_LEGACY_HEADER, f"--legacy-csv 列与历史窗档逐字节同（{old_tsv}）")

    # ── 5c. live summarize TSV 装配路径（W1-A §8-3 回归位常驻：header 曾多包一层 list ⇒
    #    "\n".join(tsv) TypeError，live 首跑即触而 W0 selfcheck 未跑该 join 故漏检。本用例
    #    mock cell 直跑真 summarize()（临时目录，零网络零产线触），bug 复发此处必红）──
    import argparse as _ap
    import contextlib
    import io
    import tempfile

    def _run_summarize(legacy):
        td = tempfile.mkdtemp(prefix="de48-selfcheck-5c-")
        a = _ap.Namespace(arm_tag="selfcheck", anchors="1:88.06", band_pct=3.0,
                          max_tokens=400, runs=2, warmups=0, arb_rounds=1,
                          base_url="http://127.0.0.1:1/v1", nextn=NEXTN_DEFAULT,
                          capture_spec=False)
        with contextlib.redirect_stdout(io.StringIO()):   # 表格进缓冲不污染自检输出
            summarize(td, [1, 4, 8], arb_cells, {}, a, SD_MD5_PIN, lambda m: None,
                      legacy_csv=legacy)
        tsv_txt = open(os.path.join(td, "de48_summary.tsv")).read()
        js = json.load(open(os.path.join(td, "de48_summary.json")))
        return tsv_txt, js

    FakeClient.seq = 0
    arb_cells = {t: [sd.run_de(FakeClient([80.0] * t), "prose", t, 400, 0, 2)]
                 for t in (1, 4, 8)}
    try:
        tsv_d, js = _run_summarize(False)
    except TypeError as e:
        need(False, f"live summarize join 路径通（W1-A §8-3 回归位；复发症状={str(e)[:60]}）")
    else:
        need(True, "live summarize join 路径通（W1-A §8-3 回归位：mock cell 真管道 TSV join）")
        lines_d = tsv_d.rstrip("\n").split("\n")
        need(lines_d[0] == TSV_LEGACY_HEADER + TSV_DUAL_EXTRA
             and all(len(ln.split("\t")) == 21 for ln in lines_d),
             "live TSV 形（默认）：头=13+8 列逐字节、每行 21 列（header/数据列数闭合）")
        need(js.get("schema") == SCHEMA_VERSION
             and [t["tier"] for t in js.get("tiers", [])] == [1, 4, 8],
             "live summary JSON 落盘形（schema/tiers 三档）")
        tsv_l, _ = _run_summarize(True)
        lines_l = tsv_l.rstrip("\n").split("\n")
        need(lines_l[0] == TSV_LEGACY_HEADER
             and all(len(ln.split("\t")) == 13 for ln in lines_l),
             "live TSV 形（--legacy-csv）：头=旧 13 列逐字节、每行 13 列")

    # ── 6. 坏输入必红（判别力纪律；sd_bench canon 形：线程级真因落 stderr，管道零静默出数）──
    try:
        FakeClient.seq = 0
        sd.run_de(BadUsageClient([80.0]), "prose", 1, 400, 0, 1)
        need(False, "坏输入（usage 缺失）必须红")
    except Exception as e:
        need("NoneType" in str(e) or "usage" in str(e) or "subscriptable" in str(e),
             f"坏输入红不静默（{type(e).__name__}；线程级真因 no-usage 落 stderr）")
    try:
        load_sd("/nonexistent-repo", quiet=True)
        need(False, "缺探针件必须红")
    except SystemExit as e:
        need("ABORT" in str(e), "缺探针件红（ABORT 面=参数校验）")

    print("SELFCHECK", "PASS" if ok else "FAIL",
          f"n={n['ran']} fail={n['fail']}",
          "（计数口径：本行 n=实际执行断言数，为权威数；含条件项[DE48_OLD_TSV 设且档在则"
          "触发对拍 +1]，与旧报告手工注记数的口径差由此消除）")
    return 0 if ok else 1


# ── CLI ───────────────────────────────────────────────────────────────────
def main():
    home = os.path.expanduser("~")
    ap = argparse.ArgumentParser(description="DE prose c1/c4/c8 三档正典量测件（mt400 直连口径）")
    ap.add_argument("--arm-tag", default="unknown")
    ap.add_argument("--base-url", default="http://127.0.0.1:8899/v1",
                    help="mt400 直连正典口（电池卡 D3 同口；压测互斥纪律）")
    ap.add_argument("--tiers", type=lambda s: [int(x) for x in s.split(",")],
                    default=list(CANON_TIERS))
    ap.add_argument("--max-tokens", type=int, default=400,
                    help="战役冻结窗口=400（DE 报数必带 maxTokens；跨窗不可比）")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--warmups", type=int, default=2)
    ap.add_argument("--arb-rounds", type=int, default=3)
    ap.add_argument("--first-warm", type=int, default=1, help="A 首发+B 暖重（0=只跑仲裁）")
    ap.add_argument("--anchors", default="1:88.06",
                    help="档:锚；默认 c1=A6-ANCHOR prose 88.06；c4/c8 缺锚=NEW-TIER 建锚")
    ap.add_argument("--band-pct", type=float, default=3.0, help="带判 ±%（DE-1/PR 容忍带先例 3）")
    ap.add_argument("--bench-repo", default=os.environ.get(
        "BENCH_REPO", f"{home}/luz-deepseek-flash-all-in-one/tools"),
        help="sd_bench 所在仓根（找 <repo>/bench/sd_bench.py）。旧默认 ~/dsv41-flash-dgxsparks "
             "已无该文件（目录只剩 logs/），改指交付仓 tools/（md5 钉守口径字节不变）")
    ap.add_argument("--campaign", default=os.environ.get("CAMPAIGN", f"{home}/luz030-opt-campaign"))
    ap.add_argument("--capture-spec", action="store_true",
                    help="T33-03 双口径采集（sd_bench run_de capture_spec；缺 sglext 必红）。"
                         "默认关 ⇒ 请求体逐字节不变，双口径面=None")
    ap.add_argument("--nextn", type=int, default=NEXTN_DEFAULT,
                    help="投机 γ（DSPARK 静态=5）；full_accept_equiv=committed×(1+γ)/accept_len")
    ap.add_argument("--legacy-csv", action="store_true",
                    help="summary TSV/JSON 只出旧 13 列/旧键面（回退兼容；INV-02 §6.9）")
    ap.add_argument("--out-dir")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    # 参数校验（自检外亦守；dry-run 也载探针做 md5/参数核——纯本地零网络）
    if not a.tiers or len(set(a.tiers)) != len(a.tiers):
        return print("tiers 非法（空/重复）", file=sys.stderr) or 2
    sd, sd_md5 = load_sd(a.bench_repo)
    bad = [t for t in a.tiers if t not in sd.ALLOWED_CONC]
    if bad:
        return print(f"tiers {bad} 不在 ALLOWED_CONC", file=sys.stderr) or 2
    if a.runs < 1 or a.warmups < 0 or a.arb_rounds < 1 or a.band_pct <= 0 or a.max_tokens < 1:
        return print("参数越界（runs≥1/warmups≥0/arb≥1/band>0/mt≥1）", file=sys.stderr) or 2
    return measure(a, sd, sd_md5)


if __name__ == "__main__":
    sys.exit(main())
