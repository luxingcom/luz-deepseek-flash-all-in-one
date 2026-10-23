# 生产环境 7.0.0 升级后调优与运维交接工作报告

> **历史报告。** 2026-10-22 23:35 UTC 已按用户指令把四机回滚到
> `6.17.0-1031-nvidia` + NVIDIA `580.173.02`，当前生产基线、回滚步骤与
> 6.17 复测结果见 `../2026-10-22-6.17-rollback/ROLLBACK-REPORT-2026-10-22.md`。
> 本文保留 7.0 窗口的调优过程与证据，不再代表当前运行状态。

- 报告日期：2026-10-22
- 适用范围：`dgxspark01`–`dgxspark04`，TP4，`r3prod`，`deepseek-v4.1-flash`
- 生产镜像：`192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c`
- 报告状态：历史定稿；7.0 窗口结束，已回滚
- 结论一句话：**7.0 窗口内完成了 NIC/GPU/绑核/自检固化，prefill 仍低约 6–13%；该结论促成随后按用户指令回滚到 6.17。**

---

## 1. 背景与任务目标

2026-10-22 12:24 停止旧栈，12:33 新栈启动完成。生产流量走 recipe 分词路径，四机 `r3prod-head` / `r3prod-worker` 均在位，引擎 `/health` 返回 200。启动日志：

```
~/r3-boot-prod-20261022-122415.log
BOOT_RC=0
```

随后发现 prefill 性能相对 A6 锚点存在回归。用户明确要求：

1. **不允许回滚**；性能变化与本次更新没有关系，应按新内核、新驱动、新固件调整配置。
2. 核查网卡底层配置，适配固件 28.50.1002 的行为偏差。
3. 网卡 lossless buffer 恢复为 **buf1=523296**；RX ring **4096** 已经测试可行，保留。
4. GPU 频率恢复默认，不设频率上限，观察 EC 能否自动调速控温。
5. 梳理高性能核 / 能效核的任务分配。
6. 梳理新内核/新驱动下哪些容器组件需要重编译，哪些可以利用新版本特性。
7. 落实持久化、自愈、自检措施，避免“丢参数启动”。

本报告覆盖上述全部工作、结果、证据、遗留风险和运维交接安排。

---

## 2. 最终生产基线

| 项目 | 当前值 | 验证方式 |
|---|---|---|
| 内核 | `7.0.0-1019-nvidia`（四机） | `boot-prod.sh` 内核允许表 + 自检 |
| 旧内核 | `6.17.0-1031` 仅保留为人工应急回退，不自动选择 | GRUB 保留，不在允许表 |
| NIC 固件 | `28.50.1002`（四机 16 口） | 逐口 `ethtool -i` |
| RX ring | `4096`；TX `1024` | `ethtool -g`，四机 16 口 |
| Lossless buffer | `19872,523296,0,0,0,0,0,0`，max `2041344` | `mlnx_qos -i`，四机 16 口 |
| PFC / trust | `0,0,0,1,0,1,0,0` / `dscp` | `mlnx_qos -i` |
| GPU 频率 | 默认，无 `-lgc/-lmc/-ac` 上限；硬件 max SM `3003 MHz` | `gb10-clock-cap.service` disabled/inactive |
| GPU 温控 | EC 自动；`nvfancontrol` 模块未加载 | 自检 `fan_policy` |
| 镜像 | `0.3.2-r032c`，digest `sha256:47f6d91a…e2ffc4` | `boot-prod.sh` digest 校验 |
| adapter | 97 件，指纹 `c41b1a45`，四机一致 | 整树 md5 指纹 |
| recipe | 0.2.0；`serving_chat.py` `3151a2ed…`，`dsv41_recipe.py` `da98467d…` | 容器内 md5 + 功能探针 |
| env | 56 键，md5 `0729e18d6a93c1c05a82e1a5d528c488` | 四机容器 env 逐键比对 |
| overlay | 28 件全部挂载 | `docker inspect` + manifest |
| API | `127.0.0.1:8899`，模型 id `deepseek-v4.1-flash` | `/health`、`/server_info`、`/v1/models` |
| 自检 | post-boot **38/38 PASS**；fast **36/36 PASS** | `selfcheck-prod.sh` |

