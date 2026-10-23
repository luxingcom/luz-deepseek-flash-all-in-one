# T33-01A —— K16 protocol canonical module CPU 单测（0 靴，mock 数据，纯 stdlib）
#
# 法源：docs/plan/033-TASKBOOK-V2-20261023.md §T33-01A（:901-950，验收门"CPU 协议
# 矩阵：5 case 必须齐全"+"CPU prompt hash 回归：默认 body 逐字节不变；只在开关开时变"）；
# §3.0 测试所有权（01C 是 tests/quality 矩阵唯一作者——本文件**不落入 tests/quality**，
# 按 SCHED_STATS_V1 先例落 tests/unit，避免污染 W0 门计数 31 passed + 21 xfailed）。
# 被测件：tools/proto/k16_protocol.py（canonical）与
#        tools/patches/t33-01a.overlay-serving-chat.patch（呈裁接线件，只做静态一致性）。
# 不 import sglang/torch/GPU；单次 <60s。运行：
#   PYTHONDONTWRITEBYTECODE=1 /tmp/w0venv/bin/python -m pytest -q tests/unit/test_k16_protocol.py \
#       -o cache_dir=/tmp/w0cache
#
# 分层：
#   A) K16 5 case 对 canonical 实现复跑（01A 验收门；01C A 层 executable spec 为语义基线）；
#   B) 与 01C resolve_max_tokens_k16 交叉对拍（网格逐点等价——"同一 5 case"的等价性证明）；
#   C) 三开关门控/惰性（默认关=现役语义不变、逐字节不变）；
#   D) response_format 投影（schema-only/grammar 路径/双重约束禁/P6 regex 休眠位）；
#   E) 接线形态（写回字段优先级、日志行、与 encoding_dsv41 端到端 prompt 对拍）；
#   F) 呈裁补丁静态一致性（canonical sentinel 段逐字一致 + 门控核验）。

import copy
import importlib.util
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(REPO, "tools", "proto", "k16_protocol.py")
PATCH_PATH = os.path.join(REPO, "tools", "patches", "t33-01a.overlay-serving-chat.patch")
SGLANG_ENCODER = "/home/liuxiaoya/sglang-main-src/python/sglang/srt/entrypoints/openai/encoding_dsv41.py"
QUALITY_DIR = os.path.join(REPO, "tests", "quality")

_spec = importlib.util.spec_from_file_location("k16_protocol", MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

CTX_LEN = 600_000
PROMPT_512K = 524_288
SHORT_PROMPT = 8_192

WEATHER_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}},
    "required": ["city"],
}


def env_on(*pairs):
    env = {}
    for name, value in pairs:
        env[name] = value
    return env


# ============================================================
# A) K16 5 case（任务书 T33-01A 验收门 :928-933，对 canonical 实现复跑）
# ============================================================


def test_case1_default_none_by_effort():
    """case 1：None → 非 Max 65536；Max 131072（均按 ctx_len − prompt_len − 1 收敛）。"""
    assert m._t33_01a_resolve_max_tokens(None, effort="high")["effective"] == 65_536
    assert m._t33_01a_resolve_max_tokens(None, effort="max")["effective"] == 131_072
    tight = m._t33_01a_resolve_max_tokens(None, effort="max", prompt_len=500_000)
    assert tight["effective"] == CTX_LEN - 500_000 - 1 == 99_999


def test_case2_explicit_65537_allowed_and_clamped():
    """case 2：65537 → allowed，按 ctx/pool 收敛，日志含 input/original/clamped。"""
    r = m._t33_01a_resolve_max_tokens(65_537)
    assert r["effective"] == 65_537  # 短 prompt 下原值有效（不静默削顶）
    assert r["log"] == {
        "input": SHORT_PROMPT,
        "original": 65_537,
        "clamped": 65_537,
    }
    boundary = m._t33_01a_resolve_max_tokens(65_537, prompt_len=PROMPT_512K - 1)
    assert boundary["effective"] == 65_537 and boundary["log"]["clamped"] == 65_537


def test_case3_explicit_131072_allowed_and_clamped():
    """case 3：131072 → allowed，按 ctx/pool 收敛，日志含 input/original/clamped。"""
    r = m._t33_01a_resolve_max_tokens(131_072)
    assert r["effective"] == 131_072
    assert r["log"]["original"] == 131_072 and r["log"]["clamped"] == 131_072
    r2 = m._t33_01a_resolve_max_tokens(131_072, prompt_len=CTX_LEN - 100_000)
    assert r2["effective"] == 99_999 and r2["log"]["clamped"] == 99_999


