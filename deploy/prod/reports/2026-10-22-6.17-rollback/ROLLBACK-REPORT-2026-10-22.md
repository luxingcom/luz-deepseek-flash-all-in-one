# 6.17 内核回滚与生产恢复报告

- 报告日期：2026-10-22（UTC；10-23 00:57 追加版本锁、guard hold 并完成最终复检）
- 适用范围：`<node01>`–`<node04>`，TP4，`r3prod`，`deepseek-v4.1-flash`
- 生产镜像：`<registry-host>:5000/dsv41-sglang-optimized:0.3.2-r032c`（digest `sha256:47f6d91a…e2ffc4`；registry 主机已脱敏为占位符）
- 报告状态：**完成；生产在线，回滚后验收通过**
- 审核归档总表：`../2026-10-23-audit-archive/TASK-ACHIEVEMENTS-2026-10-22_23.md`
- 结论一句话：**四机按 02 → 03 → 04 → 01 顺序回滚到 6.17.0-1031 + NVIDIA 580.173.02；NIC 固件 28.50.1002 保留并验证兼容。回滚后 PR 七档全部回到并超过 A6 锚点（+0.6%～+2.9%），warm gate 6463 tok/s，DE c1/c8 91.64/249.10，GSM8K 20/20。**

---

## 1. 背景与决策

2026-10-22 白天生产升级到 7.0.0 后出现 prefill 性能回归。7.0 窗口内已完成
NIC buffer 523296、RX ring 4096、GPU 默认频率/EC auto、CPU 绑核审计、
recipe 复验和自检固化，但 PR 仍比 A6 锚点低约 6–13%，且所有可测配置项都
无法解释。用户随后明确要求：

> 回滚内核到 6.17 的历史版本。若涉及必须回退的软件栈和驱动请一并处理。
> 逐个回滚，最后回滚 01 服务器。

本轮按该指令执行，不再维持 7.0。7.0 调优过程保留为历史报告，不作为当前
运行基线。

## 2. 最终基线

| 项 | 当前值 | 验证 |
|---|---|---|
| 内核 | `6.17.0-1031-nvidia`（四机） | `boot-prod.sh` 允许表 + post-boot 自检 |
| NVIDIA 用户态 | `580.173.02`（12 个包，全部 hold） | `nvidia-smi` |
| NVIDIA 内核模块 | `580.173.02`（6.17 的 `nvidia.ko`） | `modinfo -k $(uname -r) -F version nvidia` |
| GRUB 默认 | `GRUB_DEFAULT="1>2"`（四机），`next_entry=` 空 | `/etc/default/grub`、`grubenv` |
| NIC 固件 | `28.50.1002`（四机 16 口；未降级） | `ethtool -i`、NIC check |
| RX ring | `4096`（TX 1024） | `ethtool -g` |
| Lossless buffer | `523296`（`19872,523296,...`） | `mlnx_qos` |
| PFC / trust | `0,0,0,1,0,1,0,0` / `dscp` | `mlnx_qos` |
| GPU 频率/温控 | 默认无上限；EC auto；max SM 3003 MHz | `gb10-clock-cap` disabled、`nvidia-smi` |
| 镜像 | `0.3.2-r032c`，digest `sha256:47f6d91a…e2ffc4` | boot-prod digest 校验 |
| env | 56 键，md5 `0729e18d6a93c1c05a82e1a5d528c488` | 四机逐键比对 |
| overlay / adapter | 28 件 / 97 件，指纹 `c41b1a45` | 四机一致 |
| recipe | `serving_chat.py` `3151a2ed…`，`dsv41_recipe.py` `da98467d…` | 容器 md5 + probe |
| API | `127.0.0.1:8899`，`deepseek-v4.1-flash` | `/health`、`/server_info` |
| 主机状态 | `systemctl is-system-running=running`，无 failed unit | 四机 |
| 版本锁 | 22 个内核/NVIDIA 包精确 hold + APT pin 1001，另 7 个 7.0/meta/工具 guard hold（共 29）；DGX 一次性 full-upgrade 服务 masked；OTA/apt 定时器 masked | `version-lock.sh check` |
| 自检 | post-boot **46/46 PASS**；fast **44/44 PASS** | `selfcheck-prod.sh` |

