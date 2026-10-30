# REDBAND-ROOTCAUSE-20261013 — 双栈生命周期红带族（~1000 tok/s）案头根因专项 · 2026-10-13

> **性质**：纯案头根因调查档（零 boot 零流量零部署面改动；判读权=主会话/用户）。
> 任务源=用户令「这类红带的触发根因请开展案头检查，分析是哪一类 bug，问题出在哪里，
> 给出根治修复方案」。对象=W5-PROMO-20261012 窗在役靴（W5PROMO-PROD）实例级红带
> （64k prefill 五连发 927.7/1000.5/999.4/998.5/999.6 tok/s=健康带 1/6，warm 不恢复）。
> 主档=`logs/W5-PROMO-20261012/`+红带靴 docker 日志（`logs/W5-PROMO2-20261013/teardown/
> pre-stop/`，替换靴窗替本档先存）+`docs/research/` 谱系档。
> 断言纪律：【档案】=档内原文/原始件复算；【实测】=本档案头新提取的原始数据；
> 【推演】=机制推算；【OPEN】=证据不足。**在飞窗注记**：W5-PROMO2 替换靴窗
> （01:11-01:56:44Z）在本档成文过程中收窗 GREEN，其读数作为时序内证据引用并逐条
> 注记时点；本档一切实时查询（/proc/vmstat/dmesg）已注记时点与在飞相位。

---

## 〇、一句话定谳（收窄级，非闭合级）

**冷页面/页缓存/Engram 盘读/内存压强四类候选被档内直证计数器排除；红带最可能=
「四秩 eager prefill 集合通信 peer-wait 相位轨道」族的又一实例——与 P3（960 带，
HOSTPROF 已 trace 定谳 87.4% 墙在 nccl、GPU 99.1% 忙非主机阻塞）与 R1-PROMO（940 带）
同族同带（940/960/1000=同一 boot 即锁定、warm 免疫、decode 免疫、prefix 无关平坦带
的红带家族）；本实例未做四秩 trace，定谳到「最可能候选+判别实验设计」级。**
bug 分类学=**d 类：代码级状态依赖（分布式调度/集合通信 boot 期多稳态锁入）**，
冷页面假说（窗档与规避律④ a105103 的「冷页面红带族」措辞）被三组反证**证伪**；
PROMO2 替换靴（第 4 栈、30min 沉降）GREEN（warm 门 6109.4）实证=重掷骰子可愈、
栈数单调论不成立。

---

## 一、现象画像（本档新提取的引擎级/启动级原始数据）

### 1.1 红带三重量纲的精确化【实测】

| 面 | 健康对照（验证靴 W5PROMO@8898，30 分钟前同机） | 红带（W5PROMO-PROD@8899） |
|---|---|---|
| warm 步 | req1=4105.8（ttft 15.963s）→req2=5941.5（11.031s） | req1=927.7（70.643s）→req2=1000.5（65.505s） |
| 探针×3 | 6049.2/6138.5/5975.5 | 999.4/998.5/999.6，**ttft=65.576/65.639/65.565s（极差 0.074s=0.11%）** |
| 逐 chunk（引擎 Prefill batch 行） | 16 chunk 各 ~0.65s（input throughput 5962-6743 tok/s），chunk1 6.5s（含 W5 首 chunk 三重位检） | 16 chunk 各 **4.0s**（1013-1034 tok/s），chunk1 14.5s；pending-token 每 chunk 递减 4096 严格等差 |
| Engram 层（adapter 60s 统计） | warm 窗 lookups=321,342/min hit 99.8% **reads=628** | 红窗 lookups=319,866/min hit 99.9% **reads=294**（两靴逐位同构，读路径空转） |
| boot 时长（boot_ledger） | 8m06s（00:12:17→00:20:23） | **9m18s**（00:42:16→00:51:34） |
| target verify 图捕获（Engine startup timings 行） | **49.38s**（bars 3.89s/it） | **102.34s**（bars 5.88-12.55s/it=2.07×） |
| draft verify 图捕获 | 8.47s | 10.60s（≈1.0×，正常） |
| 权重装载（Load weight end） | elapsed=162.66s，mem usage 75.25GB | elapsed=**158.27s（更快）**，74.79GB |
| python/容器起栈（点火→TP0 首行） | 4m00s | 3m59s（逐位同量） |
| DSV4 memory calc available_bytes | 14.46GB | **16.80GB（红靴更多 2.3GB）** |

