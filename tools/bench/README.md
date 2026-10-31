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

> **跨代口径注记（2026-10-31）**：上行 0.3.2 参考值仅历史列（K16-off/mt400 正典口径）；
> 0.3.4 判读线=T33-03 PR 锚 **4384.8**／DE c1 锚 **91.64**／liter **≥3700**（判读以
> [034-PERF-REPORT](../../docs/report/034-PERF-REPORT-20261029.md) §一/§七代际节 为准），
> 跨代数字不比、防口径差误读为涨跌。

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

## 7. 2026-10-31 缺件回填件身份台账（SOURCE-MD5 式；md5 均为 2026-10-31 落盘实测）

正典锚指内部原件/战役形（[MANIFEST-034LOCK](../../docs/release/MANIFEST-034LOCK.tsv) 段二制式）；
公开树与战役工作区布局不同构属预期（包装器按战役布局设计），本目录件均逐字节拷自战役仓正典位
（dcgm-collector 为 $HOME 化改写形，锚指内部原件）。分叉声明=[0.3.4re-RELEASE-NOTE](../../docs/release/0.3.4re-RELEASE-NOTE.md) 卷首。

| 件 | md5（落盘实测） | 身份与正典锚 | 用法一行 | 口径对应 | 依赖 |
|---|---|---|---|---|---|
| `../conc_pr_driver.py` | `333033ce` | 量具·liter C1 512k 判读主门（锚=MANIFEST-034LOCK 段二 `conc_pr_driver.py` 行同值逐字节） | `conc_pr_driver --base-url <引擎口v1基> --lit-dir <liter语料目录> --size 524288 --conc 1 --runs 1 --json-out <out.json>`（五参均必设） | liter C1 ≥3700 快带/≤3450 退化停窗 | 引擎口 v1 基＋liter 语料目录（`corpus/s-eng-lit7` 未入公开树，见下） |
| `../de_c48_bench.py` | `a337f64e` | 量具·DE c1 判读门+EQOBS dec48 锚点（锚=MANIFEST-034LOCK 段二 `de_c48_bench.py` 行同值逐字节） | `de_c48_bench --tiers 1 --runs 5 --warmups 2 --arb-rounds 3 --anchors 1:91.64 --bench-repo <布线仓根> --campaign <战役仓根>` | DE c1 ≥91；对锚 ±3% IN-BAND（de_c48 口径，与 sd_bench 口径分列） | importlib 直载 `<bench-repo>/bench/sd_bench.py`，其 md5 硬钉 `410f543d`、失配即 ABORT（`SD_MD5_OVERRIDE` 显式重钉例外）。**布线**=把 `frozen/sd_bench-410f543d.py` 拷为 `<布线仓根>/bench/sd_bench.py` 再传 `--bench-repo <布线仓根>`；公开现值 `../sd_bench.py`（`4234672e`）与冻结件 diff 265 差异行（2026-10-31 实测），**不可**充任该位（必 ABORT） |
| `../eqgate/eq_capture.py` | `f8e3fa18` | B1 EQ-S 采集件（盐 `R1EQ2026` 内建；"secret access code"=needle 测试题面非凭据） | EQ-S 同盐夹心 capture pre/post | EQ-S GREEN 6/6=PASS 门 | 引擎口 |
| `../eqgate/eq_compare.py` | `5e62291e` | B1 逐字比对件（GREEN 6/6 判定器） | `eq_compare` 对照 pre/post 逐字相等 | 同上 | 纯本地 |
| `../lit_driver.py` | `0fb5a0c4` | liter 串行臂（BENCHMARK-SOURCE §5.1 在册锚同值） | liter 语料串行灌入驱动 | liter 面辅助臂 | `corpus/s-eng-lit7` 语料（未入公开树，见下） |
| `../pr_ladder7_lit.sh` | `6dcbee00` | liter 调用面（战役正典位逐字节） | liter 阶梯批量调用壳 | liter C1 512k 档 | `lit_driver.py`+语料 |
| `../de_c48_ladder.sh` | `5cc3578e` | DE 五档梯上盖/PERFDIAG 调用面（战役正典位逐字节） | DE c1-c16 五档批量驱动 | §3 DE 五档同口径 | `de_c48_bench.py` |
| `../census_aggregate_v31.py` | `c8ed9b0f` | census v3.1 聚合（MANIFEST-034LOCK 段二 `census_aggregate_v31.py` 行登记位；旧名 `census_aggregate.py` 并存不删） | census 采集后聚合 | census 面（时长层专用窗留位） | census 采集输出 |
| `logs/S-034-X5-RUN-20261027/tool/x5_mixed_ttft.py`（公开树根 logs/ 下） | `0b9a5200` | 量具·混合 TTFT 探针（MANIFEST-034LOCK 段二 `x5_mixed_ttft.py` 行登记路径落位） | BYPASS A/B M1 面混合 TTFT 探针 | 记录面（M1 推导锚，非硬门） | 引擎口 |
| `logs/S-034-RB033-20261028/phase3-payloads/dcgm/dcgm-collector.sh`（公开树根 logs/ 下） | 改写形 `27f8bf20`（2026-10-31 实测；锚 `50460f66` 指内部原件，$HOME 化改写故 md5 必不同） | dcgm 采集件（五族+RDMA 四口，60s×四机），:10/:17 内部路径已 $HOME 化 | `dcgm-collector.sh start\|stop`（**用法=start/stop 两态**；输出目录非命令行参数，在件内 :10/:17 内置为 `$HOME/luz030-opt-campaign/logs/S-034-RB033-20261028/phase3-payloads/dcgm`，起止由调用方控） | dcgm 伴随观测正典（util/SM/power/temp/PCIE_REPLAY） | nvidia dcgm 输出面＋四机 ssh 免密 |
| `sample500.jsonl` | `7e4deefc`（帧锚，非单文件全档） | 500q 冻结帧（CFG-33：帧漂移=500q 读数不可比） | `gsm8k_dsv41 --nq 500 --data sample500.jsonl` | 500q 地板 0.955、带 [0.956,0.982] | `gsm8k_dsv41.py` |
| `frozen/sd_bench-410f543d.py` | `410f543d` | **冻结原件并存回填**（公开现值 `4234672e`=EQ-11/DF-04 产品化形，禁覆盖） | 0.3.4 判读读数的产生原件（--key-file /dev/null） | §2/§3 主量具（判读对 T33-03 锚） | 引擎口 |
| `frozen/gsm8k_dsv41-72f9197b.py` | `72f9197b` | **冻结原件并存回填**（公开现值 `b3a756cc`=EQ-11 契约化修复形，禁覆盖） | 0.3.4 判读 500q 读数的产生原件（API_KEY=env `DSV41_API_KEY`，缺省占位符无凭据） | §4 GSM8K 质量门 | GSM8K 题集（本仓不附） |

**仍缺席两件（暂不公开+原因）**：`ppl_collect_native.py`（内部路径硬编码，须 $HOME 化改写+
终审后另批——B7-PPL 量具缺席=公开树电池 B7 不可跑，如实注记）、`corpus/s-eng-lit7`（liter
语料数据件，版权/来源未审）。缺席属公开树布局缺口如实登记，**非「验收链损坏」**
（[BENCHMARK-SOURCE](../../docs/registry/BENCHMARK-SOURCE.md) §5.1 分叉注记同源）。
