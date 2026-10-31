# README-说明 — 备查区对照总表（每件的身份、md5、血统、红线）

> 2026-10-31 备查同步窗立此件。备查区=公开仓里的**留档对照面**，回答一个问题：
> 「公开树里这份文件是什么代际的什么形、md5 多少、从哪来、能不能拿来跑」。
> 此前这些信息散落在 `reconstruct/0.3.2/README.md`、`overlay/NOTES.md`、
> `deploy/README.md`、补丁头注与 tests 断言等多处，没有一个单一对照表——本件就是
> 那个总表。本批同时把 0.3.4 overlay 29 件本体与三件正典全文落进公开树
> （此前只有锚值清单），「按新清单 `md5sum -c` 必红」的已知缺口自本批起闭合。

## 一、备查区分两区

| 区 | 路径 | 是什么 |
|---|---|---|
| **overlay 快照区** | [`overlay/o12c1-prod/`](overlay/o12c1-prod/) | 产线影子挂载目录的逐字节快照：**0.3.4 形现役 30 件**（29 个 `.py` 活件 + `overlay-map.tsv` 映射表），boot 时逐个盖进容器 |
| **正典备查区** | [`reconstruct/0.3.4/overlay/`](reconstruct/0.3.4/overlay/NOTES.md)（本批新增）、[`reconstruct/0.3.4/adapter/`](reconstruct/0.3.4/adapter/NOTES.md)（2026-10-31 回正批新增）、[`reconstruct/0.3.2/`](reconstruct/0.3.2/README.md) | 逐代际的身份正典全文：0.3.4 overlay 三件 / 0.3.4 adapter 前态面 71 \*.py（回正批新增）/ 0.3.2 完整重建包 |
| （旁支）VL 复原树 | [`overlay/v4vl-79cafec0/`](overlay/v4vl-79cafec0/) | V4.0exp 视觉臂专用 28 件复原树，与产线 o12c1-prod **零交叠**，不属本文主叙事，见 `docs/DEPLOY-GUIDE.md` §9.2 |

## 二、overlay 快照区现状（2026-10-31 起 = 0.3.4 形）

- **构成**：29 个 `.py` 活件 + 1 个 `overlay-map.tsv`（29 行，平铺文件名→容器内
  sglang 路径映射）= 目录 30 件。其中 4 件是**零字节占位件**
  （`deepseek_v4_vit.py`/`deepseek_v4_vl.py`/`dsv4_visible_window.py`/
  `mm_processor_deepseek_v4_vl.py`，md5 同为空值 `d41d8cd9…`）——占位是设计
  （挂载面计数与映射表保持闭环），不是缺数据。
- **对表清单**：[`prod/overlay-md5.txt`](prod/overlay-md5.txt)（29 行，本件自身
  md5=`6c98cf8c…`）。自验命令（在仓根执行）：

  ```bash
  cd deploy/overlay/o12c1-prod && md5sum -c ../../prod/overlay-md5.txt
  # 期望：29 行全部「成功」
  ```

- **本批换血表**（2026-10-31 前，本目录是 0.3.2 代基底混 3 件已演进件；本批整面
  同步为 0.3.4 现役形。**旧值不静默抹除**：历史值在此留档，旧文件本体可从本仓
  git 历史（本批提交之前的任意版本）逐字取回）：

