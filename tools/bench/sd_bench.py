#!/usr/bin/env python3
"""sd_bench -- sparkDash 口径 PR/DE 基准（headless 复刻，横向可比探针）。

口径出处（逐文件对齐，勿凭记忆改）：
  DE = MiaAI-Lab/sparkDash server/collectors/DecodeBench.js（+src/shared/llmPrompts.js）
       greedy（temperature 0 / top_p 1 / thinking off）、max_tokens 400（warmup 32）、
       stream+include_usage、decode tok/s = (completion_tokens-1)/(last-first token)。
       c1 = 该型精确原文（prose = hash-map essay，即社区 89.76 的那条提示）。
       c>1 非code型加 " (stream i/n)" 后缀；code型每流一个不同任务（防前缀缓存共享）。
       不附加 fill-to-max 后缀（那是 Showcase 用法，DecodeBench 不调用）。
  PR = server/collectors/PrefillBench.js：串行、每尺寸单请求、fresh salt 防跨尺寸
       前缀缓存、prompt = header(salt+Reply OK) + " the"*N + footer、GEN 8 tokens、
       每尺寸前 512-token warmup、tok/s = usage.prompt_tokens / TTFT。
       ⚠ filler 是重复 " the" ⇒ Engram 行缓存命中膨胀（社区 MiaAI-Lab#21 已知口径
       属性，虚增 16-42%；--pr-filler real 用真实文本分布填充另行测）——本口径数字
       只与同口径数字比。

判别力自检（纪律：新量具必须喂坏输入看它因正确理由变红）：
  --selfcheck  断言 c1 提示逐字节、PR 构造、坏端点必红。
"""
import argparse
import json
import sys
import threading
import time
import uuid

import requests

# ── sparkDash src/shared/llmPrompts.js（逐字节，勿改一字） ──────────────────
DE_STRUCTURED_PROMPT = "Count from 1 to 200. Output only the numbers, separated by spaces. No other text."
DE_PROSE_PROMPT = ("Write a detailed step-by-step explanation of how a hash map works, "
                   "including collision handling, resizing, and time complexity. Be thorough.")
CODE_TAIL = ("Output only Python source. No comments, no docstrings, no markdown fences. "
             "Then add tests and the helpers this needs. Keep writing code.")


def _code_task(name, spec):
    return f"{name}\n{spec}\n{CODE_TAIL}"


DE_CODE_TASKS = [
    _code_task("binary_search", "def binary_search(nums, target) -> int: index of target in a sorted list, or -1."),
    _code_task("merge_sort", "def merge_sort(nums) -> list: stable sort of a list of ints, returning a new list."),
    _code_task("lru_cache", "class LRUCache: get(key) and put(key, value) with a fixed capacity, evicting the least recently used."),
    _code_task("token_bucket", "class TokenBucket: allow(n) consumes n tokens refilled at a fixed rate, else returns False."),
    _code_task("ring_buffer", "class RingBuffer: push and pop over a fixed-capacity array, raising on overflow and underflow."),
    _code_task("dijkstra", "def dijkstra(graph, src) -> dict: shortest path weights from src on a non-negative weighted graph."),
    _code_task("edit_distance", "def edit_distance(a, b) -> int: Levenshtein distance between two strings."),
    _code_task("semver_cmp", "def semver_cmp(a, b) -> int: compare dotted numeric versions, negative if a < b."),
    _code_task("url_parse", "def url_parse(url) -> dict: scheme, host, port, path, and query pairs. No extra libraries."),
    _code_task("json_pointer", "def json_pointer(doc, pointer) -> object: follow an RFC 6901 pointer, or None if missing."),
    _code_task("glob_match", "def glob_match(pattern, text) -> bool: * and ? wildcards, no character classes."),
    _code_task("csv_parse", "def csv_parse(text) -> list: rows of fields, honoring double-quoted commas and escaped quotes."),
    _code_task("rle", "def rle_encode(s) -> str and rle_decode(s) -> str: run-length encoding of single-byte runs."),
    _code_task("top_k", "def top_k(nums, k) -> list: the k largest ints, unordered, using a bounded heap."),
    _code_task("interval_merge", "def merge_intervals(spans) -> list: merge overlapping [start, end] pairs."),
    _code_task("topo_sort", "def topo_sort(nodes, edges) -> list: a valid order, or None if the graph has a cycle."),
]
DE_JSON_PROMPT = ("Emit only a JSON array of fake GPU metrics rows. Each object needs host, gpuIndex, "
                  "utilPct, tempC, powerW, memUsedMb. Invent many rows. No markdown. Keep expanding the array.")
