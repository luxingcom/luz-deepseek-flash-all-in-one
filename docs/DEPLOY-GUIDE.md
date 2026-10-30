# DEPLOY-GUIDE — 从零部署指南（4×DGX Spark GB10 TP4 双 rail RoCE）

> 目标：在四台 DGX Spark（GB10）上从零复原 LuZ 生产栈。
> **0.3.2 定版注记（2026-10-20）**：0.3.2 现役形已完整公开——现役 env=
> [`deploy/env/CBX1A-CERTM-spec1.env`](../deploy/env/CBX1A-CERTM-spec1.env)
> （56 键/`0729e18d`），其余增量在
> [`deploy/reconstruct/0.3.2/`](../deploy/reconstruct/0.3.2/README.md)（adapter
> 13+4 件、overlay/b12x、r032c 16 件镜像补丁+构建配方、1017 权重与 engram 台账）。
> adapter 终态=0.3.1 基底+覆盖，装配账=
> [`deploy/adapter/0.3.2-MANIFEST.md5`](../deploy/adapter/0.3.2-MANIFEST.md5)。
> 本文 §1-§9 的 0.3.1 数值保留为历史基线；**现役值以 §0 表 + reconstruct 包为准**。
> 逐步升级/性能复现/回退=
> **[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)**；0.3.2 全量差异见
> [release/0.3.2-RELEASE-NOTE.md](release/0.3.2-RELEASE-NOTE.md)。
> 规程法源=`docs/runbook/OPS-MANUAL-031.md`（boot/复原/回退三章）；形权威表=
> `docs/registry/FORM-REGISTRY-031.md`（三形三元组+部署面指纹）。

## 0. 0.3.2 现役形精确重建（先读）

| 件 | 现役值 | 重建材料 |
|---|---|---|
| env | **CBX1A 56 键** / `0729e18d` | [`deploy/env/CBX1A-CERTM-spec1.env`](../deploy/env/CBX1A-CERTM-spec1.env) + `reconstruct/0.3.2/env/` 逐级链 |
| adapter | 活件指纹 `b58e49ff`；装载缝 `sitecustomize.py`=`beb131ab`、R1 `kv_fp4.py`=`75062432` | 0.3.1 基底 + 13+4 件覆盖；装配账 `deploy/adapter/0.3.2-MANIFEST.md5`（87 件） |
| overlay | `deepseek_v4_backend.py`=`a1e7c3b5` | 全文 + 补丁 |
| b12x | `roce_oneshot.py`=`035c860c`、`_allgather_cute.py`=`7253717a`、`_roce_proxy.c`=`23646e89` | 3 件全文 + 补丁 |
| IMAGE | `0.3.2-r032c` / `sha256:47f6d91a…e2ffc4` / 71 层 | 16 件全文 + `79cafec0→f9d89b02` 补丁 + 构建脚本 |
| 权重 | `DeepSeek-V4.1-Flash-1017` / 84 文件 / 510,311,045,870 B | 84 行 SHA256SUMS + NFS/秩映射 |
| engram | 8 分片 / 202,758,065,168 B | 分片哈希 + `pack_engram.py`/打包/分发/校验工具 |
| boot | `r3-boot-arm.sh` 产线 `20f22bc6`；公开件 `9ac6e113`（脱敏头） | 公开 boot + `reconstruct/.../boot/RUN-ARGS.md` |
| 升级 | 0.3.1→0.3.2 逐步命令/性能复现/回退 | **[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)** |

重建顺序、逐件命令、脱敏差异与自验：`bash deploy/reconstruct/0.3.2/verify.sh`
（期望 `RECON-KIT PASS`）。基座镜像与权重/engram 本体不分发，包内给身份指纹与
下载后校验清单。

## 1. 硬件前置

| 项 | 要求 |
|---|---|
| 节点 | 4× NVIDIA DGX Spark（GB10，SM121，ARM aarch64，UMA 架构） |
| 拓扑 | TP4；**0.3.2 现役=双 rail 以太交换机**，每机 2 口 HCA 部署对 `rocep1s0f0,roceP2p1s0f1`，`B12X_ROCE_TOPOLOGY=switched`+`LUZ_SWITCH_ROCE_FLAT=1`+`TC=106`；NCCL 用同一部署对 + `NCCL_IB_TC=106`。4 口 CX-7 hairpin 环网=0.3.1 及更早历史形，两形不可混拼 |
| 角色 | rank0=head <node01>（<mgmt-node-ip>）；rank1=<node02>（<mgmt-node-ip>）；rank2=<node04>（<mgmt-node-ip>）；rank3=<node03>（<mgmt-node-ip>）〔net-rebuild-20261015 管理段重编址；IP 具体值已脱敏〕 |

