#!/usr/bin/env bash
# version-lock.sh — keep production on kernel 6.17.0-1031 + NVIDIA 580.173.02.
#
# Protection layers:
#   1. apt-mark hold on every installed 6.17.0-1031 kernel package and the
#      matching NVIDIA userspace/module/firmware packages, plus the installed
#      7.0 meta/tool guard packages that keep the GRUB menu stable.
#   2. /etc/apt/preferences.d pin (priority 1001) for the same exact versions.
#   3. unattended-upgrades blacklist + explicit APT periodic disable.
#   4. DGX one-time apt-upgrade service masked; OTA/apt timers masked.
#
# Modes:
#   check   read-only; exit 1 on any drift (kernel, driver, GRUB, holds, pins,
#           auto-upgrade units).  Safe for a timer and for boot preflight.
#   apply   install the pin/blacklist files, set holds, mask auto-upgrade
#           units, then run check.  Must run as root; never touches running
#           containers or the data plane.
set -uo pipefail

KERNEL="6.17.0-1031-nvidia"
KERNEL_PKG_VER="6.17.0-1031.31"
DRIVER="580.173.02"
DRIVER_PKG_VER="580.173.02-1ubuntu1"
MISC_PKG_VER="580.178.04-0ubuntu0.24.04.1"
FW_PKG_VER="580.173.02-0ubuntu0.24.04.1"
GRUB_LINE='GRUB_DEFAULT="1>2"'
PIN_FILE=/etc/apt/preferences.d/99-prod-version-lock
UNATTENDED_FILE=/etc/apt/apt.conf.d/52-prod-version-lock

KERNEL_PKGS=(
  linux-image-6.17.0-1031-nvidia
  linux-headers-6.17.0-1031-nvidia
  linux-modules-6.17.0-1031-nvidia
  linux-modules-nvidia-580-6.17.0-1031-nvidia
  linux-nvidia-6.17-headers-6.17.0-1031
  linux-nvidia-6.17-tools-6.17.0-1031
  linux-tools-6.17.0-1031-nvidia
)
NVIDIA_PKGS=(
  nvidia-utils-580
  nvidia-compute-utils-580
  libnvidia-cfg1-580
  libnvidia-common-580
  libnvidia-compute-580
  libnvidia-decode-580
  libnvidia-encode-580
  libnvidia-extra-580
  libnvidia-fbc1-580
  libnvidia-gl-580
  libnvidia-gpucomp-580
  nvidia-persistenced
)
MISC_PKGS=(
  nvidia-kernel-common-580
  nvidia-kernel-source-580-open
)
FW_PKGS=(
  nvidia-firmware-580-580.173.02
)
ALL_PKGS=("${KERNEL_PKGS[@]}" "${NVIDIA_PKGS[@]}" "${MISC_PKGS[@]}" "${FW_PKGS[@]}")

# These packages stay installed as the fallback GRUB entry and NVIDIA tools.
# Their versions differ by host in one case (nvidia-modprobe), so only the
# hold is enforced here; dropping a hold could let the 7.0 meta packages move
# and shift the "1>2" menu index.  They are included in the unattended
# blacklist, but not in the exact-version pin set.
GUARD_PKGS=(
  linux-image-nvidia-hwe-24.04
  linux-nvidia-hwe-24.04
  linux-modules-nvidia-580-open-nvidia-hwe-24.04
  linux-modules-nvidia-580-open-7.0.0-1019-nvidia
  libxnvctrl0
  nvidia-modprobe
  nvidia-settings
)

log(){ printf '[version-lock] %s\n' "$*"; }
die(){ printf '[version-lock][FAIL] %s\n' "$*" >&2; exit 1; }

installed_ver(){
  local status version
  status=$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null) || return 1
  version=$(dpkg-query -W -f='${Version}' "$1" 2>/dev/null) || return 1
  # apt-mark hold changes the first field to "hold"; both mean installed.
  [[ "$status" == *"ok installed" ]] || return 1
  printf '%s\n' "$version"
}

is_installed(){ [[ -n "$(installed_ver "$1")" ]]; }

is_held(){
  apt-mark showhold 2>/dev/null | grep -qxF "$1"
}

candidate(){
  LC_ALL=C apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/{print $2; exit}'
}

write_pins(){
  cat > "$PIN_FILE" <<EOF
Explanation: production lock: kernel ${KERNEL} and NVIDIA ${DRIVER}
Package: ${KERNEL_PKGS[*]}
Pin: version ${KERNEL_PKG_VER}
Pin-Priority: 1001

Package: ${NVIDIA_PKGS[*]}
Pin: version ${DRIVER_PKG_VER}
Pin-Priority: 1001

Package: ${MISC_PKGS[*]}
Pin: version ${MISC_PKG_VER}
Pin-Priority: 1001

Package: ${FW_PKGS[*]}
Pin: version ${FW_PKG_VER}
Pin-Priority: 1001
EOF
  chmod 0644 "$PIN_FILE"
}

