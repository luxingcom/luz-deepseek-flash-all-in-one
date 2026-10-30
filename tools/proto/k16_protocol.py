# T33-01A K16 protocol canonical module -- max_tokens 解析 + response_format 条件注入
# (0.3.3 / 2026-10-23 / 0 靴纯开发：CPU-only，纯 stdlib，不 import sglang/torch)
#
# 法源（唯一）：docs/plan/033-TASKBOOK-V2-20261023.md §T33-01A（:901-950）+ §11 复核表 #4/#5
# （K16 定稿语义）+ §2.1 A1/A2 + §2.2 P6（表 2.4-B partial-now 行）。
# 语义基线：tests/quality/test_max_tokens_matrix.py::resolve_max_tokens_k16
# （T33-01C W0 executable spec；本模块实现同一语义，tests/unit 交叉对拍强制）。
#
# 开关（任务书 §T33-01A 依赖行/回退行指定的两键 + P6 休眠子门，全部默认关）：
#   SGLANG_DSV41_EFFORT_DEFAULT  -- max_tokens 策略面总门（缺省 effort 注入 + 显式值
#                                   收敛/pin/日志 + >131072 的 400 校验）。关=完全惰性，
#                                   现役链（None→1<<30→SGLANG_MAX_NEW_TOKENS_LIMIT→ctx）
#                                   原样承载，行为逐字节不变。
#   SGLANG_DSV41_RF_INJECT       -- response_format prompt 注入门（json_schema 注入首条
#                                   system；json_object 走 grammar 不注入；tools 在场不注入
#                                   ——与 T33-10 G-RF 负向护栏同律）。关=messages 原样返回。
#   SGLANG_DSV41_RF_REGEX        -- P6 regex 休眠子门（§2.2 P6"无客户证据不启用"；
#                                   且须 RF_INJECT 同开）。默认关；无客户流量证据不得开启。
#
# 交付形态（SCHED_STATS_V1 先例）：本文件为 canonical 正典位；生产接线以补丁呈裁
# （tools/patches/t33-01a.overlay-serving-chat.patch，未应用）——补丁内嵌下方
# sentinel 标记段（逐字一致，tests/unit/test_k16_protocol.py::test_patch_canonical_identity
# 强制漂移即红）。运行期回退=不设上述三键；代码回退=git apply -R 补丁。
#
# --selfcheck：无 pytest 环境下的 5-case + 惰性自检（退出码 0=PASS）。

import sys

# ============================================================
# ---- t33-01a canonical: begin
# （本标记段会被逐字内嵌进 overlay serving_chat.py 补丁；改动须同步补丁，
#   tests/unit/test_k16_protocol.py::test_patch_canonical_identity 强制一致）
# ============================================================

_T33_01A_PROTOCOL_LIMIT = 131072  # K16：显式 >131072 → 400
_T33_01A_DEFAULT_NON_MAX = 65536  # K16：缺省非 Max 65536（不照搬官方 8192/393216）
_T33_01A_DEFAULT_MAX = 131072  # K16：缺省 Max 131072
_T33_01A_PIN_512K = 65536  # K16：512k 档 pin 65536（C8×512k 池位红线）
_T33_01A_PROMPT_512K_TOKENS = 524288  # 512k 档判定阈（token 计）
_T33_01A_EFFORT_FLAG = "SGLANG_DSV41_EFFORT_DEFAULT"
_T33_01A_RF_INJECT_FLAG = "SGLANG_DSV41_RF_INJECT"
_T33_01A_RF_REGEX_FLAG = "SGLANG_DSV41_RF_REGEX"
_T33_01A_TRUTHY = ("1", "true", "on", "yes")  # 与 G-RF _rf_inject_enabled 同集
_T33_01A_REGEX_MAX_LEN = 2048  # P6 regex pattern 长度上限（自有渲染防御位）


class T33_01AMaxTokensProtocolError(ValueError):
    """K16：显式 max_tokens|max_completion_tokens > 131072 的 400 语义。"""


