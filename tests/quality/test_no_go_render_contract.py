# T33-10 —— G-RF `response_format` 负向护栏（CPU-only，必须 pass）
#
# 法源：docs/plan/033-TASKBOOK-V2-20261023.md §3.0.1 测试所有权表「G-RF」行（:342）、
#       T33-10 任务节目标 1/反例（:430-432, :452-455）、§3.0.3 硬规则（:361-369）。
# 分工边界（§3.0.1/§3.0.3 硬规则 2，不得越界）：
#   - 正例（首条 system 注入、json_schema/json_object 渲染、tools 并存、regex 变体、
#     dsv41 接线缺口 xfail）归 T33-01C test_response_format_positive.py，本文件不重复；
#   - fixture（encoding_dsv41 / baseline_prompt_hash 等）由 T33-01C conftest.py 唯一作者
#     提供，本文件只 import，不复制实现；
#   - Registry（033-W0/NO-GO-REGISTRY.md）是只读输入；G-RF 不依赖 Registry（使用规则 3）。
#
# 三条负向护栏（本文件唯一一个测试函数，验收门=1 passed）：
#   ①缺省 body 逐字节不变：无 response_format/无 tools 的请求，dsv41 渲染输出与
#     01C baseline_prompt_hash 基准逐字节一致（sha256 相等）；
#   ②SGLANG_DSV41_RF_INJECT 未开（未设或非真值）时，dsv41 路径不得把 request 级
#     schema 注入 system/prompt（不得出现 "## Response Format:" 段或 schema 字面）；
#   ③tools 在场时不得同时施加 prompt schema 与 tool-call（DSML）约束（禁双重约束）。
#
# 双层实现（变异记录据此打红，任务书目标 2）：
#   - 动态层：_dsv41_request_to_messages 镜像现役 overlay serving_chat.py dsv41 分支的
#     request→messages 接线事实（EV-05-019：request.response_format 现役不接线；
#     request.tools 挂到 messages[0]["tools"]，chat_encoding.dsv41_tool_payload 形态），
#     并显式承载 T33-01A 目标态契约：response_format 仅在开关开启且无 tools 时接入。
#     护栏判定集中在 _rf_auto_inject_permitted（变异靶点：去掉它测试必须红）。
#   - 静态层：对真实 overlay 编码路径切片做门控核验——切片内出现 response_format
#     接线时必须同时出现 SGLANG_DSV41_RF_INJECT 门（防未来 T33-01A 落地时无门接线）。
#
# 运行纪律：CPU-only、无网络、无模型权重、不启引擎/容器/GPU、<1s；只读源码。

import copy
import os

import pytest

from conftest import BASELINE_MESSAGES, LUZ_DELIVERY_ROOT

# ------------------------------------------------------------
# 护栏开关与请求样例（schema-only 投影：json_schema 取 .schema_，反例 R3 整包外壳）
# ------------------------------------------------------------

RF_INJECT_FLAG = "SGLANG_DSV41_RF_INJECT"

WEATHER_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}},
    "required": ["city"],
}

# tools 案专用 schema：与工具 parameters 刻意不同，避免工具段自带的参数 JSON
# 造成 schema 泄漏误判（泄漏检查要求该字面只能来自 RF 注入路径）。
TOOLS_CASE_SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": "string"},
        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    },
    "required": ["city", "unit"],
    "additionalProperties": False,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


class ChatBody:
    """OpenAI ChatCompletionRequest 的最小只读替身（dsv41 编码路径消费面）。"""

    def __init__(self, messages, response_format=None, tools=None, task=None):
        self.messages = messages
        self.response_format = response_format
        self.tools = tools
        self.task = task


# ------------------------------------------------------------
# 护栏判定（变异靶点；契约=T33-10 任务节目标 1）
# ------------------------------------------------------------


def _rf_inject_enabled(environ=None):
    """SGLANG_DSV41_RF_INJECT 严格解析：未设/空白/非真值一律视为未开。"""
    env = os.environ if environ is None else environ
    return env.get(RF_INJECT_FLAG, "").strip().lower() in ("1", "true", "on", "yes")