来源：`logs/W5-PROMO2-20261013/teardown/pre-stop/r3prod-{head,worker-*}.docker.log` +
`logs/W5-PROMO-20261012/teardown/W5PROMO/r3boot-head.docker.log` + 两靴 boot-checks。

**画像要点**：红带墙 = 每 chunk 恒定 ~4.0s、与 prefix 长度无关（chunk2 与 chunk16 同价）、
请求间 metronome（0.11% 极差）、五连发零恢复轨迹；同时**全模型 forward 的 boot 期影子
（target verify 捕获 2.07×）与靴龄同现，而小模型路径（draft 捕获）、顺序大读（权重装载）、
纯 python 路径（起栈）全正常**。

### 1.2 pgmajfault 的三组反证（对窗档「冷页重面」归因的否证）【实测】

| 窗 | 请求面 | 01 机 pgmajfault | 墙 | 速率 |
|---|---|---|---|---|
| 验证靴 warm 步（2×64k，健康） | req1 4105/req2 5941 | +1113 | 28s | 40/s |
| 红靴 warm 步（2×64k，红） | 927/1000 | +3631 | 136s | 27/s |
| 红靴探针（3×64k，红） | 999 带恒定 | **+555** | 214s | **2.6/s** |
| 验证靴 warm 门（3×64k，健康） | 6049 带 | **+424** | 48s | **8.8/s** |
| **PROMO2 替换靴 warm 步×4（健康绿）** | 4073→6016→6106→6102 | **+9103** | 71s | 128/s |

三条否证：①**绿靴首请求冷页 fault（+9103）＞红靴红带期 fault（+3631）2.5 倍**——
fault 计数与红带**反相关**；②红带稳态 fault 速率（2.6/s）低于健康靴稳态（8.8/s）3 倍
而墙差 6 倍——fault 与墙**脱钩**；③量纲不符：若每 chunk 3.35s 额外墙=权重冷页重读，
需每 chunk 数 GB 级 NVMe 流量=数百万 4KB fault 或数千 2MB fault，实测仅 ~150-380/chunk，
**差 2-3 个数量级**。⇒ pgmajfault=首请求冷页通有面的伴生症状（两靴 req1 俱 >1000），
非红带限速器。窗档 ⓪ 节「冷页重面」与 a105103「冷页面红带族」措辞应勘正。

### 1.3 「主机侧阻塞」判读的否证【档案+推演】

W5-PROMO ⓪ 记「请求间 GPU 0%=主机侧阻塞面」——run.log 全档无 chunk 期 GPU 采样
（本档亲核 grep 零命中；gpu-residency 量具 [N/A]）。同带同族实例 P3 已有 trace 级测量
（R1-HOSTPROF §三）：D1 深窗**计算流 99.1% 满、零 >1ms 空洞、宿主 busy 仅 0.16s/step、
Python gap 0.36s/step**——宿主没有饿 GPU，墙在 nccl 集合自旋（AG/RS 中位 1.5→39.3ms
=×26，自窗内第一个集合起在场无爬坡）。「请求间 GPU 0%」在空闲期为当然真，不能承载
「主机侧阻塞」结论；本档判 P3-W5 同带同族 ⇒「主机侧阻塞」为**未测量的误判读面**。

---

## 二、候选根因树（逐候选证据链+判别）

### c-a 内核/驱动级 UMA 页管理行为 — **排除（主面）**
- 支持：无（仅 boot 前 drop_caches 律的历史相关面）。
- 反对：Engram reads=0-294/min（§1.1）=无页缓存层盘读风暴；MemAvailable 稳定
  11-14GB/四机、WATER-RED=0、memcg 8 相位零压强；fault 计数量级与墙脱钩（§1.2）；
  权重装载（75GB 大分配）红靴反而更快（158.27 vs 162.66s）——驱动大分配路径不慢。
- 【实测】判别力：装载快+图捕获慢同靴共存 ⇒ 非「驱动全慢」类。

### c-b 资源生命周期残留（第一栈退出残留：锁/shm/JIT 缓存/Engram 盘文件/GPU 上下文）
- 支持：双栈时序相关（红带靴=验证靴拆后 599s；R1-PROMO 红=FULLGATE 五靴马拉松后）。
- 反对【实测】：/dev/shm 仅 32B 级 sem.mp-* 残段（无大共享段）；Engram 分片容器内
  **只读挂载**（r3-boot-arm.sh:411 `-v "$eng:/engram:ro"`）零写入零生命周期问题；
  JIT 面 boot 期缓存命中（暖位 4s，两靴同）；容器残=0 四机核过；r3boot 测试容器净。
  且栈数单调论被否：PROMO2 第 4 栈（距红带靴拆 30min）GREEN。