def _t33_01a_environ(env=None):
    if env is None:
        import os

        env = os.environ
    return env


def _t33_01a_flag(env=None, name=""):
    """严格真值解析：未设/空白/非真值一律视为关（G-RF 护栏②同律）。"""
    return str(_t33_01a_environ(env).get(name, "")).strip().lower() in _T33_01A_TRUTHY


def _t33_01a_max_tokens_policy_enabled(env=None):
    return _t33_01a_flag(env, _T33_01A_EFFORT_FLAG)


def _t33_01a_rf_inject_enabled(env=None):
    return _t33_01a_flag(env, _T33_01A_RF_INJECT_FLAG)


def _t33_01a_get(obj, name, default=None):
    """dict / pydantic 对象统一取字段（CPU 测试用 dict，接线层传 request 对象）。"""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _t33_01a_resolve_max_tokens(
    requested=None,
    effort="high",
    prompt_len=8192,
    ctx_len=600000,
    thinking_mode=True,
):
    """K16 解析器（任务书 §T33-01A 目标 1/2/4；语义=01C resolve_max_tokens_k16）。

    - requested=None：缺省按 effort 注入——Max 131072、其余 65536；Max 档以
      thinking_mode=True 为前提（INV-05 §6 排期条款：§4.6 thinking 键验证未闭合时
      Max 缺省只对显式 thinking=true 生效，不阻塞其余项），关则回落 65536。
    - 显式 65537-131072：对 Max/非 Max 同权允许（K16；不采纳 AUDIT-05 #5），
      不静默削顶。
    - 显式 >131072：raise T33_01AMaxTokensProtocolError（接线层 400）。
    - 512k 档（prompt_len>=524288）：pin 65536，日志写 pinned=512k。
    - 其余按 ctx_len − prompt_len − 1 收敛（与官方 resolve_max_tokens 同形）。
    返回 {"effective": int, "log": {input, original, clamped[, pinned]}}。
    pool 侧收敛由现役 scheduler 链承载（本模块不重复实现池账）。
    """
    log = {"input": prompt_len, "original": requested}
    if requested is None:
        base = (
            _T33_01A_DEFAULT_MAX
            if (effort == "max" and thinking_mode)
            else _T33_01A_DEFAULT_NON_MAX
        )
    else:
        if requested > _T33_01A_PROTOCOL_LIMIT:
            raise T33_01AMaxTokensProtocolError(
                f"max_tokens/max_completion_tokens is too large: {requested}. "
                f"This API supports at most {_T33_01A_PROTOCOL_LIMIT} "
                "completion tokens."
            )
        base = requested
    if prompt_len >= _T33_01A_PROMPT_512K_TOKENS:
        effective = min(base, _T33_01A_PIN_512K)
        log["pinned"] = "512k"
    else:
        effective = max(1, min(base, ctx_len - prompt_len - 1))
    log["clamped"] = effective
    return {"effective": effective, "log": log}


def _t33_01a_format_max_tokens_log(log):
    """K16 日志行：input/original/clamped（+pinned=512k）。"""
    parts = [
        "max_tokens_k16",
        f"input={log.get('input')}",
        f"original={log.get('original')}",
        f"clamped={log.get('clamped')}",
    ]
    if log.get("pinned") is not None:
        parts.append(f"pinned={log['pinned']}")
    return " ".join(parts)


def _t33_01a_requested_tokens(request):
    """(值, 字段名)：max_completion_tokens 优先（protocol.py:1132 同序）。"""
    mct = _t33_01a_get(request, "max_completion_tokens")
    mt = _t33_01a_get(request, "max_tokens")
    if mct is not None:
        return mct, "max_completion_tokens"
    if mt is not None:
        return mt, "max_tokens"
    return None, "max_tokens"


def _t33_01a_validate_requested_limit(requested, env=None):
    """K16 400 校验（仅策略开关开时生效；关=现役无此校验，行为不变）。"""
    if not _t33_01a_max_tokens_policy_enabled(env):
        return None
    if requested is not None and requested > _T33_01A_PROTOCOL_LIMIT:
        return (
            f"max_tokens/max_completion_tokens is too large: {requested}. "
            f"This API supports at most {_T33_01A_PROTOCOL_LIMIT} "
            "completion tokens."
        )
    return None


