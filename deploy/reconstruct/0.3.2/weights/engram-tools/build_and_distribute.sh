#!/bin/bash
# End-to-end: wait for engram shards -> pack 4 ranks -> verify -> distribute -> verify remote.
set -euo pipefail
OUT=${OUT:-$HOME/dsv41-engram-1017}
TOOLS="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT/tools"
cp -f "$TOOLS"/pack_engram.py "$TOOLS"/pack_all.sh "$TOOLS"/distribute.sh \
      "$TOOLS"/verify_engram.py "$TOOLS"/verify_remote.py "$OUT/tools/"
bash "$OUT/tools/pack_all.sh"
bash "$OUT/tools/distribute.sh"
