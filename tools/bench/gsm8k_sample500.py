#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GSM8K 500 题分层采样器（D1/D32 落地；F4-BAKE-PLAN §3.7 案头件）
====================================================================
0 靴纯新增 wrapper：对既有量具（gsm8k_dsv41.py 等）零改动、零 import。
法源：
  D1（DECISIONS-RESOLVED-20261024.md）：seed=20261001 派生分层抽样 500 题；
    不含 20 题冒烟题（固定 sanity 子集单列）；r033/F4 栈执行（r032c 读数不可签 r033）。
  D32（同档第六批）：答案位数×题面长度双维分层 + Random(20261001) + 排除首 20 题。
  F4-BAKE-PLAN-20261025.md §3.7：读 ~/data/gsm8k_test.jsonl（1319 题）→ 排除固定首 20
    （skip=0 连续段，历窗 smoke 同源）→ 余 1299 分层抽 500 → 题号列表 JSON（md5 入档）
    + 抽样日志（各层命中数）。

分层定义（D32；冻结于本件）：
  维度一：金标准答案数值位数桶 {1-2, 3, 4, 5-6, 7+}（gold=answer 尾数，与量具 last_num 同法；
          无数字防御归 1-2 桶）。
  维度二：题面长度（question 字符数）在【排除后抽样框】上的五分位 q1..q5
          （按 (length, qid) 升名次 rank*5//N 定档——确定性，含并列长度）。
  25 层按 (位数桶, 五分位) 名序分配比例配额（最大余数法，并列按层名序），
  层内 random.Random(20261001).sample(升序 qid 池, k)——单 RNG 实例按层序消耗，逐位可复现。

输出（--out-dir，默认 ~/bench-results/gsm8k-sample500/）：
  sample500.jsonl        固定顺序（qid 升序）逐题行：qid/question/answer/gold/stratum/seed
  sample500.qids.json    题号列表（判读可复现；md5 入 F4 报告）
  sample500.summary.json 采样日志：各层命中数/配额、排除记录（0..19）、去重/零交集/边界自检、
                         data/sampler/输出三件 md5、seed 亲缘（seed/frame_id/参数）
--selfcheck：生成 + 扩展自检（含同 seed 重生成逐字节比对）；rc=0 全过。

判读绑定：本样本框读数仅在 r033/F4 栈有效（D1）；20 题冒烟子集单列不混算（§3.7）。
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys

SEED = 20261001            # D1 冻结
NSAMPLE = 500              # D1 冻结
EXCLUDE_FIRST = 20         # D1/D32 冻结：固定首 20 冒烟子集（skip=0 连续段）
FRAME_ID = "gsm8k-sample500-v1"
DEFAULT_DATA = os.path.expanduser("~/data/gsm8k_test.jsonl")
DEFAULT_OUT = os.path.expanduser("~/bench-results/gsm8k-sample500")

DIGIT_BUCKETS = ("d1_2", "d3", "d4", "d5_6", "d7p")


