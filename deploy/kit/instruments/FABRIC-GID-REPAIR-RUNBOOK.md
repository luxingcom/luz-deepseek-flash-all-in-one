# FABRIC GID 洞修复 Runbook（断电后 RoCE GID 表重建）

> 2026-09-21 四机断电事故定谳产物。同款病 2026-08-15 出现过一次（luz031 runbook
> §A.3 有 GID 预案记录）。**每次整机断电/硬重启后按本册走一遍 §1 审计，有洞修洞，
> 零洞再起栈。** start.sh 已内置同款预检（`fabric_gid_preflight`，5 秒定向拦截），
> s4_bench.sh 起跑前也会自审——本册是底层手册与兜底。

## §0 病与症

- **病根**：断电重启后网卡接口初始化乱序，rdma_cm 重建 GID 表时出现**索引洞**——
  典型形态：v2-IPv4 GID 落在 idx4 而 idx3 空（正常紧凑形态=idx0 空位/v1、idx1 v2
  link-local、idx2 v1-IPv4、idx3 v2-IPv4）。MTU 9000 与 isolcpus=8-9 **不受影响**
  （2026-09-21 实测十六口 MTU 全在）。
- **为什么致命**：全集群硬钉 `NCCL_IB_GID_INDEX=3`（.env.tp4 `NCCL_IB_GID_INDEX_FORCE=3`
  与 s4_bench.sh 同值）。NCCL 在洞口 `ibv_modify_qp → RTR` 必挂。
- **三个症候**（任一命中先跑 §1 审计）：
  1. s4_bench verify 日志出现 `wrap_ibv_modify_qp failed with 61 No data available
     ... curr state INIT, next state RTR, local GID index 3, local GID ::`；
  2. 生产起栈 worker `Exited (247)` / "remote process exited"，自愈单元
     `start.sh-rc=1` 空转撞 start-limit（每轮白烧 2-3 分钟容器引导）；
  3. nccl-tests 单独跑也挂（纯 fabric 层，与引擎无关）。

## §1 四机审计（只读，30 秒）

```bash
# 注：占位符 <node0N>/<fabric-ip> 为 20261030 脱敏，实际执行时替换为真实主机名/IP。
for h in <node01> <node02> <node03> <node04>; do
  echo "── $h:"
  ssh $h 'show_gids | grep -v fe80; echo; \
    for c in rocep1s0f0 rocep1s0f1 roceP2p1s0f0 roceP2p1s0f1; do
      t=$(cat /sys/class/infiniband/$c/ports/1/gid_attrs/types/3 2>/dev/null)
      [ "$t" = "RoCE v2" ] || echo "HOLE: $c idx3=[$t]"
    done'
done
```

判读：每台 4 口，每口 idx2=v1-IPv4、**idx3=v2-IPv4（必须有）**。
零洞则 fabric 无此病，去查别处。

## §2 修复：洞口 IP 环回（逼 rdma_cm 重建紧凑表）

对**每个洞口**：先从 GID 表（或 `ip -o addr`）拿该口现地址与前缀，del 后立刻
add 同地址。GID 表随即紧凑重建（v1@2、v2@3）。

```bash
# 例：03 的 rocep1s0f1（netdev 名查法见下）挂 <fabric-ip>/24
ssh <node03> 'sudo -S sh -c "ip addr del <fabric-ip>/24 dev enp1s0f1np1 && \
  ip addr add <fabric-ip>/24 dev enp1s0f1np1 && echo CYCLE-OK"' < ~/.sudopw

# HCA → netdev 名映射（勿背表，动态查）：
cat /sys/class/infiniband/rocep1s0f1/ports/1/gid_attrs/ndevs/2   # → enp1s0f1np1
ip -o addr show enp1s0f1np1 | grep 'inet '                        # → 现地址/前缀
```

注意：
- **sudo 拆开调用**、密码走 `~/.sudopw`（600），绝不回显写盘。
- IP 消失窗口毫秒级；生产在跑时**不要**做（须窗口）。
- 修完立即 §1 复审该口（idx3 必须回到 RoCE v2）。

## §3 修复后验证门

