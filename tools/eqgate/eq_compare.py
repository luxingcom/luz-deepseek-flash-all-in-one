#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R1CERT 跨靴对照判读件（eqgate 正典参数化模板；S-LOCKCLEAN-20261020 卫生窗处结件）。

判读线（desk 判读线冻结律：6/6〔text 逐字 ∧ completion_tokens 相等〕=GREEN；任一不等=红）。
世系件 base 路径硬编码窗路径（S-C13 覆写事故同根）；本件=argv[1] 或 EQ_GATE_DIR 显式传入，
未设即 exit 2 拒跑（fail-closed）。判读逻辑与 S-C13-EXEC-20261018/eqgate/eq_compare.py
逐字节同源，仅路径参数化。

【用法】
  python3 tools/eqgate/eq_compare.py logs/<窗>/eqgate
  EQ_GATE_DIR=logs/<窗>/eqgate python3 tools/eqgate/eq_compare.py
"""
import json, os, sys

d = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("EQ_GATE_DIR", "")
if not d:
    print("[eqgate-compare] RED-ARG：eqgate 目录未指定——argv[1] 或 EQ_GATE_DIR 必须显式传入",
          file=sys.stderr)
    sys.exit(2)
base = d
pre = json.load(open(f"{base}/pre.json"))
post = json.load(open(f"{base}/post.json"))

def pairs(doc):
    out = []
    for r in doc["chats"]:
        out.append((f"chat{r['idx']}", r["text"], r["completion_tokens"]))
    for r in doc["needles"]:
        out.append((f"needle{r['target_tokens']}", r["text"], r["completion_tokens"]))
    return out

P, Q, verdict = pairs(pre), pairs(post), []
for (n1, t1, c1), (n2, t2, c2) in zip(P, Q):
    ok = (t1 == t2) and (c1 == c2)
    verdict.append(ok)
    print(f"{n1}: text_equal={t1 == t2} ct={c1}/{c2} -> {'EQ' if ok else 'DIFF'}")
    if not ok and t1 != t2:
        print(f"  pre  head: {t1[:120]!r}")
        print(f"  post head: {t2[:120]!r}")
n_ok = sum(verdict)
green = (n_ok == 6 == len(verdict))
res = {"n_pairs": len(verdict), "n_equal": n_ok, "verdict": "GREEN" if green else "RED",
       "pairs": [{"name": n, "equal": bool(v)} for (n, _, _), v in zip(P, verdict)]}
json.dump(res, open(f"{base}/eq_verdict.json", "w"), ensure_ascii=False, indent=1)
print(f"EQGATE-VERDICT={'GREEN' if green else 'RED'} ({n_ok}/{len(verdict)})")
sys.exit(0 if green else 1)
