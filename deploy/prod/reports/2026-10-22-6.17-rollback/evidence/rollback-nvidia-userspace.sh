#!/usr/bin/env bash
# Roll an NVIDIA 580.178 userspace host back to the 580.173.02 userspace that
# matches the Canonical-signed 6.17.0-1031 kernel modules.  Headless: the X
# server driver and the nvidia-driver-580-open metapackage are removed.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-mark unhold nvidia-driver-580-open nvidia-utils-580 nvidia-kernel-common-580 xserver-xorg-video-nvidia-580 2>/dev/null || true

apt-get install -y --allow-downgrades --allow-change-held-packages --no-install-recommends \
  -o Dpkg::Options::=--force-overwrite \
  nvidia-utils-580=580.173.02-1ubuntu1 \
  nvidia-compute-utils-580=580.173.02-1ubuntu1 \
  libnvidia-compute-580=580.173.02-1ubuntu1 \
  libnvidia-cfg1-580=580.173.02-1ubuntu1 \
  libnvidia-common-580=580.173.02-1ubuntu1 \
  libnvidia-extra-580=580.173.02-1ubuntu1 \
  libnvidia-gpucomp-580=580.173.02-1ubuntu1 \
  libnvidia-decode-580=580.173.02-1ubuntu1 \
  libnvidia-encode-580=580.173.02-1ubuntu1 \
  libnvidia-fbc1-580=580.173.02-1ubuntu1 \
  libnvidia-gl-580=580.173.02-1ubuntu1 \
  nvidia-persistenced=580.173.02-1ubuntu1 \
  xserver-xorg-video-nvidia-580-

dpkg --configure -a
dpkg --audit

apt-mark hold \
  nvidia-utils-580 nvidia-compute-utils-580 libnvidia-compute-580 \
  libnvidia-cfg1-580 libnvidia-common-580 libnvidia-extra-580 \
  libnvidia-gpucomp-580 libnvidia-decode-580 libnvidia-encode-580 \
  libnvidia-fbc1-580 libnvidia-gl-580 nvidia-persistenced >/dev/null

echo "--- versions ---"
dpkg-query -W -f='${Package} ${Version}\n' \
  nvidia-utils-580 nvidia-compute-utils-580 libnvidia-compute-580 \
  libnvidia-cfg1-580 libnvidia-common-580 nvidia-persistenced 2>&1
echo "--- 6.17 module ---"
modinfo -k 6.17.0-1031-nvidia -F version nvidia
modinfo -k 6.17.0-1031-nvidia -F signer nvidia
