"""admission_segment — 0731/VL 线形式感知准入门（O13 案 A 件②，admission_r1 形移植）。

法源=TLSEGMENT-CARD-20261006.md §四（主会话审定 3b97071 审定点③）+admission_r1.py
（~/migrate-assets/dsv41/adapter/，V4.1 R1 形在役同构——移植其**纪律形态**：限额由
引擎实际形态决定、惰性重估、fail-closed 清单、三键 pristine；不移植其 R1 seam 探针
——0731/VL 无 candidate 消费面，形式探针换**分段形**=tl_segment 分幅件 ENGAGED）。

== 与 48,828 政策门的关系（不拆门）=========================================
48,828 门=admission_gate.py:51-83（wrap TokenizerManager._validate_one_request，
input>2e8//4096→400，always-on 政策件，M0731-SPEC0.env 注 2）。本件**不另包
TokenizerManager、不拆政策门**：只 patch stock 门的 `_budget()`（admission_r1
同法同面，:37-41 锚）——执行的仍是同一段 admission_gate 代码，只是预算推导按
**分段后的 per-chunk T×L 降额实况**重算：

    形态 = dense（分段形未 ENGAGED）   ⇒ 限额不变：2e8//4096 = 48,828 tok
    形态 = segment（分幅件 ENGAGED）  ⇒ 限额 = min(ctx_cap, budget//mrr)
                                        = min(600000, 2e8//12≈16.7M) = 600,000

600k 判据的机理（per-chunk T×L 降额，TLSEGMENT §1.2/§四）：stock 打分链本就
rows-tile 化（flat_index_logits_tiles 逐 tile 产/放，budget=128MiB 分幅件在场），
48,828 门的「2e8 单块物化」原始前提在 main-79cafec0 已不成立；分段形把 per-chunk
打分瞬态钉回 tile 预算律（128MiB×3-4 传导≈0.4-0.5G/层）⇒ 请求级 T×L 上限可由
ctx 帽（600000）与并发 decode 账（budget//mrr）接管。

== Q4 裁定纪律（阈值数字=用户裁定项）=======================================
600,000 这个数字=Q4 重定价的用户裁定项（O10A 核证注记②维持；裁定前不越门=X1 律）。
本件的缺省态=**fail-closed 不武装**：两键（DSV41_TL_SEGMENT=1 分幅形在场 +
DSV41_TL_SEGMENT_ADMISSION=1 准入键）任一缺省 ⇒ dense 48,828 原样——武装动作
本身即 Q4 裁定的落卡形式。CTX_CAP/MRR 可配（DSV41_TL_SEGMENT_ADMISSION_CTX_CAP/
_MRR），缺省 600000/12=C12 形（COMPAT-FORM-C12 §一：mrr12）与 0.4.5 跨栈先例
（max-num-seqs 12，LUZ045-SURVEY §2.5）同值。

== fail-closed 清单（admission_r1 同构移植；每条有反向红例单测）============
FC1 键关（缺省）⇒ 零加载零漂移：不 patch、不 import 重件，stock 门原样（键缺=
   零行为直证=test_admission_segment.py::test_fc1_key_off_zero_behavior）。
FC2 键开但分段形未 ENGAGED（tl_segment 未装/探针炸）⇒ 限额坍缩回 dense 48,828
   （每请求惰性求值——「形式」以引擎实况为准，不以配置自称为准）。
FC3 三键 pristine：DSV41_TL_BUDGET_ELEMS 被显式改动（≠2e8 缺省）或 =off ⇒ 拒绝
   武装（X1 律工程化：抬预算测试证法不得与分段形同靴；三件共享键族不动）。
FC4 tile 预算防线 off/0（DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES∈{off,0}）⇒
   拒绝武装（128MiB tile 律在场是分段形准入的前件）。
FC5 ctx_cap ≤ dense 限额 ⇒ 拒绝武装（无意义形态）。
FC6 坏的 ctx_cap/MRR 值 ⇒ 拒绝武装（诚实拒，不静默取缺省后放行）。

== 安装面 ==================================================================
部署走 sitecustomize 挂点（sitecustomize.py 的 tokenizer_manager 分支，admission_r1
install 同位新增三行式分派）+ tl_segment 分幅件 install 于 scoring 分支——**O13 窗
才布**；本树零部署侧写入。卸载=键关重启（patch 不落地）。
"""
from __future__ import annotations

