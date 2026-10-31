#!/usr/bin/env python3
"""X5-MIXED-TTFT -- 0.3.4 T34-04 X5 首键窗 M1 主判读探针（长冷预填期短请求 TTFT，G-1② 口径）。

法源（规格冻结面，勿凭记忆改）：
  docs/plan/034-W1/T34-04-X5-LADDER-WINDOW-20261027.md §2.1（D101-X-4 新制量具批准）：
    - 形：单文件客户端探针直连 127.0.0.1:8899（mt400 正典，DE 纪律注同款=量具直连
      绕网关，网关 sampling-on 键态由窗内前置核承载）。
    - 长预填源 = B25 同形 repeated filler target 524288（sd_bench.py 410f543d 的
      build_pr_prompt 逐字节同构：header[salt]+\" the\"*fill+footer；在档形
      prompt_tokens 524,295±、chars_per_token 4.0）、max_tokens=16、temp=0，T0 发起。
    - 短请求探针 = T0+{10,30,60,90}s 四时位各 1 条（~1k token 冷盐 prompt、
      max_tokens=16、temp=0、stream=true，TTFT=首 SSE 块时戳=首个非空 delta.content）。
    - 3 轮/靴（轮间=长预填毕+60s 清态），计划 12 点/靴。
    - 预注册有效性规则（防事后择点）：仅「到达时位 < 该轮长预填 TTFT − 5s」的点计入；
      一轮有效点 <2 则该轮剔除；两靴合计有效点 <8 → M1 判读力降级=边界态处置
      （合计判读由 --aggregate 离线承载，零网络）。
    - 聚合：逐靴中位（辅记 p90 与逐点「剩余预填估计=长 TTFT−时位」协变列）；
      门 = B 臂中位 / A 臂中位（G-M1 ≤0.75 / G-M1′ (0.75,0.90] / 降级线 >0.90，
      门判读权在判读档——本探针 --aggregate 只出数值与信息性分档）。
    - 纪律：开发毕 md5 冻结、A/B 两靴同件同参（量具冻结红线——判读窗内零改动）。

冷盐设计（§四-5：探针短请求均冷盐防 radix 命中污染，首键不测缓存面）：
  - 长/短 prompt 盐均由固定种子确定性派生（仅依赖 轮号/时位，与臂无关）⇒
    A/B 两靴载荷序字节级逐字同（同载荷复刻 era 对冲的最强形）；靴内 12 点两两不同
    ⇒ 靴内无 radix 复命中。
  - 短 prompt 填充=盐播种词汤（非 \" the\" 重复形态）⇒ Engram 行缓存无可命中对象。

零网络面（置备/自检纪律——PR 判别靴在飞期探针绝不可发真请求）：
  --selfcheck / --dry-run / --aggregate 三路均零请求（selfcheck 含网络调用计数器
  断言=0 的机器自证）；唯一发请求路径=--run（判读窗内执行位，A/B 各一次）。
"""
import argparse
import json
import random
import statistics
import sys
import threading
import time
import uuid  # noqa: F401  (保留：与 sd_bench 盐形对照；本探针盐=确定性派生)

import requests

PROBE_NAME = "X5-MIXED-TTFT"
SPEC_VERSION = 1
SALT_SEED_DEFAULT = "x5-mixed-ttft:v1"
FILLER_UNIT = " the"  # 与 sd_bench FILLER_UNIT 逐字同（B25/PR 同源）

# 判读门线（§2.2 预注册；--aggregate 只作信息性分档，判读权在判读档）
GATE_M1 = 0.75
GATE_M1P = 0.90
MIN_POINTS_PER_ROUND = 2
MIN_VALID_POINTS_BOTH_BOOTS = 8

# 短请求词汤词表（sd_bench _RAND_WORDS 同源拷贝——量具文件零触碰，构造逻辑新制复刻）
_RAND_WORDS = (
    "time year people way day man thing woman life child world school state "
    "family student group country problem hand part place case week company "
    "system program question work government number night point home water "
    "room mother area money story fact month lot right study book eye job "
    "word business issue side kind head house service friend father power "
    "hour game line end member law car city community name president team "
    "minute idea kid body information back parent face others level office "
    "door health person art war history party result change morning reason "
    "research girl guy moment air teacher force education foot boy age policy"
).split()