## 3. 逐台回滚过程

### 3.1 顺序与原则

1. 先停 `r3prod` 栈，保存回滚前 profile、last-boot、自检、head/02 运行面快照。
2. 02 先试，成功并验证后再做 03、04，01 最后。
3. 每台先一次性 `grub-reboot "1>2"` 验证 6.17 普通模式，成功后把
   `/etc/default/grub` 持久化为 `GRUB_DEFAULT="1>2"` 并 `update-grub`。
4. 每台启动后验证 `uname -r`、`nvidia-smi`、`modinfo`、NIC 四口、
   Docker GPU 容器；任何一台失败即停止后续。

### 3.2 关键版本事实

- 6.17 自带 `nvidia.ko` 是 **580.173.02 专有模块**（Canonical 签名），
  不是 7.0 的 580.178.04 open 模块。
- 只换内核、不换用户态会得到 `NVRM: API mismatch`，`nvidia-smi`、
  `nvidia-persistenced`、`nvidia-cdi-refresh` 全部失败。
- 因此四机同时把用户态降到 `580.173.02-1ubuntu1`，并 hold 住，防止 apt
  自动升回 580.178.04。
- `nvidia-kernel-common-580` 保持 `580.178.04`；该包不提供与内核模块 ABI
  绑定的用户态库，当前组合实测正常。

### 3.3 GRUB 索引纠错

首次对 02 使用了 `grub-reboot "1>1"`，实际进入的是 **7.0 recovery
（`recovery nomodeset`）**，不是 6.17，导致 `pam_nologin` 长时间阻塞。
现场断电重启后核对 `/boot/grub/grub.cfg`，确认：

| 子菜单 | 实际条目 |
|---|---|
| `1>0` | 7.0.0 普通 |
| `1>1` | 7.0.0 recovery |
| `1>2` | **6.17.0 普通** |
| `1>3` | 6.17.0 recovery |

后续全部使用 `1>2`。这次误判不是 6.17、NIC 固件或 NVIDIA 驱动故障，详细
时间线和恢复步骤见 `INCIDENT.md`。

### 3.4 用户态降级

使用 `rollback-nvidia-userspace.sh`，关键点：

- `apt-mark unhold` 后精确安装 `580.173.02-1ubuntu1`；
- `--allow-downgrades --allow-change-held-packages --force-overwrite`；
- 移除无头机不需要的 `nvidia-driver-580-open`、
  `xserver-xorg-video-nvidia-580`；
- 修复旧 `libnvidia-gl-580` 的 EGL 文件冲突后 `dpkg --configure -a`；
- 最后 hold 12 个 580.173.02 用户态包。

02 首次手工降级未带 `--force-overwrite`，出现 EGL 文件冲突；脚本化后
03/04/01 均一次通过。

## 4. 持久化与启动门禁

### 4.1 `prod-profile.env`

```bash
PROD_KERNEL_ALLOW="6.17.0-1031-nvidia"
PROD_NVIDIA_DRIVER_ALLOW="580.173.02"
```

NIC 相关保持不变：`PROD_RX_RING=4096`、`PROD_NIC_FW_ALLOW=28.50.1002`、
`PROD_LOSSLESS_BUFFER=523296`。

### 4.2 `boot-prod.sh`

新增失败关闭检查，对四机逐台执行：

```bash
drv=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits | head -1)
kmod=$(modinfo -k "$(uname -r)" -F version nvidia)
[[ "$drv"  == "$PROD_NVIDIA_DRIVER_ALLOW" ]] || die "... API mismatch risk"
[[ "$kmod" == "$PROD_NVIDIA_DRIVER_ALLOW" ]] || die "... userspace/module mismatch"
```

