# CALIBER-AND-MEASUREMENT — 量测口径与读数纪律

> 目标读者：第一次接触本项目的工程师——你已经把栈跑起来了（boot、四查、warm 门都绿），
> 现在要**量性能、量质量**，并且希望量出来的数字别人能复核、自己也敢报。
> 本文回答一个问题：**怎么量，读数才可信**。出了症状怎么查，见同目录
> [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md)（排障词典），两文分工见文末。
>
> 法源：[`tools/bench/README.md`](../tools/bench/README.md)（量具正典）、
> [`UPGRADE-0.3.2.md`](../UPGRADE-0.3.2.md) §10（验收读数纪律）、
> [`deploy/SPEC6-SERVE-REF.md`](../deploy/SPEC6-SERVE-REF.md)（口径与命名陷阱）、
> [`docs/DEPLOY-GUIDE.md`](DEPLOY-GUIDE.md) §8（验收门）。
> 本文 §1 对照表的每一格都**亲自核对了仓内脚本源码与 `--help`**，不是转述手册。

**占位符表（按自己站点替换；本仓 0.3.2 参考形值列在括号里）**：

| 占位符 | 含义 | 本仓 0.3.2 参考形 |
|---|---|---|
| `<H1>` | head 机（rank0）地址，一切探活 ssh 到它 | — |
| `<PORT>` | 生产网关口（引擎产线流量走这里） | 8899 |
| `<TEST_PORT>` | 引擎测试口（量具专用，避开网关转发开销） | 8898 |
| `<GW_PORT>` | 网关对外车道口（客户端真实入口） | 8001 |
| `<repo>` | 本仓 checkout 根目录 | — |
| `<USER>` | 登录用户 | — |

文中引用的"外部站点手册实例数字"（如 0.33s / 167k tok/s）是**量级示意**，来自其他
站点的实测复盘，不可当本仓基线锚点照抄；本仓自己的参考读数会明确标注
"0.3.2 交换机形态"。

---

## 0. 前提三件（量之前先接受这三条，否则后面全白量）

### 0.1 引擎只绑回环，一切探活必须 ssh 到 head 机

引擎以 `--host 127.0.0.1` 启动，是**刻意形**（不扩大暴露面），所以引擎口
（`<TEST_PORT>` 和 `<PORT>`）只在 head 机本机可达。你在跳板机/管理机上执行
`curl 127.0.0.1:<TEST_PORT>/health` 得到 `000` 时，**第一反应应该是"我打错机器了"，
不是"引擎死了"**。

```bash
# 正确：ssh 到 head 机上打回环
ssh <USER>@<H1> 'curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:<TEST_PORT>/health'
# 期望输出：200
```

常见错法：在非 head 机上直接 curl，得到 `000`（连接层失败，连 HTTP 状态码都没有），
然后开始排查引擎——白查一轮。`000` 在别的机器上是**预期行为**。

### 0.2 产线口与测试口分面——跑量具用哪个口按场景定

- **性能量具（PR / DE / needle / accept_window）一律走测试口
  `http://127.0.0.1:<TEST_PORT>`**，避开生产网关 `<PORT>` 的转发开销，量的是引擎
  本体（[`tools/bench/README.md`](../tools/bench/README.md) 开篇口径）。
- **质量门按各工具正典**：GSM8K 与 qeval 的默认口都是网关
  `http://127.0.0.1:<PORT>`（GSM8K 走网关是历史口径；qeval 的价值在"带鉴权、经
  网关、按真实使用方式打请求"）。测试窗里两者都可用参数改指测试口：GSM8K 用
  `--base http://127.0.0.1:<TEST_PORT>`，qeval 用 `--url`。
- **最大的坑在默认值**：`sd_bench.py` 的 `--base-url` **默认是
  `http://127.0.0.1:8899/v1`，即生产口**。跑性能量具时必须显式
  `--base-url http://127.0.0.1:<TEST_PORT>/v1`；批量壳 `pr_ladder6.sh` 甚至对
  含 8899 的 BASE_URL **硬拒（exit 5）**，就是防这一枪。忘了传会发生什么：量具
  对着产线网关发压测流量——既污染产线读数，又量进了网关转发开销。

### 0.3 量具永不与产线流量/质量跑分并发

质量跑分（GSM8K、qeval、needle）与吞吐跑分（PR、DE）**并发上引擎会互相抢卡**：
外部站点实测 DE 各档读数被拉低**三到四成**，事后无法区分"真实差距"与"干扰"。
规矩只有两条：**排好队串行跑**；受污染的档在引擎空闲后**干净复测再采信**。
同理，引擎上有产线流量时不开判读窗；判读窗内不接产线流量。

---

## 1. CLI 口径对照总表（先认参数，再谈读数）

四个量具的参数风格**互不相同**，凭 muscle memory 抄命令必错。下面这张表先给结论，
表后每一格都附**脚本源码/`--help` 证据**（若与你手头手册冲突，以仓内脚本为准）。