服务端关键参数：`max_total_num_tokens=9600000`、`context_length=600000`、`max_running_requests=16`。

---

## 3. 本轮变更清单

| 项目 | 变更前 | 当前 | 范围 | 结果 |
|---|---|---|---|---|
| NIC lossless buffer | 固件默认 `458496` | `523296` | 四机 16 口 | 已读回；PR 无持续增益；DE 维持锚点附近，按用户决定保留余量 |
| RX ring | 4096（已测试值） | 4096 | 四机 16 口 | 保留，不随固件默认回落到 1024 |
| GPU 软件锁频 | `gb10-clock-cap.service` 执行 `nvidia-smi -lgc 0,2400` | unit disabled/inactive，已 `-rgc`，无频率上限 | 四机 | EC 自动调节，负载约 2.45 GHz |
| 手动风扇覆盖 | `nvfancontrol` 单元 disabled、模块未加载 | 保持未加载，EC auto | 四机 | 模块因 Secure Boot/MOK 无法加载；EC auto 正常 |
| prefill empty-cache 阈值 | `DSV41_PREFILL_EMPTY_CACHE_TOKENS=8192` | 测试 `131072` 后回退到 `8192` | 四机容器 env | 无稳定收益，回退保证 64k 内存安全 |
| CPU 绑核 | 默认 `0-19` | 测试全性能核后回退到默认 | 容器 cpuset/线程亲和 | 全性能核 64k 中位 5811，默认 5905，负收益 |
| 自检项 | 原有健康/参数/overlay/ring/内核 | 新增 `gpu_clock`、`fan_policy`、NIC buffer 校验 | 生产自检 | 四机全 PASS |
| 报告与证据 | 无 | 本目录 | 仓库 | 随附证据副本 |

本轮新增两个本地提交（未推送）：

```
6c13a0d fix(prod): pin 7.0.0 NIC profile and EC-default GPU clocks
bd732d4 fix(prod): pass pinned NIC targets into selfcheck and preflight
```

---

## 4. 网卡底层核查与适配

### 4.1 核查结果

四机 16 个 RoCE 口逐项读回，结果一致：

- 链路 100G，FEC RS；PCIe Gen5 x4，MPS/MRRS 512。
- PFC 仅 prio3/prio5 开启；`trust dscp`；DSCP 映射未改。
- RX ring 4096、TX ring 1024；channels 20。
- RX 中断合并 `rx-usecs=8`、`rx-frames=128`；CQE RX 开启。
- PR 512k 压测期间：`rx_discards_phy`、`rx_pause`、`tx_pause`、`rx_out_of_buffer`、CNP 全部为 0。
- `ib_write_lat` 2 B 典型 **1.74 µs**；`ib_write_bw` 单口 **11674.72 MiB/s ≈ 97.93 Gb/s**，达到单口线速。
- `prof_sel=2` 与更新前记录一致，未改。

固件 28.50.1002 的变更属于 PCC 时延/竞争修复、LRO 死锁修复等缺陷修复，**不包含 RoCE 性能新增项**；不能依靠固件升级本身恢复 prefill 性能。

### 4.2 buffer 适配与 A/B

固件升级把 lossless shared buffer 的默认值从 `523296 B` 改为 `458496 B`。按用户要求恢复更新前余量，并固定到启动单元和自检中。

同窗口单变量结果（PR，tok/s）：

| 配置 | 64k | 512k | 同靴 warm 中位 |
|---|---:|---:|---:|
| 解除 GPU 锁频，buffer 仍为固件默认 | 5916.1 | 3900.0 | — |
| buffer 恢复 523296 | 5743.7 | 3910.3 | 5760 |
| 131072 empty-cache 测试后回退 8192（最终靴） | 5797.1 | 3891.2 | 5797 |

