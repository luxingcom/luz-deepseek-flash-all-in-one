# 生产固化档（r3prod / 0.3.2-r032c）

本目录是生产栈的唯一入口与只读自检面。2026-10-22 23:35 UTC 按用户指令将
四机内核回滚到 `6.17.0-1031-nvidia`，NVIDIA 用户态与内核模块同步回退到
`580.173.02`；NIC 固件保持 `28.50.1002`，未降级。以下值由
`boot-prod.sh` fail-closed 校验，是当前生产基线。

## 工作报告与运维交接

- 审核归档成果清单：`reports/2026-10-23-audit-archive/TASK-ACHIEVEMENTS-2026-10-22_23.md`
- 回滚报告：`reports/2026-10-22-6.17-rollback/ROLLBACK-REPORT-2026-10-22.md`
- 7.0 调优报告（历史）：`reports/2026-10-22-7.0.0-tuning/WORK-REPORT-2026-10-22.md`
- 运维交接清单：`reports/2026-10-22-7.0.0-tuning/OPS-RUNBOOK.md`
- 证据副本与校验和：`reports/2026-10-22-6.17-rollback/evidence/`（含 `version-lock/`）

## 当前基线

| 项 | 值 |
|---|---|
| 内核 | `6.17.0-1031-nvidia`（四机；GRUB 默认 `1>2`） |
| NVIDIA 驱动 | `580.173.02`（用户态与 `nvidia.ko` 必须一致；580.178.04 用户态会 API mismatch） |
| 版本锁 | 22 个内核/NVIDIA 包精确版本 hold + APT pin 1001，另有 7 个 7.0/meta/工具 guard hold（共 29）；DGX 一次性 full-upgrade 服务 masked，OTA/apt 定时器 masked |
| NIC 固件 | `28.50.1002`（四机 16 口；未随内核回滚降级） |
| RX ring | `4096`（TX 1024；2026-10-09 实测可行，10-22 保留） |
| Lossless buffer (buf1) | `523296`（`19872,523296,0,0,0,0,0,0`，max 2041344） |
| PFC / trust | `0,0,0,1,0,1,0,0` / `dscp` |
| GPU 频率 | 默认，无 `-lgc/-lmc/-ac` 上限；硬件 max SM 3003 MHz |
| GPU 温控 | EC 自动（`nvfancontrol` 模块未加载；负载 72–86°C，无 SW/HW 降频） |
| 镜像 | `192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c` |
| 镜像 digest | `sha256:47f6d91a…e2ffc4` |
| adapter 指纹 | `c41b1a45`（97 件，四机一致） |
| recipe | 0.2.0；`serving_chat.py` md5 `3151a2ed…`，`dsv41_recipe.py` md5 `da98467d…` |

## 操作入口

```bash
# 启动（唯一入口；内部走 boot-with-slotlock.sh + r3-boot-arm.sh）
bash ~/migrate-assets/prod/boot-prod.sh

# 停栈（生产前缀；带三查）
CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash ~/migrate-assets/bin/r3-stop.sh

# 只读自检
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast       # 周期检查（44 项）
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot  # 起靴后全检 + 64k warm（46 项）
bash ~/migrate-assets/prod/selfcheck-prod.sh --perf       # 只跑 warm

# 版本锁只读检查（四机都要装；boot-prod/selfcheck 会调用）
ssh dgxspark01 'bash /usr/local/sbin/version-lock.sh check'
# 维护窗内重放 hold/pin/auto-upgrade 屏蔽（需要 root）
sudo /usr/local/sbin/version-lock.sh apply
```

- `prod-selfcheck.timer` 每 15 分钟跑 `--fast`；失败只报红，不重启栈。
- `prod-version-lock.timer` 每 30 分钟检查内核/驱动、GRUB 默认项、22 个精确锁包
  + 7 个 guard 包（共 29 个 hold）、APT pin 和自动升级单元；任何漂移都会报红，
  不自动改包。
- `roce-ring-check.timer` 每 5 分钟跑 `heal-if-down`：栈在跑时只做只读
  `check`（不写配置，正常时 exit 0），栈停时才 `apply`；
  `roce-ring-boot.service` 在 `docker.service` 之前重放 ring/buffer/trust/PFC。