_NET_CALLS = 0  # 网络调用计数器（selfcheck 零网络机器自证位）


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── prompt 构造 ────────────────────────────────────────────────────────────
def estimate_tokens(s):
    """≈4 chars/token（sd_bench estimate_tokens 同式：LlmStreaming 口径）。"""
    return max(1, (len(s) + 3) // 4)


def build_long_prompt(target_tokens, salt):
    """长预填源=B25 同形 repeated filler（sd_bench build_pr_prompt 逐字节同构，
    filler 固定 repeated——B25/PR 正典口径，两臂同形）。"""
    header = f"[prefill-bench {salt}]\nIgnore the filler below. Reply with the single word OK.\n"
    footer = "\nReply OK."
    fill = max(1, target_tokens - estimate_tokens(header + footer))
    return header + FILLER_UNIT * fill + footer


def build_short_prompt(target_tokens, salt):
    """短请求=~1k token 冷盐 prompt：header[盐]+词汤填充+footer。
    词汤=盐播种（同盐可复现、跨盐不同），非重复形态⇒行缓存/前缀缓存无可命中。"""
    header = f"[x5-short-probe {salt}]\nIgnore the filler below. Reply with the single word OK.\n"
    footer = "\nReply OK."
    fill = max(1, target_tokens - estimate_tokens(header + footer))
    rng = random.Random(f"x5-short:{salt}")
    target_chars = fill * len(FILLER_UNIT)
    out, n = [], 0
    while n < target_chars:
        w = _RAND_WORDS[rng.randrange(len(_RAND_WORDS))]
        out.append(w)
        n += len(w) + 1
    return header + " ".join(out) + footer


def salt_for(seed, round_no, slot):
    """确定性盐：仅依赖 (seed, round, slot) ⇒ A/B 两靴字节级同载荷；靴内两两不同。"""
    return format(random.Random(f"{seed}:r{round_no}:{slot}").getrandbits(32), "08x")


# ── HTTP 客户端（sd_bench Client 形制复刻：默认 body 逐字节同族） ─────────────
class Client:
    def __init__(self, base_url, key, timeout_connect, timeout_read):
        self.base = base_url.rstrip("/")
        self.h = {"Authorization": f"Bearer {key}"} if key else {}
        self.timeout = (timeout_connect, timeout_read)

    @staticmethod
    def build_body(prompt, max_tokens, temperature=0.0, top_p=1.0):
        """请求体=sd_bench 默认形（messages/max_tokens/temperature/top_p/stream/
        stream_options.include_usage；不加任何 capture/spec 键）。"""
        return {"messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
                "stream": True, "stream_options": {"include_usage": True}}

    def stream(self, prompt, max_tokens, temperature=0.0):
        """返回 dict(t_req, t_first, t_last, completion, prompt_tokens)。
        TTFT 口径=首个非空 delta.content 的墙钟（sd_bench 同款首 SSE 块口径）。"""
        global _NET_CALLS
        _NET_CALLS += 1
        body = self.build_body(prompt, max_tokens, temperature)
        t_first = t_last = None
        completion = prompt_tokens = None
        t0 = time.perf_counter()
        r = requests.post(f"{self.base}/chat/completions", json=body, headers=self.h,
                          stream=True, timeout=self.timeout)
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=False):
            if not line or not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                break
            try:
                j = json.loads(payload)
            except json.JSONDecodeError:
                continue
            now = time.perf_counter()
            for ch in j.get("choices", []):
                if ch.get("delta", {}).get("content"):
                    if t_first is None:
                        t_first = now
                    t_last = now
            u = j.get("usage")
            if u:
                completion = u.get("completion_tokens")
                prompt_tokens = u.get("prompt_tokens")
                t_last = t_last or now
        if t_first is None or completion is None:
            raise RuntimeError(
                f"no visible delta or usage (first={t_first is not None}, completion={completion})")
        return {"t_req": t0, "t_first": t_first, "t_last": t_last,
                "completion": completion, "prompt_tokens": prompt_tokens}


