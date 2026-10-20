# CHANGELOG — LuZ 0.3.0 → 0.3.2（0.3.2 收官定版 2026-10-20）

> 提炼自战役仓 git log（`luz-0.3.0-r1`（2026-10-05，32c6acd）之后 632 commits）
> 与总卡/定稿报告。逐项档锚见 `docs/` 各分档。

## 0.3.2 收官（2026-10-20 定版；v0.3.2）

> 版本叙事+性能终态全表+硬守门+已知局限+回退面六件全档=**`docs/release/0.3.2-RELEASE-NOTE.md`**（release note 正典档）。

**版本叙事（摘要）**：0.3.2=以五目标制（PR 吞吐/DE 质量/C8 多并发定标/512k 长上下文/bug 全清）驱动的性能与质量双线版本：净线重建（网络链路重整）→死锁修复（最小修复集 `520d6d0`+位级保持形 r032c，对拍 7/7 三面全等）→五目标执行链（A6/R1/E16-B1/B2/CBX1A/C13 定标）→收官锁定。池 84 件全部三态处置（留役 10/关案 40/挂 0.3.3 34）。

**变更集（留役 10 件分件价值）**：

- **PR 面**：A6 修复形（indexk page64 遮蔽消除；DE 四型 +8.7~+9.6%/PR +1.0~+3.0%）+R1 转正形（FP4KV 内核 `r1_formal=1`；零形变直证 ±0.2%）——64k 峰档两级抬升至 **6289.3**（+2.3%）。
- **DE 面**：CBX1A cert M 八元（`DSV41_CERT_HEAD_M=6,12,18,24,30,36,42,48`；c4 +0.7% 正向/c1/c8 零漂）+B18 资格自证；DE-48 五档锚列全齐（c1 88.64 域/c2 128.89/c4 168.35/c8 242.83/c16 357.9 观察位）。
- **通信面**：E16-B1 包络双键 1179648+B2 compact gather（RoCE gather 消息包络承载）。
- **服务面**：A8 `--tool-call-parser deepseekv41`+A9 `--enable-cache-report` 接线在役（issue #1/#2 修复）+A10②-a 网关容量四键（issue #3）；SPEC6 九参谱（含 `--sleep-on-idle`）。
- **工程面**：D12 沉降键面+D15 五门断言族在役；量具正典族（DE-48/pr_ladder7/gid-face-gate）。
- **bug 账**：21 件=已闭 13+部分闭 5+挂 0.3.3/呈裁 3（全件有处置记录）。

**性能终态（对外主口径；基线=本版本判读线列〔MS1017/A6-ANCHOR-7〕）**：sparkdash 七档 8k→512k=5522.5/6040.2/6271.3/**6289.3**/6048.1/5427.9/4290.0（64k 峰档=判读线基线 6147.3 之上 +2.3%）；DE 五档锚（mt400 正典口径）c1 **88.64 域**/c2 **128.89**/c4 **168.35**/c8 **242.83**/c16 357.9（观察位），per 流比 1.0/0.766/0.488/0.356/0.270；C8 聚合锚 C1 3757.7/C2 2849.8/C4 1571.0（C4/C1=0.418）+A/B 轨定标提案采纳。全表与 512k 斜率读数见 RELEASE-NOTE。

**硬守门零回归声明**：EQ-1 位等跨靴 6/6 逐字｜GSM8K 0.985-0.99（≥0.97）｜needle 600k 3/3｜池红线组（pool 9.6M/chunked 4096/MRR 16/ctx 600000）boot 断言在役｜PR 七档 vs 锚全 IN-BAND｜质量门全绿零回归——0.3.2 终态形（boot `r3-boot-arm.sh` 20f22bc6/adapter b58e49ff/env CBX1A 0729e18d/IMAGE r032c digest `sha256:47f6d91a…ffc4`）为「现役形即终态形」零拆靴零复靴转正。

