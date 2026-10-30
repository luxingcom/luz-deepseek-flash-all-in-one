# DeepSeek-V4.1-Flash × 4×DGX Spark（GB10）TP4 端到端优化战役（LuZ 0.3.x）

> **一句话**：本仓是一场把 **DeepSeek-V4.1-Flash 跑在 4×NVIDIA DGX Spark（GB10，TP4）内部集群**上的端到端推理优化战役——从 0.3.2 基线代到 0.3.4 调优终态，全程用**单变量 A/B、冻结量具、冻结阈值、判例制式**产出四代可对表的性能档案。
> **现在拿到的是什么**：公开仓现役发布面=**0.3.4re**（2026-10-30 移植+加固批：战役仓 0.3.4 面脱敏移植入公开树 + DF/EQ 缺陷修复族 + 上游缺陷 host 侧规避族；终态判读门全绿零劣化，KV/SWA fp8 精度判词成立，并交付一键化部署/守卫/验收/自诊断工具链与双路回退正典）。
> **从哪入门**：第一次接触先读 [GETTING-STARTED](docs/GETTING-STARTED.md)，术语随查 [GLOSSARY-PUBLIC](docs/GLOSSARY-PUBLIC.md)；指标与代际细节见本文 §3（表前有「读表先识字」图例）。

- **引擎基座**：SGLang（上游 main `79cafece` 镜像线）+ flashinfer 0.7.2；模型=DeepSeek-V4.1-Flash 官方权重（技术报告为参数对账规范基准）。许可注记见 [NOTICE](NOTICE) / [LICENSE](LICENSE)。
- **硬件**：内部集群 4×DGX Spark GB10（统一内存架构 UMA），TP4 · 每机 1 容器 · host 网络；镜像 `0.3.4-x6bake-20261026`（RepoDigest `sha256:80e4c957…8f7d0`，内部 registry 多级回退在库）。
- **当前生产终态**：**0.3.4 调优终态** = 修复固化面（x6bake + v41 三联 + BYPASS）+ DEOPT-I8 采纳面（engram 缓存 1.0→2.0 GiB，61 键产 env，四机同步，md5 `4370aab9…`）；引擎在役 ARM_TAG=`WD-034TUNED-20261029-151019`。

## 读者分流表（按你要做的事选入口；部署面按三代分流）

| 你要做什么 | 主读 | 配套 |
|---|---|---|
| 第一次接触本仓 | [GETTING-STARTED](docs/GETTING-STARTED.md) | [GLOSSARY-PUBLIC](docs/GLOSSARY-PUBLIC.md) |
| **从零部署（0.3.4re 现役形）**：镜像 x6bake+61 键 env+v41 三联+BYPASS | [docs/runbook/runbook-034.md](docs/runbook/runbook-034.md)（三命令快速上手） | [UPGRADE-0.3.4](UPGRADE-0.3.4.md)（目标形态速查表）+ `tools/` 工具六件套 |
| 从零部署（**0.3.2 交换机 flat 形**=历史定版形） | [DEPLOY-STEP-BY-STEP](docs/DEPLOY-STEP-BY-STEP.md)（主路径） | [RUNTIME-PARAMETERS](docs/RUNTIME-PARAMETERS.md)（逐键词典） |
| 从零部署（**0.3.1 环网 hairpin 形**=最早期历史形/对照面） | [RING-DEPLOY](docs/RING-DEPLOY.md) | [RING-0.3.2-COMPAT](docs/RING-0.3.2-COMPAT.md)（两形边界） |
| 从 0.3.1 升级到 0.3.2 | [UPGRADE-0.3.2](UPGRADE-0.3.2.md) | [DEPLOY-STEP-BY-STEP](docs/DEPLOY-STEP-BY-STEP.md) |
| 从 0.3.3/0.3.2 升级到 0.3.4（0.3.4re 面） | [UPGRADE-0.3.4](UPGRADE-0.3.4.md) | [docs/runbook/runbook-034.md](docs/runbook/runbook-034.md) |
| 量测/对表/判读 | [CALIBER-AND-MEASUREMENT](docs/CALIBER-AND-MEASUREMENT.md) | [tools/bench/README](tools/bench/README.md)（量具口径） |
| 排障/查坑（按现象查） | [PITFALLS-AND-FAQ](docs/PITFALLS-AND-FAQ.md)（86 条，现象→根因→判据→处置） | [KNOWN-ISSUES](docs/KNOWN-ISSUES.md)（已知问题+采用方常见误判澄清） |
| 查某个 env 键 / serve 参数 | [RUNTIME-PARAMETERS](docs/RUNTIME-PARAMETERS.md)（0.3.4 面 61 键+serve 八参全解；0.3.2 56 键为代际底稿） | [deploy/env/](deploy/env/) |
| 0.3.4 部署/验收/自诊断 | [docs/runbook/runbook-034.md](docs/runbook/runbook-034.md)（三命令快速上手） | [tools/](tools/) 工具六件套 |

