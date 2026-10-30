#!/usr/bin/env bash
# install-prod-guard.sh — install the pinned production boot profile and the
# periodic read-only self-check on the head host.  Run as root.
#
# It does not touch netplan, the 02 watchdogs, or any pre-existing service.
set -euo pipefail

SRC_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
OWNER="${SUDO_USER:-liux***ya}"
HOME_DIR="$(getent passwd "$OWNER" | cut -d: -f6)"
DEST="$HOME_DIR/migrate-assets/prod"

install -d -o "$OWNER" -g "$OWNER" "$DEST" "$HOME_DIR/r3-prod-logs"
install -m 0755 -o "$OWNER" -g "$OWNER" "$SRC_DIR/boot-prod.sh" "$DEST/boot-prod.sh"
install -m 0755 -o "$OWNER" -g "$OWNER" "$SRC_DIR/selfcheck-prod.sh" "$DEST/selfcheck-prod.sh"
install -m 0644 -o "$OWNER" -g "$OWNER" "$SRC_DIR/prod-profile.env" "$DEST/prod-profile.env"
install -m 0644 -o "$OWNER" -g "$OWNER" "$SRC_DIR/overlay-md5.txt" "$DEST/overlay-md5.txt"
install -m 0644 -o "$OWNER" -g "$OWNER" "$SRC_DIR/recipe-md5.txt" "$DEST/recipe-md5.txt"
install -m 0644 -o "$OWNER" -g "$OWNER" "$SRC_DIR/recipe_probe.py" "$DEST/recipe_probe.py"

install -m 0644 "$SRC_DIR/prod-selfcheck.service" /etc/systemd/system/prod-selfcheck.service
install -m 0644 "$SRC_DIR/prod-selfcheck.timer" /etc/systemd/system/prod-selfcheck.timer
systemctl daemon-reload
systemctl enable --now prod-selfcheck.timer >/dev/null

echo "[prod-guard] installed under $DEST"
systemctl is-active prod-selfcheck.timer
