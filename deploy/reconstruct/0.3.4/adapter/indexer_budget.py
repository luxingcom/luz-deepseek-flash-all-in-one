"""F-1 案 A 预算旋钮（W2 修复窗预装件，2026-10-09；法源=
docs/research/INDEXER-ROWCHUNK-PORTPLAN-20261009.md §三案 A +
docs/taskcards/PREFILL-FIX-CAMPAIGN-CARD-20261009.md §七 F-1 缩容判）。

新键 DSV41_INDEXER_SCORE_BUDGET_BYTES（命名避撞 sparse_wire 的 0.2.8 血统键
DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES——两键共存律见下）：

  - 未设/空/off/0            = no-op：一个常量都不改（部署面语义=sparse_wire
    缺省 128MiB 定板原样；纯 stock 靴=2<<30 位等原样）。
  - 合法正整数 [1MiB, 16GiB] = 改写 v41_indexer.scoring 两模块常量：
        _DEEP_GEMM_SCORE_BUDGET_BYTES = b              （scoring.py:205 每调用读模块全局）
        _TORCH_SCORE_BUDGET_BYTES     = max(1, b // 2)  （:313 同；//2 保 stock
                                                          2GiB:1GiB 的两路比例语义）
  - 非法值（非纯十进制整数/<1MiB 地板/>16GiB 天花）= fail-closed 拒装+横幅：
    不套用垃圾值、不静默——常量保持 install 时刻的现值（sparse_wire 语义或
    stock）原地不动。A5 负对照律：1B 预算只会铸造病态 tile 风暴，宁可拒装。

与 sparse_wire.install_scoring 的共存律（装载次序=法）：sitecustomize 的
scoring 分支先装 sparse_wire（其缺省把两常量收到 128MiB）再装本件 ⇒
键设置时本件确定性压过 128MiB 缺省；键未设时 sparse_wire 语义原样。
要真 stock 2GiB 档必须用 sparse_wire 自己的键
DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES=off（本件在键未设时不越权回改
——判别键不改产线 43 键形，产线复原目标恒=R1STDLL128 原样）。

横幅律（off 可判，family law）：ARMED/REFUSED 一行打印旧->新两路径值；
boot 期 summary() 由 sitecustomize 横幅块打印解析结果（免 GPU 可区分
off / armed / on-but-refused）。

地板/天花理由（自主决定，如实呈报；地板 2026-10-09 gear a1 网格实锚后从 1MiB
上调）：引擎 flat_index_logits_rows_per_tile 的行对齐地板=max(128//heads, …)
——预算小于 row_alignment×row_bytes 时引擎按【对齐】不按【预算】出 tile
（w2_f1_gear a1 负网格实测：B=1MiB/w=65536/h=8 → 16 行×256KiB=4MiB tile）。
最劣几何（h=8 对齐 16 行 × 最大 lc ~73k 列 fp32 ≈292KiB/行）≈4.7MiB ⇒ 地板
8MiB（2× 余量）保证【凡被接受的预算值必被引擎严格兑现】；天花 16GiB=units
错型防呆（Meant-MiB 型笔误），旋钮用途=缩预算判别非扩预算。
"""
from __future__ import annotations

import os
import re

KEY = "DSV41_INDEXER_SCORE_BUDGET_BYTES"
MIN_BUDGET = 8 << 20   # 8 MiB（见下地板理由）
MAX_BUDGET = 16 << 30  # 16 GiB
STOCK_DEEP_GEMM = 2 << 30   # v41_indexer/scoring.py:27 stock 值（位等锚）
STOCK_TORCH = 1 << 30       # v41_indexer/scoring.py:236 stock 值

_INT_RE = re.compile(r"^[0-9]+$")
_OFF = ("", "0", "off", "false", "no")

# 供 summary()/单测读取的末次解析-装载状态（进程内；scoring 每 worker 进程各一份）。
STATE = {
    "action": "noop",       # noop | arm | refuse | anchors-missing
    "value": None,
    "why": "unset",
    "installed": False,
    "before": (None, None),
    "after": (None, None),
}

_INSTALLED = set()


