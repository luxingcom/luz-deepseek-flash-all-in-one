# 服务器更新、回退、性能测试与功能增强任务成果清单

- 文档编号：AUD-2026-10-23-01
- 版本：V1.0（审核归档稿）
- 编制日期：2026-10-23
- 归档范围：2026-10-22 12:24 UTC 至 2026-10-23 06:07 UTC 的连续维护周期（覆盖 10-22 全天至 10-23 凌晨）
- 适用对象：`dgxspark01`–`dgxspark04`，TP4 推理集群，模型 `deepseek-v4.1-flash`
- 文档状态：**完成，待审核签字**

---

## 1. 审核摘要

本周期围绕“生产升级到 7.0.0 后出现 prefill 性能回归”展开。团队先按用户要求在不回滚的前提下完成网卡、GPU、CPU、recipe、容器重编译与启动链路审计，确认所有可测配置项均无法解释 6–13% 的 prefill 缺口；随后按用户明确指令，将四机逐台回滚到 `6.17.0-1031-nvidia` + NVIDIA `580.173.02`，NIC 固件 `28.50.1002` 保留不降级。

回滚后生产于 2026-10-22 23:38 UTC 恢复，性能回到并超过 A6 锚点，长 prompt prefill 相对 7.0 提升 9.0%–15.1%，64k warm gate 稳定在 6415–6463 tok/s。随后完成启动失败关闭、自检扩展、RoCE 误报修复、内核/驱动版本锁和证据归档。2026-10-23 凌晨对 ZCode 与网关之间的报错做了专项排查，确认集群 API/网关本身正常，主要失败来自 ZCode 客户端侧遗留的旧 provider 绑定。

**审核结论：本周期任务完成，生产基线稳定，性能与质量达到验收条件；建议有条件通过，条件为补跑完整 500 题 GSM8K、完成 ZCode 旧 provider 解绑。**

---

## 2. 任务成果清单

| 编号 | 任务 | 完成结果 | 验收依据 |
|---|---|---|---|
| A-01 | 7.0.0 升级后性能回归定位 | 完成 NIC、GPU、CPU、recipe、容器、启动链路六类单变量排查；PR 仍低 6–13%，无法归因于可改配置 | 7.0 调优报告第 4–10 节；`pr7-*.json`、`gpu-pr7*.csv` |
| A-02 | NIC 底层审计与固件适配 | 四机 16 口全量读回；链路 100G/FEC RS/PFC 3/5/trust dscp/ring 4096/TX 1024；512k 压测丢包类计数全 0；buffer 恢复 523296 并固化 | 7.0 报告第 4 节；NIC 检查日志、`ib_write_lat/bw` 记录 |
| A-03 | GPU 频率与 EC 温控恢复 | 解除 `-lgc 0,2400` 软件锁，恢复默认无上限；max SM 3003 MHz；负载 2.44–2.46 GHz、80–86°C，无软/硬件降频 | 7.0 报告第 5 节；`gpu-pr7*.csv` |
| A-04 | 高性能核/能效核任务审计 | 完成 20 核拓扑与占用采样；全性能核 cpuset A/B 为 5811 vs 5905 tok/s（−1.6%），判定粗粒度绑核负收益并回退默认 | 7.0 报告第 6 节 |
| A-05 | 容器组件重编译/版本梳理 | 结论：无需整镜像重编；torch/NCCL/FlashInfer/sgl_kernel 为预编译或与内核 ABI 无关；b12x、roce_proxy、Triton 已按新工具链重建；仅 `nvfancontrol` 需重编/签名 | 7.0 报告第 8 节 |
| A-06 | recipe 分词路径复核 | 容器内 `serving_chat.py`、`dsv41_recipe.py` md5 与安装版一致；64k prompt recipe/tokenizer 逐 ID 相等（65540=65540）；排除分词导致回归 | 7.0 报告第 7 节；recipe probe 记录 |
| A-07 | 持久化、自检与防丢参数启动 | 建立 `prod-profile.env` 单一基线、`boot-prod.sh` fail-closed 预检、启动后全检、15 分钟快检、5 分钟 NIC 只读检查 | 7.0 报告第 9 节；`last-boot.json`、自检日志 |
| A-08 | 四机内核与驱动回滚 | 按 02 → 03 → 04 → 01 顺序回滚至 6.17.0-1031 + 580.173.02；生产 23:38 UTC 恢复，`/health` 200 | 回滚报告第 3–5 节；`boot-prod-20261022-233453.log` |
| A-09 | GRUB 启动项纠错与固化 | 首次 `1>1` 误入 7.0 recovery 并触发 `pam_nologin`；核对后确认 `1>2` 为 6.17 普通模式；四机持久化 `GRUB_DEFAULT="1>2"`，`next_entry` 为空 | 回滚报告 3.3；`INCIDENT.md` |
| A-10 | NVIDIA 用户态降级与一致性保护 | 12 个用户态包降至 `580.173.02-1ubuntu1` 并 hold；启动脚本同时校验 `nvidia-smi` 与 `modinfo nvidia`，防止 API mismatch | 回滚报告 3.4/4.2 |
| A-11 | 回滚后性能复测 | PR 七档 5555.6–6468.1 tok/s，全部高于 A6；DE c1 91.64、c8 249.10；warm 6463（最终复检 6415） | 性能汇总表；PR/DE 原始 JSON |
| A-12 | 质量门复验 | GSM8K 20/20（content=1.0、marker=1.0、err=0）；qeval 71/75（94.7%）；needle 未重跑但上轮 4/4 | `gsm8k-20.summary.json`、`qeval-6.17-rollback.json` |
| A-13 | RoCE 自愈误报修复 | 修正 `heal-if-down`：栈运行时只读 check，零漂移 exit 0；四机恢复 `running`，`Result=success` | 回滚报告 4.4；`roce-ring-apply.sh` 副本 |
| A-14 | 内核/驱动版本锁 | 22 个精确锁包 + 7 个 guard hold（共 29）；APT pin 1001；29 包 unattended 黑名单；4 个自动升级单元 masked；30 分钟周期校验 | 回滚报告 4.5；`version-lock/host-01..04.txt` |
| A-15 | 启动门禁与自检增强 | 回滚后自检由 42/42 扩至 post-boot 46/46、fast 44/44；新增每机 `driver`、`version_lock`；启动预检失败即拒绝起栈 | 最终自检日志与 JSON |
| A-16 | ZCode/网关 API 报错排查 | 确认集群 API、网关、后端健康；44 条 `model.request.failed` 中 42 条来自旧 provider `192.168.5.65:8003`；有效入口 `192.168.0.1:8003/v1` 正常 | 第 9 节；ZCode 日志统计 |
| A-17 | 文档与证据归档 | 形成回滚报告、7.0 历史报告、运维交接清单、版本锁证据和两级 SHA256 校验 | 第 10 节；`SHA256SUMS` |

