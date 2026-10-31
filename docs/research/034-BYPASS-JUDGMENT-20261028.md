# BYPASS 合判档（G-M1 主门·冻结线判读）—— X5-BYP-A(MV-13) × X5-BYP-B(MV-14)

> **代际注记（2026-10-31 补，档内值零改动）**：本档为历史研判档案，文中面口径（件数/指纹/签名）均为 2026-10-28 时点值；现役正典面见 deploy/adapter/0.3.4-MANIFEST.md5（71 *.py/`5c2c88eb`/sitecustomize `45ca6e3e`），装钩后 99 武装面口径见 deploy/adapter/README.md。

> **判读身份**：BYPASS 合判代理（纯桌面，零引擎动作、零 sudo、零 git 提交——本档为唯一写件，主会话统一提交打标）。
> **法源链**：<内部授权链已裁剪（公开版）>。判读门=G-M1≤0.25 显著/0.25-0.50 灰带/>0.50 无效（冻结线）；采用纪律=显著带呈批建议入下一版面、本包仅存档与建议不擅自入产线（A 臂自检线 73s，>85s 呈报）；期望值唯一来源=0.3.4 固化四机亲核值。
> **输入档**：A 臂报告 `BYPASS-A-MV13-REPORT-20261028.md`+证据根 `logs/S-034-BYPASS-A-20261028/`；B 臂报告 `BYPASS-B-MV14-REPORT-20261028.md`+证据根 `logs/S-034-BYPASS-B-20261028/`；两臂派单 JSON（本合判 ask 原文）。
> **判读方式**：判读值全部自原始档独立重算/亲核（下述各表注档位行号），非转录派单面。

---

## 一、合判结论（落带）

**G-M1（B/A 残差比）= 1.971 / 74.191 = 0.02657 ≤ 0.25 冻结线 → 显著带（BYPASS 有效）**，且为显著线的 **1/9.4** 余量；机理预测带 B/A=[0.0136, 0.0682]（重估档预注册）**实测命中**（0.02657 落带内），×5 悲观推演 0.13 仍越线。**脚本报值 G-M1=0.9734 经亲算核实=改善率 (A−B)/A=0.973433，与残差比 0.026567 互补（和为 1），系同一判读的两面表述，落带判定一致（显著）**——长冷预填期（524288-token 长预填在飞）短请求 TTFT 中位 **74.191s → 1.971s（−97.3%）**，机制量（分块准入门 BYPASS=2048/缺省 SCAN 32）非吞吐尺度量。副作用面零反向：长 TTFT 对读（G-M2 记录面）B/A 中位 **1.0221 ≤ 1.03 门过**（轮1/2/3=1.0497/1.0182/1.0221；轮1 +5.0% 超单轮 3% 容差=暖起面注记项非门项）；S1 差分 liter B/A=0.9992 ≥0.97 ∧ DE +0.85% 在 ±3% 带内；EQ-S 夹心 **GREEN 6/6 双靴**（needle 至 599040）=零质量劣化。**同面性成立**（§三亲核），G-M1 判读有效。**A 臂自检线**：74.191s vs 预注册 ≈73s（快面推导锚 73.3s）=+1.2% 带内，**未触 >85s 呈报线→无判读降级注记**。

## 二、独立重算算术（自原始档，判读值唯一来源）