def _t33_01a_validate_json_schema(schema):
    """schema 校验后才注入（任务书 A1）：dict + JSON 可序列化。"""
    if not isinstance(schema, dict):
        return "json_schema response format requires a JSON object schema."
    try:
        import json

        json.dumps(schema)
    except (TypeError, ValueError):
        return "json_schema response format schema is not JSON-serializable."
    return None


def _t33_01a_validate_regex_pattern(pattern):
    """P6 自有渲染防御位：非空字符串 + 长度上限 + 可编译。"""
    if not isinstance(pattern, str) or not pattern:
        return "regex response_format requires a non-empty pattern string."
    if len(pattern) > _T33_01A_REGEX_MAX_LEN:
        return (
            "regex response_format pattern exceeds "
            f"{_T33_01A_REGEX_MAX_LEN} characters."
        )
    import re

    try:
        re.compile(pattern)
    except re.error as exc:
        return f"regex response_format pattern is invalid: {exc}"
    return None


def _t33_01a_project_response_format(response_format, env=None, tools_present=False):
    """request 级 response_format → (schema-only payload | None, 错误串 | None)。

    - 开关未开 / tools 在场（工具约束优先，禁双重约束）/ json_object（走 grammar，
      prompt 不注入）/ text：payload=None，messages 保持逐字节不变。
    - json_schema：取 .json_schema.schema_ 投影（schema-only，反例 R3 禁整包外壳）。
    - regex（P6 休眠位）：须 RF_REGEX+RF_INJECT 双门同开才渲染（无客户证据不启用）。
    """
    if tools_present:
        return None, None
    if not _t33_01a_rf_inject_enabled(env):
        return None, None
    rf_type = _t33_01a_get(response_format, "type")
    if rf_type == "json_schema":
        holder = _t33_01a_get(response_format, "json_schema")
        schema = _t33_01a_get(holder, "schema_") if holder is not None else None
        if schema is None:
            return None, (
                "schema_ is required for json_schema response format request."
            )
        err = _t33_01a_validate_json_schema(schema)
        if err is not None:
            return None, err
        return schema, None
    if rf_type in ("json_object", "text"):
        return None, None
    if rf_type == "regex":
        if not _t33_01a_flag(env, _T33_01A_RF_REGEX_FLAG):
            return None, None
        pattern = _t33_01a_get(response_format, "regex")
        if pattern is None:
            pattern = _t33_01a_get(response_format, "pattern")
        err = _t33_01a_validate_regex_pattern(pattern)
        if err is not None:
            return None, err
        return {"type": "regex", "pattern": pattern}, None
    return None, (
        f"Unsupported response_format type: {rf_type!r}; expected one of "
        "text, json_object, json_schema."
    )


def _t33_01a_attach_response_format(messages, payload):
    """payload=None 原样返回（同一 list 对象，字节不变）；否则深拷贝后写入首条
    system 的 response_format 字段（无 system 时插入空 system 宿主，同 tools 宿主
    机制）。"""
    if payload is None:
        return messages
    import copy

    msgs = copy.deepcopy(messages)
    if not msgs or _t33_01a_get(msgs[0], "role") != "system":
        msgs.insert(0, {"role": "system", "content": ""})
    if isinstance(msgs[0], dict):
        msgs[0]["response_format"] = copy.deepcopy(payload)
    return msgs


def _t33_01a_apply_response_format(messages, request, env=None):
    """接线层入口（dsv41 分支）：开关/工具/type 判定后 schema-only 注入。
    校验错误在 _validate_request 阶段已 400，此处防御性跳过。"""
    response_format = _t33_01a_get(request, "response_format")
    if response_format is None:
        return messages
    payload, _err = _t33_01a_project_response_format(
        response_format,
        env=env,
        tools_present=bool(_t33_01a_get(request, "tools")),
    )
    return _t33_01a_attach_response_format(messages, payload)


