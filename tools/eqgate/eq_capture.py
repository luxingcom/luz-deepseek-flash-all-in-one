#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R1CERT 口径位等采件（eqgate 正典参数化模板；S-LOCKCLEAN-20261020 卫生窗处结件）。

【为什么存在】eqgate 世系原为窗内副本逐窗手改（logs/<窗>/eqgate/eq_capture.py 第 77 行
  输出路径硬编码窗路径）——2026-10-19 S-C13 窗 pre-卡E 首跑经 CBX1A 窗模板内嵌硬编码路径
  把 WCBOOT71 采件覆写了 CBX1A 窗档 eqgate/pre.json（跨窗原始件覆写事故，S-C13 §四-3）。
  本件=R31-b 前置卫生项「eqgate 模板路径参数化」的处结落位：输出目录一律显式传入
  （argv[3] 或 EQ_GATE_DIR），**未设即拒跑（fail-closed）**——杜绝静默落错窗档。

【与世系件的口径等价性】探针内容与 S-C13-EXEC-20261018/eqgate/eq_capture.py 逐字节同源
  （PORT/SEED/PROMPTS/needle 构造函数零改），仅路径参数化——跨窗位等对照不受影响。

capture SIDE  : 同盐探针 6 对采集（固定 chat prompts×3〔temp=0 逐字+completion_tokens〕
               + needle 三针〔seed 固定 R1EQ2026，answer 逐字+completion_tokens〕）→ <dir>/SIDE.json
compare PRE POST : 跨靴对照——text 逐字相等 ∧ completion_tokens 相等，6/6 判 GREEN。
oracle2     : 靴内 ORACLE 双跑（固定 prompt×2 逐字节等；A6 ORACLE-15 同法）。

【用法】
  EQ_GATE_DIR=logs/<窗>/eqgate python3 tools/eqgate/eq_capture.py capture pre
  python3 tools/eqgate/eq_capture.py capture post logs/<窗>/eqgate      # argv[3]=目录（优先）
  python3 tools/eqgate/eq_capture.py oracle2
环境变量：EQ_GATE_DIR（输出目录；argv[3] 未给时必须设置，缺即 exit 2 拒跑）
"""
import json, os, sys, urllib.request

PORT = 8899
SEED = "R1EQ2026"
PROMPTS = [
    "用恰好三句话说明：为什么重打包桥的消除必须以内核内直读的位等复刻为前提？答案内含数字288。",
    "List exactly four constraints that a grow-only persistent output buffer must satisfy to keep results bit-identical. Number them 1-4.",
    "以恰好两句话解释：转正是工程形态变化而非算法变化，判定证据应当是什么？答案内含词「位等」。",
]

def chat(prompt, max_tokens=96, timeout=300):
    body = json.dumps({"model": "deepseek-v4.1-flash", "temperature": 0,
                       "max_tokens": max_tokens, "messages": [
                           {"role": "user", "content": prompt}]}).encode()
    r = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/chat/completions", data=body,
                               headers={"Content-Type": "application/json"})
    o = json.load(urllib.request.urlopen(r, timeout=timeout))
    c = o["choices"][0]
    return {"text": c["message"]["content"],
            "completion_tokens": (o.get("usage") or {}).get("completion_tokens"),
            "finish_reason": c.get("finish_reason")}

def needle3():
    """needle 三针（固定 seed；答案逐字+completion_tokens）。魔码命中判读另行走 needle_probe 口径。"""
    out = []
    for sz, depth in ((32768, 0.5), (131072, 0.5), (599040, 0.5)):
        p = _needle_prompt(sz, depth)
        r = chat(p, max_tokens=48, timeout=600)
        r["target_tokens"] = sz
        out.append(r)
    return out

def _needle_prompt(target_tokens, depth):
    """与 tools/needle_probe.py 同构：seed 播种伪随机词汤按 chars≈tokens×4 预算 + 中点魔码
    （seed=R1EQ2026 固定盐；WORD 池同源等价——逐字对照只要求同盐同构，两靴同函数即同文本）。"""
    import random
    rng = random.Random(f"{SEED}-{target_tokens}")
    words = ["alpha","bridge","cache","delta","ember","forge","glyph","harbor","index","juxtapose",
             "kernel","lumen","maven","nectar","orbit","pixel","quill","rustic","signal","tundra",
             "umbra","vault","wren","xenon","yonder","zephyr","cascade","drift","echo","flint"]
    header = ("Read the following document carefully. ")
    footer = ("\n\nAfter reading it, answer the final question briefly.\n\n"
              "What is the secret access code hidden in the document? Reply with the code only.")
    needle = f" The secret access code for this document is %08x. Remember it. " % rng.getrandbits(32)
    target_chars = target_tokens * 4 - len(header) - len(footer) - len(needle) - 32
    body, n = [], 0
    while n < target_chars:
        w = words[rng.randrange(len(words))]
        body.append(w)
        n += len(w) + 1
    text = " ".join(body)
    half = int(len(text) * depth)
    return header + text[:half] + needle + text[half:] + footer

def out_dir(argv):
    """输出目录解析：argv[3] 优先，次 EQ_GATE_DIR；两者皆缺=fail-closed 拒跑（防落错窗档）。"""
    d = argv[3] if len(argv) > 3 else os.environ.get("EQ_GATE_DIR", "")
    if not d:
        print("[eqgate] RED-ARG：输出目录未指定——argv[3] 或 EQ_GATE_DIR 必须显式传入"
              "（路径参数化正典律；防跨窗覆写）", file=sys.stderr)
        sys.exit(2)
    os.makedirs(d, exist_ok=True)
    return d

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "oracle2":
        a = chat(PROMPTS[0]); b = chat(PROMPTS[0])
        ok = a["text"] == b["text"]
        print(f"ORACLE-15R {'PASS' if ok else 'FAIL'} | 引擎级双跑逐字节等 | len={len(a['text'])}/{len(b['text'])}")
        sys.exit(0 if ok else 1)
    if mode != "capture":
        print("用法: eq_capture.py capture <pre|post> [outdir] | oracle2（EQ_GATE_DIR 可代 outdir）",
              file=sys.stderr)
        sys.exit(2)
    side = sys.argv[2]
    d = out_dir(sys.argv)
    doc = {"side": side, "seed": SEED, "chats": [], "needles": []}
    for i, p in enumerate(PROMPTS):
        r = chat(p); r["idx"] = i
        doc["chats"].append(r)
    doc["needles"] = needle3()
    path = os.path.join(d, f"{side}.json")
    if os.path.exists(path):
        print(f"[eqgate] RED-ARG：目标件已存在拒覆写 {path}（防跨窗覆写事故复发；"
              "如确需重采先人工移走旧件）", file=sys.stderr)
        sys.exit(2)
    json.dump(doc, open(path, "w"), ensure_ascii=False, indent=1)
    print(f"[eqgate] {side}: 6 探针采毕 → {path}")
    for r in doc["chats"]:
        print(f"  chat{r['idx']}: ct={r['completion_tokens']} head={r['text'][:48]!r}")
    for r in doc["needles"]:
        print(f"  needle{r['target_tokens']}: ct={r['completion_tokens']} head={r['text'][:48]!r}")

if __name__ == "__main__":
    main()
