# 0.3.2 前代档案归档索引（2026-10-22）

归档主机：`DGXspark02`（`192.168.0.202`）
归档根：`/home/liuxiaoya/cluster-archive-20261022/`
总量：**290,063,676,566 B（271G，92,931 个普通文件）**

本索引记录 0.3.2 基线之前开发/测试档案的最终位置与校验状态。0.3.2 现役回滚点不在本归档内，它在
`/home/liuxiaoya/checkpoints/0.3.2-baseline-20261022/`，身份与恢复方法见同目录
[`README.md`](README.md) 和 [`IMAGE-IDENTITY.json`](IMAGE-IDENTITY.json)。

## 目录布局

| 路径 | 内容 |
|---|---|
| `01/` | dgxspark01 上 0.3.2 之前的历史档案、旧仓库、旧发行包 |
| `02/` | dgxspark02 本机旧测试环境/迁移暂存，同盘移动，不占额外空间 |
| `03/` | dgxspark03 旧运维工作区与环境统一档案 |
| `04/` | dgxspark04 旧运维工作区与环境统一档案 |

## 01 — 历史档案与保留目录（02 有完整副本）

### 已删除源（02 为权威副本）

| 目录 | 字节（`du -sb`） | 占用 | 文件数 | 校验 |
|---|---:|---:|---:|---|
| `LuZ-0.3.0-ARCHIVE-20260930` | 2,589,878 | 2.8M | 129 | checksum 零差异 |
| `archive-20260912` | 18,575,902 | 19M | 218 | checksum 零差异 |
| `archive-20261001` | 22,023,602,388 | 21G | 4,920 | checksum 零差异 |
| `archive-20261012` | 74,533,864,463 | 70G | 6,163 | `-H` checksum 零差异；3,936 硬链接保真 |
| `archive-20261014` | 56,199,671,120 | 53G | 33,979 | checksum 零差异 |
| `archive-env-unify-20261010` | 1,966,788 | 2.0M | 30 | checksum 零差异 |
| `archive-tools-20261007` | 505,252 | 616K | 61 | checksum 零差异 |
| `dsv41-flash-dgxsparks` | 527,686,223 | 526M | 8,952 | checksum 零差异（含 215 个 root-only 文件） |
| `luz-0.3.1-dist` | 28,974,016,739 | 27G | 10 | checksum 零差异 |
| `luz-0.3.1-locked` | 7,249,145 | 7.4M | 178 | checksum 零差异 |
| `switch-1017-20261017-154237` | 52,705,438 | 51M | 118 | checksum 零差异 |
| `v4vl-regraft-20261005` | 6,016,500 | 6.4M | 130 | checksum 零差异 |
| **小计** | **182,348,449,836** | **170G** | **54,888** | |

### 保留在 01 的当前目录（02 有副本）

| 目录 | 字节（`du -sb`） | 占用 | 文件数 | 校验 |
|---|---:|---:|---:|---|
| `data` | 749,738 | 740K | 1 | checksum 零差异 |
| `luz-0.3.2-dev` | 2,078,585 | 2.2M | 47 | checksum 零差异 |
| `mesh-fabric-stage` | 291,212 | 372K | 24 | checksum 零差异 |
| `v41-opt` | 7,396,212 | 9.1M | 460 | checksum 零差异 |
| **小计** | **10,515,747** | **12.4M** | **532** | |

### 01 合计

| 项目 | 字节 | 占用 | 文件数 |
|---|---:|---:|---:|
| 已删除源 | 182,348,449,836 | 170G | 54,888 |
| 保留目录 | 10,515,747 | 12.4M | 532 |
| **总计** | **182,358,965,583** | **170G** | **55,420** |

### 01 归档校验方法

```bash
# 16 个目录逐一执行；archive-20261012 额外加 -H
rsync -rlp --checksum --dry-run --itemize-changes \
  /home/liuxiaoya/<dir>/ DGXspark02:/home/liuxiaoya/cluster-archive-20261022/01/<dir>/
```

- 16/16 目录返回 `rc=0`，差异行数为 0。
- `archive-20261012` 源内 3,936 个硬链接的 `find -printf '%s'` 文件大小合计为 122,188,199,255 B，
  而 `du -sb` 为 74,533,864,463 B（硬链接只计一次）。初次 `rsync -a` 会展开硬链接，因此重新以
  `rsync -aH --sparse` 复制；最终 02 目标同样为 74,533,864,463 B、6,163 个普通文件、
  3,936 个硬链接，`-H --checksum` 零差异。展开的旧副本已删除。