---

## 3. 任务时间线

时间均为 UTC。

| 时间 | 事件 | 结果 |
|---|---|---|
| 10-22 12:24–12:33 | 生产维护窗停止旧栈并启动 recipe 分词栈 | 四机容器在位，`/health` 200，`BOOT_RC=0` |
| 10-22 下午 | 发现 prefill 相对 A6 锚点回归，开始 NIC/GPU/CPU/recipe 单变量审计 | 确认 7.0 下 PR 低 5.7%–12.6%，DE 仅低 1–2.6% |
| 10-22 16:17 | 7.0 最终靴启动 | 启动预检通过 |
| 10-22 16:27 | 7.0 最终 post-boot 自检 | 38/38 PASS，warm 中位 5797 tok/s |
| 10-22 16:38 | 7.0 最终 fast 自检 | 36/36 PASS |
| 10-22 17:12 | 停止生产栈并保存回滚前 profile、last-boot、自检和运行面快照 | 回滚前状态完整留档 |
| 10-22 傍晚 | 02 首试：`grub-reboot "1>1"` 误入 7.0 recovery，现场断电恢复；随后处理 NVIDIA API mismatch 并定稿降级脚本（19:06） | 确认 `1>2` 才是 6.17 普通模式；02 验证通过 |
| 10-22 晚间 | 按 02 → 03 → 04 → 01 顺序完成其余主机回滚，01 最后 | 四机进入 6.17 普通模式 |
| 10-22 23:34–23:38 | 6.17 生产启动预检并拉起栈 | 四机 `r3prod` 在线，`/health` 200，`boot_rc=0` |
| 10-22 23:42 | 回滚后首次 post-boot | 42/42 PASS，warm 6463 tok/s |
| 10-22 23:44–23:57 | PR 七档、DE c1/c8 复测 | PR 全部超过 A6，DE 91.64/249.10 |
| 10-22 23:57 后 | GSM8K 20 题、qeval 75 题 | 20/20；71/75 |
| 10-23 00:06 | 版本锁前最终复检 | 42/42 PASS，warm 6446 |
| 10-23 00:41–00:42 | 版本锁安装后快检/全检 | fast 44/44；post-boot 46/46，warm 6452 |
| 10-23 00:48 | 一次性升级服务由 disabled 强化为 masked | 46/46 PASS，warm 6420 |
| 10-23 00:55:42 | guard hold 纳入后最终 post-boot | **46/46 PASS，warm 6415** |
| 10-23 00:56:48 | 最终 fast | **44/44 PASS** |
| 10-23 03:04–05:47 | ZCode/网关报错专项排查 | 定位为客户端旧 provider 绑定，集群侧正常 |
| 10-23 06:07 | 审核时点只读复核 | 四机 6.17/580.173.02、`holds=29`、`running`、0 failed unit、`/health` 200 |

---

## 4. 当前生产基线

