# LuZ-deepseek-flash-all-in-one

**LuZ-0.3.1** —— DeepSeek-V4.1-Flash @ **4×NVIDIA DGX Spark（GB10，SM121）TP4
内部 RoCE 环网**全栈优化一体化交付（基于 SGLang 上游 `main-79cafec0` 的自有
优化层，许可注记见 [NOTICE](NOTICE) / [LICENSE](LICENSE)）。

---

## 一、三大模型完整性能测试报告（0.3.1 定版读数）

> 全量档=`docs/report/031-FINAL-PERF-REPORT-20261009.md`（v2 定稿）；定型形
> 服务口径读数承接 QA31 定型窗（`docs/quality/0.3.1-RELEASE-QUALITY.md` T2）。
>
> **基准与口径来源**：全部读数出自自研 **`sd_bench`**（`tools/bench/`，headless 复刻），
> 测量口径逐文件对齐社区基准 **sparkDash**（[MiaAI-Lab/sparkDash](https://github.com/MiaAI-Lab/sparkDash)）
> 并经九项定义对表审计全 PASS；PR 表=sparkDash repeated-filler 口径（跨栈可比；filler
> 虚增属性与 `real` 真文本臂见档），DE c1=单提示精确原文口径。**口径正典档=
> [docs/registry/BENCHMARK-SOURCE.md](docs/registry/BENCHMARK-SOURCE.md)**（定义源件
> md5 表/工具谱系/对表结论/使用纪律）。

### V4.1-Flash（主模型，0.3.1 定型形=50 键+SPEC6+W5 件；FL6 转正后现役=51 键，DE 82.17 见 §三）

| 指标 | 读数 | 对照 |
|---|---|---|
| **census 步墙（服务口径）** | **626.1 ms/step** | 866 基线 **−27.8%**；≤677 目标（裕度 +50.9）——收口达成 |
| **PR ②尺四档（×3 med, tok/s）** | 8k **5203.7** / 32k **6082.2** / 64k **6126.3** / 128k **5883.3** | 对组合窗 C0 ×3 四档 +0.14/+0.69/+0.60/−0.17% **全部带内（跨窗复现成立）**；128k 发布读数 5880.1 |
| **agg600k 聚合（5×200k 中位）** | **4958.5 tok/s** | 门=3005.2（ctx600k 不劣化绿；段极差 0.5% 稳态） |
| **DE c1 双点位（post 主分母）** | **81.67** | ≥80.0 收案绿（five=[81.58,81.73]） |
| **GSM8K / needle / qeval** | **0.97** / **600k 3/3** / **75/75 逐题全等** | 质量四件全绿 |
| 断言门禁 | 10/10 逐靴直证（16 口 idx3+fail-safe PASS 96 行×4 秩+banner29+池 9,600,000+MISMATCH=0） | WATER-RED=0 |

### 0731 兼容模型（decode-CG 解锁组合，STD0731-CG-R1 形）

| 指标 | 读数（2026-10-14 G2 终态复测） | 目标 | 达成 |
|---|---|---|---|
| prose（c1 ②尺） | **80.93**（80.13-81.06 超紧带；历史锚 81.22 Δ=−0.36% 带内） | 60 | **135%** |
| code（c1 ②尺） | **123.26**（122.9-123.35；历史锚 123.21 Δ=+0.04% 带内） | 104 | **119%** |
| structured（c1） | **136.0**（c8 79.21 出塌陷域） | — | 塌陷签名消失 |

决定性杠杆=decode-CG 解锁（+79.0%/+73.0%，步墙 75→50ms；pin7103136+mf 0.89+`--cuda-graph-max-bs-decode 8`）。2026-10-14 矩阵重测中 c8 域曾现 decode 回放步墙塌陷（瞬态因子，G2 复测消失；镜像 digest 分裂定谳=显示口径差异非内容漂移，详见 `docs/research/G2-RESTORE-RESULT-20261014.md`）。

### VL 兼容模型（SGLang 基座原生视觉——VL-NATIVE-20261013 窗双臂全绿）

| 面 | 读数/状态 |
|---|---|
| **V4.1-Flash 原生视觉臂** | 零旗零文件启用（knapcio 同构；51 键族零触碰）；S1-S4 三级阶梯全绿（mm×k6×CG 三共面闭合=L3 与生产参数面逐字等价）；**G-V1 冒烟 knapcio 双形状 1024/1024 SAT 断言全对**+官方 2 图对/OCR/双图计数/canary 3/3 全 200 语义对 |
| **V4.0exp VL 同基座首飞** | 归档 overlay 28 件整树复原（cbf986df×4 机全等）→SGLang 单基座承载（替代 vLLM 容器）；S5R 靴绿+G-V5 首飞全绿（384/图 政策=预算内动态计费 340<384）；矩阵文本面 prose c1 **63.93**（+1.2%）/code c1 **112.68**（−0.5%）对锚带内 |
| 网关 VL 车道 | 8002→8899 转正态第二实例在役（rc3.8.4+V1-V5 生产验证全绿：并发阶梯 429+Retry-After/大 body 四档 200 逐字对照/61.4MiB RSS 峰/断路 <10s 恢复/注入豁免字节平权/img16MB +24.8ms 呈裁带）；GW_API_KEY 已迁 EnvironmentFile 0600+轮换 47 字符（A10） |
| （历史）vLLM 基座读数 | STDVL-K6CG-R1 形 prose **63.16** / code **112.93**（decode-CG 杠杆 +79.7%/+73.6%；vLLM 基座已退役=单基座交付律，读数留档对照） |

### 0.3.1 特性构成

R1 FP4-KV in-kernel（八件面）+ W5 stage2 MXFP8/出口直聚（两键）+ E3-A SWA
召回 N=256（SPEC6 第六参）+ O12 调度间隙（三键）+ LL128 NCCL 协议（三键）+
FL6 召回修复（**51 键转正在役定版**，见 §三；FL6 面回退两级=摘键休眠/摘接线）。
键面回退链 51→50→48→47 键四级。

---

## 二、镜像下载（内网 registry 直链）

> registry=`192.168.0.202:5000`（四机可达）。指纹提取法：
> `docker inspect --format '{{index .RepoDigests 0}}' <镜像>`。

| 镜像 | 用途 | 体量 | sha256 指纹 |
|---|---|---|---|
| `192.168.0.202:5000/lmsysorg/sglang:main-79cafec0` | **现役基座**（V4.1 文本+VL 原生视觉+0731 形+V4.0exp overlay 复原臂；运行期注入 adapter/overlay/env） | 48.6GB | `sha256:0f075735a6bf913a7cc1cd7ece4f526ae8af70fc5b88fdc02d9efe92a61cf3ae` |
| `dsv41-sglang-optimized:0.2.9-ep1q2-fin2` | 优化烘焙谱系（0.2.9 现值；ep1u-fin/ep1q2f 前代） | 47.3GB | `sha256:f51d0f2ac9b47adfe4e1052682624ecd7b9ef7dbe20ebf98c4c01b1380f43b8f` |

> **历史注记（vLLM 两形，VL 线已切 SGLang 单基座——单基座交付律，不随网盘分发）**：
> `vllm/vllm-openai:LuZ0.4.5-DeepSeek-v4-Flash-DGXspark-TP4-Ring-VL-S1-20260910b`
> （sha256 `0098a90d…42c2478`，35.9GB）与 `…-VL-DGXspark-TP4-Ring`（sha256
> `357e2f8e…526f2c12`，35.9GB）——V4.0exp VL 旧承载，仅存史注。原「保留作
> 回退备份位」安排**已于 2026-10-14 清理**（用户令 GOV-CLEANUP2：dist 侧
> `vl-vllm-S1.tar` 等备份件删除，见 CHANGELOG 注记与战役仓
> `docs/ops/GOV-CLEANUP2-RESULT-20261014.md`）。

```bash
# 拉取现役基座（四机各一，或 head 拉+docker save 分发）
docker pull 192.168.0.202:5000/lmsysorg/sglang:main-79cafec0
docker inspect --format '{{index .RepoDigests 0}}' \
  192.168.0.202:5000/lmsysorg/sglang:main-79cafec0   # 指纹核对=上表 sha256
```

**网盘分发（2026-10-14 发布，离线/外发主通道）**：夸克网盘
「luz-0.3.1-release-bundle-20261014.7z」——
链接：<https://pan.quark.cn/s/42e685a8a10e>（提取码 `24zL`）。

| 包内容 | 体量 | sha256 |
|---|---|---|
| `images/dsv41-sglang-optimized-0.3.1-r3.tar`（**0.3.1 交付镜像**，load→`192.168.0.202:5000/dsv41-sglang-optimized:0.3.1-r3`） | 14.4G | `6afa44298b9a788b584abf2181495192b7252f0e4f0f2f462fbbe3ccd8941906` |
| `repo/luz-deepseek-flash-all-in-one-v0.3.1.tar.gz`（交付仓快照含 .git@cbc9a6b；其后收官增量 8be69ca 以本仓为准） | ~90M | `6a7b6b99d4f444da36f9d10368fcf0c98ccb6f6a25e3f32a4287b0aec9bf0646` |

接收端：`sha256sum -c CHECKSUMS.manifest` 全验 → `docker load` → layer cid 核对
`ffed489217c872ea`（冷构建双跑 PASS 值；差=分发面损坏）。逐件 .sha256 伴档随包，
load/校验/身份核对细则=包内 `README-DIST.md`。GitHub Releases=发布说明与渠道
汇总页（大文件不走 Release 资产，统一走网盘包）。

---

## 三、快速上手与 FL6 状态位

**形三元组**=env 键面（`deploy/env/`）+SPEC serve 六参（`deploy/SPEC6-SERVE-REF.md`）
+adapter/overlay 面（`deploy/adapter/`、`deploy/overlay/`）——三件齐一才可 boot；
**boot 四查**=health 200/printenv 四机逐字/横幅直读/面指纹四机全等。从零部署
全流程见 **[docs/DEPLOY-GUIDE.md](docs/DEPLOY-GUIDE.md)**。

**FL6 召回修复（51 键，转正在役定版）**：FL6-PROMO 转正窗已闭 GREEN——产线现役
=51 键修复形 **ENV51 `PROD-R51W5FL6-spec1.env`（2ac74586，服务器在役位名；仓内
异名同值件=`deploy/env/PROD-R51W5-FL6FIX-spec1.env`）+sitecustomize 55b1e412
+fl6_recall.py b87cbb5e 四机全等**+SPEC6+overlay o12c1-prod；8899=200 在役健康。
实役直证：**cp30 召回锚位 99.95%+DE 82.17**。回退链两级：一级=摘第 51 键（键关
=sitecustomize 休眠逐字原版行为，不动 adapter 面）；二级=摘接线（按
`sitecustomize-wire-v2.diff` 逆向回 2c4baad3 并摘 fl6_recall.py）。adapter 供给面
=B1 整面快照 83 件（`deploy/adapter/`，见其 README 收录口径）。机理档=
`docs/research/FL6-RECALL-BUG-ANALYSIS-20261013.md`。

## 四、仓库结构

> **基础设施仓**：[luxingcom/aicad-nccl-optimization](https://github.com/luxingcom/aicad-nccl-optimization)
> —— **mesh 硬件转发层全套**（[mesh-fabric/](https://github.com/luxingcom/aicad-nccl-optimization/tree/main/mesh-fabric)：
> CX-7 无交换机 RoCE 环网——拓扑生成器 plan.py/硬件 tc hairpin 规则/驱动预置
> （hairpin 8192+trust pcp）/RDMA-TX 源标记探针/systemd 引导单元对/netplan 正典/
> Q3bA 正典拓扑/守卫自愈套件/九章研究报告与三参考对照定谳）+ **NCCL 2.30.7
> ring-only 优化资料包**（allreduce −81% 补丁栈/部署指南/排障手册/doctor 工具链）。
> 本仓通信栈=该仓硬件转发层+NCCL 层 + 本仓 `deploy/nccl/`（ring-only 库+ncclpin 在役件）。
>
> **分支**：[`switch-fabric`](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/tree/switch-fabric)
> —— 交换机方案适配（双 rail 交换机拓扑下的 RoCE flat/one-shot 运行时、C 层 fabric
> 语义键、交换机形态 env 样本）；差异档见其 `deploy/SWITCH-FABRIC.md`。`main` 保持
> 环网方案形态，两方案差异件互不污染。

```
docs/        定版成果：report(终版性能报告+TOOLS31 烘焙结果)/runbook(OPS-MANUAL)/registry(FORM-REGISTRY)/
             quality(RELEASE-QUALITY 含 T2-VL 注记行)/research(FL6+红带+VL-NATIVE 三档：RESULT/
             WINCARD/SGVISION 调查)/DEPLOY-GUIDE(含 §9 VL 面部署)/
             ACKNOWLEDGEMENTS(定版 110 条：上游谱系/社区同行/官方资产/外部对照/工具田野)/
             deploy/DEADLOCK-MITIGATION-AND-FORENSICS-20261018(0.3.2 死锁规避+py-spy 取证包)
deploy/      服务面全集：env(两形+VL 四臂)/bin(r3 链+VL 双臂 boot+冒烟量具)/adapter(现役件)/
             overlay(o12c1-prod 29 件+v4vl-79cafec0 复原树 28 件)/
             nccl(ring-only 库+ncclpin)/b12x(计算树)/kit(guard/instruments)/models.d(权重注册卡)/sentinel
tools/       全树工具：packages(五包+_lib+_bake；gateway 含 VL 车道两件)/boot-with-slotlock/census 面板族/
             judge/boot_sentinel/量具与门禁脚本/patches/ssh-password-login 运维件
tests/       fl6-recall(双臂 6 测)/unit(b12x/row_store)/whitebox(14 件矩阵)
```

CHANGELOG（0.3.0→0.3.2 在途）· SCAN-REPORT（密钥扫描）· NOTICE/LICENSE（许可）

---

## 五、致谢（ACKNOWLEDGEMENTS）

**110 条借鉴源全收录**（上游 SGLang 及 PR 谱系 26/社区同行 60/官方资产 5/外部配置对照 10/工具田野情报 9）——每条带来源+借鉴内容+使用状态（采纳在役/判负留库/参照对比/政策依据）+档案锚；**判负件与反向不吸收同样如实收录**（用户点名「无论好坏、无论是否用到」）：**[docs/ACKNOWLEDGEMENTS.md](docs/ACKNOWLEDGEMENTS.md)**。