```bash
bash ~/w6-kit/s4_bench.sh verify
```

全绿标准：四机各打 `Connected all rings` + `Out of bounds values : 0 OK`。
（s4_bench 现已自带 §1 审计，有洞会先 exit 9 并报洞口清单。）

## §4 兜底预案（GID=2 整体切换——勿单机改）

若某机环回后仍不能紧凑（罕见）：luz031 runbook §A.3 预案——**四机整体**把
`NCCL_IB_GID_INDEX` 从 3 改 2（.env.tp4 的 FORCE、s4_bench.sh、一切硬编码处），
重做 NCCL 握手。**绝不单机改 index**：集群 index 必须一致，单机改=半死态。

## §5 断电后完整复核清单（luz031 §A.3 传承）

| 项 | 判据 | 2026-09-21 实测 |
|---|---|---|
| isolcpus | 四机 /proc/cmdline 含 `isolcpus=8-9` | ✅ 全在（断电不伤，GRUB 持久） |
| MTU | 十六口 fabric netdev 全 9000 | ✅ 全在 |
| GID | §1 零洞 | ⚠ 03 两口洞→环回修复 |
| NCCL 库 | `/opt/nccl-ringonly` md5 `b7784b49…`（luz031 值）/ pin shim md5 | 未复核（容器内另有部署） |
| 端到端 | §3 verify 全绿 → 起栈 → 8001/8899 health 200 | ✅ |

## §6 事故史

- **2026-08-15**（luz031 时期）：同签名 `ibv_modify_qp failed 61`/GID3 空，
  预案=整体切 GID=2（§4）。
- **2026-09-21**（0.2.7 验收窗）：四机断电后 02 四口+03 两口出洞；02 于排障中
  环回修复、03 本册成文时修复；s4_bench verify 全绿，终态栈 09:3x 起栈成功。
  产出防线：start.sh `fabric_gid_preflight` + s4_bench 自审 + 本册。

## §7 GB10「PD 安全模式」时钟楔死（2026-09-21 定谳·社区同款病）

**病征**（NVIDIA 开发者论坛多帖同款：513/550/650/721/728MHz 家族）：
- 断电/**OOM 事件**后，USB-C 电源 PD 协商进安全模式 → SM 时钟钉死 513-728MHz
- 七联指纹：P0 态 / 96% util / 功耗仅 10-20W（正常负载 40W+）/ **零 throttle 标志**
  / `nvidia-smi -lgc` 静默无效（SUPPORTED_CLOCKS=N/A）/ **warm reboot 无效**
  / 无 spbm hwmon 节点（Ubuntu 内核无 DGX OS 的 PL1 可读口，DGX OS 上可见
  `spbm` power11_cap≈20W vs 健康 140W）
- 集群杀伤：TP4 单机楔死 ⇒ 全体 collective 等它 ⇒ **prefill 均匀减半**
  （2026-09-21 实测 5000→2500 t/s，排除链走完镜像/env/ctx/表/fabric 全洗脱才落到这）
- 2026-09-21 实锤：<node02> 钉 721MHz（96%util/15W），01/03/04 健康 2380+MHz

**修复（社区多帖确认的唯一有效法）**：
1. 关机 → **拔墙上 AC 插座（不是机箱端 USB-C！）1-2 分钟**（有帖建议按住电源键
   10 秒放残电）→ 回插 → 开机。
2. 验证：负载态（matmul burn 或起栈后）clocks.sm ≥2300MHz / power ≥40W。
3. 注意：warm reboot（systemctl reboot）**不修复**——2026-09-21 在 02 实测无效。

**防线**（已部署）：
- gate.sh「GPU 时钟健康」检查：gate 载荷下采样，util≥50% 而 clock<1200MHz 即 FAIL。
- 复发风险：社区报告该病会在崩溃/OOM 后复发；根治向=fwupdmgr 固件更新
  （官方称直接修 PD 问题），⚠但一帖报其引入 ConnectX-7 网络性能回归——
  **对本集群 ring fabric 是高危项，升级须专窗+fabric 全档重测**，勿顺手升。

**事故史补记**：2026-09-21 02 楔死（本节成立）；修复=用户现场冷断电。
