# deploy/ — 部署面（0.3.1 历史样本 + 0.3.2 现役环境/重建包）

> **0.3.2 定版注记（2026-10-20）**：本目录保留 0.3.1 定型形样本（历史基线）；
> **0.3.2 现役形已完整归位**：现役 env=`env/CBX1A-CERTM-spec1.env`（56 键
> `0729e18d`），其余增量在 [`reconstruct/0.3.2/`](reconstruct/0.3.2/README.md)
> （adapter 13+4 件、overlay backend `a1e7c3b5`、b12x 3 件、r032c 16 件镜像
> 补丁/全文/构建配方、1017 权重与 engram 分片台账）。
> adapter 终态=0.3.1 基底+reconstruct 覆盖，装配账=
> [`adapter/0.3.2-MANIFEST.md5`](adapter/0.3.2-MANIFEST.md5)（87 个运行时件）。
> `bin/r3-boot-arm.sh` 已同步 0.3.2 终态参面（SERVER_ARGS 含 A8/A9；原第九参
> `--sleep-on-idle` 2026-10-30 退役=上游 #43050 idle-wake hang host 侧规避〔禁参，
> 见 SPEC6-SERVE-REF〕、D15 五门、IMAGE 指针 `0.3.2-r032c`）。0.3.2 全量差异与性能见
> [../docs/release/0.3.2-RELEASE-NOTE.md](../docs/release/0.3.2-RELEASE-NOTE.md)；
> 逐步升级/复现/回退见 **[../UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)**。
> 下表的 50/51 键与 md5 为 **0.3.1 历史形**；重建 0.3.2 以 CBX1A + reconstruct 包为准。

> 权威表=`docs/registry/FORM-REGISTRY-031.md`（三形三元组+部署面指纹）；
> 操作规程=`docs/runbook/OPS-MANUAL-031.md`。本目录=可发布快照，逐件 md5 锚
> 见下表（与 FORM-REGISTRY §二对表）。

## env/ — 0.3.2 现役 + 0.3.1 历史形

| 件 | 键数 | md5 | 状态 |
|---|---|---|---|
| `CBX1A-CERTM-spec1.env` | 56 | **0729e18d** | **0.3.2 现役形**（E16B2 键面 + `DSV41_CERT_HEAD_M=6,12,…,48`；与 reconstruct 包内同名件逐字节相同；WCBOOT74 复役形） |
| `PROD-R51W5-spec1.env` | 50 | **15767aa6** | **0.3.1 一级回退形**（FL6 转正后自「现役」降级；=48 键 8c8c166d 逐字+FP8/TG 两键；摘第 51 键即自 51 键形回退至此） |
| `PROD-R51W5-FL6FIX-spec1.env` | 51 | 2ac74586 | **0.3.1 期在役形（历史）**——0.3.2 起现役键面已演进为 CBX1A 56 键；本件保留为 0.3.1 回退/复现样本（FL6-PROMO 窗闭 GREEN：cp30 锚位 99.95%+DE 82.17 实役直证）；机理档=`docs/research/FL6-RECALL-BUG-ANALYSIS-20261013.md` |

0.3.2 回退链（相邻级单文件回指）：**CBX1A→E16B2→E16B1→FB54→0.3.1 51 键**；
E16 链四件在 `reconstruct/0.3.2/env/`，逐级键差见其 `ENV-CHAIN.md`。
0.3.1 深回退链两级（自 50 键在役形）：48 键 PROD-R1INK48L2PF6O12C1（8c8c166d）→
47 键 PROD-R1STDLL128L2PF6O12C1（99e7ec92）+深回退 45 键 PROD-R1STDLL128L2PF6
（34977bf0）——三件随仓收录=`tools/packages/cfgmgmt/payload/env/`（cfgmgmt 包
回退链库，md5 对表 FORM-REGISTRY-031 §一全中；服务器在役位=~/migrate-assets/
dsv41/env/）。

## SPEC6-SERVE-REF.md — serve 九参（六参→九参）

50 键定型形 serve 参谱=**SPEC6**（五参基座+swa256），全文与用法见
[SPEC6-SERVE-REF.md](SPEC6-SERVE-REF.md)。

## reconstruct/ — 0.3.2 完整重建包（2026-10-20）

[`reconstruct/0.3.2/`](reconstruct/0.3.2/README.md) 是 0.3.2 现役形的逐文件重建面，
补齐 `v0.3.2` tag 时尚未归位的增量：

| 面 | 内容 |
|---|---|
| `env/` | CBX1A 56 键 `0729e18d` + FB54/E16B1/E16B2 逐级链 + 键差说明 |
| `adapter/` | 13 件现役增量 + 4 件旁挂；12 件代码逐字节=产线 md5 |
| `overlay/` | `deepseek_v4_backend.py` `a1e7c3b5` 全文+补丁 |
| `b12x/` | `roce_oneshot.py`/`_allgather_cute.py`/`_roce_proxy.c` 现役源码 |
| `image/` | r032c 16 件全文+`79cafec0→f9d89b02` 补丁+构建脚本+身份四件 |
| `weights/` | 1017 84 文件 SHA256SUMS + engram 8 分片哈希/生成工具 |
| `boot/` | 九参、WORKERS、四查与回退 |

自验：`bash deploy/reconstruct/0.3.2/verify.sh`（期望 `RECON-KIT PASS`）。基座镜像
与权重/engram 属外部大件，包内给身份指纹与校验清单，不分发本体。

## adapter/ — 0.3.1 基底 + 0.3.2 装配账