| 项目 | 当前值 | 验证方式 |
|---|---|---|
| 内核 | `6.17.0-1031-nvidia`（四机） | `uname -r`、启动允许表、自检 |
| NVIDIA 用户态 | `580.173.02`（12 包） | `nvidia-smi` |
| NVIDIA 内核模块 | `580.173.02` | `modinfo -k $(uname -r) -F version nvidia` |
| GRUB 默认 | `GRUB_DEFAULT="1>2"`，`next_entry` 空 | `/etc/default/grub`、`grubenv` |
| NIC 固件 | `28.50.1002`（16 口，未降级） | `ethtool -i` |
| RX / TX ring | `4096` / `1024` | `ethtool -g` |
| Lossless buffer | `19872,523296,0,0,0,0,0,0` | `mlnx_qos -i` |
| PFC / trust | `0,0,0,1,0,1,0,0` / `dscp` | `mlnx_qos -i` |
| GPU 频率/温控 | 默认无上限；EC auto；max SM 3003 MHz | `nvidia-smi`、`gb10-clock-cap` 状态 |
| 镜像 | `192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c` | digest 校验 |
| 镜像 digest | `sha256:47f6d91a…e2ffc4` | `boot-prod.sh` |
| env / overlay / adapter | 56 键 / 28 件 / 97 件，指纹 `c41b1a45` | 四机逐项比对 |
| recipe | 0.2.0；`serving_chat.py 3151a2ed…`、`dsv41_recipe.py da98467d…` | 容器 md5 + 功能探针 |
| 服务参数 | `max_total_num_tokens=9600000`、`context_length=600000`、`max_running_requests=16` | `/server_info` |
| 版本锁 | 29 hold（22 精确 + 7 guard）、pin 1001、4 单元 masked | `version-lock.sh check` |
| 自检 | post-boot 46/46；fast 44/44 | 最终日志/JSON |
| 主机状态 | 四机 `running`，failed unit 0 | `systemctl` |
| 生产 API | `127.0.0.1:8899`，`/health` 200 | 审核时点复核 |

---

## 5. 更新与调优成果（7.0 窗口）

### 5.1 网卡底层审计

四机 16 个 RoCE 口逐口读回，配置一致：

- 链路 100G、FEC RS；PCIe Gen5 x4，MPS/MRRS 512。
- PFC 仅 prio3/prio5 开启，`trust dscp`，DSCP 映射未改。
- RX ring 4096、TX ring 1024，channels 20；RX 中断合并 `rx-usecs=8`、`rx-frames=128`，CQE RX 开启。
- PR 512k 压测期间 `rx_discards_phy`、`rx_pause`、`tx_pause`、`rx_out_of_buffer`、CNP 全部为 0。
- `ib_write_lat` 2 B 典型 1.74 µs；`ib_write_bw` 单口 97.93 Gb/s，达到单口线速。
- `prof_sel=2` 与更新前一致，未改。

固件 28.50.1002 的变更是 PCC 时延/竞争修复、LRO 死锁修复等缺陷修复，不包含可直接开启的 RoCE 性能新增项。固件升级把 lossless shared buffer 默认值从 523296 改为 458496；按用户要求恢复 523296 并固化。buffer A/B 差异落在单次 PR 噪声范围内，保留该值的原因是 PFC prio3/prio5 在交换网络下需要原有突发吸收余量，而不是它能解释本次回归。RX ring 4096 经测试可行，保留。

### 5.2 GPU 频率与温控

- 原 `gb10-clock-cap.service` 执行 `nvidia-smi -lgc 0,2400`。已 `disable --now` 并执行 `-rgc`，恢复默认无频率上限。
- 四机 max SM 均为 3003 MHz；负载持续时钟约 2444–2457 MHz，最高 2483 MHz。
- 负载温度中位 80–82°C、最高 83–86°C；`SW Power Cap`、`HW Thermal Slowdown` 均未触发。
- 约 2.45 GHz 的持续频率来自 EC/功耗策略，不是残留软件锁；`-lgc 3003` 诊断也只能到约 2528 MHz。
- `nvfancontrol` 为 DKMS 模块，因 Secure Boot 的 MOK 未注册而无法加载；保持 EC auto，未关闭 Secure Boot，也未把风扇覆盖列为生产必需能力。

### 5.3 CPU 拓扑与绑核

20 个逻辑核：

| 类别 | CPU | 频率 |
|---|---|---|
| 能效核 | `0-4, 10-14` | 2.808 GHz |
| 性能核 | `5-9, 15-19` | 3.9 GHz |

内核参数 `isolcpus=8-9 rcu_nocbs=8-9`。`ncclpin.so` 已于 2026-10-15 退役，`LD_PRELOAD` 为空，`NCCL_IGNORE_CPU_AFFINITY=1`。64k prefill 采样显示 CPU5 约 48% usr + 50% sys、CPU19 约 80% usr、其余核 1–3%、CPU8-9 100% idle，瓶颈在 GPU 计算路径。

容器 cpuset 收到 10 个性能核的 A/B：64k 中位 5811 tok/s，默认全核 5905 tok/s，性能核版本低约 1.6%，且出现线程争抢。已回退默认 `0-19`，结论是不做整容器粗粒度绑核。

### 5.4 容器重编译与版本梳理

| 组件 | 版本/构建方式 | 结论 |
|---|---|---|
| torch | 2.13.0+cu130 | 无需重编译 |
| NCCL | 2.29.7（torch 内置） | 无独立旧二进制，无需替换 |
| b12x CuTe kernels | 启动时 JIT；Cutlass DSL 4.6.2、CUDA Python 13.4.1、`opt-level=3` | 每靴按当前工具链重建 |
| roce_proxy | 源码哈希缓存 JIT；GCC 13.3、libibverbs 50.0、`-O2` | 缓存已重建，非旧驱动残留 |
| FlashInfer | 0.6.18+cu130，预编译 cubin | 与内核 ABI 无关，无需重编 |
| Triton | 3.7.1 | autotune/cache 已在最终靴重建 |
| sgl_kernel / FlashInfer 预编译件 | 预编译 | 不依赖 7.0.0 内核 ABI |
| nvfancontrol | DKMS，已签名 | 唯一需重编/重签项；受 MOK 未注册阻塞 |

**结论：不需要为新内核重建整镜像，也不存在旧的 6.17 驱动编译产物拖慢 7.0.0 的问题。**

