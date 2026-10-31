# 升级到 LuZ 0.3.4（0.3.3/0.3.2 基底 → 修复固化+调优终态）

> **跨世代总入口**：镜像世代/digest 总表、换镜像必须联动的配套面（boot 目行/overlay/adapter/env）、
> 逐步自验与常见坑，见 [docs/IMAGE-UPGRADE-GUIDE.md](docs/IMAGE-UPGRADE-GUIDE.md)；本文是其中
> 「0.3.2/0.3.3 → 0.3.4」一跳的完整移植正文。
>
> 目标读者：已能跑 0.3.2/0.3.3、或从零搭 4×DGX Spark GB10 TP4 的采用人员。
> 目标：把 **v41 三联固化 + BYPASS 采用 + 61 键调优 env** 落成一套可 boot、
> 可判读、可回退的 0.3.4 栈，并用工具六件套完成部署/验收/自诊断闭环。
>
> **本件为移植骨架（new 条目）**：章节结构已立、素材指针已接通（均指向本仓
> 已入档的正典件），正文逐步操作细节由文档写手按素材源充实——各节
> `TODO(写手)` 标记处为待写面。

## 0. 目标形态速查

| 面 | 0.3.4 调优终态 | 验收指纹 |
|---|---|---|
| KV 布局 | **v41 三联**：env 尾行 `SGLANG_DSV4_KV_LAYOUT=v41` + `.env.tp4` v41 + guards envpin v41 | gates-034 BL11 五检（md5/键数/v41/BYPASS/CACHE_GIB=2） |
| BYPASS | `DSV41_PREFILL_BYPASS=2048`（第 60 键）+ adapter `sitecustomize.py` 钩（dd69c59a）+ `prefill_bypass.py`（c4875258） | 点火后 armed=8（2/机）∧ refusing=0（BL-BYP2/DEPLOY S6 硬门） |
| engram 缓存 | `DSV41_ENGRAM_CACHE_GIB=2`（I8 采纳，第 61 键尾行） | 横幅 8/8 全 cache=2.0GiB |
| env | `deploy/env/CBX1A-CERTM-spec1.env`（**61 键**，口径=gates BL11 判据；本仓为脱敏拷贝） | 内部正典锚 md5 `4370aab9…`（VERSION-LOCK §二） |
| guards | `deploy/kit/guard/guards.conf`（:161 envpin 钉 v41） | 内部正典锚 md5 `418414c3` |
| profile | `deploy/prod/prod-profile.env`（W-f 重钉：:8 env=4370aab9 / :9 61 键 / :12 COUNT=29） | 内部正典锚 md5 `77d7fa67` |
| overlay | 29 件面（**本体+map+md5 三件套已入仓**，2026-10-31 备查同步窗） | map `efd7d89b` · md5 清单 `6c98cf8c`（现役对表值；034-lock 时点值 `fd59c03b` 为锁档档案，见下注） |
| IMAGE | `dsv41-sglang-optimized:0.3.4-x6bake-20261026` | RepoDigest `sha256:80e4c957…8f7d0` |

> **公开拷贝 md5 注记**：上表「验收指纹」中的 md5 均为**内部正典锚**（内部四机在役原件的身份）；公开树内为脱敏拷贝，md5 天然不同（逐件公开实落值见 [CHANGELOG](CHANGELOG.md) 0.3.4 面公开移植批清单），采用者填入本站实测值后 md5 再变——站点自检一律用内容判据（键数/行值），不要拿内部锚硬套。

