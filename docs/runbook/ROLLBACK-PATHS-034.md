# 回退降级路径正典：双路（ROLLBACK-PATHS · 034-lock 束配套件二）

> **性质**：ROLLBACK-TO-033.md 的姊妹件（该件=路 A 程序正典；本件=双路总装+路 B 程序+降级面映射）。
> **回退=用户明示运营动作**（0.3.4 冻结声明 §九；033 锁档 §九同律），本件只载程序与判读映射，
> **不构成执行授权**；一切回退窗须另获用户明示批文后实施。
> **建窗法源**：<内部授权链已裁剪（公开版）>（守卫与模块自诊断完善·降级运行大声警告硬性要求+
> 回退降级路径正典）。
> **当前生产面（本件建窗时点）**=W-f 调优终面：产 env **61 键** `4370aab9…`（D121 BYPASS 60 键
> + W-f I8 采用尾行 `DSV41_ENGRAM_CACHE_GIB=2`）×4 机同步 / prod-profile.env `77d7fa67…`
> （:8/:9 钉 4370aab9/61）/ 引擎在役（WD-034TUNED-20261029-151019，横幅 8/8 全 cache=2.0GiB）。
> **W-d 修复面**（路 B 回退目标）=60 键 env `f9fec92f…`（尾键 DSV41_PREFILL_BYPASS，无 I8 尾行）
> / profile `a15da805…`（:8/:9 钉 f9fec92f/60）——两形差量**恰 3 行**（env 尾 1 行+profile :8/:9
> 两行，本窗 diff 亲证在 §四-2）。

---

## 一、双路总览

| 路 | 目标态 | 承载件 | 适用判读 | 量级 |
|---|---|---|---|---|
| **A** | **0.3.3 全回退**（033-lock 检查点全态） | `archives/034-lock-20261028/ROLLBACK-TO-033.md`（§一七面差表+§二程序；本件不重复，只补预演命令） | 0.3.4 基面本身失效（引擎/overlay/镜像族问题非单键可救）或用户明示版本级回退 | 七面差+三面零回退（boot+overlay **必须同窗联动**） |
| **B** | **W-d 修复面部分回退**（仅撤 W-f 调优面 I8 采用，0.3.4 基面全保） | 本件 §二（面単差回置程序） | 调优面（I8 CACHE_GIB=2/engram 面）判读问题：如 DG4 engram 横幅面在 2GiB 面难闭合、或用户明示撤调优增益（c16 −3.2% face 效应注记=WD-TUNED §六-1） | **恰 3 行差**（env ×4 机+profile 01+锚表重钉），全链一键可逆 |
| — | DG1/DG3（v41/fork 面）、DG2（BYPASS 面）、DG5（池指纹）、DG6（digest） | **非回退目标**（0.3.3 无 BYPASS、v41 两版同构——见 §三逐行） | 面级重钉即愈，勿越级回退 | 配置行级 |

**两版关键事实（判读防误）**：0.3.3（RB033/W-b 族）与 0.3.4 的 KV 布局**同为 v41 快形**
（ROLLBACK-TO-033 §二-5 注记「回退≠回 fork」）；BYPASS=2048 为 0.3.4 独有采用面（0.3.3 无）；
I8 尾行为 0.3.4-W-f 独有（W-d/0.3.3 均无）。故 DG1/DG3/DG2 面**不构成任何一路回退的必要条件**。

## 二、路 B 程序（W-d 面单差回置；获用户明示后实施）

**前置**：①用户明示批文（回退窗授权）；②引擎态盘点——env 为 boot 时 ARM 注入面，**回置须拆栈
重点火方达引擎**；在役栈拆栈走专门窗（`CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash <assets-root>/bin/r3-stop.sh`
D8 三查：四机 r3ctn=0+8899/8898=000），**窗外严禁启停**；③预演（§四-2）全对后动手。

1. **产 env ×4 机回置 60 键形**（01 先行+02-04 ssh BatchMode 同形）：
   `cp -p <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env.bak-pre-pathB-$(date -u +%Y%m%dT%H%MZ)`
   然后**直覆 W-d 快照**：`cp -p <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env.bak-pre-deopt-adopt-20261029 <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env`
   （或等价 sed 删尾行：`sed -i '${/^DSV41_ENGRAM_CACHE_GIB=2$/d;}'`——效果同，直覆优先=逐字节保真）。
   **门**：逐机 `md5sum …CBX1A-CERTM-spec1.env`=`f9fec92f79a99f762b33de88ce533065`；键计数=60。
2. **prod-profile.env（01 专属）:8/:9 回钉**：直覆 `cp -p <assets-root>/prod/prod-profile.env.bak-pre-deopt-adopt-20261029 <assets-root>/prod/prod-profile.env`
   （:8 PROD_ARM_ENV_MD5=f9fec92f…、:9 PROD_ARM_ENV_KEYS=60 两行差；:10 PROD_SPEC_EXTRA_ARGS 零改——
   args 采纳项为零，WD-TUNED §一）。**门**：md5=`a15da8051177ffbc2471c4b0a4dbfe66`。
