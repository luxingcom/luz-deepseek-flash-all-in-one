# T33-01C 协议/tokenizer CPU 测试矩阵 —— 共享 fixture（W0 D1 交付）
#
# 任务书法源：docs/plan/033-TASKBOOK-V2-20261023.md §3.0.1（测试所有权表）与 T33-01C 任务节。
# 本文件是下列 5 个 fixture 的唯一作者（§3.0.1：「tests/quality/conftest.py fixture」行），
# T33-10（G-RF/G-CACHE）直接复用，不得复制实现（§3.0.3 硬规则 2/4）：
#   tokenizer_v41_local / encoding_dsv41 / mock_sampling_params / detector_chunks / baseline_prompt_hash
#
# 纪律（0 靴、CPU-only）：
#   - 只读访问模型目录与 SGLang 源码树；不加载权重、不启容器/GPU、不写任何产线文件。
#   - 生产 env 文件仅按行正则提取 SGLANG_MAX_NEW_TOKENS_LIMIT 一个键，不读取/不打印其余内容。
#
# 依赖说明：detector 链（deepseekv3x_detector）依赖 pydantic/orjson/partial_json_parser/
# sglang 协议层。本机无 sglang 运行环境，这里沿用 INV-05 §8 的 E1 CPU harness 方法：
# 以最小 stdlib 桩占据这些模块名后，按真实源码文件加载 detector（行为与桩无关的路径）。
# DSML 流式路径（parse_streaming_increment/detect_and_parse/finish）不调用
# partial_json_parser（deepseekv32_detector.py:252-383 仅用 json/re），桩只满足 import 期。

import copy
import hashlib
import importlib.util
import json
import re
import sys
import types
from types import SimpleNamespace

import pytest

# ============================================================
# 路径常量（可用环境变量覆盖，默认指向本机权威副本）
# ============================================================

# SGLang 基座源码树（79cafec0 线，INV-05 证据基线；只读）
SGLANG_SRC = "/home/liuxiaoya/sglang-main-src"
# 本机同源 tokenizer（DeepSeek-V4-Flash-Vision-Exp，INV-05 EV-05-028；只读，不加载权重）
TOKENIZER_V41_LOCAL = (
    "/home/liuxiaoya/models/DeepSeek-V4-Flash-Vision-Exp/tokenizer.json"
)
# 产线 1017 tokenizer（/data/models，只读；INV-05 §9.问题的 E1 直读对象）
TOKENIZER_PROD_1017 = (
    "/data/models/DeepSeek-V4.1-Flash-1017/tokenizer.json"
)
TOKENIZER_PROD_1017_SHA256SUMS = (
    "/data/models/DeepSeek-V4.1-Flash-1017/SHA256SUMS"
)
# 交付仓根（overlay/env 的只读来源）
LUZ_DELIVERY_ROOT = "/home/liuxiaoya/luz-deepseek-flash-all-in-one"
# 生产 env 文件（只按行提取 SGLANG_MAX_NEW_TOKENS_LIMIT）
PROD_ENV_FILES = [
    LUZ_DELIVERY_ROOT + "/deploy/env/CBX1A-CERTM-spec1.env",
    LUZ_DELIVERY_ROOT + "/deploy/env/PROD-R51W5-spec1.env",
    LUZ_DELIVERY_ROOT + "/deploy/env/PROD-R51W5-FL6FIX-spec1.env",
]

# 生产参谱（任务书 §4：pool 9.6M / ctx 600000 / MAX_NEW_TOKENS_LIMIT=65536）
CTX_LEN = 600_000
POOL_TOKENS = 9_600_000
PROMPT_512K = 524_288  # 512k 档 prompt 长度（token 计）


def _env_override(name, default):
    import os

    return os.environ.get(name, default)


SGLANG_SRC = _env_override("T33C_SGLANG_SRC", SGLANG_SRC)
TOKENIZER_V41_LOCAL = _env_override("T33C_TOKENIZER_V41_LOCAL", TOKENIZER_V41_LOCAL)
TOKENIZER_PROD_1017 = _env_override("T33C_TOKENIZER_PROD_1017", TOKENIZER_PROD_1017)


# ============================================================
# tokenizer 只读加载（纯 JSON 解析，不依赖 transformers/tokenizers）
# ============================================================


