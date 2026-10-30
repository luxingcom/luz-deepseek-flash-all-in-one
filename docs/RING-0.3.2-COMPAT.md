# 0.3.2 修复在环网形（4 口 CX-7 hairpin）上的可用边界

> 0.3.2 的现役证据全部来自**双 rail 交换机 2 口 flat 形**。本文回答一个具体问题：
> 环网形采用者能拿走哪些 0.3.2 修复/优化，哪些会把拓扑混拼。
>
> 本文是**边界说明**，不是环网形 0.3.2 的验收报告。环网读数必须在环网形上
> 自行复测；不得把交换机形读数当作环网预期。

## 1. 两形速查

| 项 | 0.3.1 环网形（历史/在役回退面） | 0.3.2 交换机形（现役） |
|---|---|---|
| 物理拓扑 | 4 口 CX-7 hairpin 环（两卡 f0/f1 全用） | 双 rail 交换机，2 HCA 口 |
| HCA | `rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1` | `rocep1s0f0,roceP2p1s0f1` |
| 路由 | 逐秩 `B12X_ROCE_PEER_HCA_MAPS` + ring-only NCCL | C 层 flat/one-shot + `B12X_ROCE_TOPOLOGY=switched` |
| 关键 env | `DSV41_ROCE_RING=1`；无交换机三键 | `LUZ_SWITCH_ROCE_FLAT=1`、`B12X_ROCE_TOPOLOGY=switched`、`B12X_ROCE_TRAFFIC_CLASS=106` |
| 流量类 | ring-only 库/NCCL 面 | `NCCL_IB_TC=106`；`grh.traffic_class=106` |
| 参考 env | `deploy/env/PROD-R51W5-FL6FIX-spec1.env`（51 键 `2ac74586`） | `deploy/env/CBX1A-CERTM-spec1.env`（56 键 `0729e18d`） |
| 参考 boot | `v0.3.1` 标签的 `deploy/bin/r3-boot-arm.sh`（4 HCA + PEER_HCA） | `main` 的 `deploy/bin/r3-boot-arm.sh`（2 HCA + TC106） |

**不可混拼**：把 `LUZ_SWITCH_ROCE_FLAT=1` / `B12X_ROCE_TOPOLOGY=switched` 带进环网，
或把 `B12X_ROCE_PEER_HCA_MAPS` 带进交换机形，都会在 C 层/NCCL 面 fail-closed 或
静默走错口对。两形只能整套切换。

> **PEER_HCA_MAPS 是属主映射表**：参考 env 里的该键值编码的是**作者站点的物理接线**
> （哪个节点的哪个口连哪两个对端）。外部采用者**必须按本站 rank×口实测重生成**，
> 照抄必挂（报错会点名具体 rank 的 `ibv_modify_qp(RTR): Connection timed out`）。
> 实测方法与四条硬约束见 `docs/RING-DEPLOY.md` §4。

## 2. 环网可以直接用的 0.3.2 件

### 2.1 质量与量具（无拓扑依赖，立即用）

回补到 main 的公开件：

| 件 | 用途 |
|---|---|
| `tools/bench/qeval.py` + `qeval_tasks.py` | 75 题质量门；`--selftest` 20/20（EQ-11 后） |
| `tools/bench/gsm8k_dsv41.py` | GSM8K 8-shot CoT；`--nq 500` 复现发布读数 |
| `tools/needle_probe.py` | 600k needle；输出新增 `water_m` 有效水位线 |
| `tools/bench/README.md` | PR/DE/质量门的完整命令与口径 |

这些件只走 OpenAI 兼容接口，环网/交换机通用。跨形态仍不可互比绝对值。

### 2.2 adapter 修复（拓扑无关，但要与引擎同批）

以下 0.3.2 adapter 件不依赖 fabric，可在环网形使用：

| 件 | 0.3.2 终态 | 说明 |
|---|---|---|
| `sitecustomize.py` | `beb131ab` | A6 indexk page 遮蔽 + SM12x dense planner |
| `kv_fp4.py` | `75062432` | R1 fork 正式化（持久缓冲 + `r1_formal=1`） |
| `replicated_split.py` | `7d6f79b0` | E16B2 不等长 last-dim gather；两条 env 缺省=旧行为（`COMPACT=0`），显式开窗才变 |
| r032c 迁移 9 件 | 见 `0.3.2-MANIFEST.md5` | `seam_mount.py`/`sparse_wire.py` 等必须与 r032c 引擎同批 |

**绑定律**：`seam_mount.py`/`sparse_wire.py` 与 r032c 引擎件同批切换；旧 adapter
覆盖新引擎会静默回退上游修复。反过来，只换 adapter 不换 r032c 引擎也不成立。

### 2.3 env 面可取的拓扑无关键

以 51 键环网 env 为底，可逐项加入并复靴验证：

| 键 | 值 | 作用 | 风险 |
|---|---|---|---|
| `SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION` | `0` | 关 30s 真实生成探针，避免探测占住内存 | 低；健康面语义变化 |
| `DSV41_CERT_HEAD_M` | `6,12,18,24,30,36,42,48` | CERT 八元 gate | 低；需 lm_cert 对应版本 |
| `DSV41_CERT_HEAD_DEBUG` / `_LOG_EVERY` | `0` / `0` | 关调试日志 | 低 |
| `SGLANG_ROCE_MAX_SIZE` / `DSV41_ROCE_GATHER` | `1179648` | E16B1 聚合上限翻倍 | 中；环网 4 口需 A/B |
| `DSV41_SPLIT_COMPACT_GATHER` / `DSV41_REPLICATED_SPLIT_WINDOW` | `1` / `0` | E16B2 split 优化 | 中；需 A/B |

