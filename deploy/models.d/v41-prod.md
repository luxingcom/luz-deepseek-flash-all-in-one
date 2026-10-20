# v41-prod · DeepSeek-V4.1-Flash（生产在役）注册卡 — 2026-10-06

> **【0.3.1 交付仓注记 2026-10-13】本卡 §c/§d 的「现役产 env/boot 形」为 0.3.0-R1
> 时代快照（36 键 b7e318e0+五参+sitecustomize 91adc83d），已被 0.3.1 定型形取代：
> 现役=50 键 PROD-R51W5-spec1.env（15767aa6）+SPEC6 六参+sitecustomize 见
> `deploy/adapter/README.md` 时点注记；权威三元组表=`docs/registry/FORM-REGISTRY-031.md`
> §一，boot 链实参=`deploy/bin/r3-boot-arm.sh`。§a 权重身份指纹/§b 四机路径/§e 锚带
> 不受影响（权重未变更）。历史行原样保留（快照不回改律）。**

> **【0.3.2 现役权重注记 2026-10-20】本卡 §a/§b 的 V4.1-Flash 476G 指纹与路径为
> 0.3.1 历史。0.3.2 现役已切 `DeepSeek-V4.1-Flash-1017`：84 文件 /
> 510,311,045,870 B；`config.json` sha256 `8be45ce0476004a3…`；四机 rank 映射
> 01=r0/02=r1/04=r2/03=r3；新 engram=`~/dsv41-engram-1017`（8 分片 /
> 202,758,065,168 B）。逐文件 SHA256SUMS、NFS 布局、engram 生成工具与哈希=
> `deploy/reconstruct/0.3.2/weights/`。旧模型/旧 engram 原样保留可回退。§c/§d
> 的 env/boot 形亦让位于 0.3.2 重建包；本卡余下内容按快照不回改律保留。**

> models.d 注册表卡。字段制=MULTIMODEL-GOV-CARD-20261004 §2.4（案头草案定稿形）；
> 闭案法源=CD3-LINED-CARDS-20261006 卡二。誊录源=CHECKPOINT-LUZ030-R1-20261005
> §一/§二/§三（v41 指纹与锚带）+GOV-CARD §1.1/§1.3（四机拓扑/身份指纹）。数字零手誊。

## §a 身份指纹

| 面 | 值 | 源 |
|---|---|---|
| config sha256（前 16，注册主键） | `8be45ce0476004a3` | GOV-CARD §1.3（2026-10-04 四机实测） |
| model_type / 层数 / 体积 | deepseek_v41（嵌套 text 40 层 + vision 32 层）/ 476G | GOV-CARD §1.3 |
| sitecustomize | `91adc83d`（R1 变体，四机现役）；回滚锚=bak-pre-r1 `8c2c8b14` 四机在位（=v2 形回滚锚） | CHECKPOINT §一/§三 |
| prefill_sp | `0497e566`（零改动沿 0.3.0） | CHECKPOINT §一 |
| hc_fused（adapter 件） | `59df1cc9`（三钉重锚后值，纯 Triton 件） | H1-HCFUSED-20261001 |
| 产形三锚（final-verify 面值） | `91adc83d`/`0497e566`/`59df1cc9` ×4 机 | O13-VERDICT §三（final-verify GREEN ×2 轮） |
| 七件引擎面 md5 | seam `9c06b11a` / admission `7769a33e` / triton `24d96f9d` / reference `29861e87` / selection `35905ebe` / p12 `fe7d8053`（量具件 ro1 工作副本 `bd232c3d` 离线） | CHECKPOINT §一 |

## §b 四机路径（拓扑）

| 机 | 形态 | 源 |
|---|---|---|
| dgxspark01 | /data 本地完整（V4.1-Flash 476G） | GOV-CARD §1.1 |
| dgxspark02 | /data 本地完整（V4.1-Flash 476G） | GOV-CARD §1.1 |
| dgxspark03 | 引擎实读 **dsv41-net NFS**（476G；nfs4 vers=4.2,ro,hard,fatal_neterrors=none——读探测 OK/写 ro 拒=设计内）；另有 190G 部分副本在位 | CD3 卡二拓扑表+R0-RECOVERY C9+GOV-CARD §1.1 |
| dgxspark04 | 同 03（dsv41-net NFS 实读+190G 部分副本） | 同上 |

- 容器内 checkpoint 面=`/data/models/DeepSeek-V4.1-Flash`（GOV-CARD §2.1；03/04 生产实际挂载路径未核=GOV-CARD §7-Q2 遗留，本卡按「03/04 引擎实读 NFS（dsv41-net 476G）=产先例」口径登记——CD3 卡二）。

## §c env 模板指针