import os
from typing import Callable, Optional

ADMISSION_ENV = "DSV41_TL_SEGMENT_ADMISSION"                # 总门，缺省关
CTX_CAP_ENV = "DSV41_TL_SEGMENT_ADMISSION_CTX_CAP"          # 缺省 600000
MRR_ENV = "DSV41_TL_SEGMENT_ADMISSION_MRR"                  # 缺省 12（C12 形）

# 共享键（只读，不写——三件同键纪律原样）。
TL_BUDGET_ENV = "DSV41_TL_BUDGET_ELEMS"
TILE_BUDGET_ENV = "DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES"
STOCK_TL_BUDGET = 2 * 10**8            # stock 缺省（admission_gate.py:26 DEFAULT_BUDGET）
STOCK_ROW_CHUNK = 4096                 # stock 缺省 row chunk（=chunked_prefill_size）
DEFAULT_CTX_CAP = 600000               # 标准形态 600k（引擎 --context-length 同值）
DEFAULT_MRR = 12                       # C12 形并发（--max-running-requests 12，C12 §一）

_ON = ("1", "true", "yes", "on")
_OFF = ("off", "0", "", "false")

DENSE_FORM = "dense"
SEGMENT_FORM = "segment"


class AdmissionDecision:
    """一次限额求值的不可变结果（可 stringify 进横幅/日志；admission_r1 同构）。"""

    __slots__ = ("form", "limit", "why", "armed")

    def __init__(self, form: str, limit, why: str, armed: bool):
        self.form = form
        self.limit = limit          # int tok；None=门解除（仅沿 stock =off 语义）
        self.why = why
        self.armed = armed

    def __repr__(self) -> str:  # pragma: no cover - 调试面
        lim = "off" if self.limit is None else format(self.limit, ",")
        return (f"AdmissionDecision(form={self.form} limit={lim} "
                f"armed={self.armed} why={self.why})")


def _env(name: str):
    return os.environ.get(name)


def _parse_int_env(name: str, default: int):
    """返回 (ok, value)；坏值=(False, None)——fail-closed 拒武装（FC6）。"""
    raw = _env(name)
    if raw is None or not raw.strip():
        return True, default
    try:
        v = int(float(raw.strip()))
    except ValueError:
        return False, None
    return (v > 0), v


def stock_tl_budget():
    """stock admission_gate._budget() 语义镜像（admission_r1 同法：只读 env）。"""
    raw = _env(TL_BUDGET_ENV)
    if raw is None:
        return STOCK_TL_BUDGET
    raw = raw.strip().lower()
    if raw in _OFF:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return STOCK_TL_BUDGET


def stock_tl_budget_pristine() -> bool:
    """FC3 判据：三件键未被显式改动（未设，或设值==缺省 2e8；X1 律）。"""
    raw = _env(TL_BUDGET_ENV)
    if raw is None:
        return True
    raw = raw.strip().lower()
    if raw in _OFF:
        return False                      # 解除三件防线 ≠ 分段形
    try:
        return int(float(raw)) == STOCK_TL_BUDGET
    except ValueError:
        return True                       # 坏值沿 stock 回缺省=无行为差


def tile_guard_alive() -> bool:
    """FC4 判据：128MiB tile 律在场（共享键未显式关；tl_segment/sparse_wire 定板）。"""
    raw = _env(TILE_BUDGET_ENV)
    if raw is None:
        return True
    raw = raw.strip().lower()
    if raw in _OFF:
        return False
    try:
        return int(float(raw)) > 0
    except ValueError:
        return True                       # 坏值沿 install 法回缺省


def admission_enabled() -> bool:
    v = _env(ADMISSION_ENV)
    return v is not None and v.strip().lower() in _ON


def dense_limit(budget=None) -> int:
    b = stock_tl_budget() if budget is None else budget
    rc = _parse_int_env("DSV41_TL_ROW_CHUNK", STOCK_ROW_CHUNK)
    chunk = rc[1] if rc[0] else STOCK_ROW_CHUNK
    return b // chunk


