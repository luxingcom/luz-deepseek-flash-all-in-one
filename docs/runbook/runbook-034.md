# 0.3.4 运维手册（runbook-034 · 2026-10-28）

> **适用栈**：0.3.4 固化生产态（v41 固化面）。权威身份=「0.3.4-x6bake+repaired」版本锁档 `docs/release/034-VERSION-LOCK-20261028.md`（五面锚/镜像 digest/质量终值/冻结声明）；参数期望正典=`tools/gates-034.tsv`（8 门）。
> **集群**：<prod-host-01>（head，本机）+<prod-host-02/03/04>（worker，`ssh -o BatchMode=yes`）；网关=<gateway-host>（<gateway-ip>，Mac 独立宿主）；registry=<registry-host>:<registry-port>（宿主 02）。
> **铁律**（违者=无效操作）：①执行代理额外面 sudo=0；②容器/引擎启停仅授权窗内（slotlock wrapper 强制）；③判读窗禁切 `GW_SAMPLING_POLICY` 与 K16 两键；④量具冻结零改动零降门；⑤引擎面必须 `mode=v41 active=False`（`fork-v4-fp4 active=True`=退化面，立即停窗）；⑥战役仓 git 零提交（主会话统一提交打标）；⑦密钥零落盘；⑧偏差=停窗如实呈报不即兴。
> **产品化工具套件**（deploy/verify/doctor/config 四件，D119-② 授权新制面）：**已落盘**（2026-10-28 交付工作流产品化臂；md5 见 `docs/release/MANIFEST-034LOCK.tsv` 段二）。本手册 §一按其件头用法实写；后续如有修订以件头为正典并回改本手册。

---

## 一、快速上手：三命令

新套件=纯编排/校验层（包装既有正典原件调用：启停=`r3-boot-arm.sh`/`r3-stop`/slotlock；boot 核对面=`tools/capture-boot-evidence.sh`；量具=冻结驱动内置阈值）。三命令覆盖「体检→起栈→验栈」：

```bash
cd <repo-root>

# ① 体检（零写入零启停，任何时刻可跑；逐参数 PASS/FAIL+处置提示=自反馈自排查）
bash tools/doctor-034.sh --preflight     # 起栈前：五面锚+镜像+网关+量具锚 8 门全查
bash tools/doctor-034.sh --post-boot     # 起栈后：health/横幅/池指纹/引擎 mode=v41 面

# ② 一键部署（编排既有原件；先看清单再实跑）
bash tools/deploy-034.sh --dry-run       # 只列步骤与将执行的原始命令（S1 只读体检照跑，S2-S8 打印不执行）
bash tools/deploy-034.sh --arm-tag <窗名> # 实部署（doctor preflight→slotlock 持锁→boot :12 点火形→起栈→静置→post-boot）

# ③ 冒烟/全量验证（电池器，包装冻结量具，阈值内置）
bash tools/verify-034.sh --list          # 只列电池清单与冻结阈值，零触引擎零写
bash tools/verify-034.sh --smoke         # 快速面：EQ-S 同盐夹心+liter C1+DE c1+500q 冻结帧
bash tools/verify-034.sh --full          # 全电池：--smoke + sd_bench TTFT+B25×3+PPL golden
```

**判读门内置值**（FROZEN，D112-②b 沿承）：liter C1 ≥3700 ∧ DE c1 ≥91=快带；liter ≤3450=退化面（停窗）；带内 3450-3700=boundary（呈报）。500q 带 [0.956,0.982]/地板 0.955。（本手册 BL 系号=`tools/gates-034.tsv` 基线门行标识、CFG 系号=`tools/config-034.tsv` 参数行标识、**D 系号=内部决策台账编号（台账未入公开树，语义随文给出）**。）
**静置制（D113-①）**：health 首 200 + **300s** 后才起任何载荷；正典核对面（横幅 8/8）绿=起判读。（300s=工具序口径；手工序沉降 ≥600s，见 DEPLOY-STEP-BY-STEP §0/§7。）

### 手工等价（工具不可用时；=旧制式原步骤）

