#!/usr/bin/env python3
"""µs-level bench: CUDA repack_cuda.cu vs Triton _repack_fp4_to_v4_kernel.

Run INSIDE the r3boot-head container:
    docker exec r3boot-head python3 /opt/dsv41/adapter/tests/bench_repack_cuda.py \
        [--csv /tmp/repack_bench.csv]

CUDA events around each launch (warmup 50 + 200 reps) for kernel-time mean/p50/p99,
plus a python wall-clock loop (single trailing sync) to price the host-side launch
overhead difference. N in {512, 2048, 16384, 65536} covers decode-sized bridges up
to the 512 MiB scratch budget shape. GPU alloc stays < 100 MB (~60 MB peak).
"""
import argparse
import datetime
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch  # noqa: E402

import kv_fp4_repack as K  # noqa: E402

DEV = "cuda"
WARMUP, REPS = 50, 200
SIZES = [512, 2048, 16384, 65536]


def bench_backend(name, launch, n_reps):
    starts = [torch.cuda.Event(enable_timing=True) for _ in range(n_reps)]
    stops = [torch.cuda.Event(enable_timing=True) for _ in range(n_reps)]
    for i in range(n_reps):
        starts[i].record()
        launch()
        stops[i].record()
    torch.cuda.synchronize()
    us = sorted(starts[i].elapsed_time(stops[i]) * 1000.0 for i in range(n_reps))
    mean = sum(us) / len(us)
    p50 = us[len(us) // 2]
    p99 = us[min(len(us) - 1, int(round(0.99 * (len(us) - 1))))]
    return mean, p50, p99


def wall_backend(launch, n_reps):
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for _ in range(n_reps):
        launch()
    torch.cuda.synchronize()
    return (time.perf_counter() - t0) / n_reps * 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/tmp/repack_bench.csv")
    args = ap.parse_args()

    free, _ = torch.cuda.mem_get_info()
    print(f"GPU free: {free / 2**20:.0f} MiB")
    assert free > 200 * 2**20, "less than 200 MiB free; aborting"

    lib = K._repack_cuda_lib()
    g = torch.Generator().manual_seed(20261001)
    rows_out = []
    print(f"{'N':>7} {'backend':>7} {'mean_us':>10} {'p50_us':>10} {'p99_us':>10} {'wall_us':>10}")

    for n in SIZES:
        pages = max(1, -(-n // 256))  # pbs-256 pool pages covering n slots
        pool = torch.randint(0, 256, (pages, 288 * 256), dtype=torch.uint8, generator=g).to(DEV)
        # drop NaN-looking scale bytes for realism (prod scales are finite)
        sc = pool[:, 256 * 256:]
        sc[(sc == 0x7F) | (sc == 0xFF)] = 0x38
        idx_cpu = torch.randint(0, pages * 256, (n,), dtype=torch.int64, generator=g)
        idx_cpu[::7] = -1
        idx = idx_cpu.to(device=DEV, dtype=torch.int32).contiguous()
        dst_pages = (n + 63) // 64
        dst = torch.empty(dst_pages, 37440, dtype=torch.uint8, device=DEV)
        src_u8 = pool.reshape(-1)
        src_fp8 = pool.view(torch.float8_e4m3fn).reshape(-1)
        page_bytes = 288 * 256

        launches = {
            "triton": lambda: K._repack_fp4_to_v4_kernel[(n,)](
                src_u8, src_fp8, idx, dst, page_bytes, SRC_PAGE_BITS=8
            ),
            "cuda": lambda: lib.repack_fp4_to_v4(
                src_u8, src_fp8, idx, dst, page_bytes, 8
            ),
        }
        res = {}
        for be, fn in launches.items():
            for _ in range(WARMUP):
                fn()
            torch.cuda.synchronize()
            mean, p50, p99 = bench_backend(be, fn, REPS)
            wall = wall_backend(fn, REPS)
            res[be] = (mean, p50, p99, wall)
            print(f"{n:>7} {be:>7} {mean:>10.2f} {p50:>10.2f} {p99:>10.2f} {wall:>10.2f}")
            rows_out.append((n, be, mean, p50, p99, wall))
        sp = res["triton"][0] / res["cuda"][0]
        spw = res["triton"][3] / res["cuda"][3]
        print(f"        -> kernel speedup x{sp:.2f} (wall x{spw:.2f})")
        del pool, dst, idx, src_u8, src_fp8
        torch.cuda.empty_cache()

    host = os.uname().nodename
    os.makedirs(os.path.dirname(args.csv) or ".", exist_ok=True)
    new = not os.path.exists(args.csv)
    with open(args.csv, "a") as f:
        if new:
            f.write("host,date,n,backend,mean_us,p50_us,p99_us,wall_us\n")
        for n, be, mean, p50, p99, wall in rows_out:
            f.write(
                f"{host},{datetime.datetime.now().isoformat(timespec='seconds')},"
                f"{n},{be},{mean:.2f},{p50:.2f},{p99:.2f},{wall:.2f}\n"
            )
    print(f"CSV appended: {args.csv}")


if __name__ == "__main__":
    main()
