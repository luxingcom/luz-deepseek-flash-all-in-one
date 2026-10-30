# GLOSSARY.md — 内部代号总登记（单一登记处）

> **生成日期**：2026-09-23（`luz0.2.8pre` 冻结日）
> **性质**：本项目**唯一**的"内部代号 → 含义"登记表。此前这些代号有的只有**单点图例**
> （只在一份报告的脚注里定义过一次），有的**从未被定义过**（读的人只能从上下文猜）。
> 本表把它们集中登记，并**如实标注定义强度**。
> **烘焙落点**：`/opt/dsv41/kit/GLOSSARY.md`（与本目录下的 `REFERENCE.md` 一并入镜像）。
>
> ## 口径与纪律（读表前必读）
> 1. **绝不猜测**。找不到权威定义的一律写「**未见权威定义**」并在 §4 汇总，**不许猜词**。
> 2. 每条都有 `file:line` 出处。**首次/权威出处**列优先选"真正给出定义"的那一行；
>    若该代号只有出现点而无定义，则在该列写「未见权威定义」、把出现点写进"其他出现点"。
> 3. 同一字母数字组合在**不同语境下是不同东西**——本表**分条登记**，并在"备注"里写明歧义
>    （已知至少三组：`R1/R2/R5/R6/R8/R9`、`M1~M5`、`B1~B7`，另 `R2` 有三义）。
> 4. **行号只用于冻结件/带日期的历史报告**，并必须注明「（该文件为冻结件，行号稳定）」；指向**仍在被编辑**
>    的文件，一律用**节名 / 行名 / 引文**锚定（2026-09-23 修复轮修订：原写"行号一律为实测的行号"
>    —— **那正是引用漂移的病根**：目标文件一改，登记册就集体失准）。
> 5. 代号的**含义列不追求完整**（不复制定义原文），只求"一句话能对上号 + 能把读者送到定义处"。

---

## 0. 采集范围与统计

| 项 | 值 |
|---|---|
| 采集目录 | `/home/liux***ya/w6-kit/`、`/home/liux***ya/<source-repo>/`、`/home/liux***ya/*.md` |
| 采集方法 | 按用户给定的必登清单逐项 `grep -rn` 三个树；命中后**逐条 Read 上下文**判定定义强度 |
| 登记条目数 | 表行数按 **§5 的计数命令**实测（本行不再写手抄值，避免与编辑后的行数脱钩） |
| 其中「未见权威定义」 | **10 条**（§4.1 列全；此数是本节表格的 `行数 - 1 表头`，可用 `sed -n '/### 4.1/,/### 4.2/p' GLOSSARY.md \| grep -c '^\| \*\*'` 复算） |
| 存疑 / 需上级裁决 | **4 条**（§4.2 列全；同上，`sed -n '/### 4.2/,/^---$/p' GLOSSARY.md \| grep -c '^\| \*\*'`） |
| 本次自检 | 见 §5：两表合计登记条目 **230 条**、`file:line` 引用点 **414 个**（**复算命令见 §5.1 末**）；文件不存在 / 行号超范围 **均为 0**；其中**行内出现该代号字面量 329 个**、**行内未提 85 个**（后者含"上下文引用"与仪器口径所限，**不等于是错误**，须按 §5.2 逐条看）；明细 = 本册 97 条 / 另一册（`REFERENCE.md`）133 条。⚠ **首轮登记的 244 / 464 / 335 / 129 四个数互相矛盾且用本节脚本复算不出来**（见 §5.2 首段），本轮全部换成脚本实测值 |

---

## 1. 体系 / 版本命名

| 代号 | 含义 | 首次/权威出处 | 其他出现点（file:line） | 备注 |
|---|---|---|---|---|
| **LuZ** | **产品线前缀**（镜像 tar 包名与私有 registry tag 的家族名）。含义在本项目**从未有过文字定义**——它只以命名成分出现（`LuZ-0.2.6-dsv41-tp4-dgxspark.tar.zst`、`LuZ0.4.5-DeepSeek-v4-Flash-VL-DGXspark-TP4-Ring`）。含义列=**从命名成分反推**，非权威定义。 | `~/<source-repo>/README.md` 的 `Historical release (0.2.4)` 行（`LuZ-0.2.4-dsv41-tp4-dgxspark.tar.zst`） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:5`（`LuZ-0.2.6-…tar.zst`）、`~/w6-kit/start_tp4_head_v043.sh:10`（`生产形态: LuZ-0.4.4`）、`~/w6-kit/G1R7VL-PROD-TUNING-MASTERPLAN-20260907.md:6`（`官方名 LuZ0.4.5-…-TP4-Ring`）、`~/w6-kit/a016_contrast.sh:3`（`LuZ-0.4.4-routea-016`）、`~/<source-repo>/README.md` 中 `lux***com/aicad-nccl-optimization` 那一行（`LuZ lineage`） | ★见下方「LuZ 命名关系」专节（用户点名要核） |
| **`0.2.x`（LuZ 交付版本）** | **我方交付/镜像版本号**，与 SGLang fork 自身的版本串**不是一回事**。依据：镜像 tar 名用 `0.2.x`，而镜像内 SGLang 自报 `0.0.0.dev1+ge087e662b`。 | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `Previous（历史，被 0.2.7 取代）` 行`（`SGLang 0.0.0.dev1+ge087e662b`） vs `:11`（`Current production: dsv41-sglang-optimized:0.2.4`） | `~/<source-repo>/README.md` 的 `Historical release (0.2.4)` 与 `Historical (0.1.7)` 两行（`0.2.4` / 历史 `0.1.7`） | ★**核实结论**：`0.2.x` **不是** SGLang fork 的版本号，是**我方 delivery 版本号** |
| **`0.1.7`** | LuZ 交付版本历史档（SGLang 时代早期） | `~/<source-repo>/README.md` 中 `LuZ-0.1.7-DSV41F-image.tar.zst` 那一行（`Historical (0.1.7)` → 解出 `dsv41-sglang-optimized:v7`） | `~/V41-EXTERNAL-AUDIT-40217-VERDICT-20260919.md:9`（外部站 <external-audit-ip> = `LuZ-0.1.7`） | — |
| **`0.2.4`** | LuZ 交付版本（v18 别名）；**历史锚点**（被 0.2.7 取代，后者又被 0.2.8 取代） | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `Previous（历史，被 0.2.7 取代）` 行` | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:7`（`生产锚点：v18=0.2.4`） | 镜像 ID `sha256:110d2c4e…`，125 层，内容身份 `e4fe9dc13017e5d7` |
| **`0.2.5`** | LuZ 交付版本；V3 窗销项版 | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:3`（`生产已切 0.2.5，git v0.2.5=0cc8c5c`） | — | — |
| **`0.2.6`** | LuZ 交付版本；**拍扁单层**首版，git `142edbe` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:4`（`git v0.2.6=142edbe；导出包 ~/LuZ-0.2.6-…zst 12.65GiB md5 bc08620a…`） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:13`（四机在役） | 导出包=交付物 |
| **`0.2.7`** | LuZ 交付版本；**上一代生产 pin**（0.2.8 起取代）；镜像批（`#39482` + `#40024`/`#32888` 评估） | `~/<source-repo>/image-patches/0.2.7/README.md` 的头部说明段（首行 `0.2.7 image patch set (2026-09-21)`；**不写行号**——该文件 11 行且随补丁增删变动） | `~/V41-UPSTREAM-TRIAGE-20260920.md:122`（`0.2.7 镜像批`）、`~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md:125`（复栈生产形态） | 本批曾疑为 prefill 2.25× 回退元凶 → 破案为时钟楔死，**0.2.8pre 保留原版** |
| **`luz0.2.8pre`** | **本次冻结的版本**（pre = 预发布） | 本次会话任务书（无本地文档出处） | — | 「未见权威定义」的**边界说明**：该串是本次冻结动作的名称，未在任何既有文档中出现过 |
| **`luz0.2.8`** | **本次发布的正式版本**（0.2.8pre 的正式版；相对 pre 的差异＝logits 预算 512→128 MiB、地板守卫 -f 3→1.5、kit 刷新） | `~/<source-repo>/image-patches/0.2.8/README.md`（0.2.8pre 的 sed 版） | `~/V41-LUZ028-CLOSEOUT-PLAN-20260923.md` | 内容身份见 `BUILD-IDENTITY.md` / `guard/BASELINE.md` 的 2026-09-23 条目；⚠ `0.2.8` 与 `0.2.8pre` 是两个不同 tag，勿混 |
| **`dsv41-sglang-optimized`** | **镜像名**；tag = 交付版本号 | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `## Images` 表（`Current production (生产 pin)` 行）` | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `Historical` 行`（`v14`=0.2.3 era）、`~/<source-repo>/README.md` 的 `Historical (0.1.7)` 行末（`v7`） | `v7`/`v14`/`v18` 是同一镜像名的**内部别名**（对应 0.1.7 / 0.2.3 / 0.2.4 三个交付版本） |
| **`v7` / `v14` / `v18`** | 镜像内部别名（简写），映射见上一行 | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `Historical` 行`（`v14`） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:7`（`v18=0.2.4`） | 别名的映射关系只在上述少数几行里给出，**没有单一映射表** |
| **`dev-dsv41`** | **基座镜像 tag**（`lmsysorg/sglang:dev-dsv41`）；可变上游 tag | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `Base` 行` | `~/V41-EXTERNAL-AUDIT-40217-VERDICT-20260919.md:9`（外部站与我们**同 fork 基线** `0.0.0.dev1+gda64c5cbb`） | 无 repo digest；重烘前须自行 pin 镜像 ID（``~/<source-repo>/BUILD-IDENTITY.md` 的 `Current production (生产 pin)` 行`） |
| **`w6-kit`** | **四机各自的运维工具箱目录**（`~/w6-kit/`，在 <node01>..<node04> 各一份）。承载守卫/量具/发布件/历史包；**不是应用仓库**。 | `~/w6-kit/README.md:1`（标题：四机运维工具箱） | `~/w6-kit/README.md:3`（位置=四机各自的 `~/w6-kit/`）、`:13`（承载三类东西）、`:23`（生产配置在 `~/<source-repo>/`）、`:27`（**同名副本分叉是真实发生过的失效**） | 名字里的 `w6` **未见权威定义**（见 §4） |
| **`<source-repo>`** | **生产仓**（配置与镜像构建的唯一事实来源） | `~/w6-kit/README.md:23`（`生产仓是唯一事实来源`） | ``~/<source-repo>/BUILD-IDENTITY.md` 的标题与引言段` | `w6-kit` 里出现第二份 `.env.tp4` ⇒ 分叉 |
| **`.env.tp4-600k` / `ctx600k`** | 600K 上下文形态的 env 文件与 overlay 目录（`sglang-overlay.ctx600k*`） | `~/V41-CTX600K-READINESS-20260922.md:66`（`.env.tp4-600k budget 512MiB→128MiB`） | `~/<source-repo>/sglang-overlay.ctx600k-probe/scheduler.py:1803`（`CTX600K 诊断钩子`）、`~/V41-R3-WINDOW-INCIDENT-AND-ATTRIBUTION-20260922.md:114`（`--kv-cache-memory` 锁池）、`~/ops-handoff-20260921/03-SEQ-服务器评估与操作时序.md:41`（`ctx=147456 封顶（>128K 结构性 HTTP 400）`） | overlay 有多个变体：`ctx600k` / `ctx600k-probe` / `ctx600k-mmban` / `ctx600k-oldpool` / `diag` |
| **拍扁单层 / 内容身份 / 层天花板 125** | 镜像层纪律：层数上限 **125**（126 实测被拒）；增量一律走 `export`→`import --change` 拍扁配方；跨机一致性比 `join(RootFS.Layers)` 的**内容身份**而非镜像 `.Id` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:78-80`（条款 11：镜像拍扁条款） | ``~/<source-repo>/BUILD-IDENTITY.md` 的 `Previous（历史，被 0.2.7 取代）` 行`（`content-identity (join RootFS.Layers) = e4fe9dc13017e5d7`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:107`（`镜像层天花板复核=125 安全线`） | — |
| **`g1r7`** | **历史构建轮次代号**（vLLM 时代）：`G1R3`…`G1R7` 各轮构建/上下文目录的**末轮**；`G1R7VL` 是其中的 **VL（视觉）分支线** | `~/w6-kit/README.md:149`（`g1r3-build/ … g1r7-build/… \| G1r3–G1R7 各轮构建/上下文目录`） | `~/w6-kit/G1R7VL-W1-REPORT-20260902.md:1`（`# G1R7-VL W1 报告 — 文本等价门全绿 + 06:14 事故附录`）、`~/w6-kit/G1R7VL-WINDOW2-REPORT-20260908.md:1`（`G1R7-VL 窗口#2 报告`）、`~/w6-kit/G1R7VL-BASELINE-DELIVERY-20260908.md:1`（`VL 版本基线交付报告`，文件名即 `G1R7VL-BASELINE-DELIVERY`） | 目录名至今留在 `~/w6-kit/` 下（`g1r3-build/`…`g1r7-build/`，历史件，~20 MB） |
| **`w9r4`** | **历史窗口/轮次代号**（W9 系列的第 R4 轮）：MTP 定版那次接管调查；其**交付规程**至今在役（四机重启必须走 `w9r4_restart_guard.sh`） | `~/w9-evidence/w9r4/W9-R4-TAKEOVER-REPORT.md:1`（`# W9-R4 接管调查最终报告 — vllm0.28(实为fork) vs 0.26 生产性能退化深查`） | `~/w9-evidence/w9r4/W9-R4-TAKEOVER-REPORT.md:2`（`**接管人**: W9-R4 会话 \| **日期**: 2026-08-29`）、`:62`（`w9r4_s2_baseline.sh`）、`~/w6-kit/start_tp4_worker_v043.sh:8`（`全参数 dossier: w9-evidence/w9r4/W9-R8-PARAMETER-DOSSIER.md`）、`~/V41-OPTIMIZATION-MASTER-TASKPLAN-20260915.md:97`（`必须走 w9r4_restart_guard.sh（flock 互斥）`）、`~/w6-kit/README.md:152`（`bench3/`、`w8-evidence/`、`w9-evidence/`） | `W9-R4-TAKEOVER-REPORT.md` 实测共 **2 份**：`~/w9-evidence/w9r4/`（正本）与 `~/w6-archive-repo/docs/evidence-snapshot/`（归档快照）。⚠ 原登记称"`w6-kit` 的 `w9-evidence` 下也有一份 `w9r4` 副本"——**实测不存在**：`~/w6-kit/w9-evidence/` 下只有 `w9r2/`（2026-09-23 `ls -R` 实测） |
| **`GLM`** | 外部对照配方：`GLM-5.3-Flash-NVFP4-1M-KV-4x-DGX-Spark`（第三方在 4×DGX Spark 上的 NVFP4 KV 配方，含 Lane A/Lane B 对比） | `~/w6-kit/reference/GLM-5.3-Flash-NVFP4-1M-KV-4x-DGX-Spark/README.md:33`（`Lane A — fp8 KV` / `Lane B — NVFP4 KV`） | `~/<source-repo>/README.md` 中 `Full six-stack comparison incl. LuZ / Vision-Exp / GLM` 那一行（`六栈对比 incl. LuZ / Vision-Exp / GLM`） | 属 `w6-kit/reference/` 第三方配方树（REFERENCE.md §0 声明为**不登记其内部编号**） |
| **`Mia` / `MiaAI`** | 最接近的**同硬件同侪**（SGLang `dev-dsv41` 同源 fork，中文团队的部署） | `~/V41-UPSTREAM-TRIAGE-20260920.md:94`（`MiaAI（09-19，最接近的同侪）`） | `~/V41-UPSTREAM-TRIAGE-20260920.md:94`（`MiaAI（09-19，最接近的同侪）`）、`:23`（`mixed-chunk+interval 4 ✓（社区甜点，Mia 反而没有）`）、`~/w6-kit/guard/BASELINE.md` 的「2026-09-16 三次更新（步骤 9 判决 NOGO + 步骤 0 定谳 + 新增 arch 体检）」节 → 「旧台账把 MIA 那份 SGLang 的默认形态记成了"我方待回收"——串了坐标」句（**不写行号**：该册属主仍在改；原登记写 `:101`，实测已位移） | `Mia` 与 `MiaAI` 指同一方 |
| **`tonyd2wild`** | 外部社区发布者（EXL3 量化 + GB10 实测，含 15h prefill −30% 重启恢复、无投机 boot6 干净证据） | `~/V41-UPSTREAM-TRIAGE-20260920.md:99` | `~/V41-R8-WINDOW-REPORT-20260913.md:139`（`tonyd2wild 的 8/8+30/30 干净证据出自其无投机 boot6`） | 只在**外部对照**语境出现，非我方组件 |