- `boot-prod.sh` 在任何一项（env md5/56 键、adapter 指纹、镜像 digest、内核
  与 NVIDIA 驱动允许表、NIC profile、端口/容器净空）不符时直接拒绝启动，
  避免丢参数起栈。驱动校验同时读取 `nvidia-smi` 用户态版本和
  `modinfo nvidia` 内核模块版本，任一与 `PROD_NVIDIA_DRIVER_ALLOW` 不符即拒绝。

## 2026-10-22 23:35 内核回滚（当前生效）

- 四机按 02 → 03 → 04 → 01 顺序逐台回退，01 最后；GRUB 一次性入口先用
  `grub-reboot "1>2"` 验证，成功后再把 `/etc/default/grub` 持久化为
  `GRUB_DEFAULT="1>2"` 并 `update-grub`。四机当前 `next_entry` 为空，
  重启默认进入 6.17 普通模式。
- 6.17 自带 `nvidia.ko` 为 580.173.02 专有模块（Canonical 签名），用户态
  必须同为 580.173.02。四机已降级并 hold 住 `nvidia-utils-580`、
  `libnvidia-compute-580`、`nvidia-persistenced` 等；`nvidia-driver-580-open`
  和 `xserver-xorg-video-nvidia-580` 已移除（无头服务器）。
- NIC 固件 28.50.1002 与 6.17 的 mlx5 驱动兼容，四机 16 口 ring/buffer/PFC
  检查通过，未降级固件。
- 生产栈于 23:38 UTC 重新 UP；`boot-prod.sh` 预检与 post-boot 自检通过，
  `last-boot.json` 为 `boot_rc=0/selfcheck_rc=0`。
- 回滚后修复 `roce-ring-check.timer` 的误报：`heal-if-down` 原先在栈运行时
  无条件 exit 1，导致四机 `systemctl` 每 5 分钟变 `degraded`；现改为栈运行
  时只读 check、零漂移 exit 0，真实漂移仍 exit 1。四机已 `reset-failed`
  并验证 `Result=success`、`is-system-running=running`。

### 回滚后性能复测（2026-10-22 23:44–23:57 UTC）

PR 每档 3 次独立采样，DE mt400 五次（取中位），同口径对照 A6-ANCHOR-7：

| 输入 tokens | 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 6.17 中位 tok/s | 5555.6 | 6161.6 | 6452.8 | 6468.1 | 6194.6 | 5559.6 | 4376.9 |
| A6 锚点 | 5522.5 | 6040.2 | 6271.3 | 6289.3 | 6048.1 | 5427.9 | 4290.0 |
| 差值 | +0.6% | +2.0% | +2.9% | +2.8% | +2.4% | +2.4% | +2.0% |
| 对比 7.0 中位 | +15.1% | +9.6% | +9.1% | +11.6% | +9.0% | +14.1% | +12.5% |

- DE c1 **91.64**（锚 88.64，+3.4%；7.0 为 86.38）；DE c8 **249.10**
  （锚 242.83，+2.6%；7.0 为 240.13）。
- 64k warm gate 5 次 `5543.7 / 6494.3 / 6303.2 / 6468.4 / 6458.5`，丢弃
  首次冷读后中位 **6463 tok/s**；版本锁完成后的最终复检中位 **6415**
  （阈值 5600；7.0 为 5797，约 +11%）。
- 质量：GSM8K 20 题 20/20（content/marker 均 1.0，err=0）；qeval 75 题
  71/75（94.7%，1 题触顶；外部参考 72/75）。完整 500 题 GSM8K 未在本次
  回滚窗口重跑，代码/采样路径与回滚前一致，正式验收前低峰补跑。

## 2026-10-22 7.0 调优窗口（历史，已被上述回滚取代）

1. **NIC buffer 回到 523296**：固件 28.50.1002 把 lossless shared buffer 默认
   改为 458496；按用户要求恢复更新前余量，四机 16 口已读回
   `19872,523296,...`。同窗口复测 PR/DE，buffer 本身不是本次 prefill 缺口的
   主因（458496 与 523296 同带）。
2. **解除 GPU 软件锁频**：四机 `gb10-clock-cap.service` 原为
   `nvidia-smi -lgc 0,2400`，已 `disable --now` 并执行 `-rgc`。当前 EC 自动
   把负载时钟稳定在 ~2470–2530 MHz，硬件上限 3003 MHz；`-lgc 3003` 诊断也
   只能到 ~2528 MHz，说明上限来自 EC/功耗，不是残留软件锁。