单次 PR 波动约 ±5%，三组差异落在噪声范围内；**buffer 恢复没有带来可重复的 prefill 增益**。它仍按用户要求保留，原因是 PFC prio3/prio5 在交换网络下需要原有的突发吸收余量，而不是因为它能解释本次回归。

### 4.3 结论

NIC 配置、链路质量、PFC、固件版本均未发现会造成 prefill 回归的偏差；buffer 恢复是正确性/余量适配，不是性能修复。

---

## 5. GPU 频率与 EC 温控

### 5.1 锁频解除

四机原先由 `gb10-clock-cap.service` 执行：

```
nvidia-smi -lgc 0,2400
```

已执行并固化：

```
systemctl disable --now gb10-clock-cap.service
nvidia-smi -rgc
```

自检要求该 unit 必须 `disabled/inactive`，且 `clocks.max.sm >= 3000 MHz`。当前四机均为 disabled/inactive，max SM = 3003 MHz。

### 5.2 实测负载时钟与温度

本轮三组 PR 负载采样的结果（`gpu-pr7*.csv`）：

| 采样 | 负载时钟中位 | 负载时钟最高 | 温度中位/最高 | 负载功耗中位 | 利用率 |
|---|---:|---:|---:|---:|---:|
| 解除锁频后 | 2444 MHz | 2483 MHz | 82 / 86°C | 67 W | 96% |
| buffer 523296 | 2450 MHz | 2483 MHz | 81 / 84°C | 66 W | 96% |
| 最终靴 | 2457 MHz | 2483 MHz | 80 / 83°C | 67 W | 96% |

- `SW Power Cap`、`HW Thermal Slowdown` 均未触发。
- 硬件上限 3003 MHz；此前 `-lgc 3003` 诊断测试也只能到约 2528 MHz，说明当前约 2.45–2.48 GHz 的持续频率来自 EC/功耗策略，不是残留软件锁。
- EC 自动风扇工作正常，最终靴温度最高 83°C（前两组负载最高 84–86°C）。

### 5.3 手动风扇接口的已知限制

`nvfancontrol` 是 DKMS 模块，已为 7.0.0 编译并签名，签名密钥为 `dgxspark01 Secure Boot Module Signature key`；但 `/var/lib/shim-signed/mok/MOK.der` **未注册到 MOK**，Secure Boot 下加载失败：

```
insmod: ERROR: could not insert module ...: Key was rejected by service
```

因此 `nvfancontrol max/auto/rpm N` 目前不可用，EC 默认曲线是唯一有效控温方式。本次未注册 MOK、未关闭 Secure Boot，也不建议为了风扇覆盖而降低启动安全级别。若要启用手动风扇，应在维护窗内由安全/平台负责人在物理控制台完成 MOK 注册并重启验证；这是可选的运维能力，不是生产运行的必要条件。

---

## 6. CPU 拓扑与核心分配

### 6.1 拓扑

20 个逻辑核，分为两类：

| 类别 | CPU | 频率 |
|---|---|---|
| 能效核 | `0-4, 10-14` | 2.808 GHz |
| 性能核 | `5-9, 15-19` | 3.9 GHz |

内核参数：`isolcpus=8-9 rcu_nocbs=8-9`。8-9 是性能核，但 `ncclpin.so` 已于 2026-10-15 退役，`LD_PRELOAD` 为空，`NCCL_IGNORE_CPU_AFFINITY=1`，引擎线程并没有使用 8-9；这两个核上主要是 RCU/内核线程。

### 6.2 实测

64k prefill 采样：

- CPU5：约 48% usr + 50% sys。
- CPU19：约 80% usr。
- 其余核：1–3%。
- CPU8-9：100% idle。

说明 CPU 不是当前瓶颈，瓶颈在 GPU 计算路径。

