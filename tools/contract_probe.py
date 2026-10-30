#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_probe — 功能面契约测试量具（EQ-04 新增，任务书 035-W0-TASKBOOK-20261030.md §EQ-04）。

背景（为什么）：
  外部手册部署篇 §41/升级篇 §17 自称「整份手册最重要的一条」：51 键 env 逐字对表全绿，
  一带 tools 的真请求即暴出「工具调用标记漏成明文」的 P0——形面验收（旗标/横幅）与
  功能面验收（按实际使用方式打真请求）之间没有工具桥。仓内实测（2026-10-30）仅有
  tools/serve_flags_gate.sh（argv//get_server_info 旗标断言），无带 tools 的 chat
  契约测试工具，本件即补此缺。

功能面（对每个终点各打 3 例，共 6 例）：
  tools-nostream  带 tools 的 chat，stream=False——断言返回结构化 message.tool_calls
                  （id/type/function.name/function.arguments 合法 JSON），且 content
                  不含任何已知工具边界标记（漏成明文=FAIL）；
  tools-stream    同题 stream=True——SSE 分片按 index 拼装回完整 tool_calls 后同判
                  （标记跨分片切开亦须被抓）；
  retrieval       长上下文检索题（needle_probe 同源制式：seed 播种 filler+8 位十六
                  进制魔码埋深度中点，非流式单问单答）——判读线 finish=stop 且正文
                  非空，另加答中魔码（needle 制式同源）。
  终点：--gateway（缺省 http://127.0.0.1:8001 只读网关文本车道口，Bearer GW_API_KEY
  鉴权，见 tools/packages/gateway/payload/concurrency_proxy_v2.py:81,215）与
  --engine（缺省 http://127.0.0.1:8898 引擎直连测试口）。量具一律在 head 机回环打点
  （GETTING-STARTED.md §3：引擎只绑 head 机 127.0.0.1）。

判读线（任务书 §EQ-04 验收门逐条落具）：
  ① 工具调用漏成明文 0 例——content 命中 TOOL_MARKERS 任一即 FAIL（标记表随输出
    打印供审计，--extra-marker 可加站点特有形）；
  ② 长上下文检索题 finish=stop 且正文非空（另加答中魔码）；
  ③ tools 两例 finish 语义正常——finish_reason ∈ {stop, tool_calls}（两者皆为干净的
    正常收束语义；判读官要求严式 stop-only 时用 --tools-finish-ok stop 收窄）。

安全制式（本单元只建量具，未打任何真请求）：
  - 缺省 dry-run：只打印将发的请求（鉴权值脱敏），零网络；
  - --send 才真发（须在役引擎可达窗+判读纪律随身；请求全部只读——单发低并发，
    不占水位门，非压力量具）；
  - 8899=生产口恒拒发（dry-run 亦拒，--allow-remote 不豁免）——G5 生产口隔离，
    法源同 deploy/bin/r3-gate-endpoint-lint.sh:15；
  - --selftest 离线自测：fixture 驱动断言解析/判读逻辑
    （tools/contract_probe_selftest/manifest.json 台账），并以 socket 断连卫证明
    dry-run 全程零网络。

用法：
  python3 tools/contract_probe.py                          # 缺省 dry-run：打印 6 例将发请求
  python3 tools/contract_probe.py --only gateway           # 只打网关终点（dry-run 同律）
  python3 tools/contract_probe.py --send                   # 真发（引擎 8898+网关 8001 各 3 例）
  python3 tools/contract_probe.py --send --gw-key-file /path/to/gw.key
  python3 tools/contract_probe.py --send --gw-key "$GW_API_KEY" --engine-key-file /path
  python3 tools/contract_probe.py --selftest               # 离线自测（期望末行 SELFCHECK PASS）
  鉴权来源优先级：--gw-key > --gw-key-file > env CONTRACT_PROBE_GW_KEY > env GW_API_KEY；
  引擎侧：--engine-key > --engine-key-file > env CONTRACT_PROBE_ENGINE_KEY > env VLLM_API_KEY。

