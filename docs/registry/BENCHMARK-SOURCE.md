# BENCHMARK-SOURCE — 基准来源与口径（正典档）

> **版本**：v2.0 / 2026-10-23（0.3.3 T33-03 item3 正式版；取代 2026-10-14 骨架版，骨架内容以
> §八"历史段"收编保留）
> **状态**：0.3.3 战役现役口径正典。任务书法源：`~/luz030-opt-campaign/docs/plan/033-TASKBOOK-V2-20261023.md`
> §T33-03 目标 3（:497）——"把 PR 与 decode 的口径写进 `docs/registry/BENCHMARK-SOURCE.md`"；
> 欠账闭合：T33-03-P0-REPORT §7 未做项、TOOL-MAINT-20261023 §3 未做项。
> **数据来源**：新口径全部数值引自 W1-A 重采报告
> `~/luz030-opt-campaign/docs/plan/033-W1/T33-03-P1-RESAMPLE-REPORT.md`（原始档
> `logs/S-P1-RESAMPLE-20261023/`，142 件）；量具 md5 台账引自
> `~/luz030-opt-campaign/docs/plan/033-W1/TOOL-MAINT-20261023.md` §4 并于 2026-10-23 本档落笔前
> md5sum 亲验一致；旧口径历史锚引自任务书 §4/§6/附录 D。**本档不自算新数**。
> **本档性质**：纯文档（0 靴）；不改任何量具/产线面。

---

## 一、口径总则（先读此节，再读任何数字）

1. **分口径律**：一切性能读数必须带口径标签（PR repeated / PR real / DE committed / full-accept
   等效 / liter / warm 门 / SparkDash UI）。无口径标签的数字不得进任何表。
2. **同口径可比律**：`repeated` 只与同口径 repeated 比；`real` 只与 real 比；SparkDash UI 与
   headless DE 不混比；prose 与 structured 不混比。
3. **分列不互推律**：DE per-stream 与 aggregate 两统计分列，不得互推；committed 与
   full-accept 等效两字段独立分列，不得互相推导。
4. **投影非验收律**：绝对投影数不是第二验收线；验收一律以任务书 §6① 的相对带为准（§六）。
5. **历史值仅历史律**：A6 锚、v1.2 带、C13 旧五档、旧 8001 口 liter 锚、上游 16–42% 虚高带
   等历史值只可出现在解释/否定语境，不得作参照基线。
6. **量具钉值律**：判读前先对 §五 md5 台账；md5 不符的量具产出不得入档。

---

## 二、口径定义与量具

### 2.1 PR（prompt 处理速率）——repeated 与 real 双 filler 口径

- **定义**：PR 是 **prompt 处理速率**（prefill 面），公式 `tok_s = prompt_tokens / TTFT`
  （TTFT = 首字时刻−请求发出，fetch 前 t0）。**不是 decode 吞吐**（任务书附录 D :1381）。
- **量测形**：headless `sd_bench --mode pr --pr-filler <repeated|real>`，每档 **3 次独立调用取中位**，
  fresh uuid4 salt，512t×2 预热（pr_ladder6 调用面纪律）；产线口 127.0.0.1:8899 直连。
- **filler 两口径**：
  - `repeated`：`" the"`×N 重复填充（sparkDash 社区口径，构造 token 计数精确=名义档位）——
    历代正典带（v2 基线、W1-A 新锚）均为该口径；**相对 real 有虚高**（实测带见 §四）。
  - `real`：真实文本分布填充（0.3.1 `sd_bench_real_text.patch` 臂）；W1-A 起为并列入档的
    参考口径。real 臂实际 prompt_tokens ≈ 名义档位 ×0.85–0.88（自然文本 ~4.7 chars/token vs
    构造口径 4.0 基准；W1-A §6.1），tok_s 按实测 ptok/TTFT 计，属口径固有属性。
