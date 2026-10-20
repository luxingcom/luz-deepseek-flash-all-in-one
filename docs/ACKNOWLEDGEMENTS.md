# ACKNOWLEDGEMENTS — 致谢名单

> 源档：战役仓 `docs/release/ACKNOWLEDGEMENTS-DRAFT-20261013.md`（commit ac4212f，110 条五组；2026-10-15 B-4 增补同步=战役仓 commit 45baf29〔110→111 条〕；本档为交付面并入版，条目逐字承接）。

> **头部注记**：本名单按用户指令（2026-10-13）收录战役全程参考到的**所有**借鉴思路——
> 「无论好坏，无论是否用到」——包括采纳在役、判负留库、参照对比、政策依据、反向不吸收
> 与坏参照判负记录。所有出处均带仓内档案锚（档:节 / commit / 本地路径）可追溯；仓内查
> 不到出处的条目按纪律标【出处待核】，不臆造。
>
> 状态四类口径：**采纳在役**（进入 0.3.1/0.3.2 定型形、产线或工具包）/ **判负留库**（负结论入档，
> 禁重开或条件重开）/ **参照对比**（作为对照系/校准/互证使用，未直接移植）/ **政策依据**
> （作为规则、纪律或设计规范的法源）。
>
> 本草稿位于战役仓 docs/release/，由后继并入交付仓 docs/ACKNOWLEDGEMENTS.md。

---

## A. 上游开源项目（SGLang 及 PR 谱系）

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚（仓内档:节） |
|---|---|---|---|---|
| A1 | **sgl-project/sglang main-79cafec0**（本地只读参照树 `~/sglang-main-src`） | 引擎基座谱系锚：一切源码级核证（挂点/行号）与镜像基线 | 参照对比（基座） | docs/102-OPTIMIZATION-EXECUTION-TASKBOOK-20260930.md:112；docs/release/ARCHIVE-PLAN-20261012.md §五.6 |
| A2 | sglang **PR #40352**（候选块稀疏打分/int32 候选表协议，已随 main-79cafec0 在树） | 候选块两段打分语义级回移的现成载体；mm prefill 打分行×列双维有界化设计 | 采纳在役（语义面已消费完毕） | docs/taskcards/40352-ARMING-WINCARD-20261006.md；docs/audits/RECALL-SPARSE-REGRESSION-VERIFICATION-20261002.md:114 |
| A3 | sglang **PR #40217**（int32 块号表尾重键） | 候选发布 int32 块表（8KiB/行 vs 585.9KiB 掩码 73×）形态原生参照，G3 接线消费 | 采纳在役（已原生化） | docs/taskcards/G3-SPARSE-WIRE-DEV-20260930.md:60；docs/audits/MIA-PREFILL21-DEEPDIVE-20261002.md:123 |
| A4 | sglang **PR #39674**（int32 块号表，TP4 小批 16 头注意力面） | 核查结论=不在 main，sm12x sparse 打分器缺口须自建的对照证据 | 参照对比（缺口判定） | docs/audits/REFDIFF-BUGHUNT-20261003.md:167；docs/audits/RECALL-SPARSE-REGRESSION-VERIFICATION-20261002.md:114 |
| A5 | sglang **PR #38409**（PDL 竞态修复） | 勘误复核：PDL 竞态非 main_norm_rope；非我方钩挂面（不涉 prefill_sp/engram/b12x） | 参照对比（挂起勘误） | docs/audits/ASSET-RECON-OLD-TO-NEW-20261001.md #127；docs/audits/REFDIFF-BUGHUNT-20261003.md:167 |
| A6 | sglang **PR #39679**（Rust server datapath 统一） | 流出链 Rust 化考据：双键在树抄键验证而非重写；GD-STUDY 终裁 B1/B2 阻塞（双安全钩 fail-open+丢字段 20/40）禁臂 | 判负留库（条件禁臂） | docs/taskcards/CPP-REWRITE-REGISTRY-20261001.md A-R4；docs/verdicts/GLUE-AUDIT-ADJUDICATION-20261004.md §三 |
| A7 | sglang **PR #39627**（Rust TreeCore 默认，+8078/−1033） | 与我方 #39679 同线：上游已转默认、差距扩大的登记件（重基随行） | 参照对比（差距登记） | docs/research/COMMUNITY-DELTA-20261006.md §一.F |
| A8 | sglang **PR #39666**（Engram 模块上游化，merged 2026-09-17） | Engram 行缓存/哈希分布类修复的上游盯梢渠道位（MiaAI→knapcio→sglang 同源血统证据） | 参照对比（渠道） | docs/research/ENGRAM-UPSTREAM-BORROWING-20261009.md §3-S8 |
| A9 | sglang **PR #39187**（有界稠密 prefill 索引，closed 未合） | 563k 头崩（E 缺陷）根修上游件：2GiB logits 预算行分块语义（600k 18s/9.6GB 数据）；经 knapcio indexer_chunked_v3 语义回移 | 采纳在役（经社区回移形） | ENGRAM-UPSTREAM-BORROWING §3-S1；docs/research/INDEXER-ROWCHUNK-PORTPLAN-20261009.md |
| A10 | sglang **issue #36941**（GB10 长 prefill 静默杀 rank） | 同平台同签名实锤+速效诊断件（无条件 512 行分块 PASS）+unique-prompt/每请求 flush 测量纪律 | 采纳在役（诊断件+量具纪律） | ENGRAM-UPSTREAM-BORROWING §3-S2 |
| A11 | sglang **issue #28706**（MHC TF32 n_splits 运行时 JIT 停顿） | 5.00s/chunk 恒定节律（C 签名）的唯一上游机理候选（H-c1 待验假设，非定论） | 参照对比（假设源） | ENGRAM-UPSTREAM-BORROWING §3-S3 |
| A12 | sglang **issue #41076**（SparsePrefillWorkspace 无界 OOM） | 深队列 600k 面的 OOM 预防审计输入（admission pending 上限语义） | 参照对比（风险登记） | ENGRAM-UPSTREAM-BORROWING §3-S4；COMMUNITY-DELTA-20261006 §一.B |
| A13 | sglang **PR #34565 + issue #36131**（SWA 分支点缓存） | 跨 flush 不可逆（B 签名）的机制邻族参照（tombstone 语义） | 参照对比（邻族） | ENGRAM-UPSTREAM-BORROWING §3-S5 |
| A14 | sglang **PR #39914**（SM120 candidate torch 回退+KV 页对齐） | SM12x 解锁 dsv4.1 head 的候选通道（盯梢位） | 参照对比（盯梢） | ENGRAM-UPSTREAM-BORROWING §3-S7 |
| A15 | sglang **issue #39651**（bench 不控不记 radix 状态） | 量具纪律对齐（同族工具层放大版） | 政策依据（量具纪律） | ENGRAM-UPSTREAM-BORROWING §3-S9 |
| A16 | sglang **PR #37253**（Flash Vision 模型支持，d5a3b77） | V4.0exp 视觉线 V9：28 文件 hunk 重嫁接（G6 regraft）移植 | 采纳在役（V9 已闭） | docs/research/VL-PERFOPT-CARRYOVER-20261008.md:38/:169 |
| A17 | sglang **issue #42364/#42367**（SM12x DSV4.1 init/decode 捕获死） | 上游 main 对我方精确拓扑不可用=overlay 护城河判定的警报证据 | 参照对比（警报+护城河） | COMMUNITY-DELTA-20261006 §一.B |
| A18 | sglang **PR #41659**（prefill indexer 重做，P0 榜首） | 与 #40352 回移件同文件族的重基冲突二择仲裁对象（未吸收，登记） | 参照对比（二择仲裁） | COMMUNITY-DELTA-20261006 §一.A；docs/taskcards/40352-ARMING-WINCARD-20261006.md 头注 |
| A19 | sglang **issue #40441**（decode 图宽钉死 --context-length，SM90 2.68×） | 我树同钉实证（deepseek_v4_backend.py:1199/:2402）；600k 部署 decode 杠杆候选 | 参照对比（P0 候选） | COMMUNITY-DELTA-20261006 §一.A |
| A20 | sglang 榜面其余参照（#41987 CPU seq_lens 同步撤除/#32779 SM120 Triton sparse-MLA/#41251 Hopper 路径/#42146 row-chunk planner/#33454 DSpark RoPE 越界/#42004 Cake softmax 等） | COMMUNITY-DELTA-20261006 Top-10 移植候选与观察件台账（判定含判负 N-A：trtllm 后端 SM100-only、SM103-only 件） | 参照对比/判负留库（逐件在档） | COMMUNITY-DELTA-20261006 §一.A/§二 |
| A21 | sglang **官方 DeepSeek-V4 cookbook**（镜像 lmsysorg/sglang:dev-v4f-2dgx-v2，b12x-vision @452239a74f） | RDMA docker 四旗（缺=NCCL 静默 TCP 回落 −40%）/SGLANG_B12X_MAX_TOKENS=chunk 对齐断言/EAGLE 误绑防护/CG 梯常取 2× 并发/enforce-shared-experts-fusion（GB200 口径）/Vision 三档律与 span 对齐律 | 政策依据+采纳（断言/纪律件）；expandable_segments 与我方红键律冲突不采纳 | docs/research/COMMUNITY-DSV4-SURVEY-20261008.md §B.1/§C.1/§C.2 |
| A22 | **LMSYS DSpark 官方博客**（2026-07-06，PR#30261） | ragged verify 三态/图键总 token 数前打包/SPS 表——与我方 A18 系互证非净新 | 参照对比（互证） | COMMUNITY-DSV4-SURVEY §A6 |
| A23 | **FlashInfer 上游**（0.6.16 参照树 `~/w6-kit/fi016-src`；PR #4955/#3640 NVFP4 sparse MLA） | R1 设计 T0 精读项：上游原生 NVFP4 KV 面判读（升级+适配 vs fork）；「#5197」锚点经离线核为不可索引，以 #4955/#3640 为可锚替代（锚点勘误入档） | 参照对比（R1 设计法源） | docs/research/R1-FP4KV-DESIGN-20261011.md §3.2/A' 与锚点勘误节 |
| A24 | sglang **PR #56228**（引擎合入但未接线） | 记忆线索：仓内未检得对应档案锚 | 【出处待核】 | —（任务指令记忆线索；campaign 仓 grep 无命中） |
| A25 | sglang **PR #4603**（MoE wrapper 缓冲共享） | 记忆线索：仓内未检得对应档案锚 | 【出处待核】 | —（任务指令记忆线索；campaign 仓 grep 无命中） |
| A26 | **vLLM 0.4.5 LuZ 私有镜像线**（registry 192.168.5.187:5000 vllm/vllm-openai tags；eugr/spark-vllm-b12x） | 对账结论=无新 0.4.x 社区版本（luz045-v41-graft 系我方自产 graft 件） | 参照对比（对账完成） | COMMUNITY-DELTA-20261006 §一.方法⑤/§G；docs/research/VLLM045-ARCHAEOLOGY-20261008.md |

