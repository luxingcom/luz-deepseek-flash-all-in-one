#!/usr/bin/env bash
# Restore the 0.3.2 baseline image from the offline tar.
# This script only loads and tags the image. It never starts/stops containers.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAR="${HERE}/image-r032c-arm64.tar"
SHA="${TAR}.sha256"
# 20261030 脱敏：registry 主机改经环境变量注入，缺参拒跑。
TARGET="${TARGET:?缺环境变量 TARGET（形如 <registry-host>:5000/dsv41-sglang-optimized），拒跑}"
BASELINE_TAG="${TARGET}:0.3.2-baseline-20261022"
SOURCE_TAG="${TARGET}:0.3.2-r032c"
CONFIG_ID="sha256:ef64dec3d74b577bfcc8f54cc940b87d92701a9d9c3bb3c6c1214133c5e605b2"
INDEX_ID="sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4"

for f in "${TAR}" "${SHA}"; do
  [[ -s "${f}" ]] || { echo "missing: ${f}" >&2; exit 1; }
done

echo "== verify image tar =="
( cd "${HERE}" && sha256sum -c "$(basename "${SHA}")" )

echo "== docker load =="
docker load -i "${TAR}"

echo "== resolve loaded image =="
ID=""
for candidate in "${SOURCE_TAG}" "${CONFIG_ID}" "${INDEX_ID}"; do
  if docker image inspect "${candidate}" >/dev/null 2>&1; then
    ID="$(docker image inspect "${candidate}" --format '{{.Id}}')"
    echo "found ${candidate} -> ${ID}"
    break
  fi
done
if [[ -z "${ID}" ]]; then
  echo "loaded image not found by ${SOURCE_TAG}, ${CONFIG_ID}, or ${INDEX_ID}" >&2
  docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | grep dsv41-sglang-optimized || true
  exit 1
fi

docker tag "${ID}" "${BASELINE_TAG}"
docker tag "${ID}" "${SOURCE_TAG}"

echo "== verify =="
docker image inspect "${BASELINE_TAG}" --format 'ID={{.Id}} RepoDigests={{json .RepoDigests}}'
echo "restored ${BASELINE_TAG}"
echo
echo "Next: use the delivery repo tag v0.3.2-baseline-20261022 and the recorded"
echo "boot/env/adapter manifests to start the stack. This script does not touch"
echo "running containers."
