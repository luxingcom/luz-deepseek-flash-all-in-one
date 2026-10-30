#!/bin/bash
# plainroute_lint_45525.sh — UPSTREAM-45525 规避 lint（离线静态：纪律在位+双面同件+登记在册）
#
# 【法源】同目录 plainroute_guard_45525.sh 头注（sgl-project/sglang issue #45525：
#   DSPARK spec verify 与普通 decode 贪心分叉；规避=确定性敏感流量路由 plain 服务）。
#   本件=静态面执法：守卫管「活态车道」，lint 管「纪律文本不漂移」。
#
# 【三面】
#   L1 确定性敏感件纪律在位：登记件（ds_gate.py / t62c_anchor_gsm8k.sh）必须自带
#     「测试口 8898、生产口 8899 绝不发流量」拒绝纪律（ds_gate 为 FORBIDDEN_PORT
#     硬拒实现 :82-:94；t62c 为链红线行 :23）——纪律行失配/件在两面皆失=红
#     （确定性敏感流量将失去防误发生产 spec 口的第一道闸）。
#     性能面件（de_c48_bench.py 直连 8899）**不入登记**：吞吐/时延读数非确定性
#     敏感，spec 口正典位不受本规避约束（README「边界」节同口径）。
#   L2 双面同件律：本 kit（5 件含 SOURCE-MD5.txt 自身）在战役仓
#     luz030-opt-campaign/tools/upstream/dsp45525-plainroute/ 与公开仓
#     luz-034re/tools/upstream/dsp45525-plainroute/ 逐字节一致；且
#     SOURCE-MD5.txt 逐行 md5 与实件对表。任一失配=红（nvfp4-kv 同制）。
#   L3 登记在册：战役仓面 docs/TOOL-ANCHORS.md 须含 dsp45525-plainroute 行；
#     公开仓面 docs/KNOWN-ISSUES.md 须含 45525 节。失配=登记漂移=红。
#
# 【用法】
#   tools/upstream/dsp45525-plainroute/plainroute_lint_45525.sh [--selfcheck]
# 可覆盖参数（--selfcheck 夹具隔离用）：--tools-dir D --kit-dir D --other-kit-dir D
#   --registry-file F --face camp|pub
#
# 【出口】0=全绿 / 1=任一面红 / 2=用法错。零网络零容器零写（--selfcheck 仅写 mktemp）。
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"          # <repo>/tools/upstream/dsp45525-plainroute
ROOT="$(cd "$HERE/../../.." && pwd)"           # 仓根（kit 上溯三级：dsp45525-plainroute→upstream→tools→仓根）
FACE=""
TOOLS_DIR=""
KIT_DIR=""
OTHER_KIT_DIR=""
REGISTRY_FILE=""
SELFTEST=0

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tools-dir)     TOOLS_DIR="$2"; shift 2 ;;
    --kit-dir)       KIT_DIR="$2"; shift 2 ;;
    --other-kit-dir) OTHER_KIT_DIR="$2"; shift 2 ;;
    --registry-file) REGISTRY_FILE="$2"; shift 2 ;;
    --face)          FACE="$2"; shift 2 ;;
    --selfcheck)     SELFTEST=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "[LR45525][用法] 未知参数 $1（-h 看头注）" >&2; exit 2 ;;
  esac
done

if [ -z "$FACE" ]; then
  case "$(basename "$ROOT")" in
    luz030-opt-campaign) FACE="camp" ;;
    *)                    FACE="pub"  ;;
  esac
fi
[ -z "$TOOLS_DIR" ] && TOOLS_DIR="$ROOT/tools"
[ -z "$KIT_DIR" ]   && KIT_DIR="$HERE"
if [ -z "$OTHER_KIT_DIR" ]; then
  if [ "$FACE" = "camp" ]; then OTHER_KIT_DIR="$(dirname "$ROOT")/luz-034re/tools/upstream/dsp45525-plainroute"
  else                            OTHER_KIT_DIR="$(dirname "$ROOT")/luz030-opt-campaign/tools/upstream/dsp45525-plainroute"; fi