**已知局限与 0.3.3 待启面**：512k 斜率未达（峰→256k −12.31%/峰→512k −28.65%；A 轨 ≤−6.5% 兑底 0.3.3，治理链挂 0.3.3 头）；c16 收益主张=观察带非成立带（量具弱点注记：mt400 prose c16 均批<16，满批形收益面未覆盖）；band-3 栈级不可观测（census profiler-eager stock 回退，替代证据链在档）；DE B 轨 90 未达（缺口 ~1.4）；0.3.3 待启=全闪 decode 迁移调研线落地+树形适配+池挂 34 件。

**回退面**：镜像双存（r032c 在库+r032 基线；boot IMAGE 单行回指一键复原，1 靴 ≈1.5-2h）；adapter 逐件回拷链（A6 beb131ab→55b1e412／R1 75062432→feaaadd4）；env 回退链 CBX1A→E16B2→FB54→WG53；已执行回退件（B20/E11/B24/B25/L2OFF）零残留横幅自证。

## 0.3.2 死锁修复（2026-10-18 修复体验证毕 → 10-20 r032c 位级保持形终态转正在役）

> 43h 长稳调度死锁（2026-10-16 站点甲；四机同点 `v41_indexer/scoring.py:164` 宿主同步
> 等待，集合通信从未发起）修复线。最小修复集=上游 `520d6d0`（#41659，含 fc2795b）回移植：
> prefill/decode 索引器数据构造改整批 host-lengths 构形+async_h2d，消除步级隐含宿主同步。

1. **修复镜像（终态=r032c 位级保持形，产线转正在役）**：`dsv41-sglang-optimized:0.3.2-r032c`
   （内网 registry；digest `sha256:47f6d91a…ffc4`；=最小修复集 `520d6d0`+候选序**位级保持形**，
   位级对拍 7/7 三面全等〔logits/hidden/输出 token〕；上靴验收 code 型 128.91=−0.3% 带中——
   收回 r032b −6.8% 出带+死锁面零复发；2026-10-20 随 0.3.2 终态转正在役，boot IMAGE 指针=r032c）。
   前形 r032b（digest `sha256:1e2ca8e3…99ec4`；16 件 +1359/−313=r032 15 件+`candidate_block.py`
   闭包补件；adapter 同批原子切换律——9 件按 XCHECK §4 迁移，W0 形散失后重建版五面验证在档
   `logs/S-FIX-W0B-20261018/adapter-rebuild/`）在库保留=回退面。
2. **验收读数（S-FIX-W0B-20261018 窗实测，A 侧基准=MS1017 在役列）**：修复验证面全绿
   ——G1 单元 122 passed/0 failed；G5 直证步级隐含宿主同步 20→0（py-spy 996 样本 0 帧）；
   warm 门 6271.0（+1.4% 带内）；四查 15/15；needle 3/3；GSM8K 98.0%（196/200，err=0，
   与 MS1017 同值）；PR 六档全带内；DE c1 四型 prose 79.48/structured 145.3/json 124.74
   均带内（−1.1%/−0.9%/−0.6%）；44 项 RoCE parity A/B 双面 44/44+对拍零差。**但 code 型
   DE 120.45（−6.8%）出带**——复 A 靴归因（1017 现役形复读 128.44=−0.7% 带中，
   accept_len 佐证 5.33 vs 5.58/5.65）=**修复面回归非环境漂移**（与 XCHECK §5 风险
   「write_selection 去排序=输出级等价非位级」同向）⇒ **产线留 1017 现役形，r032b
   在库零部署**；死锁修复本体判绿，code 型性能回归呈裁（候选方向=候选序位级保持形
   回移植）。A0 第 1 采无升级触发（prose −1.1%，分型 accept 全 ≥2.8 门槛）。
   （历史读数引注不改；code 型出带的终局解=上位 r032c 位级保持形〔条目 1〕，
   「产线留 1017 形」为 r032b 窗时点态，已由 r032c 终态转正承接。）
3. **站点规避+取证包随包**：`docs/deploy/DEADLOCK-MITIGATION-AND-FORENSICS-20261018.md`
   ——修复到位前「复现即重启」口径+升级前窗口建议+py-spy dump/record/top 三件套用法
   （`scoring.py:164` vs `ncclCommInit*` 判别）+`/proc/<pid>/task/*/stack` 与环网
   ethtool 差分（区分链路停滞 vs 从未开工）+NCCL INFO 低开销窗指引。