def _rf_auto_inject_permitted(environ=None, *, tools_present=False):
    """护栏判定：request 级 response_format 自动注入仅当开关开启。

    护栏②：开关未开一律拒绝（返回 False）；
    护栏③：tools 在场一律拒绝（禁双重约束：prompt schema × tool-call DSML）。
    """
    if tools_present:
        return False
    return _rf_inject_enabled(environ)


# ------------------------------------------------------------
# dsv41 服务路径镜像（现役事实 + T33-01A 门控契约）
# ------------------------------------------------------------


def _dsv41_request_to_messages(request, environ=None):
    """镜像 overlay serving_chat.py dsv41 分支（:1512-1610）的 request→messages 接线。

    现役事实（EV-05-019）：
      - messages deepcopy、content None→""；
      - 仅当首条非 system 且（有 tools）时插入空 system（dsv41 只为 tools 插宿主）；
      - request.tools → messages[0]["tools"]（dsv41_tool_payload=OpenAI 工具原形态，
        编码器 tools_from_openai_format 再取 .function）；
      - request.response_format 不接线。
    T33-01A 目标态契约（本护栏强制）：response_format 仅在
    _rf_auto_inject_permitted 为真时以 schema-only 投影接入首条 system message 的
    ``response_format`` 字段。
    """
    messages = copy.deepcopy(request.messages)
    for msg in messages:
        if msg.get("content") is None:
            msg["content"] = ""
    if messages and messages[0].get("role") != "system" and request.tools:
        messages.insert(0, {"role": "system", "content": ""})
    if request.tools:
        messages[0]["tools"] = copy.deepcopy(request.tools)
    if (
        request.response_format is not None
        and _rf_auto_inject_permitted(environ, tools_present=bool(request.tools))
    ):
        schema = request.response_format
        if schema.get("type") == "json_schema":
            schema = schema.get("json_schema", {}).get("schema_", schema)
        messages[0]["response_format"] = copy.deepcopy(schema)
    return messages


def _render_dsv41(encoding_dsv41, request, environ=None):
    """dsv41 编码路径 CPU 直跑（thinking_mode="chat"，与 01C 基准一致）。"""
    messages = _dsv41_request_to_messages(request, environ=environ)
    return encoding_dsv41.encode_messages(messages, thinking_mode="chat")


def _dsv41_encoding_path_source():
    """读 overlay serving_chat.py 编码路径切片（含 tools 宿主与 dsv41 分支，只读）。"""
    path = LUZ_DELIVERY_ROOT + "/deploy/overlay/o12c1-prod/serving_chat.py"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find("elif self.chat_encoding_spec is not None:")
    assert start != -1, "overlay serving_chat.py 必须含编码路径分支"
    dsv41 = text.find("elif is_dsv41:", start)
    assert dsv41 != -1, "编码路径必须含 dsv41 分支"
    end = text.find("\n            else:", dsv41)
    return text[start:end if end != -1 else len(text)]


