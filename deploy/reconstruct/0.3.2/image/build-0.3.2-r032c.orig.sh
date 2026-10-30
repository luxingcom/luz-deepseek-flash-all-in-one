#!/bin/bash
# build-0.3.2-r032c.sh — r032c 位级保持形烘制（S-FIXC-BITPRESERVE-20261018）
# = build-0.3.2-r032b.sh 配方 + r032c 位级保持补件（scoring.py 恢复 stock 79cafec0 候选序排序）=> 16 件。
# 闭包准入：logs/S-FIXC-BITPRESERVE-20261018/closure/audit-r032c.txt（三层面 GREEN；r032b→r032c 差分仅 scoring.py）+ROOTCAUSE-COUPLING.md。
# 铁律全承（0.2.8/0.3.1/r032 先例）：一次性 context / mtime 钉死两遍 / BUILT_AT 常量 / 层天花板门 /
# 镜像内读回逐件校验 / fail-closed。零生产触：不 pull / 不 reload / 不动 daemon / 新 tag 零覆盖。
# 用法：
#   bash build-0.3.2-r032c.sh            # 构建 + 读回 + py_compile + import 审计
#   NOCACHE=1 TAG=<临时> bash build-0.3.2-r032c.sh   # 冷构建复现门
#   bash build-0.3.2-r032c.sh --check    # 只做前置断言
set -euo pipefail

REPLAY=/tmp/bt-r032                       # 重演树（79cafec0→295c3097→b9cf2026→f9d89b02 补件）
# 20261030 脱敏：registry 主机改经环境变量注入，缺参拒跑。
BASE="${BASE:?缺环境变量 BASE（<registry-host>:5000/lmsysorg/sglang:main-79cafec0），拒跑}"   # 现役形（80e1ea89；禁 pull）
TAG="${TAG:?缺环境变量 TAG（<registry-host>:5000/dsv41-sglang-optimized:0.3.2-r032c），拒跑}"   # 本地孪生（原 .187 命名连续性；正典为新段）
NOCACHE="${NOCACHE:-0}"
WORK="$HOME/luz030-opt-campaign/logs/S-FIXC-BITPRESERVE-20261018/bake"
CTX="$(mktemp -d "$WORK/ctx-XXXXXX")"     # 一次性 context（0.2.8 定谳）
trap 'rm -rf "$CTX"' EXIT
BUILT_AT="${BUILT_AT:-2026-10-18T05:20:00Z}"
MTIME="2026-10-18T05:20:00Z"              # mtime 钉死常量
CHECK_ONLY=0
[[ "${1:-}" = "--check" ]] && CHECK_ONLY=1

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
ok()   { printf '  OK   %s\n' "$*"; }
die()  { printf '  FATAL %s\n' "$*" >&2; exit 1; }

# 16 件回移植清单（r032 15 件 + candidate_blocks.py；钉死防漂移）
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
TREE_MD5="$HOME/luz030-opt-campaign/logs/S-FIXC-BITPRESERVE-20261018/closure/port16-tree-md5-r032c.txt"

# ═══ 1. 前置断言 ═══
log "1/7 前置断言"
[[ -d "$REPLAY/.git" ]] || die "重演树缺：$REPLAY"
[[ "$(git -C "$REPLAY" rev-parse --short HEAD)" = f9d89b02 ]] || die "重演树 HEAD 非 f9d89b02（补件 commit）"
docker image inspect "$BASE" >/dev/null 2>&1 || die "基座镜像 $BASE 不在本机（禁 pull——零生产触红线）"
base_layers=$(docker image inspect -f '{{len .RootFS.Layers}}' "$BASE")
base_cid=$(docker image inspect -f '{{join .RootFS.Layers " "}}' "$BASE" | sha256sum | cut -c1-16)
base_id=$(docker image inspect -f '{{.Id}}' "$BASE" | cut -c8-19)
ok "基座 $BASE  image=${base_id}  层数=$base_layers  内容身份=$base_cid"
[[ "$base_id" = 80e1ea8979c5* ]] || die "基座形态断言失败：期望 80e1ea89（现役形），实得 $base_id"
if docker image inspect "$TAG" >/dev/null 2>&1; then
  [[ "${FORCE:-0}" = 1 ]] || die "目标 $TAG 已存在。重 build 请显式 FORCE=1"
  log "目标 $TAG 已存在，FORCE=1 => 将覆盖其 tag"