- 裁：残留作为**直接载体排除**；作为**boot 期初始化竞态的偏置轴**（见 c-d）降级保留。

### c-c 内存压强-页缓存逐出稳态（第二栈驻留后 MemAvailable 低位→chunk 重冷读） — **排除**
- 反对【实测】：红靴 MemAvailable（01 机 10.8-11.9GB）与 Cached（10.1-11.1GB）不低于
  验证靴（11.3/9.9GB）；DSV4 calc 红靴 available_bytes 反多 2.3GB（§1.1）；
  Engram cache 零逐出告警+reads 空转；权重驻设备内存（Load weight end mem usage
  75GB）不依赖页缓存驻留，物理上无逐出-重读回路；健康对照靴同水位同足迹不同墙。
- 「warm 五连发不恢复」在逐出稳态假说下应随 LRU 适应出现部分恢复轨迹，实测零轨迹。

### c-d 代码级状态依赖：四秩集合通信 peer-wait 相位轨道（HOSTPROF 域） — **最可能（收窄定谳）**
- 机制：eager prefill 每 chunk ≈61 层 × 每层 2-4 次 TP 集合（attn AG/AR+post_experts
  AR+quant 变体；prefill_sp.py 装配面）；boot 期某秩（HOSTPROF：画像秩 TP0 99.2% 为
  先到方，迟滞在他秩）进入系统性迟滞相位 → 每次集合付 ~39ms 量子（P3 实测）→ 每 chunk
  120-240 集合 × 量子 ≈ 4s 恒定墙。**相位锁定态→warm 流量走同一 eager 路径不能
  破坏秩间相位关系→五连发不恢复**（分水岭判据的机理回答）；prefix 无关（集合次数
  ∝层数∝chunk 数、消息尺寸恒定=平坦带）；decode 走 CUDA graph replay（固定发射序、
  图内集合预先同步）→免疫；boot 期 target verify 捕获=全模型 eager forward 集合
  同染（2.07×）而 draft 小模型路径正常；红带值 ~800-1000 跨四形（43 键/47/48/50 键）
  同带 ⇒ 量子为协议/链路级常数而非消息级（与 NCCL LL/RoCE 单发路径的时间常数同量级）。
- 直接证据：P3 同带 trace（HOSTPROF §三：87.4% 墙=nccl，GPU 99.1% 忙，零宿主空洞，
  首集合即在 75.6ms 无爬坡=boot 锁入）+R1-PROMO 879/938/940（同带不恢复）+本实例
  §1.1 全画像吻合。
- 未闭合面【OPEN】：①本实例无四秩 trace/GPU 期采样直证（HOSTPROF P0 四秩同窗取证
  至今未执行）；②**触发面**（哪一秩、何变量锁入）未定——候选=boot 期 NCCL 通道/线程
  摆位竞态、RoCE NIC 前栈 QP teardown 后状态、JIT/fork 模块装载时序、核/IRQ 亲和对；
  双栈短窗为已观察偏置轴之一但非决定性（FULLGATE-RESTORE 拆后 ~10min boot 绿、
  R1-PROMO ~16min 红、PROMO2 30min 绿 ⇒ 概率性锁入，红带族史 ~3/~10 靴发生率）。

### c-d' 次级活候选：EMPTY_CACHE 重分配税的状态依赖放大 — **保留为第二候选**
- 机制：`DSV41_PREFILL_EMPTY_CACHE_TOKENS=8192` 每 chunk 后 `torch.cuda.empty_cache()`
  （prefill_empty_cache.py:41-51，64k 请求 15 次/发）+下 chunk GB 级瞬态重 cudaMalloc
  （[chunk,prefix] fp32 logits 每 src 层，64k 时 ~4GB/chunk）；若宿主 buddy/驱动分配态
  被前栈 churn 碎片化 → 每 chunk 付秒级重分配税。F6 verdict 已量该税常态 ~2×
  （0.2.7 缺省置 0 的原因）；ENGRAM-PREFILL §0 早在 Fam-A 时代即列此候选。
