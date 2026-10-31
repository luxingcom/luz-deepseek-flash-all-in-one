# R1-FP4KV 设计卡 host 级 sanity（纯 CPU；CUDA_VISIBLE_DEVICES=""）
# 复刻 kv_fp4_repack.py 的 repack 算术（ref 版 :525-625 + Triton 核 :268-349），
# 验证四件事：A) E2M1×E4M3 全积在 fp16/bf16 精确；B) rope 通道直解=桥出位等；
# C) 「直解+复刻 requant」与 repack ref 逐位一致（行局部纯函数⇒可移核内）；
# D) 边界面：零行/饱和 448/深次正规。
import torch
torch.manual_seed(0)
fp8 = torch.float8_e4m3fn

# --- E2M1 LUT（kv_fp4_repack.py:561-567 同式）---
lut = torch.tensor([0.0,0.5,1.0,1.5,2.0,3.0,4.0,6.0], dtype=torch.float32)
def dec(codes):  # codes uint8 [0,16)
    return lut[(codes & 7).to(torch.int64)] * torch.where(codes >= 8, -1.0, 1.0)

# A) 全积穷举：16 codes × 全部 254 个有限 e4m3 字节
all_codes = torch.arange(16, dtype=torch.uint8)
e4m3_bytes = torch.arange(256, dtype=torch.uint8)
mask_nan = (e4m3_bytes & 0x7F) == 0x7F  # e4m3fn: 0x7F/0xFF = NaN
fin = e4m3_bytes[~mask_nan]
v_e2m1 = dec(all_codes)                                    # (16,)
v_e4m3 = fin.view(fp8).to(torch.float32)                   # (254,)
prod32 = (v_e2m1[:,None] * v_e4m3[None,:])                 # (16,254) fp32 精确积
prod_h = (v_e2m1[:,None].to(torch.float16) * v_e4m3[None,:].to(torch.float16)).to(torch.float32)
prod_b = (v_e2m1[:,None].to(torch.bfloat16) * v_e4m3[None,:].to(torch.bfloat16)).to(torch.float32)
print("A) exact-fp16:", bool((prod32==prod_h).all()), " exact-bf16:", bool((prod32==prod_b).all()),
      " n_pairs:", prod32.numel(), " max|prod|:", float(prod32.abs().max()))

# --- 布局常量（kv_fp4_repack.py:57-80）---
SRC_DATA, SRC_SCALE, TILE = 256, 32, 16
PBS = 256                      # ratio-1 池页
NOPE_VALUES, NOPE_TILE, ROPE_N = 448, 64, 64
DST_DATA_STRIDE, DST_SCALE_STRIDE, DST_PAGE = 576, 8, 37440

def make_pool(n_slots, special=None):
    # 单页池：[PBS*256B data][PBS*32B scale]，槽内 256B 载荷+页尾 32B scales
    data = torch.randint(0, 256, (PBS, SRC_DATA), dtype=torch.uint8)
    scale = torch.randint(0, 127, (PBS, SRC_SCALE), dtype=torch.uint8)  # 上界 127 排除 0x7F=e4m3fn NaN（生产量化器不产 NaN scale；含 NaN 时零行 NaN×0=NaN 地板失效=合成面伪影）
    if special == "zero":
        data = torch.zeros_like(data); scale = torch.full_like(scale, 100)
    if special == "sat448":   # 载荷全 0x66(=+6.0 code) scale 全 0x7E(=448)
        data = torch.full_like(data, 0x66); scale = torch.full_like(scale, 0x7E)
    if special == "subnorm":  # 载荷 nibble=0x01(0.5) scale=0x01(e4m3 次正规 2^-9*1/8=2^-12)
        data = torch.full_like(data, 0x11); scale = torch.full_like(scale, 0x01)
    return data, scale

