# 发布索引 — LuZ 版本系列

> 本目录收录**公开发布面**的版本说明。逐版本的完整工程账在
> [CHANGELOG.md](../../CHANGELOG.md)；性能/口径正典在
> [docs/registry/BENCHMARK-SOURCE.md](../registry/BENCHMARK-SOURCE.md)。

## 版本系列

| 版本 | 定版 | 主题 | 发布说明 |
|---|---|---|---|
| **0.3.0** | 2026-10-05 | R1 检查点基线（36 键 env `b7e318e0`、sitecustomize 七件 `91adc83d`、池 9.6M） | 无独立 release note；基线记录见 CHANGELOG |
| **0.3.1** | 2026-10-13 定型 / 2026-10-14 发布 | FL6 召回修复转正（51 键）+VL 双臂+网关链；交付镜像 `0.3.1-r3` | tag [`v0.3.1`](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/releases/tag/v0.3.1)（GitHub Release 发布说明+渠道汇总） |
| **0.3.2** | 2026-10-20 | 净线重建→死锁修复（`520d6d0`+r032c 位级保持形）→五目标执行链→收官转正；池 84 件三态处置；重建包补齐 | [0.3.2-RELEASE-NOTE.md](0.3.2-RELEASE-NOTE.md) + GitHub Release `v0.3.2`；重建面 tag `v0.3.2-recon`；[升级指南](../../UPGRADE-0.3.2.md) |
| **0.3.3** | 2026-10-26 锁定（检查点名 r033d+split） | 正典代：镜像 `0.3.3-r033d`（73 层，registry 检查点 tag `0.3.3-final-20261026`）；58 键 K16-on env；立 T33-03 正典锚（PR 五档/DE c1/c8） | 无独立公开发布说明；对照读数=[034-PERF-REPORT](../report/034-PERF-REPORT-20261029.md) 0.3.3 列+[034-VERSION-LOCK](034-VERSION-LOCK-20261028.md) 回退级 |
| **0.3.4** | 2026-10-29（调优终态） | 修复固化代+调优终态：镜像 `0.3.4-x6bake-20261026`+v41 三联+BYPASS=2048+DEOPT-I8 采纳（engram 1.0→2.0 GiB）=61 键 env；判读门全绿零劣化+PR 全档 IN-BAND+KV/SWA fp8 精度判词成立 | [034-PERF-REPORT](../report/034-PERF-REPORT-20261029.md) · [034-WD-TUNED-FINAL](034-WD-TUNED-FINAL-20261029.md) · [034-VERSION-LOCK](034-VERSION-LOCK-20261028.md) · [0.3.4-RELEASE-NOTE.md](0.3.4-RELEASE-NOTE.md)（骨架） |
| **0.3.4re** | 2026-10-30（现役发布面） | 公开移植+加固批：0.3.4 面脱敏移植（31 copy+4 new）+DF/EQ 缺陷修复族（DF-02/03/04/05/12+EQ-02/03/04/05/09/11/12/19/20）+上游缺陷 host 侧规避族（UP43050/UP44162/UP45614/UPSTREAM-45119） | **[0.3.4re-RELEASE-NOTE.md](0.3.4re-RELEASE-NOTE.md)**；工程账=[CHANGELOG](../../CHANGELOG.md) 0.3.4re 各节 |

## 0.3.2 发布面五层

1. **GitHub Release `v0.3.2`**：版本叙事/变更集/性能终态/硬守门/已知局限/回退面
   （正文=[0.3.2-RELEASE-NOTE.md](0.3.2-RELEASE-NOTE.md)）。
2. **内网 registry**：`dsv41-sglang-optimized:0.3.2-r032c`
   （digest `sha256:47f6d91a…e2ffc4`）——大文件不进 GitHub Release。
3. **本仓源码快照**：tag `v0.3.2` 指向的树=可复核交付面（boot 参面/部署件/量具/测试）。
4. **重建包**：tag `v0.3.2-recon` → [`deploy/reconstruct/0.3.2/`](../../deploy/reconstruct/0.3.2/README.md)
   ——r032c 16 件+构建配方、A6/R1/E16B2/CBX1A 增量、1017 权重/engram 台账；
   `verify.sh` 自验期望 `RECON-KIT PASS`。
5. **升级面**：[`UPGRADE-0.3.2.md`](../../UPGRADE-0.3.2.md)——0.3.1 基底+混合快照
   的逐步升级、性能复现命令与参考值、回退/排障；现役 env 公开位
   `deploy/env/CBX1A-CERTM-spec1.env`，adapter 装配账
   `deploy/adapter/0.3.2-MANIFEST.md5`。

## 系列纪律

- **判读线零事后改**：已发布版本的性能读数与历史结论一律引注不改；后续版本
  以新增节承接。
- **口径**：性能数字只用本仓自研量具（`sd_bench`/DE-48 家族）与版本判读线列；
  DE 一律 mt400 正典口径；外部数字带外，不作判读依据。
- **回退面逐件可逆**：镜像双存、adapter 逐件回拷、env 相邻级回指、boot 单行回指
  （详见各 release note §回退面）。