### 6.3 全性能核 A/B

把容器 cpuset 收到 10 个性能核后：

- 64k 中位：**5811 tok/s**；
- 默认全核：**5905 tok/s**；
- 全性能核版本低约 **1.6%**，且出现线程争抢，已回退。
- 最终靴重新创建容器后，cpuset 恢复默认 `0-19`。

**建议**：不要做“整个容器绑性能核”的粗粒度绑核。若后续还要尝试，只针对 scheduler/NCCL 单线程做定向 pin，并在同一靴上用 warm gate 复测；当前保持默认调度，8-9 留给通信/中断类线程。

---

## 7. recipe 分词路径复核

生产 recipe 版本 0.2.0。复核结论：**recipe 分词不是本次性能变化的原因**。

- 容器内 `serving_chat.py` md5：`3151a2edf2c21e4d3492dff5bbc6ec10`。
- 容器内 `dsv41_recipe.py` md5：`da98467d3fd7d5019ea025b3d5273a20`。
- recipe 功能探针：`recipe_ids=7, tokenizer_ids=7, equal=true`。
- 64k PR 同款 serving 文本：recipe 与 tokenizer 逐 ID 相等，`65540=65540`。
- recipe 适配只在“recipe 渲染后的 prompt 与服务 prompt 字节完全一致”时生效，当前生产请求满足该条件。

因此 prefill 差异不能归因于分词路径或 recipe 适配。

---

## 8. 容器内重编译/版本梳理

| 组件 | 版本/构建方式 | 本轮结论 |
|---|---|---|
| torch | 2.13.0+cu130 | 无需重编译 |
| NCCL | 2.29.7（torch 内置） | 无独立旧二进制；无需替换 |
| b12x CuTe kernels | 启动时 JIT；Cutlass DSL 4.6.2、CUDA Python 13.4.1、`opt-level=3` | 每靴按当前工具链重建，已是新环境产物 |
| roce_proxy | 源码哈希缓存 JIT；GCC 13.3、libibverbs 50.0、`-O2 -std=gnu11 -shared -fPIC` | 缓存已重建，非旧驱动残留；`-O3/-march=native` 属未证实收益的可选微优化 |
| FlashInfer | 0.6.18+cu130，预编译 cubin | 与内核 ABI 无关；无需重编译 |
| Triton | 3.7.1 | autotune/cache 在最终靴 16:08–16:10 重建 |
| sgl_kernel / FlashInfer 预编译件 | 预编译 | 不依赖 7.0.0 内核 ABI，无需整镜像重编 |
| nvfancontrol | DKMS 模块，已签名 | 唯一需要“重编译/重签名”的项目；受 MOK 未注册阻塞 |

**结论**：不需要为新内核重建整镜像，也不存在旧的 6.17 驱动编译产物拖慢 7.0.0 的问题。新版本能利用的是当前工具链下的 fresh JIT、EC 自动时钟/温控和固件缺陷修复；NIC 固件没有可直接开启的 RoCE 性能特性。

---

## 9. 持久化、自愈与“不丢参数启动”

### 9.1 设计原则

1. **单一基线来源**：`prod-profile.env` 是唯一参数源，启动和自检都从它读取。
2. **fail-closed 启动**：任何关键项不一致，拒绝启动，不用默认值兜底。
3. **启动前重放主机态**：NIC ring/buffer/trust/PFC 在 docker 之前由 systemd 单元重放。
4. **只读自检**：周期性检查只报红，不自动重启生产栈，避免误动作。
5. **功能探针**：除静态 md5 外，还在容器内验证 recipe 分词结果，防止“文件对但运行路径错”。

### 9.2 启动入口与前置校验

唯一入口：

```bash
bash ~/migrate-assets/prod/boot-prod.sh
```

启动前逐项校验（任一失败即拒绝）：