> **当前断点声明（0.3.4re 面从零部署链，如实）**：runbook-034 面向**内部已固化集群**的运维/恢复手册——其 §六「env/tp4/guards/profile 四面零动作」只对内部已固化存储态成立，其 boot 翻 `:12` 后 md5=`d41323dd` 锚也只对内部基底（`20f22bc6`）成立；公开件基底（`9ac6e113`）翻 `:12` 后 md5 **必不等于**该锚，属预期，**勿据此误判自己改错**。[UPGRADE-0.3.4](UPGRADE-0.3.4.md) 与 [0.3.4-RELEASE-NOTE](docs/release/0.3.4-RELEASE-NOTE.md) 两件为移植**骨架**（各节 `TODO(写手)` 待后续窗充实，但其 §0「目标形态速查表」现即可用）。**当前已可用的 0.3.4re 增量=三处**：[DEPLOY-STEP-BY-STEP](docs/DEPLOY-STEP-BY-STEP.md) §5（61 键 env 落位与自检）、§6.6（deploy/verify/doctor/selftest 工具四件套）、§4.5（网关部署在管理机）；v41 三联的 tp4/guards 落位、prod-profile 钉面与镜像替换的逐步操作待 UPGRADE-0.3.4 充实。**overlay 29 件本体尚未入公开树**（锚件 map+md5 清单已入）：按新清单 `md5sum -c` 必红属已知缺口而非数据漂移；本体落地前**禁止**拿 0.3.2 overlay 增量件（`deploy/reconstruct/0.3.2/overlay/`）拼装 0.3.4 形栈（绑定律/混形禁忌），请等待整面同步窗。0.3.4re 形镜像取处=网盘包 `images/`（见包内 README-DIST）。

## 先认代际，再抄配置（部署三代声明）

本仓同时保留**三代部署档案**，同一键三代取值可能不同，同一篇里新旧读数并存。**对表、抄 env、看旧报告之前，先确认它在哪一代、哪种网络形态上成立**（判别法见 [PITFALLS-AND-FAQ](docs/PITFALLS-AND-FAQ.md) 卷首一）。三代整套互斥、不可混拼：

| 部署代 | 网络形态 | 现役位 | 镜像 | env 面 |
|---|---|---|---|---|
| **0.3.4re**（现役发布面） | 交换机 flat 形（承 0.3.2 网络面） | **现役**（runbook-034+工具六件套承载） | `0.3.4-x6bake-20261026` | 61 键 `4370aab9…`（内部正典锚；本仓为脱敏拷贝） |
| **0.3.2**（前代定版） | 交换机 flat 形 | 历史定版（tag `v0.3.2` 在案） | `0.3.2-r032c` | CBX1A 56 键 `0729e18d` |
| **0.3.1**（更早期定版） | 环网 hairpin 形 | 历史形/对照面（tag `v0.3.1` 在案） | `0.3.1-r3` | 51 键（FL6 转正形） |

> **织网件不在本仓，不是缺件**：环网形态所需的 mesh 硬件转发层全套件唯一取处=基础设施仓（详见 [RING-DEPLOY](docs/RING-DEPLOY.md) §2 与 [RING-0.3.2-COMPAT](docs/RING-0.3.2-COMPAT.md)）。在本仓 grep 不到属正常，不要据此判「交付缺件」。
>
> **读数代际另有细分**：本页 §3 性能总表在同一部署面内再分四个**读数代际**（0.3.2 基线 / 0.3.3 正典 / 0.3.4 修复固化 / 0.3.4 调优终态），代际间以「读数同构前提」对齐（见 §3 头注）；部署代与读数代是两个维度，勿混用。