### 1.x ★LuZ 命名关系（用户点名要核的一条）

**问题**：`LuZ` 与 `0.2.x` 是什么关系？`0.2.x` 是不是 SGLang fork 的版本号？

**核实结论（全部有出处）**：

1. **`LuZ` = 产品线前缀**，出现在镜像 tar 包名与私有 registry tag 的家族位上：
   `LuZ-0.2.4-dsv41-tp4-dgxspark.tar.zst`（`~/<source-repo>/README.md` 的 `Historical release (0.2.4)` 行）、
   `LuZ-0.2.6-…tar.zst`（`~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:5`）、
   历史的 `LuZ-0.3.1` / `LuZ-0.4.4` / `LuZ0.4.5-…`（`~/w6-kit/start_tp4_head_v043.sh:10,49`）。
2. **`0.2.x` 是「LuZ 交付版本」**，不是 SGLang fork 的版本：
   - 镜像 tar 名用 `0.2.x`（上面几行）；
   - 而同**一个镜像内** SGLang 自报版本是 **`0.0.0.dev1+ge087e662b`**（``~/<source-repo>/BUILD-IDENTITY.md` 的 `Previous（历史，被 0.2.7 取代）` 行`）；
   - ⇒ 两者是**两条独立编号线**。
3. **两个时代的命名形态不同**：vLLM 时代 `LuZ0.4.x`（**无** `-` 与 `-dsv41-tp4-dgxspark` 后缀，且是 registry tag：
   `<registry-host>:5000/vllm/vllm-openai:LuZ-0.4.4-routea-016`，`~/w6-kit/a016_contrast.sh:3`）；
   SGLang 时代 `LuZ-0.2.x-dsv41-tp4-dgxspark`（tar 包名，`dsv41`/`tp4`/`dgxspark` 后缀标识栈与拓扑）。
   ⇒ **`0.4.x` 与 `0.2.x` 不是同一编号线的连续版本**，是两代产品线各起的一套版本号。
4. **诚实标注**：`LuZ` 这个词本身的**词源/全称在本项目任何文档里都没有定义**（grep 三个树无
   展开式），本表只登记其**命名职能**，不猜词义。

**未解**：`LuZ` 内部两个时代的版本号是否共享同一套编号体系（`0.4.x` 与 `0.2.x` 谁在前），
**无任何文档说明**——从时间线看 vLLM 时代（0.4.x，2026-08~09）早于 SGLang 时代（0.2.x，2026-09），
但这是**从日期推断**，不是文档结论。

---

## 2. 任务与审核编号

> 本节的编号绝大多数**只在单个计划文档内有效**（"计划内的任务卡编号"），跨文档引用时会串。
> 凡是能确定"哪一份计划里的编号"的，都写在出处列。

