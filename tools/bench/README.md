# 性能与质量量具（0.3.2 复现口径）

本目录是 0.3.2 读数的公开量具面。所有命令默认：

- 引擎测试口 `http://127.0.0.1:8898/v1`（避开生产网关 8899 的转发开销）；
- 无鉴权时 `--key-file /dev/null`；有网关鉴权时传入含 `API_KEY=` 的 env 文件；
- 每档至少 3 次独立调用取中位；`sd_bench` 的 `--runs` 只对 DE 模式生效。

跨形态纪律：**环网（4 口 CX-7 hairpin）与交换机（双 rail 2 口 flat）的读数不可互比**。
每个形态先建立自己的同形 0.3.1 基线，再做 0.3.2 对照；发布档里的 0.3.2 绝对值是
交换机形态读数。

## 1. 文件

| 文件 | 用途 |
|---|---|
| `sd_bench.py` | PR（prefill）与 DE（decode）主量具；sparkDash 口径复刻 |
| `bench_url.py` | EQ-11 共享构造处：URL 三形通吃归一（origin/v1 基/全路径 → v1 基）+ argparse 拒起首行 `ERROR[<prog>]:` 摘要到 stderr、exit 2（sd_bench/qeval/gsm8k 共用；needle 未接入） |
| `pr_ladder6.sh` | PR 六/七档阶梯的批量调用壳（`SIZES`/`ANCHORS` 可覆盖） |
| `qeval.py` + `qeval_tasks.py` | 75 题质量门（code/reason/math/json/format/prose），无 LLM 判分，自带判别力自检 |
| `gsm8k_dsv41.py` | GSM8K 8-shot CoT 质量门（默认 200 题，`--nq 500` 复现发布读数） |
| `sd_bench_real_text.patch` | `--pr-filler real` 的真实文本分布补丁（已在 `sd_bench.py` 内） |
| `qeval_own_line_num.patch` | `extract_final_number` 独占纯数字行优先修复（已在 `qeval.py` 内） |
| `../needle_probe.py` | 长上下文 needle 探针（600k 档） |

## 2. PR 七档（prefill）

```bash
REPO=$HOME/luz-deepseek-flash-all-in-one
for s in 8192 16384 32768 65536 131072 262144 524288; do
  for i in 1 2 3; do
    python3 "$REPO/tools/bench/sd_bench.py" \
      --mode pr --sizes "$s" --pr-filler repeated \
      --base-url http://127.0.0.1:8898/v1 --key-file /dev/null \
      --json-out "/tmp/pr_${s}_${i}.json"
  done
done
```

0.3.2 交换机形态参考（tok/s）：

| 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 |
|---|---|---|---|---|---|---|
| 5522.5 | 6040.2 | 6271.3 | 6289.3 | 6048.1 | 5427.9 | 4290.0 |

filler 口径：

- `repeated`（缺省）= sparkDash 同口径，发布档主列。Engram 行缓存会放大重复单元
  命中率，读数偏高，只用于同口径对照；
- `random` = 随机 token 面，用于敏感性；
- `real` = 真实文本分布，用于排除重复 filler 的虚增；与 `repeated` 不可直接比绝对值。

## 3. DE 五档（mt400 正典口径）

```bash
for c in 1 2 4 8 16; do
  python3 "$REPO/tools/bench/sd_bench.py" \
    --mode de --type prose --concurrency "$c" --max-tokens 400 \
    --runs 5 --warmups 2 \
    --base-url http://127.0.0.1:8898/v1 --key-file /dev/null \
    --json-out "/tmp/de_prose_c${c}.json"
done
```

0.3.2 交换机形态参考（agg_med）：c1=88.62（锚 88.64 域）、c2=128.89、
c4=168.35、c8=242.83、c16=357.9（观察位）。判据：c1 全程 ≥84；c4 对同形锚
≥+3%；c16 不构成收益承诺。DE 只与 mt400 正典口径比，不要拿 mt64 或仪表盘数字对照。

### 3.1 外部 prose 双读数口径注记（bug #20 落锚；0.3.4re DF-12，2026-10-30）

外部移植报告（switch-v2026.10.15-b20）在同一文档内给过两个方向相反的 prose C1
读数（83.77 与 80.77），长期挂账未锚（bug #20）。正式口径如下，**引用任一读数
必须带组标签与成立条件**（不辨口径即引用=判负，负表#16 先例）：