## 版本系列

| 版本 | 定版 | 主线 | 档 |
|---|---|---|---|
| **0.3.0** | 2026-10-05 | R1 检查点封存：36 键 env `b7e318e0`+sitecustomize 七件 `91adc83d`+池 9.6M 基线 | [CHANGELOG](CHANGELOG.md) |
| **0.3.1** | 2026-10-13 定型 / 10-14 发布 | FL6 召回修复转正（51 键）+VL 双臂+网关链；交付镜像 `0.3.1-r3`（环网形） | tag [`v0.3.1`](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/releases/tag/v0.3.1) · [CHANGELOG](CHANGELOG.md) |
| **0.3.2** | 2026-10-20 | 净线重建→死锁修复（`520d6d0`+r032c 位级保持形）→五目标执行链→收官转正；交换机 flat 形；池 84 件三态处置 | tag `v0.3.2` · [0.3.2-RELEASE-NOTE](docs/release/0.3.2-RELEASE-NOTE.md) · [重建包](deploy/reconstruct/0.3.2/README.md) · [升级指南](UPGRADE-0.3.2.md) |
| **0.3.3** | 2026-10-26 锁定（检查点名 r033d+split） | **正典代**：r032c 基底+A1/A7 适配+flashinfer 0.7.2 安装树+N-pad 修复三件 image-face=镜像 `0.3.3-r033d`（73 层；registry 检查点 tag `0.3.3-final-20261026`，RepoDigest `sha256:9e34bd29…719d7`）；58 键 K16-on env；立 T33-03 正典锚（PR 五档/DE c1/c8），后续一切 IN-BAND 判读对它展开 | [034-PERF-REPORT](docs/report/034-PERF-REPORT-20261029.md) 0.3.3 对照列 · [034-VERSION-LOCK](docs/release/034-VERSION-LOCK-20261028.md) 回退级（公开仓暂无独立发布说明与 tag） |
| **0.3.4** | 2026-10-29 定版（调优终态） | **修复固化代+调优终态**：镜像 `0.3.4-x6bake-20261026`（74 层）+v41 三联固化+BYPASS=2048 采用+DEOPT-I8 采纳（engram 1.0→2.0 GiB）=61 键调优 env（md5 `4370aab9…`）；判读门全绿零劣化+PR 全档对正典 IN-BAND+KV/SWA fp8 精度判词成立（无条件） | [034-PERF-REPORT](docs/report/034-PERF-REPORT-20261029.md) · [034-WD-TUNED-FINAL](docs/release/034-WD-TUNED-FINAL-20261029.md) · [034-VERSION-LOCK](docs/release/034-VERSION-LOCK-20261028.md) · [0.3.4-RELEASE-NOTE](docs/release/0.3.4-RELEASE-NOTE.md)（骨架） |
| **0.3.4re** | 2026-10-30（本仓现役发布面） | **公开移植+加固批**：战役仓 0.3.4 面 31 copy+4 new 移植入公开树（内网值一律占位符化，正典 md5 锚指内部原件）；叠加 0.3.4re 缺陷修复单元（DF-02/03/04/05/12+EQ-02/03/04/05/09/11/12/19/20）与上游缺陷 host 侧规避族（UP43050/UP44162/UP45614/UPSTREAM-45119） | **[0.3.4re-RELEASE-NOTE](docs/release/0.3.4re-RELEASE-NOTE.md)** · [CHANGELOG](CHANGELOG.md) 0.3.4re 各节 |

> 键数口径注记：0.3.4 调优终态 env 键数一律按 gates-034 BL11 判据记 **61 键**（61 行键定义；`DSV41_ENGRAM_CACHE_GIB` 同键双行、尾行生效——:8 旧值 1.0 与 :64 尾行 2 并存，尾行胜）。个别内部台账以「62 键」记此面，与本仓锁档口径不一，**以 BL11=61 为准**。（编号体系注：**BL 系号=`tools/gates-034.tsv` 基线门行标识、CFG 系号=`tools/config-034.tsv` 期望参数行标识**，本仓多处引用；**D 系号（D8/D113/D121 等）=内部决策台账编号，台账未入公开树，语义随文给出**。）

## 1. 架构与关键面（文字简图）

