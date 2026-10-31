"""A23 prefill-AR cluster probe: E0 (transport viability, four faces) + E1
(parity faces).

Runs ONLY inside the A23 window on a live 4-node TP4 boot (DESIGN.md §八,
A23-WINCARD-20261006 J-gates).  Desk behaviour: with no CUDA/torch/distributed
the whole probe auto-skips green (same layer-3 pattern as
dev/o13-tlsegment/test_e1_m_invariance.py) -- this file is design-registered,
not desk-executed.

v2 (2026-10-06): the hedge-order faces are first-class.  Routing verdict
(docs/research/COMMUNITY-R2-BLOCKED-FACES-20261006.md, 主会话路由裁定 face 3):
if E0 confirms the wash hypothesis on the ring topology, the hedge order is
two-shot -> FI FP8 two-shot -> TBO, one-shot structurally yields.  E0 now
times FOUR faces per size:

    nccl     fused ring AR (torch.distributed.all_reduce)      -- baseline
    oneshot  the b12x second runtime (v1 arm form)             -- G3 judged
    twoshot  RS+AG two-step (reduce_scatter_tensor +
             all_gather_into_tensor, 1.5N byte tax)            -- hedge #1
    fi_fp8   flashinfer.comm.quantized_all_reduce (FP8 two-shot,
             signature pinned in overlay/a23_forms.py)         -- hedge #2

Per-face failures (e.g. FI symm-mem rendezvous over RoCE) are recorded as
face errors, not probe crashes; a face that cannot even resolve reports
UNAVAILABLE.

Pre-registered lines:
    G3 (unchanged): the oneshot arm may only be judged when
        oneshot_ms <= 1.25 x nccl_ms at the band top (42 MiB); red = wash
        hypothesis confirmed -> close window, hedge order takes over.
    Hedge faces (v2): twoshot_ms and fi_fp8_ms are recorded per size with
        ratios vs nccl; they FEED the hedge-order decision, they do not gate
        the oneshot arm.  Reference lines (report-only): twoshot
        interesting when ratio < 1.0; fi_fp8 informational (different
        numerics: FP8 lossy -- see E1).

E1 -- parity faces (DESIGN.md §4):
    oneshot/twoshot: A-face pre-registered tolerance band vs NCCL (bf16
        ulps at the accumulation scale; pass: median<=1, max<=3, P(>2)==0).
    oneshot only: B-face deterministic bit-equal form (b1 canonical-order
        bitwise, b2 cross-rank, b3 repeat) -- twoshot shares NCCL reduction
        orders, so its B-face vs the canonical reference does not apply
        (b2/b3 determinism faces still do).
    fi_fp8: FP8 E4M3 per-block scaling is a LOSSY form: record-only diff
        telemetry (max_absdiff, relative-error quantiles) -- no pass line.
        Its gate is the C-face semantic window (win card §四), never a ulp
        band.  Two faces, separately recorded; one may never excuse the
        other.
    Known pathologies always first (reverse cases, A22 assertion doctrine):
        order-sensitive tensor MUST yield a nonzero diff, invariant tensors
        MUST be exactly equal -- else PROBE-RED without judging the arm.

Usage (window): torchrun --nproc_per_node=4 probe_a23_ar_parity.py \
    [--sizes 1,4,16,32,42] [--reps 20] [--out /tmp/a23_probe.json]

Desk: python3 probe_a23_ar_parity.py  -> prints SKIP lines, exits 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a23_parity_core as core  # noqa: E402  (thresholds live in one place)


def _have_stack() -> bool:
    try:
        import torch  # noqa: F401
        import torch.distributed  # noqa: F401
    except Exception:
        return False
    return os.environ.get("A23_PROBE_LIVE") == "1" and _cuda_ok()


def _cuda_ok() -> bool:
    try:
        import torch

        return torch.cuda.is_available() and torch.cuda.device_count() > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# desk stub
# ---------------------------------------------------------------------------

def main() -> int:
    if not _have_stack():
        print("SKIP: A23 probe needs a live torch.distributed + CUDA boot "
              "(A23_PROBE_LIVE=1); desk run is design-registered only.")
        print("SKIP: pre-registered lines are in a23_parity_core.py "
              f"(A_FACE_MAX_ULP={core.A_FACE_MAX_ULP}, band "
              f"{core.DEFAULT_PREFILL_MIN_BYTES}..{core.DEFAULT_PREFILL_MAX_BYTES}).")
        print("SKIP: E0 faces = nccl/oneshot/twoshot/fi_fp8 (hedge order "
              "two-shot -> FI FP8 -> TBO; COMMUNITY-R2 路由裁定 face 3).")
        return 0

    import torch
    import torch.distributed as dist

    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default="1,4,16,32,42",
                        help="MiB sizes for E0/E1, ASCENDING (fi_fp8 symm "
                             "buffer grows on first sight; default 1,4,16,32,42)")
    parser.add_argument("--reps", type=int, default=20)
    parser.add_argument("--out", default="/tmp/a23_probe_report.json")
    args = parser.parse_args()

    dist.init_process_group("nccl")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.cuda.set_device(rank % torch.cuda.device_count())
    device = torch.device("cuda", rank % torch.cuda.device_count())

    report: dict = {"rank": rank, "world": world, "e0": {}, "e1": {}}

    # -- build the prefill-band runtime exactly like the adapter does ---------
    from b12x.comm.roce_ring import AllReduce  # migrate-assets tree on PYTHONPATH

    runtime = AllReduce.from_process_group(
        process_group=dist.group.WORLD,
        device=device,
        max_size=core.DEFAULT_PREFILL_MAX_BYTES,
    )
    runtime.prepare((torch.bfloat16,))

    # -- hedge face #2: FI FP8 two-shot (signature pinned in overlay/) --------
    fi_fn, fi_resolve_err = None, None
    try:
        from overlay.a23_forms import resolve_fi_quantized_all_reduce

        fi_fn = resolve_fi_quantized_all_reduce()
    except Exception as e:                    # desk/window FI absence: record
        fi_resolve_err = f"{type(e).__name__}: {e}"[:200]

    def twoshot_op(t):
        shard = torch.empty(t.numel() // world, dtype=t.dtype, device=t.device)
        dist.reduce_scatter_tensor(shard, t.view(-1), group=dist.group.WORLD)
        dist.all_gather_into_tensor(t.view(-1), shard, group=dist.group.WORLD)
        return t

    sizes_mib = [int(s) for s in args.sizes.split(",")]

    # -- E1a: known pathologies first (probe discriminating power) ------------
    pathos = _probe_pathologies(torch, dist, runtime, device)
    report["e1"]["pathologies"] = pathos
    probe_ok = (
        pathos["order_sensitive"]["nonzero_diff_seen"]
        and pathos["invariant"]["all_equal"]
    )
    report["e1"]["probe_power"] = "OK" if probe_ok else "PROBE-RED"

    # -- E1b/E0 per size -------------------------------------------------------
    for mib in sizes_mib:
        n = mib * 1024 * 1024 // 2
        torch.manual_seed(1234 + rank)   # per-rank distinct shards
        x = (torch.randn(n, device=device, dtype=torch.float32) * 0.5).to(torch.bfloat16)

        # B-face b1: canonical reference in fixed rank order, fp32 acc, one round
        shards = [torch.empty_like(x) for _ in range(world)]
        dist.all_gather(shards, x)
        ref = shards[0].to(torch.float32)
        for s in shards[1:]:
            ref = ref + s.to(torch.float32)          # fp32 accumulate, rank order
        ref = ref.to(torch.bfloat16)                 # single rounding

        # B-face b3: repeat determinism
        out1 = runtime.all_reduce(x.clone())
        out2 = runtime.all_reduce(x.clone())
        b3 = bool(torch.equal(out1, out2))

        # B-face b1: bitwise vs reference
        b1 = bool(torch.equal(out1, ref))
        max_absdiff = float((out1.to(torch.float32) - ref.to(torch.float32)).abs().max())

        # B-face b2: cross-rank identical bits
        gathered = [torch.empty_like(out1) for _ in range(world)]
        dist.all_gather(gathered, out1)
        b2 = all(torch.equal(g, out1) for g in gathered)

        # A-face: NCCL same tensor (baseline for oneshot AND twoshot bands)
        nccl_out = x.clone()
        dist.all_reduce(nccl_out)
        band_oneshot = _a_face_band(out1, nccl_out, x, ref, core, f"{mib}MiB.oneshot")

        # hedge #1 -- twoshot: A-face band (NCCL-order class) + b2/b3 only
        ts1 = twoshot_op(x.clone())
        ts2 = twoshot_op(x.clone())
        ts_gathered = [torch.empty_like(ts1) for _ in range(world)]
        dist.all_gather(ts_gathered, ts1)
        band_twoshot = _a_face_band(ts1, nccl_out, x, ref, core, f"{mib}MiB.twoshot")
        twoshot_e1 = {
            "b2_cross_rank": all(torch.equal(g, ts1) for g in ts_gathered),
            "b3_repeat": bool(torch.equal(ts1, ts2)),
            "a_face": band_twoshot.as_dict(),   # 2026-10-07 window fix: raw BandReport
            # broke the verdict block + rank0 json dump (not subscriptable); the
            # oneshot face already used .as_dict() -- same treatment.
            "b1_note": "N/A: twoshot shares NCCL reduction orders; the B-face "
                       "vs the canonical reference does not apply (two faces, "
                       "separately recorded)",
        }

        # hedge #2 -- fi_fp8: RECORD-ONLY telemetry (lossy form, C-face gates)
        fi_e1 = {"record_only": True, "available": fi_fn is not None}
        if fi_fn is not None:
            try:
                fi1 = fi_fn(x.clone(), dist.group.WORLD)
                d = (fi1.to(torch.float32) - nccl_out.to(torch.float32)).abs()
                rel = d / nccl_out.to(torch.float32).abs().clamp_min(1e-6)
                fi_e1.update({
                    "max_absdiff": float(d.max()),
                    "mean_reldiff": float(rel.mean()),
                    "p99_reldiff": float(rel.flatten().kthvalue(
                        max(1, int(rel.numel() * 0.99))).values),
                })
            except Exception as e:
                fi_e1["error"] = f"{type(e).__name__}: {e}"[:200]

        # E0: timed faces (CUDA events, median of reps).  fi_fp8 errors are
        # face-level records (UNAVAILABLE), never probe crashes.
        faces = {
            "nccl": (lambda t: dist.all_reduce(t), True),
            "oneshot": (lambda t: runtime.all_reduce(t), True),
            "twoshot": (twoshot_op, True),
            "fi_fp8": ((lambda t: fi_fn(t, dist.group.WORLD))
                       if fi_fn is not None else None),
        }
        face_ms, face_err = {}, {}
        for name, op in faces.items():
            if op is None:
                face_err[name] = fi_resolve_err or "unavailable"
                continue
            op0 = op[0] if isinstance(op, tuple) else op   # 2026-10-07 window fix:
            # faces values are (fn, available) tuples; the E0 loop passed the raw
            # tuple to _time_op -> 'tuple' object is not callable (face-level error
            # on every size; E1 faces were unaffected).
            try:
                face_ms[name] = _time_op(op0, x.clone(), args.reps)
            except Exception as e:
                face_err[name] = f"{type(e).__name__}: {e}"[:200]

        e0_entry = {
            "nccl_ms_med": face_ms.get("nccl"),
            "roce_ms_med": face_ms.get("oneshot"),
            "ratio": (round(face_ms["oneshot"] / max(face_ms["nccl"], 1e-9), 4)
                      if "oneshot" in face_ms and "nccl" in face_ms else None),
        }
        for name in ("twoshot", "fi_fp8"):
            e0_entry[f"{name}_ms_med"] = face_ms.get(name)
            e0_entry[f"{name}_ratio_vs_nccl"] = (
                round(face_ms[name] / max(face_ms["nccl"], 1e-9), 4)
                if name in face_ms and "nccl" in face_ms else None
            )
        if face_err:
            e0_entry["face_errors"] = face_err
        report["e0"][f"{mib}MiB"] = e0_entry

        report["e1"][f"{mib}MiB"] = {
            "b1_bit_equal": b1, "b1_max_absdiff": max_absdiff,
            "b2_cross_rank": b2, "b3_repeat": b3,
            "a_face": band_oneshot.as_dict(),
            "twoshot": twoshot_e1,
            "fi_fp8": fi_e1,
        }

    # -- verdicts (pre-registered; printed on every rank, saved on rank 0) ----
    top = f"{sizes_mib[-1]}MiB"
    top_e0 = report["e0"][top]
    e0_pass = (
        top_e0["ratio"] is not None and top_e0["ratio"] <= 1.25
    )
    ts_ratio = top_e0.get("twoshot_ratio_vs_nccl")
    fi_ms = top_e0.get("fi_fp8_ms_med")
    b_face_pass = all(
        v.get("b1_bit_equal") and v.get("b1_max_absdiff") == 0.0
        and v.get("b2_cross_rank") and v.get("b3_repeat")
        for k, v in report["e1"].items() if k.endswith("MiB")
    )
    a_face_pass = all(
        v["a_face"]["pass_line"] for k, v in report["e1"].items()
        if isinstance(v, dict) and "a_face" in v
    )
    ts_a_pass = all(
        v["twoshot"]["a_face"]["pass_line"] for k, v in report["e1"].items()
        if isinstance(v, dict) and "twoshot" in v
    )
    report["verdict"] = {
        "e0_transport": "PASS" if e0_pass else "FAIL(wash->close window)",
        "e0_hedge_twoshot": (
            f"ratio={ts_ratio} (record: <1.0 = hedge-order candidate)"
            if ts_ratio is not None else "UNAVAILABLE"
        ),
        "e0_hedge_fi_fp8": (
            f"ms={fi_ms} (informational; lossy FP8 numerics, C-face gates)"
            if fi_ms is not None else
            f"UNAVAILABLE ({top_e0.get('face_errors', {}).get('fi_fp8', 'unresolved')})"
        ),
        "e1_b_face": "PASS" if b_face_pass else "FAIL(form)",
        "e1_a_face": "PASS" if a_face_pass else "FAIL(band)",
        "e1_twoshot_a_face": "PASS" if ts_a_pass else "FAIL(band)",
        "e1_fi_fp8": "RECORD-ONLY (C-face semantic window gates this form)",
        "probe_power": report["e1"]["probe_power"],
    }
    print(f"[a23-probe rank={rank}] {json.dumps(report['verdict'])}", flush=True)
    if rank == 0:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[a23-probe] full report -> {args.out}")
    runtime.close()
    dist.destroy_process_group()
    return 0


def _a_face_band(candidate, nccl_out, x, ref, core, label):
    """A-face ulp histogram of `candidate` vs the NCCL output (shared math)."""
    import torch

    diffs = (candidate.to(torch.float32) - nccl_out.to(torch.float32)).abs()
    scale = torch.stack(
        [x.to(torch.float32).abs().max(dim=0).values,
         nccl_out.to(torch.float32).abs().max(dim=0).values,
         ref.to(torch.float32).abs().max(dim=0).values]
    ).max(dim=0).values.clamp_min(1e-30)
    ulps = (diffs / (scale * (2.0 ** -core.BF16_MANTISSA_BITS))).round().long()
    hist = torch.bincount(ulps.clamp(max=core.A_FACE_MAX_ULP + 1),
                          minlength=core.A_FACE_MAX_ULP + 2)
    return core.BandReport(
        {int(k): int(v) for k, v in enumerate(hist.tolist()) if v},
        label=label,
    )


def _time_op(op, tensor, reps: int) -> float:
    import torch

    for _ in range(3):                      # warmup
        op(tensor)
    torch.cuda.synchronize()
    times = []
    for _ in range(reps):
        s, e = torch.cuda.Event(True), torch.cuda.Event(True)
        s.record()
        op(tensor)
        e.record()
        torch.cuda.synchronize()
        times.append(s.elapsed_time(e))
    times.sort()
    return times[len(times) // 2]


def _probe_pathologies(torch, dist, runtime, device) -> dict:
    """Reverse cases (DESIGN.md §4.3): the probe must discriminate.

    2026-10-07 window fix: the b12x runtime's should_allreduce floor is
    nbytes % PACK_BYTES(16) == 0 (roce_oneshot.py:449-464) -- the original
    4-element (8-byte) pathology tensors were BELOW the eligibility floor and
    raised "input is not eligible". The cases are padded to 128 B (64 bf16
    elements): the pathological values sit at [0:world], the tail is a
    constant (0.25, a power of two -- exactly order-invariant), so the
    discriminating-power contract is unchanged: element 0 must show the
    order-sensitive ulp diff, the tail must be bitwise equal under any order.
    """
    world = dist.get_world_size()
    out = {"order_sensitive": {}, "invariant": {}}

    # case 1 (per-rank slots, DESIGN §4.3 病例1): rank r's tensor carries ITS value
    # at slot 0's contribution row -- element0 receives [1.0, t, t, t] across ranks
    # -> the order-sensitive sum; tail 0.25 (power of two) is order-invariant.
    # 2026-10-07 window fix: the first padded form put the SAME [1.0,t,t,t] tensor
    # on every rank -- 4x an identical value is exact in any order, so the case
    # lost discriminating power (probe_power=PROBE-RED, nonzero_diff_seen=False).
    tiny = 2.0 ** -9
    rank = dist.get_rank()
    n = 64                                   # 128 B: above the %16 floor
    x = torch.full((n,), 0.25, device=device, dtype=torch.bfloat16)
    x[0] = 1.0 if rank == 0 else tiny
    roce = runtime.all_reduce(x.clone())
    nccl = x.clone()
    dist.all_reduce(nccl)
    out["order_sensitive"] = {
        "roce": float(roce[0]),
        "nccl": float(nccl[0]),
        "nonzero_diff_seen": bool(not torch.equal(roce, nccl)),
        "ulp": core.diff_in_ulps_bf16(float(roce[0]), float(nccl[0])),
    }

    # case 2: identical values across ranks -> every order exact
    x2 = torch.full((n,), 0.25, device=device, dtype=torch.bfloat16)
    roce2 = runtime.all_reduce(x2.clone())
    nccl2 = x2.clone()
    dist.all_reduce(nccl2)
    out["invariant"] = {
        "roce": float(roce2[0]),
        "nccl": float(nccl2[0]),
        "all_equal": bool(torch.equal(roce2, nccl2)),
    }
    return out


if __name__ == "__main__":
    raise SystemExit(main())
