# 发布索引 — LuZ 版本系列

> 本目录收录**公开发布面**的版本说明。逐版本的完整工程账在
> [CHANGELOG.md](../../CHANGELOG.md)；性能/口径正典在
> [docs/registry/BENCHMARK-SOURCE.md](../registry/BENCHMARK-SOURCE.md)。

## 版本系列

| 版本 | 定版 | 主题 | 发布说明 |
|---|---|---|---|
| **0.3.0** | 2026-10-05 | R1 检查点基线（36 键 env `b7e318e0`、sitecustomize 七件 `91adc83d`、池 9.6M） | 无独立 release note；基线记录见 CHANGELOG |
| **0.3.1** | 2026-10-13 定型 / 2026-10-14 发布 | FL6 召回修复转正（51 键）+VL 双臂+网关链；交付镜像 `0.3.1-r3` | tag [`v0.3.1`](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/releases/tag/v0.3.1)（GitHub Release 发布说明+渠道汇总） |
| **0.3.2** | 2026-10-20 | 净线重建→死锁修复（`520d6d0`+r032c 位级保持形）→五目标执行链→收官转正；池 84 件三态处置；重建包补齐 | [0.3.2-RELEASE-NOTE.md](0.3.2-RELEASE-NOTE.md) + GitHub Release `v0.3.2`；重建面 tag `v0.3.2-recon` |

## 0.3.2 发布面四层

1. **GitHub Release `v0.3.2`**：版本叙事/变更集/性能终态/硬守门/已知局限/回退面
   （正文=[0.3.2-RELEASE-NOTE.md](0.3.2-RELEASE-NOTE.md)）。
2. **内网 registry**：`dsv41-sglang-optimized:0.3.2-r032c`
   （digest `sha256:47f6d91a…e2ffc4`）——大文件不进 GitHub Release。
3. **本仓源码快照**：tag `v0.3.2` 指向的树=可复核交付面（boot 参面/部署件/量具/测试）。
4. **重建包**：tag `v0.3.2-recon` → [`deploy/reconstruct/0.3.2/`](../../deploy/reconstruct/0.3.2/README.md)
   ——r032c 16 件+构建配方、A6/R1/E16B2/CBX1A 增量、1017 权重/engram 台账；
   `verify.sh` 自验期望 `RECON-KIT PASS`。

## 系列纪律

- **判读线零事后改**：已发布版本的性能读数与历史结论一律引注不改；后续版本
  以新增节承接。
- **口径**：性能数字只用本仓自研量具（`sd_bench`/DE-48 家族）与版本判读线列；
  DE 一律 mt400 正典口径；外部数字带外，不作判读依据。
- **回退面逐件可逆**：镜像双存、adapter 逐件回拷、env 相邻级回指、boot 单行回指
  （详见各 release note §回退面）。