| 件 | 旧值（本批前） | 新值（0.3.4 现役） | 代际注记 |
|---|---|---|---|
| `deepseek_v4_backend.py` | `736fbde5`（0.3.1 形） | **`73c80259`** | X6 bake R1 终形（血统链见 §四） |
| `deepseek_v4_model.py` | `fb87a7f0` | **`5b5ced03`** | 0.3.4 X6 重锚三件换血之一 |
| `layernorm_mhc.py` | `bd473946` | **`982a0ad0`** | 同上 |
| `serving_chat.py` | `c506bab5`（0.3.3 交付树整合形） | **`9b60a463`** | 0.3.3 W5 窗产物→0.3.4 原值承袭（01 机 head 面；02-04 机 worker 面仍为镜像 stock `b77a736c`） |
| `scheduler.py` | `3db3275e`（034-lock 锁档值） | **`4a7822a6`** | 锁档（2026-10-28）后 df07 窗演进，现役值；034-lock 档案仍记 `3db3275e` 属时点快照，非漂移 |
| `page_map_export.py` | （无此件） | **`c0dfe59a`** | 0.3.4 全新第 29 源（此前任何代际无此文件） |

  其余 23 个 `.py` 与 `overlay-map.tsv`（`efd7d89b`）本批前后逐字节相同。

- **清单沿革**：`prod/overlay-md5.txt` 本批前为 034-lock 时点形（自身 md5=
  `fd59c03b…`，scheduler 行=`3db3275e`）；本批重钉为现役权威形（`6c98cf8c…`，
  scheduler 行=`4a7822a6`），与私有侧权威清单逐字节相同。锁档档案
  （`docs/release/034-VERSION-LOCK-20261028.md`、`docs/release/MANIFEST-034LOCK.tsv`、
  `tools/gates-034.tsv`、`tools/config-034.tsv`、`docs/runbook/runbook-034.md`）
  中的 `fd59c03b`/`3db3275e` 是 **2026-10-28 锁档时点值**，保留不改，与本表现役
  值的差异=锁档后 df07 窗 scheduler 单件演进，已在此注记、非数据漂移。

## 三、正典备查区：0.3.4 三件（本批新增，`reconstruct/0.3.4/overlay/`）

| 件 | md5 | 身份（一句话） | 补丁链/血统 |
|---|---|---|---|
| `deepseek_v4_backend.py` | `73c80259…` | 0.3.4 backend 血统正典（X6 bake R1 t9 重锚预制备件，与四机部署面逐字节同） | `736fbde5`(0.3.1)→`a1e7c3b5`(0.3.2, S-FIX-W0c)→`15df9168`(r033)→`53cc9d61`(r033d)→**`73c80259`**（并入上游 hunks #45301/#40424、声明依赖 #45586/#45699；034-lock 四机 IDENTICAL） |
| `serving_chat.py` | `9b60a463…` | 0.3.4 现役 head 面 serving 正典 | 镜像 stock `b77a736c`→recipe 线 `3151a2ed`→**`9b60a463`**（W5 窗 t33-01a recipe-rebase 补丁 +333/−0，2026-10-24；此后原值承袭） |
| `page_map_export.py` | `c0dfe59a…` | 0.3.4 新增第 29 源：KV 池页映射引擎侧导出件 | **全新件，无任何旧形**（X6 bake R1 任务 8「A.2 制备」新建；env 门控 `DSV41_PAGE_MAP_EXPORT` 缺省关=零行为零开销） |

## 四、全备查件对照总表（含历史形，每件一行）