| 组 | 读数 | 成立条件（外部报告原文） | 用律 |
|---|---|---|---|
| C（外部组 1，带外） | prose C1 单路/聚合 **83.77 / 83.8** | 完整 2048-token 输出；与 hybrid_v2 同提示交叉控制；C1 配对完整流 3/3（外部 `reports/RESULTS.md`「四场景展示表」，`UPSTREAM-REPORT` §2.3 同表） | 形状对照位；**不入线** |
| D（外部组 2，带外） | prose 中位 **80.77** | 不改动公开 sd_bench（SHA256 `060884e4…`）；DE prose；max-tokens=400；自然停止；每类 5 次取中位；五次实际输出全部为 400（打满上限截断形）（`UPSTREAM-REPORT` §2.1） | 形状对照位；**不入线** |

- **两口径之间没有换算式**：输出预算（2048 完整 vs 400 截断）、统计形（3 配对
  完整流 vs 每类 5 次中位）与用途（交叉控制排名 vs 对锚差值）均不同，外部本身
  未合并解释。**不平均、不反向择用、不把差值（+3.0，约 +3.7%）归因任何一方**；
  跨组比较的唯一合法路径=同口径复测。
- 带差定位（各自对同一参照锚，仅注记、**非换算系数**）：组 C 对我方 82.17
  现役锚（FL6-PROMO warm；TRI-MATRIX TSV 81.83 同带、81.67 V4.1 历史锚）
  **+1.95%**；组 D 对同一锚 **−1.70%**——「同文档双读数反向」即由此来，两组
  各自成立、互不否定。
- 与本仓正典的关系：组 D 与本仓 §3 mt400 正典形制相近，但**器不同（外部公开
  sd_bench vs 本仓冻结件）、栈不同（外部站点 vs 本仓）**，仍属带外；本仓一切
  DE 判读只对本仓 mt400 正典锚。
- 登记出入：F5-PREP-HANDOFF §四 预登记表组 C 括注「自然停止、每类 5 次」实为
  组 D（§2.1）的条件描述，与外部原文不符；本落锚以外部报告原文为准。

## 4. GSM8K 质量门

题源：GSM8K `test.jsonl`（每行含 `question`/`answer`；默认
`~/data/gsm8k_test.jsonl`，可用 `--data` 或 `GSM8K_DATA` 覆盖）。本仓不附题集。

```bash
python3 "$REPO/tools/bench/gsm8k_dsv41.py" \
  --base http://127.0.0.1:8899 --model deepseek-v4.1-flash \
  --nq 500 --temperature 0.6 --max-tokens 1024 \
  --data ~/data/gsm8k_test.jsonl \
  --out-raw /tmp/gsm8k.raw.jsonl --out-summary /tmp/gsm8k.summary.json
```

判据：`accuracy_content` ≥0.97（0.3.2 交换机形态复读 0.985-0.99）。采样态
（8-shot、temp 0.6、并发 1、max_tokens 1024）必须与基线同功率；只换栈，不换题序。
有网关鉴权时用 `--api-key` 或环境变量 `DSV41_API_KEY`，本工具不回显密钥。

## 5. qeval 75 题质量门

题集与判据自带，无需外部数据；默认走网关 `127.0.0.1:8899`。

```bash
# 判别力自检（不连引擎；期望 selftest 20/20（EQ-11 后含 S11-S13 参数面断言））
python3 "$REPO/tools/bench/qeval.py" --selftest

# 改配置前 / 后各跑一次
python3 "$REPO/tools/bench/qeval.py" --key-file ~/luz-gateway.env --key-var API_KEY run before
python3 "$REPO/tools/bench/qeval.py" --key-file ~/luz-gateway.env --key-var API_KEY run after
python3 "$REPO/tools/bench/qeval.py" compare qeval-before.json qeval-after.json
```

`--key-file`/`--key-var` 是**顶层**参数，必须放在 `run`/`compare` 之前。结果默认落
`~/qeval-results`（`QEVAL_OUT` 或 `--out-dir` 可覆盖）。401/403 判 `AUTH` 并拒绝
出分，不会被误读成质量全红。

来源：题集与判据借自 knapcio 参考项目（`scripts/qeval.py` + `scripts/qeval_tasks.py`，
HEAD `6ea8acb`），逐题未改；移植只改端口、鉴权前置门和输出目录。

## 6. needle 600k

```bash
for s in 1 2 3; do
  python3 "$REPO/tools/needle_probe.py" \
    --base http://127.0.0.1:8898 --form r1 --sizes 600000 \
    --seed "needle-600k-${s}" --json-out "/tmp/needle_600k_${s}.json"
done
```

三次都 `PASS` 才算 3/3。水位门缺省 8000M；长上下文/大缓存 idle 形（MemAvailable
约 6.9-7.5G）设 `NEEDLE_WATER_M=6000` 后重跑。输出 JSON 的 `water_m` 字段是本次
有效水位线，`SKIP` 行 reason 同时带实测值与线值。