- **量具**：交付仓 `tools/bench/sd_bench.py`（+`pr_ladder6.sh` 调用面）；W0 起行含
  `cached_tokens/uncached_tokens/uncached_tok_s/reasoning_tokens`，`tok_s` 原式不变=total 口径主标签。
- **边界**：SparkDash UI 历史只存 decode bench（无 64k/512k PR），故 PR 正典只能用 headless
  repeated 3 次中位表；**不得拿 SparkDash 短 prompt TTFT 反推 PR**（任务书 §4 注 :274）。

### 2.2 DE（committed decode）——c1/c8 headless 正典 + 双口径账本

- **定义**：DE-48 是 **committed decode tokens/s**：`(completion−1)/(t_last−t_first)`
  （任务书附录 D :1382）；正典量测形 headless `sd_bench --mode de --type prose --max-tokens 400`
  （mt400，greedy temp0/top_p1），5 次中位。
- **量测形（W1-A）**：`de_c48` 五档梯（c1/c2/c4/c8/c16），prose mt400，runs=5/cell、warmups=2、
  arb×3 池化 15 run；8899 直连。
- **两统计分列**：per-stream（`per`/`per_all`）与 aggregate（`agg`）分列不得互推（同 run 的
  c8 aggregate 与 per-stream 无换算关系；旧档实例：c8 agg 249.10 vs per-stream 32.58）。
- **双口径账本（T33-03 Phase 0 起，W0 落盘）**：量具输出同时携带
  - `committed_decode_tps`（真实提交 token；=原 per/agg 同式）；
  - `full_accept_equiv_tps = committed×(1+nextn)/accept_len`（nextn=5 的等效口径副标签，
    **仅用于与官方/旧表可比，不得当真实 token 吞吐**；任务书附录 D :1385）；
  - `accept_rate`、`avg_verified_len`、`reasoning_tokens`、`cached_tokens`；
  - per-request 闭合行：`Σ(completion−1)=Σgenerated`、`gen=accepted+b`、
    `accept_len=1+γ·accept_rate`（仅整窗满发 draft 严格成立；流末步截断记 `truncated`
    注记不强判）。
- **量具**：战役仓 `tools/de_c48_bench.py`（梯/池化/锚对照门）+ 交付仓 `sd_bench.py`（单档
  run_de 底座）；de_c48 内建探针 md5 门钉 `sd_bench.py`。

### 2.3 liter / C13（冻结文学语料并发 PR）

- **定义**：C13 liter = 冻结文学语料（lit7 真实文本）上的并发 prompt 处理速率；语料按
  `estimate_tokens` 精确达标（524288 档 prompt 2,097,149 字符，fill×4 基准），C1/C2/C4 三档
  并发流级，×3 次中位（W1-A §6.4）。
- **量具**：战役仓 `tools/conc_pr_driver.py`（正典参数化版：G5 守卫=未显式声明的非常规口即拒，
  `--measure-port` 显式声明放行）+ `tools/lit_driver.py`（串行臂）；调用面 `pr_ladder7_lit.sh`。
- **口径迁移（2026-10-23 起）**：旧 liter 锚经 `127.0.0.1:8001` 本地 concurrency-proxy 量测口；
  当前链上无本地 8001 监听，W1-A 起 liter 走 **`127.0.0.1:8899` 引擎直连**（与本窗 PR/DE/warm
  同口，内部自洽）。主会话已裁接受该迁移；**旧 8001 口锚转历史**（§3.3），与 8899 直连新锚
  同族一致（Δ≤+1.6%）说明代理层对 liter PR 影响可忽略。

### 2.4 warm 64k 门（boot 链自检门）

- **定义**：64k PR（repeated filler）warm 读数，5 连读、**首样本丢弃后中位**，阈值 **≥5600**
  （任务书附录 D :1384）；**不是 decode 读数**。
- **量测位**：boot-prod 链 post-boot selfcheck 内嵌（非独立脚本）；W1-A 双靴 in-chain
  repeated 侧 6478/6490 全绿。
