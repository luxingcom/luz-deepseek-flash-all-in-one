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

T33-03 Phase 0 双口径（033 任务书 v2.1 §T33-03；附录 D）：
  committed_decode_tps = (completion−1)/(t_last−t_first) —— 真实提交 token（=原 per/agg 同式）；
  full_accept_equiv_tps = committed×(1+nextn)/accept_len —— 全接受等效口径，副标签，
    仅与官方/旧表（DeepInfer avg_sps×req×(1+nextn)/cp）可比，不得当真实吞吐报。
  --capture-spec 开：body 才加 return_spec_tokens_details + chat_template_kwargs.thinking=False
    （钉 thinking；缺 sglext 必红不静默）；默认关 ⇒ 请求体逐字节不变（selfcheck 断言）。
  --legacy-csv：输出裁回旧 schema 键序（回退面；INV-02 §6.9 旧管道兼容）。
  --replay：离线回放既有 JSON（旧/新 schema）验闭合，零请求零产线触。
  --runs×PR（DF-04 修复，升级篇-20）：PR 模式不再静默吞参——缺省 1=旧单发行
    schema 逐字节不变（旧锚/旧管道可比）；显式 N>1=每档 N 次独立调用（每发独立
    fresh salt 防跨发前缀缓存），行含 shots 逐发记录 + tok_s/ttft_s 的
    median/min/max/range（极差）；--legacy-csv 下 shots 逐发展开为旧键行。
  EQ-11 参数面统一（0.3.4re，2026-10-30）：--base-url 三形通吃归一到 v1 基
    （origin/v1基/全路径 → …/v1；bench_url 唯一构造处；旧正确形请求 URL 逐字节
    不变）；--targets 是 --sizes 的等价别名；URL 错形与 argparse 拒起一律
    首行 `ERROR[sd_bench.py]: …` 到 stderr + exit 2（管道 `2>&1|grep ERROR` 必命中）。