- env 文件 md5 与 56 个键；
- overlay manifest 与 28 件挂载；
- recipe manifest 与容器内 md5；
- 四机 adapter 整树指纹（97 件，`c41b1a45`）；
- 启动脚本 md5；
- 镜像 digest；
- 内核允许表（只接受 `7.0.0-1019-nvidia`）；
- NIC 固件/ring/buffer/PFC 主机 profile；
- 无残留 `r3prod`/`r3boot` 容器；
- API 端口 8899 空闲。

通过后走标准产线链：

```
tools/boot-with-slotlock.sh → ~/migrate-assets/bin/r3-boot-arm.sh
```

启动后自动执行 `selfcheck-prod.sh --post-boot`，写 `~/migrate-assets/prod/last-boot.json`；自检失败时启动脚本以 rc=4 退出，避免“起来了但参数不对”被当成成功。

### 9.3 周期自检与自愈单元

| 单元/脚本 | 频率/时机 | 行为 |
|---|---|---|
| `roce-ring-boot.service` | 每次启动，docker 之前 | 重放 ring/buffer/trust/PFC；四机 enabled |
| `roce-ring-check.timer` | 每 5 分钟 | 只读检查 NIC profile；四机 active |
| `prod-selfcheck.timer` | 每 15 分钟 | head 上跑 `selfcheck --fast`；只报红，不重启栈 |
| `selfcheck --post-boot` | 每次生产启动后 | 全量静态检查 + recipe 探针 + 5×64k warm gate |
| `selfcheck --perf` | 人工/维护窗 | 只跑 warm gate，用于性能复验 |

自检结果写入：

```
~/r3-prod-logs/selfcheck-<timestamp>.log
~/r3-prod-logs/selfcheck-<timestamp>.tsv
~/r3-prod-logs/selfcheck-latest.json
```

### 9.4 已发现的运维陷阱

1. **oneshot 单元不会因 `start` 重跑**：`roce-ring-boot.service` 是 `RemainAfterExit=yes`。如果栈已停、手动改了 buffer，再执行 `systemctl start roce-ring-boot.service` 可能是 no-op；应使用 `systemctl restart` 或显式 `LOSSLESS_BUFFER=... /usr/local/sbin/roce-ring-apply.sh apply`。本次已用显式 apply + restart 处理。
2. **自检必须以 timer 配置的运维账号运行**：timer 配置为 `User=<operator>`。用 root 直接跑会因为 root 没有到 worker 的 SSH 授权而出现大面积假失败；如必须用 sudo，只用于单条本地特权读命令，不要让整个自检以 root 身份跨机执行。
3. **NIC apply 不能在栈运行时执行**：`heal-if-down` 会拒绝；`apply` 只应在引擎停止时使用。
4. **profile 改动不等于运行态生效**：修改 `prod-profile.env` 后必须走维护窗重启，不能只改文件就认为生产已变更。

### 9.5 变更控制

- 任何基线值变更：先改 `prod-profile.env`，review diff，维护窗启动，跑 `--post-boot`，记录 `last-boot.json` 和自检报告。
- 不允许绕过 `boot-prod.sh` 直接调用底层启动脚本。
- 不允许在未确认的情况下改 netplan、02 看门狗、内核默认启动项或 NIC 固件版本。
- `roce-ring-apply.sh check` 与自检是只读的，可用于日常巡检。

---

## 10. 性能与质量结果

### 10.1 PR 七档（最终靴）

| 输入 tokens | 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 本次 tok/s | 4825.7 | 5620.0 | 5913.3 | 5797.1 | 5684.2 | 4873.9 | 3891.2 |
| A6-ANCHOR-7 | 5522.5 | 6040.2 | 6271.3 | 6289.3 | 6048.1 | 5427.9 | 4290.0 |
| 差距 | −12.6% | −7.0% | −5.7% | −7.8% | −6.0% | −10.2% | −9.3% |

### 10.2 DE

| 并发 | 本次中位 | 锚点 | 差距 |
|---|---:|---:|---:|
| c1 | 86.38 tok/s | 88.64 | −2.6% |
| c8 | 240.13 tok/s | 242.83 | −1.1% |