3. **锚表重钉（仅值重钉，禁整件回拷 .bak——见下注意）**：`tools/config-034.tsv` 六处——
   CFG-04→`f9fec92f79a99f762b33de88ce533065`、CFG-05→`60`、CFG-12→`a15da8051177ffbc2471c4b0a4dbfe66`、
   CFG-13→`PROD_ARM_ENV_MD5=f9fec92f79a99f762b33de88ce533065`、CFG-14→`PROD_ARM_ENV_KEYS=60`、
   **删除 CFG-65 行**（I8 采用键行，W-d 面无此键）；`tools/gates-034.tsv` 两处——BL11 五检回四检
   （md5=f9fec92f/60 键/v41 行=1/BYPASS 行=1，删 CACHE_GIB 第 5 检）、BL16 profile 期望回
   `a15da805…（D121 重钉形）`。
   **注意（防自锚假红）**：两 tsv 的 `.bak-pre-deopt-adopt-20261029`（config=c44dd620/gates=c87f8a06）
   是守卫降级窗**之前**时点形——其 CFG-62..64 工具自锚=旧值且无 CFG-66/67 新行，**整件回拷会把
   工具锚面一并回滚致 doctor CFG-62..67 假红**；故锚面一律按上列值行级重钉。
4. **自检**：`bash tools/doctor-034.sh --preflight`（期望 0 FAIL 0 DEGRADED；boot 双合法归一
   CFG-01 仍在合法集——boot 面路 B 零触碰）+ `bash -n` 两 tsv 无语法面问题（tsv 非脚本，跳过）+
   `bash tools/deploy-034.sh --dry-run` 全链打印走通。
5. **拆栈+重点火+验收**（窗内）：r3-stop D8 三查 → `bash tools/deploy-034.sh --arm-tag PATHB-<ts>`
   （S6 门全绿；**engram 横幅 8/8 应回 `cache=1.0GiB (3946672 slots, 16-way, 4.1% of owned rows)`
   形**=E0/W-d 面活体直证，对 2GiB 面 7893344/8.2% 恰减半）→ `bash tools/verify-034.sh --smoke`
   （阈值面不变；liter/DE/500q/EQ-S 四绿）。
6. **台账+报告**：misfire 台账点火行代录+回退窗报告落 `docs/plan/034-W1/`（含回置前后 md5 对表+
   .bak-pre-pathB-* 留证链）；MANIFEST 追记按「重封包相」处理（D124-④ 次序，勿在回退窗内越序）。

## 三、降级运行警告面 → 路径映射（doctor 降级面清单 DG1..DG6 ↔ 本件双路）

| doctor 登记 | 现象（doctor 输出行） | 影响定量（警告框内文） | 处置路径 |
|---|---|---|---|
| **DG1** | fork-v4-fp4 active（活体行/配置行在位） | 慢带 −15~19%（KVARM1 实测 liter C1 −15.7%/DE c1 −7.5% vs RB033） | **非回退目标**：三联面行级重钉（env :62/tp4 :87/guards :161→v41）+拆栈重点火；两版均 v41 快形，路 A 不解决此面（fork 非版本差面）；仍 fork=停窗呈报 |
| **DG2** | BYPASS 未武装（env :63 键/sitecustomize 钩 dd69c59a/活体 armed<8·refusing>0） | 首键 TTFT 回 74s 慢带（74.191s→1.971s=97.3% 改善丢失，MV-13/14） | **非回退目标**：D121 采用面行级重钉（env :63 键+adapter 钩形，正典副本 tools/bypass/ 互证）；**路 A 反而丢本面**（0.3.3 无 BYPASS）——除非用户明示版本级回退 |
| **DG3** | v41 键/终态面缺失（三配置面或活体行<4） | 同 DG1 慢带 | 同 DG1（三联面重钉）；注入链断=CFG-48 行单独定位 |
| **DG4** | engram 横幅 <8 | engram 装载面异常（七字段核对面=正典件 [5] 段） | 先正典采集件 [5] 段分机定位（io_threads=96/packed=True 族）；若确系 2GiB 扩容面（I8）难闭合→**路 B**（回 W-d 1.0GiB 面）+呈报；非 I8 面（装载失败/层缺）路 B 无效 |
| **DG5** | 池指纹漂移（full/mtt/mrr/ctx/cps 任一缺） | 912.25 不变式守护面（9600000/16/600000/4096；needle 599040 帧依赖） | doctor CFG-49..53 行定位（env/server-args 面）行级重钉；**伴随 overlay 面漂移**时涉路 A #5/#6 联动面（ROLLBACK-TO-033 §一 5/6 行 boot+map 同窗联退注意） |
| **DG6** | 镜像 digest/身份面失配 | 镜像被覆写/野栈占 8899——载荷读数全部不可信 | `docker pull` 正典 tag 重拉复检（IMG-1 门/CFG-28）；registry 两版共存零删除=**自愈面，A/B 两路均不适用**；野栈占用=P0 禁双靴呈报 |
| （I8 面） | CFG-65 行 FAIL（I8 采用键缺失/=2 尾行不在） | c2 +4.86%/c1 +2.55% 增益面失效回 1.0GiB（DEOPT-I8 门值） | **非降级面**（FAIL 行自反馈承载）；处置=env 尾行回置（与路 B 第 1 步同形）或维持 1.0GiB 面呈报定夺 |