| # | 路径（仓内） | md5 | 身份 | 可用性口径 |
|---|---|---|---|---|
| 1 | `reconstruct/0.3.2/overlay/deepseek_v4_backend.py` | `a1e7c3b5…` | **0.3.2 正典**（S-FIX-W0c S3′+import 预检 9/9 形） | 0.3.2 整套重建用；**仅备查**，禁拼 0.3.4 镜像 |
| 2 | `reconstruct/0.3.2/image/files/python/sglang/srt/layers/attention/deepseek_v4_backend.py` | `a1e7c3b5…` | 同一 0.3.2 正典的 r032c **镜像面**载体（挂载面与镜像面一致的自证件） | 同上 |
| 3 | `reconstruct/0.3.4/overlay/`（三件） | 见 §三 | **0.3.4 三正典**（本批新增） | 身份对照/审读；运行以发布镜像+整面 29 件为准 |
| 4 | `overlay/o12c1-prod/`（30 件） | 对表 `prod/overlay-md5.txt` | **0.3.4 形产线 overlay 快照**（本批整面同步） | 站点部署落位件（`SGLANG_OVERLAY_DIR` 指向的目录内容） |
| 5 | `overlay/o12c1-prod/overlay-map.tsv` | `efd7d89b…` | 29 行平铺名→容器路径映射表（0.3.4 新锚件） | 随 overlay 目录一起用 |
| 6 | `prod/overlay-md5.txt` | `6c98cf8c…` | overlay 29 件对表清单（0.3.4 现役形） | `md5sum -c` 自验用 |
| 7 | `overlay/v4vl-79cafec0/`（28 件） | 指纹 `cbf986df` | VL V4.0exp 臂专用复原树（历史臂，与产线零交叠） | 仅 VL 复原实验用 |
| 8 | `reconstruct/0.3.4/adapter/`（71 \*.py+NOTES.md+清单，2026-10-31 回正批新增） | \*.py 面 `5c2c88eb…`（manifest-md5，count=71） | **0.3.4 前态面身份备查正典**（canon98 面全文，与供给位逐字节同） | 身份对照/审读；运行供给位=`deploy/adapter/`（逐件账 `0.3.4-MANIFEST.md5`），装钩器=`tools/bypass/`；子树内 `MANIFEST.md5`（72 条目）`md5sum -c` 自验 |

**旧形全文去哪取**（社区问得最多的三件，公开树此前无全文，现口径如下）：

- `15df9168`（0.3.3 r033 重建形 backend）：**补丁链重建**——取 #1 的
  `a1e7c3b5` 全文，打 `tools/patches/r033-a2.overlay-backend-fi072-wiring-v2.patch`
  （补丁头注 base=`a1e7c3b5`），产物 md5 应=`15df9168…`（断言见
  `tests/unit/test_r033_a2_polish_v2.py` BASE_MD5→PATCHED_MD5）。
- `b77a736c`（serving_chat 镜像 stock 形 / 0.3.4 期 02-04 机 worker 面）：**从
  发布镜像提取**（命令见下 §六）。
- `07cd5129`（backend 镜像 stock 原件，旧代镜像面）：同上从镜像提取（该 md5 在
  本仓任何文档中均无记载，属旧代镜像内部件，非本仓交付面）。

## 五、清单文件交叉说明（哪份清单管哪代）

| 清单 | 位置 | 适用代际 | 关系 |
|---|---|---|---|
| `deploy/prod/overlay-md5.txt` | 公开树 | **0.3.4 现役**（scheduler=`4a7822a6`） | 唯一现役对表件；本批自 `fd59c03b` 形重钉而来 |
| `fd59c03b…`（值） | 034-lock 档案（VERSION-LOCK/MANIFEST-034LOCK/gates-034/config-034/runbook-034 内引用） | 2026-10-28 锁档时点 | 锁档快照，档案不改值；与现役差=scheduler 单行 |
| `tools/packages/cfgmgmt/payload/out/overlay-MANIFEST.md5` | 公开树 | **0.3.2 期**（2026-10-13；29 条目+3 行头注，serving=`b77a736c`、scheduler=`5b6fe2a3`、含 map 旧形 `a8bf0fd6`） | 0.3.2 代逐件账；查 0.3.2 期历史值用它 |
| `deploy/reconstruct/0.3.2/MANIFEST.md5` | 公开树 | 0.3.2 重建包内件 | 只覆盖 reconstruct/0.3.2/ 包内文件（含 `a1e7c3b5` 两载体） |
| `deploy/reconstruct/0.3.4/MANIFEST.md5` | 公开树（本批新增） | 0.3.4 三正典 | 只覆盖 reconstruct/0.3.4/ 包内文件 |
| `deploy/reconstruct/0.3.4/adapter/MANIFEST.md5` | 公开树（2026-10-31 回正批新增） | 0.3.4 前态面备查副本 | 只覆盖 reconstruct/0.3.4/adapter/ 包内文件（72 条目；与 `deploy/adapter/0.3.4-MANIFEST.md5` 同口径共锚——\*.py 面 manifest-md5 同为 `5c2c88eb`） |

