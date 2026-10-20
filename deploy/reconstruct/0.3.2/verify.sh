#!/usr/bin/env bash
# verify.sh — self-check for the 0.3.2 reconstruction kit.
# No production host, GPU, weights or registry access required.
set -uo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
REPO="${REPO:-$(cd "$KIT/../../.." && pwd)}"
FAIL=0
pass() { printf '  PASS  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; FAIL=$((FAIL+1)); }
need() { [[ -e "$1" ]] && pass "exists: $1" || bad "missing: $1"; }
md5of() { md5sum "$1" | cut -d' ' -f1; }
expect_md5() { # path prefix label
  local got; got=$(md5of "$1")
  [[ "$got" == "$2"* ]] && pass "$3 ($got)" || bad "$3: got $got want $2*"
}
soft_md5() { [[ "$(md5of "$1")" == "$2"* ]]; }
patch_check() { # dir patch label — per-file: pre-image or already-applied
  local dir="$1" patch="$2" label="$3" f ok=1 badf=""
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if ( cd "$dir" && git apply --check --include="$f" "$patch" 2>/dev/null ); then
      :
    elif ( cd "$dir" && git apply --check -R --include="$f" "$patch" 2>/dev/null ); then
      :
    else
      ok=0; badf="$badf $f"
    fi
  done < <(grep '^+++ b/' "$patch" | sed 's|^+++ b/||')
  if [[ "$ok" -eq 1 ]]; then
    pass "$label per-file check (pre-image or already-applied)"
  else
    bad "$label target files not at pre/post state:$badf"
  fi
}

echo "== 0. kit manifest =="
if ( cd "$KIT" && md5sum -c MANIFEST.md5 >/dev/null 2>&1 ); then
  pass "MANIFEST.md5 all files"
else
  bad "MANIFEST.md5 mismatch (run: cd $KIT && md5sum -c MANIFEST.md5)"
fi

echo "== 1. env chain =="
check_env() { # file keys md5 label
  local n; n=$(grep -cE '^[A-Z0-9_]+=' "$1" || true)
  [[ "$n" -eq "$2" ]] && pass "$4 keys=$n" || bad "$4 keys=$n want $2"
  expect_md5 "$1" "$3" "$4 md5"
}
check_env "$KIT/env/PROD-FB54-spec1.env" 54 ad635762 "FB54"
check_env "$KIT/env/PROD-E16B1-spec1.env" 54 d55baa00 "E16B1"
check_env "$KIT/env/PROD-E16B2-spec1.env" 56 5877fcb0 "E16B2"
check_env "$KIT/env/CBX1A-CERTM-spec1.env" 56 0729e18d "CBX1A"
grep -q '^DSV41_CERT_HEAD_M=6,12,18,24,30,36,42,48$' "$KIT/env/CBX1A-CERTM-spec1.env" \
  && pass "CBX1A cert M eight-value line" || bad "CBX1A cert M line"

echo "== 1b. top-level current env =="
TOP_ENV="$REPO/deploy/env/CBX1A-CERTM-spec1.env"
if [[ -f "$TOP_ENV" ]]; then
  check_env "$TOP_ENV" 56 0729e18d "top-level CBX1A"
  cmp -s "$TOP_ENV" "$KIT/env/CBX1A-CERTM-spec1.env" \
    && pass "top-level CBX1A = kit CBX1A (byte-exact)" \
    || bad "top-level CBX1A differs from kit CBX1A"
else
  bad "missing top-level deploy/env/CBX1A-CERTM-spec1.env"
fi

echo "== 2. adapter 13+4 =="
for f in build_repack_cuda.sh indexer_hoist.py kv_fp4.py p12_assertion_graph_gather.py \
         reference_impl.py replicated_split.py roce_ar.py seam_mount.py selection_dump.py \
         sitecustomize.py spark_prefill_split.py sparse_wire.py tl_segment.py \
         ep1h-manifest.txt ep1i-manifest.txt patches/0001-sparse_table-nonchunked-topk.patch \
         sitecustomize.py.f6-lmcert; do
  need "$KIT/adapter/files/$f"
done
if ( cd "$KIT/adapter/files" && md5sum -c "$KIT/adapter/production-md5-exact.txt" >/dev/null 2>&1 ); then
  pass "adapter 12 code files = production md5"
else
  bad "adapter production md5 mismatch"
fi
expect_md5 "$KIT/adapter/files/sitecustomize.py" beb131ab "sitecustomize (A6)"
expect_md5 "$KIT/adapter/files/kv_fp4.py" 75062432 "kv_fp4 (R1)"
expect_md5 "$KIT/adapter/files/replicated_split.py" 7d6f79b0 "replicated_split (E16B2)"

echo "== 2b. adapter 0.3.2 assembled tree (87 runtime files) =="
MAN032="$REPO/deploy/adapter/0.3.2-MANIFEST.md5"
if [[ -f "$MAN032" ]]; then
  [[ "$(grep -vE '^(#|$)' "$MAN032" | wc -l)" -eq 87 ]] \
    && pass "0.3.2 adapter manifest rows = 87" || bad "0.3.2 adapter manifest rows != 87"
  TMPA=$(mktemp -d "${TMPDIR:-/tmp}/recon-adapter-XXXXXX") || exit 1
  cp -a "$REPO/deploy/adapter/." "$TMPA/"
  cp -a "$KIT/adapter/files/." "$TMPA/"
  if ( cd "$TMPA" && md5sum -c "$MAN032" >/dev/null 2>&1 ); then
    pass "adapter assembly 87/87 md5"
  else
    bad "adapter assembly md5 mismatch (run md5sum -c in assembled tree)"
  fi
  rm -rf "$TMPA"
else
  bad "missing deploy/adapter/0.3.2-MANIFEST.md5"
fi

echo "== 3. overlay =="
expect_md5 "$KIT/overlay/deepseek_v4_backend.py" a1e7c3b5 "overlay backend"

echo "== 4. b12x =="
expect_md5 "$KIT/b12x/roce_oneshot.py" 035c860c "b12x roce_oneshot"
expect_md5 "$KIT/b12x/_allgather_cute.py" 7253717a "b12x _allgather_cute"
expect_md5 "$KIT/b12x/_roce_proxy.c" 23646e89 "b12x _roce_proxy.c"

echo "== 5. image 16 files =="
if ( cd "$KIT/image/files" && md5sum -c "$KIT/image/port16-tree-md5-r032c.txt" >/dev/null 2>&1 ); then
  pass "image 16/16 = port16 ledger"
else
  bad "image 16-file ledger mismatch"
fi
[[ "$(grep -c '^diff --git' "$KIT/image/79cafec0-to-r032c-16files.patch")" -eq 16 ]] \
  && pass "image patch covers 16 files" || bad "image patch file count != 16"

echo "== 6. patches apply to public 0.3.1 base =="
TMP=$(mktemp -d "${TMPDIR:-/tmp}/recon-verify-XXXXXX") || exit 1
cleanup() { cd /; rm -rf "$TMP"; }
trap cleanup EXIT
mkdir -p "$TMP/adapter/deploy" "$TMP/overlay/deploy/overlay" "$TMP/b12x/deploy/b12x"
cp -a "$REPO/deploy/adapter" "$TMP/adapter/deploy/adapter"
cp -a "$REPO/deploy/overlay/o12c1-prod" "$TMP/overlay/deploy/overlay/o12c1-prod"
cp -a "$REPO/deploy/b12x/b12x" "$TMP/b12x/deploy/b12x/b12x"
patch_check "$TMP/adapter" "$KIT/adapter/adapter-0.3.1-to-0.3.2.patch" "adapter patch"
patch_check "$TMP/overlay" "$KIT/overlay/overlay-0.3.1-to-0.3.2.patch" "overlay patch"
patch_check "$TMP/b12x" "$KIT/b12x/b12x-0.3.1-to-0.3.2.patch" "b12x patch"

if [[ -n "${SGLANG_STOCK:-}" ]]; then
  if ( cd "$SGLANG_STOCK" && md5sum -c "$KIT/image/stock16-md5.txt" >/dev/null 2>&1 ); then
    pass "stock source = 79cafec0 (16 files)"
  else bad "stock source does not match stock16-md5.txt"; fi
  if ( cd "$SGLANG_STOCK" && git apply --check "$KIT/image/79cafec0-to-r032c-16files.patch" 2>/dev/null ); then
    pass "image patch applies to stock"
  else bad "image patch does not apply to stock"; fi
else
  pass "stock/image patch apply skipped (set SGLANG_STOCK to enable)"
fi

echo "== 7. weights + engram =="
[[ "$(wc -l < "$KIT/weights/DeepSeek-V4.1-Flash-1017.sha256")" -eq 84 ]] \
  && pass "weights SHA256SUMS = 84 lines" || bad "weights SHA256SUMS line count"
python3 - "$KIT/weights/engram-bins-manifest.json" <<'PY'
import json, sys
m=json.load(open(sys.argv[1]))
assert m["tp"]==4 and m["layers"]==[1,14]
assert len(m["bins"])==8
assert sum(b["size"] for b in m["bins"])==202758065168
assert all(len(b["sha256"])==64 for b in m["bins"])
assert {(b["layer"],b["rank"]) for b in m["bins"]}=={(l,r) for l in (1,14) for r in range(4)}
print("  PASS  engram manifest: 8 bins / 202758065168 B / sha256 complete")
PY
[[ $? -eq 0 ]] || bad "engram manifest"
for f in pack_engram.py pack_all.sh distribute.sh verify_engram.py verify_remote.py build_and_distribute.sh; do
  need "$KIT/weights/engram-tools/$f"
done

echo "== 8. secret/PII scan =="
HITS=$(grep -rInE 'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE|/home/[a-z][a-z0-9]{5,}([/[:space:]]|$)|password[[:space:]]*=|sudo -S' "$KIT" --exclude=verify.sh 2>/dev/null || true)
TOP_HITS=$(grep -InE 'BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE|/home/[a-z][a-z0-9]{5,}([/[:space:]]|$)|password[[:space:]]*=|sudo -S' \
  "$REPO/UPGRADE-0.3.2.md" "$REPO/deploy/env/CBX1A-CERTM-spec1.env" \
  "$REPO/deploy/adapter/0.3.2-MANIFEST.md5" "$REPO/deploy/adapter/0.3.2-ASSEMBLY.md" 2>/dev/null || true)
if [[ -z "$HITS" && -z "$TOP_HITS" ]]; then pass "no private-key/sudo-token/user-home hits"; else
  bad "secret/PII hits:"; printf '%s\n%s\n' "$HITS" "$TOP_HITS" | head -20
fi

echo "== 9. negative self-test =="
if soft_md5 "$KIT/README.md" deadbeef; then
  bad "negative test did not fail (md5 helper broken)"
else
  pass "negative test: wrong md5 detected"
fi

echo
if [[ "$FAIL" -eq 0 ]]; then
  echo "RECON-KIT PASS"
  exit 0
fi
echo "RECON-KIT FAIL ($FAIL)"
exit 1
