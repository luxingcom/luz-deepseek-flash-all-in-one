# SPEC6 — serve 参谱（六参→八参；第 9 参已退役；0.3.2 定版形 + 2026-10-30 规避窗）

> **0.3.2 定版注记（2026-10-20）**：九参谱为 0.3.2 终态在役形（boot
> `r3-boot-arm.sh` `20f22bc6`）；本文档的 50 键引用为 0.3.1 键面历史锚，
> 0.3.2 现役 env=CBX1A 56 键（公开位
> [`deploy/env/CBX1A-CERTM-spec1.env`](env/CBX1A-CERTM-spec1.env)，md5 `0729e18d`）。
> 升级与性能复现判据见 [`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md)。
> 起栈接线有效性由 [`tools/serve_flags_gate.sh`](../tools/serve_flags_gate.sh)
> 从运行进程 argv 直证（issue #4 采纳件）。
>
> **2026-10-30 UP43050 规避窗（上游缺陷 host 侧规避）**：第 9 参 `--sleep-on-idle`
> **退役为禁参**（上游 sglang
> [#43050](https://github.com/sgl-project/sglang/issues/43050)：GB10/SM121/UMA ×
> DGX Spark + DSv4.1-Flash + DSPARK speculative + NCCL 2.32.3 + `--sleep-on-idle`
> 的同构栈，空闲 10-20 分钟后被任意请求〔含健康探测〕唤醒即进入死 prefill，
> py-spy 卡 `_low_ratio_index_topk_dense`〔indexer_chunked_v3.py:181〕的
> `prefill_empty_cache` 唤醒重捕获路径，疑似唤醒后缺一处 host 同步点；无修复
> PR。报告者实测：同一硬件去掉该参后空闲期完全正常）。现役谱=**八参**（第
> 7/8/9 行中第 9 行退役）；归一指纹回 **6b12a445**（九参 9d64a5de 史档）。
> 禁参三面固化=r3-gate-env-lint EQ-03（值面注入位拒起）+ serve_flags_gate
> 缺席判据（argv 在场即 FAIL）+ selfcheck-prod 禁参表。空闲资源回收改走
> 低峰期主动 `/release_memory` 或定时重启；升级镜像时优先吸收 #45397/#46636
> 一类 idle 路径修复并在补丁镜像里守卫 wake 路径 host-sync 后方可复评此参。

> 法源：FORM-REGISTRY-031 §一（50 键行）+KV-LIFE desk/lib.sh:11+E3A §六。
> C0 定型臂 serve=SPEC6（COMBO 冻结窗卡 §三）；SPEC7（六参+`--chunked-prefill-size
> 8192`）已判负不进形（COMBO-STACK-RESULT 门 1）。
> **2026-10-15 W-C sglang 起机窗升档**：六参→**八参**（第 7/8 行=issue #1/#2 · A8/A9
> 接线，法源=032-ADDENDUM-NETWORK-20261015 §十；boot 参面单键新增，既有六参零动）。
> **2026-10-16 W-G 引擎参数微调窗升档**：八参→九参（第 9 行=V1 空闲面
> `--sleep-on-idle`，来源=用户令 2026-10-16；boot 参面单键新增，既有八参零动）。
> **2026-10-30 UP43050 规避窗降档**：九参→**八参**（第 9 行退役=上游 #43050
> idle-wake hang host 侧规避；史注全档保留，见下节）。

## 六参（基座）

| # | 参数 | 值 | 出处 |
|---|---|---|---|
| 1 | `--prefill-decode-interval` | 16 | 五参基座 |
| 2 | `--max-queued-requests` | 32 | 五参基座 |
| 3 | `--min-free-slots-delay` | 1 | 五参基座 |
| 4 | `--enable-decoder-swa-bounded-replay` | （flag） | 五参基座 |
| 5 | `--reasoning-parser` | deepseek-v41 | 五参基座 |
| 6 | `--swa-prefix-tails` | **256** | **E3-A 转正在役**（64→256；召回 N=256） |

## 第 7/8 行（2026-10-15 W-C 窗新增；A8/A9）

| # | 参数 | 值 | 出处 |
|---|---|---|---|
| 7 | `--tool-call-parser` | **deepseekv41** | **issue #1 · A8**（GitHub luxingcom/luz-deepseek-flash-all-in-one #1，贡献者 waterliu1981；DSML 原生工具调用不成型根因=serving.py `tool_call_parser` 缺省 None+`_tool_call_parsing_active()` 门禁整链旁路） |
| 8 | `--enable-cache-report` | （flag） | **issue #2 · A9**（同仓 #2；`usage.prompt_tokens_details.cached_tokens` 恒 null 根因=serving.py:189-192 缺省 False+serving_chat.py:796 硬门；knapcio v2.4 生产栈交叉印证） |

**命名陷阱注记（防后续参谱维护照抄错写）**：`tool_call` 侧与 `reasoning` 侧**两个名字并存、
互不通用**——tool_call=`deepseekv41`（**连写**，`function_call/parser_names.py` 白名单名；写
`deepseek-v41` 或 `deepseekv4` 不认，DSML 原样返回）；reasoning=`deepseek-v41`（**连字符**，
第 5 行照旧不动）。A8 只对带 `tools` 的请求生效；无 tools 请求行为零变化。

## 第 9 行（2026-10-16 W-G 窗新增；**2026-10-30 退役=禁参**）

| # | 参数 | 值 | 出处 |
|---|---|---|---|
| 9 | ~~`--sleep-on-idle`~~ | ~~（flag）~~ | **RETIRED-UP43050-20261030**：上游 sglang [#43050](https://github.com/sgl-project/sglang/issues/43050)（与我栈完全同构：GB10+DSv4.1-Flash+DSPARK+NCCL 2.32.3+--sleep-on-idle；空闲 10-20 分钟后被任意请求〔含健康探测〕唤醒即死 prefill，py-spy 卡 `_low_ratio_index_topk_dense`〔indexer_chunked_v3.py:181〕`prefill_empty_cache` 唤醒重捕获路径，疑似唤醒后缺 host 同步点；无修复 PR；报告者实测去参即正常）。原入谱理由=W-G 引擎参数微调窗 NET-WG-SLEEPIDLE-20261016（空闲忙转 1 核/墙插 +10–12W/台的省电收益）——**让位可用性，整行退役**。 |

- **现行判据=缺席**：argv/值面**不得出现**该参。三面固化：
  `deploy/bin/r3-gate-env-lint.sh` EQ-03 禁参组合（SPEC_EXTRA_ARGS/EXTRA_SGLANG_ARGS
  等注入位携带即 REFUSE 拒起）+ `tools/serve_flags_gate.sh` 缺席判据（R8：在场即
  FAIL）+ `deploy/prod/selfcheck-prod.sh` 禁参表（Config.Cmd 含即 FAIL）。
- **旧回退面作废**：W-G 窗登记的「去单行重靴 / 回拷 `.bak-pre-wg`〔9f3cdaac〕」
  回退路径**禁止执行**（该动作=重新引入 #43050 idle-wake hang）；boot 件内的
  W-G 史注与 RETIRED 注记原样保留（史面不覆写）。
- **替代面**：空闲资源回收改走低峰期主动 `/release_memory` 或定时重启（勿用自动
  idle-sleep）；重启窗照走沉降律。
- **复评条件**：升级镜像时优先吸收 #45397/#46636 一类 idle 路径修复，并在补丁
  镜像里守卫 wake 路径的 host-sync；满足后另开复评窗重议此参（届时本表改回并
  重登指纹）。

## 注入面

- boot 链注入位=`deploy/bin/r3-boot-arm.sh` SERVER_ARGS（SPEC=1 时另加
  `--speculative-algorithm DSPARK`；SPEC_EXTRA_ARGS 空格分词追加面缺省 no-op）。
  第 7/8 行落 **SERVER_ARGS 固定面**（非 SPEC_EXTRA_ARGS 注入面）——生产主链载体；
  运行时直证=docker inspect `{{json .Config.Cmd}}` 含两键（W-C 窗四查③位）。
  **第 9 行（W-G）原同落 SERVER_ARGS 固定面；2026-10-30 UP43050 窗退役**
  （参行注释化+RETIRED 注记；运行时直证=Cmd **不含** `--sleep-on-idle`——
  缺席即绿，在场即红，见下方对照表）。
- QA31 定型窗 SPEC6 归一指纹=**33d7161f**（四靴一致；**保留不覆写**=判读线零事后改同律）。
- **W-C 首靴指纹换代预登记**：八参形归一指纹=**6b12a445**（算式=md5(join(sorted(八参
  空格串)))[:8]，同 boot_sentinel.sh:309 口径；含第 7/8 行。旧六参 33d7161f 史档保留。
- **W-G 首靴指纹换代预登记**：九参形归一指纹=**9d64a5de**（算式同前；含第 7/8/9 行。
  旧八参 6b12a445 史档保留）。
- **UP43050 规避窗指纹复用登记（2026-10-30）**：第 9 参退役后现役谱=八参，归一
  指纹**回 6b12a445**（离线复算逐位复核=与 W-C 八参预登记同值；九参 9d64a5de
  转史档——三档指纹 33d7161f/6b12a445/9d64a5de 全保留不覆写，判读线零事后改同律）。
- 其余池面参数（池门 `--max-total-tokens 9600000`、
  `--json-model-override-args '{"candidate_topk_blocks": 2048}'`、
  `--fp8-gemm-backend flashinfer_cutlass`）为 boot 链固定面，不属 SPEC 参谱
  （r3-boot-arm.sh 内嵌，逐行注释在档）。

## 旗标-能力-生效值对照表（issue #4 + UP43050）

> 判据纪律：**断言"正在跑的进程 argv/运行时自省"，不断言源码或 env 里的静态串**。
> 只证"镜像支持"=假绿；接线漏了 `/health` 仍 200。闸门实现=
> [`tools/serve_flags_gate.sh`](../tools/serve_flags_gate.sh)（只读、fail-closed、
> 含 R1-R8 反向自检）。

| 能力 | 必需旗标 | 生效值怎么读 | 缺了/在场会怎样 |
|---|---|---|---|
| 工具调用成型 | `--tool-call-parser deepseekv41`（连写；`deepseek-v41` 是 reasoning parser 写法，不通用） | 容器内 `/proc/1/cmdline`；或 `/get_server_info` 的 `tool_call_parser` | DSML 以纯文本吐出，`/health` 仍 200（静默降级） |
| 缓存用量上报 | `--enable-cache-report` | 同上；`/get_server_info` 的 `enable_cache_report` | `usage.prompt_tokens_details.cached_tokens` 恒 `null`，面板缓存命中恒 0% |
| 排队上限 | `--max-queued-requests 32` | argv 值 | 并发/背压行为偏离定型形 |
| ~~空闲降 CPU~~（已退役） | `--sleep-on-idle` = **禁参（UP43050）** | argv **缺席**=绿 | **在场即红**：上游 #43050 空闲唤醒死 prefill 挂起（第 9 参，2026-10-16 入谱 / 2026-10-30 退役禁参） |

用法（head 与 worker 必须各查——角色差异 R7）：

```bash
tools/serve_flags_gate.sh --container r3boot-head --container r3boot-worker
tools/serve_flags_gate.sh --api http://127.0.0.1:30000
tools/serve_flags_gate.sh --self-test    # R1-R8 判别力回归
```

## 与 env 键面的配对律

一个形=**env 键面+SPEC 参+adapter/overlay 面**三元组齐一（README 快速上手）；
serve 参变体（如 SPEC7）必须与键面变体同窗冻结判读，禁跨形拼装。

**A8/A9 配对律适用注记（ADDENDUM §10.6）**：第 7/8 行为参面**新增**（非变体替换），
与 env 键面零耦合；但任一判读窗读数期内**禁切此两参**（切参=该窗判读作废重跑），
与「serve 参变体与键面同窗冻结」同律。

**W-C 窗形三元组（2026-10-15 起在役，速查；W-E/W-G 后见下行）**：env=44 键 `PROD-WC44-spec1.env`
（md5 a4f8bfe5；=51 键 R51W5FL6 减 RoCE/b12x 环网族 7 键）+SPEC 八参（归一指纹
6b12a445 预登记）+adapter 面（sitecustomize 55b1e412 等）+overlay o12c1-prod（29 件）
+启动器参面（r3-boot-arm.sh md5 06b25aac：NCCL_IB_HCA 部署对 rocep1s0f0,roceP2p1s0f1
+NCCL_IB_TC=106+NCCL_IB_TOS 退役+NCCL_IB_PEER_HCA 退役）。回退=旧 51 键件
`PROD-R51W5FL6-spec1.env`（2ac74586）+旧启动器件 `.bak-pre-wc`（939d32e6）回指重靴。

**W-G 窗形三元组（2026-10-16 起在役，速查）**：env=53 键 `PROD-WG53-spec1.env`
（md5 1e8e4daa；=52 键 W-E 件逐字+`DSV41_ROCE_GATHER=524288`〔呈裁②恢复 adapter 侧
gather 限幅；READY 面 gather=524288 预期〕）+SPEC 九参（归一指纹 9d64a5de 预登记）
+adapter 面（sitecustomize 55b1e412 / roce_ar.py f61e0183 / roce_gather.py 93a2c823 等）
+overlay o12c1-prod（29 件）+启动器参面（r3-boot-arm.sh md5 7e3ddbc8：W-E 形+
`--sleep-on-idle` 单参）。回退=相邻级 ①env 回指 `PROD-WE52-spec1.env`（4457ec76）
+启动器件回拷 `.bak-pre-wg`（9f3cdaac）重靴；再下一级=WE52 件同级回退链见 W-E 结果档 §十。
**〔UP43050-20261030 覆写注记〕**上段为 W-G 窗史档原样保留；其中「+`--sleep-on-idle`
单参」与「回拷 `.bak-pre-wg`」两处**已被 2026-10-30 规避窗覆写**：该参退役为禁参
（上游 #43050），回拷该旧件=重新引入 idle-wake hang，禁止执行（详见上方「第 9 行」
节的现行判据/作废回退面/替代面/复评条件四款）。env 面回退链不受影响。

——net-rebuild W-C sglang 起机窗 / 2026-10-15（A8/A9 行入谱；指纹换代预登记）
——NET-WG-SLEEPIDLE-20261016 W-G 引擎参数微调窗 / 2026-10-16（第 9 行入谱；指纹换代预登记 9d64a5de）
——UP43050-SLEEPIDLE-RETIRE 规避窗 / 2026-10-30（第 9 行退役=禁参；指纹回 6b12a445；禁参三面固化）