```
                    ┌────────────── 内部网关节点（Mac 独立宿主） ──────────────┐
  客户端流量 ──────▶   concurrency-proxy-v2（采样策略 on = 一切判读读数基线）     │
                    └───────────────────────┬─────────────────────────────────┘
                                            │ 转发至引擎 OpenAI 兼容 API（环回端口）
        ══════════════ 五面配置（点火面，四机逐字节一致）══════════════
        产线 env CBX1A-CERTM-spec1.env（61 键·md5 4370aab9…：尾行 v41 固化
          + PREFILL_BYPASS=2048 + ENGRAM_CACHE_GIB=2；K16 两键 on）
        boot 链 r3-boot-arm.sh（存储形 r032c 占位 / 点火窗单行翻 x6bake）
        .env.tp4（v41 + prefill TP-split 保全）   guards.conf（envpin 钉 v41）
        prod-profile.env（head 机专属钉面：env/键数/镜像 digest 全值）
                                            │ slotlock 治理（锁下原子校验四机容器净）
   ┌────────────────────────┴─────────────────────────┐
   │   内部集群：4×DGX Spark（GB10）· TP4 · 1 head + 3 worker  │
   │                                                       │
   │   镜像 0.3.4-x6bake（74 层 = 0.3.3 r033d 73 层 + 1 增量层）│
   │   挂载（ro）：adapter 99 件 / overlay 29 件（sglang 补丁面）│
   │   挂载（ro）：DeepSeek-V4.1-Flash 权重 + engram 行缓存分片  │
   │             （NVMe 常驻 + pread 流式加载，缓存 2.0 GiB/层） │
   │   挂载（rw）：autotune 表（唯一读写面）                    │
   │                                                       │
   │   引擎正典态：[kv_fp4] gate=1 mode=v41 active=False      │
   │     → backend 直调 flashinfer 0.7.2 原生 V41 分支         │
   │     → fp4-KV 四 seam 全 passthrough（不经 repack 桥=快带） │
   │   KV 池：full=9,600,000 tokens / ctx 600,000 / fp8_e4m3   │
   │   SWA：bounded_replay on · prefix_tails=256               │
   │   BYPASS：小请求准入 armed 8/8 · refusing 0（首键 TTFT 面）│
   └───────────────────────────────────────────────────────┘
```

**关键面一句话**：
- **adapter 件数口径**：上图「99 件」=0.3.4 在役面（BYPASS 采用后：98 个修复固化运行时件 + 1 个 BYPASS 件 `prefill_bypass.py`，整树签名 `0beb4bee`，正典=[034-VERSION-LOCK](docs/release/034-VERSION-LOCK-20261028.md) §六-1）。runbook-034 §四架构图所记「98 件/`d52b0e3d`」为 2026-10-28 锁档（修复固化面、BYPASS 未入包）时点值——两数同代不同时点，非矛盾。
- **v41 固化**：KV 布局显式注入 v41 → fp4 补丁全 passthrough → flashinfer 原生快路径。若 boot 见 `mode=fork-v4-fp4 active=True` 即**退化面**（慢带 −15~19%，见 §5 降级警告）。
- **BYPASS（2048）**：小请求准入旁路，长 prefill 期间首键 TTFT 74.191s→**1.971s**（97.3% 改善）。
- **engram 行缓存**：NVMe 常驻流式；调优终态缓存 2.0 GiB/层（DE c1 +2.0~+2.4% 增益来源）。
- **量具冻结**：全部读数出自冻结原件（sd_bench `410f543d` / conc_pr_driver `333033ce` / de_c48 `a337f64e` / dcgm `50460f66` 等，调用前逐量具 md5 断言，失配拒跑）。

## 2. 快速上手（四命令）

> 前提：仓根为工作目录；四机 ssh 免密可达；引擎启停属**治理动作**（slotlock 持锁，仅授权运维窗内执行；拆栈走正典停栈件+三查）。