- **现役产 env**=`~/migrate-assets/dsv41/env/PROD-R1STDFORM-spec1.env`（R1 标准形 **36 键**=31 基线+R1′ 五键；md5 `b7e318e0`，全值 `b7e318e0c9525507c9b03825ea31ecb9`）——CHECKPOINT §一+QAVLW2 CARD.md。
- 回滚族 v2 31 键=`~/migrate-assets/dsv41/env/PROD-RS-spec1.env`（md5 `acb43d8b`；rollback-archive-r1prime5/ + go/ 隔离档）——CHECKPOINT §三。

## §d boot 形

- **r3prod R1 形**：`~/migrate-assets/bin/r3-boot-arm.sh`，参数面=ARM_ENV_FILE=`~/migrate-assets/dsv41/env/PROD-R1STDFORM-spec1.env` + CTN_PREFIX=`r3prod` + API_PORT=`8899` + SPEC=1 + SPEC_EXTRA_ARGS 五参（`--prefill-decode-interval 16` `--max-queued-requests 32` `--min-free-slots-delay 1` `--enable-decoder-swa-bounded-replay` `--reasoning-parser deepseek-v41`）；TP4 四机——CHECKPOINT §一+logs/VLW2R-20261005/seg4_restore_vlw2r.sh（在档实例）。
- 池指纹=max_total_num_tokens=**9,600,000** / context_len=**600,000** / max_running_requests=**16** / chunked_prefill=**4096**——CHECKPOINT §一。
- 横幅合同（每靴必现）：`banner complete: 29 gates` / `ENGAGED (tier=triton; prefill_consume=stock` / `consume=gate=1 tier=triton prefill=(off)` / `SELF-CHECK PASS (10/10` / `AdmissionDecision(form=r1 limit=600,000 armed=True`；反面四模式全 0——CHECKPOINT §一。

## §e 锚带（CHECKPOINT §二誊录；v41 专属禁外推）

- GSM8K n500 **0.968**（err=0）；canary n200 **0.98/0.975**（两窗）；DE c1 中位 **79.19**（c1 带 **[76.9,80.0]**，R1CERT4 G5——GOV-CARD §2.4 §e 注）。
- accept **3.075/3.093**（窗 **[2.90,3.30]**——GOV-CARD §2.4 §e 注）；PR4k **3802.1/3615.4**（第五火 E′+GO2）。
- M1 里程碑 MET：64k PR=**4886.3**≥4.5k；M2 **4752.1**<5.5k（0.3.1 目标，A23-α 线）。
- census 锚：bs=16 DRAFT 图内 **99.932%**/VERIFY **99.998%**（G-2 闭案）；步墙 c1 **42.14ms**→c16 **226.20ms** 阶梯（MEAS 五窗）。
- KV/水位池指纹=**890.00 B/token** fp4KV 四缝（GOV-CARD §2.4 §e）。
- 纪律：本带与 V4.1 暖态产形绑定，禁向 0731/VL 外推（GOV-CARD §3.3+MODEL-COMPAT-TASKBOOK §一.5）。

## §f 开放项

- **零回归证明件链**（v41 红线面）：每新模型窗前后 8899 复原验证链在档——T11 §六 / T13 §六 / O10A / O10B / O13 final-verify GREEN（三锚 `91adc83d`/`0497e566`/`59df1cc9` ×4+产 env `b7e318e0`/36 键+禁键 0+r3boot 残留 0）。
- 回滚族三件不可失：bak-pre-r1 sitecustomize=`8c2c8b14` / 31 键 v2 env=`acb43d8b` / 复原链法源=RE-CERT-CARD-4 §七+R1GO2 段5——CHECKPOINT §三。
- 0.3.1 定板关联（非本卡缺口）：定板法式=CD3 卡三（指纹总账卡+锚表+回滚族+tag）。

## §g 冷缓存注记

- 03/04=NFS ro 实读（nfs4 ro hard；R0-RECOVERY C9 读探测）=**产先例**（生产长期在役=暖态；s/it≤6 与步墙 ~50ms 带为 V4.1 **暖态标定**——GOV-CARD §2.3 注 4）。
- 切回门（新模型窗后回产放行）=四件全绿：canary n200 ≥0.95+DE c1 锚位等（[76.9,80.0]）+漂移三查+复原复验链（8899/8001=200+selfcheck+smoke 3/3 北京+水位>4G 四机）——GOV-CARD §3.4；现行实例=T13 §六（banner29/池 9.6M/600k/smoke 3/3/水位 18.6-21.1G）。

——models.d 注册表·v41-prod / 2026-10-06（案头零集群；誊录自 CHECKPOINT-LUZ030-R1+GOV-CARD）