- 支持：warm 免疫（碎片不随使用愈合）、metronome、decode 免疫（图池不 empty）、
  前栈 churn 时序相关。
- 反对：PROMO2 第 4 栈绿（碎片无 30min 自愈的已知机制，kcompactd 主动性弱）；
  红靴 75GB 权重装载（同分配器路径）反而更快；红带值跨形同带（税应随分配尺寸形变）。
- 判别：见 §四验证窗 V2（empty_cache=0 臂+cudaMalloc 计时探针）。

### c-e 量具/环境 confound — **部分成立（判读面勘正）**
- 「主机侧阻塞」（§1.3）与「冷页重面」（§1.2）两判读面被否证=量具/推演层面 confound
  实存；但红带读数本身（探针冻结件+引擎 Prefill batch 行双源互证）量具稳健。

**判别矩阵小结**：三重量纲（pgmajfault/GPU 0%/chunk 4s）中，pgmajfault 排除 a/c/e、
GPU 0%（chunk 期无测量）不能承载任何结论、chunk 4s 恒定+boot 影子分布（捕获慢/
装载快/draft 正常）联合排除 a/c、强支持 d（弱支持 d'）。

---

## 三、与历史族谱系结论

1. **940（R1-PROMO）/960（P3）/1000（W5-PROD）=同一家族**（高置信）：同带
   （786-1035 平坦、四形同带）、同签名（boot 即锁定、warm 不恢复、decode 绿、
   重启重掷即愈）、同形面（皆带 R1 fork 路径形；W5 验证靴绿=形非固有的同门反证）。
   HOSTPROF 的 P3 trace=本族的唯一直接机理测量（集合 peer-wait×26）。
2. **Fam-A（KV-V41/W1-B1，43 键时代，800 带）=同动力学类、触发相不同**（中置信）：
   同为 boot 即锁定平坦带+decode 绿+复靴即愈；但触发相=长空窗（≥8h idle）冷机首靴，
   与本族短窗双栈相反向。若统一，统一载体应为「boot 期四秩 prefill 管线降级态」
   （如冷链路/空闲电源态下的初始化竞态）而非冷页面。**用户工作假说「冷页面×大权重栈
   ×host 侧读路径」家族统一被本档证伪**——冷页与 host 侧读路径在本实例被直证排除
   （§1.1/§1.2）；建议谱系措辞改为「boot 锁入四秩 prefill 降级态族（触发相：长空窗/
   短窗双栈两轴）」。
3. **KV-V41 累积崩族（4400→~600 跨 flush 不可逆+Engram thrash 57%）=不同族**
   （用户预判正确）：累积型（~500k token 后崩）vs 本族 boot 即红；且该族 v2 主判自证
   「Engram 读路径近乎空转、靴已 4-6× 慢」（ENGRAM-PREFILL §0 v2）——与本档 §1.1
   「读路径空转+墙在别处」同法互证，但崩族另含头崩（buddy 碎片×深前缀）独立面。
4. **W1 判别窗结论的再解释**：载体①「首靴冷态坐实主载体」的 B1 慢/B2 快对照，
   在轨道语义下=「冷机 boot 锁入坏相位/复靴重掷入好相位」；EMPTY_CACHE 零害
   （B3 绿）对 d' 的**常态**毒性排除成立，但不排除**状态依赖放大**（本档 d' 仍活的
   正是后者）。
5. **R1-PROMO2「warm 修复」结论勘正**：本档证明 warm 步不修复坏锁入（W5-PROD 五连发
   实证）；PROMO2 绿=好骰子靴+warm 步恰好首测，warm 步的**探测价值**（红带拦截门）
   成立、**修复价值**不成立。规避律③的语义应从「修复动作」勘正为「探测动作」。

---

## 四、根治修复方案（分级）

### P0 行为级（在役，视为缓解非根治）
1. 规避律④（a105103）骨架保留：沉降 ≥30min+warm 加量 64k×4+**红带现形即停靴**。
   本档修正两点：①「冷页面红带族」措辞勘正为「boot 锁入红带族」（机理面，a105103
   的操作面不受影响）；②30min 沉降的机理支撑弱化（§二 c-d：概率性锁入，PROMO2 绿
   可为好骰子）——**可靠的组件是「红带现形即停靴重掷」**（史 3/3 愈：R1-PROMO 回退靴
   /PROMO2/V41B 族），沉降延长只是降低坏骰子概率的保守项。
