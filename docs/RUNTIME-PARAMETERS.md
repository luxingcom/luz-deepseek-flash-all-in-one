# RUNTIME-PARAMETERS — 运行参数词典（env 56 键 + serve 九参 + 禁键 + 换模型 + 回退链）· 2026-10-30

> **目标读者**：要改配置、要换模型、要排查参数问题的外部部署/运维工程师。
> **本篇定位**：运行参数的**一处正典**。0.3.1 与 0.3.2 两代键值一度分叉（环网形
> 与交换机形、51 键与 56 键并存），外部手册里出现过「拿旧代表判新站、把做对了的
> 配置改回去」的代际混淆事故。本篇终止这种混淆：**本表只描述 0.3.2 终态在役形**，
> 任何历史值一律标注〔0.3.1〕或〔窗级〕；两代同名键不同值的逐级对照，以
> [`deploy/reconstruct/0.3.2/env/ENV-CHAIN.md`](../deploy/reconstruct/0.3.2/env/ENV-CHAIN.md)
> 为准，本篇不另立对照表。
> **性质**：参数词典，不是操作规程；涉及停机、回退、判读窗的操作细节以引用的
> 仓内正档为准。**文中所有实测数字为战役内量具读数、量级示意，不是跨站基线锚，
> 不可照抄为验收线**（量具口径见 [`CALIBER-AND-MEASUREMENT.md`](CALIBER-AND-MEASUREMENT.md)）。
> 排障词条（现象→根因→判据→处置四段式）见同批
> [`PITFALLS-AND-FAQ.md`](PITFALLS-AND-FAQ.md)；模型输出质量面的已知现象见
> [`KNOWN-ISSUES.md`](KNOWN-ISSUES.md)。

## 卷首：占位符表

本篇**不出现任何真实内网 IP、主机名、registry 地址、家目录路径**。命令与示例中
的站点专属值一律用占位符（与 `PITFALLS-AND-FAQ.md` 卷首二同款）：

| 占位符 | 含义 |
|---|---|
| `<H1>`~`<H4>` | 四机地址，rank0~rank3，`<H1>` 为 head |
| `<USER>` / `<PORT>` / `<GW_PORT>` | 登录用户 / 引擎监听口 / 网关口（示例值 8899，按站点替换） |
| `<CTN>` / `<PREFIX>` | 引擎容器名 / 容器名前缀（产线与测试线前缀可能不同） |
| `<ENVFILE>` / `<BOOT>` | 站点形 env 文件路径 / 点火脚本（本仓对应 `tools/boot-with-slotlock.sh` 包裹的 boot 件） |
| `<IM_*>` | 镜像（`<IM_OLD>` 旧代 / `<IM_NEW>` 新代 / `<IM_A>`、`<IM_B>` 待比对） |
| `<IFACE>` / `<PRODUCT_DIR>` | 网卡口名 / 站点部署资产目录 |

---

# 0. 代际总则（先认代际，再对表）

**第一律：先认代际，再对表。** 本仓同时保留两代档案：0.3.1 环网形（4 口 CX-7
hairpin，51 键）与 0.3.2 交换机形（双 rail 2 口，56 键）。同一个键在两代里值可能
不同（见下表）；同一个值在两代里的**含义**也可能不同（见 §1.9 RoCE 聚合两键）。
动手对表之前，先确认手上这张表、这个 env 文件、这个 boot 件是哪一代哪个形态的。

**0.3.2 终态在役形（本表基准）**——五件套齐一才算一个形：

| 面 | 件 / 值 | 验收指纹 |
|---|---|---|
| env | [`deploy/env/CBX1A-CERTM-spec1.env`](../deploy/env/CBX1A-CERTM-spec1.env)（56 键） | md5 `0729e18d` |
| serve 参 | SPEC6 九参（§2） | 归一指纹 `9d64a5de`（预登记） |
| boot 链 | `deploy/bin/r3-boot-arm.sh` | 产线 `20f22bc6`；公开件 `9ac6e113`（快照头+掩码） |
| 镜像 | `<IM_NEW>`＝tag `0.3.2-r032c`（registry 地址按站点配置） | digest `sha256:47f6d91a…ffc4`；71 层 |
| adapter/overlay | 0.3.1 基底 + reconstruct 覆盖（87 运行时件） | 装配账 [`deploy/adapter/0.3.2-MANIFEST.md5`](../deploy/adapter/0.3.2-MANIFEST.md5) |

一个形 = **env 键面 + serve 参 + adapter/overlay 件面**三元组齐一
（[`deploy/SPEC6-SERVE-REF.md`](../deploy/SPEC6-SERVE-REF.md) 配对律）；serve 参
变体必须与键面变体同窗冻结判读，禁跨形拼装。

**两代同名键不同值对照**（完整演进链见 ENV-CHAIN；本表只列值有分叉的键）：

| 键 | 〔0.3.1〕51 键形 | 0.3.2 CBX1A（56 键） | 分叉点 |
|---|---|---|---|
| `SGLANG_ROCE_MAX_SIZE` | 262144 | **1179648** | 262144→〔FB54〕524288→〔E16B1〕1179648 |
| `DSV41_ROCE_GATHER` | 524288 | **1179648** | 〔E16B1〕翻倍 |
| `B12X_ROCE_HCA` | 4 口裸列 | **2 口部署对** | 〔FB54〕收口 |
| `DSV41_CERT_HEAD_M` | 6（单点） | **6,12,18,24,30,36,42,48**（八元） | CBX1A 唯一终态改值键 |
| `DSV41_CERT_HEAD_DEBUG` | 1 | **0** | 〔FB54〕 |
| `DSV41_CERT_HEAD_LOG_EVERY` | 200 | **0** | 〔FB54〕 |

另有**键面增删**分叉：0.3.2 新增 `LUZ_SWITCH_ROCE_FLAT`、`B12X_ROCE_TOPOLOGY`、
`B12X_ROCE_TRAFFIC_CLASS`、`SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION`、
`DSV41_SPLIT_COMPACT_GATHER`、`DSV41_REPLICATED_SPLIT_WINDOW` 六键；删除环网形
`B12X_ROCE_PEER_HCA_MAPS`（§1.11）。**环网形与交换机形 env 不可整文件互抄**
（[`docs/RING-0.3.2-COMPAT.md`](RING-0.3.2-COMPAT.md) §1）。