## 0.3.2 前置线（2026-10-15/16）：net-rebuild 修复 + 交换机方案适配

> 本节=0.3.2 在途增量（net-rebuild 战役收口批）。交换机方案与环网方案的差异件
> 另见 **`switch-fabric` 分支**（差异档 `deploy/SWITCH-FABRIC.md`+RoCE
> flat/one-shot 运行时+交换机形态 env 样本）；`main` 保持环网方案形态。

### 问题修复

1. **issue #1 — tool call 不成型**：DSML `tool_calls` 无解析根因=serving
   `tool_call_parser` 缺省未接线。修复=serve 参 `--tool-call-parser deepseekv41`
   （连写正字法；`deepseek-v41` 系 reasoning parser 写法不通用）；SPEC6-SERVE-REF
   补第 7 行。
2. **issue #2 — usage 缓存字段恒 null**：`enable_cache_report` 缺省 False。
   修复=serve 参 `--enable-cache-report`（`prompt_tokens_details.cached_tokens`
   随响应返回）；SPEC6-SERVE-REF 补第 8 行。
3. **issue #3 — /v1/models 无容量字段**：客户端默认窗 262144 低估引擎真值。
   修复=网关 rc3.8.6 容量四键（`ADVERTISE_MODEL_CAPACITY` 单键，缺省 0=逐字节
   零行为差；=1 时 `/v1/models(/id)` 补客户端模型发现四键=`max_model_len`；
   三硬门=纯增量/幂等/fail-open）+测试台 `test_rc386.py` 14/14。
4. **网关鉴权窗（rc3.8.5）**：`GW_REQUIRE_AUTH` 全局鉴权门（缺省休眠）+`GW_ALLOWED_MODELS`
   模型名白名单（假名 404 OpenAI 形）；测试台内容寻址坑修（原基准取 `git show HEAD:`
   在提交后退化为自比恒绿假凭据→按内容 md5 检索 blob）。
5. **管理段重编址同步**：registry/角色址 192.168.5.186-189 → 192.168.0.201-204
   （`r3-boot-arm.sh`/`r3-boot.sh`/`r3-watchdog.sh`/README/DEPLOY-GUIDE 五件；
   语义参数零动）。
6. **致谢面**：ACKNOWLEDGEMENTS 增 B-4（issue #1/#2/#3 报告者；110→111 条）。
7. **网络重建后部署面同步**：Mac 部署节更新（01 面网关载荷吸收 rc3.8.6；隧道形=
   systemd 托管 `ssh -N -R` 新址形；02 侧 upstream 旧址 drop-in 修复；P6 隧道旁路
   验收）——`sources.tsv`/README/MAC_DEPLOY 行重钉。

### 开发新增

1. **SPEC6 参谱八参→九参**：增 `--sleep-on-idle`（SGLang 空闲调度省电；实测空闲
   调度核占用 ≈1 核→≈0.05 核/机，−87.6~−91.6%；归一指纹 9d64a5de，旧八参
   6b12a445 保留不覆写）。
2. **交换机方案适配（`switch-fabric` 分支）**：双 rail 交换机拓扑下以 flat/one-shot
   运行时复活 RoCE all-reduce（`LUZ_SWITCH_ROCE_FLAT` 选门+C 层
   `B12X_ROCE_TOPOLOGY=switched`/`B12X_ROCE_TRAFFIC_CLASS=106`）；实测 decode DE
   四型自 NCCL 回落态收敛 −13.7%→−3.8%，经 `DSV41_ROCE_GATHER=524288` 恢复
   adapter 侧 gather 限幅再 +5.8~+6.2%（超额回收）；44 项 rank/shape parity 全过。
3. **基准线工具链（已在 fb5798c 批入仓）**：`tools/bench/`（sparkDash 口径量具
   复刻四件）+`docs/registry/BENCHMARK-SOURCE.md` 口径正典——净线基准读数谱系可溯。