### 10.3 热态门槛

最终靴 5 次 64k PR：

```
5097 / 5952 / 5807 / 5714 / 5787 tok/s
```

第一次为冷读，按规则丢弃；后四次中位 **5797 tok/s**，高于 5600 阈值。该值也是当前日常验收的稳定指标；单次 PR 数字波动较大，不宜单独作为结论。

### 10.4 质量门

- GSM8K 冒烟：20/20，content accuracy = 1.0，marker accuracy = 1.0，err=0；temperature 0.6、8-shot、concurrency 1、max_tokens 1024。
- Needle：8k/32k/64k/128k 四档全部 PASS。
- **限制**：完整 500 题 GSM8K 本轮未重跑；本次没有改 logits/采样路径，但正式验收前应在低峰补跑一次全量。

### 10.5 残余差距判断

- 已单变量排除：NIC buffer、RX ring、GPU 软件锁频、empty-cache 阈值、CPU 粗粒度绑核、recipe 分词。
- 残余 PR 差距约 6–13%，DE 仅约 1–2.5%，说明 decode 路径基本正常，差距主要集中在长 prompt prefill。
- 现有证据不能归因于任何一项可改配置；最可能落在“7.0.0 内核 + 新驱动/固件下的 GPU 持续频率/驱动路径”。
- **后续：** 2026-10-22 23:35 UTC 用户明确要求回滚到 6.17；回滚后同口径复测恢复到 A6 锚点以上，见回滚报告。本节的“保持新版本”仅是 7.0 窗口内的历史结论。

---

## 11. 过程中的问题与纠正

| 问题 | 影响 | 纠正 |
|---|---|---|
| 最初 PR 基准用了 1k–64k 档，而不是 A6 的 8k–512k | 会得出错误对比结论 | 改为 8k/16k/32k/64k/128k/256k/512k 重跑 |
| `taskset -a` 只覆盖主进程，未覆盖子进程 | CPU 绑核实验数据不完整 | 改用容器 cpuset + 对全部 PID 设亲和，再复测 |
| `docker update --cpuset-cpus ''` 未能完全恢复线程亲和 | 绑核残留 | 显式设置 `0-7,10-19` 并对全部 PID `taskset`；最终靴重建容器恢复默认 |
| `nvfancontrol` 模块加载被 Secure Boot 拒绝 | 手动风扇不可用 | 保留 EC auto；MOK 注册列为可选维护项，未降低安全启动 |
| `roce-ring-boot.service` oneshot 已 active，`start` 不重放 | buffer 写入看似成功实际未执行 | 使用显式 `apply` + `systemctl restart` |
| 自检以 root 运行导致 worker SSH 假失败 | 21 项假红 | 确认 timer 以运维账号运行；最终 fast 36/36 PASS |
| GSM8K 脚本引用的 `state` 目录凭据文件不存在 | 未使用指定凭据 | 仍以默认凭据完成 20 题冒烟；未泄露任何密钥，正式跑前补齐正确凭据 |
| 单次 PR 与 warm gate 混用 | 容易把噪声当回归 | 验收统一以 5×64k 热态中位为准，PR 单次仅作趋势 |

---

## 12. 统一运维安排（建议执行）

### 12.1 角色

| 角色 | 职责 |
|---|---|
| 平台负责人 | 生产变更审批、维护窗、基线签字 |
| 当班运维 | 每日健康/自检/温度巡检，异常升级 |
| 网络安全 | Secure Boot/MOK、固件与内核安全策略 |
| 性能/模型 | warm gate、全量质量门、厂商性能问题跟踪 |

### 12.2 巡检节奏