```bash
cd <本仓检出路径>

# ① 体检（只读，零写入零启停，任何时刻可跑；逐参数 PASS/FAIL+处置提示）
bash tools/doctor-034.sh --preflight    # 点火前：五面锚/镜像 digest/盘空间/量具锚全查
bash tools/doctor-034.sh --post-boot    # 点火后：health/kv_fp4 v41/池指纹/横幅/ARMED 面

# ② 一键部署（编排既有正典原件；S1 体检→boot 翻点火形→起栈→静置 300s→核对面→post-boot）
bash tools/deploy-034.sh --dry-run          # 先看清单：动作级逐条打印不执行
bash tools/deploy-034.sh --arm-tag <窗名>    # 实部署（S6 硬门：ARMED=8 ∧ refusing=0）

# ③ 验收电池（纯包装冻结量具，阈值 FROZEN 内置；--list 零触列清单）
bash tools/verify-034.sh --list     # 列电池与冻结阈值，不执行
bash tools/verify-034.sh --smoke    # EQ-S 同盐夹心 + liter C1 + DE c1 + 500q 冻结帧
bash tools/verify-034.sh --full     # --smoke + 512k TTFT + B25×3 + PPL golden A/A

# ④ 交付包自诊断（四段器：A 比较器单元/B 沙箱负例/C 完整性走查/D 降级检测负例）
bash tools/selftest-034.sh          # 期望 exit 0（重定版后实测 A 20/20·B 7/7·D 4/4·C checked=108 fail=0）
```

冻结判读门（内置，改动=停窗呈批）：liter C1 ≥3700 tok/s ∧ DE c1 ≥91 为快带；liter ≤3450 为退化停窗；500q 地板 0.955（带 [0.956, 0.982]）；EQ-S 须 GREEN 6/6；PPL A/A 须 Δtf=0.0000。W-f 终靴实测 **PASS=5 WARN=2 FAIL=0（rc=0）**（两 WARN=记录面）。

## 3. 性能总表（代际对照）

> 全部数值转引自已验收档（出处逐处列明于 [034-PERF-REPORT-20261029](docs/report/034-PERF-REPORT-20261029.md)，本表为其外部摘要）。**读数同构前提**：K16 两键 on + 网关 sampling-on + 冻结量具原件；0.3.4 起另须 v41 面同构，调优终态另须 engram 2.0GiB 面同构——任一不同构即口径不齐，只作历史列。

**读数代际定义**：0.3.2=基线代（镜像 `0.3.2-r032c`）｜0.3.3=正典代（`0.3.3-r033d`/`0.3.3-final-20261026`）｜0.3.4=修复固化代（`0.3.4-x6bake-20261026`+v41 三联+BYPASS）｜**0.3.4 调优终态**=+DEOPT-I8 采纳面。（部署三代声明见卷首「先认代际」。）

### 3.1 判读门面（冻结阈值族；调优终态 W-f 终靴读数）

**读表先识字（一句话图例，详见 [CALIBER-AND-MEASUREMENT](docs/CALIBER-AND-MEASUREMENT.md)）**：
- **liter C1**＝长上下文单流灌入吞吐量具的 512k 档读数（tok/s，主快带判读门）。
- **DE c1**＝decode 吐字量具的并发 1 档聚合读数（agg 口径，tok/s）；c2/c4/c8/c16＝并发档。
- **500q 冻结帧**＝冻结题版 500 题质量帧的准确率读数。
- **EQ-S 同盐夹心**＝等价性判读：同一盐值埋入超长上下文首尾（「夹心」），两处取回必须逐字相等，GREEN 6/6 为过。
- **PPL golden A/A**＝困惑度双跑对拍（同输入跑两次），Δtf=0.0000 即确定性零差。
- **T33-03 正典锚**＝2026-10-26 立的 0.3.3 正典代基准读数列，后续一切 IN-BAND 判读对它展开。
- **W-d / W-f**＝战役窗编号（W-d=0.3.4 修复固化面窗、W-f=调优终态终靴窗），同一代内部的时点标签。
- **IN-BAND**＝读数落在锚 ±3% 带内=无回退的判读结论。
- **sparkDash=repeated**＝PR 阶梯的填充口径（社区基准 sparkDash 对齐、重复单元填充），跨填充口径读数不比。