退出码：0=全过（dry-run=完整打印）；1=有 FAIL（契约负例）；2=用法/取证失败（fail-closed）。
"""
import argparse
import json
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ── 常量面 ────────────────────────────────────────────────────────────────────
PROG = "contract_probe"
PROD_PORT = "8899"                       # 生产口恒拒（G5 隔离，endpoint-lint 法源）
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
UNKNOWN_FORM_LIMIT = 131072              # needle 制式：未登记形态 fail-closed ≤128k 红线
DEFAULT_MODEL = "deepseek-v4.1-flash"    # 与 needle_probe.py:235 同源缺省

# 工具调用明文边界标记表（判读线①的检测面；随输出打印供审计，--extra-marker 可扩充）。
TOOL_MARKERS = (
    # DeepSeek 官方边界符族（U+FF5C 全角竖线 + U+2581 下八分块；--tool-call-parser
    # deepseekv41 的原生形——parser 未接线/失配时漏出的正是这族标记）
    "<｜tool▁calls▁begin｜>", "<｜tool▁calls▁end｜>", "<｜tool▁call▁begin｜>",
    "<｜tool▁call▁end｜>", "<｜tool▁sep｜>",
    # ASCII 转写形（上游模板/文档常见转写）
    "<|tool_calls_begin|>", "<|tool_calls_end|>", "<|tool_call_begin|>", "<|tool_call_end|>",
    # Qwen/Hermes 通用形
    "<tool_call>", "</tool_call>", "<tool_calls>", "</tool_calls>",
    # Mistral/Llama 形
    "[TOOL_CALLS]", "[/TOOL_CALLS]", "[TOOL_CALL]", "[/TOOL_CALL]",
    # 旧模板形
    "<function=", "</function>",
)

# 只读契约测试工具面（量具自随，无副作用；题目显式要求走工具调用路径）
TOOLS_SPEC = (
    {"type": "function", "function": {
        "name": "get_server_time",
        "description": "查询服务器当前时间（只读工具）",
        "parameters": {"type": "object",
                       "properties": {"tz": {"type": "string", "description": "时区，如 Asia/Shanghai"}},
                       "required": []}}},
    {"type": "function", "function": {
        "name": "echo_text",
        "description": "原样返回给定文本（只读自检工具）",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}},
)

# filler 词表与 needle_probe.py WORDS 同源（seed 播种伪随机、跨 seed 不同文本，防行缓存假命中）
WORDS = ("time year people way day man thing woman life child world school state "
         "family student group country problem hand part place case week company "
         "system program question work government number night point home water "
         "room mother area money story fact month lot right study book eye job "
         "word business issue side kind head house service friend father hour "
         "line end member law car city name team minute idea kid body back parent "
         "face level office door health person art war history party result change "
         "morning reason research girl guy moment air teacher force education").split()


# ── 判读逻辑（纯函数，selftest 的断言对象） ────────────────────────────────────
def scan_leak(text):
    """判读线①：返回 content 中命中的明文工具边界标记列表。"""
    if not text:
        return []
    return [m for m in TOOL_MARKERS if m in text]


def validate_tool_calls(tool_calls):
    """结构化 tool_calls 结构面断言。返回 findings（空表=过）。"""
    findings = []
    if not isinstance(tool_calls, list) or not tool_calls:
        findings.append("结构化 tool_calls 缺失/为空（判读线：须返回结构化工具调用，而非明文标记）")
        return findings
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            findings.append(f"tool_calls[{i}] 非对象形")
            continue
        if not (isinstance(tc.get("id"), str) and tc.get("id")):
            findings.append(f"tool_calls[{i}].id 缺失/非字符串")
        if tc.get("type") != "function":
            findings.append(f"tool_calls[{i}].type={tc.get('type')!r}（期望 'function'）")
        fn = tc.get("function")
        if not (isinstance(fn, dict) and isinstance(fn.get("name"), str) and fn.get("name")):
            findings.append(f"tool_calls[{i}].function.name 缺失/非字符串")
        args = fn.get("arguments") if isinstance(fn, dict) else None
        if not isinstance(args, str) or not args.strip():
            findings.append(f"tool_calls[{i}].function.arguments 缺失/空")
        else:
            try:
                parsed = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                findings.append(f"tool_calls[{i}].function.arguments 非合法 JSON：{args[:80]!r}")
            else:
                if not isinstance(parsed, dict):
                    findings.append(f"tool_calls[{i}].function.arguments 合法 JSON 但非对象形")
    return findings


def validate_tools_case(content, tool_calls, finish_reason, ok_finishes):
    """tools 两例（流式拼装后与非流式同判）的完整判读。返回 findings（空表=过）。"""
    findings = validate_tool_calls(tool_calls)
    leaks = scan_leak(content)
    for hit in leaks:
        findings.append(f"工具调用漏成明文：content 含边界标记 {hit!r}（判读线①：漏成明文 0 例）")
    if not finish_reason:
        findings.append("finish_reason 缺失（finish 语义异常）")
    elif finish_reason not in ok_finishes:
        findings.append(f"finish 语义异常：{finish_reason!r}∉{sorted(ok_finishes)}（判读线③）")
    return findings


def validate_retrieval_case(content, finish_reason, magic):
    """长上下文检索题判读：finish=stop 且正文非空（判读线②）+答中魔码（needle 制式同源）。"""
    findings = []
    if finish_reason != "stop":
        findings.append(f"finish_reason={finish_reason!r}（判读线②：finish=stop 且正文非空）")
    if not (isinstance(content, str) and content.strip()):
        findings.append("正文为空（判读线②：finish=stop 且正文非空）")
    elif magic.lower() not in content.lower():
        findings.append(f"未答中魔码 {magic}（needle 制式：检索题须答中埋点魔码）")
    return findings


def parse_sse(text):
    """SSE 原文 → chunk 对象列表。data 行 JSON 解析；非 JSON data 行保留 _unparsable 供判读。"""
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(":"):        # 空行/SSE 注释（keepalive）
            continue
        if not line.startswith("data:"):
            continue
        body = line[5:].strip()
        if body == "[DONE]":
            break
        try:
            chunks.append(json.loads(body))
        except (json.JSONDecodeError, ValueError):
            chunks.append({"_unparsable": body[:200]})
    return chunks


def assemble_stream(chunks):
    """流式分片拼装：delta.content 串接、delta.tool_calls 按 index 拼回完整调用。

    标记跨分片切开由「先串接后扫描」天然覆盖（selftest 有专例）。
    """
    content_parts, calls, finish, usage, bad = [], {}, None, {}, 0
    for n, ch in enumerate(chunks, 1):
        if not isinstance(ch, dict):
            bad += 1
            continue
        if "_unparsable" in ch:
            bad += 1
            continue
        u = ch.get("usage")
        if isinstance(u, dict):
            usage.update(u)
        choices = ch.get("choices") or []
        if not choices:
            continue
        c = choices[0] if isinstance(choices[0], dict) else {}
        fr = c.get("finish_reason")
        if fr:
            finish = fr
        d = c.get("delta") or {}
        if d.get("content"):
            content_parts.append(d["content"])
        for tc in d.get("tool_calls") or []:
            if not isinstance(tc, dict):
                bad += 1
                continue
            i = tc.get("index", 0)
            slot = calls.setdefault(i, {"id": None, "type": None, "name": "", "arguments": ""})
            if tc.get("id"):
                slot["id"] = tc["id"]
            if tc.get("type"):
                slot["type"] = tc["type"]
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["name"] += fn["name"]
            if fn.get("arguments"):
                slot["arguments"] += fn["arguments"]
    tool_calls = [{"id": s["id"], "type": s["type"],
                   "function": {"name": s["name"], "arguments": s["arguments"]}}
                  for _, s in sorted(calls.items())]
    return {"content": "".join(content_parts), "tool_calls": tool_calls,
            "finish_reason": finish, "usage": usage, "chunks": len(chunks),
            "unparsable": bad}


# ── 请求构造面 ────────────────────────────────────────────────────────────────
def estimate_tokens(text):
    return len(text) // 4          # ≈4 chars/token（sd_bench/needle 同源口径）


def make_filler(seed, target_tokens):
    rng = random.Random(f"needle:{seed}")
    out, n = [], 0
    target_chars = target_tokens * 4
    while n < target_chars:
        w = WORDS[rng.randrange(len(WORDS))]
        out.append(w)
        n += len(w) + 1
    return " ".join(out)


def build_retrieval_prompt(target_tokens, seed, depth=0.5):
    """needle_probe.build_prompt 同源制式（header/filler/魔码句/题面），返回 (prompt, magic)。"""
    rng = random.Random(f"magic:{seed}")
    magic = "%08x" % rng.getrandbits(32)
    header = (f"[contract-probe {seed}]\nBelow is a long document. "
              "After reading it, answer the final question briefly.\n\n")
    footer = ("\n\nQuestion: What is the magic code hidden in the document above? "
              "Answer with the code only.")
    needle = f"\nThe magic code for this session is {magic}. Remember it.\n"
    fill_tokens = max(1, target_tokens - estimate_tokens(header + footer + needle) - 8)
    body = make_filler(seed, fill_tokens)
    cut = int(len(body) * depth)
    return header + body[:cut] + needle + body[cut:] + footer, magic


def build_tools_payload(model, stream):
    return {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "You are a contract test assistant. 你必须使用提供的工具完成任务。"},
            {"role": "user",
             "content": "请调用 get_server_time 工具（时区 Asia/Shanghai）查询服务器当前时间。"
                        "必须通过工具调用完成，禁止直接用文字回答时间。"},
        ],
        "tools": [dict(t) for t in TOOLS_SPEC],
        "tool_choice": "auto",
        "max_tokens": 128,
        "temperature": 0.0,
        "stream": bool(stream),
    }


def build_retrieval_payload(model, target_tokens, seed, depth, max_tokens):
    prompt, magic = build_retrieval_prompt(target_tokens, seed, depth)
    payload = {"model": model,
               "messages": [{"role": "user", "content": prompt}],
               "max_tokens": max_tokens, "temperature": 0.0, "stream": False}
    return payload, prompt, magic


# ── 终点卫与网络面 ────────────────────────────────────────────────────────────
def guard_url(name, url, allow_remote):
    """终点卫：8899 恒拒；非回环须 --allow-remote 显式豁免。返回 None=放行，否则拒因。"""
    try:
        p = urllib.parse.urlsplit(url)
        port = p.port or (443 if p.scheme == "https" else 80)
    except ValueError as exc:
        return f"{name} 终点 {url} 不可解析：{exc}"
    if p.scheme != "http":
        return f"{name} 终点 {url} 非 http 形（本量具只打回环明文口）"
    if str(port) == PROD_PORT:
        return (f"{name} 终点 {url} 命中 8899 生产口——本量具恒拒发（G5 生产口隔离，"
                f"--allow-remote 亦不豁免；法源 r3-gate-endpoint-lint.sh:15）")
    host = (p.hostname or "").strip("[]").lower()
    if host not in LOOPBACK_HOSTS and not allow_remote:
        return (f"{name} 终点 {url} 非回环口——量具须在 head 机回环打点"
                f"（GETTING-STARTED.md §3；确需远打用 --allow-remote 显式豁免）")
    return None


def mask_headers(headers):
    out = {}
    for k, v in headers.items():
        out[k] = f"***（已脱敏，{len(v)} 字）" if k.lower() == "authorization" else v
    return out


def read_key_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    return line
        return ""
    except OSError as exc:
        raise SystemExit(f"[{PROG}][用法错] 读键文件失败 {path}: {exc}")


def http_chat(url, payload, headers, timeout, want_stream):
    """POST /v1/chat/completions。非流式返回 (obj, status)；流式返回 (chunks, status)。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    h = dict(headers)
    h["Content-Type"] = "application/json"
    if want_stream:
        h.setdefault("Accept", "text/event-stream")
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions",
                                 data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        status = r.status
        if not want_stream:
            return json.loads(r.read().decode("utf-8")), status
        chunks = []
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                chunks.append(json.loads(body))
            except (json.JSONDecodeError, ValueError):
                chunks.append({"_unparsable": body[:200]})
        return chunks, status


