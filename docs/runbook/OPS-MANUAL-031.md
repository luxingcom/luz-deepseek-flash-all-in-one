# OPS-MANUAL-031 — LuZ-0.3.1 定型形运维手册（七章）· 2026-10-12

> **法源**：FINAL31-PLAN-20261012 §T3-4 + CODE31-REVIEW-PLAN-20261012 §4.2
> （两档=战役仓归档，不在本交付仓）。
> 落位=docs/runbook/（本仓；战役仓原位 docs/runbooks/）。
> **适用形（2026-10-14 升档=FL6 转正形）**：0.3.1 定型形现役=**51 键 ENV51
> `PROD-R51W5FL6-spec1.env` md5 2ac74586**（摘第 51 键 DSV41_FL6_RECALL_FIX=1
> 即休眠回 50 键形）+SPEC6+W5 件 32cf9abf+R1 八件面 4b40a123+adapter
> sitecustomize=55b1e412+fl6_recall=b87cbb5e（FL6 转正件）+overlay o12c1-prod；
> 三元组详见 `docs/registry/FORM-REGISTRY-031.md`。
> 红线：**02 机两守护（pid 3535/3536）绝对不动**；8898=测试靴面/8899=产线服务面
> 分面律（测试窗 boot 走 8898 槽，产线恢复恒 8899）；一切停机窗 OUTAGE 制+
> 先存后删+容器删除前必存 docker logs。

---

## 第一章 boot 规程

1. **点火前缀**：`ARM_TAG=<tag> ARM_ENV_FILE=<env 件> bash
   tools/boot-with-slotlock.sh bash ~/migrate-assets/bin/r3-boot-arm.sh`
   ——**ENV51 现役文件名=`PROD-R51W5FL6-spec1.env`**（51 键 2ac74586；50 键
   一级回退件名=`PROD-R51W5-spec1.env` 15767aa6）
   —— 靴槽锁（flock fd9 排他；`.slot-lock` 残文本仅取证）四机容器净核
   （docker ps 无 r3boot）后点火；**boot 命令 rc 透传**（wrapper 零行为扰动）。
2. **ARM_TAG/SPEC 注入面**：env 件经 `ARM_ENV_FILE` 逐行进 docker -e（四秩一致
   留痕）；`GATE_FORM` 显式带即激活 env-lint 拒绝门（r3-gate-env-lint.sh
   md5 a69f5f0e，红=拒起；EQ-03 后含 serve 禁参组合检查④——mixed-chunk/回放
   互斥、chunked 8192 判负档/16384 永禁值面命中即拒）。
3. **overlay 挂载面**：`SGLANG_OVERLAY_DIR=~/migrate-assets/v4vl/sglang-overlay.o12c1-prod`
   ——28 件映射逐行 -v 影子挂载（挂载计数断言==28；任一件缺=拒起；worker 远端
   在位核验前置拦）。
4. **沉降 600s 律**：前栈拆靴→本靴点火间隔 ≥600s（快速重启=首请求慢窗特异
   放大源，R1-DEAUDIT 档内不可分离结论；FULLGATE/REWORK2/COMBO 三窗 6/6 过门
   先例）。补足法=静候计时，禁以「容器已净」替代。
5. **warm 请求步 64k×2 第一动作**：boot rc=0+8899=200 后**第一动作**=warm
   请求步 64k×2（PROMO2 直证：跳过=首请求 940 级慢窗；COMBO 三靴 req2 俱
   5972.5-6104.3 健康带）。
6. **warm 门 4500/5000**：warm 请求步后 64k×3 中位 ≥4500 绿（<4500=红不起测；
   入役绿线 ≥5000——COMBO 三靴 6031.9/6083.9/6124.5）。