| 量 | A 臂（MV-13，基线自锚靴） | B 臂（MV-14，BYPASS 挂载靴） | 来源（亲读） |
|---|---|---|---|
| M1 有效点 | 12/12（3 轮全 round_valid） | 12/12（3 轮全 round_valid） | `S-034-*/phase3-payloads/m1/mixed-ttft-{A,B}.json` rounds[].points[].ttft_s（valid=true 逐点） |
| 点全集（升序） | {28.763, 28.817, 29.618, 58.764, 58.818, 59.619, 88.763, 88.818, 89.62, 108.764, 108.819, 109.62} | {1.325, 1.357, 1.412, 1.641, 1.701, 1.919, 2.023, 2.057, 2.229, 2.338, 2.389, 6.271} | 同上（与派单 m1PointsS 逐字同） |
| **中位** | **(59.619+88.763)/2 = 74.191s** | **(1.919+2.023)/2 = 1.971s** | 本合判 python statistics.median 亲算 |
| 长 TTFT（轮1/2/3） | 119.619 / 118.763 / 118.819s | 125.565 / 120.92 / 121.447s | 同上 rounds[].long.ttft_s |
| **G-M1 残差比** | — | **1.971/74.191 = 0.026567 ≤0.25 → 显著** | 本合判亲算 |
| 改善率（脚本报值核对） | — | (74.191−1.971)/74.191 = **0.973433 ≈ 脚本 0.9734 ✓** | 本合判亲算 |
| G-M2 记录面（长 TTFT 对读） | 分母 | B/A=1.0497/1.0182/1.0221，**中位 1.0221 ≤1.03 门过** | 本合判亲算 |
| sanity liter c1 早 | **3904.4** tok/s（≥3700 ✓） | **3901.1**（≥3700 ✓；B/A=0.9992≥0.97 ✓） | `perf/liter_524288_c1_early.json` tok_s_median |
| sanity DE c1 早 | **93.32**（锚 91.64，Δ+1.8% IN-BAND ✓） | **94.11**（Δ+2.7% IN-BAND ✓；对 A +0.85% 带 ±3% ✓） | `bench/dec48-early/de48_summary.json` tiers[0].agg_med + de48_summary.tsv 判读行 |
| EQ-S | GREEN 6/6 | GREEN 6/6 | `eqgate/eq_verdict.json`（两根亲读） |

**量具冻结亲核**：M1 探针 `tool/x5_mixed_ttft.py` 两证据根 md5 同值 `0b9a520001e2315695be732a20fe83e5`（=冻结锚 0b9a5200）；DE 量具 `sd_bench` 两臂 `sd_md5_pin=410f543d…`（de48_summary.json caliber 面钉行）；census `6e073acd`/liter `333033ce`/de_c48 `a337f64e`/正典 boot 件 `7cc69694` 两臂 phase0-[E] 锚列同——**零改动零降门**。

## 三、同面性判读（fidelity 差分校验——成立，G-M1 可判）

1. **起点存储态逐字同（四机×两靴 phase0 亲读）**：`S-034-*/phase0-pre/state-pre-check.log` [A] 段——boot=50700486（:12=r032c，:465=-eq 29）/env=ba4be586 59 键 kvl=1/tp4=e225c391（:87 v41+split=1）/guards=418414c3（:161 v41）/backend=73c80259/maplines=29/adapter=d52b0e3d·98/so=9eec98f8 ×4 机同；[B] 段 profile=1be1c37c（PinFix 新锚）+overlay md5sum -c 29/29 PASS；[C] 段 RepoDigest 80e4c957×4；[D] 段 slotlock FREE+网关 rc3.8.7 sampling-on（判读窗禁切律遵守：GW_SAMPLING_POLICY/K16 两键零触）。
2. **引擎面同形**：两臂 `phase2-boot/fidelity-gate-kvfp4.log` 均 `mode=v41 active=False installed=(none) r1_inkernel=True`（13 行）+passthrough 来源行在+fork-v4-fp4 active=True 计数=0+swa_fixed=2.53GB+repack bridge=0 → **忠实度硬门双 PASS（v41 快面，退化面零现）**。
3. **单变量差=B 臂仅三件**：env 第 60 键 `DSV41_PREFILL_BYPASS=2048`（60 键 BEN，固化 59 键 ba4be586 零写零翻）+sitecustomize 钩 dd69c59a+prefill_bypass.py c4875258（flip 日志四机同值亲读）+adapter staged 面 0beb4bee·99；宿主引擎文件零改（B phase0 引擎树锚 scheduler.py=85353fe3 :3831 靶函数在+overlay 29/29）。**生效直证**：`bypass-armed-gate.log` 四机 ARMED 行 ×2/机+refusing-to-arm=0×4 → 断言 PASS。
4. **判读窗纪律**：同日相邻（A 16:53Z 点火/B 18:22Z 点火，A 拆栈 17:52:30Z，B phase0-[D] settle 锚直证 639s 后点火），era 免疫+带免疫制式。