## 六、从发布镜像提取镜像面原件（写给社区用户，在你自己的机器上执行）

`serving_chat.py` 的 worker 面 stock 形（`b77a736c`）与 backend 旧代镜像原件
（`07cd5129`）都在镜像里、不在仓里。取法（示例，镜像 tar 来自网盘发布包
`images/`，先 `docker load`）：

```bash
# 1) 建一个不运行的容器并整树导出（无需 docker exec，也不必知道 site-packages 路径）
cid=$(docker create dsv41-sglang-optimized:0.3.4-x6bake-20261026)
docker export "$cid" -o rootfs.tar && docker rm "$cid"
# 2) 用 overlay-map.tsv 的容器内相对路径定位（serving_chat→srt/entrypoints/openai/；
#    backend→srt/layers/attention/），先列出再解出
tar -tf rootfs.tar | grep -E 'sglang/srt/(entrypoints/openai/serving_chat|layers/attention/deepseek_v4_backend)\.py$'
tar -xf rootfs.tar <上一步列出的两条完整路径>   # 或 tar -xf rootfs.tar -O <路径> > ./serving_chat.py
# 3) 对锚
md5sum ./sglang/srt/entrypoints/openai/serving_chat.py ./sglang/srt/layers/attention/deepseek_v4_backend.py
# 期望：serving_chat.py = b77a736c…（worker 面 stock 形）
#       deepseek_v4_backend.py = 07cd5129…（旧代镜像原件形）
```

网盘发布包（镜像 tar+仓快照+网关配方+网络层材料，约 14G）：夸克网盘
`https://pan.quark.cn/s/95fcb0efd1c4`（提取码 `QkfP`），下载后先按包内
`CHECKSUMS.manifest` 逐件校验，再按包内 `README-DIST.md` 走。**取件口径
（包内仓快照是哪个时点、镜像 tar 烘焙了多少 0.3.4 面、哪些件必须回仓取）见下
§七。**

## 七、网盘发布包取件口径（包快照时点、镜像面实测、包自足边界）

> 2026-10-31 判读处置窗立此节，回答接收端三个问题：包内仓快照是哪个时点、
> 镜像 tar 里实际烘焙了多少 0.3.4 面、起一套 0.3.4 栈哪些件必须从本仓取而
> 包内取不到。包本体（`README-DIST.md`/`CHECKSUMS.manifest` 的文案口径）
> 的修订属发布包刷新决策，不在仓侧改；本节是仓侧的权威对照说明。

### 7.1 包内仓快照时点：fb9c200（早于写入本件的 85aa172 批）

- 包内 `repo/luz-deepseek-flash-all-in-one-0.3.4re-snapshot.tar.gz` 打包于
  2026-10-30，内容时点=**fb9c200**（git 历史上 85aa172 的直接前驱）；85aa172
  备查同步窗（2026-10-31，即写入本件的批次，overlay 整面闭合+本件立档）
  **不在包内**。快照不含 `.git`（打包排除，包内 `README-DIST.md` 第 12 行声
  明），commit
  号以内容证据锚定：快照 `deploy/overlay/o12c1-prod/` 的五件旧值与本件 §二
  换血表「旧值（本批前）」列逐一吻合（backend `736fbde5`/model `fb87a7f0`/
  layernorm `bd473946`/scheduler `3db3275e`/serving_chat `c506bab5`），且快照
  自带 `deploy/prod/overlay-md5.txt` 为锁档形（自身 md5=`fd59c03b`，scheduler
  行=`3db3275e`）。