- **口径注**：阈 5600 属 repeated 口径门；real 侧同形复算（64k real 5 连读首读弃、余 4 读
  中位 **5738.9**，W1-A §6.2）**仅作口径对照，不作门判**。

### 2.5 SparkDash UI（仅追溯/互证，不作验收）

- **定义**：SparkDash（MiaAI-Lab）仪表盘 UI decode bench（maxTokens=400）；c1–c8 为
  per-stream、c8 aggregate 单列；prose/structured 两种 prompt 不得混比；UI 与 headless DE
  不混口径（任务书附录 D :1383）。
- **正典关系**：DE 正典=headless（§2.2）；SparkDash prose c1/c8 aggregate 91.74/251.12 与
  headless 91.64/249.10 仅互证（差 0.1%/0.8%，任务书 §4 :270）。**仅追溯用途**。
- **在档 run**（2026-10-23 00:56/00:57Z，两 run 均在最终版本锁自检之后）：见 §3.5 历史锚表。

### 2.6 FI-LAND B-pilot R 比（tools/filand/bench_b_pilot.py）

- **定义**：在役 decode 路径（leg A，in-image flashinfer 0.6.18，含 split+repack+kernel）对
  候选（leg B，0.7.2 wheel kernel-only）的冻结形状格几何均值 `R = geomean(t_A/t_B)`；
  冻结公式 `tools/filand/B-PILOT-FORMULA-FROZEN.json`，判读线零事后改。
- **判读**：R≥1.4 才烘 r033；1.2–1.4 默认 abort（继续须用户明批，勘误 E-13）；<1.2 abort③
  关案（任务书 §T33-06；量具头注同源）。leg A 已含 T33-06 F0 patch-3（2026-10-23）。

### 2.7 端口与量测口（任务书附录 D :1388）

| 口 | 用途 |
|---|---|
| 8899 | 产线引擎（W1-A 全部读数的量测口：PR/DE/liter/warm 直连） |
| 8898 | 测试窗直连 |
| 8001 | 文本网关（**当前链上无本地 8001 监听**；旧 liter 量测口，已迁移，见 §2.3） |
| 8002 | VL 网关 |
| 8003 | 鉴权入口 |

---

## 三、当前锚与历史锚（新旧双列）

> 当前锚=**W1-A 重采（2026-10-23 停机窗，靴 1/靴 2 双靴全绿、基线五件套零漂移）**；
> 旧锚=v2 基线（2026-10-23 6.17 回滚后 repeated/headless 表）。判读参照规则见 §六。

### 3.1 PR 七档双口径（headless `sd_bench --mode pr`，每档 3 次中位；W1-A §6.1）

| 名义档 | 旧 repeated（v2 基线） | **新 repeated（W1-A）** | rep vs 旧% | **新 real（W1-A）** | real 离散% | real 实测 ptok | real/rep% |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 8k | 5555.6 | **5532.7** | −0.41 | **4963.4**\* | 14.2\* | 7223 | −10.3 |
| 16k | 6161.6 | **6171.2** | +0.16 | **5498.2** | 1.7 | 14080 | −10.9 |
| 32k | 6452.8 | **6402.6** | −0.78 | **5684.1** | 0.5 | 27817 | −11.2 |
| 64k | 6468.1 | **6447.7** | −0.32 | **5762.0** | 1.2 | 55942 | −10.6 |
| 128k | 6194.6 | **6192.6** | −0.03 | **5573.7** | 0.4 | 111358 | −10.0 |
| 256k | 5559.6 | **5550.0** | −0.17 | **5130.9** | 0.1 | 222444 | −7.6 |
| 512k | 4376.9 | **4384.8** | +0.18 | **4259.9** | 0.1 | 444635 | −2.8 |