| 代号 | 含义 | 首次/权威出处 | 其他出现点（file:line） | 备注 |
|---|---|---|---|---|
| **`T1`~`T7c`** | **优化总计划的任务卡编号**（V3 批次 1-7 与 V4 轨 7A/7B）。`T1`=#40217 mask→blockID 移植；`T4`=wo_a fp8 重打包 + lm_head 双遍合并；`T5`/`U2`=FlashInfer #5197；`T7a`=chat-vs-native 通道差；`T7b`=chunk 边界台阶定谳；`T7c`=prefill 桶单变量 A/B | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:24-28`（T1-T5 卡） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:36-40`（W2/T4/T3-h/T5/U2/Z6/N2）、`:47-50`（T7c/T7a）、`:29`（`T7b 定谳`） | `T3` 有**两次含义变更**：原 dense bake-off → 转 `T3-harness`（`V4:62`） |
| **`Z1`~`Z7`** | 零窗批次任务（Z=零窗）。`Z1`=F1 kineto 步时实测；`Z2`=F2 engram 统计 patch；`Z3`=A3 残留核查；`Z4`=D4-sub3；`Z5`=D3 #38792 selective rebase；`Z6`=PREFILL_SHARE_TOKENS 份额门 A/B | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:34-39` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:40`（Z6） | 用户清单里写的 `Z1~Z7`，在 V3 里只列到 **Z6**（`Z7` **未见**） |
| **`W1`~`W4`** | V3 §2·F 车道的窗口任务（W=Window）。`W1`=GPU 时钟行为审计；`W2`=comm/compute overlap（#38792=D3）；`W3`=并发长档调度劣化归因 | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:82-84` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:36`（W2）、`:64`（W1 已关账） | ⚠ **与历史 `W1/W2` 撞号**：`~/V41-R7-W1W2-WINDOW-REPORT-20260913.md:1` 里的 W1/W2 是**另一个**窗口任务对 |
| **`N1`~`N7`** | **N 车道（网络/通信面）**任务。`N3`=四机 nccl-tests all_reduce_perf；`N5`=判决翻案臂（NCHANNELS/BUFFSIZE/LL128）；`N6`=拓扑比选（用户决策项） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:57-68`（批次 5 全表） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:56-58`（N6 决策项） | 用户清单里的 `N1` 在 V3 表中**未列**（从 N2 起） |
| **`U1`~`U3`** | **上游跟踪**任务（U=Upstream），"合并即复评、零自研成本"。`U1`=compact verify 切换（触发=#39257 或 #40162 合并）；`U2`=FlashInfer #5197；`U3`=b12x master 动向 | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:41-47` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:39`（T5/U2） | `U1 门`在 ctx600k 语境另指"compact 路线的前置门"（`~/V41-UPSTREAM-TRIAGE-20260920.md:40`） |
| **`C1`~`C3`** | **合规与交付**任务（C=Compliance）。`C1`=LuZ NCCL shim 许可处置（已销项）；`C2`=b12x"非生产用途"自述法务口径；`C3`=文档口径清理 | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:53-55`（C1/C2/C3 三行） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:64`（C1 已关闭） | ⚠ 与外部对照语境里的 `C1`（外部站点 C1 边际延迟）**同形不同义** |
| **`F1`~`F6`** | V3 §2·F 车道（第三方两包对照产出）。`F1`=boot.py 热机补 ≥8192-token 档；`F4`=worker CODE_VOL 存在性检查；`F6`=DE 分段速率工具（后升级为「chunk 边界混批丢失」机理） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:76-81` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:48`（`F6 三靴定方差+empty_cache 16384 A/B`）、`:63`（F1-F6 已关闭） | ⚠ `F1` 与**Lane F 的 F1**（kineto 测量债）是同一批编号，但与 `FIX-A/B/D` 系列**无关** |
| **`H1`~`H10`** | **批次 7 · H 车道「防静默自反馈」10 项**。`H1`=alert() 加 GUARD_ALERT_HOOK；`H3`=崩溃循环出声（OnFailure + NRestarts 断言）；`H5`=oom_gate 日志迁出 /tmp + shout()；`H9`=journalctl 假零防护 | `~/V41-BATCH7-HLANE-REPORT-20260920.md:23-32`（H1-H10 全表） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:25`（`H 车道 H1-H10 \| 防静默自反馈`）、`~/V41-BATCH7-HLANE-REPORT-20260920.md:6`（17 个静默失败点）、`~/w6-kit/guard/guardctl.sh:67`（`2026-09-20 H1：可选 webhook 出口`）、`~/w6-kit/guard/BASELINE.md` 的「2026-09-20 台账更新（批次 7 · H 车道）」节 → `guardctl.sh` 行（H1/H3 落地） | ⚠ **另有一套 `H1~H3` 是交叉审核 inline 编号**（见下条） |
| **`H1`/`H3`/`I1`（guardctl inline audit ID）** | 写在**脚本注释里**的**交叉审核发现编号**，指向 2026-09-17 前后三份 REVIEW 的条目。`guardctl.sh:67` 的 `H1` 与 `:407`/`:664` 的 `H3` 指批次 7 H 车道；`:1257` 的 `I1` 指交叉审核改进项 I1 | `~/w6-kit/guard/guardctl.sh:1257`（`才被发现（2026-09-17 交叉审核 I1）`） | `~/w6-kit/guard/guardctl.sh:67`、`:407`、`:664` | 脚本里的 `H*`/`I*` 是**注释标签**，不带前缀会与计划编号混 |
| **`B1`~`B4`（交叉审核）** | **2026-09-17 交叉审核的"会沉默的缺陷"编号**（B=blocking）。`B1`=`required=no` 的守卫打印 FAIL 却报 ALL-OK；`B2`=`role=all` 的行永不被判定；`B3`=停泊的 RECOVERY 链脚本被渲染成 PASS；`B4`=`guard/README.md` **§9「与启动脚本的集成」**的接线指错位置。**序列止于 B4**（`B5`~`B7` 三树零命中，见 §4.1） | `~/w6-kit/guard/BASELINE.md` 的「2026-09-17 五次更新」节 → `guardctl.sh` 行（B1/B2/B3 逐条）、同行表内 `README.md` 行（B4） | `~/w6-kit/guard/BASELINE.md` 同节的 `healthcheck-rebuild.sh（01）` 行（`停泊桩在 01 上挂了 6 天…（B3）`）、`~/w6-kit/guard/guardctl.sh:459` | ⚠ 与 `B1′`（campaign 的 MBT 8192 任务）**不同套** |
| **`B1′`（campaign）** | campaign 任务卡「MBT 8192」 | `~/V41-CAMPAIGN-SCORECARD-20260912.md:15`（`④ B1′ MBT 8192`） | — | 判决 FAIL 关账 |
| **`I1`~`I12`（交叉审核）** | 交叉审核**改进项**（不阻断，附理由）。`I1`=`watch` 纳入 RECOVERY 链；`I3`=止损守护 role 改 all；`I5`=`proc` 期望值非整数 → SKIP；`I8`=引擎加载期 `/health` 5xx → SKIP；`I12`=oneshot+RemainAfterExit 分支不可达 | `~/w6-kit/guard/BASELINE.md` 的「2026-09-17 五次更新」节 → `guardctl.sh` 行（I1/I3/I5/I8/I12 逐条） | `~/w6-kit/guard/guardctl.sh:1257`（I1）、`~/w6-kit/guard/BASELINE.md` 的「2026-09-17 四次更新」节 → `guardctl.sh` 行末的（`⑧SKIP 升为一等结论`） | 权威出处另见 `~/r4-ops-work/r9-ops-20260914/evidence/crossreview-20260917/REVIEW-GOVERNANCE.md:157`（`## 改进项（不阻断，附理由）`） |
| **`P0`~`P3`（审计猎杀分级）** | **审计任务的分级标签**（P=优先级），用于给并行只读子代理下发"猎杀列表 + 分级" | `~/ops-handoff-20260921/01-CODE-CHANGES.md:153`（`各自拿到…猎杀列表 + P0-P3 分级`） | — | **只有单点图例**（一处提到分级存在，未给分级定义表） |
| **`P0-0` / `P0′`** | 落地计划 v1 的方案号（`P0-0`=S1 接线（写操作）；`P0′`=启动失败只读诊断） | `~/v41-manual/stage/01-plan/v41-landing-plan-2026-09-11.md:735`（Rev.3 修订表） | — | `P0′` 属**落地计划**套，与 `P0~P3` 分级、`P0-A` 归因**三套不同** |
| **`P0-A`** | **「两层归因」任务**（37ms 停顿的两层归因，用于线 A 设计） | `~/V41-P0A-ATTRIBUTION-20260912.md:1`（标题） | `~/V41-CAMPAIGN-SCORECARD-20260912.md:32`（`P0-A 两层归因 ✅（午收口）`）、`~/v41-campaign-bprime/E-ASYNC-DESIGN-20260912.md:3`（`基于 … 逐行研读 + P0-A 两层实测`）、`~/V41-R8-WINDOW-REPORT-20260913.md:12`（`P0-A 口径代价 eager 30 vs 图 40 tok/s`） | — |
| **`Q1`~`Q7`** | **现场取证问题清单编号**（Q=Question）。已找到的：`Q1–Q4` = engram-c 侧现场取证探针；`Q2`/`Q2b`/`Q4` 有对应脚本名 | `~/v41-operators-engramc-20260912/engram-c-handover-2026-09-12/reports/engram-c-optimization-handover-2026-09-12.md:591`（`Q1–Q4 现场取证`） | `~/v41-operators-engramc-20260912/engram-c-handover-2026-09-12/reports/engram-c-optimization-handover-2026-09-12.md:109`（`含本轮 Q1–Q4 + M1–M5 现场取证脚本`） | 用户清单写 `Q1~Q7`，本地**只找到 Q1–Q4**；`Q5~Q7` **未见权威定义** |
| **`M1`~`M5`（engram-c 取证）** | **engram-c 的现场取证脚本编号**（名无关取证）：`_m1_detector_validate.py` / `_m2_pool_evidence.py` / `_m3_perthread_io.py` / `_m4_syscall_catch.py` / `_m5_concurrency.py` | `~/v41-operators-engramc-20260912/engram-c-handover-2026-09-12/reports/engram-c-optimization-handover-2026-09-12.md:592` | 同上 `:109` | ⚠ 与 **CHUNK8192 COMPENDIUM 的 `M8`/`M4`/`M6`/`M9`/`M10`**（见 §3 条目）**不同套** |
| **`D1`~`D6`** | **R4「缺失算子」交接的开发清单**（D=Develop），交运营开发；`D1` 为唯一"全套资料已齐、可立即开工"的成熟主体 | `~/r4-ops-handoff/r4-missing-ops-handoff-2026-09-13/01-交付文档/README-R4-缺失算子挑选与放弃.md:18`（`交运营开发 6 项（D1–D6）`） | `~/V41-R4-OPS-TRACK-PLAN-20260913.md:18`、`~/V41-R4-OPS-MASTER-PLAN-20260913.md:12` | 同套另有 **`X1`~`X8` 放弃清单** |
| **`D3` / `D4-sub3`** | 与 `D1~D6` **同一套**的开发项：`D3`=#38792 selective rebase（SM120 direct SWA KV + FP8 wo_a）；`D4-sub3`=MXFP8 quant 融进 combine+norm epilogue | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:38`（Z5=D3 #38792）、`:37`（Z4=D4-sub3） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:36`（`W2 comm/compute overlap（#38792=D3）`） | — |
| **`O1`~`O6`** | **算子全景与回退台账**的条目编号（台账记 17 条判负 + O1-O6） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:6`（`17 条判负+O1-O6`） | `~/V41-CAMPAIGN-SESSION2-20260912.md:123`（`O1/O2 表述与计数` 勘误） | 台账本体=`~/V41-OPERATOR-INVENTORY-AND-ROLLBACK-LEDGER-20260919.md` |
| **`O5`** | 台账条目 O5 = `PREFILL_SHARE_TOKENS` 份额门（Z6 的 A/B 对象） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:39`（`Z6 PREFILL_SHARE_TOKENS 份额门 A/B（O5）`） | — | — |
| **`Lane A`~`Lane F`** | **行动全貌追踪的六条"车道"**（工作流分组）。`Lane A`=7 项；`Lane B`=chunk 档 4 档（2048/4096/6144/8192）；`Lane C`=pin 阶梯（3.5M→8M→9.6M）；`Lane D`=上游 cherry-pick 预研；`Lane E`=预算旋钮；`Lane F`=测量/工具 | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:13`（六车道判决率一句话全表） | `~/V41-SGLANG-OPS-ROUND2-20260914.md:16`（`Lane D 上游 cherry-pick 预研`）、`:73`（Lane D 预研产物）、`~/V41-FULLPATH-REVIEW-20260916.md:66`（`Lane D Wave1+2+3 全在役`） | ⚠ `Lane A/B` 与 **GLM 配方的 Lane A/B（fp8 KV vs NVFP4 KV）** 同形不同义 |
| **`Lane D Wave 1/2/3`** | Lane D **上游 cherry-pick 的三波批次**（按风险递增）。Wave 1=#38409+#39370-sub1+#39138 三连（✅已转正）；Wave 2=#39420 流序单流化（`WAVE2-VERDICT.md`）；Wave 3=#39187+#38979（`WAVE3-VERDICT.md`） | `~/V41-SGLANG-OPS-ROUND2-20260914.md:93`（Wave1）、`:158`（Wave 2 GO 转正）、`:170`（Wave 3） | `~/V41-SGLANG-OPS-ROUND2-20260914.md:98`（`Lane D Wave2 #39420 → Wave3 #39187/#38979`）、`~/r4-ops-work/r9-ops-20260914/evidence/lane-d/WAVE3-VERDICT.md:1`（标题）、`~/<source-repo>/start.sh` 中 `Lane D Wave 1 (2026-09-15, r9-ops)` / `Lane D Wave 2 (2026-09-15, r9-ops)` / `Lane D Wave 3 (2026-09-15, r9-ops)` 三行注释 | 波次内容已全部落到 `start.sh` 的在役注释里 |
| **`R1`~`R9`（轮次报告）** | **报告轮次编号**（R=Round），对应 `V41-R<N>-*.md` 系列文件名。已见：R3、R4、R5、R5B、R6、R7、R8、R9 | `~/V41-R4-OPS-MASTER-PLAN-20260913.md:1` | `~/V41-R7-MASTER-ACTION-PLAN-20260913.md:1`、`~/V41-R8-WINDOW-REPORT-20260913.md:1`、`~/w6-kit/guard/BASELINE.md` 的「2026-09-19（下午）：v10 上线」节 → `v9 事故翻案` 行（`R9 档案已知的偶发慢靴`）、`~/V41-R3-FOLLOWUP-AND-LEVERS-20260922.md:1` | ⚠ **`R2` 在本套里缺号**（没有 `V41-R2-*.md`），`R1` 亦无；**`R2` 被另外两套占用**（见下两条） |
| **`R1`/`R2`（ctx600k 源码修复项）** | **完全不同的另一套**：`R1`=`indexer.py` 的 row-chunk 修复（**已判死**：与镜像的 111 行差异全落在 `C4Indexer` 死分支）；`R2`=**page_table 页数网格**（`SGLANG_DSV4_PAGETABLE_PAGES_GRID=1`，形状 `[q,np]`→`[q,np_alloc]`） | `~/V41-CTX600K-READINESS-20260922.md:82`（`indexer.py(R1) 与镜像的 111 行差异全部落在 C4Indexer 死分支`） | `~/V41-CTX600K-READINESS-20260922.md:41`（`R2 已写好未部署`）、`:67`（`R2（page_table 页数网格）— 本轮关闭`）、`~/V41-R3-WINDOW-INCIDENT-AND-ATTRIBUTION-20260922.md:114` | ★**三义警告**：这里的 `R1/R2` 是**源码修复补丁号**，与报告轮次、与"第二轮优化计划"都不相干 |
| **`R2`（第二轮优化计划）** | **第三义**：`V41-CAMPAIGN-PLAN-R2-20260913.md` 的"R2 轮"计划（campaign 第二轮） | `~/V41-CAMPAIGN-PLAN-R2-20260913.md:1`（标题） | `~/w6-kit/...`（无）、`~/v41-campaign-bprime/r2-round-20260913/`（目录名） | ★用户清单里要求"与 `R2=indexer 宽度门` 区分"——**实测 `R2` 有三义**：①ctx600k 的 page_table 页数网格（**不是"indexer 宽度门"**）②campaign 第二轮计划 ③（缺号的）报告轮次 R2。用户记忆里的"indexer 宽度门"对应的是 **R1**（indexer.py 行块）那一侧，**编号记反了**——本表如实登记 |
| **`R5B`** | 非 torch 内存 + SGLang 的 R5 附轮 | `~/V41-R5B-NONTORCH-AND-SGLANG-20260913.md:1` | — | — |
| **`变更 #12`~`变更 #17`** | **生产配置变更的流水号**（`变更 #N`）。`#12`=pin 定档 8,000,000；`#13`=删两个死 flag；`#14`=慢靴事故改判（靴态）；`#15`=**NSEQ 12→16（+ pin 8M→9.6M）**；`#16`=**indexer 瞬态预算收紧（`DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES` 2GiB→512MiB）**；`#17`=身份索引缓冲图捕获修复 | `~/V41-SGLANG-SESSION-DOSSIER-20260916.md:56-59`（#10/#15/#16 对照表） | `~/w6-kit/guard/BASELINE.md` 的「2026-09-16 二次更新（变更 #15：NSEQ 16 + pin 9.6M）」节（原登记写 `:54`——该节标题未变，行号已漂）、`~/w6-kit/guard/guards.conf` 的 `oom-gate-floor` 行（`★2026-09-16 变更 #16 定档`）、`~/w6-kit/guard/BASELINE.md` 同节内 `guards.conf`/`.env.tp4` 两行（= 变更 #15 的 pin/NSEQ 前置；原登记写 `:132-133`，实测该处是分隔线，已改指） 、`~/V41-CED-OPTIMIZATION-REPORT-V2-20260916.md:5`（`变更 #12/#13`）、`~/V41-SGLANG-SESSION-DOSSIER-20260916.md:115`（变更 #17） | **权威流水登记在 `SESSION-DOSSIER`**；`guards.conf` 的 `oom-gate-floor`/`sglang-pin`/`sglang-nseq` 行是**执行侧**的引用 |
| **`ADR-004`** | **架构决策记录 004**：「内存地板守卫」（解释为什么用 `eff_idle` 口径、为什么止损线是 1.5 GiB——2026-09-23 由 3 下调，见其 §0.1） | `~/w6-kit/adr/ADR-004-three-gib-floor-guard.md` 的**标题行**（`# ADR-004：以 eff_idle ≥ 1.5 GiB 作为…`）、「编号」表行 | `~/w6-kit/WINDOW-RUNBOOK.md` **「参考」节的 `adr/ADR-004-three-gib-floor-guard.md` 索引行**（`为什么是 eff_idle、为什么止损线是 1.5 GiB`）、WINDOW-RUNBOOK **开篇索引的「内存地板守卫」行**、WINDOW-RUNBOOK **「窗口内」检查表的 `记 guard_stop(ADR-004)` 项**、`~/w6-kit/v41_dose_ladder.sh` 的 `note="$note,guard_stop(ADR-004)"` 行、`~/w6-kit/oom-gate/oom_gate.sh.pre-e-tier-20260918:133`（`地板击穿 ⇒ 自动 docker stop…（ADR-004 止损）`；**该文件为冻结件 = pre-e-tier 历史副本，行号稳定，故保留行号**）、`~/w6-kit/README.md` 的**量具索引表** → `oom-gate/oom_gate.sh.pre-e-tier-20260918` 行（自述"`ADR-004` 引用在 `:133`"；**不写行号**：该册 2026-09-23 02:13 仍在改）、`~/w6-kit/adr/ADR-004-three-gib-floor-guard.md` 的「本文件日期」表行（自述"此前无定义"） | **该文件已存在**（同僚新建）⇒ 指针是活的。此前状态：`ADR-004` 在多个脚本/文档里被引用而**定义文件缺失**，本 ADR 自述了这段历史 |
| **`eff_idle` / 内存地板（1.5 GiB）** | 有效空闲口径与守卫地板值：`eff_idle = MemFree + Cached + SReclaimable − Shmem`；`-f`（止损线）= **1.5 GiB**（2026-09-23 起；原 3） | `~/w6-kit/adr/ADR-004-three-gib-floor-guard.md` 的标题行 + **§2 决策的四条线表**（`-e 1` 应急线行） | `~/w6-kit/guard/guards.conf` 的 `oom-gate-floor` 行（`-w 6（警戒线） + -f 1.5（止损线） + -e 1（应急线）`）、`~/w6-kit/guard/BASELINE.md` 的「2026-09-16 三次更新」节 → 「⚠️ 更正上一节的一句话」小节（`守护地板维持 -f 3，不得因"将来能买回 4.5 GiB"而松劲`）、同小节末句（`不要再把 Mlocked/Shmem 当"待回收量"`） | — |
| **`WINDOW-RUNBOOK §5`** | **「停泊与放行顺序」**（开窗/收窗时先 hold 谁、后 release 谁）。`§5.3` = **两个裸进程守卫的重挂**（`oom_gate.sh monitor` / `guardctl.sh watch`） | `~/w6-kit/WINDOW-RUNBOOK.md` **§5「停泊与放行顺序（hold / release）」**（正文含 `§5.1`/`§5.2`/`§5.3`/`§5.4`） | `~/w6-kit/guard/guards.conf` 的 `guard-watch` 行（`重挂命令见同一份 §5.3`） | — |
| **`WINDOW-RUNBOOK §7`** | **「时钟健康预检」**（起栈前查 GPU 时钟是否被钉/降频） | `~/w6-kit/WINDOW-RUNBOOK.md` **§7「时钟健康预检（开窗前必做）」**（正文含 `§7.1`~`§7.5`） | `~/w6-kit/guard/guards.conf` 的 `guard-watch` 行（`见 WINDOW-RUNBOOK §7`） | ★**原报的交叉引用错位，2026-09-23 已由 `guards.conf` 属主就地校准**：原 `guards.conf` 的 `guard-watch` 行注释（当时记作 `:123`，**该册同日注释级改动后已位移，此处只作历史记录、不复指**）写「见 §7」而语境是「**已知缺口**」——缺口本体在 **§7.5**、重挂命令在 **§5.3**。属主已改注释为"裸进程缺口 = §7.5、重挂命令 = §5.3"并自记"原写「§7」「§5」"（`guard-watch` 行上方注释块）。⇒ **本册原始发现成立、现已消解**；引用该缺口请按 `guard-watch` 行名定位 |
| **`attempt13`** | **vLLM 时代第 13 次重建尝试**（一次 CUDA OOM 事件/一套扫描参数），是 `v41_devfree_host.sh` 设计动机的来源 | `~/w6-kit/v41_devfree_host.sh:11`（`（attempt13 的 worker init CUDA OOM 真死因）`） | `~/v41-manual/stage/02-audit/v41-audit-engineer-2026-09-12.md:358-359`（`重建者已定位`…`attempt13 的 vllm serve 实参`）、`:515`（`生产无锁、被 attempt13 扫描反复重建`）、`:577`（`attempt13 的最终结果`）、`~/V41-R4-OPS-MASTER-PLAN-20260913.md:133`（`attempt13 CUDA OOM 真因`）、`~/V41-R6-LONGGAME-OPTIONS-20260913.md:25`（`attempt13 真因`）、`~/v41-manual/stage/02-audit/v41-prod-kv-oom-rca-2026-09-12.md:440-441`（两个 `attempt13.log` 文件） | 编号来源=当时那轮**有编号的重建尝试序列**；序列本体（1..13）**未见权威定义表** |
| **`Boot2`~`Boot6`（靴次编号）** | **同一天的"第 N 次起栈"**（剂量阶梯/窗口内的靴次序号），用于跨靴对照。`Boot6` 是 ctx600k 形态之前的一靴（ctx147456、旧代码）；`boot5` OOM 是 2026-09-14 的一次事件 | `~/V41-CTX600K-READINESS-20260922.md:185`（`Boot6（ctx147456）125K 档 drain 台账 = 总 7.69 G`） | `~/V41-CTX600K-READINESS-20260922.md:66`（`性能账 Boot6 实测 PR ≤1%/DE 零/PRv3=4830`）、`:112`（`Boot6（ctx147456、旧代码）在 125K 档的同类增量是 2/2/3/1`）、`~/v41-campaign-bprime/r2-round-20260913/launcher-b7/v41_b7_launch.sh:126`（`DEFAULT=1 since the 2026-09-14 boot5 OOM`）、`:395`（`[2026-09-14 boot5] built-in per-host watchdog`）、`~/V41-R8-WINDOW-REPORT-20260913.md:180`（`boot4 待 A23 包络验证`）、`~/V41-SGLANG-REDEPLOY-20260914.md:69`（`launch.json/serve-boot3.log…`）、`:91`（`boot4 NCCL 日志交叉验证`） | ★**未见集中登记表**：`Boot3/4/5/6` 的编号只在各报告的上下文里出现，**没有一处给出"Boot N = 哪一靴"的完整对照表**。可确定：`boot3` 有 `serve-boot3.log`、`boot4` 有 NCCL 日志与 A23 包络、`boot5`=2026-09-14 OOM 靴、`boot6`=FI07 质量臂靴。**Boot2 只做过一次引用**（`V4:16` 的 `8192-C1: 2383（boot2）`），`Boot1` **未见任何引用** |
| **`FIX-A`** | **`max_split_size_mb=256` 试验**——**反噬实锤并已回退**（与 vLLM `#58068` 的结论互为独立印证） | `~/V41-UPSTREAM-TRACK-20260922.md:41`（`我们的 FIX-A（max_split_size_mb=256）反噬实锤并已回退`） | `~/V41-UPSTREAM-TRACK-20260922.md:39`（`#58068 文中明确：max_split_size_mb:256…都被试过，「更差或无效」`） | — |
| **`FIX-B`** | **全闲态释放 CUDA 缓存分配器未用段**的钩子：`_maybe_idle_release()`，门 `DSV41_IDLE_RELEASE=1`（缺省关），全闲窗内按阈值+间隔释放；v2 改用扁平键（torch 版 `.current/.peak` 后缀） | `~/<source-repo>/sglang-overlay.ctx600k-probe/scheduler.py:1807`（`FIX-B：全闲态释放 CUDA 缓存分配器的未用段`） | `~/<source-repo>/sglang-overlay.ctx600k-probe/scheduler.py:1811`（`本钩子在 is_fully_idle() 的安全窗`）、`:1815`（`三死法` 纪律注记）、`~/V41-CTX600K-READINESS-20260922.md:62`（`由 FIX-B 在全闲时回收瞬态部分`）、`:179`（`FIX-B` 台账） | 与 **FIX-A/FIX-D 无关**（三条独立修复） |
| **`FIX-D`** | **宽度分桶**：把宽度对齐到 `_DENSE_LOGITS_WIDTH_BUCKET=16384`（`lc_aligned`/`w_bucket`）。是 `mask_b` 宽度问题的**上游同思路局部实现** | `~/V41-CTX600K-READINESS-20260922.md:14`（`FIX-D 确是主力`）、`:24`（`FIX-D 宽度桶 w_bucket = ceil_align(ceil_align(lc,4), 16384)`） | `~/V41-ABCD-SCOPED-PLAN-20260922.md:94`（`FIX-D 已经把 logits 宽度对齐到 _DENSE_LOGITS_WIDTH_BUCKET=16384`）、`~/V41-UPSTREAM-TRACK-20260922.md:41`（`FIX-D「宽度分桶（9185 尺寸→2）」是同一思想的局部实现`）、`~/V41-CTX600K-READINESS-20260922.md:31`（`与 FIX-D 验证观测「reserved 段 773→777」同机制`）、`:66`（budget 128MiB ⇒ FIX-D 上界 18.5→4.6 GiB） | — |
| **`FIX-M1`** | **单 carrier 复用**（把 per-chunk 的 ∝lc 活暂态从 dip 9.96 G 压到 ~2.2 G 的修复方向之一） | `~/V41-CTX600K-READINESS-20260922.md:226`（`FIX-M1（carrier 复用）`） | `~/V41-R3-WINDOW-INCIDENT-AND-ATTRIBUTION-20260922.md:114`（`③ FIX-M1（carrier 复用）/ FIX-M2（块索引）`） | **只有单点图例**（两处都是并列提及，**没有一处展开定义**）——含义列是从"名称+出现地上下文"反推的 |
| **`FIX-M2`** | **块索引发布**（对应 `(b1)` 方案：掩码常驻 64 MiB） | `~/V41-CTX600K-READINESS-20260922.md:227`（`FIX-M2 = (b1) 块索引发布，掩码常驻 64 MiB`） | `~/V41-R3-WINDOW-INCIDENT-AND-ATTRIBUTION-20260922.md:114` | 同上：**只有单点图例** |
| **`QW1`/`QW2`/`QW3`** | **快赢（Quick Win）任务号**。`QW1`=compact ragged verify（激活成功但首跑即崩，**NOGO-for-now**）；`QW2`=#39482 DeepGEMM SM121（**NOGO 严重回归**，全路径慢 ~100×）；`QW3`=#39154 移植（Phase A NOGO-迭代1，其机理标签后被**改判**「环境瞬态」→「靴态」） | `~/V41-SGLANG-OPS-ROUND2-20260914.md:246`（`QW1（compact ragged verify）NOGO-for-now`） | `~/V41-SGLANG-OPS-ROUND2-20260914.md:248`（`QW2（#39482 DeepGEMM SM121）NOGO 严重回归`）、`:244`（`快赢窗 QW1/QW2 + FP4 M0/M1 离线`）、`:254`（`QW3 #39154 未测`）、`:268`（`QW3（PR #39154 移植）窗口 — Phase A NOGO-迭代1`）、`~/V41-CED-OPTIMIZATION-REPORT-V2-20260916.md:21`（`改判 QW3 Phase A 的机理标签（「环境瞬态」→「靴态」）`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:45`（`U1 compact verify 切换（QW1/SPS 表激活）`） | — |

