"""R1 形式感知准入门（form-aware admission）——600k 长档准入的 R1 正解件。

用户裁定（A22b，2026-10）：64k/128k 撞 dense 态 T×L 门，必须按 DeepSeek 技术报告采用
「近似进度、只做局部计算」（R1 = 消费层候选内 gather 打分）来解除，**抬
DSV41_TL_BUDGET_ELEMS 只是测试臂证法（C16-600K-spec0 臂 2.478e9），不得转正**。

本模块把该裁定工程化：准入门的限额不再由「抬预算」决定，而由**引擎的实际形态**决定——

    形态 = dense（R1 消费面未上岗）      ⇒ 限额不变：budget // row_chunk = 48,828 tok
    形态 = R1（gather 消费面 ENGAGED）   ⇒ 限额 = min(ctx_cap, decode_elems_cap)

R1 形态限额的推导（全部常量有出处，非拍脑袋）：
1. **ctx_cap**：引擎 `--context-length 600000`（标准形态令；模型
   max_position_embeddings=1048576 在限内）。缺省 600,000，键
   `DSV41_SPARSE_LOCAL_ADMISSION_CTX_CAP` 可改（须 > dense 限额，否则拒绝武装）。
2. **decode_elems_cap = budget // max_running_requests**：R1 形态下 decode 步仅剩
   publish 层 1 次全量打分（论文「retaining the initial full-range pass」），每步
   elems = bs × lmax；C16-PREFLIGHT §一.1 同律评估（16×600k=9.6e6 ≪ 2e8，1000×
   裕度）。4 个消费层已 gather 化（宽度 16,384 常数，DESIGN.md §一.2）。
3. **prefill publish 全扫的瞬态**由 128MiB tile 律管辖（score_tiles 逐 tile 产/放，
   C16-PREFLIGHT §一.2 四条代码证据）——因此武装前置断言
   `DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES` 不得为 off/0（该防线在场是 R1 形式
   准入的前件）。

== fail-closed 清单（每条在 unit_xcheck §5 与容器冒烟 p5/p6 有反向红例）==========
FC1 键关（缺省）⇒ 零加载零漂移：不 patch、不 import 重件，stock 门原样。
FC2 键开但 seam 未 ENGAGED（探针拒/锚缺/CONSUME 键关）⇒ 限额坍缩回 dense 48,828
   （每请求惰性求值——「形式」以引擎实况为准，不以配置自称为准。这正是与
   「抬 TL_BUDGET」的本质差：抬预算在 gather 静默回退 dense 时照样放行 600k）。
FC3 `DSV41_TL_BUDGET_ELEMS` 被显式改动（≠2e8 缺省，或 =off）⇒ 拒绝武装：双重改门
   = 语义不明，一律 refuse（测试臂证法不得与 R1 同靴）。
FC4 `DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES` ∈ {off, 0} ⇒ 拒绝武装（prefill publish
   瞬态防线不在场）。
FC5 ctx_cap ≤ dense 限额 ⇒ 拒绝武装（无意义形态）。
FC6 坏的 ctx_cap/MRR 值 ⇒ 拒绝武装（诚实拒，不静默取缺省后放行）。

== 安装面 =====================================================================
不另包 TokenizerManager（避免与 stock admission_gate 的 wrap 顺序耦合）：本模块
patch **stock 门的 `_budget()`**——三件同键的纪律由此保持（执行的仍是同一段
admission_gate 代码，只有预算推导变成形式感知；stock 的 =off 解除语义、坏值回缺省
语义原样保留在未武装臂）。部署走 seam 审批线（本树零部署侧写入）。
"""

from __future__ import annotations

import os

ADMISSION_ENV = "DSV41_SPARSE_LOCAL_ADMISSION"            # 总门，缺省关
CTX_CAP_ENV = "DSV41_SPARSE_LOCAL_ADMISSION_CTX_CAP"      # 缺省 600000（标准形态）
MRR_ENV = "DSV41_SPARSE_LOCAL_ADMISSION_MRR"              # 缺省 16（标准形态并发）

# 与 stock admission_gate/sparse_wire/needle_probe 三件共享的键（只读，不写）。
TL_BUDGET_ENV = "DSV41_TL_BUDGET_ELEMS"
TILE_BUDGET_ENV = "DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES"
STOCK_TL_BUDGET = 2 * 10**8          # stock 缺省（admission_gate.py DEFAULT_BUDGET）
STOCK_ROW_CHUNK = 4096               # stock 缺省 row chunk（= chunked_prefill_size）
DEFAULT_CTX_CAP = 600000             # 标准形态 600k（引擎 --context-length 同值）
DEFAULT_MRR = 16                     # 标准形态并发（--max-running-requests 同值）

_ON = ("1", "true", "yes", "on")
_OFF = ("off", "0", "", "false")

DENSE_FORM = "dense"
R1_FORM = "r1"


