#!/usr/bin/env bash
# roce-ring-apply.sh — pin the RoCE host profile to the production baseline.
#
# Why: production runs rx=4096 on all four RoCE ports per host (2026-10-09
# impact run, retained 2026-10-22); the 4096 page pool leaves ~3 GB more UMA
# for the engine than 8192.  A kernel reboot resets the driver default to 1024,
# so the boot unit re-asserts the profile before docker starts.
#
# Firmware 28.50.1002 changed one lossless default: the shared receive buffer
# (mlnx_qos buffer 1, used by PFC prio3/prio5) dropped from 523296 B to
# 458496 B.  Production pins the pre-update 523296 B margin back (user decision
# 2026-10-22) so the PFC class keeps its burst absorption through the switch.
# The same pass re-asserts trust=dscp and PFC 3+5 because a buffer write may
# reset them.
#
# Modes:
#   check             read-only; exit 1 if any pinned value differs
#   apply             set the profile (only safe while the engine is stopped)
#   heal-if-down      apply only if no r3prod/r3boot container is running;
#                     while the stack is up, fall back to read-only check so a
#                     healthy running stack does not mark the timer unit failed
#
# The script never changes TX ring, MTU, link state, DSCP map, or rate limits.
set -uo pipefail

RX_TARGET="${RX_TARGET:-4096}"
FW_TARGET="${FW_TARGET:-28.50.1002}"
LOSSLESS_BUFFER="${LOSSLESS_BUFFER:-523296}"
PFC_TARGET="${PFC_TARGET:-0,0,0,1,0,1,0,0}"
DEVS="${DEVS:-enp1s0f0np0 enp1s0f1np1 enP2p1s0f0np0 enP2p1s0f1np1}"
MODE="${1:-check}"

cur_rx() {
  ethtool -g "$1" 2>/dev/null | awk '
    /Current hardware settings:/ {in_cur=1; next}
    in_cur && /^RX:/ {print $2; exit}
  '
}

cur_fw() {
  ethtool -i "$1" 2>/dev/null | awk '/firmware-version/ {print $2; exit}'
}

cur_buf_list() {
  mlnx_qos -i "$1" 2>/dev/null | awk -F': ' '/Receive buffer size/ {print $2; exit}' | cut -d, -f1-8
}

cur_buf1() {
  cur_buf_list "$1" | cut -d, -f2
}

cur_trust() {
  mlnx_qos -i "$1" 2>/dev/null | awk '/Priority trust state/ {print $NF; exit}'
}

cur_pfc() {
  mlnx_qos -i "$1" 2>/dev/null | awk '$1=="enabled" {print $5","$7; exit}'
}

stack_up() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^r3(prod|boot)-'
}

fail=0
case "$MODE" in
  check|apply|heal-if-down) ;;
  *) echo "usage: $0 [check|apply|heal-if-down]" >&2; exit 2 ;;
esac

if [[ "$MODE" == "heal-if-down" ]]; then
  if stack_up; then
    # Never write while the engine is running.  A healthy profile must still
    # exit 0; real drift is reported by the same read-only checks below.
    echo "[nic] stack is up; read-only check (no write)" >&2
    MODE=check
  else
    MODE=apply
  fi
fi

for dev in $DEVS; do
  [[ -e "/sys/class/net/$dev" ]] || { echo "[nic] $dev missing" >&2; fail=1; continue; }

  fw_before=$(cur_fw "$dev")
  if [[ -z "$fw_before" ]]; then
    echo "[nic] $dev: cannot read firmware" >&2
    fail=1
    continue
  fi
  if [[ "$fw_before" != "$FW_TARGET" ]]; then
    echo "[nic] $dev: firmware $fw_before != $FW_TARGET (review before boot; no auto-downgrade)" >&2
    fail=1
    continue
  fi

  rx_before=$(cur_rx "$dev")
  buf_before=$(cur_buf1 "$dev")
  trust_before=$(cur_trust "$dev")
  pfc_before=$(cur_pfc "$dev")
  if [[ -z "$rx_before" || -z "$buf_before" ]]; then
    echo "[nic] $dev: cannot read ring/buffer (fw=$fw_before)" >&2
    fail=1
    continue
  fi

  if [[ "$MODE" == "apply" ]]; then
    [[ "$rx_before" == "$RX_TARGET" ]] || ethtool -G "$dev" rx "$RX_TARGET" >/dev/null 2>&1
    if [[ "$buf_before" != "$LOSSLESS_BUFFER" ]]; then
      list=$(cur_buf_list "$dev")
      new_list=$(awk -F, -v b="$LOSSLESS_BUFFER" 'BEGIN {OFS=","} { $2=b; print $1,$2,$3,$4,$5,$6,$7,$8 }' <<<"$list")
      mlnx_qos -i "$dev" --buffer_size "$new_list" >/dev/null 2>&1
    fi
    # A buffer write may reset the lossless state; re-assert it every apply.
    mlnx_qos -i "$dev" --trust dscp >/dev/null 2>&1
    mlnx_qos -i "$dev" --pfc "$PFC_TARGET" >/dev/null 2>&1
  fi

  rx_after=$(cur_rx "$dev")
  buf_after=$(cur_buf1 "$dev")
  trust_after=$(cur_trust "$dev")
  pfc_after=$(cur_pfc "$dev")
  printf '[nic] %s fw=%s rx=%s->%s buf1=%s->%s trust=%s pfc3/5=%s\n' \
    "$dev" "$fw_before" "$rx_before" "$rx_after" "$buf_before" "$buf_after" "$trust_after" "$pfc_after"
  [[ "$rx_after" == "$RX_TARGET" ]] || fail=1
  [[ "$buf_after" == "$LOSSLESS_BUFFER" ]] || fail=1
  [[ "$trust_after" == "dscp" ]] || fail=1
  [[ "$pfc_after" == "1,1" ]] || fail=1
done

if [[ "$fail" != 0 ]]; then
  echo "[nic] FAIL rx=$RX_TARGET fw=$FW_TARGET buf1=$LOSSLESS_BUFFER trust=dscp pfc3/5=1,1" >&2
  exit 1
fi
echo "[nic] OK rx=$RX_TARGET fw=$FW_TARGET buf1=$LOSSLESS_BUFFER trust=dscp pfc3/5=1,1"
