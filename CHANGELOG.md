# CHANGELOG — LuZ 0.3.0 → 0.3.4（0.3.4 调优终态 2026-10-29 定版）

> 提炼自战役仓 git log（`luz-0.3.0-r1`（2026-10-05，32c6acd）之后 632 commits）
> 与总卡/定稿报告。逐项档锚见 `docs/` 各分档。

## 2026-10-31 备查同步批（0.3.4re：overlay 29 件本体 + 三件正典全文入公开树）

> 闭合 0.3.4re 已知布局缺口「overlay 29 件本体未随批入公开树」。零引擎触碰、零
> 工具触碰；逐件身份/血统/旧形取回总表=`deploy/README-说明.md`（本批新增）。

- **overlay 29 件本体入仓**：`deploy/overlay/o12c1-prod/` 整面同步为 0.3.4 现役形
  （目录 30 件=29 个 `.py`+`overlay-map.tsv`；相对旧树 5 件换血+1 件新增：
  backend `736fbde5`→`73c80259`、model `fb87a7f0`→`5b5ced03`、mhc `bd473946`→
  `982a0ad0`、serving_chat `c506bab5`→`9b60a463`、scheduler `3db3275e`→
  `4a7822a6`、新增 `page_map_export.py` `c0dfe59a`；旧值换血表留档 README-说明
  §二，旧文件本体可从本批之前的 git 历史取回）。
- **对表清单重钉**：`deploy/prod/overlay-md5.txt` 自 034-lock 时点形（自身
  `fd59c03b…`，scheduler=`3db3275e`）重钉为现役权威形（自身 `6c98cf8c…`，
  scheduler=`4a7822a6`，与私有侧权威清单逐字节同）；公开树内 `md5sum -c` 实测
  29/29 全绿。
- **三件正典全文备查**：`deploy/reconstruct/0.3.4/overlay/` 新增
  backend/serving_chat/page_map_export 三件+NOTES.md+MANIFEST.md5（补「只有锚值
  没有本体」缺口）。
- **文档面**：新增 `deploy/README-说明.md` 备查区对照总表（两区结构+四清单交叉
  说明+旧形取回口径+红线）；README 断点声明、UPGRADE-0.3.4 §0 缺口注记改写为
  「已闭合」并补两区入口链接；0.3.4-RELEASE-NOTE §表、0.3.4re-RELEASE-NOTE
  §三.5、RUNTIME-PARAMETERS §表+§5.4 回退节代际注记、DEPLOY-GUIDE §5 表、GETTING-STARTED §1.3、
  deploy/README.md 同步换值/补入口；锁档档案（034-VERSION-LOCK/MANIFEST-034LOCK/
  gates-034/config-034/runbook-034）一律不改值（时点快照口径）。

## 2026-10-30 发布面文档修订批（可读性+完整性评审意见落实）

> 来源：0.3.4re 发布面两份评审意见（可读性 13 条+完整性 10 条）。本批纯文档+登记面
> 修订（零 git 写/零引擎触碰/零量具触碰），逐条落实如下；被修订件的**最新 md5 以本节
> 为准**（下文移植批所登为该批时点值，与本节并存对照）。

- **主链断点声明（③最重）**：README 分流表下与网盘包 README-DIST §二-4 各增「当前
  断点声明」——runbook-034 面向内部已固化集群（`d41323dd` 点火锚仅对内部基底
  `20f22bc6` 成立，公开件基底 `9ac6e113` 翻后必不中属预期）；已可用 0.3.4re 增量
  =DEPLOY §5/§6.6/§4.5 三处；overlay 29 件本体缺口给过渡路径（禁 0.3.2 overlay
  拼 0.3.4 栈，等待整面同步窗）。
- **镜像分流（①）**：DEPLOY §2.1 头加分流框（现役 0.3.4re 形镜像=x6bake/80e4c957/
  74 层、取处网盘包 images/；本章拉取命令面向 0.3.2 历史形）；§6.4 补 IMAGE= 该填
  x6bake 全名。
- **引擎绑定两形态统一（①用户红线级，五处联动）**：裁决口径=公开 boot 件缺省
  `--host 0.0.0.0`（四机可达）+参考产线形由站点收敛为 head 回环（探活须 ssh head 打
  回环）——GETTING-STARTED §3/要点/Q1、DEPLOY §4.5/§8.1-①/§9 表、GLOSSARY「网关与
  车道」、KNOWN-ISSUES §2 首行五处同步改写，探活口径两种形态分别给出。
- **网关 UPSTREAM 误读（①）**：DEPLOY §4.5 验收第 2 条改 `UPSTREAM=http://<mac-gw-ip>:<tunnel-port>`
  （隧道终点=head 回环；网关容器内 127.0.0.1=Mac 自身直写必断链）；8898 措辞改
  「引擎测试口（量具专用），网关上游不得指向它」（与 GETTING-STARTED Q10 对齐）。
- **网关版本两说（①/②）**：DEPLOY §4.5 与 runbook §四图后注统一为「0.3.4re 批后
  现役=rc3.8.8（公开适配形 md5 `4f12f2d3`，含 DF-05 开关默认关）；rc3.8.7
  （`be9b0aba`）为调优终态时点值」。
- **沉降时长口径（②）**：DEPLOY §0 纪律 2 与 §7 第 5 步、GLOSSARY「沉降」词条、
  runbook §一统一注：工具序（deploy-034 S5/D113-①）=300s；手工序=≥600s；1800s
  旧制已废。
- **五面配置三件无解释（②）**：DEPLOY §4.1 落位总表补 `.env.tp4`/`guards.conf`/
  `prod-profile.env` 三行（源→落位→角色→何时必须改）。
- **adapter 件数两说（②）**：裁定=98 件（2026-10-28 锁档修复固化面，runbook §四
  历史时点值）→ BYPASS 采用后 99 件在役（`0beb4bee`，正典=034-VERSION-LOCK §六-1）；
  README §1 图后、GLOSSARY「adapter」、runbook §四图后三处口径注。
- **README §3.1 表前「读表先识字」图例（④）**：liter C1/DE c1/500q 冻结帧/EQ-S 同盐
  夹心/PPL golden A/A/T33-03 正典锚/W-d·W-f/IN-BAND/sparkDash=repeated 九词一句话
  释义；README 卷首「一句话」拆为三句（做什么/拿到什么/从哪入门）。
- **内部编号首现括注（②）**：README 键数注（BL/CFG=gates/config 两 tsv 行标识；D 系号
  =内部决策台账编号未入公开树）、DEPLOY §0 纪律 2（D 系号）、runbook §一（BL/CFG/D
  三系号）、RUNTIME-PARAMETERS 键面演进链（D121）、0.3.4re-RELEASE-NOTE §二（CFG）。
- **学习路径图断链（③）**：GETTING-STARTED §4 增「我要部署现役 0.3.4re 形」行
  （runbook+UPGRADE 骨架注+DEPLOY §5/§6.6）；交换机形行注 0.3.4re 增量并入位置。
- **端口口径（①/④）**：GETTING-STARTED §3 网关车道口改「8001（8002 视觉车道已撤除
  留回退线）」；RUNTIME-PARAMETERS 占位符表拆行（<PORT>→8899/<GW_PORT>→8001/补
  <TEST_PORT>→8898）。
- **overlay 双计数（④）**：DEPLOY §4.3 注明 29 目录项（28 活件+map）/ov_n 门 28/
  map 行数门 29（BL15）与 §8.1 横幅「29 gates」（守卫门数）三个数的区别。
- **runbook 悬空引用改写（①）**：§五 `ROLLBACK-TO-033.md` 与 §落款 `DELIVERY-NOTES`
  改为「内部件未入公开树+公开树承载=ROLLBACK-PATHS-034/034-VERSION-LOCK」；§2.2/§2.3
  注明 `REBOOT-RECOVERY-*`/`BASELINE-GATE-CURRENT`/`logs/` 树/census wrapper 未入
  公开树；§六补外部从零者四面落位指引。