def segment_limit(ctx_cap: int, mrr: int, budget: int) -> int:
    """分段形限额=min(ctx 帽, 并发 decode 元素账 budget//mrr)——per-chunk T×L 已由
    128MiB tile 律钉住，请求级上限由这两项接管（admission_r1 :219-220 同构）。"""
    return min(ctx_cap, budget // mrr)


def evaluate(segment_engaged_fn: Callable[[], bool]) -> AdmissionDecision:
    """纯函数决策面（host 可测；segment_engaged_fn()=tl_segment.segment_engaged）。

    求值序（先便宜后贵；任何 refuse 都带 why）：
      键关 → dense 形态（限额照 stock 求值，FC1）
      FC3/FC4/FC5/FC6 前置 → 拒绝武装（form=dense，why 注明 refuse 因）
      分段形未 ENGAGED → FC2：dense 限额（形式坍缩——保守，非 refuse）
      全过 → segment 形态，limit = min(ctx_cap, budget//mrr)
    """
    if not admission_enabled():
        return AdmissionDecision(
            DENSE_FORM, dense_limit(), "admission key off (zero-load)", armed=False)

    budget = stock_tl_budget()
    if budget is None:
        return AdmissionDecision(
            DENSE_FORM, None,
            "REFUSED: " + TL_BUDGET_ENV + "=off disarms the shared T×L family; "
            "segment admission refuses to arm on a disarmed family (FC3)",
            armed=False)
    if not stock_tl_budget_pristine():
        return AdmissionDecision(
            DENSE_FORM, budget // STOCK_ROW_CHUNK,
            "REFUSED: " + TL_BUDGET_ENV + " explicitly mutated ("
            f"{_env(TL_BUDGET_ENV).strip()}); raising the test-arm budget is proof "
            "only and must not combine with the segment form (FC3, X1 law)",
            armed=False)
    if not tile_guard_alive():
        return AdmissionDecision(
            DENSE_FORM, budget // STOCK_ROW_CHUNK,
            "REFUSED: " + TILE_BUDGET_ENV + " off/0; the 128MiB tile law must be "
            "in place as a precondition of the segment form (FC4)",
            armed=False)
    ok_cap, ctx_cap = _parse_int_env(CTX_CAP_ENV, DEFAULT_CTX_CAP)
    if not ok_cap:
        return AdmissionDecision(
            DENSE_FORM, budget // STOCK_ROW_CHUNK,
            f"REFUSED: {CTX_CAP_ENV}={_env(CTX_CAP_ENV).strip()!r} unparseable/"
            f"non-positive (FC6)", armed=False)
    ok_mrr, mrr = _parse_int_env(MRR_ENV, DEFAULT_MRR)
    if not ok_mrr:
        return AdmissionDecision(
            DENSE_FORM, budget // STOCK_ROW_CHUNK,
            f"REFUSED: {MRR_ENV}={_env(MRR_ENV).strip()!r} unparseable/"
            f"non-positive (FC6)", armed=False)
    dl = budget // STOCK_ROW_CHUNK
    if ctx_cap <= dl:
        return AdmissionDecision(
            DENSE_FORM, dl,
            f"REFUSED: ctx cap {ctx_cap:,} <= dense limit {dl:,} (FC5)", armed=False)

    try:
        engaged = bool(segment_engaged_fn())
    except Exception as exc:  # 探针本身炸=形式未知=保守（FC2）
        return AdmissionDecision(
            DENSE_FORM, dl,
            f"FC2: segment engagement probe raised {type(exc).__name__}; "
            f"collapsed to dense limit", armed=False)
    if not engaged:
        return AdmissionDecision(
            DENSE_FORM, dl,
            "FC2: segment form NOT ENGAGED (tl_segment not installed / tile guard "
            "missing); admission follows the engine's actual form, not the "
            "configured one", armed=False)

    limit = segment_limit(ctx_cap, mrr, budget)
    return AdmissionDecision(
        SEGMENT_FORM, limit,
        f"segment form: per-chunk T×L derated under the 128MiB tile law; "
        f"limit=min(ctx cap {ctx_cap:,}, elems {budget:,}//{mrr}="
        f"{budget // mrr:,})={limit:,} tok; dense fallback {dl:,}",
        armed=True)


# ───────────────────────── 安装面（部署审批线；本树零部署） ─────────────────────────

_PATCHED = {"stock": None}


def effective_budget(segment_engaged_fn) -> Optional[int]:
    """patch 后 stock `_budget()` 的替身：按 evaluate() 决策返回等效预算（元素数）。

    返回值语义与 stock 完全一致：int elems（limit×row_chunk）或 None（=off，仅沿
    stock 解除语义——armed 恒不为 None，双保险同 admission_r1 :234-249）。
    """
    d = evaluate(segment_engaged_fn)
    if not d.armed:
        return stock_tl_budget()          # 未武装：stock 语义原样
    rc = _parse_int_env("DSV41_TL_ROW_CHUNK", STOCK_ROW_CHUNK)
    chunk = rc[1] if rc[0] else STOCK_ROW_CHUNK
    return d.limit * chunk


def install(stock_admission_module, segment_engaged_fn) -> bool:
    """patch stock admission_gate._budget 为形式感知版。返回是否武装。

    纪律（admission_r1 同构）：只在分段形前置全过时 patch；坍缩态 patch 与不
    patch 行为相同（都回 stock 求值），patch 的意义=后续每请求惰性重估。键关=
    零 patch 零 import 重件。
    """
    if not admission_enabled():
        return False                      # FC1：键缺=零行为
    if stock_admission_module is None:
        print("[tl_segment_admission] REFUSED -> stock admission gate intact. "
              "why: stock admission_gate module not supplied", flush=True)
        return False
    if not hasattr(stock_admission_module, "_budget"):
        print("[tl_segment_admission] REFUSED -> stock admission gate intact. "
              "why: stock _budget anchor missing", flush=True)
        return False
    d0 = evaluate(segment_engaged_fn)
    if not d0.armed and d0.why.startswith("REFUSED"):
        print(f"[tl_segment_admission] {d0.why}", flush=True)
        return False

    orig = stock_admission_module._budget
    if getattr(orig, "_tlseg_patched", False):
        return True                       # 幂等

    def _budget():
        return effective_budget(segment_engaged_fn)

    _budget._tlseg_patched = True
    _budget._tlseg_orig = orig
    stock_admission_module._budget = _budget
    _PATCHED["stock"] = stock_admission_module
    print(
        "[tl_segment_admission] form-aware admission ARMED (engine form probed "
        "per request; segment limit shows as the gate's own limit line; dense "
        f"fallback {dense_limit():,} tok stays whenever the segment form is "
        "not ENGAGED)",
        flush=True,
    )
    return True


def uninstall() -> bool:
    """回退 patch（测试面；部署侧回退=键关即坍缩 dense）。"""
    mod = _PATCHED["stock"]
    if mod is None:
        return False
    cur = getattr(mod, "_budget", None)
    if getattr(cur, "_tlseg_patched", False):
        mod._budget = cur._tlseg_orig
    _PATCHED["stock"] = None
    return True


def summary() -> str:
    on = admission_enabled()
    if not on:
        return (f"gate={ADMISSION_ENV}=(off; zero-load) "
                f"stock_limit={dense_limit():,}")
    d = evaluate(lambda: False)           # 摘要不探针：给最保守形态+注明惰性
    cap = _parse_int_env(CTX_CAP_ENV, DEFAULT_CTX_CAP)[1]
    mrr = _parse_int_env(MRR_ENV, DEFAULT_MRR)[1]
    cap_s = "bad" if cap is None else format(cap, ",")
    mrr_s = "bad" if mrr is None else str(mrr)
    lim = "off" if d.limit is None else format(d.limit, ",")
    return (
        f"gate={_env(ADMISSION_ENV)} ctx_cap={cap_s} mrr={mrr_s} "
        f"static_view(form={d.form}, limit={lim}) per-request probe=on "
        f"patched={_PATCHED['stock'] is not None}"
    )
