# cfgmgmt（P5 配置管理包）

> **代际声明（2026-10-30 加）**：本包内 env 树/boot 链指纹表（boot-chain.md5：
> r3-boot-arm `c051bb41` 等）为 **0.3.1 时点快照**，早于 0.3.2 终态（r3-boot-arm 生产形
> `20f22bc6`）。0.3.2 在役锚以 `deploy/reconstruct/0.3.2/` 与 `UPGRADE-0.3.2.md` 为准；
> 本包的 keydiff/keycheck/admregen/genmf 工具本身代际无关可照用，指纹表勿当 0.3.2 锚。
>
> TOOLS31-PACKAGE-PLAN-20261012 §二 P5 承载。整备位=`tools/packages/cfgmgmt/`；烘焙位=
> `/opt/dsv41/packages/cfgmgmt/`（env 树与 golden 树=配置参照载荷可入镜像；部署真源=
> 宿主 bind mount 面，镜像内只读参照——RECIPE 排除清单注记边界）。

## 为什么存在

0.3.1 的配置面=四级 env 树+boot 脚本链+overlay/adapter 两树+golden 参照集，判据散在
FORM-REGISTRY/TOOL-ANCHORS/adapter-sync 三处。本包收编为工具面：键面 diff、真键核、
复原序检查单、boot 链指纹表、golden 树、**ADAPTER-MANIFEST 重生成器**（CODE31 P1-②
陈旧清单闭合件）与 **env/overlay 双清单生成器**（CODE31 P2-8 集合指纹算式闭合件）。

## 用法

`bin/cfgmgmt help`；`bin/cfgmgmt selfcheck`；`bin/cfgmgmt keydiff <envA> <envB>`；
`bin/cfgmgmt keycheck --dump <printenv dump> --env <env 件>`；
`bin/cfgmgmt admregen --out <file>`（重生成）/`--check`（对活树校验）；
`bin/cfgmgmt genmf env|overlay --out <file>`；`bin/cfgmgmt restore --plan`。

## 构成（详=MANIFEST.md5；在役源对表=selfcheck/sources.tsv）

| 件 | 说明/来源 |
|---|---|
| env/（四件） | 50 键定型形 PROD-R51W5（15767aa6）+48/47/45 键回退三级件（FORM-REGISTRY §一 权威承接） |
| boot/boot-with-slotlock.sh（fcaed824）+boot-chain.md5 | P0 治理 wrapper+链指纹表（r3-boot-arm c051bb41/r3-stop 5ad87830/孪生 r3-boot.sh 29ccab6c） |
| env-keydiff.sh / printenv-keycheck.sh / restore-sequence.sh | 本包新件（键面差集/真键核/双复原义务十步检查单） |
| adapter-manifest-regen.sh + out/ADAPTER-MANIFEST.regenerated | **CODE31 P1-② 闭合**：活清单法重生成（125 件逐件 md5+六类分类+口径钉头行+SITECUSTOMIZE_MD5 变量位+PENDING-FL6-FINAL 回填位） |
| gen-manifests.sh + out/{env,overlay}-MANIFEST.md5 | **CODE31 P2-8 闭合**：正典集合指纹算式钉定（确定性/判别力/路径无关三性自检）；快照=env 0b8dcc8a（11 件）/overlay 73695876（29 件） |
| golden/flashinfer-golden（32/34 可读件+UNREADABLE-NOTE） | 树内自述 fi_version=0.6.18（**卡文「0.6.16 参照集」差异=呈裁注记位**）；2 件 root-0600 引擎写面零 sudo 不触碰已登记 |
| golden/r3-boot-arm.autotune-golden.diff | 再生模板（bb5c38ed；已对 c051bb41 基在役=留档） |

## 关键口径（本包钉定面）

1. **hook 面口径钉（CODE31 P1-③/D.3 主会话裁定承载）**：「29 活性 hook 面/40 挂装件」
   （24 env 键武装+3 COMMON_ENV 键武装+1 缺省开+1 常开对）——骨架「26」旧计弃用；
   admregen 输出头行恒载。
2. **sitecustomize 指纹变量位**：`SITECUSTOMIZE_MD5`（当前实测 d5dc42a4=FL6 两行钩子
   接线后值；**FL6 窗验证终值=回填位**）——工具锚引用变量不引硬值（改一处全同步）。
3. **FL6 入位态**：fl6_recall.py（b87cbb5e）+sitecustomize elif 钩子已入 adapter
   （2026-10-13 09:36Z FL6 窗在飞）——包按「已入位」终态收列；FL6 窗终后重跑 admregen
   =终态清单（PENDING-FL6-FINAL 行在档）。
4. **集合指纹正典算式**：`LC_ALL=C find <dir> -type f -print0 | sort -z | xargs -0
   md5sum | md5sum` 前 8 位——历史 20fa6a1d（overlay）为旧未记录算式值不再复现义务，
   下次对表窗以正典算式四机两遍核重钉（过渡注记入 TOOL-ANCHORS）。

## 排除了什么

- **在役件与回退件绝不入档**（归档 mv=禁；T5 联动律）——包内 env=整备副本非档案。
- **boot 治理 wrapper 真源恒在 tools/**（包内副本只随镜像；点火恒走真源——P0 治理）。
- **adapter/overlay 真源=宿主 bind mount 面**：镜像不烘焙两树（adapter-sync 权威源
  纪律+任务卡 §七.5 悬裁位维持）；包内 out/ 快照=参照件非供给源。
- **密钥零携带**（env 件=键面规格，无密钥值类；GW_API_KEY 类值面在 gateway 包模板律）。

## 红线注记

1. 回退四级链**动作序**=selfheal 包 rollback-chain.sh（相邻级强制+每级四查）——本包
   只管键面与指纹，动作面不双源。
2. 双清单快照=时点件：树变更→同日重生成（三联动律：MANIFEST+VERSION+TOOL-ANCHORS）。
3. printenv 真键核=只读判读（dump 由窗内采集；本包零容器操作）。

——TOOLS31 T4 P5 / 2026-10-13 案头整备。