- **脱敏收口（②）**：`deploy/env/.env.tp4` 头注内部代号占位符化（原内部 recipe 代号
  →`<recipe-id>`；`ecd387f0`→`2a0d0d3d`）；`deploy/prod/prod-selfcheck.service` 与
  `install-prod-guard.sh` 用户名实值按网盘包先例掩码（→`liux***ya`，本仓与包内快掩码
  形一致；`prod-selfcheck.service`→`e7b51a7c`、`install-prod-guard.sh`→
  `c40b2a1e`）。主机名/内部路径历史存量面**不随本批清理**（涉证据件完整性），改在
  KNOWN-ISSUES §7 与 deploy/README「内网值说明」（更新为如实口径：IP 已清零/主机名
  存量保留清单）+ README-DIST §三（存量披露+快照时点注）登记。
- **其他登记**：KNOWN-ISSUES §7 补 EQ-13（selfdiag 未入公开树）与 `.bak` 备份件两行；
  0.3.4re-RELEASE-NOTE §三-5 补 overlay 过渡路径指引；UPGRADE-0.3.4 §0 补公开拷贝
  md5 注记与 overlay 过渡路径二选一。
- **本批后实落 md5（对表用）**：README.md `e4d2f880` · UPGRADE-0.3.4.md `9c69ae75` ·
  runbook-034.md `ae980320` · .env.tp4 `2a0d0d3d` · DEPLOY-STEP-BY-STEP `4ca777e1` ·
  GETTING-STARTED `84c810e4` · GLOSSARY-PUBLIC `caed0da8` · RUNTIME-PARAMETERS
  `7b17310f` · KNOWN-ISSUES `ed7d31ce` · 0.3.4re-RELEASE-NOTE `19ba9ee5` ·
  deploy/README `1adb7fbd`。（0.3.4-RELEASE-NOTE 本批未触，仍 `664e0fe7`。）
  网盘包面：README-DIST 同步修订（断点声明+脱敏声明如实化），CHECKSUMS.manifest
  该行已刷新（sha256 `0f47c8e9…`/7617 B）；repo/ 快照保持打包时点、以 GitHub 为准。

## 2026-10-30 0.3.4re 缺陷修复批（17 个 DF/EQ 单元 + 上游并入 + 新量具 contract_probe）

> 来源：战役仓任务书 `luz030-opt-campaign/docs/plan/035-W0-TASKBOOK-20261030.md`
> DF/EQ 章圈定的 17 个修复单元（DF-01~06/12 + EQ-02~05/09/11/12/13/19/20），由
> `0.3.4re-修复与发布准备` 工作流并行执行后随本批收口；单元逐条的背景/证据锚/验收门
> 均以任务书对应节为法源。键数口径沿上节移植批同律：一律按 gates-034 BL11 判据
> **「61 键」**（0.3.4 调优终态产 env；0.3.2 历史 CBX1A 形为 56 键，两数并存期文档
> 各标各代，不混用）。

### 修复清单（17 单元逐条：单元号 / 一句话 / 文件面）

1. **DF-01** 内部产线面同缺陷同步——公开仓 0.3.2-p1 的 env 注入尾行守护与
   sentinel/doctor 修复同步到内部产线副本；文件面=内部 `~/migrate-assets/bin/r3-boot-arm.sh`
   （env 注入 read 循环加尾行守护，与 EQ-02 断言同批落）+ 战役仓
   `tools/packages/fabric-net/payload/guards/fabric-sentinel.sh`（loads 双形解析+awk
   浮点比较+SENTINEL_* 全参数化，与公开树逐字节同 md5 `04e535e4`）、
   `…/payload/diag/fabric-doctor.sh`（`--json` 失锚显式 `exit 2`）、
   `dev/lutune/fabric-sentinel.sh`（同构同步）；`migrate-assets/bin/r3-boot.sh`
   实查无 env 注入 while-read 循环（无该缺陷面）、`dev/lutune/` 下无 fabric-doctor
   件——两处如实记跳过。
2. **DF-02** 守卫族车队绑定残留参数化——fabric-restore-gate.sh 的执行主机判定/四机
   HOSTS/SSH 用户与 boot_sentinel.sh 的家目录默认全部改显式环境参数、缺参拒跑打印
   缺什么（替代静默 `exit 0`）；文件面=战役仓 `dev/lutune/fabric-restore-gate.sh`、
   `tools/packages/fabric-net/payload/guards/fabric-restore-gate.sh`、
   `tools/boot_sentinel.sh` 与 `tools/packages/fabric-net/README.md`（外部采用者
   必读段补站点适配清单）；公开面 `tools/boot_sentinel.sh`（公开布局改写形
   `f00e5dca`）。**残留**：公开树 `tools/packages/fabric-net/payload/guards/fabric-restore-gate.sh`
   （`f41564ce`）未随批同步战役仓新形（`ae014c91`），待下个 fabric-net 整面同步窗。
3. **DF-03** 停栈脚本内建硬断言——r3-stop.sh 收尾断言「四机目标前缀容器数=0 且 head
   端口 /health 返回 000（连接失败形）」，任一不满足即 `exit 1` 并明示禁止进入
   沉降/点火（removed 自报行不再作为成功依据，对齐 UPGRADE-0.3.2.md §15）；文件面=
   `deploy/bin/r3-stop.sh`（留档 `.bak-pre-df03-20261030`）+ 内部
   `~/migrate-assets/bin/r3-stop.sh`。
4. **DF-04** sd_bench PR 模式实现 `--runs`——PR 模式不再静默吞参：`runs=1` 缺省=
   旧单发行（schema 逐字节旧兼容），`runs=N>1`=每档 N 次独立调用、每发 fresh salt
   防跨发前缀缓存，产物 JSON 输出逐发记录（shots）+判读器断言 shots 数=runs；文件面=
   `tools/bench/sd_bench.py`（战役仓无该件，按单元预案只改公开面）。
5. **DF-05** 网关 thinking 双键同步+保守采样缺省档（默认关）——先把 0.3.2-p1 的
   thinking 双键注入同步到战役仓副本，再新增 `INJECT_CONSERVATIVE_SAMPLING`（缺省 0=
   关）开启时对 POST chat body 缺省注入 temperature/top_p/frequency_penalty 三键
   （`CONSERVATIVE_*` 三 env 可调，建议带 0.6/0.95/0.4），客户端显式传任一键则完全
   不动 body，开关状态入代理横幅与 METRICS 双计数可审计；文件面=公开+战役仓
   `tools/packages/gateway/payload/concurrency_proxy_v2.py`（双面逐字节同 md5
   `4f12f2d3`）+ `…/payload/env/gateway.env.template`（新键登记默认关）。
6. **DF-06** census 面板 spec 三列接线——**未随批实施**：d_spec_steps/d_verified/
   d_accept_rate 恒 null 的根因在引擎侧 `is_target_verify` 接线（spec-v2 形 decode
   路径从未为真），属引擎在役面（overlay/镜像通道），按任务书依赖注记需停机窗+
   判读窗+批文，本批记呈批位（见 KNOWN-ISSUES §7）。
7. **DF-12** 外部 prose 双读数口径落锚——bug #20 的「同文档两组反向读数」（组 C
   对锚 +1.95% vs 组 D 对同一锚 −1.70%）落成正式口径注记：两读数分属两组锚条件、
   先分组再引用、不合并不换算；文件面=`tools/bench/README.md` §3.1 +
   `docs/CALIBER-AND-MEASUREMENT.md` §3.9（含 §2.1 引用注记）。
8. **EQ-02** RoCE 通信聚合双键纳入 boot 断言族——env 声明
   `SGLANG_ROCE_MAX_SIZE`/`DSV41_ROCE_GATHER` 时在役值必须双双 =1179648、单边声明
   即绑定律破裂、回滚值或互斥违例 die 拒起（条件式门：新代际两键均缺=不断言放行），
   绿时横幅自报；文件面=公开+内部 `deploy/bin/r3-boot-arm.sh` /
   `~/migrate-assets/bin/r3-boot-arm.sh`。详见本档 EQ-02 专节（0.3.4re）。
9. **EQ-03** 判负/互斥禁键组合真 fail-closed——env-lint 门把 serve 禁参组合
   （`--enable-mixed-chunk`×回放旗标互斥、`--chunked-prefill-size` 8192 判负档/
   16384 永禁档、UP43050 `--sleep-on-idle`）纳入硬拒绝路径：命中即 REFUSE `exit 1`
   并打印命中的禁组合，台账判负不再是「当时跑着没坏」空窗；文件面=公开
   `deploy/bin/r3-gate-env-lint.sh` + 内部 `~/migrate-assets/bin/r3-gate-env-lint.sh`。