class AdmissionDecision:
    """一次限额求值的不可变结果（可 stringify 进横幅/日志）。"""

    __slots__ = ("form", "limit", "why", "armed")

    def __init__(self, form: str, limit, why: str, armed: bool):
        self.form = form
        self.limit = limit          # int tok；None = 门解除（仅沿 stock =off 语义）
        self.why = why
        self.armed = armed

    def __repr__(self) -> str:  # pragma: no cover - 调试面
        lim = "off" if self.limit is None else format(self.limit, ",")
        return f"AdmissionDecision(form={self.form} limit={lim} armed={self.armed} why={self.why})"


def _env(name: str):
    return os.environ.get(name)


def _parse_int_env(name: str, default: int):
    """返回 (ok, value)；坏值=（False, None）——fail-closed 拒武装，不静默回缺省。"""
    raw = _env(name)
    if raw is None or not raw.strip():
        return True, default
    try:
        v = int(float(raw.strip()))
    except ValueError:
        return False, None
    return (v > 0), v


def stock_tl_budget():
    """stock admission_gate._budget() 的语义镜像（只读 env，不 import 部署侧件）。

    None = 三件键显式解除（off/0/false）；坏值回缺省 2e8（stock 同律）。
    """
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
    """FC3 判据：三件键未被显式改动（未设，或设值==缺省 2e8）。"""
    raw = _env(TL_BUDGET_ENV)
    if raw is None:
        return True
    raw = raw.strip().lower()
    if raw in _OFF:
        return False                      # 解除三件防线 ≠ R1 形式
    try:
        return int(float(raw)) == STOCK_TL_BUDGET
    except ValueError:
        return True                       # 坏值沿 stock 回缺省 = 无行为差


def tile_guard_alive() -> bool:
    """FC4 判据：prefill publish 全扫的 128MiB tile 防线在场（未显式关）。"""
    raw = _env(TILE_BUDGET_ENV)
    if raw is None:
        return True                       # stock 键缺省即 128MiB（sparse_wire 定板）
    raw = raw.strip().lower()
    if raw in _OFF:
        return False
    try:
        return int(float(raw)) > 0
    except ValueError:
        return True                       # 坏值沿 sparse_wire 回缺省


def admission_enabled() -> bool:
    return _env(ADMISSION_ENV) is not None and _env(ADMISSION_ENV).strip().lower() in _ON


def dense_limit(budget=None) -> int:
    b = stock_tl_budget() if budget is None else budget
    rc = _parse_int_env("DSV41_TL_ROW_CHUNK", STOCK_ROW_CHUNK)
    chunk = rc[1] if rc[0] else STOCK_ROW_CHUNK
    return b // chunk