# ── 用例计划与执行 ────────────────────────────────────────────────────────────
CASE_TOOLS_NS, CASE_TOOLS_S, CASE_RET = "tools-nostream", "tools-stream", "retrieval"


def plan_cases(args, endpoints):
    plan = []
    for ep_name, url, headers in endpoints:
        plan.append({"endpoint": ep_name, "url": url, "headers": headers,
                     "case": CASE_TOOLS_NS, "stream": False,
                     "payload": build_tools_payload(args.model, stream=False)})
        plan.append({"endpoint": ep_name, "url": url, "headers": headers,
                     "case": CASE_TOOLS_S, "stream": True,
                     "payload": build_tools_payload(args.model, stream=True)})
        payload, prompt, magic = build_retrieval_payload(
            args.model, args.retrieval_tokens, args.retrieval_seed,
            args.retrieval_depth, args.retrieval_max_tokens)
        plan.append({"endpoint": ep_name, "url": url, "headers": headers,
                     "case": CASE_RET, "stream": False, "payload": payload,
                     "prompt": prompt, "magic": magic})
    return plan


def print_request(item, full_body):
    """dry-run 打印将发的请求（鉴权脱敏；retrieval 正文过长者默认摘录，--full-body 全文）。"""
    print(f"[{item['endpoint']}][{item['case']}] DRY-RUN 将发请求（未发送、零网络）：")
    print(f"  POST {item['url'].rstrip('/')}/v1/chat/completions")
    hs = " ; ".join(f"{k}={v}" for k, v in mask_headers(item["headers"]).items()) \
         + (" ; " if item["headers"] else "") + "Content-Type=application/json"
    if item["stream"]:
        hs += " ; Accept=text/event-stream"
    print(f"  headers: {hs}")
    body = json.dumps(item["payload"], ensure_ascii=False, indent=2)
    if item["case"] == CASE_RET and not full_body:
        nbytes = len(json.dumps(item["payload"], ensure_ascii=False).encode("utf-8"))
        content = item["payload"]["messages"][0]["content"]
        excerpt = (content[:400] + "\n……〈长上下文正文中段摘录略〉……\n" + content[-200:])
        shown = dict(item["payload"])
        shown["messages"] = [{"role": "user", "content": excerpt}]
        print(f"  body 摘录（全文 {nbytes} 字节 / 正文 {estimate_tokens(content)} tok 估算；"
              f"--full-body 打印全文）：")
        print(json.dumps(shown, ensure_ascii=False, indent=2))
        print(f"  本例埋点魔码：{item['magic']}")
    else:
        print("  body:")
        print(body)
    print()


