# T33-01C —— response_format 正例矩阵（CPU prompt 渲染层）
#
# 法源：任务书 §3.0.1「response_format 正例矩阵」行（T33-01C 唯一作者）。
# 分工（不得越界，§3.0.3 硬规则 2）：
#   - 本文件只写正例：首条 system 注入、json_schema/json_object、tools 并存；
#   - 负向护栏（缺省 body 逐字节不变 / SGLANG_DSV41_RF_INJECT 未开不注入 /
#     tools 双重约束禁止）归 T33-10 G-RF（test_no_go_render_contract.py），
#     本文件不重复实现。
#
# 两层结构：
#   A) encoder 层正例（encoding_dsv41 现有能力，pass）：message 级
#      response_format 渲染进首条 system（response_format_template，
#      encoding_dsv41.py:50,270-273），tools 段与 RF 段可并存。
#   B) 接线层缺口（xfail 登记）：dsv41 服务路径未把 request.response_format
#      喂给 encoder（EV-05-019）与协议无 regex 变体（EV-05-011/P6）——
#      实现属 T33-01A（W5 条件件），0.3.3 不改产线。

import json

import pytest

from conftest import LUZ_DELIVERY_ROOT, SGLANG_SRC

# json_schema 正例：按 T33-01A 目标接线形态，message 级 response_format 携带
# schema-only（json_schema 取 .schema_ 投影；官方/01A 均不做整包 model_dump——
# 整包会把 {"type":"json_schema",...} 外壳渲染进 prompt，即 INV-05 反例 R3）。
# encoder 现状对 message 级 response_format 原样 to_json（encoding_dsv41.py:270-273），
# schema-only 投影的职责在 serving 接线层（见本文件 xfail 登记）。
WEATHER_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}},
    "required": ["city"],
}

SYSTEM_RF_MESSAGES = [
    {
        "role": "system",
        "content": "You are a helpful assistant.",
        "response_format": WEATHER_SCHEMA,
    },
    {"role": "user", "content": "Weather in Paris?"},
]

JSON_OBJECT = {"type": "json_object"}

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


def _schema_payload(prompt):
    """截取 prompt 中 '## Response Format:' 段内注入的 JSON 对象。"""
    marker = "## Response Format:"
    idx = prompt.find(marker)
    assert idx != -1, "prompt 必须含 ## Response Format: 段"
    rest = prompt[idx + len(marker):]
    start = rest.find("{")
    depth, end = 0, None
    for i, ch in enumerate(rest):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    assert end is not None
    return json.loads(rest[start:end])


# ============================================================
# A) encoder 层正例（pass）
# ============================================================


def test_json_schema_injected_into_first_system(encoding_dsv41):
    """正例：json_schema 注入首条 system（schema-only，非整包 model_dump）。"""
    prompt = encoding_dsv41.encode_messages(
        [dict(m) for m in SYSTEM_RF_MESSAGES], thinking_mode="chat"
    )
    payload = _schema_payload(prompt)
    # schema-only 注入（反例 R3：整包 model_dump 出现 {"type":"json_schema"} 外壳）
    assert payload == WEATHER_SCHEMA
    # 注入落在首条 system 内（在 <｜User｜> 之前），用户段不受影响
    assert prompt.find("## Response Format:") < prompt.find("<｜User｜>")
    assert "Weather in Paris?" in prompt


def test_json_object_injected(encoding_dsv41):
    """正例：json_object 以 {"type":"json_object"} 形态注入。"""
    messages = [
        {
            "role": "system",
            "content": "Answer in JSON.",
            "response_format": JSON_OBJECT,
        },
        {"role": "user", "content": "hi"},
    ]
    prompt = encoding_dsv41.encode_messages(messages, thinking_mode="chat")
    assert _schema_payload(prompt) == JSON_OBJECT


def test_tools_and_response_format_coexist(encoding_dsv41):
    """正例：tools 与 response_format 并存（工具段 + RF 段同时渲染，不互斥）。"""
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant.",
            "tools": TOOLS,
            "response_format": JSON_OBJECT,
        },
        {"role": "user", "content": "hi"},
    ]
    prompt = encoding_dsv41.encode_messages(messages, thinking_mode="chat")
    assert "## Tools" in prompt and "get_weather" in prompt
    assert _schema_payload(prompt) == JSON_OBJECT
    # 顺序与官方一致：tools 段在前，RF 段在后（同一首条 system 内）
    assert prompt.find("## Tools") < prompt.find("## Response Format:")


# ============================================================
# B) 接线层缺口登记（xfail strict，实现归 T33-01A）
# ============================================================


def _dsv41_branch_source():
    """读 overlay serving_chat.py 的 dsv41 encode 分支切片（只读静态检查）。"""
    path = LUZ_DELIVERY_ROOT + "/deploy/overlay/o12c1-prod/serving_chat.py"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find("elif is_dsv41:")
    assert start != -1, "overlay serving_chat.py 必须含 dsv41 分支"
    end = text.find("\n            else:", start)
    return text[start:end if end != -1 else len(text)]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "接线缺口：dsv41 分支调用 encoding_dsv41.encode_messages 时不传"
        " response_format（overlay serving_chat.py:1588-1604；EV-05-019；"
        " renderer_handles_response_format 仅 kimi_k3 为 true，:1217），"
        " 故 request 级 response_format 永远到不了 encoder 的注入模板。"
        " schema 注入 + SGLANG_DSV41_RF_INJECT 开关属 T33-01A（W5 条件件）；"
        " 开关未开时的负向护栏归 T33-10 G-RF，本文件不重复。"
    ),
)
def test_dsv41_serving_path_passes_response_format():
    """正例（目标态）：dsv41 服务分支把 request.response_format 传入 encoder。"""
    branch = _dsv41_branch_source()
    assert "response_format" in branch


@pytest.mark.xfail(
    strict=True,
    reason=(
        "协议缺口：ResponseFormat.type Literal 仅 text/json_object/json_schema"
        "（protocol.py:234-236），无 regex 变体；顶层 regex 字段已可进 xgrammar"
        "（protocol.py:926,1143，EV-05-011/P6）。regex response_format 属"
        " T33-01A P3 附件（自有渲染/开关，无客户证据不启用，不接管官方 parser）。"
    ),
)
def test_regex_response_format_variant_accepted():
    """正例（目标态）：协议接受 response_format.type=regex。"""
    path = SGLANG_SRC + "/python/sglang/srt/entrypoints/openai/protocol.py"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find("class ResponseFormat(BaseModel):")
    end = text.find("\nclass ", start + 1)
    body = text[start:end if end != -1 else len(text)]
    assert '"regex"' in body
