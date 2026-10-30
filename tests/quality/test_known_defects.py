# T33-01C —— defer_loading / prefix 已知缺陷登记（xfail strict，逐条带 reason）
#
# 法源：任务书 §3.0.1「defer_loading / prefix 已知缺陷」行 + T33-01B（P3 挂起，
# 0.3.4）+ A3/A4（§2.1）。0.3.3 只登记现状（xfail strict、不静默跳过、不删 case），
# 不写产线代码；全部修复归 T33-01B，进入条件=真实客户流量证据 + 协议兼容评审。
#
# 每条缺陷两层证据：encoder/协议行为（动态）与 serving 接线（静态只读源码检查）。
# 附一条 pass：wo_eos 真续写原语在 encoder 层已存在（证明「底座有、接线无」）。

import pytest

from conftest import LUZ_DELIVERY_ROOT, SGLANG_SRC

DEFER_TOOL = {
    "type": "function",
    "function": {
        "name": "heavy_tool",
        "description": "Deferred until needed",
        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        "defer_loading": True,
    },
}


# ============================================================
# A3：defer_loading 工具不得渲染进 prompt schema（官方 render_tool_prompt 过滤）
# ============================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（A3）：render_tools 把 function 字段整包 to_json 序列化，"
        " defer_loading=true 的工具原样进入 prompt schema（encoding_dsv41.render_tools"
        " 无过滤，encoding_dsv41.py:159-170；官方 render_tool_prompt 过滤 defer_loading，"
        " EV-05-002）。工具可见性泄漏 + 模型可调用未加载工具；过滤归"
        " T33-01B（0.3.4，prompt/grammar/detector 三处同源过滤）。"
    ),
)
def test_defer_loading_tool_filtered_from_prompt_schema(encoding_dsv41):
    rendered = encoding_dsv41.render_tools(
        [DEFER_TOOL["function"]]
    )
    assert "defer_loading" not in rendered, "defer_loading 不得渲染进 prompt schema"
    assert "heavy_tool" not in rendered, "deferred 工具不得进入工具清单"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（A3 接线面）：协议层把 defer_loading 传播进 function"
        "（protocol.py Function.defer_loading:776 + Tool._propagate_defer_loading），"
        " serving_chat 对 dsv41 无任何 defer_loading 过滤（overlay 全文 0 处）；"
        " deferred 工具同时进入 structural tag。过滤归 T33-01B（0.3.4）。"
    ),
)
def test_defer_loading_filtered_in_serving_path():
    """目标态：dsv41 serving 路径存在 defer_loading 过滤（静态只读检查）。"""
    for path in (
        LUZ_DELIVERY_ROOT + "/deploy/overlay/o12c1-prod/serving_chat.py",
        SGLANG_SRC + "/python/sglang/srt/entrypoints/openai/encoding_dsv41.py",
    ):
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        assert "defer_loading" in text and "filter" in text.lower(), (
            "defer_loading 过滤缺失: %s" % path
        )


# ============================================================
# A4：prefix:true 真续写（无 EOS、无生成头；thinking 下前缀不当 reasoning）
# ============================================================


def test_wo_eos_prefix_primitive_exists_at_encoder(encoding_dsv41):
    """pass：encoder 底座已支持 wo_eos（不追加 EOS 的 assistant 渲染）。"""
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "visible prefix", "wo_eos": True},
    ]
    with_eos = encoding_dsv41.encode_messages(
        [dict(m) for m in messages[:-1]]
        + [{k: v for k, v in messages[-1].items() if k != "wo_eos"}],
        thinking_mode="thinking",
    )
    without_eos = encoding_dsv41.encode_messages(messages, thinking_mode="thinking")
    assert with_eos.endswith(encoding_dsv41.eos_token)
    assert not without_eos.endswith(encoding_dsv41.eos_token)
    assert without_eos.endswith("visible prefix")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（A4）：continue_final_message 仍是『删末条 assistant 消息 + "
        "tokenizer.encode(prefix) 拼 token』（overlay serving_chat.py:410-464 与"
        " :1621-1625 调用点），不设 wo_eos——thinking 下可见前缀落在 <think> 内被当"
        " reasoning，属假续写（INV-05 §7 R6 / EV-05-021）。真续写（wo_eos=True 保留"
        " assistant 消息、reasoning-only prefix 先 400）归 T33-01B（0.3.4）。"
    ),
)
def test_continue_final_message_uses_wo_eos_true_continuation():
    """目标态：continue_final_message 走 wo_eos 真续写（静态只读检查）。"""
    path = LUZ_DELIVERY_ROOT + "/deploy/overlay/o12c1-prod/serving_chat.py"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find("def _handle_last_assistant_message")
    end = text.find("def _append_assistant_prefix_to_prompt_ids")
    helper = text[start:end]
    assert "wo_eos" in helper, (
        "前缀处理必须保留 assistant 消息并设 wo_eos，而不是删消息拼 token"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷（A4 协议面）：ChatCompletionMessage 无 prefix:bool 字段"
        "（官方 schema.rs:45-47 有；INV-05 差距矩阵），客户端无法表达真续写；"
        " prefix:true 的 400『明确不支持』与字段引入均归 T33-01B（0.3.4）。"
    ),
)
def test_protocol_message_has_prefix_field():
    """目标态：协议消息体接受 prefix 字段（静态只读检查）。"""
    path = SGLANG_SRC + "/python/sglang/srt/entrypoints/openai/protocol.py"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.find("class ChatCompletionMessageGenericParam")
    end = text.find("\nclass ", start + 1)
    body = text[start : end if end != -1 else len(text)]
    assert "prefix" in body