def test_case4_explicit_131073_rejected_400():
    """case 4：131073 → 400（K16：显式 >131072 拒绝；Max/非 Max 同权）。"""
    with pytest.raises(m.T33_01AMaxTokensProtocolError) as excinfo:
        m._t33_01a_resolve_max_tokens(131_073)
    assert "131073" in str(excinfo.value) and "131072" in str(excinfo.value)


def test_case5_512k_prompt_pins_65536():
    """case 5：512k prompt + 65537 → 65536，日志含 pinned=512k。"""
    r = m._t33_01a_resolve_max_tokens(65_537, prompt_len=PROMPT_512K)
    assert r["effective"] == 65_536 and r["log"]["pinned"] == "512k"
    r2 = m._t33_01a_resolve_max_tokens(None, effort="max", prompt_len=PROMPT_512K)
    assert r2["effective"] == 65_536 and r2["log"]["pinned"] == "512k"


def test_max_default_requires_thinking_mode():
    """INV-05 §6 排期条款：§4.6 thinking 键验证未闭合时，Max 缺省只对 thinking=true 生效。"""
    assert (
        m._t33_01a_resolve_max_tokens(None, effort="max", thinking_mode=False)[
            "effective"
        ]
        == 65_536
    )
    assert (
        m._t33_01a_resolve_max_tokens(None, effort="max", thinking_mode=True)[
            "effective"
        ]
        == 131_072
    )
    # 显式值不受 thinking 门影响（65537-131072 同权允许）
    assert (
        m._t33_01a_resolve_max_tokens(
            131_072, effort="high", thinking_mode=False
        )["effective"]
        == 131_072
    )


# ============================================================
# B) 与 01C executable spec 交叉对拍（"同一 5 case"的逐点等价证明）
# ============================================================


def _load_01c_spec():
    sys.path.insert(0, QUALITY_DIR)
    try:
        mod = importlib.import_module("test_max_tokens_matrix")
    finally:
        sys.path.remove(QUALITY_DIR)
    return mod.resolve_max_tokens_k16, mod.K16Rejected


@pytest.mark.parametrize(
    "requested,effort,prompt_len",
    [
        (None, "low", 8192),
        (None, "high", 8192),
        (None, "max", 8192),
        (None, "max", 500000),
        (None, "max", 524287),
        (None, "max", 524288),
        (None, "xhigh", 8192),
        (1, "high", 8192),
        (65_536, "high", 8192),
        (65_537, "high", 8192),
        (65_537, "max", 524287),
        (65_537, "high", 524288),
        (65_537, "low", 599999),
        (100_000, "high", 8192),
        (131_072, "high", 8192),
        (131_072, "max", 500000),
        (131_072, "high", 524288),
        (131_072, "low", 599999),
    ],
)
def test_cross_validation_with_01c_spec(requested, effort, prompt_len):
    """canonical 与 01C A 层参考解析器逐点等价（effective + log 全键）。"""
    spec_k16, spec_rejected = _load_01c_spec()
    spec_result = spec_k16(
        SimpleNamespace(max_new_tokens=requested), effort=effort, prompt_len=prompt_len
    )
    ours = m._t33_01a_resolve_max_tokens(
        requested, effort=effort, prompt_len=prompt_len, thinking_mode=True
    )
    assert ours["effective"] == spec_result["effective"]
    assert ours["log"] == spec_result["log"]


def test_cross_validation_reject_shape():
    spec_k16, spec_rejected = _load_01c_spec()
    with pytest.raises(spec_rejected):
        spec_k16(SimpleNamespace(max_new_tokens=131_073))
    with pytest.raises(m.T33_01AMaxTokensProtocolError):
        m._t33_01a_resolve_max_tokens(131_073)


# ============================================================
# C) 开关门控与默认惰性（验收门：默认 body 逐字节不变；只在开关开时变）
# ============================================================


