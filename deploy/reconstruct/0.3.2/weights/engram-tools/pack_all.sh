#!/bin/bash
# Wait for the two engram shards of DeepSeek-V4.1-Flash-1017 to be complete
# and hash-verified, then pack all 4 Tensor-Parallel ranks.
set -euo pipefail

TGT=/data/models/DeepSeek-V4.1-Flash-1017
MAN=/data/models/.manifests/DeepSeek-V4.1-Flash-1017.json
META=/data/models/.manifests/1017-meta
PACK=${PACK:-$(cd "$(dirname "$0")" && pwd)/pack_engram.py}
OUT=${OUT:-$HOME/dsv41-engram-1017}
VIEW=$OUT/model-view
LOG=$OUT/tools/pipeline.log

mkdir -p "$OUT" "$OUT/tools" "$VIEW" "$OUT/staging/r1" "$OUT/staging/r2" "$OUT/staging/r3"
cp -f "$META/config.json" "$VIEW/config.json"
cp -f "$META/model.safetensors.index.json" "$VIEW/model.safetensors.index.json"
ln -sfn "$TGT/model-00047-of-00048.safetensors" "$VIEW/model-00047-of-00048.safetensors"
ln -sfn "$TGT/model-00048-of-00048.safetensors" "$VIEW/model-00048-of-00048.safetensors"
exec >>"$LOG" 2>&1
echo "=== $(date +%F' '%T) wait for engram shards ==="

fails=0
while :; do
  if [ ! -e "$TGT/model-00047-of-00048.safetensors.aria2" ] && \
     [ ! -e "$TGT/model-00048-of-00048.safetensors.aria2" ]; then
    if python3 - "$TGT" "$MAN" <<'PY'
import hashlib, json, os, sys
tgt, man = sys.argv[1:3]
want = {m["path"]: m for m in json.load(open(man))}
for name in ("model-00047-of-00048.safetensors", "model-00048-of-00048.safetensors"):
    p = os.path.join(tgt, name)
    m = want[name]
    if not os.path.exists(p) or os.path.getsize(p) != m["size"]:
        print(f"{name}: size mismatch/absent", flush=True); sys.exit(1)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 26), b""):
            h.update(chunk)
    ok = h.hexdigest() == m["sha256"]
    print(f"{name}: sha256 {'OK' if ok else 'MISMATCH'}", flush=True)
    if not ok:
        sys.exit(1)
PY
    then
      echo "$(date +%F' '%T) engram shards verified, starting pack"
      break
    fi
    fails=$((fails+1))
    echo "$(date +%F' '%T) shards hash not ready (attempt $fails), retry in 5 min"
    if [ "$fails" -ge 12 ]; then
      echo "$(date +%F' '%T) FATAL: shards never hashed clean; stopping"
      exit 1
    fi
  else
    echo "$(date +%F' '%T) shards still downloading, retry in 5 min"
  fi
  sleep 300
done

for r in 0 1 2 3; do
  if [ "$r" = 0 ]; then out="$OUT"; else out="$OUT/staging/r$r"; fi
  echo "=== $(date +%F' '%T) pack rank $r -> $out ==="
  python3 "$PACK" --model "$VIEW" --out "$out" --rank "$r" --tp 4 --layers 1,14
done

echo "=== $(date +%F' '%T) pack done ==="
ENGRAM_MODEL="$VIEW" python3 "$OUT/tools/verify_engram.py"