write_unattended(){
  local p
  {
    printf '// Production version lock: never auto-upgrade the kernel/driver stack.\n'
    printf 'APT::Periodic::Unattended-Upgrade "0";\n'
    printf 'Unattended-Upgrade::Package-Blacklist {\n'
    for p in "${ALL_PKGS[@]}" "${GUARD_PKGS[@]}"; do
      printf '  "%s";\n' "$p"
    done
    printf '};\n'
  } > "$UNATTENDED_FILE"
  chmod 0644 "$UNATTENDED_FILE"
}

check_lock(){
  local fail=0 out drv kmod p ver cand
  out=$(uname -r)
  if [[ "$out" != "$KERNEL" ]]; then
    log "kernel $out != $KERNEL"; fail=1
  fi

  drv=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits 2>/dev/null | head -1)
  kmod=$(modinfo -k "$(uname -r)" -F version nvidia 2>/dev/null)
  if [[ "$drv" != "$DRIVER" ]]; then
    log "NVIDIA userspace ${drv:-?} != $DRIVER"; fail=1
  fi
  if [[ "$kmod" != "$DRIVER" ]]; then
    log "nvidia.ko ${kmod:-?} != $DRIVER"; fail=1
  fi

  if ! grep -qxF "$GRUB_LINE" /etc/default/grub 2>/dev/null; then
    log "GRUB default is not $GRUB_LINE"; fail=1
  fi
  # grub.cfg is root-only; the timer runs as root and enforces this.  The
  # non-root fast check still verifies GRUB_DEFAULT above.
  if [[ -r /boot/grub/grub.cfg ]] && ! grep -q "menuentry .*${KERNEL}" /boot/grub/grub.cfg 2>/dev/null; then
    log "GRUB menuentry for $KERNEL missing"; fail=1
  fi
  [[ -f "$PIN_FILE" ]] || { log "missing $PIN_FILE"; fail=1; }
  [[ -f "$UNATTENDED_FILE" ]] || { log "missing $UNATTENDED_FILE"; fail=1; }

  for p in "${ALL_PKGS[@]}"; do
    ver=$(installed_ver "$p") || true
    [[ -n "$ver" ]] || { log "$p not installed"; fail=1; continue; }
    is_held "$p" || { log "$p not held"; fail=1; }
    cand=$(candidate "$p")
    if [[ "$cand" != "$ver" ]]; then
      log "$p candidate ${cand:-?} != installed $ver"; fail=1
    fi
  done

  for p in "${GUARD_PKGS[@]}"; do
    ver=$(installed_ver "$p") || true
    [[ -n "$ver" ]] || { log "$p not installed"; fail=1; continue; }
    is_held "$p" || { log "$p guard hold missing"; fail=1; }
  done

  if [[ "$(systemctl is-enabled nvidia-spark-run-apt-upgrade-once.service 2>/dev/null)" != "masked" ]]; then
    log "nvidia-spark-run-apt-upgrade-once.service is not masked"; fail=1
  fi
  for u in nvidia-spark-ota-check.timer apt-daily.timer apt-daily-upgrade.timer; do
    if [[ "$(systemctl is-enabled "$u" 2>/dev/null)" != "masked" ]]; then
      log "$u is not masked"; fail=1
    fi
  done

  if [[ "$fail" -ne 0 ]]; then
    log "FAIL kernel=$KERNEL driver=$DRIVER (drift detected)"
    return 1
  fi
  log "OK kernel=$KERNEL driver=$DRIVER holds=$(( ${#ALL_PKGS[@]} + ${#GUARD_PKGS[@]} )) lock=${#ALL_PKGS[@]} guard=${#GUARD_PKGS[@]} pins=$PIN_FILE grub=1>2"
  return 0
}

apply_lock(){
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || die "apply must run as root"
  write_pins
  write_unattended
  log "wrote $PIN_FILE and $UNATTENDED_FILE"

  local p
  for p in "${ALL_PKGS[@]}" "${GUARD_PKGS[@]}"; do
    if is_installed "$p"; then
      apt-mark hold "$p" >/dev/null 2>&1 || die "apt-mark hold failed: $p"
    else
      log "skip missing package $p"
    fi
  done

  # DGX's one-time full-upgrade service is the direct auto-upgrade path; its
  # done flag exists but mask the unit as well.  The OTA/apt timers are
  # already masked; re-assert the mask so a package update cannot re-enable
  # them silently.
  systemctl mask --now nvidia-spark-run-apt-upgrade-once.service \
    nvidia-spark-ota-check.timer apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
  systemctl reset-failed nvidia-spark-run-apt-upgrade-once.service >/dev/null 2>&1 || true

  check_lock || die "post-apply verification failed"
}

case "${1:-check}" in
  check) check_lock ;;
  apply) apply_lock ;;
  *) die "usage: $0 [check|apply]" ;;
esac