## B. 社区同行（knapcio / MiaAI-Lab / 其他船队）

### B-1 knapcio（knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4，MiaAI-Lab 下游 profile fork；审计克隆 `~/knapcio-v41-audit-20260925` HEAD 58f2321，对账至 origin/main 27616be=v2.4）

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| B1 | `runtime/b12x_next/_shared/mla/prefill_mg.py:869-941`（s1_qk_nope_nvfp4_bf16_mg2 NVFP4 内核内直读先例） | R1 FP4KV 结构路线（R1）的参照系：288B fp4 行直读+寄存器内 E2M1×E4M3 反量化 | 采纳在役（R1 转正，PR 成对 +18.5~22.3%，超出参照形） | docs/research/COMMUNITY-GAP-VERDICT-20261010.md §2.1；COMMUNITY-DELTA-20261012 §2.3 |
| B2 | knapcio 全仓「无 repack 面=原生 fp8 KV 零支付」格局（flash_mla_sm120.py:19-38，584B/token） | R1 问题定谳对照：我方 repack 桥（kv_fp4.py:322-412）为独有代价面的证据 | 参照对比（定谳） | COMMUNITY-GAP-VERDICT §2.1 |
| B3 | `runtime/b12x_next/_shared/mla/decode_math.py:1447-1531` + `_lib/intrinsics.py`（CuTe DSL 反量化原语库） | R1 反量化指令序列法源（移植整 DSL 核被否决——基建面≫fork 面，留作对照） | 参照对比（法源） | R1-FP4KV-DESIGN §3.2-B |
| B4 | `adapter/prefill_sp.py:837-863`（_fp8_input stage2 MXFP8 AG-in 参考实现） | W5 stage2 直投 tuple 模式的照抄对象（E4M3+ue8m0 swizzled scale，17/21 层，~1/1.94 wire） | 采纳在役（W5 两键转正，PR 四档 +1.68~+2.18%） | COMMUNITY-GAP-VERDICT §2.3；docs/research/W5-STAGE2-RESULT-20261012.md |
| B5 | `adapter/prefill_sp.py:800-802`（生产端直调 flashinfer_mxfp8_quantize） | 弃用我方复刻件的依据（复刻件深次正规/饱和边界与参考有字节分歧） | 采纳在役（W5 实现面） | COMMUNITY-GAP-VERDICT §2.3 |
| B6 | `adapter/prefill_sp.py:784-797`（fp8_eligible_attn 层门 17/21） | W5 层门等价排除（kv/index source 层 2/8/14/20） | 采纳在役（W5 层门） | COMMUNITY-GAP-VERDICT §2.3 |
| B7 | `adapter/prefill_sp.py:429-459`（_tail_real_rows 出口尾行直聚+退化门 :387-389） | 出口尾行直聚（~15× 流量减，5.5-6ms/chunk）移植参照 | 采纳在役（DSV41_PREFILL_SP_TAIL_GATHER 转正） | COMMUNITY-GAP-VERDICT §2.4；031 终报 §一-B |
| B8 | `adapter/spark_prefill_split.py`（TPsplit，int32 top-k AG 无浮点集合） | TPsplit 重开参照（社区生产 3499→4364；我方 T50 塌陷→修复设计三步→组合窗 split 差分 +2.41% 出带正） | 判负留库→留库复活位（件 6498aa39 在库，用户裁定留库不转正） | COMMUNITY-GAP-VERDICT §2.2；docs/research/COMBO-STACK-RESULT-20261012.md；031 终报 §九⑤ |
| B9 | knapcio `docs/history.md:182`（2GiB logits 预算留每 rank 分区内） | TPsplit 对齐修复的社区式参照（tile 形状/平局决胜） | 参照对比（对齐设计） | COMMUNITY-GAP-VERDICT §2.2 |
| B10 | v2.4 **CHUNKED_PREFILL_SIZE 4096→8192**（+MEM_FRACTION 0.78） | 组合窗验证件第一顺位（社区 A/B 链 chunk 单因子 +10~12%@388K） | 判负留库（T1 组合窗红：四档出带，社区 A/B 链非同具形不可平移；0.3.2 观察位） | COMMUNITY-DELTA-20261012 §三.b/§5.2；COMBO-STACK-RESULT；031 终报 §一-B |
| B11 | v2.4 **chunk 16384 死刑**（他网 1M 档 worker 2.5GiB 挂死直证） | 永禁红线（16384 永禁维持） | 政策依据（红线） | COMMUNITY-DELTA-20261012 §2.2/§5.2；031 终报 §九④ |
| B12 | v2.4 **DSV41_PREFILL_BYPASS=256 小请求准入**（adapter/prefill_bypass.py，hushengkai Mia#44/#9 诊断自研实现） | 多用户 QoS 面观察位；若立项照抄其 sha256 source-pin 指纹门+计算帽/池保留面边界律 | 观察位（不吸收在档） | COMMUNITY-DELTA-20261012 §三.c/§5.3 |
| B13 | v2.4 **--swa-prefix-tails 128**（388K 会话重访 1.5s/100% cached） | E3-A 同路独立佐证：我方 N=256 剂量领先一档且先行一日 | 采纳在役（E3-A N=256 六参产线形；社区数据=机制价值独立佐证） | COMMUNITY-DELTA-20261012 §三.a；docs/research/E3A-DOSE-RECALL-RESULT-20261011.md §六 |
| B14 | `docs/switchless-ring.md:503-527` **环网恢复田野笔记**（GID 3→4 漂移/carrier 假活跃/TX 塌 14Gb/s/NFS 软挂载四症状；来源 Mia#40/#41） | runbook 案头登记件：四症状+恢复命令入运维索引（fabric-net 包 COMMUNITY-FIELDNOTES 摘译在役） | 采纳在役（runbook 索引+工具包） | COMMUNITY-DELTA-20261012 §2.4/§5.1.2；docs/TOOL-ANCHORS.md 五包表 |
| B15 | `boot.py required_sglang_args()` MXFP8 backend 保全（v2.4 e9c9644） | 案头卫生件：核对我方 spec 铜无 --fp8-gemm-backend 覆盖路径 | 采纳在役（一行核对闭格） | COMMUNITY-DELTA-20261012 §三.b/§5.1.1 |
| B16 | `adapter/prefill_empty_cache.py`（98b8c99）+ `docs/chunked-prefill-memory.md`（T×L≲2.0e8 token² 硬规则） | E 缺陷（563k 头崩）机理吻合度最高的工程件：长 prefill 按 chunk 归还宿主内存钩子 | 采纳在役（EMPTY_CACHE 税面终判挂 B3/F-2 臂，机理在档） | ENGRAM-UPSTREAM-BORROWING K1/K2；docs/research/BOOT-LOWSPEED-ROOTCAUSE-20261010.md §0 |
| B17 | `docs/chunked-prefill-memory.md` §2.1-2.4（自适应 chunk sizer+分数预算下调+key 轴分块 topk+DSA prefill CP） | E 的调度面根修设计谱（四层定价） | 参照对比（设计谱） | ENGRAM-UPSTREAM-BORROWING K2 |
| B18 | `adapter/engram_backend.py`+`row_store.cpp`+`.env.tp4.example` serving 块（CACHE_GIB 4/WAYS 16/pack 谱系） | Engram 行缓存容量/局部性杠杆族（D 签名：cyclic victim+id%sets 无哈希混合 thrash 机理） | 采纳在役（我方 0.5GiB/16-way 形+扩容条件判负 B6） | ENGRAM-UPSTREAM-BORROWING K3；docs/research/KNAPCIO-DEEPOPT-BACKLOG-20261007.md §一.B6 |
| B19 | `adapter/engram_prefetch.py`（abfb15e） | Engram NVMe miss 侧流预取（步 51.7→49.5ms 形） | 采纳在役（我方 F6 勘误：r3-boot-arm.sh 常注 −2.2ms 已在基座） | ENGRAM-UPSTREAM-BORROWING K4；KNAPCIO-DEEPOPT-BACKLOG §二 |
| B20 | `docs/upstream-watch.md` 新鲜靴基线表+tonyd2wild 外部船队劣化实录（15h −30% cause open/时钟锁低） | 「靴级出生慢模式」（Fam-A/R-0 族）的外部同族参照+检测协议（五档 unique-prefix 探针+新鲜靴基线） | 参照对比+采纳（检测协议面） | ENGRAM-UPSTREAM-BORROWING K5；BOOT-LOWSPEED-ROOTCAUSE §2.1 X-1 行 |
| B21 | `scripts/prefix_scan.py`+`ds_gate.py`+cert_head（5f11a97 v2.3 质量门三件） | 质量门参照：前缀缓存冷/暖/部分命中三态+KL 门+degenerate 检测（源头 GLM-5.3-Flash issue #2） | 采纳在役（cert 线/banner 契约 30 门参照） | ENGRAM-UPSTREAM-BORROWING K6；docs/taskcards/KNAPCIO-NEWCOMMITS-20261001.md |
| B22 | `adapter/replay_guard.py`（5f11a97） | 请求类崩溃 containment 范式（校验层拦截绝不让 forward 抛）——我方 A1 已移植 | 采纳在役（A1 移植+bounded-replay flag 武装激活） | ENGRAM-UPSTREAM-BORROWING K7；KNAPCIO-DEEPOPT-BACKLOG §二 |
| B23 | knapcio 转引 **Mia #23** buddy-allocator 碎片楔死（compact_memory 定时器 workaround） | E 的运维面缓解（order-8+ 耗尽签名→/proc/buddyinfo 先验）；与 sglang #36941 marknx min_free_kbytes 建议正面冲突的处置原则 | 参照对比（分场景试验+公开冲突） | ENGRAM-UPSTREAM-BORROWING K8 |
| B24 | `adapter/autotune_keep.py` 谱系（5c89dd0→b07c714→aeeacad，SGLANG_RUN_ID 排除出指纹；上游 #40320/#40420） | autotune 缓存 launch 指纹纪律（autotune-golden 谱系对接） | 采纳在役（autotune-golden 补丁四机应用） | ENGRAM-UPSTREAM-BORROWING K9；TOOL-ANCHORS r3-boot-arm 行 |
| B25 | knapcio **2200MHz 时钟帽方法学**（nvidia-smi -lgc 0,2200 定时重打；decode 不敏感 89.7 vs 89.8/prefill −3.2~−5.9%） | 跨栈对数必对时钟态——我方「时钟态锁录律」的政策依据（knapcio 深研 d15c1e6 呈裁项） | 政策依据（TOOL-ANCHORS 规则 6） | docs/taskcards/KNAPCIO-NEWCOMMITS-20261001.md §B2；TOOL-ANCHORS 派单纪律 6；docs/research/KNAPCIO-PR-DEEP-20261008.md §一 |
| B26 | knapcio **R1 36 键适配器族**（verify_cap+router_live/wo_a W8×3/draft_head_fp8+tp4/shared_pad_k/draft_main_proj_split/replicated_split/spec_sync_free/eager_glue/hc_fused/prefill_sp deepcarry 等） | 适配器层全家桶吸收映射（我方现役板对账表） | 采纳在役 | KNAPCIO-DEEPOPT-BACKLOG §二；docs/research/V41-COMPUTE-PATH-FORENSICS-20261006.md §3.2 |
| B27 | knapcio/mia **环网件 K1-K16 对照表**（mesh hairpin 对角硬转/hairpin_queue_size 8192/IDLE_SPINS 2e7/NCCL ring-only 等价实现/GID idx3+第二平面编址/NIC 资质档/marker 端口纪律/CPU pinning 负判/--sleep-on-idle） | 环网通讯面三参考对照清单（已吸收/判负/冻结/无意义四桶终判；真开放候选=空） | 采纳在役+判负留库（逐件在表） | docs/audits/RING-FACE-3REF-COMPARISON-20261002.md §一 |
| B28 | knapcio 通信面负结论七件（换传输三形态全负/RoCEnante AR 全量路由判负/2HOP 三代全负/TWO_WAVE/NCCL 通道调优无益/CPU 亲和无益/大 prefill gather 不适用） | 我方负墙 14 项判负登记的社区双背书（两岸独立同向） | 判负留库（双背书） | KNAPCIO-DEEPOPT-BACKLOG §一.A；RING-FACE K4/K5/K7/K15/K16 |
| B29 | knapcio 计算面负结论（尾 20 层跳过架构性不成立/fused hc prefill 更慢/MoE 重构无收益/HC 权重 L2 预取 −1.8%/block_verify+draft_tau/γ=2） | 计算面负结论墙（禁重开台账） | 判负留库 | KNAPCIO-DEEPOPT-BACKLOG §一.B；docs/research/KNAPCIO-TAIL20-DEEPDIVE-20261002.md |
| B30 | knapcio **PR #11**（xueyinmei-dot R5 独立有线环全档实测，sparkDash 1.8.8，chunk8192+帽 262144） | 独立车队复测佐证：我方 48 键 128k 名义反超点（5656.1 vs 5462.13=+3.6%）+C29 铁律 decode 侧佐证+跨舰协议差表 12 项纪律 | 参照对比（独立复测） | COMMUNITY-DELTA-20261012 §四/§六；docs/research/KNAPCIO-ROUND2-20261008.md §A.3 |
| B31 | knapcio v2.3 **real-text 修正数**（3915-4946）与 sparkDash filler 膨胀自认 | 量具口径纪律（跨栈对数必换步时或真文本口径） | 政策依据（三尺律） | docs/research/GAUGE-COMPARABILITY-20261006.md §1.2；KNAPCIO-DEEPOPT-BACKLOG §一.C |
| B32 | knapcio v2.4 **量测实践放宽**（prefill 单跑/decode 两扫取优+撤同靴 A/B 对比表） | 反向不吸收：我方同窗成对 arb_med 纪律更严；社区宣称数字降权使用的红线 | 判负留库（反向） | COMMUNITY-DELTA-20261012 §三.d.2/§5.4 |
| B33 | knapcio v2.4 协议两件（image placeholder 清洗 dec9ac2=移植 Mia PR#15/thinking 无 budget=移植 Mia PR#47）与装机链族（doctor/download/SKIP_PULL/SSH/NFS） | 判定=不吸收（服务健壮性面/部署面，非我方战役轴；注记在档） | 判负留库（不吸收注记） | COMMUNITY-DELTA-20261012 §三.c/§5.4 |
| B34 | knapcio v2.4 KV 池代价账（5.77M→3.67M）+EP4 路死注记+DRM 资源磨损披露 | 多用户旋钮容量代价明码（分层记账依据）+EP 扩展路堵死负信息 | 参照对比（代价账） | COMMUNITY-DELTA-20261012 §三.d.3-5 |