| 频率 | 动作 | 通过标准 |
|---|---|---|
| 每 5 分钟 | `roce-ring-check.timer` 自动 | NIC profile 四机一致 |
| 每 15 分钟 | `prod-selfcheck.timer` 自动 | `selfcheck-latest.json` 无 FAIL |
| 每日 | 看 `/health`、四机容器、`systemctl --failed`、GPU 温度/时钟、自检最新 JSON | 容器在线，温度 < 90°C，无 FAIL |
| 每周低峰 | `selfcheck --perf` | 64k warm 中位 ≥ 5600 tok/s |
| 每次启动后 | `--post-boot` | 38/38 PASS |
| 每月/维护窗 | 复核内核、固件、镜像、adapter/overlay 基线 | 有变更单和回退边界 |

### 12.3 日常命令

```bash
# 只读快检
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast

# 启动后全检（含 recipe 探针和 5×64k warm）
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot

# 只看 warm 门槛
bash ~/migrate-assets/prod/selfcheck-prod.sh --perf

# 查看最近一次启动记录
cat ~/migrate-assets/prod/last-boot.json

# NIC 只读核查（不写配置）
sudo /usr/local/sbin/roce-ring-apply.sh check

# 正常停栈（生产前缀 + 三查）
CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash ~/migrate-assets/bin/r3-stop.sh
```

### 12.4 异常处置矩阵

| 现象 | 首先确认 | 处置 |
|---|---|---|
| 自检 NIC FAIL | 是否栈在运行、是否刚重启 | 栈停：`systemctl restart roce-ring-boot.service`；栈在：记录并排维护窗，禁止热写 |
| env/overlay/adapter FAIL | 文件 md5、manifest、指纹 | 不启动；按 manifest 修复/同步，复跑 `--post-boot` |
| GPU 温度持续 > 90°C | `nvidia-smi` 的降频标志、EC 风扇 | 降低负载/停机检查；不要尝试 `nvfancontrol`（MOK 未注册） |
| warm 低于 5600 | 是否冷读、是否并发干扰、NIC 计数、GPU 时钟 | 先按 5 次重测；再收集 `nvidia-smi`、NIC 计数和 `selfcheck` 日志，禁止同时改多个变量 |
| selfcheck timer 红 | timer 用户、SSH、栈状态 | 以 timer 配置的运维账号手工跑 `--fast`；root 跨机运行会假失败 |
| 需要改基线 | 变更单、维护窗、回退边界 | 改 profile → 重启 → `--post-boot` → 记录，禁止绕过 boot-prod |

### 12.5 禁止项

- 禁止自动回滚内核、自动降级 NIC 固件。
- 禁止在栈运行时写 NIC ring/buffer/PFC。
- 禁止绕过 `boot-prod.sh` 直接起栈。
- 禁止未审批修改 netplan、`oom-gate-monitor`、`r3-watchdog-worker`。
- 禁止把 sudo 密码、模型凭据 写入日志、报告、仓库或命令行参数。
- 禁止为了手动风扇关闭 Secure Boot；MOK 只能在控制台按安全流程注册。

---

## 13. 遗留风险与后续建议

| 项目 | 等级 | 现状 | 建议 |
|---|---|---|---|
| prefill 残余差距 6–13% | 中 | 无配置项可解释 | 由厂商确认 7.0.0 下 GPU 持续时钟/驱动路径；保持新版本，不回滚 |
| 手动风扇不可用 | 低 | EC auto 正常，最高 83–86°C | 需要时在维护窗完成 MOK 注册；否则维持 EC auto |
| 完整 500 题 GSM8K 未跑 | 中 | 仅 20 题冒烟 | 低峰补跑，作为正式质量签字依据 |
| 自检只报红不告警 | 中 | 结果落 JSON/日志 | 接入现有监控/告警平台，FAIL 时通知当班 |
| 报告/证据散落在 `/tmp` 与 `~/r3-prod-logs` | 低 | 本目录已复制副本 | 原始日志按保留策略归档；`/tmp` 不作为长期记录 |

---

## 14. 记录与证据索引

### 14.1 仓库文档与脚本