class TokenizerContract:
    """tokenizer.json 的只读契约视图（added_tokens 表 + 文件指纹）。

    仅解析 tokenizer.json 的 `added_tokens` 数组（HF fast 格式），
    不加载 vocab 权重，单文件 ~6.4MB，解析 <1s。
    """

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            raw = f.read()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.md5 = hashlib.md5(raw).hexdigest()
        doc = json.loads(raw)
        self.added_by_id = {t["id"]: t for t in doc.get("added_tokens", [])}
        self.added_by_content = {
            t["content"]: t for t in doc.get("added_tokens", [])
        }

    def entry_by_id(self, tid):
        return self.added_by_id.get(tid)

    def entry_by_content(self, content):
        return self.added_by_content.get(content)

    def flag(self, tid):
        e = self.entry_by_id(tid)
        return None if e is None else bool(e.get("special"))


@pytest.fixture(scope="session")
def tokenizer_v41_local():
    """本机同源 V4.1 tokenizer 只读契约（DeepSeek-V4-Flash-Vision-Exp 副本）。"""
    import os

    if not os.path.isfile(TOKENIZER_V41_LOCAL):
        pytest.skip(f"本机同源 tokenizer 不存在: {TOKENIZER_V41_LOCAL}")
    return TokenizerContract(TOKENIZER_V41_LOCAL)


@pytest.fixture(scope="session")
def tokenizer_production_1017():
    """产线 1017 tokenizer 只读契约（/data/models/DeepSeek-V4.1-Flash-1017）。

    INV-05 §9 开放问题 1 的直读对象；目录缺失时 skip（测试侧另有结论登记）。
    """
    import os

    if not os.path.isfile(TOKENIZER_PROD_1017):
        pytest.skip(f"产线 1017 tokenizer 不可读: {TOKENIZER_PROD_1017}")
    return TokenizerContract(TOKENIZER_PROD_1017)


def read_production_max_new_tokens_limit():
    """从生产 env 文件按行提取 SGLANG_MAX_NEW_TOKENS_LIMIT（不读其余行）。

    返回 {文件名: int}；文件缺失的条目记 None。
    """
    out = {}
    pattern = re.compile(r"^SGLANG_MAX_NEW_TOKENS_LIMIT=(\d+)\s*$")
    for path in PROD_ENV_FILES:
        value = None
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    m = pattern.match(line)
                    if m:
                        value = int(m.group(1))
                        break
        except OSError:
            value = None
        out[path.rsplit("/", 1)[-1]] = value
    return out


# ============================================================
# encoding_dsv41（纯 stdlib，按文件直接加载）
# ============================================================


def _load_module_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def encoding_dsv41():
    """SGLang 基座 encoding_dsv41（dsv41 路径编码器，只读源码，CPU 直跑）。

    该文件仅依赖 stdlib（copy/json/typing），无桩即可加载。
    """
    path = SGLANG_SRC + "/python/sglang/srt/entrypoints/openai/encoding_dsv41.py"
    return _load_module_from_path("t33c_encoding_dsv41", path)


# ============================================================
# DSML detector 真源加载（INV-05 §8 式最小桩 harness）
# ============================================================


class _StubBaseModel:
    """pydantic.BaseModel 的最小等价物：按类注解默认值填字段。

    core_types.ToolCallItem / StreamingParseResult 只作数据容器使用，
    detector 与本测试均不调用 pydantic 特有方法。
    """

    def __init__(self, **kwargs):
        for klass in reversed(type(self).__mro__):
            for field in getattr(klass, "__annotations__", {}):
                if field in kwargs or not hasattr(klass, field):
                    continue
                setattr(self, field, copy.deepcopy(getattr(klass, field)))
        for key, value in kwargs.items():
            setattr(self, key, value)