### B-2 MiaAI-Lab（DeepSeek-v4.1-Flash-DGX-Sparks 主仓，社区环网线；提交止 cad252b7，issues 活跃；全树 /tmp/mia-fresh）与 sparkring 谱系

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| B35 | **MiaAI-Lab issue #21**（koldfrontier，sparkDash filler→Engram 行缓存膨胀 prefill 虚高 16-42% 报告+对照实验） | F 签名（基准虚增）定谳来源；「一切 prefill 数字附 cache 档位+hit_rate+filler 熵三件套」纪律 | 政策依据（量具纪律；sd_bench_real_text 已消费） | ENGRAM-UPSTREAM-BORROWING §2-M1；GAUGE-COMPARABILITY 〇① |
| B36 | **ZackO2o（Mia #21 评论/第三船队）**：cache 4→0 反向账（KV 池 +9%/MemAvailable +1.55GiB/真文本 decode ~0%）+「按启动日志 max_total_num_tokens 公布 KV 池」立规 | UMA 上行缓存与 headroom 直接竞争的第三方证（host-table 判负+容量档实验口径）；环研报 §6.3 反架构参照（三运维课：carrier 采样/GID 漂移重探/健康判据 artifacts 化） | 参照对比+采纳（等价 F07/F05/fabricctl） | ENGRAM-UPSTREAM-BORROWING M1 评论；RING-FACE K14；docs/audits/REVIVAL-AUDIT-20261002.md J18/E9 |
| B37 | **ZackO2o 1M 五件套**（993k needle PASS） | C6 复活候选（前提推翻类：抬池 +89MB/rank 即可+准入参数化+内存纪律成立） | 参照对比（复活候选登记） | docs/audits/REVIVAL-AUDIT-20261002.md C6/B-8；docs/audits/ASSET-RECON-OLD-TO-NEW-20261001.md #105 |
| B38 | **MiaAI-Lab issue #23**（mrpmorris，宿主 buddy-allocator 碎片活锁 NV_ERR_NO_MEMORY） | 见 B23（knapcio 已在我族栈复现同签名，故归 knapcio 侧收录；Mia 为原始报告源） | 参照对比（同 B23） | ENGRAM-UPSTREAM-BORROWING K8/M2 |
| B39 | **MiaAI-Lab issues #43/#44/#35/#27**（长前缀驱逐异常+短请求 HOL 阻塞 ~67s+跨会话驱逐） | 600k/高并发轴核心证据包：T17/O13B/K5 admission 判据输入+C4(TWO_WAVE) 重开条件登记 | 参照对比（判据输入） | COMMUNITY-DELTA-20261006 §一.C；KNAPCIO-DEEPOPT-BACKLOG §一.A4 重开条件 |
| B40 | **MiaAI-Lab issue #40**（RoCEnante 装后 mlx5 TX 降速 ~14Gb/s 仅重启可清） | P1 警报（我 RoCEnante 在役面的 fabric 健康监控覆盖核查输入） | 参照对比（警报） | COMMUNITY-DELTA-20261006 §一.G |
| B41 | **MiaAI-Lab issue #39**（TP8 vs 2×TP4 实测）+issue #41（decode 扫自有 harness） | 拓扑参照（TP8 单用户 decode +28-49%/2×TP4 并发胜）+校准点更新（口径各异不可横比） | 参照对比（备查+校准） | COMMUNITY-DELTA-20261006 §一.G/§三 |
| B42 | **MiaAI-Lab #44/#9（hushengkai）+#43（LECYWZA）+#31** | 社区自引外部诊断源：短请求饥饿+chunk8192/前缀逐出/backend 覆盖（经 knapcio v2.4 自研实现收录） | 参照对比（诊断源） | COMMUNITY-DELTA-20261012 §六 |
| B43 | **MiaAI-Lab b12x_next 环网线**（#36 TP4 产线合入；EP1/EP2 使能链=DSV41_FAST_LOAD_EP_SIZE 等） | DE 杠杆对照：EP1 证据链 09-24/25 固化、EP2 仅回滚位（FlashInfer MXFP4 MoE 需 per-rank 宽度 128 倍数）——零增量结论 | 参照对比（零增量） | docs/taskcards/KNAPCIO-NEWCOMMITS-20261001.md §B EP1/EP2 |
| B44 | **MiaAI-Lab `l2_prefetch.py`**（DSV41_L2_PREFETCH，图捕获期学习 collective→权重预取） | 异世系参照（我方自研 l2pf 在役另一缝；ZackO2o 警告 NCCL 路径下静默零效=预检纪律）；ring 靴惰性注记（switchless-ring.md:551-558） | 参照对比（异世系+惰性注记） | docs/audits/MIA-COMPUTE-PATH-DIFF-20261002.md:68；COMMUNITY-DELTA-20261012 §2.4 末 |
| B45 | **MiaAI-Lab `switchless-ring.md` 全文**（fabric 参数段/补丁 NCCL Route A/B/K6 环专用 NCCL 2.30.7/K9 第二平面编址 netplan 模板/K11 plan.py cap 防呆） | 环网技术清单正身（RING-FACE 对照的一参考；我方等价实现不逐参数照抄） | 参照对比（参数谱） | RING-FACE-3REF-COMPARISON §一 K6/K9/K11 |
| B46 | **MiaAI-Lab 上游基线表**（sparkDash 3350/3782/3768/3531/3251）与合成/真文本比 1.18:1 | 社区量具对照基线（口径链表输入） | 参照对比（基线） | GAUGE-COMPARABILITY §1.2 |
| B47 | **sparkring**（FujitsuPolycom 环网部署框架；f16b5f4→6d27dd10 432 commits） | TWO_WAVE proxy 源+fabric 路由恢复 PR#345+线缆带宽测量 PR#346（`sparkring cabling --bandwidth`）+发行缺省 IDLE_SPINS 200K 教训（我方血统本就带 2e7 对值） | 参照对比（运维工具面+教训） | COMMUNITY-DELTA-20261006 §一.G；KNAPCIO-ROUND2 §A.4① |
| B48 | **ntxf31415 分叉线**（本地 fetch 三线对账之一） | 分叉增量对账对象（结论=无净新增） | 参照对比（对账） | COMMUNITY-DELTA-20261006 §一.方法④ |

