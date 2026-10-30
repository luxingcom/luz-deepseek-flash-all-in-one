"""tl_segment — 0731/VL 线行分幅位等分段件（O13 案 A 件①，键控 install，缺省关）。

法源=TLSEGMENT-CARD-20261006.md 案 A（主会话审定 3b97071）+A23RESTART-ENG-CARD
§二(a) shared tile 网格法。本件是战役 dev 树新文件：**不改在役件任何行**（引擎
树/adapter 零接触）；install 形=sparse_wire.install_scoring 同法（模块属性 patch，
scoring.py:210-225 的 score_tiles 调用期读模块全局——单点覆盖 dense topk+块发布+
块消费三路，full_topk.py:73-74/dense_blocks.py:256,310）。

== 与在役 sparse_wire 的关系（2026-10-05 实测定谳，如实登记）==================
M0731W2 靴日志直证：0731 线 adapter 挂载（PYTHONPATH=/opt/dsv41/adapter）下
sparse_wire.install_scoring **常开生效**（seg4-teardown-logs/<prod-log>：「sparse_wire: scoring row-chunk budgets <- ..(deep_gemm
2,147,483,648->134217728..)」）——TLSEGMENT-CARD §1.1「0731 现形=stock 2GiB」
的预算面前提**已被实测推翻**：A4 黑名单剥的是 env 键（arm env 不得设
DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES），不是 install 本体。因此本件 ①预算
同源的职责=**键控自有化+审计面**（同值 128MiB 幂等收编；adapter 缺位时兜底
patch 到同值），而非从 2GiB 降额；分段形的增量价值在 ②形式探针（供 admission_
segment 判 ENGAGED）与 ③tile 网格/A-B 位等对拍面（E1 一锤的常驻载具）。

== 键面（全部新键；共享键只读不写）==========================================
DSV41_TL_SEGMENT            总门，缺省关。键缺/非 1=零行为（零 patch 零 banner）。
DSV41_TL_SEGMENT_TILE_BYTES tile 预算（字节），缺省 134217728=128MiB（V4.1 在役
                            同值同语义，sparse_wire.py DEFAULT_SCORE_BUDGET）；
                            off/0/坏值=拒绝武装（FC4/FC6，fail-closed）。
DSV41_TL_SEGMENT_GRID       tile 网格形：derate（缺省，128MiB 网格）/stock（stock
                            2GiB 同网格=A/B 位等对拍形，本形不降预算、只作 E1
                            对拍与 first-call bit-identical 探针载具）；坏值拒绝。

== 位等立场（A23RESTART §三 E1 前置）=======================================
H-B（kernel M-不变，E1 绿）⇒ derate 形纯内存件、逐位等、直装；
H-A ⇒ derate 形=全靴单一 M 形（自洽，T17 建锚窗重建基线），但 on/off A/B 对拍
   须走 grid=stock 形（同 M 同 width 同输入⇒逐位等 by construction，调用级确定性）。
E1 卷宗=test_e1_m_invariance.py；kernel 级 first-call bit-identical 探针=
   kernel_probe()（GPU+deep_gemm 在场才可跑；O13 窗在役首调）。
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

_logger = logging.getLogger("tl_segment")

SEGMENT_ENV = "DSV41_TL_SEGMENT"
TILE_BYTES_ENV = "DSV41_TL_SEGMENT_TILE_BYTES"
GRID_ENV = "DSV41_TL_SEGMENT_GRID"

DEFAULT_TILE_BUDGET = 134217728            # 128MiB，V4.1 在役同值（sparse_wire 定板）
STOCK_TILE_BUDGET = 2 << 30                # main scoring.py:27 stock 值
STOCK_TORCH_BUDGET = 1 << 30               # main scoring.py:236 stock 值
ROW_ALIGN_ELEMS = 256                      # mqa_logits_utils.MQA_LOGITS_ROW_ALIGN_ELEMS
BYTES_PER_ELEM = 4                         # fp32 logits
KERNEL_ROW_ALIGN_DEN = 128                 # flat_index_logits_rows_per_tile 的 128//heads
WIDTH_ALIGN = 4                            # score_tiles 调用 width_align=4（scoring.py:220）

GRID_DERATE = "derate"
GRID_STOCK = "stock"
_ON = ("1", "true", "yes", "on")
_OFF = ("off", "0", "", "false")

# install 状态（进程内单例；admission_segment 的形式探针读这里）
_STATE = {"installed": False, "budget": None, "grid": None, "patches": None}


# ───────────────────────── 纯算术核（零依赖，可离线单测） ─────────────────────────

def _ceil_div(x: int, y: int) -> int:
    return -(-x // y)


def _ceil_align(x: int, y: int) -> int:
    return _ceil_div(x, y) * y


def mqa_row_bytes(width: int) -> int:
    """行字节=ceil(width/256)·256·4B（mqa_logits_utils.mqa_logits_row_bytes 同式；
    A23RESTART §1.2 row_bytes 同律）。"""
    return _ceil_align(max(int(width), 1), ROW_ALIGN_ELEMS) * BYTES_PER_ELEM


def rows_per_tile(rows: int, width: int, heads: int, budget_bytes: int) -> int:
    """flat_index_logits_rows_per_tile 镜像（index_logits.py:20-33 逐式同构）。

    行对齐=128//heads；预算行数= budget//row_bytes；None（全批即一 tile）时返回
    rows 本身；否则对齐到行对齐倍数（max(alignment, R//alignment*alignment)）。
    """
    row_alignment = max(1, KERNEL_ROW_ALIGN_DEN // max(int(heads), 1))
    aligned_rows = _ceil_align(int(rows), row_alignment)
    rb = mqa_row_bytes(width)
    if aligned_rows * rb <= budget_bytes:
        return int(rows)
    r = max(budget_bytes // max(rb, 1), 1)
    if r >= aligned_rows:
        return int(rows)
    return max(row_alignment, r // row_alignment * row_alignment)


def tile_slices(rows: int, rows_per_tile: int) -> List[slice]:
    """行分幅 slice 表：恰切分割 [0,rows)（无重叠无缝；末 tile 收余数）。

    E1 前提之一：分幅只切行不切列，行集合=全批（TLSEGMENT §三案 A 跨段合并语义
    「无需合并」的离散化形式——每 tile 行集不相交并集=全批）。
    """
    if rows <= 0:
        return []
    step = max(1, min(int(rows_per_tile), rows))
    return [slice(off, min(off + step, rows)) for off in range(0, rows, step)]


def segment_width(context_lengths: Sequence[int]) -> int:
    """宽度律=ceil_align(max(lens),4)（index_logits.py:54；scoring.py:220 传 4）。"""
    return _ceil_align(max(context_lengths, default=0), WIDTH_ALIGN)


# ───────────────────────── 分幅打分（生成器，kernel 可注入） ─────────────────────────

def _num_rows(q0) -> int:
    """torch 张量（.shape[0]）与嵌套 list（len）双载体的行数面。"""
    shape = getattr(q0, "shape", None)
    return int(shape[0]) if shape is not None else len(q0)


def _elem_add(a, b):
    """逐元素加：torch 张量=+；嵌套 list=zip 逐元（离线等价构造面）。"""
    if isinstance(a, list) and isinstance(b, list):
        return [x + y for x, y in zip(a, b)]
    return a + b


def segmented_logits(
    *,
    q: tuple,
    kv: tuple,
    weights,
    starts,
    lengths,
    context_lengths: Sequence[int],
    heads: int,
    budget_bytes: int,
    logits_fn: Callable,
) -> Iterator[tuple]:
    """flat_index_logits_tiles 的分段镜像（index_logits.py:36-74 语义逐点同构）。

    每 tile 调同一 kernel（logits_fn，在役=deep_gemm.fp8_fp4_mqa_logits；M 形=该
    tile 行数），yield (slice, logits)；width 全批同源（segment_width）⇒ 每 tile 的
    kernel 调用与 stock 全批 tile 同 width 同 starts/ends 语义，唯一自由变量=M
    （A23RESTART §1.2）。引擎路径不拼装——tile 直接喂 per-row topk（scoring.py:
    221-226，行独立无跨行归约=topk.py:185-223）⇒ 下游零改；assemble_logits 仅
    E1/对拍面使用。
    """
    rows = _num_rows(q[0])
    width = segment_width(context_lengths)
    if rows == 0 or width == 0:
        return
    step = rows_per_tile(rows, width, heads, budget_bytes)
    for tile in tile_slices(rows, step):
        tile_starts = starts[tile]
        yield (
            tile,
            logits_fn(
                (q[0][tile], q[1][tile]),
                kv,
                weights[tile],
                tile_starts,
                _elem_add(tile_starts, lengths[tile]),
                False,
                width,
            ),
        )


def assemble_logits(tiles: Iterator[tuple], rows: int, width: int, factory: Callable):
    """分幅拼装回全批 logits 视图（E1「分幅拼装=全批」判定的载具）。

    factory(rows,width)→空阵；tile 写入各自行段；行集恰切分割（tile_slices）⇒
    每行恰被写一次。引擎在役路径**不调用本函数**（下游流式 topk 零改）。
    """
    out = factory(rows, width)
    seen = 0
    for tile, logits in tiles:
        out[tile] = logits
        seen += tile.stop - tile.start
    if seen != rows:
        raise AssertionError(f"tile partition cover {seen} != rows {rows}")
    return out


# ───────────────────────── 参考后端（M-不变 by construction；仅测试面） ─────────────────────────

def reference_logits_factory(seed: int = 20261006):
    """纯 Python M-不变参考 kernel（离线 E1 用；float 精度=IEEE double）。

    logits[i][j] = Σ_h w[i][h]·⟨q[i][h], k[starts[i]+j]⟩（窗口内）；窗口外=确定性
    垫值 f(i,j)（仿真「garbage past lengths」且可判 mask 错位）。逐行独立计算⇒
    输出只依赖行自身输入与全局 starts/ends，与调用 M 形无关=H-B 形式化。
    """
    state = seed & 0xFFFFFFFF

    def rand():
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    def backend(q_pair, kv, weights, starts, ends, _flag, width):
        q0 = q_pair[0]                          # [rows, heads, dim] 嵌套 list
        keys = kv[0]                            # [cols, dim] 嵌套 list
        rows = len(q0)
        out = [[0.0] * width for _ in range(rows)]
        for i in range(rows):
            s = int(starts[i])
            e = int(ends[i])
            for j in range(width):
                col = s + j
                if col < e:
                    acc = 0.0
                    for h in range(len(q0[i])):
                        d = q0[i][h]
                        kcol = keys[col]
                        acc += weights[i][h] * sum(d[t] * kcol[t] for t in range(len(d)))
                    out[i][j] = acc
                else:
                    out[i][j] = float((i * 1000003 + j * 99991) % 977) - 488.5
        return out

    def make_qkv(rows, heads, dim, cols):
        q0 = [[[rand() for _ in range(dim)] for _ in range(heads)] for _ in range(rows)]
        q1 = [[0] * heads for _ in range(rows)]                        # sf 占位（参考面不消费）
        keys = [[rand() for _ in range(dim)] for _ in range(cols)]
        wts = [[rand() for _ in range(heads)] for _ in range(rows)]
        return (q0, q1), (keys,), wts

    return backend, make_qkv


# ───────────────────────── 键控 install 面（sitecustomize 式挂点） ─────────────────────────

def _env_raw(name: str) -> Optional[str]:
    v = os.environ.get(name)
    return None if v is None else v.strip()


def segment_enabled() -> bool:
    v = _env_raw(SEGMENT_ENV)
    return v is not None and v.lower() in _ON


def _parse_bytes(name: str, default: int) -> Tuple[bool, Optional[int]]:
    """(ok, value)；off/0/坏值=(False, None)——拒绝武装，不静默回缺省（FC4/FC6）。"""
    raw = _env_raw(name)
    if raw is None or not raw:
        return True, default
    low = raw.lower()
    if low in _OFF:
        return False, None
    try:
        v = int(float(low))
    except ValueError:
        return False, None
    return (v > 0), v


def grid_form() -> str:
    raw = (_env_raw(GRID_ENV) or GRID_DERATE).lower()
    return raw


def effective_tile_budget() -> Tuple[bool, Optional[int], str]:
    """(ok, budget, grid)；grid=stock ⇒ budget=stock 2GiB（A/B 位等对拍形，不降额）。"""
    ok_grid, grid = True, grid_form()
    if grid not in (GRID_DERATE, GRID_STOCK):
        return False, None, grid
    if grid == GRID_STOCK:
        return True, STOCK_TILE_BUDGET, grid
    ok, budget = _parse_bytes(TILE_BYTES_ENV, DEFAULT_TILE_BUDGET)
    return ok, budget, grid


def segment_engaged() -> bool:
    """形式探针（admission_segment FC2 面）：分段形 ENGAGED=本件已 install 且
    budget 锚定在场。探针本身零 import 重件、零引擎接触。"""
    return bool(_STATE["installed"])


def segment_state() -> str:
    if not segment_enabled():
        return f"gate={SEGMENT_ENV}=(off; zero-load)"
    b = _STATE["budget"]
    return (f"gate={SEGMENT_ENV} grid={_STATE['grid']} "
            f"tile_budget={'?' if b is None else format(b, ',')} "
            f"engaged={segment_engaged()}")


def install(scoring_module, torch_budget_floor: int = 64 << 20) -> bool:
    """键控 install：true=分段形武装；false=零行为（键关/FC 拒绝/锚缺）。

    patch 面=模块属性二常量（scoring._DEEP_GEMM_SCORE_BUDGET_BYTES /
    _TORCH_SCORE_BUDGET_BYTES），sparse_wire.install_scoring 同法同值（128MiB
    幂等收编其 always-on 形；adapter 缺位时兜底自 stock 2GiB 降额到同值）。
    grid=stock 形把二常量钉回 stock 值（=对拍形，行为与不装逐位同、仅横幅差）。
    """
    if not segment_enabled():
        return False                      # FC1 键关=零加载零漂移
    ok, budget, grid = effective_tile_budget()
    if not ok:
        reason = (f"grid={grid!r} invalid" if grid not in (GRID_DERATE, GRID_STOCK)
                  else f"{TILE_BYTES_ENV}={_env_raw(TILE_BYTES_ENV)!r} off/0/unparseable")
        _logger.warning("tl_segment: REFUSED (%s; stock intact)", reason)
        return False                      # FC4/FC6 坏值拒绝武装
    if budget is None:
        return False                      # 不可达（effective 已滤 off/0）；双保险
    dg = getattr(scoring_module, "_DEEP_GEMM_SCORE_BUDGET_BYTES", None)
    tw = getattr(scoring_module, "_TORCH_SCORE_BUDGET_BYTES", None)
    if dg is None and tw is None:
        _logger.warning("tl_segment: scoring budget anchors missing; REFUSED "
                        "(stock intact)")
        return False                      # 锚缺=拒绝（不盲装）
    patches = {}
    if dg is not None:
        patches["_DEEP_GEMM_SCORE_BUDGET_BYTES"] = (dg, budget)
        scoring_module._DEEP_GEMM_SCORE_BUDGET_BYTES = budget
    if tw is not None:
        patches["_TORCH_SCORE_BUDGET_BYTES"] = (tw, max(budget, torch_budget_floor))
        scoring_module._TORCH_SCORE_BUDGET_BYTES = max(budget, torch_budget_floor)
    _STATE.update(installed=True, budget=budget, grid=grid, patches=patches,
                  module=scoring_module)
    _logger.info(
        "tl_segment: SEGMENT FORM ARMED (grid=%s, tile budget=%s; "
        "deep_gemm %s->%s, torch %s->%s; rows/tile@width150k,h32=%d; "
        "%s=off/unset disables the segment form)",
        grid, format(budget, ","),
        format(dg, ","), format(budget, ","),
        format(tw, ","), format(patches.get("_TORCH_SCORE_BUDGET_BYTES",
                                            (None, tw))[1], ","),
        rows_per_tile(999999, 150016, 32, budget),
        SEGMENT_ENV,
    )
    return True


def uninstall() -> bool:
    """回退 patch（测试面；部署侧回退=键关重启，patch 不落地）。"""
    mod = _STATE.get("module")
    if not _STATE["installed"] or mod is None:
        return False
    for attr, (orig, _cur) in _STATE["patches"].items():
        setattr(mod, attr, orig)
    _STATE.update(installed=False, budget=None, grid=None, patches=None, module=None)
    return True


# ───────────────────────── kernel 级 first-call bit-identical 探针（O13 窗） ─────────────────────────

def kernel_probe(inputs: dict) -> dict:
    """E1 kernel 级一锤（在役首调；本机零 GPU 不可跑=设计稿+函数体在场）。

    输入 fixtures（O13 窗在役构取，构造面=引擎同源）：
      q      = (q_fp4[rows,heads,64] int8, q_sf[rows,heads] int32)   # 任意位型合法
      kv     = get_low_ratio_index_k_fp4 产物（full_topk.py:73 同源）
      weights= [rows,heads] fp32；starts/lengths=int32；context_lengths=list
    判据（预登记，零事后改）：
      full = flat_index_logits_tiles(budget=STOCK)   ⇒ 单 tile，M=rows（或 stock M）
      seg  = flat_index_logits_tiles(budget=128MiB)  ⇒ 多 tile，M=derate M
      逐位 torch.equal(full_logits, assemble(seg)) ⇒ H-B（M-不变，derate 直装位等）
      否则 H-A（M 形可位移数值：derate 形=T17 建锚自洽+A/B 走 grid=stock 形）
    任何 shape/签名漂移=fail-loud 异常（不静默降级）。
    """
    import torch  # 探针面才 import 重件

    from sglang.kernels.ops.attention.dsv4.index_logits import flat_index_logits_tiles

    q, kv, weights = inputs["q"], inputs["kv"], inputs["weights"]
    starts, lengths = inputs["starts"], inputs["lengths"]
    context_lengths = inputs["context_lengths"]
    heads = q[0].shape[1]
    rows = q[0].shape[0]
    width = segment_width(context_lengths)

    def run(budget):
        tiles = flat_index_logits_tiles(
            q=q, kv=kv, weights=weights, starts=starts, lengths=lengths,
            context_lengths=context_lengths, budget_bytes=budget,
        )
        return assemble_logits(tiles, rows, width,
                               lambda r, w: torch.empty((r, w), dtype=torch.float32,
                                                        device=q[0].device))

    full = run(STOCK_TILE_BUDGET)
    seg = run(DEFAULT_TILE_BUDGET)
    bit_equal = bool(torch.equal(full, seg))
    return {
        "rows": rows, "width": width, "heads": heads,
        "stock_rows_per_tile": rows_per_tile(rows, width, heads, STOCK_TILE_BUDGET),
        "derate_rows_per_tile": rows_per_tile(rows, width, heads, DEFAULT_TILE_BUDGET),
        "bit_equal": bit_equal,
        "verdict": "H-B (M-invariant; derate form bitwise-equal, install as-is)"
        if bit_equal else
        "H-A (M-form shifts numerics; derate=per-boot single M-form + fresh "
        "anchor, A/B pair must use grid=stock form)",
        "max_absdiff": float((full - seg).abs().max()) if not bit_equal else 0.0,
    }
