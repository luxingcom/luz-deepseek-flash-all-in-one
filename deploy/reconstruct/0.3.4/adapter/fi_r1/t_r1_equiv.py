# -*- coding: utf-8 -*-
"""R1-FP4KV T4 位等价单测矩阵（host CPU；CUDA_VISIBLE_DEVICES=""）。

法源：docs/research/R1-FP4KV-DESIGN-20261011.md §4.3 表逐行 + §4.2-D 零行律。

比较器律（§4.3 末）：oracle=现役 repack 路径算术（kv_fp4_repack.py:525-625 ref
同式）；被检=fork 内核 IO/rope 算术的 host 逐指令镜像（fp4_extra_traits.cuh 的
torch 复刻——同一解码序/同一 __fdiv_rn 语义（CPU fp32 除法=IEEE RN）/同一
ue8m0 位技巧/同一 satfinite requant 面）。

零行断言律（§4.2-D 验收修正+F1/DIFFLOC-20261011）：一切零行断言按幅值位
（&0x7F==0，0x80=−0.0 合法）或值域比较，禁按字节全 0x00 断言；窗内 -1 行
=门控零行（分数 0 参与 softmax，分母 +2^0/条=幻影单位质量），两腿同载。

B 部掩码律（F2/DIFFLOC-20261011 §四-F2）：oracle 腿掩码=仅长度（ar>=etl）——
真实 oracle 路=repack 恒等 arange 桥索引（kv_fp4_repack.py:459-464）永非负，
stock ib<0 掩蔽永不击发；fork 腿随 F1 修复形（idx<0 → IO 门控零行）同式。

喂坏反向用例律：每检查器配坏孪生（错位/差一字节/错组尺度类）必红=判别力证。

窗内待验边界（如实，禁伪造）：设备端 e2e（fork 核 vs repack+现核 torch.equal）
与 fail-safe 首块对拍需 sm120 设备——本件提供 host 级核数学忠实仿真（B 部）+
设备端比较器函数（run_device_e2e，需 CUDA 时才执行）。

用法：CUDA_VISIBLE_DEVICES="" python3 fi_r1/t_r1_equiv.py   （13 面门+喂坏孪生）
"""

import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import struct
import sys

import torch

torch.manual_seed(20261011)
fp8 = torch.float8_e4m3fn

HERE = os.path.dirname(os.path.abspath(__file__))
DEV = os.path.dirname(HERE)

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'GREEN' if ok else 'RED'}] {name}{(' — ' + detail) if detail else ''}")


# ============================================================================
# 公共算术（oracle=现役 repack ref 行局部算术；replica=fork 内核 host 镜像）
# ============================================================================

_lut = torch.tensor([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0], dtype=torch.float32)


def _e2m1_byte(b):  # b: python int byte -> (lo, hi) f32 精确值（低 nibble=偶值）
    lo = _lut[(b & 0xF) & 7].item() * (-1.0 if (b & 0xF) >= 8 else 1.0)
    hi = _lut[(b >> 4) & 7].item() * (-1.0 if (b >> 4) >= 8 else 1.0)
    return lo, hi


def _e4m3_byte_to_f32(sb):
    return torch.tensor([sb], dtype=torch.uint8).view(fp8).to(torch.float32).item()


def _f32_bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _bits_f32(u):
    return struct.unpack("<f", struct.pack("<I", u))[0]


def _fdiv_rn(a, b):  # CPU fp32 除法 = IEEE RN（=内核 __fdiv_rn；ftz 域外已证无差）
    return float(torch.tensor([a], dtype=torch.float32) / torch.tensor([b], dtype=torch.float32))


# ---- oracle：repack ref 行局部算术（kv_fp4_repack.py:545-619 同式） ----
def repack_ref_row(payload, scale, gate=1.0):
    """一行 256B 载荷+32B 尺度 -> (nope_f8_bytes[448], ue8m0[8], rope_bf16_bits[64])

    gate=repack idx 门（kv_fp4_repack.py:301 ``gate = tl.where(valid, 1.0, 0.0)``，
    值级 (code×scale)×gate——F1 零行语义的 oracle 面：gate=0 ⇒ 符号携带 ±0 载荷+
    地板 ue8m0，与 fork 门控镜像逐位同构）。gate=1.0 精确无操作。"""
    codes = torch.empty(512, dtype=torch.uint8)
    codes[0::2] = payload & 0xF
    codes[1::2] = payload >> 4
    scales = scale.view(fp8).to(torch.float32).repeat_interleave(16)
    vals = _lut[(codes & 7).to(torch.int64)] * torch.where(codes >= 8, -1.0, 1.0) * scales * gate
    nope, rope = vals[:448], vals[448:]
    tiles = nope.view(7, 64)
    amax = tiles.abs().amax(dim=1)
    scale_raw = torch.maximum(amax, torch.full_like(amax, 1e-4)) / 448.0
    u = scale_raw.view(torch.int32)
    ue8m0 = ((u >> 23) & 0xFF) + (u & 0x7FFFFF != 0).to(torch.int32)
    inv = ((254 - ue8m0) << 23).view(torch.float32)
    f8 = (tiles * inv[:, None]).reshape(448).to(fp8).view(torch.uint8)
    ropeb = rope.to(torch.bfloat16)
    foot = torch.zeros(8, dtype=torch.uint8)
    foot[:7] = ue8m0.to(torch.uint8)
    return f8, foot, ropeb.view(torch.uint16)