**0.3.1 基底 83 件/约 3.0M**（顶层 68+fi_r1/ 6+lib/ 1+overlay/ 3+tests/ 5；
sitecustomize 55b1e412 装载缝+boot 装载闭包 48 件+留役休眠件 10+`.so` 运行库+
dspark_sps 表+构建源）。收录口径（剔 `*.bak*` 39+变体 1+EP1 陈旧清单 2）与排除
名单逐件、FL6 终值注记见 [adapter/README.md](adapter/README.md)；逐件
md5=[adapter/MANIFEST.md5](adapter/MANIFEST.md5)。

**0.3.2 终态**=上述基底 + `reconstruct/0.3.2/adapter/files/` 覆盖，装配后
**87 个运行时件**（生产记录 89 件，多 2 个宿主 `.bak`）。逐件验收=
[`adapter/0.3.2-MANIFEST.md5`](adapter/0.3.2-MANIFEST.md5)，装配/落位/回退=
[`adapter/0.3.2-ASSEMBLY.md`](adapter/0.3.2-ASSEMBLY.md)。关键锚：
`sitecustomize.py`=`beb131ab`、`kv_fp4.py`=`75062432`、`replicated_split.py`=
`7d6f79b0`、`roce_ar.py`=`f61e0183`、`seam_mount.py`=`a65797a5`、
`sparse_wire.py`=`0067abc4`。产线活件指纹 `b58e49ff`；86/87 件 md5 与产线
逐字节相同，`build_repack_cuda.sh` 仅注释家目录脱敏（产线 `cd6c7707`）。

## bin/ — r3-boot-arm.sh 部署链

> 服务面其余模块（overlay/nccl/b12x/kit/models.d/sentinel）落位映射与部署序
> 见 `docs/DEPLOY-GUIDE.md` §5。

| 件 | md5 | 用途 |
|---|---|---|
| `r3-boot-arm.sh` | 20f22bc6（产线）/ 9ac6e113（公开件） | ARM 主 boot 链（0.3.2 终态参面：SERVER_ARGS 九参/D15 五门/IMAGE r032c/env 注入/overlay 挂载/横幅门/池门 9,600,000）。公开件=产线体+8 行快照头+3 处用户名路径掩码，功能逐字等价；还原命令见 reconstruct 包 README §5 |
| `r3-boot.sh` | — | 基座 boot（无 ARM 注入面） |
| `r3-stop.sh` | 5ad87830 | 四机停靴（先存后删律配套） |
| `r3-watchdog.sh` | — | 水位/健康看护 |
| `r3-window.sh` | — | 窗口冒烟（拓扑一句话探针） |
| `r3-gate-env-lint.sh` | a69f5f0e | env 键面 lint 拒绝门（红=拒起；含 EQ-03 serve 禁参组合 fail-closed 检查④） |
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

## overlay/ — o12c1-prod/（产线 overlay 快照，0.3.4 形）+ v4vl-79cafec0/（VL 复原树 28 件）

**o12c1-prod/＝0.3.4 形现役快照（2026-10-31 备查同步窗整面入仓）**：目录 30 件=
29 个 `.py` 活件+`overlay-map.tsv` 映射表；对表清单=
[`prod/overlay-md5.txt`](prod/overlay-md5.txt)（`md5sum -c` 应 29 行全绿）。三件
身份正典全文备查于 [`reconstruct/0.3.4/overlay/`](reconstruct/0.3.4/overlay/NOTES.md)；
逐件身份/md5/血统/换血表/旧形取回总表=**[`README-说明.md`](README-说明.md)**。

**v4vl-79cafec0/**＝V4.0exp 臂供给面（bind mount 面，非镜像内容）：源=宿主
`~/migrate-assets/vl-native/sglang-overlay.v4vl-79cafec0/`（四机同路径纪律），
内容指纹 cbf986df×4 机全等；平铺键→容器 sglang 路径映射=`boot_mvl40exp_r2.sh`
内嵌 OV_MAP（28 件 fail-closed 计数断言）。与 `o12c1-prod/`（产线 30 件）零交叠。
详=DEPLOY-GUIDE §5/§9.2+`docs/research/VL-NATIVE-RESULT-20261013.md` §三。

## 内网值说明（2026-10-30 更新）

- **内网 IP：全树已清零**（RFC1918 编址亲扫 0 命中，0.3.4re 起一律占位符形
  `<registry-host>`/`<H1>`~`<H4>` 等）。
- **主机名/内部路径：0.3.1/0.3.2 期历史存量件仍保留**——`dgxspark01-04`、`macgw`
  等主机名与 `migrate-assets`/`luz030-opt-campaign`/`dsv41-flash-dgxsparks` 等
  内部路径见于旧证据档、旧报告与旧工具缺省值（沿用 2026-10-13 扫描的「密钥扫描
  策略保留」面，清单见 [../SCAN-REPORT.md](../SCAN-REPORT.md)）；0.3.4re 移植件
  本族零命中。这些值不属密钥面；如需零命中口径须另批整树脱敏（会改写历史证据件，
  见 KNOWN-ISSUES §7「脱敏存量面」行）。
- **备份件注记**：`bin/r3-stop.sh.bak-pre-df03-20261030`（DF-03 修复留档，CHANGELOG
  在案）与 `b12x/comm.bak-prerocenante-r2`、`b12x/b12x/comm/roce_ring/` 下 3 件
  `.bak-pre-k1b`（历史窗留档）为 `.bak` 备份面，**不属任何装配面**，验收对表一律
  排除 `*.bak*`。
