# deploy/adapter/ — adapter 供给面整面快照（B1 收录 2026-10-13）

> **权威口径（2026-10-31 回正）：本目录=0.3.4 公开树交付面=canon98 前态正典面**
> （0.3.4 锁档修复固化面在 BYPASS 未入包时点的正典形态，即「98 前态面」）。
>
> - **\*.py 正典面 71 件**（顶层+`fi_r1/`/`overlay/`/`tests/`/`recipe_lib/` 子树含内），
>   与 audit 侧 canon98 材料逐字节同；正典锚（fingerprint.py 口径）：
>   count=71 / manifest-md5=**5c2c88eb**61411d67d8a040b5407e5e3d
>   （manifest-sha256=c569adc8…、concat-md5=4bc363eb…）、
>   **sitecustomize.py=45ca6e3e**1ca0eb34c3ff21abb0023571（前态，装钩前）。
> - **逐件账=[0.3.4-MANIFEST.md5](0.3.4-MANIFEST.md5)**（全供给面 91 件=71 \*.py+20 在役
>   非 py 件；验收：`cd deploy/adapter && md5sum -c 0.3.4-MANIFEST.md5` 全绿；*.py 面
>   指纹公开复算配方（LC_ALL=C 钉字节序，实测逐位复现）见该清单头部注——量具
>   fingerprint.py 为同算法实现、不随公开树分发。〔2026-10-31 复核批改注：原「验收两步」
>   之②引 `<量具>/fingerprint.py` 对外部采用者不可达，现以公开复算配方替代。〕）。
> - **prefill_bypass.py 不在面内（原因）**：0.3.4 交付前态面 BYPASS 未入包
>   （2026-10-28 锁档口径），适配件正典件住 [../tools/bypass/](../../tools/bypass/README.md)
>   （prefill_bypass.py=c4875258…），由装钩器按需升入——交付面默认不携带
>   env 门控实验钩，保持前态零突变面。
> - **装钩叙事（98 前态面 → 99 武装面）**：`bash tools/bypass/install-prefill-bypass.sh`
>   一键升入：sitecustomize 45ca6e3e →确定性插钩→ **dd69c59a**1098b735dd20e8aec1baaee9、
>   prefill_bypass.py c487525873cc2c0e09436414efb22115 入面、面件数 +1（本仓面 91→92 件；
>   锁档全文件口径 98→99）；env 门控 DSV41_PREFILL_BYPASS，未设键零突变、已装=幂等。
>   装钩细节与武装验收门=**[../tools/bypass/README.md](../../tools/bypass/README.md)**；
>   镜像升级操作=**[../docs/IMAGE-UPGRADE-GUIDE.md](../../docs/IMAGE-UPGRADE-GUIDE.md) ④**。
>   〔机侧注（2026-10-31 复核批）：装钩器缺省 `ADAPTER_DIR=$HOME/migrate-assets/dsv41/adapter`
>   =内部四机在役位；**无该位的机须以 `ADAPTER_DIR=<供给面目录绝对路径>` 覆盖运行**——裸命令
>   字面照跑必 PANIC exit 9「找不到 …/migrate-assets/dsv41/adapter/sitecustomize.py」=防呆设计；
>   ADAPTER_DIR 覆盖路径已实测可照跑（45ca6e3e→dd69c59a、c4875258 入面、重跑幂等）。〕
> - **计数口径谱系（同物异计非内容差）**：78=GitHub main deploy/adapter 顶层目录项数
>   （74 文件+4 子目录，非递归）；87=0.3.2 版本装配账（[0.3.2-MANIFEST.md5](0.3.2-MANIFEST.md5)
>   条目）；98=0.3.4 锁档全文件时点值（BYPASS 未入包）；71=同一前态面 \*.py 口径；
>   99=装钩器后在役武装口径。
>   〔代际注记（2026-10-31 复核批）：**78 系回正前（b4822e37 代）时点值**——彼时顶层=74 文件
>   +4 子目录；回正批后本目录顶层实测 `find -maxdepth 1`=**76 文件+5 子目录=81**（新增
>   `recipe_lib/`、`0.3.4-MANIFEST.md5` 等），同谱系唯一未标代际者即此 78，现值以
>   0.3.4-MANIFEST.md5（91 供给件）与本目录实数为准。〕
> - **历史指纹注记**：d52b0e3d/0beb4bee=2026-10-28 锁档「8-hex 集签名」口径时点值
>   （生成算法不在 fingerprint.py 三法内，另律不混用）；b58e49ff=0.3.2 装配面产线记录
>   口径（0.3.2 代）；73e5c5e4=[MANIFEST.md5](MANIFEST.md5)（EQ-12 在役账）清单文本口径
>   ——均为历史代时点值原样保留，交付验收以 0.3.4-MANIFEST.md5 为准。
> - 本文件以下 B1/FL6 代小节为历史注记**原样保留**（55b1e412、83 件面等=0.3.1 代
>   时点值，行值不删不改；现役面现值一律以 0.3.4-MANIFEST.md5 逐件为准）。