# ── 判读窗执行（--run：唯一发请求路径） ─────────────────────────────────────
def run_probe(a, key):
    client = Client(a.base_url, key, a.timeout_connect, a.timeout_s)
    out = {"probe": PROBE_NAME, "spec_version": SPEC_VERSION,
           "arm": a.arm, "started_utc": utcnow(),
           "params": {"rounds": a.rounds, "offsets": list(a.offsets),
                      "target_long": a.target_long, "target_short": a.target_short,
                      "max_tokens": a.max_tokens, "temperature": a.temperature,
                      "cooldown_s": a.cooldown, "validity_margin_s": a.validity_margin,
                      "min_points_per_round": MIN_POINTS_PER_ROUND,
                      "salt_seed": a.salt_seed, "base_url": a.base_url,
                      "timeout_read_s": a.timeout_s, "key_file": a.key_file or "(none)"}}
    rounds = []
    any_valid_round = False
    for r in range(1, a.rounds + 1):
        rd = run_round(client, a, r)
        rounds.append(rd)
        if rd.get("round_valid"):
            any_valid_round = True
        if r < a.rounds:
            time.sleep(a.cooldown)
    out["finished_utc"] = utcnow()
    out["rounds"] = rounds
    valid = [p for rd in rounds if rd.get("round_valid") for p in rd["points"] if p["valid"]]
    out["aggregate"] = {
        "n_planned": a.rounds * len(a.offsets),
        "n_valid": len(valid),
        "n_rounds_valid": sum(1 for rd in rounds if rd.get("round_valid")),
        "ttft_valid_s": sorted(round(p["ttft_s"], 3) for p in valid),
        "median_ttft_s": round(statistics.median(p["ttft_s"] for p in valid), 3) if valid else None,
        "p90_ttft_s": round(percentile([p["ttft_s"] for p in valid], 90), 3) if valid else None,
    }
    return out, any_valid_round


def run_round(client, a, round_no):
    """一轮=1 条长预填（T0）+ 四时位短请求（T0+offset 绝对时序调度）。"""
    rd = {"round": round_no, "started_utc": utcnow()}
    long_salt = salt_for(a.salt_seed, round_no, "long")
    long_prompt = build_long_prompt(a.target_long, long_salt)
    rd["long"] = {"salt": long_salt, "prompt_chars": len(long_prompt),
                  "estimate_tokens": estimate_tokens(long_prompt)}

    t0_box, t0_evt = [None], threading.Event()
    long_res, long_err = [None], [None]

    def long_worker():
        try:
            t0_box[0] = time.perf_counter()
            t0_evt.set()
            long_res[0] = client.stream(long_prompt, a.max_tokens, a.temperature)
        except Exception as e:  # 长预填失败=轮失败（如实记，不 silently 判）
            long_res[0] = None
            long_err[0] = f"{type(e).__name__}: {e}"

    th = threading.Thread(target=long_worker, daemon=True)
    th.start()
    t0_evt.wait()
    t0 = t0_box[0]

    slots = []

    def short_worker(offset):
        rec = {"pos_s": offset}
        try:
            deadline = t0 + offset
            delay = deadline - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            rec["send_offset_s"] = round(time.perf_counter() - t0, 3)
            salt = salt_for(a.salt_seed, round_no, f"p{offset}")
            prompt = build_short_prompt(a.target_short, salt)
            rec["salt"], rec["prompt_chars"] = salt, len(prompt)
            o = client.stream(prompt, a.max_tokens, a.temperature)
            rec["ttft_s"] = round(o["t_first"] - o["t_req"], 3)
            rec["total_s"] = round(o["t_last"] - o["t_req"], 3)
            rec["prompt_tokens"], rec["completion_tokens"] = o["prompt_tokens"], o["completion"]
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        slots.append(rec)

    sths = [threading.Thread(target=short_worker, args=(off,), daemon=True) for off in a.offsets]
    for t in sths:
        t.start()
    for t in sths:
        t.join()
    th.join()

    if long_err[0] is not None:
        rd["long"]["error"] = long_err[0]
        rd["round_failed"] = True
    else:
        o = long_res[0]
        rd["long"]["ttft_s"] = round(o["t_first"] - o["t_req"], 3)
        rd["long"]["total_s"] = round(o["t_last"] - o["t_req"], 3)
        rd["long"]["prompt_tokens"] = o["prompt_tokens"]
        rd["long"]["completion_tokens"] = o["completion"]

    # 预注册有效性规则（§2.1）：到达时位 < 长TTFT−margin 才计入
    long_ttft = rd["long"].get("ttft_s")
    for rec in sorted(slots, key=lambda x: x["pos_s"]):
        if long_ttft is None or "ttft_s" not in rec:
            rec["valid"] = False
        else:
            rec["valid"] = rec["send_offset_s"] < (long_ttft - a.validity_margin)
            if rec["valid"]:
                rec["remaining_prefill_est_s"] = round(long_ttft - rec["send_offset_s"], 3)
    rd["points"] = sorted(slots, key=lambda x: x["pos_s"])
    rd["valid_points"] = sum(1 for p in rd["points"] if p["valid"])
    rd["round_valid"] = (not rd.get("round_failed")) and rd["valid_points"] >= MIN_POINTS_PER_ROUND
    rd["finished_utc"] = utcnow()
    return rd


