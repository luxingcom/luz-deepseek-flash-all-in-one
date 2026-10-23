# T33-01C —— max_tokens 协议矩阵（K16 定稿语义，5 case，纯 CPU / mock sampling params）
#
# 法源：任务书 §3.0.1「max_tokens 协议矩阵」行 + T33-01A 目标 1（K16，:912-919）
# 与 T33-01A 验收门（:928-933）。K16 语义（任务书 §11 复核表 #5 / R12）：
#   - 显式 65537-131072 对 Max/非 Max 同权允许（不采纳 AUDIT-05 #5 的「非 Max 一律 400」）；
#   - 允许值按 ctx_len − prompt_len − 1 收敛并记 input/original/clamped 日志；
#   - 显式 >131072 返回 400；
#   - 512k 档 pin 65536 并记 pinned=512k（避免 C8×512k 池位越红线）；
#   - 缺省 None：非 Max 65536 / Max 131072（不照搬官方 8192/393216）。
#
# 本文件分两层：
#   A) K16 参考解析器（executable spec）——把任务书语义固化为纯函数，5 case 全部
#      pass（语义锁定；T33-01A 实现后以同一矩阵对真实接线复跑）。
#   B) 现役生产行为登记——按 overlay scheduler.py:2659-2682 + 生产 env
#      SGLANG_MAX_NEW_TOKENS_LIMIT=65536 忠实重建的「现役解析器」，K16 增量
#      （131072 放行 / 131073 400 / 512k pin 日志 / Max 缺省档）尚未达成，
#      逐条 xfail(strict=True) 登记，实现归 T33-01A（W5 条件件）。
#
# 红线：不启引擎；sampling params 全部走 conftest.mock_sampling_params。

import pytest

from conftest import (
    CTX_LEN,
    PROMPT_512K,
    read_production_max_new_tokens_limit,
)

# ---- K16 常量 ----
K16_PROTOCOL_LIMIT = 131_072  # >131072 → 400
K16_DEFAULT_NON_MAX = 65_536
K16_DEFAULT_MAX = 131_072
K16_512K_PIN = 65_536
SHORT_PROMPT = 8_192  # 短 prompt 样本（512k 之外的代表档）


class K16Rejected(Exception):
    """K16：显式 max_tokens > 131072 的 400 语义。"""


def resolve_max_tokens_k16(sampling_params, effort="high", prompt_len=SHORT_PROMPT,
                           ctx_len=CTX_LEN):
    """K16 参考解析器（executable spec，纯 CPU）。

    输入 mock sampling params（max_new_tokens=None 表示请求未给预算）。
    返回 dict：effective / log（input、original、clamped、pinned）。
    """
    requested = sampling_params.max_new_tokens
    log = {"input": prompt_len, "original": requested}

    if requested is None:
        # 缺省按 effort 注入：Max 131072，其余（含非思考）65536
        base = K16_DEFAULT_MAX if effort == "max" else K16_DEFAULT_NON_MAX
    else:
        if requested > K16_PROTOCOL_LIMIT:
            raise K16Rejected(
                f"max_tokens {requested} exceeds protocol limit {K16_PROTOCOL_LIMIT}"
            )
        base = requested  # 65537-131072 对 Max/非 Max 同权允许

    if prompt_len >= PROMPT_512K:
        # 512k 档 pin 65536（C8×512k 池位红线），日志写 pinned=512k
        effective = min(base, K16_512K_PIN)
        log["pinned"] = "512k"
    else:
        # 按 ctx 收敛：ctx_len − prompt_len − 1（与官方 resolve_max_tokens 同形）
        effective = max(1, min(base, ctx_len - prompt_len - 1))
    log["clamped"] = effective
    return {"effective": effective, "log": log}