\* 8k real 为高离散档：靴 1 首批 3 读中位 4625.4（离散 17.1%）→ 靴内加读 5 读中位 4989.8
（10.1%）→ 靴 2 复测 3 读中位 4962.0（14.2%）；两靴同形复测离散均 >5% ⇒ 判定为**口径固有
短测程高方差**（测程 ~1.4s，单次 200ms 调度抖动即 ≈14%），非引擎异常；**锚值=11 读池化中位
4963.4**，该档不作紧公差判读位（≥16k 档离散 ≤1.7%）。（W1-A §6.1 注）

- repeated 七点与旧带最大偏差 |−0.78%|（32k）——**无漂移信号**；64k 峰位保持；512k 4384.8。
- 跨靴复现性（靴 2 抽检对靴 1，W1-A §6.5）：repeated 64k +0.03%、repeated 512k +0.38%、
  real 64k +0.18%、real 512k +1.02%。
- real 臂 ptok ≈ 名义 ×0.85–0.88（§2.1），512k 档 444635 ptok 即 ~0.85。

### 3.2 DE 五档（headless `de_c48` prose mt400；W1-A §6.3）

| 档 | 旧锚（v2 基线） | **新锚（W1-A）agg_med** | 离散% | per_med | P95 | P99 | Δ% vs 旧 | 判定 |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| c1 | **91.64** | **90.54** | 0.7 | 90.54 | 90.77 | 90.77 | **−1.2** | IN-BAND(±3%) |
| c2 | （旧 C13 128.89，仅历史） | **131.93** | 3.7 | 69.44 | 69.58 | 69.62 | — | NEW-TIER 建锚 |
| c4 | （旧 C13 168.7，仅历史） | **169.93** | 7.8 | 44.69 | 46.94 | 47.80 | — | NEW-TIER 建锚 |
| c8 | **249.10** | **251.14** | 10.0 | 32.29 | 34.43 | 35.00 | **+0.8** | IN-BAND(±3%) |
| c16 | （旧 C13 357.9，仅历史） | **366.29** | 6.7 | 24.66 | 26.74 | 27.79 | — | NEW-TIER 建锚 |

- c1/c8 偏差 −1.2%/+0.8% 均 ≤3%，不触发复测/G-BL 漂移上报（任务书 T33-03 验收门 :523）。
- **c2/c4/c16 = T33-08 F6-B 的唯一当前锚**（旧 C13 五档 88.59/128.89/168.7/244.79/357.9
  仅历史；新锚对旧相对 +2.4%/+0.7%/+2.3%）。
- c8 per_med 32.29 与 aggregate 251.14 分列不得互推；c16 早停 0（无 OOM/截断）。
- 旧锚 c8 分列注：v2 正典 c8 同样本 per-stream 32.58、五次 per 中位 33.17（任务书 §4 :270）。

### 3.3 liter C13（524288 冻结文学语料 ×3 流级中位；W1-A §6.4）

| 档 | 旧锚（8001 量测口，**转历史**） | **新锚（W1-A，8899 直连）** | Δ% |
|---:|---:|---:|---:|
| C1 | 3757.7 | **3818.6** | +1.6 |
| C2 | 2849.8 | **2851.6** | +0.06 |
| C4 | 1571.0 | **1592.7** | +1.4 |

- 衰减率：C2/C1=**0.747**（旧 0.758）、C4/C1=**0.417**（旧 0.418——两窗同值级一致）。
- 口径迁移注（§2.3）：旧锚 8001 口不在现链上，主会话已裁接受 8899 直连口径；旧锚仅历史对照。

### 3.4 warm 门（64k PR repeated，阈 ≥5600）

| 项 | 旧（v2 基线） | **新（W1-A）** |
|---|---|---|
| in-chain warm 门（repeated） | 首轮 6463.4 → 最终复检 6415 | 靴 1 **6478**（runs=[5573,6326,6493,6480,6476]，首读弃余 4 中位）/ 靴 2 **6490**（runs=[5682,6489,6491,6463,6492]）——双靴 ≥5600 绿 |
| real 侧对照（不作门判） | — | **5738.9**（64k real 5 连读 [5719.3,5708.0,5756.4,5771.0,5721.4]，首读弃余 4 读中位；W1-A §6.2） |