| 面 | 0.3.2 基线 | 0.3.3 正典 | 0.3.4 修复固化 | **0.3.4 调优终态** | 冻结阈值 |
|---|---:|---:|---:|---:|---|
| liter C1 512k（tok/s） | —（无同口径在档） | 3954.0/3922.5 | 3906.8 | **3910.3** | ≥3700；≤3450 停窗 |
| DE c1 ·de_c48（agg_med） | — | 94.07/94.19（锚 91.64） | 91.07 | **93.83**（对锚 +2.39%） | ≥91（±3% IN-BAND） |
| DE c1 ·sd_bench（agg 中位） | — | — | 91.23 | **93.47**（对锚 +2.00%） | 同上（跨量具只报告） |
| 500q 冻结帧（accuracy） | — | 0.964 | 0.966 | **0.96**（err=0） | 地板 0.955 |
| EQ-S 同盐夹心 | — | GREEN 6/6 | GREEN 6/6 | **GREEN 6/6**（needle 599040 5/5） | GREEN 6/6 |
| PPL golden A/A（Δtf） | — | 0.0000 | 0.0000 | **+0.0000/+0.0000** | =0.0000 |
| 512k TTFT（s） | 119.6（K16-off 记录面） | 118.584 | 118.436 | **118.839** | 记录面（非门） |

### 3.2 PR 阶梯（sparkDash=repeated 口径；arb 三样本中位；tok/s=prompt_tokens/TTFT）

| 档 | 0.3.3 正典锚 | 0.3.4 W-d | **调优终态 W-f** | W-f 对锚 Δ% |
|---:|---:|---:|---:|---:|
| 32k | 6402.6 | 6492.7 | **6485.2** | +1.29 |
| 64k | 6447.7 | 6538.1 | **6532.0** | +1.31 |
| 128k | 6192.6 | 6293.8 | **6259.6** | +1.08 |
| 256k | 5550.0 | 5617.3 | **5603.8** | +0.97 |
| 512k | 4384.8 | 4403.2 | **4411.8** | +0.62 |

全档对正典锚 **IN-BAND（±3%）**——调优面在 PR 面零回退。

### 3.3 DE prose 全梯（调优终态五档全闭合）

| c | 1 | 2 | 4 | 8 | 16 |
|---:|---:|---:|---:|---:|---:|
| agg 中位（tok/s） | **93.47** | **133.12** | **175.61** | **257.12** | **348.88** |
| 对参照 | +2.00% 对锚 | +4.66% 对时代基线 | 振荡档（在册双簇） | +3.22% 对锚（快向） | −3.20% 贴缘（face 效应注记） |

比值面：**c8/c1=2.750×**（正典 2.718×）；**c16/c1=3.732×** 对历史 4.04× −7.7%=**唯一在案弱化面**（低并发放大，归 0.3.5 算子窗）；跨量具互差收敛 0.38%。调优增益（同日相邻靴 W-e0→W-f）：DE c1 **+2.30%** / c2 **+4.66%**，与 A/B 窗增益同量级复现=采纳面在产面在位。

### 3.4 历史基线段（0.3.2 / 0.3.1 定版读数；口径与 §3.1-3.3 不同代，只作历史列不混判）

> 以下两表转引自各自版本定版档（0.3.2=[0.3.2-RELEASE-NOTE](docs/release/0.3.2-RELEASE-NOTE.md)；0.3.1=[031-FINAL-PERF-REPORT](docs/report/031-FINAL-PERF-REPORT-20261009.md)），口径=各版本自身判读线，**与 §3.1-3.3 的 T33-03 正典锚口径不同代**（0.3.2 期为 K16-off、mt400 正典 DE 口径；0.3.4 起 K16-on+de_c48/sd_bench 双量具口径），跨段只报告不判读。

**0.3.2 定版（现役形 CBX1A 56 键+SPEC6 九参+r032c；sparkDash repeated-filler 七档口径，基线=本版本判读线列 MS1017/A6-ANCHOR-7）**：PR 七档 8k→512k = 5522.5 / 6040.2 / 6271.3 / **6289.3**（64k 峰档，对判读线基线 6147.3 +2.3%）/ 6048.1 / 5427.9 / 4290.0 tok/s；DE 五档锚（mt400 正典口径 agg_med）c1 88.64 域 / c2 128.89 / c4 168.35 / c8 242.83 / c16 357.9（观察位）；C8 聚合锚 C1 3757.7 / C2 2849.8 / C4 1571.0（C4/C1=0.418）；质量面 GSM8K 0.985-0.99 / needle 600k 3/3 / EQ-1 位等 6/6 / 池 9.6M 全绿零回归。（衔接注记：0.3.2 期 512k repeated v2 锚 4376.9 为 K16-off 口径，与 §3.2 的 T33-03 锚 4384.8 同域不同代，出处=034-PERF-REPORT §1.2 历史列。）