## 0.3.1 发布分发（2026-10-14）

1. **网盘发布**：夸克网盘 `luz-0.3.1-release-bundle-20261014.7z`
   （<https://pan.quark.cn/s/42e685a8a10e>，提取码 `24zL`）=0.3.1-r3 交付镜像
   tar 14.4G（sha256 `6afa4429…`）+交付仓快照 tar.gz ~90M（sha256
   `6a7b6b99…`，.git@cbc9a6b）+CHECKSUMS.manifest+README-DIST.md。
2. **GitHub Release v0.3.1** 建：发布说明+渠道汇总（网盘/registry/本仓三层）；
   大文件不走 Release 资产。仓库 HEAD=8be69ca（含 G2-RESTORE 收官增量，快照
   之后增量以本仓为权威）。
3. **交付镜像现值=0.3.1-r3**（TOOLS31-BAKE-R3-20261014：G1'' 冷构建双跑 PASS
   cid=`ffed489217c872ea`，sha256 `f8095fa8…415c1`；gateway rc3.8.3 修复面+
   cfgmgmt c4fb0c3e 整面；r2=回退位保留）。dsv41-sglang-optimized 谱系未推
   registry——离线分发恒走网盘包。
4. **过时件清理（GOV-CLEANUP2，2026-10-14）**：dist 包 DEPRECATED 件出库——
   `images/dsv41-sglang-optimized-0.3.1.tar`（首烤版 14G）+`images/vl-vllm-S1.tar`
   （vLLM VL 旧承载 12G）+repo/ 三件 DEPRECATED tgz 及伴 .sha256 共 9 件
   ≈25.7GiB；CHECKSUMS.manifest 重组为现行三行（r3+r2 回退+repo 现行）。
   README §二「历史/备份 vLLM 两形」段同步改清理注记（docker save 分卷
   建议句删除）。四机镜像清理（03/04 anemll+luz031-backup 互锁组、01/02
   dev-dsv41 双机血统件）对账见战役仓 `docs/ops/GOV-CLEANUP2-RESULT-20261014.md`。

## 0.3.1（2026-10-13 定型，tag v0.3.1）

1. **0.3.1 开线**：0.3.0-R1 检查点封存（36 键 b7e318e0/91adc83d 七件/池 9.6M
   横幅合同）→ LUZ-031-DEV-PLAN 立线（多模型扩展+M2 闭合+QA 基建）。
2. **LL128 三键采纳**：NCCL_BUFFSIZE 1MiB + LL128_BUFFSIZE 262144 +
   PROTO ^LL128（LL128-ADOPT 窗，45 键形；LL128 中性确认带内）。
3. **O12 主机间隙调度三键产线化**：SCHED_ASYNC=1 + RECV_INTERVAL=4 + 配套件
   scheduler 5b6fe2a3（47 键形 01:34Z 绿起；HOSTGAP 86.9ms 归因定谳法源）。
4. **R1 FP4-KV in-kernel 八件转正**：kv_fp4.py feaaadd4 + fi_r1/ 六件 +
   装载缝挂点（48 键 8c8c166d；面 4b40a123 四机全等；fail-safe 双跑
   t_r1_equiv 49 GREEN；FULLGATE/REWORK2/PROMO2 三窗直证）。
5. **E3-A SWA 召回 N=256 + L2PF6**：`--swa-prefix-tails` 64→256 转正在役
   （SPEC6 六参定谱=五参基座+swa256）；L2 prefetch 6MB 单键域。
6. **W5 stage2 MXFP8+出口直聚两键单独转正**：DSV41_PREFILL_SP_FP8=1 +
   TAIL_GATHER=1（50 键定型形 15767aa6；W5 件 prefill_sp.py 32cf9abf
   2026-10-13 00:02:23Z 换入产线；MXFP8 byte AG ON 三重对拍）。
7. **T1 组合窗裁定**：chunk8192 判负不进形（16384 永禁维持）；TPsplit D1-block
   留库不转正（6498aa39 在库）；组合账 C0 步墙 648.6 对 866 基线 −25.1%。