1. 点火：`ARM_TAG=<窗名> CTN_PREFIX=r3prod SPEC=1 ARM_ENV_FILE=<assets-root>/dsv41/env/CBX1A-CERTM-spec1.env bash tools/boot-with-slotlock.sh bash <assets-root>/bin/r3-boot-arm.sh`（boot :12 需先翻点火形，见 §六）。
2. 核对面：`bash tools/capture-boot-evidence.sh <输出目录>`（期望横幅 8/8、池指纹 full=9600000/MRR=16/ctx=600000/cps=4096、镜像 .Config.Image=x6bake、CUDA/Traceback=0）。
3. 引擎 KV 面：四机 `docker logs` 末态必含 `[kv_fp4] gate=1 mode=v41 active=False`；见 `mode=fork-v4-fp4 active=True` 即退化面停窗。

## 二、日常运维

### 2.1 停栈（正典件；D8 三查）

```bash
CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash <assets-root>/bin/r3-stop.sh
```
三查=容器计数（四机 r3ctn=0）+8899/8898 双探针应答 000。**生产栈必带前缀**（缺省=r3boot 测试线）。停栈后 boot :12 回置存储形（`50700486`，:12=r032c 占位）——点火形 `d41323dd` 仅窗内合法。

### 2.2 全检（例行体检）

```bash
bash tools/doctor-034.sh --preflight        # 停机态全门（等价逐门手跑见 tools/gates-034.tsv「核验命令」列）
bash tools/REBOOT-RECOVERY-baseline-verify-20261026-wb.sh   # 基线门现役版四机实跑
```
（注：`tools/REBOOT-RECOVERY-baseline-verify-20261026-wb.sh`、`tools/BASELINE-GATE-CURRENT.txt` 与 §2.3/§2.4 所引 `logs/` 树、census wrapper 两件均属**内部件，未随批入公开树**——公开树拷贝上这些步骤暂不可执行，待后续同步窗；`tools/doctor-034.sh` 与 `tools/gates-034.tsv` 已入公开树可跑。）
**对账正典**：固化态下 -wb 门 FAIL 集=恰授权面（01：BL09/BL11/BL12/BL15/BL16/GOV-3；02-04 同减 BL16）——**预期内 FAIL≠故障**；预期外 FAIL=停窗呈报（PINFIX §三对账表）。期望值逐门见 `tools/gates-034.tsv`。

### 2.3 日志面索引

| 面 | 路径 | 用途 |
|---|---|---|
| 窗证据根 | `logs/S-<窗名>-<日期>/`（phase0-pre/phase1-flip/phase2-boot/phase3-payloads/phase4-teardown/phase5-judgment 六段制） | 每靴全证据（判读值原始 JSON 都在 phase3） |
| misfire 台账 | `logs/misfire-class.tsv` | **每靴两行代录**（点火行+post-teardown 行；窗毕必写） |
| 基线门档 | `tools/BASELINE-GATE-CURRENT.txt`→`REBOOT-RECOVERY-baseline-verify-20261026-wb.sh` | 现役版指认 |
| 期望正典 | `tools/gates-034.tsv` | 8 门期望+核验命令+失败提示 |
| 锁档/回退 | 公开树：`docs/release/034-VERSION-LOCK-20261028.md`+`docs/release/MANIFEST-034LOCK.tsv`+`docs/runbook/ROLLBACK-PATHS-034.md`（原 034 束散件落位；033 束=回退件源属内部归档，未入公开树） | 身份链/锚全表/回退程序 |
| 决策台账 | 内部件 `DECISIONS-RESOLVED-20261024.md`（未入公开树；本手册 D 系号=该台账决策编号，语义随文给出） | 一切制式的法源（D 系号引用） |
| 网关 | <gateway-host> `docker logs concurrency-proxy-v2-mac`（grep "sampling="） | sampling-on 判读面前置确认 |

### 2.4 census/w1 量具调用制式（EQ-20 固化：PYTHONPATH=$SDB_DIR 补链+双 md5 钉前置断言）

> **法源**：035 任务书 EQ-20（源 KVSWA-六4）；wrapper 制式=批 0-3/M6（`tools/census_w1_pyfix_wrapper.sh`+`tools/census_w1_pyfix_usage.md`，**战役仓件未随批入公开树**）；census 窗模板=内部档 `NCCL-WINDOW-DESIGN-20261028.md` §四 censusPlan（未入公开树）。本节量具面（`logs/` 树与 wrapper）均内部件——公开树使用者 w1/census 量测暂不可执行，等待量具面公开窗。
> **因**：冻结量具 `logs/R1CERT3-20261004/w1_longctx_bench.py:19` 与 census 驱动 heredoc（`tools/census_capture_w3.sh:232`）均写死旧径 `<user-home>/<fleet-env-dir>/bench`（整树已灭失，sd_bench.py 现址已迁 `$SDB_DIR`）——**量具本体零改红线**下唯一合法补链=调用侧注入 `PYTHONPATH=$SDB_DIR`；漏注入即 `from sd_bench import …` 取不到模块**跑崩**（或错径**静默跑错**）。故 census/w1 调用前**强制**双 md5 钉前置断言，任一不中/缺参=**停呈报禁跑**（不现场改锚不降门）。