fi
[[ -f "$TREE_MD5" ]] || die "树侧 md5 台账缺：$TREE_MD5"
[[ ${#PORT_FILES[@]} -eq 16 ]] || die "回移植清单数 != 16"

# ═══ 2. staging（git archive 纯净导出）═══
log "2/7 staging 载荷（git archive 自重演树 $(git -C "$REPLAY" rev-parse --short HEAD)）"
mkdir -p "$CTX/rootfs"
git -C "$REPLAY" archive HEAD -- "${PORT_FILES[@]}" | tar -x -C "$CTX/rootfs"
find "$CTX/rootfs" -exec touch -h -d "$MTIME" {} +
find "$CTX/rootfs" -exec touch -h -d "$MTIME" {} +
n_files=$(find "$CTX/rootfs" -type f | wc -l)
[[ "$n_files" -eq 16 ]] || die "staging 件数 $n_files != 16"
( cd "$CTX/rootfs" && md5sum "${PORT_FILES[@]}" ) > "$CTX/staging-md5.txt"
if ! diff <(sort "$TREE_MD5") <(sort "$CTX/staging-md5.txt") >/dev/null; then
  diff <(sort "$TREE_MD5") <(sort "$CTX/staging-md5.txt") | head -10 || true
  die "staging md5 与树台账不一致（fail-closed）"
fi
ok "16 件 staging md5 与树台账逐件一致"

# ═══ 3. Dockerfile（单 COPY 层）═══
log "3/7 Dockerfile 生成"
cat > "$CTX/Dockerfile" <<EOF
FROM $BASE
LABEL DSV41_IMAGE_VERSION="0.3.2-r032c" \
      DSV41_PORT_BASE="520d6d0+fc2795b+391e665(candidate_block_mask)" \
      DSV41_PORT_SCOPE="minimal-deadlock-fix +bit-preserve-selection-order 16 files" \
      DSV41_REPLAY_TREE="$(git -C "$REPLAY" rev-parse HEAD^{tree})" \
      DSV41_BASE_DIGEST="$base_id" \
      BUILT_AT="$BUILT_AT"
COPY rootfs/ /sgl-workspace/sglang/
EOF
ok "Dockerfile：FROM $BASE + 1 COPY 层（层天花板=基座+1）"

[[ "$CHECK_ONLY" = 1 ]] && { log "--check 完成（未构建）"; exit 0; }

# ═══ 4. 构建 ═══
log "4/7 构建 $TAG"
if [[ "$NOCACHE" = 1 ]]; then
  docker build --no-cache -t "$TAG" "$CTX"
else
  docker build -t "$TAG" "$CTX"
fi
new_layers=$(docker image inspect -f '{{len .RootFS.Layers}}' "$TAG")
new_cid=$(docker image inspect -f '{{join .RootFS.Layers " "}}' "$TAG" | sha256sum | cut -c1-16)
[[ "$new_layers" -eq $((base_layers + 1)) ]] || die "层数断言失败：$new_layers != $base_layers+1"
ok "构建完成：层数=$new_layers（基座 $base_layers+1）内容身份 cid=$new_cid"

# ═══ 5. 镜像内读回逐件校验（16 件 md5 对表树台账）═══
log "5/7 镜像内读回校验"
FILES_ARG="${PORT_FILES[*]}"
docker run --rm --network none "$TAG" bash -c "cd /sgl-workspace/sglang && md5sum $FILES_ARG" \
  2>/dev/null | grep -E '^[0-9a-f]{32}  ' | sort > "$CTX/image-md5.txt"
if ! diff <(sort "$TREE_MD5") <(sort "$CTX/image-md5.txt") >/dev/null; then
  diff <(sort "$TREE_MD5") <(sort "$CTX/image-md5.txt") | head -10 || true
  die "镜像内读回 md5 不一致（fail-closed）"
fi
ok "镜像内 16 件 md5 与重演树台账逐字节一致"

# ═══ 6. 语法+import 闭包冒烟（CPU 面）═══
log "6/7 py_compile 16 件 + import 审计（G1 门升格步）"
docker run --rm --network none "$TAG" bash -c \
  "cd /sgl-workspace/sglang && python -m py_compile $FILES_ARG && echo PYCOMPILE-16-OK" \
  2>/dev/null | grep -E "PYCOMPILE-16-OK|Error" || die "语法冒烟未过"
ok "py_compile 16/16 OK"
AUDIT_MODS="sglang.srt.layers.attention.dsv4.v41_indexer.dense_blocks sglang.srt.layers.attention.dsv4.v41_indexer.full_topk sglang.srt.layers.attention.dsv4.v41_indexer.scoring sglang.srt.layers.attention.dsv4.v41_indexer.sparse_table sglang.srt.layers.attention.dsv4.v41_indexer.types sglang.srt.layers.attention.dsv4.v41_indexer sglang.kernels.ops.attention.dsv4.candidate_blocks sglang.kernels.ops.attention.dsv4.fp4_indexer sglang.srt.layers.attention.dsv4.indexer sglang.srt.layers.attention.dsv4.dsv41_sparse sglang.srt.layers.engram sglang.srt.model_executor.model_runner_components.ngram_embedding_manager sglang.srt.layers.attention.deepseek_v4_backend"
docker run --rm --network none "$TAG" bash -c "for m in $AUDIT_MODS; do python -c \"import \$m\" 2>/dev/null && echo OK \$m || echo RED \$m; done; python -c 'import sglang' 2>/dev/null && echo OK sglang || echo RED sglang" \
  2>/dev/null | tee "$CTX/import-audit.txt" | grep -c '^OK' | { read n; echo "  import 审计 OK=$n/13(+sglang)"; }
grep -q '^RED' "$CTX/import-audit.txt" && die "import 审计有 RED（fail-closed）"
ok "import 审计 14/14 OK（16 件符号面 13 模块+sglang 顶层；G1 门升格=烘制内置步）"

# ═══ 7. 四件套 pytest collection 冒烟（S-FIX-W0 G1 红组镜像内重跑）═══
log "7/7 pytest collection 四件套"
docker run --rm --network none "$TAG" bash -c \
  "cd /sgl-workspace/sglang && python -m pytest test/registered/kernels/ops/attention/test_fp4_indexer.py test/registered/kernels/ops/attention/test_dense_prefill_indexer.py test/registered/kernels/ops/attention/test_dsv41_prefill_sparse_indexer.py test/registered/unit/layers/test_dsv4_nonpaged_indexer.py --collect-only -q >/tmp/col.txt 2>&1; rc=\$?; tail -3 /tmp/col.txt; exit \$rc" \
  2>/dev/null | tail -4 || die "pytest collection 红（fail-closed）"
ok "四件套 collection 绿（G1 红组封口）"

log "完成：$TAG（cid=$new_cid；tag 正典化+push 由窗收口段执行）"
