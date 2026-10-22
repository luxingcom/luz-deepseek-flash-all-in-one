#!/usr/bin/env bash
# selfcheck-prod.sh — verify that the running production stack still matches
# the pinned profile.  Read-only: it never restarts or reconfigures anything.
#
#   --fast       health + env + argv + overlay/recipe md5 + banner + ring (timer)
#   --post-boot  above + functional recipe probe + 64k warm gate
#   --perf       above + warm gate only (skip probe)
set -uo pipefail

PROFILE="${PROD_PROFILE:-$HOME/migrate-assets/prod/prod-profile.env}"
# shellcheck disable=SC1090
source "$PROFILE"

MODE="${1:---fast}"
[[ "$MODE" == "--fast" || "$MODE" == "--post-boot" || "$MODE" == "--perf" ]] || {
  echo "usage: $0 [--fast|--post-boot|--perf]" >&2; exit 2;
}
SELFCHECK="${PROD_SELFCHECK:-$HOME/migrate-assets/prod/selfcheck-prod.sh}"
TS="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="${PROD_LOG_DIR:-$HOME/r3-prod-logs}"
mkdir -p "$OUT_DIR"
TSV="$OUT_DIR/selfcheck-$TS.tsv"
LOG="$OUT_DIR/selfcheck-$TS.log"
JSON="$OUT_DIR/selfcheck-latest.json"
: > "$TSV"
exec > >(tee -a "$LOG") 2>&1

LOCAL="$(hostname -s)"
HOSTS=(${PROD_HOSTS})
fails=0
record(){
  local st="$1" name="$2" detail="$3"
  printf '%s\t%s\t%s\n' "$st" "$name" "$detail" >> "$TSV"
  printf '[%s] %-22s %s\n' "$st" "$name" "$detail"
  [[ "$st" == PASS ]] || fails=$((fails+1))
}
run_on(){
  local h="$1" cmd="$2"
  if [[ "$h" == "$LOCAL" ]]; then bash -c "$cmd"; else ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" "$cmd"; fi
}

# ── stack presence ──────────────────────────────────────────────────────────
names=$(docker ps --format '{{.Names}}' 2>/dev/null || true)
if ! printf '%s\n' "$names" | grep -qx "${PROD_CTN_PREFIX}-head"; then
  if [[ "$MODE" == "--fast" ]]; then
    echo "[SKIP] ${PROD_CTN_PREFIX}-head is not running; periodic check skipped"
    exit 0
  fi
  record FAIL stack "no ${PROD_CTN_PREFIX}-head container"
  exit 1
fi
record PASS stack "${PROD_CTN_PREFIX}-head running"

# ── health ──────────────────────────────────────────────────────────────────
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${PROD_API_PORT}/health" || true)
[[ "$code" == 200 ]] && record PASS health "HTTP 200" || record FAIL health "HTTP ${code:-000}"

# ── server_info truth ───────────────────────────────────────────────────────
si=$(curl -fsS --max-time 10 "http://127.0.0.1:${PROD_API_PORT}/server_info" 2>/dev/null || true)
tok=$(grep -oE '"max_total_num_tokens":[ ]*[0-9]+' <<<"$si" | head -1 | grep -oE '[0-9]+$')
ctx=$(grep -oE '"context_length":[ ]*[0-9]+' <<<"$si" | head -1 | grep -oE '[0-9]+$')
mrr=$(grep -oE '"max_running_requests":[ ]*[0-9]+' <<<"$si" | head -1 | grep -oE '[0-9]+$')
if [[ "$tok" == 9600000 && "$ctx" == 600000 && "$mrr" == 16 ]]; then
  record PASS server_info "tok=$tok ctx=$ctx mrr=$mrr"
else
  record FAIL server_info "tok=${tok:-?} ctx=${ctx:-?} mrr=${mrr:-?}"
fi
curl -fsS --max-time 10 "http://127.0.0.1:${PROD_API_PORT}/v1/models" 2>/dev/null | grep -q '"id":[ ]*"deepseek-v4.1-flash"' \
  && record PASS model_id "deepseek-v4.1-flash" || record FAIL model_id "missing served model id"

# ── container env (four ranks) ──────────────────────────────────────────────
PYENV=$(mktemp)
cat > "$PYENV" <<'PY'
import json, sys
envfile, raw = sys.argv[1], sys.argv[2]
wanted = {}
for line in open(envfile, errors='replace'):
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    wanted[k] = v
got = {}
for item in json.load(open(raw)):
    if '=' in item:
        k, v = item.split('=', 1)
        got[k] = v