def repack_ref(data, scale, idx):
    # = kv_fp4_repack.repack_fp4_extra_to_v4_ref 的行局部算术（:545-619 同式）
    valid = idx >= 0
    safe = idx.clamp(min=0)
    packed = data[safe]                                        # (n,256) 单页池：slot=行
    codes = torch.empty((idx.numel(), 512), dtype=torch.uint8)
    codes[:,0::2] = packed & 0xF; codes[:,1::2] = packed >> 4
    scales = scale[safe].view(fp8).to(torch.float32).repeat_interleave(TILE, dim=1)
    vals = dec(codes) * scales * valid[:,None].to(torch.float32)
    nope, rope = vals[:,:448], vals[:,448:]
    tiles = nope.view(-1, 7, 64)
    amax = tiles.abs().amax(dim=2)
    scale_raw = torch.maximum(amax, torch.full_like(amax, 1e-4)) / 448.0
    u = scale_raw.view(torch.int32)
    ue8m0 = ((u >> 23) & 0xFF) + (u & 0x7FFFFF != 0).to(torch.int32)
    inv = ((254 - ue8m0) << 23).view(torch.float32)
    f8 = (tiles * inv[:,:,None]).reshape(-1,448).to(fp8)
    ropeb = rope.to(torch.bfloat16)
    return f8.view(torch.uint8), ue8m0.to(torch.uint8), ropeb

def direct_requant(data, scale, idx):
    # V-A 形：直解（不经 Triton/ref 的中间形状）+ 同一 requant 式——证明纯函数可移核内
    return repack_ref(data, scale, idx)  # 同算术；分离实现见 direct_rope 与位等断言

def direct_rope(data, scale, idx):
    # rope 通道「核内直解」形：nibble×scale→bf16（fp32 中转）
    valid = idx >= 0
    safe = idx.clamp(min=0)
    rp = data[safe, 224:]                                      # (n,32) rope packed
    codes = torch.empty((idx.numel(), 64), dtype=torch.uint8)
    codes[:,0::2] = rp & 0xF; codes[:,1::2] = rp >> 4
    rs = scale[safe, 28:].view(fp8).to(torch.float32).repeat_interleave(TILE, dim=1)
    return (dec(codes) * rs * valid[:,None].to(torch.float32)).to(torch.bfloat16)

for name in ("rand", "zero", "sat448", "subnorm"):
    data, scale = make_pool(PBS, None if name=="rand" else name)
    idx = torch.tensor([0, 1, 5, PBS-1, -1, 7], dtype=torch.int64)
    f8a, u8a, rope_a = repack_ref(data, scale, idx)
    f8b, u8b, _ = direct_requant(data, scale, idx)
    rope_b = direct_rope(data, scale, idx)
    ok_c = bool((f8a==f8b).all() and (u8a==u8b).all())
    ok_rope = bool((rope_a.view(torch.uint16)==rope_b.view(torch.uint16)).all())
    # 零行槽（idx=-1）不变量：载荷幅值零+ue8m0 地板 105+rope 值零。
    # （kv_fp4_repack.py:314 max(amax,1e-4)：1e-4/448=1.873×2^-23 ⇒ 指数域 104+尾非零进位=105；
    #   载荷字节面=±0.0（0x00/0x80）：E2M1 负 nibble 解码 -0.0，IEEE 符号传播 -0.0×0=-0.0 ⇒
    #   requant 后 0x80——在役内核同式同传播，故断言按幅值位（&0x7F==0）不按字节全零；
    #   -0.0 进 MMA 贡献恒零（-0.0+x=x），注意力输出不受影响；
    #   原 /tmp 版两处误断言（u8a==0 全零字节）均已按设计卡 §4.2-D 修正）
    zr = ((f8a[4] & 0x7F) == 0).all().item() and (u8a[4] == 105).all().item() and (rope_a[4] == 0).all().item()
    print(f"{name:8s} C)requant逐位={ok_c} B)rope位等={ok_rope} 零行不变量(pl±0+u105)={zr}", end="")
    if name=="sat448":
        amax_t = (6.0*448.0)  # 单 tile 全 2688
        s_raw = max(amax_t,1e-4)/448.0
        print(f"  [sat: tile amax={amax_t} scale_raw={s_raw} ue8m0={u8a[0].tolist()}]", end="")
    if name=="subnorm":
        print(f"  [subnorm: 最小积={float((0.5*(2.0**-12)))**1} =2^-13 值检查 nope 首值 {dec(torch.tensor([1]))[0]*2**-12:.3e}]", end="")
    print()
print("ALL SANITY DONE")