内核不在允许表、用户态与模块任一不符、版本锁（hold/pin/GRUB/自动升级单元）
漂移、NIC profile 漂移、env/overlay/recipe/adapter/digest 不符、端口或容器不净，
都会在起栈前拒绝。

### 4.3 `selfcheck-prod.sh`

新增每机 `driver` 检查（用户态 + 模块）；版本锁安装后再新增每机
`version_lock` 检查（hold/pin/GRUB/自动升级单元），自检最终为
**44 项 fast / 46 项 post-boot**。当前最近结果：

- 版本锁安装前 post-boot：42/42 PASS，`warm_gate median=6463 tok/s`（23:44）；
- 版本锁安装前 fast：40/40 PASS（23:49）；
- 版本锁安装前最终复检（00:06）：42/42 PASS，`warm_gate median=6446 tok/s`；
- 版本锁安装后 fast（00:41）：**44/44 PASS**；
- 版本锁安装后 post-boot（00:42）：**46/46 PASS**，`warm_gate median=6452 tok/s`；
- 一次性升级服务由 disabled 强化为 masked 后（00:48）：**46/46 PASS**，
  `warm_gate median=6420 tok/s`；fast（00:50）：**44/44 PASS**；
- 把 7 个 7.0/meta/工具 guard 包纳入漂移校验后（00:55:42）：最终
  **46/46 PASS**，`warm_gate median=6415 tok/s`；最终 fast（00:56:48）：
  **44/44 PASS**。

### 4.4 自愈误报修复

回滚后首次巡检发现四机 `systemctl` 为 `degraded`，原因是
`roce-ring-check.service` 调用 `heal-if-down`，而旧逻辑在栈运行时无条件
`exit 1`。已改为：

- 栈在跑：执行只读 `check`，零漂移 `exit 0`，有漂移 `exit 1`；
- 栈停：执行 `apply`，保持原来的自愈能力。

修正版已安装到四机 `/usr/local/sbin/roce-ring-apply.sh`，`reset-failed`
后验证 `Result=success`，四机恢复 `running`，`systemctl --failed` 为空。

### 4.5 内核/驱动版本锁（2026-10-23）

用户要求“对当前服务器内核版本和驱动版本做好配置保护，避免自动升级”。
四机已安装同一套锁：

| 层 | 配置 | 作用 |
|---|---|---|
| 包 hold | 7 个 `6.17.0-1031` 内核包 + 12 个 580.173.02 用户态包 + `nvidia-kernel-common-580`、`nvidia-kernel-source-580-open`、`nvidia-firmware-580-580.173.02`，共 22 个 | apt 不自动升级/移除 |
| guard hold | 4 个 7.0 内核 meta/module + `libxnvctrl0`、`nvidia-modprobe`、`nvidia-settings`，共 7 个 | 固定 GRUB 菜单顺序和现有 NVIDIA 工具版本；缺 hold 会被定时检查发现 |
| APT pin | `/etc/apt/preferences.d/99-prod-version-lock`，`Pin-Priority: 1001` | 22 个受锁包的 candidate 锁定为已安装精确版本 |
| 自动升级屏蔽 | `/etc/apt/apt.conf.d/52-prod-version-lock`（29 包黑名单）；`apt-daily*.timer`、`nvidia-spark-ota-check.timer` masked | 关闭 unattended 和定时检查 |
| DGX 一次性升级 | `nvidia-spark-run-apt-upgrade-once.service` masked | 阻断 `apt full-upgrade` + `reboot` 路径 |
| 周期校验 | `prod-version-lock.timer` 每 30 分钟；`boot-prod.sh` 和 selfcheck 的 `version_lock` 项 | 漂移 fail-closed |

