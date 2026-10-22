# 0.3.2 baseline checkpoint — 2026-10-22

This directory is the **single rollback point for the 0.3.2 production line** after
the 2026-10-22 baseline decision. It supersedes the `0.3.2-r032` and `0.3.2-r032b`
candidate images and all pre-0.3.2 images for future development.

## Canonical image identity

| Item | Value |
|---|---|
| Registry baseline tag | `192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-baseline-20261022` |
| Source tag | `192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c` |
| OCI index digest | `sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4` |
| arm64 manifest digest | `sha256:ad7e362f4fe74cc0706bc13d77839909e0742669b4291b0ac58374967dc2b57e` |
| Config digest | `sha256:ef64dec3d74b577bfcc8f54cc940b87d92701a9d9c3bb3c6c1214133c5e605b2` |
| Layers / compressed size | 71 layers / 14,439,524,460 bytes |
| Uncompressed size | 33,221,760,806 bytes |
| Image version label | `DSV41_IMAGE_VERSION=0.3.2-r032c` |
| Built at / base | `2026-10-18T05:20:00Z` / `DSV41_BASE_DIGEST=80e1ea8979c5` |
| Replay tree | `DSV41_REPLAY_TREE=dab49d96d33839480e30a1d24ac9e6cdb0a9c29d` |

The registry tag is an OCI index. The arm64 manifest inside it resolves to the
config digest above. Docker reports the ID differently depending on the storage
backend:

| Host | Role | Local image ID | Storage backend |
|---|---|---|---|
| dgxspark01 | head | `sha256:47f6d91ada98…` (index digest) | `overlayfs` (containerd snapshotter) |
| dgxspark02 | worker + registry | `sha256:ef64dec3d74b…` (config digest) | `overlay2` |
| dgxspark03 | worker | `sha256:ef64dec3d74b…` (config digest) | `overlay2` |
| dgxspark04 | worker | `sha256:ef64dec3d74b…` (config digest) | `overlay2` |

These are the **same image content**, not two builds: 01 displays the index
digest, 02–04 display the config digest.

## Files in this checkpoint

| File | Purpose |
|---|---|
| `image-r032c-arm64.tar` | Offline `docker save` of the canonical arm64 image (33,591,321,600 bytes) |
| `image-r032c-arm64.tar.sha256` | SHA256 of the image tar |
| `registry/` | OCI index, arm64 manifest, attestation manifest, image inspect, baseline-tag proof |
| `deploy/migrate-assets.tar.zst` | Live deployment assets (`bin/`, `dsv41/`, `v4vl/`, `b12x/`, NCCL tree) |
| `deploy/luz-deepseek-flash-all-in-one.bundle` | Full git bundle of the delivery repo (`main`, `switch-fabric`, tags) |
| `deploy/luz030-opt-campaign.bundle` | Full git bundle of the local campaign repo (all refs) |
| `runtime/` | Read-only container, systemd, NFS, network, GPU and health snapshots |
| `README.md`, `IMAGE-IDENTITY.json`, `RESTORE.sh`, `MANIFEST.md`, `SHA256SUMS` | This checkpoint's documentation and verification |

The image tar is stored only on `DGXspark02` in this checkpoint directory. The
registry also holds the same OCI index under the baseline tag. The tar was
verified with `sha256sum -c` and `tar -tf` before this document was written.

## Restore

### From the registry (fastest)

```bash
docker pull 192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-baseline-20261022
docker image inspect 192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-baseline-20261022 \
  --format '{{json .RepoDigests}}'
# must contain sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4
```

### From the offline tar

```bash
bash RESTORE.sh
```

The script verifies the tar, runs `docker load`, and tags the loaded image
`0.3.2-baseline-20261022`. It does **not** start, stop or restart any container.

### Deployment assets

`deploy/migrate-assets.tar.zst` is a backup of the live assets, not an
overwrite instruction. To inspect or restore on a host:

```bash
zstd -t deploy/migrate-assets.tar.zst
mkdir -p /tmp/migrate-assets-restore
zstd -dc deploy/migrate-assets.tar.zst | tar -C /tmp/migrate-assets-restore -xf -
# compare, then copy only the needed files to the live path
```

The delivery repo bundle is the authoritative source for the public deploy kit.
The image itself already contains the 16-file r032c payload; the overlay,
adapter, b12x and boot/env pieces are in `migrate-assets` and in the delivery
repo at tag `v0.3.2-baseline-20261022`.

## What is intentionally not in this checkpoint

- **Model weights**: `/data/models/DeepSeek-V4.1-Flash-1017` (01/02), `/data/models/dsv41-net` (03/04) and the NFS exports are 476 GB per copy and remain in place. Their 84-file SHA256 manifest and engram manifest are in the delivery repo under `deploy/reconstruct/0.3.2/weights/`.
- **Engram shards**: `~/dsv41-engram-1017` (48 GB per host) remain in place; the 8-shard identity is in `deploy/reconstruct/0.3.2/weights/engram-bins-manifest.json`.
- **0.2.4 checkpoint**: `DGXspark02:~/checkpoint/LuZ-0.2.4-head-image-v14-6d6353d16c2d.tar` remains untouched. It is a pre-0.3.2 rollback copy and is not part of this baseline.
- **Two root-owned 300-byte files** under `migrate-assets/flashinfer-golden/work/0.6.18/sm121/` were excluded from the assets tar because they are unreadable to the deploy user. They are regenerable JIT metadata; the exclusion list is in `deploy/migrate-assets.EXCLUDED.txt`.
- **Old 0.3.1/0.3.2-r032/r032b images and their archives** are handled by the cluster archive/cleanup pass, not by this checkpoint.

## Archive and cleanup closure (2026-10-22)

The pre-0.3.2 archive consolidation and the old image/tag/cache cleanup completed
on 2026-10-22. The 0.3.2 baseline image identity above is unchanged.

- Historical sources are consolidated on `DGXspark02:~/cluster-archive-20261022/`
  (290,063,676,566 bytes, 92,931 files); per-directory checksums and the retained
  paths are in [`ARCHIVE-INDEX.md`](ARCHIVE-INDEX.md).
- Removed images, registry tags, GC result, cache cleanup and host disk changes are
  in [`CLEANUP-20261022.md`](CLEANUP-20261022.md).
- The registry now keeps only `0.3.2-r032c` and `0.3.2-baseline-20261022`, both at
  OCI index digest `sha256:47f6d91a…ffc4`.

## Verification

```bash
cd /path/to/checkpoint
sha256sum -c SHA256SUMS
zstd -t deploy/migrate-assets.tar.zst
git bundle verify deploy/luz-deepseek-flash-all-in-one.bundle
git bundle verify deploy/luz030-opt-campaign.bundle
```

The git tag `v0.3.2-baseline-20261022` in
`luz-deepseek-flash-all-in-one` points at the commit that records this checkpoint.