### 5.5 recipe 分词复核

- 容器内 `serving_chat.py` md5 `3151a2edf2c21e4d3492dff5bbc6ec10`。
- 容器内 `dsv41_recipe.py` md5 `da98467d3fd7d5019ea025b3d5273a20`。
- 功能探针：`recipe_ids=7, tokenizer_ids=7, equal=true`。
- 64k PR 同款 serving 文本 recipe 与 tokenizer 逐 ID 相等，`65540=65540`。

recipe 只在“recipe 渲染后的 prompt 与服务 prompt 字节完全一致”时生效，当前生产请求满足该条件。**prefill 差异不能归因于分词路径或 recipe 适配。**

---

## 6. 回滚成果

### 6.1 执行方式

1. 停止 `r3prod` 栈，保存回滚前 profile、`last-boot`、自检和 head/02 运行面快照。
2. 02 先试，成功并验证后再做 03、04，01 最后。
3. 每台先一次性 `grub-reboot "1>2"` 验证 6.17 普通模式，成功后持久化 `GRUB_DEFAULT="1>2"` 并 `update-grub`。
4. 每台启动后验证 `uname -r`、`nvidia-smi`、`modinfo`、NIC 四口、Docker GPU 容器；任一台失败即停止后续。

### 6.2 GRUB 索引纠错

首次对 02 使用 `grub-reboot "1>1"`，实际进入的是 **7.0 recovery（`recovery nomodeset`）**，不是 6.17，导致 `pam_nologin` 长时间阻塞，现场断电重启后恢复。核对 `/boot/grub/grub.cfg` 后确认：

| 子菜单 | 实际条目 |
|---|---|
| `1>0` | 7.0.0 普通 |
| `1>1` | 7.0.0 recovery |
| `1>2` | **6.17.0 普通** |
| `1>3` | 6.17.0 recovery |

后续全部使用 `1>2`。该事件已记录在 `INCIDENT.md`，结论是操作索引误判，不是 6.17、NIC 固件或 NVIDIA 驱动故障。四机无 BMC，错误启动项只能现场断电，这是当前环境的硬约束。

### 6.3 NVIDIA 驱动栈处理

- 6.17 自带 `nvidia.ko` 是 580.173.02 专有模块（Canonical 签名），不是 7.0 的 580.178.04 open 模块。
- 只换内核、不换用户态会得到 `NVRM: API mismatch`，`nvidia-smi`、`nvidia-persistenced`、`nvidia-cdi-refresh` 全部失败。
- 四机用户态降至 `580.173.02-1ubuntu1`，移除无头机不需要的 `nvidia-driver-580-open`、`xserver-xorg-video-nvidia-580`，修复 EGL 文件冲突后 hold 12 个包。
- `nvidia-kernel-common-580` 保持 `580.178.04`；该包不提供与内核模块 ABI 绑定的用户态库，当前组合实测正常。
- NIC 固件 28.50.1002 未降级，与 6.17 的 mlx5 驱动兼容。

### 6.4 回滚结果

- 生产 2026-10-22 23:38 UTC 恢复，四机 `r3prod-head` / `r3prod-worker` 在线，`/health` 200。
- `last-boot.json`：`boot_rc=0`、`selfcheck_rc=0`。
- 回滚未改镜像、overlay、adapter、recipe、NIC 固件、ring/buffer/PFC 或 GPU 策略，性能对照为单变量比较。

---

## 7. 性能与质量结果

### 7.1 PR 七档（tok/s）

口径：sparkDash `repeated`，每档 3 次独立调用取中位；测试期间生产栈在线，未改参数。

| 输入 tokens | 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6.17 中位 | **5555.6** | **6161.6** | **6452.8** | **6468.1** | **6194.6** | **5559.6** | **4376.9** |
| A6 锚点 | 5522.5 | 6040.2 | 6271.3 | 6289.3 | 6048.1 | 5427.9 | 4290.0 |
| 对 A6 | +0.6% | +2.0% | +2.9% | +2.8% | +2.4% | +2.4% | +2.0% |
| 7.0 中位 | 4825.7 | 5620.0 | 5913.3 | 5797.1 | 5684.2 | 4873.9 | 3891.2 |
| 对 7.0 | +15.1% | +9.6% | +9.1% | +11.6% | +9.0% | +14.1% | +12.5% |

8k 档 +0.6% 在单次 PR 噪声范围内；16k–512k 的 +2.0%–+2.9% 与 7.0 的 −5.7%–−12.6% 形成方向明确的对照。

### 7.2 DE 与 warm gate

| 项 | 6.17 中位 | A6/阈值 | 7.0 | 对锚点 | 对 7.0 |
|---|---:|---:|---:|---:|---:|
| DE c1 (tok/s) | **91.64** | 88.64 | 86.38 | +3.4% | +6.1% |
| DE c8 (tok/s) | **249.10** | 242.83 | 240.13 | +2.6% | +3.7% |
| 64k warm (tok/s) | **6463**（最终复检 6415） | 5600 阈值 | 5797 | +15.4%（最终 +14.6%） | +11.5%（最终 +10.7%） |

warm 五次：`5543.7 / 6494.3 / 6303.2 / 6468.4 / 6458.5`；首次为冷读，按既定规则丢弃后，其余四次中位 6463。最终复检五次 `6472.5 / 6413.1 / 6417.4 / 6411.5 / 6435.2`，同样丢弃首次后中位 **6415**，仍高于阈值约 14.6%。

