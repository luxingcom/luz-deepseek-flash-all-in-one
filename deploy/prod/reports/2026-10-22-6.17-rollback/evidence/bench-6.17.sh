#!/usr/bin/env bash
# 6.17 rollback validation: PR seven tiers (3 independent samples each),
# DE c1/c8 (5 runs, mt400), GSM8K 20-question smoke.  Read-only against :8899.
set -uo pipefail
REPO=$HOME/luz-deepseek-flash-all-in-one
OUT=$HOME/rollback-20261022-6.17/bench-$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
BASE=http://127.0.0.1:8899/v1
BENCH="$REPO/tools/bench/sd_bench.py"

echo "OUT=$OUT"
for s in 8192 16384 32768 65536 131072 262144 524288; do
  for i in 1 2 3; do
    echo "== PR $s rep$i =="
    python3 "$BENCH" --mode pr --sizes "$s" --pr-filler repeated \
      --base-url "$BASE" --key-file /dev/null \
      --json-out "$OUT/pr_${s}_${i}.json" || echo "PR_FAIL ${s} ${i}"
  done
done

for c in 1 8; do
  echo "== DE c$c =="
  python3 "$BENCH" --mode de --type prose --concurrency "$c" --max-tokens 400 \
    --runs 5 --warmups 2 --base-url "$BASE" --key-file /dev/null \
    --json-out "$OUT/de_c${c}.json" || echo "DE_FAIL ${c}"
done

echo "== GSM8K 20 =="
python3 "$REPO/tools/bench/gsm8k_dsv41.py" \
  --base http://127.0.0.1:8899 --model deepseek-v4.1-flash \
  --nq 20 --temperature 0.6 --max-tokens 1024 \
  --data "$HOME/data/gsm8k_test.jsonl" \
  --out-raw "$OUT/gsm8k-20.raw.jsonl" \
  --out-summary "$OUT/gsm8k-20.summary.json" || echo "GSM8K_FAIL"

echo "DONE $OUT"