# ---- replica：fork IO 生产者 host 镜像（fp4_extra_traits.cuh 逐指令对应） ----
def fork_io_row(payload, scale, gate=1.0):
    """io_fp4_gather_tile 单行镜像：两遍解码（遍1 amax 单累加、遍2 重取 requant）+
    页脚 ue8m0+pad0。word 序=小端 u32（=内核 LDG u32 后的 (w>>8j)&0xFF 字节序）。

    gate=F1 门控镜像（fp4_extra_traits.cuh R1-FP4KV F1：``sf = decode(scale) * gate``
    ——code×(sf×gate) 与 repack 值级 (code×sf)×gate 的 ±0 符号携带逐位一致；
    gate=0 ⇒ amax=0 ⇒ 地板 ue8m0=105+载荷 ±0 字节）。gate=1.0 精确无操作。"""
    out = torch.zeros(448, dtype=torch.uint8)
    foot = torch.zeros(8, dtype=torch.uint8)
    for t in range(7):
        # sw = 尺度行 u32（srow + t*4，小端）；pw[i] = 载荷 u32（prow + t*32 + i*4）
        sw = int.from_bytes(scale[t * 4 : t * 4 + 4].tolist(), "little")
        pw = [
            int.from_bytes(payload[t * 32 + i * 4 : t * 32 + i * 4 + 4].tolist(), "little")
            for i in range(8)
        ]
        # 遍 1：amax（值域 |v|，fp max 序无关）
        amax = 0.0
        vals = []
        for i in range(8):
            sf = _e4m3_byte_to_f32((sw >> (8 * (i >> 1))) & 0xFF) * gate  # 组 = i/2（16 值/组=2 词/组）
            w = pw[i]
            for j in range(4):
                lo, hi = _e2m1_byte((w >> (8 * j)) & 0xFF)
                vals += [lo * sf, hi * sf]
                amax = max(amax, abs(lo * sf), abs(hi * sf))
        # requant 尺度（__fdiv_rn 同式位技巧）
        scale_raw = _fdiv_rn(max(amax, 1e-4), 448.0)
        uu = _f32_bits(scale_raw)
        ue8m0 = ((uu >> 23) & 0xFF) + (1 if (uu & 0x7FFFFF) != 0 else 0)
        inv = _bits_f32((254 - ue8m0) << 23)
        # 遍 2：requant + 写（satfinite RN 面=torch .to(fp8)）
        tf = torch.tensor([v * inv for v in vals], dtype=torch.float32).to(fp8)
        out[t * 64 : (t + 1) * 64] = tf.view(torch.uint8)
        foot[t] = ue8m0
    return out, foot


def fork_rope_row(payload, scale, gate=1.0):
    """rope 直解镜像：值 k -> 字节 224+k//2，nibble=k&1，组=28+k//16，f32 积->bf16 RN。

    gate=F1 门控镜像（prefetch_kv_rope_fp4/load_rope_v_fp4 的 ``sf*gate``）：
    gate=0 ⇒ bf16 ±0 位（符号=slot0 nibble 符号），与 repack gate=0 rope 行逐位同。"""
    bits = torch.zeros(64, dtype=torch.uint16)
    for k in range(64):
        b = int(payload[224 + (k >> 1)])
        nib = _e2m1_byte(b)[0 if (k & 1) == 0 else 1]
        sf = _e4m3_byte_to_f32(int(scale[28 + (k >> 4)])) * gate
        bits[k] = torch.tensor([nib * sf], dtype=torch.float32).to(torch.bfloat16).view(torch.uint16)
    return bits


def row_compare(a, b):
    """行级比较器（幅值位零行律在断言侧，不在比较器侧：比较器=逐字节相等）。"""
    return bool(torch.equal(a[0], b[0]) and torch.equal(a[1], b[1]))