**0.3.1 定型形（50 键+SPEC6+W5 件；FL6 转正后 51 键；QA31 定型窗服务口径）**：census 步墙 **626.1 ms/step**（866 基线 −27.8%；≤677 目标达成）；PR ②尺四档（×3 med）8k 5203.7 / 32k 6082.2 / 64k 6126.3 / 128k 5883.3 tok/s；agg600k 聚合（5×200k 中位）4958.5 tok/s（门=3005.2）；DE c1 双点位（post 主分母）81.67（≥80.0 收案绿）；GSM8K 0.97 / needle 600k 3/3 / qeval 75/75 逐题全等。

## 4. 质量与精度

- **EQ-S 同盐夹心**：全代 **GREEN 6/6**（盐 R1EQ2026；含 needle 599040 逐字 5/5，贴 ctx 600000 上限）。
- **PPL golden A/A**：**Δtf=0.0000 确定性零**（short/long；tf 1.1359/0.4212=v41 面正典签名；跨靴与 0.3.3 fp8 锚顶层全等，items 级最大差 2.5e-7≪0.002 阈）。
- **KV/SWA fp8 精度判词：成立（无条件）——生产面 SWA 缓存精度不低于 fp8。**（内部档 `KV-SWA-PRECISION-20261029.md` §五，未入公开树；判词与证据面转引见 [034-PERF-REPORT](docs/report/034-PERF-REPORT-20261029.md) §四）
  - 存储面：四机 `[kv_fp4] mode=v41 active=False`（fp4 补丁四 seam 全 passthrough）；fork 反面计数 **0**；`kv_cache_dtype=fp8_e4m3` + `swa_prefix_tails=256` + bounded_replay 六键在役；池指纹四机钳后同值。
  - 数值面：PPL A/A 精确零 + fork 面签名缺席（fork tf 1.0691/0.4511 全代未现）+ EQ-S/500q/liter/DE 全带内。
  - 证据深度边界（如实）：PPL tf 探针深度≤40001；599040 全深度精确性由 EQ-S 逐字相等与 w1 功能单跑覆盖，非 tf 逐位探针覆盖。
- **500q 冻结帧**：家族史 0.964×3/0.958/0.966/0.96 全带内（<0.958 复现再入调查线）。

## 5. 回退与降级警告

**回退=用户明示运营动作**（正典= [ROLLBACK-PATHS-034](docs/runbook/ROLLBACK-PATHS-034.md)，本仓只载程序不构成执行授权）。双路：

| 路 | 目标态 | 差量 | 适用 |
|---|---|---|---|
| **A** | 0.3.3 全回退 | 七面差+三面零回退（boot+overlay 须同窗联动） | 0.3.4 基面本身失效或用户明示版本级回退 |
| **B** | W-d 修复面（仅撤调优 I8 采纳，0.3.4 基面全保） | **恰 3 行差**（env 去尾行+profile 两行回钉），全链一键可逆 | 调优面（engram 2GiB）判读问题；六降级面中仅 DG4 可能导向此路 |

**降级运行大声警告（doctor 内建 DG1..DG6；任一命中=多行星号框大字警告+退出码 2）**：

| 登记 | 症状 | 影响定量 |
|---|---|---|
| DG1/DG3 | `mode=fork-v4-fp4 active=True` / v41 三联面缺失 | 慢带 **−15~19%**（liter −15.7%/DE −7.5%）+TTFT +19% |
| DG2 | BYPASS 未武装（armed<8/refusing>0） | 首键 TTFT 回 **74s 慢带**（97.3% 改善丢失） |
| DG4 | engram 横幅 <8 | engram 装载面异常；若确系 2GiB 面难闭合→路 B |
| DG5 | 池指纹漂移（full/mtt/mrr/ctx/cps） | 912.25 B/token 不变式守护面破坏（needle 599040 帧依赖） |
| DG6 | 镜像 digest 失配 | 载荷读数全部不可信（registry 重拉自愈面） |

处置通则：先面级行级重钉→doctor 复检（0 FAIL 0 DEGRADED）→仍不闭合才升级呈报；**无一面以路 A 为首选**。回退锚 `.bak-pre-deopt-adopt-20261029` 全链在位；四级镜像在库（0.3.4 final/0.3.3×2/0.3.2）零覆盖。