**调用前置断言（两调用面通用，缺一要素=无效调用）**：

```bash
SDB_DIR=<deploy-workspace>/tools/bench   # sd_bench 现址仓（缺位/件缺=拒）
md5sum <user-home>/<repo-root>/logs/R1CERT3-20261004/w1_longctx_bench.py \
  # 期望 941a853bfbbb7c3ab9b96f00efd91044（w1 量具本体锚）
md5sum $SDB_DIR/sd_bench.py \
  # 期望 410f543d4cc363defa66ffd54d190c9a（sd_bench 现址锚）
# 任一不中=量具形态漂移：停用调用并呈报，禁跑禁改锚
```

| 调用面 | 制式（PYTHONPATH=$SDB_DIR 补链已内置/必带） |
|---|---|
| ① w1 直跑 | `bash tools/census_w1_pyfix_wrapper.sh --base-url http://127.0.0.1:8899/v1 --sizes 32768 65536 --runs 4 --max-tokens 64`（wrapper 自带双 md5 自检：缺件/漂移=rc=2 拒跑，再注入 PYTHONPATH 后 exec 量具、参数原样透传；等价手工形=`PYTHONPATH=$SDB_DIR python3 logs/R1CERT3-20261004/w1_longctx_bench.py <原参数>`） |
| ② census 窗（W 形） | 照 `docs/plan/034-W1/NCCL-WINDOW-DESIGN-20261028.md` §四 censusPlan **逐字**执行：三 md5 预核（census_capture_w3.sh=6e073acd…+w1=941a853b…+sd_bench=410f543d…，任一不中=停呈报）后，调用 env **必带** `PYTHONPATH=$SDB_DIR`；rc 语义 41/44/45 全部如实记、禁现场降门 |

—— 0.3.4re 修复单元 EQ-20 增节（2026-10-30）／本节为插入节，其余章节与原署名原文未动。

## 三、故障排查矩阵（症状 → doctor/门行 → 处置）

| # | 症状 | 先查（doctor 行/门） | 处置 |
|---|---|---|---|
| 1 | **liter 骤降 ~15%（3330-3395 带）/TTFT ~140s/窗均功耗反升 40-43W** | 引擎 `mode` 行（doctor --post-boot 忠实度面） | **退化面**：`mode=fork-v4-fp4 active=True`=env 缺 v41 注入。查 BL11 三项（md5=ba4be586/59 键/v41 独立行=1）+tp4 :87+guards :161 三面（v41 三联）；修复=回 v41 三联（锁档 §六）；未explained=停窗呈报。**根因链**：flashinfer 0.7.2 include 缺件→JIT 永败→核外 repack 桥 |
| 2 | boot 起到 :52 die「挂载计数≠29」 | BL15（map 行数=29） | overlay-map.tsv 被改/缺行；对照 `md5sum -c overlay-md5.txt` 29/29；复原自 `.bak-pre-x6` 族+map `.bak-pre-a2` |
| 3 | boot-prod env 校验 die | BL16（profile=1be1c37c/清单=fd59c03b） | profile pin 行漂移：diff `.bak-pre-pinfix-20261028` 应恰 :8/:9/:18 三行差；超标=有人改件，停窗呈报 |
| 4 | health 长时不 200 | doctor --post-boot health 面；`logs/<窗>/phase2-boot/` | 看正典 `capture-boot-evidence.sh` 输出（横幅/池指纹/CUDA）；worker 起不来先查 02-04 overlay 远端在位预核段与 GPU 面 |
| 5 | 守卫水位告警/BREACH | guard watch（`tools/guard/watch-orchestration-fixed.sh` 档）；`memprofile-*.csv` | 01 会话构成性挤压（pswpout/cfail 高）非引擎面；eff_free<6.00GiB 线=真告警，按窗呈报 |
| 6 | census rc=41 | census G1 行（MemAvailable<8192MB） | **环境门拒非故障**：G1/A0H 不降门；01 内存腾挪 ~1.3GB 或低载窗择时重拍（W-a 当日 pre=8115MB 过门先例）；换机执行=不合法（脚本七处硬绑 01 docker）；w1/census 调用制式=§2.4（PYTHONPATH=$SDB_DIR 补链+双 md5 钉前置断言，EQ-20） |
| 7 | 网关非 sampling-on | GW-1（只读探测） | 判读窗禁切律：不现场切；处置走专门窗（先读 GW-RC387-POLICY-ON-REPORT-20261026.md） |
| 8 | 镜像 digest 失配 | IMG-1（80e4c957…f7d0；profile :21 同锚） | 镜像被覆写/重推=重大事件，停窗呈报；冻结 tag 族零覆盖红线 |
| 9 | guards 漂移/:161 非 v41 | GOV-3（418414c3） | 守护面被改；注意在役位=`<guards-kit-dir>/guard/guards.conf`（kit/deploy 下同名件=副本勿误钉） |
| 10 | slotlock 拒起（rc=2/3/4） | slotlock wrapper 出口码 | 2=锁被占（他窗在役）；3=四机容器非净（孤儿容器→`r3-stop` 清）；4=adapter 四机对表红 |
| 11 | 500q 读数 <0.958 | verify --full 500q 行 | 带内地板上=非门；连续靴低值再入调查线（0.3.4 观察位，锁档 §十-3） |
| 12 | PPL tf=1.0691/0.4511 | doctor --post-boot / PPL 面 | =fork 面签名（同 #1 退化面的确定性直证）；v41 面正典=1.1359/0.4212 |

