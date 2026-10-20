"""R1 torch 参考实现：候选内 gather + 局部打分（DenseBlocks 消费面的论文 reindex 合同）。

本文件是**正确性金标准**，不是性能路径：纯 torch、无 sglang 依赖、任意设备（含 CPU）可跑，
供 unit_xcheck.py 对拍与未来 sm12x sparse 内核（R2 / deep_gemm `fp8_fp4_paged_sparse_mqa_logits`）
落地后的数值基准。

== SM100 sparse_logits 语义对齐说明 =========================================
现网「局部计算」正身 = `sglang/kernels/ops/attention/dsv4/index_logits.py:104-126 sparse_logits()`
（deep_gemm fp8_fp4_paged_sparse_mqa_logits，SM100 专属，GB10/SM121 不可达——V4 报告 Q2b/Q4）。
其输出合同：logits ``[rows, topk_blocks * 8]``，候选块背靠背布局（块 j 占列 8j..8j+7）。
本模块 ``gathered_decode_logits`` 同宽同布局，因此**在无 SM100 的机器上，本参考实现即
sparse_logits 的金标准替身**；R2 内核落地后对拍靶翻转（VERIFICATION.md 判别①第三层）。

数值差异声明：SM100 核是 fp8(q)×fp4(k) tcgen05 路径、出 bf16；本参考与现网 Triton 全量打分器
（`fp4_indexer.py:434 _fp4_index_logits_kernel`）同族：fp4 e2m1 反量化 × ue8m0 块标 → bf16 →
fp32 累加 dot → bf16 → relu → ×bf16 头权 → bf16 → 头求和 → bf16。R1 相对**现网消费面**的目标是
候选位置上逐位相等（少算，不改数）；相对 SM100 sparse_logits 只承诺同族近似（容差对拍）。

== 逐位相等的三层口径（VERIFICATION.md 判别①） ==============================
1. torch 参考内部：``full_scan_decode_logits`` vs ``gathered_decode_logits`` —— 同一实现、
   同一逐位置算术 → 候选位置上 **bitwise 相等**（本模块保证）。
2. torch 参考 vs 现网 Triton 全量打分器（有 GPU 处）：逐位置算术链相同，但 fp32 求和次序
   （torch reduction vs tl.dot 树）可能差最后一位 → 容差对拍（atol=2e-2 相对量级，经验值，
   靴上校准）。
3. Triton gather 内核 vs Triton 全量内核：同形 tl.dot（K 维=64 不分块、同 operand 形状）→
   逐位置 bitwise 相等；调优若改 K 分块则降级为容差（triton_kernel.py 头注释同款声明）。

== 记号 =====================================================================
- ``blocks``：publish 发布的 int32 块表 ``[rows, n]``（n ≤ topk_blocks=2048，-1 填充），
  块 b 覆盖压缩位置 ``8b .. 8b+7``（candidate_block_size=8）。
- ``slots``：索引 K 池槽号（池页 page_size=64，槽宽 68B = 64 payload + 4 ue8m0 标度字节）。
- ``lens``：每行可见压缩长度（c1 消费层 ratio=1 时 = 位置数）。
- 打分宽度 C = 8n ≤ 16384：**与 ctx 无关的常数**（DESIGN.md 数学账）。
"""

from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn.functional as F

__all__ = [
    "CANDIDATE_BLOCK_SIZE",
    "read_index_k_payload",
    "dequant_index_k",
    "index_logits_from_k",
    "full_scan_decode_logits",
    "candidate_positions",
    "candidate_slots",
    "gathered_decode_logits",
    "topk_among_blocks_torch",
    "topk_among_candidates",
    "topk_among_candidates_cols",
    "consume_decode_dense_reference",
    "consume_decode_gather",
    "consume_prefill_gather",
]

CANDIDATE_BLOCK_SIZE = 8  # config.json candidate_block_size；论文 2048 块 × 8 位池

# e2m1 (NVFP4 载荷) 16 个码点值：exp=bits2..1，man=bit0，sign=bit3。
_E2M1 = torch.tensor(
    [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, -0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]
)