> 权威源=宿主 `~/migrate-assets/dsv41/adapter/`（bind mount 唯一供给面，四机全等律，
> cfgmgmt 包红线不烘焙）；同步/对表工具=selfheal 包 `adapter-sync.sh`
> （--apply/--check/--expect）。本目录=B1 整面收录快照（盲测呈裁「adapter 面不完整
> →整面收录」落实件），逐件 md5 锚=[MANIFEST.md5](MANIFEST.md5)（adapter-sync
> 同口径：find 排 `__pycache__`+LC_ALL=C sort，`md5sum -c` 可直验）。
> 逐件 CLASS 分类（active 29/inert 11/loader/UNCLASSIFIED）权威表=
> `tools/packages/cfgmgmt/payload/out/ADAPTER-MANIFEST.regenerated`（CODE31 D.3）。

## 清单格式律与只读校验（EQ-12，2026-10-30）

清单件（本目录 `MANIFEST.md5`、`0.3.2-MANIFEST.md5` 及五包同形 `MANIFEST.md5`）统一
**规范格式**——注释行与路径条目行彻底分离，只允许三类行：

1. **条目行**：`^[0-9a-f]{32}`+两空格+相对路径（`md5sum -c` 同形；禁绝对路径与 `..` 段）；
2. **注释行**：统一 `#` 前缀（不可混淆前缀；GNU `md5sum -c` 容忍）；
3. **空行**。

其余任何行=格式红（fail-loud 拒比对）。此律消除外部手册 P3-7（部署篇 §44 口径）
的高频假警报：「拿清单行数 vs 文件数当缺口」的差额是头部注释行不是真缺件；注释行
被逐词当路径解析会凭空多出假缺件。

只读校验工具=`tools/adapter-manifest-verify.sh`（内建注释过滤+逐件 md5 对 manifest+
「N 件差异」机器可判 RESULT 行，校验路径零写盘）：

```bash
bash tools/adapter-manifest-verify.sh --manifest deploy/adapter/MANIFEST.md5 --root deploy/adapter
# 出口 0=「RESULT: 0 件差异=通过」；缺件/md5 不符逐件列名并计入差异总数（exit 1）
# 格式红（非条目非 # 注释行/重复条目/单空格分隔）exit 2；清单不可读/树缺位 exit 3
# --extra 另检树内多件；--extra-exclude './MANIFEST.md5,./README.md' 豁免自指件
# --selfcheck 本地逻辑自检 13 项（含 strace %file 零写盘直证）
```

注：本仓树为工作面，与清单锚的 md5 漂移以工具实报为准（工具判「恰好哪几件」，
不产生注释行假缺件）；条目 md5 重钉属交付包发布动作（清单格式变更随下次交付包
发布生效，任务书 EQ-12 依赖注记）。

## 规模与构成（收录 83 件，约 3.0M）

> 代际注记（2026-10-31）：本节为 **B1 收录（0.3.1/FL6 代）83 件口径**的历史记录，
> 行值保留不删。现役 0.3.4 面=**91 件**（71 \*.py 前态正典面+20 在役非 py 件；较 B1 代
> 新增 dsv41_recipe.py、recipe_lib/deepseek_recipe/\_\_init\_\_.py 等前态正典件），
> 逐件以 [0.3.4-MANIFEST.md5](0.3.4-MANIFEST.md5) 为准。