| 量具 | 参数风格 | URL 参数名与形态 | 并发参数写法 | 尺寸/题量参数名 | 输出文件字段结构 | 典型错法 → 报错码 |
|---|---|---|---|---|---|---|
| **qeval**（75 题质量门） | **子命令式**：`run <label>` / `compare <a> <b>`；`--key-file` 等是**顶层参数，必须写在子命令之前** | `--url`，**全路径**，带 `/v1/chat/completions`；默认 `http://127.0.0.1:<PORT>/v1/chat/completions` | `run --concurrency N`（默认 1；正典=1，>1 时 compare 会注记批噪声） | 无尺寸档：75 题固定；`--limit N` 取前 N 题冒烟，`--only code,math` 筛类别 | `~/qeval-results/qeval-<label>.json`（`--out-dir`/`QEVAL_OUT` 覆盖）：`{label, url, concurrency, wall_s, utc, median_tok_s, truncated, results:[{id, category, pass, why, content, finish_reason, completion_tokens, seconds, tok_s, …}]}`；`compare` 输出终端表格+McNemar p 值，不落文件 | 只给根路径 → 前置门 TRANSPORT 拒跑 **exit 2**（打印 http 405/404）；401/403 → AUTH 拒跑 **exit 2**；`--key-file` 放 `run` 之后 → argparse **exit 2**；不带子命令 → 打印帮助 **exit 64** |
| **sd_bench**（PR/DE 主量具） | **旗标式**：`--mode pr|de` 必填（`--selfcheck` 时可省） | `--base-url`，**带 `/v1`**（脚本自拼 `/chat/completions`）；**默认=生产口 8899**，跑量具必须显式指 `<TEST_PORT>` | `--concurrency N` **单值**，只许 `{1,2,3,4,5,6,8,10,12,16,24,32}`；空格多值直接拒 | **`--sizes`**（`nargs="+"`，空格多值**合法**：`--sizes 8192 32768`）；**没有 `--targets`** | PR 模式：`{label, pr:[{target, prompt_tokens, ttft_s, tok_s, prompt_chars, chars_per_token, filler}]}`；DE 模式：`{label, de:[{type, conc, per, per_all, agg, completion}]}`——**每轮一行**（`--runs 5` ⇒ `de[]` 5 行）；**没有** `agg_tok_s`/`tok_s` 字段，单流看 `per`、聚合看 `agg` | `--targets 8192` → argparse **exit 2**；`--concurrency 1 2 4` → **exit 2**（`unrecognized arguments: 2 4`）；`--concurrency 7` → **exit 2**（允许清单外）；`--base-url …/v1/chat/completions` → 拼成 `/chat/completions/chat/completions` → **404**；忘传 `--base-url` → 打到生产口 |
| **gsm8k**（GSM8K 质量门） | **旗标式**（无子命令） | `--base`，**不带 `/v1`**（脚本自拼 `/v1/chat/completions`）；默认网关 `<PORT>` | **无并发参数**：源码并发恒为 1，顺序出题（与历史口径一致） | 无尺寸档：题量 `--nq N`（默认 200；复现发布读数用 `--nq 500`），`--skip N` 跳题 | `--out-raw` jsonl，每行 `{i, gold, pred_content, pred_marker, ok_content, ok_marker, ct, sec, err}`；`--out-summary` json：`{accuracy_content, accuracy_marker, correct_content, correct_marker, err, median_ct, median_elapsed, nq, temperature, shots, concurrency, …}` | `--base-url …` → argparse **exit 2**（不识别）；`--base http://…:<TEST_PORT>/v1` → 拼成 `/v1/v1/chat/completions` → 每题 **HTTP 404**——**记进 err 字段、照常出 summary**（404 被算成错题，先看 `err` 计数再谈准确率） |
| **needle**（长上下文探针） | **旗标式**（无子命令） | `--base`，**不带 `/v1`**；默认 `http://127.0.0.1:8898`（即测试口） | 无并发参数（单问单答） | **`--sizes`**（空格多值；默认 `8192 32768 65536 131072`；600k 档须显式 `--form r1`） | `{seed, base, form, form_limit, water_m, rows:[{target_tokens, est_tokens, magic, prompt_tokens, completion_tokens, elapsed_s, answer_head, status: PASS/FAIL/SKIP, reason|error}], n_pass, n_fail, n_skip, gate_pass}` | `--base …/<TEST_PORT>/v1` → `/v1/v1/…` → 异常 → 全行 **SKIP**（`gate_pass:false`，无证据不得放行）；600k 不带 `--form r1` → **SKIP**「形态门：form=unknown 上限 131072，档 600000 超限」 |

补充一个**伴生量具**（不在四行表里，但同属量具族）：`tools/accept_window.py`
（投机接受率窗，均值 ±2σ）。它也是旗标式；`--base` **不带 `/v1`**（默认
`http://127.0.0.1:8898`，打的是 `GET /metrics`）；判窗用 `--window lo,hi`
（默认 `3.10,3.40`）；`/metrics` 里抓不到 accept 指标时走 fallback：`--census
<census.json> --de <de1.json> <de2.json>…` 用「census 步数 + DE completion 反推」。

### 1.1 表格证据（逐格对源码与 --help，亲自核对）

**sd_bench（`tools/bench/sd_bench.py`）**

- 参数风格/URL：`--help` 实测输出为旗标式（`--mode {de,pr}`、`--type`、`--sizes
  [SIZES ...]`、`--pr-filler {repeated,random,real}` 等）。源码 `main()`：
  `--base-url` 缺省 `http://127.0.0.1:8899/v1`（生产口+带 `/v1`）；`Client.stream()`
  实际 POST 到 `f"{self.base}/chat/completions"`——所以 `--base-url` 带不带
  `/v1` 的分界就在这一行：**带 `/v1`，不要带 `/chat/completions`**。
- 并发：`--concurrency` 是 `type=int` 的**单值**参数；取值必须落在
  `ALLOWED_CONC = (1,2,3,4,5,6,8,10,12,16,24,32)`，否则打印
  `concurrency 必须是 (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 24, 32)` 并 **exit 2**
  （实测复现）。`--concurrency 1 2 4` 里 argparse 只吃 `1`，`2 4` 变成多余位置
  参数 → `unrecognized arguments: 2 4`，**exit 2**（实测复现）。并发档必须
  **逐档串行循环**。