### B-3 其他社区船队与博客

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| B49 | **tonyd2wild/DeepSeek-V4-Flash-Vision-SGLang-DGX-Spark**（2×Spark TP2 实测仓） | VL+DSPARK+CG 同役同硬件实证（k6 非互斥第三/四证）+OOM killer 处方序（swapfile+serial 载入+drop-cache）+15h 服役 −30% 实录（另见 K5） | 参照对比（互证+运维件） | COMMUNITY-DSV4-SURVEY §A2/§B.1/§C.2-6/7；ENGRAM-UPSTREAM-BORROWING K5 |
| B50 | **dnhkng 2×GH200 Part-4**（独立深测博客）+上游 **PR#33276/#33312**（loader 修复链） | draft 共享专家映射完整性=accept 第一杀手（修前 1.3-1.8→修后 3.5-5.05，story +52%）——accept 冷读数 boot 门的最高价值单件；k 扫描过冲回落曲线；唯一 nonce 前缀缓存纪律 | 采纳在役（E1 门链纪律件） | COMMUNITY-DSV4-SURVEY §A3/§B.2/§C.1-1/2/12 |
| B51 | **Lei-010 sglang issue #40877**（8×RTX PRO 6000 SM120 生产田野） | 量具校准面（tokens 取 usage/双跑 −1.3%/`/get_server_info` 配置门）+chunk 2048 窄互联参照+SM12x 缺口清单（prefill CG capture 崩=我方「条件位挂起」互证） | 采纳在役（G15 量具面）+参照对比 | COMMUNITY-DSV4-SURVEY §A4/§B.3；COMMUNITY-DELTA-20261006 §一.E |
| B52 | **Helix 博客**（SM120 三引擎横评） | CG-cliff 律：捕获梯覆盖必须绑定运行上限（缺档=eager 悬崖 78@32；修复=绑 mrr16）——我方 G-A 梯设计校准 | 采纳在役（G-A 臂卡补强） | COMMUNITY-DSV4-SURVEY §A5/§B.3 |
| B53 | **NVIDIA 论坛 GR7a 4 节点 0731 帖**（vLLM 系+Patch-4 dspark.py shared_experts 映射）+jasl/Eugr/Aiden 谱系 | Patch-4 与 dnhkng loader 案例跨引擎同构双证（draft 共享专家映射=accept 第一杀手）；2×TP2 vs 1×TP4 拓扑备查 | 参照对比（双证+备查） | COMMUNITY-DSV4-SURVEY §A11/§C.1-1/§C.2 明确不借 |
| B54 | **magicbear/DeepSeek-V4.1-Flash-SGLang-DGX-Spark**（实测配方仓） | 「阿里云 GB10 最终配置」正身（见 D 组 D1 条；8192=ctx 上限非 chunked-prefill 长域主张的辨析源） | 参照对比（取舍参考） | docs/research/COMMUNITY-SCHEME-DEEPDIVE-20261006.md ②；F5-O1 §1.4 |
| B55 | **RustyAiLab（Mia #16）`--sleep-on-idle`**（head CPU 47%→14%） | 微件注记（G5 判中性：机队本就干净不收） | 判负留库（不收件） | ENGRAM-UPSTREAM-BORROWING §2 附注；RING-FACE K16 |
| B56 | **Mia #20 DSpark k=3 争议**（两船队独立实测 −16~−26%） | k 阶梯预期校准注记（经 knapcio CHANGELOG 引注核实） | 参照对比（校准） | ENGRAM-UPSTREAM-BORROWING §2 附注 |
| B57 | **SemiAnalysis**（InferenceX MI355X 篇+DSV4-1.6T Day0-43 篇） | 方法论可借=「内核级逐层压榨+口径纪律」（异构全折减，SM121 无 TileLang 通道） | 参照对比（池行 D 级） | COMMUNITY-DSV4-SURVEY §A8/§A9/§D |
| B58 | **vramcalculator.io 4×Spark 配方站** | 判定=源为 MiaAI-Lab commit 25379c2 衍生（去重行，防重复吸收） | 判负留库（去重） | COMMUNITY-DSV4-SURVEY §A7 |
| B59 | **guqiong96 discussion#34752**（CPU-GPU 混合 0731） | 反架构排除依据（我方全 GPU UMA 不适用；仅证社区热度） | 判负留库（反架构） | COMMUNITY-DSV4-SURVEY §A12 |
| B60 | **Cesarus85/DwarfStar、HabanaAI fork、Fixstars B300 day-1** | 排除依据（非 sglang/异构/单卡容量线；Fixstars 仅佐证生态） | 判负留库（排除） | COMMUNITY-DSV4-SURVEY §A13 |