| 分区 | 件数 | 内容 |
|---|---|---|
| 顶层 | 68 | sitecustomize.py 装载缝+全部 hook/库件（见下分类）+运行库+构建源 |
| `fi_r1/` | 6 | R1 FP4-KV 面（__init__/t_r1_equiv 对拍链+csrc 2+.cuh 2） |
| `lib/` | 1 | `librepack_cuda.so`（repack CUDA 运行库） |
| `overlay/` | 3 | a23 overlay 子树（A23E0 裁定「a23 六件+overlay/ 留役=键缺零惰性」） |
| `tests/` | 5 | adapter 树内验证件（test_replay_guard/test_score_budget_knob/test_repack_*/bench_repack_cuda；W2 卡在役引用 `python3 tests/test_score_budget_knob.py`） |

顶层分类（判定法=sitecustomize.py import 面 AST 传递闭包 × adapter-sync 清单交叉）：

- **boot 装载闭包 48 件**（sitecustomize 直接/传递 import 全集）：engram_backend、
  prefill_sp、kv_fp4（+kv_fp4_repack）、seam_mount（+reference_impl/selection_dump/
  triton_kernel）、verify_cap（+router_live）、admission_r1/gate、sparse_wire、
  indexer_hoist/budget、lm_cert、roce_ar/gather、b12x 双件、wo_a_w8、spec_sync_free
  等——闭包复算脚本核过：仓内树 48 件全在位。
- **留役休眠/库件 10 件**（当前 sitecustomize 未接线，档证留役）：tl_segment.py/
  admission_segment.py（O13 裁定「留役=键缺零惰性」）、a23_parity_core.py/
  a23_prefill_ar.py/probe_a23_ar_parity.py（A23E0 裁定留役）、mm_feature_lifecycle.py/
  mm_alloc_hygiene.py/mm_lifecycle_glue.py（L0 窗三件收窗留档）、
  p12_assertion_graph_gather.py（R1-FIX-2 交付件③断言器）、sanity_host.py
  （R1 面 host 侧 12 断言件，CODE31 复审计划归 fi_r1 面）。
- **运行库/资料件**：libdsv41_l2pf.so、librow_store.so、dspark_sps*.json ×4
  （SPS 表，容器侧 `--speculative-dspark-sps-table-path` 消费；2d 表四机留档惰性件）。
- **构建源**：l2pf.cu、repack_cuda.cu、row_store.cpp、build_repack_cuda.sh（三 .so
  的可复现源）。
- **仓侧谱系件**：sitecustomize-wire-v2.diff（FL6 接线重放 diff，仓自有件）。

## 收录口径与排除项（排除 42 件，逐件列名）

真源 adapter-sync 面 125 件（find 排 `__pycache__`）剔除以下 42 件=本快照 83 件：

1. **历史备份 39 件（`*.bak*`，RECIPE 恒拒族）**：`indexer_hoist.py.bak-pre-t4-20261007`、
   `l2_prefetch.py.bak-pre-f6prime`、`lm_cert.py.bak-pre-t4diag`、
   `mm_alloc_hygiene.py.bak-{pre-l0retry-20261006,pre-t4-20261007}`、
   `mm_lifecycle_glue.py.bak-pre-t4-20261007`、`prefill_sp.py.bak-deepcarry-t61{,b..i}`
   （9 件）、`prefill_sp.py.bak-deepcarry-t62{,b,c}`（3 件）、
   `prefill_sp.py.bak-{pre-t4-20261007,r1recert,v1rs-prod}`、
   `replicated_split.py.bak-pre-f6prime`、`sitecustomize.py.bak-{ih-indexer-hoist,
   p0-prefill-sp,pre-a23e0-20261007,pre-c24-20261006,pre-f5prime-20261007,pre-gaugeab,
   pre-k1,pre-l0-20261006,pre-l1f5-20261007,pre-o13-20261006,pre-o13b-20261006,pre-r1,
   pre-t17-20261006,preroce-c1}`（14 件）、`spark_prefill_split.py.bak-{,s2b-,s3-}eb53ea12`
   （3 件）。回退值需用时在真源/服务器在役位取，不随仓。
2. **历史变体 1 件**：`sitecustomize.py.f6-lmcert`（FL6-lmcert 窗变体；在役
   sitecustomize.py 并存，谱系由 wire-v2.diff 承载——「xxx_v1 与 xxx 并存只收在役件」律）。
3. **EP1 窗时点陈旧记录 2 件**：`ep1h-manifest.txt`/`ep1i-manifest.txt`（时点 md5 表，
   spec_sync_free/eager_glue 现值已漂移，留之误导）。

