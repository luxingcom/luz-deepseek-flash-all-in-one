# fabric-net（P1 环网通讯方案工具包）

> TOOLS31-PACKAGE-PLAN-20261012 §二 P1 承载。整备位=战役仓 `tools/packages/fabric-net/`；
> 烘焙位=`/opt/dsv41/packages/fabric-net/`（**guards/ 族=宿主侧守护件不入镜像**，部署面
> 分发——00-BAKED-BY-0.2.8「它是载荷不是运行时守卫」律：判据全来自宿主 /proc//sys 接口）。
>
> **外部采用者必读（2026-10-30 加）**：
> 1. **兄弟仓取件**：织网全套运行件（拓扑生成器 plan.py/inventory.sh、mesh-up/mesh-down、
>    hairpin.sh、qos.sh、systemd 引导单元对、fabricctl、topology.json 正典生成位）在
>    基础设施仓 **`luxingcom/aicad-nccl-optimization`**（见仓库 README「基础设施仓」段）；
>    本包收编的是织网**判据/守护/诊断**面。`grep` 本仓找不到织网安装件≠缺件。
>    环网从零部署全程见 `docs/RING-DEPLOY.md`。
> 2. **站点适配**：本包 guards/diag 内的期望值（topology.json 的 hosts 键/路由/PFC 期型）
>    与哨兵的运行参数均为**作者站点采样**——hosts 键必须改成你本站真主机名
>    （守卫用 `socket.gethostname()` 取键）；路由字段按 `ip route` 打印形写（主机路由不带
>    `/32`）；fabric-sentinel 需显式设 `SENTINEL_IMAGE/SENTINEL_MASTER_ADDR/SENTINEL_W1-W3`
>    （缺参拒跑；2026-10-30 参数化，此前为作者站硬编码）。适配三步详见
>    `docs/RING-DEPLOY.md` §7。
> 3. 2026-10-30 修复：fabric-sentinel idle 门兼容 `{"loads":[…]}` 包裹形、带外判据改
>    浮点比较（此前 verdict 恒 0 永不告警）；fabric-doctor `--json` 在 _lib 失锚时
>    显式 exit 2（此前静默失能）。

## 为什么存在

四机 RoCE 环网（switchless ring，4 口×4 机 16 口）是产线 TP4 的数据面。环网件的
知识散在 dev/lutune（织网+守护）、~/w6-kit（bench+GID 修复 runbook）、FABRIC-SELFHEAL
设计卡与社区田野笔记四处——本包把「织网/守护/诊断/runbook」收编为一处可 md5 锚定、
可自检、可随镜像交付的工具面。

## 用法

`bin/fabric-net help`（子命令总览）；`bin/fabric-net selfcheck`（离线红绿自检）；
`bin/fabric-net doctor`（只读诊断，`--json` 出 verdict 三字段族）；
`bin/fabric-net run <件名>`（转发部署面件，判读语义零改律）。

## 构成（详 md5+指向=MANIFEST.md5；在役源对表=selfcheck/sources.tsv）

| 类 | 件 | 来源/在役位 |
|---|---|---|
| 织网 weave/ | lutune.sh（RX_TARGET=4096 裁定值；幂等 apply） | dev/lutune/（部署位 /opt/dsv41-mesh/bin/） |
|  | topology.json（canonical 路由+gid3 期望态） | ~/<source-repo>/scripts/ring_mesh/（部署位 /opt/dsv41-mesh/） |
|  | netplan-templates/97-roce-mtu+99-nvidia-sync-cluster（.template；期望态登记非部署件） | 四机 /etc/netplan/ 同名件（root-0600 部署面，部署窗 diff 核） |
| 守护 guards/ | fabric-guard.sh（F-G1..F-G10+Q1-Q7 判据+四路大声+熔断） | dev/lutune/（宿主 systemd 周期件） |
|  | fabric-sentinel.sh（15min 32MB AR 性能哨兵；idle 双确认门） | dev/lutune/ |
|  | fabric-gid-heal.sh（GID idx3 洞环回重铺；四前置 P1-P4+单法单次+熔断） | dev/lutune/ |
|  | fabric-restore-gate.sh（引擎死态五判据→READY-TO-BOOT 广播；Phase1 只告警） | dev/lutune/ |
| 诊断 diag/ | s4_bench.sh（NCCL allreduce verify：四机 Connected all rings+OOB 0；GID 预检 exit 9 fail-closed） | ~/w6-kit/（链路量具，TOOL-ANCHORS 在锚） |
|  | fabric-doctor.sh（本包新件：HCA ACTIVE/接口在位/carrier 采样——症状2 鉴别承载） | TOOLS31 §二 P1-3 |
| runbook/ | FABRIC-GID-REPAIR-RUNBOOK.md（蓝本 md5 cc84ba86 收编） | ~/w6-kit/（TOOL-ANCHORS 在锚） |
|  | COMMUNITY-FIELDNOTES.md（社区四症状**摘译+出处**；GID 3→4 漂移/carrier 假活跃/TX 塌 14Gb/s/NFS 软挂载+补丁 NCCL Route A/B） | COMMUNITY-DELTA-20261012 §2.4（knapcio 仓 docs/switchless-ring.md:503-527 摘译律） |

## 排除了什么（装了什么/没装什么同样重要）

- **宿主 systemd unit 面不收编**（dsv41-mesh.service 等）：guards 族的在役形态=宿主侧
  周期件，容器内无判据；烘焙镜像不带、不自启（部署面四机分发）。
- **netplan 部署原件不收编**：root-0600 面，包内只登记期望态模板；部署窗原件 diff 核。
- **社区笔记不逐字收编**：摘译+出处链接口径（任务卡 §七.6 默认；逐字收编=呈裁面）。
- **密钥/口令零携带**（daily_smoke SMOK_KEY 前科律）。
- **无任何自动动作新面**：doctor=只读；heal=唯一 auto_ok（既有设计，FABRIC-SELFHEAL
  §二）；restore-gate=Phase1 只告警档。

## 红线注记

1. **判读线零改**：NCCL_IB_GID_INDEX=3 不动（集群一致性律）；ring 4096 档为现役裁定值。
2. **白名单硬界**：只碰 DEVLIST 四口；enP7s7 管理口与 01 机 macgw /30 副地址
   （<mgmt-node-ip>）永不在任何动作面。
3. **熔断+人工复位律**：heal 1h 内 ≥2 次=熔断停手（state/heal-fuse.reset 人工复位）；
   双法皆败=停手 CRIT 不盲目重试。
4. **判读语义零改律**：本包收编=复制+包装，不改各件判读逻辑；md5 漂移=selfcheck 红
   （同日更新律：改源→同日再吸收→MANIFEST/VERSION/TOOL-ANCHORS 三联动）。
5. **02 机双守护零触碰**（本包动作面与 02 机 3535/3536 两守护无交叠；绝对不动律见
   selfheal 包 README）。

——TOOLS31 T4 P1 / 2026-10-13 案头整备（零集群零 boot 零流量）。