### 7.3 质量门

| 项 | 结果 | 说明 |
|---|---|---|
| GSM8K 20 题 | **20/20，content=1.0，marker=1.0，err=0** | 8-shot、temp 0.6、max_tokens 1024、并发 1 |
| qeval 75 题 | **71/75（94.7%）** | code 24/25、format 7/7、json 6/8、math 13/14、prose 5/5、reason 16/16；1 题触顶 |
| needle | 本轮未重跑 | 回滚不改 logits/长上下文路径；上一轮 8/32/64/128k 4/4 PASS |

qeval 的 4 个失败为 `code_interval_intersect`、`json_escape`、`json_count`、`math_m9`（后者 `finish_reason=length`）。qeval 自带参考记录为 72/75，当前 71/75，未发现回滚引入的系统性质量下降。完整 500 题 GSM8K 未在本次窗口重跑。

### 7.4 结果解释

同一镜像、同一 NIC 固件/ring/buffer/PFC、同一 GPU 频率策略，只把内核与 NVIDIA 用户态/模块从 7.0/580.178.04 换回 6.17/580.173.02，PR 从低 6–13% 变为高 0.6–2.9%。这使“7.0 内核 + 新驱动路径”成为最强相关项；NIC buffer、ring、recipe、CPU 绑核均已被单变量排除。DE 也同步恢复，说明改善不只发生在长 prompt prefill。

---

## 8. 功能修复与增强

### 8.1 fail-closed 启动

唯一入口：

```bash
bash ~/migrate-assets/prod/boot-prod.sh
```

启动前逐项校验，任一失败即拒绝：

- env 文件 md5 与 56 个键；
- overlay manifest 与 28 件挂载；
- recipe manifest 与容器内 md5；
- 四机 adapter 整树指纹（97 件，`c41b1a45`）；
- 启动脚本 md5；
- 镜像 digest；
- 内核允许表（只接受 `6.17.0-1031-nvidia`）；
- NVIDIA 用户态与 `nvidia.ko` 必须同时为 `580.173.02`；
- 版本锁 hold/pin/GRUB/自动升级单元；
- NIC 固件/ring/buffer/PFC 主机 profile；
- 无残留 `r3prod`/`r3boot` 容器；
- API 端口 8899 空闲。

通过后走标准产线链：

```text
tools/boot-with-slotlock.sh → ~/migrate-assets/bin/r3-boot-arm.sh
```

启动后自动执行 `selfcheck-prod.sh --post-boot`，写 `~/migrate-assets/prod/last-boot.json`；自检失败时启动脚本以 rc=4 退出，避免“起来了但参数不对”被当成成功。

### 8.2 自检扩展

| 单元/脚本 | 频率/时机 | 行为 |
|---|---|---|
| `roce-ring-boot.service` | 每次启动，docker 之前 | 重放 ring/buffer/trust/PFC；四机 enabled |
| `roce-ring-check.timer` | 每 5 分钟 | 只读检查 NIC profile；栈停时才 apply |
| `prod-selfcheck.timer` | 每 15 分钟 | head 上跑 `--fast`；只报红，不重启栈 |
| `prod-version-lock.timer` | 每 30 分钟 | 校验内核/驱动、GRUB、29 hold、pin、自动升级单元 |
| `selfcheck --post-boot` | 每次生产启动后 | 全量静态检查 + recipe 探针 + 5×64k warm gate |
| `selfcheck --perf` | 人工/维护窗 | 只跑 warm gate |

自检项从 7.0 窗口的 38/36 扩展到回滚后的 **46 post-boot / 44 fast**，新增每机 `driver` 和 `version_lock` 检查。

### 8.3 版本锁

四机安装同一套锁：

| 层 | 配置 | 作用 |
|---|---|---|
| 精确包 hold | 7 个 `6.17.0-1031` 内核包 + 12 个 580.173.02 用户态包 + `nvidia-kernel-common-580`、`nvidia-kernel-source-580-open`、`nvidia-firmware-580-580.173.02`，共 22 个 | apt 不自动升级/移除 |
| guard hold | 4 个 7.0 内核 meta/module + `libxnvctrl0`、`nvidia-modprobe`、`nvidia-settings`，共 7 个 | 固定 GRUB 菜单顺序和现有 NVIDIA 工具版本 |
| APT pin | `/etc/apt/preferences.d/99-prod-version-lock`，`Pin-Priority: 1001` | 22 个受锁包 candidate 锁定为已安装精确版本 |
| 自动升级屏蔽 | `/etc/apt/apt.conf.d/52-prod-version-lock`（29 包黑名单）；`apt-daily*.timer`、`nvidia-spark-ota-check.timer` masked | 关闭 unattended 和定时检查 |
| DGX 一次性升级 | `nvidia-spark-run-apt-upgrade-once.service` masked | 阻断 `apt full-upgrade` + `reboot` 路径 |
| 周期校验 | `version-lock.sh check`；`prod-version-lock.timer`；启动预检与自检调用 | 漂移 fail-closed |

guard 包只校验 hold、不做统一精确 pin，原因是 `nvidia-modprobe` 在 01/02 为 `610.43.02-1ubuntu1`、03/04 为 `610.57.04-1ubuntu1`。

验证结果：