### 3.5 历史锚清单（仅解释/否定语境可用）

| 历史锚 | 数值 | 出处/性质 |
|---|---|---|
| A6 PR 七档 | 5522.5/6040.2/6271.3/6289.3/6048.1/5427.9/4290.0 | 任务书 §4 注 :274；v1.2 历史对照 |
| A6 DE | 88.64/242.83 | 同上 |
| v1.2 512k 斜率带 | −28.65%→−25.5~−23.7%、3.1~4.9pp（A6 旧峰 ≈6012.6 口径） | 任务书 §4 注 :276；仅历史 |
| 上游 repeated 虚高带 | 16–42%（MiaAI-Lab#21） | 本栈未复现，转历史（§四） |
| C13 旧五档 DE | 88.59/128.89/168.7/244.79/357.9 | 任务书 §T33-08 :666；仅历史 |
| liter 旧锚（8001 口） | 3757.7/2849.8/1571.0，C4/C1=0.418 | §3.3；已转历史 |
| SparkDash prose UI | c1 91.74/c2 67.04/c4 44.74/c8 32.69 per-stream；c8 agg 251.12；c1 TTFT 231.26ms（2026-10-23 00:57Z，`83c9d5d0…`） | 任务书 §4 :267；仅追溯/互证 |
| SparkDash structured UI | c1 164.12/c2 118.99/c4 71.10/c8 46.23 per-stream；c8 agg 305.74；c1 TTFT 322.38ms（2026-10-23 00:56Z，`9c659af0…`） | 任务书 §4 :268；仅追溯 |
| DE 旧门槛带 | 旧 DE 90 门槛、85.4–89.5/89–90 带 | 已作废，不再作目标（任务书 §6② :311） |

---

## 四、repeated 虚高与 real 换算律（实测带取代历史带）

- **本栈实测虚高带（W1-A §7，repeated 高出 real，按 repeated/real−1）**：8k **+11.5%**（按
  8k real 池化锚 4963.4）、16k +12.2%、32k +12.6%、64k +11.9%、128k +11.1%、256k +8.2%、
  **512k +2.9%**——即 **2.9%–12.6%**，中带 ~11%，**档位越大越窄**。
  （对偶口径：§6.1 real/rep 列为 real 低于 repeated 2.8%–11.2%，分母不同、两列并存。）
- **上游 16–42% 带在本栈未复现**（上沿 16% 仅在 8k 档首批冷读低基线上短暂出现，复测后消失），
  自本版起该带**转历史**，仅保留于 §八上游口径终源作社区已知属性注记。
- **换算律（W1-A §7 判读律）**：B25 M2 等以 real 口径换算/对比时，**必须用 W1-A 同档实测比值**
  （§3.1 real/rep 列），不得沿用 16–42% 平带，**也不得跨档外推**（512k 比值 1.029 ≠ 64k 的
  1.119）。
- **real ptok 律**：real 臂实际 prompt_tokens ≈ 名义档位 ×0.85–0.88（自然文本 ~4.7 chars/token
  vs 构造口径 4.0 基准）；tok_s 一律按实测 ptok/TTFT，不得按名义档位折算。

---

## 五、量具 md5 台账与 selfcheck 权威计数口径

### 5.1 md5 台账（2026-10-23 本档落笔前 md5sum 亲验，与 TOOL-MAINT §4 一致）