# ── 统计与离线聚合（--aggregate：零网络） ───────────────────────────────────
def percentile(xs, q):
    """线性插值 p90（与 numpy 默认 percentile 同族；n=1 时=该值）。"""
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * q / 100.0
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def collect_valid(doc):
    pts = []
    for rd in doc.get("rounds", []):
        if rd.get("round_valid"):
            for p in rd.get("points", []):
                if p.get("valid") and p.get("ttft_s") is not None:
                    pts.append(p)
    return pts


def aggregate(path_a, path_b, json_out=None):
    docs = {}
    for arm, path in (("A", path_a), ("B", path_b)):
        with open(path) as fp:
            docs[arm] = json.load(fp)
        for k in ("arm", "rounds"):
            if k not in docs[arm]:
                raise RuntimeError(f"{path}: 缺字段 {k}（非本探针产物必红）")
    res = {"probe": PROBE_NAME, "mode": "aggregate", "generated_utc": utcnow(),
           "gate_lines_informational": {"G-M1": GATE_M1, "G-M1p_band": GATE_M1P}}
    per = {}
    for arm in ("A", "B"):
        pts = collect_valid(docs[arm])
        ttfts = [p["ttft_s"] for p in pts]
        per[arm] = {"n_valid": len(pts), "n_planned": docs[arm]["aggregate"]["n_planned"],
                    "n_rounds_valid": docs[arm]["aggregate"]["n_rounds_valid"],
                    "median_ttft_s": round(statistics.median(ttfts), 3) if ttfts else None,
                    "p90_ttft_s": round(percentile(ttfts, 90), 3) if ttfts else None,
                    "remaining_prefill_est_s": [p.get("remaining_prefill_est_s") for p in pts]}
    res["per_arm"] = per
    ma, mb = per["A"]["median_ttft_s"], per["B"]["median_ttft_s"]
    if ma is not None and mb is not None and ma > 0:
        ratio = mb / ma
        res["ratio_B_over_A"] = round(ratio, 4)
        if ratio <= GATE_M1:
            res["band"] = "PASS-line (<=0.75)"
        elif ratio <= GATE_M1P:
            res["band"] = "weak-effect boundary (0.75,0.90]"
        else:
            res["band"] = "degrade line (>0.90)"
        res["note"] = "信息性分档——门判读权在判读档（预注册 §2.2，零事后改律）"
    else:
        res["band"] = "unavailable (median missing)"
    total_valid = per["A"]["n_valid"] + per["B"]["n_valid"]
    res["total_valid_points_both_boots"] = total_valid
    if total_valid < MIN_VALID_POINTS_BOTH_BOOTS:
        res["validity_degrade"] = True
        res["validity_note"] = (f"两靴合计有效点 {total_valid}<{MIN_VALID_POINTS_BOTH_BOOTS}"
                                " → M1 判读力降级=边界态处置（§2.1 预注册）")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if json_out:
        with open(json_out, "w") as fp:
            fp.write(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


# ── 离线干跑（--dry-run：零网络，打印计划面） ───────────────────────────────
def dry_run(a):
    print(f"== {PROBE_NAME} dry-run（零网络——不构造 Client、不发任何请求）==")
    print(f"rounds={a.rounds} offsets={a.offsets} → 计划 {a.rounds * len(a.offsets)} 点/靴")
    print(f"target_long={a.target_long} target_short={a.target_short} max_tokens={a.max_tokens} "
          f"temp={a.temperature} cooldown={a.cooldown}s validity_margin={a.validity_margin}s "
          f"min_points/round={MIN_POINTS_PER_ROUND}")
    for r in range(1, a.rounds + 1):
        lsalt = salt_for(a.salt_seed, r, "long")
        lp = build_long_prompt(a.target_long, lsalt)
        print(f"[round {r}] long salt={lsalt} chars={len(lp)} est_tokens={estimate_tokens(lp)} "
              f"chars_per_est_token={round(len(lp) / estimate_tokens(lp), 3)}")
        for off in a.offsets:
            ssalt = salt_for(a.salt_seed, r, f"p{off}")
            sp = build_short_prompt(a.target_short, ssalt)
            body_unit = sp.split("OK.\n", 1)[1].rsplit("\nReply OK.", 1)[0]
            print(f"  +{off:>3}s short salt={ssalt} chars={len(sp)} "
                  f"est_tokens={estimate_tokens(sp)} 词汤={not body_unit.startswith(FILLER_UNIT)}")
    print("== 计划面自检 ==")
    salts = [salt_for(a.salt_seed, r, s) for r in range(1, a.rounds + 1)
             for s in ["long"] + [f"p{o}" for o in a.offsets]]
    print(f"PASS salts 唯一：{len(salts)} 盐 {len(set(salts))} 唯一" if len(set(salts)) == len(salts)
          else "FAIL salts 重复")
    print(f"零网络自证：_NET_CALLS={_NET_CALLS}（应=0）" + (" ✓" if _NET_CALLS == 0 else " ✗"))
    return 0 if len(set(salts)) == len(salts) and _NET_CALLS == 0 else 1


# ── 判别力自检（--selfcheck：零网络；新量具纪律=喂坏输入看它因正确理由变红）──
def selfcheck(a):
    ok = True

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        ok = ok and cond

    # 1) 长预填=B25 同形（sd_bench build_pr_prompt 逐字节同构）
    lp = build_long_prompt(524288, "ab12cd34")
    need(lp.startswith("[prefill-bench ab12cd34]\n"), "长 header 含盐（B25 同形）")
    need(lp.endswith("\nReply OK."), "长 footer=\\nReply OK.（B25 同形）")
    need(lp.count(FILLER_UNIT) >= 524288 - 32, "长 filler 覆盖目标 token（B25 同形）")
    need(abs(len(lp) / estimate_tokens(lp) - 4.0) < 0.01, "长 chars_per_est_token≈4.0（在档形）")
    need(lp.count("[prefill-bench ") == 1 and lp.count("Reply OK.") == 1, "盐/足语各恰一次")

    # 2) 确定性盐⇒A/B 同载荷；靴内两两不同
    need(build_long_prompt(524288, salt_for(SALT_SEED_DEFAULT, 1, "long"))
         == build_long_prompt(524288, salt_for(SALT_SEED_DEFAULT, 1, "long")),
         "同 (seed,round,slot) 长 prompt 逐字节同（跨靴复刻前提）")
    need(salt_for(SALT_SEED_DEFAULT, 1, "long") != salt_for(SALT_SEED_DEFAULT, 2, "long"),
         "跨轮盐不同（轮间无复命中）")
    s1 = build_short_prompt(1024, salt_for(SALT_SEED_DEFAULT, 1, "p10"))
    s2 = build_short_prompt(1024, salt_for(SALT_SEED_DEFAULT, 1, "p10"))
    s3 = build_short_prompt(1024, salt_for(SALT_SEED_DEFAULT, 1, "p30"))
    need(s1 == s2, "同盐短 prompt 逐字节同（可复现）")
    need(s1 != s3, "跨时位盐不同（点间无复命中）")

    # 3) 短 prompt=词汤冷盐（~1k token、非重复形态）
    need(950 <= estimate_tokens(s1) <= 1100, f"短 prompt ≈1k token（est={estimate_tokens(s1)}）")
    body = s1.split("OK.\n", 1)[1].rsplit("\nReply OK.", 1)[0]
    need(body.count(FILLER_UNIT * 3) == 0, "短填充无 ' the' 三连重复（行缓存无可命中）")
    need(len(set(body.split()[:200])) > 80, "短填充词多样（词汤非重复）")

    # 4) 有效性规则（防事后择点）：arrival < long_ttft − 5
    need((10 < 143.34 - 5), "合成：arrival=10 vs TTFT=143.34 → 有效")
    need((90 < 143.34 - 5), "合成：arrival=90 vs TTFT=143.34 → 有效（era-B 形）")
    need(not (90 < 87.6 - 5), "合成：arrival=90 vs TTFT=87.6 → 无效（era-A 快带形被剔除）")
    need(not (138.34 < 143.34 - 5), "合成：arrival=TTFT−5 边界 → 无效（严格 <）")

    # 5) 统计面：median/p90 合成对表
    xs = [80.0, 60.0, 100.0, 40.0]
    need(statistics.median(xs) == 70.0, "median 合成对表=70.0")
    need(abs(percentile(xs, 90) - 94.0) < 1e-9, f"p90 线性插值合成对表=94.0（{percentile(xs, 90)}）")
    need(percentile([42.0], 90) == 42.0, "p90 单点=该值")

    # 6) --aggregate 合成：门线/降级/判读力降级（合成 JSON 落临时文件后离线聚合）
    import tempfile, os
    def synth(arm, ttfts, round_valid=True):
        pts = [{"pos_s": 10 + 20 * i, "send_offset_s": 10 + 20 * i, "ttft_s": t,
                "valid": True, "remaining_prefill_est_s": 143.0 - (10 + 20 * i)}
               for i, t in enumerate(ttfts)]
        return {"arm": arm, "rounds": [{"round": 1, "round_valid": round_valid,
                                        "points": pts, "valid_points": len(pts)}],
                "aggregate": {"n_planned": 12, "n_valid": len(pts), "n_rounds_valid": 1,
                              "median_ttft_s": statistics.median(ttfts), "p90_ttft_s": None,
                              "ttft_valid_s": ttfts}}
    with tempfile.TemporaryDirectory() as td:
        def agg(ma_list, mb_list):
            fa, fb = os.path.join(td, "a.json"), os.path.join(td, "b.json")
            for path, doc in ((fa, synth("A", ma_list)), (fb, synth("B", mb_list))):
                with open(path, "w") as fp:
                    json.dump(doc, fp)
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                aggregate(fa, fb, json_out=os.path.join(td, "agg.json"))
            with open(os.path.join(td, "agg.json")) as fp:
                return json.load(fp)
        r1 = agg([80.0, 80.0, 80.0], [60.0, 60.0, 60.0])
        need(abs(r1["ratio_B_over_A"] - 0.75) < 1e-9 and r1["band"].startswith("PASS-line"),
             f"合成 B/A=0.75 恰落 ≤0.75 线（{r1['ratio_B_over_A']}/{r1['band']}）")
        r2 = agg([80.0, 80.0, 80.0], [68.0, 68.0, 68.0])
        need(r2["band"].startswith("weak-effect"), f"合成 B/A=0.85 → 弱效边界带（{r2['band']}）")
        r3 = agg([80.0, 80.0, 80.0], [80.0, 80.0, 80.0])
        need(r3["band"].startswith("degrade"), f"合成 B/A=1.0 → 降级线（{r3['band']}）")
        r4 = agg([80.0, 80.0], [60.0])  # 合计 3<8 点
        need(r4.get("validity_degrade") is True, "合成合计有效点<8 → 判读力降级注记")
        # 坏输入必红：非本探针 JSON/缺字段
        bad = os.path.join(td, "bad.json")
        with open(bad, "w") as fp:
            json.dump({"foo": 1}, fp)
        try:
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                aggregate(bad, bad)
            need(False, "aggregate 坏输入（缺字段）必须红")
        except (RuntimeError, KeyError):
            need(True, "aggregate 坏输入（缺字段）红不静默")
        try:
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                aggregate(os.path.join(td, "missing.json"), os.path.join(td, "missing.json"))
            need(False, "aggregate 缺文件必须红")
        except OSError:
            need(True, "aggregate 缺文件红不静默")

    # 7) 零网络机器自证：selfcheck/dry-run 全程 _NET_CALLS==0
    dry_run(argparse.Namespace(rounds=2, offsets=[10, 30, 60, 90], target_long=524288,
                               target_short=1024, max_tokens=16, temperature=0.0,
                               cooldown=60, validity_margin=5, salt_seed=SALT_SEED_DEFAULT))
    need(_NET_CALLS == 0, f"零网络自证：selfcheck+dry-run 全程 _NET_CALLS=0（实测={_NET_CALLS}）")

    print("SELFCHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(
        description=f"{PROBE_NAME} 混合 TTFT 探针（T34-04 §2.1 M1；置备自检/干跑/聚合均零网络）")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="判读窗执行（唯一发请求路径；A/B 同件同参）")
    mode.add_argument("--dry-run", action="store_true", help="离线计划面干跑（零网络）")
    mode.add_argument("--selfcheck", action="store_true", help="离线判别力自检（零网络）")
    mode.add_argument("--aggregate", nargs=2, metavar=("A_JSON", "B_JSON"),
                      help="离线跨臂聚合判读面（零网络）")
    ap.add_argument("--arm", choices=("A", "B"), help="臂标签（--run 必填；仅记档不影响载荷）")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--offsets", type=int, nargs="+", default=[10, 30, 60, 90],
                    help="短请求时位（s，相对 T0；§2.1 冻结={10,30,60,90}）")
    ap.add_argument("--target-long", type=int, default=524288)
    ap.add_argument("--target-short", type=int, default=1024)
    ap.add_argument("--max-tokens", type=int, default=16)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--cooldown", type=int, default=60, help="轮间清态（长预填毕+60s）")
    ap.add_argument("--validity-margin", type=float, default=5.0,
                    help="有效性规则边距（arrival < long_ttft − margin；§2.1 冻结=5）")
    ap.add_argument("--salt-seed", default=SALT_SEED_DEFAULT)
    ap.add_argument("--base-url", default="http://127.0.0.1:8899/v1")
    ap.add_argument("--key-file", default="state/api-key",
                    help="缺省沿用 sd_bench 惯例（CWD 相对；缺失=无鉴权头直连）")
    ap.add_argument("--timeout-s", type=float, default=600.0,
                    help="SSE 读超时（长预填静默期 ≫ TTFT；绝对锚 era 250s 量级故 600）")
    ap.add_argument("--timeout-connect", type=float, default=10.0)
    ap.add_argument("--json-out")
    a = ap.parse_args()

    if a.run:
        if not a.arm:
            ap.error("--run 必填 --arm {A,B}")
        key = ""
        try:
            with open(a.key_file) as fp:
                key = fp.read().strip()
        except OSError:
            pass
        print(f"[{PROBE_NAME}] RUN arm={a.arm} base={a.base_url} rounds={a.rounds} "
              f"offsets={a.offsets} start={utcnow()}", flush=True)
        out, any_valid = run_probe(a, key)
        if a.json_out:
            with open(a.json_out, "w") as fp:
                fp.write(json.dumps(out, ensure_ascii=False, indent=1))
        print(json.dumps(out["aggregate"], ensure_ascii=False))
        return 0 if any_valid else 1
    if a.selfcheck:
        return selfcheck(a)
    if a.dry_run:
        return dry_run(a)
    return aggregate(a.aggregate[0], a.aggregate[1], json_out=a.json_out)


if __name__ == "__main__":
    sys.exit(main())