- 四机 `version-lock.sh check` 均 OK（`holds=29 lock=22 guard=7`）。
- `apt-get -s full-upgrade` 对 `linux-*`、`nvidia-*`、`libnvidia-*`、`libxnvctrl*` 无任何 `Inst`/`Remv`。
- 一次性升级服务与 OTA/apt 三个定时器均为 masked；`prod-version-lock.timer` active；`prod-version-lock.service` 为 `Result=success`。
- 审核时点（06:07 UTC）再次复核四机仍全部 OK。

版本变更只能在维护窗内先解除 pin/hold（含 guard），再安装目标版本并重新 apply，最后走 `boot-prod.sh` 和 `--post-boot`。

### 8.4 RoCE 误报修复

回滚后首次巡检发现四机 `systemctl` 为 `degraded`，原因是 `roce-ring-check.service` 调用 `heal-if-down`，旧逻辑在栈运行时无条件 `exit 1`。已改为：

- 栈在跑：执行只读 `check`，零漂移 `exit 0`，有漂移 `exit 1`；
- 栈停：执行 `apply`，保留自愈能力。

修正版已安装到四机。`reset-failed` 后验证 `Result=success`，四机恢复 `running`，`systemctl --failed` 为空。该修复消除了每 5 分钟一次的假告警。

### 8.5 操作入口

```bash
# 启动（唯一入口）
bash ~/migrate-assets/prod/boot-prod.sh

# 停栈
CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash ~/migrate-assets/bin/r3-stop.sh

# 自检
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot
bash ~/migrate-assets/prod/selfcheck-prod.sh --perf

# 版本锁
/usr/local/sbin/version-lock.sh check
sudo /usr/local/sbin/version-lock.sh apply

# 日常确认
systemctl is-system-running
systemctl --failed
/usr/local/sbin/version-lock.sh check
docker ps --format '{{.Names}} {{.Status}}' | grep '^r3prod'
curl -fsS http://127.0.0.1:8899/health
```

---

## 9. ZCode 与网关 API 排查

### 9.1 结论

**集群 API、网关和后端服务正常，报错主因不在集群侧。** 调查窗口内网关侧正常推理请求均返回 200；有效 base URL 为 `http://192.168.0.1:8003/v1`，网关健康检查 200，认证冒烟请求约 585 ms 返回 200。失败集中在 ZCode 客户端遗留的旧 provider 绑定 `cffc3a51-b294-4cad-8f50-738aeedeb0c4` → `http://192.168.5.65:8003`。

### 9.2 链路

```text
ZCode → Mac 192.168.0.1:8003（responses-gateway-mac）
      → concurrency-proxy-v2-mac
      → concurrency-proxy:8001
      → 集群 127.0.0.1:8899
```

Mac 接口：en0 `192.168.0.1`（当前有效）、en1 `192.168.5.71`、en11 `192.168.5.65`（旧 provider 指向）。从集群侧访问 `.65`/`.71` 可建立 TCP，但收不到 HTTP 响应；网关日志中没有对应请求。有效入口 `.1` 的请求均有正常响应。

### 9.3 报错归类

调查窗口内 `model.request.failed` 共 44 条：

| 来源 | 条数 | 说明 |
|---|---:|---|
| 旧 provider `cffc…` → `192.168.5.65:8003` | 42 | 40 条 `network_error` + 2 条 `cancelled`；多次自动重试，最高 15 次 |
| `dgxspark-v41` → `192.168.0.1:8003/v1` | 1 | `reason=unknown`，持续约 743 s；同一时刻网关返回 200、240772 字节 |
| 公有云 `deepseek` | 1 | `cancelled` |

另有 8 条 `zcode_protocol.v4.gateway_error`，均为客户端本地协议/会话错误，不是网关 HTTP 5xx：

- 3 条 `project.remote-project-required`（resume/initialize）；
- 1 条 `Session not found`（hydrate）；
- 4 条命令执行错误：2 条 provider registry 中不存在旧 provider，2 条 `no_active_turn`。

`hook.run.failed` 为本地 mimosa 插件 hook 失败，与网关无关。

### 9.4 处置建议

1. 在 ZCode 客户端把任务/会话重新绑定到当前 provider `dgxspark-v41`（`http://192.168.0.1:8003/v1`），或新建任务，清除旧 `cffc…`/`.65` 绑定。
2. 客户端侧 743 s 长请求与 75 s 客户端超时不匹配的请求需跟踪（2026-10-24 复核更正：该请求来自本机 ZCode CLI，版本 0.17.0 为当前发行版本而非陈旧客户端；应作为当前版本的客户端侧缺陷跟踪，而非升级/退役旧客户端）。
3. 网关侧在客户端断开时取消上游请求；调查中观察到两条零字节、持续 656/677 s 的上游流。
4. 网关容器环境中的静态 API key 应按安全流程轮换并移出明文环境变量；本文不记录任何密钥值。
5. 旧接口 `.65`/`.71` 不应作为生产 provider 入口；如需保留，应明确标注为调试地址。

本次排查未修改生产、网关或集群配置。

---

## 10. 文档与证据清单

### 10.1 文档

