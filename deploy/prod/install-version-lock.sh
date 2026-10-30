#!/usr/bin/env bash
# install-version-lock.sh — install and apply the kernel/driver version lock.
# Run as root on each host.  Idempotent; does not restart the production stack.
set -euo pipefail

SRC_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"

install -m 0755 "$SRC_DIR/version-lock.sh" /usr/local/sbin/version-lock.sh
install -m 0644 "$SRC_DIR/prod-version-lock.service" /etc/systemd/system/prod-version-lock.service
install -m 0644 "$SRC_DIR/prod-version-lock.timer" /etc/systemd/system/prod-version-lock.timer

systemctl daemon-reload
/usr/local/sbin/version-lock.sh apply
systemctl enable --now prod-version-lock.timer >/dev/null
systemctl reset-failed prod-version-lock.service >/dev/null 2>&1 || true
systemctl start prod-version-lock.service

echo "[version-lock-install] installed; timer=$(systemctl is-active prod-version-lock.timer)"
/usr/local/sbin/version-lock.sh check
