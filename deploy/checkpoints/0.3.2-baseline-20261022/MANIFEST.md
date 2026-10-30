# 0.3.2 baseline checkpoint manifest — 2026-10-22

This manifest covers the git-committed checkpoint documentation. The large

external assets live on `<node02>:~/checkpoints/0.3.2-baseline-20261022/`

and are listed separately below with their SHA256 values.

> 20261030 脱敏注记：本清单及各件中的 registry 主机、节点主机名与家目录已改占位符；
> `registry/` 两件 inspect 件由内网主机形原名相应改名为 `image-inspect-node0N.json`，
> 下表哈希与字节数均为脱敏后实算值。

## Committed files

| Path | Bytes | SHA256 |
|---|---:|---|
| `ARCHIVE-INDEX.md` | 7028 | `cb44fa3e966baacba0f48c67d558d7739b15bc5b538ed59eab1f992bcc321966` |
| `CLEANUP-20261022.md` | 5870 | `c2d9fb825ec4020b26f4000590c2ef26db71ec7afb92dd30011b05b323055db7` |
| `IMAGE-IDENTITY.json` | 3749 | `6bbde788dbc6f74072cf6a236c874ea6ec5bf87e27c44c06cbc4fff7d2241251` |
| `README.md` | 6264 | `8c57d1d57e5c419175689a8fc6cc3f9fc77179ad2ee046c4204e5fd5772e4613` |
| `RESTORE.sh` | 1884 | `c0a6c7fcc3127670f47a74b716c900b3e7e251d418f2625aee4f3575c4f3f0ce` |
| `deploy/migrate-assets.EXCLUDED.txt` | 428 | `fb45eeb560893ca304b9cf090125a21c6e6189f1b8d48e461ee1398906ef2c13` |
| `deploy/migrate-assets.FILES.txt` | 59012 | `684a969457de4a86127747eb4d5aa2f1b35a4e605c0e33acdf47c090286b936c` |
| `registry/arm64-manifest.json` | 13862 | `ad7e362f4fe74cc0706bc13d77839909e0742669b4291b0ac58374967dc2b57e` |
| `registry/attestation-manifest.json` | 566 | `c24cf49ac63cb2f820df2f4fe0ab8039f7bc5b02eb803eb7c1f8c0e61d049153` |
| `registry/baseline-tag-put.headers` | 397 | `886f5b371a42cbb606cf81c3eb84fe2a3f07ace4645bf07be43cb01b746104fc` |
| `registry/baseline-tag-verify.txt` | 217 | `8a86c2fc8b73dbb828b7637c9e57cf6afb04501f877598e4d71b93a43ea482ea` |
| `registry/image-inspect-node01.json` | 1820 | `6e393e4612bcf68e986bd8cd34d97107077f33fdacb20923b414a99c6f0774f8` |
| `registry/image-inspect-node02.json` | 1634 | `0e906f8d49678d283cbd07fb0afee1d7324f71e08bb3e1e91ee2b306308d5e1c` |
| `registry/index-r032c.json` | 857 | `47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4` |
| `registry/removed-tags-20261022.txt` | 739 | `dcaf8e840ff13fd06e307b2b22b965c5d3ee15ce22fc3546b5958082a9ed0ffc` |
| `runtime-summary.md` | 3183 | `724954866ec0d063084fee2c21fa4d33ed151a148a63c2bcaaa75680142f37b3` |

## External assets on <node02>

> Git bundles are regenerated from the tagged commit; their byte sizes and
> SHA256 values are recorded in the corresponding `.sha256` sidecars on 02,
> not embedded here (a bundle cannot contain a hash of itself).

| Path | Bytes | SHA256 |
|---|---:|---|
| `image-r032c-arm64.tar` | 33591321600 | `3d168db1dd7852e752b2c4a45534a20cc6c66f8cd276c7341acf7b72b45f624a` |
| `deploy/migrate-assets.tar.zst` | 48901567 | `35ea9f9887a0deeb09a8c4ac852e224df240396ed387710b422d1219cfcf1250` |
| `deploy/luz-deepseek-flash-all-in-one.bundle` | — | sidecar on 02 |
| `deploy/luz030-opt-campaign.bundle` | — | sidecar on 02 |
| `runtime/<node01>.json` | 53105 | `ac4b213a3f9b76974980e42fcf28fe81c23a46bc821e11ba477926469cfa789e` |
| `runtime/<node02>.json` | 55329 | `be4d343119c3f1c820e7a9c3c4577ee6dc5f46adf2d71e5979d278313e9ca320` |
| `runtime/<node03>.json` | 44134 | `6ba90bfc9a5711793ffb627fcfd452a56938536484d00c87fa9341006baffdb0` |
| `runtime/<node04>.json` | 43669 | `988a6a6d42de4c21412b9e92a03f1fffb0aa9bf4a84fae8cf05e6edeb0b03799` |

## Verification

```bash
cd /path/to/checkpoint
sha256sum -c SHA256SUMS
sha256sum -c image-r032c-arm64.tar.sha256
zstd -t deploy/migrate-assets.tar.zst
git bundle verify deploy/luz-deepseek-flash-all-in-one.bundle
git bundle verify deploy/luz030-opt-campaign.bundle
```

`migrate-assets.tar.zst` excludes two root-owned 300-byte JIT metadata files

listed in `deploy/migrate-assets.EXCLUDED.txt`; all other readable files are

included and enumerated in `deploy/migrate-assets.FILES.txt`.