### B-4 waterliu1981（luxingcom/luz-deepseek-flash-all-in-one issue #1/#2/#3 报告者，2026-10-15）

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| B61 | **waterliu1981**（luxingcom/luz-deepseek-flash-all-in-one issue #1/#2/#3，2026-10-15） | #1 tool_call_parser 缺省未接线根因定位（serving.py 缺省 None+`_tool_call_parsing_active()` 门禁）+`deepseekv41` 连写正字法+非流式/流式/经网关三路径结构化成型实测；#2 enable_cache_report 缺省关定位（serving.py:189-192+serving_chat.py:796）+接线实测（cached_tokens 面板 97.9%）；#3 `/v1/models` 容量字段发现面缺陷定位（客户端四扁平字段 0/4 命中⇒落默认窗 262144⇒正常完成响应被判 CONTEXT_WINDOW_EXCEEDED+`max_tokens:1` 截断链）+反向陷阱红线（禁调大声明）+网关响应侧广播临时形实测（17/17 单测+引擎响应逐字节未改+零中断）+双计数口径（`pi-ai detected context overflow`/`error.code == CONTEXT_WINDOW_EXCEEDED` 各计一次） | 采纳在役（A8/A9 已落 W-C 窗；A10 待实施） | 0.3.2 032-ADDENDUM §十 A8/A9+§十一 A10；GitHub luxingcom/luz-deepseek-flash-all-in-one issue #1/#2/#3 |

