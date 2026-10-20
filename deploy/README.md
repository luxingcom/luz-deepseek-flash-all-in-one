# deploy/ — 0.3.1 定型形部署面（env 键面 + SPEC serve 参 + adapter 现役件 + boot 链）

> **0.3.2 定版注记（2026-10-20）**：本目录是**混合快照**——`bin/r3-boot-arm.sh`
> 已同步 0.3.2 终态参面（SERVER_ARGS 九参含 A8/A9/`--sleep-on-idle`、D15 五门、
> IMAGE 指针 `0.3.2-r032c`，md5 `20f22bc6`），而 `env/` 与 `adapter/` 仍为 0.3.1
> 定型形样本（0.3.2 现役 env=CBX1A 56 键 `0729e18d`、adapter `b58e49ff`，属
> 内部臂件，公开仓归位=呈裁位）。0.3.2 全量差异与性能见
> [../docs/release/0.3.2-RELEASE-NOTE.md](../docs/release/0.3.2-RELEASE-NOTE.md)。
> 下表的 50/51 键与 md5 为 **0.3.1 历史形**，不声称是 0.3.2 现役键面。

> 权威表=`docs/registry/FORM-REGISTRY-031.md`（三形三元组+部署面指纹）；
> 操作规程=`docs/runbook/OPS-MANUAL-031.md`。本目录=可发布快照，逐件 md5 锚
> 见下表（与 FORM-REGISTRY §二对表）。

## env/ — 两形收录与状态位

| 件 | 键数 | md5 | 状态 |
|---|---|---|---|
| `PROD-R51W5-spec1.env` | 50 | **15767aa6** | **一级回退形**（FL6 转正后自「现役」降级；=48 键 8c8c166d 逐字+FP8/TG 两键；摘第 51 键即自 51 键形回退至此） |
| `PROD-R51W5-FL6FIX-spec1.env` | 51 | 2ac74586 | **0.3.1 期在役形（历史）**——0.3.2 起现役键面已演进为 CBX1A 56 键（内部臂件，见上方定版注记）；本件保留为 0.3.1 回退/复现样本（FL6-PROMO 窗闭 GREEN：cp30 锚位 99.95%+DE 82.17 实役直证）；机理档=`docs/research/FL6-RECALL-BUG-ANALYSIS-20261013.md` |

回退链两级（自 50 键在役形）：48 键 PROD-R1INK48L2PF6O12C1（8c8c166d）→
47 键 PROD-R1STDLL128L2PF6O12C1（99e7ec92）+深回退 45 键 PROD-R1STDLL128L2PF6
（34977bf0）——三件随仓收录=`tools/packages/cfgmgmt/payload/env/`（cfgmgmt 包
回退链库，md5 对表 FORM-REGISTRY-031 §一全中；服务器在役位=~/migrate-assets/
dsv41/env/）。

## SPEC6-SERVE-REF.md — serve 六参

50 键定型形 serve 参谱=**SPEC6**（五参基座+swa256），全文与用法见
[SPEC6-SERVE-REF.md](SPEC6-SERVE-REF.md)。

## adapter/ — 供给面整面快照（B1 收录 2026-10-13）

**83 件/约 3.0M**（顶层 68+fi_r1/ 6+lib/ 1+overlay/ 3+tests/ 5；sitecustomize 55b1e412
装载缝+boot 装载闭包 48 件+留役休眠件 10+`.so` 运行库+dspark_sps 表+构建源）。
收录口径（剔 `*.bak*` 39+变体 1+EP1 陈旧清单 2）与排除名单逐件、FL6 终值注记见
[adapter/README.md](adapter/README.md)；逐件 md5=[adapter/MANIFEST.md5](adapter/MANIFEST.md5)。

## bin/ — r3-boot-arm.sh 部署链

> 服务面其余模块（overlay/nccl/b12x/kit/models.d/sentinel）落位映射与部署序
> 见 `docs/DEPLOY-GUIDE.md` §5。

| 件 | md5 | 用途 |
|---|---|---|
| `r3-boot-arm.sh` | 20f22bc6 | ARM 主 boot 链（0.3.2 终态参面：SERVER_ARGS 九参/D15 五门/IMAGE r032c/env 注入/overlay 挂载/横幅门/池门 9,600,000；与产线同体，仅用户名路径掩码三处） |
| `r3-boot.sh` | — | 基座 boot（无 ARM 注入面） |
| `r3-stop.sh` | 5ad87830 | 四机停靴（先存后删律配套） |
| `r3-watchdog.sh` | — | 水位/健康看护 |
| `r3-window.sh` | — | 窗口冒烟（环网一句话探针） |
| `r3-gate-env-lint.sh` | 5337c6cf | env 键面 lint 拒绝门（红=拒起） |
| `r3-gate-assert-lint.sh` / `r3-gate-banner-contract.sh` / `r3-gate-endpoint-lint.sh` | — | 断言/横幅合同/端点 lint 三门 |
| `boot_mvl41_native.sh` | — | **VL V4.1 原生视觉臂 boot**（零旗启用；S1-S4 三级阶梯全绿收录；用法=DEPLOY-GUIDE §9.1） |
| `boot_mvl40exp_r2.sh` | — | **VL V4.0exp overlay 复原臂 boot**（C24+overlay 28 件 fail-closed+mm 直证；§9.2） |
| `vl_smoke_gv1.py` | — | G-V1/G-V5 冒烟量具（knapcio 双形状 1024/1024 SAT 断言+官方对+canary×3） |

boot 规程（点火前缀/沉降 600s 律/warm 64k×2 第一动作/warm 门 4500/5000/
四查）——见 OPS-MANUAL 第一章。产线基座镜像=SGLang 上游 main-79cafec0
（NOTICE §4）。

## env/ — VL 四臂形（VL-NATIVE 窗收录 2026-10-13）

| 件 | md5 | 状态 |
|---|---|---|
| `VL41N-SPEC0.env` | d7f07588 | V4.1 原生臂 S1/S3 认证形（五驱动约定键；零 DSV41_* 性能键=51 键族零触碰律） |
| `VL41N-K6.env` | 6041757d | L2 级 k6+GRAPHS0 阶梯臂 |
| `VL41N-K6CG.env` | bd5d62d8 | L3 级 k6+CG bs16=生产全量形（参数面与产线逐字等价动态预证） |
| `VL40EXP-R2-C24T.env` | —（脱敏收录） | V4.0exp R2 认证形 19 键+`SGLANG_OVERLAY_DIR` 复原树指针（用户名掩码位=部署时替换，见 DEPLOY-GUIDE §5 脱敏注记） |

## overlay/ — v4vl-79cafec0/（VL 专用复原树 28 件）

V4.0exp 臂供给面（bind mount 面，非镜像内容）：源=宿主
`~/migrate-assets/vl-native/sglang-overlay.v4vl-79cafec0/`（四机同路径纪律），
内容指纹 cbf986df×4 机全等；平铺键→容器 sglang 路径映射=`boot_mvl40exp_r2.sh`
内嵌 OV_MAP（28 件 fail-closed 计数断言）。与 `o12c1-prod/`（产线 29 件）零交叠。
详=DEPLOY-GUIDE §5/§9.2+`docs/research/VL-NATIVE-RESULT-20261013.md` §三。

## 内网 IP 说明

本目录与 docs/ 各档含内网 IP/主机名（dgxspark01-04 等）——内网部署文档性质，
按密钥扫描策略保留（SCAN-REPORT.md）；对外发布时如需脱敏按该档处置行执行。