- 尺寸：参数名是 `--sizes`，`nargs="+"`（`--sizes 8192 16384 32768` 合法）。
  **不存在 `--targets`**：写 `--targets 8192` → `unrecognized arguments:
  --targets 8192`，**exit 2**（实测复现）。特别注意：这个错如果在管道里接了
  `grep`，会变成**静默空输出**，看着像"量具坏了"——量具命令要么先裸跑一次
  看退出码，要么确认 json 落了地，别拿空输出当"跑过了"。
- `--runs` 语义：只进 `run_de(..., a.runs)`，**DE 模式生效**（每轮一行写进
  `de[]`）；`run_pr()` 的签名里根本没有 runs——**PR 模式 `--runs` 被忽略**，
  一次调用每个尺寸只发一发。所以"64k×3 取中位"= **三次独立调用**，不是
  `--runs 3`（`pr_ladder6.sh` 头注坑①同源；bench README 开篇同律）。
- 输出字段：PR 行 `{target, prompt_tokens, ttft_s, tok_s, prompt_chars,
  chars_per_token, filler}`；DE 行 `{type, conc, per, per_all, agg, completion}`
  （`completion` 是**各流 completion_tokens 的数组**）。tok/s 口径：DE 单流
  `per = (completion-1)/(t_last-t_first)`，聚合
  `agg = Σ(completion-1)/(max(t_last)-min(t_first))`；PR
  `tok_s = prompt_tokens/TTFT`。
- 佐证命令与期望输出（离线，不连引擎）：
  ```bash
  python3 <repo>/tools/bench/sd_bench.py --selfcheck
  # 期望末行：SELFCHECK PASS
  ```

**qeval（`tools/bench/qeval.py`）**

- 参数风格：argparse 用 `add_subparsers(dest="cmd")`，`run` 收位置参数 `label`，
  `compare` 收两个文件参数；`--selftest/--key-file/--key-var/--out-dir` 挂在
  **顶层 parser** 上。`run` 的 `run --help` 实测只列出
  `--url/--timeout/--concurrency/--only/--limit`——顶层参数放到子命令之后会
  `unrecognized arguments`，**exit 2**（实测复现；源码头注记录过 2026-09-25
  两次照抄错示例撞上此坑）。不带子命令 → `ap.print_help()` + **exit 64**。
- URL：`DEFAULT_URL = "http://127.0.0.1:8899/v1/chat/completions"`，**全路径、
  逐字使用、不自拼**。只给根路径/`/v1` 时 POST 打到错误路径，返回 405/404；
  qeval 的**前置门** `preflight()` 把非 2xx 分类为 TRANSPORT（401/403 → AUTH），
  打印 `REFUSED: 前置门未过（…）—— 不出质量分` 并 **exit 2**——它宁可拒跑
  也不把传输错误读成"质量全红"。
- 并发：`run --concurrency`，默认 1。正典口径=1（题序固定时 greedy 才
  run-to-run 可复现）；>1 时 `compare` 会注记 `some flips may be batching noise`。
- 输出：`os.makedirs(out_dir)` 后写 `qeval-<label>.json`，顶层字段
  `{label, url, concurrency, wall_s, utc, median_tok_s, truncated, results}`。
- 佐证（离线，不连引擎；先准备含 `API_KEY=` 的 env 文件再跑正式量）：
  ```bash
  python3 <repo>/tools/bench/qeval.py --selftest
  # 期望末行：selftest 15/15
  ```

**gsm8k（`tools/bench/gsm8k_dsv41.py`）**

- 参数风格：`--help` 实测为旗标式：`--base/--api-key/--model/--temperature/
  --max-tokens/--nq/--skip/--data/--out-raw/--out-summary`。**没有 `--base-url`、
  没有任何并发参数**（源码 `CONC = 1` 常量，顺序出题，与历史口径一致）。
- URL：`BASE = "http://127.0.0.1:8899"`（网关、**不带 `/v1`**）；请求行
  `BASE + "/v1/chat/completions"`，`--base` 值先 `rstrip("/")`。所以：
  - `--base http://127.0.0.1:<TEST_PORT>` → 正确拼出 `/v1/chat/completions`；
  - `--base http://127.0.0.1:<TEST_PORT>/v1` → 拼出 `/v1/v1/chat/completions`
    → 每题 HTTP 404（离线复现拼接结果）。**gsm8k 没有前置门**：每题的异常被
    `except` 捕获、写进该行 `err` 字段，`ok_content=False` 照常计入准确率——
    全 404 时 summary 会给你一个难看的 `accuracy_content: 0.0` 和
    `err: nq`。**先看 `err` 计数，err 大就是取数面问题，不是质量面问题。**
- 题量/题源：`--nq`（默认 200）+`--skip`；题源 `--data`（默认
  `~/data/gsm8k_test.jsonl`，或环境变量 `GSM8K_DATA`）。本仓不附题集，需自备
  GSM8K `test.jsonl`（每行含 `question`/`answer`）。
- 判分双口径：`extract_content`（boxed → 末数字）与 `extract_marker`（boxed →
  answer 标记 → 末数字），判据用 `accuracy_content`。

**needle（`tools/needle_probe.py`）**

- 参数风格：`--help` 实测为旗标式：`--base/--model/--form/--sizes/--depth/
  --seed/--json-out/--selfcheck`。
- URL：`--base` 缺省 `http://127.0.0.1:8898`（**不带 `/v1`**）；`ask()` 请求
  `base.rstrip("/") + "/v1/chat/completions"`。带 `/v1` 会拼成 `/v1/v1/…` →
  异常 → 该档记 **SKIP**（带 error 字段）。SKIP 不是 FAIL，但**全 SKIP 时
  `gate_pass=false`**（源码 gate 语义：无证据不得放行）。