def _install_detector_stubs():
    """在 sys.modules 中放置 detector 链所需的最小桩（幂等）。"""
    if "sglang.srt.function_call.deepseekv41_detector" in sys.modules:
        return

    def pkg(name):
        m = types.ModuleType(name)
        m.__path__ = []
        sys.modules[name] = m
        return m

    pkg("sglang")
    pkg("sglang.srt")
    pkg("sglang.srt.entrypoints")
    pkg("sglang.srt.entrypoints.openai")

    protocol = types.ModuleType("sglang.srt.entrypoints.openai.protocol")

    class Tool:  # 仅类型标注/属性访问用
        pass

    class ToolChoice:
        pass

    protocol.Tool = Tool
    protocol.ToolChoice = ToolChoice
    sys.modules["sglang.srt.entrypoints.openai.protocol"] = protocol

    environ = types.ModuleType("sglang.srt.environ")

    class _EnvFlag:
        def get(self, default=None):
            return default if default is not None else False

    class _Envs:
        SGLANG_FORWARD_UNKNOWN_TOOLS = _EnvFlag()

    environ.envs = _Envs()
    sys.modules["sglang.srt.environ"] = environ

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = _StubBaseModel
    sys.modules["pydantic"] = pydantic

    orjson = types.ModuleType("orjson")
    orjson.loads = lambda s: json.loads(s)
    orjson.dumps = (
        lambda obj, **kw: json.dumps(obj).encode()
    )
    sys.modules["orjson"] = orjson

    pjp = types.ModuleType("partial_json_parser")

    def _pj_loads(s, flags=None):
        return json.loads(s)  # 不完整 JSON 抛 json.JSONDecodeError（DSML 路径不调用）

    pjp.loads = _pj_loads
    sys.modules["partial_json_parser"] = pjp

    core = types.ModuleType("partial_json_parser.core")
    sys.modules["partial_json_parser.core"] = core
    pjp.core = core

    exceptions = types.ModuleType("partial_json_parser.core.exceptions")

    class MalformedJSON(Exception):
        pass

    exceptions.MalformedJSON = MalformedJSON
    sys.modules["partial_json_parser.core.exceptions"] = exceptions
    core.exceptions = exceptions

    options = types.ModuleType("partial_json_parser.core.options")

    class Allow:
        ALL = 0b1111
        STR = 0b0001

    options.Allow = Allow
    sys.modules["partial_json_parser.core.options"] = options
    core.options = options

    pkg("sglang.srt.function_call")


def _load_detector_chain():
    """按真实源码文件加载 core_types→utils→base→v32→v41 detector 链。"""
    _install_detector_stubs()
    fc = SGLANG_SRC + "/python/sglang/srt/function_call/"
    modules = [
        ("sglang.srt.function_call.core_types", fc + "core_types.py"),
        ("sglang.srt.function_call.utils", fc + "utils.py"),
        (
            "sglang.srt.function_call.base_format_detector",
            fc + "base_format_detector.py",
        ),
        (
            "sglang.srt.function_call.deepseekv32_detector",
            fc + "deepseekv32_detector.py",
        ),
        (
            "sglang.srt.function_call.deepseekv41_detector",
            fc + "deepseekv41_detector.py",
        ),
    ]
    for name, path in modules:
        if name not in sys.modules:
            _load_module_from_path(name, path)
    return sys.modules["sglang.srt.function_call.deepseekv41_detector"]


@pytest.fixture(scope="session")
def dsv41_detector_cls():
    """现役 DeepSeekV41Detector 类（SGLang 79cafec0 真源，桩仅覆盖 import 期）。"""
    return _load_detector_chain().DeepSeekV41Detector


# ============================================================
# mock sampling params 工厂
# ============================================================


@pytest.fixture()
def mock_sampling_params():
    """SamplingParams 的最小 mock 工厂（不启引擎；scheduler 链只消费下列字段）。

    与 scheduler.init_req_max_new_tokens 的真实消费面一致（overlay scheduler.py:2659-2682）：
    max_new_tokens（None → 引擎侧 1<<30）。
    """

    def _make(max_new_tokens=None, **overrides):
        params = SimpleNamespace(
            max_new_tokens=max_new_tokens,
            temperature=1.0,
            top_p=0.95,
            ignore_eos=False,
        )
        for key, value in overrides.items():
            setattr(params, key, value)
        return params

    return _make


@pytest.fixture()
def detector_chunks():
    """现役 8 档 chunk 矩阵（test_deepseekv41_detector.py:26；EV-05-025）。"""
    return [1, 2, 3, 5, 7, 11, 23, 1000]


# ============================================================
# baseline prompt hash（T33-10 G-RF 复用：缺省 body 逐字节不变的基准）
# ============================================================

BASELINE_MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the weather in Paris?"},
]


@pytest.fixture(scope="session")
def baseline_prompt_hash(encoding_dsv41):
    """缺省（无 response_format/无 tools）dsv41 prompt 的 sha256 基准。

    T33-10 G-RF 负向护栏用它做「缺省 body 逐字节不变」对照：
    同一 messages 经 encoding_dsv41.encode_messages 的输出 sha256 必须与此一致。
    负向护栏本体归 T33-10（test_no_go_render_contract.py），此处只提供基准。
    """
    prompt = encoding_dsv41.encode_messages(
        copy.deepcopy(BASELINE_MESSAGES), thinking_mode="chat"
    )
    return {
        "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt": prompt,
        "messages": copy.deepcopy(BASELINE_MESSAGES),
    }