10. **EQ-04** 功能面契约测试量具新建 `tools/contract_probe.py`——对网关口与引擎
    直连口各发 3 例（tools-nostream/tools-stream/retrieval 长上下文检索），断言返回
    结构化 tool_calls 而非明文标记（标记跨 SSE 分片切开亦被抓）、finish 语义正常；
    缺省 dry-run 零网络、`--selftest` 离线夹具自测（`tools/contract_probe_selftest/`
    8 件 fixture〔6 JSON+2 SSE〕+manifest 台账）、8899 生产口恒拒发。详见下文「新工具」段。
11. **EQ-05** engram-权重身份一致性断言——doctor-034 增换权重静默劣化防线（权重
    config sha 登记对表+engram 派生物 mtime 新旧判序，混配即红），登记面 config-034.tsv
    增 CFG-68..72 行；文件面=战役仓 `tools/doctor-034.sh`+`tools/config-034.tsv`。
12. **EQ-09** 网关纳入验收序列（第五查）——verify-034 增 B0 网关第五查三断言
    （网关 /health=200、UPSTREAM 车道指向正确、模型清单以网关 /v1/models 为正典与
    引擎直连逐 id 一致），引擎健康≠主链健康，fail-closed；文件面=战役仓
    `tools/verify-034.sh`+`tools/deploy-034.sh`（--smoke/--full 同跑）。
13. **EQ-11** 量具参数面统一与管道静默失败治理——新增共享构造处
    `tools/bench/bench_url.py`：URL 三形通吃归一（origin/v1 基/全路径一律归一为 v1
    基，历史正确传参逐字节不变、历史必 404/405 错形修复为可用）+ argparse 拒起改
    首行 `ERROR[<prog>]: …` 可 grep 摘要到 stderr、`exit 2`（管道下不再静默空输出）；
    接入件=`sd_bench.py`（+`--targets` 别名）/`qeval.py`/`gsm8k_dsv41.py`（`--base`
    别名 `--base-url`），机读参数对照表=`docs/CALIBER-AND-MEASUREMENT.md` §1.2。
14. **EQ-12** adapter 增量清单格式与校验工具产品化——清单头注与路径行分离的规范
    格式（注释行不再被当路径解析致假缺件）+只读校验工具：内建注释过滤、逐件 md5
    对 manifest、输出机器可判差异结果；文件面=`tools/adapter-manifest-verify.sh`
    （含 `--self-test` 负例夹具）+ `deploy/adapter/README.md`「清单格式律」节。
15. **EQ-13** 缓存配额 guard 换算升级——DSV41_ENGRAM_CACHE_GIB 的 per-store×层数=
    per-host 换算、上限与余量三行常打印（cap 与在役 `_warn_cache_share` 同式），
    `--enforce` 阻起档超限 REFUSE / `--warn` 强告警档缺省，「乘层数」从人工纪律变
    工具输出；文件面=战役仓 `tools/packages/selfdiag/payload/gates/r3-gate-engram-quota.sh`
    （selfdiag 包新件，`--selfcheck` 红绿例）+包 README/MANIFEST 登记。
16. **EQ-19** pr_ladder6 档锚登记缺口收口——现行 HEAD 锚 `ed303431` 首次入台账并
    标 RETIRED（G5 8899 硬拒+BENCH_REPO 灭失双因，量具本体零改），现行 sparkDash
    阶梯载体=sd_bench.py 直调；文件面=`docs/registry/BENCHMARK-SOURCE.md` §5.1
    台账行+§十追加节。
17. **EQ-20** w1_longctx_bench 硬编码路径补链制式固化——冻结量具本体零改红线下，
    把 `PYTHONPATH=$SDB_DIR` 补链+双 md5 钉（w1 `941a853b`+sd_bench `410f543d`）
    前置断言固化为 census/w1 调用制式（缺件/漂移=rc=2 拒跑），漏注入即跑崩/静默
    跑错的脆弱点收口；文件面=公开 `docs/runbook/runbook-034.md` §2.4 增节（制式
    引战役仓 `tools/census_w1_pyfix_wrapper.sh`+`census_w1_pyfix_usage.md` 两件）。

### 上游并入项（host 侧规避，全部零镜像改动；镜像补丁类备方案呈批未实施）

- **UP44162** bench 开环到达漂移（`tools/upstream/bench-arrival/` 两件套）——见
  本档专节；
- **UP45614** thinking 泄漏（`tools/thinking_leak_guard.sh` 三面执法+gw-verify lint
  三例）——见本档专节；
- **UP43050** `--sleep-on-idle` 退役（SPEC6 九参→八参，禁参三面固化）——见本档专节；
- **UPSTREAM-45119** `cache_hit_rate` gauge 伪零（`tools/obs/cache_hit_caliber.py`
  计数器正典口径）——见本档专节；
- **UP42369** nvfp4 KV scales 误配长上下文崩塌（`tools/upstream/nvfp4-kv/` 三件套：
  守卫/剥 scales 手术/needle 验收门；本栈现役不命中缺陷态）——登记档=
  `docs/KNOWN-ISSUES.md` §4；
- **UP45525** DSPARK 与普通解码贪心输出分叉（`tools/upstream/dsp45525-plainroute/`：
  plain 车道参数面+四段守卫+lint；确定性敏感流量路由 plain 服务）——登记档=
  `docs/KNOWN-ISSUES.md` §5。

### 新工具：contract_probe（EQ-04）

`tools/contract_probe.py`——形面验收（旗标/横幅/md5）与功能面验收（按实际使用方式
打真请求）之间的工具桥：每终点（`--gateway` 网关文本车道口 / `--engine` 引擎直连
测试口）3 例共 6 例——带 tools 的 chat 流式+非流式（断言结构化 tool_calls、
arguments 合法 JSON、content 无工具边界明文标记）与长上下文检索题（needle 制式
同源：seed 播种+8 位十六进制魔码埋深度中点，判 finish=stop+正文非空+答中魔码）。
三律：缺省 dry-run 只打印将发的请求零网络；`--selftest` 离线夹具自测（判读纯函数
+socket 断连卫）；8899 生产口恒拒发（dry-run 亦拒）。接入验收序列随 EQ-01 类工具窗
另批编排，本批只建量具。

### 文档更新（0.3.4re 面同步）

README 版本面升 0.3.4 调优终态（三代版本系列表+性能主表，61 键口径）；新增
`UPGRADE-0.3.4.md` 与 `docs/release/0.3.4-RELEASE-NOTE.md`（移植批 new 骨架）；
`docs/DEPLOY-GUIDE.md`/`docs/DEPLOY-STEP-BY-STEP.md`/`docs/RUNTIME-PARAMETERS.md`
升 0.3.4 面与八参谱；`docs/KNOWN-ISSUES.md` 增 §4/§5/§6 上游现象条+§7 呈批位
（本批）；`docs/GETTING-STARTED.md`/`docs/GLOSSARY-PUBLIC.md` 抽查更新过时表述
（56 键→61 键口径、九参→八参、代际三代等）；`docs/registry/BENCHMARK-SOURCE.md`
§十（EQ-19）/§十一（计数器口径）/§十二（bench-arrival 登记）；
`docs/runbook/runbook-034.md` §2.4（EQ-20）；`docs/CALIBER-AND-MEASUREMENT.md`
§1.2 参数对照表（EQ-11）+§3.9 双读数落锚（DF-12）；`tools/bench/README.md` §3.1
（DF-12）+EQ-11 参数面；`tools/serve_flags_gate.README.md`（UP43050 判据）。

### 公开仓自 0.3.2-p1 跳版说明

公开仓上一批为 2026-10-30 round 91「公开面修复与文档治理批（0.3.2-p1）」，此后
**0.3.3（死锁修复过渡代）与 0.3.4（修复固化代+调优终态）两代全部在战役仓
`luz030-opt-campaign` 完成、未在公开仓逐代发版**——本批以 **0.3.4re** 把 0.3.4 面经
PortMap 移植（31 copy + 4 new，见上节）连同 17 单元修复与上游规避首次整体公开，
故公开仓版本号自 0.3.2-p1 直接跳至 0.3.4re；0.3.3/0.3.4 的版本叙事与读数不因跳版
缺失（正档=本 CHANGELOG 既有各节+`docs/release/` 034 系列档）。后续若上游
0.3.5 立项批落地，公开仓随该窗回到逐代同步。