- **后果**：拿包内快照的 overlay 区跑 `md5sum -c` 不会全绿——用快照自带
  `fd59c03b` 清单跑=红 4 行内容旧（backend/model/layernorm/serving_chat）+1 行
  缺件（page_map_export，快照内无此本体），scheduler 行恰好同值通过；改用
  现役 `6c98cf8c` 清单跑=红 5 行内容旧+1 行缺件。这是**时点差**（快照在
  「清单先行、本体滞后」的中间态被打包），不是快照损坏，也不影响包内其余
  内容。
- **0.3.4 整面取件以 GitHub main ≥85aa172 为准**：取
  `deploy/overlay/o12c1-prod/` 整目录 + `deploy/prod/overlay-md5.txt`，自验
  命令见 §二（期望 29 行全绿）。快照内 overlay 区不要拿来当 0.3.4 面用。

### 7.2 镜像 tar 烘焙面实测（2026-10-31 tar 直读核验）

对包内 `images/dsv41-sglang-optimized-0.3.4-final-20261028.tar`（docker-save
OCI 混合布局；image id=`sha256:80e4c957…8f7d0`，与锁档档案所称 x6bake 面同源）
按 `overlay-map.tsv`（`efd7d89b`）29 条映射对全部 74 层核到最终态，读数如下：

| 类别 | 件数 | 明细 |
|---|---|---|
| 已烘焙至 0.3.4 权威形 | **21/29** | 与 `6c98cf8c` 清单逐件 md5 相等（含由顶层覆盖修到的 `layernorm_mhc=982a0ad0`、`deepseek_v4_model=5b5ced03`） |
| 旧形（在镜像、非权威值） | **3** | `serving_chat=b77a736c`（镜像 stock 形，=02-04 机 worker 面值，§二/§四）；`deepseek_v4_backend=07cd5129`（旧代镜像原件，§四）；`scheduler=85353fe3`（烘焙时点第三形：≠现役 `4a7822a6`，亦≠锁档 `3db3275e`，自烘焙层起未再更新） |
| 路径不存在 | **5** | 四件零字节占位（`dsv4_visible_window`/`deepseek_v4_vit`/`deepseek_v4_vl`/`mm_processor_deepseek_v4_vl`，权威形本即 0 字节，§二）+ `page_map_export`（实体件 `c0dfe59a`，镜像内连路径都没有） |

- **生产语义**：boot 时 `SGLANG_OVERLAY_DIR` 所指 overlay 目录**整面 29 件逐个
  盖入**容器（`prod-profile.env:12 COUNT=29` 钉面）——镜像只是**部分预烘焙**
  （21/29 预置到位，降低而非消除对 overlay 的依赖），整面 overlay 才是 0.3.4
  运行面。
- **「仅 load 镜像、不挂 overlay」不是受支持构型**：backend/scheduler 将以
  旧代形运行（非 0.3.4 栈），serving_chat 以 stock 形运行（=02-04 worker 面
  值，功能可用但非 01 机 head 面 0.3.4 形）。五件缺路径的行为面（2026-10-31
  对全部 74 层 tar 直读实测：五个模块名与 `DSV41_PAGE_MAP_EXPORT` 在镜像内
  全部 `.py` 与 sglang 两树**零引用**，阳性对照正常；镜像内烘焙
  `scheduler.py`（`85353fe3`）压根没有 PME 接线）：`page_map_export` 属 env
  门控件——挂 overlay 后由现役 `scheduler.py`（`4a7822a6`）提供接线，
  `DSV41_PAGE_MAP_EXPORT` 未设/空→`_make_page_map_exporter()` 返回 None、
  零导入零行为，开闸且缺件也只记 REFUSED 日志降级、不伤主流程；「仅镜像」
  态则连开闸入口都不存在。四件占位权威形即 0 字节空文件、全域零引用——
  镜像缺这四件路径与产线挂空占位在运行面无差。
