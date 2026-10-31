#!/usr/bin/env bash
# de_c48_ladder.sh — DE prose c1/c4/c8 三档正典量测 runbook（S-DE48TOOL；用户令六量具面）
#
# 【是什么】tools/de_c48_bench.py 的运维包络（量具本体/口径/自检在彼件件首）；本壳负责
#   campaign 惯例的操作面：ARM_TAG 输出布局（logs/<ARM_TAG>/dec48/<ts>/）、水位看护采样、
#   压测互斥检查、timeout 护栏、日志 tee——pr_ladder6.sh 同构位。
#
# 【口径一句话】prose mt400 直连 8899（与电池卡 D3 同口同法同语料：sd_bench run_de 直载
#   md5 钉 f0dd91c4）；三步法=A 首发+B 暖重+C 仲裁×3 轮间档序左旋；主量=agg_med（c1 时
#   agg≡per，与 A6-ANCHOR-7 prose 88.06 同量同义）；报数必带 arb_med+P95/P99+流级公平性
#   （jain/slow_ratio/completion 完整性）——防单流饿死假读数。
#
# 【与 pr_ladder6 的 8899 律差异（勿混）】pr_ladder6 面向 staging 靴（:8898）故硬拒 8899；
#   本件=在役电池面量具（电池卡 D3/E16B1 卡 9a 同形态，直连 8899 在役口）。代价=互斥纪律
#   必须执行：半速律（DE-CALIBER-VERIFY §3，任何一条并发流把 c1 减半）⇒ ①测者一次只留
#   一侧在跑；②跑前 pgrep 互斥检查（SKIP_MUTEX=1 才可豁免，须窗档注记）；③Mac 侧 rgw
#   巡检流量零撞窗（对时法 DE-CALIBER-VERIFY §4：docker logs responses-gateway-mac --since 15m）。
#
# 【用法】
#   ARM_TAG=<窗标> bash tools/de_c48_ladder.sh                    # 真跑（引擎 8899 须在役）
#   ARM_TAG=selftest DRY_RUN=1 bash tools/de_c48_ladder.sh        # 干跑：cell 计划零发包
#   python3 tools/de_c48_bench.py --selfcheck                     # 离线自检（零网络）
# 环境变量：
#   ARM_TAG(默认 unknown)      输出 logs/<ARM_TAG>/dec48/<ts>/（py 件内建）
#   BASE_URL(默认 http://127.0.0.1:8899/v1)  mt400 直连正典口
#   TIERS(默认 "1,4,8")        档集（DE-48 列=c1/c4/c8；c16 观察位归 E16 卡）
#   ANCHORS(默认 "1:88.06")    档:锚；c4/c8 建锚后传 "1:88.06 4:<v> 8:<v>"
#   BAND_PCT(默认 3)           带判 ±%（DE-1/PR 容忍带先例）
#   ARB_ROUNDS(默认 3) RUNS(默认 5) WARMUPS(默认 2) FIRST_WARM(默认 1) MAX_TOKENS(默认 400)
#   STEP_TIMEOUT_S(默认 3600)  整梯 timeout 护栏（15 cell×~1-3min 预算 + 余量）
#   DRY_RUN(默认 0) SKIP_MUTEX(默认 0)   BENCH_REPO/CAMPAIGN(默认 ~/dsv41-flash-dgxsparks/~/luz030-opt-campaign)
#
# 【输出】logs/<ARM_TAG>/dec48/<ts>/：de48_prose_c{t}_{phase}.json（逐 cell 原始）+
#   de48_summary.json/tsv（三档判定表+tri_tier 合成判）+ de_c48.log + water.txt（本壳）。
# 【护栏】互斥检查；水位 15s 采样（<6G WATCH 行；<4GiB STOP-TEST=停测杀梯）；整梯 timeout；
#   sudo 零用；02 两不动域/netplan 零触；密钥零入档；本件不起靴不碰集群只发 DE 请求。
set -uo pipefail

ARM_TAG="${ARM_TAG:-unknown}"
DRY_RUN="${DRY_RUN:-0}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8899/v1}"
TIERS="${TIERS:-1,4,8}"
ANCHORS="${ANCHORS:-1:88.06}"
BAND_PCT="${BAND_PCT:-3}"
ARB_ROUNDS="${ARB_ROUNDS:-3}"
RUNS="${RUNS:-5}"
WARMUPS="${WARMUPS:-2}"
FIRST_WARM="${FIRST_WARM:-1}"
MAX_TOKENS="${MAX_TOKENS:-400}"
STEP_TIMEOUT_S="${STEP_TIMEOUT_S:-3600}"
SKIP_MUTEX="${SKIP_MUTEX:-0}"
BENCH_REPO="${BENCH_REPO:-$HOME/dsv41-flash-dgxsparks}"
CAMPAIGN="${CAMPAIGN:-$HOME/luz030-opt-campaign}"
BENCH="$CAMPAIGN/tools/de_c48_bench.py"