2. warm 门常设为 boot 收容判读（已在役）——本档建议 OPS-MANUAL 注记其探测语义。

### P1 配置级（判别+缓解双承载；零代码）
1. **boot 期红带预测哨兵（新增，零代码增量）**：`Engine startup timings` 行的
   `target_verify=X` 已是免费信号——本形健康带 46-49s、红带靴 102.34s（2/2 分离）。
   规程：boot rc=0 后 grep 该行，**X>75s ⇒ 预测红带 ⇒ 直接执行替换靴（省一次 warm
   步红带流量与在役风险）**；数据落 boot 台账（F-9 哨兵面扩字段）。三靴校准后可硬化
   为判读线。
2. **NCCL_PROTO=Simple 单窗 A/B**（HOSTPROF P1 承载，今日仍未执行）：同形单靴
   `NCCL_PROTO=Simple`（当前 ^LL128）跑 warm 门——红带消失⇒LL 协议×流形状相互作用
   定谳+获得配置级缓解；不消失⇒轨道结构面，转 P2 四秩取证。附带产出：对 D1-R
   「快速重启 -16.7%」面的协议归因。
3. NCCL 通道/线程摆位钉扎试验（次序在后）：`NCCL_MAX_NCHANNELS` 固定值 +
   逐秩 CPU 亲和钉扎（缩小 boot 期竞态空间）；与 2 同窗可组合。
4. **页缓存预热通道问题（任务书问项）的裁定**：本族根因不在页缓存（§1.2），**禁主动
   预热页缓存红线维持不动、无需为本族开任何预热通道**（fadvise/只读映射驻留等讨论
   对本族无增益；首请求冷页 +N 千 fault=通有一次性面，4073 tok/s 带已可接受）。
   EMPTY_CACHE 键维持现值（W1-B3 零害实证；若 V2 判 d' 坐实再议 8192→0）。

### P2 代码级（根治闭合路径）
1. **四秩同窗 census trace（HOSTPROF P0，本族 5 天悬置的闭合钥匙）**：census 量具
   扩四秩同步 trace+AG 到达相位对齐。**执行协议挂靠规避律④红带取证段**：红带现形
   验证窗内先取证（10-15min 四秩 trace+GPU 1s 采样）再拆靴——判据二选一：
   (i) 存在固定迟滞秩 ⇒ 查该秩 boot 期独有面（NIC/QP/JIT/亲和）→ 点对点根治；
   (ii) 相位轨道无固定迟滞秩 ⇒ 结构面 → P2.2。
2. **boot 末轨道检测-重置钩子（修复件设计，d 类坐实后实施）**：ModelRunner boot 尾
   （fail-safe 后）注入一次 4096 tok 合成 chunk，测 per-layer 集合墙（正常 ~0.7s）；
   >2× 阈值 ⇒ 判锁入 ⇒ **destroy/recreate TP NCCL communicator 后重测**（通信子重建
   重掷通道摆位，不需整机重启）——即把「重启治愈」内化为「boot 内自愈」，把红带
   从「停靴替换」降为「boot 延长 ~2min」。挂点=sitecustomize 既有 scheduler/model_runner
   装配链，fail-safe 同款防御式（异常则放行+横幅）。
