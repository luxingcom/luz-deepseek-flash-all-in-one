"""auto=hybrid 派发单元测（A6 census 2026-10-01 后立）：
小 n→triton、大 n→cuda、强制语义保留、两路径位等。
判别力：_active_backend 必须随 n 翻转（不翻=派发没接上）。"""
import os, sys
os.environ.pop("DSV41_FP4KV_REPACK_BACKEND", None)
os.environ["DSV41_FP4KV_REPACK_CUDA_MIN_N"] = "1024"
sys.path.insert(0, "/opt/dsv41/adapter")
import torch
import kv_fp4_repack as K

torch.manual_seed(7)
dev = torch.device("cuda")
pbs, tok = 16, 128         # ratio-2 页池：16 页×128 token=2048 槽
pool = torch.randint(0, 256, (pbs, tok, 1, 288), dtype=torch.uint8, device=dev)
pool = pool.view(torch.uint8)

def run(n):
    idx = torch.randint(0, pbs * tok, (n,), dtype=torch.int32, device=dev)
    idx[::7] = -1
    s, ids = K.repack_fp4_extra_to_v4(pool, idx.view(1, n), tok)
    torch.cuda.synchronize()
    return s.reshape(-1).clone(), K._active_backend

# 1) auto 派发：n<thr→triton，n>=thr→cuda
_, b_small = run(512)
_, b_big = run(2048)
assert b_small == "triton", f"n=512 应派 triton，得 {b_small}"
assert b_big == "cuda", f"n=2048 应派 cuda，得 {b_big}"
print("T1 hybrid dispatch flips with n: OK")

# 2) 两条路径位等（n=2048 走 cuda，再强制 triton 比对）
idx = torch.randint(0, pbs * tok, (2048,), dtype=torch.int32, device=dev); idx[::5] = -1
os.environ["DSV41_FP4KV_REPACK_BACKEND"] = "cuda"
s_cuda, _ = K.repack_fp4_extra_to_v4(pool, idx.view(1, 2048), tok)
os.environ["DSV41_FP4KV_REPACK_BACKEND"] = "triton"
s_tri, _ = K.repack_fp4_extra_to_v4(pool, idx.view(1, 2048), tok)
torch.cuda.synchronize()
assert torch.equal(s_cuda.reshape(-1), s_tri.reshape(-1)), "两后端输出应逐字节相等"
print("T2 both backends byte-identical: OK")

# 3) 强制语义：cuda 强制下 n=512 也走 cuda（臂可复现性）
os.environ["DSV41_FP4KV_REPACK_BACKEND"] = "cuda"
run(512); assert K._active_backend == "cuda", "强制 cuda 应无视阈值"
os.environ["DSV41_FP4KV_REPACK_BACKEND"] = "triton"
run(2048); assert K._active_backend == "triton", "强制 triton 应无视阈值"
print("T3 explicit force overrides threshold: OK")

# 4) 阈值 env 生效
os.environ.pop("DSV41_FP4KV_REPACK_BACKEND")
os.environ["DSV41_FP4KV_REPACK_CUDA_MIN_N"] = "256"
run(512); assert K._active_backend == "cuda", "thr=256 时 n=512 应 cuda"
print("T4 threshold env honored: OK")
print("ALL-PASS")
