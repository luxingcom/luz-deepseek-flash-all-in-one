# tools/upstream/bench-arrival/ — sglang bench_serving 开环 --request-rate 到达漂移缺陷的 host 侧规避两件套 <!-- bench-arrival: doc -->

> 法源：sgl-project/sglang [PR #44162](https://github.com/sgl-project/sglang/pull/44162)
> （[Fix] benchmark: Compensate cumulative request arrival drift；fixes issue #43930；
> 2026-10 时点 **open 未合**）。缺陷：`python/sglang/benchmark/serving.py` 的
> `get_request` 泊松（finite-rate、非 trace）分支把 `await asyncio.sleep(interval)`
> 放在 yield 之后、以 **consumer 恢复 generator 的时刻**为睡起点——consumer 的
> 发包/收流/记账工作与事件循环晚唤醒逐请求累进到达间隔，**offered load 随请求数
> 系统性偏低**（上游报告：100 req/s 档实测 ~68 req/s、400 req/s 档实测 ~190 req/s，
> 即长压测读数整体失真，TTFT/吞吐被系统性偏置）。修法：累积单调绝对到达时刻
> `target_arrival_time`，每次 yield 前只 sleep 剩余时间；迟到请求立即追上而不重置
> 调度表；terminal sleep 移除但保留最后一次 exponential draw（RNG 兼容）。
> 同窗关联：#46504（多轮输入 token 计入 serving metrics）、#47050（timed-trace
> replay）。host 侧规避=**压测口径侧落地**：不重烘引擎镜像、不改上游源码树，
> 开环有限速率基准一律经修补件跑，避免把调度漂移算进引擎回归。
> 落点双面同件（md5 一致互证）：战役仓 `luz030-opt-campaign/tools/upstream/bench-arrival/`
> 与公开仓 `luz-034re/tools/upstream/bench-arrival/`；`SOURCE-MD5.txt` 为互证锚。

## 两件套与用法

| 件 | 职责 | 用法 | 退出码 |
|---|---|---|---|
| `bench_serving_44162.py` | 修补版载体（薄启动器）：运行时把缺陷版 `get_request` 换成 #44162 修补版后原样透传 bench_serving 全部 CLI | `python3 bench_serving_44162.py [--sglang-root PATH] [--] <bench 参数>`；`--selfcheck` | 0=bench 结束；1=bench 失败；2=定位/判别 fail-closed |
| `bench_arrival_guard.py` | 口径守卫：`--check` 判别 sglang 面 get_request 缺陷态；`--lint` 扫仓面「未经修补的有限 `--request-rate` 开环口径」 | `--check [--path P]`；`--lint [PATH ...]`；`--selfcheck` | 0=PASS；1=VULNERABLE/REFUSE；2=取证失败 |

sglang 定位优先级（启动器与守卫一致）：`--sglang-root`/`--path` 显式 >
`$SGLANG_ROOT` > `~/sglang-main-src` > 已安装包；全部缺位=rc2 fail-closed。

判定矩阵（`--check`）：

| 目标 get_request 泊松分支 | 判定 | 动作 |
|---|---|---|
| `np.random.exponential(...)` 后 `await asyncio.sleep(interval)`（睡起点=恢复时刻） | **VULNERABLE**（rc1） | 开环基准必须经 `bench_serving_44162.py`（PATCHED 注入） |
| `target_arrival_time +=` 且 yield 前 `sleep(target-now)` | FIXED（rc0） | 可直跑；启动器自动 ALREADY-FIXED 透传 |
| 两者皆非/取不到源 | UNKNOWN（rc2） | fail-closed 拒跑，人工核对后更新夹具 |

## 口径落地制式（开环基准怎么跑）

1. **判源**：`python3 bench_arrival_guard.py --check`（缺省 `~/sglang-main-src`；
   引擎容器内的 sglang 以其源码树/安装根显式给 `--path`，只读不 exec）。
2. **跑基准**：VULNERABLE 面上一律
   `python3 bench_serving_44162.py --host 127.0.0.1 --port 8899 --backend sglang --request-rate 100 ...`
   （启动器打印 `PATCHED` 后透传；FIXED 面打印 `ALREADY-FIXED` 直接透传）。
   <!-- bench-arrival: patched -->
3. **替代路线**：trace replay 分支（`--use-trace-timestamps`，#47050 谱系）本身即
   绝对时刻法，不经本件也不受漂移影响；泊松分支（默认）必须经本件。
4. **lint 执法**：仓面脚本/文档出现「裸跑 sglang bench_serving 且
   `--request-rate` 为有限值」即 REFUSE；豁免标记三枚——`# bench-arrival: patched`
   （经修补件）、`# bench-arrival: closed-loop`（闭环/无限速率口径）、
   `<!-- bench-arrival: doc -->`（纯文档行）。工具本体两 py 不适用 lint（自描述
   必然含关键词）。
5. **闭环量具不受影响**：本仓正典量具 sd_bench（CFG-31 锚）/de_c48_bench（CFG-32）/
   conc_pr_driver（CFG-30）均为闭环并发驱动，无到达率调度面，不经本件（2026-10-30
   grep 亲核：三件零 `request_rate`/`exponential`/`asyncio.sleep` 命中）。

## 修补版语义要点（#44162 同构，selfcheck 已断言）

- **绝对时刻表**：第 i 个请求的到达目标=启动时刻+Σ前 i 个 interval（单调，不重置）；
  yield 前 sleep `target-now`（≤0 立即发）。
- **迟到即追**：晚唤醒/consumer 工作导致的落后以连发追平，落后有界（单次晚唤醒
  量级），不随请求数累积；缺陷版则逐请求累积（gap 恒拉长）。
- **消费端饱和诚实呈现**：consumer 单请求工作 > gap 时到达率上限=消费率（async
  generator 拉取模型的物理上限，非缺陷）；修补版=上限连发，缺陷版再慢一拍。
- **RNG 兼容**：修补函数以目标模块 `__dict__` 为全局命名空间 exec（np/time/asyncio
  继承模块对象）；draw 次数与顺序、与 consumer 侧 NumPy draw 的 interleaving、
  消费完后 RNG state 均与上游修复版一致（最后 draw 保留、terminal sleep 移除）。

## 当前生产态取证（2026-10-30 建件窗，只读亲核）

- 本地 sglang 主干 checkout `~/sglang-main-src`（commit 79cafec0，2026-09-28；
  与生产 overlay 基线同源）：`benchmark/serving.py:1111-1123` 泊松分支为缺陷版
  （守卫 `--check` 实测 VULNERABLE，rc1，输出在档）。
- 本仓双面（战役仓+公开仓 tools/docs 全树）**零处**使用 `bench_serving`/
  `--request-rate`（lint 实测 PASS rc0）——即当前战役的正典量具全闭环，本件为
  **未来开环基准（PR 复测、SLO 校验、与上游数字对齐）的前置口径面**。
- 宿主无 sglang 运行环境（Python 3.12.3 未装 sglang 及 orjson 等依赖）：启动器
  对真树实跑为 rc2 fail-closed（输出在档，属预期）；实跑基准须在具备 sglang
  bench 依赖的环境（如容器外 venv）执行，届时本件零改动可用。

## 红线与边界

- 两件全离线自检（合成缺陷版/修复版模块+假时钟，不 import 真 sglang、不发包、
  不写仓）；对产线/引擎/镜像零触碰；零 git、零容器生命周期动作。
- 启动器**运行时覆盖**只发生在本进程内（exec 注入+重绑模块属性），不改上游
  源码树任何字节、不装包、不烘镜像；bench 客户端行为其余面（请求构造、统计、
  输出）与上游逐字节一致。
- 上游 #44162 合入发布后：目标面 `--check` 转 FIXED ⇒ 启动器自动透传，本件进入
  维持态；判别器 FIXED 语义与上游一致，长青保留。关联 #46504（多轮输入 token 计
  serving metrics）与 #47050（timed-trace replay）若后续随版本入栈，升级跟踪以
  `tools/upstream/deepseek-recipe-pypi-probe.sh` 同款版本探针/CHANGELOG 核对面承接。
