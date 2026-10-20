# SPEC6 — serve 参谱（六参→九参；0.3.2 定版形）

> **0.3.2 定版注记（2026-10-20）**：九参谱为 0.3.2 终态在役形（boot
> `r3-boot-arm.sh` `20f22bc6`）；本文档的 50 键引用为 0.3.1 键面历史锚，
> 0.3.2 现役 env=CBX1A 56 键（内部臂件）。起栈接线有效性由
> [`tools/serve_flags_gate.sh`](../tools/serve_flags_gate.sh) 从运行进程 argv
> 直证（issue #4 采纳件）。

> 法源：FORM-REGISTRY-031 §一（50 键行）+KV-LIFE desk/lib.sh:11+E3A §六。
> C0 定型臂 serve=SPEC6（COMBO 冻结窗卡 §三）；SPEC7（六参+`--chunked-prefill-size
> 8192`）已判负不进形（COMBO-STACK-RESULT 门 1）。
> **2026-10-15 W-C sglang 起机窗升档**：六参→**八参**（第 7/8 行=issue #1/#2 · A8/A9
> 接线，法源=032-ADDENDUM-NETWORK-20261015 §十；boot 参面单键新增，既有六参零动）。
> **2026-10-16 W-G 引擎参数微调窗升档**：八参→**九参**（第 9 行=V1 空闲面
> `--sleep-on-idle`，来源=用户令 2026-10-16；boot 参面单键新增，既有八参零动）。

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

## 第 9 行（2026-10-16 W-G 窗新增；V1 空闲面）

| # | 参数 | 值 | 出处 |
|---|---|---|---|
| 9 | `--sleep-on-idle` | （flag） | **W-G 引擎参数微调窗**（NET-WG-SLEEPIDLE-20261016；来源=用户令 2026-10-16：SGLang 调度器空闲忙转吃满 1 个核（预测实锤≈98.6% 单核）、墙插 +10–12W/台〔四台≈40–48W〕；镜像支持已核=main-79cafec0 容器内 `python3 -m sglang.launch_server --help` 含“Reduce CPU usage when sglang is idle.”；行为面=仅空闲态降 CPU，请求路径零变化） |

- 回退=去`--sleep-on-idle`单行重靴（或启动器件 `.bak-pre-wg`〔9f3cdaac〕还原；零 env 耦合）。

## 注入面

- boot 链注入位=`deploy/bin/r3-boot-arm.sh` SERVER_ARGS（SPEC=1 时另加
  `--speculative-algorithm DSPARK`；SPEC_EXTRA_ARGS 空格分词追加面缺省 no-op）。
  第 7/8 行落 **SERVER_ARGS 固定面**（非 SPEC_EXTRA_ARGS 注入面）——生产主链载体；
  运行时直证=docker inspect `{{json .Config.Cmd}}` 含两键（W-C 窗四查③位）。
  **第 9 行（W-G）同落 SERVER_ARGS 固定面**（:435 `)` 前、A9 段后；运行时直证=
  docker inspect Cmd 含 `--sleep-on-idle`（W-G 窗四查新增证①位）。
- QA31 定型窗 SPEC6 归一指纹=**33d7161f**（四靴一致；**保留不覆写**=判读线零事后改同律）。
- **W-C 首靴指纹换代预登记**：八参形归一指纹=**6b12a445**（算式=md5(join(sorted(八参
  空格串)))[:8]，同 boot_sentinel.sh:309 口径；含第 7/8 行。旧六参 33d7161f 史档保留。
- **W-G 首靴指纹换代预登记**：九参形归一指纹=**9d64a5de**（算式同前；含第 7/8/9 行。
  旧八参 6b12a445 史档保留）。
- 其余池面参数（池门 `--max-total-tokens 9600000`、
  `--json-model-override-args '{"candidate_topk_blocks": 2048}'`、
  `--fp8-gemm-backend flashinfer_cutlass`）为 boot 链固定面，不属 SPEC 参谱
  （r3-boot-arm.sh 内嵌，逐行注释在档）。

## 旗标-能力-生效值对照表（issue #4）

> 判据纪律：**断言"正在跑的进程 argv/运行时自省"，不断言源码或 env 里的静态串**。
> 只证"镜像支持"=假绿；接线漏了 `/health` 仍 200。闸门实现=
> [`tools/serve_flags_gate.sh`](../tools/serve_flags_gate.sh)（只读、fail-closed、
> 含 R1-R7 反向自检）。

| 能力 | 必需旗标 | 生效值怎么读 | 缺了会怎样 |
|---|---|---|---|
| 工具调用成型 | `--tool-call-parser deepseekv41`（连写；`deepseek-v41` 是 reasoning parser 写法，不通用） | 容器内 `/proc/1/cmdline`；或 `/get_server_info` 的 `tool_call_parser` | DSML 以纯文本吐出，`/health` 仍 200（静默降级） |
| 缓存用量上报 | `--enable-cache-report` | 同上；`/get_server_info` 的 `enable_cache_report` | `usage.prompt_tokens_details.cached_tokens` 恒 `null`，面板缓存命中恒 0% |
| 排队上限 | `--max-queued-requests 32` | argv 值 | 并发/背压行为偏离定型形 |
| 空闲降 CPU | `--sleep-on-idle` | argv 存在 | 空闲期 CPU 忙转（第九参，2026-10-16 入谱） |

用法（head 与 worker 必须各查——角色差异 R7）：

```bash
tools/serve_flags_gate.sh --container r3boot-head --container r3boot-worker
tools/serve_flags_gate.sh --api http://127.0.0.1:30000
tools/serve_flags_gate.sh --self-test    # R1-R7 判别力回归
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

——net-rebuild W-C sglang 起机窗 / 2026-10-15（A8/A9 行入谱；指纹换代预登记）
——NET-WG-SLEEPIDLE-20261016 W-G 引擎参数微调窗 / 2026-10-16（第 9 行入谱；指纹换代预登记 9d64a5de）