验证结果：四机 `version-lock.sh check` 均 OK
（`holds=29 lock=22 guard=7`）；`apt-get -s full-upgrade` 对 `linux-*`、
`nvidia-*`、`libnvidia-*`、`libxnvctrl*` 无任何 `Inst`/`Remv`；
`prod-version-lock.service` `Result=success`；一次性升级服务与 OTA/apt 三个
定时器均为 masked。最终复检（00:55:42/00:56:48 UTC）再次确认四机
`once=masked`、三个定时器 masked、`prod-version-lock.timer` active，post-boot
46/46（warm 6415）、fast 44/44 PASS。版本变更只能在维护窗内先解除 pin/hold
（含 guard），再安装目标版本并重新 apply，不能绕过。

## 5. 生产启动与自检

启动入口仍是唯一入口：

```bash
bash ~/migrate-assets/prod/boot-prod.sh
```

2026-10-22 23:35 UTC 启动，关键输出：

- `kernel + NVIDIA driver allowlist OK (580.173.02)`；
- `RX ring 4096 OK on all hosts`；
- 四机 28 件 overlay、56 键 env、adapter 指纹全部一致；
- 23:38 UTC 栈 UP，`/health` 200；
- 启动时（版本锁尚未安装）post-boot 42/42 PASS；版本锁安装后
  00:48 最终复检 46/46 PASS，见 4.3/4.5；
- `last-boot.json`：`boot_rc=0`、`selfcheck_rc=0`。

关键服务参数：`max_total_num_tokens=9600000`、`context_length=600000`、
`max_running_requests=16`、模型 `deepseek-v4.1-flash`。

## 6. 性能复测

口径：PR 用 sparkDash `repeated`，每档 3 次独立调用取中位；DE 为 mt400
prose，c1/c8 各 5 次取中位；对照 7.0 最终靴和 A6-ANCHOR-7。测试期间生产
栈在线，未改任何参数。

### 6.1 PR 七档（tok/s）

| 输入 tokens | 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6.17 三次采样 | 5555.6 / 5609.2 / 5435.7 | 5637.1 / 6169.4 / 6161.6 | 6453.8 / 6452.8 / 6417.4 | 6468.1 / 6403.5 / 6473.5 | 6194.6 / 6206.4 / 6189.4 | 5562.0 / 5556.8 / 5559.6 | 4384.6 / 4376.9 / 4362.3 |
| **6.17 中位** | **5555.6** | **6161.6** | **6452.8** | **6468.1** | **6194.6** | **5559.6** | **4376.9** |
| A6 锚点 | 5522.5 | 6040.2 | 6271.3 | 6289.3 | 6048.1 | 5427.9 | 4290.0 |
| 对 A6 | +0.6% | +2.0% | +2.9% | +2.8% | +2.4% | +2.4% | +2.0% |
| 7.0 中位 | 4825.7 | 5620.0 | 5913.3 | 5797.1 | 5684.2 | 4873.9 | 3891.2 |
| 对 7.0 | +15.1% | +9.6% | +9.1% | +11.6% | +9.0% | +14.1% | +12.5% |

8k 档 +0.6% 在单次 PR 噪声范围内；16k–512k 的 +2.0%～+2.9% 与 7.0 的
−5.7%～−12.6% 形成方向明确的对照。

### 6.2 DE 与 warm gate

| 项 | 6.17 中位 | A6/阈值 | 7.0 |
|---|---:|---:|---:|
| DE c1 (tok/s) | **91.64** | 88.64（+3.4%） | 86.38 |
| DE c8 (tok/s) | **249.10** | 242.83（+2.6%） | 240.13 |
| 64k warm (tok/s) | **6463**（复检 6446 / 6452 / 6420 / 6415） | 5600 阈值 | 5797 |