| 文档 | 路径 | 用途 |
|---|---|---|
| 本成果清单 | `deploy/prod/reports/2026-10-23-audit-archive/TASK-ACHIEVEMENTS-2026-10-22_23.md` | 审核归档总表 |
| 6.17 回滚报告 | `deploy/prod/reports/2026-10-22-6.17-rollback/ROLLBACK-REPORT-2026-10-22.md` | 当前权威回滚记录 |
| 7.0 调优报告 | `deploy/prod/reports/2026-10-22-7.0.0-tuning/WORK-REPORT-2026-10-22.md` | 历史调优与排除过程 |
| 运维交接清单 | `deploy/prod/reports/2026-10-22-7.0.0-tuning/OPS-RUNBOOK.md` | 日常巡检、启动、异常处置 |
| 生产基线 | `deploy/prod/README.md` | 当前基线、版本锁、操作入口 |
| 回滚事件记录 | `deploy/prod/reports/2026-10-22-6.17-rollback/evidence/INCIDENT.md` | GRUB 误选与恢复时间线 |

### 10.2 证据

目录：`deploy/prod/reports/2026-10-22-6.17-rollback/evidence/`

| 证据 | 内容 |
|---|---|
| `boot-prod-20261022-233453.log` | 6.17 生产启动完整日志 |
| `selfcheck-20261022-234245.log/.tsv` | 回滚后首次 post-boot 42/42，warm 6463 |
| `selfcheck-20261023-000538.log/.tsv` | 版本锁前最终 42/42，warm 6446 |
| `selfcheck-20261023-005415.log/.tsv` | **最终 post-boot 46/46，warm 6415** |
| `selfcheck-20261023-005620.log/.tsv` | **最终 fast 44/44** |
| `selfcheck-postboot-final.json` | 版本锁前 42/42 JSON |
| `selfcheck-fast-final.json` | 最终 fast 44/44 JSON（00:56:48） |
| `warm-20261023-005415-1..5.json` | 最终 warm 五次原始读数 |
| `version-lock/` | 版本锁脚本、unit、pin/blacklist、四机终态、最终自检、校验和 |
| `last-boot.json` | `boot_rc=0`、`selfcheck_rc=0` |
| `prod-profile.env` | 回滚后生产 profile |
| `pr_*.json` | PR 8k–512k 每档 3 次原始读数 |
| `de_c1.json` / `de_c8.json` | DE 五次原始读数 |
| `gsm8k-20.summary.json` / `.raw.jsonl` | GSM8K 20 题冒烟 |
| `qeval-6.17-rollback.json` / `qeval.log` | qeval 75 题 |
| `performance-summary.tsv/.json` | 性能汇总 |
| `bench-6.17.sh` / `bench-6.17.log` | 可重放复测脚本与日志 |
| `host-01..04.txt` | 版本锁安装前四机终态 |
| `production-state.txt` | `/health`、`server_info`、容器状态 |
| `INCIDENT.md` | GRUB 误选事件 |
| `SHA256SUMS` | 本目录 87 个文件的校验和 |

补充证据：`version-lock/host-01..04.txt` 记录四机最终 `holds=29 lock=22 guard=7`、masked 单元、timer active、`failed_units=0`、升级模拟无 `Inst/Remv`。

### 10.3 校验和

两级清单均已 `sha256sum -c` 通过：

```text
79886779d894b996d3f785f14ba5c653dd2abcaa454883fb61750385ebc8a172  evidence/SHA256SUMS
5d6a03e7cda011a96b8dbbb61f236b452aef450148aeafd479f454834dc1a482  evidence/version-lock/SHA256SUMS
```

本审核目录的文件清单与校验和见同目录 `SHA256SUMS`。

### 10.4 代码与配置变更

已修改（工作区，未提交/推送）：

- `deploy/prod/prod-profile.env`：内核允许表改为 6.17；新增 `PROD_NVIDIA_DRIVER_ALLOW=580.173.02`。
- `deploy/prod/boot-prod.sh`：新增用户态 + 内核模块双重校验和版本锁预检。
- `deploy/prod/selfcheck-prod.sh`：新增每机 `driver`、`version_lock`，最终 44/46 项。
- `deploy/prod/roce-ring-apply.sh`：修复 `heal-if-down` 在栈运行时的误报。
- `deploy/prod/README.md`、`OPS-RUNBOOK.md`、7.0 历史报告：同步回滚与版本锁状态。

新增（未跟踪）：

- `deploy/prod/version-lock.sh`
- `deploy/prod/install-version-lock.sh`
- `deploy/prod/prod-version-lock.service`
- `deploy/prod/prod-version-lock.timer`
- `deploy/prod/reports/2026-10-22-6.17-rollback/`（报告与证据）
- `deploy/prod/reports/2026-10-23-audit-archive/`（本清单）

7.0 窗口曾有两个本地提交（未推送）：`6c13a0d`、`bd732d4`。回滚、版本锁和本归档相关变更目前仍在工作区，未提交、未推送。

---

## 11. 遗留风险与待办