# ============================================================================
# A 部：§4.3 矩阵 1-6 行（fork replica vs repack oracle，逐位；每行配喂坏孪生）
# ============================================================================

def make_row(kind, rng=None):
    payload = torch.zeros(256, dtype=torch.uint8)
    scale = torch.full((32,), 100, dtype=torch.uint8)
    if kind == "rand":
        payload = torch.randint(0, 256, (256,), dtype=torch.uint8)
        scale = torch.randint(0, 127, (32,), dtype=torch.uint8)  # 上界 127 排 NaN（sanity §4.2 注）
    elif kind == "exhaustive":  # 全 16 码×全 254 有限尺度（行 5 的真全刷面）
        for g in range(32):
            for v in range(16):
                byte_idx = g * 8 + (v // 2)
                if v % 2 == 0:
                    payload[byte_idx] = (payload[byte_idx] & 0xF0) | v
                else:
                    payload[byte_idx] = (payload[byte_idx] & 0x0F) | (v << 4)
            # 组尺度字节扫过全部有限值（绕开 0x7F/0xFF NaN：0x00..0x7E,0x80..0xFE）
            scale[g] = (g * 8 + 3) % 256 if ((g * 8 + 3) % 256) & 0x7F != 0x7F else 0x7E
    elif kind == "zero":
        pass  # 载荷全零+尺度任意
    elif kind == "sat448":
        payload = torch.full((256,), 0x66, dtype=torch.uint8)
        scale = torch.full((32,), 0x7E, dtype=torch.uint8)
    elif kind == "subnorm":  # scale 0x01=e4m3 最小次正规（M/8×2^-6=2^-9），nibble 0x01=0.5
        # -> 值 2^-10。设计卡 §4.3 行 3 标注「0x01=2^-12→2^-13」为算术笔误（e4m3 次正规
        # 公式 = M/8 × 2^(1-bias) = M/8 × 2^-6）；行意图=最深次正规值路径逐位+零 nibble 混排，
        # 本行照卡意图实现（torch 证 e4m3(0x01)=2^-9）。奇字节 0x10=零 nibble 混排（卡「及全零 nibble」）。
        for i in range(256):
            payload[i] = 0x10 if (i % 2) == 0 else 0x11
        scale = torch.full((32,), 0x01, dtype=torch.uint8)
    elif kind == "subnorm_sweep":  # 行 4：组尺度扫 0x00/0x01/0x02 段
        payload = torch.randint(0, 256, (256,), dtype=torch.uint8)
        scale[:11] = 0x00
        scale[11:22] = 0x01
        scale[22:] = 0x02
    elif kind == "signs":  # 行 6：符号 nibble 位 3 全覆盖（含 -0.0/-6.0）
        for i in range(256):
            payload[i] = (i % 256) & 0xFF  # 全字节值=符号面全覆盖
        scale = torch.full((32,), 0x50, dtype=torch.uint8)
    return payload, scale


def fed_bad_twin(oracle_out):
    """喂坏孪生族（错位/差一字节/错组尺度类）→ row_compare（nope 字节+页脚）必 False。

    自适应律（输入性质 vs 检查器缺陷的分界）：
    - 值改变类（nope 字节 xor、ue8m0 差一）在任何行上恒可检测 → 恒适用；
    - 结构类（tile-swap）仅在非常量行上可检测——全零/全饱和行 7 tile 逐字节相同，
      交换后字节面不变（输入性质，非检查器盲区）→ 仅当行非常量时纳入必红集。
    rope 面的喂坏由 run_part_a 的 rope 专用比较器独立断言（row_compare 不含 rope）。"""
    f8, foot = oracle_out[0], oracle_out[1]
    bads = []
    b1 = (f8.clone(), foot.clone(), oracle_out[2].clone())
    b1[0][137] ^= 0x01  # 差一字节（nope 载荷）
    bads.append(("nope-byte-xor", b1))
    b2 = (f8.clone(), foot.clone(), oracle_out[2].clone())
    b2[1][3] = (int(b2[1][3]) + 1) & 0xFF  # ue8m0 差一（组尺度错档类）
    bads.append(("ue8m0-off-by-one", b2))
    tiles = f8.view(7, 64)
    constant = all(torch.equal(tiles[0], tiles[t]) for t in range(1, 7))
    skipped = []
    if not constant:
        b3 = (f8.clone(), foot.clone(), oracle_out[2].clone())
        v = b3[0].view(7, 64).flip(0).reshape(448)  # tile 错位（swap 类）
        bads.append(("tile-swap", (v, b3[1], b3[2])))
    else:
        skipped.append("tile-swap（常量行不可检测=输入性质）")
    return bads, skipped


def run_part_a():
    rows = [
        ("A1 zeros", "zero", {"zero_magnitude_law": True}),
        ("A2 448 饱和", "sat448", {"sat": True}),
        ("A3 深次正规 2^-13", "subnorm", {"subnorm": True}),
        ("A4 次正规边界扫", "subnorm_sweep", {}),
        ("A5 随机面", "rand", {}),
        ("A5b 全码×全尺度穷举", "exhaustive", {}),
        ("A6 负号面", "signs", {}),
    ]
    for name, kind, extra in rows:
        payload, scale = make_row(kind)
        o = repack_ref_row(payload, scale)
        f = fork_io_row(payload, scale)
        ok = row_compare(f, o) and bool(
            torch.equal(fork_rope_row(payload, scale), o[2].view(torch.uint16))
        )
        detail = ""
        if extra.get("zero_magnitude_law"):
            # 零行律：幅值位 &0x7F==0（0x80=-0.0 合法）；载荷非全 0x00 亦合法
            mag = (o[0] & 0x7F) == 0
            ok = ok and bool(mag.all())
            detail = f"幅位零={bool(mag.all())} 含0x80字节={bool((o[0] == 0x80).any())} ue8m0={o[1][:7].tolist()}"
        if extra.get("sat"):
            u = o[1][:7].tolist()
            ok = ok and all(x == 129 for x in u) and bool((o[0][:64] == 0x7E).all())
            detail = f"ue8m0={u[0]} payload首tile=0x{int(o[0][0]):02x}"
        if extra.get("subnorm"):
            v = _e2m1_byte(0x11)[0] * _e4m3_byte_to_f32(0x01)
            ok = ok and abs(v - 2.0**-10) < 1e-20 and v == 2.0**-10 * 1.0
            detail = f"2^-10 值={v!r}（e4m3(0x01)=2^-9 次正规，卡标注笔误见 make_row 注）"
        check(f"A {name}（replica==oracle 逐位）", ok, detail)
        # 喂坏孪生：检查器判别力证（必红；常量行上结构类退化为跳过并注明）
        bads, skipped = fed_bad_twin(o)
        all_red = all(not row_compare(f, b) for _, b in bads) and len(bads) >= 2
        check(f"A {name} 喂坏孪生必红（{len(bads)} 例{'; 跳过 ' + ','.join(skipped) if skipped else ''}）",
              all_red)
        # rope 面喂坏：专用比较器必红（非零位翻转；全零 rope 行退化跳过）
        rope_o = o[2].view(torch.uint16)
        if int(rope_o.sum()) > 0:
            rope_bad = rope_o.clone()
            nz = (rope_o != 0).nonzero()[0]
            rope_bad[int(nz)] = int(rope_bad[int(nz)]) ^ 0x0001
            check(f"A {name} rope 喂坏必红", not bool(torch.equal(fork_rope_row(payload, scale), rope_bad)))
        else:
            check(f"A {name} rope 喂坏跳过（全零 rope=输入性质）", True)

    # A7（F1 零行门控镜像，DIFFLOC-20261011）：idx<0 → 门控解碁=repack gate=0
    # 零行的逐位复刻——载荷符号携带 ±0（0x00/0x80，符号=slot0 nibble）+地板
    # ue8m0=105+pad0；fork 镜像与 repack ref 字节逐位同（构造性位等的零行根基）。
    for name in ("rand", "signs", "sat448"):
        payload, scale = make_row(name)
        f_z = fork_io_row(payload, scale, 0.0)
        o_z = repack_ref_row(payload, scale, 0.0)
        fr_z = fork_rope_row(payload, scale, 0.0)
        bytes_eq = torch.equal(f_z[0], o_z[0]) and torch.equal(f_z[1], o_z[1])
        mag0 = bool(((o_z[0] & 0x7F) == 0).all())
        has_neg0 = bool((o_z[0] == 0x80).any())  # 仅当源行含负 nibble（输入性质）
        foot_ok = bool((o_z[1][:7] == 105).all()) and int(o_z[1][7]) == 0
        rope_eq = bool(torch.equal(fr_z, o_z[2].view(torch.uint16)))
        rope_mag0 = bool(((o_z[2].view(torch.uint16) & 0x7FFF) == 0).all())
        check(f"A7 {name} 零行门控镜像==repack gate=0 行逐位（±0+地板105）",
              bytes_eq and mag0 and foot_ok and rope_eq and rope_mag0,
              f"含0x80={has_neg0} ue8m0={o_z[1].tolist()}"
              + ("" if has_neg0 else "（全正 nibble 行=纯 +0，输入性质）"))
        # 喂坏：门控镜像若改回常量 +0（旧 load_rope_v_fp4 形）→ 位面必可分辨
        # （仅当 slot0 行存在负 nibble 即 ±0 混排时；纯正行退化跳过）。
        if bool((o_z[2].view(torch.uint16) == 0x8000).any()):
            check(f"A7 {name} 零行 rope −0 位喂坏必红（常量+0 旧形可分辨）",
                  not bool(torch.equal(fr_z, torch.zeros(64, dtype=torch.uint16))))
        else:
            check(f"A7 {name} 零行 rope 喂坏跳过（slot0 无负 nibble=输入性质）", True)


# ============================================================================
# B 部：行 7 host 级 e2e 仿真（含 -1/短 topk_length；掩码承担位等）
# ============================================================================

def ue8m0_to_f32(b):
    return _bits_f32(int(b) << 23)


def smem_row_to_values(nope_bytes, foot, rope_bits):
    """math warp 消费面镜像：E4M3 字节→f32 × ue8m0 尺度（per-64 tile）；rope bf16。"""
    k = torch.zeros(512, dtype=torch.float32)
    f8 = nope_bytes.view(fp8).to(torch.float32)
    scales = torch.tensor([ue8m0_to_f32(int(foot[t])) for t in range(7)], dtype=torch.float32)
    k[:448] = (f8.view(7, 64) * scales[:, None]).reshape(448)
    k[448:] = rope_bits.view(torch.bfloat16).to(torch.float32)
    return k


def emulate_attention(paths_kv, q, mask_rows, sm_scale, apply_mask=True):
    """kernel-faithful host 仿真：掩码行 qk=-1e30 → w=exp2(负巨大)=+0.0 →
    贡献 ±0.0（fp32 x+±0.0=x 逐位不变）。paths_kv=(T,topk,512) f32。"""
    T, K, _ = paths_kv.shape
    qk = torch.einsum("thd,tkd->thk", q.to(torch.float32), paths_kv) * (sm_scale * 1.4426950408889634)
    if apply_mask:
        qk = qk.masked_fill(mask_rows[:, None, :], -1e30)
    m = qk.max(dim=-1, keepdim=True).values
    w = torch.exp2(qk - m)
    lse = torch.log2(w.sum(dim=-1)) + m.squeeze(-1)
    out = torch.einsum("thk,tkd->thd", w, paths_kv).to(torch.bfloat16)
    return out, lse.to(torch.float32)


def run_part_b():
    PBS = 128  # ratio-2 池页（另一几何 256 由 A 部行覆盖几何无关性：行局部纯函数）
    PAGES = 3
    pool = torch.randint(0, 256, (PAGES * PBS, 256), dtype=torch.uint8)
    poolscale = torch.randint(0, 127, (PAGES * PBS, 32), dtype=torch.uint8)
    # 特殊行埋点：slot0（fork 门控零行的钳位读目标）与若干全零/饱和行
    pool[0] = 0x5A
    poolscale[0] = 0x40
    pool[1] = 0
    poolscale[1] = 100
    pool[2] = 0x66
    poolscale[2] = 0x7E
    T, TOPK = 5, 6
    # 生产域索引形：topk_length≥1；窗内可含 -1（生产形=幻影行，F1/F2 后两腿同载
    # 单位质量）；≥etl 项=窗外（长度掩蔽，两腿同式）。
    idx = torch.tensor(
        [[0, 1, 2, 130, -1, -1], [257, 258, -1, 0, 1, 2], [3, 3, 3, 200, -1, 5],
         [7, 8, 9, 10, -1, -1], [7, 8, 9, 10, 11, 12]], dtype=torch.int64)
    etl = torch.tensor([3, 6, 2, 4, 6], dtype=torch.int64)  # 短 topk_length（≥1 生产域）
    ar = torch.arange(TOPK)
    H = 4
    q = (torch.randn(T, H, 512) * 0.05).to(torch.bfloat16)

    def rows_of(indices):
        safe = indices.clamp(min=0)
        return pool[safe], poolscale[safe]

    # F2（DIFFLOC-20261011 §四-F2）：掩码=仅长度（ar>=etl）两腿同式——真实 oracle 路
    # =repack 恒等 arange 桥索引（kv_fp4_repack.py:459-464）⇒ 永非负 ⇒ stock 的
    # ib<0 掩蔽永不击发；fork 腿随 F1 修复形（idx<0 → IO 门控零行）同式仅长度。
    # 两腿对窗内 -1 同载「分数 0 参与 softmax」的幻影单位质量（E2 host 直证形）。
    mask = ar.unsqueeze(0) >= etl.unsqueeze(1)
    gate = (idx >= 0).to(torch.float32)  # 行级 idx 门（fork 门控镜像=repack gate 同源）

    # fork 路径（F1 修复形）：门控解碁（-1 → 零行：±0 载荷+地板尺度+±0 rope）
    fkv = torch.zeros(T, TOPK, 512, dtype=torch.float32)
    pl, sc = rows_of(idx)
    for t in range(T):
        for r in range(TOPK):
            g = float(gate[t, r])
            nb, foot = fork_io_row(pl[t, r], sc[t, r], g)
            rb = fork_rope_row(pl[t, r], sc[t, r], g)
            fkv[t, r] = smem_row_to_values(nb, foot, rb)
    # oracle 路径：repack ref（idx 门 gate=0 = kv_fp4_repack.py:301 值级门）
    okv = torch.zeros(T, TOPK, 512, dtype=torch.float32)
    for t in range(T):
        for r in range(TOPK):
            nb, foot, rb = repack_ref_row(pl[t, r], sc[t, r], float(gate[t, r]))
            okv[t, r] = smem_row_to_values(nb, foot, rb.view(torch.uint16))
    sm = 512**-0.5
    out_f, lse_f = emulate_attention(fkv, q, mask, sm)
    out_o, lse_o = emulate_attention(okv, q, mask, sm)
    check("B1 e2e 仿真 fork vs oracle out torch.equal（仅长度掩码+零行语义）",
          bool(torch.equal(out_f, out_o)))
    check("B2 e2e 仿真 fork vs oracle LSE torch.equal（窗内 -1 两腿同载幻影质量）",
          bool(torch.equal(lse_f, lse_o)))
    # 窗内行值面逐位相等（含窗内 -1 行：两腿皆门控零行——构造性位等的根基）
    inwin = ~mask
    fkv_rows_eq = all(
        torch.equal(fkv[t, r], okv[t, r]) for t in range(T) for r in range(TOPK) if inwin[t, r]
    )
    phantom = ((idx < 0) & (ar.unsqueeze(0) < etl.unsqueeze(1))).sum()
    phantom_zero = all(
        bool((fkv[t, r] == 0).all()) and bool((okv[t, r] == 0).all())
        for t in range(T) for r in range(TOPK) if inwin[t, r] and idx[t, r] < 0
    )
    check("B3 窗内行值面逐位相等（含 -1 行两腿皆零行）", fkv_rows_eq and phantom_zero,
          f"窗内幻影行数={int(phantom)}")
    # 喂坏孪生（判别力）：fork 旧形=钳位读真数据（去门控）+仅长度掩码 → 必红
    # （窗内 -1 行漏入真分数=幻影缺失；零行构造+F2 掩码面皆是承重件）
    fkv_old = torch.zeros(T, TOPK, 512, dtype=torch.float32)
    for t in range(T):
        for r in range(TOPK):
            nb, foot = fork_io_row(pl[t, r], sc[t, r])
            rb = fork_rope_row(pl[t, r], sc[t, r])
            fkv_old[t, r] = smem_row_to_values(nb, foot, rb)
    out_fo, _ = emulate_attention(fkv_old, q, mask, sm)
    check("B4 喂坏：fork 旧形（钳位真数据+仅长度掩码）→必红（零行承重）",
          not bool(torch.equal(out_fo, out_o)))
    # 喂坏孪生：去掉长度掩码 → 输出必不等（窗外真数据行漏入；长度掩码承重）
    out_nf, _ = emulate_attention(fkv, q, mask, sm, apply_mask=False)
    check("B5 喂坏：长度掩码移除→必红", not bool(torch.equal(out_nf, out_f)))
    # 喂坏孪生：oracle 某行翻一字节 → 必红
    okv_bad = okv.clone()
    okv_bad[0, 0, 100] += 1.0
    out_ob, _ = emulate_attention(okv_bad, q, mask, sm)
    check("B6 喂坏：oracle 差一行值→必红", not bool(torch.equal(out_ob, out_o)))
    # B7 域内化（F1/F2 后）：全 -1 窗（topk_length≥1 生产域内「全掩码 token」形）
    # 两腿皆满窗幻影 → torch.equal——旧「域外退化形特判」消除（F1 前该形 fork 钳位
    # 真数据 vs repack 零行必不等，今值面同构）。etl=0 全窗外形亦同理等（注记）。
    def legs_equal(idx_x, etl_x):
        K_x = idx_x.shape[1]
        plx, scx = rows_of(idx_x)
        qx = (torch.randn(idx_x.shape[0], H, 512) * 0.05).to(torch.bfloat16)
        gx = (idx_x >= 0).to(torch.float32)
        k_f = torch.zeros(idx_x.shape[0], K_x, 512, dtype=torch.float32)
        k_o = torch.zeros_like(k_f)
        for t in range(idx_x.shape[0]):
            for r in range(K_x):
                nb, foot = fork_io_row(plx[t, r], scx[t, r], float(gx[t, r]))
                k_f[t, r] = smem_row_to_values(nb, foot, fork_rope_row(plx[t, r], scx[t, r], float(gx[t, r])))
                nb, foot, rb = repack_ref_row(plx[t, r], scx[t, r], float(gx[t, r]))
                k_o[t, r] = smem_row_to_values(nb, foot, rb.view(torch.uint16))
        mx = torch.arange(K_x).unsqueeze(0) >= etl_x.unsqueeze(1)
        o_f, l_f = emulate_attention(k_f, qx, mx, sm)
        o_o, l_o = emulate_attention(k_o, qx, mx, sm)
        return bool(torch.equal(o_f, o_o) and torch.equal(l_f, l_o)), l_o

    eq_full, lse_full = legs_equal(torch.tensor([[-1, -1, -1, -1, -1, -1]], dtype=torch.int64),
                                   torch.tensor([6], dtype=torch.int64))
    eq_e0, _ = legs_equal(torch.tensor([[9, -1, -1]], dtype=torch.int64),
                          torch.tensor([0], dtype=torch.int64))
    check("B7 全 -1 窗（etl≥1 域内形）两腿 torch.equal（满窗幻影=域内位等律；旧域外特判消除）",
          eq_full and eq_e0, f"满窗 LSE={lse_full[0, 0].item():.4f}=log2(6)（N=6 幻影同载）")


# ============================================================================
# C 部：fail-safe 检查器 + 键律 + fi_r1 壳律（host 可验面）
# ============================================================================

def run_part_c():
    # C1 fail-safe 检查器判别力（=桥内 torch.equal 双面门的 host 复刻）
    a = torch.randn(4, 8, 512).to(torch.bfloat16)
    la = torch.randn(4, 8)
    b = a.clone()
    lb = la.clone()
    check("C1 fail-safe 检查器：同件绿", bool(torch.equal(a, b) and torch.equal(la, lb)))
    bad_cases = []
    b1 = b.clone(); b1[2, 5, 300] = b1[2, 5, 300] ^ torch.tensor(1, dtype=torch.bfloat16) if b1.dtype != torch.bfloat16 else b1[2, 5, 300]
    b1 = b.clone(); b1[2, 5, 300] = torch.where(b1[2, 5, 300] == 0, torch.tensor(1.0, dtype=torch.bfloat16), -b1[2, 5, 300])
    bad_cases.append(("out 翻号", b1, lb))
    lb2 = lb.clone(); lb2[1, 3] += 1e-6
    bad_cases.append(("lse 微差", b, lb2))
    b3 = b.clone(); b3[0] = b3[1].clone()
    bad_cases.append(("行交换", b3, lb))
    b4 = b.clone(); b4[3, :, :] = 0
    bad_cases.append(("整行清零", b4, lb))
    all_red = all(not (torch.equal(a, x) and torch.equal(la, y)) for _, x, y in bad_cases)
    check("C2 fail-safe 检查器：四喂坏例必红", all_red)

    # C3 键律：严格布尔
    sys.path.insert(0, DEV)
    import kv_fp4 as kf

    for v, want in [("1", True), ("on", True), (" TRUE ", True), ("0", False), ("", False),
                    ("off", False), (None, False)]:
        os.environ.pop(kf.R1_ENV, None) if v is None else os.environ.__setitem__(kf.R1_ENV, v)
        got = kf._parse_r1_key()
        check(f"C3 键律 {v!r}->{want}", got == want)
    os.environ[kf.R1_ENV] = "bogus"
    try:
        kf._parse_r1_key()
        check("C3 键律 bogus 拒绝", False)
    except RuntimeError:
        check("C3 键律 bogus 拒绝（RuntimeError）", True)
    os.environ.pop(kf.R1_ENV, None)

    # C4 路由门静态律：键关=零新分支（R1 块=wrapper 内唯一 [R1] 插入且在 stock 体前门）
    src = open(os.path.join(DEV, "kv_fp4.py")).read()
    gate_ok = (
        '_r1["armed"]' in src
        and "module.SM120_DECODE_MAX_TOKENS" in src
        and src.count("[R1]") >= 3
        and "routed = _r1_try_prefill(module, kwargs)" in src
        and "if routed is not None:" in src
    )
    check("C4 路由门静态律（键∧prefill 面∧回退落穿）", gate_ok)

    # C5 fi_r1 壳 host 律：import 安全+get_module 无 flashinfer 时 fail-loud
    sys.path.insert(0, HERE)
    import fi_r1

    check("C5a fi_r1 import host 安全", fi_r1._MODULE_NAME == "sparse_mla_sm120_fp4")
    try:
        fi_r1.get_module()
        check("C5b fi_r1 get_module 无 flashinfer fail-loud", False)
    except RuntimeError as e:
        check("C5b fi_r1 get_module 无 flashinfer fail-loud（RuntimeError）", "fi_r1" in str(e))
    except ImportError:
        check("C5b fi_r1 get_module 无 flashinfer fail-loud（ImportError 上抛路径）", True)
    s = fi_r1.summary()
    check("C5c fi_r1 summary()", "module=sparse_mla_sm120_fp4" in s)


# ============================================================================
# D 部：sanity_host §4.2 复跑（12 断言锚复用）+ 设备端 e2e 比较器（窗内件）
# ============================================================================

def run_device_e2e():
    """设备端 e2e（§4.3 行 7 设备面）：需 sm120+装包 flashinfer+fi_r1 JIT 构建。
    host 无 CUDA 时如实跳过=窗内待验（探针窗 G1 承接），禁伪造。"""
    if not torch.cuda.is_available() or torch.cuda.get_device_capability(0)[0] != 12:
        print("[SKIP] D 设备端 e2e：无 sm120 设备（窗内待验，G0/G1 承接）")
        return
    import fi_r1
    from flashinfer.mla._sparse_mla_sm120 import _sparse_mla_sm120_paged_attention

    from kv_fp4_repack import repack_fp4_extra_to_v4  # 需生产镜像环境

    PBS, PAGES, T, TOPK, H = 128, 3, 8, 32, 32
    dev = "cuda"
    pool = torch.randint(0, 256, (PAGES, PBS, 1, 288), dtype=torch.uint8, device=dev)
    flat = pool.view(PAGES, PBS * 288)
    # 埋特殊行
    flat[0, : 256] = 0x5A
    flat.view(PBS * PAGES * 288)[:] = flat.reshape(-1)  # noop keep
    idx = torch.randint(0, PBS * PAGES, (T, TOPK), dtype=torch.int32, device=dev)
    idx[0, TOPK - 1] = -1
    idx[1, : TOPK // 2] = -1
    etl = torch.randint(1, TOPK + 1, (T,), dtype=torch.int32, device=dev)
    q = (torch.randn(T, H, 512, device=dev) * 0.05).to(torch.bfloat16)
    main = torch.randint(0, 256, (64, 64, 1, 584), dtype=torch.uint8, device=dev)  # 占位主缓存
    sm = 512**-0.5
    out_f = torch.empty(T, H, 512, dtype=torch.bfloat16, device=dev)
    lse_f = torch.empty(T, H, dtype=torch.float32, device=dev)
    fi_r1.r1_fp4kv_prefill(q, main, idx, out_f, lse_f, sm,
                           extra_kv_cache=pool, extra_indices=idx,
                           extra_topk_length=etl)
    scratch, bridged = repack_fp4_extra_to_v4(pool, idx, PBS)
    out_o = torch.empty_like(out_f)
    lse_o = torch.empty_like(lse_f)
    _sparse_mla_sm120_paged_attention(q, main, idx, out_o, lse_o, sm,
                                      extra_kv_cache=scratch, extra_indices=bridged,
                                      extra_topk_length=etl, mid_out=None, mid_lse=None)
    check("D1 设备端 e2e out torch.equal", bool(torch.equal(out_f, out_o)))
    check("D2 设备端 e2e LSE torch.equal", bool(torch.equal(lse_f, lse_o)))


def run_sanity_replay():
    """复跑设计卡 §4.2 host sanity（dev/r1-fp4kv/sanity_host.py 12/12 锚）。"""
    import contextlib
    import importlib.util
    import io

    spec = importlib.util.spec_from_file_location(
        "r1_sanity_host", os.path.join(DEV, "sanity_host.py")
    )
    mod = importlib.util.module_from_spec(spec)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        spec.loader.exec_module(mod)
    out = buf.getvalue()
    ok = (
        "ALL SANITY DONE" in out
        and "requant逐位=True" in out
        and "rope位等=True" in out
        and out.count("requant逐位=True") == 4  # 四面
    )
    check("D3 sanity_host.py 复跑（§4.2 四面 12 断言）", ok)


if __name__ == "__main__":
    run_part_a()
    run_part_b()
    run_part_c()
    run_sanity_replay()
    run_device_e2e()
    print(f"\n===== {len(PASS)} GREEN / {len(FAIL)} RED =====")
    for f in FAIL:
        print(f"  RED: {f}")
    sys.exit(1 if FAIL else 0)