7. **四查**（boot 收口核）：①health GET 200；②printenv 四机真键核（键名+值
   与 ARM_ENV_FILE 逐字）；③横幅直读（adapter 29+ 横幅门行+W5/R1/O12 armed
   态+撤净态+**FL6FIX 横幅判读：四容器×2 行 patched+FL6FIX=1 4/4**——任一
   容器缺 patched 行或 FL6FIX≠1=FL6 面红）；④面指纹四机全等（adapter 面=
   定型形 md5 表对表）。伴：水位 sandwich（boot 前/中/后）+qmg 在役+02 机
   两守护 pid 双核。

## 第二章 复原规程（双复原义务）

1. **双复原义务序律（FULLGATE §六）**：**先撤件再产线 boot**——窗内任何
   部署件（adapter/overlay/env/serve 参）必须先复原至产线复原目标面，再点火
   产线 boot；禁「带窗件直接 bump 产线」。
2. **adapter 撤件**：`bash ~/luz030-opt-campaign/tools/adapter-sync.sh --apply`
   （权威源=<node01>:~/migrate-assets/dsv41/adapter；一切件变更先落 01 再
   下发）+`--prune` 需先存后删（差异件备份 `adapter-archive-<ts>/<host>/`）；
   撤后 `--check` 四机全等+`--expect` 锚断言（如
   `prefill_sp.py=0497e566`〔回退至 48 键形时〕）。
3. **fi_r1/ 撤件**：整目录撤除后残件计数=0 核（FULLGATE RESTORE 先例：面复回
   92d4c8ad+fi_r1 残件 0+归档 deploy/fi_r1-deployed-fullgate/）。
4. **env/serve/池门**：复原目标件与在役件全等直证（四机 md5 一致）+池门
   9,600,000 横幅直读。
5. **产线 boot**：沉降 600s→产线形 boot（CTN_PREFIX=r3prod/8899）→四查+smoke
   3/3→OUTAGE-END 宣告。容器删除前必存 docker logs。

## 第三章 回退链（51→50→48→47→45 键五级+FL6 面两级）

**回退件 md5 表**（R 级=回退动作序，逐级呈裁后执行；2026-10-14 升档=自 51 键起算）：

| 级 | 形 | env 件/md5 | adapter 面 | 动作（R.n） |
|---|---|---|---|---|
| L0 定型 | **51 键** | PROD-R51W5FL6-spec1.env=**2ac74586** | **55b1e412+b87cbb5e（FL6 转正）**+4b40a123+**32cf9abf**（W5 件）+overlay | —（在役目标） |
| L0.5 一级 | 50 键 | PROD-R51W5-spec1.env=15767aa6 | 55b1e412（51 键缺省=sitecustomize 休眠逐字原版）+overlay | **R.0 摘第 51 键 DSV41_FL6_RECALL_FIX=1 即休眠**→boot→四查+FL6FIX 横幅撤净直证 |
| L1 二级 | 48 键 | PROD-R1INK48L2PF6O12C1=8c8c166d | 4b40a123+0497e566（或 32cf9abf 键关=等价）+overlay | R.1 两键 unset（FP8/TG）→boot→四查+W5 横幅撤净直证；件级=md5 复原 0497e566 四机三步（adapter-sync） |
| L2 三级 | 47 键 | PROD-R1STDLL128L2PF6O12C1=99e7ec92 | 4b40a123+0497e566+overlay（O12 两键保留） | R.2 48 键基础上 unset DSV41_FP4KV_R1_INKERNEL →boot→R1 横幅撤净+t_r1_equiv 面=构造性回退（G5 四查绿先例 rw2/P3 两度） |
| L3 深回退 | 45 键 | PROD-R1STDLL128L2PF6=34977bf0 | 零 overlay+回退 scheduler（O12 撤） | R.3 零 overlay+以其 bump boot 一次+四查复绿（TOOL-ANCHORS:48-49 先例行） |

- **FL6 面两级回退**（独立于键级链）：一级=L0.5 摘键休眠（上表）；二级=**摘接线回
  2c4baad3**（目录级锚=sitecustomize 原形期；动作序详见 `deploy/adapter/README.md`）。

