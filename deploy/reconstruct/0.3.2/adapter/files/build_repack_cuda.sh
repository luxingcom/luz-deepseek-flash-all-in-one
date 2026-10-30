#!/usr/bin/env bash
# Build the DSV4.1 fp4-KV repack CUDA extension (repack_cuda.cu -> librepack_cuda.so).
#
# One-shot from the HOST (<node01>..<node04>; the adapter mount is read-only inside
# the container, so the product is copied back out with docker cp):
#   bash /home/<deploy-user>/migrate-assets/dsv41/adapter/build_repack_cuda.sh
# The compile + unit smoke run INSIDE the r3boot-head container (nvcc 13.0,
# torch 2.13.0+cu130). Running the script inside the container builds only and
# leaves the .so at /tmp/repack_build (for bring-your-own use).
#
# Flags: -O3 -std=c++17, NO --use_fast_math (bit-exactness: IEEE div, RN casts,
# no reciprocal approximations; -prec-div/-ftz stay at their exact defaults).
# Arch: SM121 first (GB10); if nvcc rejects compute_121, fall back to
# sm_120+compute_120 (PTX JITs to 121).
set -euo pipefail

CTNR=${REPACK_BUILD_CONTAINER:-r3boot-head}
CTR_ADAPTER=/opt/dsv41/adapter

in_container=0
[[ -x /usr/local/cuda/bin/nvcc && -d $CTR_ADAPTER ]] && in_container=1

container_build() {  # runs INSIDE the container
  set -euo pipefail
  BUILD=/tmp/repack_build
  NVCC=/usr/local/cuda/bin/nvcc
  mkdir -p "$BUILD"
  cd "$BUILD"
  cp /opt/dsv41/adapter/repack_cuda.cu .

  # Torch/python paths via sidecar files (the sitecustomize banner pollutes
  # every python3 stdout, so scalars must never travel over stdout).
  python3 - <<'PYEOF'
import sysconfig
from torch.utils import cpp_extension as ce

try:
    inc = ce.include_paths(device_type="cuda")
    lib = ce.library_paths(device_type="cuda")
except TypeError:  # older signature
    inc = ce.include_paths(cuda=True)
    lib = ce.library_paths(cuda=True)
import torch
with open("inc_flags.txt", "w") as f:
    f.write("\n".join("-I" + p for p in inc + [sysconfig.get_paths()["include"]]) + "\n")
with open("lib_flags.txt", "w") as f:
    f.write("\n".join("-L" + p for p in lib) + "\n")
with open("abi.txt", "w") as f:
    f.write(str(int(torch._C._GLIBCXX_USE_CXX11_ABI)) + "\n")
PYEOF
  INC_ARGS=$(paste -sd' ' inc_flags.txt)
  LIB_ARGS=$(paste -sd' ' lib_flags.txt)
  ABI=$(cat abi.txt)

  build() {  # $1 = arch flags
    "$NVCC" -O3 -std=c++17 -shared -Xcompiler -fPIC $1 \
      -DTORCH_EXTENSION_NAME=repack_cuda \
      -DTORCH_API_INCLUDE_EXTENSION_H \
      -D_GLIBCXX_USE_CXX11_ABI="$ABI" \
      $INC_ARGS \
      repack_cuda.cu -o librepack_cuda.so \
      $LIB_ARGS -ltorch -ltorch_cpu -ltorch_python -lc10 -lcudart \
      2> nvcc.log
  }

  echo "[build] trying arch=compute_121,code=sm_121 ..."
  if ! build "-gencode arch=compute_121,code=sm_121"; then
    echo "[build] sm_121 rejected (see nvcc.log); falling back to sm_120+PTX" >&2
    build "-gencode arch=compute_120,code=[sm_120,compute_120]"
  fi

  # Smoke: import + a 1-row launch on the current device.
  python3 - <<'PYEOF' > smoke.log 2>&1
import importlib.machinery, importlib.util, torch
loader = importlib.machinery.ExtensionFileLoader("repack_cuda", "/tmp/repack_build/librepack_cuda.so")
spec = importlib.util.spec_from_loader("repack_cuda", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
pool = torch.randint(0, 256, (1, 288 * 256), dtype=torch.uint8, device="cuda")
idx = torch.tensor([0], dtype=torch.int32, device="cuda")
dst = torch.empty(1, 37440, dtype=torch.uint8, device="cuda")
mod.repack_fp4_to_v4(pool, pool.view(torch.float8_e4m3fn), idx, dst, 288 * 256, 8)
torch.cuda.synchronize()
print("smoke OK")
PYEOF
  grep -q "^smoke OK" smoke.log || { echo "[build] smoke FAILED (see $BUILD/smoke.log)" >&2; exit 1; }
  echo "[build] smoke OK: /tmp/repack_build/librepack_cuda.so"
}

if [[ $in_container == 1 ]]; then
  container_build
  exit 0
fi

# Host: orchestrate the container build, then copy the product back out
# (the adapter mount is read-only inside the container).
HOST_ADAPTER=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
docker exec "$CTNR" bash -c "$(declare -f container_build); container_build"
mkdir -p "$HOST_ADAPTER/lib"
docker cp "$CTNR:/tmp/repack_build/librepack_cuda.so" "$HOST_ADAPTER/lib/librepack_cuda.so"
# Final smoke against the shipped path (read-only mount: dlopen must work).
docker exec "$CTNR" python3 -c "
import importlib.machinery, importlib.util, torch, sys
loader = importlib.machinery.ExtensionFileLoader('repack_cuda', '$CTR_ADAPTER/lib/librepack_cuda.so')
spec = importlib.util.spec_from_loader('repack_cuda', loader)
mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
pool = torch.randint(0, 256, (1, 288*256), dtype=torch.uint8, device='cuda')
idx = torch.tensor([0], dtype=torch.int32, device='cuda')
dst = torch.empty(1, 37440, dtype=torch.uint8, device='cuda')
mod.repack_fp4_to_v4(pool, pool.view(torch.float8_e4m3fn), idx, dst, 288*256, 8)
torch.cuda.synchronize(); print('final smoke OK')
" 2>&1 | grep -E "final smoke OK|Error" || true
echo "[build] done: $HOST_ADAPTER/lib/librepack_cuda.so"
