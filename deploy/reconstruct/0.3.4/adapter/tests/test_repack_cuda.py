#!/usr/bin/env python3
"""Bit-equality gate: CUDA repack_cuda.cu vs the Triton _repack_fp4_to_v4_kernel.

Run INSIDE the r3boot-head container (GPU + sglang + triton):
    docker exec r3boot-head python3 /opt/dsv41/adapter/tests/test_repack_cuda.py

Gate: for every case the two backends' raw V4 scratch bytes must be IDENTICAL
(memcmp over the uint8 view, zero tolerance). The pool is built in the real
V41_FP4 block-planar page layout the kernel indexes into: per page
[pbs*256 payload bytes][pbs*32 e4m3 scale bytes]. Plus semantic spot checks
(zero-row footer floor, rope bf16 exact re-derivation, sign-of-zero payloads),
backend-switch unit checks and a comparator discrimination self-test.

GPU budget: worst case allocates ~25 MB (well under the 100 MB cap; assert
>200 MB free first).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch  # noqa: E402

import kv_fp4_repack as K  # noqa: E402

DEV = "cuda"
PBS_BY_BITS = {7: 128, 8: 256}
E2M1_LUT = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
E2M1_LUT_SIGNED = E2M1_LUT + [-v for v in E2M1_LUT]  # code bit 3 = sign

PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


# ---------------------------------------------------------------- pool build
def build_pool(num_pages, pbs, kind, seed):
    """(pages, pbs*288) uint8 in the block-planar V41_FP4 page layout."""
    g = torch.Generator().manual_seed(seed)
    page = 288 * pbs
    flat = torch.zeros(num_pages, page, dtype=torch.uint8)
    data = flat[:, : pbs * 256]
    scales = flat[:, pbs * 256:]
    if kind == "random":
        data.copy_(torch.randint(0, 256, data.shape, dtype=torch.uint8, generator=g))
        sc = torch.randint(0, 256, scales.shape, dtype=torch.uint8, generator=g)
        sc[(sc == 0x7F) | (sc == 0xFF)] = 0x38  # no NaN scales in random data
        scales.copy_(sc)
    elif kind == "codes256":  # every e2m1 code in both nibble positions
        pat = torch.arange(data.numel(), dtype=torch.int64) % 256
        data.copy_(pat.view(data.shape).to(torch.uint8))
        sc = torch.randint(0, 256, scales.shape, dtype=torch.uint8, generator=g)
        sc[(sc == 0x7F) | (sc == 0xFF)] = 0x3A
        scales.copy_(sc)
    elif kind == "scales_edge":  # e4m3 subnormal / zero / +-max / negatives
        edge = torch.tensor(
            [0x00, 0x01, 0x02, 0x03, 0x07, 0x08, 0x10, 0x38,
             0x3A, 0x7E, 0x80, 0xC0, 0xFE, 0x39, 0x55, 0x2A],
            dtype=torch.uint8,
        )
        scales.copy_(edge.repeat((scales.numel() + 15) // 16)[: scales.numel()].view(scales.shape))
        data.copy_(torch.randint(0, 256, data.shape, dtype=torch.uint8, generator=g))
    elif kind == "zero_data":  # amax=0 floor path with live scales
        scales.copy_(torch.randint(0, 256, scales.shape, dtype=torch.uint8, generator=g))
    elif kind == "zero_scale":
        data.copy_(torch.randint(0, 256, data.shape, dtype=torch.uint8, generator=g))
    elif kind == "zeros":
        pass
    elif kind == "neg_zero":  # code 0x8 everywhere: -0.0 must stay -0.0
        data.fill_(0x88)
        scales.fill_(0x38)
    else:
        raise ValueError(kind)
    return flat


def build_idx(kind, n, num_slots, seed):
    g = torch.Generator().manual_seed(seed + 1)
    if kind == "all_neg1":
        v = torch.full((n,), -1, dtype=torch.int64)
    elif kind == "valid_dense":
        v = torch.arange(n, dtype=torch.int64) % num_slots
    elif kind == "mixed":
        v = torch.randint(0, num_slots, (n,), generator=g)
        v[::7] = -1
        v[::11] = -1
    elif kind == "boundary":
        cand = [0, 1, num_slots - 1]
        for b in (128, 256):
            cand += [b - 1, b, b + 1, 2 * b - 1, 2 * b]
        cand = [c for c in cand if 0 <= c < num_slots]
        rows = []
        i = 0
        while len(rows) < n:
            rows.append(cand[i % len(cand)] if i % 3 else -1)
            i += 1
        v = torch.tensor(rows[:n], dtype=torch.int64)
    else:
        raise ValueError(kind)
    return v.to(torch.int32).contiguous()


# ---------------------------------------------------------------- comparator
def first_diff(a, b):
    if torch.equal(a, b):
        return None
    d = a != b
    flat = d.reshape(-1).nonzero()[0].item()
    return f"ndiff={int(d.sum())} first_flat={flat} a={a.reshape(-1)[flat].item()} b={b.reshape(-1)[flat].item()}"


def run_case(name, pool_cpu, pbs, idx_cpu, fill=0xCD):
    pool = pool_cpu.to(DEV)
    src_u8 = pool.reshape(-1)
    src_fp8 = pool.view(torch.float8_e4m3fn).reshape(-1)
    idx = idx_cpu.to(DEV)
    n = idx.numel()
    pages = (n + 63) // 64
    page_bytes = 288 * pbs
    bits = pbs.bit_length() - 1
    outs = {}
    for backend in ("triton", "cuda"):
        dst = torch.full((pages, 37440), fill, dtype=torch.uint8, device=DEV)
        if backend == "triton":
            K._repack_fp4_to_v4_kernel[(n,)](
                src_u8, src_fp8, idx, dst, page_bytes, SRC_PAGE_BITS=bits
            )
        else:
            K._repack_cuda_lib().repack_fp4_to_v4(
                src_u8, src_fp8, idx, dst, page_bytes, bits
            )
        torch.cuda.synchronize()
        outs[backend] = dst.cpu()
    diff = first_diff(outs["triton"], outs["cuda"])
    check(f"memcmp::{name}", diff is None, diff or "byte-identical")
    return outs["triton"], outs["cuda"]


# ------------------------------------------------------------ semantic probes
def footer_floor_check():
    """Zero rows' footer = ue8m0 of the amax floor 1e-4/448 (not zero bytes)."""
    t = torch.tensor(1e-4, dtype=torch.float32) / 448.0
    u = t.view(torch.int32)
    floor_ue8m0 = int(((u >> 23) & 0xFF) + (u & 0x7FFFFF != 0))
    pool = build_pool(1, 256, "random", 404)
    idx = torch.tensor([-1, -1, 0, -1], dtype=torch.int32)
    tr, _ = run_case("footer-floor-probe", pool, 256, idx)
    row3 = tr[0, 3 * 576: 3 * 576 + 576]
    foot = tr[0, 36864 + 3 * 8: 36864 + 3 * 8 + 8]
    check(
        "semantic::zero_row_footer_is_floor",
        foot[:7].tolist() == [floor_ue8m0] * 7 and foot[7].item() == 0,
        f"footer={foot.tolist()} floor_ue8m0={floor_ue8m0}",
    )
    zbytes = set(row3.tolist())
    check(
        "semantic::zero_row_payload_is_signed_zero",
        zbytes <= {0x00, 0x80},
        f"distinct payload bytes of a -1 row: {sorted(zbytes)}",
    )