`__pycache__/`（顶层+fi_r1/+tests/ 三处，.pyc 按机生成非部署面）与 `.DS_Store`
（真源无）同律不计。

## 关键件锚（与 MANIFEST.md5 对表）

| 件 | md5 | 注记 |
|---|---|---|
| `sitecustomize.py` | **55b1e412** | **FL6 接线后稳定版=现役定版**（见下节） |
| `fl6_recall.py` | b87cbb5e | FL6 召回修复件（SWA interior retirement+match retract；第 51 键门控） |
| `prefill_sp.py` | **32cf9abf** | **W5 定型件**（stage2 MXFP8+出口直聚；回退件=0497e566 键关语义等价） |
| `kv_fp4.py` | feaaadd4 | R1 FP4-KV（严格布尔解析+路由门+fail-safe 双跑+横幅三态） |
| `fi_r1/` 六件 | 0b6f13f1 等 | R1 八件面（49 GREEN 对拍链），逐件见 MANIFEST.md5 |
| `spark_prefill_split.py` | eb53ea12 | TPsplit 库版（split 判负留库件；禁设键 DSV41_SPARK_PREFILL_TP_SPLIT） |

> 代际注记（2026-10-31）：本表=**B1/FL6 代（0.3.1）时点值**，行值保留。0.3.4 前态面
> 现值：`sitecustomize.py`=**45ca6e3e**（前态；装钩器后 dd69c59a，三代谱系
> 45ca6e3e 前态→b4822e37 EQ-12 重钉漂移代→dd69c59a 武装，本仓现钉回 45ca6e3e）、
> `kv_fp4.py`=**75062432**、`spark_prefill_split.py`=**8427a4c8**（0.3.4 锁档修复固化值）；
> `fl6_recall.py` b87cbb5e、`prefill_sp.py` 32cf9abf 两件跨代同值未变。逐件以
> [0.3.4-MANIFEST.md5](0.3.4-MANIFEST.md5) 为准。

## sitecustomize.py 状态注记（FL6 转正终值）

> 代际注记（2026-10-31）：本节=**0.3.1/FL6 代状态记录**（55b1e412 行值保留）。
> 0.3.4 代本件现值=**45ca6e3e**（canon98 前态面正典，见文首权威口径）；装钩器
> （`tools/bypass/install-prefill-bypass.sh`）插钩后=dd69c59a（env 门控
> DSV41_PREFILL_BYPASS）。下述 FL6 第 51 键机制在 0.3.4 面继续在役。

- **FL6 已转正在役（GREEN 收窗）**：产线现役=51 键 ENV51
  `PROD-R51W5FL6-spec1.env`（2ac74586；仓内异名同值件=`deploy/env/
  PROD-R51W5-FL6FIX-spec1.env`）+本件 55b1e412+fl6_recall.py b87cbb5e 四机全等。
  实役直证：cp30 召回锚位 99.95%+DE 82.17（8899=200 在役健康）。
- 变更谱系：2c4baad3（50 键产线原形）→〔`sitecustomize-wire-v2.diff` 重放：elif
  两支接线+EngramFinder 白名单两行〕→ **55b1e412（本仓件=现役）**。
- **休眠语义**：未设第 51 键（DSV41_FL6_RECALL_FIX）时逐字原版行为（与 2c4baad3
  配 50 键 env 行为等价）；设键=激活（值域 1/retire/retract 三态，门控表=
  `tests/fl6-recall/DEPLOY-NOTES.md`）。
- **回退链两级**：一级=摘第 51 键（sitecustomize 不动，休眠逐字原版行为）；二级=
  摘接线（按 wire-v2.diff 逆向回 2c4baad3 并摘 fl6_recall.py，adapter-sync
  `--expect sitecustomize.py=2c4baad3` 四机对表）。机理档=
  `docs/research/FL6-RECALL-BUG-ANALYSIS-20261013.md`。

## 与 overlay 面的关系

overlay o12c1-prod（29 件=28 活件+1 映射表，scheduler 5b6fe2a3 等）收录在本仓
`deploy/overlay/o12c1-prod/`（`SGLANG_OVERLAY_DIR` 挂载面，与本地 `overlay/`
a23 子树两回事）；派生面上游文件按上游许可（NOTICE §2）；指纹与构成=
FORM-REGISTRY §二。