3. **d' 坐实时的修复件**：prefill_empty_cache.py 增 `DSV41_PREFILL_EMPTY_CACHE_MODE=
   pool`（chunk 瞬态改持久 grow-only 池+idle_release 统一回收，绕过每 chunk
   cudaFree/cudaMalloc 对）；或 8192→0 键改形（已有 F-2 臂先例）。
4. Engram 盘文件生命周期/共享段回收/atexit 清理：本档核过无残面（§二 c-b），**无需
   修复件**；/dev/shm sem.mp-* 微残段（32B 级）可顺手在 r3-stop 加清理（卫生级，非本族）。

### 验证窗设计（一锤定音判别实验，按序）
| 窗 | 设计 | 判别 | 预算 |
|---|---|---|---|
| V1 | 任一 boot 后读 `target_verify` 值+逐靴登记（可挂自然窗零成本） | 建立红带预测线（现 2/2：49s 绿/102s 红） | 0 |
| V2 | 红带取证窗（下次红带现形）：四秩 trace（P2.1）+nvidia-smi dmon 1s（host 侧）+`NCCL_PROTO=Simple` 重掷一靴 | GPU 忙+AG 39ms 带⇒c-d 定谳；GPU 空闲+cudaMalloc 慢⇒c-d' 定谳；Simple 绿⇒协议面+缓解到手 | 1 窗 |
| V3 | empty_cache=0 单臂（若 V2 判 d'）：48/50 键同形唯键差 8192→0，warm 门判读 | 红带消失⇒d' 坐实+键级修复；不消失⇒回 c-d | 1 窗 |
| V4 | （远期）轨道检测-重置钩子上窗：故意红带靴上执行 comm 重建，warm 门判读 | 重建后绿⇒P2.2 修复件成立=根治 | 1 窗 |

---

## 五、红线合规声明

纯案头：零 boot 零流量零部署面改动零 sudo（sudo -n 拒口令零接触）；在飞 W5-PROMO2
替换靴窗（01:11-01:56:44Z）全程未触碰，其收窗读数以已落档 run.log 引用；实时查询
仅 /proc/vmstat、/proc/meminfo、/proc/buddyinfo、/dev/shm ls、journalctl/dmesg 只读
（时点 02:08Z 注记，彼时窗已收窗、新靴在役）；~/migrate-assets（adapter 全件只读）、
~/sglang-main-src、~/dsv41-engram 只读；logs/ 全档只读；引用逐条标源；【档案/实测/
推演/OPEN】分层；git=单文件 add（本档一件）中文 message 禁 --amend 禁 add -A。

## 六、证据索引

- 红带靴 docker 日志（含 Prefill batch 逐 chunk 行+Engram 60s 统计+idle-release 行+
  Capturing batches bars+startup timings）：`logs/W5-PROMO2-20261013/teardown/pre-stop/
  r3prod-{head,worker-<node0{2,3,4}>}.docker.log`（:406-:1210 红窗段）。
- 健康对照：`logs/W5-PROMO-20261012/teardown/W5PROMO/r3boot-head.docker.log`+
  `bench/W5PROMO/warm_request_0.json`+`bench/W5PROMO-PROD/*`+`state/sentinel-*`+
  `boot-checks/W5PROMO{,-PROD}-boot.log`+`state/boot_ledger.txt`。
- PROMO2 绿靴（时序内证据）：`logs/W5-PROMO2-20261013/run.log`（warm×4 曲线 01:50-01:52Z
  +OUTAGE-END 01:56:44Z）+`state/sentinel-warmstep-{pre,post}.txt`（+9103）+
  `state/boot_ledger.txt`（8m06s）。
- 谱系：`docs/research/R1-HOSTPROF-20261011.md`（§三 nccl×26+GPU 99.1%+P0/P1 悬置件）、
  `R1-FULLGATE-RESULT-20261012.md` §三/五-2/五-3、`R1-DEAUDIT-20261012.md` §3.3、
  `BOOT-LOWSPEED-ROOTCAUSE-20261010.md`（Fam-A/载体①②/慢靴 boot 时长弱信号）、
  `ENGRAM-PREFILL-DEGRADATION-FORENSICS-20261009.md` §0 v2、`W5-PROMO-RESULT-20261012.md` ⓪、
  `W5-PROMO2-RESULT-20261013.md`（f37d3fc）。
- 代码面（只读）：`~/migrate-assets/dsv41/adapter/{engram_backend.py（cudaLaunchHostFunc+
  pread/ packed ro）、prefill_empty_cache.py（每 chunk empty_cache 钩）、idle_release.py、
  roce_gather.py、prefill_sp.py（装配面）}`；`~/migrate-assets/bin/r3-boot-arm.sh`（/engram
  ro 挂载+env 面）；`~/sglang-main-src/python/sglang/srt/model_loader/loader.py`（mmap 装载面）。
- 系统（时点注记 02:08Z）：本机 /proc/{vmstat,meminfo,buddyinfo}、/dev/shm、journalctl
  00:10-01:05Z（fabric-guard 常态噪声=F-G6b-1 每 5min 全窗在含健康段=非相关面）。

*REDBAND-ROOTCAUSE 案头根因代理（零集群零 boot；判读权归主会话/用户）。*

## 附：用户裁定（2026-10-13，主会话落档）

根治窗（P2.1 四秩同窗 census trace+P2.2 boot 末轨道检测-NCCL communicator
重建自愈钩子）排期=**纳入 0.3.2 开发计划**（0.3.1 定型不阻塞；规避律④行为
缓解+target_verify 哨兵 V1 登记线在役）。0.3.2 计划队列梳理已派专项代理。
