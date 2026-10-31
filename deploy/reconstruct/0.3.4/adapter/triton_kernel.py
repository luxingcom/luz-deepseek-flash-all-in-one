"""R1 Triton 内核：`_fp4_gather_index_logits_kernel`（候选内 gather + 局部打分）。

== 发射宽度目标（census 判别锚，见 VERIFICATION.md 判别②）==================
现网全量打分器 `_fp4_index_logits_kernel` 的发射宽度 = lmax（grid dim1 =
cdiv(lmax, BLOCK_L)，随 ctx 线性增长）。本内核的发射宽度 = **C = topk_blocks *
block_size = 2048 * 8 = 16384（常数，与 ctx 无关）**：生产参数下 grid =
(rows, cdiv(16384, BLOCK_C))，BLOCK_C=64 时 dim1=256。

census 判别形态（~/l10-quality/r12/*.json raw_rows 三元组 {name, ms_per_step,
calls_per_step}）：
  ENGAGED  = 出现本名 `_fp4_gather_index_logits_kernel`（calls_per_step ≈ 4.0
             = 消费层 24/28/32/36 各一次/解码步）且 `_fp4_index_logits_kernel` 的
             calls_per_step 从 5.0（1 publish + 4 consume，A0S-base-spec1 实测）降到 ≈1.0
             （仅 publish 存活）。
  NOT-ENGAGED = 新名缺席且旧名仍 5.0/步（键关/锚缺/回退）。
宽度律旁证：本核 us_avg 不随 ctx 档增长（常数宽度）；存活的 publish 旧核 us_avg 随 ctx 增长
——两者的 ctx 斜率分离即为「发射宽度从 lmax 降到 16384」的直接证据。

== 数值口径 =================================================================
逐位置算术与 `_fp4_index_logits_kernel`（fp4_indexer.py:434-527）逐算子同链：
fp4 e2m1 反量化 × ue8m0 块标 → bf16 → tl.dot(bf16,bf16)→fp32（K 维 = HALF_D = 64，
不分块）→ bf16 → relu → ×bf16 头权 → bf16 → 头求和 → bf16。同形 tl.dot + 确定性内核
⇒ 候选位置上的 logit 与全量内核 **bitwise 相等**（R1 不改数，只是少算）。
性能调优若改变 K 分块/累加形状，此口径降级为容差对拍（VERIFICATION.md 判别①第 3 层）。

== 骨架范围（本段）=========================================================
结构 + 边界断言齐；性能调优留待靴上（_TUNING_TODO）。本文件在无 triton 的开发机上
只过 py_compile/AST 断言（不执行 import）；有 GPU 处由 unit_xcheck.py 第 4 节
（TORCH_GATHER_XCHECK=1）做 gather-vs-全量 内核对拍。
"""

from __future__ import annotations

import torch
import triton
import triton.language as tl

__all__ = ["gather_index_logits_decode", "_fp4_gather_index_logits_kernel"]

# _TUNING_TODO（靴上，非本段）：
#  1. BLOCK_C ∈ {64, 128, 256} 扫描（16384 宽 → 256/128/64 个 tile）；num_warps ∈ {4, 8}。
#  2. 槽查表内联：把 candidate_slots prologue（req_to_token gather）折进内核，省一次
#     [rows, C] int64 物化与发射（当前 prologue 与全量路径同型，利于对拍；上线后内联）。
#  3. PDL（launch_pdl）如 is_arch_support_pdl()——与 _candidate_row_lens_kernel 同款。
#  4. verify 批形（DSpark 多行/请求）时 rows 膨胀的行分块。
#  5. 与 publish 面（保持全量，论文首层全扫）的 L2 复用调度——测量后再动。


@triton.jit
def _e2m1_decode(code):
    # 与 fp4_indexer.py:423-430 同源：uint 0..15 -> e2m1 值。
    e = (code >> 1) & 3
    m = (code & 1).to(tl.float32)
    sub = m * 0.5
    nor = (1.0 + m * 0.5) * tl.exp2((e - 1).to(tl.float32))
    v = tl.where(e == 0, sub, nor)
    return tl.where((code >> 3) == 1, -v, v)