bad = [k for k, v in wanted.items() if got.get(k) != v]
print(f'{len(wanted)} keys; missing/mismatch={len(bad)}' + ((' first=' + bad[0]) if bad else ''))
sys.exit(1 if bad else 0)
PY
for h in "${HOSTS[@]}"; do
  ctn="${PROD_CTN_PREFIX}-worker"
  [[ "$h" == "$LOCAL" ]] && ctn="${PROD_CTN_PREFIX}-head"
  raw=$(mktemp)
  if [[ "$h" == "$LOCAL" ]]; then
    docker inspect "$ctn" --format '{{json .Config.Env}}' > "$raw" 2>/dev/null
  else
    ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" "docker inspect $ctn --format '{{json .Config.Env}}'" > "$raw" 2>/dev/null
  fi
  if python3 "$PYENV" "$PROD_ARM_ENV_FILE" "$raw"; then
    record PASS "env:$h" "$(python3 "$PYENV" "$PROD_ARM_ENV_FILE" "$raw")"
  else
    record FAIL "env:$h" "$(python3 "$PYENV" "$PROD_ARM_ENV_FILE" "$raw" 2>&1)"
  fi
  rm -f "$raw"
done

# ── argv ────────────────────────────────────────────────────────────────────
PYARGV=$(mktemp)
cat > "$PYARGV" <<'PY'
import json, sys
raw = json.load(open(sys.argv[1]))
if isinstance(raw, list):
    text = ' '.join(str(x) for x in raw)
else:
    text = str(raw)
required = [
    '--tool-call-parser deepseekv41', '--enable-cache-report', '--sleep-on-idle',
    '--speculative-algorithm DSPARK', '--prefill-decode-interval 16',
    '--max-queued-requests 32', '--min-free-slots-delay 1',
    '--enable-decoder-swa-bounded-replay', '--reasoning-parser deepseek-v41',
    '--swa-prefix-tails 256',
]
missing = [x for x in required if x not in text]
print('all SPEC6/SPEC1 args present' if not missing else 'missing: ' + ', '.join(missing))
sys.exit(1 if missing else 0)
PY
argv_raw=$(mktemp)
docker inspect "${PROD_CTN_PREFIX}-head" --format '{{json .Config.Cmd}}' > "$argv_raw" 2>/dev/null
if [[ "$(tr -d '[:space:]' < "$argv_raw")" == "null" ]]; then
  docker inspect "${PROD_CTN_PREFIX}-head" --format '{{json .Args}}' > "$argv_raw" 2>/dev/null
fi
if python3 "$PYARGV" "$argv_raw"; then
  record PASS argv "$(python3 "$PYARGV" "$argv_raw")"
else
  record FAIL argv "$(python3 "$PYARGV" "$argv_raw" 2>&1)"
fi
rm -f "$argv_raw" "$PYARGV" "$PYENV"

# ── overlay mounts + in-container md5 ───────────────────────────────────────
PYMNT=$(mktemp)
cat > "$PYMNT" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
n = sum(1 for x in m if '/sgl-workspace/sglang/python/sglang' in (x.get('Destination') or ''))
print(f'{n} overlay mounts')
sys.exit(0 if n == 28 else 1)
PY
mnt=$(mktemp)
docker inspect "${PROD_CTN_PREFIX}-head" --format '{{json .Mounts}}' > "$mnt" 2>/dev/null
if python3 "$PYMNT" "$mnt"; then record PASS overlay "$(python3 "$PYMNT" "$mnt")"; else record FAIL overlay "$(python3 "$PYMNT" "$mnt" 2>&1)"; fi
rm -f "$mnt" "$PYMNT"

md5out=$(docker exec "${PROD_CTN_PREFIX}-head" md5sum \
  /sgl-workspace/sglang/python/sglang/srt/entrypoints/openai/serving_chat.py \
  /opt/dsv41/adapter/dsv41_recipe.py 2>/dev/null || true)
if grep -q "$PROD_SERVING_CHAT_MD5" <<<"$md5out" && grep -q "$PROD_RECIPE_MD5" <<<"$md5out"; then
  record PASS in_container_md5 "serving_chat=$PROD_SERVING_CHAT_MD5 recipe=$PROD_RECIPE_MD5"
else
  record FAIL in_container_md5 "$(tr '\n' ' ' <<<"$md5out")"
fi