| 件 | md5 | 状态 |
|---|---|---|
| 交付仓 `tools/bench/sd_bench.py` | `410f543d4cc363defa66ffd54d190c9a` | W0 双口径 schema 版；de_c48/conc_pr 两量具探针 pin 门命中值 |
| 战役仓 `tools/de_c48_bench.py` | `a337f64e835a20b75f905ed5d11d6e4e` | TOOL-MAINT 任务 A 修复+§5c 自检后钉值（钉史：`f0dd91c4`→`84ff45b1`→`410f543d`(sd_bench)；本件 `3ba79b1d`→`811c8de3`→现值） |
| 战役仓 `tools/conc_pr_driver.py` | `333033ce2fae98b28187d106f7cbb14f` | TOOL-MAINT 任务 B 正典参数化新档（测量逻辑与归档原件逐字节同） |
| 战役仓 `tools/lit_driver.py` | `0fb5a0c498fe265a81e915bc02df59dc` | 零改动（W1-A/TOOL-MAINT 同值） |
| 战役仓 `tools/filand/bench_b_pilot.py` | `75cbf060b4f303d335948ac1087346f9` | FI-LAND B-pilot 冻结量具（含 T33-06 F0 patch-3） |
| 归档原件 `conc_pr_driver.py` ×3 | `4c7f34d36ac86852fffff34c8f2bf412` | 零触留档（S-ENG-EXEC/S-C13-EXEC/S-C13PRE 三处归档，亲验同值） |
| W1-A 副本 `conc_pr_driver.w1a.py` | `bca57cfb359fe6099f1901d272d2a8a1` | 窗档证据留档不删；功能已被正典参数化取代，**后续窗禁再用副本手法** |

### 5.2 selfcheck 权威计数口径

- **通则：凡工具 selfcheck 末行输出 `n=` 的，以该 `n=`（实际执行断言数）为权威数**，不以
  报告手工注记数为准（TOOL-MAINT §1.2 裁定；工具末行自述"本行 n=实际执行断言数，为权威数"）。
- 各量具现值：

| 量具 | selfcheck 末行形态 | 现值 |
|---|---|---|
| `de_c48_bench.py` | `SELFCHECK PASS n=<…> fail=0`（含 n= 计数行） | **n=48**（无 env）/ **n=49**（设 `DE48_OLD_TSV` 且档在，条件对拍项 +1） |
| `conc_pr_driver.py` | `CONC-PR-SELFCHECK PASS n=<…> fail=0`（含 n=） | **n=12** |
| `lit_driver.py` | `LIT-SELFCHECK PASS`（无 n= 行，按断言计） | 12/12（W1-A 与 TOOL-MAINT 双窗复验） |
| `sd_bench.py` | `SELFCHECK PASS`（无 n= 行；常驻断言计数） | 44/44（W0 落盘、W1-A 复跑同值；md5 `410f543d` 期间恒定） |

- **口径差注记**：W0 报告 de_c48"# 44/44"为手工注记常驻数（少计 1 条条件项），W1-A 本机
  "45 PASS"为实际行数——同件全绿、非漂移；该歧义已由 n= 计数行终结，今后一律以末行 n= 为准
  （TOOL-MAINT §1.2）。

---

## 六、判读门引用（全部引任务书行号，本档不自创）

> 引用基线：`~/luz030-opt-campaign/docs/plan/033-TASKBOOK-V2-20261023.md`（v2.1，已批准执行）。
> 本节只转述任务书判读门并给出当前锚的对应关系；任何改门/加门须回任务书修订流程。