@triton.jit
def _fp4_gather_index_logits_kernel(
    q_ptr,  # [B, H, D] bf16，已 rope 的 fq4 查询（与全量内核同源输入）
    w_ptr,  # [B, H] bf16 头权（softmax scale 已折入）
    table_ptr,  # [pages, page_size*64 + page_size*4] uint8 索引 K 池（2D 视图）
    cand_slots_ptr,  # [B, C] int64 候选槽（-1 哨兵；C = 8*n_blocks，prologue 物化）
    out_ptr,  # [B, C] fp32 logits，-inf 于哨兵/越界
    C,  # 运行期候选宽度（生产 16384；短 ctx 时 = 8*min(topk_blocks, ceil(lmax/8))）
    page_size,  # 索引 K 池页大小（SM121 钉 64；sparse_wire #1b）
    row_stride,  # table.stride(0)
    stride_qb,
    stride_qh,
    stride_wb,
    H: tl.constexpr,  # 32（config index_n_heads；对拍测试可用小 H）
    HALF_D: tl.constexpr,  # D // 2 == 64：每行 nibble 对数
    BLOCK_C: tl.constexpr,  # 候选 tile 宽；必须 % 8 == 0（块对齐，发射宽度断言）
):
    # ---- 边界断言（骨架纪律）：合同在入口声明，违者当场红 -------------------
    tl.assume(C > 0)
    tl.assume(C % 8 == 0)  # 候选宽度 = block_size(8) × 块数（块背靠背布局）
    tl.assume(page_size > 0)
    if H > 1:  # 排除 singleton 头：其 stride 不受 PyTorch 连续性约束（同全量内核 :453-455）
        tl.assume(stride_qh == HALF_D * 2)

    b = tl.program_id(0)  # 查询行（decode=请求行；prefill 复用同核=查询行）
    cb = tl.program_id(1)  # 候选 tile（发射宽度维：dim1 = cdiv(C, BLOCK_C)，与 lmax 无关）
    offs_c = cb * BLOCK_C + tl.arange(0, BLOCK_C)
    offs_h = tl.arange(0, H)
    offs_i = tl.arange(0, HALF_D)  # 字节 i 存元素 2i（低 nibble）/ 2i+1（高 nibble）

    in_range = offs_c < C
    slot = tl.load(cand_slots_ptr + b * C + offs_c, mask=in_range, other=-1).to(tl.int64)
    valid = in_range & (slot >= 0)  # -1 哨兵 = 块 -1 填充或位置 ≥ lens（prologue 已掩蔽）

    page = slot // page_size
    off = slot % page_size
    row_base = page * row_stride
    safe_page = tl.where(valid, page, 0)  # 哨兵读 0 页 0 槽，值被掩蔽不参与结果
    safe_off = tl.where(valid, off, 0)
    safe_base = safe_page * row_stride

    # K payload：[BLOCK_C, HALF_D] uint8（寻址式与全量内核 :479-487 逐字节同源）
    pay = tl.load(
        table_ptr + safe_base[:, None] + safe_off[:, None] * 64 + offs_i[None, :],
        mask=valid[:, None],
        other=0,
    )
    low = _e2m1_decode(pay & 0x0F)
    high = _e2m1_decode((pay >> 4) & 0x0F)
    # ue8m0 块标：元素 j 用块 j//16 的标度字节 → 字节 i 用 i//16（同全量内核 :490-501）
    sc_idx = offs_i // 16
    exps = tl.load(
        table_ptr
        + safe_base[:, None]
        + page_size * 64
        + safe_off[:, None] * 4
        + sc_idx[None, :],
        mask=valid[:, None],
        other=127,  # 掩蔽行标度=1.0（2^0），值随后被 -inf 掩蔽
    )
    scale = tl.exp2(exps.to(tl.float32) - 127.0)
    k_low = (low * scale).to(tl.bfloat16)  # [BLOCK_C, HALF_D] 元素 2i
    k_high = (high * scale).to(tl.bfloat16)  # 元素 2i+1

    # 查询偶/奇元素：[H, HALF_D] bf16（同全量内核 :505-515）
    q_even = tl.load(
        q_ptr + b * stride_qb + offs_h[:, None] * stride_qh + 2 * offs_i[None, :]
    )
    q_odd = tl.load(
        q_ptr + b * stride_qb + offs_h[:, None] * stride_qh + 2 * offs_i[None, :] + 1
    )

    # 同形 tl.dot（K 维 = HALF_D，不分块）→ 候选位置 logit 与全量内核 bitwise 相等
    acc = tl.dot(q_even, tl.trans(k_low))  # [H, BLOCK_C] fp32
    acc += tl.dot(q_odd, tl.trans(k_high))
    # 参考舍入链（同全量内核 :519-524）：bf16 dot -> relu -> *bf16 权 -> bf16 -> 头和 -> bf16
    s = acc.to(tl.bfloat16).to(tl.float32)
    s = tl.maximum(s, 0.0)
    w = tl.load(w_ptr + b * stride_wb + offs_h).to(tl.float32)
    s = (s * w[:, None]).to(tl.bfloat16).to(tl.float32)
    logit = tl.sum(s, axis=0).to(tl.bfloat16).to(tl.float32)
    logit = tl.where(valid, logit, float("-inf"))
    tl.store(out_ptr + b * C + offs_c, logit, mask=in_range)


def gather_index_logits_decode(
    q: torch.Tensor,
    weights: torch.Tensor,
    cand_slots: torch.Tensor,
    table: torch.Tensor,
    page_size: int,
    *,
    block_c: int = 64,
) -> torch.Tensor:
    """宿主发射面：``q`` [B, H, 128] bf16、``weights`` [B, H]、``cand_slots`` [B, C]
    int64（-1 哨兵；由 reference_impl.candidate_slots 产出）、``table`` = 池 2D uint8
    视图。返回 fp32 [B, C]（-inf 于哨兵）。

    发射合同（census 判别锚）：grid = (B, cdiv(C, block_c))——**dim1 只依赖候选宽度
    C=8n（生产 16384），不依赖 lmax**。这就是「发射宽度从 lmax 降到 16384」的可观测面。
    """
    assert q.dtype == torch.bfloat16 and q.shape[-1] == 128
    B, H, _ = q.shape
    C = cand_slots.shape[1]
    assert table.dtype == torch.uint8 and table.dim() == 2
    assert C % 8 == 0, f"candidate width {C} not block-aligned (block_size=8)"
    assert block_c % 8 == 0, f"BLOCK_C {block_c} not block-aligned"
    q = q.contiguous()
    weights = weights.to(torch.bfloat16).contiguous()
    cand_slots = cand_slots.contiguous()
    out = torch.empty((B, C), dtype=torch.float32, device=q.device)
    if C == 0 or B == 0:
        return out
    grid = (B, triton.cdiv(C, block_c))
    _fp4_gather_index_logits_kernel[grid](
        q,
        weights,
        table,
        cand_slots,
        out,
        C,
        page_size,
        table.stride(0),
        q.stride(0),
        q.stride(1),
        weights.stride(0),
        H=H,
        HALF_D=64,
        BLOCK_C=block_c,
        num_warps=4,  # _TUNING_TODO: 靴上扫 {4, 8}
    )
    return out