## 6. 文档索引

| 文档 | 内容 |
|---|---|
| **[0.3.4re-RELEASE-NOTE](docs/release/0.3.4re-RELEASE-NOTE.md)** | **0.3.4re 发布说明（现役发布面）**：版本叙事/性能终态/硬守门清单/已知局限/DF·EQ 修复清单/回退面 |
| [034-PERF-REPORT-20261029](docs/report/034-PERF-REPORT-20261029.md) | **完整性能报告（终版）**：全代对照总表+PR/DE 阶梯+sparkDash 口径注记+KV/SWA fp8 精度判词+测试制式 |
| [ACKNOWLEDGEMENTS](docs/ACKNOWLEDGEMENTS.md) | 致谢：knapcio / heterogeneous-gpu-pd-lab / sparkDash / sglang / DeepSeek / 判例制式 |
| [034-VERSION-LOCK-20261028](docs/release/034-VERSION-LOCK-20261028.md) | 版本锁档（锁包 v2，含 §十二调优终态追记）：身份链/五面锚/冻结声明 |
| [MANIFEST-034LOCK](docs/release/MANIFEST-034LOCK.tsv) | 锁包冻结清单（固化件 live+archive 双面 md5、工具冻结锚） |
| [ROLLBACK-PATHS-034](docs/runbook/ROLLBACK-PATHS-034.md) | 回退双路正典+降级面→路径映射（路 A 程序正典=内部档 ROLLBACK-TO-033.md，未入公开树） |
| [runbook-034](docs/runbook/runbook-034.md) | 运维手册：四命令详解/故障排查矩阵/§八调优面与回退双路 |
| [034-WD-TUNED-FINAL-20261029](docs/release/034-WD-TUNED-FINAL-20261029.md) | 调优终态收口档：61 键面唯一来源定义（I8 唯一采纳+I4/I5/I6 REVERT+I7 SKIP） |
| [034-KV-MECH-NOTE](docs/research/034-KV-MECH-NOTE-20261028.md) | KV_LAYOUT 双态机制深读（v41 固化面 vs fork-v4-fp4 机理差异） |
| [034-BYPASS-JUDGMENT](docs/research/034-BYPASS-JUDGMENT-20261028.md) | BYPASS 采用合判档（首键 TTFT 74.191s→1.971s 判读依据） |
| [034-ERA-DRIFT-INVESTIGATION](docs/research/034-ERA-DRIFT-INVESTIGATION-20261027.md) | 吞吐口径 era 漂移归因调查（量具口径方法论） |
| [0.3.4-RELEASE-NOTE](docs/release/0.3.4-RELEASE-NOTE.md) | 0.3.4 发布说明（骨架，正文待后续窗充实） |
| [UPGRADE-0.3.4](UPGRADE-0.3.4.md) | 0.3.3/0.3.2→0.3.4 升级指南（骨架，正文待后续窗充实） |
| [0.3.2-RELEASE-NOTE](docs/release/0.3.2-RELEASE-NOTE.md) | 前代（0.3.2）发布说明 |
| [KNOWN-ISSUES](docs/KNOWN-ISSUES.md) | 已知现象与误判澄清（含上游缺陷四件与思考流退化判词） |
| [tools/](tools/) | 工具链：deploy/doctor/verify/selftest 四件套 + config/gates 期望正典 + bypass/guard 配套件 |

## 7. 战役纪律（本仓一切读数的产生前提）

单变量 A/B（每窗恰一键/一值差）｜量具冻结（调用前 md5 断言，零改动零降门）｜冻结阈值不降门｜同日相邻靴相对带（era 判读制式）｜跨量具/跨 era 只报告不混判｜判读窗禁切网关采样与 K16 两键｜偏差=停窗如实呈报。

---

—— 文档写手（0.3.4re 发布门面窗）/ 2026-10-30 / 数值正典源=[034-PERF-REPORT-20261029](docs/report/034-PERF-REPORT-20261029.md)（出处逐处列明）；版本系列素材源=PERF-REPORT+WD-TUNED-FINAL+CHANGELOG+各代锁档；本页密钥零落盘、内网地址以「内部集群/内部网关/内部 registry」泛化。