## C. 官方资产（DeepSeek 论文/权重/NVIDIA 驱动件）

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| C1 | **DeepSeek-V4.1-Flash 技术报告**（本地 `/data/models/DeepSeek-V4.1-Flash/DeepSeek_V41_Tech_Report.pdf`，52 页〔T62-3 注记：pdfinfo 实测 51 页，差异留档不深究〕） | G3 sparse 接线的规范基准：CSA2 三模式分工/分层稀疏索引器/候选池 2048×8=16,384/Top-K 512/FP4 main KV 与 FP4 indexer Q/K/SWA 窗 128/缓存生命周期 L1-L7——与论文冲突处以论文为准，论文未载项显式标注 | 政策依据（规范基准） | docs/taskcards/PAPER-APPROX-SPEC-20260930.md（全文）；docs/audits/PAPER-UPSTREAM-TAIL20-SCHEMES-20261002.md；docs/research/T62-3-PAPER-GSM8K-NOTE-20261003.md |
| C2 | **DeepSeek-V4.1-Flash 官方检查点**（48 shards safetensors+config.json） | 部署参数论文对账锚（candidate_topk_blocks=2048/candidate_block_size=8 等）与生产模型本体 | 采纳在役（模型本体+config 锚） | PAPER-APPROX-SPEC §5；docs/taskcards/KV-LIFECYCLE-TEST-CARD-20261009.md 法源行 |
| C3 | **NVIDIA 专有驱动模块重装源**（`~/archive-20261001/superseded-workspaces/drv-prop-1031/` 与 `drv-kit-580-proprietary/`，运行内核 6.17.0-1031） | 唯一离线拷贝禁动件（SOLE LOCAL COPY，20261001 INDEX ⚠标记+20261012 交叉再标记）；来源=厂商分发 | 采纳在役（保留资产；不修改） | docs/release/ARCHIVE-PLAN-20261012.md §五.4；docs/taskcards/FINAL31-PLAN-20261012.md:79-80；docs/release/ARCHIVE-EXEC1-RESULT-20261013.md:65 |
| C4 | **GB10 PD 安全模式时钟**（记忆线索：楔定谳前社区驱动讨论） | 仓内未检得该讨论原始档案锚；最近关联=时钟态锁录律（knapcio 2200MHz 帽深研 d15c1e6 驱动呈裁） | 【出处待核】（关联锚=TOOL-ANCHORS 规则 6） | —（任务指令记忆线索；campaign 仓 grep 无命中） |
| C5 | **NVIDIA 开发者论坛**（forums.developer.nvidia.com：GR7a #378878/Aiden #372268/Eugr #376220/Vision #381911） | 论坛二手参照源（C 级证据；跨引擎互证与生态不对称发现） | 参照对比 | COMMUNITY-DSV4-SURVEY §D 引用等级表 |

