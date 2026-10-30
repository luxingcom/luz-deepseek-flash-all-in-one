# -*- coding: utf-8 -*-
"""GSM8K 500 题分层采样器单测（S0 案头批 2026-10-25；D1/D32/F4-BAKE-PLAN §3.7）.

0 靴纯新增；stdlib-only mock（合成语料，不读真数据/不联网）；
被测件：tools/bench/gsm8k_sample500.py（既有量具零改动的纯新增 wrapper）。
"""
import importlib.util
import json
import math
import os
import sys

import pytest

SAMPLER = os.path.join(os.path.dirname(__file__), "../../tools/bench/gsm8k_sample500.py")
_spec = importlib.util.spec_from_file_location("gsm8k_sample500", SAMPLER)
gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gs)


def make_rows(total=100, seed=7):
    """合成 GSM8K 形语料：题面长度可控变化 + answer 尾数可控位数。"""
    rows = []
    for i in range(total):
        ln = 40 + (i * 37) % 400           # 题面长度确定性变化
        digits = 1 + (i * 13) % 6          # 金答位数 1..6
        gold = int("9" * digits)
        rows.append({
            "question": f"Q{i} " + "x" * ln,
            "answer": f"reasoning ... the answer is {gold:,}",
        })
    return rows


# 1. 分层确定性：同 seed 两次生成逐题全等（qids 与整行均等）
def test_same_seed_reproducible():
    rows = make_rows(200)
    a, ma = gs.build_frame(rows, seed=20261001, n=60, exclude_first=20)
    b, mb = gs.build_frame(rows, seed=20261001, n=60, exclude_first=20)
    assert [r["qid"] for r in a] == [r["qid"] for r in b]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert ma["strata"] == mb["strata"]


# 2. 排除断言：与固定首 20 冒烟子集零交集（D1/D32 硬条件）
def test_excludes_first20_zero_intersection():
    rows = make_rows(200)
    out, meta = gs.build_frame(rows, seed=20261001, n=60, exclude_first=20)
    qids = {r["qid"] for r in out}
    assert not (qids & set(range(20)))
    assert meta["excluded_qids"] == list(range(20))
    assert meta["frame_size"] == 180


# 3. 固定顺序 + 去重 + 计数（输出 qid 升序、无重、数量=配额）
def test_fixed_order_dedup_count():
    rows = make_rows(200)
    out, meta = gs.build_frame(rows, seed=20261001, n=60, exclude_first=20)
    qids = [r["qid"] for r in out]
    assert qids == sorted(qids)
    assert len(set(qids)) == len(qids) == 60
    assert meta["checks"]["fixed_order_asc"] and meta["checks"]["no_dup"]


# 4. 异 seed 必异（同参不同种子的确定性差异；分层确定性不等于跨 seed 相同）
def test_seed_change_changes_draw():
    rows = make_rows(400)
    a, _ = gs.build_frame(rows, seed=20261001, n=100, exclude_first=20)
    b, _ = gs.build_frame(rows, seed=20261002, n=100, exclude_first=20)
    assert [r["qid"] for r in a] != [r["qid"] for r in b]


# 5. 边界：抽样框不足 fail-closed（SystemExit，禁静默缩样）
def test_insufficient_frame_fails_closed():
    rows = make_rows(100)
    with pytest.raises(SystemExit):
        gs.build_frame(rows, seed=1, n=500, exclude_first=20)


# 6. 边界：n==frame 全选（每层 pool==alloc，全帧命中）
def test_exact_fit_full_frame():
    rows = make_rows(100)
    out, meta = gs.build_frame(rows, seed=20261001, n=80, exclude_first=20)
    assert len(out) == 80
    assert all(s["pool"] == s["alloc"] == s["hit"] for s in meta["strata"])
    assert sum(s["pool"] for s in meta["strata"]) == 80


# 7. 分层记账：五分位在排除后抽样框上定档（rank*5//N：N=80 → 每五分位恰 16）
def test_quintile_on_post_exclusion_frame():
    rows = make_rows(100)
    out, meta = gs.build_frame(rows, seed=20261001, n=40, exclude_first=20)
    per_q = {}
    for s in meta["strata"]:
        per_q[s["stratum"].split("|")[1]] = per_q.get(s["stratum"].split("|")[1], 0) + s["pool"]
    assert per_q == {"q1": 16, "q2": 16, "q3": 16, "q4": 16, "q5": 16}
    # 排除段不占层：首 20 行（合成里长度 40..743 变化）不出现在任何层池
    assert sum(s["pool"] for s in meta["strata"]) == 80


# 8. 金答防御：answer 无数字 → gold=None 归 d1_2 桶（不炸、确定性）
def test_gold_none_defensive_bucket():
    rows = make_rows(40)
    rows.append({"question": "QnoNum " + "y" * 100, "answer": "no digits here"})
    out, meta = gs.build_frame(rows, seed=20261001, n=10, exclude_first=0)
    hit = [r for r in out if r["qid"] == 40]
    if hit:  # 抽中才断言桶标签；抽不中则该行必在层池中
        assert hit[0]["stratum"].startswith("d1_2|")
        assert hit[0]["gold"] is None
    else:
        assert any(s["stratum"].startswith("d1_2|") for s in meta["strata"])


# 9. 行亲缘字段齐：每行带 seed/stratum/题/金答（seed 亲缘记录可审计）
def test_row_lineage_complete():
    rows = make_rows(100)
    out, _ = gs.build_frame(rows, seed=20261001, n=30, exclude_first=20)
    for r in out:
        assert r["seed"] == 20261001
        assert r["stratum"] and "|" in r["stratum"]
        assert r["question"] and r["answer"]
        assert r["gold"] is None or isinstance(r["gold"], int)
    # 与量具同法的金答抽取（千分位逗号剥离）
    assert gs.last_num("the answer is 1,234.") == 1234
    assert gs.last_num("no digits") is None


# 10. 位数桶边界（D32 维度一：{1-2,3,4,5-6,7+}）
def test_digit_buckets():
    assert gs.digit_bucket(7) == "d1_2"
    assert gs.digit_bucket(99) == "d1_2"
    assert gs.digit_bucket(100) == "d3"
    assert gs.digit_bucket(999) == "d3"
    assert gs.digit_bucket(1000) == "d4"
    assert gs.digit_bucket(9999) == "d4"
    assert gs.digit_bucket(10000) == "d5_6"
    assert gs.digit_bucket(999999) == "d5_6"
    assert gs.digit_bucket(1000000) == "d7p"
    assert gs.digit_bucket(None) == "d1_2"
