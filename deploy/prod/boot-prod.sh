#!/usr/bin/env bash
# boot-prod.sh — pinned, fail-closed production boot for LuZ 0.3.2.
#
# This is the only supported production entrypoint.  It sources
# prod-profile.env, refuses to start if any pinned artifact or host parameter
# has drifted, then calls the standard slot-locked chain:
#
#   tools/boot-with-slotlock.sh -> ~/migrate-assets/bin/r3-boot-arm.sh
#
# No production parameter is passed ad hoc.  To change one, edit the profile,
# review the diff, and re-run this script.
set -euo pipefail

PROFILE="${PROD_PROFILE:-$HOME/migrate-assets/prod/prod-profile.env}"
# shellcheck disable=SC1090
source "$PROFILE"

SELFCHECK="${PROD_SELFCHECK:-$HOME/migrate-assets/prod/selfcheck-prod.sh}"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="${PROD_LOG_DIR:-$HOME/r3-prod-logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/boot-prod-$TS.log"
MARKER="$HOME/migrate-assets/prod/last-boot.json"
HOSTS=(${PROD_HOSTS})
LOCAL="$(hostname -s)"

log(){ printf '[preflight] %s\n' "$*"; }
die(){ printf '[preflight][RED] %s\n' "$*" >&2; exit 1; }

run_on(){
  local h="$1" cmd="$2"
  if [[ "$h" == "$LOCAL" ]]; then
    bash -c "$cmd"
  else
    ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" "$cmd"
  fi
}

# ── artifacts ────────────────────────────────────────────────────────────────
log "profile=$PROFILE"
[[ -f "$PROD_ARM_ENV_FILE" ]] || die "env file missing: $PROD_ARM_ENV_FILE"
got_md5=$(md5sum "$PROD_ARM_ENV_FILE" | awk '{print $1}')
[[ "$got_md5" == "$PROD_ARM_ENV_MD5" ]] || die "env md5 $got_md5 != $PROD_ARM_ENV_MD5"
got_keys=$(grep -cE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "$PROD_ARM_ENV_FILE" || true)
[[ "$got_keys" == "$PROD_ARM_ENV_KEYS" ]] || die "env key count $got_keys != $PROD_ARM_ENV_KEYS"

[[ -d "$PROD_OVERLAY_DIR" ]] || die "overlay dir missing: $PROD_OVERLAY_DIR"
[[ -f "$PROD_OVERLAY_MANIFEST" ]] || die "overlay manifest missing: $PROD_OVERLAY_MANIFEST"
( cd "$PROD_OVERLAY_DIR" && md5sum -c --quiet "$PROD_OVERLAY_MANIFEST" ) \
  || die "overlay manifest mismatch (serving_chat/backend changed?)"
ov_n=$(awk -F'\t' '!/^#/ && NF>=2 && $1!="" {n++} END{print n+0}' "$PROD_OVERLAY_DIR/overlay-map.tsv")
[[ "$ov_n" == "$PROD_OVERLAY_COUNT" ]] || die "overlay map count $ov_n != $PROD_OVERLAY_COUNT"

[[ -f "$HOME/migrate-assets/dsv41/adapter/dsv41_recipe.py" ]] || die "recipe adapter missing"
[[ -f "$PROD_RECIPE_MANIFEST" ]] || die "recipe manifest missing: $PROD_RECIPE_MANIFEST"
( cd "$HOME/migrate-assets/dsv41/adapter" && md5sum -c --quiet "$PROD_RECIPE_MANIFEST" ) \
  || die "recipe/adapter manifest mismatch"

# Whole-tree fingerprint: catches files outside the recipe manifest (the
# maintenance window left the recipe files on head only until 2026-10-22).
ADAPTER_DIR="$HOME/migrate-assets/dsv41/adapter"
fp_cmd="cd '$ADAPTER_DIR' && find . -type f ! -path '*__pycache__*' | LC_ALL=C sort | xargs -r md5sum 2>/dev/null | LC_ALL=C sort | md5sum | cut -c1-8"
for h in "${HOSTS[@]}"; do
  fp=$(run_on "$h" "$fp_cmd" 2>/dev/null || true)
  [[ "$fp" == "$PROD_ADAPTER_FINGERPRINT" ]] \
    || die "$h adapter fingerprint ${fp:-?} != $PROD_ADAPTER_FINGERPRINT (run adapter-sync --apply)"
done
log "adapter fingerprint $PROD_ADAPTER_FINGERPRINT OK on all hosts ($PROD_ADAPTER_FILES files)"

