# Runtime snapshot — 0.3.2 baseline, 2026-10-22T01:17Z

Collected read-only before any image or cache cleanup. Raw JSON for each host is
stored on `DGXspark02:~/checkpoints/0.3.2-baseline-20261022/runtime/`; this page
is the sanitized summary committed to git. Container `Config.Env` was explicitly
excluded from the snapshot.

| Host | Role | Main container | Local image ID | Storage | API probe |
|---|---|---|---|---|---|
| dgxspark01 | head | `r3prod-head` | `sha256:47f6d91ada98…` | overlayfs (containerd) | `http://127.0.0.1:8899/health` → 200 |
| dgxspark02 | worker + registry | `r3prod-worker` | `sha256:ef64dec3d74b…` | overlay2 | `http://127.0.0.1:30000/health` → 200 |
| dgxspark03 | worker | `r3prod-worker` | `sha256:ef64dec3d74b…` | overlay2 | `http://127.0.0.1:30000/health` → 200 |
| dgxspark04 | worker | `r3prod-worker` | `sha256:ef64dec3d74b…` | overlay2 | `http://127.0.0.1:30000/health` → 200 |

Head also answered `/health_generate` → 200 and `/get_model_info` → 200 with
`served_model_name=deepseek-v4.1-flash` and `model_path=/models/DeepSeek-V4.1-Flash`.

## Containers observed running

- **dgxspark01**: `r3prod-head`, `aicad-node-exporter`, `aicad-dcgm-exporter`, `aicad-fw-25000`.
- **dgxspark02**: `r3prod-worker`, `registry`, `node-exporter`, `dcgm-exporter`.
- **dgxspark03**: `r3prod-worker`, `aicad-node-exporter`, `aicad-dcgm-exporter`.
- **dgxspark04**: `r3prod-worker`, `aicad-node-exporter`, `aicad-dcgm-exporter`.

All main containers use host networking. The runtime snapshot captures mounts,
network settings, restart policy, state and health fields; it does not include
environment values.

## systemd state

| Unit | 01 | 02 | 03 | 04 |
|---|---|---|---|---|
| `oom-gate-monitor.service` | active (pid 278786) | active | active | active |
| `r3-watchdog-head.service` | active | absent | absent | absent |
| `r3-watchdog-worker.service` | absent | active | absent | absent |
| `daily-smoke.timer` | active | absent | absent | absent |
| `nvmodule-guard.service` | active (oneshot) | active (oneshot) | active (oneshot) | active (oneshot) |

`oom-gate-monitor` on 02 and `r3-watchdog-worker` on 02 are the two protected
domains from the cluster safety rules; they were only read, never touched.

## Mounts relevant to rollback

- Head `r3prod-head`: read-only bind mounts from `~/migrate-assets/v4vl/…` plus
  `/data/models/DeepSeek-V4.1-Flash-1017` at `/models/DeepSeek-V4.1-Flash`.
- Workers: read-only `~/migrate-assets/v4vl/…`, `~/migrate-assets/b12x`,
  `~/migrate-assets/dsv41/adapter` where present, current model path and
  `~/dsv41-engram-1017`.
- DGXspark03 mounts `10.10.1.11:/home/<deploy-user>/models/DeepSeek-V4-Flash-Vision-Exp`
  and `…/deepseek-v4-flash-0731` as old NFS exports; DGXspark04 mounts the
  corresponding 02 exports. These are old-model mounts, not current 0.3.2
  dependencies.

## GPU / load at snapshot time

All four hosts reported `NVIDIA GB10`; utilization was 94–96%. DGXspark03's
audit noted ~14.3 GiB MemAvailable and load average 14.92 at 13:23 UTC, so
archive work should be scheduled outside production pressure. No container was
started, stopped or restarted for this snapshot.