def _t33_01a_validate_chat_request(request, env=None):
    """_validate_request 钩子：>131072 的 400 + RF 投影校验（各自受门控，
    两键全关时返回 None，现役校验行为不变）。"""
    requested, _field = _t33_01a_requested_tokens(request)
    err = _t33_01a_validate_requested_limit(requested, env=env)
    if err is not None:
        return err
    response_format = _t33_01a_get(request, "response_format")
    if response_format is not None and _t33_01a_rf_inject_enabled(env):
        _payload, err = _t33_01a_project_response_format(
            response_format,
            env=env,
            tools_present=bool(_t33_01a_get(request, "tools")),
        )
        if err is not None:
            return err
    return None


def _t33_01a_resolve_for_request(
    request, prompt_len, ctx_len, thinking_mode=True, effort="high", env=None
):
    """门控入口：策略开关关 → None（接线层不动 request，现役链承载）；
    开 → 对缺省与显式值统一按 K16 解析（显式 >131072 已在 _validate_request
    阶段 400，此处 raise 为防御位）。"""
    if not _t33_01a_max_tokens_policy_enabled(env):
        return None
    requested, _field = _t33_01a_requested_tokens(request)
    return _t33_01a_resolve_max_tokens(
        requested,
        effort=effort,
        prompt_len=prompt_len,
        ctx_len=ctx_len,
        thinking_mode=thinking_mode,
    )


def _t33_01a_apply_max_tokens(
    request, prompt_len, context_len, thinking_mode=True, effort="high", env=None
):
    """接线层入口（dsv41 分支 prompt_ids 生成后）：写回有效 max_tokens（写客户端
    实际使用的字段；缺省注入写 max_tokens，protocol.py:1132 `mct or mt` 同序）并
    打 input/original/clamped[/pinned] 日志。开关关 → None，零改动零日志。"""
    resolution = _t33_01a_resolve_for_request(
        request,
        prompt_len=prompt_len,
        ctx_len=context_len,
        thinking_mode=thinking_mode,
        effort=effort,
        env=env,
    )
    if resolution is None:
        return None
    _value, field = _t33_01a_requested_tokens(request)
    setattr(request, field, resolution["effective"])
    import logging

    logging.getLogger(__name__).info(
        "%s", _t33_01a_format_max_tokens_log(resolution["log"])
    )
    return resolution

# ============================================================
# ---- t33-01a canonical: end
# ============================================================


