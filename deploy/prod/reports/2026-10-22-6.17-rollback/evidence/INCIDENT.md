# 6.17 回滚事件记录（2026-10-22）

## 当前状态

**已恢复。** 四机均运行 `6.17.0-1031-nvidia`，NVIDIA 用户态与内核模块均为
`580.173.02`；GRUB 默认持久化为 `1>2`，`next_entry` 为空。生产栈于
2026-10-22 23:38 UTC 重新 UP，`boot-prod.sh` 预检与 post-boot 自检全绿，
`last-boot.json` 为 `boot_rc=0/selfcheck_rc=0`。NIC 固件保持 `28.50.1002`，
未降级。

| 主机 | 内核 | 驱动 | GRUB 默认 | 验证 |
|---|---|---|---|---|
| dgxspark02 | 6.17.0-1031 | 580.173.02 | `1>2` | NIC 4 口、GPU 容器、nvidia-smi |
| dgxspark03 | 6.17.0-1031 | 580.173.02 | `1>2` | NIC 4 口、GPU 容器、nvidia-smi |
| dgxspark04 | 6.17.0-1031 | 580.173.02 | `1>2` | NIC 4 口、GPU 容器、nvidia-smi |
| dgxspark01 | 6.17.0-1031 | 580.173.02 | `1>2` | NIC 4 口、GPU 容器、nvidia-smi |

回滚顺序按要求执行：02 → 03 → 04 → 01，01 最后。

## 事件时间线（UTC）

1. 停止 `r3prod` 栈，保存回滚前 profile、last-boot、自检、head/02 运行面快照
   到 `pre/`。
2. 首次对 02 使用一次性 `grub-reboot "1>1"`。**该条目实际是 7.0.0 recovery
   （`recovery nomodeset`），不是 6.17**。启动后停在 `pam_nologin`，SSH 端口
   在线但无法登录；无 BMC/远程电源，最终由现场断电重启恢复。
3. 重新核对 `/boot/grub/grub.cfg` 的 advanced 子菜单顺序，确认
   `1>0`=7.0 普通、`1>1`=7.0 recovery、`1>2`=6.17 普通、`1>3`=6.17 recovery。
   改用 `1>2`。
4. 02 进入 6.17 后出现 NVIDIA API mismatch：6.17 自带 `nvidia.ko`
   580.173.02，用户态仍是 580.178.04，`nvidia-smi`/persistenced/CDI 刷新失败。
   用精确版本降级并修复 dpkg EGL 文件冲突后恢复。
5. 02 验证通过后，03、04 按同样步骤回退并验证；最后回退 01。
6. 四机固化 GRUB 默认 `1>2`，把 NVIDIA 580.173.02 包 hold，更新
   `prod-profile.env` 的内核允许表并新增驱动允许表，然后启动生产栈。

## 根因

1. **GRUB 子菜单索引误判**：把 `1>1` 当成 6.17，实际进入 7.0 recovery；
   `nomodeset`/recovery 环境触发登录阻塞，不是 6.17 或 NIC 固件故障。
2. **NVIDIA 用户态/内核模块不匹配**：6.17 的模块是 580.173.02，7.0 安装的
   用户态是 580.178.04。只换内核不换用户态必现 `NVRM: API mismatch`。
3. 首台 02 的手工降级未带 `--force-overwrite`，与旧 `libnvidia-gl-580`
   的 EGL 文件冲突；脚本化后加入 `-o Dpkg::Options::=--force-overwrite`，
   03/04/01 均一次通过。

## 回滚后锁定项

- 内核允许表：`PROD_KERNEL_ALLOW="6.17.0-1031-nvidia"`。
- 驱动允许表：`PROD_NVIDIA_DRIVER_ALLOW="580.173.02"`；`boot-prod.sh` 和
  selfcheck 同时校验 `nvidia-smi` 用户态版本与 `modinfo nvidia` 模块版本，
  任一不符则拒绝启动。
- GRUB：四机 `/etc/default/grub` 为 `GRUB_DEFAULT="1>2"`，`update-grub` 已
  执行；6.17 普通模式菜单项已确认存在；`next_entry` 为空。
- NVIDIA 用户态包 hold：`nvidia-utils-580`、`nvidia-compute-utils-580`、
  `libnvidia-compute-580`、`libnvidia-cfg1-580`、`libnvidia-common-580`、
  `libnvidia-extra-580`、`libnvidia-gpucomp-580`、`libnvidia-decode-580`、
  `libnvidia-encode-580`、`libnvidia-fbc1-580`、`libnvidia-gl-580`、
  `nvidia-persistenced`，均为 580.173.02。
- `nvidia-kernel-common-580` 保持 580.178.04（不参与内核模块 ABI 匹配）。
- `nvidia-driver-580-open`、`xserver-xorg-video-nvidia-580` 已移除（无头机）。
- NIC：固件 28.50.1002、ring 4096、buffer 523296、PFC/trust 保持；6.17
  下四机 16 口检查通过。
- `roce-ring-check.timer` 误报已修复：原 `heal-if-down` 在栈运行时会无条件
  `exit 1`，导致四机每 5 分钟被标成 `degraded`。现已安装修正版，栈运行时
  只读 `check`，零漂移时 `Result=success`；四机 `is-system-running=running`，
  `systemctl --failed` 为空。

## 证据

- 回滚前快照：`pre/`
- 降级脚本：`rollback-nvidia-userspace.sh`
- 性能复测：`bench-20261022-234439/`、`bench-6.17.log`
- 生产启动与自检：`~/r3-prod-logs/boot-prod-20261022-233453.log`、
  `~/r3-prod-logs/selfcheck-20261022-234245.log`、
  `~/migrate-assets/prod/last-boot.json`

## 教训与防再发

1. 禁止用 recovery 条目做内核回滚；切换前必须打印并核对 `grub.cfg` 中
   `menuentry` 的完整路径，而不是只看子菜单编号。
2. 换内核必须同时核对 NVIDIA 用户态与 `nvidia.ko` 版本；两者不一致时
   fail-closed，不带病起栈。
3. 回滚必须逐台执行并逐台验证，01 最后；任何一台失败即停止后续。
4. 本机无 BMC，错误启动项只能现场断电恢复；远程改 GRUB 默认项必须保留
   一次性 `next_entry` 与可回退的默认项。
5. 自愈脚本的正常预期路径不能返回失败：周期 unit 的“拒绝写入”应降级为
   只读检查并返回 0，否则会把健康运行态持续标记为 failed/degraded，掩盖
   真正的漂移。