8. **质量链收口**：CODE31 交叉审查 P0=0/P1=3（镜像件零分叉：23 件 cmp 逐字节
   等上游 main-79cafec0）；白盒矩阵 13 绿/1 注记红回填；QA31 定型窗四靴全
   电池——步墙 626.1 服务口径（866→626，−27.8%）、128k PR 5880、GSM8K 0.97、
   needle 3/3、断言门禁 10/10 逐靴直证。
9. **FL6 召回修复（呈裁在飞）**：QA31 cp30 召回 0/3 红位 → 根因定谳（SWA
   interior 未退休+match retract 缺位，swa_evictable −64.1% 机理直证）→
   fl6_recall.py b87cbb5e + 第 51 键门控验证窗=部分绿呈裁位（cp30 未复现；
   严格冻结双门 2/3）→ 产线复原 50 键原形（sitecustomize 2c4baad3）；
   ENV51 转正即用形在库（本仓 deploy/env/ 收录）。
10. **运维工具五包 T4 就绪**：fabric-net / selfdiag / selfheal / gateway /
    cfgmgmt + _lib（每包五件套+MANIFEST 指纹+selfcheck 三态退出码；
    TOOLS31-PACKAGES-RESULT 档；GIT 锚=各自整备提交）。

## 0.3.1 后继增量（VL-NATIVE-20261013 窗全绿收录，随仓不入 tag）

- **VL 面双臂全绿**：SGLang 基座原生视觉 V4.1 臂（零旗零文件；G-V1 knapcio
  1024/1024 SAT 断言全对）+V4.0exp overlay 复原臂（28 件 cbf986df×4 同基座
  首飞，G-V5 预算内动态计费全绿）+网关 VL 车道（8002→8898）在档；VL 形
  转正在役=呈裁位（`docs/research/VL-NATIVE-RESULT-20261013.md`）。
- **镜像面收束**：vLLM 两形移历史/备份注记（单基座交付律=主表只留 SGLang
  基座+烘焙镜像）。

> **DEPRECATED 产物处置建议（注记不执行——清理窗承载）**：宿主
> `~/luz-0.3.1-dist/`（约 26G：S9 打包产物 images/+repo/+CHECKSUMS.manifest，
> 已标 `DEPRECATED-20261013.md`）=S9 整体暂缓裁定后的废弃产物。建议清理窗
> 处置序：①确认烘焙镜像 0.3.1（cid 658a5fe…）四机在位+registry 副本可再拉
> ②如需离线分发保底先 `docker save` 分卷重制 ③rm 整目录前 `du`/`ls` 快照
> 留档。处置执行=主会话清理窗，本注记只入档不动作。

## 0.3.1 发布后组件同步批（2026-10-14，GitHub 完整性核实）

1. **网关包 rc3.8.3→rc3.8.4**（G2-RESTORE S5 验证窗 V2b 413 透传修复；战役仓同批
   f8322934/本仓实算 a9c17506）——包内=在役同形（rc3.8.4 f0a47b17 V1-V5 全绿）；
   镜像 0.3.1-r3 烘焙时点=rc3.8.3，差面下一烘焙窗吸收（README-DIST 已注）。
2. **守卫/自愈面收官态入仓**：oom_gate.sh ada688d4（T8 D1 三键加固）+r3-watchdog
   156a1a7c（01/02 在役形，systemd ExecStart 亲证；包副本回填双哨律注记=逻辑零改动）
   +guards.conf 产线现值（网关锚随 rc3.8.4 吸收重钉）+kit BASELINE 同步。
3. **fabric-net 收官态**：fabric-guard.sh+weave/topology.json+VERSION t4.2。
4. **五包 VERSION 指纹全量重钉**（脱敏仓实算；修 SANITIZATION 掩码批后 VERSION
   陈值潜伏漂移+selfdiag F4 锚重钉 f2f10cb6+cfgmgmt regen 源路径 ${HOME} 化——
   五包 selfcheck RED=0 复跑全绿）。