### 呈批与残留（未批零执行）

引擎侧呈批位=DF-06（spec 三列接线）/DF-07（页映射导出）/DF-08（grammar cache
有界化，案头方案在档三呈批位）/DF-09（B15 FP4 漂移核查）/DF-10（DSML 修复面，
条件位挂起）/DF-11（N=193 eager 观察）——逐项现状见 `docs/KNOWN-ISSUES.md` §7；
上游 image_patch 类（含 #45122 cherry-pick）备方案未实施；公开树
fabric-restore-gate.sh 未随 DF-02 同步（见单元 2）；boot/断言族的产线验证靴
（BL/CFG 行重钉+四机同步核+同靴抽测）随停机窗+判读窗另批。

## 2026-10-30 0.3.4 面公开移植批（0.3.4re；31 copy + 4 new）

> 战役仓 `luz030-opt-campaign` 0.3.4 面（修复固化代+调优终态）按 PortMap 移植入公开树。
> 键数口径一律按 gates-034 BL11 判据「61 键」；内网值（IP/主机名/网卡名/内部路径）一律
> 占位符化（数据位 `<…>` 形 / shell 执行位 `__XXX__` 形）；正典 md5 锚指内部原件，
> 公开树为脱敏拷贝故 md5 天然不同（逐件实落 md5 见下）。

- **工具六件套**（`tools/`）：deploy-034.sh `90e4d287` · verify-034.sh `349d9f86` ·
  doctor-034.sh `54ea1601` · selftest-034.sh `bc0e8cd8`（C 段已随公开布局改写：
  MANIFEST→docs/release、archive 面经 pub_path 映射 deploy//docs/ 落位、报告落 tests/）
  · config-034.tsv `0b6e761c` · gates-034.tsv `904c5ad1`。
- **bypass 三件+登记**（`tools/bypass/`）：prefill_bypass.py `c4875258`（与内部正典
  逐字节同，零内网命中）· stage-one-host-bypb.sh `aa50a90a` · bypass-armed-gate.sh
  `296923e3` · SOURCE-MD5.txt `6fedfb5c`（逐字节同）。
- **guard 两件**（`tools/guard/`）：gate_check.sh `a7357c94` · gate_check_unittest.sh
  `6d246156`（逐字节同）。
- **编排/观测件覆盖更新**：boot_sentinel.sh `f00e5dca`（DF-02 缺参拒跑 fail-closed 形，
  弃旧 a9250e4a）· boot-with-slotlock.sh `2fcbc125`（SL_LOCKFILE/SL_HOSTS mock 面形）
  · capture-boot-evidence.sh `24e8b0b5`。
- **deploy 面锚件**：env CBX1A-CERTM-spec1.env `1dd2cd3e`（61 键脱敏拷贝；内部正典锚
  `4370aab9`）· .env.tp4 `ecd387f0`（修订批头注代号占位符化后=`2a0d0d3d`，见上节）· prod-profile.env `f731914e`（**W-f 重钉**：:8
  env=4370aab9/:9 61 键/:12 COUNT=29；覆盖 2698B 旧形）· guards.conf `32f74b0e`
  （内部正典锚 `418414c3`；:161 envpin 钉 v41）· overlay-map.tsv `efd7d89b`+overlay-md5.txt
  `fd59c03b`（两锚与内部正典逐字节同；**29 件本体未随批=按新清单 md5sum -c 必红**，
  待整面同步窗）。
- **docs 面**：MANIFEST-034LOCK.tsv `98374e57`（段一/段二路径随公开布局改写）·
  034-VERSION-LOCK `c7ef8bd4` · ROLLBACK-PATHS-034 `bd2529ba`（授权链头注裁剪）·
  034-PERF-REPORT `51810738`（档头链接改 ../../README.md）· ACKNOWLEDGEMENTS `0135f0dd`
  （逐字节同）· runbook-034 `28687277`（修订批后=`ae980320`，见上节）· 034-KV-MECH-NOTE `600c5151` ·
  034-ERA-DRIFT `db7558c4`（逐字节同）· 034-BYPASS-JUDGMENT `cfabddd8` ·
  034-WD-TUNED-FINAL `d0e8314d`。
- **new 骨架四件**：README.md `081e79fa`（战役 0.3.4 产品化面为主基+旧版读者分流表底稿
  并入，八件导览留写手；其后经 0.3.4re 文档同步批再触=曾漂至 `a2ea9141`，修订批后
  现值=`e4d2f880`，见上节）· UPGRADE-0.3.4.md `b9b3f359`（修订批后=`9c69ae75`）·
  docs/release/0.3.4-RELEASE-NOTE.md `664e0fe7` · 本段。
- **两项 2026-10-30 公开修复注记**（详见本档既有两节）：①EQ-02 通信聚合双键纳入 boot
  断言族（RoCE 双键缺一 fail-closed，见「EQ-02 通信聚合双键」节）；②UP43050
  `--sleep-on-idle` 退役（SPEC6 九参→八参禁参，见「UP43050」节）。

## 2026-10-30 UP44162 上游缺陷 host 侧规避窗（bench 开环到达漂移面；0.3.4re）

