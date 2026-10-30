#!/usr/bin/env python3
"""C1_ACCEPT_CALIBER -- C1③记录级/C1④ DSPARK σ 采样判读侧离线计算器（0 靴纯开发件）。

法源
  * 池件定义 `032-MASTER-TASKLIST-20261016.md` C1 行（EV-07-007）：
    C1③=记录级补采；C1④=DSPARK σ 采样（"GSM8K 级预热后，采样口径固定"）。
  * 任务书 `033-TASKBOOK-V2-20261023.md` §T33-03 验收（恒等式
    `Σ generated = Σ accepted + b`、`accept_len = 1+γ·accept_rate`、客户端-引擎
    闭合）；W4 §5.6 C1④ 行（SCHED_STATS_V1 913 窗 ×4 秩逐窗
    d_accept_len/d_accept_rate/d_accept_base 原始面 = C1④ 天然数据基座）。
  * D17 判据 5 容差（W5 §5）：|raw−visible| ≤ 60 + n_req·k（W5 实测
    k_meas=+4.850/req；W4 离线 k=6.15）。
  * 勘误 `033-W1/SCHED-STATS-IF-ERRATA-20261024.md`（D18）：spec 三列
    （d_spec_steps/d_verified/d_accept_rate）V1 已知缺口——is_target_verify 在
    spec-v2 形引擎恒假 ⇒ 该三列结构性空载；accept 判读用 all 基
    d_accept_len + 派生 rate（(accept_len−1)/γ），口径随输出声明。
  * γ=n−1 语义（W5PREP 任务 1 / W5 §4）：W5 起记录 `gamma` 字段=真 γ
    （DSPARK 5）；W4 旧面（10dce982 前）`gamma` 字段=verify 长度（6=γ+1），
    本计算器按 `--gamma` 显式覆盖并如实标注口径。

性质与红线
  * 纯 stdlib（json/math/re），不 import sglang/torch -- CPU-only 可测。
  * 判读侧离线工具：输入=引擎日志或已提取的 `SCHED_STATS_V1 {json}` 行；
    输出=JSON 摘要（含口径声明块），不回写任何档。
  * 不把派生 accept_rate 冒充 d_accept_rate 直读值；spec 三列结构性空载时
    必须输出 `spec_subset: structurally-null` 提示（勘误 D18 对表）。
"""

from __future__ import annotations

import json
import math
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "extract_records",
    "summarize",
    "closure_check",
    "pctl_nearest_rank",
    "CALIBER_NOTE",
    "main",
]

CALIBER_NOTE = (
    "C1③④ 判读口径（P0 冻结 2026-10-24）：accept 面以 SCHED_STATS_V1 all 基 "
    "d_accept_len 为主量（含 golden，gen=accepted+b 恒等式）；d_accept_rate 直读列在 "
    "spec-v2 形结构性空载（is_target_verify 恒假，见 SCHED-STATS-IF-ERRATA-20261024），"
    "派生 rate=(d_accept_len-1)/γ 仅作 C1④ σ 采样参考列，不作验收线。γ 取 "
    "--gamma 覆盖 > 记录内 gamma 字段（W4 旧面 gamma=verify 长度=γ+1，W5 起为真 γ）；"
    "C1④ 采样时点=GSM8K 级预热后（预热段须以 --warm-after-window 剔除，冷态声明随档）。"
)

_LINE_RE = re.compile(r"SCHED_STATS_V1\s*(\{.*\})\s*$")
_PREFIX_RE = re.compile(r"\[[^\]]*TP(\d+)[^\]]*\]")