def _selfcheck():
    """CPU 自检：K16 5 case + 三开关惰性 + RF 投影（无 pytest 环境可用）。"""
    from types import SimpleNamespace

    checks = []

    def ok(name, cond):
        checks.append((name, bool(cond)))
        if not cond:
            print(f"FAIL {name}")
        else:
            print(f"PASS {name}")

    env_off = {}
    r = _t33_01a_resolve_max_tokens(None, effort="high")
    ok("case1_non_max_default_65536", r["effective"] == 65536)
    r = _t33_01a_resolve_max_tokens(None, effort="max")
    ok("case1_max_default_131072", r["effective"] == 131072)
    r = _t33_01a_resolve_max_tokens(None, effort="max", prompt_len=500000)
    ok("case1_max_ctx_clamped_99999", r["effective"] == 99999)
    r = _t33_01a_resolve_max_tokens(65537)
    ok(
        "case2_explicit_65537_allowed",
        r["effective"] == 65537
        and r["log"]["input"] == 8192
        and r["log"]["original"] == 65537
        and r["log"]["clamped"] == 65537,
    )
    r = _t33_01a_resolve_max_tokens(65537, prompt_len=524287)
    ok("case2_boundary_not_clamped", r["effective"] == 65537)
    r = _t33_01a_resolve_max_tokens(131072)
    ok("case3_explicit_131072_allowed", r["effective"] == 131072)
    r = _t33_01a_resolve_max_tokens(131072, prompt_len=500000)
    ok("case3_ctx_clamped_99999", r["effective"] == 99999)
    try:
        _t33_01a_resolve_max_tokens(131073)
        ok("case4_131073_rejected", False)
    except T33_01AMaxTokensProtocolError:
        ok("case4_131073_rejected", True)
    r = _t33_01a_resolve_max_tokens(65537, prompt_len=524288)
    ok(
        "case5_512k_pin_65536",
        r["effective"] == 65536 and r["log"]["pinned"] == "512k",
    )
    r = _t33_01a_resolve_max_tokens(None, effort="max", prompt_len=524288)
    ok("case5_512k_max_default_pinned", r["effective"] == 65536)
    r = _t33_01a_resolve_max_tokens(None, effort="max", thinking_mode=False)
    ok("thinking_gate_max_falls_back", r["effective"] == 65536)
    ok(
        "log_line_format",
        "input=8192" in _t33_01a_format_max_tokens_log({"input": 8192})
        and "pinned=512k"
        in _t33_01a_format_max_tokens_log(
            {"input": 524288, "original": 65537, "clamped": 65536, "pinned": "512k"}
        ),
    )
    req = SimpleNamespace(
        max_completion_tokens=None, max_tokens=131073, response_format=None, tools=None
    )
    ok(
        "switch_off_no_400",
        _t33_01a_validate_chat_request(req, env=env_off) is None,
    )
    ok(
        "switch_on_400",
        _t33_01a_validate_chat_request(
            req, env={_T33_01A_EFFORT_FLAG: "1"}
        )
        is not None,
    )
    ok(
        "switch_off_inert_resolve",
        _t33_01a_resolve_for_request(
            SimpleNamespace(max_completion_tokens=None, max_tokens=None),
            prompt_len=8192,
            ctx_len=600000,
            env=env_off,
        )
        is None,
    )
    schema = {"type": "object", "properties": {"city": {"type": "string"}}}
    rf = {"type": "json_schema", "json_schema": {"schema_": schema}}
    payload, err = _t33_01a_project_response_format(rf, env=env_off)
    ok("rf_switch_off_inert", payload is None and err is None)
    payload, err = _t33_01a_project_response_format(
        rf, env={_T33_01A_RF_INJECT_FLAG: "1"}, tools_present=True
    )
    ok("rf_tools_no_double_constraint", payload is None and err is None)
    payload, err = _t33_01a_project_response_format(
        rf, env={_T33_01A_RF_INJECT_FLAG: "1"}
    )
    ok("rf_json_schema_schema_only", payload == schema and err is None)
    payload, err = _t33_01a_project_response_format(
        {"type": "json_object"}, env={_T33_01A_RF_INJECT_FLAG: "1"}
    )
    ok("rf_json_object_grammar_path", payload is None and err is None)
    payload, err = _t33_01a_project_response_format(
        {"type": "regex", "regex": "^\\d+$"}, env={_T33_01A_RF_INJECT_FLAG: "1"}
    )
    ok("rf_regex_dormant_without_subgate", payload is None and err is None)
    payload, err = _t33_01a_project_response_format(
        {"type": "regex", "regex": "^\\d+$"},
        env={_T33_01A_RF_INJECT_FLAG: "1", _T33_01A_RF_REGEX_FLAG: "1"},
    )
    ok(
        "rf_regex_enabled_under_double_gate",
        payload == {"type": "regex", "pattern": "^\\d+$"} and err is None,
    )
    msgs = [{"role": "user", "content": "hi"}]
    ok("rf_attach_none_identity", _t33_01a_attach_response_format(msgs, None) is msgs)
    out = _t33_01a_attach_response_format(msgs, schema)
    ok(
        "rf_attach_host_and_payload",
        len(out) == 2
        and out[0]["role"] == "system"
        and out[0]["response_format"] == schema
        and out[1] == msgs[0]
        and msgs == [{"role": "user", "content": "hi"}],  # 原消息不被原地改动
    )
    failed = [name for name, cond in checks if not cond]
    print(f"selfcheck: {len(checks) - len(failed)}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
