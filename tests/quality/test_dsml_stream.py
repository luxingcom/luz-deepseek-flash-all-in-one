# T33-01C —— 流式 DSML 解析矩阵（字面 DSML / 特殊 token 分块 / 8 档 chunk）
#
# 法源：任务书 §3.0.1「流式 DSML 矩阵」行 + T33-01C 目标 1/3；A5（§2.1）。
# 现役基线：SGLang 79cafec0 文本正则 detector（deepseekv32/v41_detector），
# 8 档 chunk 正常调用通过（EV-05-025/026）；字面 DSML 误判与吞尾为已知缺陷，
# 0.3.3 只登记（xfail strict），文本层修复归 T33-01B（0.3.4），不改产线。
#
# 范围说明：本文件只测 DSML detector（DeepSeekV41Detector 真源 + conftest 最小桩）。
# 上游 ReasoningParser（</think> 前的 reasoning 段）不在此矩阵内：喂给 detector 的
# 是 </think> 之后的内容，与生产栈（reasoning parser → tool detector）的分工一致。
#
# 官方对照（不移植）：recipe output_parser 按 token kind 区分 plain/special 段，
# 特殊 token 只按已解码 special token 匹配（EV-05-003/004）——模型用 plain token
# 拼出的字面 DSML 是内容、不是标记；这正是字面 DSML 用例的目标语义。

import json

import pytest

DSML = "｜DSML｜"

ARGUMENTS = {"query": '{"a": 1}', "limit": 2, "flags": [1, True, None]}


def _tools():
    from types import SimpleNamespace

    def tool(name):
        return SimpleNamespace(function=SimpleNamespace(name=name))

    return [tool("get_weather"), tool("lookup")]


def _rendered_call(encoding_dsv41):
    """encoder 渲染的正常 assistant 工具调用（</think> 之后的部分）。"""
    completion = encoding_dsv41.render_message(
        1,
        [
            {"role": "user", "content": "question"},
            {
                "role": "assistant",
                "reasoning_content": "reason",
                "content": "summary",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "arguments": json.dumps(ARGUMENTS),
                        },
                    }
                ],
            },
        ],
        thinking_mode="thinking",
    )
    full = "<think>" + completion  # 与上游 8 档用例同形
    return full.split("</think>", 1)[1]


def _stream(detector, text, chunk, tools):
    """按 chunk 分块流式喂给 detector，返回 (normal_text, calls)。"""
    normal, calls = "", []
    for i in range(0, len(text), chunk):
        res = detector.parse_streaming_increment(text[i : i + chunk], tools)
        normal += res.normal_text
        calls.extend(res.calls)
    res = detector.finish(tools)
    normal += res.normal_text
    calls.extend(res.calls)
    return normal, calls


def _assemble(calls):
    by_index = {}
    for call in calls:
        entry = by_index.setdefault(call.tool_index, {"name": None, "args": ""})
        if call.name:
            entry["name"] = call.name
        entry["args"] += call.parameters or ""
    return [
        (entry["name"], json.loads(entry["args"]))
        for _, entry in sorted(by_index.items())
    ]


LITERAL_DSML_PROSE = (
    "Here is the syntax: "
    f"<{DSML} calls>\n"
    f'<{DSML} invoke name="get_weather">\n'
    '{"city": "Paris"}\n'
    f"</{DSML} invoke>\n"
    f"</{DSML} calls>"
    " and that is all."
)


# ============================================================
# 正常调用：8 档 chunk 必须保持通过（T33-01C 目标 3）
# ============================================================


@pytest.mark.parametrize("chunk", [1, 2, 3, 5, 7, 11, 23, 1000])
def test_normal_call_round_trip_every_chunk(
    dsv41_detector_cls, encoding_dsv41, chunk
):
    """encoder 渲染的正常工具调用在各档 chunk 下解析回同一参数（现役基线）。"""
    detector = dsv41_detector_cls()
    normal, calls = _stream(
        detector, _rendered_call(encoding_dsv41), chunk, _tools()
    )
    assert _assemble(calls) == [("lookup", ARGUMENTS)]
    # 前导空白随 chunk 边界释放/裁剪（与上游用例同口径），prose 本体钉住
    assert normal.strip() == "summary"