3. **自检新增**：`gpu_clock`（cap unit 必须 disabled/inactive，max SM ≥3000）、
   `fan_policy`（`nvfancontrol` 必须未加载 = EC auto）、NIC buffer 523296 校验。
4. **recipe 复验**：64k PR 同款文本 recipe/tokenizer 逐 ID 相等
   （65540=65540），排除分词路径导致 prefill 变化的可能。

## 内核/驱动版本锁（2026-10-23）

生产固定为 `6.17.0-1031-nvidia` + NVIDIA `580.173.02`，四机使用同一套锁：

1. **包 hold（22 + 7）**：7 个 `6.17.0-1031` 内核包、12 个 580.173.02 用户态包、
   `nvidia-kernel-common-580` / `nvidia-kernel-source-580-open`（保持当前
   580.178.04 包版本）和 `nvidia-firmware-580-580.173.02` 做精确版本锁；另有
   4 个 7.0 内核 meta/module、`libxnvctrl0`、`nvidia-modprobe`、`nvidia-settings`
   作为 guard hold，固定 GRUB 菜单和现有工具版本。
2. **APT pin**：`/etc/apt/preferences.d/99-prod-version-lock`，22 个受锁包
   `Pin-Priority: 1001`，高于 Ubuntu/NVIDIA 仓库；candidate 必须等于已安装版本。
   guard 包只校验 hold（`nvidia-modprobe` 在 01/02 与 03/04 版本不同，不做统一 pin）。
3. **自动升级屏蔽**：`/etc/apt/apt.conf.d/52-prod-version-lock` 关闭
   unattended-upgrade，并把 29 个包全部列入黑名单；`apt-daily*.timer` 与
   `nvidia-spark-ota-check.timer` 为 masked；DGX 的
   `nvidia-spark-run-apt-upgrade-once.service`（会执行 `apt full-upgrade` 并
   重启）已 masked。
4. **周期校验**：`/usr/local/sbin/version-lock.sh check` 校验运行内核、用户态/
   模块版本、GRUB `1>2`、GRUB 菜单项、22 个精确锁包、7 个 guard hold、candidate
   和自动升级单元；`prod-version-lock.timer` 每 30 分钟运行。`boot-prod.sh`
   起栈前、自检的 `version_lock` 项也会调用它，任何漂移都会失败关闭。
5. **验证**：四机 `version-lock.sh check` 为 `holds=29 lock=22 guard=7`；
   `apt-get -s full-upgrade` 不再计划任何 `linux-*`、`nvidia-*`、`libnvidia-*`
   或 `libxnvctrl*` 包的 `Inst/Remv`；最终 fast **44/44**（00:56:48）、post-boot
   **46/46**（00:55:42，warm median 6415）PASS。

变更版本时只能走维护窗：先改 `prod-profile.env`；每台机调整/删除
`99-prod-version-lock` 并解除目标包（含需要移动 GRUB 条目的 guard 包）的 hold；
安装目标版本；重新执行 `sudo /usr/local/sbin/version-lock.sh apply`；最后
`boot-prod.sh` 和 `--post-boot`。禁止只改 pin、只 unhold 一半，或跳过 post-boot。

## 审计结论（2026-10-22）

### 网卡
- 四机 16 口 link 100G、FEC RS、PFC prio3/5、trust dscp、ring 4096/tx1024、
  channels 20、rx-usecs 8/rx-frames 128、CQE RX on；PCIe Gen5 x4、MPS/MRRS 512。
- PR 512k 负载期间 `rx_discards_phy/rx_pause/tx_pause/rx_out_of_buffer/CNP` 全 0。
- `ib_write_lat` 2 B 典型 1.74 µs；`ib_write_bw` 单口 97.93 Gb/s（switched
  单口线速）。
- 固件 28.50.1002 的 PCC/LRO 修复不包含 RoCE 性能新增项；`prof_sel=2` 与
  更新前记录一致，未改。

### GPU / EC
- 负载采样：SM 中位约 2.45–2.46 GHz（最高 2.483 GHz），温度中位
  80–82°C（三组最高 86°C），功耗中位 66–67 W（峰值约 71 W），95–96% util；
  `SW Power Cap`、`HW Thermal Slowdown` 均 Not Active。