def resolve_max_tokens_current(sampling_params, prompt_len=SHORT_PROMPT,
                               ctx_len=CTX_LEN, limit=None):
    """现役生产行为的忠实重建（E1 源码链，非 K16 目标）。

    链条（overlay scheduler.py:2659-2682 + 生产 env）：
      None → 1<<30 → min(cap=SGLANG_MAX_NEW_TOKENS_LIMIT) → min(ctx_len−input−1)
    无 400 协议校验、无 effort 分档、无 512k pin 日志。limit 缺省从生产 env
    文件实读（deploy/env/*: SGLANG_MAX_NEW_TOKENS_LIMIT=65536）。
    """
    if limit is None:
        values = read_production_max_new_tokens_limit()
        usable = [v for v in values.values() if v is not None]
        assert usable, "生产 env 文件均不可读，无法确定现役 cap"
        limit = usable[0]
    requested = sampling_params.max_new_tokens
    max_new_tokens = requested if requested is not None else 1 << 30
    if limit is not None and limit > 0:
        max_new_tokens = min(max_new_tokens, limit)
    max_new_tokens = max(0, min(max_new_tokens, ctx_len - prompt_len - 1))
    return max_new_tokens


# ============================================================
# A) K16 5 case（必须齐全，任务书 T33-01A 验收门）
# ============================================================


def test_case1_default_none_by_effort(mock_sampling_params):
    """case 1：None → 非 Max 65536；Max 131072（均按 ctx 收敛）。"""
    non_max = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=None), effort="high"
    )
    assert non_max["effective"] == 65_536
    mx = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=None), effort="max"
    )
    assert mx["effective"] == 131_072
    # 收敛检查：Max 缺省 131072 在 prompt>468927 时被 ctx 收敛；演示档取
    # prompt=500000（<524288，不触发 512k pin；ctx 余量 99999 < 131072）
    tight = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=None),
        effort="max",
        prompt_len=500_000,
    )
    assert tight["effective"] == CTX_LEN - 500_000 - 1 == 99_999


def test_case2_explicit_65537_allowed_and_clamped(mock_sampling_params):
    """case 2：65537 → allowed，按 ctx/pool 收敛，日志含 input/original/clamped。"""
    r = resolve_max_tokens_k16(mock_sampling_params(max_new_tokens=65_537))
    assert r["effective"] == 65_537  # 短 prompt 下原值有效（不静默削顶）
    assert r["log"]["input"] == SHORT_PROMPT
    assert r["log"]["original"] == 65_537
    assert r["log"]["clamped"] == 65_537
    # 收敛侧算术（非 512k 档）：remaining = ctx_len − prompt_len − 1 ≥ 75711
    # （prompt<524288），恒大于 65537——即 65537 在非 512k 档不会被 ctx 削；
    # 其收敛只发生在 512k 档，而那里由 pin=65536 接管（case 5）。
    boundary = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=65_537), prompt_len=PROMPT_512K - 1
    )
    assert boundary["effective"] == 65_537  # 512k 档外原值有效（不静默削顶）
    assert boundary["log"]["clamped"] == 65_537


def test_case3_explicit_131072_allowed_and_clamped(mock_sampling_params):
    """case 3：131072 → allowed，按 ctx/pool 收敛，日志含 input/original/clamped。"""
    r = resolve_max_tokens_k16(mock_sampling_params(max_new_tokens=131_072))
    assert r["effective"] == 131_072
    assert r["log"]["original"] == 131_072 and r["log"]["clamped"] == 131_072
    r2 = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=131_072),
        prompt_len=CTX_LEN - 100_000,
    )
    assert r2["effective"] == 99_999  # ctx 收敛记录在 clamped


def test_case4_explicit_131073_rejected_400(mock_sampling_params):
    """case 4：131073 → 400（显式 >131072 拒绝）。"""
    with pytest.raises(K16Rejected):
        resolve_max_tokens_k16(mock_sampling_params(max_new_tokens=131_073))