## 四、census 两靴汇总（NCCL 挂载位·D119-⑦ 收口）

| 靴 | TAG | G1 读数 | rc | 等待环 | 处置 |
|---|---|---|---|---|---|
| BYPA | mv13-bypa-purew1 | MemAvailable=7549MB < 8192MB（首读 7971MB） | 41 | 1200s 满未达 8400 预测线 | 未降门（G1=8192/A0H=6656 原样）、三处登记齐（`census/census-attempt-bypa-dw1{,-g1}.log`+`phase-timestamps.log:13-16` 时间线行+报告 §4.3）、零 misfire 行 |
| BYPB | mv14-bypb-purew1 | MemAvailable=7994MB < 8192MB（首读 8007MB） | 41 | 1200s 满未达 8400 预测线 | 未降门、三处登记齐（同形三处）、零 misfire 行 |

两靴均 W-a 制式单拍、四冻结旋钮（PROBE_FLOOR_MB=6656/BUDGET=700/STEPS=24/WINDOWS=1/RUNS=2）与 RB033/REPAIR 逐字同、量具三锚预核全中（6e073acd/941a853b/410f543d）、health=200 后发起（两臂 phase0-[E] 首读 113GB→census 时点 7.5-8.0GB=01 会话窗内构成性挤压直证）。**四窗 G1 拒序列=RB033 6918 → REPAIR 7537 → BYPA 7549 → BYPB 7994MB 同族**（水位 6.9-8.0GB 带）。

**D119-⑦ 收口条件成立（两靴均 G1 拒）→ 终局注记：NCCL 修复面=既有档案代理证据闭合、时长直读缺。**代理证据（设计窗亲读在档）：W-a 快锚 589.6ms/step（nccl RS 73.067/AG 65.174）vs X2-MV02 慢锚 783.5ms/step（RS 73.618/AG 66.770/kv_repack 119.146）——**RS/AG 时长快慢带基本不动（Δ<2ms/step），慢带超额 +194ms/step 落 kv_repack_fp4（0→119.1ms），与 v41 根因（repack 桥）互证=NCCL 集合通讯非慢带主载体**（档位：`ROOTFIX-CLOSURE-20261028.md:135`、`NCCL-WINDOW-DESIGN-20261028.md:160` 含 census 档案件路径）。修复后同基面时长直读缺→**专用窗留位**（01 内存腾挪 ~1.3GB 或低载窗择时；DELIVERY-NOTES P3 项同步）。

## 五、异项复核（A 4 项+B 7 项，全部=显示面/注记面非门项，处置认可）

