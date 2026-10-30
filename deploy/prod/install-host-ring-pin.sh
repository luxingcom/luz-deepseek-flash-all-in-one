#!/usr/bin/env bash
# install-host-ring-pin.sh — install the RoCE ring boot pin on one host.
# Run as root.  Idempotent; touches only the three files below plus systemd.
set -euo pipefail

SRC_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
install -m 0755 "$SRC_DIR/roce-ring-apply.sh" /usr/local/sbin/roce-ring-apply.sh
install -m 0644 "$SRC_DIR/roce-ring-boot.service" /etc/systemd/system/roce-ring-boot.service
install -m 0644 "$SRC_DIR/roce-ring-check.service" /etc/systemd/system/roce-ring-check.service
install -m 0644 "$SRC_DIR/roce-ring-check.timer" /etc/systemd/system/roce-ring-check.timer

systemctl daemon-reload
systemctl enable roce-ring-boot.service >/dev/null
# Never reprogram a live data plane from the installer: a buffer/PFC write
# can reset RoCE QPs.  With an engine running, leave the boot unit enabled
# for the next boot and verify current state read-only.
if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq '^r3(prod|boot)-'; then
  echo "[nic-install] r3 stack is running; boot unit enabled, apply deferred to next boot" >&2
  /usr/local/sbin/roce-ring-apply.sh check || true
else
  systemctl start roce-ring-boot.service
  /usr/local/sbin/roce-ring-apply.sh check
fi
systemctl enable --now roce-ring-check.timer >/dev/null
systemctl is-active roce-ring-boot.service
systemctl is-active roce-ring-check.timer