# ── 护栏 ──────────────────────────────────────────────────────────────────
[ -f "$BENCH" ] || { echo "ABORT: 缺 $BENCH" >&2; exit 5; }
command -v python3 >/dev/null || { echo "ABORT: 无 python3" >&2; exit 5; }
[ -f "$BENCH_REPO/bench/sd_bench.py" ] || { echo "ABORT: 缺 $BENCH_REPO/bench/sd_bench.py" >&2; exit 5; }

if [[ "$SKIP_MUTEX" != "1" && "$DRY_RUN" != "1" ]]; then
  others=$(pgrep -af "sd_bench.py|pr_ladder6|lit_driver|census_capture|de_c48_bench" | grep -v "de_c48_ladder\|$$" || true)
  if [ -n "$others" ]; then
    echo "ABORT: 压测互斥纪律——在跑量测件检出（半速律污染 c4/c8 读数）：" >&2
    echo "$others" >&2
    exit 5
  fi
fi

# ── 水位看护（battery 卡 9a 同源；R25-a 三件套同语义）──────────────────────
# 卫生窗修正①（S-LOCKCLEAN-20261020；R30-c 处结）：water 子壳重定向补齐——原 echo 落
#   stdout 混入 ladder 日志（S-L2RB §四-2：water_*.txt 未生成、需自 stdout 手工抽出）。
# 卫生窗修正②（同窗）：水位原生 CSV 落盘（.csv 名正字）+收梯 min 行自 CSV 抽取入日志
#   ——免窗后手工 stdout 抽取（water_extracted_*.csv 补档操作不再需要）。
TS="$(date +%Y%m%d-%H%M%S)"
OUTROOT="$CAMPAIGN/logs/$ARM_TAG/dec48"
mkdir -p "$OUTROOT"
WATER="$OUTROOT/water_$TS.csv"
WW_PID=""
if [[ "$DRY_RUN" != "1" ]]; then
  ( echo "# ts,memavail_mb"; while :; do
      m=$(awk '/^MemAvailable:/{print int($2/1024)}' /proc/meminfo)
      echo "$(date -u +%FT%TZ),$m"
      if [ "${m:-99999}" -lt 4096 ]; then
        pkill -f "de_c48_bench.py" 2>/dev/null
        echo "$(date -u +%FT%TZ),STOP-TEST-4GiB" ; break
      fi
      sleep 15
    done ) > "$WATER" 2>&1 &
  WW_PID=$!
  echo "water_watch pid=$WW_PID -> $WATER（<4GiB=STOP-TEST 停梯；水位 CSV 原生落盘）"
fi

echo "== de_c48_ladder 启动 ARM_TAG=$ARM_TAG tiers=$TIERS base=$BASE_URL DRY_RUN=$DRY_RUN =="
echo "   口径: prose mt400 直连（DE 报数必带 maxTokens=$MAX_TOKENS）；anchors=[$ANCHORS] band=±${BAND_PCT}%"
echo "   纪律: 半速律互斥（测者一侧独跑+Mac rgw 零撞窗）；本件不起靴不碰集群"

timeout "$STEP_TIMEOUT_S" python3 "$BENCH" \
  --arm-tag "$ARM_TAG" --base-url "$BASE_URL" --tiers "$TIERS" \
  --max-tokens "$MAX_TOKENS" --runs "$RUNS" --warmups "$WARMUPS" \
  --arb-rounds "$ARB_ROUNDS" --first-warm "$FIRST_WARM" \
  --anchors "$ANCHORS" --band-pct "$BAND_PCT" \
  --bench-repo "$BENCH_REPO" --campaign "$CAMPAIGN" \
  $([[ "$DRY_RUN" == "1" ]] && echo --dry-run) 2>&1 | tee "$OUTROOT/ladder_$TS.log"
rc=${PIPESTATUS[0]}

[ -n "$WW_PID" ] && kill "$WW_PID" 2>/dev/null
sleep 1   # 子壳收尾 flush（STOP-TEST 尾行落盘）
if [ -f "$WATER" ]; then
  wmin=$(awk -F, 'NR>1 && $2+0>0 {if(m==""||$2+0<m)m=$2+0} END{print (m==""?"?":m)}' "$WATER")
  wstop=$(grep -c "STOP-TEST" "$WATER" || true)
  echo "water_summary: min_memavail_mb=$wmin stop_test=$wstop（CSV=$WATER）"
fi
echo "== de_c48_ladder 完 rc=$rc（判定表见 de48_summary.tsv；NEW-TIER 档=首跑建锚 DE-48 列位）=="
exit "$rc"