warm 五次：`5543.7 / 6494.3 / 6303.2 / 6468.4 / 6458.5`；首次为冷读，
按规则丢弃，后四次中位 6463.45。00:06 复检五次
`6447 / 6451 / 6450 / 6442 / 6434`，中位 6446；版本锁后 00:42 复检
`6445 / 6452 / 6452 / 6454 / 6436`，中位 6452；mask 强化后 00:48 复检
`6473 / 6462 / 6425 / 6411 / 6415`，中位 6420；guard 完成后 00:55 最终复检
`6472 / 6413 / 6417 / 6412 / 6435`，中位 6415，仍高于阈值 15%。

### 6.3 质量门

| 项 | 结果 | 说明 |
|---|---|---|
| GSM8K 20 题 | **20/20，content=1.0，marker=1.0，err=0** | 8-shot、temp 0.6、mt1024、并发 1 |
| qeval 75 题 | **71/75（94.7%）** | code 24/25、format 7/7、json 6/8、math 13/14、prose 5/5、reason 16/16；1 题触顶 |
| needle | 本轮未重跑 | 回滚不改 logits/长上下文路径；上一轮 8/32/64/128k 4/4 PASS |

qeval 的 4 个失败为 `code_interval_intersect`、`json_escape`、`json_count`、
`math_m9`（后者 finish_reason=length）。qeval 自带参考记录为 72/75，当前
71/75，未发现回滚引入的系统性质量下降。完整 500 题 GSM8K 未在本次窗口
重跑，正式验收前应在低峰补跑。

## 7. 结果解释

1. **回滚解决了 prefill 回归**：同一镜像、同一 NIC 固件/ring/buffer/PFC、
   同一 GPU 频率策略，只把内核与 NVIDIA 用户态/模块从 7.0/580.178.04 换回
   6.17/580.173.02，PR 从低 6–13% 变为高 0.6–2.9%。这使“7.0 内核 + 新
   驱动路径”成为最强相关项；不是 NIC buffer、ring、recipe 或绑核。
2. **不需要降级 NIC 固件**：28.50.1002 + 6.17 的 mlx5 驱动在四机 16 口
   上通过 ring/buffer/PFC/trust 检查，生产负载下未出现丢包计数。
3. **DE 也同步恢复**：c1/c8 从 86.38/240.13 提升到 91.64/249.10，说明
   回滚改善的不只是长 prompt prefill，decode 路径也从新驱动栈的额外开销中
   恢复。
4. **成本是版本锁定**：6.17 与 580.173.02 必须成对出现；用户态已 hold，
   7.0 仍在 GRUB 但不在允许表。这是当前稳定基线的明确边界。

## 8. 风险与边界

| 风险 | 现状 | 处置 |
|---|---|---|
| 用户态被 apt 升级回 580.178.04 | 12 个包已 hold | 变更前先 `apt-mark showhold`；升级需维护窗并同步换内核模块 |
| 7.0 与 6.17 驱动混用 | boot-prod 双重校验用户态+模块 | 任一不符拒绝启动，不允许绕过 |
| GRUB 误选 recovery | 已固化 `1>2`；`next_entry` 空 | 禁止用 `1>1` 做回滚；改默认前打印 grub.cfg 菜单项 |
| 无 BMC | 错误启动项只能现场断电 | 一次性 `next_entry` 先验证，再持久化默认 |
| 自愈 timer 误报 | 已修正并验证 `Result=success` | 每班检查 `systemctl --failed` 为空 |
| 完整 500 题未跑 | 20 题 + qeval 75 题通过 | 低峰补跑，记录 accuracy_content |
| 生产在线跑基准 | 有客户端流量时单次 PR 波动 | 以 3 次中位/warm gate 判定，不以单发下结论 |

## 9. 运维交接

```bash
# 启动（唯一入口）
bash ~/migrate-assets/prod/boot-prod.sh

# 只读自检
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot

# 日常确认
systemctl is-system-running
systemctl --failed
systemctl show -p Result --value roce-ring-check.service
systemctl show -p Result --value prod-version-lock.service
/usr/local/sbin/version-lock.sh check
docker ps --format '{{.Names}} {{.Status}}' | grep '^r3prod'
curl -fsS http://127.0.0.1:8899/health
```