fi
if [ -z "$REGISTRY_FILE" ]; then
  if [ "$FACE" = "camp" ]; then REGISTRY_FILE="$ROOT/docs/TOOL-ANCHORS.md"
  else                            REGISTRY_FILE="$ROOT/docs/KNOWN-ISSUES.md"; fi
fi

RED=0
ok()   { echo "[LR45525][OK] $*"; }
red()  { echo "[LR45525][RED] $*"; RED=1; }
info() { echo "[LR45525][INFO] $*"; }

# ── L1 确定性敏感件纪律在位 ───────────────────────────────────────────────
# 登记件表：相对 tools/ 路径 : 判据甲 : 判据乙（两判据须同中）
l1_registry() {
  printf '%s\n' \
    'ds_gate.py:FORBIDDEN_PORT = 8899:BASE = "http://127.0.0.1:8898"' \
    't62c_anchor_gsm8k.sh:8898 only:绝不发流量'
}

find_tool() { # 在本面 tools/ 与对面 tools/ 找登记件；找到输出路径，找不到输出空
  local rel="$1" found=""
  [ -r "$TOOLS_DIR/$rel" ] && found="$TOOLS_DIR/$rel"
  if [ -z "$found" ]; then
    otd="$(cd "$(dirname "$(dirname "$OTHER_KIT_DIR")")" 2>/dev/null && pwd)"   # 对面 tools/（kit 上两级）
    [ -n "$otd" ] && [ -r "$otd/$rel" ] && found="$otd/$rel"
  fi
  printf '%s' "$found"
}

l1() {
  echo "== L1 确定性敏感件纪律在位 =="
  l1_registry | while IFS=: read -r rel p1 p2; do
    [ -z "$rel" ] && continue
    f=$(find_tool "$rel")
    if [ -z "$f" ]; then
      echo "[LR45525][RED] L1 登记件 $rel 两面皆失——确定性敏感工具丢失（防误发生产口第一道闸失效）；查 tools/ 面后复跑"
      continue
    fi
    c1=$(grep -cF -- "$p1" "$f" || true)
    c2=$(grep -cF -- "$p2" "$f" || true)
    if [ "$c1" -ge 1 ] && [ "$c2" -ge 1 ]; then
      echo "[LR45525][OK] L1 $rel 纪律在位（『$p1』+『$p2』，件=$f）——确定性敏感面自带测试口纪律，不误发生产 spec 口"
    else
      echo "[LR45525][RED] L1 $rel 纪律行失配（判据『$p1』=$c1/『$p2』=$c2，期望各≥1；件=$f）——8898-only/生产口拒绝纪律被删改；停窗呈报复原本"
    fi
  done
}

# ── L2 双面同件律 ─────────────────────────────────────────────────────────
l2() {
  echo "== L2 双面同件律（kit 5 件逐字节一致 + SOURCE-MD5 对表）=="
  files="README.md plain-face-45525.env plainroute_guard_45525.sh plainroute_lint_45525.sh SOURCE-MD5.txt"
  if [ ! -d "$OTHER_KIT_DIR" ]; then
    red "L2 对面 kit 目录缺失：$OTHER_KIT_DIR——双面同件律破（一面独有=漂移源）；对照本面补齐后复跑"
    return 0
  fi
  bad=0
  for f in $files; do
    if [ ! -r "$KIT_DIR/$f" ] || [ ! -r "$OTHER_KIT_DIR/$f" ]; then
      red "L2 件 $f 在某一面缺失（本面=$KIT_DIR 对面=$OTHER_KIT_DIR）"; bad=1; continue
    fi
    a=$(md5sum "$KIT_DIR/$f" | awk '{print $1}')
    b=$(md5sum "$OTHER_KIT_DIR/$f" | awk '{print $1}')
    if [ "$a" != "$b" ]; then
      red "L2 件 $f 双面 md5 失配（本面=${a:0:8} 对面=${b:0:8}）——改件须双面同批同改并重算 SOURCE-MD5.txt（nvfp4-kv 同制）"
      bad=1
    fi
  done
  [ "$bad" = 0 ] && ok "L2 kit 5 件双面逐字节一致（$KIT_DIR ≡ $OTHER_KIT_DIR）"
  # SOURCE-MD5 对表（只对表 4 件清单行——SOURCE-MD5 自身不入自身清单）
  sm="$KIT_DIR/SOURCE-MD5.txt"
  if [ -r "$sm" ]; then
    smbad=0
    while read -r h f2; do
      [ -z "$h" ] || [ -z "$f2" ] && continue
      case "$h" in \#*) continue ;; esac
      actual=$(md5sum "$KIT_DIR/$f2" 2>/dev/null | awk '{print $1}')
      if [ "$actual" != "$h" ]; then
        red "L2 SOURCE-MD5 对表失配：$f2 登记=$h 实测=${actual:-缺件}——登记与实件脱钩；重算 SOURCE-MD5.txt"
        smbad=1
      fi
    done < "$sm"
    [ "$smbad" = 0 ] && ok "L2 SOURCE-MD5.txt 逐行对表一致"
  else
    red "L2 SOURCE-MD5.txt 不可读：$sm"
  fi
}

