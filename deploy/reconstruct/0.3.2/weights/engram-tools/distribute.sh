#!/bin/bash
# Distribute rank1/2/3 Engram shards to their machines and verify SHA256 there.
set -euo pipefail
OUT=${OUT:-$HOME/dsv41-engram-1017}
LOG=$OUT/tools/pipeline.log
exec >>"$LOG" 2>&1
echo "=== $(date +%F' '%T) distribute ==="

declare -A HOST=( [1]=${HOST_R1:-10.10.1.21} [2]=${HOST_R2:-10.10.1.41} [3]=${HOST_R3:-10.10.1.31} )
for r in 1 2 3; do
  h=${HOST[$r]}
  ssh -o BatchMode=yes -o StrictHostKeyChecking=no "$h" "mkdir -p \$HOME/dsv41-engram-1017"
  echo "--- $(date +%F' '%T) rank$r -> $h"
  rsync -a --partial --info=progress2 -e "ssh -o BatchMode=yes -o StrictHostKeyChecking=no" \
    "$OUT/staging/r$r/" "$h:dsv41-engram-1017/"
done

echo "=== $(date +%F' '%T) verify remote ==="
python3 "$OUT/tools/verify_remote.py"
echo "=== $(date +%F' '%T) distribution complete ==="