**第二律：env 键改了不等于生效了。** boot 用 `ARM_ENV_FILE` 指向哪个 env 文件，
就是哪一形；改 env 后**必须复靴**，热改无效（ENV-CHAIN §5）。env 件经 boot 逐行
进 `docker -e`（四秩一致、留痕）；注入块在 boot 固定面 `COMMON_ENV` **之后**追加，
同名键 **last-wins，env 件胜**——所以「删掉 env 里的某行」不等于「回到零」，而是
「回到 boot 固定面的缺省值」（实例见 §1.10 engram 键、§1.5 LL128 三键）。另防
两个静默坑：env 文件**末行缺换行会整行丢失**且不报错（PITFALLS P2-1）；改注释也
会改 md5，锚表要同步（[`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) §6）。

**第三律：判参数是否生效，看运行中的进程，不看静态串。** 直证法见 §2.5；
`/health` 200 与横幅正常都证明不了接线类参数真的生效。

---

# 1. env 56 键逐键词典

本节覆盖 CBX1A 56 键**全部**（`grep -c '^[A-Z0-9_]*='` = 56）。按功能族分九张表；
表列＝键名 / 现值 / 作用（一句话，说给新人听）/ 何时需要改 / 改错会怎样 / 代际注记。
三个重点键（RoCE 聚合两键、engram 缓存配额、环网映射表）另设专节展开（§1.9-§1.11）。

**通用读法**（适用于下文所有「开关型」键，不逐行重复）：

- 这 56 键绝大多数是**优化路径开关**：`1`/`0` 严格布尔，值域基本只有开/关两档。
  普通运维**永远不需要动它们**；只有对应优化面的回退窗/排障窗才会 unset（unset =
  构造性回退到上游缺省路径，引擎不会因此拒起，性能/行为回到旧实现）。
- 不进判读面就不动键面；一个判读窗内 env/serve/adapter 三元组不许中途切换
  （SPEC6 配对律）。改任何键＝形变＝复靴＋四查（§5.1）。
- 三个键「转正后仍是 1」，**不要按「转正=删键」误删**：`DSV41_CERT_HEAD`、
  `DSV41_FP4KV_R1_INKERNEL`、`DSV41_FL6_RECALL_FIX`（ENV-CHAIN §6）。

## 1.1 计算路径族（21 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `DSV41_HC_FUSED` | 1 | 打开注意力「单 K 融合」内核，把多头注意力的 K 处理合并成一次算 | 仅 hc_fused 面回退/对拍窗 unset | unset=融合路径关闭，回上游分步实现（性能回落） | 两代同值 |
| `DSV41_INDEXER_HOIST` | 1 | 接管稀疏索引器的三处挂点（模型/打分/元数据） | 索引器面对拍/排障 | unset=索引计算回上游路径 | 两代同值 |
| `DSV41_PREFILL_EMPTY_CACHE_TOKENS` | 8192 | 预填充阶段判定「缓存为空」的 token 阈值，低于它走空缓存路径 | 一般不改 | 调大调小=空缓存路径的触发边界移动，行为漂移 | 两代同值 |
| `DSV41_IDLE_RELEASE` | 1 | 引擎空闲窗口主动释放缓存，压长稳内存水位 | 内存面排障 | unset=空闲期不释放，长稳水位偏高 | 两代同值 |
| `DSV41_ENGRAM_CACHE_GIB` | 0.5 | engram 行缓存的容量配额（GiB）——**每层**一份，见 §1.10 专节 | 扩容/缩容窗 | 见专节 | 两代同值 0.5；boot 固定面缺省 1 靠 last-wins 被本键覆盖 |
| `DSV41_WO_A_W8` | 1 | 注意力输出投影族走 W8A8 量化路径（族总开关） | wo_a 面回退窗 | unset=族内三键全失效，回非量化路径 | 两代同值 |
| `DSV41_WO_A_W8_MID` | 1 | 同族：中段投影的量化分支 | 同上 | 同上 | 两代同值 |
| `DSV41_WO_A_W8_DROP` | 1 | 同族：dropout 段的量化分支 | 同上 | 同上 | 两代同值 |
| `DSV41_REPLICATED_SPLIT` | wqkv_a,engram.wkv | 把复制层的 `wqkv_a` 与 `engram.wkv` 两块权重按张量并行做列分片，省驻留内存 | 几乎从不需要（换分片策略=工程变更） | 改错名单（漏名/多名）=装载期位等校验失败，拒起（fail-closed） | 两代同值 |
| `SGLANG_FLASHINFER_MOE_FUSED_FINALIZE` | 0 | 关掉引擎自带 MoE 收尾融合，把收尾让给 b12x 计算树 | 与 b12x 切换绑定的工程窗，不单独动 | 误开=收尾计算与 b12x 路径打架 | 两代同值 |
| `DSV41_SPEC_SYNC_FREE` | all | 投机解码面：rank0 广播「释放/合并/审计」三挂点全开 | 投机面排障 | unset=多 rank 缓存释放不同步 | 两代同值 |
| `DSV41_EAGER_GLUE` | all | 采样器/草稿两级 stage cache 的急切粘合全开 | 同上 | unset=stage 间张量交接路径回退 | 两代同值 |
| `DSV41_FOLDED_FENCE` | 1 | 投机校验结果的折叠栅栏：一次同步把各 rank 结果收拢 | 同上 | unset=收拢路径变化，通信面漂移 | 两代同值 |
| `DSV41_SKIP_NONFINAL_DECODER` | 1 | 非末段 chunk 跳过晚层尾窗计算（省一次无效解码） | 性能回退窗 | unset=多算尾窗，变慢 | 两代同值 |
| `DSV41_DRAFT_HEAD_FP8` | 1 | 投机草稿头走 fp8 量化 | 草稿面回退 | unset=草稿头回高精度，变慢 | 两代同值 |
| `DSV41_DRAFT_HEAD_FP8_IMPL` | tp4 | 草稿头 fp8 的实现选 tp4 行瓦 | — | 换别的实现名=未验证路径 | 两代同值 |
| `DSV41_DRAFT_MAIN_PROJ_SPLIT` | 1 | 草稿主投影做分裂 | — | unset=回合并投影 | 两代同值 |
| `DSV41_VERIFY_CAP` | conf:0.1 | 投机校验按置信度 0.1 截断（`conf:` 前缀+数值格式） | 调投机接受率的实验窗 | 格式写错=解析失败；数值乱调=接受率漂移 | 两代同值 |
| `DSV41_SHARED_PAD_K` | 1 | 共享 padding-K 快路径 | — | unset=padding 路径回退 | 两代同值 |
| `DSV41_ROUTER_LIVE` | 1 | 死行路由折叠（与 verify_cap 同族收尾） | — | unset=死行不再折叠 | 两代同值 |
| `DSV41_MOE_B12X_NEXT_DETERMINISTIC` | 1 | b12x MoE 计算走确定式：同输入必同输出，位等对拍的前提 | 需要非确定高性能实验时（不建议产线） | unset=位等对拍失效，跨靴 diff 判读作废 | 两代同值 |
| `TP_SIZE` | 4 | 钉死张量并行度=4，防止引擎按缺省把头数/分组/词表垫错 | 改并行度=换栈级变更，不在参数面动 | 改错=垫子把引擎结构参数整组垫错（头数/分组/词表全错），质量面崩 | 两代同值 |

（`DSV41_MOE_B12X_NEXT=1` 主开关在 boot 固定面注入，不在 56 键内；本键只是它的
确定式子开关。）

## 1.2 预填充/稀疏/输出上限族（7 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `DSV41_PREFILL_SP` | 1 | 预填充稀疏化基座（deep-carry stage1 三挂点），长上下文预填充省算力的地基 | SP 面回退窗 | unset=预填充回稠密路径，长上下文显著变慢 | 两代同值 |
| `SGLANG_MAX_NEW_TOKENS_LIMIT` | 65536 | 单请求最大输出 token 数的硬上限 | 客户端确需更长输出时上调 | 调小=输出被截；调大=极端请求占池、挤压并发吞吐 | 两代同值 |
| `DSV41_SPARSE_LOCAL_CONSUME` | 1 | R1 形的稀疏 gather/consume 接缝开关 | R1 面回退（unset 即回退族） | unset=回 stock consume 路径 | 两代同值 |
| `DSV41_SPARSE_LOCAL_CONSUME_TIER` | triton | consume 实现选 triton 档 | — | 换档=未验证路径 | 两代同值 |
| `DSV41_SPARSE_LOCAL_ADMISSION` | 1 | 「形知准入」：按上下文上限+并发上限在请求入口提前拦截，超限请求不进引擎 | 调整准入策略的实验窗 | unset=准入探测关闭，超限请求进了引擎才失败（报错面后移） | 两代同值 |
| `DSV41_SPARSE_LOCAL_ADMISSION_CTX_CAP` | 600000 | 准入的上下文上限（与池门 ctx 600000 绑定） | 必须与 serve `--context-length` 同步改 | 与引擎池门不一致=误拦合法请求或放行超限请求 | 两代同值；属池红线组（§3.4） |
| `DSV41_SPARSE_LOCAL_ADMISSION_MRR` | 16 | 准入的最大并发请求数（与池门 MRR 16 绑定） | 必须与 serve `--max-running-requests` 同步改 | 同上 | 两代同值；属池红线组（§3.4） |

## 1.3 CERT 认证筛幕族（4 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `DSV41_CERT_HEAD` | 1 | 打开 CERT 认证筛幕：推理过程中按层位自检输出质量（1=性能模式） | CERT 面实验 | unset=筛幕整体关闭 | 两代同值=1 |
| `DSV41_CERT_HEAD_M` | 6,12,18,24,30,36,42,48 | 筛幕的检查点位：第 6/12/…/48 层共八元 gate | CERT 档位实验 | 需 lm_cert 件对应版本支持，不匹配=gate 不生效 | 〔0.3.1〕6（单点）；八元=CBX1A 唯一终态改值键（c4 +0.7% 正向/c1/c8 零漂） |
| `DSV41_CERT_HEAD_LOG_EVERY` | 0 | 筛幕日志频率（0=不打） | 排障时临时开 | 开=产线日志量增大 | 〔0.3.1〕200 |
| `DSV41_CERT_HEAD_DEBUG` | 0 | 筛幕调试开关（0=关） | 排障时 | 开=日志与开销增大 | 〔0.3.1〕1 |

## 1.4 平台噪声/健康面（1 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION` | 0 | 关掉 `/health` 探针「每次真跑一次生成」的行为——关上之后健康检查只是轻量探活 | 想要真生成型探针的站点 | 误开或**丢键**=health 每次真生成（约 1s/次）且占用生成资源；本键常见丢法=env 末行缺换行（PITFALLS P2-1） | 〔0.3.1 无此键〕D12 沉降键，51→FB54 新增四键之一 |

## 1.5 NCCL LL128 三键 + L2 预取两键 + O12 调度两键（7 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `NCCL_BUFFSIZE` | 1048576 | NCCL 常规协议缓冲改为 1MiB（覆盖 boot 固定面缺省 8MiB，靠注入序 last-wins） | 通信调优窗（不建议产线乱动） | 漏注/写错=回 boot 固定面缺省，协议面漂移 | 两代同值（〔0.3.1〕LL128 采纳窗） |
| `NCCL_LL128_BUFFSIZE` | 262144 | LL128 协议缓冲 256KiB（覆盖固定面缺省 `-2`） | 同上 | 同上 | 两代同值 |
| `NCCL_PROTO` | ^LL128 | 协议选择里**排除** LL128（覆盖固定面 `LL,LL128,Simple`） | 同上 | 写成别的集合=协议面漂移 | 两代同值 |
| `DSV41_L2_PREFETCH` | 1 | GPU L2 预取总开关（五个挂点），把即将用的数据提前拉进 L2 | L2PF 面回退窗 | unset=盘读延迟重新暴露 | 两代同值（〔0.3.1〕L2PF6 转正） |
| `DSV41_L2_PREFETCH_MB` | 6 | 预取额度 6MB（单键域：开关+额度两键一族） | 调优窗 | 调大=挤占 L2 有效容量；调小=预取不足 | 两代同值 |
| `SGLANG_DSV4_O12_SCHED_ASYNC` | 1 | O12 主机间隙调度：调度异步化（overlay scheduler 面） | O12 面回退 | unset=主机调度间隙回潮（HOSTGAP 变大） | 两代同值；DP/PP/disagg 拓扑下此键面拒起（拓扑门） |
| `SGLANG_DSV4_O12_RECV_INTERVAL` | 4 | 接收轮询间隔=4 | 同上 | 调大=接收延迟；unset=回缺省 | 两代同值 |

## 1.6 W5 两键 + R1 一键 + FL6 一键（4 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `DSV41_PREFILL_SP_FP8` | 1 | W5：预填充 all-gather 走 MXFP8 字节域（通信量减半级；三重对拍+永久 bf16 回退护栏） | W5 面回退（unset 即回退族） | unset=回 bf16 AG（构造性回退，位等安全） | 两代同值（〔0.3.1〕W5 转正 50 键新增） |
| `DSV41_PREFILL_SP_TAIL_GATHER` | 1 | W5：预填充出口尾行直聚（尾行不再走全行聚合） | 同上 | unset=尾行回全行 AG | 两代同值 |
| `DSV41_FP4KV_R1_INKERNEL` | 1 | R1：FP4-KV 预填充走 in-kernel 路径（严格布尔；fail-safe 双跑护栏在 adapter 件内） | R1 面回退（unset 即回退族） | unset=构造性回退（R1 横幅撤净）；**转正后误删=同 unset** | 两代同值=1；转正≠删键（ENV-CHAIN §6） |
| `DSV41_FL6_RECALL_FIX` | 1 | FL6 召回修复门：开着=修复件生效；摘掉=sitecustomize 逐字原版行为（修复休眠） | FL6 面回退（两级回退的一级=摘本键） | unset=召回修复休眠，长上下文召回回退 | 〔0.3.1〕第 51 键（FL6 转正窗入役）；0.3.2 保留=1，FL6 面具在役 |

## 1.7 RoCE/通信面（9 键）

前两键是双门、聚合两键见 §1.9 专节、HCA 对见 §1.11。**通信面是「绑定项」不是
「可选调优」**——整族要么整套在役、要么随整栈换代，不做单键清理。

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `DSV41_ROCE_RING` | 1 | RoCE all-reduce 安装门之一（`gates_on()` 两键与门；缺任一=install 早退） | 不单独动（与下键同批） | 单退其一=RoCE AR 面整族失效 | 两代同值=1；**0.3.2 语义被 `LUZ_SWITCH_ROCE_FLAT` 覆盖为兼容位**（选 flat 运行时） |
| `SGLANG_ROCE_ALLREDUCE` | 1 | 双门第二键（同一批门，须与上键同批进出） | 同上 | 同上 | 两代同值=1 |
| `LUZ_SWITCH_ROCE_FLAT` | 1 | 拓扑选择门：选 flat/one-shot 交换机运行时（优先级最高） | 拓扑换代工程窗 | 环网形误带=拓扑混拼（fail-closed 或走错口对） | 〔0.3.1 无此键〕交换机专属键 |
| `B12X_ROCE_TOPOLOGY` | switched | C 层拓扑声明=交换机 fabric：关掉环网 2 跳假设与 flow-label 技巧 | 同上 | 非 ring/switched 的值=报错退出（fail-closed）；环网形禁带 | 〔0.3.1 无此键〕交换机专属键 |
| `B12X_ROCE_TRAFFIC_CLASS` | 106 | RoCE 报文流量类=106→DSCP26→交换机 SP3/TC3/PFC prio3 受保护档 | 交换机 QoS 规划不同的站点按本站实测 | 照抄外部形 96=无本系列交换机验证、可能掉出受保护档；须与 boot 固定面 `NCCL_IB_TC=106` 同档（对称载流） | 〔0.3.1 无此键〕**我方值，不照抄外部 96** |
| `B12X_ROCE_HCA` | rocep1s0f0,roceP2p1s0f1 | b12x RoCE 用的网卡部署对：跨 PCIe 域各取一口（见 §1.11） | 换机器/换布线时**本站实测** | 照抄旧 4 口裸列=与 2 口部署对冲突，起机炸 | 〔0.3.1〕4 口裸列；〔FB54〕收口为 2 口对 |
| `B12X_ROCE_TWO_WAVE_THRESHOLD_BYTES` | 0 | 显式关掉 two-wave 分波（与 C 层 switched 同向双保险） | — | flat 运行时**无读点=零行为差**（自文档化）；ring 支改它才改行为 | 两代同值=0 |
| `SGLANG_ROCE_MAX_SIZE` | 1179648 | RoCE all-reduce 单发字节上限 → **§1.9 绑定律专节** | **★见专节（不许动）** | **★见专节** | 〔0.3.1〕262144→〔FB54〕524288→〔E16B1〕1179648 |
| `DSV41_ROCE_GATHER` | 1179648 | RoCE all-gather 单发限幅（adapter 侧 gather 面）→ **§1.9 专节** | **★见专节（不许动）** | **★见专节** | 〔0.3.1〕524288→〔E16B1〕1179648 |

## 1.8 E16B2 split/compact gather 两键（2 键）

| 键 | 现值 | 作用 | 何时需要改 | 改错会怎样 | 代际注记 |
|---|---|---|---|---|---|
| `DSV41_SPLIT_COMPACT_GATHER` | 1 | 复制分裂走「紧凑 gather」：不等长 last-dim 的聚合一次收拢（省通信轮次） | 与 adapter `replicated_split.py` 配套的实验窗 | 两键缺省=旧行为；动它必须与配套件同批（绑定律），否则不生效或行为不齐 | 〔0.3.1 无此键〕E16B2 新增（T2 件配套） |
| `DSV41_REPLICATED_SPLIT_WINDOW` | 0 | 分裂窗口显式写 0（=保持缺省旧行为；显式写出=自文档化+可直证） | 开窗实验时 | 非 0=进入实验路径，需配套件与判读窗 | 〔0.3.1 无此键〕E16B2 新增 |

## 1.9 ★专节：RoCE 聚合两键绑定律（`SGLANG_ROCE_MAX_SIZE` + `DSV41_ROCE_GATHER`，均 1179648）

这两个键限定**一条 RoCE 聚合消息最多打包多少字节**（1179648 B = 1152 KiB）。
上限越大，一次集合通信能打包的块越多、消息轮次越少——**0.3.2 引擎（r032c）的
高并发路径硬依赖这个更大的聚合窗口**。

**回滚实测（A/B/A，同镜像、同 adapter、同量具，只改这两键）**：

| 并发 | A：1179648 | B：回滚旧档位 | A'：改回 |
|---|---|---|---|
| c1 | 正常 | **−55%** | 完全复原 |
| c4 | 正常 | −68% | 完全复原 |
| c8 | 正常 | **−96%** | 完全复原 |
| c16 | 正常 | −94% | 未测 |

**退回慢路径的指纹**：高并发下**越并越慢的非单调塌陷**（c8 比 c4 还慢），且
**单请求 tok/s 也一起掉**、加重预热不恢复。这不是负载波动、不是没热透、不是网卡
问题——看到这个指纹，**先查这两键有没有被改**，再去查别的。

**三条纪律**（判据细节见 [`PITFALLS-AND-FAQ.md`](PITFALLS-AND-FAQ.md) P4-1/P4-2）：

1. 跑 0.3.2 引擎就**不许回滚这两键**；任何「清理多余参数」「参数瘦身」的操作
   都**不许碰它们**——否则性能掉一半以上且高并发塌陷。
2. **A/B 必须在 0.3.2 引擎上做**。在 0.3.1 引擎上做会得出「无收益」的**反向
   结论**：旧引擎没有依赖该窗口的快路径，两档位差值落在噪声带内；这不是矛盾，
   是代际差异。**换代之后，上一代的所有 A/B 结论全部失效**，报告里必须写清
   「这是哪一代引擎上的读数」。
3. 环网形站点取这对键必须自行 A/B（[`docs/RING-0.3.2-COMPAT.md`](RING-0.3.2-COMPAT.md)
   §2.3 标「中风险；环网 4 口需 A/B」）。

演进链：〔0.3.1〕262144 →〔FB54〕524288 →〔E16B1 起〕1179648（ENV-CHAIN §2）。
**与 §5 回退链的交叉警示**：env 是整文件回退，退到 E16B1 以下＝这两键一起回到
524288/262144——那不是「env 回退」，是**通信档位回滚**，只应随整栈换代（回到
0.3.1 引擎）一起做（§5.6 红框）。

## 1.10 ★专节：`DSV41_ENGRAM_CACHE_GIB` 的 per-store 语义（0.5）

engram 是本栈的长上下文行缓存（从权重打包出的稀疏索引数据，按需 pread 读取，
严禁整体加载）。本键是它的**页缓存配额**，三个最容易判错的点：

1. **配额是每层（per-store）额度，不是每机总额**。单机实际占用 = 值 × 层数
   （本模型两层做 engram 分片，见
   [`deploy/reconstruct/0.3.2/weights/WEIGHTS.md`](../deploy/reconstruct/0.3.2/weights/WEIGHTS.md)
   §3 的 L1/L14 分层）。boot 注释（`deploy/bin/r3-boot-arm.sh` COMMON_ENV 段）：
   该键语义=「显式每层顶（废除 //2 隐除）」。算内存预算时**必须乘层数**，拿
   单层值当总占用会低估一倍。
2. **守卫只记 warning、不阻起**。超限守卫（超 `min(4GiB, 10%MemAvail)` 档）只在
   日志告警，不会拒起（[`CALIBER-AND-MEASUREMENT.md`](CALIBER-AND-MEASUREMENT.md)
   §5.3）。所以**「没报警」推不出「没事」**——要自己按层数乘完再对上限。
3. **boot 固定面另有缺省值 1**（`COMMON_ENV` 注入 `-e DSV41_ENGRAM_CACHE_GIB=1`），
   env 件的 0.5 靠 last-wins 覆盖它（§0 第二律）。因此**删掉 env 里这行 ≠ 回到 0**，
   而是回到 1——扩容/缩容操作要改值，不要靠删行。

**扩容收益怎么看：看淘汰（驱逐）次数趋零，不看命中率。** 战役内实测（0.5 →
2.0 每层）：淘汰次数从每轮 1000-2100 次降到整窗累计 7 次；命中率 58.8% → 99.6%。
判读要点：

- **冷启动命中率低是常态**：缓存逐层预热需要真实流量，新靴后头几轮命中率低
  不是配额不足的证据；
- **命中率长期低位也不必然是配额不足**：工作集变了、重复率低了都会压命中率；
- **淘汰次数持续高位才是配额不足的直接证据**（缓存装得下工作集时几乎不需要
  淘汰）。扩容决策以「淘汰次数趋零」为准，命中率只作旁证。

## 1.11 ★专节：`B12X_ROCE_HCA` 部署对与环网映射表 `B12X_ROCE_PEER_HCA_MAPS`

**`B12X_ROCE_HCA`（0.3.2 在役，2 口部署对）**：值 `rocep1s0f0,roceP2p1s0f1`
是**作者站点的物理接线**——跨 PCIe 域各取一个口组成双 rail 部署对。机制可学、
值必须本站实测：先看本机 `ibstat`/`lspci` 的网卡-PCIe 域归属，再按「跨域各取一」
组对。历史注记：〔0.3.1〕环网形用 4 口裸列，实测 4 口 twin 分区面有间歇黑洞且
不增带宽（2 口即达同量级物理封顶），故 0.3.2 收口为 2 口。boot 固定面的
`NCCL_IB_HCA` 部署对与本键是**同一个口对**（NCCL 面与 b12x 面对称载流），改一处
必须两处同步。

**`B12X_ROCE_PEER_HCA_MAPS`（〔0.3.1〕环网形历史键，0.3.2 已退役删除）**：
环网形的逐秩「属主映射表」——哪台机的哪个口连哪两个对端，是作者物理接线的
逐 rank 编码。三个要点（判据细节见 [`PITFALLS-AND-FAQ.md`](PITFALLS-AND-FAQ.md) P1-3）：

- **照抄必挂，且错在哪几段、报错就点名哪几个 rank**（`ibv_modify_qp(RTR)
  Connection timed out`）。拿到环网形（如 [`deploy/env/PROD-R51W5-FL6FIX-spec1.env`](../deploy/env/PROD-R51W5-FL6FIX-spec1.env)）
  必须把映射表按本站实测值逐 rank 段重写，四机一致。
- 四个硬约束（不满足直接抛异常，不会静默降级）：每 rank 必须映射全部非自身
  rank 且各一次；同一 peer 的索引互异且落在 `[0, HCA 数)` 内；HCA 数 >2 而表留
  空=直接 `RuntimeError`（「首靴留空、读 INFO 后填」的模板注释在 4 口环网下是
  陷阱）；改路径数必须同步改表。
- **两形互斥**：环网形要逐秩表；交换机形（0.3.2）删表走 flat 运行时。把表带进
  交换机形、或把交换机三键带进环网形，都是拓扑混拼（C 层/NCCL 面 fail-closed
  或静默走错口对）。环网物理接线与逐秩映射的部署正档见本仓
  [`docs/RING-DEPLOY.md`](RING-DEPLOY.md) §4（织网安装件取自基础设施仓
  `luxingcom/aicad-nccl-optimization`，取件指引见该档 §2）；环网/交换机
  两形可取件边界见 [`docs/RING-0.3.2-COMPAT.md`](RING-0.3.2-COMPAT.md)。
  boot 件 `WORKERS` 表的 PEER_HCA 末列在 0.3.2 保留为史档、不再注入。

---

# 2. serve 九参词典（SPEC6 九参）

serve 参数分**两个注入面**（这是外部最容易拼错的地方）：

- 第 1-6 参经 `SPEC_EXTRA_ARGS` 环境变量在点火时传入（空格分词追加面，缺省
  no-op——漏传不报错，行为静默偏离定型形）；
- 第 7-9 参写死在 boot 件 `SERVER_ARGS` 固定面（`deploy/bin/r3-boot-arm.sh`）；
- `SPEC=1` 时另追加 `--speculative-algorithm DSPARK`（投机解码总开关，不计入
  九参谱）。

正典谱表=[`deploy/SPEC6-SERVE-REF.md`](../deploy/SPEC6-SERVE-REF.md)；九参归一
指纹=`9d64a5de`（旧六参 `33d7161f`、旧八参 `6b12a445` 为史档，保留不覆写）。

| # | 参数 | 值 | 作用 | 命名/书写陷阱 | 直证法 |
|---|---|---|---|---|---|
| 1 | `--prefill-decode-interval` | 16 | 预填充与解码的交替间隔：每 16 步预填充让位一次解码，平衡首 token 与吞吐 | 值在 argv 里位于参数名**下一行**，三层引号下 grep `-A1` 会被打坏——先落盘再查（PITFALLS P2-5） | argv 值直读 |
| 2 | `--max-queued-requests` | 32 | 排队请求上限：超出即背压，保护池与延迟 | 同上 | argv 值直读 |
| 3 | `--min-free-slots-delay` | 1 | 池空闲槽不足时的让位延迟 | 同上 | argv 值直读 |
| 4 | `--enable-decoder-swa-bounded-replay` | （flag） | 解码侧 SWA 有界回放：滑动窗口注意力用「有界重放」路径（也是 §3.2 互斥律里的「回放旗标」） | **flag 类不带值**：写成 `=true`/`=1` 不认 | argv 存在性 |
| 5 | `--reasoning-parser` | `deepseek-v41` | 思考流解析器选 DeepSeek V4.1 专用 | **连字符**。与第 7 参互不通用，写反**不报错、功能静默缺失** | `/get_server_info` 或 argv |
| 6 | `--swa-prefix-tails` | 256 | SWA 前缀尾巴保留 256（召回窗口；〔0.3.1 早期〕64→256 转正在役） | 调小=长上下文召回退化 | argv 值直读 |
| 7 | `--tool-call-parser` | `deepseekv41` | 工具调用解析器：让 `tool_calls` 结构化成型（issue #1 修复；只对带 `tools` 的请求生效） | **连写**（无连字符）。写 `deepseek-v41` 不认、DSML 原样返回纯文本；`/health` 仍 200（静默降级） | `serve_flags_gate.sh`/`/get_server_info` 的 `tool_call_parser` |
| 8 | `--enable-cache-report` | （flag） | 响应里上报 `usage.prompt_tokens_details.cached_tokens`（issue #2 修复；缺省关，面板缓存命中恒 0%） | flag 类不带值 | `serve_flags_gate.sh`/`enable_cache_report` |
| 9 | `--sleep-on-idle` | （flag） | 空闲时调度器休眠：空闲忙转从约 1 核降到近零（每台省 10-12W 级；仅空闲态，请求路径零变化） | flag 类不带值 | argv 存在性 |

**旗标-能力对照**（缺了会怎样）与判据表见 SPEC6「旗标-能力-生效值对照表」；
逐条要点：第 7 参缺=工具调用纯文本输出；第 8 参缺=缓存字段恒 null；第 2 参偏=
并发/背压行为偏离定型形；第 9 参缺=空闲期 CPU 忙转。

## 2.5 直证法（判「参数真的生效」的唯一正道）

判据纪律：**断言正在跑的进程 argv / 运行时自省，不断言源码或 env 里的静态串**；
只证「镜像支持」=假绿，接线漏了 `/health` 仍 200。

```bash
# ① 闸门（只读、fail-closed、含 R1-R7 反向自检；head 与 worker 必须各查——角色差异 R7）
bash tools/serve_flags_gate.sh --container <PREFIX>-head --container <PREFIX>-worker
bash tools/serve_flags_gate.sh --api http://127.0.0.1:<PORT>      # /get_server_info 自省面
bash tools/serve_flags_gate.sh --self-test                        # 判别力回归

# ② 裸读进程 argv（NUL 转换后落盘再 grep；值在参数名下一行）
docker exec <CTN> sh -c 'tr "\0" "\n" < /proc/1/cmdline' > /tmp/argv.txt
grep -A1 '^--chunked-prefill-size' /tmp/argv.txt
```

**注意 `docker inspect` 的 `Config.Cmd` 只是镜像设计意图**：它反映「镜像配置
层面打算跑什么」，经 entrypoint/wrapper 起栈、或 argv 被启动链改写时，**不反映
真实 argv**。本仓 boot 链直接以 `python3 -m sglang.launch_server …` 为容器命令，
`Config.Cmd` 恰与真实 argv 一致——但这是巧合不是保证，且部分四查口径（如
[`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) §9）仍引用它作**镜像面**证据。判
「参数是否生效」恒用 ①/②；`Config.Cmd` 只能用来答「镜像设计意图」这一个问题
（PITFALLS P2-4）。

---

# 3. 禁键词典

三级清单正典=[`docs/runbook/OPS-MANUAL-031.md`](runbook/OPS-MANUAL-031.md) 第六章；
组合窗裁定=[`CHANGELOG.md`](../CHANGELOG.md) 0.3.1 节 T1 条（chunk8192 判负不
进形、16384 永禁维持、TPsplit 留库不转正）。

## 3.1 三级清单

| 级 | 键/值 | 含义 | 依据 |
|---|---|---|---|
| **永禁** | `--chunked-prefill-size 16384` | 死刑令：任何形任何窗都不许再进 | COMBO 判负链（CHANGELOG T1） |
| **判负不进形** | `--chunked-prefill-size 8192` | SPEC7 臂已判负、不进定型形；正典值=**4096**（池红线组）。留作 0.3.2 观察位：**非同具形不可平移定谳**——别的站别的形上没做过同具 A/B，不许引用本判负当自己站的结论 | COMBO 门 1（SPEC6 谱注） |
| **观察位** | bypass / A23-β TBO / CG-β | 未定谳实验位（t4-patch 形 `0847a7cd` 留库），进形须另开判读窗 | OPS-MANUAL 第六章 |

在役正态（对照）：`--chunked-prefill-size 4096`，且**无** mixed-chunk 旗标。

## 3.2 ★专节：成对判负关系（chunked 档位 × mixed-chunk）

判负旗标常常**成对出现，撤一个不撤另一个等于没撤**：

- `--chunked-prefill-size 8192/16384`（判负不进形 / 永禁）
- `--enable-mixed-chunk`（判负）

**互斥律（boot 期 guard 台账硬门）**：回放旗标（第 4 参
`--enable-decoder-swa-bounded-replay`）在场 ⇒ 混合批旗标（`--enable-mixed-chunk`）
**必须不在场**。台账（guard 注册面）按此判负。

**定性口径（重要，报缺陷时别说错）**：**台账判负 ≠ 引擎拒起**。引擎源码里没有
对应 raise——两旗标共存时引擎实际能正常起栈；硬门在 guard 侧台账，不在引擎。
所以报问题时要说「**台账判负、与回放旗标互斥**」，不可说「已触发故障」或
「引擎会拒起」（PITFALLS P2-6 实测口径）。

**撤除操作**：先落盘 argv 再逐条对清单 grep：

```bash
grep -E 'chunked-prefill-size|mixed-chunk' /tmp/argv.txt
```

两条纪律：①撤就**成对撤**；②「当时跑着没坏」≠「合规」——测量说「这一格没
退化」，规范说「这个值不许进形」，两者不冲突，**后者优先**，别拿测量结论覆盖
规范结论。

## 3.3 其他禁设/零携带

| 类 | 键 | 口径 |
|---|---|---|
| 测量键零携带律 | `CHUNK_WALL` / `wallhook` | 产线 boot 禁带测量键；直证=容器内两值俱 0/缺席 |
| unset 即回退族 | `DSV41_PREFILL_SP_FP8` / `_TAIL_GATHER` / `DSV41_FP4KV_R1_INKERNEL` | 键关=构造性 no-op 回退，无需件回滚 |
| 禁设键 | `DSV41_SPARK_PREFILL_TP_SPLIT`（SPLIT 键） | spark_prefill_split 留库不转正；库内件 `6498aa39` 的复活位=定型微调/单臂差分**呈裁**，未裁前禁设 |
| 禁设键 | `FP8_MOE` | W5 弃用钉死：现役 `prefill_sp.py` 下恒 bf16 + DEPRECATED 横幅（[`docs/registry/FORM-REGISTRY-031.md`](registry/FORM-REGISTRY-031.md) §三） |

## 3.4 硬守门表（改参数后的零回归底线）

改任何参数面后，下表全绿才有资格谈「形没变」（正典=
[`docs/release/0.3.2-RELEASE-NOTE.md`](release/0.3.2-RELEASE-NOTE.md) §四）：

| 门 | 0.3.2 终态 |
|---|---|
| EQ-1 位等 | 跨靴 6/6 逐字 |
| GSM8K | 0.985-0.99（≥0.97；快核 err=0） |
| needle | 600k 3/3 |
| **池红线组** | pool **9,600,000** / chunked **4096** / MRR **16** / ctx **600000**（boot 期 `/server_info` 真值断言在役） |
| PR 七档 | vs 锚全 IN-BAND |
| gid-face-gate | 16/16 GREEN |

池红线组四值同时出现在 serve 参（`--max-total-tokens`/`--chunked-prefill-size`/
`--max-running-requests`/`--context-length`）与 env 准入两键（§1.2）——**改一处
必须四处同批同步**，boot 断言会对表。

---

# 4. 换模型流程（换形不换栈）

**总则：换模型=换形不换栈。** boot 链、容器结构、网络栈、serve 九参全部不动；
换的是四样东西：**权重、engram、注册卡、参数形**。多模型注册正典=
[`deploy/models.d/README.md`](../deploy/models.d/README.md)（三卡制：v41-prod /
v4-0731 / v4-vl-exp；nvfp4 变体已弃用留痕不立卡）。

## 4.1 权重身份三件（对注册卡）

一个模型的身份由**三件**钉死，与注册卡逐字段相等才算同一模型：

1. **分片数**（safetensors 分片个数；现役 1017 形=48 分片、84 文件）；
2. **`config.json` sha256 前 16 位**（注册主键；1017 形=`8be45ce0476004a3`）；
3. **目录总字节**（1017 形=510,311,045,870 B）。

boot 指纹行 `MODEL=<model_id> CFG=<config sha256 前 16> PATH=<挂载路径>
BYTES=<目录字节数>` 与注册卡登记值**逐字段相等方算靴成；不等=形面红**
（models.d 更新纪律）。全量校验命令与逐件 sha256 台账见
[`deploy/reconstruct/0.3.2/weights/WEIGHTS.md`](../deploy/reconstruct/0.3.2/weights/WEIGHTS.md)。

## 4.2 参数表三段论（锚带与读数属于谁）

判定某张参数表/某个读数锚能不能用到自己站上，走三段论：

1. **别的模型形不行（fail-closed）**：量具带形态门——needle 忘带 `--form` 时
   auto 判不出形态→unknown→按 ≤128k 红线直接 SKIP/拒跑（不是跑慢，是不让跑）；
   env 面有形态 lint 黑名单（§4.3）。抄错模型的键面会被门拦下，这是保护不是故障。
2. **别的引擎（代际）不行**：A/B 结论不跨代（§1.9 纪律 2）；旧代引擎上的「无
   收益/有收益」到新代全部作废重测。
3. **只有「本模型 × 本引擎代 × 本形态」的组合成立**：注册卡锚带（GSM8K/DE/PR
   参考值）与 V4.1 暖态产形绑定，**禁向 0731/VL 外推**（v41-prod 卡 §e 纪律）。
   跨形态（环网↔交换机）读数同样不可互比（CALIBER §6.2 三不比+跨形态不比）。

## 4.3 形态 lint：未知形态拒起，禁抄专属键

boot 件带 env-lint 拒绝门（`deploy/bin/r3-boot-arm.sh` QA-GATES 段）：点火时
显式带 `GATE_FORM=<形态名>` 即激活 lint 器（对 `ARM_ENV_FILE` 过三禁令+形态键
黑名单+键面合同；`--form` 形态名集合在 lint 器内白名单化，**未知形态=拒绝起栈**，
红=fail-closed 拒起；不带 `GATE_FORM`=整段跳过、生产行为不变）。含义：

- 每个模型/形态有自己的键面合同，**把 A 形的专属键抄进 B 形**（如把 0731/VL 形
  键抄进 v41 形、把交换机三键抄进环网形）会被黑名单拦下——拦下是设计行为；
- 「未知形态拒起」是防代际混淆的机器门：宁可拒起，不静默混跑。

## 4.4 ★换权重 ≠ 换 engram（最容易静默劣化的一步）

**engram 是从权重打包出来的派生物**（8 分片=L1/L14 两层 × 4 rank；由
`engram-tools/pack_all.sh` 从 checkpoint 全量树打包，分片头带 magic/layer/行区间，
不含权重身份字段）。因此换权重时**必须连同 engram 一起换**：

- **换权重不换 engram = 新权重配旧 wkv 混跑**。分片只按 layer/rank 命名、不含
  权重身份 ⇒ 引擎照常挂载、**不报错**、质量**可能静默劣化**——这是换模型流程里
  唯一既不 fail-closed 也不报警的错法。
- 处置**二选一**（不可都不做）：
  1. **重生成**：`pack_all.sh` 从新 checkpoint 打包 → `distribute.sh` 四机分发
     → `verify_engram.py`/`verify_remote.py` 校验（约 189G，耗时数小时）；
  2. **跑质量锚对比**：不重生成时，必须用注册卡锚带（GSM8K/needle/qeval）对新
     旧组合各跑一轮，读数对锚带判漂移，带内才许放行。
- **判定新旧看 mtime**：engram 目录的修改时间**晚于**权重目录才算「engram 比
  权重新」；engram mtime 早于权重 mtime=旧 engram 配新权重，按上段处置。
- 旧权重/旧 engram 原样保留=回退面（WEIGHTS.md §4：boot 的模型源/engram 指针
  指回旧路径即可回退）。

## 4.5 秩映射与切回门

- boot 件 `WORKERS` 表逐行钉 rank↔机↔模型源↔engram 目录；**秩映射错位=引擎找
  不到 `engram-l{1,14}-r{rank}of4.bin`，起机即失败**（fail-closed，这是好门，
  不要绕过）。
- 新模型窗结束回产放行=四件全绿：质量锚（canary/GSM8K 对卡带）+漂移三查+复原
  复验链（健康口 200+selfcheck+smoke 3/3+四机水位）+boot 指纹行逐字段相等
  （v41-prod 卡 §g 切回门）。

---

# 5. 回退链全集

**回退五律**（正典=[`docs/runbook/OPS-MANUAL-031.md`](runbook/OPS-MANUAL-031.md)
第三章 + [`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) §11）：

1. **env 键级回退优先于件级回退**：键 unset 即回退、无件回滚需求——能摘键解决
   的不要动文件（md5 面、四机同步面都省掉）。
2. env 回退=**相邻级单文件整替**（`ARM_ENV_FILE` 回指旧件+复靴），**不手改键**；
   改 env 热改无效。
3. 件级回退=**md5 复原四机三步**：先在 head 落件 → 同步下发 → 四机 `--check`
   全等；先备份后覆盖（`cp -a` 保属性），删件先存档。
4. 每级回退后与 boot 同律收口：沉降 ≥600s → 复靴 → 四查（health 200/printenv
   逐字/横幅直读/面指纹四机全等）→ 接线闸门 → warm 请求步 64k×2+warm 门 →
   smoke。**回退完成前不开流量**；容器删除前必存 docker logs。
5. **旧形 A8/A9 未接线时闸门应红——这是预期判别，不是回归**（回退到六参/八参
   形，`serve_flags_gate.sh` 红是正确表现）。

## 5.1 env 键级/件级链（0.3.2 五级）

| 级 | 形 | md5 | 相对上级差异 |
|---|---|---|---|
| L0 在役 | CBX1A（56 键） | `0729e18d` | 终态（CERT M 八元） |
| L1 | E16B2（56 键） | `5877fcb0` | −compact gather 两键 |
| L2 | E16B1（54 键） | `d55baa00` | 聚合两键回 524288（**§5.6 红框**） |
| L3 | FB54（54 键） | `ad635762` | 聚合上限 524288→262144；无交换机三键 |
| L4 | 0.3.1（51 键） | `2ac74586` | 回 0.3.1 环网形基线（+环网 7 键族） |

（键级细回退另有一族：unset 即回退键见 §3.3；FL6 面两级=摘第 51 键休眠→摘
adapter 接线。）env 件内注释块还留有战役窗级回指注记（WE52/WG53/WC44 等），
是 provenance 史档，不是回退链成员。注：
[`docs/release/0.3.2-RELEASE-NOTE.md`](release/0.3.2-RELEASE-NOTE.md) §六的
摘要链跳过了 E16B1 级，逐级正典以 ENV-CHAIN 为准。

## 5.2 镜像：单行回指

boot 件 `IMAGE=` 单行回指旧 tag（r032c → r032b 在库 → 0.3.1 基座 tag）+复靴；
`RepoDigests` 四机必须同值。镜像双存（现役+基线）是设计内回退面，单靴约
1.5-2h（含沉降+warm+四查）。digest 判源豁免与重建口径见
[`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) §3。

## 5.3 adapter：逐件回拷与整树回拷

- **逐件链**（单优化面回退）：A6 `sitecustomize.py` `beb131ab`→`55b1e412`；
  R1 `kv_fp4.py` `75062432`→`feaaadd4`。动作=四机三步（01 落件→sync
  `--apply`→`--check` 四机全等+`--expect` 锚断言）。
- **整树回拷**（整代回退）：升级前备份目录
  `rsync -a --delete <PRODUCT_DIR>/dsv41/adapter-bak-pre-032-<ts>/ …/adapter/`，
  复靴后按 [`deploy/adapter/0.3.2-MANIFEST.md5`](../deploy/adapter/0.3.2-MANIFEST.md5)
  对表验收。
- **绑定律警告**：adapter 与引擎必须同批（`seam_mount`/`sparse_wire` 等装载缝件
  与 r032c 引擎件绑定）——只回退 adapter 不回退引擎、或反之，=能起能跑但静默
  回退上游修复（PITFALLS P2-3）。

## 5.4 overlay 与 b12x：整目录备份回拷

- overlay：29 件（0.3.1 基底 [`deploy/overlay/o12c1-prod/`](../deploy/overlay/o12c1-prod/)
  原样回拷；0.3.2 只覆盖了 `deepseek_v4_backend.py`，回拷该件原版即回退）。
  换引擎版本时 overlay 影子件与镜像/adapter **三步一起换**（PITFALLS P2-2）。
- b12x：3 件 RoCE 源码回拷 0.3.1 基底件；`_roce_proxy.c` 按源码 sha256 缓存在
  `~/.cache/b12x/roce/` 编译，回拷后**清编译缓存**再复靴（否则旧编译产物继续生效）。

## 5.5 boot 参面：单参回退

- 第 9 参：去 `--sleep-on-idle` 单行重靴（或回拷启动器件 `.bak-pre-wg`
  `9f3cdaac`；零 env 耦合、零 A8/A9 耦合）。
- A8/A9：回拷对应旧启动器件（SPEC6 注入面注记）。
- 换 boot 件后同样四查；公开件与产线件 md5 差异（快照头+掩码）见
  [`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) §8。

## 5.6 红框：通信面两键不可回滚

> **`SGLANG_ROCE_MAX_SIZE` / `DSV41_ROCE_GATHER` = 1179648 在 0.3.2 引擎上
> 不许回滚。** 回滚实测 c1 −55% / c8 −96% 塌陷（§1.9）；env 整文件回退到
> E16B1 以下会**连带**回滚这两键——那不是 env 回退，是整栈换代动作，只许与
> 镜像/adapter/网络面一起、按 §5 全套走。「清理多余参数」「对齐旧文档」都不
> 构成动这两键的理由。

---

## 附：本篇引用档索引（相对本文件 `docs/` 的路径）

| 引用档 | 用途 |
|---|---|
| [`../deploy/env/CBX1A-CERTM-spec1.env`](../deploy/env/CBX1A-CERTM-spec1.env) | 0.3.2 现役 56 键（本表数据源） |
| [`../deploy/reconstruct/0.3.2/env/ENV-CHAIN.md`](../deploy/reconstruct/0.3.2/env/ENV-CHAIN.md) | 51→56 键逐级演进链（两代对照正典） |
| [`../deploy/SPEC6-SERVE-REF.md`](../deploy/SPEC6-SERVE-REF.md) | serve 九参正典+命名陷阱+旗标对照表 |
| [`runbook/OPS-MANUAL-031.md`](runbook/OPS-MANUAL-031.md) | 禁键三级/boot 规程/回退律（0.3.1 手册，禁键章仍为正典） |
| [`release/0.3.2-RELEASE-NOTE.md`](release/0.3.2-RELEASE-NOTE.md) | 硬守门表/回退面/升级路径 |
| [`../deploy/bin/r3-boot-arm.sh`](../deploy/bin/r3-boot-arm.sh) | boot 固定面（NCCL/env 缺省/GATE_FORM lint/池门断言） |
| [`registry/FORM-REGISTRY-031.md`](registry/FORM-REGISTRY-031.md) | 0.3.1 历史键值与用途（代际标注源） |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 组合窗裁定段（T1） |
| [`PITFALLS-AND-FAQ.md`](PITFALLS-AND-FAQ.md) | 排障词典（P1-3/P2-1/P2-4/P2-6/P4-1/P4-2 等词条） |
| [`RING-0.3.2-COMPAT.md`](RING-0.3.2-COMPAT.md) | 环网/交换机两形边界 |
| [`../UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) | 逐步升级/验收门/回退操作 |
| [`../deploy/models.d/README.md`](../deploy/models.d/README.md) · [`../deploy/reconstruct/0.3.2/weights/WEIGHTS.md`](../deploy/reconstruct/0.3.2/weights/WEIGHTS.md) | 权重注册卡/身份三件/engram 生成与校验 |
| [`../tools/serve_flags_gate.sh`](../tools/serve_flags_gate.sh) | 起栈接线闸门（§2.5 直证法） |
| [`RING-DEPLOY.md`](RING-DEPLOY.md) | 环网物理接线/逐秩映射部署正档（§1.11 实测法；织网件取自基础设施仓，取件指引在该档 §2） |

——2026-10-30 公开仓文档治理批次建立。参数面再演进时：本表随代际滚动，历史值
一律加〔代际〕标不删行（判读线零事后改同律）。