# ── L3 登记在册 ───────────────────────────────────────────────────────────
l3() {
  echo "== L3 登记在册（$FACE 面）=="
  pat="dsp45525-plainroute"
  if [ "$FACE" = "pub" ]; then pat="45525"; fi
  if [ -r "$REGISTRY_FILE" ]; then
    c=$(grep -c -- "$pat" "$REGISTRY_FILE" || true)
    if [ "$c" -ge 1 ]; then
      ok "L3 登记行在位（$REGISTRY_FILE 含『$pat』×$c）"
    else
      red "L3 登记行失位：$REGISTRY_FILE 不含『$pat』——kit 落地而登记漂移（无锚=防漂移面失效）；补登记后复跑"
    fi
  else
    red "L3 登记面不可读：$REGISTRY_FILE（$FACE 面）——登记文件丢失；停窗呈报"
  fi
}

# ── selfcheck（离线夹具：假 tools 对/假 kit 对/假登记面，红绿两面）──────────
selfcheck() {
  local T rc_pass=0 rc_fail=0
  T="$(mktemp -d)" || { echo "[LR45525][SELFTEST] mktemp 失败"; exit 1; }
  # 假 tools：纪律在位形
  mkdir -p "$T/tools"
  printf 'BASE = "http://127.0.0.1:8898"\nFORBIDDEN_PORT = 8899\n' > "$T/tools/ds_gate.py"
  printf '# 红线：8898 only（8899=生产口绝不发流量）\n' > "$T/tools/t62c_anchor_gsm8k.sh"
  # 假 kit 对（本面/对面同内容）+ SOURCE-MD5
  for d in "$T/kitA" "$T/kitB"; do
    mkdir -p "$d"
    cp "$KIT_DIR/plainroute_lint_45525.sh" "$d/" 2>/dev/null || printf '# lint\n' > "$d/plainroute_lint_45525.sh"
    printf 'A\n' > "$d/README.md"; printf 'B\n' > "$d/plain-face-45525.env"
    cp "$KIT_DIR/plainroute_guard_45525.sh" "$d/" 2>/dev/null || printf '# guard\n' > "$d/plainroute_guard_45525.sh"
  done
  { md5sum "$T/kitA/README.md" "$T/kitA/plain-face-45525.env" "$T/kitA/plainroute_guard_45525.sh" | awk '{print $1"  "$2}' | sed "s|$T/kitA/||"; } > "$T/kitA/SOURCE-MD5.txt"
  cp "$T/kitA/SOURCE-MD5.txt" "$T/kitB/SOURCE-MD5.txt"
  # 假登记面
  printf 'x dsp45525-plainroute y\n' > "$T/anchors.md"
  # 用例 1：全绿基线（camp 面）
  out=$(bash "$0" --face camp --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/kitB" --registry-file "$T/anchors.md" 2>&1); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q 'L1 ds_gate.py 纪律在位' && printf '%s' "$out" | grep -q 'L2 kit 5 件双面逐字节一致' && printf '%s' "$out" | grep -q 'L3 登记行在位'; then
    echo "[LR45525][SELFTEST] 用例1 全绿基线：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例1 全绿基线：FAIL（rc=$rc 输出=$out）"; rc_fail=$((rc_fail+1)); fi
  # 用例 2：纪律行被删→L1 红
  printf 'BASE = "http://127.0.0.1:8899"\n' > "$T/tools/ds_gate.py"
  out=$(bash "$0" --face camp --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/kitB" --registry-file "$T/anchors.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'L1 ds_gate.py 纪律行失配'; then
    echo "[LR45525][SELFTEST] 用例2 纪律删改必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例2 纪律删改必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  printf 'BASE = "http://127.0.0.1:8898"\nFORBIDDEN_PORT = 8899\n' > "$T/tools/ds_gate.py"
  # 用例 3：登记件两面皆失→L1 红
  mv "$T/tools/t62c_anchor_gsm8k.sh" "$T/t62c.bak"
  out=$(bash "$0" --face camp --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/kitB" --registry-file "$T/anchors.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'L1 登记件 t62c_anchor_gsm8k.sh 两面皆失'; then
    echo "[LR45525][SELFTEST] 用例3 登记件丢失必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例3 登记件丢失必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  mv "$T/t62c.bak" "$T/tools/t62c_anchor_gsm8k.sh"
  # 用例 4：双面某件漂移→L2 红
  printf 'DRIFT\n' >> "$T/kitB/README.md"
  out=$(bash "$0" --face camp --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/kitB" --registry-file "$T/anchors.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'L2 件 README.md 双面 md5 失配'; then
    echo "[LR45525][SELFTEST] 用例4 双面漂移必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例4 双面漂移必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  cp "$T/kitA/README.md" "$T/kitB/README.md"
  # 用例 5：SOURCE-MD5 与实件脱钩→L2 红
  printf '00000000000000000000000000000000  README.md\n' >> "$T/kitA/SOURCE-MD5.txt"
  out=$(bash "$0" --face camp --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/kitB" --registry-file "$T/anchors.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'L2 SOURCE-MD5 对表失配'; then
    echo "[LR45525][SELFTEST] 用例5 SOURCE-MD5 脱钩必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例5 SOURCE-MD5 脱钩必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  cp "$T/kitB/SOURCE-MD5.txt" "$T/kitA/SOURCE-MD5.txt"
  # 用例 6：pub 面登记失位→L3 红
  printf 'no registry here\n' > "$T/known.md"
  out=$(bash "$0" --face pub --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/kitB" --registry-file "$T/known.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'L3 登记行失位'; then
    echo "[LR45525][SELFTEST] 用例6 登记失位必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例6 登记失位必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 7：对面 kit 目录整失→L2 红
  out=$(bash "$0" --face camp --tools-dir "$T/tools" --kit-dir "$T/kitA" --other-kit-dir "$T/nonexistent" --registry-file "$T/anchors.md" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'L2 对面 kit 目录缺失'; then
    echo "[LR45525][SELFTEST] 用例7 对面缺失必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[LR45525][SELFTEST] 用例7 对面缺失必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  rm -rf "$T"
  echo "[LR45525][SELFTEST] 判别力电池：$rc_pass PASS / $rc_fail FAIL（7 例，离线零网络）"
  [ "$rc_fail" = 0 ] || exit 1
}

if [ "$SELFTEST" = 1 ]; then selfcheck; exit $?; fi

OUT_L1=$(l1); printf '%s\n' "$OUT_L1"
OUT_L2=$(l2); printf '%s\n' "$OUT_L2"
OUT_L3=$(l3); printf '%s\n' "$OUT_L3"
N_RED=$(printf '%s\n%s\n%s\n' "$OUT_L1" "$OUT_L2" "$OUT_L3" | grep -c '\[LR45525\]\[RED\]' || true)
if [ "$N_RED" -gt 0 ]; then RED=1; fi
if [ "$RED" = 0 ]; then
  echo "[LR45525] lint 全绿（纪律在位+双面同件+登记在册）"
  exit 0
else
  echo "[LR45525] lint 存在红面（见上；红=纪律/双面/登记漂移，逐行处置后复跑）"
  exit 1
fi
