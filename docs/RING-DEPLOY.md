# RING-DEPLOY — 无交换机 RoCE 环网（4 口 CX-7 hairpin）从零部署指南

> **读者**：拿到 4×NVIDIA DGX Spark（GB10 统一内存），打算用**无交换机 RoCE 环网**形态
> （4 口 ConnectX-7 hairpin 环）部署本仓 DeepSeek-V4.1-Flash TP4 推理栈的工程师。
> 这是外部镜像站点的实际组网形态，也是本仓文档此前最大的空白——本篇补的就是这一块。
>
> **一句话定位**：环网形是本仓 0.3.1 及更早版本的**历史在役形**；0.3.2 现役形是双 rail
> 交换机 flat 形（从零部署见 [DEPLOY-GUIDE.md](DEPLOY-GUIDE.md)）。本篇只讲环网形怎么
> 从零把**物理面、织网面、映射表面、路由面、env 面、守卫面**立起来；镜像、权重、
> adapter 落位、boot 四查等与拓扑无关的共享步骤，直接引 DEPLOY-GUIDE，不再复述。
>
> **全文用占位符，按自己环境替换，禁止照抄文中示意值**：
>
> | 占位符 | 含义 |
> |---|---|
> | `<H1>~<H4>` | 四机的 ssh 可达地址或主机名，rank0~rank3，`<H1>` 为 head |
> | `<USER>` | 登录用户 |
> | `<registry:port>` / `<image-tag>` | 站点可达 registry 地址 / 镜像 tag |
> | `<MESH_DIR>` | 织网部署位（作者站示意 `/opt/dsv41-mesh`，守卫件内为常量） |
> | `<mesh-fabric>` | 兄弟仓（mesh 硬件转发层）在本机的克隆路径 |
> | `<ip-xx>` / `<net-xx>` | fabric 子网地址 / 网段（示意，全部需按本站实测替换） |
> | `<pref>` | transit tc flower 规则的 pref 值 |
> | `<pci-bus>` | HCA 的 devlink 总线地址（形如 `pci/0000:01:00.0`） |
>
> 文中所有具体数值、读数、md5、地址、路径都只是**量级与形态示意**，不可直接当基线锚点照抄。
>
> 相关档：环网可用边界=[RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md)（下称 RING-COMPAT）；
> 交换机形从零部署=[DEPLOY-GUIDE.md](DEPLOY-GUIDE.md)；serve 参谱=
> [../deploy/SPEC6-SERVE-REF.md](../deploy/SPEC6-SERVE-REF.md)；升级与回退=
> [../UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)；环网工具包=
> [../tools/packages/fabric-net/](../tools/packages/fabric-net/)。

---

## 0. 定位与边界

### 0.1 什么是「环网形」

本仓说「环网形」，指的就是这一种组网：**四台 DGX Spark 不接任何交换机，用 CUDA 网卡
直连线围成一个环**。每机两张 ConnectX-7、每张卡出两个口，全机 4 个 fabric 口，四机
共 16 口；每台机恰好有两个直接邻居，每对邻居之间拉**两条**直连链路（各走一张卡），
全环 8 条物理链路。作者站的布线习惯是：一个邻居方向用两张卡的 f0 口（netdev 名
`enp1s0f0np0` / `enP2p1s0f0np0` 一对），另一个方向用两张卡的 f1 口
（`enp1s0f1np1` / `enP2p1s0f1np1` 一对）——这只是示意，**你的站以实测为准**。

环网与 0.3.2 现役的「双 rail 交换机形」是两套互斥的形态，速查对照与不可混拼律见
RING-COMPAT §1。核心一句话：**两形只能整套切换**。把交换机三键带进环网、或把环网的
逐秩映射表带进交换机形，都会在 C 层或 NCCL 面 fail-closed，或者静默走错口对。

### 0.2 本篇覆盖什么、不覆盖什么

覆盖（环网专属面，本篇正文）：

1. 环网物理面总览与对向硬件转发机理（§1）；
2. 织网安装序与黄金态验收（§2、§3）；
3. `B12X_ROCE_PEER_HCA_MAPS` 映射表实测法（§4）；
4. 静态路由与连通性验收（§5）；
5. 环网 env 形（§6）；
6. 哨兵与守卫的站点适配（§7）；
7. 开机自检清单与物理面排障（§8、§9）。

不覆盖（与拓扑无关的共享面，直接读既有档）：