def rope_bf16_check():
    """Re-derive a valid row's rope region in pure torch f32->bf16 and compare."""
    pool = build_pool(1, 256, "scales_edge", 707)
    idx = torch.tensor([5], dtype=torch.int32)
    tr, _ = run_case("rope-probe", pool, 256, idx)
    pbs = 256
    slot = 5
    rope_packed = pool[0, slot * 256 + 224: slot * 256 + 256]
    scale_bytes = pool[0, pbs * 256 + slot * 32: pbs * 256 + slot * 32 + 32]
    scales = scale_bytes[28:].view(torch.float8_e4m3fn).to(torch.float32)
    vals = []
    for j in range(32):
        b = int(rope_packed[j])
        g = float(scales[j // 8])
        vals.append(E2M1_LUT_SIGNED[b & 0xF] * g)
        vals.append(E2M1_LUT_SIGNED[b >> 4] * g)
    exp_bf16 = torch.tensor(vals, dtype=torch.float32).to(torch.bfloat16)
    got = tr[0, 448: 576].view(torch.bfloat16)
    ok = torch.equal(exp_bf16, got)
    check("semantic::rope_bf16_exact", ok,
          "" if ok else f"first mismatch at {int((exp_bf16 != got).nonzero()[0])}")


def nope_fp8_check():
    """Re-derive a valid row's nope payload (amax->ue8m0->inv->e4m3) in torch."""
    pool = build_pool(1, 256, "codes256", 808)
    idx = torch.tensor([9], dtype=torch.int32)
    tr, _ = run_case("nope-probe", pool, 256, idx)
    pbs, slot = 256, 9
    packed = pool[0, slot * 256: slot * 256 + 224]
    scale_bytes = pool[0, pbs * 256 + slot * 32: pbs * 256 + slot * 32 + 28]
    scales = scale_bytes.view(torch.float8_e4m3fn).to(torch.float32)
    lut = torch.tensor(E2M1_LUT + [-v for v in E2M1_LUT])
    grp = torch.arange(224) // 8          # per-16-value source scale group
    tile = torch.arange(224) // 32        # V4 tile of each packed byte
    vlo = lut[(packed & 0xF).to(torch.int64)] * scales[grp]
    vhi = lut[(packed >> 4).to(torch.int64)] * scales[grp]
    amax = torch.stack([vlo.view(7, 32), vhi.view(7, 32)]).abs().amax(dim=(0, 2))
    scale_raw = torch.maximum(amax, torch.full_like(amax, 1e-4)) / 448.0
    u = scale_raw.view(torch.int32)
    ue8m0 = ((u >> 23) & 0xFF) + (u & 0x7FFFFF != 0).to(torch.int32)
    inv = ((254 - ue8m0) << 23).view(torch.float32)
    plo = (vlo * inv[tile]).to(torch.float8_e4m3fn).view(torch.uint8)
    phi = (vhi * inv[tile]).to(torch.float8_e4m3fn).view(torch.uint8)
    exp3 = torch.empty(448, dtype=torch.uint8)
    exp3[0::2] = plo
    exp3[1::2] = phi
    got = tr[0, : 448]
    ok = torch.equal(exp3, got)
    foot = tr[0, 36864: 36864 + 8]
    check("semantic::nope_fp8_exact", ok, "" if ok else "payload mismatch")
    check("semantic::footer_matches_torch",
          foot[:7].tolist() == ue8m0.tolist() and foot[7].item() == 0,
          f"foot={foot.tolist()} exp={ue8m0.tolist()}")


# ------------------------------------------------------- backend switch units
def backend_switch_checks():
    prev = os.environ.get(K.ENV_REPACK_BACKEND)
    try:
        os.environ[K.ENV_REPACK_BACKEND] = "triton"
        b = K._repack_backend()
        check("backend::env_triton_lock", b == ("triton", "triton"), str(b))
        os.environ[K.ENV_REPACK_BACKEND] = "cuda"
        b = K._repack_backend()
        check("backend::env_cuda_selects_cuda", b == ("cuda", "cuda"), str(b))
        os.environ.pop(K.ENV_REPACK_BACKEND)
        b = K._repack_backend()
        check("backend::auto_defaults_cuda", b == ("cuda", "auto"), str(b))
        # broken .so -> auto falls back to triton (fail-safe direction)
        mod, err = K._cuda_repack_mod, K._cuda_repack_error
        K._cuda_repack_mod, K._cuda_repack_error = None, "synthetic failure"
        b = K._repack_backend()
        K._cuda_repack_mod, K._cuda_repack_error = mod, err
        check("backend::broken_so_falls_back_to_triton", b == ("triton", "auto"), str(b))
        os.environ[K.ENV_REPACK_BACKEND] = "cuda"
        K._cuda_repack_mod, K._cuda_repack_error = None, "synthetic failure"
        b = K._repack_backend()
        K._cuda_repack_mod, K._cuda_repack_error = mod, err
        check("backend::explicit_cuda_unavailable_still_fails_safe",
              b == ("triton", "cuda"), str(b))
    finally:
        if prev is None:
            os.environ.pop(K.ENV_REPACK_BACKEND, None)
        else:
            os.environ[K.ENV_REPACK_BACKEND] = prev


def wrapper_level_check():
    """Full wrapper path with the backend env lock: triton vs cuda snapshots."""
    from sglang.srt.runtime_context import get_resources

    pool = build_pool(4, 256, "random", 909).to(DEV)
    idx = torch.randint(0, 4 * 256, (37,), dtype=torch.int32, device=DEV)
    idx[::5] = -1
    snaps = {}
    for be in ("triton", "cuda"):
        os.environ[K.ENV_REPACK_BACKEND] = be
        view, ids = K.repack_fp4_extra_to_v4(pool, idx, 256)
        torch.cuda.synchronize()
        snaps[be] = (torch.as_strided(view, (view.shape[0], 37440), (37440, 1), 0).cpu().clone(),
                     ids.cpu().clone())
    diff = first_diff(snaps["triton"][0], snaps["cuda"][0])
    check("wrapper::triton_vs_cuda_env_lock", diff is None, diff or "byte-identical")
    check("wrapper::ids_identity", torch.equal(snaps["triton"][1], snaps["cuda"][1]))
    os.environ.pop(K.ENV_REPACK_BACKEND, None)


def discrimination_check():
    """Flip one byte in an otherwise-identical result; the comparator MUST fire."""
    pool = build_pool(1, 256, "random", 123)
    idx = torch.tensor([3], dtype=torch.int32)
    tr, cu = run_case("discrimination-base", pool, 256, idx)
    assert torch.equal(tr, cu)
    cu2 = cu.clone()
    cu2[0, 1234] ^= 0xFF
    diff = first_diff(tr, cu2)
    check("gate_discrimination::flipped_byte_detected", diff is not None, diff)


def main():
    free, _ = torch.cuda.mem_get_info()
    print(f"GPU free: {free / 2**20:.0f} MiB")
    assert free > 200 * 2**20, "less than 200 MiB free; aborting"

    # (name, pages, pbs, kind, idxkind, n)
    cases = [
        ("n1_random_mixed", 2, 256, "random", "mixed", 1),
        ("n63_random_mixed", 2, 256, "random", "mixed", 63),
        ("n64_random_mixed", 2, 256, "random", "mixed", 64),
        ("n65_random_mixed", 2, 256, "random", "mixed", 65),
        ("n512_random_mixed", 8, 256, "random", "mixed", 512),
        ("n2048_random_mixed", 16, 256, "random", "mixed", 2048),
        ("n16384_random_dense", 64, 256, "random", "valid_dense", 16384),
        ("n512_all_neg1", 4, 256, "random", "all_neg1", 512),
        ("n64_codes256_dense", 2, 256, "codes256", "valid_dense", 64),
        ("n65_codes256_mixed", 2, 256, "codes256", "mixed", 65),
        ("n64_scales_edge_dense", 2, 256, "scales_edge", "valid_dense", 64),
        ("n512_scales_edge_mixed", 4, 256, "scales_edge", "mixed", 512),
        ("n64_zero_data_floor", 2, 256, "zero_data", "valid_dense", 64),
        ("n64_zero_scale", 2, 256, "zero_scale", "valid_dense", 64),
        ("n128_all_zeros", 2, 256, "zeros", "valid_dense", 128),
        ("n64_neg_zero", 2, 256, "neg_zero", "valid_dense", 64),
        ("n48_boundary_pbs256", 3, 256, "random", "boundary", 48),
        ("n97_boundary_scales", 3, 256, "scales_edge", "boundary", 97),
        ("n64_pbs128_mixed", 2, 128, "random", "mixed", 64),
        ("n65_pbs128_codes", 2, 128, "codes256", "mixed", 65),
        ("n512_pbs128_boundary", 4, 128, "scales_edge", "boundary", 512),
        ("n128_pbs128_neg1", 2, 128, "random", "all_neg1", 128),
    ]
    for i, (name, pages, pbs, kind, ik, n) in enumerate(cases):
        pool = build_pool(pages, pbs, kind, seed=1000 + i)
        idx = build_idx(ik, n, pages * pbs, seed=1000 + i)
        run_case(name, pool, pbs, idx)
        if i % 6 == 5:
            torch.cuda.empty_cache()

    footer_floor_check()
    rope_bf16_check()
    nope_fp8_check()
    backend_switch_checks()
    wrapper_level_check()
    discrimination_check()

    print(f"\n==== {len(PASS)} passed, {len(FAIL)} failed ====")
    if FAIL:
        print("FAILED:", *FAIL, sep="\n  ")
        sys.exit(1)
    print("BIT-EQUALITY GATE: ALL GREEN")


if __name__ == "__main__":
    main()