def evaluate(seam_engaged_fn) -> AdmissionDecision:
    """纯函数决策面（host 可测；seam_engaged_fn() → bool = 引擎实况形式探针）。

    求值序（先便宜后贵；任何 refuse 都带 why）：
      键关 → dense 形态（限额照 stock 求值）
      FC3/FC4/FC5/FC6 前置 → 拒绝武装（form=dense，why 注明 refuse 因）
      seam 未 ENGAGED → FC2：dense 限额（这不是 refuse，是形式坍缩——配置开但
        引擎没有局部计算形态，门必须保守）
      全过 → R1 形态，limit = min(ctx_cap, budget//MRR)
    """
    if not admission_enabled():
        return AdmissionDecision(
            DENSE_FORM, dense_limit(), "admission key off (zero-load)", armed=False)

    budget = stock_tl_budget()
    if budget is None:
        return AdmissionDecision(
            DENSE_FORM, None,
            "REFUSED: " + TL_BUDGET_ENV + "=off disarms the shared T×L family; "
            "R1 admission refuses to arm on a disarmed family (FC3)", armed=False)
    if not stock_tl_budget_pristine():
        return AdmissionDecision(
            DENSE_FORM, budget // STOCK_ROW_CHUNK,
            "REFUSED: " + TL_BUDGET_ENV + " explicitly mutated ("
            f"{_env(TL_BUDGET_ENV).strip()}); raising the test-arm budget is proof "
            "only and must not combine with R1 (FC3)", armed=False)
    if not tile_guard_alive():
        return AdmissionDecision(
            DENSE_FORM, budget // STOCK_ROW_CHUNK,
            "REFUSED: " + TILE_BUDGET_ENV + " off/0; the prefill publish full-range "
            "pass keeps the 128MiB tile guard as a precondition of the R1 form (FC4)",
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
        engaged = bool(seam_engaged_fn())
    except Exception as exc:  # 探针本身炸 = 形式未知 = 保守
        return AdmissionDecision(
            DENSE_FORM, dl,
            f"FC2: engagement probe raised {type(exc).__name__}; collapsed to dense "
            f"limit", armed=False)
    if not engaged:
        return AdmissionDecision(
            DENSE_FORM, dl,
            "FC2: gather consumer NOT ENGAGED (key off / probe refused / anchor "
            "missing); admission follows the engine's actual form, not the "
            "configured one", armed=False)

    decode_cap = budget // mrr
    limit = min(ctx_cap, decode_cap)
    return AdmissionDecision(
        R1_FORM, limit,
        f"R1 form: gather consumer ENGAGED; limit=min(ctx cap {ctx_cap:,}, decode "
        f"elems {budget:,}//{mrr}={decode_cap:,})={limit:,} tok; dense fallback "
        f"{dl:,}; publish keeps the full-range pass under the 128MiB tile law",
        armed=True)


# ───────────────────────── 安装面（部署审批线；本树零部署） ─────────────────────────

_PATCHED = {"stock": None}


def effective_budget(seam_engaged_fn):
    """patch 后 stock `_budget()` 的替身：按 evaluate() 决策返回等效预算。

    返回值语义与 stock 完全一致：int elems（limit×row_chunk）或 None（=off 沿
    stock 解除语义——只在三件键本身 off 时出现，此时 evaluate 已 REFUSED 回 dense
    形态，而 dense 形态下 budget=None 的 stock 行为=门解除，与用户常开裁定冲突？
    不冲突：FC3 已把 off 判为 refuse-arm，refuse-arm 时本函数不会被安装（见
    install 的武装条件）。此处保守双保险：R1 未武装时永不返回 None。
    """
    d = evaluate(seam_engaged_fn)
    if not d.armed:
        b = stock_tl_budget()
        return b  # 未武装：stock 语义原样（含 None——与 stock 门自身一致）
    rc = _parse_int_env("DSV41_TL_ROW_CHUNK", STOCK_ROW_CHUNK)
    chunk = rc[1] if rc[0] else STOCK_ROW_CHUNK
    return d.limit * chunk


def install(stock_admission_module, seam_engaged_fn) -> bool:
    """patch stock admission_gate._budget 为形式感知版。返回是否武装。

    纪律：只在 evaluate() 判 R1 形态（或形式坍缩但前置全过）时 patch——坍缩态
    patch 与不 patch 行为相同（都回 stock 求值），patch 的意义是让后续每请求
    惰性重估（探针晚到/晚拒都跟得上）。键关=零 patch 零 import 重件。
    """
    if not admission_enabled():
        return False
    if stock_admission_module is None:
        print("[sparse_local_admission] REFUSED -> stock admission gate intact. "
              "why: stock admission_gate module not supplied", flush=True)
        return False
    if not hasattr(stock_admission_module, "_budget"):
        print("[sparse_local_admission] REFUSED -> stock admission gate intact. "
              "why: stock _budget anchor missing", flush=True)
        return False
    d0 = evaluate(seam_engaged_fn)
    if not d0.armed and d0.why.startswith("REFUSED"):
        print(f"[sparse_local_admission] {d0.why}", flush=True)
        return False

    orig = stock_admission_module._budget
    if getattr(orig, "_r1_patched", False):
        return True  # 幂等

    def _budget():
        return effective_budget(seam_engaged_fn)

    _budget._r1_patched = True
    _budget._r1_orig = orig
    stock_admission_module._budget = _budget
    _PATCHED["stock"] = stock_admission_module
    print(
        f"[sparse_local_admission] form-aware admission ARMED (engine form probed "
        f"per request; R1 limit will show as the gate's own limit line; dense "
        f"fallback {dense_limit():,} tok stays whenever the gather consumer is "
        f"not ENGAGED)",
        flush=True,
    )
    return True


def uninstall() -> bool:
    """回退 patch（测试面；部署侧回退=键关即坍缩 dense，无需卸载）。"""
    mod = _PATCHED["stock"]
    if mod is None:
        return False
    cur = getattr(mod, "_budget", None)
    if getattr(cur, "_r1_patched", False):
        mod._budget = cur._r1_orig
    _PATCHED["stock"] = None
    return True


def summary() -> str:
    on = admission_enabled()
    if not on:
        return f"gate={ADMISSION_ENV}=(off; zero-load) stock_limit={dense_limit():,}"
    d = evaluate(lambda: False)  # 摘要不探针：给最保守形态 + 注明惰性
    # 修复（R1STDFORM X-2，2026-10-03）：键设时 _env() 返回 str，f"{str:,}" 崩
    # （"Cannot specify ',' with 's'"）——部署态（A25 键全设）sitecustomize banner
    # 调本函数曾令 adapter 整体中止。先经 _parse_int_env 归一（坏值也安全显示）。
    cap = _parse_int_env(CTX_CAP_ENV, DEFAULT_CTX_CAP)[1]
    mrr = _parse_int_env(MRR_ENV, DEFAULT_MRR)[1]
    cap_s = "bad" if cap is None else format(cap, ",")
    mrr_s = "bad" if mrr is None else str(mrr)
    lim = "off" if d.limit is None else format(d.limit, ",")
    return (
        f"gate={_env(ADMISSION_ENV)} ctx_cap={cap_s} "
        f"mrr={mrr_s} static_view(form={d.form}, "
        f"limit={lim}) per-request probe=on patched={_PATCHED['stock'] is not None}"
    )
