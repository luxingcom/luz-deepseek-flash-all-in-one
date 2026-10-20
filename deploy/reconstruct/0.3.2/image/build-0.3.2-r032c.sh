#!/usr/bin/env bash
# build-0.3.2-r032c.sh — public reconstruction of LuZ 0.3.2-r032c.
#
# Derived from the in-production bake script. Behaviour is the same single-COPY
# layer recipe; staging reads the 16 full files shipped in ./files instead of a
# private replay tree, and the tree identity is asserted by tree hash.
#
# Usage:
#   bash build-0.3.2-r032c.sh              # build + readback + py_compile + import + collection
#   NOCACHE=1 bash build-0.3.2-r032c.sh    # cold rebuild
#   bash build-0.3.2-r032c.sh --check      # assertions only, no build
#   SKIP_BASE_ID=1 BASE=<other-base> TAG=<local-tag> bash build-0.3.2-r032c.sh
set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
REPLAY_TREE="dab49d96d33839480e30a1d24ac9e6cdb0a9c29d"
BASE="${BASE:-192.168.0.202:5000/lmsysorg/sglang:main-79cafec0}"
TAG="${TAG:-dsv41-sglang-optimized:0.3.2-r032c}"
NOCACHE="${NOCACHE:-0}"
SKIP_BASE_ID="${SKIP_BASE_ID:-0}"
BUILT_AT="${BUILT_AT:-2026-10-18T05:20:00Z}"
MTIME="2026-10-18T05:20:00Z"
CHECK_ONLY=0
[[ "${1:-}" = "--check" ]] && CHECK_ONLY=1

PORT_FILES=(
  python/sglang/kernels/ops/attention/dsv4/candidate_blocks.py
  python/sglang/kernels/ops/attention/dsv4/fp4_indexer.py
  python/sglang/srt/layers/attention/deepseek_v4_backend.py
  python/sglang/srt/layers/attention/dsv4/v41_indexer/dense_blocks.py
  python/sglang/srt/layers/attention/dsv4/v41_indexer/full_topk.py
  python/sglang/srt/layers/attention/dsv4/v41_indexer/__init__.py
  python/sglang/srt/layers/attention/dsv4/v41_indexer/scoring.py
  python/sglang/srt/layers/attention/dsv4/v41_indexer/sparse_table.py
  python/sglang/srt/layers/attention/dsv4/v41_indexer/types.py
  python/sglang/srt/layers/engram.py
  python/sglang/srt/model_executor/model_runner_components/ngram_embedding_manager.py
  python/sglang/srt/utils/common.py
  test/registered/kernels/ops/attention/test_dense_prefill_indexer.py
  test/registered/kernels/ops/attention/test_dsv41_prefill_sparse_indexer.py
  test/registered/kernels/ops/attention/test_fp4_indexer.py
  test/registered/unit/layers/test_dsv4_nonpaged_indexer.py
)

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
ok()  { printf '  OK   %s\n' "$*"; }
die() { printf '  FATAL %s\n' "$*" >&2; exit 1; }

