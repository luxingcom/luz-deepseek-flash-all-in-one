# 交换机方案适配（`switch-fabric` 分支差异档；0.3.2 终态）

> **0.3.2 现役拓扑=双 rail 以太交换机**（每机 2 口 HCA 部署对、flat/one-shot
> RoCE、`B12X_ROCE_TOPOLOGY=switched`/`LUZ_SWITCH_ROCE_FLAT=1`/TC106）。
> 0.3.2 的 switched 运行时与 CBX1A env 已并入 `main` 的 reconstruct 包与顶层
> `deploy/env/CBX1A-CERTM-spec1.env`；本分支在其上保留**交换机差异总表 +
> WG53 53 键历史样本 + 顶层 switch 运行时件**，作为交换机线的完整参考面。
>
> 不再使用“main=环网、本分支=交换机”的二分：0.3.2 main 已是 switched 形；
> 4 口 CX-7 hairpin 环网是 0.3.1 及更早历史形，两形不可混拼。
> 分支基线=`main` 0.3.2 发布面（`8e51a2f`）；本分支差异=4 个文件（见 §三）。

## 一、0.3.2 交换机形对表（环网历史 → 交换机现役）

| 面 | 0.3.1 环网历史形 | 0.3.2 交换机现役形 |
|---|---|---|
| 物理拓扑 | 4 口 CX-7 无交换机 hairpin 环网 | 双 rail 以太交换机；每机 2 口部署对 `rocep1s0f0,roceP2p1s0f1` |
| RoCE AR 运行时 | `b12x.comm.roce_ring`（4 设备空间+对位 rank 物理 2 跳+flow-label 16383 技巧） | `b12x.comm.roce` flat/one-shot（每对 peer 恒 1 跳；无环网假设） |
| 运行时选门 | 依 `DSV41_ROCE_RING` 二选一 | `LUZ_SWITCH_ROCE_FLAT=1` 最高优先门（`roce_ar.py:_roce_module_name()`） |
| C 层拓扑语义 | ring：物理 2 跳假设 + flow-label 技巧 | `B12X_ROCE_TOPOLOGY=switched`：关 2 跳假设/关 flow-label（fail-closed：仅认 `ring`/`switched`，非法值拒起） |
| 流量标记 | 由 NCCL 面标记 | `B12X_ROCE_TRAFFIC_CLASS=106`→DSCP26→受保护档 SP3/TC3/PFC prio3（与 `NCCL_IB_TC=106` 同档对称载流；**我方证成值，勿照抄他站 96**） |
| 两波阈值 | `B12X_ROCE_TWO_WAVE_THRESHOLD_BYTES` 参与 ring 双波复用 | `=0` 显式关闭（flat 支无读点=自文档化） |
| HCA 口对 | 4 口裸列 | 2 口部署对（跨 PCIe 域各取一；**禁拷贝旧 4 口形**） |
| AR/AG 尺寸 | 524288 档 | `SGLANG_ROCE_MAX_SIZE=1179648`；`DSV41_ROCE_GATHER=1179648`（E16B1/B2 包络） |
| NCCL 面 | 环网补丁链 | 补丁链退役；仅 `NCCL_IB_HCA` 部署对 + `NCCL_IB_TC=106`（`NCCL_IB_TOS`/`PEER_HCA` 退役） |
| env | 51 键 `PROD-R51W5FL6`（2ac74586） | **CBX1A 56 键**（`deploy/env/CBX1A-CERTM-spec1.env`，**0729e18d**） |
| adapter | `55b1e412` 形 | **`b58e49ff`**（A6 `beb131ab`/R1 `75062432`/E16B2 `7d6f79b0`/W-E `f61e0183`） |
| IMAGE | `0.3.1-r3` | **`0.3.2-r032c`**（digest `47f6d91a…e2ffc4`，71 层） |

## 二、env：WG53（0.3.1 交换机样本）→ CBX1A（0.3.2 终态）

本分支同时保留两个交换机形态 env：

| 件 | 键数 | md5 | 定位 |
|---|---|---|---|
| `deploy/env/PROD-WG53-spec1.env` | 53 | `1e8e4daa` | 2026-10-15/16 交换机实测窗的验证样本（0.3.1 基座+交换机族 9 键） |
| `deploy/env/CBX1A-CERTM-spec1.env` | 56 | **0729e18d** | 0.3.2 终态现役形（WCBOOT74 复役）；与 main reconstruct 包同名件逐字节相同 |

CBX1A = WG53 + 3 键 + 5 处改值：

```
新增：DSV41_SPLIT_COMPACT_GATHER=1
      DSV41_REPLICATED_SPLIT_WINDOW=0
      SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=0
改值：DSV41_CERT_HEAD_M=6,12,18,24,30,36,42,48
      DSV41_CERT_HEAD_DEBUG=0
      DSV41_CERT_HEAD_LOG_EVERY=0
      SGLANG_ROCE_MAX_SIZE=1179648
      DSV41_ROCE_GATHER=1179648
```

键面自检：

```bash
grep -c '^[A-Z0-9_]*=' deploy/env/CBX1A-CERTM-spec1.env   # 56
md5sum deploy/env/CBX1A-CERTM-spec1.env                    # 0729e18d...
grep -c '^[A-Z0-9_]*=' deploy/env/PROD-WG53-spec1.env      # 53
md5sum deploy/env/PROD-WG53-spec1.env                      # 1e8e4daa...
```

## 三、落地件（本分支相对 main 的 4 个差异）