通过标准：四机 `running`、无 failed unit、post-boot 46/46、fast 44/44、
`version-lock.sh check` OK、`last-boot.json` 的 `boot_rc=0/selfcheck_rc=0`。

禁止项：绕过 `boot-prod.sh` 起栈；只改内核不改 NVIDIA 用户态；栈运行时
写 ring/buffer/PFC；自动降级 NIC 固件；把 7.0 加回允许表而不做完整验收；
绕过 `version-lock.sh` unhold/pin 后直接起栈。

## 10. 证据与记录

- 回滚前快照、降级脚本、事件记录：
  `~/rollback-20261022-6.17/`（`INCIDENT.md`、`rollback-nvidia-userspace.sh`、`pre/`）
- 生产启动日志：`~/r3-prod-logs/boot-prod-20261022-233453.log`
- post-boot 自检：`~/r3-prod-logs/selfcheck-20261022-234245.log/.tsv`
- 最终 post-boot 复检（版本锁前）：`~/r3-prod-logs/selfcheck-20261023-000538.log/.tsv`
- 版本锁后复检：`~/r3-prod-logs/selfcheck-20261023-004117.log/.tsv`（46/46）
- mask 强化后复检（00:48）：`~/r3-prod-logs/selfcheck-20261023-004703.log/.tsv`
  （46/46，warm median=6420）
- 最终 post-boot（guard 完成后）：`~/r3-prod-logs/selfcheck-20261023-005415.log/.tsv`
  （46/46，00:55:42 UTC，warm median=6415）及 `evidence/selfcheck-20261023-005415.*`
- 最终 fast：`~/r3-prod-logs/selfcheck-20261023-005620.log/.tsv`
  （44/44，00:56:48 UTC）及 `evidence/selfcheck-fast-final.json`
- 版本锁证据：`evidence/version-lock/`（四机 host 终态、脚本、pin/blacklist、
  fast/post-boot 日志与 JSON、`README.md`、`SHA256SUMS`）
- `last-boot.json`：`boot_rc=0`、`selfcheck_rc=0`
- 性能原始 JSON 与汇总：`evidence/pr_*.json`、`de_c*.json`、
  `performance-summary.tsv/.json`、`bench-6.17.log`
- 质量：`evidence/gsm8k-20.summary.json`、`evidence/qeval-6.17-rollback.json`
- 主机终态：`evidence/host-01..04.txt`、`production-state.txt`
- 校验和：`evidence/SHA256SUMS`

本目录内证据副本与 `SHA256SUMS` 只对应本次回滚；7.0 历史证据仍在
`../2026-10-22-7.0.0-tuning/evidence/`。

## 11. 代码与文档变更

- `deploy/prod/prod-profile.env`：内核允许表 6.17；新增
  `PROD_NVIDIA_DRIVER_ALLOW=580.173.02`。
- `deploy/prod/boot-prod.sh`：新增用户态 + 模块双重校验。
- `deploy/prod/selfcheck-prod.sh`：新增每机 `driver` 与 `version_lock` 检查
  （最终 44/46 项）。
- `deploy/prod/roce-ring-apply.sh`：修复 `heal-if-down` 在栈运行时的误报。
- `deploy/prod/version-lock.sh`、`install-version-lock.sh`、
  `prod-version-lock.service`、`prod-version-lock.timer`：新增内核/驱动版本锁
  （22 个精确锁包 + 7 个 guard hold，共 29 个 hold；29 包 unattended 黑名单）。
- `deploy/prod/README.md`、`OPS-RUNBOOK.md`、7.0 历史报告：同步回滚和版本锁状态。
- 变更已写入工作区，尚未提交/推送。
