# 0.3.2 baseline checkpoint manifest — 2026-10-22

This manifest covers the git-committed checkpoint documentation. The large

external assets live on `DGXspark02:~/checkpoints/0.3.2-baseline-20261022/`

and are listed separately below with their SHA256 values.

## Committed files

| Path | Bytes | SHA256 |
|---|---:|---|
| `ARCHIVE-INDEX.md` | 7045 | `f8ee1cf4d7de49699175b7b18936e533a102ba19bb7c618afd7733a5679fda6e` |
| `CLEANUP-20261022.md` | 5844 | `7dae588908a1b4b36806a94377fdaf8347c9107cc0d9a2ed7ee55d8abbd0d4e7` |
| `IMAGE-IDENTITY.json` | 3741 | `fd92056ad17b201fc21fa9bf02402b6fbc1afc328acd9723e8b6aba7d90d1033` |
| `README.md` | 6270 | `5986a4cbfbf328aba52f7042be0dfba5e95f4d402ee7350601c38cc25ef4a008` |
| `RESTORE.sh` | 1749 | `fcb78080d799a67548617a65a0510aa80b03b22ce71bfcb40f6d1f1829ab7fe4` |
| `deploy/migrate-assets.EXCLUDED.txt` | 428 | `fb45eeb560893ca304b9cf090125a21c6e6189f1b8d48e461ee1398906ef2c13` |
| `deploy/migrate-assets.FILES.txt` | 59012 | `684a969457de4a86127747eb4d5aa2f1b35a4e605c0e33acdf47c090286b936c` |
| `registry/arm64-manifest.json` | 13862 | `ad7e362f4fe74cc0706bc13d77839909e0742669b4291b0ac58374967dc2b57e` |
| `registry/attestation-manifest.json` | 566 | `c24cf49ac63cb2f820df2f4fe0ab8039f7bc5b02eb803eb7c1f8c0e61d049153` |
| `registry/baseline-tag-put.headers` | 397 | `886f5b371a42cbb606cf81c3eb84fe2a3f07ace4645bf07be43cb01b746104fc` |
| `registry/baseline-tag-verify.txt` | 217 | `8a86c2fc8b73dbb828b7637c9e57cf6afb04501f877598e4d71b93a43ea482ea` |
| `registry/image-inspect-dgxspark01.json` | 1810 | `b014acf55e6211eb811080d708b187fe4ebad071632cbad14a234635cfd5e142` |
| `registry/image-inspect-dgxspark02.json` | 1628 | `d44c3bcb4c2b051ed0336f8c1cd55f988520e68e834fe32059d090b844e4bf5e` |
| `registry/index-r032c.json` | 857 | `47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4` |
| `registry/removed-tags-20261022.txt` | 739 | `dcaf8e840ff13fd06e307b2b22b965c5d3ee15ce22fc3546b5958082a9ed0ffc` |
| `runtime-summary.md` | 3195 | `21b1891fe14a73908b770080d5f086cca6ad286765496c825beaea737d194f10` |

## External assets on DGXspark02

> Git bundles are regenerated from the tagged commit; their byte sizes and
> SHA256 values are recorded in the corresponding `.sha256` sidecars on 02,
> not embedded here (a bundle cannot contain a hash of itself).

| Path | Bytes | SHA256 |
|---|---:|---|
| `image-r032c-arm64.tar` | 33591321600 | `3d168db1dd7852e752b2c4a45534a20cc6c66f8cd276c7341acf7b72b45f624a` |
| `deploy/migrate-assets.tar.zst` | 48901567 | `35ea9f9887a0deeb09a8c4ac852e224df240396ed387710b422d1219cfcf1250` |
| `deploy/luz-deepseek-flash-all-in-one.bundle` | — | sidecar on 02 |
| `deploy/luz030-opt-campaign.bundle` | — | sidecar on 02 |
| `runtime/dgxspark01.json` | 53105 | `ac4b213a3f9b76974980e42fcf28fe81c23a46bc821e11ba477926469cfa789e` |
| `runtime/DGXspark02.json` | 55329 | `be4d343119c3f1c820e7a9c3c4577ee6dc5f46adf2d71e5979d278313e9ca320` |
| `runtime/DGXspark03.json` | 44134 | `6ba90bfc9a5711793ffb627fcfd452a56938536484d00c87fa9341006baffdb0` |
| `runtime/DGXspark04.json` | 43669 | `988a6a6d42de4c21412b9e92a03f1fffb0aa9bf4a84fae8cf05e6edeb0b03799` |

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