| # | 异项（臂） | 合判亲核 | 处置 |
|---|---|---|---|
| 1 | 正典件 [arm] docker logs 取面=0+worker .Image f4cd1a98 与 head 80e4c957 不对称（A/B 同形） | 两臂 phase0-[C] RepoDigest 四机全 80e4c957 亲读；真值面=ignite 外层日志 59/60 行（fidelity gate [arm] 段亲读）；RB033 异⑦/W-b 披露⑦/REPAIR 异②同形族 | 显示面缺陷，无判读影响，认可 |
| 2 | teardown .so 身份行文件名笔误 libow→librow、行内 md5 空（A/B 同形继承） | A=`teardown-bypa.log:74` 正名补核 9eec98f8…在档；B=teardown 行确缺陷（teardown-bypb.sh:100），真值由 phase0（so=9eec98f8×4）+flip（flip-bypb.log:42-45 so=9eec98f8×4）正名读承载 | 显示面缺陷，身份链真值在档，认可 |
| 3 | M2 sd_bench 未跑（A/B 对齐：载荷单未列） | 两臂 payloads 单与时间线一致（非漏跑）；G-M2 记录面由 M1 探针轮内长 TTFT 三值承载（§二表） | 如实注记非门，认可；正式 M2 比值面=另呈位 |
| 4 | M1 残差列 1/12 点越带：6.271s vs 预测带上沿 5s（B，轮1/位30s） | mixed-ttft-B.json 轮1 位30 点=6.271 亲读；≫30s「适配未生效」诊断线远未触；ARMED 断言独立直证生效 | 方向一致，模型带余量收紧注记，非门项，认可 |
| 5 | G-M2 轮1 单轮 +5.0% 超 3% 容差（B） | 轮1 1.0497 亲算复核属实；轮2/3=+1.8%/+2.2% 带内，中位 1.0221≤1.03 门过 | 首轮 piggyback 暖起面注记，与机理预测同号，非门项，认可 |
| 6 | payloads-main.log 横幅残留「BYPASS-A」×2（B） | `payloads-main.log:1,72` 亲读确 2 处；数据面全 B（mixed-ttft-B.json arm:"B"+时间戳 18:32-18:52Z） | 编排件 sed 显示面缺陷，无判读影响，认可 |
| 7 | census G1 硬门拒（A/B） | §四表亲核 | 未降门+登记齐，收口注记成立 |

**misfire 台账代录核**：`logs/misfire-class.tsv:86-89` 两靴各两行（unknown 无日志行+post-teardown 行，clean-teardown/rc=0，D8 三查 PASS、boot :12 回置 50700486×4、bypass staged 面卸载回置、引擎文件零残留、gateway sampling-on）——代录齐、零 misfire 事件。

## 六、采用建议（呈批形·D119-⑤ 纪律：本包仅存档与建议，不擅自入产线）

**建议：纳入下一版面。** G-M1 显著带越线（0.02657，9.4× 余量）+副作用面零反向+EQ 零质量劣化+单变量证据链干净（同面性 §三）→ **BYPASS=2048（`DSV41_PREFILL_BYPASS=2048`，缺省 SCAN 32）晋级梯级③=组合形基座候选，建议随 0.3.4 下一版面固化**。固化路径五步（详见提呈结论）：①env 固化锚升格 59 键 ba4be586→60 键 BEN 面，连带 profile :8/:9 钉行与 BL 门期望表 env 键位重锚；②staged 三件正典入包注源 md5（sitecustomize/prefill_bypass.py/pyc）；③ARMED 断言（×2/机+refusing=0）入 boot 正典核对面与 doctor post-boot 面；④基线门期望表 BL 族新增 bypass 面；⑤生产设值时序=用户独立呈批位（W-d 点火时序留用户）。附带入下一版验证清单：M1 残差带余量收紧（单点 6.271s）、G-M2 首轮暖起 +5.0%、M2 sd_bench 正式比值面、NCCL 时长直读专用窗。回退路径已亲证：B 拆栈四机卸载回置+引擎文件零残留=单靴拆栈制式可逆。

## 七、合规注记

执行面零额外 sudo、容器/引擎启停仅授权窗内、判读窗禁切律遵守（网关 K16/GW_SAMPLING_POLICY 零触）、量具冻结全锚在档零降门、D56 engram 常驻、密钥零落盘、战役仓 git 零提交（本档写文件即止）。本合判为纯桌面读档判读，未执行任何引擎/容器/远程操作。

—— 0.3.4 战役 BYPASS 合判代理 / 2026-10-28 / 判读终态=**G-M1=0.02657≤0.25 显著带（BYPASS 有效，改善 97.3%）；同面性成立；建议纳入下一版面（呈批位）**。