def test_case5_512k_prompt_pins_65536(mock_sampling_params):
    """case 5：512k prompt + 65537 → 65536，日志含 pinned=512k。"""
    r = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=65_537), prompt_len=PROMPT_512K
    )
    assert r["effective"] == 65_536
    assert r["log"]["pinned"] == "512k"
    # Max 缺省同样被 pin（512k 档统一 65536）
    r2 = resolve_max_tokens_k16(
        mock_sampling_params(max_new_tokens=None),
        effort="max",
        prompt_len=PROMPT_512K,
    )
    assert r2["effective"] == 65_536 and r2["log"]["pinned"] == "512k"


# ============================================================
# B) 现役生产行为登记（K16 增量未达成项，xfail 单列）
# ============================================================


@pytest.mark.xfail(
    strict=True,
    reason=(
        "现役登记：SGLANG_MAX_NEW_TOKENS_LIMIT=65536（deploy/env/CBX1A-CERTM-spec1.env:31"
        " 等三份生产 env 一致），显式 131072 被 scheduler 静默削顶到 65536"
        "（scheduler.py:2666-2673 无 65537-131072 放行档）；K16 同权放行属"
        " T33-01A（W5 条件件，0 靴矩阵先行锁定语义）。"
    ),
)
def test_production_gap_allows_131072(mock_sampling_params):
    """K16 case 3 语义在现役生效：显式 131072（短 prompt）不被削顶。"""
    assert resolve_max_tokens_current(mock_sampling_params(max_new_tokens=131_072)) == 131_072


@pytest.mark.xfail(
    strict=True,
    reason=(
        "现役登记：显式 >131072 不返回 400，而是与其它值同样静默收敛到 65536"
        "（scheduler 链无协议上限校验；serving_chat 仅有 prompt+output>ctx 的"
        " total-token 校验，serving_chat.py:1090-1095）；400 语义属 T33-01A。"
    ),
)
def test_production_gap_rejects_131073_with_400(mock_sampling_params):
    """K16 case 4 语义在现役生效：显式 131073 返回 400。"""
    with pytest.raises(K16Rejected):
        resolve_max_tokens_current(mock_sampling_params(max_new_tokens=131_073))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "现役登记：512k 档结果值碰巧为 65536（cap<ctx 余量），但无 pinned=512k"
        " 观测点（scheduler 仅打印 requested/cap，无 512k pin 语义），运维不可区分"
        " 「pin」与「碰巧削顶」；pin+日志属 T33-01A。"
    ),
)
def test_production_gap_512k_pin_observable(mock_sampling_params):
    """K16 case 5 语义在现役生效：512k 档 pin 65536 且日志含 pinned=512k。"""
    r = resolve_max_tokens_current(
        mock_sampling_params(max_new_tokens=65_537), prompt_len=PROMPT_512K
    )
    # 结果值 65536 现役已满足；缺的是 pinned=512k 日志观测点——这里以
    # 「现役无 pin 语义」为红：把现役输出包成 K16 日志形状必然失败。
    assert isinstance(r, dict) and r.get("log", {}).get("pinned") == "512k"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "现役登记：缺省 None 无 effort 分档（None → 1<<30 → cap 65536，"
        " EV-05-032 历史日志实证），Max 档缺省 131072 属 T33-01A。"
    ),
)
def test_production_gap_default_max_effort_131072(mock_sampling_params):
    """K16 case 1 语义在现役生效：缺省 + effort=max → 131072。"""
    assert resolve_max_tokens_current(mock_sampling_params(max_new_tokens=None)) == 131_072


def test_production_default_non_max_is_65536(mock_sampling_params):
    """现役基线（非缺陷）：缺省 None → 65536——K16 亦保持该缺省，不因放宽而变。"""
    values = read_production_max_new_tokens_limit()
    usable = [v for v in values.values() if v is not None]
    assert usable and set(usable) == {65_536}, (
        "生产 env 的 SGLANG_MAX_NEW_TOKENS_LIMIT 应全部为 65536（当前基线）: %r"
        % values
    )
    assert resolve_max_tokens_current(mock_sampling_params(max_new_tokens=None)) == 65_536