- 形态门（F-2）：`--form` 默认 `auto` 按模型名判别，**判不出（含默认模型名
  `deepseek-v4.1-flash`）= unknown → ≤128k（131072）全局红线 fail-closed**。
  600k 档必须显式 `--form r1`（r1 上限 600,000）；其他登记形态与上限
  （`dense0731`/`vl`=131072，`seg0731`/`segvl`=65536，`seg600k`=600000）见
  源码 `FORM_LIMITS`。超限档 SKIP 并打印「形态门：…超限」。
- 尺寸：`--sizes` 空格多值（`nargs="+"`），默认 `8192 32768 65536 131072`。
- 埋深：`--depth` 默认 0.5（针埋在文档中点）；魔码=8 位十六进制，seed 播种
  可复现。
- 佐证（离线，不连引擎）：
  ```bash
  python3 <repo>/tools/needle_probe.py --selfcheck
  # 期望末行：SELFCHECK PASS
  ```

**accept_window（`tools/accept_window.py`，伴生）**：`--base` 缺省
`http://127.0.0.1:8898` 不带 `/v1`（抓 `GET /metrics`）；`--samples N`
（默认 10）、`--interval-s`（默认 2.0）；`--window lo,hi` 默认 `3.10,3.40`；
fallback 需 `--census`（须与 DE 同窗的 census json）+ `--de`（可多份 sd_bench
DE json）。有 `--selfcheck` 离线自测。

---

## 2. 各量具正典命令与判据

统一前置：`REPO=<repo>`；性能量具全部打测试口；每档**至少 3 次独立调用取中位**。
新到手先把三个离线自检跑绿（判别力自检纪律：新量具必须喂坏输入看它因正确理由
变红——这三个 selfcheck 就是干这个的）：

```bash
python3 <repo>/tools/bench/sd_bench.py --selfcheck   # 期望末行：SELFCHECK PASS
python3 <repo>/tools/needle_probe.py --selfcheck     # 期望末行：SELFCHECK PASS
python3 <repo>/tools/bench/qeval.py --selftest       # 期望末行：selftest 15/15
```

### 2.1 PR 七档（prefill 吞吐）

```bash
for s in 8192 16384 32768 65536 131072 262144 524288; do
  for i in 1 2 3; do
    python3 <repo>/tools/bench/sd_bench.py \
      --mode pr --sizes "$s" --pr-filler repeated \
      --base-url http://127.0.0.1:<TEST_PORT>/v1 --key-file /dev/null \
      --json-out "/tmp/pr_${s}_${i}.json"
  done
done
```

- 期望输出：每个 json 里 `pr[0]` 形如
  `{"target": 65536, "prompt_tokens": 65xxx, "ttft_s": 10.x, "tok_s": 6xxx.x,
  "prompt_chars": ..., "chars_per_token": ..., "filler": "repeated"}`。
- 0.3.2 交换机形态参考（tok/s，中位；发布档主列）：
  8192=5522.5、16384=6040.2、32768=6271.3、**65536=6289.3**、131072=6048.1、
  262144=5427.9、524288=4290.0。判读基线=**同机 0.3.1 同形基线七档全带内**
  （量具默认 ±5%）；64k 峰档主张 ≥6147.3（release note：6289.3=+2.3%）。
  绝对值受时钟/温度影响，先记 `nvidia-smi -q -d CLOCK` 再比（见 §5.5）。
- **filler 三档口径（互不可比）**：
  - `repeated`（缺省）= sparkDash 同口径，**发布档主列、锚口径**。Engram 行缓存
    会放大重复单元命中率，读数偏高——只用于同口径对照；
  - `random` = 均随机词汤，敏感性检查用；
  - `real` = 真实文本分布，用于排除重复 filler 的虚增；**与 repeated 不可直比
    绝对值**，且 real 无历史列锚，首跑即建锚（NEW-TIER）。
- `--runs` 注记：**PR 模式被忽略**（§1.1 已证），"每档 3 发"靠外层 for 循环
  三次独立调用实现。
- 批量壳：`tools/bench/pr_ladder6.sh`（六档三步法：首发+暖重+仲裁×3，仲裁轮间
  档序左旋换位；`SIZES`/`ANCHORS`/`BASE_URL` 环境变量可覆盖；`DRY_RUN=1` 干跑；
  对含 8899 的 BASE_URL 硬拒 exit 5；`BENCH_REPO` 指向 sd_bench.py 所在仓）。

### 2.2 DE 五档（decode 吞吐，mt400 正典口径）

```bash
for c in 1 2 4 8 16; do
  python3 <repo>/tools/bench/sd_bench.py \
    --mode de --type prose --concurrency "$c" --max-tokens 400 \
    --runs 5 --warmups 2 \
    --base-url http://127.0.0.1:<TEST_PORT>/v1 --key-file /dev/null \
    --json-out "/tmp/de_prose_c${c}.json"
done
```

- 期望输出：每个 json 的 `de[]` 有 5 行（`--runs 5`），每行
  `{"type": "prose", "conc": 4, "per": 4x.x, "per_all": [...], "agg": 1xx.x,
  "completion": [...]}`。
- 0.3.2 交换机形态参考（**agg 中位**，mt400）：c1=88.62（锚 88.64 域）、
  c2=128.89、c4=168.35、c8=242.83、c16=357.9（观察位）。判据：**c1 全程 ≥84**；
  **c4 对同形锚 ≥+3%**；c16 是观察位，不构成收益承诺。
- DE 数字**只与 mt400 正典口径比**：不要拿 mt64、也不要拿仪表盘数字对照。
- `--runs` 注记：DE 模式 `--runs` 生效=每档写 `de[]` N 行，**取数必须取这 N 行
  的中位**（见 §3.6），不能取 `de[0]`。