@pytest.mark.parametrize("value", [None, "", "0", "false", "off", "no", "  ", "FALSE"])
def test_flag_off_values(value):
    env = {} if value is None else {m._T33_01A_RF_INJECT_FLAG: value}
    assert m._t33_01a_rf_inject_enabled(env) is False
    assert m._t33_01a_max_tokens_policy_enabled(env) is False


@pytest.mark.parametrize("value", ["1", "true", "on", "yes", "TRUE", " On ", "Yes"])
def test_flag_on_values(value):
    assert m._t33_01a_flag({m._T33_01A_EFFORT_FLAG: value}, m._T33_01A_EFFORT_FLAG)
    assert m._t33_01a_flag({m._T33_01A_RF_INJECT_FLAG: value}, m._T33_01A_RF_INJECT_FLAG)


def test_max_tokens_policy_off_full_inertness():
    """EFFORT_DEFAULT 关：缺省/显式一律不解析、不写回、不 400——现役链原样承载。"""
    env = {}
    req = SimpleNamespace(
        max_completion_tokens=None, max_tokens=None, response_format=None, tools=None
    )
    assert (
        m._t33_01a_resolve_for_request(
            req, prompt_len=8192, ctx_len=CTX_LEN, env=env
        )
        is None
    )
    assert m._t33_01a_apply_max_tokens(req, 8192, CTX_LEN, env=env) is None
    assert req.max_tokens is None  # 未写回
    req_big = SimpleNamespace(
        max_completion_tokens=131_073, max_tokens=None, response_format=None, tools=None
    )
    assert m._t33_01a_validate_chat_request(req_big, env=env) is None  # 关=无新 400
    # 显式值也不产生新日志/写回
    req_explicit = SimpleNamespace(
        max_completion_tokens=None, max_tokens=100_000, response_format=None, tools=None
    )
    assert (
        m._t33_01a_apply_max_tokens(req_explicit, 8192, CTX_LEN, env=env) is None
    )
    assert req_explicit.max_tokens == 100_000


def test_max_tokens_policy_on_writeback_and_log(caplog):
    """EFFORT_DEFAULT 开：缺省注入写回 max_tokens；显式值写回实际使用的字段。"""
    env = {m._T33_01A_EFFORT_FLAG: "1"}
    req = SimpleNamespace(
        max_completion_tokens=None,
        max_tokens=None,
        response_format=None,
        tools=None,
        reasoning_effort="max",
    )
    with caplog.at_level("INFO", logger="k16_protocol"):
        res = m._t33_01a_apply_max_tokens(
            req, 8192, CTX_LEN, thinking_mode=True, effort="max", env=env
        )
    assert res["effective"] == 131_072 and req.max_tokens == 131_072
    assert any(
        "max_tokens_k16" in r.message
        and "input=8192" in r.message
        and "original=None" in r.message
        and "clamped=131072" in r.message
        for r in caplog.records
    )
    # 显式 max_completion_tokens 优先写回该字段（protocol.py:1132 `mct or mt` 同序）
    req2 = SimpleNamespace(
        max_completion_tokens=100_000,
        max_tokens=None,
        response_format=None,
        tools=None,
    )
    res2 = m._t33_01a_apply_max_tokens(req2, 8192, CTX_LEN, env=env)
    assert res2["effective"] == 100_000 and req2.max_completion_tokens == 100_000
    assert req2.max_tokens is None
    # 512k 档 pin 写回 + pinned 日志
    req3 = SimpleNamespace(
        max_completion_tokens=None, max_tokens=65_537, response_format=None, tools=None
    )
    with caplog.at_level("INFO", logger="k16_protocol"):
        res3 = m._t33_01a_apply_max_tokens(req3, PROMPT_512K, CTX_LEN, env=env)
    assert res3["effective"] == 65_536 and req3.max_tokens == 65_536
    assert any("pinned=512k" in r.message for r in caplog.records)


def test_validate_400_only_when_policy_on():
    """>131072 的 400 只在策略开关开时生效（关=现役静默收敛行为不变）。"""
    env_on_ = {m._T33_01A_EFFORT_FLAG: "1"}
    req = SimpleNamespace(
        max_completion_tokens=None, max_tokens=200_000, response_format=None, tools=None
    )
    assert m._t33_01a_validate_chat_request(req, env=env_on_) is not None
    assert m._t33_01a_validate_chat_request(req, env={}) is None
    # max_completion_tokens 路径同律
    req2 = SimpleNamespace(
        max_completion_tokens=131_073, max_tokens=None, response_format=None, tools=None
    )
    err = m._t33_01a_validate_chat_request(req2, env=env_on_)
    assert err is not None and "131073" in err and "131072" in err