def md5_file(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def last_num(s):
    """与量具 gsm8k_dsv41.py 同法：answer 尾数（千分位逗号剥离）。"""
    s = (s or "").replace(",", "")
    nums = re.findall(r"\d+", s)
    if not nums:
        return None
    try:
        return int(nums[-1])
    except ValueError:
        return None


def digit_bucket(gold):
    """位数桶（D32 维度一）；gold None（无数字）防御归 d1_2。"""
    n = len(str(abs(gold))) if gold is not None else 1
    if n <= 2:
        return "d1_2"
    if n == 3:
        return "d3"
    if n == 4:
        return "d4"
    if n <= 6:
        return "d5_6"
    return "d7p"


def build_frame(rows, seed=SEED, n=NSAMPLE, exclude_first=EXCLUDE_FIRST):
    """读行→排除首段→双维分层→配额→层内抽样；返回 (rows_out, meta)。

    rows_out：qid 升序固定顺序 [{qid,question,answer,gold,stratum,seed}]。
    meta：summary 用全量记账（strata 目标/实抽、排除记录、自检布尔、亲缘）。
    """
    total = len(rows)
    if exclude_first + n > total:
        raise SystemExit(
            f"FATAL: 抽样框不足：total={total} < exclude_first({exclude_first})+n({n})")
    frame = list(range(exclude_first, total))  # 排除固定首段（0..exclude_first-1）
    excluded = list(range(exclude_first))

    golds = {i: last_num(rows[i].get("answer", "")) for i in frame}
    lens = {i: len(rows[i].get("question", "")) for i in frame}

    # 维度一：位数桶
    bucket = {i: digit_bucket(golds[i]) for i in frame}
    # 维度二：题面长度五分位（在排除后抽样框上定档；(length, qid) 升名次 rank*5//N）
    by_len = sorted(frame, key=lambda i: (lens[i], i))
    quint = {}
    for rank, i in enumerate(by_len):
        quint[i] = f"q{rank * 5 // len(frame) + 1}"

    strata = {}
    for i in frame:
        strata.setdefault((bucket[i], quint[i]), []).append(i)
    keys = sorted(strata)  # 层名序（位数桶序 × 五分位序）

    # 比例配额：最大余数法（并列余数按层名序，确定性）
    alloc = {k: n * len(strata[k]) // len(frame) for k in keys}
    rem = n - sum(alloc.values())
    order = sorted(keys, key=lambda k: (-(n * len(strata[k]) % len(frame)), k))
    for k in order[:rem]:
        alloc[k] += 1
    assert sum(alloc.values()) == n

    # 层内抽样：单 RNG 按层名序消耗；层内池按 qid 升序（逐位可复现）
    rng = random.Random(seed)
    picked = []
    for k in keys:
        pool = sorted(strata[k])
        k_n = alloc[k]
        picked.extend(rng.sample(pool, k_n) if k_n else [])
    picked.sort()  # 固定输出顺序=qid 升序

    rows_out = [
        {
            "qid": i,
            "question": rows[i]["question"],
            "answer": rows[i]["answer"],
            "gold": golds[i],
            "stratum": f"{bucket[i]}|{quint[i]}",
            "seed": seed,
        }
        for i in picked
    ]

    # ---- 自校验（分层分布统计、去重、与 20 题零交集、边界）----
    qids = [r["qid"] for r in rows_out]
    checks = {
        "count_is_n": len(qids) == n,
        "no_dup": len(set(qids)) == len(qids),
        "zero_intersect_smoke": not (set(qids) & set(excluded)),
        "qid_in_frame": all(exclude_first <= q < total for q in qids),
        "fixed_order_asc": qids == sorted(qids),
        "alloc_sum": sum(alloc.values()) == n,
    }
    strata_stat = [
        {"stratum": f"{k[0]}|{k[1]}", "pool": len(strata[k]),
         "alloc": alloc[k],
         "hit": sum(1 for q in qids if (bucket[q], quint[q]) == k)}
        for k in keys
    ]
    meta = {
        "frame_id": FRAME_ID,
        "seed": seed,
        "n": n,
        "exclude_first": exclude_first,
        "total_rows": total,
        "frame_size": len(frame),
        "excluded_qids": excluded,
        "strata": strata_stat,
        "checks": checks,
        "lineage": {
            "seed": seed,
            "frame_id": FRAME_ID,
            "stratification": "digit_bucket(question gold last_num) x "
                              "question_length_quintile(post-exclusion frame)",
            "digit_buckets": list(DIGIT_BUCKETS),
            "allocation": "proportional largest-remainder, tie by stratum key order",
            "within_stratum": "random.Random(seed).sample(pool sorted by qid), "
                              "single RNG consumed in stratum key order",
        },
    }
    if not all(checks.values()):
        bad = [k for k, v in checks.items() if not v]
        raise SystemExit(f"FATAL: 自校验未过：{bad}")
    return rows_out, meta


def write_outputs(rows_out, meta, out_dir, data_path):
    os.makedirs(out_dir, exist_ok=True)
    p_jsonl = os.path.join(out_dir, "sample500.jsonl")
    p_qids = os.path.join(out_dir, "sample500.qids.json")
    p_sum = os.path.join(out_dir, "sample500.summary.json")
    with open(p_jsonl, "w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(p_qids, "w", encoding="utf-8") as f:
        json.dump({"frame_id": meta["frame_id"], "seed": meta["seed"],
                   "n": meta["n"], "qids": [r["qid"] for r in rows_out]},
                  f, ensure_ascii=False, indent=1)
        f.write("\n")
    meta["md5"] = {
        "data": md5_file(data_path),
        "sample500.jsonl": md5_file(p_jsonl),
        "sample500.qids.json": md5_file(p_qids),
    }
    meta["sampler"] = os.path.abspath(__file__)
    meta["sampler_md5"] = md5_file(os.path.abspath(__file__))
    with open(p_sum, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return p_jsonl, p_qids, p_sum


def selfcheck(data_path, out_dir, seed, n, exclude_first):
    """生成 + 扩展自检：标准自校验（build_frame 内）+ 同 seed 重生成逐字节比对
    + 改 seed 必异（分层确定性边界）。"""
    rows = [json.loads(l) for l in open(data_path, encoding="utf-8")]
    rows_out, meta = build_frame(rows, seed=seed, n=n, exclude_first=exclude_first)
    p_jsonl, p_qids, p_sum = write_outputs(rows_out, meta, out_dir, data_path)

    ok = True
    # CHECK 1: 标准 checks（build_frame 内已断言，此处复核留痕）
    for k, v in meta["checks"].items():
        print(f"CHECK {k}: {'PASS' if v else 'FAIL'}")
        ok &= bool(v)
    # CHECK 2: 同 seed 重现（逐字节）
    rows_out2, _ = build_frame(rows, seed=seed, n=n, exclude_first=exclude_first)
    same = json.dumps(rows_out, ensure_ascii=False, sort_keys=True) == \
        json.dumps(rows_out2, ensure_ascii=False, sort_keys=True)
    print(f"CHECK same_seed_reproducible: {'PASS' if same else 'FAIL'}")
    ok &= same
    # CHECK 3: 改 seed 必异（同参异种子抽样的确定性差异）
    rows_out3, _ = build_frame(rows, seed=seed + 1, n=n, exclude_first=exclude_first)
    diff = [r["qid"] for r in rows_out] != [r["qid"] for r in rows_out3]
    print(f"CHECK seed_change_changes_draw: {'PASS' if diff else 'FAIL'}")
    ok &= diff
    # CHECK 4: 分层分布记账（各层 hit==alloc、池量总和=frame_size）
    stat_ok = all(s["hit"] == s["alloc"] for s in meta["strata"]) and \
        sum(s["pool"] for s in meta["strata"]) == meta["frame_size"]
    print(f"CHECK strata_accounting: {'PASS' if stat_ok else 'FAIL'}")
    ok &= stat_ok
    # CHECK 5: 每行 seed 亲缘在位（seed/stratum/frame 字段齐）
    lin_ok = all(r["seed"] == seed and r["stratum"] and r["question"] and
                 r["answer"] is not None for r in rows_out)
    print(f"CHECK row_lineage_complete: {'PASS' if lin_ok else 'FAIL'}")
    ok &= lin_ok

    print(f"SELFCHECK RESULT: {'ALL PASS' if ok else 'FAIL'}")
    print(f"out: {p_jsonl}\n     {p_qids}\n     {p_sum}")
    print(f"md5 sample500.jsonl = {meta['md5']['sample500.jsonl']}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=NSAMPLE)
    ap.add_argument("--exclude-first", type=int, default=EXCLUDE_FIRST)
    ap.add_argument("--selfcheck", action="store_true",
                    help="生成 + 扩展自检（同 seed 重现/改 seed 必异/记账/亲缘）")
    args = ap.parse_args()
    data_path = os.path.expanduser(args.data)
    out_dir = os.path.expanduser(args.out_dir)
    if args.selfcheck:
        return selfcheck(data_path, out_dir, args.seed, args.n, args.exclude_first)
    rows = [json.loads(l) for l in open(data_path, encoding="utf-8")]
    rows_out, meta = build_frame(rows, seed=args.seed, n=args.n,
                                 exclude_first=args.exclude_first)
    p_jsonl, p_qids, p_sum = write_outputs(rows_out, meta, out_dir, data_path)
    print(json.dumps({"frame_id": meta["frame_id"], "n": meta["n"],
                      "seed": meta["seed"], "checks": meta["checks"],
                      "jsonl_md5": meta["md5"]["sample500.jsonl"],
                      "out": p_sum}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
