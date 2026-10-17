# 交换机方案适配（`switch-fabric` 分支差异档）

> 适用范围：双 rail 以太交换机拓扑（双 rail + PFC prio3 载流面）下的 RoCE
> all-reduce 运行时适配。**分支关系**：`main`=环网方案（CX-7 无交换机 hairpin
> 环网）；本分支=方案差异件叠加（flat/one-shot RoCE 运行时 + C 层 fabric 语义键 +
> 交换机形态 env 样本），其余历史与 `main` 逐字相同。生效判据=2026-10-15/16
> 双 rail 交换机实网实测（§三）。

## 一、方案差异总表（环网 → 交换机）

| 面 | 环网方案（main） | 交换机方案（本分支） |
|---|---|---|
| RoCE AR 运行时 | `b12x.comm.roce_ring`（4 设备空间+对位 rank 物理 2 跳+flow-label 16383 技巧） | `b12x.comm.roce` flat/one-shot runtime（每对 peer 恒 1 跳；无环网假设） |
| 运行时选门 | 依 `DSV41_ROCE_RING` 二选一 | 新增 `LUZ_SWITCH_ROCE_FLAT=1` 最高优先门（`roce_ar.py:_roce_module_name()`） |
| C 层拓扑语义 | ring：物理 2 跳假设 + flow-label 技巧 | `B12X_ROCE_TOPOLOGY=switched`：关 2 跳假设/关 flow-label（fail-closed：仅认 `ring`/`switched`，非法值拒起） |
| 流量标记 | 由 NCCL 面标记 | `B12X_ROCE_TRAFFIC_CLASS=106`→DSCP26→受保护档 SP3/TC3/PFC prio3（与 `NCCL_IB_TC=106` 同档对称载流；**我方证成值，勿照抄他站 96**） |
| 两波阈值 | `B12X_ROCE_TWO_WAVE_THRESHOLD_BYTES` 参与 ring 双波复用 | `=0` 显式关闭（平摊单波语义；flat 支本无读点=自文档化） |
| HCA 口对 | 4 口裸列（环网旧形） | 2 口部署对 `rocep1s0f0,roceP2p1s0f1`（跨 PCIe 域各取一；**禁拷贝旧 4 口形**） |
| AR/AG 尺寸 | — | `SGLANG_ROCE_MAX_SIZE=524288`；`DSV41_ROCE_GATHER=524288`（adapter 侧 gather 限幅恢复） |
| NCCL 面 | 环网补丁链（main 的 boot 脚本含） | 补丁链退役；NCCL 仅 `NCCL_IB_HCA` 部署对+`NCCL_IB_TC=106`（`NCCL_IB_TOS`/`PEER_HCA` 退役） |

## 二、落地件（本分支相对 `main` 的差异）

1. `deploy/adapter/roce_ar.py`（md5 `f61e0183`）——新增 `_roce_module_name()`：
   `LUZ_SWITCH_ROCE_FLAT` 优先返回 flat 模块；安装路径与横幅共用该选门。**缺省
   （键未设）行为与 `main` 逐字一致**（纯增量可选门）。
2. `deploy/b12x/b12x/comm/roce/_roce_proxy.c`（md5 `23646e89`）——结构体 +2 字段
   （`traffic_class`/`switched_fabric`）；`B12X_ROCE_TOPOLOGY` fail-closed 解析
   （`switched` ⇒ 关 2 跳假设+关 flow-label）；`B12X_ROCE_TRAFFIC_CLASS` 缺省回落
   `NCCL_IB_TC`、strict 校验、非法值拒起；`grh.traffic_class` 透传。**两键缺省时
   与 `main` 逐字节同行为**（代理编译缓存键随源 sha256 变化自动重建）。
3. `deploy/env/PROD-WG53-spec1.env`——交换机形态 env 样本（53 键=通用基座键组+
   交换机族 9 键；键语义注记见文件内注释块）。
4. 本档。

> 注：引擎参面（SPEC6 九参：`--tool-call-parser deepseekv41`/`--enable-cache-report`/
> `--sleep-on-idle` 等）与网关件为两方案**通用面**，在 `main` 及其
> `deploy/SPEC6-SERVE-REF.md`/`tools/packages/gateway/` 维护，不在本分支。

## 三、实测（2026-10-15/16 双 rail 交换机实网）

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

> 方法学对照：2026-10-15 外部独立交换机移植报告（对比基底固定为本仓 `fb5798c6`，
> 报告公开）——flat/one-shot 路线经我方独立复核后采纳并实测。

## 四、回退面（分级）

1. **键面（零文件回退）**：清 `LUZ_SWITCH_ROCE_FLAT` ⇒ 按 `DSV41_ROCE_RING`
   走环网选门；清 `B12X_ROCE_TOPOLOGY`/`B12X_ROCE_TRAFFIC_CLASS` ⇒ C 层缺省语义。
2. **件面回退**：`roce_ar.py`/`_roce_proxy.c` 还原 `main` 版本（选门/C 键解析移除；
   代理随源变化自动重编译）。
3. **env 整体回退**：回环网形态 env 样本（`deploy/env/PROD-R51W5-FL6FIX-spec1.env`，
   51 键形；`B12X_ROCE_PEER_HCA_MAPS` per-rank 变通保持弃用）。

---

*本分支=main + 本档/三件套（差异提交两条：运行时支持 + 本档与 env 样本）。*
