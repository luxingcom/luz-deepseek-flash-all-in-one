# 生产固化档（r3prod / 0.3.2-r032c）

本目录是生产栈的唯一入口与只读自检面。2026-10-22 内核/NIC 固件更新后，
生产不再回退到 6.17；以下值是在 7.0.0 内核上逐项核过、并由
`boot-prod.sh` fail-closed 校验的当前基线。

## 当前基线

| 项 | 值 |
|---|---|
| 内核 | `7.0.0-1019-nvidia`（四机；6.17.0-1031 仅保留为人工回退，不自动选） |
| NIC 固件 | `28.50.1002`（四机 16 口） |
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
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast       # 周期检查
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot  # 起靴后全检 + 64k warm
bash ~/migrate-assets/prod/selfcheck-prod.sh --perf       # 只跑 warm
```

- `prod-selfcheck.timer` 每 15 分钟跑 `--fast`；失败只报红，不重启栈。
- `roce-ring-check.timer` 每 5 分钟跑只读 NIC 检查；`roce-ring-boot.service`
  在 `docker.service` 之前重放 ring/buffer/trust/PFC。
- `boot-prod.sh` 在任何一项（env md5/56 键、adapter 指纹、镜像 digest、内核
  允许表、NIC profile、端口/容器净空）不符时直接拒绝启动，避免丢参数起栈。

## 2026-10-22 维护窗变更

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
- 负载 64k：SM ~2476 MHz、72°C、55 W、96% util；`SW Power Cap`、
  `HW Thermal Slowdown` 均 Not Active。512k 连续负载最高 ~86°C。
- EC 自动风扇正常；但 `nvfancontrol` 的 DKMS 模块在 Secure Boot 下加载失败：
  `insmod: Key was rejected by service`。模块已为 7.0.0 编译，签名密钥
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

### 性能读数（最终靴，2026-10-22 16:17 UTC 起）
- PR 七档 8k→512k（sparkdash repeated，单发）：`4825.7 / 5620.0 / 5913.3 /
  5797.1 / 5684.2 / 4873.9 / 3891.2` tok/s；A6-ANCHOR-7 为
  `5522.5 / 6040.2 / 6271.3 / 6289.3 / 6048.1 / 5427.9 / 4290.0`。
  当前仍低约 6–13%，且 buffer/锁频/empty_cache/核心绑定/recipe 五个单变量
  均不能解释；剩余差异与“旧锚在 6.17 内核、当前 7.0.0 + 新驱动/固件”的
  GPU 持续时钟/驱动路径一致，未做回退。
- DE c1/c8：86.38 / 240.13 tok/s（锚 88.64 / 242.83，约 −1.5% / −1.1%）。
- 64k warm 门：5 次采集中位 5797（阈值 5600，冷读 5097 不计）。
- 质量门（最终靴）：GSM8K smoke 20/20=1.0（err=0）；needle
  8k/32k/64k/128k 4/4 PASS。完整 500 题 GSM8K 未在本次窗口重跑（配置未改
  logits 路径）。

## 回退边界

- 内核不自动回退；6.17.0-1031 仍在 GRUB 中，仅供人工选择。
- NIC 固件不允许自动降级（脚本只校验版本）。
- 若需回退配置：buffer 改回 458496、GPU cap unit 重新 enable（需重新
  `-lgc 0,2400`）都会改变生产基线，必须在维护窗内由人确认，不能单改
  `prod-profile.env` 后直接起栈。