> 来源：上游 sglang
> [PR #44162](https://github.com/sgl-project/sglang/pull/44162)（[Fix] benchmark:
> Compensate cumulative request arrival drift，fixes issue #43930；2026-10 时点
> **open 未合**）——`python/sglang/benchmark/serving.py` 的 `get_request`
> 泊松（finite-rate、非 trace）分支把 `await asyncio.sleep(interval)` 放在
> yield 之后、**以 consumer 恢复 generator 的时刻为睡起点**：consumer 的发包/
> 收流/记账工作与事件循环晚唤醒逐请求累进到达间隔，offered load 随请求数系统性
> 偏低（上游报告 100 req/s 档实测 ~68 req/s、400 req/s 档实测 ~190 req/s）。
> 修法=累积单调绝对到达时刻 `target_arrival_time`，yield 前只 sleep 剩余时间，
> 迟到即追不重置时刻表，terminal sleep 移除但保留最后 draw（RNG 兼容）。
> 同窗关联：#46504（多轮输入 token 计入 serving metrics）、#47050（timed-trace
> replay；trace 分支本身即绝对时刻法不受本缺陷影响）。**本缺陷在 bench 客户端，
> 不在引擎镜像**——规避全落压测口径侧，零镜像改动。

**本栈计量面影响核实（2026-10-30 只读亲核）**：本地 sglang 主干 checkout
`~/sglang-main-src`（commit 79cafec0，2026-09-28，与生产 overlay 基线同源）
`benchmark/serving.py:1111-1123` 泊松分支为缺陷版（守卫 `--check` 实测
VULNERABLE rc1，输出在档）。本仓正典量具全闭环（sd_bench〔CFG-31〕/
de_c48_bench〔CFG-32〕/conc_pr_driver〔CFG-30〕均并发驱动，零 `request_rate`/
`exponential`/`asyncio.sleep` 调度面，grep 亲核）——**现行读数不受本缺陷偏置**；
受影响面=未来开环基准（PR 复测、SLO 校验、与上游数字对齐），本窗补前置口径面。

**规避两件套（双面同件，`tools/upstream/bench-arrival/` + SOURCE-MD5.txt 互证）**：

- `bench_serving_44162.py`（修补版载体/薄启动器）：定位 sglang（`--sglang-root` >
  `$SGLANG_ROOT` > `~/sglang-main-src` > 已装包，缺位 rc2 fail-closed）→ import
  `sglang.benchmark.serving` → 判别 `get_request`：缺陷版=**运行时注入 #44162
  修补版并重绑**（exec 进模块自身 `__dict__`，np/time/asyncio 继承模块对象=
  draw 序与 RNG state 兼容；`serving.py:1560` 调用点为模块全局查找，重绑即生效；
  上游源码树/镜像零改动）→ 原样透传 bench_serving 全部 CLI；已修复面
  ALREADY-FIXED 直接透传；签名不识 rc2 拒跑。
- `bench_arrival_guard.py`（口径守卫）：`--check [--path P]` 判别 sglang 面
  （源码树/安装根/serving.py 单件）get_request 缺陷态（VULNERABLE rc1 /
  FIXED rc0 / UNKNOWN rc2 fail-closed）；`--lint [PATH...]` 扫仓面「裸跑
  sglang bench_serving 且 `--request-rate` 有限值」的开环口径=REFUSE，豁免
  标记三枚（`bench-arrival: patched/closed-loop/doc`），工具本体两 py 自豁免。
- **开环基准制式**：凡有限 `--request-rate` 跑延迟/吞吐基准，一律
  `python3 bench_serving_44162.py <bench 参数>`（启动器横幅须 PATCHED 或
  ALREADY-FIXED 方为有效口径）；闭环量具与 `--request-rate inf` 不经本件。
  <!-- bench-arrival: patched -->
- **自证（两面各自亲跑）**：guard selfcheck **n=20**（判别器红绿夹具、源码
  提取器、三场景假时钟语义〔work<gap 到达=名义表、work>gap 饱和连发=消费率
  上限、晚唤醒迟到即追且时刻表不重置〕、RNG draw 数守恒、lint 红绿五例）；
  启动器 selfcheck **n=10**（PATCHED/ALREADY-FIXED/UNKNOWN 三路、重绑生效、
  修补后到达表、guard/启动器补丁核心代码级同源）；`--check` 对本地 checkout
  实测 VULNERABLE；`--lint` 双仓实测 PASS（存量零命中）。宿主无 sglang 运行
  环境（未装包），启动器对真树实跑=rc2 fail-closed（预期，输出在档）。
- **退役条件**：上游 #44162 合入发布后目标面 `--check` 转 FIXED ⇒ 启动器自动
  透传，本套转维持态；判别器 FIXED 语义与上游一致长青保留。#46504/#47050
  随版本入栈的升级跟踪以 `tools/upstream/deepseek-recipe-pypi-probe.sh` 同款
  版本探针/CHANGELOG 核对面承接。公开面同批登记=docs/KNOWN-ISSUES.md §6、
  docs/registry/BENCHMARK-SOURCE.md §十二；战役仓锚=docs/TOOL-ANCHORS.md
  「其他工具族现役锚点」节。

## 2026-10-30 UP45614 上游缺陷 host 侧规避窗（thinking 泄漏面；0.3.4re）

> 来源：上游 sglang
> [#45614](https://github.com/sgl-project/sglang/issues/45614)（[Bug]
> DeepSeek-V4.1 + SGLANG_DEFAULT_THINKING=1: thinking block leaks into content
> when the request carries no reasoning_effort）——v0.5.22 + DeepSeek-V4.1-Flash-1017
> + `--reasoning-parser auto` + `SGLANG_DEFAULT_THINKING=1` 时，不带
> reasoning_effort 的裸 chat 请求思维链整体漏进 content（reasoning_content=null）；
> 带 reasoning_effort 即恢复。根因为两侧不对称：prompt 侧
> `_apply_jinja_template` 回退读该环境变量、解析侧 `_get_reasoning_from_request`
> 不读，deepseek-v41 解析器以 force_reasoning=False 运行。无修复 PR。

**本栈同病核实（overlay 在档）**：`deploy/overlay/o12c1-prod/serving_chat.py:1794`
prompt 侧回退读 `envs.SGLANG_DEFAULT_THINKING.get()`，而同文件 `_get_reasoning_from_request`
（:3241 起，含 explicit_thinking 形）全程不读——不对称与上游同构（v4vl-79cafec0 面
:1482 同形）。触发条件=该 env 真值 **且** 请求裸发（无 reasoning_effort/无 thinking
键）。我栈 env 面（deploy/env、prod-profile、在役 ARM_ENV_FILE 面、boot 脚本）实测
**均未设该键**（sglang `environ.py:1462` `SGLANG_DEFAULT_THINKING = EnvBool(False)`
——不设即关）；网关 rc3.8.8（2026-10-30 双键注入窗）已对裸请求注入
`chat_template_kwargs.thinking=true`+`enable_thinking=true`，01 在役
`inject.conf` 落 `INJECT_ENABLE_THINKING=1`。即：**两腿规避的现值面均已绿**，
本窗补的是机器执法面（防回退/防漂移），proxy 行为零改、镜像零改。

**守卫新件（双面同件 md5 `1908dff7`）**：`tools/thinking_leak_guard.sh`
（公开面与战役仓 `luz030-opt-campaign/tools/` 同件落位）三面执法：

- **R1 env unset 律**（issue 建议修法「干脆 unset」）：扫在役 ARM_ENV_FILE 面
  （`~/migrate-assets/dsv41/env`、`~/migrate-assets/prod`）、repo env 面、boot
  脚本双位（在役 + 快照）、`/etc/default`——`SGLANG_DEFAULT_THINKING` 真值
  （=1/true/on 等一切非假形）即红；`=0/false/no/off`/空值/注释行=绿；缺面=INFO
  跳过不红。`--selfcheck` 31 例（红绿夹具+分类器单元）全绿。
- **R2 网关注入面**（issue 建议修法「网关强制注入」）：01 在役 drop-in
  `inject.conf` 必须 `INJECT_ENABLE_THINKING=1`；包模板主车道必须 =1；vl 车道
  钉 =0（VL 呈裁 C3 形）。
- **R3 客户端锚**：`ds_gate.py` 必含 `chat_template_kwargs` 与 `reasoning_effort`
  双锚（我方自有 chat 流量永不裸发；该两锚为存量行为，本窗只加断言）。

**lint 面（gateway 包，双面 payload 同件）**：`gw-verify.sh --offline` 增
**#45614 面**——`SGLANG_DEFAULT_THINKING` 属引擎侧 env、对网关为异键，env 文件
内任何声明（含 =0 假形）=红；**主车道 `INJECT_ENABLE_THINKING` 必须 =1**（缺键
/=0=裸请求兜底敞开=红）；vl 车道（第二实参）维持 {0,1} 域检查分形。`--selfcheck`
新增 T9（异键真值/假形双红）、T10（主车道 =0/缺键红）、T11（车道分形判别：同一
=0 形 vl 绿主车道红），T1-T8 原样全绿（14 例）。

**serve 参数/模板注记**：`gateway.env.template` A2 节补 #45614 部署红线注记
（主车道=1 的依据与配套执法件指针）。

**三联动与登记面**：gateway 包 MANIFEST 再生成（公开 13 件/战役仓 14 件）、
VERSION 指纹重钉（`0.3.2-gwfix4`→`gwfix5`；公开 `0668bb8a`/战役仓 `549c07e7`）、
战役仓 `docs/TOOL-ANCHORS.md` gateway 锚段同日更新。**同窗吸收 rc3.8.8 未随滚
欠账**：同日早窗 payload 升 rc3.8.8 后 VERSION 未钉，双面包 selfcheck 各有
一条既有指纹红（改前实测在档），本窗重钉后双面 `selfcheck/run.sh` 复跑
OK=16/RED=0/exit 0 全绿。

**长期面（随镜像补丁窗承载，本窗不动镜像）**：升级镜像时吸收 issue 建议修法
（`_get_reasoning_from_request()` 回退读该 env，或 prompt 侧对 explicit_thinking
类解析器忽略该 env）；吸收后本守卫 R1 转观察位或退役。boot 期硬门
（`r3-gate-env-lint.sh` EQ 系增该键拒起）属产线 boot 链改动面，不在本窗落点
（其产线孪生 `~/migrate-assets/bin` 面有并行单元在途），留待 EQ-10 吸收窗并入。

## 2026-10-30 UP43050 上游缺陷 host 侧规避窗（--sleep-on-idle 退役；0.3.4re）

> 来源：上游 sglang
> [#43050](https://github.com/sgl-project/sglang/issues/43050)（[Bug] Idle-wake
> hang at `_low_ratio_index_topk_dense` when `--sleep-on-idle` is enabled）——与我栈
> **完全同构**的外部报告：DeepSeek-V4.1-Flash + DSPARK speculative + 3× DGX Spark
> （GB10/SM121/UMA）+ NCCL 2.32.3 + `--sleep-on-idle`。空闲 10-20 分钟后被任意请求
> （含健康探测）唤醒即进入死 prefill，py-spy 卡
> `_low_ratio_index_topk_dense`（indexer_chunked_v3.py:181）的 `prefill_empty_cache`
> 唤醒重捕获路径，疑似唤醒后缺一处 host 同步点；无修复 PR、无评论。报告者实测：
> 同一硬件去掉 `--sleep-on-idle` 后空闲期完全正常。

**serve 参数面（一件退役）**：`deploy/bin/r3-boot-arm.sh` SERVER_ARGS 去
`--sleep-on-idle` 单参（W-G 窗 2026-10-16 入谱的第九参；参行注释化+RETIRED-UP43050
注记，W-G 史注原样保留）。SPEC6 谱 9→**8** 参，归一指纹回 **6b12a445**（=W-C 八参
预登记复用，离线复算逐位复核；九参 9d64a5de 转史档）。W-G 窗省电收益（空闲忙转
约 1 核/台、墙插 10-12W/台）让位可用性。公开件 md5 自 `8384bbd7` 起变（实测
`d1852b0f`，头注有变更记录）；**镜像零改**（host 侧规避，不动 r032c）。

**禁参三面固化（守卫/lint）**：

1. `tools/serve_flags_gate.sh` 增**缺席判据**（UP43050）：`--sleep-on-idle` 在场即
   FAIL（判据方向与 A8/A9 相反）；自检增 R8 负控制（禁参在场应 rc≠0），R1-R7 原样
   全绿；`--api` 模式对 `sleep_on_idle` 尽力取证（argv 两模式为权威取证面）。公开件
   md5 `2bc33b88`→`7a009657`（实测）。
2. `deploy/bin/r3-gate-env-lint.sh` EQ-03 禁参组合增 `--sleep-on-idle`：任何值面
   注入位（`SPEC_EXTRA_ARGS`/`EXTRA_SGLANG_ARGS` 等）携带即 REFUSE 拒起。公开件
   md5 `a69f5f0e`→`09b48c28`（实测）。
3. `deploy/prod/selfcheck-prod.sh` argv 判据翻面：required 摘该参，新增 forbidden
   禁参表（`Config.Cmd` 含即 FAIL）。公开件 md5 `5de1f509`→`a5363213`（实测）。

**回退面作废与替代面**：W-G 窗登记的「回拷 `.bak-pre-wg`〔9f3cdaac〕单参回退」
**作废禁用**（回拷=重新引入 #43050 idle-wake hang；三面硬门拦截）。空闲资源回收
改走**低峰期主动 `/release_memory` 或定时重启**（勿用自动 idle-sleep）；重启窗照走
沉降律。

**升级面指引**：升级镜像时优先吸收 #45397/#46636 一类 idle 路径修复，并在补丁镜像
里守卫 wake 路径的 host-sync；满足后另开复评窗方可重议此参（届时 SPEC6 表改回并
重登指纹）。

**登记面同步（八件）**：`deploy/SPEC6-SERVE-REF.md`（谱表 9→8、第 9 行 RETIRED 节、
指纹复用登记、对照表判据反转、W-G 三元组覆写注记）、`docs/RUNTIME-PARAMETERS.md`
（参表第 9 行、指纹行、§5.5 回退节）、`docs/DEPLOY-GUIDE.md`（§6 参面、§7 四查
3b 闸门）、`docs/DEPLOY-STEP-BY-STEP.md`（§6.2 参面清单）、`docs/PITFALLS-AND-FAQ.md`
（接线判据方向注记）、`deploy/README.md`（boot 件参面简介）、`UPGRADE-0.3.2.md`
（§7 五件套表覆写注记、§8 点火参面、§9 验收门、§11 回退表）、
`tools/serve_flags_gate.README.md`（判据表+R8+取证面说明）。历史档（0.3.2 release
note、ACKNOWLEDGEMENTS、reconstruct/0.3.2、CHANGELOG 旧条、README 0.3.2 增量段）
按史面不覆写律原样保留。

**验证**：`bash -n`×4 全过；`serve_flags_gate.sh --self-test` R1-R8 全 PASS；
env-lint 禁参负例（v2/v40731 双形态）REFUSE rc=1、净例 PASS rc=0；selfcheck-prod
内嵌 argv 判据三态离线抽测（绿 rc=0/禁参在场 rc=1/缺参 rc=1）。产线内部源形
（`~/migrate-assets/bin/`）与活容器本窗**零动**——产线同步（活件去参+复靴+四查）
由主会话另开停机窗承载，战役仓正典注记见
`luz030-opt-campaign/tools/packages/cfgmgmt/payload/boot/boot-chain.md5` 2026-10-30 条。

## 2026-10-30 上游规避：cache_hit_rate gauge 伪零的监控侧口径（UPSTREAM-45119）

> 来源：上游 sgl-project/sglang issue #45119（`sglang:cache_hit_rate` gauge 在空/无命中
> prefill 报告时发布 0.0，健康缓存〔真实 ~0.96〕在 Grafana 上来回跳 0；修复 PR #45122
> open 未合）。本栈在役引擎 /metrics 实测快照同页：计数器
> `sglang:prefill_effective_tokens_total{mode="input"}=1.068429e+07`、
> `{mode="device_hit"}=910336`（有真实流量与命中）而 gauge=0.0——缺陷签名现势铁证。
> **镜像不动**（cherry-pick #45122 随后续镜像窗承载）；本批全部落在 host 侧监控面。

**新增一件**：`tools/obs/cache_hit_caliber.py`（host 侧口径规避件；战役仓
`luz030-opt-campaign/tools/obs/` 逐字节同件双面，锚=战役仓 `docs/TOOL-ANCHORS.md`）：

- **正典口径（计数器）**：`hit_rate = rate(Σ *_hit mode) / rate(全 mode)`，族=
  `sglang:prefill_effective_tokens_total`（HELP 自述即此式）；两快照取窗（Δhits/Δtotal）、
  单快照累计、计数器回绕自动降级累计并注记；备用族 `cached_tokens_total`/`prompt_tokens_total`；
- **gauge 兜底**：`!= 0` 过滤+保留最后非零值（真 0% 冷缓存会误持旧值→只作兜底带降级注记，
  判读恒以计数器为准）；verdict 同时输出 gauge 原始值/过滤值/缺陷签名
  （`defect_signature`=计数器有流量而 gauge 归零）；
- **env 旋钮**（host 侧自用，不进引擎 env 面）：`CACHE_HIT_CALIBER_MIN_TRAFFIC`
  （缺省 1000）小流量防伪率；
- **守卫/lint 面**：`--lint` 扫 .py/.sh 裸读 `cache_hit_rate` 判据一律 REFUSE
  （出口 0/1/2 同 env-lint 制式；豁免=同行 `# cache-hit-caliber: raw-snapshot`）；
  本仓 `tools/`+`deploy/` 1098 文件实扫 PASS；
- **离线自证**：`--selfcheck` 13/13（内嵌缺陷重放：计数器健康+gauge 归零必判签名）；
  单测 `tests/unit/test_cache_hit_caliber.py` 19/19（纯 stdlib、零网络零引擎）。

**配套两件**：`tools/kvlife_driver.py`（双面同批）裸 gauge 快照位加豁免标注+docstring
口径指引（行为零改）；口径纪律入册 `docs/registry/BENCHMARK-SOURCE.md` §十一
（计数器正典律，镜像修合入后仍有效）+ 现象条目 `docs/KNOWN-ISSUES.md` §3
（现象→判据→根因→缓解四段式，含 Grafana 侧建议查询式）。

## 2026-10-30 EQ-02 通信聚合双键纳入 boot 断言族（0.3.4re）

> 来源：`luz030-opt-campaign/docs/plan/035-W0-TASKBOOK-20261030.md` §EQ-02（外部
> 手册升级篇 §14：A/B/A 实测两键回滚即 c8 −96% 非单调塌陷；此前「不许回滚这两键」
> 只有台账铁律、tools/deploy 全无机器断言——任何「清理多余参数」式操作可静默砍掉
> 高并发路径）。

**代码修复一件**：`deploy/bin/r3-boot-arm.sh` 在 ARM_ENV_FILE 注入循环之前新增
**RoCE 通信聚合双键条件式 fail-closed 断言**（EQ-02 红线断言族成员，与 D15 五门
同列 boot 前置拒起门）：

- env（ARM_ENV_FILE）声明 `SGLANG_ROCE_MAX_SIZE`/`DSV41_ROCE_GATHER` 两键时，
  在役值必须双双 `=1179648`，任一回滚值（524288/262144 等历史档位）即 **die
  拒起**并在横幅报因；
- 单边声明（其一缺）= 两键绑定律（`docs/RUNTIME-PARAMETERS.md` §1.9）破裂，
  「清理多余参数」式砍键指纹，**die 拒起**；
- 两键均未声明（新代际形：RoCE 聚合面整族退役的 env，如 VL41N 系）→ **不断言
  放行**——条件式门而非无条件断言（代际分形：勿以在役值门误杀新代际缺省面）；
- ARM_ENV_FILE 缺位 = 无注入面（两键不在 COMMON_ENV 固有面）→ 不断言；
- 绿时横幅自报 `[EQ-02] ... =1179648 PASS`（boot 四查可直证）。

**同步面**：产线内部源形 `~/migrate-assets/bin/r3-boot-arm.sh` 同批同构落
（留档 `.bak-pre-eq02-20261030`）；本仓件为快照镜像，头注已追加变更记录。boot
md5 变化以 `md5sum` 实测为准；BL/CFG 行重钉（`prod-profile.env` 的
`PROD_BOOT_SCRIPT_MD5` 等）+四机同步核+同靴抽测（DE c8 242.83 / PR 64k 6289.3
锚 ±5% 与 524288 负例拒起直证）随停机窗+判读窗承载（任务书 §EQ-02 依赖与前置）。

## 2026-10-30 公开面修复与文档治理批（0.3.2-p1）

> 来源：外部镜像部署站点回传的两本踩坑手册（升级/部署篇，97 条编号条目）+
> 一份思考流质量证据包，全部逐条核验后处置。核验记录与误报澄清见
> [`docs/KNOWN-ISSUES.md`](docs/KNOWN-ISSUES.md) §2。

**代码修复五件**（每处带出处注释；bash -n / py_compile / 功能抽测全绿）：

1. `deploy/bin/r3-boot-arm.sh`、`boot_mvl41_native.sh`、`boot_mvl40exp_r2.sh`：
   env 注入循环加**尾行守护**（`|| [ -n "$line" ]`）——env 文件末尾缺换行时
   `while read` 静默丢末行，而 env-lint 件自带守护会照常 PASS（lint 绿但键丢）。
2. `tools/packages/gateway/payload/concurrency_proxy_v2.py`：思考链注入改**双键**
   （`chat_template_kwargs.thinking`〔V4.1 族 overlay 实读键〕+
   `enable_thinking`〔其他模型族兼容键〕）——此前单注入 `enable_thinking`
   对 V4.1 族是 no-op（假键）。
3. `tools/packages/fabric-net/payload/diag/fabric-doctor.sh`：`--json` 在
   `_lib` 层级失锚时显式 `exit 2`（此前静默跳过=三字段出口失能无报错）。
4. `tools/packages/fabric-net/payload/guards/fabric-sentinel.sh`：idle 双确认门
   兼容 `{"loads":[…]}` 包裹形（此前只认顶层 list，包裹形下恒读 0/0=在飞请求盲判）。
5. 同文件：带外判据改 **awk 浮点比较**（`ar_probe.py` 输出 `%.1f` 浮点，
   `[ -gt ]` 恒假=verdict 恒 0 永不告警）；站点绑定全面参数化
   （`SENTINEL_ASSETS/IMAGE/MASTER_ADDR/W1-W3/SUDO_USER`，缺参拒跑），
   清除旧网段 registry/主机名/家目录硬编码。

**md5 变化**：`r3-boot-arm.sh` 公开件自 `9ac6e113` 起变（以 `md5sum` 实测为准，
头注有变更记录）；其余四件同理。产线内部源形不受影响——本批为公开仓独立修复，
内部产线面同步另窗承载。

**文档治理（八件新增 + 六处补注）**：新增 `docs/GETTING-STARTED.md`、
`docs/GLOSSARY-PUBLIC.md`、`docs/DEPLOY-STEP-BY-STEP.md`（从零部署主路径，承接
DEPLOY-GUIDE）、`docs/RING-DEPLOY.md`（环网形部署）、`docs/PITFALLS-AND-FAQ.md`
（排障词典，手册 97 条全量吸收）、`docs/CALIBER-AND-MEASUREMENT.md`（量具口径
全集）、`docs/RUNTIME-PARAMETERS.md`（运行参数词典）、`docs/KNOWN-ISSUES.md`
（已知现象，含思考流重复退化判词与缓解）；`UPGRADE-0.3.2.md` §9 验收门勘正
（argv 直证替代 `Config.Cmd`）+新增 §15 停机窗五步/§16 通信面铁律/§17 取源顺序；
`docs/RING-0.3.2-COMPAT.md` 加 PEER_HCA_MAPS 属主映射表警示；
`tools/packages/cfgmgmt/README.md` 加 0.3.1 时点快照代际声明；
`tools/packages/fabric-net/README.md` 加外部采用者必读（兄弟仓取件+站点适配）。

## 0.3.2 基线回滚点（2026-10-22；tag `v0.3.2-baseline-20261022`）

- 以 r032c OCI index `sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4`
  作为唯一 0.3.2 基线；registry 新增 tag `0.3.2-baseline-20261022`。
- 离线 `docker save` tar `image-r032c-arm64.tar`（33,591,321,600 B；
  SHA256 `3d168db1…f624a`）与 OCI index/arm64 manifest/config digest 一并存档。
- 01 head（containerd overlayfs）与 02–04 worker（overlay2）的本地 image ID
  差异仅为 storage backend：index digest `47f6d91a…` vs config digest
  `ef64dec3…`，内容同一。
- 基线文档、恢复脚本、运行时快照与 `migrate-assets`/git bundle 备份见
  `deploy/checkpoints/0.3.2-baseline-20261022/`。

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

## 0.3.2 定版维护（2026-10-20 定版后；tag `v0.3.2` 面）

> 本节的改动全部在 0.3.2 已推 main（`c52a560`）之后、tag `v0.3.2` 之前落盘，
> 属**发布面一致性与可用性维护**，不动产线形、不改历史读数。

1. **README 版本面升级**：头档 0.3.1→**0.3.2 定版**；新增「版本系列」总览
   （0.3.0/0.3.1/0.3.2）与 0.3.2 性能主表（PR 七档/DE 五档锚/C8 聚合/512k/质量）；
   0.3.1 读数保留为历史基线；镜像表补 `0.3.2-r032c`（digest `47f6d91a…ffc4`）；
   现役形状态位改为 CBX1A 56 键+SPEC6 九参+adapter `b58e49ff`；致谢计数 110→**111**。
2. **部署面注记**：`deploy/README.md` 标明 0.3.1 历史样本与 0.3.2 重建包入口；
   `deploy/bin/r3-boot-arm.sh` 行 md5 更新为 `20f22bc6`（产线）/`9ac6e113`（公开件）；
   `deploy/SPEC6-SERVE-REF.md` 与 `docs/DEPLOY-GUIDE.md` 加 0.3.2 定版注记。
3. **issue #4 采纳件**：新增 `tools/serve_flags_gate.sh`——从运行进程 argv /
   `/get_server_info` 断言 `--tool-call-parser deepseekv41` 与
   `--enable-cache-report` 真的接线（只读、fail-closed、不经管道取 rc）；
   内置 R1-R7 反向自检（`--self-test`），测试包装
   `tests/unit/test_serve_flags_gate.sh`。SPEC6 新增「旗标-能力-生效值」对照表。
   本件是交付面补充工具，**不改产线 boot 快照**。
4. **发布索引**：新增 `docs/release/README.md`（版本系列+发布面三层+系列纪律）。
5. **文档修整**：`deploy/b12x/b12x_next/integration/vllm/README.md` 的
   上游文档引用由相对链接改为路径说明（上游件未 vendored，原链接为坏链）；
   `docs/ACKNOWLEDGEMENTS.md` 状态口径补 0.3.2。
6. **量具可用性修**：`tools/bench/sd_bench.py` 的 `--selfcheck` 不再被
   `--mode` 的 required 拦住（原状=文档写 `--selfcheck`、实跑先报缺 `--mode`）；
   非自检路径仍强制 `--mode`。自检 21/21 PASS 复跑。
7. **tag `v0.3.2` 清洁门**：打 tag 前在定版树上重跑密钥/凭据/PII 全量扫描、
   103 件 shell + 927 件 Python 语法检查、临时件检查与相对链接检查；
   结果与保留项见 `SCAN-REPORT.md` §「0.3.2 tag 清洁门」。

## 0.3.2 重建包（2026-10-20 定版后；tag `v0.3.2-recon`）

> `v0.3.2` tag 后核对“公开材料能否完整重建部署环境”，确认 r032c/A6/R1/E16B2/
> CBX1A 的增量件与 1017 配套尚未入仓。本节=补齐后的重建面；零产线触、零历史
> 读数改动。

1. **r032c 镜像面**：`deploy/reconstruct/0.3.2/image/` 收录 16 件全文、
   `79cafec0→f9d89b02` 补丁、公开构建脚本（单 COPY 层+读回+py_compile+import+
   collection）、IMAGE-IDENTITY、16 件 md5 台账、基座 16 件 md5。
2. **adapter 面**：13 件现役增量（A6 `sitecustomize.py` beb131ab、R1
   `kv_fp4.py` 75062432、E16B2 `replicated_split.py` 7d6f79b0、W-E `roce_ar.py`
   f61e0183、r032c 迁移 9 件）+4 件产线旁挂；12 件代码逐字节=产线 md5。
3. **overlay/b12x**：`deepseek_v4_backend.py` a1e7c3b5；b12x 三件
   035c860c/7253717a/23646e89（含 W-E 的 C 层 fabric/TC 语义）。
4. **env 链**：CBX1A 56 键 0729e18d + E16B2 5877fcb0 + E16B1 d55baa00 + FB54
   ad635762，附逐级键差与回退序。
5. **权重/engram**：1017 84 文件 SHA256SUMS（510,311,045,870 B）、NFS/四机秩映射、
   engram 8 分片 sha256（202,758,065,168 B）+ `pack_engram.py`/打包/分发/校验工具。
6. **boot/文档**：九参/WORKERS/四查与回退说明；README、DEPLOY-GUIDE、
   release note §八、发布索引同步指向重建包；不再保留“内部臂件/呈裁位”缺件口径。
7. **验证**：新增 `deploy/reconstruct/0.3.2/verify.sh`（MANIFEST/env/adapter/
   overlay/b12x/image/weights/patch apply/敏感面/反向自检），本地结果
   `RECON-KIT PASS`；补丁在公开 0.3.1 基线上逐件复算到产线 md5。
8. **边界**：基座镜像（48.6GB）、1017 权重（476G）、engram（189G）属外部大件，
   不分发；包内给身份指纹与校验清单。

## 0.3.2 公开升级面（2026-10-20；tag `v0.3.2-recon` 后）

> 用户裁定：0.3.2 现役 env（CBX1A 56 键）与 adapter 终态（`b58e49ff`）可公开；
> 公开仓以 **0.3.1 基底 + 混合快照 + 升级补丁/文档** 承接；`switch-fabric`
> 分支增量批准（远端头 `84b6732` 起点，不重写历史）。零产线触、零历史读数改动。

1. **现役 env 公开位**：`deploy/env/CBX1A-CERTM-spec1.env`（56 键/`0729e18d`，
   与 reconstruct 包内同名件逐字节相同）；deploy/README 状态表补 0.3.2 行与
   回退链 CBX1A→E16B2→E16B1→FB54→0.3.1 51 键。
2. **adapter 终态装配账**：`deploy/adapter/0.3.2-MANIFEST.md5`（87 个运行时件；
   86/87 与产线逐字节相同，`build_repack_cuda.sh` 仅注释家目录脱敏）+
   `deploy/adapter/0.3.2-ASSEMBLY.md`（基底+覆盖、落位、备份、绑定律、回退）。
3. **升级文档**：新增根档 `UPGRADE-0.3.2.md`——0.3.1→0.3.2 逐步升级、boot 门、
   PR 七档/DE 五档/质量门的复现命令与参考值、回退与排障；README、DEPLOY-GUIDE、
   SPEC6、release note §七/§八、发布索引同步指向。
4. **网络形态校正**：0.3.2 现役=双 rail 交换机（2 口 HCA 部署对 +
   `B12X_ROCE_TOPOLOGY=switched`/`LUZ_SWITCH_ROCE_FLAT=1`/TC106）；环网 4 口
   CX-7 标注为 0.3.1 历史形，两形不可混拼。
5. **switch-fabric 分支**：以 main 0.3.2 为基座合并并更新差异档（WG53 53 键
   历史样本保留；CBX1A 56 键为 0.3.2 交换机现役形）；远端快进，不 force。
6. **验证**：`verify.sh` 仍 `RECON-KIT PASS`；adapter 装配 `md5sum -c` 87/87；
   新增面密钥/PII 扫描与链接检查见 `SCAN-REPORT.md`。

## 0.3.2 环网可用面回补（2026-10-20；公开升级面后）

> 用户令：梳理本地 git 资料，把 main/环网分支用得上的修复与优化一并推送，
> 不局限于交换机分支。只收**拓扑无关且可复核**的件；交换机专属运行时不进环网面。
> 零产线触、零历史读数改动。

1. **质量量具公开**：新增 `tools/bench/qeval.py` + `qeval_tasks.py`（75 题，
   含 `extract_final_number` 独占纯数字行优先修复；`--selftest` 15/15）与
   `tools/bench/gsm8k_dsv41.py`（8-shot CoT，`--nq 500`；输出目录/题源/API key
   全部参数化，去掉硬编码宿主路径）。`tools/bench/README.md` 给 PR 七档/DE 五档/
   GSM8K/qeval/needle 的完整口径。
2. **needle 水位修复**：`tools/needle_probe.py` 回补随形校准律与输出 `water_m`
   字段；SKIP 行同时带实测值与线值，长上下文 idle 形可用 `NEEDLE_WATER_M=6000`
   校准后重跑。
3. **环网可用边界档**：新增 `docs/RING-0.3.2-COMPAT.md`——环网形可直接用的
   0.3.2 件（r032c 引擎+同名迁移 adapter、A6/R1、E16B2 split，拓扑无关键）、
   交换机专属件（flat one-shot/C 层 W-E/交换机三键）与“环网 + r032c”尚缺的
   boot profile；明确环网读数不得引用交换机形绝对值。
4. **已知负判留档**：环网 `channelId % 4` 四口轮转（v5-quad）在现有 hairpin
   布线下会落到不存在的直连口对并 `ibv_modify_qp` 超时；v4 配对表是对布线的
   编码，不重布线不要开 quad。
5. **口径同步**：UPGRADE §0/§6/§7/§10.3/§14、README 文档索引与结构块指向
   环网边界档与量具 README；`verify.sh` 增加量具自检（qeval 15/15、needle
   selfcheck、py_compile）。

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
5. **管理段重编址同步**：registry/角色址 <mgmt-node-ip 旧段> → <mgmt-node-ip 新段>（20261030 脱敏：内网值以占位符示形）
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
   （<发布网盘链接>，提取码 `<提取码>`——链接与码走发布渠道另行分发）=0.3.1-r3 交付镜像
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

## 0.3.0 基线（2026-10-05 检查点；系列起点）

- **R1 检查点封存**：`luz-0.3.0-r1`（commit `32c6acd`）=系列基线——36 键 env
  `b7e318e0`+sitecustomize 七件 `91adc83d`+池 9.6M 门；后续 0.3.1 在此基线上
  完成 FL6 召回修复转正与 VL 双臂。
- 0.3.0 无独立公开发布包；其形态与读数作为 0.3.1 的对照基线保留在
  `docs/report/` 与 `docs/registry/FORM-REGISTRY-031.md` 的历史引注中。