不要从 `CBX1A` 整文件复制到环网：它含 3 个交换机键并删除了
`B12X_ROCE_PEER_HCA_MAPS`。环网要么保留 51 键原文件，要么按键表手工增量。

## 3. 仅属于交换机形、不要带到环网的件

| 件/键 | 原因 |
|---|---|
| `LUZ_SWITCH_ROCE_FLAT=1` | 选 `b12x.comm.roce` flat 运行时；环网走 `roce_ring` |
| `B12X_ROCE_TOPOLOGY=switched` | C 层关闭 2 跳假设/flow-label 技巧，只对交换机成立 |
| `B12X_ROCE_TRAFFIC_CLASS=106` | 对应交换机 PFC/DSCP 规划；环网无此规划 |
| `deploy/b12x/.../roce/roce_oneshot.py`、`_allgather_cute.py` | flat/one-shot 运行时；环网用 `roce_ring/` 同族件 |
| `deploy/adapter/roce_ar.py` 的 W-E 选择门 | 默认回落 `roce_ring`，对环网无害但无收益；环网不必追这个 md5 |
| `deploy/reconstruct/0.3.2/b12x/_roce_proxy.c` | 改的是 `roce/` 的 C 代理；`roce_ring/_roce_proxy.c` 是另一份 |
| 0.3.2 boot 的 2 HCA/TC106 面 | 环网需要 4 HCA + 逐秩 PEER_HCA |

## 4. r032c 引擎上环网：还差一个 boot profile

这是当前公开面的**已知缺口**，必须说清楚：

- `v0.3.1` 的 ring boot 把 `IMAGE` 写死为基座
  `<registry-host>:5000/lmsysorg/sglang:main-79cafec0`，并校验 golden 表的
  `MANIFEST.image` 与之相等（`r3-boot-arm.sh:12`、`:178`）。
- `main` 的 0.3.2 boot 把 `IMAGE` 写死为 `0.3.2-r032c`，网络面是双 rail 2 口
  （`:20`、`:305` 附近）。
- 因此“环网 + r032c”需要在测试窗做一次 boot profile 合成：
  1. 以 0.3.2 boot 的 IMAGE/adapter/overlay/b12x 落位和 D15 五门为骨架；
  2. 把 NCCL 面恢复成 4 HCA + 逐秩 `NCCL_IB_PEER_HCA` + ring-only 库；
  3. 重新捕获或改写 golden 表的 image 身份，使 `MANIFEST.image` 与 r032c 一致；
  4. 用 ring 51 键 env 起栈，跑本文 §5 的门。
- 该 profile **未随本仓发布、未在环网硬件上验收**；不要把它当成现成升级包。
  没有测试窗时，环网保持在 0.3.1 形，只取 §2.1/§2.3 的低风险件。

## 5. 环网形验收门（合成 profile 后）

1. 起栈前：四机 `docker inspect` HCA 列表=4 口；容器 env 无交换机三键；
   `NCCL_IB_PEER_HCA` 逐秩在位；ring-only 库/pin 件 md5 对表。
2. 起栈后：`/health` 200；banner 的 backend 面是 ring（不是 flat）；
   `DSV41_ROCE_RING=1`；R1 `r1_formal=1`；A6 page 横幅。
3. 连通性：ring 邻接 allreduce 全通；无 `ibv_modify_qp` 超时。
4. 性能：先跑同形 0.3.1 基线，再跑 r032c；PR 七档/DE mt400 同口径对照。
   **不要拿交换机 0.3.2 的 5522.5/…/88.62 当环网预期。**
5. 质量：GSM8K `--nq 500` ≥0.97；qeval 与基线 compare；needle 600k 3/3。

## 6. 已知负判（环网）

- **`channelId % 4` 四口轮转（v5-quad）不可用**：4 口 hairpin 的物理布线不是
  全互联，逐跳任意口对会落到不存在的直连对，`ibv_modify_qp` 超时。ring-only 的
  v4 配对表是对实际布线的编码，默认不要开 quad；除非先重布线并重做端到端验收。
  公开的 ring-only 补丁栈与部署资料在
  [`luxingcom/aicad-nccl-optimization`](https://github.com/luxingcom/aicad-nccl-optimization)。
- 本仓 `deploy/nccl/nccl-ringonly/libnccl.so.2.30.7`（`2be94172`）是 v4 配对构建，
  不带 quad 门；不要用未经验证的源码改造替换在役库。

## 7. 回退

1. 停栈，恢复 0.3.1 adapter 整面（`deploy/adapter/`）与 ring env 51 键；
2. IMAGE 回 0.3.1 基座；golden 表回原 image 身份；
3. 移除新增的 `B12X_ROCE_TOPOLOGY` 等非 51 键键；
4. 复靴后按 §5 的 1-3 门复核，再开性能窗。

相关档：[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)、
[deploy/reconstruct/0.3.2/ENV-CHAIN.md](../deploy/reconstruct/0.3.2/env/ENV-CHAIN.md)、
[switch-fabric 差异档](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/blob/switch-fabric/deploy/SWITCH-FABRIC.md)、
[tools/bench/README.md](../tools/bench/README.md)。