- 何时用哪个：PR 回答"长上下文灌进来多快"，DE 回答"吐字多快"；
  `--type prose` 是正典列（hash-map essay 原文提示），`--type code/json/
  structured` 另有语义（见 §3.5 内容类型纪律）。

### 2.3 GSM8K 质量门

```bash
python3 <repo>/tools/bench/gsm8k_dsv41.py \
  --base http://127.0.0.1:<PORT> --model deepseek-v4.1-flash \
  --nq 500 --temperature 0.6 --max-tokens 1024 \
  --data ~/data/gsm8k_test.jsonl \
  --out-raw /tmp/gsm8k.raw.jsonl --out-summary /tmp/gsm8k.summary.json
```

- 期望输出（summary json 关键字段）：
  `"accuracy_content": 0.98x, "err": 0, "nq": 500, "temperature": 0.6`。
- 判据：`accuracy_content` ≥0.97（0.3.2 交换机形态复读 0.985-0.99）。
- 采样态（8-shot、temp 0.6、并发 1、max_tokens 1024）必须与基线**同功率**：
  只换栈，不换题、不换温度、不换并发、不换题序。
- 有网关鉴权时用 `--api-key` 或环境变量 `DSV41_API_KEY`（本工具不回显密钥）。
- 默认 200 题、`--nq 500` 复现发布读数；题源自备（`--data`/`GSM8K_DATA`）。
- **先看 `err` 再看准确率**：`err` 大 = 取数面问题（404/超时/鉴权），不是质量
  面（§1.1 gsm8k 格）。

### 2.4 qeval 75 题质量门（改配置前后对比）

```bash
# 判别力自检（不连引擎）
python3 <repo>/tools/bench/qeval.py --selftest          # 期望 selftest 15/15

# 改配置前 / 后各跑一次（--key-file/--key-var 是顶层参数，必须在 run 之前）
python3 <repo>/tools/bench/qeval.py --key-file ~/gateway.env --key-var API_KEY run before
python3 <repo>/tools/bench/qeval.py --key-file ~/gateway.env --key-var API_KEY run after
python3 <repo>/tools/bench/qeval.py compare \
  ~/qeval-results/qeval-before.json ~/qeval-results/qeval-after.json
```

- 期望输出：run 尾行 `NN/75 passed (xx.x%)`；compare 给出
  `PRIMARY code+reason+math` 的 kept/BROKE/fixed 与 McNemar p 值，并打印
  resolution 提示（本样本量下净 5 题以下的劣化分不开噪声）。
- 用途定位：这是**配置变更门**（前后对照，看 BROKE 数），不是绝对分数榜；
  PRIMARY=code+reason+math 定质量，json+format 只报不判，prose 仅当退化哨兵。
- 401/403 判 AUTH 并拒绝出分——鉴权坏了不会被误读成质量全红。

### 2.5 needle 600k（长上下文检索）

```bash
for s in 1 2 3; do
  python3 <repo>/tools/needle_probe.py \
    --base http://127.0.0.1:<TEST_PORT> --form r1 --sizes 600000 \
    --seed "needle-600k-${s}" --json-out "/tmp/needle_600k_${s}.json"
done
```

- 期望输出：三次都 `"gate_pass": true` 且 600k 行 `"status": "PASS"` 才算 3/3。
- 水位门缺省 8000M；长上下文/大缓存 idle 形（MemAvailable 约 6.9-7.5G）设
  `NEEDLE_WATER_M=6000` 后重跑。输出 JSON 的 `water_m` 字段是**本次有效水位线**，
  `SKIP` 行 reason 同时带实测值与线值——按字段对表，不要凭残留内存推断。
- 何时用哪个：needle 答"600k 窗口里藏的针找得到吗"；PR/DE 答吞吐；
  GSM8K/qeval 答质量。全量验收=全都要，且**串行**（§0.3）。

### 2.6 warm 门（判读窗开启前的最后一道）

boot rc=0 且 health 200 后的**第一动作**是 warm 请求步（64k×2），然后 warm 门
64k×3 取中位：**≥4500 绿**（低于=红，不起测），**≥5000 入役绿线**（产线先例
6181.8；G2-RESTORE 复绿锚 5929.2）。warm 门红了不要开判读窗，先按部署指南的
验收门处置。

---

## 3. 读数纪律（数字能不能信，全在这一节）

### 3.1 每档三轮取中位，不是可选项

冷态税会系统性砸中批次里最先跑的那一发。外部站点实测同一靴 PR 8k 档三轮读到
5397/5369/**2378**、32k 档三轮读到 **4352**/6188/6202——两条最低值都是批次里
最先跑的那一发；只跑一次就采信，会把冷态税报成"−56% 性能回归"。**每档至少
3 次独立调用取中位**是最低成本手段（bench README 开篇纪律）。

### 3.2 塌陷点每轮换档 → 看单调性

多档批次里，塌陷点**每轮换地方**：第 1 轮 16k 塌、第 3 轮 8k 与 32k 塌，而同档
其余两轮都在正常带内——单看任意一轮都会报出"−45% 回归"，按档取三轮中位后全部
落回 ±5%。判读动作：**"某一格暴跌且是批次里最先跑的那格"先复测，别直接报回归；
曲线的单调性（后续档位能不能爬回来）才是干净信号**。PR 和 DE 都中这一枪
（外部站点实例：PR 首档 −52%、DE 首格 −41.9%，空载后单独复测 3 发中位反比基线
高 3.3%）。`pr_ladder6.sh` 的"仲裁轮间档序左旋换位"就是这条纪律的工程化：
位置偏差在三次中位处对消。