def test_log_line_format():
    line = m._t33_01a_format_max_tokens_log(
        {"input": 524288, "original": 65537, "clamped": 65536, "pinned": "512k"}
    )
    assert line == "max_tokens_k16 input=524288 original=65537 clamped=65536 pinned=512k"
    line2 = m._t33_01a_format_max_tokens_log(
        {"input": 8192, "original": 100000, "clamped": 100000}
    )
    assert line2 == "max_tokens_k16 input=8192 original=100000 clamped=100000"
    assert "pinned" not in line2


# ============================================================
# D) response_format 投影（A1 条件吸收：schema 校验后注入/grammar/禁双重约束）
# ============================================================

RF_JSON_SCHEMA = {"type": "json_schema", "json_schema": {"schema_": WEATHER_SCHEMA}}
RF_ON = {m._T33_01A_RF_INJECT_FLAG: "1"}


@pytest.mark.parametrize(
    "rf",
    [
        RF_JSON_SCHEMA,
        {"type": "json_object"},
        {"type": "text"},
        {"type": "regex", "regex": r"^\d+$"},
    ],
)
@pytest.mark.parametrize("flag_value", [None, "", "0", "false", "off"])
def test_rf_switch_off_inert_for_all_types(rf, flag_value):
    """护栏②同律：RF_INJECT 未开（任意非真值/未设）时任何 RF 类型都不注入。"""
    env = {} if flag_value is None else {m._T33_01A_RF_INJECT_FLAG: flag_value}
    payload, err = m._t33_01a_project_response_format(rf, env=env)
    assert payload is None and err is None


def test_rf_json_schema_schema_only_projection():
    """json_schema → schema-only 投影（反例 R3：不得出现整包 model_dump 外壳）。"""
    payload, err = m._t33_01a_project_response_format(RF_JSON_SCHEMA, env=RF_ON)
    assert err is None and payload == WEATHER_SCHEMA
    assert "json_schema" not in payload and "schema_" not in payload


def test_rf_json_object_and_text_go_grammar_path():
    """A1：json_object 走 grammar（prompt 不注入）；text 不渲染。"""
    for rf in ({"type": "json_object"}, {"type": "text"}):
        payload, err = m._t33_01a_project_response_format(rf, env=RF_ON)
        assert payload is None and err is None


def test_rf_tools_present_never_injects():
    """护栏③同律：tools 在场 → prompt schema 一律不注入（工具约束优先，禁双重约束）。"""
    for flag in (None, "1"):
        env = {} if flag is None else {m._T33_01A_RF_INJECT_FLAG: flag}
        payload, err = m._t33_01a_project_response_format(
            RF_JSON_SCHEMA, env=env, tools_present=True
        )
        assert payload is None and err is None


def test_rf_missing_schema_is_error():
    rf = {"type": "json_schema", "json_schema": {}}
    payload, err = m._t33_01a_project_response_format(rf, env=RF_ON)
    assert payload is None and err is not None and "schema_" in err


@pytest.mark.parametrize(
    "bad_schema", [None, 42, "not-a-dict", {"t": {1, 2}}]  # set 不可 JSON 序列化
)
def test_rf_invalid_schema_is_error(bad_schema):
    rf = {"type": "json_schema", "json_schema": {"schema_": bad_schema}}
    payload, err = m._t33_01a_project_response_format(rf, env=RF_ON)
    assert payload is None and err is not None


def test_rf_unknown_type_is_error_only_when_enabled():
    payload, err = m._t33_01a_project_response_format({"type": "yaml"}, env=RF_ON)
    assert payload is None and err is not None and "yaml" in err
    # 开关关时未知类型也不报错（整面惰性，缺省行为不变）
    payload2, err2 = m._t33_01a_project_response_format({"type": "yaml"}, env={})
    assert payload2 is None and err2 is None


def test_rf_regex_dormant_by_default():
    """P6（§2.2/表 2.4-B）：regex 休眠位——RF_REGEX 未开不渲染（无客户证据不启用）。"""
    payload, err = m._t33_01a_project_response_format(
        {"type": "regex", "regex": r"^\d+$"}, env=RF_ON
    )
    assert payload is None and err is None


