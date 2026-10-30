# T33-01C —— G-TOK 产线 1017 tokenizer 只读契约核对（T33-01C 独占；NG-08 只读引用）
#
# 法源：任务书 §3.0.1「tokenizer id/flag 契约」行 + T33-01C 目标 1（G-TOK）。
# 红线：只断言 id/flag/content，不替换 tokenizer（NG-08）；不按官方 <｜image｜>
# special=true 硬断言我方 tokenizer——官方样本仅作对照。
#
# 白名单（repo id / 文件 hash；2026-10-23 E1 实测）：
#   - 产线 1017：/data/models/DeepSeek-V4.1-Flash-1017
#       tokenizer.json     sha256 c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b
#                          （与模型自带 SHA256SUMS 首行逐字一致）
#       tokenizer_config.json 存在但无 added_tokens_decoder（added token 表只在
#                          tokenizer.json 的 added_tokens 数组，HF fast 格式）
#   - 本机同源副本：/home/liuxiaoya/models/DeepSeek-V4-Flash-Vision-Exp
#       tokenizer.json     sha256 与 1017 逐字节相同（c90dfa01…476b）
#   - 官方对照样本（不作为我方断言目标，E4 带外，EV-05-005）：
#       deepseek-recipe static/tokenizers/v41 —— 修改副本，id 129264 = <｜image｜>
#       special=true（我方/上游同源为 <｜deepseek_image｜> special=false）
#
# 任务书预期记录：本机 `[图像]`=129264、special=false（T33-01C 节引 INV-05:63）。
# E1 实测该 id 的 content 字面为 `<｜deepseek_image｜>`（INV-05:63 原文即如此）；
# 契约不变量是 id=129264 + special=false + 非官方改名副本，测试按此断言。
#
# 结论预告（详见 033-W0/T33-01C-REPORT.md）：产线 1017 与本机同源副本逐字节一致，
# INV-05 §9 开放问题 1 就此闭合——test_tokenizer_contract_production_1017 由原计划
# 的 xfail(strict=True) 升级为直接执行并通过（未确认项已确认）。

import re

import pytest

from conftest import TOKENIZER_PROD_1017_SHA256SUMS

# ---- 契约常量（任务书 §3.0.1 / INV-05 EV-05-028）----
ID_IMAGE = 129264
CONTENT_IMAGE_UPSTREAM = "<｜deepseek_image｜>"
CONTENT_IMAGE_OFFICIAL = "<｜image｜>"  # 官方修改副本对照，不得出现在我方文件
ID_THINK, CONTENT_THINK = 128821, "<think>"
ID_THINK_END, CONTENT_THINK_END = 128822, "</think>"
ID_DSML, CONTENT_DSML = 128825, "｜DSML｜"

WHITELIST_SHA256 = (
    "c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b"
)


def _assert_core_ids(tok):
    """三组核心 id 的 content/special 断言（本机与产线共用）。"""
    image = tok.entry_by_id(ID_IMAGE)
    assert image is not None, "id 129264 必须存在于 added_tokens"
    assert image["content"] == CONTENT_IMAGE_UPSTREAM
    assert image["special"] is False, "129264 必须保持 special=false（上游形态）"
    assert (
        tok.entry_by_content(CONTENT_IMAGE_OFFICIAL) is None
    ), "不得出现官方改名副本 <｜image｜>"
    assert tok.flag(ID_THINK) is False and tok.flag(ID_THINK_END) is False
    assert tok.entry_by_id(ID_THINK)["content"] == CONTENT_THINK
    assert tok.entry_by_id(ID_THINK_END)["content"] == CONTENT_THINK_END
    assert tok.flag(ID_DSML) is False
    assert tok.entry_by_id(ID_DSML)["content"] == CONTENT_DSML


def test_tokenizer_contract_local(tokenizer_v41_local):
    """本机同源副本：129264=<｜deepseek_image｜>/special=false + hash 白名单。"""
    _assert_core_ids(tokenizer_v41_local)
    # hash 白名单：漂移即红（防止换入官方修改副本或别的 tokenizer）
    assert tokenizer_v41_local.sha256 == WHITELIST_SHA256


def test_tokenizer_contract_production_1017(
    tokenizer_production_1017, tokenizer_v41_local
):
    """产线 1017 直读核对（INV-05 §9 问题 1 闭合）。

    原计划在未直读前 xfail(strict=True)；本机 /data/models 副本可读且与模型自带
    SHA256SUMS 逐字一致，故直接执行。三重核对：
      1) id/flag 契约与本机同源副本一致；
      2) tokenizer.json 与本机副本逐字节一致（sha256 相同）；
      3) sha256 与 1017 模型目录自带 SHA256SUMS 清单中的登记值一致。
    """
    _assert_core_ids(tokenizer_production_1017)
    assert (
        tokenizer_production_1017.sha256 == tokenizer_v41_local.sha256
    ), "产线 1017 与本机同源副本必须逐字节一致"
    assert tokenizer_production_1017.sha256 == WHITELIST_SHA256

    try:
        with open(TOKENIZER_PROD_1017_SHA256SUMS, "r", encoding="utf-8") as f:
            manifest = f.read()
    except OSError:
        pytest.skip("SHA256SUMS 清单不可读（目录缺失）")
    m = re.search(r"^([0-9a-f]{64})\s+tokenizer\.json\s*$", manifest, re.M)
    assert m, "SHA256SUMS 必须登记 tokenizer.json"
    assert m.group(1) == tokenizer_production_1017.sha256


@pytest.mark.xfail(
    strict=True,
    reason=(
        "已知缺陷：现役 tokenizer 的 added_tokens 含 ｜DSML｜(id 128825，special=false)，"
        "tokenizer.encode() 会把用户 content 里的字面 ｜DSML｜ 静默编码为 added token"
        "（INV-05:113 / EV-05-028）；官方以「去 added 词表的 plain 段 + 仅 special range"
        " 编码为 added token」规避。0.3.3 不替换 tokenizer（NG-08），token-kind-aware"
        " 解析归 T33-01B（0.3.4）。"
    ),
)
def test_tokenizer_special_text_not_added(tokenizer_v41_local):
    """user content 中特殊 token 文本不得被静默转为 added token（目标语义，现未达成）。"""
    entry = tokenizer_v41_local.entry_by_content(CONTENT_DSML)
    assert entry is None, (
        "｜DSML｜ 不应作为 added token 存在（存在即 encode() 静默转换）——"
        "现状：id=%s" % (entry and entry["id"])
    )