def execute_case(item, args, ok_finishes):
    """真发一例并判读。返回 (status, record)：status ∈ PASS/FAIL/ERROR。"""
    t0 = time.time()
    url = item["url"].rstrip("/") + "/v1/chat/completions"
    rec = {"endpoint": item["endpoint"], "case": item["case"], "url": url,
           "stream": item["stream"]}
    try:
        if item["case"] == CASE_RET:
            obj, status = http_chat(item["url"], item["payload"], item["headers"],
                                    args.timeout, want_stream=False)
            ch = (obj.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            findings = validate_retrieval_case(msg.get("content"),
                                               ch.get("finish_reason"), item["magic"])
            rec.update({"http_status": status,
                        "finish_reason": ch.get("finish_reason"),
                        "content_head": " ".join((msg.get("content") or "").split())[:120],
                        "magic": item["magic"],
                        "prompt_tokens": (obj.get("usage") or {}).get("prompt_tokens"),
                        "completion_tokens": (obj.get("usage") or {}).get("completion_tokens")})
        elif item["case"] == CASE_TOOLS_NS:
            obj, status = http_chat(item["url"], item["payload"], item["headers"],
                                    args.timeout, want_stream=False)
            ch = (obj.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            findings = validate_tools_case(msg.get("content"), msg.get("tool_calls"),
                                           ch.get("finish_reason"), ok_finishes)
            rec.update({"http_status": status, "finish_reason": ch.get("finish_reason"),
                        "content_head": " ".join((msg.get("content") or "").split())[:120],
                        "tool_call_names": [((t.get("function") or {}).get("name")
                                             if isinstance(t, dict) else None)
                                            for t in (msg.get("tool_calls") or [])],
                        "leak_markers": scan_leak(msg.get("content"))})
        else:  # tools-stream
            chunks, status = http_chat(item["url"], item["payload"], item["headers"],
                                       args.timeout, want_stream=True)
            asm = assemble_stream(chunks)
            findings = validate_tools_case(asm["content"], asm["tool_calls"],
                                           asm["finish_reason"], ok_finishes)
            if asm["unparsable"]:
                findings.append(f"流式分片含非 JSON data 行 ×{asm['unparsable']}（契约面异常）")
            rec.update({"http_status": status, "finish_reason": asm["finish_reason"],
                        "content_head": " ".join((asm["content"] or "").split())[:120],
                        "tool_call_names": [t["function"]["name"] for t in asm["tool_calls"]],
                        "leak_markers": scan_leak(asm["content"]),
                        "chunks": asm["chunks"],
                        "completion_tokens": (asm["usage"] or {}).get("completion_tokens")})
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001 — 取证尽力，不掩盖原错
            pass
        rec["error"] = f"HTTP {exc.code}: {detail}"
        return "ERROR", rec
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        rec["error"] = f"传输失败：{exc}"[:200]
        return "ERROR", rec
    rec["elapsed_s"] = round(time.time() - t0, 2)
    rec["findings"] = findings
    verdict = "PASS" if not findings else "FAIL"
    return verdict, rec


def report_case(rec, verdict):
    line = f"[{rec['endpoint']}][{rec['case']}] {verdict}"
    if verdict == "ERROR":
        print(f"{line} —— 取证失败：{rec.get('error')}")
        return
    extras = []
    if rec.get("tool_call_names"):
        extras.append("tool_calls=" + ",".join(str(n) for n in rec["tool_call_names"]))
    if rec.get("finish_reason"):
        extras.append(f"finish={rec['finish_reason']}")
    if rec.get("leak_markers") is not None:
        extras.append(f"明文泄漏={len(rec['leak_markers'])}")
    if rec.get("http_status"):
        extras.append(f"http={rec['http_status']}")
    if rec.get("elapsed_s") is not None:
        extras.append(f"{rec['elapsed_s']}s")
    suffix = (" —— " + "，".join(extras)) if extras else ""
    print(line + suffix)
    for f in rec.get("findings", []):
        print(f"  - FAIL 判读：{f}")


# ── 离线自测（--selftest，零网络） ────────────────────────────────────────────
def _fixture_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "contract_probe_selftest")


class NetBlocked(RuntimeError):
    pass


def selftest():
    ok = True

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        ok = ok and bool(cond)

    fdir = _fixture_dir()
    manifest_path = os.path.join(fdir, "manifest.json")
    need(os.path.isfile(manifest_path), f"fixture 台账在场 {manifest_path}")
    if not ok:
        print("SELFCHECK FAIL")
        return 1
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    # A. 标记判别力（判读线①的检测面）
    deepseek_leak = ("<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>function"
                     "<｜tool▁sep｜>get_server_time<｜tool▁call▁end｜><｜tool▁calls▁end｜>")
    need(scan_leak(deepseek_leak) != [], "DeepSeek 官方边界符族命中")
    need(scan_leak("好的，我调用 <tool_call>{\"tz\":\"Asia/Shanghai\"}</tool_call>") != [],
         "Qwen/Hermes 通用形命中")
    need(scan_leak("[TOOL_CALLS] get_server_time") != [], "Mistral 形命中")
    need(scan_leak("当前服务器时间是 14:03。") == [], "正常正文零误报")
    need(scan_leak("") == [] and scan_leak(None) == [], "空 content 零误报")
    # 标记跨分片切开：先拼装再扫描（流式天然覆盖）
    halves = ("答：<｜tool▁calls", "▁begin｜>get_server_time<｜tool▁calls▁end｜>")
    need(scan_leak("".join(halves)) != [], "跨分片切开的标记拼装后仍命中")

    # B. 结构校验判别力
    good_call = [{"id": "c1", "type": "function",
                  "function": {"name": "get_server_time",
                               "arguments": "{\"tz\": \"Asia/Shanghai\"}"}}]
    need(validate_tool_calls(good_call) == [], "结构完整的 tool_calls 零 findings")
    need(validate_tool_calls([]) != [], "空 tool_calls 判负")
    bad_args = [{"id": "c1", "type": "function",
                 "function": {"name": "get_server_time", "arguments": "{'tz': 'x'}"}}]
    need(any("JSON" in f for f in validate_tool_calls(bad_args)),
         "arguments 非合法 JSON 判负")
    need(validate_tools_case("", good_call, "stop", {"stop", "tool_calls"}) == [],
         "tools 例正判（content 空+tool_calls 全+finish=stop）")
    need(validate_tools_case("答：<tool_call>x</tool_call>", good_call, "stop",
                             {"stop", "tool_calls"}) != [], "tools 例明文泄漏判负")
    need(validate_tools_case("", good_call, "length", {"stop", "tool_calls"}) != [],
         "tools 例 finish=length 判负")

    # C. 检索题判读线（判读线②）
    need(validate_retrieval_case("3f2a9c1d", "stop", "3f2a9c1d") == [],
         "检索题正判（finish=stop+正文非空+答中魔码）")
    need(validate_retrieval_case("3f2a9c1d", "length", "3f2a9c1d") != [],
         "检索题 finish≠stop 判负")
    need(validate_retrieval_case("", "stop", "3f2a9c1d") != [], "检索题正文空判负")
    need(validate_retrieval_case("不知道", "stop", "3f2a9c1d") != [], "检索题未答中魔码判负")

    # D. fixture 驱动（台账逐条；含流式拼装负例）
    kinds_ok = True
    for ent in manifest.get("fixtures", []):
        fpath = os.path.join(fdir, ent["file"])
        label = f"fixture {ent['file']}（{ent['kind']}→{ent['expect']}）"
        if not os.path.isfile(fpath):
            print("FAIL", label + "：文件缺")
            kinds_ok = False
            continue
        with open(fpath, "r", encoding="utf-8") as fh:
            raw = fh.read()
        try:
            if ent["kind"] == "tools_nostream":
                obj = json.loads(raw)
                ch = (obj.get("choices") or [{}])[0]
                msg = ch.get("message") or {}
                findings = validate_tools_case(msg.get("content"), msg.get("tool_calls"),
                                               ch.get("finish_reason"),
                                               tuple(ent.get("ok_finishes", ("stop", "tool_calls"))))
            elif ent["kind"] == "tools_stream":
                asm = assemble_stream(parse_sse(raw))
                findings = validate_tools_case(asm["content"], asm["tool_calls"],
                                               asm["finish_reason"],
                                               tuple(ent.get("ok_finishes", ("stop", "tool_calls"))))
            elif ent["kind"] == "retrieval":
                obj = json.loads(raw)
                ch = (obj.get("choices") or [{}])[0]
                msg = ch.get("message") or {}
                findings = validate_retrieval_case(msg.get("content"),
                                                   ch.get("finish_reason"), ent["magic"])
            else:
                print("FAIL", label + f"：未知 kind {ent['kind']!r}")
                kinds_ok = False
                continue
        except Exception as exc:  # noqa: BLE001 — fixture 坏=自测红，不掩盖
            print("FAIL", label + f"：解析/判读异常 {exc}")
            kinds_ok = False
            continue
        verdict = "PASS" if not findings else "FAIL"
        good = verdict == ent["expect"]
        for kw in ent.get("expect_keywords", []):
            if not any(kw in f for f in findings):
                good = False
        print(("PASS" if good else "FAIL"),
               label + ("" if good else f"：得 {verdict}，findings={findings}"))
        kinds_ok = kinds_ok and good
    need(kinds_ok, "fixture 台账逐条判读与期望一致")

    # E. 台账登记完整性：目录内 fixture 文件全部被 manifest 引用（防孤儿/漏跑）
    listed = {e["file"] for e in manifest.get("fixtures", [])}
    on_disk = {f for f in os.listdir(fdir)
               if f != "manifest.json" and f != "README.md" and not f.startswith(".")}
    need(on_disk == listed, f"fixture 登记完整（盘上 {sorted(on_disk - listed)} 未登记 / "
                            f"台账 {sorted(listed - on_disk)} 缺文件）" if on_disk != listed
         else "fixture 登记完整（盘上文件与台账一一对应）")

    # F. 终点卫：8899 恒拒+非回环须豁免
    need(guard_url("t", "http://127.0.0.1:8899/v1", allow_remote=True) is not None,
         "8899 生产口恒拒（--allow-remote 亦不豁免）")
    need(guard_url("t", "http://127.0.0.1:8899/v1", allow_remote=False) is not None,
         "8899 生产口 dry-run 形同拒")
    need(guard_url("t", "http://10.0.0.5:8001", allow_remote=False) is not None,
         "非回环口无 --allow-remote 拒")
    need(guard_url("t", "http://10.0.0.5:8001", allow_remote=True) is None,
         "非回环口 --allow-remote 显式豁免放行")
    need(guard_url("t", "http://127.0.0.1:8898", allow_remote=False) is None,
         "回环测试口 8898 放行")
    need(guard_url("t", "http://127.0.0.1:8001", allow_remote=False) is None,
         "回环网关口 8001 放行")

    # G. 请求构造面
    p_ns, p_s = build_tools_payload("m", stream=False), build_tools_payload("m", stream=True)
    need(len(p_ns["tools"]) == 2 and p_ns["stream"] is False, "非流式 payload 带 tools 且 stream=False")
    need(p_s["stream"] is True and p_s["tools"] == p_ns["tools"], "流式 payload 同题面且 stream=True")
    pr1, m1 = build_retrieval_prompt(32768, "eq04")
    pr2, m2 = build_retrieval_prompt(32768, "eq04")
    need(pr1 == pr2 and m1 == m2, "检索题同 seed 可复现（同魔码同正文）")
    need(len(m1) == 8 and all(c in "0123456789abcdef" for c in m1), "魔码 8 位十六进制")
    need(31000 <= estimate_tokens(pr1) <= 34500,
         f"32K 档覆盖（{estimate_tokens(pr1)} tok 估算）")

    # H. dry-run 零网络证明：socket 断连卫下走完 dry-run 主路
    orig_connect = socket.socket.connect

    def blocked_connect(self, address):  # noqa: ANN001
        raise NetBlocked(f"selftest 禁网络：试图连 {address}")

    net_clean = True
    try:
        socket.socket.connect = blocked_connect
        ep = [("engine", "http://127.0.0.1:8898", {})]
        plan = plan_cases(argparse.Namespace(model="m", retrieval_tokens=4096,
                                             retrieval_seed="sc", retrieval_depth=0.5,
                                             retrieval_max_tokens=64), ep)
        for item in plan:
            print_request(item, full_body=False)
    except NetBlocked as exc:
        net_clean = False
        print("FAIL", f"dry-run 零网络被证伪：{exc}")
    finally:
        socket.socket.connect = orig_connect
    need(net_clean and len(plan) == 3, "dry-run 三例在 socket 断连卫下完整打印（零网络）")

    print("SELFCHECK " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ── 主路 ─────────────────────────────────────────────────────────────────────
def collect_endpoints(args):
    eps = []
    if args.only in (None, "gateway"):
        key = args.gw_key or (read_key_file(args.gw_key_file) if args.gw_key_file else None) \
            or os.environ.get("CONTRACT_PROBE_GW_KEY") or os.environ.get("GW_API_KEY")
        eps.append(("gateway", args.gateway, {"Authorization": "Bearer " + key} if key else {}))
    if args.only in (None, "engine"):
        key = args.engine_key or (read_key_file(args.engine_key_file) if args.engine_key_file else None) \
            or os.environ.get("CONTRACT_PROBE_ENGINE_KEY") or os.environ.get("VLLM_API_KEY")
        eps.append(("engine", args.engine, {"Authorization": "Bearer " + key} if key else {}))
    return eps


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        prog=PROG,
        description="EQ-04 功能面契约测试量具：网关口与引擎直连口各打带 tools 的 chat（流式/非流式）"
                    "与长上下文检索题，断言结构化 tool_calls 而非明文标记、finish 语义正常。"
                    "缺省 dry-run 零网络；--send 才真发；8899 生产口恒拒。",
        epilog="详见文件头注释（判读线/安全制式/退出码）。")
    ap.add_argument("--gateway", default="http://127.0.0.1:8001",
                    help="网关终点（只读网关文本车道口，参考形 8001；Bearer 鉴权）")
    ap.add_argument("--engine", default="http://127.0.0.1:8898",
                    help="引擎直连终点（测试口参考形 8898；性能量具同口径）")
    ap.add_argument("--only", choices=("gateway", "engine"),
                    help="只打其中一个终点（缺省两者都打）")
    ap.add_argument("--model", default=os.environ.get("CONTRACT_PROBE_MODEL", DEFAULT_MODEL),
                    help=f"模型名（缺省 {DEFAULT_MODEL}，与 needle_probe 同源；"
                         f"网关清单正典以 /v1/models 为准——EQ-09 口径）")
    ap.add_argument("--send", action="store_true",
                    help="真发请求（缺省 dry-run 只打印将发请求；真发须在役引擎可达窗）")
    ap.add_argument("--allow-remote", action="store_true",
                    help="豁免回环限制（8899 生产口仍恒拒）")
    ap.add_argument("--gw-key", help="网关 Bearer 键值（优先级最高；缺省脱敏打印）")
    ap.add_argument("--gw-key-file", help="网关 Bearer 键文件（取首个非空行）")
    ap.add_argument("--engine-key", help="引擎侧 Bearer 键值（上游若设 VLLM_API_KEY 鉴权时用）")
    ap.add_argument("--engine-key-file", help="引擎侧 Bearer 键文件")
    ap.add_argument("--timeout", type=float, default=600.0,
                    help="单请求超时秒（缺省 600：32K 长上下文冷缓存 prefill 余量）")
    ap.add_argument("--tools-finish-ok", default="stop,tool_calls",
                    help="tools 两例可接受的 finish_reason 集合（缺省 stop,tool_calls；"
                         "严式判读官收窄为 stop）")
    ap.add_argument("--retrieval-tokens", type=int, default=32768,
                    help=f"长上下文检索题目标 token（缺省 32768；fail-closed 上限 "
                         f"{UNKNOWN_FORM_LIMIT}，needle 未登记形态红线同源）")
    ap.add_argument("--retrieval-seed", default="eq04", help="检索题 seed（同 seed 可复现）")
    ap.add_argument("--retrieval-depth", type=float, default=0.5, help="魔码埋深（缺省中点）")
    ap.add_argument("--retrieval-max-tokens", type=int, default=64,
                    help="检索题 max_tokens（缺省 64）")
    ap.add_argument("--extra-marker", action="append", default=[],
                    help="追加站点特有明文标记（可重复；入 TOOL_MARKERS 检测面）")
    ap.add_argument("--json-out", help="机读结果落盘路径（含逐例判读与汇总）")
    ap.add_argument("--full-body", action="store_true",
                    help="dry-run 打印检索题全文 body（缺省摘录，防刷屏）")
    ap.add_argument("--selftest", action="store_true",
                    help="离线自测：fixture 驱动断言解析逻辑+socket 卫证 dry-run 零网络")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    global TOOL_MARKERS
    if args.extra_marker:
        TOOL_MARKERS = tuple(TOOL_MARKERS) + tuple(args.extra_marker)

    if not (1 <= args.retrieval_tokens <= UNKNOWN_FORM_LIMIT):
        print(f"[{PROG}][用法错] --retrieval-tokens {args.retrieval_tokens} 越界"
              f"[1,{UNKNOWN_FORM_LIMIT}]（fail-closed：未登记形态 ≤128k 红线，needle 同源）")
        return 2
    ok_finishes = {s.strip() for s in args.tools_finish_ok.split(",") if s.strip()}
    if not ok_finishes:
        print(f"[{PROG}][用法错] --tools-finish-ok 为空集合")
        return 2

    endpoints = collect_endpoints(args)
    refused = [(n, u, guard_url(n, u, args.allow_remote)) for n, u, _ in endpoints]
    for n, u, why in refused:
        if why:
            print(f"[{PROG}][FAIL-CLOSED] {why}")
    if any(why for _, _, why in refused):
        return 2

    plan = plan_cases(args, endpoints)
    records, n_pass = [], 0

    if not args.send:
        print(f"[{PROG}] dry-run 模式：只打印将发的 {len(plan)} 例请求，零网络"
              f"（真发加 --send，须在役引擎可达窗+判读纪律随身）")
        if TOOL_MARKERS:
            print(f"[{PROG}] 明文标记检测面 {len(TOOL_MARKERS)} 条"
                  f"（含 --extra-marker 追加；判读线①）")
        for item in plan:
            print_request(item, args.full_body)
            records.append({"endpoint": item["endpoint"], "case": item["case"],
                            "url": item["url"].rstrip("/") + "/v1/chat/completions",
                            "status": "DRY-RUN", "magic": item.get("magic")})
        print(f"[{PROG}] dry-run 完整打印 {len(records)} 例（退出 0；未发送任何请求）")
        if args.json_out:
            _dump(args, records, "dry-run")
        return 0

    print(f"[{PROG}] send 模式：真发 {len(plan)} 例（只读单发低并发，不占水位门；"
          f"终点 gateway={args.gateway} engine={args.engine}）")
    rc = 0
    for item in plan:
        verdict, rec = execute_case(item, args, ok_finishes)
        rec["status"] = verdict
        report_case(rec, verdict)
        records.append(rec)
        if verdict == "PASS":
            n_pass += 1
        elif verdict == "FAIL":
            rc = max(rc, 1)
        else:
            rc = 2
    n_fail = sum(1 for r in records if r.get("status") == "FAIL")
    n_err = sum(1 for r in records if r.get("status") == "ERROR")
    print(f"[{PROG}] 汇总：PASS {n_pass}/{len(records)}，FAIL {n_fail}，取证失败 {n_err}"
          f"（判读线：明文泄漏 0 例、检索题 finish=stop 且正文非空）")
    if args.json_out:
        _dump(args, records, "send")
    return rc


def _dump(args, records, mode):
    out = {"tool": PROG, "mode": mode, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "model": args.model, "gateway": args.gateway, "engine": args.engine,
           "retrieval_tokens": args.retrieval_tokens,
           "tools_finish_ok": sorted({s.strip() for s in args.tools_finish_ok.split(",")}),
           "markers": list(TOOL_MARKERS),
           "unit_note": "EQ-04 工具窗：本单元只建量具，未打真请求",
           "cases": records,
           "summary": {"total": len(records),
                       "pass": sum(1 for r in records if r.get("status") == "PASS"),
                       "fail": sum(1 for r in records if r.get("status") == "FAIL"),
                       "error": sum(1 for r in records if r.get("status") == "ERROR")}}
    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"[{PROG}] 机读结果落盘 {args.json_out}")


if __name__ == "__main__":
    sys.exit(main())