## 四、架构图（五面/镜像/overlay/adapter/网关）

```
                       ┌────────────────────────── <gateway-host> (<gateway-ip>) ──────────────────────────┐
   客户端流量 ──────────▶  concurrency-proxy-v2 (rc3.8.7, GW_SAMPLING_POLICY=1 sampling-on 判读基线) │
                       └───────────────┬──────────────────────────────────────────────────────────┘
                                       │ 转发 (loopback :8899)
        ═══════════════ 五面（点火配置面，四机一致）═══════════════
        env CBX1A-CERTM-spec1.env (ba4be586·59键·尾行 v41)  ←ARM_ENV_FILE 整文件注入容器
        boot r3-boot-arm.sh (50700486 存储/:12点火翻 x6bake=d41323dd)  :411 DSV41_FP4KV_PORT=1 常设
        tp4 .env.tp4 (e225c391·:87 v41+split=1)   guards <guards-kit-dir>/guard/guards.conf (418414c3·:161 v41)
        profile prod-profile.env (01专属·1be1c37c·COUNT=29·镜像钉 :20-21)
                                       │ slotlock wrapper（P0 治理：锁下原子校验四机净）
   ┌───────────────────────────────────┴───────────────────────────────────┐
   │ <prod-host-01> (head·rank0)          <prod-host-02/03/04> (worker·rank1-3)     │  TP4·每机 1 容器
   │ 容器 r3prod-head                 容器 r3prod-worker                     │  host 网络
   │  API :8899(生产)/:8898(测试窗)   DIST :20000                            │
   │                                                                       │
   │  镜像 x6bake sha256:80e4c957…f7d0 (74层=r033d 73+1；registry @02)      │
   │  挂载(ro)：adapter 98件/d52b0e3d(.so 9eec98f8·kv_fp4.py 75062432)      │
   │           overlay 29件→/sgl-workspace/sglang/...（backend 73c80259    │
   │           +model 5b5ced03+mhc 982a0ad0+page_map c0dfe59a·按 map.tsv） │
   │  挂载(ro)：<models-dir>/DeepSeek-V4.1-Flash 权重+engram 分片(D56 流式) │
   │  挂载(rw)：autotune 表（唯一 rw）                                       │
   │  引擎正典态：[kv_fp4] mode=v41 active=False → backend 直调 flashinfer  │
   │             0.7.2 原生 V41 分支（不经 repack 桥=快带）                  │
   └───────────────────────────────────────────────────────────────────────┘
```