---

## 3. 项目术语与代号

| 代号 | 含义 | 首次/权威出处 | 其他出现点（file:line） | 备注 |
|---|---|---|---|---|
| **`mask_b`** | **dense-indexer 候选掩码**：`[pub_rows, lc]` bool。是 600K 下**最大的 ∝lc 活暂态**（~4.85 GiB/次），每次 chunk 更宽一档 ⇒ 分配器永远用不上前一块（"增长型 strand"） | `~/V41-EXTERNAL-AUDIT-40217-VERDICT-20260919.md:39`（`mask_b = torch.empty((pub_rows, lc), bool)`（:3405）） | `~/V41-CTX600K-READINESS-20260922.md:40`（`mask_b（backend:3472）` 尺寸公式）、`:75`（`mask_b = [t_len, lc] bool = t_len×lc 字节`，600K 下 ~4.85 GiB/次）、`~/V41-ABCD-SCOPED-PLAN-20260922.md:94`（`但 mask_b 用的仍是原始 lc`） | — |
| **`A 门`** | **A 门 = 环境变量门 `DSV41_MASK_B_EMPTY_NONFINAL`**（非末 chunk 发布空掩码的开关）。**窗口 A1（2026-09-22）已证明它从不触发** | `sglang-overlay.ctx600k-probe/deepseek_v4_backend.py` 的门名 `DSV41_MASK_B_EMPTY_NONFINAL`（3 处：注释 / `get_bool_env_var` 读点 / 日志串） | 同文件注释串 `window A1 (2026-09-22) proved it never`（A1 窗口判它从不触发那句，源码跨行 ⇒ 锚点取逐行可证的前半） | — |
| **`A-1`** | **A 门对应的台账条目**（A 门判决的账本行） | `sglang-overlay.ctx600k-probe/deepseek_v4_backend.py` 的注释串 `A-1 (2026-09-22)` | — | **只有单点**（"A-1 ledger"注释一处） |
| **`e-tier`** | **oom_gate 的"应急线"档位**：`-e <GiB>`（当前 `-e 1`）= **单采样、零等待立即止损**（"最后 1 GiB 里没有时间做确认"）；2026-09-18 加，历史副本名 `oom_gate.sh.pre-e-tier-20260918` | `~/w6-kit/oom-gate/oom_gate.sh:28`（`-e ★应急线（2026-09-18 加）`） | `~/w6-kit/oom-gate/README.md` **§2 四条线的表行 `-e`（`应急线：单采样、零等待立即止损`）**、同册 **§11 文件清单的 `oom_gate.sh.pre-e-tier-20260918` 行**、`~/w6-kit/oom-gate/oom_gate.sh:224`（`★应急线（-e）：单采样、零等待`）、`:240`（`shout CRIT … exit 4`）、`~/w6-kit/guard/guards.conf` 的 `oom-gate-floor` 行（`-e 1（应急线…2026-09-18 用户令）`）、`~/w6-kit/adr/ADR-004-three-gib-floor-guard.md` 的「引用点」块（首行 = `oom-gate/oom_gate.sh 的「ADR-004 = 本行止损线」注释行`）与 **§2 决策的四条线表** | 三层线：`-w 6`（只记日志）/ `-f 1.5`（止损，2026-09-23 起）/ `-e 1`（应急） |
| **`mm-ban` / `mmban`** | **多模态占位符禁集**：从**采样概率层**（logits 置 −inf）排除仅供输入的 mm 占位符与提示词控制 token。两组独立开关：`DSV41_BAN_MM_PLACEHOLDERS`（默认开，425 个 id = 422 占位符 + 3 图像控制）与 `DSV41_BAN_PROMPT_CONTROL_TOKENS`（默认开，13 个 id） | `~/<source-repo>/sglang-overlay.ctx600k-mmban/deepseek_v4_model.py:281`（`MM_BAN_BLOCK_BEGIN`）、`:314`（`_MM_BAN_ENV = "DSV41_BAN_MM_PLACEHOLDERS"`） | `~/<source-repo>/sglang-overlay.ctx600k-mmban/deepseek_v4_model.py:306`（`MM_BAN_APPLY_FAILED` 标记）、`:308`（`mm_ban_selfcheck()`）、`:312`（`gate 日志断言…必须见到 438 那条 INFO`）、`~/<source-repo>/sglang-overlay.ctx600k-mmban/`（overlay 目录名） | **不实施静默降级**：应用失败打 `MM_BAN_APPLY_FAILED`，gate 按此串判 FAIL |
| **`ctxsnap`** | **上下文快照诊断钩子**：SIGUSR1 → `torch.cuda.memory_snapshot()/summary()` 落 `/state/ctxsnap/`，用于长 prefill chunk 绞死分配点名；**全链 fail-open**（诊断永不杀伺服） | `~/<source-repo>/sglang-overlay.ctx600k-probe/scheduler.py:1804`（`SIGUSR1 → torch.cuda.memory_snapshot()/summary() 落 /state/ctxsnap/`） | `~/<source-repo>/sglang-overlay.ctx600k-probe/scheduler.py:1903`（`snap_dir = "/state/ctxsnap"`）、`:1917`（`[ctxsnap] dumped %d segments`）、`~/<source-repo>/start.sh` 中 `SIGUSR1→CUDA memory_snapshot 落 /state/ctxsnap` 那一行（`诊断 overlay（sglang-overlay.diag/）`）、`~/V41-CTX600K-READINESS-20260922.md:87`（`4 份负载态 ctxsnap`）、`:255`（`①ctxsnap 钩子按 chunk 抓 RSS`） | 只在 `sglang-overlay.diag/` 与 `ctx600k-probe` 携带 |
| **`dspark`** | **投机解码方法名**（MTP 实现），在 vLLM 时代用 `--speculative-config '{"method":"dspark",…}'`；也出现在镜像名 `anemll/dspark-vllm-gx10` | `~/w6-kit/start_tp4_worker_v043.sh:58`（`--speculative-config '{"method":"dspark","num_speculative_tokens":7,…}'`） | `~/w6-kit/w9r2_mtp_fix2_run.sh:11`、`~/w6-kit/w6_patch_guard.py:5`（`生产 fork dspark-vllm-gx10:0.2.1-v026.0 core.py:126-129 同款语义`）、`~/w6-kit/G1R7VL-W1-REPORT-20260902.md:24`（`dspark.py 不在 24 文件移植清单`）、`~/V41-UPSTREAM-TRIAGE-20260920.md:38`（`#39116 DSV4 DSpark 接受长度修复`） | ⚠ **"DSpark #29488" 不存在**：`~/V41-UPSTREAM-TRACK-20260922.md:9` 记载该号 GitHub API **404**（编号查证失败，已入 REFERENCE.md §13） |
| **`Engram`** | **DeepSeek-V4.1 的 host 表/主机 cache 机制**（2 层，`/engram` 数据挂载）。GB10 统一内存下 **host 表无收益**（官方 `SGLANG_ENABLE_DSV41_ENGRAM_HOST_TABLE=0` ✓） | `~/w6-kit/v41_post_boot_check.sh:60`（`THE engram assertion: mapped, not pinned`） | `~/w6-kit/v41_post_boot_check.sh:61`（`Engram table mapped from`）、`:62`（`Engram table offloaded to pinned host memory`）、`~/V41-UPSTREAM-TRIAGE-20260920.md:98`（`Engram host 表在 GB10 无收益`）、`~/V41-CTX600K-READINESS-20260922.md:51`（`Engram 主机 cache 1.0 GiB（2 层×0.5GiB 匿名 mmap…empty_cache 结构上碰不到）`）、`:52`（Engram staging）、`~/V41-CTX600K-READINESS-20260922.md`（`~/V41-R8-WINDOW-REPORT-20260913.md:139` 另见 engram-offset post-mortem） | 启动断言：**必须 map（disk-backed），不能 pinned** |
| **`CED`** | **Causal Encoder-Decoder**（V4.1 的编码器-解码器结构：编码器全 SWA、解码器只末 `n_win=128` token 过解码器）。★本项目对其收益有**三重降级**记录：绝对上界 ≤9%、实际预期 ≤4.6%、且与结构不兼容 | `~/v41-manual/stage/01-plan/v41-landing-plan-2026-09-11.md:831`（`### 12.2 🆕 方案⑧：CED（Causal Encoder-Decoder）`） | `~/v41-manual/stage/01-plan/v41-optimization-playbook-2026-09-12.md:39`（`CED（Causal Encoder-Decoder）…三重降级`）、`~/v41-manual/stage/01-plan/v41-landing-plan-2026-09-11.md:735`（`方案⑧ CED（收益修正为 ≤9%，降 P2）`）、`~/V41-CED-OPTIMIZATION-REPORT-V2-20260916.md:25`（`上游调研吸收：CED 8 项的逐项判决`）、`~/V41-PD-SEPARATION-ANALYSIS-20260913.md:173`（该行原文：`- 官方报告：/data/models/DeepSeek-V4.1-Flash/DeepSeek_V41_Tech_Report.pdf（2.2 节 CED / 2.4.4 FP4 KV / 3.2 EPD）` —— ⚠ **这里的"2.2 节"是《V4.1 技术报告 PDF》的节号，不是本 md 的章节**；本 md 实有章节 = `§0`~`§6` + 附录，原文抄录时请勿当作本文件章节）、`~/v41-manual/stage/01-plan/mhc-three-ops-sm121-benchmark-verdict-2026-09-11.md:7`（`CED 收益 −48.4% → 上界 ≤9%`） | 全称只在**两份**落地计划文档里给过 |
| **`b12x`** | **SM12x 专用 NVFP4/MXFP4/MXFP8 CuteDSL 内核家族**（vLLM PR `#39634` 引入，FlashInfer 以 sync-to-b12x-HEAD 方式收编）。我方 MoE 走 b12x（**不走 FI 的 `moe_utils`**） | `~/V41-UPSTREAM-TRIAGE-20260920.md:63`（`b12x 真身=SM12x 专用 NVFP4/MXFP4/MXFP8 CuteDSL 内核家族`） | `~/w6-kit/guard/BASELINE.md` 的「2026-09-16 三次更新」节 → 「新增 `archscr` kind 与 `flashinfer-arch` 前置」小节第 1 条（`我方 MoE 走 b12x，moe_utils 从未被取件`）、`~/w6-kit/guard/guards.conf` 的「v8 上线（b12x 回补 02407f65+ff36d2d1）」注释行、同册 `flashinfer-arch` 行的注释块（`#5237 的靶子 moe_utils 只有 100a/103a，但根本不在我方路径上（MoE 走 b12x）`）、`~/V41-CTX600K-READINESS-20260922.md:49`（`b12x MoE 逐层输出 outs[cap]`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:25`（`b12x-a8 vs FI W4A8`）、`~/V41-B12X-LARGEM-REGRESSION-ANALYSIS-20260919.md:1` | ★**归属教训**：本地 vendored 代码暗示 repo owner 是 `lukealonso/b12x`，而 WebFetch 到的 **#396** 页面显示的 owner 是 `local-inference-lab` ⇒ REFERENCE.md §5 已把这个矛盾当**显式caveat** 记下，未取单一归属 |
| **`MBT`** | **`--max-num-batched-tokens`** 的脚本变量缩写。含义列=**从脚本上下文反推**（`MBT="${MBT:-2048}"` 直接喂给 `--max-num-batched-tokens "$MBT"`） | `~/v41-campaign-bprime/r2-round-20260913/launcher-b4/v41_b4_launch.sh:79`（`MBT="${MBT:-2048}"`） | `~/v41-campaign-bprime/r2-round-20260913/launcher-b4/v41_b4_launch.sh:163`（`--max-num-batched-tokens "$MBT"`）、`~/v41-campaign-bprime/c2-round-20260912/v41_baked_launch.base.sh:79,163`、`~/v41-campaign-bprime/r2-round-20260913/launcher-b7/v41_b7_launch.sh:101,288`、`~/V41-CAMPAIGN-SCORECARD-20260912.md:15`（`B1′ MBT 8192`）、`~/V41-CAMPAIGN-PLAN-R2-20260913.md:15`（`已关账不重开：APC/NCCL env/CONF_MIN/MBT/…`） | **无文字展开**（只有变量用法）⇒ 属"上下文反推"，非权威定义 |
| **`PRv3` / `PR-v3`** | **纯 prefill 矩阵采集器**（`bench/prv3_collector.py`），v3 口径；原工具为会话内联已失传，本版按 v14 数据模式同口径重建 | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:89`（`PR-v3 工具已固化 bench/prv3_collector.py（原工具为会话内联已失传，本版按 v14 数据模式同口径重建）`） | `~/V41-BATCH7-HLANE-REPORT-20260920.md:34`（`H10 三修（bench/prv3_collector.py…）`）、`:71`（`bench/prv3_collector.py=d20f002e…`）、`~/V41-CTX600K-READINESS-20260922.md:66`（`PRv3=4830≥4500`）、`~/V41-PRV3-BASELINE-V18-20260919.md:1` | **跨工具绝对值不可比，序列内可比**（工具重建纪律） |
| **`SPF`** | **shortest-prefill-first**（`schedule-policy shortest-prefill-first`）：按剩余未命中 prefill 长度排序的调度策略。上游 `#40024` 把它正式化但**默认仍 FCFS**。我方 09-21 A/B **判负**（同尺寸格 −14%） | `~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md:98`（`## 四、SPF 臂（schedule-policy shortest-prefill-first）A/B 判负`） | `~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md:102`（FCFS vs SPF 对照表）、`:115`（`SPF 理论 no-op 却仍掉 14%`）、`:118`（`上游 #40024 把 SPF 正式化但默认仍 FCFS`）、`:132`（`T7c 异构混批格（SPF 终审…）`）、`~/<source-repo>/start.sh` 中 `09-21 SPF 臂实锤的病类` 那一行（`EXTRA_SGLANG_ARGS 传值被吞、引擎仍 fcfs`） | — |
| **`FCFS`** | **First-Come-First-Served 调度**（SGLang 默认）。与 SPF 对立；上游 `#38478`（open RFC）描述的"FCFS 队头大请求 NO_TOKEN 即 break、队后小请求饿死"正是我方 ≥32K 断崖机制 | `~/V41-UPSTREAM-TRIAGE-20260920.md:36`（`FCFS 队头大请求 NO_TOKEN 即 break，队后小请求饿死`） | `~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md:102`（FCFS/SPF 对照表）、`:118`（`默认仍 FCFS`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:29`（`台阶=chunk FCFS`） | — |
| **`EC0` / `ec0`** | **`DSV41_PREFILL_EMPTY_CACHE_TOKENS=0`**（prefill empty_cache 钩子关闭；"冻结"）。`ec131072` = 同一旋钮取 131072 时的形态（**看门狗拦**） | `~/<source-repo>/sglang-overlay.ctx600k-probe/scheduler.py:1816`（`ec0 冻结/ec131072 看门狗拦/压强+阈值 SIGABRT`） | `~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md:125`（`0.2.7 + ctx147456 + share4096 + ec0 + golden 锁定`）、`~/ops-handoff-20260921/03-SEQ-服务器评估与操作时序.md:41`（`三死法：ec0 冻结/ec131072 看门狗/阈值 SIGABRT`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:96`（`DSV41_PREFILL_EMPTY_CACHE_TOKENS=0` 生产形态） | ★**「三死法」是项目的 empty_cache 铁令来源**（原文：`本项目曾有「empty_cache 任何形式禁再启」铁令（三死法在案）`）；FIX-B 是**唯一新增主动例外**（三重护栏） |
| **`GLM`**（术语侧） | 见 §1 —— 外部对照配方树 | `~/w6-kit/reference/GLM-5.3-Flash-NVFP4-1M-KV-4x-DGX-Spark/README.md:33` | `~/<source-repo>/README.md` 中 `Full six-stack comparison incl. LuZ / Vision-Exp / GLM` 那一行 | 重复登记以免漏检 |
| **`rex`** | **脚本家族前缀**（`rex_*`，vLLM 时代的回归/交付脚本），也以注释者署名 `rex-g` 出现 | `~/w6-kit/rex_g4_i2_bench.sh:2`（`rex_g4_i2_bench.sh <TAG> — G4-T3 二项回归`） | `~/w6-kit/monitor_tp4_worker_v043.sh:5`（`rex-g 20260831: 增加 guard 互斥`）、`~/w6-kit/rex_g4_handoff.sh:3`（`G4-T1/G4-T3 双臂 ×5 轮 执行清单`）、`~/w6-kit/rex_g4_de3.sh:2`、`~/w6-kit/rex_g4_handoff_v2.sh:151`、`~/w6-kit/026_gen_patch.sh:2`（`供 rex-g P4 镜像重建使用`） | `rex_g4_*` 里的 `G4` = 第四轮（与 `g1r7` 的 `G1` 同套轮次命名） |
| **`s4` / `S4`** | ★**多义**：①`V41-SGLANG-MOE-DENSE-REPORT-AND-PLANS-20260915.md:253` 的 `#### S4 — 收口`（该报告的收口节）；②`V41-PRDE-SCHEDULING-OPTIONS-20260919.md:16` 的 **S4 = PD 分离**（Prefill-Decode Disaggregation，方案编号 S1-S4）；③`V41-R7-MASTER-ACTION-PLAN-20260913.md:45` 的 **S4 = #47808 全局 top-B 预算跨请求回移**（投机解码面 S1-S4）；④`V41-R3-FOLLOWUP-AND-LEVERS-20260922.md:142` 的 **`S4(4.89M)` = KV 池缩容档位**（`C(9.6M)` vs `S1(8.42M)` vs `S4(4.89M)`） | 无单一定义，四处各自成立 | 同上四处 | ★**未见统一权威定义**——用户清单里的 `s4` 无法唯一归属，本表**四种都给**，请上级裁 |
| **`ACTIVE` / `HELD` / `DRIFT` / `DEGRADED` / `SKIP`** | **guardctl 判定词表**（`verdict: OK HELD DRIFT DEAD MISSING DEGRADED`，另有 `ACTIVE` 用于单元状态、`SKIP` 用作一等结论）。`HELD`=脚本是**停泊桩**（有意的维护态，渲染 WARN 但**照样计数**）；`DRIFT`=md5 与登记值不符（**计入问题数**）；`DEGRADED`=降级运行；`SKIP`=**一等结论**（"本机不适用/结构性不存在"），**不是 WARN** | `~/w6-kit/guard/guardctl.sh:136`（`# verdict: OK HELD DRIFT DEAD MISSING DEGRADED`） | `~/w6-kit/guard/guardctl.sh:61-62`（`SKIP = 一等结论…不是 WARN`）、`:145`（`HELD\|脚本是停泊桩`）、`:147`（`DRIFT\|md5=… 期望=…`）、`:459`（`HELD→WARN 口径正好相反，结果是"链被关掉"成了唯一不会被渲染出来的失效形态`）、`:516-517`（渲染分级）、`~/w6-kit/guard/BASELINE.md` 的「2026-09-16 四次更新」节 → `guardctl.sh` 行（`HELD = 脚本是停泊桩 = 有意的维护态`） | `ACTIVE` 是**systemd 单元状态**词（不是 guardctl 判定词）；`DEAD`/`MISSING` 见 `guardctl.sh:136` |
| **`0211 事故`** | ★**命名与内容不符**：名字像日期（2 月 11 日），但定义是**一次探针 OOM 扫射事故**——分配探针请求量**必须 ≤ free − 4 GiB**；请求距 free 仅 ~1.3 GiB 时（118 GiB 请求 @ free 116.7），驱动向内核施压 ⇒ swap off 下 **OOM killer 扫射**，击杀的是**最大 RSS 进程而非探针**（02 上 registry/aicad 容器/dbus/avahi 被连杀，sshd 饿死 35+ 分钟，02/04 被打到重启，docker `restart=always` 把 15 个已停泊 aicad 容器全部拉回） | `~/w6-kit/WINDOW-RUNBOOK.md` **§0.5「探针请求必须 ≤ free − 4 GiB」内的「`≤ free − 4 GiB` 是红线。0211 事故：请求距 free 仅 ~1.3 GiB 时（118 GiB 请求 @ free 116.7）」句** | `~/w6-kit/v41_devfree_host.sh:19`（`--min4 # 安全护栏自检：MemFree<4GiB 时**拒绝**建上下文（防 0211 事故）`）、`~/V41-R3-FOLLOWUP-AND-LEVERS-20260922.md:127`（`MemFree 地板拒绝建上下文（对齐 0211 红线）`） | ★**日期存疑（如实登记）**：全部三条出处都**只有"0211"这个串，没有任何一处写出事故日期**。项目时间线是 **2026-08~09**（`V41-R3-…-20260922`、`v41_devfree_host.sh` 提及 `attempt13`/`0.2.7`），**本地找不到任何 2026-02-11 或其它年份 02-11 的记录**。两种可能（**都不作为结论**）：①"0211"是**事故/事件的流水编号**（如 attempt13 那样的序号），不是日期；②是日期但发生在**本树记录覆盖期之前**，故无当日报告。**登记为存疑，请上级裁决** |
| **`慢靴` / `靴态签名` / `boot-signature`** | **靴次态问题**：配置**逐字节不动**、重启即恢复的解码塌陷（10-25×）⇒ 判为**靴态**而非配置；判据工具=`scripts/boot-signature.sh`（v2，旧判据被证伪） | `~/V41-CED-OPTIMIZATION-REPORT-V2-20260916.md:21`（`★…撞上「慢靴」生产事故——解码塌 10-25×，质量门全绿`） | `~/V41-SGLANG-SESSION-DOSSIER-20260916.md:77`（`慢靴事故（变更 #14）…判据改版为 boot-signature.sh v2（旧判据被证伪）`）、`~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md`（0.2.7 回退疑云最终破案为**时钟楔死**，非慢靴）、`~/w6-kit/guard/BASELINE.md` 的「2026-09-19（下午）：v10 上线」节 → `v9 事故翻案` 行（`R9 档案已知的偶发慢靴`）+「2026-09-19（终）：慢路径根因定谳与根治（v13）—— R9 慢靴结案」节标题 | ★0.2.7 的"prefill 2.25× 回退"**最终不是慢靴**——真因是 <node02> **PD 安全模式时钟楔死**（721 MHz@96%util/15W，拔墙 AC 冷断电修复） |
| **`停泊桩` / `hold` / `release`** | 窗口作业的**有意维护态**：`guardctl hold` 把守卫脚本换成**停泊桩**（桩本身合法、判定为 `HELD`），`release` 还原并只重启**本次真被 hold 过**的 simple 单元 | `~/w6-kit/guard/guardctl.sh:464`（`HELD\|链脚本是**停泊桩**…不在维护窗口内就用 'guardctl.sh release <tag>' 还原`） | `~/w6-kit/guard/BASELINE.md` 的「2026-09-17 五次更新」节 → `healthcheck-rebuild.sh（01）` 行（`停泊桩在 01 上挂了 6 天，本次 release 还原`）、`~/w6-kit/WINDOW-RUNBOOK.md` **§5「停泊与放行顺序」**、`~/w6-kit/guard/BASELINE.md` 的「2026-09-16 四次更新」节 → `guardctl.sh` 行（HELD 定义） | — |
| **`裸进程守卫`** | **没有 systemd 单元托管**的常驻守卫（`oom_gate.sh monitor` / `guardctl.sh watch`），手工 `nohup`/`setsid` 拉起 ⇒ **机器重启或被人 kill 后不会自愈**（=已知缺口） | `~/w6-kit/guard/guards.conf` 的 `guard-watch` 行（`机器重启或被人 kill 后不会自愈`；属主 2026-09-23 已在注释里把缺口指到 `§7.5`） | `~/w6-kit/guard/BASELINE.md` 的「2026-09-16 四次更新」节 → 「仍未做（如实登记）」段（`两个常驻仍是手工拉起…而它们恰恰是 2026-09-15 W4 事故的缺失项`）、`~/w6-kit/WINDOW-RUNBOOK.md` **§5.3「两个裸进程守卫的重挂」**、`~/w6-kit/guard/guards.conf` 的 `oom-gate-floor` 行（`★2026-09-18 起由 systemd 单元 oom-gate-monitor.service 托管（Restart=always，根治裸进程不随整机重启自启）`） | ★该缺口**已部分关闭**（2026-09-18 起 oom-gate-monitor 由 systemd 托管）；但 `guard-watch` 行上方注释的"**没有任何单元保证**"**未同步更新**（2026-09-23 复核仍如此） |
| **`SPS 表`** | **speculative sampling / STATIC 形态相关的表**（`SPS 表缺失=注`；生产当前 live 处于 **verify-all 降级态**，STATIC 模式下良性） | `~/V41-BATCH7-HLANE-REPORT-20260920.md:26`（`SPS 表缺失=注（**生产当前 live 处于 verify-all 降级态，STATIC 模式下良性，现已在门可见**）`） | `~/V41-UPSTREAM-TRIAGE-20260920.md:109`（`padded spec batch 挂死 sparse MLA（FI #5015）… RAGGED_VERIFY_MODE=static`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:45`（`U1 compact verify 切换（QW1/SPS 表激活）`） | **`SPS` 全称未见权威定义**（只有缩写与用途） |
| **`U1 门`（compact 语境）** | compact 路线的前置门：**切 compact 前必修 `#39257`**（compact ragged CUDA graph 非最大档槽位算错，仍在 open） | `~/V41-UPSTREAM-TRIAGE-20260920.md:40`（`#39257 \| open \| compact ragged CUDA graph 非最大档槽位算错 \| 已知（我方 U1 门），确认仍在 open`） | `~/V41-UPSTREAM-TRIAGE-20260920.md:110`（`compact ragged graph 槽位（#39257）… U1 门已知 ✓`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:45`（`U1 compact verify 切换 …触发=#39257 或 #40162 合并`） | — |
| **`M4`~`M10`（CHUNK8192 COMPENDIUM）** | **第三套 `M` 编号**：CHUNK8192-vs-4096 汇编里的**未测点/待办编号**（`M4`=当代 4096 的 1×245.7K 复测（修口径警示）；`M6`=16×245.7K 地板；`M8`=工具带收益格；`M9`=8192×mixed-chunk 组合；`M10`=GSM8K） | `~/V41-CHUNK8192-VS-4096-COMPENDIUM-20260919.md:74`（`1. 工具带收益格…（M8）；2. 16×245.7K 地板（M6）；3. GSM8K（M10）；4. 8192×mixed-chunk 组合（M9）；5. 当代 4096 的 1×245.7K 复测（修 M4 的口径警示）`） | `~/V41-CHUNK8192-VS-4096-COMPENDIUM-20260919.md:21`（`M8`）、`:57`（`M8` 的唯一直接证据） | ★**`M1~M5` 有三义**：①engram-c 取证脚本 ②本套 M4~M10 ③用户清单里的 `M1~M5`——**无法唯一归属**。本表三处都登 |
| **`P0-A`（重复避免漏检）** | 见 §2 —— 37ms 停顿两层归因 | `~/V41-P0A-ATTRIBUTION-20260912.md:1` | `~/V41-CAMPAIGN-SCORECARD-20260912.md:32` | 重复登记以免漏检 |
| **`K2-R`** | **288B 主 KV 写回契约**（"读侧内核=兑现前提"）：把主 KV 的 288 B/token 布局的**写回**（`outs[cap]` 侧）与**读侧内核**配成对的工程项目；是我方"池/字节面独存主杠杆"（+8.2%/+23.5%） | `~/V41-CAMPAIGN-SCORECARD-20260912.md:42`（`K2-R 288B 写回 \| 待外部 \| **池/字节面独存主杠杆**（+8.2%/+23.5%）；读侧内核=兑现前提`） | `~/V41-CAMPAIGN-SCORECARD-20260912.md:16`（`复活=K2-R 后池成约束`）、`:31`（`K2-R/M2 集成准备 ✅ 契约+备忘录`）、`~/v41-campaign-bprime/E-ASYNC-DESIGN-20260912.md:57`（`K2-R/FP4 字节面（33ms 流地板的下压）`）、`~/V41-R8-WINDOW-REPORT-20260913.md:26`（`agent-k2r.md：K2-R 五件全 0 交付且从未成文下发`）、`~/V41-CAMPAIGN-SESSION2-20260912.md:123`（`K2-R 288B 写回集成契约`）、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:28`（`若 #5197 不含 SM121 须自研（K2-R 轨资产可复用）`） | ⚠ `K2-R/M2` 里的 **`M2` 是第四套 M 编号**（集成准备的子项），**未见定义** |
| **`outs[cap]` 契约** | b12x MoE 的**逐层输出缓冲按容量 `cap` 分配**（`outs[cap]`），600K 下 21 层 × (8192·5120·2=80MiB + …) = **3.025 GiB 刚性**，只在首次请求时物化 | `~/V41-CTX600K-READINESS-20260922.md:49`（`b12x MoE 逐层输出 outs[cap] \| 3.025 GiB \| 21 层 × (8192·5120·2=80MiB + 40 + 22.5 + 5 MiB)；late_layer_start=21`） | `~/V41-CTX600K-READINESS-20260922.md:53`（`b12x 部分首次请求时物化（=旧台账里「~2.9G/req 常数杂项」的真身，一次性而非每请求）`） | REFERENCE.md §5 把 b12x `#397` 判为"`outs[cap]` 契约" |
| **`late_layer_start`** | 非末 chunk **跳过解码器层的起点层号**（21）——与 CED（末 `n_win` 过解码器）同族机制；`DSV41_SKIP_NONFINAL_DECODER=1` 在役 | `~/V41-CTX600K-READINESS-20260922.md:49`（`late_layer_start=21（layers≥21 非末 chunk 跳过）`） | `~/V41-CED-SKIP-FUSE-REUSE-20260915.md:11-13`（`DSV41_SKIP_NONFINAL_DECODER=1 出现在服务进程 environ`，链路五处行号） | — |
| **`A 档 / B 档 / C 档`（第三方包 3）** | 第三方反馈包的**采纳分级**：`A 档`=关账项（#40217 外部实锤 + 三参数形态确认）；`B 档`=采纳四项已固化；`C 档`=入窗（T7b 定谳/T7a/T7c） | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:87-88`（`A 档两项关账…B 档四项采纳已固化、C 档 T7b 定谳/T7a/T7c 入窗`） | — | **只有单点图例**（一处列出三级） |
| **`17 个静默失败点`** | 批次 7 的**静默失败点盘点**：H 车道闭环 14 个、遗留 3 个合批 0.2.7 | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:86`（`H 车道 10 项全落地（17 个静默失败点闭环 14、遗留 3 合批 0.2.7）`） | `~/V41-BATCH7-HLANE-REPORT-20260920.md:3`（`第三方反馈包 3 + 17 个静默失败点盘点`）、`:38`（`## 三、17 个静默失败点闭环状态`） | — |
| **`三参数形态`** | 生产在役的**三个关键参数组合**：`chunk 8192 + mixed-chunk + interval 4` | `~/V41-OPTIMIZATION-MASTER-PLAN-V4-20260920.md:13-14`（`三参数形态 chunk 8192+mixed-chunk+interval 4；#40217 已修（131072×C16 两靴 16/16）`） | `~/V41-UPSTREAM-TRIAGE-20260920.md:23`（`mixed-chunk+interval 4 ✓（社区甜点，Mia 反而没有）`） | — |
| **`v13`** | **autotune 多数表决的版本号**（v13 引入多数表决；`JIT wedge`/`block-size 128`/`DeepGEMM block_kv` 限制等 post-mortem 属 per-boot 复盘的 boot3/4/5） | `~/V41-UPSTREAM-TRIAGE-20260920.md:24`（`autotune 多数表决 ✓（v13）`） | `~/w6-kit/guard/BASELINE.md` 的「2026-09-19（终）：慢路径根因定谳与根治（v13）—— R9 慢靴结案」节（**不写行号**：该册属主仍在改；原登记写 `:260`，实测已位移） | ⚠ 与镜像别名 `v7/v14/v18` **不冲突**（那是镜像别名，`v13` 指 autotune 表版本），但**字面相近，易混** |
| **`Autotune golden tree` / `autotune-golden`** | **宿主端 autotune 金表树**（多数表决后的表）——用于覆盖/校验容器内 autotune 结果 | `~/V41-UPSTREAM-TRIAGE-20260920.md:24`（`autotune 多数表决 ✓（v13）`） | `~/V41-027-INCIDENT-AND-WINDOW-REPORT-20260921.md:125`（`golden 锁定`）、`~/w6-kit/G1R7VL-W1-REPORT-20260902.md:17`（`autotune 24 配置命中（autotune-g1r6）`） | 树本体名 `autotune-golden/`（`w6-kit` 树内） |