1. **B25 512k PR 验收带（唯一验收口径）**——任务书 §6 表①行（**:310**）：
   - B25 512k PR **+4.4~6.9%**（相对同形 v2 基线，中枢 +5~6%）为**唯一验收口径**；
   - 按 v2 512k 基线 4376.9 的绝对投影 **4569.5~4678.9 tok/s**（绝对数仅投影，不是第二验收线）；
   - **`<+2%` 即 abort=4464.4**；**2.0–4.4% 为灰区 4464.4~4569.5，仅一次复测**，仍不过降级/关案；
   - **512k 斜率**：按固定参照峰 v2 64k=**6468.1** 换算为相对改善 **2.977~4.669pp**（报告
     2.98~4.67pp；中枢约 3.82pp），**由 PR 带唯一决定、只作交叉核对、不单独判红**；M2 同 run
     峰与 6468.1 偏离 >1% 时斜率只报告、不改变 PR 验收带（§4 注 :276）；
   - **同形基线偏离 4376.9 时只按相对带重算**（:310 备注）。W1-A 重采 512k repeated 4384.8
     （+0.18%，无漂移信号）⇒ M2 判读仍按 §6① 相对带执行；绝对投影数不在本档重算。
   - A 轨 ≤−6.5% 已按 U-01 退出验收线/目标/门/KPI；v1.2 绝对值带与 3.1~4.9pp 为 A6 旧峰口径，
     仅历史。
2. **DE 对照门**——任务书 §6③（:312）/§T33-08 验收门（:680）：
   - DE ±3%；c1/c8 以 v2 基线 91.64/249.10 为参照，**若 T33-03 同窗重采则以重采值为准**；
     c2/c4/c16 **必须用 W1-A 重采值 131.93/169.93/366.29**（不得用旧 C13 锚）。
   - W1-A 已重采：c1 90.54（−1.2%）、c8 251.14（+0.8%）均 IN-BAND(±3%)。
3. **C13 重采验收门**——任务书 §T33-03（:523）：c1/c2/c4/c8/c16 有同形当前值；c1/c8 与 v2
   基线偏差 ≤3%（>3% 复测一次，仍 >3% 报 G-BL 漂移，不得直接改基线）；c2/c4/c16 写入 T33-08
   门；旧五档只作历史。（W1-A 已闭合。）
4. **warm 门**——阈 5600（repeated 口径，附录 D :1384）；real 侧 5738.9 仅对照不作门判（§2.4）。
5. **FI-LAND R 门**——R≥1.4 才烘 r033；1.2–1.4 默认 abort（继续须用户明批，勘误 E-13）；
   <1.2 abort③ 关案（任务书 §T33-06/〇；量具头注同源）。
6. **sparkDash 换算禁令**——SparkDash UI 读数仅追溯/互证，不得反推 PR（§2.1/§2.5）。

---

## 七、使用纪律（承接 0.3.1 骨架并升级）

1. 一切 PR 数字附 filler 档位（repeated/real）+ salt + 中位法；一切 DE 数字附口径标签
   （committed/full-accept 等效）与统计位（per-stream/aggregate）。
2. prefill 数字解读三件套：cache 档位 + hit_rate + filler 熵（0.3.1 纪律，继续有效）；
   `uncached_tok_s` 与 `tok_s`（total 主标签）分列。
3. 量具判别力纪律：改量具必附负对照（喂坏输入、看它因正确理由变红）；selfcheck 按 §5.2
   权威计数口径记录末行原文。
4. 跨栈对数（与社区 sparkDash 等外部数字比）须同口径+同档位+带仪器带（±10% 单提示带，
   §八 8.2）；E4 带外数字不作验收线。
5. 本档数值更新仅随战役窗报告（W1-A 形态：原始 JSON 全量在档 + 报告表）；**不得在本档
   自算新数**。

---

## 八、历史段：上游口径终源与 0.3.1 对表审计（原 2026-10-14 骨架收编）

> 本段为量具谱系与上游来源存档；其中"16-42% 虚高"等社区已知属性已按 §四转历史。

### 8.1 口径终源（上游引用）

**sparkDash**（MiaAI-Lab）——DGX Spark 社区推理基准/仪表盘项目（<https://github.com/MiaAI-Lab/sparkDash>）。
口径定义源件（v1.8.6 归档源码，逐文件对齐锚；定义审计 md5 留痕）：