> **§四图口径注（2026-10-30 补）**：①图内「adapter 98件/`d52b0e3d`」为 2026-10-28 锁档（修复固化面、BYPASS 未入包）时点值；BYPASS 采用（D121）后 `prefill_bypass.py` 入包=**在役 99 件**（整树签名 `0beb4bee`，正典=[034-VERSION-LOCK](../release/034-VERSION-LOCK-20261028.md) §六-1 与 [README](../../README.md) §1 口径注）——两数同代不同时点，非矛盾。②图内网关「rc3.8.7」为 0.3.4 调优终态时点值；**0.3.4re 批后现役=rc3.8.8**（公开适配形 md5 `4f12f2d3`，含 DF-05 `INJECT_CONSERVATIVE_SAMPLING` 开关、默认关；开关关闭时与 rc3.8.7 行为零差异），见 [DEPLOY-STEP-BY-STEP](../DEPLOY-STEP-BY-STEP.md) §4.5。

## 五、回退 0.3.3 程序

**全文=内部档 `ROLLBACK-TO-033.md`（`archives/034-lock-20261028/` 束，未入公开树）**；公开树承载=[ROLLBACK-PATHS-034](ROLLBACK-PATHS-034.md)（路 A 程序正典摘要+§四-1 预演）。差异面七项逐面锚值+机侧 .bak 链+程序七步。要点：五面（env 58 键/tp4 c4f13f93/guards bb35df68/profile 5f223044/boot 20f22bc6）+overlay 28 行形（53cc9d61）+点火 tag 回 r033d 七面联动；adapter/网关/K16/engram 零回退；回退后 -wb 基线门四机 FAIL=0；**回退=用户明示运营动作**（另批执行）。

## 六、W-d 生产恢复步骤（固化面就绪；点火时序=用户裁量）

前置全绿（0.3.4 修复已固化=D118-③，静态放置满足 D113）。**适用面注记**：本节面向**内部已固化集群**——「env/tp4/guards/profile 四面零动作」以 v41 已固化在内部存储态为前提；**外部从零部署者四面须自行落位**（env=`deploy/env/CBX1A-CERTM-spec1.env` 61 键落位与自检=DEPLOY-STEP-BY-STEP §5；tp4/guards/profile 三面落位=DEPLOY §4.1 总表；目标形态速查=UPGRADE-0.3.4 §0）。

1. **时点呈批**：W-d 点火时点由用户定（ROOTFIX §5.1-5 移交项；本手册不设自动点火）。
2. **pre-flight**：`bash tools/doctor-034.sh --preflight` 全 PASS（或 §2.2 逐门手跑；网关 GW-1 行 sampling-on 确认）。
3. **boot 点火形**：boot `:12` 单行翻 `<registry-host>:<registry-port>/dsv41-sglang-optimized:0.3.4-x6bake-20261026`（翻后 md5 应=d41323ddac5743b54c00ad2ec3097d13；:465 -eq 29 不动）。**公开件 md5 锚注记**：`d41323dd` 只对内部基底（`20f22bc6`）成立；公开树基底（`9ac6e113`，快照头+掩码差）翻 `:12` 后 md5 **必不等于**该锚，属预期——公开件使用者以 `:12` 行内容（IMAGE=x6bake 全名）判读，勿拿 `d41323dd` 硬套自己的站点件。**env/tp4/guards/profile 四面零动作**（v41 已固化在存储态=W-d 免三联补执行的设计面；外部从零者见本节头「适用面注记」）。
4. **起栈**：§一手工等价第 1 步（slotlock wrapper+ARM_TAG 命名 `Wd-<日期>` 形）。
5. **静置+核对面**：health 首 200+300s→`tools/capture-boot-evidence.sh` 横幅 8/8 绿→引擎 `mode=v41 active=False` ×4 确认。
6. **post-boot**：`bash tools/doctor-034.sh --post-boot` 全绿后转生产流量（网关侧确认转发 :8899）。
7. **窗毕拆栈**（维护窗/演练窗形态）：r3-stop D8 三查→boot :12 回置存储形 50700486（复读 md5）→misfire 台账两行代录。
8. **长期生产态注记**：如转常驻不停机，boot :12 的回置项仅适用于窗制运维形；常驻期间以 doctor --post-boot 周期体检替代。

## 七、红线速查

sudo=0（链内 drop_caches 既有制式除外）｜启停仅授权窗（slotlock）｜判读窗禁切 GW_SAMPLING_POLICY/K16｜量具冻结（MANIFEST-034LOCK.tsv 段二 18 锚零改动零降门）｜engram 常驻硬盘流式（D56）｜git 零提交（主会话统一）｜密钥零落盘｜偏差=停窗呈报。