**映射律**：六降级面中**仅 DG4 可能导向路 B**，**无一面以路 A 为首选**（路 A=版本级用户明示动作）；
一切面先行级重钉→复检（doctor 两模式 0 FAIL 0 DEGRADED）→仍不闭合才升级呈报。

## 四、每路预演命令（全只读；不构成执行）

### 4.1 路 A 预演（程序体=ROLLBACK-TO-033.md §一/§二；此处=差量面亲核）

```bash
# boot 链 .bak 族在位与 033 锚（20f22bc6；:465 计数门 -eq 28 时代形）
ls -la <assets-root>/bin/r3-boot-arm.sh.bak-pre-x6*
md5sum <assets-root>/bin/r3-boot-arm.sh.bak-pre-x6          # 期望 20f22bc6…
# overlay 三件 .bak 族与 033 锚（backend 53cc9d61；map 回 28 行；01 清单 d5048485）
md5sum <assets-root>/v4vl/sglang-overlay.o12c1-prod/deepseek_v4_backend.py.bak-pre-x6   # 53cc9d61…
awk -F'\t' '!/^#/ && NF>=2 && $1!="" {n++} END{print n+0}' <assets-root>/v4vl/sglang-overlay.o12c1-prod/overlay-map.tsv.bak-pre-a2   # 期望 28
md5sum <assets-root>/prod/overlay-md5.txt.bak-pre-x6        # d5048485…
# 差量面其余（env/tp4/guards/profile）.bak 链速查=ROLLBACK-TO-033 §三表（现场 ls -la 亲核为准）
# 回退演练门（不点火）：bash tools/deploy-034.sh --dry-run   # S1 只读照跑（033 形下 CFG 面预期红=回退态自证，非漂移）
```

### 4.2 路 B 预演（本窗 2026-10-29 亲跑全对；三行差直证）

```bash
# ① env 单行差（期望恰 1 行：63a64 尾增 DSV41_ENGRAM_CACHE_GIB=2）
diff <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env.bak-pre-deopt-adopt-20261029 <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env
md5sum <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env.bak-pre-deopt-adopt-20261029   # f9fec92f…=W-d 目标锚
# ② profile 两行差（期望恰 :8/:9）
diff <assets-root>/prod/prod-profile.env.bak-pre-deopt-adopt-20261029 <assets-root>/prod/prod-profile.env
md5sum <assets-root>/prod/prod-profile.env.bak-pre-deopt-adopt-20261029             # a15da805…
# ③ 02-04 同形在位（期望四机同值 f9fec92f）
for h in <prod-host-02> <prod-host-03> <prod-host-04>; do ssh -o BatchMode=yes -o ConnectTimeout=8 $h \
  'md5sum <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env.bak-pre-deopt-adopt-20261029'; done
# ④ 锚表差量面清点（期望恰 CFG-04/05/12/13/14 值差+CFG-65 新行）
diff <(grep -v '^#' tools/config-034.tsv.bak-pre-deopt-adopt-20261029) <(grep -v '^#' tools/config-034.tsv)
diff <(grep -v '^#' tools/gates-034.tsv.bak-pre-deopt-adopt-20261029) <(grep -v '^#' tools/gates-034.tsv)
# ⑤ 键计数面（W-d=60；现面=61）
grep -c '^[A-Za-z_][A-Za-z0-9_]*=' <assets-root>/dsv41/env/CBX1A-CERTM-spec1.env.bak-pre-deopt-adopt-20261029   # 60
```

## 五、红线与档面

- 回退窗红线随身同战役律：零 sudo（boot 链 drop_caches 既有制式除外）/零 git 写/引擎启停=获批
  回退窗内（窗外严禁）/量具冻结零改动/<gateway-host> 两键不触/报告密钥掩码（本件仅 md5 与键名，无 env 内容引文）。
- 路径与档源索引：路 A=`ROLLBACK-TO-033.md`+`archives/033-lock-20261026/` 束；路 B 差量源=
  `WD-TUNED-FINAL-20261029.md` §一/§九（回退路径段）+`logs/S-034-DEOPT-I8-20261029/DEOPT-I8-REPORT-20261029.md`
  （I8 A/B 门值）；降级面检测=tools/doctor-034.sh（GUARD-DEGRADED-20261029）；自诊断=tools/selftest-034.sh §D。
- 本件锚：config-034.tsv CFG-67（md5 锚钉）；档内值以建窗时点亲核为准，回退实施窗须先重跑 §四预演复核。

——守卫降级完善窗（GUARD-DEGRADED-20261029）/ 2026-10-29 / 只载程序不构成执行授权。