[[ -f "$PROD_BOOT_SCRIPT" ]] || die "boot script missing: $PROD_BOOT_SCRIPT"
boot_md5=$(md5sum "$PROD_BOOT_SCRIPT" | awk '{print $1}')
[[ "$boot_md5" == "$PROD_BOOT_SCRIPT_MD5" ]] || die "boot script md5 $boot_md5 != $PROD_BOOT_SCRIPT_MD5"
[[ -f "$PROD_WRAPPER" ]] || die "slotlock wrapper missing: $PROD_WRAPPER"
[[ -x "$SELFCHECK" ]] || die "selfcheck missing or not executable: $SELFCHECK"

if docker image inspect "$PROD_IMAGE" >/dev/null 2>&1; then
  refs=$(docker image inspect "$PROD_IMAGE" --format '{{json .RepoDigests}}' 2>/dev/null || true)
  if [[ "$refs" != *"${PROD_IMAGE_DIGEST#sha256:}"* ]]; then
    die "image digest mismatch: expected ${PROD_IMAGE_DIGEST}; got ${refs:-<none>}"
  fi
  log "image digest OK"
else
  die "image not present: $PROD_IMAGE"
fi

# ── host state ───────────────────────────────────────────────────────────────
for h in "${HOSTS[@]}"; do
  k=$(run_on "$h" 'uname -r') || die "$h unreachable"
  case " $PROD_KERNEL_ALLOW " in
    *" $k "*) ;;
    *) die "$h kernel $k not in allowlist [$PROD_KERNEL_ALLOW]" ;;
  esac
done
log "kernel allowlist OK"

for h in "${HOSTS[@]}"; do
  run_on "$h" "bash /usr/local/sbin/roce-ring-apply.sh check" >/dev/null \
    || die "$h NIC profile drift (ring/firmware/lossless buffer/PFC); run: sudo /usr/local/sbin/roce-ring-apply.sh apply (engine stopped)"
done
log "RX ring $PROD_RX_RING OK on all hosts"

for h in "${HOSTS[@]}"; do
  names=$(run_on "$h" "docker ps --format '{{.Names}}'" 2>/dev/null) \
    || die "$h docker unreachable"
  if printf '%s\n' "$names" | grep -qE '^r3(prod|boot)-'; then
    die "$h has a running r3 stack: $(printf '%s\n' "$names" | grep -E '^r3(prod|boot)-' | tr '\n' ' ')"
  fi
done
log "all hosts clean (no r3prod/r3boot containers)"

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${PROD_API_PORT}/health" || true)
[[ "$code" == "000" ]] || die "port ${PROD_API_PORT} already answers /health ($code)"

# ── boot ─────────────────────────────────────────────────────────────────────
export ARM_TAG="${PROD_CTN_PREFIX}-pinned-$TS"
export CTN_PREFIX="$PROD_CTN_PREFIX"
export API_PORT="$PROD_API_PORT"
export SPEC="$PROD_SPEC"
export ARM_ENV_FILE="$PROD_ARM_ENV_FILE"
export SPEC_EXTRA_ARGS="$PROD_SPEC_EXTRA_ARGS"
export SGLANG_OVERLAY_DIR="$PROD_OVERLAY_DIR"

log "booting ARM_TAG=$ARM_TAG CTN_PREFIX=$CTN_PREFIX API_PORT=$API_PORT SPEC=$SPEC"
log "log=$LOG"
set +e
bash "$PROD_WRAPPER" bash "$PROD_BOOT_SCRIPT" 2>&1 | tee "$LOG"
boot_rc=${PIPESTATUS[0]}
set -e
if [[ "$boot_rc" != 0 ]]; then
  printf '[preflight][RED] boot rc=%s; see %s\n' "$boot_rc" "$LOG" >&2
  exit "$boot_rc"
fi

# ── post-boot hard checks ────────────────────────────────────────────────────
set +e
bash "$SELFCHECK" --post-boot 2>&1 | tee -a "$LOG"
sc_rc=${PIPESTATUS[0]}
set -e

python3 - "$MARKER" "$ARM_TAG" "$TS" "$boot_rc" "$sc_rc" "$PROD_ARM_ENV_MD5" "$boot_md5" <<'PY'
import json, sys, os
path, tag, ts, boot_rc, sc_rc, env_md5, boot_md5 = sys.argv[1:]
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump({
        'arm_tag': tag, 'timestamp': ts,
        'boot_rc': int(boot_rc), 'selfcheck_rc': int(sc_rc),
        'env_md5': env_md5, 'boot_script_md5': boot_md5,
        'profile': os.path.expanduser('~/migrate-assets/prod/prod-profile.env'),
    }, f, indent=2)
    f.write('\n')
PY

if [[ "$sc_rc" != 0 ]]; then
  printf '[preflight][RED] post-boot selfcheck rc=%s; stack is UP but parameters need review\n' "$sc_rc" >&2
  exit 4
fi
log "production boot + post-boot selfcheck PASS"