## 八、调优面与回退双路（0.3.4 调优终态；2026-10-29 D124 重定版增节）

> 本节由重定版封包窗增（D124-④；法源=WD-TUNED-FINAL-20261029.md+GUARD-DEGRADED-20261029.md）。
> **调优终态**=61 键产 env（`4370aab9`）+profile（`77d7fa67`）+engram cache=2.0GiB 活体面，引擎在役
> （ARM_TAG=WD-034TUNED-20261029-151019）。§二/§五/§六 中的旧锚值（ba4be586/f9fec92f 等）为各时点
> 历史层，**现值以 config-034.tsv（CFG-04/05/12/13/14/65）与 MANIFEST 追记三为准**。

### 8.1 调优面（相对 0.3.4 修复固化面 W-d 的恰 3 行差）

- **唯一采纳项=DEOPT-I8**：env 尾行第 61 键 `DSV41_ENGRAM_CACHE_GIB=2`（:64；1.0→2.0 单变量 A/B，
  四预注册门全过）+profile :8/:9 重钉两行。**args 类采纳项=零**（I4/I5/I6=REVERT、I7=SKIP，产面从未
  携带——profile :10 PROD_SPEC_EXTRA_ARGS 与 W-d 面逐字节同）。
- 增益面（W-e0→W-f 同日相邻靴对，ERA-DRIFT 制式）：DE c1 **+2.30%**（93.83 vs 91.37）/c2 **+4.66%**；
  liter C1 3910.3（快带偏上）；c16 −3.20% face 效应注记（贴 −3% 缘，61 键面子带 n=2 待第三样本）。
- 活体判读面：engram 横幅 8/8 应全为 `cache=2.0GiB (7893344 slots, 16-way, 8.2% of owned rows)`——
  对 1.0GiB 面（3946672/4.1%）恰翻倍；见 1.0GiB 形横幅≠故障，=路 B 回退后的 W-d 面形态。
- 回退锚（全链在位）：`.bak-pre-deopt-adopt-20261029` ×{env×4 机，profile，config-034.tsv，gates-034.tsv}。

### 8.2 回退双路（正典=docs/runbook/ROLLBACK-PATHS-034.md；回退=用户明示运营动作，本手册只载索引）

| 路 | 目标态 | 差量 | 承载 |
|---|---|---|---|
| **A** | 0.3.3 全回退 | 七面差+三面零回退（boot+overlay 必须同窗联动） | `ROLLBACK-TO-033.md` §一/§二（=本手册 §五）+ROLLBACK-PATHS §四-1 预演 |
| **B** | W-d 修复面（仅撤 I8 采纳，0.3.4 基面全保） | **恰 3 行差**（env ×4 机去尾行+profile :8/:9 回钉）+锚表 6 处值重钉（CFG-04/05/12/13/14 回 60 键值+**删 CFG-65 行**）+BL11 回四检/BL16 回 a15da805 | ROLLBACK-PATHS §二六步+§四-2 预演（全只读亲证在档） |

- **路 B 防坑（ROLLBACK-PATHS §二-3）**：锚表**仅值重钉、禁整件回拷 .bak**——.bak 是守卫降级窗前
  时点形，整拷会回滚 CFG-62..67 工具自锚致 doctor 假红。
- **路 B 步序**（获用户明示后）：预演 §四-2 全对 → env/profile 回置 → 锚表重钉 → doctor preflight
  0 FAIL 0 DEGRADED → 拆栈重点火（横幅应回 1.0GiB 形）→ verify --smoke 四绿 → 台账+报告。
- **映射律**：六降级面中**仅 DG4 可能导向路 B**；无一面以路 A 为首选（两版 KV 布局同 v41 快形、
  BYPASS=0.3.4 独有〔路 A 反丢此面〕、DG6=registry 自愈面）。

### 8.3 降级运行警告处置表（doctor DG1..DG6；任一命中=多行星号框大字警告+**退出码 2**；用户 2026-10-29 硬性要求落制）