- **键级回退优先于件级回退**（键 unset 即回退、无件回滚需求——W5 卡 §四律）；
  件级回退=md5 复原四机标准三步（01 落件→sync --apply→--check 全等）。
- 每级回退后：warm 请求步 64k×2+warm 门+四查+smoke（与 boot 规程同律）。

## 第四章 规避律三条（PROMO2 直证依据）

1. **禁快速重启**：拆靴→点火 <600s=首请求慢窗（940 级）特异放大（R1-DEAUDIT
   快速重启×首请求档内不可分离；PROMO2 三窗 6/6 过门直证）。**注记**：首靴
   warm 探针门未跳过时快速重启面尚有档内不可分离项（DEAUDIT 结论），按最严
   律执行=恒沉降 600s。
2. **首靴 warm 探针门**：boot 后第一动作恒 warm 请求步 64k×2（跳过=首请求
   940 级慢窗、JIT 冷面放大；PROMO2 直证 run0=879.1/run1=938.9/run2=940.1
   中位 938.9<4500 红 vs warm 后 5972+ 绿）。
3. **warm 请求步 64k×2 常设**：每靴（测试/产线/回退）第一动作；≥4500 绿/
   <4500 红不起测；产线入役线 ≥5000。
4. **boot 期相位轨道锁入红带族（W5-PROMO 2026-10-13 新增规避律④；机理勘正
   2c9cc93：冷页面假说证伪，定谳收窄=四秩集合通信 peer-wait 相位轨道）**：
   双靴切换场景（验证靴→拆→短沉降→转正在役靴）出现实例级持续红带（64k
   prefill ~1000 tok/s=健康带 1/6，warm 五连发不恢复；metronome 4.0s/chunk；
   decode 免疫=图 replay）——**根因=boot 期初始化竞态锁入多稳态降级态（d 类
   代码级状态依赖，概率性 ~3/10 靴，重掷可愈）**，与 P3 960/R1-PROMO 940 同族
   同带（HOSTPROF trace 域）；pgmajfault 重面=首请求冷页伴生症状（绿靴 +9103
   ＞红带期 +3631 反相关直证）。**律：多靴切换沉降 ≥30min+warm 请求步加量
   64k×4（W5-PROMO2 直证重掷可愈）；红带现形即停靴取证（INCIDENT 面，取证段
   含四秩 census trace+GPU dmon 1s 采样=HOSTPROF P0 闭合钥匙）不连发重试**。
   **免费预测哨兵（V1 登记律）：boot 期 `Engine startup timings` 的
   target_verify 值>75s=红带靴预测（2/2 分离：49s 绿/102s 红）——每靴登记
   建预测线，红带根治件（comm 重建自愈钩子）=0.3.2 池首件候选**。

## 第五章 INCIDENT runbook 索引

| 事件族 | 档 | 处置要点 |
|---|---|---|
| dump 擦除（NFS dump 盘被清） | `docs/research/INCIDENT-DUMPWIPE-20261011.md`（战役仓归档，不在本仓） | 先取证（atime/挂载面）再恢复；处置后核对 dump 盘独立面 |
| E3A-T384 qmg 拆线 | `docs/research/E3A-DOSE-RECALL-RESULT-20261011.md` §一/§四.1（战役仓归档，不在本仓） | qmg 6000 硬门触发=按序拆线（非引擎崩/非楔死/memcg 四机 0 行核）；384 档除名先例 |
| 2218 翻转家族 | `docs/incidents/INCIDENT-20261007-ENVDEG-PREFILL-2X.md` 等（战役仓归档，不在本仓；grep「2218」族） | 翻转事件先档后处置；macgw /30 迁专口后 MPI wireup 绿=遗留①闭 |
| GID 环回法 | `tools/packages/fabric-net/payload/guards/fabric-gid-heal.sh`（FABRIC-SELFHEAL-DESIGN-20261008 配套：四前置+Tier1/2）+同目录 `fabric-restore-gate.sh`（Phase1 只告警）+期望态 `tools/packages/fabric-net/payload/weave/topology.json`（三件均在本仓 fabric-net 包） | GID 断言块（r3-boot-arm 16 口 idx3）红→环回修复→guard F-G1 判值四机 GREEN 复核 |
| 楔死处置 | oom-gate/watchdog 配套（oom-gate=`tools/packages/selfheal/payload/oom-gate/`；watchdog=`deploy/bin/r3-watchdog.sh`；FINAL31 §T4-1 修复自愈工具包） | **D8 三查**（dmesg/memcg/engine 日志三面）+**不重试律**（楔死禁盲目 reboot 重试，先三查定面） |
| KV-LIFE 客户端哨兵 | `logs/KV-LIFE-20261009/READINGS.md` §0（战役仓日志归档，不在本仓） | 7168/6300 低水位灌批正确拦截=设计动作非事故 |