- **接收端注意**：包内 `README-DIST.md` 对镜像的校验止于 image-id 级
  （load/tag/inspect），不含上述烘焙面读数，包内也无镜像内容级清单可供自行
  发现——故本节把 21/3/5 读数钉在仓侧；接收后如需自核，按 §六 的提取法在
  29 条映射路径上逐件 `md5sum` 对 `prod/overlay-md5.txt`。

### 7.3 包自足边界（包外取件清单）

全包任何位置都取不到完整 29 件 0.3.4 面（仓快照 23/29、镜像烘焙面 21/29）。
起 0.3.4 栈的取件组合=**包内镜像 tar（先按包内 `CHECKSUMS.manifest` 校验）+
本仓 main ≥85aa172 的 `deploy/overlay/o12c1-prod/` 整目录 +
本仓 main 回正批（2026-10-31）的 `deploy/adapter/` 整目录（含 `0.3.4-MANIFEST.md5`）**；
权重与 engram
本就不在包内，另按 [GETTING-STARTED §5](../docs/GETTING-STARTED.md) 从官方
渠道取。**adapter 面同理必须取自仓侧回正后形**：包内仓快照 fb9c200 早于回正批，
其 `deploy/adapter` 仍是漂移代（sitecustomize=`b4822e37`、无 `0.3.4-MANIFEST.md5`），
装钩器对其必 PANIC「面漂移」exit 9——照旧组合（镜像 tar+overlay 整目录）取件会
留下一块既过不了 0.3.4 清单验收也装不上钩的旧 adapter（2026-10-31 复核批补注；
发布包刷新窗应同步重切包，见 CHANGELOG 回正批「需随 0.3.4-MANIFEST.md5 重切包」口径）。
包内 `README-DIST.md` §四-4「overlay 本体未入公开树、`md5sum -c` 必红
属已知缺口」的警告描述的是 fb9c200 时点；85aa172 起该缺口已在仓侧闭合，包体
文案待发布包刷新窗同步（刷新后本节 7.1/7.3 的时点与缺口描述随之更新）。

## 八、红线（备查区使用纪律）

1. **旧形仍仅备查**：`reconstruct/0.3.2/` 全部内容=0.3.2 历史定版形，只用于
   0.3.2 整套重建（[DEPLOY-STEP-BY-STEP](../docs/DEPLOY-STEP-BY-STEP.md)）。
   **禁止**拿 0.3.2 overlay 增量件拼 0.3.4 镜像（overlay 与镜像代际绑定，
   混拼=无档混形）。
2. **0.3.4 正典现予备查，但不背书拼装**：本批起 29 件本体+三件正典全文在树，
   `md5sum -c` 应全绿；但拼源运行的正确姿势仍是**发布镜像
   （`0.3.4-x6bake-20261026`）+ 整面 29 件 overlay**，本仓对自拼栈不做运行
   保证。
3. **overlay 目录是快照不是档案库**：目录里永远是「当前现役形」；被换下的历史
   形靠（a）本件 §二 换血表的值注记、（b）git 历史、（c）cfgmgmt 0.3.2 期清单
   三条线索找回，不在目录里堆 `.bak`（产线侧的 `.bak-pre-*` 侧车备份一律
   不收，沿用 deploy/README.md「备份件注记」口径）。
4. **锁档档案不改值**：034-lock 系档案中的 md5 是时点快照，后代演进在本文注记，
   不回改档案。

## 九、术语与编号速查

- **BL/CFG 系号**：`tools/gates-034.tsv`（基线门）与 `tools/config-034.tsv`
  （期望参数）的行标识，全仓多处引用。
- **D 系号**（D8/D113/D118 等）：内部决策台账编号，台账未入公开树，语义随文
  给出；详见根 [README](../README.md) 版本系列节末注记。
- 「备查」=留档对照用、不构成运行分发面的件；「正典」=某代际身份的唯一权威形
  （以 md5 锚定）；「锚」=用来对表身份的 md5 值或清单件。