- 硬件前置、系统依赖版本锚、镜像获取、权重目录布局、服务面落位映射：见
  [DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §1~§5；
- boot 与四查（health 200 / printenv 四机逐字 / 横幅直读 / 面指纹四机全等）：见
  DEPLOY-GUIDE §7；
- serve 参谱与 env 键面的配对律：见 [../deploy/SPEC6-SERVE-REF.md](../deploy/SPEC6-SERVE-REF.md)。

### 0.3 0.3.2 的件在环网能拿什么

这是环网采用者最常问的问题，答案的**唯一权威**是
[RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md)，这里只给导览：

- **能直接拿**（拓扑无关）：质量量具 `tools/bench/qeval.py`、`gsm8k_dsv41.py`、
  `needle_probe.py`（RING-COMPAT §2.1）；adapter 修复件（§2.2，注意与引擎的绑定律）；
  env 面拓扑无关键（§2.3，本篇 §6 会再引一次）。
- **不能拿**（交换机专属）：`LUZ_SWITCH_ROCE_FLAT=1`、`B12X_ROCE_TOPOLOGY=switched`、
  `B12X_ROCE_TRAFFIC_CLASS=106` 三键与 flat/one-shot 运行时件（RING-COMPAT §3）。
- **还差一块**：「环网 + r032c 引擎」当前缺一个 boot profile 合成，未随本仓发布、
  未在环网硬件上验收（RING-COMPAT §4）；没有测试窗时，环网保持在 0.3.1 形，只取
  低风险件。
- **已知负判**：`channelId % 4` 四口轮转（v5-quad）在 4 口 hairpin 环上不可用，
  ring-only 的 v4 配对表才是对实际布线的编码（RING-COMPAT §6）。本仓
  `deploy/nccl/nccl-ringonly/libnccl.so.2.30.7` 是 v4 配对构建，不要用未经
  验证的源码改造替换在役库。

### 0.4 一条贯穿全篇的经验

环网部署的坑分四层，从下往上：**物理面（接线/FEC/路由）→ 织网面（hairpin/QoS/
tc 规则）→ 通信面（映射表/GID/NCCL）→ 验收面（怎么量才可信）**。绝大多数误判，
都是「用上一层的结论去解释下一层的现象」——比如把映射表配错引起的 QP 建链超时，
当成网卡或线材问题去查。本篇各节都按「命令 + 预期输出 + 失败先查什么」组织，
就是为了让每一层的问题在它自己的层内先被排除。

---

## 1. 环网物理面总览

### 1.1 环拓扑（文字版图）

四机围成一个环。示意（哪两台互为邻居由你的实际接线决定，下图只是形态示意；
rank 编号沿环顺序分配）：

```
              ┌───────── 双链路（示意：f1 对口）─────────┐
              │                                          │
        <H1> (rank0, head)                        <H2> (rank1)
              │                                          │
        双链路（示意：f0 对口）                  双链路（示意：f0 对口）
              │                                          │
        <H4> (rank3)                              <H3> (rank2)
              │                                          │
              └───────── 双链路（示意：f1 对口）─────────┘
```

按这个环序，**对向对**就是：rank0↔rank2、rank1↔rank3——环上相隔一台、
**没有物理直连**的那两台。这一点是整个环网方案的轴心：邻居对走直连链路，
对向对走「中间机硬件转发」，见 1.2。

口名速查（DGX Spark 上 CX-7 的典型命名，**装机后第一件事是核对你站的真名**）：

| 面 | 典型名 | 说明 |
|---|---|---|
| fabric 口（netdev） | `enp1s0f0np0` `enp1s0f1np1` `enP2p1s0f0np0` `enP2p1s0f1np1` | 两卡×两口；后文 DEVLIST 即这四个 |
| fabric 口（RDMA/HCA 名） | `rocep1s0f0` `rocep1s0f1` `roceP2p1s0f0` `roceP2p1s0f1` | 与 netdev 一一对应，`ibstat` 可见 |
| 管理口 | `enP7s7` | OOB/bootstrap/ssh 走它；NCCL 的 `NCCL_SOCKET_IFNAME` 也指它 |

核对命令与预期：

```bash
ibstat | grep -E 'CA |Port 1|State'      # 应看到 4 个 CA、各 1 口、State: ACTIVE
ip -br link | grep -E 'enp1s0|enP2p1'    # 4 个 fabric netdev + 管理
```

失败先查：CA 数量不足 4（网卡/驱动面，`lspci | grep -i mell`）；口名与上表不符
（换内核/驱动会变命名，此时全篇命令里的口名都要跟着替换，别硬抄）。

### 1.2 对向无直连：靠中间机硬件转发

4 节点环里，对向两台之间**没有物理链路**。对向数据面的做法不是让中间机跑软件路由，
而是让中间机的 ConnectX 在**硬件里转发**，机理分三步：

1. 发起端建对向 QP 时带 **flow label 16383**；
2. mlx5 驱动由该 flow label 派生 **UDP 源端口 65535**；
3. 中间机上预置的 `tc flower` 硬件规则（`skip_sw`）按端口匹配这类包，
   **只改以太头**（`pedit` 改 eth type 与目的 MAC），然后从另一个口转出
   （`mirred egress redirect`）。

规则的通用形态（每机每个 transit 口一条；所有值都是占位符，由织网件按本站拓扑生成，
**不要手搓**，见 §2）：

```bash
tc filter add dev <口> ingress protocol 0x88b5 pref <pref> handle <pref> flower skip_sw \
  src_mac <邻居> dst_mac <对角> action pedit ex munge eth type set 0x0800 pipe \
  action pedit ex munge eth dst set <本机> pipe action mirred egress redirect dev <另一口>
```

**为什么引擎侧不自己建这些规则**：本仓通信引擎只调标准 verbs（`create_qp` /
`modify_qp` / `reg_mr` / `post_send` / `poll_cq`），**零 flow steering**——它假设
硬件转发规则已经由织网件预先存在。也别想着自己用 netdev 层 `tc` 去拦 RoCE 流量
补一个「软件版转发」：发往 4791 端口的流量在网卡内部先被 RDMA steering 接走，
根本不进 tc 域——这条路已被证否，唯一有效形态就是 `in_hw` 的 flower 规则。

### 1.3 物理面常量（作者站裁定值，站点装机后逐项断言）

| 项 | 值 | 归属域 |
|---|---|---|
| MTU | 9000（16 口全量） | netplan/织网域 |
| hairpin 队列 | `hairpin_queue_size=8192`（devlink `driverinit`） | 织网件 hairpin 域 |
| trust 模式 | `pcp` | 织网件 qos 域 |
| ring 收发队列 | RX 4096 / TX 1024（本仓 [lutune.sh](../tools/packages/fabric-net/payload/weave/lutune.sh) 的 `RX_TARGET=4096`） | 本包织网参数件 |
| GID index | `NCCL_IB_GID_INDEX=3`（全集群硬钉，一致性律，零改） | NCCL/env 域 |

---

## 2. 织网安装序

### 2.1 先取件：织网件在兄弟仓，不在本仓

织网（mesh 硬件转发层）的全套件**不在本仓交付包里**。本仓 [README §四](../README.md)
点名的基础设施仓是
**[luxingcom/aicad-nccl-optimization](https://github.com/luxingcom/aicad-nccl-optimization)**，
其 `mesh-fabric/` 目录承载 CX-7 无交换机 RoCE 环网的：**拓扑生成器（plan.py /
inventory.sh）、硬件 tc hairpin 规则、驱动预置（hairpin 8192 + trust pcp）、
RDMA-TX 源标记探针、systemd 引导单元对、netplan 正典、正典拓扑、守卫自愈套件、
九章研究报告**；同仓另有 NCCL 2.30.7 ring-only 优化资料包（补丁栈/部署指南/
排障手册/doctor 工具链）。

取件指引：

```bash
git clone https://github.com/luxingcom/aicad-nccl-optimization <mesh-fabric>
```

三条纪律：

1. **本仓里 `grep` 不到织网件 ≠ 厂商没做**。在役件放在兄弟仓是本套方案的既定分工，
   判「缺件」前先读本仓 README §四 的指引段。
2. 各件的**具体用法、参数、子命令名以兄弟仓 README/部署指南为准**，本篇不转述、
   不虚构；下面各步给的都是「这一步在宿主机上怎么验收」的只读命令。
3. 内容判定权威顺序：**镜像烘焙件 > 兄弟仓 dev tip > 脱敏交付仓副本 > 已装件**。
   对版本有疑义，先对镜像烘焙面，别拿仓副本猜。

本仓与织网相关的自有件是 [tools/packages/fabric-net/](../tools/packages/fabric-net/)
（织网参数器 lutune.sh、topology.json 黄金态、守卫/诊断/runbook 的收编包），与兄弟仓件
的分工关系见其 [README.md](../tools/packages/fabric-net/README.md)。

### 2.2 安装序总览

按依赖顺序，一机一机装、四机装完再验收（顺序不能颠倒的原因见 2.6 的 qos 铁律）：

| 步 | 件（兄弟仓） | 作用 | 验收锚 |
|---|---|---|---|
| 1 | `plan.py` + `inventory.sh`（拓扑生成器） | 采集本站接线，产出本站正典拓扑与 transit 规则/路由清单 | 生成产物的 cap 值（§3.2） |
| 2 | `mesh-up.sh` / `mesh-down.sh` | 把 transit tc flower 规则与对向 /32 路由落到运行态 | `tc filter show` 的 `in_hw` 计数（§3.1） |
| 3 | `hairpin.sh`（驱动预置） | `devlink` 把 `hairpin_queue_size` 设 8192（driverinit） | `devlink dev param show`（§3.3） |
| 4 | `qos.sh`（驱动预置） | 把 trust 模式设 `pcp` | `mlnx_qos -i` 的 trust 行（§3.3） |
| 5 | systemd 双单元（引导单元对） | 开机重放 hairpin/规则/路由，织网态重启存活 | `systemctl`（§3.4） |
| 6 | `fabricctl`（检查/自愈/自检） | 织网态日常巡检与自愈入口 | `fabricctl check` 全绿（§3.5） |
| — | 本仓 `lutune.sh` | NIC ring 收发队列参数（RX 4096），幂等 apply | `ethtool -g`（§3.3） |
| — | netplan 正典 | MTU 9000 与 canonical 路由的持久化 | `ip route` + netplan 原件 diff（§5.4） |

### 2.3 步 1：拓扑生成

在 head 机上按兄弟仓指南先跑 `inventory.sh` 采集四机真实接线，再跑 `plan.py` 生成本站
拓扑与规则清单。这一步的产出是后面所有步骤的唯一输入——**生成的值就是本站的值**，
包括每机的两个 transit 口、每条 transit 规则的 MAC 对与 pref、对向路由的 dst/via/dev。

失败先查：inventory 采集不到某机的口（该机驱动未就绪或口名与预期不符，回 §1.1 核对）；
生成器报 cap 异常（见 §3.2 的 cap 判读，81920 说明 hairpin 还没预置，属正常首跑顺序）。

### 2.4 步 2：mesh-up 落规则

用 `mesh-up.sh` 把生成清单落到运行态：每机两条 transit tc flower 规则（对两个方向
各一条）+ 对向 /32 主机路由（`ip route add <dst>/32 via <via> dev <dev>` 形）。
`mesh-down.sh` 是对应拆除件。

一条硬纪律：**以后任何停 mesh 的操作都必须走 unit / 脚本正典入口，绝不 `pkill`**。
pkill 残留流表会把该机 TX 吞吐塌到 ~14Gb/s 量级（社区同款病，见
[COMMUNITY-FIELDNOTES.md](../tools/packages/fabric-net/payload/runbook/COMMUNITY-FIELDNOTES.md)
症状 3），修复要重载 `mlx5_core` 驱动，代价远大于多敲一条正规命令。

失败先查：`mesh-up` 报 Nexthop/路由错误（大概率是开机竞态——网络规则脚本只等
`operstate=up` 不等 IPv4 就绪，详见 §8.3；事后手动重跑即可）。

### 2.5 步 3~4：hairpin 与 qos（顺序铁律）

hairpin 与 qos 是两个驱动预置件，**必须 hairpin 在前、qos 在后**。原因：hairpin 的
实现走 `devlink driver_reinit`，这个动作会把 trust 模式**打回 dscp 缺省**——如果你
先跑 qos 再跑 hairpin，qos 刚设好的 `pcp` 会被 hairpin 悄悄抹掉，而且没有任何报错，
只在起栈后表现为对向流量不通或劣化。这是环网装机被踩过多次的坑，写进操作规程里：
**qos 永远后于 hairpin，且每次重放 hairpin 之后都要复查 trust**。

另外注意：hairpin 的 `devlink driver_reinit` 每口会停顿约 4 秒、trust 切换还会再抖
一次，四口全过一遍是「看起来卡住其实在工作」，等它跑完再下结论（§8.3 开机竞态
同机理）。

失败先查：hairpin 写不进（`devlink` 权限/驱动版本，须 root）；trust 复查不是 `pcp`
（重放 hairpin 后忘了重跑 qos——本节铁律的直接症状）。

### 2.6 步 5~6：systemd 双单元与 fabricctl

把 mesh 引导做成 systemd 双单元（作者站形：mesh 主单元负责 boot 重放 hairpin/
规则/对角路由，参数单元负责 ring 队列 apply），部署到四机并 enable。之后日常的
织网态巡检走 `fabricctl`：**检查（check）/自愈/自检**三个面（子命令名以兄弟仓
指南为准；`check` 在本仓守卫件中有实证调用形 `<MESH_DIR>/bin/fabricctl check`）。

本仓 `lutune.sh` 的角色补充一句：它是幂等 apply（读现值→等值跳过→差值才写），
失败为 fail-open——参数面缺失不让机器不可用，但会在 journal 高优先级大声留痕；
守卫巡检发现 ring 漂移时会自动 L1 重放它。

失败先查：单元起不来（§8.3 竞态）；`fabricctl check` 有 FAIL（先看 FAIL 项属于哪一面——
规则面回 §3、路由面回 §5、GID 面回 §5.5，逐层归位，别一上来就重装）。

---

## 3. 织网黄金态验收

织网装完不等于织对了。黄金态判据四条，全部是只读命令，四机各跑一遍。

### 3.1 判据一：每机恰 2 条 transit tc flower 规则且 `in_hw`

验收判据是**硬件落地**，不是「有规则就算」——`in_hw` 计数为 0 或软件落地的规则
等于没装（fail-closed 语义）。每机两个 transit 口、每口恰一条：

```bash
for d in enp1s0f0np0 enp1s0f1np1 enP2p1s0f0np0 enP2p1s0f1np1; do
  n=$(tc -s filter show dev "$d" ingress 2>/dev/null | grep -c in_hw)
  echo "$d in_hw=$n"
done
```

预期：**恰两个口各 `in_hw=1`（全机合计 2 条），其余口 0**。带 `-s` 还能看到每条
规则的命中计数，起栈后对向流量会让它增长。

失败先查：规则存在但 `in_hw` 数不到（软件落地——检查规则是否漏了 `skip_sw`，或
网卡 eSwitch/steering 模式不支持，回兄弟仓部署指南的对应用节）；规则整个不存在
（mesh-up 没跑成，回 §2.4）；条数大于 2（重跑 mesh-up 叠加了重复规则，走 mesh-down
清干净重来，别手工挑着删）。

### 3.2 判据二：RoCE cap 值判「织没织网」

拓扑生成器算出的 RoCE cap 只有两个正常取值，**它不是调优参数，是织网状态的判读位**：

| cap 值 | 含义 |
|---|---|
| `81920` | `hairpin_queue_size` 还是默认 1024——**还没织网** |
| `262144` | hairpin ≥ 8192 已预置——**已织网** |

看到 81920 别去「调大它」，先回 §2.5 把 hairpin 预置补上。

### 3.3 判据三：驱动与队列参数逐口断言

```bash
# hairpin：四口各一条，cmode driverinit value 应为 8192
for b in <pci-bus-1> <pci-bus-2> <pci-bus-3> <pci-bus-4>; do
  devlink dev param show "$b" name hairpin_queue_size
done
# 预期含：cmode driverinit value 8192

# trust：应 pcp（qos 域；重放 hairpin 后必复查，见 §2.5 铁律）
mlnx_qos -i enp1s0f0np0 | grep -i trust
# 预期：Priority trust state: pcp

# ring 队列：RX 4096 / TX 1024（取 Current 段，别取 Max 段）
ethtool -g enp1s0f0np0
# 预期 Current hardware settings: RX 4096 / TX 1024
```

失败先查：hairpin 值不对（重放 hairpin 后忘了让 systemd 单元接手持久化，重启就丢，
回 §2.6）；trust 是 dscp（§2.5 顺序铁律的标准症状）；`ethtool -g` 读数混乱——它打
两段（Max 与 Current），取错段会把最大档当当前档，属读数面经典假信号。

### 3.4 判据四：单元与部署面完整性

```bash
systemctl list-units --all | grep -Ei 'mesh|lutune|fabric'   # 双单元 loaded+active
ls <MESH_DIR>/                                              # topology.json / bin / state 齐备
```

本仓件的版本完整性用包自带自检：

```bash
cd <本仓>/tools/packages/fabric-net && bin/fabric-net selfcheck   # 0=绿
bin/fabric-net manifest                                          # md5 逐件对表
```

失败先查：单元 `failed`（§8.3 竞态，手动重拉一次再判）；selfcheck 红（件被改过——
md5 漂移按同日更新律处理，别带病继续）。

### 3.5 黄金态参照物：topology.json

`<MESH_DIR>/topology.json` 是黄金态期望的权威载体（本仓收编样本见
[weave/topology.json](../tools/packages/fabric-net/payload/weave/topology.json)，
其字段结构就是你要维护的那份的样子）：

| 字段 | 内容 | 谁消费 |
|---|---|---|
| `hosts.<真主机名>.role` | head/worker、rank 号、NFS 角色 | 人读 |
| `hosts.<真主机名>.ports` | netdev → {ip, mac} | 路由/规则校验 |
| `hosts.<真主机名>.routes32` | canonical 静态路由清单（`dst via nh dev 口`） | 守卫 F-G6b、fabricctl |
| `hosts.<真主机名>.gid3` | 每 HCA 的 idx3 期望 IPv4 | 守卫 F-G5 GID 洞/错值判定 |
| `hosts.<真主机名>.tc_ingress_prefs` | 每 transit 口的 pref | 规则面核对 |
| `nfs_mount` / `exports` | 权重 NFS 面 | 守卫 F-G6 可达性 |

注意：**`hosts` 键必须是真主机名**（消费方用 `socket.gethostname()` 取键），
填别名/IP 会让守卫整面 FAIL——这是 §7 站点适配三步的第一步。

---

## 4. PEER_HCA_MAPS 映射表实测法

### 4.1 它是什么：一张「属主映射表」

env 里的 `B12X_ROCE_PEER_HCA_MAPS` 编码的是**「哪个节点的哪个口，走哪两条路径到
哪个对端」**——也就是作者站点的物理接线本身。格式拆解（以
[../deploy/env/PROD-R51W5-FL6FIX-spec1.env](../deploy/env/PROD-R51W5-FL6FIX-spec1.env)
的现役值为形态示例）：

```
B12X_ROCE_PEER_HCA_MAPS=1=1/3,2=0/3,3=0/2;0=1/3,2=0/2,3=0/3;0=1/2,1=0/2,3=1/3;0=0/2,1=1/2,2=1/3
```

- 按 `;` 分成四段，**段顺序 = rank 顺序**（第一段是 rank0 的表，以此类推）；
- 段内每个条目 `对端rank=本机HCA索引/本机HCA索引`：到该对端用本机哪两条路径
  （双路径），HCA 索引是 `B12X_ROCE_HCA` 列表里的 0 基下标；
- 每段恰好 3 条（4 节点映射全部非自身 rank）。

**这张表是拓扑绑定件，只拿机制、不拿值**：上面的值是作者布线的编码，你的站
照抄必挂。值必须从你自己的织网产物（§2.3 生成的拓扑/路径清单）推导。

### 4.2 照抄必挂的报错长什么样

映射表与实际布线不符时，起栈会在 RoCE 建链阶段失败，报错**点名具体 rank**：

```
RoCE all-reduce connect failed: rank 0: RoCE queue-pair connect failed:
ibv_modify_qp(RTR): Connection timed out;  rank 2: …同
```

看到这个报错，第一反应不是去查网卡和线（那是用物理层结论解释通信层现象，
见 §0.4），而是回到映射表本身。

### 4.3 排查抓手：按 `;` 分段逐 rank diff

把「交付形/你疑心的形」与「本机实测推导形」按 `;` 分段拆开，逐段 diff：

```bash
old='1=1/3,2=0/3,3=0/2;0=1/3,2=0/2,3=0/3;0=1/2,1=0/2,3=1/3;0=0/2,1=1/2,2=1/3'   # 示意
new='<按本站织网产物推导的值>'
diff <(tr ';' '\n' <<<"$old") <(tr ';' '\n' <<<"$new")
```

判读：**不一致的那几段，就是报错点名的那几个 rank**。diff 结果与报错点名的 rank
因果吻合，即可高置信按本站值改表动手，不用先去碰网卡。

### 4.4 四条硬约束（不满足直接抛异常，不会静默降级）

1. **每个 rank 必须映射全部非自身 rank 且各一次**（4 节点就是 3 条），漏一个报
   `missing=[…]`；
2. **同一 peer 的两个索引必须互异**，且都落在 `[0, hca_count)` 内；
3. **HCA 数 > 2 且本表留空 → 直接 RuntimeError**。交付模板里「首靴留空、读 INFO
   后填」那条注释在 4 口环网下是**陷阱**——HCA>2 时空表起栈即炸，根本走不到
   「读 INFO」那一步，表必须在首靴前就按布线推导填好；
4. **改路径数必须同步改表**：路径数（双路径/更多）与这张表是一对，只改一边必炸。

### 4.5 实测路线与「失败点前移」

- 邻居对的口对可以先用 perftest 直接验证（perftest 的正确用法见 §5.3——它只能测
  邻居对）；
- 对向对的最终裁决只能靠起栈（图捕获阶段的对向 RDMA write，见 §1.2 与 §5.1）；
- **修好映射表后，失败点会前移而不是立刻全绿**——典型顺序是从「QP 建链 RTR 超时」
  推进到「图捕获阶段 `RDMA write to rank N ... transport retry counter exceeded
  (vendor_err 0x81)`」。后者的 N 若=本机对向 rank，那是 §3 织网面的问题（transit
  规则/路由），**且与路径数无关**——别去改路径数参数，白费一轮。
  「失败点变了且更靠后」本身就是上一步修复生效的证据，别因为又失败了把上一处
  改回去。

---

## 5. 静态路由与连通性

### 5.1 机理：路由必须挂在「该 path 真正用的那个口」

内核的 `ib_resolve_eth_dmac` **强制从 QP 自己绑定的网卡做路由查找**。所以对向
（以及一切非直连目标）的静态路由必须满足两条：

1. **挂在该条 path 真正使用的那个口上**（`dev <该口>`）；
2. **下一跳 = 该口的直接邻居**（不是随便哪个邻居，更不是对角地址本身）。

另外，**同一目标不要挂在两个口上**（二义性）。

有一条常见误读要先拆掉：手册里「路由表仅直连 4 条 fabric 子网 → 干净/不改」
这句话，指的是**别加额外的全局路由**，**不是**「对向不要路由」。对向主机路由
（mesh-up 落的 `/32` 形）是必需件，少了它对向必不通。

### 5.2 验收：`ip route get` 逐条命中

对每个「本机 × 对端 fabric 地址 × 该 path 用的口」组合验收：

```bash
ip route get <对端fabric地址> oif <该path真正用的口>
# 预期输出形：<对端fabric地址> via <该口邻居地址> dev <该口> src <本机该口地址>
```

必须逐字命中 `via <邻居> dev <该口>`。**挂错口的表现是起栈 7 秒速败，不是慢**——
看到秒级失败先查路由挂口，别往性能方向想。

一个读数坑：`ip route show` 对主机路由**不打印 `/32`**（打印形就是裸地址），所以
用 `grep '/32'` 验收会「假丢路由」；验收一律用上面的 `ip route get` 语义法，或按
网段前缀查。同理，写 topology.json 的 `routes32` 字段时也要按 `ip route` 的打印形
写（裸地址、不带 `/32`），写成 `/32` 会让守卫的字符串匹配双双假红——这是 §7
适配三步的第二步。

### 5.3 ICMP 与 perftest 判不了对向

- **ICMP ping 到对向不通是预期**，别用它判对向连通——中间机硬件转发按 flow label
  派生的 UDP 源端口匹配，ICMP 根本不匹配这套规则；
- **`ibv_rc_pingpong` / `ib_write_bw` 同样不设 flow label**，拿它们测对向一对
  「必然连不上」，只会得到「对向挂了」的假结论。它们的正确用法是**测邻居对**；
- 写探测脚本时**判据别用子串匹配**（如 `"0% packet loss" in out`）——它会被
  `"100% packet loss"` 命中，把全失败读成全通。判 exit code 或解析 `received` 数。

对向连通的正典验收是 NCCL 面（见 5.6 的 s4_bench verify），不是 ping。

### 5.4 路由持久化

运行态路由验收绿后，确认重启存活：canonical 路由要进 netplan 正典（作者站形：
f0 对口归 `97-roce-mtu.yaml`、f1 对口归 `99-nvidia-sync-cluster.yaml`，两文件是
root-0600 部署面；本仓只登记期望态模板，见
[netplan-templates/](../tools/packages/fabric-net/payload/weave/netplan-templates/)），
或由 mesh 单元 boot 重放（mesh-up 在册的 `ip route add <dst>/32 via <via>` 成对
= 重启存活直证；守卫 F-G6b-2 按逐条证据认这两种持久化提供者）。渲染器归属
（NetworkManager/networkd）按各机现状零改，canonical 路由进各口既有文件。

### 5.5 GID 洞三件套

判一个口是不是「GID 洞」，要读**三件套**，不是单看一处：

```bash
hca=rocep1s0f0   # 逐口轮换
cat /sys/class/infiniband/$hca/ports/1/gid_attrs/types/3   # 期望 RoCE v2
cat /sys/class/infiniband/$hca/ports/1/gids/3              # 期望非全零
cat /sys/class/infiniband/$hca/ports/1/gid_attrs/ndevs/2   # 期望能解析出 netdev
```

**type + gid 值 + ndev 三者全零/全空才是洞**；只读一处容易把「值漂移」误判成洞。
洞的根因通常是**该口没有 IPv4**——修法是把 IPv4 加回来（或做一次 IP 环回重铺，
见下），并四机复查。断电/硬重启后这个病高发，正典手册=
[FABRIC-GID-REPAIR-RUNBOOK.md](../tools/packages/fabric-net/payload/runbook/FABRIC-GID-REPAIR-RUNBOOK.md)。

四机零洞审计（每台 4 口 × idx3）：

```bash
for h in <H1> <H2> <H3> <H4>; do
  ssh "$h" 'for c in rocep1s0f0 rocep1s0f1 roceP2p1s0f0 roceP2p1s0f1; do
    t=$(cat /sys/class/infiniband/$c/ports/1/gid_attrs/types/3 2>/dev/null)
    g=$(cat /sys/class/infiniband/$c/ports/1/gids/3 2>/dev/null)
    { [ "$t" = "RoCE v2" ] && [ -n "$g" ] && [ "$g" != 0000:0000:0000:0000:0000:0000:0000:0000 ]; } \
      || echo "HOLE: '$h' $c idx3=[$t] gid=[$g]"
  done'
done
# 预期：零 HOLE 行
```

修复：对每个洞口做一次 IP 环回（`ip addr del` 同址后立刻 `add` 回来，逼 rdma_cm
重建紧凑 GID 表；毫秒级窗口，**引擎在跑时禁做**）。守卫面有自动版
[fabric-gid-heal.sh](../tools/packages/fabric-net/payload/guards/fabric-gid-heal.sh)
（四前置 P1-P4 全绿才动手、单法单次、1h 内 ≥2 次熔断）。兜底预案是**四机整体**
把 `NCCL_IB_GID_INDEX` 从 3 切 2——**绝不单机改**（集群 index 一致性律，单机改=
半死态）。

### 5.6 端到端终验

用本包 [s4_bench.sh](../tools/packages/fabric-net/payload/diag/s4_bench.sh) 的
verify 档做四机 NCCL allreduce 验证：

```bash
bash tools/packages/fabric-net/bin/fabric-net run s4_bench verify
```

全绿标准：四机各打 `Connected all rings` + `Out of bounds values : 0 OK`。
它自带 5.5 的 GID 预检，有洞会先 `exit 9` 并报洞口清单（fail-closed），
修完重跑至零洞再跑 verify。

---

## 6. 环网 env 形

### 6.1 基线：51 键环网 env

环网形的 env 基线 =
[../deploy/env/PROD-R51W5-FL6FIX-spec1.env](../deploy/env/PROD-R51W5-FL6FIX-spec1.env)
（0.3.1 定型 51 键；含 RoCE/b12x 环网族 7 键）。环网族键清单——这 7 键是环网形
区别于交换机形的 env 骨架，逐键都要在（值按本站实测）：

| 键 | 作用 |
|---|---|
| `DSV41_ROCE_RING=1` | 选 ring 运行时（roce_ring 同族件） |
| `SGLANG_ROCE_ALLREDUCE=1` | RoCE allreduce 面 |
| `SGLANG_ROCE_MAX_SIZE` / `DSV41_ROCE_GATHER` | 通信聚合窗口（通信档位两键，见 6.3） |
| `B12X_ROCE_HCA` | 四口部署对（`rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1`） |
| `B12X_ROCE_PEER_HCA_MAPS` | §4 的映射表 |
| `B12X_ROCE_TWO_WAVE_THRESHOLD_BYTES=0` | 双波阈值 |

NCCL 面配套：`NCCL_IB_HCA` 用同一四口部署对、`NCCL_IB_GID_INDEX=3`（一致性律）、
LL128 三键（`NCCL_BUFFSIZE`/`NCCL_LL128_BUFFSIZE`/`NCCL_PROTO`）随基线文件；
NCCL 库面用 `deploy/nccl/nccl-ringonly/` 的 v4 配对构建 + ncclpin（RING-COMPAT §6）。

### 6.2 禁带交换机三键

从交换机形 env 整文件复制是最高频事故源。**这三键绝不进环网 env**：

| 禁键 | 为什么 |
|---|---|
| `LUZ_SWITCH_ROCE_FLAT=1` | 选 flat 运行时；环网走 `roce_ring`，带进即 fail-closed 或走错口对 |
| `B12X_ROCE_TOPOLOGY=switched` | C 层关闭 2 跳假设/flow-label 技巧——这些恰恰是环网的命根 |
| `B12X_ROCE_TRAFFIC_CLASS=106` | 对应交换机 PFC/DSCP 规划；环网无此规划 |

反过来，交换机 env（如 CBX1A 56 键）**删掉了** `B12X_ROCE_PEER_HCA_MAPS`——所以
环网要么保留 51 键原文件，要么按 RING-COMPAT §2.3 键表**手工增量**，永远不要
整文件横拷。

### 6.3 可增键与通信档位

51 键基线上可逐项加入的拓扑无关键（健康探针开关、CERT 八元、E16 双键等）以
RING-COMPAT §2.3 的键表为唯一依据，逐键加、逐靴验。其中「通信聚合窗口两键」
（`SGLANG_ROCE_MAX_SIZE`/`DSV41_ROCE_GATHER`）要单独提醒两条纪律：

1. **这两键是绑定项不是调优项**：在新代引擎上它们是硬依赖，回滚即高并发塌陷
   （非单调塌陷=退回慢路径的指纹）；A/B 结论只在**做 A/B 的那一代引擎**上成立，
   换代后全部作废重做；
2. 环网 4 口形上把两键抬到 1179648 一档，RING-COMPAT §2.3 标注为中风险、需 A/B
   ——先跑同形基线再开窗，别拿交换机形读数当环网预期。

### 6.4 env 尾换行检查

boot 链用 `while read` 逐行注入 env，文件末尾缺 `\n` 时**最后一行整个静默丢失**
（丢的经常正是关键开关）。boot 链当前版本已带尾行守护（尾行丢失会拦截提示），
但自检仍然建议每次改完 env 跑一遍：

```bash
tail -c 1 <ENVFILE> | xxd
# 预期末字节：0a
```

两个后续动作别忘：补换行会改文件 md5，锚表里的形 md5 要同步更新；补换行**不改
运行中的容器**，须重靴才生效——报告里别写成「已生效」。

---

## 7. 哨兵与守卫的站点适配

fabric-net 包里的守卫/哨兵族是**宿主侧件**（判据全来自宿主 /proc /sys，不入烘焙
镜像，部署面分发到四机），装上即用是错觉——它们按作者站校准，新站必须做本节
适配。适配完成后用 §3.4 的 selfcheck/manifest 对版本。

### 7.1 fabric-sentinel：SENTINEL_* 参数表

[fabric-sentinel.sh](../tools/packages/fabric-net/payload/guards/fabric-sentinel.sh)
是 15 分钟级的 32MB torch allreduce 性能哨兵。**当前版本已站点参数化（2026-10-30）**：
带 `:?` 的必设参数缺一即拒跑（不再有作者站硬编码静默失效面），参数全表：

| 参数 | 必设 | 含义 |
|---|---|---|
| `SENTINEL_IMAGE` | **是** | 探针镜像：任意可达 registry 的 sglang 同族镜像（torch AR 探测用，非引擎镜像） |
| `SENTINEL_MASTER_ADDR` | **是** | head 机的 **fabric 子网**地址（rank0 rendezvous 用，别填管理网地址） |
| `SENTINEL_W1` / `W2` / `W3` | **是** | 三台 worker 的 ssh 可达主机名（对应 rank1/2/3） |
| `SENTINEL_ASSETS` | 否（缺省 `$HOME/migrate-assets`） | 探针资产根，四机同路径可达；其下应有 `dsv41/sentinel/ar_probe.py`、`nccl-ringonly/`（含 `libnccl.so.2.30.7`）、`ncclpin.so`。**root 跑法下 `$HOME=/root` 会失锚**（docker -v 静默建空目录），务必显式设 |
| `SENTINEL_SUDO_USER` | 否 | root/systemd 跑法下降身到该用户走 ssh 密钥面 |
| `SENTINEL_API` / `SENTINEL_MPORT` | 否 | 引擎 API（缺省 `http://127.0.0.1:8899`）/ rendezvous 端口（缺省 29617） |
| `SENTINEL_STATE` / `SENTINEL_ALERTS` / `NODE_EXPORTER_CTN` | 否 | state/alerts 路径与 node-exporter 容器名 |

示例调用（head 机）：

```bash
SENTINEL_ASSETS=<ASSETS根> \
SENTINEL_IMAGE=<registry:port>/lmsysorg/sglang:<image-tag> \
SENTINEL_MASTER_ADDR=<H1的fabric地址> \
SENTINEL_W1=<H2> SENTINEL_W2=<H3> SENTINEL_W3=<H4> \
SENTINEL_SUDO_USER=<USER> \
bash tools/packages/fabric-net/payload/guards/fabric-sentinel.sh --baseline
```

行为要点：先建带后检测（`--baseline` 5 发取中位、±25% 建带；不足 3 有效发不写带）；
每轮发射前过 **idle 双确认门**（health=200 且 running=0 且 waiting=0，不过=SKIP
绝不与在飞请求共跑 GPU 探测）；带外=CRIT 三通道告警，带下越只留痕。两处 2026-10-30
修复后才是可用态：`/v1/loads` 包裹形（`{"loads":[…]}`）解析兼容、带外比较改 awk
浮点——**如果你用的是别处拷来的旧版守卫，这两处静默 bug 会让哨兵永不告警**，
一律用本仓当前版，并把修复推回你拿件的上游。

### 7.2 守卫（fabric-guard）站点适配三步

[fabric-guard.sh](../tools/packages/fabric-net/payload/guards/fabric-guard.sh) 的
F-G1..F-G10+Q1-Q7 判据里，三处按作者站写死，新站必须改：

1. **topology 的 `hosts` 键 = 真主机名**。守卫用 `socket.gethostname()` 取键，你
   在 topology.json 里填别名或 IP，GID 面（F-G5）与路由面（F-G6/F-G6b）整面 FAIL。
   `hostname` 命令回什么就填什么；
2. **`routes32` 字段按 `ip route` 的打印形写**。主机路由打印形是**裸地址、不带
   `/32`**（见 §5.2 的读数坑）；字段里写成 `/32` 会让注册面匹配双双假红；
3. **PFC/缓冲期望按本站规划**。守卫的 F-G2 收缓冲模板与 F-G3 PFC prio3/5 期望
   （`1 1`）是**作者车队的前置硬化**——新信任模式（trust=pcp）下 PFC 3/5 空闲、
   未配不影响环网；你的站没做同款硬化就把这两条期望改成你站的实际规划值，否则
   守卫首巡检一片红，全是「作者站的题你站没抄」的假故障。FEC corrected 阈值
   （F-G7）不在此列——**那项要当真**，见 §9.1。

另外两处hostname相关：[fabric-restore-gate.sh](../tools/packages/fabric-net/payload/guards/fabric-restore-gate.sh)
开头有一道 `hostname = 作者站 head 主机名` 的门——非该主机名直接 exit 0（整件
no-op）。站点采用时把这一行改成你站 head 的真主机名（同时核对件内四机 ssh 汇读
用的工作机组常量），否则引擎死态 READY-TO-BOOT 广播永远不会触发。

### 7.3 fabric-doctor：`--json` 的 fail-closed 语义

[fabric-doctor.sh](../tools/packages/fabric-net/payload/diag/fabric-doctor.sh) 是
只读诊断件（HCA ACTIVE/接口在位/carrier 采样）。**当前版本**（2026-10-30 修复）：
`--json` 出 verdict 三字段族的前提是 `_lib/verdict.sh` 在位——**五包（fabric-net
等）必须同根部署**；`_lib` 失锚时 `--json` 直接 `exit 2` 并报
「五包须同根部署；--json 出口需要 verdict.sh，拒绝静默降级」，不再假装成功。
见到 exit 2 先查部署根布局，别当判据红。

---

## 8. 开机自检清单

每次整机重启/断电恢复后，起栈前按单走一遍（顺序即依赖序）：

| # | 检查 | 命令 | 判据 |
|---|---|---|---|
| 1 | mesh 单元状态 | `systemctl status <mesh单元>` | active；显示 `activating` 是在逐口调参（约 7s/口），**等即可，不是故障** |
| 2 | 织网黄金态 | §3.1 命令块 | 每机恰 2 条 `in_hw` |
| 3 | 驱动参数 | §3.3 命令块 | hairpin 8192 / trust pcp / RX 4096 |
| 4 | 路由面 | §5.2 命令块 | 逐条 `via <邻居> dev <该口>` 命中 |
| 5 | GID 零洞 | §5.5 审计块 | 四机 16 口零 HOLE |
| 6 | 端到端 | §5.6 verify | 四机 `Connected all rings` + OOB 0 |
| 7 | 引擎面 | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<PORT>/health`（ssh 到 `<H1>` 上打回环） | 起栈后 200；重启后**常为 000，须人工拉**（见 8.2） |
| 8 | 锁与自启 | `crontab -l | grep reboot`；`docker ps --format '{{.Names}}' | grep -c <容器前缀>` | 无 `@reboot` 自启在你的点火窗口内抢锁 |

### 8.1 mesh 单元失败无重试 → 对向静默失效

mesh 引导单元**没有配置自动重试**：一次失败就是失败，后果是**对向 2 跳静默失效**
（守卫只记 WARN 不修）。所以上表第 1~2 项是每次开机最优先的两条——直连流量一切
正常、只有对向不通的病，九成在这里。

### 8.2 引擎自启单元常为空

作者的部署形里引擎自启**常为空位**（重启后 API 直接 000），须人工点火。同理，
点火前先查 `@reboot` 自启（第 8 项）——手动流程与开机自启抢同一把靴槽的时序
不可控；看到「靴槽锁被占」先查是不是别人（含自启）点过火，别急着排查自己的改动。

### 8.3 开机竞态：先量化再说话

已知竞态根因（第三方脚本面，不要自作主张改硬件或显存）：hairpin 的
`devlink driver_reinit` 每口停 ~4s、trust 切换再抖一次之后，**网络规则脚本没等
IPv4 恢复就加路由**，而它的第一道检查只等 `operstate=up`（物理链路 ≠ IP 就绪），
`set -euo pipefail` 使单元非零退出判失败。判它多罕见再决定动作：

```bash
journalctl -u <mesh单元> | grep -c 'mesh-up OK'    # 成功次数
journalctl -u <mesh单元> | grep -c Nexthop         # 竞态失败次数
```

作者车队的量级是全环 46:1（量级示意）——即**绝大多数开机是好的**。处理就是
事后手动重拉一把单元；真要做根治（等端口 IPv4 就绪的覆盖单元/重启策略）必须先
请示，这是启动链纪律。

### 8.4 断电/硬重启的附加项

整机断电后除上表外，按
[FABRIC-GID-REPAIR-RUNBOOK.md](../tools/packages/fabric-net/payload/runbook/FABRIC-GID-REPAIR-RUNBOOK.md)
§5 清单补查：GID 洞（§5.5，断电后高发）、isolcpus 内核参数（`/proc/cmdline`）、
16 口 MTU 9000、NCCL 库 md5 对表；另见 §9.5 的 PD 时钟楔死检查。

---

## 9. 物理面排障

物理层的总纪律先立住：**配置偏差改一个键就回去了，物理改动不可逆——永远先查
配置，后动硬件。** 按 §0.4 的分层法，确认问题确实落在物理层（织网/路由/GID/映射
表面全绿）之后，才进本节。

### 9.1 线材劣化：判据是 Δ 速率，不是累计值

`ethtool -S <口>` 里的 `rx_corrected_bits_phy` 是**累计计数器**，直接比大小没有
意义；判据用**两次采样相减的速率**（60~120s 窗口，用 awk 算，别心算）：

```bash
d=enp1s0f0np0   # 逐口轮换
t0=$(ethtool -S "$d" | awk -F: '/rx_corrected_bits_phy/{gsub(/ /,"",$2);print $2}')
sleep 60
t1=$(ethtool -S "$d" | awk -F: '/rx_corrected_bits_phy/{gsub(/ /,"",$2);print $2}')
echo "$t1 $t0" | awk '{printf "%.1f/分\n", $1-$2}'
```

判读（量级示意，各站自建基线）：健康本底 ≈ 0~1/分；**>100/分就要查**。守卫
F-G7 的 5 分钟窗阈值 600（≈2/s 为病理水位）是作者站校准值，可作参照。注意
**一段链路两端都会报**——定位时同段两头一起读。

### 9.2 一头爆、自环与对调实验

- **只有一头爆**：可能只是自环（活环里 a↔b 互指，同段两端读数天差地别时先怀疑
  插错了口形成了环上短路）；
- **判死用对调实验**：**关机态**下，把整跳两根线**整根换位、不换口**——重启后
  错误跟着线走 = 线的锅；错误留在原口 = 口/卡的锅；
- **一切插拔/对调都必须关机做**：热插拔会让链路降到 25000Mb/s 档，必须重启才能
  恢复——热插拔后看到的「降速」不是故障证据，是操作污染。

### 9.3 重启污染历史读数

一次整机重启就贡献十几条 up/down 抖动，全被算成「翻转」；多次多台同时重启会把
翻转计数与 FEC 历史读数全部污染。判法：把事件按时间排出来，与 `uptime -s` /
`last -x reboot` 对轴——**事件全落在重启窗口内 = 计数噪声，不是线在抖**。重启后
重取基线，别拿重启前的告警当现在的问题。

### 9.4 读数工具的两个坑

- `ethtool -m <口>` 普通用户读不到模块 DOM 信息——**读不到 ≠ 没坏**，改用 9.1
  的 FEC 速率判；
- `ethtool -g` 打**两段**（Max/Current），取第一段会把最大档当当前档；凡探针
  脚本，先断言一个已知真值再采信其余读数；
- carrier 假活跃（口 state=ACTIVE 而实际每几秒抖 0）不能靠单次读 state，用
  `bin/fabric-net doctor` 的 carrier 采样（3 发任一 0 即红面）。

### 9.5 两个非线材的物理层病（收尾备忘）

- **TX 塌到 ~14Gb/s 量级**：多因 pkill 停 mesh 残留流表（§2.4 纪律的后果面），
  处置=走 unit 正典停 mesh，必要时 `modprobe -r mlx5_core` 重载驱动；
- **GB10 PD 安全模式时钟楔死**（断电/OOM 后，SM 钉 513-728MHz 家族、96% util
  但功耗仅 10-20W、warm reboot 无效）：唯一有效修法=关机、**拔墙上 AC 插座**
  1-2 分钟、回插开机；`fwupdmgr` 固件更新号称根治但对 CX-7 网络有引入回归的
  报告——**对环网 fabric 是高危项，升级必须专窗+fabric 全档重测，勿顺手升**
  （详见 GID-REPAIR-RUNBOOK §7）。

---

## 附：与既有档的接线图

| 你要做的事 | 去读 |
|---|---|
| 交换机形（0.3.2 现役）从零部署 | [DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) |
| 判断某件 0.3.2 物能不能带到环网 | [RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md) |
| serve 参谱与 env 配对律 | [../deploy/SPEC6-SERVE-REF.md](../deploy/SPEC6-SERVE-REF.md) |
| 0.3.1→0.3.2 升级/回退 | [../UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) |
| 织网硬件转发层全套件 | [luxingcom/aicad-nccl-optimization](https://github.com/luxingcom/aicad-nccl-optimization)（本仓 [README §四](../README.md) 点名） |
| 环网工具包自检/清单 | [../tools/packages/fabric-net/README.md](../tools/packages/fabric-net/README.md) |
| GID 修复正典序 | [../tools/packages/fabric-net/payload/runbook/FABRIC-GID-REPAIR-RUNBOOK.md](../tools/packages/fabric-net/payload/runbook/FABRIC-GID-REPAIR-RUNBOOK.md) |
| 社区四症状鉴别 | [../tools/packages/fabric-net/payload/runbook/COMMUNITY-FIELDNOTES.md](../tools/packages/fabric-net/payload/runbook/COMMUNITY-FIELDNOTES.md) |

——RING-DEPLOY / 2026-10-28 案头成文（零集群零 boot 零流量；全部判据与命令取自
本仓公开件与外部环网踩坑手册的实测条目，占位符纪律=零真实内网地址/主机名/家目录）。