> **overlay 缺口注记（2026-10-31 备查同步窗后改写，如实）**：0.3.4 overlay 29 件
> 本体**已入公开树** `deploy/overlay/o12c1-prod/`（29 个 `.py` 活件+`overlay-map.tsv`
> 映射表共 30 件；三件身份正典全文另备查于 `deploy/reconstruct/0.3.4/overlay/`），
> 对表清单=`deploy/prod/overlay-md5.txt`（该件自身 md5 `6c98cf8c…`，29 行）——
> `cd deploy/overlay/o12c1-prod && md5sum -c ../../prod/overlay-md5.txt` 应 29 行
> 全绿。清单沿革：034-lock 时点形为 `fd59c03b…`（scheduler 行=`3db3275e`），锁档后
> df07 窗 scheduler 单件演进至 `4a7822a6`，现役清单随之重钉为 `6c98cf8c…`；锁档
> 档案仍记旧值属时点快照而非漂移（逐件换血表与旧形取回口径=
> [deploy/README-说明.md](deploy/README-说明.md)）。**绑定律不变**：overlay 与镜像
> 代际绑定，本 29 件配 `0.3.4-x6bake-20261026` 镜像；如需先行验证 0.3.2 历史定版
> 形，按 [DEPLOY-STEP-BY-STEP](docs/DEPLOY-STEP-BY-STEP.md) 全 0.3.2 面（r032c
> 镜像+56 键 env+87 件 adapter+0.3.2 overlay）整套起栈——**禁止**拿 0.3.2 overlay
> 增量件（`deploy/reconstruct/0.3.2/overlay/`）拼 0.3.4 镜像（绑定律/混形禁忌，
> 0.3.4 镜像×0.3.2 overlay=无档混形）。

## 1. v41 三联（KV_LAYOUT 固化）

TODO(写手)：env 尾行 / `.env.tp4` / guards envpin 三面的落位方法与核验命令；
机理背景=[034-KV-MECH-NOTE](docs/research/034-KV-MECH-NOTE-20261028.md)
（fork-v4-fp4 退化面=慢带 −15~19%，doctor DG1/DG3 大声警告承载）。

## 2. 61 键 env 替换（0.3.2 期 56 键 → 0.3.4 期 61 键）

TODO(写手)：以 `deploy/env/CBX1A-CERTM-spec1.env` 替换现役 env 的步骤与四机
同步面；键数口径一律按 gates-034 BL11 判据「**61 键**」表述（61 行键定义见
[034-WD-TUNED-FINAL](docs/release/034-WD-TUNED-FINAL-20261029.md)：I8 唯一
采纳+I4/I5/I6 REVERT+I7 SKIP，含同键双行末行胜语义注记）。

## 3. guards envpin 与生产钉面

TODO(写手)：`guards.conf` :161 envpin 重钉、`prod-profile.env` :8/:9/:12 三钉
行含义、镜像 digest 核验（IMG-1 门）。

## 4. 工具六件套上手（doctor / deploy / verify / selftest + config / gates）

TODO(写手)：四命令流程（README §2 已有速览）+ `tools/config-034.tsv`（期望
唯一来源，72 参数行）与 `tools/gates-034.tsv`（10 门）的关系说明；详档=
[runbook-034](docs/runbook/runbook-034.md)。

## 5. 2026-10-30 两项公开修复注记

TODO(写手)：
1. **EQ-02 RoCE 双键 fail-closed**——boot 链对 `B12X_ROCE_HCA`/`B12X_ROCE_TOPOLOGY`
   两键缺失即拒起（r3-boot-arm.sh 公开线 round-91/92 修复；config-034 CFG-01
   双合法归一承载）。
2. **UP43050 去 `--sleep-on-idle`**——SPEC6 第 9 参退役=禁参（上游 issue #43050），
   见 `deploy/SPEC6-SERVE-REF.md` 覆写注记。

## 6. 验收与回退

- 验收= `bash tools/verify-034.sh --smoke`（EQ-S 夹心+liter+DE+500q）/ `--full`；
- 回退=双路正典 [ROLLBACK-PATHS-034](docs/runbook/ROLLBACK-PATHS-034.md)
  （路 A=0.3.3 全回退 / 路 B=W-d 调优单差回置恰 3 行）；
- 判读门终值与代际对照=[034-PERF-REPORT](docs/report/034-PERF-REPORT-20261029.md)。

---

<!-- 0.3.4re 移植骨架注记：素材源=runbook-034+034-VERSION-LOCK+WD-TUNED-FINAL+gates-034
     （均已入仓）；体例对齐 UPGRADE-0.3.2.md。内网值一律占位符（__REPO_ROOT__ 等
     shell 位/<registry-host> 等数据位），采用者按自有环境替换。 -->