def test_no_go_rf_negative_guardrails(encoding_dsv41, baseline_prompt_hash, monkeypatch):
    """G-RF：response_format 三条负向护栏（缺省逐字节不变/未开不注入/禁双重约束）。"""
    schema_literal = encoding_dsv41.to_json(WEATHER_SCHEMA)
    rf_request = ChatBody(
        copy.deepcopy(BASELINE_MESSAGES),
        response_format={"type": "json_schema", "json_schema": {"schema_": WEATHER_SCHEMA}},
    )
    tools_rf_request = ChatBody(
        copy.deepcopy(BASELINE_MESSAGES),
        response_format={
            "type": "json_schema",
            "json_schema": {"schema_": TOOLS_CASE_SCHEMA},
        },
        tools=TOOLS,
    )

    # ---- 护栏①：缺省 body 逐字节不变（含开关已开但请求未带 response_format）----
    monkeypatch.delenv(RF_INJECT_FLAG, raising=False)
    default_prompt = _render_dsv41(encoding_dsv41, ChatBody(copy.deepcopy(BASELINE_MESSAGES)))
    assert default_prompt == baseline_prompt_hash["prompt"], (
        "护栏①被破坏：缺省（无 response_format/无 tools）body 的 dsv41 渲染与 01C "
        "baseline_prompt_hash 基准不逐字节一致"
    )
    monkeypatch.setenv(RF_INJECT_FLAG, "1")
    default_prompt_flag_on = _render_dsv41(
        encoding_dsv41, ChatBody(copy.deepcopy(BASELINE_MESSAGES))
    )
    assert default_prompt_flag_on == baseline_prompt_hash["prompt"], (
        "护栏①被破坏：开关开启不得改变未带 response_format 的缺省 body 渲染"
    )
    for bad in ("## Response Format:", "## Tools"):
        assert bad not in default_prompt, f"护栏①被破坏：缺省 body 出现幻影段 {bad!r}"

    # ---- 护栏②：SGLANG_DSV41_RF_INJECT 未开时不得把 schema 注入 system/prompt ----
    for flag_value in (None, "", "0", "false", "off", "no", "  "):
        if flag_value is None:
            monkeypatch.delenv(RF_INJECT_FLAG, raising=False)
        else:
            monkeypatch.setenv(RF_INJECT_FLAG, flag_value)
        assert not _rf_inject_enabled(), f"开关解析过宽：{flag_value!r} 不得视为开启"
        prompt = _render_dsv41(encoding_dsv41, rf_request)
        assert "## Response Format:" not in prompt, (
            f"护栏②被破坏：SGLANG_DSV41_RF_INJECT 未开（值={flag_value!r}）时 "
            "dsv41 路径把 schema 注入了 prompt（## Response Format: 段）"
        )
        assert schema_literal not in prompt, (
            f"护栏②被破坏：SGLANG_DSV41_RF_INJECT 未开（值={flag_value!r}）时 "
            "schema 字面泄漏进 prompt"
        )
        assert '"json_schema"' not in prompt and '"schema_"' not in prompt, (
            "护栏②被破坏：整包 model_dump 外壳（反例 R3）泄漏进 prompt"
        )

    # 静态门控核验：真实 overlay 编码路径切片内，response_format 接线必须带开关门
    slice_text = _dsv41_encoding_path_source()
    wired = "response_format" in slice_text
    gated = RF_INJECT_FLAG in slice_text
    assert not wired or gated, (
        "护栏②被破坏：overlay dsv41 编码路径把 response_format 接入 prompt "
        f"但未受 {RF_INJECT_FLAG} 门控"
    )

    # ---- 护栏③：tools 在场时不得同时施加 prompt schema 与 tool-call 约束 ----
    for flag_value in (None, "1"):
        if flag_value is None:
            monkeypatch.delenv(RF_INJECT_FLAG, raising=False)
        else:
            monkeypatch.setenv(RF_INJECT_FLAG, flag_value)
        prompt = _render_dsv41(encoding_dsv41, tools_rf_request)
        assert "## Tools" in prompt and "get_weather" in prompt, (
            "前置失效：tools 请求必须渲染工具段（工具段正例归 01C，此处只作前置）"
        )
        assert (
            "## Response Format:" not in prompt
            and encoding_dsv41.to_json(TOOLS_CASE_SCHEMA) not in prompt
        ), (
            f"护栏③被破坏：tools 在场（开关值={flag_value!r}）时同时施加了 prompt "
            "schema 与 tool-call 约束（双重约束）"
        )
        messages_out = _dsv41_request_to_messages(
            tools_rf_request,
            environ={"SGLANG_DSV41_RF_INJECT": flag_value or ""},
        )
        assert all("response_format" not in m for m in messages_out), (
            "护栏③被破坏：tools 请求的 messages 被写入 response_format 字段"
        )