| 定义源件（sparkDash 内路径） | md5 | 定义面 |
|---|---|---|
| `server/collectors/PrefillBench.js` | `eb3f68f2…` | PR：串行/每尺寸单请求/fresh salt/`" the"`×N filler/GEN 8/512t 预热/tok/s=usage.prompt_tokens÷TTFT |
| `server/collectors/DecodeBench.js` | `37c1380f…` | DE：greedy（temp0/top_p1/thinking off）/max 400（warmup 32）/stream+include_usage/decode tok/s=(completion−1)/decode 时长 |
| `server/collectors/LlmStreaming.js` | `90554e60…` | TTFT=tFirst−t0（fetch 前）；estimateTokenCount=len/4；median 均二中位 |
| `src/shared/llmPrompts.js` | `4fd85699…` | prose/structured/json 原文；code=clamp_00..49 单提示；c>1 非 code 型 `(stream i/n)` 后缀 |

社区已知口径属性：PR filler=重复 `" the"` ⇒ 行缓存命中致 PR 虚增（上游 issue MiaAI-Lab#21
自认；knapcio v2.3 亦给 real-text 修正数）——**本栈 W1-A 实测为 2.9–12.6% 档位相关带，未复现
上游 16–42%**（§四）；本口径数字只与同口径数字比。

### 8.2 对表审计结论（2026-10-06，0.3.1）

- **PR 面**：`pr_ladder6 type=sparkdash` 全列对 sparkDash 定义九项对表全 PASS（filler/salt/
  TTFT 公式/串行/预热全对齐）——SPARKDASH-ALIGN-20261006（战役仓 `docs/verdicts/`）；DIFF 9 项
  中 2 项已修（opt-in flag，锚字节面零触碰）、7 项登记不修、定义两义 0 项。
- **量具可比性定谳**：定义层可比（≡社区 sparkDash PR 定义）；仪器层带 ±10% 单提示带
  （W0 对桩"各自成系不作换算"）——跨读数比较须同口径+同档位+带仪器带
  （GAUGE-COMPARABILITY-20261006）。
- **DE c1 口径**：c1=prose/code 单提示精确原文；0.3.1 读数 81.67 为五点位中位（post 主分母）
  ——0.3.1 历史值，已被 v2/W1-A 正典取代（§3.2）。

### 8.3 工具谱系（交付仓 tools/bench/ 0.3.1 存档）

| 件 | 说明 |
|---|---|
| `tools/bench/sd_bench.py` | sparkDash 口径 headless 复刻基准（PR/DE；头注=逐文件对齐出处，勿凭记忆改）；0.3.3 W0 起为双口径 schema 版（md5 见 §5.1） |
| `tools/bench/pr_ladder6.sh` | PR 阶梯调用面（3 独立调用取中位/fresh uuid4 salt/512t×2 预热——knapcio 口径自注） |
| `tools/bench/sd_bench_real_text.patch`（+.README.md） | 第三 filler 档 `real`（真实文本分布填充；对照 repeated/random 臂隔离行缓存膨胀）——0.3.1 为补丁形态，0.3.3 W1-A 起 real 臂并列入档（§2.1/§3.1） |

### 8.4 致谢交叉引用

sparkDash 相关借鉴源（社区实测复测/real-text 修正数/filler 膨胀报告/上游基线表）收录于
[docs/ACKNOWLEDGEMENTS.md](../ACKNOWLEDGEMENTS.md) **B30/B31/B35/B46** 条（含出处锚与使用
状态）。上游 MiaAI-Lab/sparkDash 与其 issue 讨论对本仓量具口径的奠基作用在此一并致谢。

---

> **版本史**：v1.0（2026-10-14，0.3.1 骨架：口径终源/工具实体/对表审计/致谢）→ **v2.0
> （2026-10-23，0.3.3 T33-03 item3 正式版：新增 §一~§七（口径定义与量具、W1-A 新旧双列锚、
> 虚高实测带、md5 台账与 selfcheck 权威计数、判读门引用、使用纪律），骨架收编为 §八）**。