### 3.3 nonce 必加，否则 radix 前缀缓存给你假绿

引擎有 radix 前缀缓存：**同一提示第二次起会被整段缓存命中**。外部站点实测同一
58k 提示第 2 次起 **0.33s / 167k tok/s**——假绿。另一实例：同一批长文探测连跑
三次，第二次起耗时从 84.8s 掉到 1.9s，看起来"提速 45 倍"，查 `prompt_tokens`
三轮完全相同（395104）⇒ 引擎整段命中缓存，只补了新增 token。

- 判据：**`prompt_tokens` 与前一次完全一致 ⇒ 耗时差异来自缓存，不是性能变化**。
- 量具侧已内置：sd_bench PR 每次调用 fresh salt（uuid）防跨调用前缀缓存、
  needle 靠 seed 播种换文本。**但手发 curl 不享受这些**——自己发请求必须把
  独立 nonce 放进提示词开头：

```bash
ssh <USER>@<H1> 'curl -s http://127.0.0.1:<TEST_PORT>/v1/chat/completions \
  -H "Content-Type: application/json" -d @-' <<'EOF'
{"model": "deepseek-v4.1-flash", "max_tokens": 32, "temperature": 0,
 "messages": [{"role": "user", "content": "[nonce $(date +%s%N)] <你的长提示…>"}]}
EOF
# 期望：每次返回的 usage.prompt_tokens 都按完整提示计，耗时量级一致
```

错法：不加 nonce 连发三次，第 2 次起秒回——那是缓存，不是引擎快。

### 3.4 repeated vs real 填充：约 10% 起步的口径差，不可直比

外部站点同靴同尺寸 64k 实测：`repeated` 6056 vs `real` 5507（虚增约 10%）；
本仓 `sd_bench.py` 头注登记的口径属性更宽（MiaAI-Lab#21：repeated 单 token
重复 × Engram 行缓存命中 ⇒ **虚增 16-42%**；16k-128k 段 9-20%）。无论取哪个
数，结论一致：**两种 filler 的绝对值不可直接比**；本仓发布档主列与 γ1 锚均为
repeated（sparkDash）口径，real 是独立口径、首跑建锚。
（注意：外部手册有"锚值/门读数一律用 real 填充"的说法，那是该站点的自建锚
口径；**在本仓，与发布档/γ1 锚对照必须用 repeated**——与仓内脚本和锚表冲突时
以仓内为准。）

### 3.5 单流 tok/s 必须带内容类型

同一引擎、同一并发、同样 max_tokens，单流 tok/s 随内容类型大幅漂移（外部站点
实例）：prose 88.8 / code 141.4 / structured 160.9。机理=**投机解码的 draft
接受率依赖内容可预测性**——数数和结构化字段高度可预测，draft 多被接受；
散文最难预测。本仓可用 `tools/accept_window.py` 直接量化接受率窗（均值 ±2σ，
默认窗 3.10-3.40）。纪律：**报"这台机器多少 tok/s"必须带 `--type`**，跨类型
横比是误用；DE 正典列=`--type prose`。

### 3.6 de[] 是多轮数组：取 median，不是 [0]

单格 json 里存的是**多轮 `de[]` 数组**。`--runs 5` 写 5 行，**只取 `de[0]` 会
拿到首轮冷态值**。外部站点实例：三轮 `85.88/88.64/89.59`，`de[0]`=85.88 而中位
88.64，据此报"提升 69%"是错的。正确写法（两边都必须取中位）：

```bash
python3 - <<'EOF'
import json, statistics
d = json.load(open("/tmp/de_prose_c4.json"))
print("per_med :", statistics.median([e["per"] for e in d["de"]]))
print("agg_med :", statistics.median([e["agg"] for e in d["de"]]))
EOF
# 期望输出：两个中位数（per_med 单流、agg_med 聚合）
```

同理，**读数与上次报出去的数字不符时，第一动作是查取数方式**：同一格、同一轮次
口径、同一提取下标——全部对齐后再谈浮动。用"正常浮动"糊过去，那个解释本身可能
是假的，还会把下一次排查引向错误方向。

### 3.7 agg 是 ragged 指标：先打印 completion 数组再比读数

`agg = Σ(completion_i − 1) / (max(t_last) − min(t_first))`：分母由批次里
**最慢那条流**决定，分子是**实际产出量**。同一并发档只要各流生成长度不齐，读数
就会自己漂——structured 是负载最不齐的一档（模型自己决定停在哪），同批 16 路
会生成 30~400 各种长度。外部站点实例：五轮总 completion 1000/1150/1000/…/1150
对应 agg 257.9/335.3/304.6/…/336.6，天然带 25%~65% 极差。**判读动作：报数前
把 `de[].completion` 打出来看一眼——各轮形状不一致，就不许把差异读成提速/回归**：

```bash
python3 - <<'EOF'
import json
d = json.load(open("/tmp/de_c16.json"))
for i, e in enumerate(d["de"]):
    print(i, "sum(completion)=", sum(e["completion"]), "agg=", e["agg"])
EOF
# 期望输出：逐轮 completion 总量与 agg 并排，先看形状是否一致
```

### 3.8 并发曲线非单调：凹陷点复现两次才认

并发档 c1→c2→c4（凹陷）→c8→c16 这类非单调点，**单次出现一律归噪声**；两组
独立测试都复现才写进报告，并注明"现象已复现、根因未查"。另一面，"越并越慢且
单请求也掉"的单调恶化是通信面退到慢路径的指纹，与噪声可分——那是排障词典的
领域（见文末分工）。

---

## 4. 长上下文测法

### 4.1 用"检索题"，不要用"计数题"