# 1. static assertions -------------------------------------------------------
log "1/7 static assertions"
[[ -d "$KIT/files" ]] || die "missing $KIT/files"
[[ ${#PORT_FILES[@]} -eq 16 ]] || die "PORT_FILES count != 16"
[[ -f "$KIT/port16-tree-md5-r032c.txt" ]] || die "missing md5 ledger"
( cd "$KIT/files" && md5sum -c "$KIT/port16-tree-md5-r032c.txt" >/dev/null ) \
  || die "16 shipped files do not match port16-tree-md5-r032c.txt"

if [[ -n "${SGLANG_STOCK:-}" ]]; then
  log "checking stock source at $SGLANG_STOCK"
  ( cd "$SGLANG_STOCK" && md5sum -c "$KIT/stock16-md5.txt" >/dev/null ) \
    || die "stock source does not match 79cafec0 fingerprints"
  ok "stock16 md5 match (79cafec0)"
else
  ok "stock source check skipped (set SGLANG_STOCK to enable)"
fi

docker image inspect "$BASE" >/dev/null 2>&1 || die "base image absent: $BASE (pull it first; no auto-pull)"
base_layers=$(docker image inspect -f '{{len .RootFS.Layers}}' "$BASE")
base_id=$(docker image inspect -f '{{.Id}}' "$BASE" | cut -c8-19)
ok "base $BASE image=$base_id layers=$base_layers"
if [[ "$SKIP_BASE_ID" != 1 ]]; then
  [[ "$base_id" = 80e1ea8979c5* ]] || die "base id != 80e1ea89 (set SKIP_BASE_ID=1 to override)"
fi
[[ "$base_layers" -eq 70 ]] || die "base layers != 70 (got $base_layers)"

# 2. staging ----------------------------------------------------------------
log "2/7 staging 16 files"
WORK="${WORK:-$(mktemp -d "${TMPDIR:-/tmp}/r032c-bake-XXXXXX")}"
CTX="$WORK/ctx"
mkdir -p "$CTX/rootfs"
trap 'rm -rf "$WORK"' EXIT
for f in "${PORT_FILES[@]}"; do
  mkdir -p "$CTX/rootfs/$(dirname "$f")"
  cp -p "$KIT/files/$f" "$CTX/rootfs/$f"
done
find "$CTX/rootfs" -exec touch -h -d "$MTIME" {} +
find "$CTX/rootfs" -exec touch -h -d "$MTIME" {} +
[[ "$(find "$CTX/rootfs" -type f | wc -l)" -eq 16 ]] || die "staging count != 16"
( cd "$CTX/rootfs" && md5sum "${PORT_FILES[@]}" ) | sort > "$CTX/staging-md5.txt"
diff <(sort "$KIT/port16-tree-md5-r032c.txt") "$CTX/staging-md5.txt" >/dev/null \
  || die "staging md5 mismatch"
ok "staging md5 16/16"

# 3. Dockerfile -------------------------------------------------------------
log "3/7 Dockerfile"
cat > "$CTX/Dockerfile" <<EOF
FROM $BASE
LABEL DSV41_IMAGE_VERSION="0.3.2-r032c" \\
      DSV41_PORT_BASE="520d6d0+fc2795b+391e665(candidate_block_mask)" \\
      DSV41_PORT_SCOPE="minimal-deadlock-fix +bit-preserve-selection-order 16 files" \\
      DSV41_REPLAY_TREE="$REPLAY_TREE" \\
      DSV41_BASE_DIGEST="$base_id" \\
      BUILT_AT="$BUILT_AT"
COPY rootfs/ /sgl-workspace/sglang/
EOF
ok "FROM + single COPY layer"

if [[ "$CHECK_ONLY" = 1 ]]; then log "--check done"; exit 0; fi

# 4. build ------------------------------------------------------------------
log "4/7 build $TAG"
if [[ "$NOCACHE" = 1 ]]; then
  docker build --no-cache -t "$TAG" "$CTX"
else
  docker build -t "$TAG" "$CTX"
fi
new_layers=$(docker image inspect -f '{{len .RootFS.Layers}}' "$TAG")
new_cid=$(docker image inspect -f '{{join .RootFS.Layers " "}}' "$TAG" | sha256sum | cut -c1-16)
[[ "$new_layers" -eq $((base_layers + 1)) ]] || die "layer count $new_layers != $((base_layers+1))"
ok "built: layers=$new_layers cid=$new_cid"

# 5. in-image readback ------------------------------------------------------
log "5/7 readback 16 files"
docker run --rm --network none "$TAG" bash -c \
  "cd /sgl-workspace/sglang && md5sum ${PORT_FILES[*]}" 2>/dev/null \
  | grep -E '^[0-9a-f]{32}  ' | sort > "$CTX/image-md5.txt"
diff <(sort "$KIT/port16-tree-md5-r032c.txt") "$CTX/image-md5.txt" >/dev/null \
  || { diff <(sort "$KIT/port16-tree-md5-r032c.txt") "$CTX/image-md5.txt" | head; die "readback mismatch"; }
ok "readback 16/16"

# 6. syntax + import --------------------------------------------------------
log "6/7 py_compile + import audit"
docker run --rm --network none "$TAG" bash -c \
  "cd /sgl-workspace/sglang && python -m py_compile ${PORT_FILES[*]} && echo PYCOMPILE-16-OK" \
  2>/dev/null | grep -q 'PYCOMPILE-16-OK' || die "py_compile failed"
ok "py_compile 16/16"
AUDIT_MODS="sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks sglang.srt.layers.attention.dsv4.v41_indexer.full_topk sglang.srt.layers.attention.dsv4.v41_indexer.scoring sglang.srt.layers.attention.dsv4.v41_indexer.sparse_table sglang.srt.layers.attention.dsv4.v41_indexer.types sglang.srt.layers.attention.dsv4.v41_indexer sglang.kernels.ops.attention.dsv4.candidate_blocks sglang.kernels.ops.attention.dsv4.fp4_indexer sglang.srt.layers.attention.dsv4.indexer sglang.srt.layers.attention.dsv4.dsv41_sparse sglang.srt.layers.engram sglang.srt.model_executor.model_runner_components.ngram_embedding_manager sglang.srt.layers.attention.deepseek_v4_backend"
docker run --rm --network none "$TAG" bash -c \
  "for m in $AUDIT_MODS; do python -c \"import \$m\" 2>/dev/null && echo OK \$m || echo RED \$m; done; python -c 'import sglang' 2>/dev/null && echo OK sglang || echo RED sglang" \
  2>/dev/null > "$CTX/import-audit.txt"
grep -q '^RED' "$CTX/import-audit.txt" && die "import audit RED"
ok "import audit $(grep -c '^OK' "$CTX/import-audit.txt")/14"

# 7. pytest collection ------------------------------------------------------
log "7/7 pytest collection"
docker run --rm --network none "$TAG" bash -c \
  "cd /sgl-workspace/sglang && python -m pytest test/registered/kernels/ops/attention/test_fp4_indexer.py test/registered/kernels/ops/attention/test_dense_prefill_indexer.py test/registered/kernels/ops/attention/test_dsv41_prefill_sparse_indexer.py test/registered/unit/layers/test_dsv4_nonpaged_indexer.py --collect-only -q >/tmp/col.txt 2>&1; rc=\$?; tail -3 /tmp/col.txt; exit \$rc" \
  2>/dev/null | tail -4 || die "pytest collection red"
ok "collection green"

log "done: $TAG (cid=$new_cid)"
