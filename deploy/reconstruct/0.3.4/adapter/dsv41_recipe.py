"""Recipe-backed prompt encoding for DeepSeek-V4.1.

The serving renderer produces the official prompt text, but encoding that text
with ``tokenizer.encode`` applies the added vocabulary to plain text as well:
a literal ``<｜User｜>`` inside a user message becomes the role token and can
forge a turn boundary. ``DeepseekV41Encoding.encode`` encodes only the
renderer's structural spans with the added vocabulary and keeps plain text
literal. Use it only when its rendered prompt is byte-identical to the serving
prompt; any other shape returns ``None`` so the caller stays on its existing
path.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_RECIPE_PATH = os.environ.get("DSV41_RECIPE_PATH", "/opt/dsv41/adapter/recipe_lib")

_lock = threading.Lock()
_recipe = None
_encoder = None
_failed = False

# Recipe 0.2.0 accepts low/high/max. Production renders xhigh as 75, the same
# budget as high, so normalize it; the prompt-equality gate still decides.
_RECIPE_EFFORTS = {
    "low": "low",
    "high": "high",
    "xhigh": "high",
    "max": "max",
}


def _load(tokenizer: Any):
    global _recipe, _encoder, _failed

    if _encoder is not None:
        return _recipe, _encoder
    with _lock:
        if _encoder is not None:
            return _recipe, _encoder
        if _failed:
            return None
        try:
            import sys

            if _RECIPE_PATH not in sys.path:
                sys.path.insert(0, _RECIPE_PATH)
            import deepseek_recipe as dr

            payload = tokenizer.backend_tokenizer.to_str()
            _encoder = dr.DeepseekV41Encoding().with_tokenizer(
                dr.Tokenizer.from_str(payload)
            )
            _recipe = dr
            return _recipe, _encoder
        except Exception:
            _failed = True
            logger.warning(
                "deepseek-recipe prompt encoding unavailable; "
                "falling back to whole-string tokenization",
                exc_info=True,
            )
            return None


def _tool_definitions(dr: Any, tools: List[Dict[str, Any]]):
    definitions = []
    for tool in tools:
        if not isinstance(tool, dict):
            return None
        function = tool.get("function", tool)
        if not isinstance(function, dict):
            return None
        # Recipe's ToolDefinition has no namespace field; the serving encoder
        # renders namespaced schemas itself, so leave those on the old path.
        if "namespace" in tool or "namespace" in function:
            return None
        name = function.get("name")
        if not isinstance(name, str) or not name:
            return None
        definitions.append(
            dr.ToolDefinition(
                name=name,
                description=function.get("description"),
                parameters=function.get("parameters"),
                strict=function.get("strict"),
            )
        )
    return definitions


def _build_conversation(
    dr: Any,
    messages: List[Dict[str, Any]],
    thinking: bool,
    reasoning_effort: Any,
):
    tools = None
    built = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        content = message.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            return None

        if role == "system":
            message_tools = message.get("tools")
            if message_tools:
                # A mid-conversation schema update renders differently from a
                # request-level Tools section; only the first system message
                # hosts the serving request's tools.
                if index != 0:
                    return None
                tools = _tool_definitions(dr, message_tools)
                if tools is None:
                    return None
            built.append(dr.SystemMessage(content))
        elif role == "user":
            if message.get("task") is not None:
                return None
            built.append(dr.UserMessage(content))
        elif role == "latest_reminder":
            built.append(dr.LatestReminderMessage(content))
        elif role == "assistant":
            if message.get("mask") or message.get("prefix"):
                return None
            calls = []
            for tool_call in message.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    return None
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    return None
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    return None
                calls.append(
                    dr.ToolCall(
                        tool_call.get("id") or "",
                        function.get("name") or "",
                        arguments,
                    )
                )
            built.append(
                dr.AssistantMessage(
                    content,
                    message.get("reasoning_content"),
                    calls or None,
                )
            )
        elif role == "tool":
            built.append(dr.ToolMessage(content, message.get("tool_call_id")))
        else:
            return None

    if not built:
        return None
    return dr.Conversation(
        built,
        thinking_mode=thinking,
        tools=tools,
        reasoning_effort=reasoning_effort,
    )


def encode_prompt_ids(
    messages: List[Dict[str, Any]],
    prompt: str,
    thinking_mode: Any,
    reasoning_effort: Any,
    tokenizer: Any,
) -> Optional[List[int]]:
    """Return recipe prompt ids, or None when the recipe path does not apply."""
    loaded = _load(tokenizer)
    if loaded is None:
        return None
    dr, encoder = loaded

    # Recipe's Conversation accepts the named efforts only; a numeric 1-100
    # budget stays on the serving path, whose encoder handles it directly.
    if reasoning_effort is not None:
        if not isinstance(reasoning_effort, str):
            return None
        reasoning_effort = _RECIPE_EFFORTS.get(reasoning_effort)
        if reasoning_effort is None:
            return None

    thinking = str(getattr(thinking_mode, "value", thinking_mode)) == "thinking"
    try:
        conversation = _build_conversation(
            dr, messages, thinking, reasoning_effort
        )
        if conversation is None:
            return None

        rendered = encoder.render_conversation(conversation)
        if rendered.prompt != prompt:
            return None
        ids = encoder.encode(conversation)
    except Exception:
        logger.warning(
            "deepseek-recipe prompt encoding failed; falling back",
            exc_info=True,
        )
        return None
    return ids or None