| 项目 | 等级 | 现状 | 建议 |
|---|---|---|---|
| 完整 500 题 GSM8K 未重跑 | 中 | 仅 20 题冒烟 + qeval 75 题 | 低峰补跑，记录 `accuracy_content`，作为正式质量签字依据 |
| ZCode 旧 provider 绑定 | 中 | 44 条失败中 42 条来自 `cffc…`/`.65` | 客户端重新绑定 `dgxspark-v41` 或新建任务；清理旧 provider |
| 网关断开后未取消上游 | 中 | 观察到零字节长流 | 网关侧增加客户端断开取消逻辑 |
| 客户端 743 s 长请求超时 | 低 | 本机 CLI 0.17.0（当前版本）的客户端侧超时/解析问题；743 s 与 75 s 超时不一致 | 作为当前版本缺陷跟踪；随客户端版本更新验证是否修复 |
| 网关静态 API key | 中（安全） | 容器环境中为明文 | 按安全流程轮换并移出明文环境变量；本文不记录密钥 |
| 无 BMC | 中 | GRUB 误选只能现场断电 | 变更启动项前先打印菜单项，先 `next_entry` 验证再持久化 |
| 手动风扇不可用 | 低 | MOK 未注册，EC auto 正常 80–86°C | 如确需，维护窗内按安全流程注册 MOK；不关闭 Secure Boot |
| guard 包版本差异 | 低 | `nvidia-modprobe` 01/02 与 03/04 版本不同 | 保持 hold 校验，不做统一 pin |
| 生产在线跑基准 | 低 | 有客户端流量时单次 PR 波动 | 以 3 次中位和 warm gate 判定，不以单发下结论 |
| `/tmp` 原始记录 | 低 | 部分原件在 `/tmp` | 已复制到 evidence；按保留策略清理，`/tmp` 不作长期记录 |

---

## 12. 审核结论与验收

### 12.1 验收结果

| 维度 | 标准 | 实际 | 结论 |
|---|---|---|---|
| 生产可用性 | 四机容器在线，`/health` 200 | 01 head + 02/03/04 worker 在线，200 | 通过 |
| 主机状态 | `running`，无 failed unit | 四机 `running`，0 failed | 通过 |
| 内核/驱动 | 6.17.0-1031 + 580.173.02，四机一致 | 四机一致，模块/用户态匹配 | 通过 |
| 版本锁 | `holds=29 lock=22 guard=7`，无升级计划 | 四机 OK，`apt-get -s full-upgrade` 无 Inst/Remv | 通过 |
| 自检 | post-boot 46/46，fast 44/44 | 46/46（00:55:42），44/44（00:56:48） | 通过 |
| 性能 | PR 全部 ≥ A6；warm ≥ 5600 | PR +0.6%–+2.9%；warm 6415 | 通过 |
| 质量 | GSM8K 冒烟全对，qeval 无系统性下降 | 20/20；71/75（参考 72/75） | 有条件通过（补跑 500 题） |
| API 排查 | 明确故障边界 | 集群/网关正常；旧 provider 绑定 | 通过（待客户端解绑） |
| 文档证据 | 报告、原始数据、校验和齐全 | 两级 SHA256 均验证通过 | 通过 |

### 12.2 审核意见

1. 本周期完成了从 7.0.0 升级后诊断、单变量排除、逐台回滚、性能恢复、质量复验到版本固化的闭环，关键结论均有原始数据支撑。
2. 回滚后的生产基线明确且可重复：`6.17.0-1031-nvidia` + `580.173.02` + NIC 固件 `28.50.1002` + ring 4096 + buffer 523296 + GPU 默认频率/EC auto。
3. 性能恢复是单变量结果：镜像、NIC 配置、GPU 策略未变，仅内核与 NVIDIA 驱动栈变化，PR 由低 6–13% 转为高 0.6–2.9%。
4. 版本锁已形成多层防护，但属于“配置锁”而非“不可绕过”；任何变更必须走维护窗和完整复验。
5. 两项条件性遗留：完整 500 题 GSM8K 未跑；ZCode 旧 provider 绑定需在客户端侧清理。二者不影响当前生产运行，但应在正式验收前关闭。

### 12.3 签字栏

| 角色 | 姓名/签字 | 日期 | 意见 |
|---|---|---|---|
| 平台负责人 |  |  |  |
| 当班运维 |  |  |  |
| 性能/模型负责人 |  |  |  |
| 网络安全负责人 |  |  |  |
| 审核归档人 |  |  |  |

---

## 13. 附录：审核复核命令

```bash
# 1) 四机基线与版本锁
for h in dgxspark01 dgxspark02 dgxspark03 dgxspark04; do
  ssh "$h" 'uname -r; nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits | head -1; /usr/local/sbin/version-lock.sh check; systemctl is-system-running'
done

# 2) 生产健康与容器
docker ps --format '{{.Names}} {{.Status}}' | grep '^r3prod'
curl -fsS http://127.0.0.1:8899/health

# 3) 自检
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast

# 4) 证据校验
cd deploy/prod/reports/2026-10-22-6.17-rollback/evidence
sha256sum -c SHA256SUMS
(cd version-lock && sha256sum -c SHA256SUMS)

# 5) 最终自检计数
python3 - <<'PY'
import json
for p in [
 'reports/2026-10-22-6.17-rollback/evidence/version-lock/version-lock-postboot-20261023-005542.json',
 'reports/2026-10-22-6.17-rollback/evidence/version-lock/version-lock-fast-20261023-005648.json',
]:
    d=json.load(open(p))
    print(p, d['timestamp'], d['mode'], len(d['checks']), 'fails=', d['fails'])
PY
```

审核时点只读复核结果（2026-10-23 06:07 UTC）：

```text
dgxspark01..04  kernel=6.17.0-1031-nvidia  driver=580.173.02
version-lock OK  holds=29 lock=22 guard=7  grub=1>2
systemctl is-system-running=running  failed_units=0
r3prod-head + r3prod-worker x3  Up 7 hours
/health=200
```

---

**文档结束。**