---

## 4. 「未见权威定义」与存疑清单

### 4.1 未见权威定义（登记但**无定义**，绝不猜词）

| 代号 | 状态 | 已找到的全部出现点 | 处理 |
|---|---|---|---|
| **`R4x`** | **未见权威定义**。三个树 grep **零命中**（本册自身那一行除外）。**复算命令**：`grep -rnoE '\bR4x\b' ~/w6-kit ~/<source-repo> ~/*.md \| grep -v GLOSSARY.md` ⇒ **0 命中**（2026-09-23 实测） | 无 | 请上级补记；本表**不猜** |
| **`w6-kit` 的 `w6`** | **含义未见权威定义**（`w6-kit` 作为目录名的**职能**有定义，见 §1；但 `w6` 这两个字符从何而来**无任何文档说明**） | `~/w6-kit/README.md:1`（只有职能，无词源） | 本表只登职能 |
| **`CED` 之外：`SPS`** | **全称未见权威定义**（只有缩写 `SPS 表` 与用途） | `~/V41-BATCH7-HLANE-REPORT-20260920.md:26`、`~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:45` | 本表只登用途 |
| **`LuZ` 词源** | **全称/词源未见权威定义**（命名职能有，见 §1.x） | 见 §1.x | 本表只登职能 |
| **`Q5`~`Q7`** | **未见权威定义**：本项目的 **engram-c 现场取证问题清单**只到 `Q1–Q4` | `~/v41-operators-engramc-20260912/engram-c-handover-2026-09-12/reports/engram-c-optimization-handover-2026-09-12.md:591`（只到 Q4） | ⚠ 2026-09-23 实测：`Q5` 在**另一套问题清单**里确实出现过 **1 次** —— `~/qa-vision-token-audit-A-20260922.md:90` 的「区间结构全景（**回答 Q4 / Q5**）」，那是**视觉 token 审计自己的问号表**，与本条 engram-c 系列**不同套**（复算：`grep -rnoE '\bQ5\b' ~/w6-kit ~/<source-repo> ~/*.md`）。请上级确认 engram-c 序列是否存在于别处 |
| **`Z7`** | **未见权威定义**（V3 零窗批次只列到 `Z6`） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:34-39`（Z1-Z6） | 同 |
| **`N1`** | **未见权威定义**（N 车道表从 `N2` 起列） | `~/V41-OPTIMIZATION-MASTER-PLAN-V3-20260919.md:61-68`（N2-N7） | 同 |
| **`K2-R/M2` 的 `M2`** | **未见权威定义**（第四套 M 编号，只在 `K2-R/M2 集成准备` 一处并列出现） | `~/V41-CAMPAIGN-SCORECARD-20260912.md:31` | 同 |
| **`B5`~`B7`（交叉审核）** | **未见权威定义 —— 但"三树零命中"这句自述是错的，2026-09-23 实测更正如下**：① 交叉审核序列**止于 `B4`**（本地只有 `B1`~`B4`，见 `~/w6-kit/guard/BASELINE.md` 的「2026-09-17 五次更新」节 → `guardctl.sh` / `README.md` 两行）；② 字面量 `B5`/`B6`/`B7` **确有命中**，但**都不是这一套**：**(a) vendored 上游树内**（`fi-main/`、`fi-main2/`、`fi-src/`、`b12x-site/`、`ringonly-v5/src-tree/` 的第三方头/测试）= **16 处**；**(b)** 排除 vendored 树后仍有 **28 处，其中 14 处是本册自己**在讲这件事的文字 ⇒ **本册之外的 14 处**全在**另一套编号**的报告里，逐文件：`V41-CAMPAIGN-PLAN-R2-20260913.md` 4、`V41-R4-OPS-MASTER-PLAN-20260913.md` 4、`V41-CAMPAIGN-PLAN-V2-20260912.md` 3、`V41-WEIGHT-PATH-VLLM-VS-SGLANG-20260914.md` 1、`V41-R7-MASTER-ACTION-PLAN-20260913.md` 1、`<source-repo>/docs/4DGX-dsv41-上游调研-20260913.md` 1 | 无（"无处可指"即结论） | **复算命令**（含排除规则与"扣掉本册"的一步）：`grep -rnoE '\b(B5\|B6\|B7)\b' --exclude-dir=fi-main --exclude-dir=fi-main2 --exclude-dir=fi-src --exclude-dir=fi016-src --exclude-dir=fi18-wheels --exclude-dir=fi-wheels --exclude-dir='cutlass*' --exclude-dir=b12x-site --exclude-dir=patches028 --exclude-dir=reference --exclude-dir='s0-dspark-*' --exclude-dir=src-tree ~/w6-kit ~/<source-repo> ~/*.md \| grep -v 'w6-kit/GLOSSARY.md'` ⇒ **14 行**（2026-09-23 实测；不过滤 vendored = 44、过滤后 = 28 = 本册 14 + 本册外 14）。⚠ **44/28 里含本册自己**（本册每写一次这三个字面量就 +1）——**这本身就是"计数被登记册自己污染"的实例**，故本条只认"扣掉本册"的 14。⚠ 原登记曾把 `V41-MAC-TP2-DECODE-ASSESSMENT-20260913.md`、`V41-HETEROGENEOUS-PD-ASSESSMENT-20260913.md` 两个文件算在命中里——**2026-09-23 复核：两个文件里连 `B` 开头的编号都没有，已删**（原文不可复算）。**`TB5` 缩写与本条无关** |
| **`FIX-M1`/`FIX-M2` 的完整定义正文** | **只有单点并列图例**，无展开段 | `~/V41-CTX600K-READINESS-20260922.md:226-227`、`~/V41-R3-WINDOW-INCIDENT-AND-ATTRIBUTION-20260922.md:114` | 含义列已按上下文最小化反推，并已在备注里标注"单点图例" |

### 4.2 存疑（需要上级裁决，本表**不替上级下结论**）

| 项 | 存疑点 | 证据 | 建议 |
|---|---|---|---|
| **`0211 事故`** | 名字像日期（2 月 11 日），但**三条出处全无日期**；项目记录覆盖期是 2026-08~09，**找不到任何 02-11 的记录** | `~/w6-kit/WINDOW-RUNBOOK.md` **§0.5**（`≤ free − 4 GiB` 红线句）、`~/w6-kit/v41_devfree_host.sh:19`（`--min4` 自检行）、`~/V41-R3-FOLLOWUP-AND-LEVERS-20260922.md:127` | 疑为**流水编号**而非日期（同 `attempt13` 的命名法）；请上级确认后回填 |
| **`R2` 三义** | ①ctx600k 的 `page_table` 页数网格 ②campaign 第二轮计划（`V41-CAMPAIGN-PLAN-R2-20260913.md`）③缺号的报告轮次。**用户记忆里的"R2=indexer 宽度门"在本地对不上**——indexer 侧那个是 **`R1`**（`indexer.py` 行块），且已判死 | `~/V41-CTX600K-READINESS-20260922.md:67,82`、`~/V41-CAMPAIGN-PLAN-R2-20260913.md:1` | 建议给 ctx600k 的两个修复项**改前缀**（如 `CR1/CR2`），消歧 |
| **`guards.conf` 的 `guard-watch` 行，注释里的 `§7` 引用（原记的注释行号 `:123`，**该册同日已改，只作历史记录、不复指**）** | 该注释语境是「**已知缺口**」（缺口本体在 `WINDOW-RUNBOOK §7.5`、重挂命令在 `§5.3`），落笔时却引 `§7`（时钟健康预检）——**指错节** | `~/w6-kit/guard/guards.conf` 的 `guard-watch` 行 vs `~/w6-kit/WINDOW-RUNBOOK.md` **§7.5**（裸进程缺口）与 **§5.3**（重挂） | ★**已被属主就地校准（2026-09-23）**：注释改为"裸进程缺口 = §7.5、重挂命令 = §5.3"并自记"原写「§7」「§5」"。⇒ 本行的原始发现**成立且已消解**，无需上级动作 |
| **`guards.conf` 的 `guard-watch` 行缺口状态** | 该注释说两个裸进程守卫"没有任何单元保证…不会自愈"，但同册的 `oom-gate-floor` 行已记 `2026-09-18 起由 systemd 单元 oom-gate-monitor.service 托管` ⇒ **注释未同步**（2026-09-23 复核：仍未同步） | `~/w6-kit/guard/guards.conf` 的 `oom-gate-floor` 行 vs `guard-watch` 行（原文对照，不写行号——行号随注释改动漂移，见该册自记的 old→new 对照表） | 同上：只登记，不动文件 |

---

## 5. 自检（核验脚本与实测输出）

**纪律**：本节所有 `file:line` 用**只读**命令核一遍（文件存在 + 行号在范围内 + 该行**确实提到**该代号）。
脚本见下（`§5.1`，实测全文），输出见 `§5.2`（实测原文照贴）。

### 5.1 核验脚本（实测使用的版本，非示意）

脚本**自解析两份登记表的表格行**：抽出该行里所有 `file:line` 引用点，对每个引用点做三重检查
①文件存在 ②行号 ≤ 文件行数 ③该行含该行首列的**代号字面量**（`#` 注释放行内，因为本项目的
定义常写在注释里）。**不做启发式抽号**——被检对象就是从表里读出来的，表错则检错。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refcheck.py — REFERENCE.md / GLOSSARY.md 登记项只读核验"""
import os, re

HOME = "/home/liux***ya"
FILES = [("REFERENCE.md", os.path.join(HOME, "w6-kit/REFERENCE.md")),
         ("GLOSSARY.md",  os.path.join(HOME, "w6-kit/GLOSSARY.md"))]

REF_RE = re.compile(
    r'(?:~|/(?:home|opt)\b) ?[^\s`|()\[\]，。；：、<>"]*?\.(?:md|sh|py|conf|json|cu|so|tsv|txt|log|pdf|jsonl)'
    r'(?::\d+(?:-\d+)?(?:,\d+)?)')

def norm(p):
    return p.strip().rstrip(',.;)').replace('~/', HOME + '/')

def split_ref(ref):
    m = re.match(r'^(.*?):(\d+)(?:-(\d+))?(?:,(\d+))?$', ref)
    if not m: return ref, None
    return m.group(1), [int(m.group(2))] + ([int(m.group(4))] if m.group(4) else [])

def tokens_for(cell):
    """从表格首列抽候选 token（用于'该行确实提到该代号'的检查）"""
    s2 = cell.replace('**', ''); toks = set()
    for bt in re.findall(r'`([^`]+)`', s2): toks.add(bt.strip())
    for m in re.findall(r'#(\d{3,6})', s2): toks.add('#' + m); toks.add(m)
    for m in re.findall(r'\b([A-Za-z][A-Za-z0-9]*(?:[._-][A-Za-z0-9]+)+)\b', s2): toks.add(m)
    for m in re.findall(r'变更\s*#(\d+)', s2): toks.add('变更 #' + m); toks.add('#' + m)
    for m in re.findall(r'\b([A-Z]\d{1,2}[a-z]?)\b', s2): toks.add(m)
    base = re.sub(r'\(.*?\)', '', s2)              # 兜底：单元格本体
    base = re.sub(r'[~／/、，,。]', ' ', base)
    for w in base.split():
        w = w.strip('`*_ ')
        if 2 <= len(w) <= 24: toks.add(w)
    return {t for t in toks if len(t) >= 2}

def main():
    g = dict(rows=0, rp=0, rf=0, refs=0, refp=0, reff=0,
             miss=0, oor=0, notok=0); fails = []; missf = set()
    for name, path in FILES:
        raw = open(path, encoding='utf-8').read()
        print("### %s (%d 行)" % (name, raw.count('\n') + 1))
        for lineno, line in enumerate(raw.split('\n'), 1):
            if not line.startswith('|'): continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not cells or set(cells[0]) <= set('-: '): continue
            if cells[0] in ('编号', '代号', '项', '统计', '位置', '文件'): continue
            refs = {norm(x) for x in REF_RE.findall(line)}
            if not refs: continue
            g["rows"] += 1; toks = tokens_for(cells[0]); row_ok = True; det = []
            for r in sorted(refs):
                f, lns = split_ref(r); g["refs"] += 1
                if not os.path.isfile(f):
                    g["reff"] += 1; g["miss"] += 1; missf.add(f); row_ok = False
                    det.append("MISSING-FILE %s" % r); continue
                content = open(f, encoding='utf-8', errors='replace').read().split('\n')
                ok = True
                for ln in (lns or []):
                    if ln > len(content):
                        g["reff"] += 1; g["oor"] += 1; ok = False; row_ok = False
                        det.append("OUT-OF-RANGE %s" % r); continue
                    if not any(t in content[ln-1] for t in toks):
                        ok = False; det.append("NO-TOKEN %s" % r)
                if ok: g["refp"] += 1
                else:  g["notok"] += 1
            if row_ok: g["rp"] += 1
            else: g["rf"] += 1; fails.append((name, lineno, cells[0], det))
    print("登记条目 %d / 通过 %d / 失败 %d" % (g["rows"], g["rp"], g["rf"]))
    print("引用点 %d / 通过 %d / 文件不存在 %d / 行号超范围 %d / 行内未提该代号 %d"
          % (g["refs"], g["refp"], g["miss"], g["oor"], g["notok"]))
    for x in fails: print(x)
    for f in sorted(missf): print("缺文件:", f)

main()
```

> **复算命令**（本节所有数字的唯一来源；脚本正文就是上面那一段，不另设外部输入）：
>
> ```bash
> # ① 从本册抽脚本正文（该代码块以 ```python 起、``` 止）
> sed -n '/^```python$/,/^```$/{ /^```/d; p }' /home/liux***ya/w6-kit/GLOSSARY.md > /tmp/refcheck.py
> # ② 两册合计
> python3 /tmp/refcheck.py
> # ③ 单册（把 FILES 里另一册那行删掉）
> sed -e '/^FILES = \[("REFERENCE.md"/s|.*|FILES = [("GLOSSARY.md",  os.path.join(HOME, "w6-kit/GLOSSARY.md"))]|' \
>     -e '/^         ("GLOSSARY.md",  os.path.join/d' /tmp/refcheck.py > /tmp/refcheck-gloss.py
> python3 /tmp/refcheck-gloss.py
> # ④ 把"未提该代号"桶逐条打印出来（人工复核用）
> sed 's@ok = False; det.append("NO-TOKEN %s" % r)@ok = False; det.append("NO-TOKEN %s" % r); print("   NO-TOKEN " + r + "  <<  " + cells[0])@' \
>     /tmp/refcheck.py > /tmp/refcheck2.py && python3 /tmp/refcheck2.py | grep NO-TOKEN
> ```
>
> ⚠ **口径诚实说明（2026-09-23 修复后重写）**：第③项检查是**字面量**检查（大小写敏感），
> 且**首列是裸序号的行抽不出可比对 token**（`tokens_for()` 会把 `| 1 |`…`| 5 |` 这类首列过滤成空集
> ⇒ 必然落进"未提该代号"桶，**这是仪器口径所限，不是登记错误**）。另有"引的行是定义块的邻行/
> 范围行"或"表头是范围（如 `` `T1`~`T7c` ``）而该行只提到区间中一个成员"这类**上下文引用**也落此桶。
> **该桶不等于错误**：2026-09-23 修复后实测该桶 = **85 条**（GLOSSARY 76 + REFERENCE 9），
> 已用上面 ④ 逐条打印实际行内容人工过目，**无一处行号错位**。

### 5.2 实测输出与统计（2026-09-23 修复后末次复跑，原文照贴）

**首轮口径的一处不诚实，如实记下**：原块里那两行"表格数据行 N 行，含引用点 M 个"**不是本节脚本
打印的**（`§5.1` 的脚本只打印 `### <名> (N 行)` 与末尾四条统计），且它与总数**对不上**
（134 + 109 = 243 ≠ 244；164 + 463 = 627 ≠ 464）⇒ **首轮的 244/464 无法用本节脚本复算**。
这正是"不许留一个没人能复算的数"要治的病。**本轮改为脚本原样输出**（下面四行是
`python3 /tmp/refcheck.py` 的全部输出，无删改）：

```
### REFERENCE.md (522 行)
### GLOSSARY.md (390 行)
登记条目 230 / 通过 230 / 失败 0
引用点 414 / 通过 329 / 文件不存在 0 / 行号超范围 0 / 行内未提该代号 85
```

| 统计 | 值（2026-09-23 修复后实测） | 首轮（修复前）值 |
|---|---|---|
| 登记条目（两表含 `file:line` 的表行） | **230 条** | 244 条（**不可复算**，见上） |
| 其中 GLOSSARY.md | **97 条** | 110 条 |
| 其中 REFERENCE.md | **133 条** | 134 条 |
| 登记 `file:line` 引用点 | **414 个** | 464 个（**不可复算**） |
| **核验通过（条目级）** | **230 / 230**（100%） | 244 / 244 |
| 文件不存在 | **0** | 0 |
| 行号超范围 | **0** | 0 |
| 行内出现该代号字面量 | **329 / 414** | 375 / 464 |
| 行内未提该代号（含仪器口径所限 + 上下文引用） | **85**（GLOSSARY 76 + REFERENCE 9） | 89 |

> ⚠ **为什么修复后反而"变小"了（这不是漏检）**：本轮把指向 **6 个仍在被编辑的目标文件**
> （`WINDOW-RUNBOOK.md`、`adr/ADR-004-*.md`、`oom-gate/README.md`、`guard/README.md`、
> `guard/BASELINE.md`、`guard/guards.conf`）的**行号引用改成了节名/行名/引文锚点**，
> 那些 `file:line` 就从本脚本的计数面上消失了 —— **这正是修的目的**（行号会漂，锚点不会）。
>
> **行数口径**：脚本用 `raw.count('\n') + 1`（上面块里的 522 / 390 就是它）；`wc -l` 少 1
> （两文件均以换行结尾，脚本多算的那 1 行是末尾空串）。2026-09-23 实测 `wc -l`：
> `REFERENCE.md` = **521**、`GLOSSARY.md` = **389**。
> ⚠ **本节的这些数字随编辑变动**（写进来就会立刻变）——**复算一律用命令**：
> `wc -l /home/liux***ya/w6-kit/REFERENCE.md /home/liux***ya/w6-kit/GLOSSARY.md`，
> 条目数/引用点数用 `§5.1` 的脚本（复算命令见 §5.1 末）。

**首轮实测发现并已修正的 6 处真错**（这就是做这次自检的价值）：

| # | 位置 | 原登记 | 实测 | 修正为 |
|---|---|---|---|---|
| 1 | `w9r4` 报告 | `~/w9-evidence/w9r4/W9-R4-PHASE2-REPORT.md`（第 2 行；**该文件不存在**） | 真实文件名是 `W9-R4-TAKEOVER-REPORT.md`（无 `PHASE2` 那份） | `W9-R4-TAKEOVER-REPORT.md:1-2`（**该文件为冻结件 = 带日期的历史报告，行号稳定**） |
| 2 | `FIX-A` | `...V41-UPSTREAM-TRACK-20260922.md:39` | :39 是 #58068 行，`FIX-A` 在 :41 | `:41` |
| 3 | `FIX-B` | `...scheduler.py:1806` | :1806 是 `def` 行，`FIX-B` 字面量在 :1807 | `:1807` |
| 4 | `QW1/QW2/QW3` | `...V41-UPSTREAM-TRACK-20260922.md:41` | **该文件全篇无 QW 串**（QW 系列在 `V41-SGLANG-OPS-ROUND2-20260914.md:244-269`） | 改为该文件 `:246,248,244,254,268` |
| 5 | `ADR-004` | `~/w6-kit/guard/guards.conf` 的一处注释行（当时记的**历史行号**为 `:140`——该册 2026-09-23 注释改动后已位移，该册自记了 old→new 对照表；**引用请按行名**） | **guards.conf 全篇无 `ADR-004` 串**（当时 `:140` 是 #5237 行）；ADR-004 的实际引用点在 RUNBOOK 与 dose_ladder | 改为 `WINDOW-RUNBOOK.md` 的「参考」节 ADR-004 索引行 / 开篇索引「内存地板守卫」行 / 「窗口内」检查表的 `guard_stop(ADR-004)` 项、`v41_dose_ladder.sh` 的 `note="…,guard_stop(ADR-004)"` 行、`oom_gate.sh.pre-e-tier-20260918:133`（**冻结件 = pre-e-tier 历史副本，行号稳定**）。⚠ 2026-09-23 复核：本行原登记的四条行号（RUNBOOK 三条 `425`／`7`／`400`、`v41_dose_ladder.sh` 一条 `326`）**又已漂**（RUNBOOK 被并行修复者改过、dose_ladder 01:26 改过）⇒ **已全部改按行名/节名锚定，不再写行号**；连历史号也只留裸数字，**不写成 `文件:行` 形态**——否则仪器与人都还会去解析它 |
| 6 | `C1~C3` | `...V3-20260919.md:51-55` | :51 是空行，C1 行在 :53 | `:53-55` |

> 另修正 REFERENCE.md 侧 5 处：`#40352` 的 `V41-CTX600K-READINESS-20260922.md:244`（该文件无此号）、
> `#34846` 的 `V41-UPSTREAM-TRIAGE-20260920.md:17`（该文件无此号）、`#39187` 的 `:76`→`:77` 与
> `:315`→`:136`、`#55569` 的 `:36`（空行）→`:37`、`#4603` 的 `:95-98`→`:96,98`、
> `#45861` 等批号的 `:227,206`→`:206`。**全部已改毕并复跑通过。**

---

## 6. 已知交叉引用错位（只登记，未改任何既有文件）

| 位置 | 错位 | 正确 | 处理 |
|---|---|---|---|
| `~/w6-kit/guard/guards.conf` 的 `guard-watch` 行（原记 `:123`——**该册属主 2026-09-23 改过注释，行号已漂，请按行名看**） | 引 `WINDOW-RUNBOOK §7` 说明「已知缺口」 | 应为 `§7.5`（缺口本体）/ `§5.3`（重挂命令） | ★**属主已就地校准**（2026-09-23 注释改动）；本行**已消解** |
| `~/w6-kit/guard/guards.conf` 的 `guard-watch` 行（同上） | 称两个裸进程守卫"没有任何单元保证…不会自愈" | `oom-gate-monitor.service` 已 systemd 托管（见同册 `oom-gate-floor` 行） | **仍未同步**（2026-09-23 复核）；只登记，不动文件 |
| `~/w6-kit/guard/BASELINE.md` 的「2026-09-17 五次更新」节的审核来源段（原记 `:189-190`） | 旧版路径写成裸 `r4-ops-work/…`（从 `guard/` 下无法解析） | 已在同处**自行补注更正**（2026-09-23） | 已修复，无需动作 |
| `~/w6-kit/guard/BASELINE.md` 的同节（原记 `:199`） | 旧版称三个历史启动脚本"都不存在" | 已在同处**自行订正**（文件在 `~/w6-kit/` 留档，只是离开启动路径） | 已修复，无需动作 |
| `~/w6-kit/README.md` 的量具索引表 → `oom-gate/oom_gate.sh.pre-e-tier-20260918` 行（自述"`ADR-004` 引用在 `:133`"） | 自述行号指**冻结副本**（`oom_gate.sh.pre-e-tier-20260918` = pre-e-tier 历史副本，行号稳定）⇒ **不是错位** | 无需动作 | 只登记。该册属主 2026-09-23 02:13 仍在改 ⇒ **引用请按行名/表行**，不要抄行号 |
| `~/w6-kit/guard/BASELINE.md` 的 md5 登记行（`flashinfer-arch-guard.sh` 记 `dacd7afc7339`） | **实测 md5 = `3e6f1957ced2`**（同一行的登记值与实际不符；`refcheck.py` 报 FAIL MD5） | 该行由 `guard/` 属主维护 | ★**只登记，不动文件**：这是**目标文件自身的登记错误**，不在本次两册的权限内（本次只允许改 `REFERENCE.md` 与 `GLOSSARY.md`）；请 `guard/` 属主核 |
| 两册里指向**仍在被编辑的非目标文件**的行号（`<source-repo>/start.sh` 2026-09-23 01:48、`~/w6-kit/oom-gate/oom_gate.sh` 01:26、`~/w6-kit/v41_dose_ladder.sh` 01:26、`~/w6-kit/v41_devfree_host.sh` 01:26、`~/w6-kit/guard/flashinfer-arch-guard.sh` 01:25、`~/w6-kit/README.md` 02:13） | 这些文件**不在本轮允许改的范围内**，指向它们的行号引用（如 `start.sh` 的 615／618／622／626／640／643／648）**可能已漂** | 待下一轮 / 待各属主 | ★**只登记，不改**——按纪律，行号引用只应指向冻结件；这些是活文件，本轮**只把 6 个目标文件**的引用改成了锚点 |

---

*本表由引用登记员（reference registrar）生成：**首轮**为只读采集、未改任何既有文件；**2026-09-23 修复轮**由文档修复工程师 F 在本册与 `REFERENCE.md` 内修订（**只动这两份文件**，其余文件一字未改）。*