- `dsv41-flash-dgxsparks` 的 `state/b12x-compile/` 与 `state/b12x-next-compile/` 下有 root-only
  编译缓存（134 个文件，约 8.6 MB）。用户态 rsync 先排除了这两个目录；随后用 root tar 流补齐，
  并对两个目录全部 215 个文件做 SHA256 对表，源/档 215/215 全等。最终源/档均为
  527,686,223 B、8,952 个文件。
- `mesh-fabric-stage` 的 `du -sh` 源/档分别为 324K/372K，是目录分配块差异；`du -sb` 均为
  291,212 B，文件数均为 24。
- 仅对“已删除源”列表中的目录执行删除；保留目录的 01 源仍在。01 上还保留本索引之外的在役仓库
  （`luz-deepseek-flash-all-in-one`、`luz030-opt-campaign`、`sglang-main-src`、`w6-kit`、
  `knapcio-v41-audit-20260925` 等），以及 `/tmp` 重演/审计目录。

## 02 — 本机旧测试环境/迁移暂存

| 目录 | 字节 | 占用 | 文件数 | 说明 |
|---|---:|---:|---:|---|
| `aicad-rollback` | 189,457,778 | 181M | 20 | 同盘移入 |
| `aicad-test` | 8,693,488,279 | 8.2G | 11,017 | 同盘移入 |
| `gw-mig-staging` | 123,988,693 | 121M | 591 | 同盘移入 |
| `r4-ops-work` | 32,866,784,442 | 31G | 8,479 | 同盘移入 |
| **合计** | **41,873,719,192** | **40G** | **20,107** | |

同盘 `mv` 不经过网络复制，源路径已不存在；文件数/字节数按移动后的目录实测。

## 03 — 旧运维工作区与环境统一档案

| 目录 | 字节 | 占用 | 文件数 | 说明 |
|---|---:|---:|---:|---|
| `archive-env-unify-20261010` | 48,696,554 | 48M | 223 | 含 root-only 文件；223/223 SHA256 对表全等 |
| `r4-ops-work` | 32,866,784,442 | 31G | 8,479 | 复制后 checksum 零差异，源已删除 |
| **合计** | **32,915,480,996** | **32G** | **8,702** | |

## 04 — 旧运维工作区与环境统一档案

| 目录 | 字节 | 占用 | 文件数 | 说明 |
|---|---:|---:|---:|---|
| `archive-env-unify-20261010` | 48,726,353 | 48M | 223 | 含 root-only 文件；223/223 SHA256 对表全等 |
| `r4-ops-work` | 32,866,784,442 | 31G | 8,479 | 复制后 checksum 零差异，源已删除 |
| **合计** | **32,915,510,795** | **32G** | **8,702** | |

## 03/04 补充校验

- `archive-env-unify-20261010` 初次复制因 root-only `state/b12x-next-compile` 文件不完整；
  随后用 `sudo tar` 流补齐，源/档各 223 个文件，SHA256 逐文件 223/223 全等，源目录已删除。
- `r4-ops-work` 在复制完成且 `rsync --checksum --dry-run` 零差异后才删除源目录。

## 不在归档内的对象

以下对象仍留在原位，不属于“0.3.2 之前档案清理”范围：

- 模型权重与网络模型目录（`/data/models/DeepSeek-V4.1-Flash-1017`、`/data/models/dsv41-net`）。
- Engram 分片 `~/dsv41-engram-1017`。
- 02 的 0.2.4 checkpoint `~/checkpoint/LuZ-0.2.4-head-image-v14-6d6353d16c2d.tar`。
- 在役 r032c 重演/审计输入：`/tmp/bt-r032`、`/tmp/bt-a`、`/tmp/closure-stock`、
  `/tmp/closure-postport`。
- 在役基础设施源：`mesh-fabric-stage`、netplan/systemd。
- 02 两个不动域：`oom-gate-monitor`、`r3-watchdog-worker`。

## 复核

```bash
ssh DGXspark02 'du -sb ~/cluster-archive-20261022; du -sh ~/cluster-archive-20261022; \
  find ~/cluster-archive-20261022 -type f | wc -l'
# 期望：290063676566 / 271G / 92931
```

0.3.2 回滚点与归档是两套独立备份：回滚点在
`DGXspark02:~/checkpoints/0.3.2-baseline-20261022/`（镜像 tar、registry manifest、deploy kit、
运行时快照、git bundle），归档在 `DGXspark02:~/cluster-archive-20261022/`（历史资料）。
