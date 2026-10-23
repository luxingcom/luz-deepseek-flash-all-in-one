# 内核/驱动版本锁证据（2026-10-23）

## 目的与基线

按用户要求将四机固定在当前生产版本，禁止自动升级：

| 项 | 固定值 |
|---|---|
| 运行内核 | `6.17.0-1031-nvidia`（包版本 `6.17.0-1031.31`） |
| NVIDIA 用户态 | `580.173.02-1ubuntu1` |
| `nvidia.ko` | `580.173.02` |
| GRUB 默认 | `1>2`（6.17 normal） |
| `nvidia-kernel-common-580` / `nvidia-kernel-source-580-open` | `580.178.04-0ubuntu0.24.04.1`（保持安装状态，不随用户态降级） |
| `nvidia-firmware-580-580.173.02` | `580.173.02-0ubuntu0.24.04.1` |

## 保护层

| 层 | 配置 | 覆盖 |
|---|---|---|
| 精确版本 hold + APT pin 1001 | `/etc/apt/preferences.d/99-prod-version-lock` | 22 个受锁包（7 内核 + 12 NVIDIA 用户态 + 2 misc + 1 firmware），candidate 必须等于已安装版本 |
| 额外 guard hold | `apt-mark hold` | 7 个既有包：4 个 7.0 内核 meta/module（保持 GRUB 菜单和 `1>2` 索引稳定）、`libxnvctrl0`、`nvidia-modprobe`、`nvidia-settings` |
| unattended 屏蔽 | `/etc/apt/apt.conf.d/52-prod-version-lock` | 关闭 unattended-upgrade；29 个包全部列入 blacklist |
| DGX OTA 屏蔽 | systemd mask | `nvidia-spark-run-apt-upgrade-once.service`（会执行 `apt full-upgrade` 并重启） |
| APT 定时器屏蔽 | systemd mask | `nvidia-spark-ota-check.timer`、`apt-daily.timer`、`apt-daily-upgrade.timer` |
| 周期只读校验 | `prod-version-lock.timer` / `prod-version-lock.service` | 每 30 分钟；校验内核、用户态、模块、GRUB、22 个精确锁包、7 个 guard hold、自动升级单元 |
| 启动/自检门禁 | `boot-prod.sh`、`selfcheck-prod.sh` 的 `version_lock` 项 | 漂移 fail-closed，拒绝起栈或自检 FAIL |

`version-lock.sh check` 汇总行的 `holds=29 lock=22 guard=7` 表示：22 个包做
精确版本 + pin 校验，另外 7 个 guard 包只要求仍安装且仍为 hold。guard 不纳入
精确 pin 的原因：`nvidia-modprobe` 在 01/02 为 `610.43.02-1ubuntu1`，在
03/04 为 `610.57.04-1ubuntu1`；统一 pin 会造成无意义的跨机差异。它们已全部
进入 unattended blacklist，且 hold 缺失会被定时检查发现。

guard 中的 7.0 meta/module 是回滚后保留的备用启动项。固定它们是为了防止
meta 包升级新增 ABI、改变 GRUB 菜单顺序，使 `GRUB_DEFAULT="1>2"` 指向错误
条目。

## 最终验证（2026-10-23）

- 四机 `version-lock.sh check`：
  `OK kernel=6.17.0-1031-nvidia driver=580.173.02 holds=29 lock=22 guard=7 ... grub=1>2`
- 四机 `apt-mark showhold | wc -l` = **29**。
- 四机 `apt-get -s full-upgrade` 中对 `linux-*`、`nvidia-*`、`libnvidia-*`、
  `libxnvctrl*` 无任何 `Inst`/`Remv`/`Conf` 行。
- 四机 `once=masked`，OTA/apt 三个 timer 为 `masked`，
  `prod-version-lock.timer=active`、`prod-version-lock.service=success`。
- 最终 post-boot（`2026-10-23T00:55:42Z`）：**46/46 PASS**，
  `warm_gate median=6415 tok/s`（阈值 5600）。
- 最终 fast（`2026-10-23T00:56:48Z`）：**44/44 PASS**。
- 生产栈未因版本锁操作重启；`/health` 保持 200。

## 文件

| 文件 | 内容 |
|---|---|
| `version-lock.sh` | 已安装脚本副本（`check` / `apply`） |
| `install-version-lock.sh` | 安装器，负责下发脚本/unit、apply、启停 timer |
| `prod-version-lock.service` / `.timer` | root oneshot 只读检查；每 30 分钟 |
| `99-prod-version-lock` | 四机一致的 APT pin 文件（22 包精确版本） |
| `52-prod-version-lock` | 四机一致的 unattended blacklist（29 包） |
| `host-01..04.txt` | 四机终态：内核、驱动、模块、GRUB、29 个 hold、单元状态、升级模拟 |
| `postboot-20261023-005415.log/.tsv` | 最终 post-boot 原始日志/TSV（46/46，warm 6415） |
| `version-lock-postboot-20261023-005542.json` | 最终 post-boot JSON |
| `fast-20261023-005620.log/.tsv` | 最终 fast 原始日志/TSV（44/44） |
| `version-lock-fast-20261023-005648.json` | 最终 fast JSON |
| `SHA256SUMS` | 本目录校验和 |

## 变更版本（仅维护窗）

1. 更新 `deploy/prod/prod-profile.env` 的内核/NVIDIA 白名单。
2. 在维护窗内删除/调整 `99-prod-version-lock` 和 `52-prod-version-lock`，
   对所有目标包 `apt-mark unhold`（包括 guard 包，若需要移动 GRUB 条目）。
3. 安装目标内核/驱动，确认用户态与 `nvidia.ko` 完全一致。
4. 重新运行 `sudo /usr/local/sbin/version-lock.sh apply`，然后走唯一启动入口
   `boot-prod.sh` 和 `selfcheck-prod.sh --post-boot`。
5. 重新记录 GRUB 索引并更新 `version-lock.sh` 的 `GRUB_LINE`；禁止只改 pin、
   只解除部分 hold 或跳过 post-boot。