```
deploy/prod/README.md                         生产基线与操作入口
deploy/prod/prod-profile.env                  唯一基线来源
deploy/prod/boot-prod.sh                      fail-closed 启动入口
deploy/prod/selfcheck-prod.sh                 只读自检
deploy/prod/roce-ring-apply.sh                NIC profile check/apply/heal
deploy/prod/install-host-ring-pin.sh          NIC 主机侧安装
deploy/prod/install-prod-guard.sh             生产 guard 安装
deploy/prod/recipe_probe.py                   recipe 功能探针
deploy/prod/prod-selfcheck.service/.timer     15 分钟自检
deploy/prod/roce-ring-boot.service            启动时 NIC 重放
deploy/prod/roce-ring-check.service/.timer    5 分钟 NIC 只读检查
deploy/prod/overlay-md5.txt                   28 件 overlay 指纹
deploy/prod/recipe-md5.txt                    recipe 指纹
```

### 14.2 本报告证据副本

目录：`deploy/prod/reports/2026-10-22-7.0.0-tuning/evidence/`

| 文件 | 内容 |
|---|---|
| `pr7-final.json` | 最终靴 PR 8k–512k |
| `pr7-capoff.json` | 解除 GPU 锁频后 PR |
| `pr7-buf523296.json` | buffer 523296 后 PR |
| `de-final-c1.json` / `de-final-c8.json` | DE c1/c8 五次结果 |
| `gsm8k-final-summary.json` | 20 题冒烟汇总 |
| `needle-final.json` | 4 档 needle |
| `boot-prod-final-20261022.log` | 最终靴完整启动 + post-boot 自检 |
| `boot-prod-buf523296.log` | buffer 523296 靴 |
| `boot-prod-ec131072.log` | empty-cache 131072 测试靴 |
| `selfcheck-postboot-20261022-162719.{log,tsv}` | 最终靴 38 项自检 |
| `selfcheck-fast-20261022-163826.{log,tsv}` | 最终 fast 36 项自检 |
| `selfcheck-latest-fast.json` | 自检 JSON |
| `warm-20261022-162719-[1-5].json` | 5 次 64k warm 原始值 |
| `gpu-pr7*.csv` | GPU 时钟/温度/功耗采样 |
| `last-boot.json` | 最终启动 rc、env md5、boot 脚本 md5 |

### 14.3 运行态原始记录

```
~/r3-boot-prod-20261022-122415.log    首次生产启动
~/r3-prod-logs/boot-prod-20261022-161712.log  最终靴
~/r3-prod-logs/selfcheck-latest.json  最新自检
~/r3-prod-logs/selfcheck-latest.log   自检文本
~/migrate-assets/prod/last-boot.json  启动结果
```

### 14.4 代码记录

本地分支：`main`，当前 HEAD 为报告相关提交；运行基线提交：

```
6c13a0d fix(prod): pin 7.0.0 NIC profile and EC-default GPU clocks
bd732d4 fix(prod): pass pinned NIC targets into selfcheck and preflight
```

本轮未推送。`switch-fabric` 分支保持既有状态。

---

## 15. 验收结论

- 生产栈：四机 `r3prod` 容器在线，`/health` 200。
- 参数：内核 7.0.0、固件 28.50.1002、ring 4096、buffer 523296、56 env keys、28 overlay、97 文件 adapter、recipe md5 全部符合基线。
- 自检：post-boot **38/38 PASS**；最新 fast **36/36 PASS**。
- 性能：64k warm 中位 **5797 tok/s**（阈值 5600）；DE c1/c8 **86.38/240.13**。
- 质量：GSM8K 冒烟 20/20，needle 4/4。
- 未回滚；手动风扇受 MOK 限制，EC auto 正常；prefill 残余差距已记录为厂商侧待确认项。

**签字/交接建议**：平台负责人确认基线；当班运维接收日常巡检与异常矩阵；性能负责人在低峰补跑 500 题 GSM8K 并跟踪厂商结论。