## 2. 系统依赖（版本锚——系统级件不随仓分发，逐项对版）

| 组件 | 版本锚 | 核验法 |
|---|---|---|
| NVIDIA 驱动 | **580.173.02** | `nvidia-smi --query-gpu=driver_version --format=csv,noheader` |
| 内核 | **6.17.0-1031-nvidia**（arm64） | `uname -r` |
| CUDA 面 | **13.0**（容器内经 nvidia-container 注入） | `nvidia-smi`（右上 CUDA Version） |
| nvidia-container-toolkit | **1.19.1** | `dpkg -l \| grep nvidia-container-toolkit ` |
| NCCL 特殊栈 | **ring-only 构建 2.30.7**（`deploy/nccl/nccl-ringonly/libnccl.so.2.30.7`，fork 库盖 pip 路径同身份；pin 件挂 `/opt/ncclpin.so`） | boot 前置检查（r3-boot-arm.sh :165） |
| Docker | ≥支持 compose 前述 toolkit 的稳定版 | `docker info` |
| SSH 互信 | 四机 head→workers 免密（密钥登录；密码登录面见 `tools/ssh-password-login-20261013/` 运维件，凭据绝不入仓） | `ssh <worker> true` |

## 3. 镜像获取

见 [README §二](../README.md#二镜像下载内网-registry-直链)：现役基座
`<registry-host>:5000/lmsysorg/sglang:main-79cafec0`（48.6GB，
sha256 `0f075735…cf3ae`）。四机 `docker pull` 后以 RepoDigest 对表指纹。
0.3.2 现役=**`dsv41-sglang-optimized:0.3.2-r032c`**（digest
`sha256:47f6d91a…e2ffc4`，71 层=基座 70+1）；可直接 pull，或按
`deploy/reconstruct/0.3.2/image/` 的 16 件全文/补丁从基座烘制。
VL 线已切 SGLang 单基座（vLLM 两形移历史/备份注记，见 README §二尾注）。

**镜像三通道身份表（2026-10-14 固化窗引入，交叉=`~/luz-0.3.1-dist/README-DIST.md`）**：

| 通道 | 值 | 复核法 |
|---|---|---|
| registry manifest digest（r3） | `sha256:f8095fa8…415c1`（四机一致） | `docker inspect --format '{{.RepoDigests}}' <r3 镜像>` |
| 冷构建内容身份 cid | `ffed489217c872ea`（RootFS 层链算式） | README-DIST 载复算命令 |
| 基座钉 | `0f075735`（main-79cafec0 01 原始形；r3prod-head 实跑 Id） | `docker inspect r3prod-head` |
| r3 离线 tar | sha256 `6afa4429…`（`~/luz-0.3.1-dist/images/`+CHECKSUMS.manifest） | `sha256sum -c` |

注意：01 本地镜像 ID=f8095fa8d6ed 而 02 显示 a23298ed=digest 同、显示口径异
（containerd 索引 digest vs overlay2 config digest——G2 定谳，非内容漂移）。

## 4. 权重目录布局（0.3.2 现役=1017）

| 机 | 路径 | 内容 |
|---|---|---|
| <node01>/<node02> | `/data/models/DeepSeek-V4.1-Flash-1017/` | 1017 权重 84 文件 / 510,311,045,870 B（`config.json` sha256 `8be45ce0…21879`） |
| <node03>/<node04> | `/data/models/dsv41-net/`（符号链接 `/data/models/DeepSeek-V4.1-Flash-1017`） | 同权重 NFS 只读位（源 <nfs-server-ip>×2） |

逐文件 sha256=`deploy/reconstruct/0.3.2/weights/DeepSeek-V4.1-Flash-1017.sha256`
（84 行）；NFS 导出/挂载/秩映射=`weights/WEIGHTS.md`。
权重注册卡（三模型谱系+指纹）：`deploy/models.d/`（v41-prod/v4-0731/v4-vl-exp）。
engram 分片（**宿主生成物，约 189G，不随仓分发**）：`~/dsv41-engram-1017/`
（L1/L14 各 4 秩，8 件 202,758,065,168 B）——生成/分发/校验工具与逐件 sha256=
`deploy/reconstruct/0.3.2/weights/`；缺分片=boot 前置检查拒起。

> 0.3.1 历史位（仅回退用）：`/data/models/DeepSeek-V4.1-Flash/`（476G）+
> `~/dsv41-engram/`（48G）。0.3.2 切换时旧树/旧 engram 原样保留，可回退。

## 5. 服务面部署（本仓 → 服务器落位映射）

> **脱敏注记（2026-10-13）**：本仓为分发脱敏版——用户名统一掩码为 `liux***ya`
> （路径/systemd `User=` 位）。部署落位时将 `liux***ya` 替换为实际运行用户；
> 产线路径清单（`payload/out/*-MANIFEST.md5`、`boot-chain.md5`、selfcheck
> `sources.tsv`）为产线清单的脱敏快照，到靶机以 gen-manifests.sh /
> adapter-manifest-regen.sh 按实际用户重生成。详见
> `docs/registry/SANITIZATION-20261013.md`。

| 本仓 | 服务器落位 | 说明 |
|---|---|---|
| `deploy/bin/` | `~/migrate-assets/bin/` | r3-boot-arm.sh 部署链（0.3.2 产线 md5 **20f22bc6**；公开件 9ac6e113=脱敏头）+gate 四件+stop/watchdog |
| `deploy/reconstruct/0.3.2/` | 按包内 README 分段落位 | **0.3.2 现役增量全件**：CBX1A env、adapter 13+4、overlay/b12x、r032c 16 件、1017/engram 台账 |
| `deploy/bin/boot_mvl41_native.sh`+`boot_mvl40exp_r2.sh`+`vl_smoke_gv1.py` | `~/luz030-opt-campaign/dev/vl-native/`（战役位；或任意可写位+`CAMP=` 覆写） | VL-NATIVE 窗执行件（2026-10-13 全绿收录）：V4.1 原生视觉臂 boot+V4.0exp overlay 复原臂 boot+G-V1/G-V5 冒烟量具（knapcio 双形状 1024/1024 SAT 断言）；用法=§9 |
| `deploy/adapter/` | `~/migrate-assets/dsv41/adapter/` | **0.3.1 基底 83 件/约 3.0M**（=0.3.2 装配基底；B1 收录 2026-10-13：顶层 68+fi_r1/ 6+lib/ 1+overlay/ 3+tests/ 5；sitecustomize 55b1e412 装载缝+闭包 48 件+留役休眠件+`.so`/json/构建源；排除 `*.bak*` 39+变体 1+EP1 陈旧清单 2）。0.3.2 终态=基底+`reconstruct/0.3.2/adapter/files/` 覆盖，装配后 **87 个运行时件**；逐件账=`deploy/adapter/0.3.2-MANIFEST.md5`，步骤=`deploy/adapter/0.3.2-ASSEMBLY.md` |
| `deploy/env/` | `~/migrate-assets/dsv41/env/` | **0.3.2 现役=`CBX1A-CERTM-spec1.env`（56 键/0729e18d）**；E16B2/E16B1/FB54 逐级链在 `reconstruct/0.3.2/env/`；仓内另有 0.3.1 两形+**VL 四臂形**历史/回退样本（VL41N-SPEC0/K6/K6CG 三级阶梯+VL40EXP-R2-C24T；详=§9） |
| `deploy/overlay/o12c1-prod/` | `~/migrate-assets/v4vl/sglang-overlay.o12c1-prod/`（=`SGLANG_OVERLAY_DIR`） | 29 件=28 活件影子挂载+1 映射表（scheduler 5b6fe2a3 等；boot 链挂载计数断言==28——r3-boot-arm.sh `ov_n` 门；目录 29 件含 overlay-map.tsv 自身） |
| `deploy/overlay/v4vl-79cafec0/` | `~/migrate-assets/vl-native/sglang-overlay.v4vl-79cafec0/` | **VL 专用 overlay 复原树 28 件**（V4.0exp 臂供给面；内容指纹 cbf986df×4 机全等——VL-NATIVE S5 整树复原律；boot_mvl40exp_r2.sh 内嵌 OV_MAP 平铺键→容器路径映射+28 件 fail-closed 计数断言；与 o12c1-prod 零交叠） |
| `deploy/nccl/nccl-ringonly/`+`ncclpin.so` | `~/migrate-assets/nccl-ringonly/`+`~/migrate-assets/ncclpin.so` | ring-only NCCL 2.30.7+pin 件（只读挂载 /opt） |
| `deploy/b12x/` | `~/migrate-assets/b12x/` | b12x/b12x_next MoE 计算树（boot 硬前置） |
| `deploy/kit/` | `~/w6-kit/`（或烘入 /opt/dsv41/kit/） | guard 守卫族+instruments 量具+adr（oom-gate 面单元让位 selfheal 包） |
| `tools/packages/` | 五包各自 README 部署位（如 gateway→/opt/aicad-prod/） | fabric-net/selfdiag/selfheal/gateway/cfgmgmt（含 systemd 单元面：oom-gate-monitor.service、concurrency-proxy-v2.service+10-gateway-hardening.conf drop-in） |
| `deploy/sentinel/`、`tests/unit/` | 案头/巡检位 | ar_probe 探针+b12x/row_store 单元测 |

部署序：目录映射→`tools/boot-with-slotlock.sh`+r3-boot-arm.sh 资产面前置检查
（adapter/NCCL/b12x_next/分片/权重五项在场，:165）→env/serve/adapter 三元组
对表 FORM-REGISTRY。

## 6. env 形选择（0.3.2 现役 CBX1A；0.3.1 五级链为回退）

| 形 | 件/md5 | 适用 |
|---|---|---|
| **CBX1A 56 键（0.3.2 现役）** | `deploy/env/CBX1A-CERTM-spec1.env` / **0729e18d**（与 `reconstruct/0.3.2/env/` 同名件逐字节相同） | 0.3.2 终态（WCBOOT74 复役形）：E16B2 键面 + `DSV41_CERT_HEAD_M=6,12,…,48` |
| **E16B2 56 键（一级回退）** | `reconstruct/0.3.2/env/PROD-E16B2-spec1.env` / 5877fcb0 | 摘 CERT M 八元即回此形 |
| **E16B1 54 键** | `reconstruct/0.3.2/env/PROD-E16B1-spec1.env` / d55baa00 | RoCE 聚合尺寸翻倍形 |
| **FB54 54 键** | `reconstruct/0.3.2/env/PROD-FB54-spec1.env` / ad635762 | D12 三键/交换机面初形 |
| **51 键 FL6 形（0.3.1 历史）** | `PROD-R51W5-FL6FIX-spec1.env` / 2ac74586（服务器位名=`PROD-R51W5FL6-spec1.env`） | 0.3.1 定型形；0.3.2 下为历史/复现样本 |
| **50 键形（深回退）** | `PROD-R51W5-spec1.env` / 15767aa6 | 0.3.1 一级回退（摘第 51 键即得） |

serve 参=**SPEC6 八参**（六参基座 + A8 `--tool-call-parser deepseekv41` + A9
`--enable-cache-report`；原第九参 W-G `--sleep-on-idle` 已于 2026-10-30 退役为
禁参=上游 #43050 idle-wake hang host 侧规避，`deploy/SPEC6-SERVE-REF.md`）。
0.3.1 键面回退链 **51→50→48→47→45 键五级**仍有效（45 键=零 overlay 深回退一级，
`PROD-R1STDLL128L2PF6-spec1.env`=34977bf0——见 `docs/registry/FORM-REGISTRY-031.md`
§一 L3；48/47/45 键件在 `tools/packages/cfgmgmt/payload/env/`）。0.3.2 的新回退链=
**CBX1A→E16B2→E16B1→FB54→51 键**（`reconstruct/0.3.2/env/ENV-CHAIN.md` 逐级键差）。
adapter 装载缝在 0.3.2 为 **beb131ab**（A6）；0.3.1 的 55b1e412 仅作历史对照。
adapter 终态装配与 87 件逐件账见 `deploy/adapter/0.3.2-ASSEMBLY.md` /
`deploy/adapter/0.3.2-MANIFEST.md5`；完整升级流程见
[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)。

## 7. boot 与四查

1. 点火（0.3.2 现役）：`ARM_TAG=r3prod ARM_ENV_FILE=~/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env SPEC=1 SPEC_EXTRA_ARGS="--prefill-decode-interval 16 --max-queued-requests 32 --min-free-slots-delay 1 --enable-decoder-swa-bounded-replay --reasoning-parser deepseek-v41 --swa-prefix-tails 256" bash tools/boot-with-slotlock.sh bash ~/migrate-assets/bin/r3-boot-arm.sh`（靴槽锁+四机容器净核）。注：wrapper 缺省锁位=`~/luz030-opt-campaign/.slot-lock`（`CAMPAIGN=<目录>` 环境变量可覆写；全新机器无该目录时先 `mkdir -p` 或设 CAMPAIGN 指向任一可写目录，否则锁文件打开失败即拒起）。
2. 沉降 600s 律（前栈拆靴→点火 ≥600s）。
3. **四查**：①health GET 200；②printenv 四机真键核（与 CBX1A env 逐字）；③横幅直读（banner29+O12/R1/FL6/page/CERT 在役态）；④面指纹四机全等（adapter/overlay/IMAGE 对表）。
3b. **起栈接线闸门**：`tools/serve_flags_gate.sh --container r3prod-head --container r3prod-worker`——从运行进程 argv 直证 A8/A9 在场 + 禁参 `--sleep-on-idle` **缺席**（UP43050-20261030：上游 #43050 idle-wake hang 规避判据）；`/health` 200 不能证明接线（静默降级），故此门 fail-closed。
4. warm 请求步 64k×2 第一动作→warm 门（64k×3 中位 ≥4500 绿/≥5000 入役绿线）。
5. **target_verify 45s 健康带（免费预测哨兵，V1 登记律）**：boot 期 `Engine startup
   timings` 的 target_verify 值健康带=**44-46s**（49s 绿/102s 红带 2/2 分离先例；
   >75s=红带靴预测——红带根治件=0.3.2 池首件候选）。**warm 门 ≥5000 入役绿线
   读数锚=5929.2 先例**（G2-RESTORE 2026-10-14 产线复绿靴实测；早期 COMBO 三靴
   6031.9-6124.5 同带）。

## 8. 验收门（定型形合格判据）

> 0.3.2 现役沿用本门判据；性能读数更新为 release note 主表（PR 七档/DE 五档），
> 池/断言/质量/水位门不变。逐步验收/性能复现命令与参考值见
> [UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §9-§10。

| 门 | 判据 |
|---|---|
| 池门 | boot 横幅池 9,600,000 |
| 断言门禁 | fail-safe PASS rows（四秩）+MISMATCH=0+16 口 idx3 |
| 性能带 | warm 门≥5000；PR 四档对定型带 ±3%；agg600k ≥3005.2 |
| 质量 | smoke 3/3；GSM8K 带；needle 3/3 |
| 水位 | WATER-RED=0（qmg 在役+02 机两守护不动红线）。**水位线三线值（boot 头注+models.d 定钉）**：V41=WATER_MARK_FLOOR **20480**（MB；四机在役 23.5-23.9G）/0731=**9216**（O13 定钉）/VL=**12288**（O13B 缺省形；48M 预测形 c24 变体=32768）。**测试段豁免注记**：qmg=窗驱动启停测试看护件，不入产线 boot 链（qmg 头注律）；02 机两守护（unit 3535/3536）绝对不动 |

任一门红→按 OPS-MANUAL 第二章双复原义务（先撤件再产线 boot）+第三章回退链处置。

## 9. VL 面部署（SGLang 基座原生视觉双臂——VL-NATIVE-20261013 窗全绿收录）

> 判读线与证据=`docs/research/VL-NATIVE-RESULT-20261013.md`（窗卡+调查档同目录）。
> VL 形**转正在役=呈裁位**（RESULT §八）——本节为已验证的部署面，非默认在役态。

### 9.1 V4.1 原生视觉臂（零旗零文件=knapcio 同构）

- 启用面=**空集**：enable_multimodal 缺省 True+auto-detect（model_type=deepseek_v41 且
  vision_n_layers>0）+处理器按类自动注册——生产文本靴同代码形态，只是流量形态之差。
- boot：`DRY_RUN=1 ARM_ENV_FILE=<VL41N 臂 env> ARM_TAG=<tag> bash tools/boot-with-slotlock.sh
  bash deploy/bin/boot_mvl41_native.sh`（DRY-RUN 先行=零集群纪律；臂 env 三级阶梯=
  `deploy/env/VL41N-SPEC0.env`（S1/S3 认证形）→`VL41N-K6.env`（L2 k6+GRAPHS0）→
  `VL41N-K6CG.env`（L3 k6+CG bs16=生产全量形，参数面与产线逐字等价））。
- 冒烟：`python3 deploy/bin/vl_smoke_gv1.py --port 8898 --out <目录> [--light]`（G-V1：
  knapcio 双形状 **1024/1024 SAT 断言**+官方 2 图对+OCR+双图计数+canary×3）。
- 51 键族零触碰律：臂 env 只含五驱动约定键，零 DSV41_* 性能键注入。

### 9.2 V4.0exp overlay 复原臂（同基座承载，替代 vLLM 容器）

- 前置：overlay 复原树落位 §5 行（`~/migrate-assets/vl-native/sglang-overlay.v4vl-79cafec0/`
  28 件；源=`deploy/overlay/v4vl-79cafec0/` rsync 四机同路径，内容指纹 cbf986df 全等）。
- boot：`DRY_RUN=1 ARM_ENV_FILE=deploy/env/VL40EXP-R2-C24T.env ARM_TAG=<tag>
  bash tools/boot-with-slotlock.sh bash deploy/bin/boot_mvl40exp_r2.sh`（C24 拓扑+水位
  20480+overlay 28 件影子挂载 fail-closed+mm 直证断言〔KV 0.10G+processors 逐机≥1，
  头位分面=勘正 4〕；臂 env `SGLANG_OVERLAY_DIR` 指针即 §5 复原树位）。
- 冒烟：同 9.1 量具（G-V5：384/图 政策=预算内动态计费判读，340<384 非帽满）。

### 9.3 网关 VL 车道（第二实例，车道制分流）

- **在役版本锚（2026-10-14 固化窗补）**：网关 proxy 现役=**rc3.8.4**
  （`/opt/aicad-prod/scripts/concurrency_proxy_v2.py` md5 **f0a47b17**，staging 同步
  同值）；**镜像内谱系=rc3.8.3（md5 31746cb1）**——差=V2b 413 透传修复+A6 留痕，
  G2-RESTORE S5 窗吸收（r3 镜像内五包指纹行载 rc3.8.3 形；kit LABEL 6df809ae
  已钉镜像内形态）。升级/回退走 gateway 包 staging 同步面（包指纹 f8322934；
  ASSET-REGISTRY CFG-07 双值并列注记）。
- 件=`tools/packages/gateway/`：`payload/units/concurrency-proxy-vl.service`（同 v2 模板
  仅 Description/EnvironmentFile 两处差=零代码改动）+`payload/env/gateway-vl.env.template`
  （8002→UPSTREAM 8898〔认证期〕/8899〔转正后〕；MAX_CONCURRENCY=8+DEDUP_ENABLE=0=图像
  大 body 前缀哈希伪碰撞规避；GW_API_KEY 值位空红线——只入宿主 0600 secrets 面）。
- 启用：env 填值落 `/opt/aicad-prod/secrets/gateway-vl.env`（0600）→unit 落
  `/etc/systemd/system/`→`daemon-reload`+`enable --now concurrency-proxy-vl`→8002=200
  核（详=包 README 部署面分发注记 5）。客户端按端口选车道（8001=文本现役不动；
  8002=VL）。

### 9.4 客户端模型发现面（/v1/models 容量四键——GW-PATCH-20261015/A10）

- **客户端读法**：harness/llm-pi-ai 族模型发现只认 `/v1/models` 条目的**四个扁平字段**
  （`context_length`/`context_window`/`max_input_tokens`/`limit.context`）；读不到 ⇒ 落
  默认窗 262144（引擎真值 600000 的 2.3 倍低估）⇒ 已完成的成功响应被判
  `CONTEXT_WINDOW_EXCEEDED` 整轮丢弃 + 每请求 `max_tokens` 被改写为 1（截断空参数
  工具调用链）。**部署要求**：网关（rc3.8.6+）侧 `ADVERTISE_MODEL_CAPACITY=1` 即
  在响应侧补四键=引擎真值（`MODELS_CONTEXT_LEN=0` 缺省）；8003 公共入口（v2.2.2+）
  名录面同带四键。**红线**：声明值恒=引擎真值，禁「调大声明消本地检测」；缺省 0=
  行为逐字节零变化（升级/回退见 `tools/packages/gateway/README.md` Mac 部署节）。