- EC 自动风扇正常；但 `nvfancontrol` 的 DKMS 模块在 Secure Boot 下加载失败：
  `insmod: Key was rejected by service`。模块此前为 7.0.0 编译，签名密钥
  `dgxspark01 Secure Boot Module Signature key` 不在 MOK 列表，
  `/var/lib/shim-signed/mok/MOK.der` 未注册。因此 `nvfancontrol max/auto/rpm`
  目前不可用，EC 默认曲线是唯一可用控温方式。要手动控风扇需在控制台完成
  MOK 注册（本次未改安全启动）。

### CPU 拓扑与绑核
- 20 核：`0-4,10-14` 为 2.808 GHz 能效核；`5-9,15-19` 为 3.9 GHz 性能核。
- `isolcpus=8-9 rcu_nocbs=8-9` 隔离的是两个性能核；但 `ncclpin` 已于
  2026-10-15 退役，当前 `LD_PRELOAD` 为空、`NCCL_IGNORE_CPU_AFFINITY=1`，
  引擎线程没有使用 8-9（只有 RCU 内核线程）。
- 64k prefill 采样：CPU5 ~48% usr + 50% sys、CPU19 ~80% usr，其余核 1–3%；
  8-9 100% idle。CPU 不是瓶颈，移除 isolcpus 预计收益很小。
- A/B：容器 cpuset 收到 10 个性能核后 64k 中位 5811，默认 5905（−1.6%）；
  “全部线程上性能核”反而争抢，已回退。当前保持默认 0-19 调度。
- 建议：不要把整个容器绑到性能核；若后续要再试，只针对 scheduler/NCCL
  单线程做定向 pin，并保留 8-9 给通信线程。

### 容器内可重编译/重调优面
- **不是旧二进制**：b12x CuTe 内核在每次启动时 JIT（Cutlass DSL 4.6.2、
  CUDA Python 13.4.1、`opt-level=3`）；`roce_proxy` 也是源码哈希缓存，
  当前 15:15 重新编译，GCC 13.3 + libibverbs 50.0，`-O2`。
- Torch 2.13.0+cu130，实际 NCCL 2.29.7（torch 内置），FlashInfer
  0.6.18+cu130 预编译 cubin，Triton 3.7.1；FlashInfer autotune 与 Triton
  缓存在 16:08–16:10 本靴全部重建，无旧驱动缓存。
- `sgl_kernel`/FlashInfer 预编译件与内核 7.0.0 无 ABI 关系，不需要为新内核
  重编译；`roce_proxy` 若要做 `-O3/-march=native` 属可选微优化，未证实收益。
- 唯一确认需要“重编译/重签名”的是 `nvfancontrol` DKMS 模块（见上），但它是
  风扇覆盖接口，不影响 EC auto 的默认控温。

### 性能读数（7.0 最终靴，历史）
- PR 七档 8k→512k（sparkdash repeated，单发）：`4825.7 / 5620.0 / 5913.3 /
  5797.1 / 5684.2 / 4873.9 / 3891.2` tok/s；A6-ANCHOR-7 为
  `5522.5 / 6040.2 / 6271.3 / 6289.3 / 6048.1 / 5427.9 / 4290.0`。
  当时低约 6–13%，且 buffer/锁频/empty_cache/核心绑定/recipe 五个单变量
  均不能解释。
- DE c1/c8：86.38 / 240.13 tok/s（锚 88.64 / 242.83，约 −1.5% / −1.1%）。
- 64k warm 门：5 次采集中位 5797（阈值 5600，冷读 5097 不计）。
- 质量门：GSM8K smoke 20/20=1.0（err=0）；needle 8k/32/64/128k 4/4 PASS。

## 回退边界

- 当前生产只允许 6.17.0-1031 + NVIDIA 580.173.02；`7.0.0-1019-nvidia` 仍在
  GRUB 中，但不在允许表内。切回 7.0 必须同时恢复 580.178.04 用户态、改
  `PROD_KERNEL_ALLOW`、调整/删除版本锁 pin 并解除 hold，走维护窗和 post-boot
  验收，不能只改内核入口。
- 6.17 的 NVIDIA 用户态包已 hold，防止 apt 自动升回 580.178.04 再次造成
  `NVRM: API mismatch`。
- NIC 固件不允许自动降级（脚本只校验版本）；28.50.1002 已在 6.17 上验证。
- buffer 523296、GPU 默认频率/EC auto 是当前基线；改回 458496 或重新启用
  `gb10-clock-cap.service` 都必须在维护窗内由人确认。
- 四机统一：不得只回退其中一台；01 最后回退，回滚顺序已记录在回滚报告中。