1. `deploy/adapter/roce_ar.py`（md5 **f61e0183**）——`_roce_module_name()`：
   `LUZ_SWITCH_ROCE_FLAT` 优先返回 flat 模块；安装路径与横幅共用该选门。缺省
   （键未设）行为与 0.3.1 逐字一致。该文件与 main reconstruct 包内
   `adapter/files/roce_ar.py` 逐字节相同。
2. `deploy/b12x/b12x/comm/roce/_roce_proxy.c`（md5 **23646e89**）——结构体 +2 字段
   （`traffic_class`/`switched_fabric`）；`B12X_ROCE_TOPOLOGY` fail-closed 解析；
   `B12X_ROCE_TRAFFIC_CLASS` 缺省回落 `NCCL_IB_TC`、strict 校验、非法值拒起；
   `grh.traffic_class` 透传。两键缺省时与 0.3.1 逐字节同行为（代理编译缓存键随
   源 sha256 变化自动重建）。与 main reconstruct 包内 `b12x/_roce_proxy.c` 相同。
3. `deploy/env/PROD-WG53-spec1.env`——53 键交换机历史样本（键语义注记见文件内）。
4. 本档。

> 引擎参面（SPEC6 九参：`--tool-call-parser deepseekv41`/`--enable-cache-report`/
> `--sleep-on-idle`）、CBX1A env、adapter 终态装配、r032c 16 件与 1017 权重台账
> 均在 main 的 `deploy/reconstruct/0.3.2/` 与 `UPGRADE-0.3.2.md`，本分支不重复。

## 四、实测

### 4.1 交换机适配窗（2026-10-15/16 双 rail 实网）

- **RoCE AR 复归效果**：交换机化后 MoE all-reduce 曾回落 NCCL，DE decode 四型较
  环网锚 −10~−13.7%；本适配（flat 运行时+TC106）收敛至 **−3.8%**；经
  `DSV41_ROCE_GATHER=524288` 恢复 adapter 侧 gather 限幅后四型再 **+5.8~+6.2%**
  （对环网锚 **+1.8~+2.7%**，prose 越 80 收案线）。
- **正确性**：44 项 rank/shape 冒烟（bf16/fp32 共 11 档×4 秩，sum/gather/graph
  逐位相等）44/44×2；262k 长文与 600k needle 全中。
- **TC 生效核**（prio 计数器三窗法）：受控刺激下 `prio3` 每口/向 +62.3GB、
  `prio0` ~2KB ⇒ PFC 保护档载流成立；起靴期 `prio0` 单向大流=权重 NFS 读取
  （逐对吻合），与 RoCE 面无关。
- **prefill/网关面**：PR 六档全带内（±8%）；网关转发开销 ≈0.06~0.25%。

### 4.2 0.3.2 终态读数（CBX1A switch env）

| 面 | 读数 |
|---|---|
| PR 七档（8k→512k） | 5522.5 / 6040.2 / 6271.3 / **6289.3** / 6048.1 / 5427.9 / 4290.0 tok/s；64k 峰档较判读线 6147.3 **+2.3%** |
| DE mt400（c1/c2/c4/c8/c16） | **88.62**（锚 88.64 域）/ 128.89 / 168.35 / 242.83 / 357.9（c16 观察位） |
| GSM8K | 0.985-0.99（门 ≥0.97） |
| needle 600k | 3/3 |
| warm 64k×3 中位 | 产线先例 6181.8（门 ≥5000） |

判读口径与完整表=[0.3.2 release note](../docs/release/0.3.2-RELEASE-NOTE.md)；
升级/复现命令=[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §10。

> 方法学对照：2026-10-15 外部独立交换机移植报告（对比基底固定为本仓 `fb5798c6`，
> 报告公开）——flat/one-shot 路线经我方独立复核后采纳并实测。

## 五、回退（分级）

1. **0.3.2 → 0.3.1 交换机前形**：env `CBX1A→E16B2→E16B1→FB54→WG53`（相邻级单文件
   回指；WG53=53 键 `1e8e4daa`）；复靴。件面同时回 0.3.1 的 `roce_ar.py`
   （932fe12b）/`_roce_proxy.c`（c4393aef），避免新件配旧 env 的混形。
2. **交换机 → 环网历史形**：必须整组回退——0.3.1 的 4 口环网 env + 0.3.1 boot
   （环网补丁链）+ 0.3.1 adapter/overlay；不能只清 `LUZ_SWITCH_ROCE_FLAT` 就把
   2 口 HCA 部署对塞进 4 口环网形（C 层会 fail-closed 或链路缺失）。
3. **键面单退**：清 `LUZ_SWITCH_ROCE_FLAT`/`B12X_ROCE_TOPOLOGY`/
   `B12X_ROCE_TRAFFIC_CLASS` 只回到 C 层缺省语义，不改变物理 2 口部署；仅用于
   定位，不作为生产回退形。
4. **代理缓存**：回退 `_roce_proxy.c` 后删 `~/.cache/b12x/roce/` 或让源 sha256
   变化自然触发重编译。

## 六、分支纪律

- 本分支=main 0.3.2 发布面 + 上述 4 个差异件；远端从 `84b6732` **快进合并**，
  不 force、不重写历史。
- 0.3.2 env/adapter 已公开；本分支不含额外私有资产，无需再走呈裁。
- 交换机实测读数与 0.3.2 判读线分栏陈列；历史环网读数只作对照，不混算。