# ── banner gates ────────────────────────────────────────────────────────────
blog=$(docker logs "${PROD_CTN_PREFIX}-head" 2>&1 || true)
gates=$(grep -ac 'banner complete: 29 gates' <<<"$blog" || true)
if [[ "$gates" -ge 1 ]] && grep -aq 'kv_fp4.*active=True' <<<"$blog" && grep -aq 'lm_cert.*built' <<<"$blog" \
   && grep -aq 'prefill_sp.*armed=True' <<<"$blog"; then
  record PASS banner "banner29=$gates kv_fp4=on lm_cert=built prefill_sp=armed"
else
  record FAIL banner "banner29=$gates kv_fp4/lm_cert/prefill_sp gate missing"
fi

# ── host ring + kernel ──────────────────────────────────────────────────────
for h in "${HOSTS[@]}"; do
  if out=$(run_on "$h" "RX_TARGET=$PROD_RX_RING FW_TARGET=$PROD_NIC_FW_ALLOW LOSSLESS_BUFFER=$PROD_LOSSLESS_BUFFER bash /usr/local/sbin/roce-ring-apply.sh check" 2>&1); then
    record PASS "ring:$h" "rx=$PROD_RX_RING"
  else
    record FAIL "ring:$h" "$(tr '\n' ' ' <<<"$out")"
  fi
done
for h in "${HOSTS[@]}"; do
  k=$(run_on "$h" 'uname -r' 2>/dev/null || true)
  case " $PROD_KERNEL_ALLOW " in
    *" $k "*) record PASS "kernel:$h" "$k" ;;
    *) record FAIL "kernel:$h" "$k not allowed" ;;
  esac
done

# ── functional recipe probe ─────────────────────────────────────────────────
if [[ "$MODE" == "--post-boot" ]]; then
  probe=$(docker exec -i "${PROD_CTN_PREFIX}-head" python3 - < "$PROD_RECIPE_PROBE" 2>&1 || true)
  if grep -q '"ok": true' <<<"$probe"; then
    record PASS recipe_probe "$(grep '"ok": true' <<<"$probe" | tail -1)"
  else
    record FAIL recipe_probe "$(tail -1 <<<"$probe")"
  fi
fi

# ── adapter tree fingerprint (four hosts) ───────────────────────────────────
ADAPTER_DIR="$HOME/migrate-assets/dsv41/adapter"
fp_cmd="cd '$ADAPTER_DIR' && find . -type f ! -path '*__pycache__*' | LC_ALL=C sort | xargs -r md5sum 2>/dev/null | LC_ALL=C sort | md5sum | cut -c1-8"
for h in "${HOSTS[@]}"; do
  fp=$(run_on "$h" "$fp_cmd" 2>/dev/null || true)
  if [[ "$fp" == "$PROD_ADAPTER_FINGERPRINT" ]]; then
    record PASS "adapter:$h" "fingerprint=$fp files=$PROD_ADAPTER_FILES"
  else
    record FAIL "adapter:$h" "fingerprint=${fp:-?} != $PROD_ADAPTER_FINGERPRINT (adapter-sync --check)"
  fi
done

# ── NIC firmware + lossless buffer (first port on each host) ─────────────────
for h in "${HOSTS[@]}"; do
  line=$(run_on "$h" "ethtool -i enp1s0f0np0 | awk '/firmware-version/{print \$2}'; mlnx_qos -i enp1s0f0np0 2>/dev/null | awk -F': ' '/Receive buffer size/{print \$2}'; mlnx_qos -i enp1s0f0np0 2>/dev/null | awk '/Priority trust state/{print \$NF}'" 2>/dev/null || true)
  fw=$(sed -n '1p' <<<"$line"); buf=$(sed -n '2p' <<<"$line" | cut -d, -f2); trust=$(sed -n '3p' <<<"$line")
  if [[ "$fw" == "$PROD_NIC_FW_ALLOW" && "$buf" == "$PROD_LOSSLESS_BUFFER" && "$trust" == "dscp" ]]; then
    record PASS "nic:$h" "fw=$fw lossless_buf=$buf trust=$trust"
  else
    record FAIL "nic:$h" "fw=${fw:-?} lossless_buf=${buf:-?} trust=${trust:-?} (expect $PROD_NIC_FW_ALLOW/$PROD_LOSSLESS_BUFFER/dscp)"
  fi
done