def test_rf_regex_enabled_under_double_gate():
    env = {m._T33_01A_RF_INJECT_FLAG: "1", m._T33_01A_RF_REGEX_FLAG: "1"}
    payload, err = m._t33_01a_project_response_format(
        {"type": "regex", "regex": r"^\d+$"}, env=env
    )
    assert err is None and payload == {"type": "regex", "pattern": r"^\d+$"}
    # tools 在场仍不注入（双重约束禁，覆盖 regex 分支）
    payload2, _ = m._t33_01a_project_response_format(
        {"type": "regex", "regex": r"^\d+$"}, env=env, tools_present=True
    )
    assert payload2 is None


@pytest.mark.parametrize(
    "bad_pattern", [None, "", 123, "[" * 3 + "x", "a" * 2049]
)
def test_rf_regex_invalid_patterns_rejected(bad_pattern):
    env = {m._T33_01A_RF_INJECT_FLAG: "1", m._T33_01A_RF_REGEX_FLAG: "1"}
    payload, err = m._t33_01a_project_response_format(
        {"type": "regex", "regex": bad_pattern}, env=env
    )
    assert payload is None and err is not None


# ============================================================
# E) 接线形态：attach 语义 + 与 encoding_dsv41 端到端 prompt 对拍
# ============================================================


def test_attach_none_is_identity():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    snapshot = copy.deepcopy(msgs)
    out = m._t33_01a_attach_response_format(msgs, None)
    assert out is msgs and msgs == snapshot  # 同一对象、零改动（字节不变）


def test_attach_payload_deep_copies_and_inserts_host():
    msgs = [{"role": "user", "content": "hi"}]
    snapshot = copy.deepcopy(msgs)
    out = m._t33_01a_attach_response_format(msgs, WEATHER_SCHEMA)
    assert out is not msgs and msgs == snapshot  # 原消息不被原地改动
    assert out[0] == {"role": "system", "content": "", "response_format": WEATHER_SCHEMA}
    assert out[1] == {"role": "user", "content": "hi"}
    # 已有 system 时写入既有首条 system（官方顺序：content → tools → RF 段）
    msgs2 = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
    ]
    out2 = m._t33_01a_attach_response_format(msgs2, WEATHER_SCHEMA)
    assert len(out2) == 2 and out2[0]["response_format"] == WEATHER_SCHEMA
    assert out2[0]["content"] == "sys"


def _load_encoder():
    if not os.path.isfile(SGLANG_ENCODER):
        pytest.skip(f"encoding_dsv41 源不可读: {SGLANG_ENCODER}")
    spec = importlib.util.spec_from_file_location("t33a_encoding_dsv41", SGLANG_ENCODER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_end_to_end_prompt_with_encoder():
    """端到端：开关关 → prompt 与基线逐字节一致；json_schema 开 → 仅首 system 增段。"""
    enc = _load_encoder()
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Weather in Paris?"},
    ]
    request_off = SimpleNamespace(
        messages=copy.deepcopy(messages),
        response_format=RF_JSON_SCHEMA,
        tools=None,
    )
    baseline = enc.encode_messages(copy.deepcopy(messages), thinking_mode="chat")
    # 开关关：apply 原样返回 → prompt 逐字节不变
    out_messages = m._t33_01a_apply_response_format(
        copy.deepcopy(messages), request_off, env={}
    )
    assert enc.encode_messages(out_messages, thinking_mode="chat") == baseline
    # json_schema 开：首 system 增 ## Response Format: 段（schema-only）
    request_on = SimpleNamespace(
        messages=copy.deepcopy(messages),
        response_format=RF_JSON_SCHEMA,
        tools=None,
    )
    out_messages_on = m._t33_01a_apply_response_format(
        copy.deepcopy(messages), request_on, env=RF_ON
    )
    prompt_on = enc.encode_messages(out_messages_on, thinking_mode="chat")
    assert prompt_on != baseline
    assert "## Response Format:" in prompt_on
    assert '"city"' in prompt_on  # schema 字面进入
    assert '"json_schema"' not in prompt_on and '"schema_"' not in prompt_on  # R3 外壳禁
    # json_object 开：走 grammar，prompt 仍逐字节等于基线
    request_jo = SimpleNamespace(
        messages=copy.deepcopy(messages), response_format={"type": "json_object"}, tools=None
    )
    out_jo = m._t33_01a_apply_response_format(
        copy.deepcopy(messages), request_jo, env=RF_ON
    )
    assert enc.encode_messages(out_jo, thinking_mode="chat") == baseline