## D. 外部配置与对照（阿里云/第三方船队/坏参照判负）

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| D1 | **阿里云 GB10 最终配置**（magicbear 仓实测配方：8192-token ctx 上限+decode 图 bs 1-8+**prefill 图不开**+DSpark block 5） | prefill 图 600k 形「尺寸-水位权衡」的同族取舍参考；红线 A：其关图理由不迁移我方 600k 深域（外部关图禁引为反噬证据）；已做/已禁/新增三分类对照（我方 chunk 4096 在役、prefill-CG=真缺口走 T4/O1 自研线） | 参照对比（取舍参考非判据） | docs/taskcards/F5-O1-PREFILLCG-WINCARD-20261006.md §1.4；COMMUNITY-SCHEME-DEEPDIVE §② |
| D2 | **第三方 A 站**（星型交换机 2 口+标准 NCCL 2.30.7 自动调优） | PR-v3 中位 1.548×/1.56-1.58 互证——fabric 主导结论的三角验证一角 | 参照对比（fabric 主导定谳） | RING-FACE-3REF-COMPARISON §4-2；~/RING-NETWORK-RESEARCH-REPORT-20261002.md §6.4（原档 V41-THIRDPARTY-CROSS-ANALYSIS-20260920，LuZ-0.3.0 世代） |
| D3 | **第三方 B 站**（环直连+站点自编译 ring-only+锁频） | ≈我方 ×1.08——「代码不缺、fabric 是主变量」的三角验证另一角（「MoE 修复解释 1.548×」三重反证否决） | 参照对比（同上） | 同上 |
| D4 | **外部交换机同镜像自测**（中位 1.548×、长档 ≥8192 中位 2.01×） | 换数据通路=唯一大边际剩余但属硬件决策域（Amdahl 张力如实披露：collective 27.7% 下 1.55× 只该兑 ~1.11-1.17×，余来自长档停顿带消除）；验收线 busbw ≥14.3GB/s 且对 mesh ≥1.5× | 参照对比（硬件决策备档） | RING-FACE §4-2/§七 |
| D5 | **2×TP2 vs 1×TP4 拓扑重构**（GR7a 2×TP2 C12+ 胜 8-30%/Helix 2×TP4 sticky-LB 653@64 近线性） | 登记为架构裁备查件（单役 TP4 环网为既定约束，非行动件） | 判负留库（备查件） | COMMUNITY-DSV4-SURVEY §C.2 明确不借 |
| D6 | **换传输三形态**（oneshot/twoshot/fi_fp8，A23 线） | A23E0 终谳全灭：oneshot 传输门 2.90×≫1.25×（3N 字节税）/twoshot 环上对消/fi_fp8 symm-mem rendezvous UNAVAILABLE | 判负留库（禁再立项） | docs/verdicts/A23E0-VERDICT-20261007.md §一.1；KNAPCIO-DEEPOPT-BACKLOG §一.A1 |
| D7 | **ROCE 降帽/全量路由**（社区环配方 cap 256K 的平移主张） | 死刑：在役 262144 已同社区环值（A22B-CAP256K 采纳在先）；RoCEnante AR 全量路由=A2d 三靴终谳判负（c1 −43%/accept 3.25→2.7 通道②签名） | 判负留库（死刑项）+采纳在役（decode 小消息 cap 例外） | COMMUNITY-GAP-VERDICT §A5 死刑项；KNAPCIO-DEEPOPT-BACKLOG §一.A2；RING-FACE M1 |
| D8 | **TWO_WAVE 两波调度**（knapcio/mia 两家 tested-and-not-adopted；我方 B11 复活配方记录错误纠出=应保持 =0） | 判负维持：只在有丢包时才有意义，配 256KB 帽后反多一次等待；重开条件=Mia#44/#35 证据包（G12 已内嵌） | 判负留库（两岸双关） | KNAPCIO-DEEPOPT-BACKLOG §一.A4；RING-FACE K5/§〇.2；docs/verdicts/A22C1REV-ADOPTED-20261002.md:39 |
| D9 | **ep1n 轮子**（记忆线索） | 仓内未检得「ep1n」对应判负档案锚（近邻档案：dense 轮子 sglang-kernel 0.4.7 判负〔键 472a7346 污染→nightly 原生取代〕；EP1/EP2 使能链零增量结论） | 【出处待核】 | —（任务指令记忆线索；近邻锚=docs/audits/ASSET-RECON-OLD-TO-NEW-20261001.md #77、KNAPCIO-NEWCOMMITS §B） |
| D10 | **CG 阶梯经济学**（F4 阶梯平坦性/L1F5 CG 阶梯格两靴两红/CG-β 停车） | 判负留库：阶梯平坦性钉位不成立（600k 派生 tile 维恒在）；CG 阶梯格 C4096-M8K 两红三件齐前不开臂；CG-β 停车（t4-patch 形 0847a7cd 留库，0.3.2 B4 统筹呈裁） | 判负留库（条件重开） | docs/verdicts/F4-VERDICT-20261006.md:13；docs/verdicts/L1F5-VERDICT-20261007.md §一/裁定 1；031 终报 §九②；docs/plan/032-PLAN-20261013.md B4 |

## E. 工具与田野情报（sparkDash/环网笔记/量具）