外部站点实例：12k 提示 + `max_tokens=4000`，问"重复了几次"（要数数）→ 返回
`finish_reason=length` 且 `content` 为空串，看着像链路坏了；改成"只回答标记后
四位"（提取题）→ `finish=stop`、精准答对、思考链仅 107 字符。
**判据：看 `usage.completion_tokens` 是否撞到 `max_tokens` 上限——撞了就是
token 预算问题，不是链路问题**。长上下文验证一律用不需要长推理的检索/提取题
（needle 探针就是这种形态：魔码埋在文中，只要求回 8 位 hex）。

### 4.2 needle 深度档与形态门

- 深度：`--depth 0.5`（缺省，埋中点）。要多深度扫面就显式跑
  `--depth 0.25/0.5/0.75`，每次独立 seed。
- 档位与形态门：默认阶梯 8K/32K/64K/128K；600k 档**必须显式 `--form r1`**
  （auto 对默认模型名判不出形态 → unknown → ≤128k 红线 fail-closed，600k 档
  直接 SKIP）。各形态合法上限表见 §1.1 needle 格。
- 期望输出与错法：`--form r1 --sizes 600000` → 该行 `"status": "PASS"`；
  忘 `--form` → `[needle] SKIP 600000（形态门：form=unknown 上限 131072，
  档 600000 超限…）`——SKIP 不是 FAIL，但 3/3 里缺一发就不算过。

### 4.3 水位注意

- needle 每档发包前查 head 机 `MemAvailable`，低于水位线整档 SKIP（盘读/瞬态
  余量不足）。缺省 8000M；长上下文/大缓存 idle 形（MemAvailable 约 6.9-7.5G）
  按**靴形显式校准**后设 `NEEDLE_WATER_M=6000` 再跑——有效线恒记入输出
  `water_m` 字段，凭字段判读，不凭印象。
- 长档本身也吃内存：跑 600k 前先确认上一档的缓存已沉降；档与档之间看
  `water_m` 与 SKIP reason，连续 SKIP 先查内存面（§5），别当检索失败上报。

---

## 5. 内存与 GPU 观测口径

### 5.1 MemAvailable 的正解 vs `free` 第 4 列陷阱

`free` 的第 4 列（free 列）是**纯空闲**：引擎起来后页缓存会把它吃到只剩
1-3 GiB，看着像要 OOM；**真实可用在 `MemAvailable`**（含可回收页缓存）。拿错
列会把"正常"报成"只剩几 G，危险"（外部站点实测误报过）。

```bash
ssh <USER>@<H1> "awk '/^MemAvailable:/{printf \"%d MiB\n\", \$2/1024}' /proc/meminfo"
# 期望输出：一个整数 MiB 值（如 "7123 MiB"）
```

错法：`free -g` 看第 4 列报"内存只剩 2G"——那是页缓存占位，不是险情。

### 5.2 UMA 架构下，常规工具读不到 GPU 侧占用

GB10 是统一内存（UMA）：`nvidia-smi memory.used` / `ps` RSS / 容器 cgroup
**全都读不到** GPU 侧占用，显示 `N/A` **不是故障**。唯一可靠量法是
`/proc/meminfo` 穷举分类取残差（needle 的水位门就是这么实现的）。

### 5.3 禁止用"比例参数 × 总内存"倒推

某些内存比例参数的语义是"**在可用内存里**拿 N% 建静态区"，不是"占总内存 N%"
（另有缓存配额是 **per-store（每层）**额度：per-host = 值 × 层数，且该类守卫
只记 warning 不阻起——"没报警所以没事"不成立，要自己按层数乘完再对上限）。
拿比例 × 总内存倒推"剩多少给 OS"会**凭空造出不存在的数**。
**报不出的量就不给数字，先实测。**

### 5.4 GPU 被占：先核 PID 活不活

前置守卫按 `nvidia-smi --query-compute-apps=pid` 拦起栈，但那一栏可能是
**瞬时**占用（已消失的进程、图形栈残留）。拦下后先逐 PID 核活再定性：

```bash
ssh <USER>@<H1> 'nvidia-smi --query-compute-apps=pid --format=csv,noheader | \
  while read p; do [ -n "$p" ] && { [ -d "/proc/$p" ] && echo "$p alive" || echo "$p gone"; }; done'
# 期望输出：每个 PID 一行 alive/gone；背景进程占十几 MiB 不阻碍起栈
```

错法：把一次瞬时占用当成"有人在用卡"，白白放弃一靴。

### 5.5 降频唯一判法：P0 + Clocks Event Reasons；功耗数字不反推

```bash
ssh <USER>@<H1> 'nvidia-smi -q -d PERFORMANCE | grep -E "Performance State|Clocks Event Reasons" -A 8'
# 期望：Performance State : P0
#       Clocks Event Reasons 下各项（SW Power Cap / HW Slowdown / …）全为 Not Active
```

- `96% util / 28~31W / SM 时钟低于上限` 看着像被限功耗，实测可能不是：
  **功耗计数器非零只说明历史上碰过功率墙**，要跟 `Clocks Event Reasons` 一起读。
- UMA 整机形报 `Current/Max Power Limit` 为 `N/A` 是正常的，别拿它判
  "限功率被设错"；**别用功耗数字反推降频**，白查一轮。
- 绝对 tok/s 比对前先记录钟态（`nvidia-smi -q -d CLOCK`）与 warm 态
  （UPGRADE §10 纪律），否则绝对值没有可比性。

---

## 6. 报数与排程纪律

### 6.1 质量与吞吐绝不并发