# ── GPU clock policy: default/unlimited, EC controls thermals ───────────────
# gb10-clock-cap.service used to pin SM to 2400 MHz.  It is disabled on all
# four hosts (2026-10-22); the check catches a re-enabled unit or a lowered
# hardware max before it silently costs prefill throughput.
for h in "${HOSTS[@]}"; do
  line=$(run_on "$h" "systemctl is-enabled gb10-clock-cap.service 2>&1 || true; systemctl is-active gb10-clock-cap.service 2>&1 || true; nvidia-smi --query-gpu=clocks.max.sm --format=csv,noheader,nounits 2>/dev/null | head -1" 2>/dev/null || true)
  en=$(sed -n '1p' <<<"$line"); act=$(sed -n '2p' <<<"$line"); mx=$(sed -n '3p' <<<"$line" | tr -d ' ')
  if [[ "$en" != "enabled" && "$act" != "active" && "${mx:-0}" =~ ^[0-9]+$ && "$mx" -ge 3000 ]]; then
    record PASS "gpu_clock:$h" "cap_unit=$en/$act max_sm=${mx}MHz (EC auto)"
  else
    record FAIL "gpu_clock:$h" "cap_unit=${en:-?}/${act:-?} max_sm=${mx:-?} (expect disabled/inactive, >=3000)"
  fi
done

# ── fan policy: EC auto, no manual override module ──────────────────────────
# nvfancontrol is a DKMS module signed by a MOK key that is not enrolled under
# Secure Boot on 7.0.0, so it cannot load.  EC auto is the safe operating mode;
# a loaded override module means someone re-enabled a fixed RPM curve.
for h in "${HOSTS[@]}"; do
  fan_loaded=$(run_on "$h" "grep -c '^nvfancontrol ' /proc/modules 2>/dev/null || true" 2>/dev/null || true)
  if [[ "$fan_loaded" == "0" ]]; then
    record PASS "fan_policy:$h" "EC auto (nvfancontrol module unloaded)"
  else
    record FAIL "fan_policy:$h" "manual fan override loaded (expect EC auto)"
  fi
done

# ── warm performance gate (N consecutive 64k reads; first is cold, discard) ─
# The first read after a boot is consistently ~10% cold (page cache, autotune
# settling).  The historical "64k x4 + median of 3" gate dropped it for the
# same reason.  We run 5 and take the median of reads 2..5.
if [[ "$MODE" == "--post-boot" || "$MODE" == "--perf" ]]; then
  runs="${PROD_WARM_GATE_RUNS:-5}"
  vals=()
  for i in $(seq 1 "$runs"); do
    perf_json="$OUT_DIR/warm-$TS-$i.json"
    python3 "$PROD_BENCH" --mode pr --sizes "$PROD_WARM_GATE_SIZE" --pr-filler repeated \
      --base-url "http://127.0.0.1:${PROD_API_PORT}/v1" --json-out "$perf_json" >/dev/null 2>&1 || true
    v=$(python3 - "$perf_json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(int(round(d['pr'][0]['tok_s'])))
except Exception:
    print(0)
PY
)
    vals+=("$v")
  done
  tok_s=$(python3 - "${vals[@]}" <<'PY'
import statistics, sys
v = [int(x) for x in sys.argv[1:] if int(x) > 0]
# drop the cold first read; keep at least two values
warm = v[1:] if len(v) > 2 else v
print(int(round(statistics.median(warm))) if warm else 0)
PY
)
  if [[ "$tok_s" -ge "$PROD_WARM_GATE_TOK_S" ]]; then
    record PASS warm_gate "median=${tok_s} tok/s >= ${PROD_WARM_GATE_TOK_S} runs=[${vals[*]}]"
  else
    record FAIL warm_gate "median=${tok_s} tok/s < ${PROD_WARM_GATE_TOK_S} runs=[${vals[*]}] (anchor 6289)"
  fi
fi

# ── report ──────────────────────────────────────────────────────────────────
python3 - "$TSV" "$JSON" "$MODE" <<'PY'
import json, sys, time
tsv, out, mode = sys.argv[1:]
checks = []
for line in open(tsv):
    st, name, detail = line.rstrip('\n').split('\t', 2)
    checks.append({'status': st, 'name': name, 'detail': detail})
with open(out, 'w') as f:
    json.dump({'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'mode': mode, 'checks': checks,
               'fails': sum(c['status'] == 'FAIL' for c in checks)}, f, indent=2)
    f.write('\n')
PY
if [[ "$fails" == 0 ]]; then
  echo "[selfcheck] PASS ($MODE) report=$JSON"
  exit 0
fi
echo "[selfcheck] RED fails=$fails ($MODE) report=$JSON" >&2
exit 1