def parse(raw):
    """解析键值 → (action, value, why)；action ∈ {'noop','arm','refuse'}。

    fail-closed 律：任何看不懂的 token 一律 refuse（拒装+横幅），绝不猜。
    刻意比 knapcio 的 int(float(raw)) 更严：拒绝 0x..、1e6、1MiB、1_0 等
    一切非纯十进制写法——判别臂的预算值必须是操作者无歧义写下的字节数。
    """
    if raw is None or raw.strip() in _OFF:
        return "noop", None, "unset/explicit-off"
    s = raw.strip()
    if not _INT_RE.match(s):
        return "refuse", None, "non-integer token %r" % raw
    v = int(s)
    if v < MIN_BUDGET:
        return "refuse", None, (
            "%d < floor %d (8MiB)——A5 负对照：低于引擎行对齐地板的预算无法被"
            "严格兑现（w2_f1_gear a1 负网格实证），拒装保现值（不允许静默全量）"
            % (v, MIN_BUDGET))
    if v > MAX_BUDGET:
        return "refuse", None, (
            "%d > ceiling %d (16GiB)——units 错型防呆（旋钮用途=缩预算判别）"
            % (v, MAX_BUDGET))
    return "arm", v, "ok"


def install(module) -> bool:
    """scoring 模块 exec 时改写两常量；装在 sparse_wire.install_scoring 之后。

    只动两个 int 常量、不动任何函数对象（与 indexer_hoist 的 decode_scores
    包装零冲突——设计稿 §三交互核对律）。
    """
    key = module.__name__ + "#indexer_budget"
    if key in _INSTALLED:
        return False
    raw = os.environ.get(KEY)
    action, value, why = parse(raw)
    dg = getattr(module, "_DEEP_GEMM_SCORE_BUDGET_BYTES", None)
    tw = getattr(module, "_TORCH_SCORE_BUDGET_BYTES", None)
    STATE["before"] = (dg, tw)
    if dg is None and tw is None:
        STATE.update(action="anchors-missing", value=None, why=why, installed=False)
        _INSTALLED.add(key)
        print("[indexer_budget] anchors missing on %s; skipped (fail-closed)"
              % module.__name__, flush=True)
        return False
    if action == "arm":
        new_tw = max(1, value // 2)
        if dg is not None:
            module._DEEP_GEMM_SCORE_BUDGET_BYTES = value
        if tw is not None:
            module._TORCH_SCORE_BUDGET_BYTES = new_tw
        STATE.update(action="arm", value=value, why=why, installed=True,
                     after=(value if dg is not None else None,
                            new_tw if tw is not None else None))
        _INSTALLED.add(key)
        print("[indexer_budget] ARMED %s=%d (%.0fMiB): deep_gemm %s->%s, "
              "torch %s->%s (b//2 stock 比例律); installed AFTER "
              "sparse_wire.install_scoring => 本键压过其 128MiB 缺省"
              % (KEY, value, value / (1 << 20), dg,
                 value if dg is not None else "(absent)", tw,
                 new_tw if tw is not None else "(absent)"), flush=True)
        return True
    # noop 或 refuse：常量原样（refuse 必须出声——不允许静默）
    STATE.update(action=action, value=None, why=why, installed=False,
                 after=(dg, tw))
    _INSTALLED.add(key)
    if action == "refuse":
        print("[indexer_budget] REFUSED %s=%r: %s —— 常量保持现值 "
              "(deep_gemm=%s, torch=%s)，no-op"
              % (KEY, raw, why, dg, tw), flush=True)
    return False


def summary() -> str:
    """boot 横幅行：免 GPU 可判 off / armed / on-but-refused（解析面，不含
    install 时刻——scoring 模块此后才 import，ARMED/REFUSED 行届时另出）。"""
    raw = os.environ.get(KEY)
    action, value, why = parse(raw)
    if action == "arm":
        eff = "ARMED(pending scoring import) value=%d deep_gemm=%d torch=%d" % (
            value, value, max(1, value // 2))
    elif action == "refuse":
        eff = "WILL-REFUSE: %s" % why
    else:
        eff = "no-op (sparse_wire 语义原样)"
    return ("gate=%s parse=%s floor=%dMiB cap=%dGiB installed=%s"
            % (raw if raw is not None else "(unset)", eff,
               MIN_BUDGET >> 20, MAX_BUDGET >> 30,
               ",".join(sorted(_INSTALLED)) or "no"))