def test_selfcheck_subprocess():
    """--selfcheck 子进程退出码 0（无 pytest 环境的复核通道）。"""
    proc = subprocess.run(
        [sys.executable, MODULE_PATH, "--selfcheck"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "selfcheck: 23/23 passed" in proc.stdout


# ============================================================
# F) 呈裁补丁静态一致性（canonical sentinel 段逐字一致 + 门控核验）
# ============================================================

CANONICAL_BEGIN = "# ---- t33-01a canonical: begin"
CANONICAL_END = "# ---- t33-01a canonical: end"


def _module_canonical_region():
    with open(MODULE_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    start = text.index(CANONICAL_BEGIN)
    end = text.index(CANONICAL_END) + len(CANONICAL_END)
    return text[start:end].rstrip("\n")


def _patch_canonical_region():
    with open(PATCH_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    collecting, out = False, []
    for line in lines:
        if line.startswith(("+++", "---")):
            continue
        if not line.startswith("+"):
            continue
        content = line[1:]
        if CANONICAL_BEGIN in content:
            collecting = True
        if collecting:
            out.append(content)
        if collecting and CANONICAL_END in content:
            collecting = False
    assert out, "补丁必须内嵌 canonical sentinel 段"
    return "".join(out).rstrip("\n")


@pytest.mark.skipif(not os.path.isfile(PATCH_PATH), reason="呈裁补丁未生成")
def test_patch_canonical_identity():
    """补丁内嵌 canonical 段与模块逐字一致（漂移即红；SCHED_STATS_V1 同法）。"""
    assert _patch_canonical_region() == _module_canonical_region()


@pytest.mark.skipif(not os.path.isfile(PATCH_PATH), reason="呈裁补丁未生成")
def test_patch_static_gate_checks():
    """补丁静态门控核验：只动 serving_chat.py 一个 overlay 文件（任务书回退面
    "overlay 单文件回滚"）；三个接线点各自带对应开关门的注释同现（应用后
    T33-10 G-RF 对真实文件的静态断言 `not wired or gated` 仍绿）；无 env 改动。"""
    with open(PATCH_PATH, "r", encoding="utf-8") as f:
        patch_text = f.read()
    touched = {
        line.split()[1][2:]  # 剥离 a/ b/ 前缀
        for line in patch_text.splitlines()
        if line.startswith(("--- a/", "+++ b/"))
    }
    assert touched == {"deploy/overlay/o12c1-prod/serving_chat.py"}, touched
    assert "deploy/env" not in patch_text  # env 文件不在本补丁（臂决策另呈裁）

    added = [line[1:] for line in patch_text.splitlines() if line.startswith("+")]
    added_text = "\n".join(added)

    def wiring_comment_gate(call_snippet, flag):
        """接线调用点的上方注释块（≤8 行）必须出现门控开关键名。"""
        idx = added_text.find(call_snippet)
        assert idx != -1, f"补丁缺少接线点: {call_snippet}"
        context_above = added_text[max(0, idx - 600) : idx]
        assert flag in context_above, f"{call_snippet} 接线未带 {flag} 门注释"

    wiring_comment_gate(
        "messages = _t33_01a_apply_response_format(messages, request)",
        m._T33_01A_RF_INJECT_FLAG,
    )
    wiring_comment_gate(
        # 16 空格缩进=接线调用点（canonical 里的 def 是模块级零缩进，避免误配）
        "\n                _t33_01a_apply_max_tokens(",
        m._T33_01A_EFFORT_FLAG,
    )
    wiring_comment_gate(
        "_t33_01a_error = _t33_01a_validate_chat_request(request)",
        m._T33_01A_EFFORT_FLAG,
    )
    # canonical 段含两键（EFFORT_DEFAULT/RF_INJECT）+ regex 休眠子键
    region = _patch_canonical_region()
    for key in (
        m._T33_01A_EFFORT_FLAG,
        m._T33_01A_RF_INJECT_FLAG,
        m._T33_01A_RF_REGEX_FLAG,
    ):
        assert key in region