def _bf16(x: torch.Tensor) -> torch.Tensor:
    """内核舍入链的 bf16 检查点（值以 bf16 表示后回 fp32 参与下一步）。"""
    return x.to(torch.bfloat16).to(torch.float32)


# ─────────────────────────── 池读取与反量化 ─────────────────────────────────


def read_index_k_payload(
    table: torch.Tensor, slots: torch.Tensor, page_size: int
) -> Tuple[torch.Tensor, torch.Tensor]:
    """按槽读 fp4 索引 K 的原始字节。

    ``table`` = 池的 2D uint8 视图 ``[pages, page_size*64 + page_size*4]``
    （= ``get_index_k_with_scale_buffer`` 的返回布局，``scoring.py:404``）；
    ``slots`` int64 任意形状。返回 ``(payload uint8 [*, 64], scale_bytes uint8 [*, 4])``，
    与 Triton 内核的寻址式逐字节同源（``fp4_indexer.py:479-500``）：
    ``page = slot // page_size``，``off = slot % page_size``，
    payload 字节 i 在 ``row_base + off*64 + i``，标度字节 s 在
    ``row_base + page_size*64 + off*4 + s``（元素 j 用块 ``j // 16`` 的标度）。
    ``slot < 0``（无效候选哨兵）读 0 页 0 槽——值被调用方掩蔽，不参与结果。
    """
    assert table.dtype == torch.uint8 and table.dim() == 2
    flat = table.reshape(-1)
    row_base = (slots // page_size) * table.stride(0)
    off = slots % page_size
    payload = flat[
        (row_base[..., None] + off[..., None] * 64 + torch.arange(64, device=slots.device))
    ]
    scales = flat[
        (
            row_base[..., None]
            + page_size * 64
            + off[..., None] * 4
            + torch.arange(4, device=slots.device)
        )
    ]
    return payload, scales


def dequant_index_k(
    payload: torch.Tensor, scale_bytes: torch.Tensor
) -> Tuple[torch.Tensor, torch.Tensor]:
    """fp4 字节 → bf16 K：``k_even[i] = e2m1(low_nibble)*2^(sc[i//16]-127)``（奇偶同式）。

    返回 ``(k_even, k_odd)`` bf16 ``[*, 64]``，对应 K 行的偶/奇元素（字节 i 存 2i/2i+1）。
    与内核 :488-503 同链：decode → ×scale → bf16。
    """
    e2m1 = _E2M1.to(payload.device)
    low = e2m1[(payload & 0x0F).long()]
    high = e2m1[(payload >> 4).long()]
    # 元素 j 的标度字节 = j//16（块标度）；gather 索引须与输入同维 → expand 到 [*, 64]。
    sc_idx = torch.arange(payload.shape[-1], device=payload.device) // 16
    sc = scale_bytes.gather(-1, sc_idx.expand(payload.shape[:-1] + (-1,)))
    scale = torch.exp2(sc.float() - 127.0)
    return (low * scale).to(torch.bfloat16), (high * scale).to(torch.bfloat16)


# ─────────────────────────── 打分（论文 s(q, k)） ───────────────────────────


def index_logits_from_k(
    q: torch.Tensor, weights: torch.Tensor, k_even: torch.Tensor, k_odd: torch.Tensor
) -> torch.Tensor:
    """一行查询对一组 K 行的打分，舍入链逐算子复刻 ``_fp4_index_logits_kernel:517-524``：
    ``dot(bf16,bf16)→fp32`` 累加（K=64 不分块）→ bf16 → relu → ×bf16 头权 → bf16 →
    头求和(f32) → bf16。``q`` ``[B, H, 128]`` bf16；``weights`` ``[B, H]``；
    K ``[C, 64]``×2（B 行共享同一组 C 候选）。出 fp32 ``[B, C]``。

    注：torch 的 fp32 规约次序与 tl.dot 树不同 → 跨实现对拍用容差（见模块 docstring 第 2 层）。
    """
    q_even = q[..., 0::2].float()  # [B, H, 64]
    q_odd = q[..., 1::2].float()
    acc = q_even @ k_even.float().transpose(-1, -2)  # [B, H, C]
    acc = acc + q_odd @ k_odd.float().transpose(-1, -2)
    s = _bf16(acc)
    s = torch.relu(s)
    w = weights.to(torch.bfloat16).float()  # [B, H]（内核加载 bf16 后转 f32）
    s = _bf16(s * w[:, :, None])
    return _bf16(s.sum(dim=1))  # [B, C]


def _row_batched_logits(
    q: torch.Tensor, weights: torch.Tensor, k_even: torch.Tensor, k_odd: torch.Tensor
) -> torch.Tensor:
    """每行各自的一组 K：``q`` [B, H, 128]，K [B, W, 64]×2 → fp32 [B, W]。

    舍入链与 :func:`index_logits_from_k` 逐算子同式（逐输出元素的数学与归约维
    不变：K 维=64）——full_scan 与 gathered 两个入口共用本函数，故「候选位置
    logits bitwise 相等」的判据在同一实现内部仍然成立（遍历无关性）。
    容器冒烟 p1 实跑发现并修复：flatten 成 [B*W, 64] 喂单行版会把不同行的 K 串
    到同一查询上（形状崩或错值）。
    """
    q_even = q[..., 0::2].float()                       # [B, H, 64]
    q_odd = q[..., 1::2].float()
    acc = q_even @ k_even.float().transpose(-1, -2)     # [B, H, W]
    acc = acc + q_odd @ k_odd.float().transpose(-1, -2)
    s = _bf16(acc)
    s = torch.relu(s)
    w = weights.to(torch.bfloat16).float()              # [B, H]
    s = _bf16(s * w[:, :, None])
    return _bf16(s.sum(dim=1))                          # [B, W]


def full_scan_decode_logits(
    q: torch.Tensor,
    weights: torch.Tensor,
    slots: torch.Tensor,
    lens: torch.Tensor,
    table: torch.Tensor,
    page_size: int,
) -> torch.Tensor:
    """现网 ``fp4_index_logits_decode``（全量 T×L 打分器）的 torch 镜像，对拍基线。

    ``q`` ``[B, H, 128]`` bf16、``slots`` ``[B, L]`` int64（``decode_scores:365`` 的全量槽表）、
    ``lens`` ``[B]``。返回 fp32 ``[B, L]``，``-inf`` 于 ``lens`` 之外——与内核输出合同一致。
    """
    B, L = slots.shape
    payload, scales = read_index_k_payload(table, slots.reshape(-1), page_size)
    k_even, k_odd = dequant_index_k(payload, scales)
    out = _row_batched_logits(q, weights, k_even.view(B, L, 64),
                              k_odd.view(B, L, 64))
    j = torch.arange(L, device=q.device)
    return out.masked_fill(j[None, :] >= lens[:, None], float("-inf"))


# ─────────────────────────── 候选面（gather） ───────────────────────────────


def candidate_positions(
    blocks: torch.Tensor, lens: torch.Tensor, block_size: int = CANDIDATE_BLOCK_SIZE
) -> torch.Tensor:
    """块表 → 候选位置矩阵 ``[rows, 8n]`` int64：块 j 展开为 ``8j'..8j'+7``（j'=blocks[:,j]），
    无效（块 -1 或位置 ≥ lens）为 -1。即论文候选池 C(b) 的稠密表示（DESIGN.md §3）。"""
    rows, n = blocks.shape
    b64 = blocks.to(torch.int64)
    t = torch.arange(block_size, device=blocks.device)
    pos = b64[:, :, None] * block_size + t[None, None, :]  # [rows, n, bs]
    valid = (b64[:, :, None] >= 0) & (pos < lens[:, None, None])
    return pos.masked_fill(~valid, -1).reshape(rows, n * block_size)


def candidate_slots(
    blocks: torch.Tensor,
    lens: torch.Tensor,
    req_rows: torch.Tensor,
    req_to_token: torch.Tensor,
    ratio: int,
    block_size: int = CANDIDATE_BLOCK_SIZE,
) -> torch.Tensor:
    """候选位置 → 池槽：``slot = req_to_token[req, pos*ratio] // ratio``
    （``decode_scores:365`` 的逐行查表，只做 ≤16,384 次/行而非 lmax 次）。无效候选槽=-1。"""
    pos = candidate_positions(blocks, lens, block_size)
    safe = pos.clamp_min(0)
    slots = req_to_token[req_rows[:, None], safe * ratio].to(torch.int64) // ratio
    return slots.masked_fill(pos < 0, -1)


def gathered_decode_logits(
    q: torch.Tensor,
    weights: torch.Tensor,
    cand_slots: torch.Tensor,
    table: torch.Tensor,
    page_size: int,
) -> torch.Tensor:
    """**R1 核心**：只对候选槽打分。``cand_slots`` ``[B, 8n]`` int64（-1 哨兵）。
    返回 fp32 ``[B, 8n]``（-inf 于哨兵处）——SM100 ``sparse_logits`` 的 ``[rows, topk_blocks*8]``
    块背靠背布局（模块 docstring 对齐声明）。宽度与 ctx 无关。"""
    B, C = cand_slots.shape
    payload, scales = read_index_k_payload(table, cand_slots.reshape(-1), page_size)
    k_even, k_odd = dequant_index_k(payload, scales)
    out = _row_batched_logits(q, weights, k_even.view(B, C, 64),
                              k_odd.view(B, C, 64))
    return out.masked_fill(cand_slots < 0, float("-inf"))


# ─────────────────────────── 选点与消费面 ───────────────────────────────────


def topk_among_blocks_torch(
    scores: torch.Tensor,
    lens: torch.Tensor,
    blocks: torch.Tensor,
    k: int,
    block_size: int = CANDIDATE_BLOCK_SIZE,
) -> torch.Tensor:
    """``candidate_blocks.py:169-206 topk_among_blocks`` 的本仓 torch 镜像（免 sglang 依赖），
    供 dense 参考消费面对拍；语义逐行同源（含 -1 填充与 newest-block 语义由调用方 scores 保证）。"""
    rows, width = scores.shape
    n = blocks.shape[1]
    if width == 0 or n == 0:
        return torch.full((rows, k), -1, dtype=torch.int64, device=scores.device)
    if width % block_size:
        scores = F.pad(scores, (0, -width % block_size), value=-torch.inf)
    num_blocks = scores.shape[1] // block_size
    by_block = scores.unflatten(1, (num_blocks, block_size))
    blocks64 = blocks.to(torch.int64)
    ids = blocks64.clamp(0, num_blocks - 1)
    candidates = by_block.gather(1, ids[:, :, None].expand(rows, n, block_size))
    offsets = torch.arange(block_size, device=scores.device, dtype=lens.dtype)
    room = lens[:, None] - blocks64 * block_size
    drop = (offsets[None, None, :] >= room[:, :, None]) | (blocks64 < 0)[:, :, None]
    candidates = candidates.masked_fill(drop, -torch.inf)
    flat = candidates.flatten(1)
    top = flat.topk(min(k, flat.shape[1]), dim=-1, sorted=False)
    block_of_pick = top.indices // block_size
    picked = blocks64.gather(1, block_of_pick) * block_size + (
        top.indices - block_of_pick * block_size
    )
    picked = picked.masked_fill(top.values == -torch.inf, -1)
    if picked.shape[1] < k:
        picked = F.pad(picked, (0, k - picked.shape[1]), value=-1)
    return picked


def topk_among_candidates_cols(
    cand_logits: torch.Tensor,
    cand_positions: torch.Tensor,
    k: int,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """``topk_among_candidates`` 的列追踪版：额外返回每个选点所在的候选列号。

    R1-FIX capture-safe 基元（R1STDFORM-NOGO-ADJUDICATION-20261003 §二.1 落选路 (c)
    的实现载体）：写回槽可按**同一 ``top.indices`` 张量**直接从候选槽表按列 gather——
    位置↔槽的配对由共享索引张量在**执行时刻**建立（CUDA 图 replay 读 replay 时刻
    buffer：topk/argsort 在 replay 期对 replay 时刻数据重算，配对随之重建，不依赖
    捕获期数据），从而免去 ``nonzero``+位置槽表散射（数据依赖同步算子，输出形状
    随数据定形，decode CUDA graph capture 路径结构性禁用——2026-10-03 四机同靴
    同错根因）。等价性：行内活候选位置互异 ⇒ 位置↔列单射，列槽 = 位置槽。
    """
    top = cand_logits.topk(min(k, cand_logits.shape[1]), dim=-1, sorted=False)
    picked = cand_positions.gather(1, top.indices)
    return picked.masked_fill(top.values == -torch.inf, -1), top.indices


def topk_among_candidates(
    cand_logits: torch.Tensor,
    cand_positions: torch.Tensor,
    k: int,
) -> torch.Tensor:
    """gather 面选点：``cand_logits`` ``[B, 8n]``（-inf 无效），直接在候选列上取 top-k 并重建
    压缩位置（列 c ↔ 位置 ``cand_positions[:, c]``）。与 ``topk_among_blocks`` 在同一值集上选点
    → 集合相等（平局次序差异见 VERIFICATION.md 判别①注记）。出 int64 ``[B, k]``，-1 填充。"""
    picked, _cols = topk_among_candidates_cols(cand_logits, cand_positions, k)
    return picked


def _slot_by_position(
    cand_pos: torch.Tensor, cand_slot: torch.Tensor, lmax: int
) -> torch.Tensor:
    """候选列 → 位置索引槽表 ``[B, lmax]``（位置 p 的槽；非候选位填 0——调用方
    reach/-1 合同会掩蔽它们）。

    写回合同（write_decode）按**位置升序** gather 槽，因此 gather 面必须先把
    「候选列槽」散射成「位置索引槽」——直接拿 cand_slot 按位置序 gather 是列/位
    混用（容器冒烟 p1 层 2 page_indices 判据抓出的真 bug，2026-10-03 修复）。
    """
    rows = cand_pos.shape[0]
    out = torch.zeros((rows, lmax), dtype=cand_slot.dtype, device=cand_pos.device)
    live = cand_pos >= 0
    b_idx, c_idx = live.nonzero(as_tuple=True)
    # 高级索引赋值：每行候选位置互异 ⇒ (行,位置) 键唯一，确定性（scatter_ 对
    # 重复索引不保证序，死列钳 0 位会与活候选 0 位竞争）。
    out[b_idx, cand_pos[b_idx, c_idx]] = cand_slot[b_idx, c_idx]
    return out


def _write_like_write_decode(
    picked: torch.Tensor,
    cand_slots: torch.Tensor,
    lens: torch.Tensor,
    lmax: int,
) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
    """``scoring.py:465-471 write_decode`` 的合同：-1→lmax → 按位置升序 → reach=位置<lens →
    page_indices=槽（否则 -1）、raw_indices=位置（否则 -1）。"""
    posx = picked.masked_fill(picked < 0, lmax)
    order = posx.argsort(dim=-1)
    pos_s = posx.gather(1, order)
    slot_s = cand_slots.gather(1, order).clamp_min(0)
    reach = pos_s < lens[:, None]
    page_indices = torch.where(reach, slot_s, torch.full_like(slot_s, -1)).to(torch.int32)
    raw_indices = torch.where(reach, pos_s, torch.full_like(pos_s, -1)).to(torch.int32)
    return page_indices, raw_indices


def consume_decode_dense_reference(
    q: torch.Tensor,
    weights: torch.Tensor,
    slots_full: torch.Tensor,
    lens: torch.Tensor,
    table: torch.Tensor,
    page_size: int,
    blocks: torch.Tensor,
    k: int,
    block_size: int = CANDIDATE_BLOCK_SIZE,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """现网 ``DenseBlocksBackend.consume_decode`` 的端到端 torch 镜像（全量打分 +
    ``topk_among_blocks``），对拍的 dense 侧。返回 ``(scores_full, page_indices, raw_indices)``。"""
    scores = full_scan_decode_logits(q, weights, slots_full, lens, table, page_size)
    picked = topk_among_blocks_torch(scores, lens, blocks, k, block_size)
    lmax = slots_full.shape[1]
    # write_decode 用全量槽表 gather；此处按 picked 位置查槽（同值同源）。
    safe = picked.clamp(0, lmax - 1)
    slot_of_pos = slots_full.gather(1, safe)
    page_indices, raw_indices = _write_like_write_decode(picked, slot_of_pos, lens, lmax)
    return scores, page_indices, raw_indices


def consume_decode_gather(
    q: torch.Tensor,
    weights: torch.Tensor,
    blocks: torch.Tensor,
    lens: torch.Tensor,
    req_rows: torch.Tensor,
    req_to_token: torch.Tensor,
    ratio: int,
    table: torch.Tensor,
    page_size: int,
    k: int,
    block_size: int = CANDIDATE_BLOCK_SIZE,
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """R1 消费面（torch 档）：gather + 候选内打分 + 候选内 top-k + 同合同写回。
    与 ``consume_decode_dense_reference`` 的等价契约（unit_xcheck 判据）：
    ① ``scores_full[b, pos] == cand_logits[b, c]``（pos=候选重建位置，bitwise）；
    ② ``(page_indices, raw_indices)`` 逐元素相等（k 个选点含 -1 填充）。"""
    cand_pos = candidate_positions(blocks, lens, block_size)
    cand_slot = candidate_slots(blocks, lens, req_rows, req_to_token, ratio, block_size)
    cand_logits = gathered_decode_logits(q, weights, cand_slot, table, page_size)
    picked = topk_among_candidates(cand_logits, cand_pos, k)
    lmax = int(lens.max().item()) if lens.numel() else 0
    # 写回合同要「每选点槽 [B,k]」（_write_like_write_decode 按 order=列置换 gather）：
    # 候选列槽先散成位置槽表，再按 picked 位置取每选点槽。
    slot_by_pos = _slot_by_position(cand_pos, cand_slot, max(lmax, 1))
    per_pick = slot_by_pos.gather(1, picked.clamp_min(0).clamp_max(max(lmax, 1) - 1))
    page_indices, raw_indices = _write_like_write_decode(picked, per_pick, lens, lmax)
    return cand_logits, page_indices, raw_indices


def consume_prefill_gather(
    q: torch.Tensor,
    weights: torch.Tensor,
    blocks_rows: torch.Tensor,
    lens_rows: torch.Tensor,
    req_rows: torch.Tensor,
    req_to_token: torch.Tensor,
    ratio: int,
    table: torch.Tensor,
    page_size: int,
    k: int,
    block_size: int = CANDIDATE_BLOCK_SIZE,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """prefill 消费面（torch 档，第二段面）：每查询行只对候选位置打分（宽度 8n 常数），
    替代 ``_torch_consume_prefill`` 的全宽 ``indexer.scores``。返回 ``(raw_positions, page_slots)``
    int32 ``[rows, k]``（-1 填充，未排序——调用方按 ``write_prefill`` 合同排序/映射）。"""
    cand_pos = candidate_positions(blocks_rows, lens_rows, block_size)
    cand_slot = candidate_slots(blocks_rows, lens_rows, req_rows, req_to_token, ratio, block_size)
    cand_logits = gathered_decode_logits(q, weights, cand_slot, table, page_size)
    picked = topk_among_candidates(cand_logits, cand_pos, k)
    lmax = int(lens_rows.max().item()) if lens_rows.numel() else 0
    slot_by_pos = _slot_by_position(cand_pos, cand_slot, max(lmax, 1))
    safe = picked.clamp_min(0)
    slot_of_pos = slot_by_pos.gather(1, safe)
    reach = picked >= 0
    page = torch.where(reach, slot_of_pos, torch.full_like(slot_of_pos, -1)).to(torch.int32)
    raw = torch.where(reach, picked, torch.full_like(picked, -1)).to(torch.int32)
    return raw, page