"""
import argparse
import json
import sys
import threading
import time
import uuid

import requests

# ── EQ-11 共享构造处（bench_url）：URL 三形归一 + argparse 拒起首行 ERROR 摘要 ──
try:
    import bench_url  # 直跑（python3 tools/bench/sd_bench.py）时 sys.path[0] 即本目录
except ImportError:  # importlib 直载（de_c48_bench spec_from_file_location）时本目录不在 sys.path
    import importlib.util as _ilu
    import os as _os
    _spec = _ilu.spec_from_file_location(
        "bench_url", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "bench_url.py"))
    bench_url = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(bench_url)

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

# ── T33-03 Phase 0 双口径常量（附录 D：committed 与 full-acceptance 分列不得互推）──
NEXTN_DEFAULT = 5  # 投机 γ（DSPARK 静态 nextn=5，INV-02 §6.3）；SPEC=0 臂双口径置 null 不判读
DE_ROW_LEGACY_KEYS = ("type", "conc", "per", "per_all", "agg", "completion")  # --legacy-csv 键序
PR_ROW_LEGACY_KEYS = ("target", "prompt_tokens", "ttft_s", "tok_s",
                      "prompt_chars", "chars_per_token", "filler")
# DF-04：PR 单发（runs=1）行的完整键序=旧版行构造序（runs=1 输出须与旧版逐字节可比）
PR_FLAT_ROW_KEYS = ("target", "prompt_tokens", "ttft_s", "tok_s",
                    "prompt_chars", "chars_per_token", "filler", "cached_tokens",
                    "uncached_tokens", "uncached_tok_s", "reasoning_tokens")


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
        # EQ-11：--base-url 三形通吃归一到 v1 基（bench_url 唯一构造处）。旧正确形
        # （带 /v1）归一后逐字节不变；origin 形（旧版会拼成 …/chat/completions 404）
        # 与全路径形（旧版 /chat/completions/chat/completions 404）现均成形；错形
        # （非 http(s)/无 host）构造时即首行 ERROR 摘要 + exit 2（不再等到请求才 404）。
        self.base = bench_url.v1_base(base_url, flag="--base-url", prog="sd_bench.py")
        self.h = {"Authorization": f"Bearer {key}"} if key else {}
        self.timeout = timeout_s

    @staticmethod
    def build_body(prompt, max_tokens, temperature=0.0, top_p=1.0,
                   extra_body=None, capture_spec=False):
        """请求体构造（唯一出口）。默认=旧版逐字节（键序含）；capture_spec 只在
        显式开时追加双口径/钉 thinking 两键；extra_body 只叠加显式键。"""
        body = {"messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
                "stream": True, "stream_options": {"include_usage": True}}
        if capture_spec:  # T33-03：per-request spec 遥测 + thinking 钉 off（默认关=字节不变）
            body["return_spec_tokens_details"] = True
            body["chat_template_kwargs"] = {"thinking": False}
        if extra_body:
            body.update(extra_body)
        return body

    def stream(self, prompt, max_tokens, temperature=0.0, top_p=1.0,
               extra_body=None, capture_spec=False):
        """返回 dict(t_first, t_last, completion, prompt_tokens, reasoning_tokens,
        cached_tokens, spec)。SSE 解析：first = 第一个带非空 delta 内容的 chunk 墙钟；
        last = 最后一个 chunk 墙钟。reasoning/cached 取 usage.*_tokens_details（缺=None 不造 0）；
        spec 取末次 sglext.spec_tokens_details（仅 capture_spec 请求才有）。"""
        body = self.build_body(prompt, max_tokens, temperature, top_p, extra_body, capture_spec)
        t_first = t_last = None
        completion = prompt_tokens = None
        reasoning = cached = spec = None
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
                pd = u.get("prompt_tokens_details")
                if isinstance(pd, dict) and pd.get("cached_tokens") is not None:
                    cached = pd["cached_tokens"]      # A9 --enable-cache-report 面（KV 前缀缓存）
                cd = u.get("completion_tokens_details")
                if isinstance(cd, dict) and cd.get("reasoning_tokens") is not None:
                    reasoning = cd["reasoning_tokens"]  # thinking 未钉缺省的探针（E5 判读位）
            sg = j.get("sglext")
            if isinstance(sg, dict) and sg.get("spec_tokens_details"):
                spec = sg["spec_tokens_details"]
        if t_first is None or completion is None:
            raise RuntimeError(f"no visible delta or usage (first={t_first is not None}, completion={completion})")
        return {"t_first": t_first, "t_last": t_last, "completion": completion,
                "prompt_tokens": prompt_tokens, "t_req": t0,
                "reasoning_tokens": reasoning, "cached_tokens": cached, "spec": spec}


def run_de(c: Client, type_, conc, max_tokens, warmups, runs,
           capture_spec=False, nextn=NEXTN_DEFAULT):
    # warmup：先发热身请求（code 型用 warmup_noop，防 JIT/前缀缓存混入）
    for _ in range(warmups):
        c.stream(de_warmup_prompt(type_), 32, capture_spec=capture_spec)
    results = []
    for _ in range(runs):
        prompts = de_prompt(type_, conc)
        out = [None] * conc

        def work(i):
            out[i] = c.stream(prompts[i], max_tokens, capture_spec=capture_spec)

        th = [threading.Thread(target=work, args=(i,)) for i in range(conc)]
        for t in th:
            t.start()
        for t in th:
            t.join()
        if capture_spec and any((o.get("spec") if isinstance(o, dict) else None) is None for o in out):
            # INV-02 §6.8-7：sglext 被网关剥离/缺字段必须红，禁止静默当 0 出双口径数
            missing = sum(1 for o in out if not (isinstance(o, dict) and o.get("spec")))
            raise RuntimeError(f"capture_spec=on 但 {missing}/{conc} 流缺 sglext.spec_tokens_details"
                               "（网关剥离或缺字段）——禁止静默出数")
        per = [(o["completion"] - 1) / (o["t_last"] - o["t_first"]) for o in out]
        agg = sum(o["completion"] - 1 for o in out) / (max(o["t_last"] for o in out) - min(o["t_first"] for o in out))
        reqs = per_request_rows(out, per, nextn)
        row = {"type": type_, "conc": conc, "per": round(sorted(per)[len(per) // 2], 2),
               "per_all": [round(x, 2) for x in per], "agg": round(agg, 2),
               "completion": [o["completion"] for o in out]}
        row.update(dual_caliber_block(out, reqs, agg, nextn))
        results.append(row)
    return results


# ── T33-03 Phase 0 双口径记账（committed 与 full-acceptance 两独立字段，不互相推导）──
def per_request_rows(out, per, nextn):
    """per-request 闭合行：gen=completion−1（首 token 出自 prefill）、accepted/b/proposed
    出自 sglext（b=verify 步数，每步含 1 golden token）。无 spec（capture off / SPEC=0）
    ⇒ 引擎侧闭合量=None 不造数；committed 仍可算（=per 原式）。"""
    rows = []
    for o, p in zip(out, per):
        sp = (o.get("spec") or {}) if isinstance(o, dict) else {}
        vc = sp.get("spec_verify_ct")
        acc = sp.get("spec_num_correct_drafts")
        prop = sp.get("spec_num_proposed_drafts")
        gen = o["completion"] - 1
        if vc:  # 引擎账在：闭合行成形
            accept_len = gen / vc
            rate = (acc / prop) if prop else None
            fae = p * (1 + nextn) / accept_len if accept_len > 0 else None
            rows.append({"completion": o["completion"], "generated": gen,
                         "accepted": acc, "b": vc, "proposed": prop,
                         "accept_len": round(accept_len, 4),
                         "accept_rate": round(rate, 4) if rate is not None else None,
                         "verified_len": round(prop / vc, 4) if prop is not None else None,
                         "committed_decode_tps": round(p, 2),
                         "full_accept_equiv_tps": round(fae, 2) if fae is not None else None,
                         "reasoning_tokens": o.get("reasoning_tokens"),
                         "cached_tokens": o.get("cached_tokens"),
                         "gen_eq_accepted_plus_b": (acc + vc == gen) if acc is not None else None})
        else:
            rows.append({"completion": o["completion"], "generated": gen,
                         "accepted": None, "b": None, "proposed": None,
                         "accept_len": None, "accept_rate": None, "verified_len": None,
                         "committed_decode_tps": round(p, 2), "full_accept_equiv_tps": None,
                         "reasoning_tokens": o.get("reasoning_tokens"),
                         "cached_tokens": o.get("cached_tokens"),
                         "gen_eq_accepted_plus_b": None})
    return rows


def dual_caliber_block(out, reqs, agg, nextn):
    """run 行级双口径汇总 + closure 恒等式块。
    Σ(completion−1)=Σgenerated（客户端-引擎闭合，±1 容差=流末步截断/舍入）；
    gen=accepted+b（逐流，禁 bonus 重复计数）；accept_len=1+γ·rate 仅整窗满发 draft 时
    严格成立（proposed=γ·b），否则记 mode=truncated 不强判。"""
    sum_cm1 = sum(o["completion"] - 1 for o in out)
    rsum = None if any(o.get("reasoning_tokens") is None for o in out) \
        else sum(o["reasoning_tokens"] for o in out)
    ksum = None if any(o.get("cached_tokens") is None for o in out) \
        else sum(o["cached_tokens"] for o in out)
    with_spec = [q for q in reqs if q["b"]]
    base = {"nextn": nextn, "committed_decode_tps": round(agg, 2),
            "reasoning_tokens": rsum, "cached_tokens": ksum, "per_request": reqs}
    if not with_spec:  # capture off / SPEC=0：双口径 spec 面=None（附录 D：不与 spec 臂混比）
        base.update({"full_accept_equiv_tps": None, "accept_rate": None,
                     "avg_verified_len": None,
                     "closure": {"sum_completion_minus_1": sum_cm1, "sum_generated": None,
                                 "identity_sum_completion_eq_generated": None,
                                 "identity_gen_eq_accepted_plus_b": None,
                                 "identity_accept_len": None,
                                 "accept_len_identity_mode": None}})
        return base
    sum_gen = sum(q["generated"] for q in reqs)
    sum_acc = sum(q["accepted"] for q in with_spec)
    sum_b = sum(q["b"] for q in with_spec)
    sum_prop = sum(q["proposed"] for q in with_spec if q["proposed"] is not None)
    accept_len = sum_gen / sum_b if sum_b else None
    rate = sum_acc / sum_prop if sum_prop else None
    fae = agg * (1 + nextn) / accept_len if accept_len else None
    full_prop = all(q["proposed"] is not None and q["proposed"] == nextn * q["b"]
                    for q in with_spec)
    if full_prop and rate is not None:
        id_len = abs(accept_len - (1 + nextn * rate)) <= 1e-6
        mode = "exact"
    else:
        id_len = None  # 流末步 draft 未满发：1+γ·rate 分母失真，不强判（口径注记位）
        mode = "truncated"
    base.update({"full_accept_equiv_tps": round(fae, 2) if fae is not None else None,
                 "accept_rate": round(rate, 4) if rate is not None else None,
                 "avg_verified_len": round(sum_prop / sum_b, 4) if sum_b else None,
                 "closure": {"sum_completion_minus_1": sum_cm1, "sum_generated": sum_gen,
                             "sum_accepted": sum_acc, "sum_b": sum_b, "sum_proposed": sum_prop,
                             "identity_sum_completion_eq_generated": abs(sum_cm1 - sum_gen) <= 1,
                             "identity_gen_eq_accepted_plus_b":
                                 all(q["gen_eq_accepted_plus_b"] for q in with_spec),
                             "identity_accept_len": id_len,
                             "accept_len_identity_mode": mode}})
    return base


def run_pr(c: Client, sizes, runs=1, warm_tokens=512, gen_tokens=8, filler="repeated",
           capture_spec=False):
    """PR 基准（PrefillBench 口径：串行、fresh salt、GEN 8、tok_s=prompt/TTFT）。
    DF-04（升级篇-20）：runs 不再被静默吞掉——
      runs=1（缺省）＝旧单发口径，行 schema 与旧版逐字节相同（旧锚/旧管道可比）；
      runs=N>1＝每档 N 次**独立调用**，每发独立 fresh salt（防跨发前缀缓存），
        行含 shots 逐发记录 + tok_s/ttft_s 的 median/min/max/range（极差），
        median=sorted(发)[N//2]（与 run_de per 同族取法；3 发时=statistics.median）。"""
    if runs < 1:
        raise ValueError(f"runs 必须 ≥1（got {runs}；DF-04：禁止静默空转/吞参）")
    c.stream(build_pr_prompt(warm_tokens, uuid.uuid4().hex[:8], filler), gen_tokens,
             capture_spec=capture_spec)  # warmup
    rows = []
    for n in sizes:
        if runs <= 1:  # 旧路径：单发扁平行（键序=PR_FLAT_ROW_KEYS，逐字节旧 schema）
            salt = uuid.uuid4().hex[:8]
            prompt = build_pr_prompt(n, salt, filler)
            o = c.stream(prompt, gen_tokens, capture_spec=capture_spec)
            ttft = o["t_first"] - o["t_req"]
            pt = o["prompt_tokens"] or n
            # T33-03：PR 双口径=total（tok_s 原式不变）+ cached/uncached 拆分（cached_tokens
            # 是 KV 前缀缓存【A9 --enable-cache-report】，不是 Engram 行缓存；缺=None 不造 0）
            ct = o.get("cached_tokens")
            rows.append({"target": n, "prompt_tokens": pt, "ttft_s": round(ttft, 3),
                         "tok_s": round(pt / ttft, 1) if ttft > 0 else None,
                         # 行级 cpt 记录位（PR-ANCHOR-AUDIT §四.2-4 三要素；探针侧只读不猜）
                         "prompt_chars": len(prompt),
                         "chars_per_token": round(len(prompt) / pt, 3) if pt else None,
                         "filler": filler,
                         "cached_tokens": ct,
                         "uncached_tokens": (pt - ct) if ct is not None else None,
                         "uncached_tok_s": round((pt - ct) / ttft, 1)
                         if (ct is not None and ttft > 0) else None,
                         "reasoning_tokens": o.get("reasoning_tokens")})
            continue
        # DF-04 新路径：每档 N 次独立调用（每发独立 uuid salt ⇒ 跨发前缀缓存不可命中）
        shots = []
        for i in range(runs):
            salt = uuid.uuid4().hex[:8]
            prompt = build_pr_prompt(n, salt, filler)
            o = c.stream(prompt, gen_tokens, capture_spec=capture_spec)
            ttft = o["t_first"] - o["t_req"]
            pt = o["prompt_tokens"] or n
            ct = o.get("cached_tokens")
            shots.append({"shot": i + 1, "salt": salt, "target": n,
                          "prompt_tokens": pt, "ttft_s": round(ttft, 3),
                          "tok_s": round(pt / ttft, 1) if ttft > 0 else None,
                          "prompt_chars": len(prompt),
                          "chars_per_token": round(len(prompt) / pt, 3) if pt else None,
                          "filler": filler,
                          "cached_tokens": ct,
                          "uncached_tokens": (pt - ct) if ct is not None else None,
                          "uncached_tok_s": round((pt - ct) / ttft, 1)
                          if (ct is not None and ttft > 0) else None,
                          "reasoning_tokens": o.get("reasoning_tokens")})
        row = {"target": n, "runs": runs, "filler": filler, "shots": shots}
        for name, rnd in (("tok_s", 1), ("ttft_s", 3)):  # 逐发记录+中位数+极差
            vals = [s[name] for s in shots if s[name] is not None]
            row[f"{name}_median"] = round(sorted(vals)[len(vals) // 2], rnd) if vals else None
            row[f"{name}_min"] = round(min(vals), rnd) if vals else None
            row[f"{name}_max"] = round(max(vals), rnd) if vals else None
            row[f"{name}_range"] = round(max(vals) - min(vals), rnd) if vals else None
        rows.append(row)
    return rows


def strip_legacy_rows(data):
    """--legacy-csv：输出裁回旧 schema 键序（回退面；INV-02 §6.9 旧管道/旧锚可比性）。
    DF-04：PR runs>1 的 shots 行按发展开为 N 条旧键行（=旧管道「N 次独立调用各自
    成行」的同形态；shot 行自含 target 等全部旧键）。"""
    out = {"label": data.get("label")}
    if "de" in data:
        out["de"] = [{k: r[k] for k in DE_ROW_LEGACY_KEYS} for r in data["de"]]
    if "pr" in data:
        pr = []
        for r in data["pr"]:
            if r.get("shots"):  # DF-04：runs>1 档行 → 逐发展开
                pr.extend({k: s[k] for k in PR_ROW_LEGACY_KEYS} for s in r["shots"])
            else:
                pr.append({k: r[k] for k in PR_ROW_LEGACY_KEYS})
        out["pr"] = pr
    return out


# ── 离线回放（T33-03 实施阶段 2：r032c/6.17 既有日志闭合验证；零请求零产线触）──
def check_de_row(row, nextn=NEXTN_DEFAULT):
    """旧/新 schema 通用的 per-row 闭合检查。返回 (ok, notes)。
    旧 schema（无 per_request）验可推导恒等式：流数闭合、per=median(per_all)、
    c1 时 agg==per（同式退化）、agg ≤ conc×min(per_all)（共同窗上限=最慢流定窗）。"""
    notes = []

    def bad(m):
        notes.append(m)

    conc, per_all, comps = row.get("conc"), row.get("per_all"), row.get("completion")
    per, agg = row.get("per"), row.get("agg")
    if not (isinstance(conc, int) and conc >= 1):
        return False, ["conc 非法"]
    if not per_all or not comps:
        return False, ["缺 per_all/completion"]
    if len(per_all) != conc or len(comps) != conc:
        bad(f"流数不闭合：len(per_all)={len(per_all)} len(completion)={len(comps)} conc={conc}")
    med = sorted(per_all)[len(per_all) // 2]
    if per is None or abs(per - med) > 0.011:
        bad("per≠median(per_all)")
    if conc == 1:
        if agg is None or abs(agg - per) > 0.011:
            bad("c1 应 agg==per（同式退化恒等）")
    elif agg is None or agg > conc * min(per_all) + 0.01 + 0.005 * conc:
        bad(f"agg={agg} > conc×min(per_all)≈{round(conc * min(per_all), 2)}（窗口闭合上限）")
    sum_cm1 = sum(c - 1 for c in comps)
    reqs = row.get("per_request")
    if reqs is not None:
        if len(reqs) != conc:
            bad("per_request 行数≠conc")
        for q in reqs:
            if q.get("generated") != q["completion"] - 1:
                bad("generated≠completion−1（per_request 行）")
            if q.get("b"):
                if q.get("gen_eq_accepted_plus_b") is not True:
                    bad("gen≠accepted+b（bonus 重复计数/丢计数）")
                al = q["generated"] / q["b"]
                if abs((q.get("accept_len") or 0) - al) > 0.011:
                    bad("accept_len≠generated/b")
                if q.get("proposed") == nextn * q["b"] and q.get("accept_rate") is not None:
                    if abs(al - (1 + nextn * q["accept_rate"])) > 1e-3:
                        bad("accept_len≠1+γ·rate（整窗满发 draft）")
        cl = row.get("closure") or {}
        sg = cl.get("sum_generated")
        if sg is not None:
            if abs(sum_cm1 - sg) > 1:
                bad(f"Σ(completion−1)={sum_cm1} ≠ Σgenerated={sg}")
            if cl.get("identity_sum_completion_eq_generated") is not True:
                bad("closure.identity_sum 非 true")
    return not notes, notes


def check_pr_row(row):
    """PR 行闭合：tok_s=prompt_tokens/TTFT（total 口径）、chars_per_token=chars/tokens；
    cached 在场时 uncached=prompt−cached、uncached_tok_s=uncached/TTFT。
    DF-04 shots 行（--runs N>1 档行）：runs=shots 数、salt 唯一（fresh salt 口径）、
    逐发闭合、median/min/max/range（极差）与逐发自洽。"""
    notes = []

    def bad(m):
        notes.append(m)

    if row.get("shots") is not None:  # DF-04：--runs N>1 的档行
        shots = row["shots"]
        if not shots or row.get("runs") != len(shots):
            return False, [f"shots 数 {len(shots)} ≠ runs {row.get('runs')}"]
        salts = [s.get("salt") for s in shots]
        if len(set(salts)) != len(salts):
            bad("shots salt 非唯一（fresh salt 独立调用口径破坏）")
        for s in shots:
            ok_one, ns = check_pr_row(s)
            notes.extend(ns)
        for name, rnd in (("tok_s", 1), ("ttft_s", 3)):
            vals = [s.get(name) for s in shots]
            if any(v is None for v in vals):
                bad(f"{name} 存 None 发（ttft≤0？）——median/极差不判")
                continue
            med = round(sorted(vals)[len(vals) // 2], rnd)
            if row.get(f"{name}_median") != med:
                bad(f"{name}_median≠逐发中位（{row.get(f'{name}_median')} vs {med}）")
            lo, hi = round(min(vals), rnd), round(max(vals), rnd)
            if row.get(f"{name}_min") != lo or row.get(f"{name}_max") != hi:
                bad(f"{name}_min/max≠逐发极值（{row.get(f'{name}_min')}/{row.get(f'{name}_max')}"
                    f" vs {lo}/{hi}）")
            if row.get(f"{name}_range") != round(hi - lo, rnd):
                bad(f"{name}_range≠max−min（极差不闭合）")
        return not notes, notes
    pt, ttft = row.get("prompt_tokens"), row.get("ttft_s")
    if not pt or not ttft:
        return False, ["缺 prompt_tokens/ttft_s"]
    tol = pt / (ttft * ttft) * 0.0005 + 0.06  # ttft 存 3 位小数 + tok_s 存 1 位的舍入界
    if row.get("tok_s") is not None and abs(row["tok_s"] - pt / ttft) > tol:
        bad("tok_s ≠ prompt_tokens/TTFT")
    if row.get("prompt_chars") and row.get("chars_per_token") is not None:
        if abs(row["chars_per_token"] - row["prompt_chars"] / pt) > 0.0015:
            bad("chars_per_token ≠ chars/tokens")
    ct = row.get("cached_tokens")
    if ct is not None:
        if row.get("uncached_tokens") != pt - ct:
            bad("uncached_tokens ≠ prompt−cached")
        ut = row.get("uncached_tok_s")
        if ut is not None:
            utol = (pt - ct) / (ttft * ttft) * 0.0005 + 0.06
            if abs(ut - (pt - ct) / ttft) > utol:
                bad("uncached_tok_s ≠ uncached/TTFT")
    return not notes, notes


def replay(paths, nextn=NEXTN_DEFAULT):
    """离线回放：解析既有 sd_bench/de_c48 JSON（旧或新 schema），验证 per-request 闭合
    与字段自洽。零网络、零产线触（0 靴口径验证件）。"""
    total = failed = 0
    for path in paths:
        with open(path) as fp:
            d = json.load(fp)
        de, pr = d.get("de") or [], d.get("pr") or []
        rows = [("de", r) for r in de] + [("pr", r) for r in pr]
        if not rows:
            print(f"REPLAY SKIP {path}: 无 de/pr 行")
            continue
        pbad = []
        for kind, r in rows:
            total += 1
            ok, notes = check_de_row(r, nextn) if kind == "de" else check_pr_row(r)
            if not ok:
                failed += 1
                pbad.append((kind, notes))
        status = "PASS" if not pbad else "FAIL"
        print(f"REPLAY {status} {path}: de={len(de)} pr={len(pr)}"
              + ("" if not pbad else f" 首错={pbad[0][1][:2]}"))
        for kind, notes in pbad:
            for m in notes:
                print(f"  [{kind}] {m}")
    print(f"REPLAY {'PASS' if failed == 0 else 'FAIL'} rows={total} failed={failed}")
    return 0 if failed == 0 else 1


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

    # ── 7. T33-03 Phase 0：默认请求体逐字节不变（硬门；capture_spec 只在显式开时加键）──
    legacy_body = {"messages": [{"role": "user", "content": DE_PROSE_PROMPT}],
                   "max_tokens": 400, "temperature": 0.0, "top_p": 1.0,
                   "stream": True, "stream_options": {"include_usage": True}}
    b0 = Client.build_body(DE_PROSE_PROMPT, 400)
    need(json.dumps(b0) == json.dumps(legacy_body) and list(b0) == list(legacy_body),
         "默认 body 与旧版逐字节同（键序含，requests json= 序列化等价）")
    b1 = Client.build_body(DE_PROSE_PROMPT, 400, capture_spec=True)
    need(set(b1) == set(legacy_body) | {"return_spec_tokens_details", "chat_template_kwargs"}
         and b1["return_spec_tokens_details"] is True
         and b1["chat_template_kwargs"] == {"thinking": False},
         "capture_spec body 恰加两键（thinking 钉 off + spec 遥测）")
    b2 = Client.build_body(DE_PROSE_PROMPT, 400, extra_body={"x": 1})
    need(set(b2) == set(legacy_body) | {"x"}, "extra_body 只叠加显式键")

    # ── 8. 双口径恒等式（合成样本，零请求；INV-02 §7 反例 1 同数）──
    # completion=321, b=100, γ=5 ⇒ gen=320, accepted=220, proposed=500,
    # accept_len=3.2, rate=0.44, 1+5×0.44=3.2；committed=80 ⇒ full-accept=80×6/3.2=150
    class _SpecClient:
        """确定性合成客户端（离线复刻 Client.stream 契约；spec 计数内部自洽）。"""

        def __init__(self, completion=321, accepted=220, b=100, prop=500, rate=80.0,
                     no_spec=False):
            self.completion, self.accepted, self.b, self.prop, self.rate = \
                completion, accepted, b, prop, rate
            self.no_spec = no_spec  # True=模拟网关剥离 sglext（坏输入面）

        def stream(self, prompt, max_tokens, temperature=0.0, top_p=1.0,
                   extra_body=None, capture_spec=False):
            dur = (self.completion - 1) / self.rate
            t0 = 100.0
            o = {"t_first": t0, "t_last": t0 + dur, "completion": self.completion,
                 "prompt_tokens": 64, "t_req": t0 - 0.05,
                 "reasoning_tokens": 0, "cached_tokens": 0}
            if capture_spec and not self.no_spec:
                o["spec"] = {"spec_verify_ct": self.b,
                             "spec_num_correct_drafts": self.accepted,
                             "spec_num_proposed_drafts": self.prop,
                             "spec_accept_length": (self.completion - 1) / self.b,
                             "spec_accept_rate": self.accepted / self.prop}
            return o

    rows4 = run_de(_SpecClient(), "prose", 4, 321, 0, 1, capture_spec=True, nextn=5)
    r = rows4[0]
    need(all(abs(q["accept_len"] - 3.2) < 1e-6 and abs(q["accept_rate"] - 0.44) < 1e-6
             for q in r["per_request"]), "accept_len=3.2/rate=0.44（合成对表）")
    need(all(q["gen_eq_accepted_plus_b"] is True for q in r["per_request"]),
         "gen=accepted+b（per-request 恒等；gen=320=220+100）")
    need(abs(r["committed_decode_tps"] - 320.0) < 0.05
         and abs(r["agg"] - 320.0) < 0.05, "committed=agg 同式（4×80 流共同窗）")
    need(abs(r["full_accept_equiv_tps"] - 600.0) < 0.05,
         "full-accept=600=320×6/3.2（副标签，不得当真实吞吐）")
    need(r["closure"]["sum_completion_minus_1"] == 1280
         and r["closure"]["sum_generated"] == 1280
         and r["closure"]["identity_sum_completion_eq_generated"] is True,
         "Σ(completion−1)=Σgenerated=1280（客户端-引擎闭合）")
    need(r["closure"]["identity_gen_eq_accepted_plus_b"] is True, "closure 恒等式 b 面")
    need(r["closure"]["identity_accept_len"] is True
         and r["closure"]["accept_len_identity_mode"] == "exact",
         "accept_len=1+γ·rate（整窗满发 draft：proposed=γ·b）")
    # 重复计数反例（INV-02 §7 反例 1：accepted 把 golden 再算 ⇒ 2560≠1280 必红）
    bad_rows = run_de(_SpecClient(accepted=220 + 320), "prose", 4, 321, 0, 1,
                      capture_spec=True, nextn=5)[0]
    need(bad_rows["closure"]["identity_gen_eq_accepted_plus_b"] is False,
         "bonus 重复计数必红（gen≠accepted+b）")
    # 截断步（proposed<γ·b）恒等式不强判、只注记
    tr = run_de(_SpecClient(prop=499), "prose", 1, 321, 0, 1, capture_spec=True, nextn=5)[0]
    need(tr["closure"]["identity_accept_len"] is None
         and tr["closure"]["accept_len_identity_mode"] == "truncated",
         "流末步截断：accept_len 恒等式注记不强判")
    # 缺 sglext（capture on，模拟网关剥离）必须红不静默；默认路径 spec 面=None 不造数
    try:
        run_de(_SpecClient(no_spec=True), "prose", 1, 321, 0, 1, capture_spec=True)
        need(False, "缺 sglext（capture on）必须红")
    except RuntimeError as e:
        need("sglext" in str(e), f"缺 sglext 红不静默（{str(e)[:48]}…）")
    plain = run_de(_SpecClient(), "prose", 1, 321, 0, 1)[0]
    need(plain["full_accept_equiv_tps"] is None and plain["accept_rate"] is None
         and plain["avg_verified_len"] is None
         and plain["closure"]["identity_sum_completion_eq_generated"] is None
         and plain["committed_decode_tps"] == plain["agg"],
         "默认路径：spec 面 None 不造数；committed=agg 同式照出")

    # ── 9. --legacy-csv 键序与离线回放判别力（合成 + 坏输入必红）──
    leg = strip_legacy_rows({"label": "sd", "de": [plain]})
    need(list(leg["de"][0]) == list(DE_ROW_LEGACY_KEYS),
         "--legacy-csv 行=旧键序（type,conc,per,per_all,agg,completion）")
    ok8 = {"type": "prose", "conc": 8, "per": 32.58,
           "per_all": [31.98, 33.88, 32.82, 31.79, 32.58, 31.14, 35.07, 31.79],
           "agg": 249.1, "completion": [400] * 8}
    need(check_de_row(ok8)[0], "旧 schema 行闭合（6.17 证据 de_c8 run1 同数）")
    need(not check_de_row({**ok8, "agg": 260.0})[0], "agg 超共同窗上限必红")
    need(not check_de_row({**ok8, "per": 40.0})[0], "per≠median(per_all) 必红")
    need(not check_de_row({**ok8, "conc": 8, "per_all": ok8["per_all"][:7]})[0],
         "流数不闭合必红")
    prow = {"target": 131072, "prompt_tokens": 131083, "ttft_s": 21.161, "tok_s": 6194.6,
            "prompt_chars": 524287, "chars_per_token": 4.0, "filler": "repeated"}
    need(check_pr_row(prow)[0], "PR 行闭合（tok_s=prompt_tokens/TTFT）")
    need(not check_pr_row({**prow, "tok_s": 9999.0})[0], "PR tok_s 虚假必红")
    need(not check_pr_row({**prow, "cached_tokens": 50000, "uncached_tokens": 123})[0],
         "PR uncached≠prompt−cached 必红")
    bad_req_row = {**ok8, "per_request": [
        {"completion": 321, "generated": 320, "accepted": 540, "b": 100, "proposed": 500,
         "accept_len": 3.2, "accept_rate": 0.44, "verified_len": 5.0,
         "committed_decode_tps": 80.0, "full_accept_equiv_tps": 150.0,
         "reasoning_tokens": 0, "cached_tokens": 0, "gen_eq_accepted_plus_b": False}]}
    need(not check_de_row(bad_req_row)[0], "per_request 重复计数必红（回放面）")

    # ── 10. DF-04：PR --runs 生效（每档 N 次独立调用 + 逐发记录 + 中位数 + 极差）──
    flat = run_pr(_SpecClient(), [4096], runs=1)[0]
    need(list(flat) == list(PR_FLAT_ROW_KEYS) and flat["target"] == 4096,
         "DF-04 runs=1 行=旧扁平 schema 键序（旧锚/旧管道逐字节可比）")
    need(check_pr_row(flat)[0], "DF-04 runs=1 行闭合（合成：tok_s=1280.0）")
    r3 = run_pr(_SpecClient(), [4096], runs=3)[0]
    need(r3["runs"] == 3 and len(r3["shots"]) == 3, "runs=3 ⇒ 每档 3 条独立记录")
    need(len(set(s["salt"] for s in r3["shots"])) == 3, "每发独立 fresh salt（防跨发前缀缓存）")
    need(all(s["tok_s"] == 1280.0 and s["ttft_s"] == 0.05 for s in r3["shots"]),
         "逐发记录含 tok_s/ttft_s（合成固定 1280.0/0.05）")
    need(r3["tok_s_median"] == 1280.0 and r3["tok_s_range"] == 0.0
         and r3["ttft_s_median"] == 0.05 and r3["ttft_s_range"] == 0.0,
         "同值三发：median=1280.0 / 极差=0（合成对表）")
    need(check_pr_row(r3)[0], "runs=3 行闭合（median/min/max/极差与逐发自洽）")

    class _PrVarClient(_SpecClient):
        """逐发递增 TTFT 的合成客户端（DF-04 变异对表：第 k 次调用 ttft=0.05+0.01k）。"""

        def __init__(self):
            super().__init__()
            self.k = 0

        def stream(self, prompt, max_tokens, temperature=0.0, top_p=1.0,
                   extra_body=None, capture_spec=False):
            self.k += 1
            o = super().stream(prompt, max_tokens, temperature, top_p, extra_body,
                               capture_spec)
            o["t_req"] = o["t_first"] - (0.05 + 0.01 * self.k)
            return o

    rv = run_pr(_PrVarClient(), [4096], runs=3)[0]
    # warmup 消耗 k=1；档内三发 k=2,3,4 ⇒ ttft=0.07/0.08/0.09 ⇒ tok_s=914.3/800.0/711.1
    need([s["tok_s"] for s in rv["shots"]] == [914.3, 800.0, 711.1],
         "逐发记录保序（合成递增 ttft ⇒ tok_s 914.3/800.0/711.1）")
    need(rv["tok_s_median"] == 800.0 and rv["tok_s_min"] == 711.1
         and rv["tok_s_max"] == 914.3 and rv["tok_s_range"] == 203.2,
         "median/min/max/极差 对表（800.0 / 711.1 / 914.3 / 203.2）")
    need(rv["ttft_s_median"] == 0.08 and rv["ttft_s_range"] == 0.02,
         "ttft 中位/极差 对表（0.08 / 0.02）")
    need(check_pr_row(rv)[0], "变异行闭合（回放面自洽）")
    need(not check_pr_row({**rv, "tok_s_median": 999.0})[0], "median 虚假必红")
    dup = {**rv, "shots": [dict(rv["shots"][i], salt="deadbeef") for i in range(3)]}
    need(not check_pr_row(dup)[0], "shots salt 重复必红（fresh salt 口径）")
    try:
        run_pr(_SpecClient(), [8], runs=0)
        need(False, "runs=0 必须红")
    except ValueError as e:
        need("runs" in str(e), f"runs<1 红不静默（{str(e)[:40]}…）")
    leg3 = strip_legacy_rows({"label": "sd", "pr": [r3]})
    need(len(leg3["pr"]) == 3
         and all(list(x) == list(PR_ROW_LEGACY_KEYS) for x in leg3["pr"]),
         "--legacy-csv：shots 行逐发展开 3 条旧键行（旧管道兼容）")

    try:  # 坏端点必须因正确理由红
        Client("http://127.0.0.1:1/v1", "k", 2).stream(DE_PROSE_PROMPT, 32)
        need(False, "坏端点必须红")
    except Exception as e:
        need("Connection" in type(e).__name__ or "connection" in str(e).lower(), f"坏端点红（{type(e).__name__}）")

    # ── 11. EQ-11 参数面统一：URL 三形归一 + 拒起首行 ERROR 摘要（零请求离线）──
    import contextlib as _ctx
    import io as _io
    b = bench_url.v1_base
    need(b("http://127.0.0.1:8899", flag="--base-url", prog="sd_bench.py")
         == "http://127.0.0.1:8899/v1", "EQ-11 origin 形归一补 /v1")
    need(b("http://127.0.0.1:8899/v1", flag="--base-url", prog="sd_bench.py")
         == "http://127.0.0.1:8899/v1", "EQ-11 v1 基形原样（旧正确形逐字节不变）")
    need(b("http://127.0.0.1:8899/v1/", flag="--base-url", prog="sd_bench.py")
         == "http://127.0.0.1:8899/v1", "EQ-11 尾斜坡形归一")
    need(b("http://127.0.0.1:8899/v1/chat/completions", flag="--base-url", prog="sd_bench.py")
         == "http://127.0.0.1:8899/v1", "EQ-11 全路径形剥 /chat/completions（旧 404 形修复）")
    need(b("https://h.example/api", flag="--base-url", prog="sd_bench.py")
         == "https://h.example/api", "EQ-11 自定义挂载路径原样保留自担")
    need(bench_url.chat_completions("http://127.0.0.1:8899/v1", flag="--base-url", prog="sd_bench.py")
         == "http://127.0.0.1:8899/v1/chat/completions",
         "EQ-11 请求 URL=旧正确形逐字节同（Client.stream 拼接不变量）")
    need(Client("http://127.0.0.1:1", "k", 2).base == "http://127.0.0.1:1/v1",
         "EQ-11 Client 构造即归一（origin 形不再等到请求才 404）")
    for bad in ("foo", "://x", "http://", "127.0.0.1:8899"):  # 错 URL 形必红：首行 ERROR 摘要 + exit 2
        buf = _io.StringIO()
        try:
            with _ctx.redirect_stderr(buf):
                Client(bad, "k", 2)
            need(False, f"错 URL 形 {bad!r} 必须拒起")
        except SystemExit as e:
            first = buf.getvalue().splitlines()[0] if buf.getvalue() else ""
            need(e.code == 2 and first.startswith("ERROR[sd_bench.py]:"),
                 f"错 URL 形 {bad!r} 首行 ERROR 摘要+exit 2（{first[:44]}…）")
    p = bench_url.BenchArgumentParser(prog="sd_bench.py")
    buf = _io.StringIO()
    try:
        with _ctx.redirect_stderr(buf):
            p.error("argument --type: invalid choice: 'prose2'")
        need(False, "拒起必须 exit")
    except SystemExit as e:
        first = buf.getvalue().splitlines()[0] if buf.getvalue() else ""
        need(e.code == 2 and first.startswith("ERROR[sd_bench.py]:"),
             f"argparse 拒起首行 ERROR 摘要+exit 2（{first[:44]}…）")
    print("SELFCHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = bench_url.BenchArgumentParser(prog="sd_bench.py")  # EQ-11：拒起首行 ERROR 摘要 + exit 2
    ap.add_argument("--mode", choices=("de", "pr"), required=False,
                    help="de/pr；--selfcheck 时可不填")
    ap.add_argument("--type", choices=DE_TYPES, default="prose")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--runs", type=int, default=None,
                    help="重复次数。DE 缺省 5；PR 缺省 1（旧单发口径，旧锚/旧管道可比）。"
                         "PR 下显式 N>1=每档 N 次独立调用（每发 fresh salt），行含 shots"
                         " 逐发记录+median/极差（DF-04：PR 不再静默吞参）")
    ap.add_argument("--warmups", type=int, default=2)  # knapcio 口径：first run after two warm-ups
    ap.add_argument("--sizes", "--targets", type=int, nargs="+", default=[4096, 8192, 16384, 32768],
                    help="PR 档位（token 数）。--targets 是 --sizes 的等价别名（EQ-11 参数面统一）")
    ap.add_argument("--pr-filler", choices=("repeated", "random", "real"), default="repeated",
                    help="PR 填充口径：repeated=sparkDash 原样（行缓存膨胀）；random=均匀词汤（P5）；"
                         "real=真实文本分布（ds_gate 语料生成器，MiaAI-Lab#21 口径）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8899/v1")
    ap.add_argument("--key-file", default="state/api-key")
    ap.add_argument("--label", default="sd")
    ap.add_argument("--json-out")
    ap.add_argument("--capture-spec", action="store_true",
                    help="T33-03 双口径采集：body 加 return_spec_tokens_details 与 "
                         "chat_template_kwargs.thinking=False（钉 thinking）；缺 sglext 必红。"
                         "默认关=请求体与旧版逐字节相同")
    ap.add_argument("--nextn", type=int, default=NEXTN_DEFAULT,
                    help="投机 nextn（γ，DSPARK 静态=5）；full_accept_equiv_tps="
                         "committed×(1+γ)/accept_len（副标签）")
    ap.add_argument("--legacy-csv", action="store_true",
                    help="输出裁回旧 schema 键序（回退面/旧管道兼容；不影响请求体）")
    ap.add_argument("--replay", nargs="+", metavar="FILE",
                    help="离线回放既有 JSON（旧/新 schema 通吃）验证闭合；零请求零产线触")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    if a.replay:
        return replay(a.replay, nextn=a.nextn)
    if not a.mode:
        ap.error("--mode 必填（仅 --selfcheck/--replay 时可省）")
    # DF-04：--runs 缺省分模式——DE=5（旧默认）；PR=1（旧实际行为，pr_ladder6.sh 等
    # 在役链按「每次调用=单发读数」解析产物，缺省变更即断链）；显式传值两模式均真生效。
    runs = a.runs if a.runs is not None else (5 if a.mode == "de" else 1)
    if runs < 1:
        bench_url.fail("sd_bench.py", f"--runs 必须 ≥1（got {runs}）")  # EQ-11：首行 ERROR 摘要 + exit 2
    if a.mode == "pr" and runs > 1:
        print(f"[sd_bench] DF-04：pr 模式 --runs {runs} 生效——每档 {runs} 发独立调用"
              f"（每发 fresh salt），产物含 shots 逐发记录+median/极差", file=sys.stderr)
    if a.concurrency not in ALLOWED_CONC:
        bench_url.fail("sd_bench.py", f"--concurrency 必须是 {ALLOWED_CONC}（got {a.concurrency}）")
    key = ""
    try:
        key = open(a.key_file).read().strip()
    except OSError:
        pass
    c = Client(a.base_url, key, timeout_s=max(120, a.max_tokens * 8))
    data = {"label": a.label,
            "de": run_de(c, a.type, a.concurrency, a.max_tokens, a.warmups, runs,
                         capture_spec=a.capture_spec, nextn=a.nextn)} if a.mode == "de" \
        else {"label": a.label, "pr": run_pr(c, a.sizes, runs=runs, filler=a.pr_filler,
                                             capture_spec=a.capture_spec)}
    if a.legacy_csv:
        data = strip_legacy_rows(data)
    print(json.dumps(data, ensure_ascii=False))
    if a.json_out:
        open(a.json_out, "w").write(json.dumps(data, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