## 第六章 禁键清单+两守护+分面律

- **永禁**：`--chunked-prefill-size 16384`（死刑令，COMBO 判负链）；**判负不进形**：
  `--chunked-prefill-size 8192`（0.3.2 观察位，非同具形不可平移定谳）；**观察位**：
  bypass/A23-β TBO/CG-β（t4-patch 形 0847a7cd 留库）。
- **测量键零携带律**：产线 boot 禁带测量键（CHUNK_WALL/wallhook=0 直证法）。
- **unset 即回退族**：FP8/TG/R1_INKERNEL/SPLIT（spark_prefill_split 留库不转正
  ——SPLIT 键禁设；6498aa39 在库复活位=定型微调/0.3.2 单臂差分呈裁）。
- **02 机两守护（pid 3535/3536）绝对不动**（COMBO/R1 窗窗前窗终双核先例）。
- **8898/8899 分面律**：8898=测试靴槽（窗口臂 boot）；8899=产线服务面（复原
  后恒此口；四查 health GET 200 靶口）。**8899 产线规程注记（2026-10-14 补）**：
  8899 禁流量红线下，产线健康判据=**GET 200+四查**（本机只读探针；经网关面
  =`8001 /health` 口径）；**禁压测类/批量类请求**打点产线。

## 第七章 量具锚点引用

- 一切工具以战役仓 `docs/TOOL-ANCHORS.md` 表内锚（md5+用法+在役线）为准（该档
  =战役仓归档，不在本交付仓）；**本仓对应权威面**=`docs/registry/FORM-REGISTRY-031.md`
  §二（boot 链/adapter/overlay 指纹）+`tools/packages/` 五包各自 `MANIFEST.md5`
  （md5sum -c 自验）。本手册不复制工具 md5（防二次漂移）。
- 本手册配套三件：白盒矩阵
  `tests/whitebox/CODE31-WHITEBOX-MATRIX-20261012.md`（14 件自检红绿基线+判别力
  反例抽查法，本仓实位）、审查报告 `docs/release/CODE31-REVIEW-REPORT-20261012.md`
  （发现分级+回退键注记 P2-9；战役仓归档，不在本仓）、形档案
  `docs/registry/FORM-REGISTRY-031.md`
  （三元组权威面）。
- boot 哨兵（boot_sentinel.sh+anchors.tsv）：定型三形锚待 QA31 健康靴回填
  （W-1；遇未知形=ANCHOR-UNKNOWN 横幅不判快慢=设计安全态）。

——CODE31 T3 文档窗 / 2026-10-12（七章骨架+先例锚；数字源=窗档锚点引注制）；
2026-10-14 E2 固化窗升档（头注适用形=ENV51+第一章 ENV51 文件名与 FL6FIX 横幅
判读+第三章 51→45 五级回退链+第六章 8899 产线规程注记；正文与战役仓
docs/runbooks/ 版同源同步——双档差异仅仓定位注记行）。