DE_CODE_WARMUP_PROMPT = _code_task("warmup_noop", "def warmup_noop(x): return x unchanged.")
DE_TYPES = ("structured", "prose", "code", "json")
ALLOWED_CONC = (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24, 32)
FILLER_UNIT = " the"


def de_prompt(type_: str, n: int):
    if type_ == "code":
        out = []
        for i in range(n):
            t = DE_CODE_TASKS[i % len(DE_CODE_TASKS)]
            cyc = i // len(DE_CODE_TASKS)
            out.append(t if cyc == 0 else f"[stream {i + 1}]\n{t}")
        return out
    base = {"structured": DE_STRUCTURED_PROMPT, "prose": DE_PROSE_PROMPT, "json": DE_JSON_PROMPT}[type_]
    if n <= 1:
        return [base]
    return [f"{base} (stream {i + 1}/{n})" for i in range(n)]


def de_warmup_prompt(type_: str) -> str:
    return DE_CODE_WARMUP_PROMPT if type_ == "code" else de_prompt(type_, 1)[0]


# ── PR prompt 构造（PrefillBench.buildPrefillPrompt） ───────────────────────
def estimate_tokens(s: str) -> int:
    return max(1, (len(s) + 3) // 4)  # ≈4 chars/token（LlmStreaming.estimateTokenCount）


def build_pr_prompt(target_tokens: int, salt: str, filler: str = "repeated") -> str:
    header = f"[prefill-bench {salt}]\nIgnore the filler below. Reply with the single word OK.\n"
    footer = "\nReply OK."
    fill = max(1, target_tokens - estimate_tokens(header + footer))
    if filler == "repeated":
        body = FILLER_UNIT * fill
    elif filler == "random":
        body = _random_filler(salt, fill)
    elif filler == "real":
        body = _real_filler(salt, fill)
    else:
        raise ValueError(f"unknown filler {filler!r} (repeated|random|real)")
    return header + body + footer


# 诚实填充口径（MiaAI-Lab#21：重复 " the" 令 Engram 行缓存命中膨胀 9-20%@16k-128k）。
# random：salt 播种的伪随机词序列（同 salt 可复现），字符量与 repeated 档同基准，
# 词行各不相同 ⇒ Engram 行缓存无可命中对象。
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


def _random_filler(salt: str, units: int) -> str:
    import random as _random
    rng = _random.Random(f"pr-filler:{salt}")
    target_chars = units * len(FILLER_UNIT)
    out = []
    n = 0
    while n < target_chars:
        w = _RAND_WORDS[rng.randrange(len(_RAND_WORDS))]
        out.append(w)
        n += len(w) + 1
    return " ".join(out)


# 真实文本口径（--pr-filler real；MiaAI-Lab#21：repeated 单 token 重复 × Engram 行缓存
# 命中 ⇒ 虚增 16-42%；random 是均匀词汤，token 分布仍非真实）。借
# ~/luz030-opt-campaign/tools/ds_gate.py 的语料生成器（PORT(3) 语法模板散文）：
# 名词/动词/形容词库 × 句模板 × 段落/章节/列表结构，函数词经模板高频出现（近似
# 自然词频），行长/标点/数字多样 ⇒ 真实 token 分布、行级无重复（行缓存无可命中）。
# salt 播种可复现、跨 salt 不同；字符量与 repeated/random 同基准（同 fill）。
_REAL_N = ("system server record cluster session packet worker queue index cache request "
           "handler table config message batch checkpoint shard ledger policy cursor buffer "
           "window stream license tenant metric trace span journal vector matrix kernel "
           "bridge gateway router beacon pilot harbor vessel cargo raft signal lantern "
           "compass anchor deck cabin sail tide storm").split()
_REAL_V = ("holds writes reads locks merges splits joins retries fails recovers mirrors "
           "strips rebalances validates compacts snapshots restores archives replays rotates "
           "seals verifies signs drains leases releases scans folds sorts packs ships tracks "
           "reports schedules collects").split()
_REAL_A = ("stable stale warm cold dense sparse exact rough smooth quiet loud fast slow "
           "tight loose fresh aged bold calm dry plain fancy broad narrow deep shallow").split()
_REAL_T = [
    "The {a} {n} {v} the {n2} before the {a2} {n3} {v2}.",
    "After the {n} {v}, the crew {v2} every {a} {n2} on the {n3}.",
    "Each {n} holds {d} {a} {n2} records, and the {n3} {v} them at {d2} second intervals.",
    "When the {a} {n} goes {a2}, the pilot {v} the {n2} and {v2} a {n3}.",
    "The harbor log notes that raft {d} {v} {d2} crates while the tide {v2} the eastern anchor.",
    "No {n} may {v} a sealed {n2} unless the {a} {n3} also {v2} it.",
    "Between {d} and {d2} checks the {a} {n} {v} quietly, then {v2} the {n2}.",
    "A {a} {n}, a {a2} {n2} and three {n3}s {v} the same ledger before dawn.",
    "Records {d} through {d2} show the {a} {n} {v} while the {n2} {v2} nothing at all.",
]


def _real_filler(salt: str, units: int) -> str:
    import random as _random
    rng = _random.Random(f"pr-real:{salt}")
    target_chars = units * len(FILLER_UNIT)

    def sent():
        return rng.choice(_REAL_T).format(
            a=rng.choice(_REAL_A), a2=rng.choice(_REAL_A), n=rng.choice(_REAL_N),
            n2=rng.choice(_REAL_N), n3=rng.choice(_REAL_N), v=rng.choice(_REAL_V),
            v2=rng.choice(_REAL_V), d=rng.randint(3, 977), d2=rng.randint(3, 977))

    def para():
        return " ".join(sent() for _ in range(rng.randint(3, 8)))

    parts, n, sec = [], 0, 0
    while n < target_chars:
        sec += 1
        parts.append("## Part %d: the %s and the %s" % (sec, rng.choice(_REAL_N), rng.choice(_REAL_N)))
        n += len(parts[-1]) + 1
        for _ in range(rng.randint(3, 6)):
            parts.append(para())
            n += len(parts[-1]) + 1
        if rng.random() < 0.5:
            li = "\n".join("- %s the %s %s (%d units)" % (rng.choice(_REAL_V), rng.choice(_REAL_A),
                                                            rng.choice(_REAL_N), rng.randint(1, 500))
                            for _ in range(rng.randint(2, 5)))
            parts.append(li)
            n += len(li) + 1
    return "\n".join(parts)


class Client:
    def __init__(self, base_url, key, timeout_s):
        self.base = base_url.rstrip("/")
        self.h = {"Authorization": f"Bearer {key}"} if key else {}
        self.timeout = timeout_s

    def stream(self, prompt, max_tokens, temperature=0.0, top_p=1.0):
        """返回 dict(t_first, t_last, completion, prompt_tokens)。SSE 解析：
        first = 第一个带非空 delta 内容的 chunk 墙钟；last = 最后一个 chunk 墙钟。"""
        body = {"messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
                "stream": True, "stream_options": {"include_usage": True}}
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
            raise RuntimeError(f"no visible delta or usage (first={t_first is not None}, completion={completion})")
        return {"t_first": t_first, "t_last": t_last, "completion": completion,
                "prompt_tokens": prompt_tokens, "t_req": t0}


def run_de(c: Client, type_, conc, max_tokens, warmups, runs):
    # warmup：先发热身请求（code 型用 warmup_noop，防 JIT/前缀缓存混入）
    for _ in range(warmups):
        c.stream(de_warmup_prompt(type_), 32)
    results = []
    for _ in range(runs):
        prompts = de_prompt(type_, conc)
        out = [None] * conc

        def work(i):
            out[i] = c.stream(prompts[i], max_tokens)

        th = [threading.Thread(target=work, args=(i,)) for i in range(conc)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        per = [(o["completion"] - 1) / (o["t_last"] - o["t_first"]) for o in out]
        agg = sum(o["completion"] - 1 for o in out) / (max(o["t_last"] for o in out) - min(o["t_first"] for o in out))
        results.append({"type": type_, "conc": conc, "per": round(sorted(per)[len(per) // 2], 2),
                        "per_all": [round(x, 2) for x in per], "agg": round(agg, 2),
                        "completion": [o["completion"] for o in out]})
    return results


def run_pr(c: Client, sizes, warm_tokens=512, gen_tokens=8, filler="repeated"):
    c.stream(build_pr_prompt(warm_tokens, uuid.uuid4().hex[:8], filler), gen_tokens)  # warmup
    rows = []
    for n in sizes:
        salt = uuid.uuid4().hex[:8]
        prompt = build_pr_prompt(n, salt, filler)
        o = c.stream(prompt, gen_tokens)
        ttft = o["t_first"] - o["t_req"]
        pt = o["prompt_tokens"] or n
        rows.append({"target": n, "prompt_tokens": pt, "ttft_s": round(ttft, 3),
                     "tok_s": round(pt / ttft, 1) if ttft > 0 else None,
                     # 行级 cpt 记录位（PR-ANCHOR-AUDIT §四.2-4 三要素；探针侧只读不猜）
                     "prompt_chars": len(prompt),
                     "chars_per_token": round(len(prompt) / pt, 3) if pt else None,
                     "filler": filler})
    return rows


def selfcheck():
    ok = True

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        ok = ok and cond

    need(de_prompt("prose", 1) == [DE_PROSE_PROMPT], "prose c1 = 精确原文（hash-map essay）")
    need(de_prompt("structured", 1) == [DE_STRUCTURED_PROMPT], "structured c1 = 精确原文")
    need(de_prompt("prose", 4)[1] == f"{DE_PROSE_PROMPT} (stream 2/4)", "c>1 后缀形态")
    need(len(set(de_prompt("code", 16))) == 16, "code c16 = 16 个不同任务（无前缀共享）")
    p = build_pr_prompt(4096, "abcd1234")
    need(p.startswith("[prefill-bench abcd1234]\n"), "PR header 含 salt")
    need(p.endswith("\nReply OK."), "PR footer")
    need(p.count(FILLER_UNIT) >= 4096 - 32, "PR filler 覆盖目标 token")
    # P5 双填充口径：默认=sparkDash 原样 repeated（字节不变）；random=salt 确定性、
    # 与 repeated 不同文本、覆盖同级、跨 salt 不同 ⇒ 判别力各自成立。
    import inspect as _inspect
    _sig = _inspect.signature(build_pr_prompt)
    need(_sig.parameters["filler"].default == "repeated", "PR filler 默认 repeated（向后兼容）")
    need(build_pr_prompt(4096, "abcd1234") == build_pr_prompt(4096, "abcd1234", "repeated"),
         "默认调用与显式 repeated 逐字节等")
    pr1, pr2 = build_pr_prompt(4096, "abcd1234", "random"), build_pr_prompt(4096, "abcd1234", "random")
    need(pr1 == pr2, "random 同 salt 可复现")
    body1 = pr1.split("OK.\n", 1)[1].rsplit("\nReply OK.", 1)[0]
    need(body1.count(FILLER_UNIT) < len(body1.split()) // 100,
         "random 填充非重复形态（行缓存无可命中）")
    need(estimate_tokens(pr1) >= 4096 - 64, "random 覆盖目标 token（同基准）")
    pr3 = build_pr_prompt(4096, "ffff5678", "random")
    need(pr1.split("OK.\n", 1)[1] != pr3.split("OK.\n", 1)[1], "random 跨 salt 不同文本")
    # real 口径：可复现、跨 salt 不同、同基准覆盖、行级无重复、词频非均匀（近似自然）。
    import collections as _collections
    pr1r = build_pr_prompt(4096, "abcd1234", "real")
    need(pr1r == build_pr_prompt(4096, "abcd1234", "real"), "real 同 salt 可复现")
    need(estimate_tokens(pr1r) >= 4096 - 64, "real 覆盖目标 token（同基准）")
    body_r = pr1r.split("OK.\n", 1)[1].rsplit("\nReply OK.", 1)[0]
    need(body_r.count(FILLER_UNIT * 2) == 0, "real 无相邻重复单元（行缓存无可命中；' the'自然高频不算）")
    need(len(set(body_r.splitlines())) == len(body_r.splitlines()), "real 行级无重复")
    wrd = body_r.split()
    top = _collections.Counter(wrd).most_common(1)[0][1]
    need(top > len(wrd) * 0.05, f"real 词频非均匀（高频函数词，top={top}/{len(wrd)}）")
    need("## Part" in body_r and any(c.isdigit() for c in body_r), "real 具文档结构（章节+数字）")
    pr3r = build_pr_prompt(4096, "ffff5678", "real")
    need(pr1r.split("OK.\n", 1)[1] != pr3r.split("OK.\n", 1)[1], "real 跨 salt 不同文本")
    try:  # 坏端点必须因正确理由红
        Client("http://127.0.0.1:1/v1", "k", 2).stream(DE_PROSE_PROMPT, 32)
        need(False, "坏端点必须红")
    except Exception as e:
        need("Connection" in type(e).__name__ or "connection" in str(e).lower(), f"坏端点红（{type(e).__name__}）")
    print("SELFCHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("de", "pr"), required=False,
                    help="de/pr；--selfcheck 时可不填")
    ap.add_argument("--type", choices=DE_TYPES, default="prose")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--warmups", type=int, default=2)  # knapcio 口径：first run after two warm-ups
    ap.add_argument("--sizes", type=int, nargs="+", default=[4096, 8192, 16384, 32768])
    ap.add_argument("--pr-filler", choices=("repeated", "random", "real"), default="repeated",
                    help="PR 填充口径：repeated=sparkDash 原样（行缓存膨胀）；random=均匀词汤（P5）；"
                         "real=真实文本分布（ds_gate 语料生成器，MiaAI-Lab#21 口径）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8899/v1")
    ap.add_argument("--key-file", default="state/api-key")
    ap.add_argument("--label", default="sd")
    ap.add_argument("--json-out")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    if not a.mode:
        ap.error("--mode 必填（仅 --selfcheck 时可省）")
    if a.concurrency not in ALLOWED_CONC:
        return print(f"concurrency 必须是 {ALLOWED_CONC}", file=sys.stderr) or 2
    key = ""
    try:
        key = open(a.key_file).read().strip()
    except OSError:
        pass
    c = Client(a.base_url, key, timeout_s=max(120, a.max_tokens * 8))
    data = {"label": a.label,
            "de": run_de(c, a.type, a.concurrency, a.max_tokens, a.warmups, a.runs)} if a.mode == "de" \
        else {"label": a.label, "pr": run_pr(c, a.sizes, filler=a.pr_filler)}
    print(json.dumps(data, ensure_ascii=False))
    if a.json_out:
        open(a.json_out, "w").write(json.dumps(data, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