| # | 来源 | 借鉴内容（一句话） | 使用状态 | 出处锚 |
|---|---|---|---|---|
| E1 | **sparkDash 1.8.8**（社区量具，knapcio/MiaAI 共用其 UI 收集器） | 量具口径锚：prefill bench（256 新 token/temp 0/弃 2 次预热）与 decode bench 定义；我方②尺口径=sparkDash PR 列定义（filler/salt/TTFT 公式/串行/预热九项对齐 PASS） | 采纳在役（口径对齐） | GAUGE-COMPARABILITY 〇④/§1.2；KNAPCIO-PR-DEEP §1.2 |
| E2 | **sd_bench.py**（`~/dsv41-flash-dgxsparks/bench/`，我方 fork 主量具，sparkDash 口径） | ②尺主量具（prl6 三步法 arb_med 的底座工具）；realtext 臂存在（诚实口径对） | 采纳在役（主量具） | docs/TOOL-ANCHORS.md:28；GAUGE-COMPARABILITY §1.1/SPARKDASH-ALIGN |
| E3 | **W0 对桩 sparkdash-calibration.md**（`~/v41-opt/data/w0/`） | 仪器层带 ±10% 单提示带、「各自成系不作换算」的量具纪律 | 政策依据（仪器带纪律） | GAUGE-COMPARABILITY 〇④ |
| E4 | **社区量测实践（未吸收面）**：prefill「3 跑取 2/3 中位」退为单跑/decode「两扫取优」/sparkDash filler 行缓存膨胀 | 反向借鉴：坚持同窗成对 arb_med+fresh salt+膨胀因子披露（19.45/19.2 同钟收敛法） | 判负留库（反向不吸收=纪律来源） | COMMUNITY-DELTA-20261012 §三.d.2/§5.4；GAUGE-COMPARABILITY §1 |
| E5 | **knapcio 环网恢复田野笔记**（switchless-ring.md:503-527，来源 Mia#40/#41） | 四症状+恢复命令（GID 3→4 漂移 modprobe -r mlx5_ib/carrier 采样/TX 塌陷 modprobe -r mlx5_core/NFS 软挂载 timeout 探测） | 采纳在役（运维索引+fabric-net 包 COMMUNITY-FIELDNOTES 摘译） | COMMUNITY-DELTA-20261012 §2.4/§5.1.2；TOOL-ANCHORS 五包表 fabric-net 行 |
| E6 | **perftest/ib_write_bw 链路量具**（`sparkring cabling --bandwidth` 谱系；`~/w6-kit/s4_bench.sh`+perftest） | 线缆带宽测量与链路对桩量具（OPEN-28 窗实绩） | 采纳在役（链路量具） | COMMUNITY-DELTA-20261006 §一.G sparkring 行；TOOL-ANCHORS:30 |
| E7 | **mxfp8_oracle 量化回环对拍器与三重对拍纪律**（A23-β C-2；基座 mxfp8_dequantize 文档律 :1317-1337；社区 per-chunk bitwise 校验模式参照 knapcio indexer_chunked_v3） | checked-not-assumed 运行时位等对拍（首 chunk 三重 torch.equal，任一失配永久回退 bf16）；C-2 假红教训=比较器拿 bf16 原象比量化回环必 False（一行修 :3321，:1664 正确式） | 采纳在役（W5 fail-safe 对拍面） | COMMUNITY-GAP-VERDICT §2.3；docs/research/A23BETA-PREP-FOUR-20261010.md §3.3；ENGRAM-UPSTREAM-BORROWING S1③（bitwise 校验模式） |
| E8 | **LuZ-0.3.0 世代社区横向档**（doc66/doc87/doc89/doc91 等 archive 档系） | 逐条借鉴记录的历史底册（社区横评/适配器代码级 diff/社区全景深挖——本名单多处的上游证据源） | 参照对比（底册） | GAUGE-COMPARABILITY（doc66 引注勘误）；KNAPCIO-DEEPOPT-BACKLOG 输入档案行；COMMUNITY-DSV4-SURVEY 去重声明 |
| E9 | **环研报**（~/RING-NETWORK-RESEARCH-REPORT-20261002.md，542 行） | 环网通讯面 R1-R3 参照与第三方 A/B 站三角验证的母档 | 参照对比（母档） | RING-FACE-3REF-COMPARISON 头注输入行 |

---

## 统计与待核清单

**条目统计**：总计 **111** 条——A 上游开源项目 26 / B 社区同行 61（B-1 knapcio 34、B-2 MiaAI 与 sparkring 14、B-3 其他船队 12、B-4 waterliu1981 1）/ C 官方资产 5 / D 外部配置与对照 10 / E 工具与田野情报 9。

**使用状态分布**（按主状态归一计数，一条多状态以主状态计）：
- **采纳在役** ≈ 30 条（A2/A3/A9/A10/A16/A21/A23 部分；B1/B4/B5/B6/B7/B13/B14/B15/B16/B19/B21/B22/B24/B26/B27 部分；B35/B36 部分/B50/B51/B52；C2/C3；E1/E2/E5/E6/E7）
- **判负留库/死刑/不吸收** ≈ 24 条（A6/A20 部分；B8（留库）/B10/B12（观察）/B28/B29/B32/B33；B55/B58/B59/B60；D5/D6/D7/D8/D9/D10；E4）
- **参照对比/校准/互证** ≈ 24 条（A1/A4/A5/A7/A8/A11-A15/A17-A20/A22/A26；B2/B3/B9/B17/B20/B23/B30/B34/B37-B46/B48/B49/B53/B54/B56/B57；C5；D1-D4；E3/E8/E9）
- **政策依据** ≈ 7 条（A15/A21 部分；B25/B31/B35；C1；E3）
- **【出处待核】** 4 条（A24 #56228、A25 #4603、C4 GB10 PD 安全模式时钟、D9 ep1n 轮子）

**【出处待核】清单**（任务指令记忆线索，campaign 仓内 grep 无命中，不臆造）：
1. sglang PR #56228（引擎合入但未接线）——【出处待核】
2. sglang PR #4603（MoE wrapper 缓冲共享）——【出处待核】
3. GB10 PD 安全模式时钟楔定谳前的社区驱动讨论——【出处待核】（最近关联锚=TOOL-ANCHORS 时钟态锁录律）
4. 「ep1n 轮子判负」——【出处待核】（近邻档案=dense 轮子 sglang-kernel 0.4.7 判负、EP1/EP2 使能链零增量，均已在 D9 行注记）

---

*ACKNOWLEDGEMENTS 挖掘代理落档 · 2026-10-13 · 纯案头只读挖掘（零集群零 boot）；本草稿由后继并入交付仓 docs/ACKNOWLEDGEMENTS.md。*
