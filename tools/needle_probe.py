#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""needle_probe — 长上下文含针检索最小实现（M0 eval 三件套之一）。

bench/ 仓内无现成 needle 件（已 ls+find 核实 2026-09-30），故按任务书最小实现：
  生成含针的长 prompt + 单问答；PASS = 答中魔码。

口径（与 sd_bench PR random-filler 同哲学，防 Engram 行缓存假命中）：
  - filler = seed 播种伪随机词序列（同 seed 可复现，跨 size/seed 不同文本）
  - needle 句埋在深度中点（depth=0.5），含 8 位十六进制魔码
  - 单问单答：max_tokens 32, temperature 0, 非流式
  - token 估算 ≈4 chars/token（对齐 sd_bench.estimate_tokens）
  - PASS = 回答文本含魔码（大小写不敏感）；HTTP/长度错误 = SKIP（记原因，不算 FAIL）

形态感知门（F-2，2026-10-06 升级，替代 pre-R1 静态 T×L 门）:
  旧门（A22 世系债）：est×4096 行块元素 > 2.0e8 → SKIP（上限 48,828 tok）——pre-R1
  dense 绕行态假设；三现行形态下均失效（R1 服务端准入=600,000 ⇒ ≥64k 被结构性误挡，
  A24DDCOFF 窗 QA 登记升级，READINGS.md OPEN-3）。新门按 --form 放行到各自合法上限；
  未登记形态 fail-closed 按 ≤128k（131072）全局红线（A24DELTA 卡 G1「needle 快检
  ≤128k 阶梯不降档」同源），边界值（==上限）放行。
    r1        = 600,000（AdmissionDecision form=r1 limit=600,000；context_len=600,000，
                CHECKPOINT-LUZ030-R1-20261005.md:17-18）
    dense0731 = 131,072（0731 dense 无 CED：boot_m0731.sh:148/169 --context-length 131072）
    vl        = 131,072（VL 测试线池重裁形：boot_mvl_vlw3b1.sh:218/240 + 池 524288）
    seg600k   = 600,000（E5 裁定②600k 准入形，2026-10-10 登记：0731/VL 两线
                admission_segment 限额 min(600000, 2e8//12)=600,000——E5-ADMISSION-
                600K-CARD-20261010.md §一；Q4 同值同律一次裁定两线受益先例沿
                seg0731/segvl。与 r1 形同值不同键族：r1=产线 V4.1（DSV41_SPARSE_
                LOCAL_ADMISSION*），seg600k=0731/VL 测试线（DSV41_TL_SEGMENT*）。
                600k 加档须显式 --form seg600k（r1 同律），未登记/unknown 仍按
                ≤128k 全局红线 fail-closed）
    unknown   = 131,072（fail-closed 全局红线）

自测（离线，不发包）:
  python3 tools/needle_probe.py --selfcheck   # 构造 prompt 验证尺寸/复现/埋深 + 门判别力
      #（喂 >上限 看拒、喂边界看放行；旧 48,828 假设不再挡 64k 档）
用法:
  python3 tools/needle_probe.py --base http://127.0.0.1:8898 --form r1 \
      --sizes 8192 32768 65536 131072 --json-out logs/<arm>/eval/needle.json
默认档 = 8K/32K/64K/128K 阶梯（G1 同源）；R1 形加档（262144/599040 等）需 --form r1。
水位门缺省 8000M（G1 靴前 MemAvailable≥8G 同源；R1 引擎稳态 head 17-19G 不再误挡，
NEEDLE_WATER_M 可覆盖）。
随形校准律：水位线必须按靴形显式校准后开跑——长上下文/大缓存 idle 形
（MemAvailable 约 6.9-7.5G）设 NEEDLE_WATER_M=6000 档，常规产线形保持缺省 8000。
有效水位线恒记入输出 JSON 的 water_m 字段（窗档判读凭据）；SKIP 行 reason 带实测值
与线值，可直接对表，不要凭残留内存推断。
"""
import argparse
import os
import json
import random
import re
import sys
import time
import urllib.request

WORDS = ("time year people way day man thing woman life child world school state "
         "family student group country problem hand part place case week company "
         "system program question work government number night point home water "
         "room mother area money story fact month lot right study book eye job "
         "word business issue side kind head house service friend father power "
         "hour game line end member law car city community name president team "
         "minute idea kid body information back parent face others level office "
         "door health person art war history party result change morning reason "
         "research girl guy moment air teacher force education foot boy age policy").split()


def estimate_tokens(s: str) -> int:
    return max(1, (len(s) + 3) // 4)  # 对齐 sd_bench.estimate_tokens


# ── F-2 形态感知门（2026-10-06）：按模型/形态放行到各自合法上限 ──
# 证据锚见文件头注；unknown/未登记形态一律 fail-closed 按 ≤128k 全局红线。
FORM_LIMITS = {
    "r1": 600000,         # R1 标准形：admission limit=600,000 = context_len
    "dense0731": 131072,  # 0731 dense 无 CED：ctx 131072
    "seg0731": 65536,     # O13 形（2026-10-06 登记）：0731 线 A7-600K 形
                          # （引擎 capability ctx=600,000，admission_segment 限额
                          # min(65536, 2e8//12)=65536；O13A1-SEG65536 臂）——
                          # 钉=65536（O13-WINCARD §〇 Q4 修订 3：needle 65536=门边界行）
    "segvl": 65536,       # O13B 形（2026-10-06 登记）：VL 线 A7-600K-VL 形
                          # （引擎 capability ctx=600,000，admission_segment 限额
                          # min(65536, 2e8//12)=65536；O13B1-VL-SEG65536 臂）——
                          # 钉=65536 对齐 0731=Q4 同值同律一次裁定两线受益
                          # （O13B-WINCARD §二 K3/port 卡 §六 K3）
    "vl": 131072,         # VL 测试线池重裁形：ctx 131072（池 524288）
    "seg600k": 600000,    # E5 裁定②600k 准入形（2026-10-10 登记）：0731/VL 两线
                          # admission_segment 限额 min(600000, 2e8//12)=600,000
                          # （arms/C-0731-SEG600K.env / C-VL-SEG600K.env 唯键差=
                          # CTX_CAP 65536→600000；E5-ADMISSION-600K-CARD-20261010
                          # §一）——与 r1 同值不同键族（r1=产线 V4.1
                          # DSV41_SPARSE_LOCAL_ADMISSION*；seg600k=测试线
                          # DSV41_TL_SEGMENT*）；600k 档须显式 --form seg600k
}
GLOBAL_LIMIT = 131072     # ≤128k 全局红线（不动）


def resolve_form(form: str, model: str) -> str:
    """--form auto：按模型名判别（vision→vl / 0731→dense0731）；判不出=unknown（红线）。"""
    if form != "auto":
        return form
    m = (model or "").lower()
    if "vision" in m:
        return "vl"
    if "0731" in m:
        return "dense0731"
    return "unknown"


def form_limit(form: str) -> int:
    return FORM_LIMITS.get(form, GLOBAL_LIMIT)


def gate_check(target_tokens: int, form: str):
    """返回 None=放行；否则返回 SKIP 原因。判别力：>上限拒，==上限放行。"""
    lim = form_limit(form)
    if target_tokens > lim:
        why = (f"形态门：form={form} 上限 {lim}，档 {target_tokens} 超限"
               + ("（unknown 按 ≤128k 全局红线 fail-closed；R1 形请显式 --form r1）"
                  if form not in FORM_LIMITS else ""))
        return why
    return None


def make_filler(seed: str, target_tokens: int) -> str:
    rng = random.Random(f"needle:{seed}")
    out, n = [], 0
    target_chars = target_tokens * 4
    while n < target_chars:
        w = WORDS[rng.randrange(len(WORDS))]
        out.append(w)
        n += len(w) + 1
    return " ".join(out)


def build_prompt(target_tokens: int, seed: str, depth: float = 0.5):
    """返回 (prompt, magic)。魔码句埋在 depth 比例处。"""
    rng = random.Random(f"magic:{seed}")
    magic = "%08x" % rng.getrandbits(32)
    header = (f"[needle-probe {seed}]\nBelow is a long document. "
              "After reading it, answer the final question briefly.\n\n")
    footer = ("\n\nQuestion: What is the magic code hidden in the document above? "
              "Answer with the code only.")
    needle = f"\nThe magic code for this session is {magic}. Remember it.\n"
    fill_tokens = max(1, target_tokens - estimate_tokens(header + footer + needle) - 8)
    body = make_filler(seed, fill_tokens)
    cut = int(len(body) * depth)
    prompt = header + body[:cut] + needle + body[cut:] + footer
    return prompt, magic


def ask(base: str, prompt: str, model: str, max_tokens: int = 32, timeout: int = 600):
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.loads(r.read().decode())
    txt = obj["choices"][0]["message"].get("content") or ""
    ct = (obj.get("usage") or {}).get("completion_tokens", 0)
    pt = (obj.get("usage") or {}).get("prompt_tokens", 0)
    return txt, pt, ct, time.time() - t0


def probe(base, model, target_tokens, seed, depth):
    prompt, magic = build_prompt(target_tokens, seed, depth)
    est = estimate_tokens(prompt)
    try:
        txt, pt, ct, dt = ask(base, prompt, model)
    except Exception as e:  # noqa: BLE001
        return {"target_tokens": target_tokens, "est_tokens": est, "magic": magic,
                "status": "SKIP", "pass": False, "error": str(e)[:200]}
    hit = magic.lower() in (txt or "").lower()
    resp = re.sub(r"\s+", " ", (txt or ""))[:80]
    return {"target_tokens": target_tokens, "est_tokens": est, "magic": magic,
            "prompt_tokens": pt, "completion_tokens": ct, "elapsed_s": round(dt, 2),
            "answer_head": resp, "status": "PASS" if hit else "FAIL", "pass": hit}


def selfcheck():
    ok = True

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        ok = ok and cond

    p1, m1 = build_prompt(30720, "sc1")
    p2, m2 = build_prompt(30720, "sc1")
    need(p1 == p2, "同 seed 可复现")
    p3, _ = build_prompt(30720, "sc2")
    need(p1 != p3, "跨 seed 不同文本")
    need(29500 <= estimate_tokens(p1) <= 31500, f"30K 档覆盖({estimate_tokens(p1)} tok)")
    p4, m4 = build_prompt(229376, "sc4")
    need(228000 <= estimate_tokens(p4) <= 231000, f"229K 档覆盖({estimate_tokens(p4)} tok)")
    p5, _ = build_prompt(470528, "sc5")
    need(469000 <= estimate_tokens(p5) <= 472000, f"470K 档覆盖({estimate_tokens(p5)} tok)")
    for tgt in (30720, 229376, 470528):
        p, m = build_prompt(tgt, "depth")
        needle_pos = p.index("The magic code")
        depth = needle_pos / len(p)
        need(0.4 <= depth <= 0.6, f"{tgt} 档埋深≈中点({depth:.2f})")
    need(re.fullmatch(r"[0-9a-f]{8}", m1) is not None, "魔码为 8 位 hex")
    # ── F-2 形态感知门判别力自检（喂 >上限 看拒、喂边界看放行）──
    for f, lim in (("r1", 600000), ("dense0731", 131072), ("seg0731", 65536),
                   ("segvl", 65536), ("vl", 131072), ("seg600k", 600000),
                   ("unknown", 131072)):
        need(gate_check(lim, f) is None, f"门边界放行：{f} =={lim}")
        need(gate_check(lim + 1, f) is not None
             and "超限" in gate_check(lim + 1, f), f"门超限拒：{f} {lim + 1}")
    need(gate_check(599040, "r1") is None, "r1 形 599040 档放行（旧 T×L 门曾误挡）")
    need(gate_check(65536, "r1") is None, "64k 档 r1 放行（≥64k 不再结构性挡）")
    need(gate_check(470528, "unknown") is not None, "unknown 形 470K 档拒（红线 fail-closed）")
    need(form_limit("no-such-form") == GLOBAL_LIMIT, "未登记形态按全局红线")
    need(resolve_form("auto", "deepseek-v4-flash-vision-exp") == "vl", "auto 判别 vision→vl")
    need(resolve_form("auto", "dspark-0731-w3") == "dense0731", "auto 判别 0731")
    need(resolve_form("auto", "deepseek-v4.1-flash") == "unknown", "auto 判不出→unknown（fail-closed）")
    p6, _ = build_prompt(599040, "sc6")  # r1 边界档实际构造（离线只构造不发包）
    need(estimate_tokens(p6) <= 600000, f"r1 边界档构造 est({estimate_tokens(p6)})≤600000")
    try:
        ask("http://127.0.0.1:1", "x", "m", timeout=2)
        need(False, "坏端点必须红")
    except Exception as e:
        need("Connection" in type(e).__name__ or "connection" in str(e).lower(),
             f"坏端点红（{type(e).__name__}）")
    print("SELFCHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8898")
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--form", default="auto",
                    choices=["auto", "r1", "dense0731", "seg0731", "segvl", "vl",
                             "seg600k", "unknown"],
                    help="形态感知门键（auto=按模型名判别，判不出按 ≤128k 红线；"
                         "R1 形 600k 档必须显式 --form r1；O13 seg0731=65536；O13B VL 形 segvl=65536；"
                         "E5 600k 准入形（0731/VL）须显式 --form seg600k=600,000）")
    ap.add_argument("--sizes", type=int, nargs="+",
                    default=[8192, 32768, 65536, 131072],
                    help="token 档（默认 8K/32K/64K/128K 阶梯，G1 同源）")
    ap.add_argument("--depth", type=float, default=0.5)
    ap.add_argument("--seed", default=None, help="默认=按日期固定（跨臂可复现）")
    ap.add_argument("--json-out")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    seed = a.seed or time.strftime("needle-%Y%m%d")
    form = resolve_form(a.form, a.model)
    limit = form_limit(form)
    # F-2（2026-10-06）：形态感知门（替代 F-1 pre-R1 静态 T×L 门 est×4096>2e8——
    #   48,828 上限为 dense 绕行态假设，A24DDCOFF OPEN-3 登记）。
    #   按形态放行合法上限；≤128k（131072）全局红线不动。
    # 水位门：head MemAvailable < 水线 → SKIP（盘读/瞬态余量不足）。
    #   缺省 8000M=G1 靴前 MemAvailable≥8G 同源（旧缺省 20000M 低于 R1 引擎稳态
    #   17-19G 会全档误挡，READINGS OPEN-3；NEEDLE_WATER_M 可覆盖）。
    WATER_M = int(os.environ.get("NEEDLE_WATER_M", "8000"))
    rows = []
    for s in a.sizes:
        why = gate_check(s, form)
        if why:
            rows.append({"target_tokens": s, "form": form, "status": "SKIP",
                         "reason": why})
            print(f"[needle] SKIP {s}（{why}）", flush=True)
            continue
        try:
            memavail = int(next(l for l in open("/proc/meminfo")
                                if l.startswith("MemAvailable")).split()[1]) // 1024
        except Exception:
            memavail = -1
        if 0 < memavail < WATER_M:
            rows.append({"target_tokens": s, "status": "SKIP",
                         "reason": f"水位门：MemAvailable={memavail}M < {WATER_M}M"})
            print(f"[needle] SKIP {s}（水位门 MemAvail={memavail}M）", flush=True)
            continue
        rows.append(probe(a.base, a.model, s, f"{seed}-{s}", a.depth))
    # gate 语义：任一 FAIL → False；全 SKIP → False（无证据不得放行）；其余 True
    out = {"seed": seed, "base": a.base, "form": form, "form_limit": limit,
           "water_m": WATER_M,
           "rows": rows,
           "n_pass": sum(1 for r in rows if r["status"] == "PASS"),
           "n_fail": sum(1 for r in rows if r["status"] == "FAIL"),
           "n_skip": sum(1 for r in rows if r["status"] == "SKIP"),
           "gate_pass": (not any(r["status"] == "FAIL" for r in rows)
                         and not all(r["status"] == "SKIP" for r in rows))}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.json_out:
        open(a.json_out, "w").write(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