| 登记 | 现象 | 影响定量 | 处置（按序） |
|---|---|---|---|
| **DG1** | `mode=fork-v4-fp4 active=True`（活体/配置） | 慢带 **−15~19%**（liter −15.7%/DE −7.5%） | 同 §三-1 退化面：v41 三联面（env :62/tp4 :87/guards :161）行级重钉+拆栈重点火；仍 fork=停窗呈报 |
| **DG2** | BYPASS 未武装（armed<8 或 refusing>0/env :63 缺/钩面失配） | 首键 TTFT 回 **74s 慢带**（97.3% 改善丢失） | D121 采用面行级重钉（env 键+sitecustomize 钩 dd69c59a，正典副本 tools/bypass/ 互证）；**路 A 反丢此面** |
| **DG3** | v41 键/三联面缺失 | 同 DG1 | 同 DG1；注入链断=CFG-48 行单独定位 |
| **DG4** | engram 横幅 <8 | engram 装载面异常 | 正典采集件 [5] 段分机定位（io_threads=96/packed=True 族）；**若确系 2GiB 面（I8）难闭合→路 B**+呈报；非 I8 面路 B 无效 |
| **DG5** | 池指纹漂移（full/mtt/mrr/ctx/cps 任一缺） | 912.25 不变式守护面（9600000/16/600000/4096） | CFG-49..53 行定位行级重钉；伴随 overlay 漂移时涉路 A #5/#6 联动面 |
| **DG6** | 镜像 digest/身份失配 | 载荷读数全部不可信 | `docker pull` 正典 tag 重拉复检（IMG-1/CFG-28）；registry 两版共存=自愈面；野栈占 8899=P0 禁双靴呈报 |
| （I8 面） | CFG-65 行 FAIL（=2 尾行缺失） | c1 +2.55%/c2 +4.86% 增益面失效 | **非降级面**（FAIL 行自反馈承载）：env 尾行回置（路 B 第 1 步同形）或维持 1.0GiB 呈报定夺 |

- doctor 退出码语义（GUARD-DEGRADED §1.2）：**0**=FAIL 0 且 DEGRADED 0｜1=有 FAIL 无降级｜**2=降级面命中**｜3=用法错/数据源缺失（降级与 FAIL 并存以 2 为准）。
- 自诊断入口：`bash tools/selftest-034.sh`（四段器：A 比较器单元/B 沙箱负例/C 完整性走查〔锁包 v2 追记三后 checked=108 fail=0〕/D 降级检测负例；重定版后实测 **exit 0**，2026-10-29T17:0xZ 亲跑在档）。

—— 定版封包员（重定版窗增节 §八）/ 2026-10-29 / D124-④；本节为插入节，其余章节与下行原署名原文未动。

—— 交付文档工程师 / 2026-10-28 / 配套：版本锁档束（公开树落位=`docs/release/034-VERSION-LOCK-20261028.md`+`docs/release/MANIFEST-034LOCK.tsv`+`docs/runbook/ROLLBACK-PATHS-034.md`；交付注记 `DELIVERY-NOTES-20261028.md` 为内部件，未入公开树）

## 附：git push 通道（02 工具链，2026-10-29 D123 勘定）

1. 通道事实：gh CLI 在 02（账号 luxingcom，token 活性）；**gh-proxy 已 401 失效勿再用**；02 可直连 github.com。
2. 标准推送序（01 侧零 gh 依赖）：
   - 01：`git push lan02 main delivery --tags`（remote=ssh://<prod-host-02><user-home>/.repos/<repo-root>.git，全史萸仓）
   - 02：`ssh <prod-host-02>` 后
     `cd ~/.repos/<repo-root>.git && T=$(gh auth token) && git -c http.version=HTTP/1.1 -c http.extraheader="AUTHORIZATION: Basic $(printf 'x-access-token:%s' "$T" | base64)" push https://x-access-token@github.com/luxingcom/<repo-root>.git delivery:main && unset T`
     （`http.version=HTTP/1.1` 必带：2026-10-30 起 02→github.com 走 HTTP/2 报 `GnuTLS recv error (-110)` TLS 非正常终止，1.1 破局；token 零打印零落盘，推送 rc 用输出重文件+`exit $rc` 取勿被管道吞）
   - 验证：`gh api repos/luxingcom/<repo-root>/branches/main --jq .commit.sha`
3. GitHub 面=交付快照支（delivery→main）；>100MB 历史 blob 三件（早期 census trace）已剔=GitHub 单文件限；全史在 02 萸仓。全史上 GitHub 需 filter-repo 重写（另批）。
4. 推送前清洁扫描制式：`git grep -IE '(sk-[A-Za-z0-9]{16,}|BEGIN (RSA |EC )?PRIVATE KEY)'` + 全历史 `git log --all -p | grep -cE …`（D123 扫描=树面 0/历史 0）。