def test_normal_call_one_shot(dsv41_detector_cls, encoding_dsv41):
    """一次性 detect_and_parse（非流式）同一调用。"""
    detector = dsv41_detector_cls()
    res = detector.detect_and_parse(_rendered_call(encoding_dsv41), _tools())
    assert _assemble(res.calls) == [("lookup", ARGUMENTS)]
    assert res.normal_text.strip() == "summary"


@pytest.mark.parametrize("chunk", [1, 2, 3, 5, 7, 11, 23, 1000])
def test_bare_invoke_without_calls_block(dsv41_detector_cls, chunk):
    """无外层 calls 块的 bare invoke（流式路径接受）在 8 档 chunk 下解析一致。"""
    text = (
        "summary\n\n"
        f'<{DSML} invoke name="get_weather">\n'
        '{"city": "Paris"}\n'
        f"</{DSML} invoke>"
    )
    detector = dsv41_detector_cls()
    normal, calls = _stream(detector, text, chunk, _tools())
    assert _assemble(calls) == [("get_weather", {"city": "Paris"})]
    assert normal.strip() == "summary"


def test_marker_split_across_chunk_boundary(dsv41_detector_cls):
    """特殊 token 分块正例：真实调用的 '<' 与 '｜DSML｜' 被切在不同 chunk 仍解析。"""
    text = (
        "summary\n\n"
        f"<{DSML} calls>\n"
        f'<{DSML} invoke name="get_weather">\n'
        '{"city": "Paris"}\n'
        f"</{DSML} invoke>\n"
        f"</{DSML} calls>"
    )
    cut = text.find(f"<{DSML} calls>") + 1  # 恰在 '<' 之后切开 marker
    # 逐段手动喂：prefix（以 '<' 结尾）→ marker 余段
    detector = dsv41_detector_cls()
    normal, calls = "", []
    for piece in (text[:cut], text[cut:]):
        res = detector.parse_streaming_increment(piece, _tools())
        normal += res.normal_text
        calls.extend(res.calls)
    res = detector.finish(_tools())
    normal += res.normal_text
    calls.extend(res.calls)
    assert _assemble(calls) == [("get_weather", {"city": "Paris"})]
    assert normal.strip() == "summary"


# ============================================================
# 字面 DSML：已知缺陷登记（修复归 T33-01B / 0.3.4，0.3.3 不改产线）
# ============================================================


@pytest.mark.parametrize("chunk", [1, 2, 3, 5, 7, 11, 23, 1000])
@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷：字面 DSML（prose 里展示语法）被现役文本正则 detector 误判为"
        " 工具调用——各档 chunk 均复现（INV-05 §7 P4 现测 / EV-05-026；A5）。"
        " 官方按 token kind 只在已解码 special token 上匹配标记（EV-05-003/004）。"
        " 0.3.3 只登记现状，文本层修复归 T33-01B（0.3.4）。"
    ),
)
def test_literal_dsml_prose_not_parsed_as_call(dsv41_detector_cls, chunk):
    detector = dsv41_detector_cls()
    normal, calls = _stream(detector, LITERAL_DSML_PROSE, chunk, _tools())
    assert calls == [], "字面 DSML 是内容，不是调用"
    assert LITERAL_DSML_PROSE in normal


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷：chunk 1000 一次性到达时，首个完整 invoke 使 current_tool_id 置位，"
        " finish() 直接丢弃残余 buffer，尾部 prose『 and that is all.』被吞"
        "（deepseekv32_detector.py:374-383；INV-05 §7 P4 / EV-05-026）。"
        " marker-only finish 应释放整段；修复归 T33-01B（0.3.4）。"
    ),
)
def test_literal_dsml_tail_preserved_at_chunk_1000(dsv41_detector_cls):
    detector = dsv41_detector_cls()
    normal, calls = _stream(detector, LITERAL_DSML_PROSE, 1000, _tools())
    assert " and that is all." in normal, "DSML 之后的尾部 prose 不得被吞"