def extract_records(text: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """从引擎日志/JSONL 提取 SCHED_STATS_V1 记录；坏行计数不抛（log_prefix 顺带捕获）。"""
    records: List[Dict[str, Any]] = []
    stats = {"lines": 0, "malformed": 0}
    prefix_seen: Dict[str, int] = {}
    for raw in text.splitlines():
        if "SCHED_STATS_V1" not in raw:
            continue
        stats["lines"] += 1
        m = _LINE_RE.search(raw)
        if not m:
            stats["malformed"] += 1
            continue
        try:
            rec = json.loads(m.group(1))
        except json.JSONDecodeError:
            stats["malformed"] += 1
            continue
        if not isinstance(rec, dict) or rec.get("schema") != "sched-stats-v1":
            stats["malformed"] += 1
            continue
        pm = _PREFIX_RE.search(raw[: raw.find("SCHED_STATS_V1")] if "SCHED_STATS_V1" in raw else raw)
        rec["_log_prefix_tp"] = int(pm.group(1)) if pm else None
        prefix_seen[pm.group(1) if pm else "?"] = (
            prefix_seen.get(pm.group(1) if pm else "?", 0) + 1
        )
        records.append(rec)
    stats["prefix_groups"] = prefix_seen
    return records, stats


def pctl_nearest_rank(xs: Sequence[float], q: float) -> Optional[float]:
    """nearest-rank 分位：P_q = sorted[ceil(q/100·n)-1]；空→None（不外插）。"""
    ys = sorted(xs)
    n = len(ys)
    if n == 0:
        return None
    i = math.ceil(q * n / 100.0) - 1
    i = min(max(i, 0), n - 1)
    return float(ys[i])


def _sigma(xs: Sequence[float]) -> Tuple[Optional[float], Optional[float]]:
    """（总体 σ，样本 σ）；n<2 时样本 σ=None。"""
    n = len(xs)
    if n == 0:
        return None, None
    mean = sum(xs) / n
    var_p = sum((x - mean) ** 2 for x in xs) / n
    if n >= 2:
        var_s = sum((x - mean) ** 2 for x in xs) / (n - 1)
        return math.sqrt(var_p), math.sqrt(var_s)
    return math.sqrt(var_p), None


def closure_check(
    engine_total: int,
    client_total: int,
    n_req: int,
    k: float = 6.15,
    base: float = 60.0,
) -> Dict[str, Any]:
    """判据 5 D17 容差闭合（|raw−visible| ≤ 60 + n·k；k 缺省=W4 离线 6.15）。"""
    diff = engine_total - client_total
    band = base + n_req * k
    per_req = diff / n_req if n_req > 0 else None
    return {
        "engine_total_raw": engine_total,
        "client_total_visible": client_total,
        "n_requests": n_req,
        "diff_raw_minus_visible": diff,
        "diff_pct": (diff / client_total * 100.0) if client_total else None,
        "band": band,
        "band_ok": abs(diff) <= band,
        "k_measured_per_req": per_req,
        "caliber": "D17: |raw-visible| <= 60 + n*k (k=W4 offline 6.15 default; "
                   "W5 live k_meas=4.850)",
    }


def summarize(
    records: Sequence[Dict[str, Any]],
    gamma: Optional[int] = None,
    warm_after_window: Optional[int] = None,
) -> Dict[str, Any]:
    """C1③④ 判读指标计算（含口径声明与勘误对表）。

    gamma 语义：None=逐记录用自身 gamma 字段（须一致，否则按记录值并声明混合）；
    显式值=覆盖（W4 旧面 gamma=6 实为 verify 长度时传 --gamma 5 并声明）。
    warm_after_window：C1④ 预热剔除（tot_windows > 该值的窗才进 σ 面）。
    """
    d_windows = [r for r in records if (r.get("d_steps") or 0) > 0]
    accept_lens: List[float] = []
    derived_rates: List[float] = []
    rate_gammas: List[int] = []
    for r in d_windows:
        alen = r.get("d_accept_len")
        if alen is None:
            continue
        accept_lens.append(float(alen))
        g = gamma if gamma is not None else r.get("gamma")
        dr = r.get("d_accept_rate")
        try:
            gi = int(g) if g is not None else 0
        except (TypeError, ValueError):
            gi = 0
        if gi > 0 and dr is None:
            derived_rates.append((float(alen) - 1.0) / gi)
            rate_gammas.append(gi)

    sig_p, sig_s = _sigma(accept_lens)
    sig_pr, _ = _sigma(derived_rates)

    # 转移窗（p_steps>0）vs 稳态窗（p_steps==0 且 d_steps>0）gen/step 分解
    # （W5 §5 方法；W4 离线 +21.0/边界 同构复算位）。
    trans = [r for r in d_windows if (r.get("p_steps") or 0) > 0]
    steady = [r for r in d_windows if (r.get("p_steps") or 0) == 0]
    trans_gs = [
        r["d_gen_tokens"] / r["win_steps"]
        for r in trans
        if r.get("win_steps")
    ]
    steady_gs = [
        r["d_gen_tokens"] / r["win_steps"]
        for r in steady
        if r.get("win_steps")
    ]

    # spec 三列结构性空载检测（勘误 D18 对表）。
    spec_steps_all = [r.get("d_spec_steps") or 0 for r in records]
    spec_null = bool(records) and all(v == 0 for v in spec_steps_all)

    # Σ窗=cum 闭合核对（W5 §5"Σ窗两法核对一致"方法）。
    sum_dgen = sum(r.get("d_gen_tokens") or 0 for r in records)
    last_tot = None
    for r in records:
        if r.get("tot_windows") is not None:
            last_tot = r
    tot_dgen = last_tot.get("tot_d_gen_tokens") if last_tot else None

    # 预热剔除面（C1④）。
    sigma_face = accept_lens
    warm_note = None
    if warm_after_window is not None and last_tot is not None:
        # 逐窗定位：tot_windows 单调，剔除 tot_windows <= warm_after_window 的窗。
        sigma_face = [
            float(r["d_accept_len"])
            for r in d_windows
            if r.get("d_accept_len") is not None
            and (r.get("tot_windows") or 0) > warm_after_window
        ]
        warm_note = {
            "warm_after_window": warm_after_window,
            "windows_in_sigma_face": len(sigma_face),
            "windows_excluded": len(accept_lens) - len(sigma_face),
        }
    sigp4, sigs4 = _sigma(sigma_face)

    ident_bad = sum(1 for r in records if r.get("ident_ok") is False)
    emit_fail_max = max(
        (r.get("emit_fail_tot") or 0 for r in records), default=0
    )
    gammas = sorted({r.get("gamma") for r in records if r.get("gamma") is not None})
    kv_usage = [
        r["kv_usage_pct"] for r in records
        if isinstance(r.get("kv_usage_pct"), (int, float))
    ]
    kv_free = [
        r["kv_free"] for r in records
        if isinstance(r.get("kv_free"), (int, float))
    ]

    gamma_caliber = (
        f"override gamma={gamma}"
        if gamma is not None
        else f"record gamma field (distinct={gammas})"
    )
    return {
        "caliber": CALIBER_NOTE,
        "gamma_caliber": gamma_caliber,
        "n_records": len(records),
        "n_decode_windows": len(d_windows),
        "gamma_distinct": gammas,
        "ident_ok_false_count": ident_bad,
        "emit_fail_tot_max": emit_fail_max,
        "accept_face": {
            "n": len(accept_lens),
            "mean": (sum(accept_lens) / len(accept_lens)) if accept_lens else None,
            "sigma_population": sig_p,
            "sigma_sample": sig_s,
            "min": min(accept_lens) if accept_lens else None,
            "max": max(accept_lens) if accept_lens else None,
            "p50": pctl_nearest_rank(accept_lens, 50),
            "p99": pctl_nearest_rank(accept_lens, 99),
        },
        "derived_accept_rate_face_c1_4": {
            "n": len(derived_rates),
            "gammas_used": sorted(set(rate_gammas)),
            "mean": (sum(derived_rates) / len(derived_rates))
            if derived_rates else None,
            "sigma_population": sig_pr,
            "note": "derived=(d_accept_len-1)/γ; d_accept_rate 直读列 spec-v2 形恒空"
                    "（D18 勘误）；本列不作验收线",
        },
        "spec_subset": (
            "structurally-null: d_spec_steps==0 全程（is_target_verify 恒假，"
            "SCHED-STATS-IF-ERRATA-20261024 D18）"
            if spec_null else "present"
        ),
        "window_class_split": {
            "transition_windows(p_steps>0)": len(trans),
            "transition_gen_per_step": (sum(trans_gs) / len(trans_gs))
            if trans_gs else None,
            "steady_windows": len(steady),
            "steady_gen_per_step": (sum(steady_gs) / len(steady_gs))
            if steady_gs else None,
            "note": "转移窗含 prefill 边界（W4 离线 +21.0/边界、W5 活体 +21.4/边界 同构）",
        },
        "sigma_face_c1_4": sigp4 if warm_after_window is not None else sig_p,
        "sigma_face_c1_4_sample": sigs4 if warm_after_window is not None else sig_s,
        "warm_state": warm_note or {
            "warm_after_window": None,
            "note": "未剔除预热段（C1④ 要求 GSM8K 级预热后采样；随档声明冷态）",
        },
        "totals_closure": {
            "sum_window_d_gen_tokens": sum_dgen,
            "last_tot_d_gen_tokens": tot_dgen,
            "equal": (sum_dgen == tot_dgen) if tot_dgen is not None else None,
        },
        "kv_watch": {
            "kv_usage_pct_max": max(kv_usage) if kv_usage else None,
            "kv_free_min": min(kv_free) if kv_free else None,
        },
    }


def _selfcheck() -> int:
    """--selfcheck：合成面走查（负对照=γ 语义/坏行/恒等式破必须显性）。"""
    checks = 0

    def need(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise SystemExit(f"SELFCHK C1_ACCEPT_CALIBER FAIL: {what}")

    def rec(win, gen, bs, p_steps=0, gamma=5, spec=0, tot=None, alen=None):
        acc = gen - bs
        ver = gamma * bs if gamma > 0 else None
        r = {
            "schema": "sched-stats-v1", "gamma": gamma, "win_steps": win,
            "p_steps": p_steps, "d_steps": win - p_steps,
            "d_gen_tokens": gen, "d_batch_sum": bs, "d_accepted": acc,
            "d_verified": ver, "d_accept_len": (gen / bs) if bs else None,
            # canonical 语义：rate 仅 spec 基出数（all 基=null，W4/W5 实测面同形）。
            "d_accept_rate": (acc / ver) if (ver and spec > 0) else None,
            "d_accept_base": "all" if spec == 0 else "spec",
            "d_spec_steps": spec, "ident_ok": acc >= 0,
            "kv_usage_pct": 99.0, "kv_free": 10000, "emit_fail_tot": 0,
        }
        if tot is not None:
            r["tot_windows"] = win
            r["tot_d_gen_tokens"] = tot
        return r

    # 1) 提取：日志前缀 + 坏行计数。
    text = (
        "[2026-10-24 02:34:52 TP0] SCHED_STATS_V1 {\"schema\":\"sched-stats-v1\","
        "\"gamma\":6,\"win_steps\":4,\"p_steps\":0,\"d_steps\":4,"
        "\"d_gen_tokens\":8,\"d_batch_sum\":4,\"d_accepted\":4,\"d_verified\":null,"
        "\"d_accept_len\":2.0,\"d_accept_rate\":null,\"d_accept_base\":\"all\","
        "\"d_spec_steps\":0,\"ident_ok\":true,\"kv_usage_pct\":98.7,"
        "\"kv_free\":125184,\"emit_fail_tot\":0}\n"
        "SCHED_STATS_V1 not-json\n"
        "SCHED_STATS_V1 {\"schema\":\"other\"}\n"
    )
    recs, st = extract_records(text)
    need(len(recs) == 1 and st["malformed"] == 2, "提取/坏行计数")
    need(recs[0]["_log_prefix_tp"] == 0, "日志前缀 TP 组")

    # 2) 汇总：γ=6 旧面 → --gamma 5 覆盖派生 rate。
    rs = [rec(4, 8, 4, gamma=6), rec(4, 8, 4, gamma=6),
          rec(4, 8, 4, gamma=6, tot=24)]
    s = summarize(rs, gamma=5)
    need(s["accept_face"]["mean"] == 2.0, "accept_len 均值")
    need(abs(s["derived_accept_rate_face_c1_4"]["mean"] - 0.2) < 1e-9,
         "派生 rate=(2-1)/5")
    need(s["gamma_caliber"] == "override gamma=5", "γ 口径声明")
    need(s["totals_closure"]["equal"] is True, "Σ窗=cum 闭合")
    need(s["spec_subset"].startswith("structurally-null"), "spec 空载声明")

    # 3) spec 基形（rate 直读列存在 → 派生面 n=0）。
    r5 = rec(4, 16, 4, gamma=5, spec=4)
    s2 = summarize([r5])
    need(s2["derived_accept_rate_face_c1_4"]["n"] == 0, "直读 rate 在→不派生")
    need(s2["spec_subset"] == "present", "spec 形在场不误报")

    # 4) 转移窗/稳态窗分解（手算闭值）。
    rs3 = [rec(4, 16, 4, p_steps=1), rec(4, 8, 4, p_steps=0)]
    s3 = summarize(rs3)
    need(s3["window_class_split"]["transition_gen_per_step"] == 4.0
         and s3["window_class_split"]["steady_gen_per_step"] == 2.0, "窗类分解")

    # 5) 预热剔除（C1④）。
    rs4 = [rec(4, 8, 4, gamma=5), rec(4, 16, 4, gamma=5)]
    for i, r in enumerate(rs4):
        r["tot_windows"] = i + 1
        r["tot_d_gen_tokens"] = 8 * (i + 1) + 8 * i
    s4 = summarize(rs4, warm_after_window=1)
    need(s4["warm_state"]["windows_excluded"] == 1
         and s4["warm_state"]["windows_in_sigma_face"] == 1, "预热剔除")

    # 6) D17 闭合带（W5 复算值同构：24231 vs 23940, n=60, k=6.15 → +291 带内）。
    c = closure_check(24231, 23940, 60)
    need(c["diff_raw_minus_visible"] == 291 and c["band_ok"], "D17 带复算")
    need(abs(c["k_measured_per_req"] - 4.85) < 1e-9, "k_meas 复算")
    c2 = closure_check(24309, 23940, 60, k=0, base=60)
    need(not c2["band_ok"], "旧 ±60 口径红（W4 +369 形）")

    # 7) 恒等式破显性（ident_ok=false 计数）。
    bad = rec(4, 8, 4)
    bad["ident_ok"] = False
    need(summarize([bad])["ident_ok_false_count"] == 1, "恒等式破计数")

    print(f"SELFCHK C1_ACCEPT_CALIBER ok checks={checks}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selfcheck":
        return _selfcheck()
    if argv and argv[0] == "summarize":
        path = argv[1]
        gamma = warm = None
        rest = argv[2:]
        if "--gamma" in rest:
            gamma = int(rest[rest.index("--gamma") + 1])
        if "--warm-after-window" in rest:
            warm = int(rest[rest.index("--warm-after-window") + 1])
        with open(path, encoding="utf-8", errors="replace") as f:
            recs, st = extract_records(f.read())
        s = summarize(recs, gamma=gamma, warm_after_window=warm)
        s["extract_stats"] = {k: v for k, v in st.items()}
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0
    if argv and argv[0] == "closure":
        kv = {argv[i]: argv[i + 1] for i in range(1, len(argv) - 1, 2)}
        c = closure_check(
            int(kv.get("--engine-total", "0")), int(kv.get("--client-total", "0")),
            int(kv.get("--n-req", "0")),
            float(kv["--k"]) if "--k" in kv else 6.15,
            float(kv["--base"]) if "--base" in kv else 60.0,
        )
        print(json.dumps(c, ensure_ascii=False, indent=2))
        return 0 if c["band_ok"] else 1
    print(__doc__.splitlines()[0])
    print("usage: c1_accept_caliber.py --selfcheck | summarize <file> "
          "[--gamma N] [--warm-after-window N] | closure --engine-total T "
          "--client-total V --n-req N [--k K] [--base B]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