§0.3 的展开：并发跑会互相抢卡，DE 各档被拉低三到四成，事后无法区分真实差距与
干扰。排程铁律：**串行队列**——PR → DE → GSM8K → qeval → needle，一条道走完；
受污染的档在引擎空闲后干净复测再采信。主链跑在本地引擎上时再加三条：开跑前
告知"这段时间会变慢"；量具期间不起并行任务；报告如实标"读数含主链自流量，
误差在噪声带内"，别装实验室读数。

### 6.2 三不比：跨量具 / 跨填充 / 跨代际

- **跨量具不比**：sd_bench 的 `per`/`agg` 与别的工具的 tok/s 不是同一算式
  （§1.1 字段差异）；仪表盘数字、mt64 数字不与 mt400 正典对照。
- **跨填充不比**：repeated/random/real 三档互不可比（§3.4）。
- **跨代际不比**：旧代引擎上做的 A/B 结论，换代后全部失效必须重做；报告里
  写清"这是哪一代引擎上的读数"，否则下一个人会拿旧结论覆盖你的。
- **跨形态不比**：环网（4 口 hairpin）与交换机（双 rail flat）的读数不可互比；
  每个形态先建自己的同形基线再对照。

### 6.3 要比，先过三道

对表/宣称差值之前，逐条自问：

1. **nonce 道**：两边量具提示词是否都防了前缀缓存（§3.3）？没 nonce 的读数
   虚增 16-42%（MiaAI-Lab#21 口径），"比谁快一倍"很可能就是缓存+代际红利。
2. **代际道**：两边是否同一代引擎、同一靴形、同一钟态？
3. **误差棒道**：某些类型（structured 的 agg、少轮单发）自身离散度就比待报
   差异宽——误差棒盖住差异时，能对表的只有：类型排序、离散度结构、曲线
   单调性与峰位。

三道有一道不过，**宁可说"不可比"，不要给一个好看但站不住的数**。

### 6.4 报不出的量不给数字；负结论写穷尽范围

- **报不出的量不给数字**（§5.3）：读不到的指标写"不可观测+原因"，不倒推。
- **负结论写穷尽范围**："没找到"没有复核价值；要写"已查 A/B/C/D 四处、
  条件是什么"，别人才能判断你漏了哪。
- **"比谁快一倍"类数字的举证责任**在报数人：先过 §6.3 三道，再落笔；凡引用
  外部数字，注明来源与口径（本文对外部站点手册数字一律标"量级示意"即此律）。

---

## 7. 长量具作业规程

### 7.1 nohup 落文件，不要前台跑

PR 七档 × 3 全程超过 7 分钟，前台 ssh 会话会被超时掐断；脚本里没 nohup 时
**ssh 断 = 任务死**。写法：

```bash
# 先把量具命令写成脚本上传（示例：PR 七档三轮），再后台起
ssh <USER>@<H1> 'nohup bash /tmp/pr_ladder.sh > /tmp/pr_ladder.log 2>&1 &'
# 期望输出：立即返回（不挂住会话）；之后看 /tmp/pr_ladder.log 与产物目录
```

### 7.2 轮询产物目录计数收尾 + pgrep 确认死活，不盲目重发

- 收尾判据=**产物目录文件数**（21 个 json = 七档×3），**别轮询日志内容**——
  日志刷新与任务完成不同步。
- 会话被掐后，**脚本可能还在远端继续跑**：先 `pgrep -af` 确认进程死活：

```bash
ssh <USER>@<H1> 'pgrep -af "sd_bench|pr_ladder" ; ls /tmp/pr_out 2>/dev/null | wc -l'
# 期望输出：进程行（活着）或空（已死）+ 产物计数；两者对得上才谈下一步
```

- 错法：不看 pgrep 直接重发——**双跑互扰**，两轮读数都废。
- 被要求"重跑一遍"时**不要原样重跑**：先改掉产生疑问的那个测量弱点（加
  warmups、改取中位、跑前加热身），**只改测量参数、不改被测配置**，并保留
  上一轮产物作基线。怀疑回归时的正确复测形态是**长窗口单格**：固定一格、
  确认空载、一次调用跑 8 轮看中位与极差（外部站点实例：8 轮 517~562、中位
  536.1、极差 8.5% = 与基线同水平，才算无回归；真回归会任何窗口都塌）。

### 7.3 rsync 不存在时，tar over ssh

```bash
# 首选 rsync
rsync -a <USER>@<H1>:/tmp/pr_out/ ./pr_out/
# 报 command not found 时改用：
ssh <USER>@<H1> 'cd /tmp/pr_out && tar czf - *.json' | tar xzf - -C ./pr_out/
# 期望输出：本地 ./pr_out/ 出现全部 json
```

注意：远端路径里的 `~` 在部分嵌套引号下**不展开**，写 `$HOME` 或绝对路径更稳。

---

## 与 PITFALLS-AND-FAQ.md 的分工

- **本文（CALIBER-AND-MEASUREMENT.md）= 怎么量才可信**：量具口径、CLI 参数
  对照、正典命令与判据、读数纪律（中位/冷态/nonce/口径）、观测口径、报数规矩、
  长量具作业规程。读者场景：要开判读窗、要出读数、要报数。
- **[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md)（排障词典）= 出了症状怎么查**：
  引擎起不来、请求 4xx/5xx、读数异常下沉到根因（网络/启动/守卫/权限各层）、
  按症状检索处置步骤。读者场景：已经红了的门、已经出现的坏读数。
- 使用顺序建议：动手量之前读本文；量出来不对劲、或量具本身报错时，带着
  本文记下的口径信息（哪个量具、哪个口、什么参数、什么报错码）去查彼文。
  两文互为入口：彼文排障若怀疑"量法问题"，回链本文对应小节；本文各纪律条
  若要查反面症状（例如"假绿长什么样"），链去彼文词条。
