#!/bin/bash
# adapter-manifest-verify.sh — adapter/包清单（MANIFEST.md5 形）只读校验工具（EQ-12 产品化件）
#
# 【为什么存在】外部手册 P3-7（部署篇 §44 口径）：清单头部注释行被逐词当路径解析=
#   假缺件高频警报源；「拿清单行数 vs 文件数当缺口」的差额实为注释行，非真缺口。
#   本工具内建注释过滤、逐件 md5 对 manifest、输出「N 件差异」机器可判结果——
#   把「比对前先 grep -E '^[0-9a-f]{32}  ' 过滤注释行」从人工纪律变成工具输出
#   （EQ-12，0.3.4re 缺陷修复单元；任务书 035-W0-TASKBOOK-20261030.md §EQ-12）。
#
# 【规范格式（本工具执法）】清单只允许三类行，注释行与路径条目行彻底分离：
#   ① 条目行：^[0-9a-f]{32} + 两个空格 + 相对路径（md5sum -c 同形；禁绝对路径与 .. 段）
#   ② 注释行：统一 # 前缀（不可混淆前缀；GNU md5sum -c 容忍=先例 regen-manifest.sh）
#   ③ 空白行
#   其余任何行=格式红（exit 2，fail-loud）——「统一不可混淆前缀」的执法面：
#   任何将来混入的、既非条目也非 # 注释的行都会被拒，不会静默滑过去当路径比对。
#
# 【只读律】校验路径零写盘：无 mktemp、无重定向建件、无移删改、无 heredoc/herestring
#   落盘（进程替换经 /dev/fd 管道，Linux 上不建临时件）；--selfcheck 的测试夹具仅落
#   /tmp，其 T7 以 strace %file 直证「校验路径零写向文件系统调用」。
#
# 【用法】
#   bash tools/adapter-manifest-verify.sh --manifest <清单> [--root <目标树>]
#   bash tools/adapter-manifest-verify.sh --manifest <清单> --root <目标树> --extra \
#        [--extra-exclude './MANIFEST.md5,./README.md']
#   bash tools/adapter-manifest-verify.sh --selfcheck
#   缺省 --root=$PWD（与「cd <目标树> && md5sum -c <清单>」的既有用法同位）；
#   --extra=另检树内多件（树列举口径=find 排 __pycache__ 与 *.pyc，adapter-sync 家族律）；
#   --extra-exclude=逗号分隔的不计入自指件（可带或不带 ./ 前缀）。
#
# 【输出（机器可判）】末行 RESULT 形如：
#   [adapter-manifest-verify] RESULT: 0 件差异=通过（exit 0）
#   [adapter-manifest-verify] RESULT: 3 件差异=失败（缺件=2 md5不符=1 多件=0）（exit 1）
#
# 【出口】0=0 件差异；1=差异红（缺件/md5不符/多件≥1）；2=用法/格式红（不可混淆行、
#   重复条目、零条目清单等）；3=环境红（清单不可读/树缺位/md5 采集失败）。
set -uo pipefail

TAG="[adapter-manifest-verify]"
red()  { printf '%s[RED] %s\n' "$TAG" "$*" >&2; }
info() { printf '%s %s\n' "$TAG" "$*"; }

usage() {
  cat <<'USAGE'
用法：
  adapter-manifest-verify.sh --manifest <清单> [--root <目标树>] [--extra [--extra-exclude <逗号表>]]
  adapter-manifest-verify.sh --selfcheck
口径：
  规范格式=条目行（32 位 md5+两空格+相对路径）/# 注释行/空行，三类之外=格式红（exit 2）；
  注释行内建过滤，绝不当作路径解析（外部手册 P3-7 假缺件消除件）；
  缺省 --root=$PWD；校验路径零写盘；--selfcheck=本地逻辑自检（零网络零集群，夹具仅落 /tmp）。
USAGE
}

# ── 参数解析 ──
MODE="verify"
MANIFEST=""
ROOT=""
EXTRA=0
EXTRA_EXCLUDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --manifest)      [ $# -ge 2 ] || { red "--manifest 需 <清单路径> 参数"; usage; exit 2; }
                     MANIFEST="$2"; shift ;;
    --root)          [ $# -ge 2 ] || { red "--root 需 <目标树目录> 参数"; usage; exit 2; }
                     ROOT="$2"; shift ;;
    --extra)         EXTRA=1 ;;
    --extra-exclude) [ $# -ge 2 ] || { red "--extra-exclude 需 <逗号分隔件表> 参数"; usage; exit 2; }
                     EXTRA_EXCLUDE="$2"; EXTRA=1; shift ;;
    --selfcheck)     MODE="selfcheck" ;;
    -h|--help)       usage; exit 0 ;;
    *)               red "未知参数: $1"; usage; exit 2 ;;
  esac
  shift
done

TOOL_ABS="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

# ── 本地逻辑自检（零网络零集群；夹具仅落 /tmp；含 strace 零写盘直证）──
selfcheck() {
  local SC_PASS=0 SC_FAIL=0 T M1 R1 H1 H2 H3 OUT RC N
  T=$(mktemp -d /tmp/adapter-manifest-verify-selftest.XXXXXX) || { red "mktemp 失败"; exit 3; }

  sc_ok()  { SC_PASS=$((SC_PASS+1)); info "selfcheck $1 PASS"; }
  sc_bad() { SC_FAIL=$((SC_FAIL+1)); red  "selfcheck $1 FAIL：$2"; }

  # 夹具：3 件小树 + 含 4 行注释（含空 # 行）与 1 空行的清单（注释词刻意含历史假缺件词形）
  R1="$T/r1"; M1="$T/MANIFEST.md5"
  mkdir -p "$R1/sub"
  printf 'alpha\n' >"$R1/f1.py"; printf 'beta\n' >"$R1/f2.py"; printf 'gamma\n' >"$R1/sub/f3.py"
  H1=$(md5sum "$R1/f1.py" | cut -d' ' -f1)
  H2=$(md5sum "$R1/f2.py" | cut -d' ' -f1)
  H3=$(md5sum "$R1/sub/f3.py" | cut -d' ' -f1)
  {
    echo "# MANIFEST.md5 — 测试清单头部注释（EQ-12 负例消除直证用）"
    echo "# 第二行注释：deploy/adapter 整面快照逐件 md5 B1 整面收录 2026-10-13——这些词历史上被逐词当路径"
    echo "# 第三行注释：注释行不是条目，校验工具必须内建过滤"
    echo "#"
    echo ""
    echo "$H1  ./f1.py"
    echo "$H2  ./f2.py"
    echo "$H3  ./sub/f3.py"
  } >"$M1"

  # T1 负例消除直证：含注释行+空行的清单，树完整 → 0 件差异（注释既不计数也不当路径）
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$R1" 2>&1); RC=$?
  if [ "$RC" = 0 ] && echo "$OUT" | grep -q "条目=3 注释=4 空行=1" \
     && echo "$OUT" | grep -q "RESULT: 0 件差异=通过"; then
    sc_ok "T1 含注释清单判 0 差异（负例消除）"
  else sc_bad "T1" "rc=$RC 输出=$OUT"; fi

  # T2 正例：删恰一件 → 报恰好该件缺失
  cp -a "$R1" "$T/r2"; rm -f "$T/r2/f2.py"
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$T/r2" 2>&1); RC=$?
  N=$(echo "$OUT" | grep -c "缺件: ./f2.py")
  if [ "$RC" = 1 ] && [ "$N" = 1 ] && echo "$OUT" | grep -q "缺件=1 md5不符=0" \
     && echo "$OUT" | grep -q "RESULT: 1 件差异=失败" \
     && ! echo "$OUT" | grep -q "缺件: ./f1.py"; then
    sc_ok "T2 删一件报恰好该件缺失（正例）"
  else sc_bad "T2" "rc=$RC 缺件行数=$N 输出=$OUT"; fi

  # T3 内容漂移：改一件内容 → md5不符恰好该件
  cp -a "$R1" "$T/r3"; printf 'drifted\n' >"$T/r3/sub/f3.py"
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$T/r3" 2>&1); RC=$?
  N=$(echo "$OUT" | grep -c "md5不符: ./sub/f3.py")
  if [ "$RC" = 1 ] && [ "$N" = 1 ] && echo "$OUT" | grep -q "缺件=0 md5不符=1"; then
    sc_ok "T3 内容漂移报恰好该件 md5 不符"
  else sc_bad "T3" "rc=$RC 行数=$N 输出=$OUT"; fi

  # T4a 不可混淆执法：裸文本行（无 # 前缀，历史事故原形）→ 格式红 exit 2
  sed '2a deploy/adapter 整面快照逐件 md5 这些词没有 # 前缀' "$M1" >"$T/m4a"
  OUT=$(bash "$TOOL_ABS" --manifest "$T/m4a" --root "$R1" 2>&1); RC=$?
  if [ "$RC" = 2 ] && echo "$OUT" | grep -q "格式红" && echo "$OUT" | grep -q "第 3 行"; then
    sc_ok "T4a 裸文本行（无 # 前缀）被格式红拒绝"
  else sc_bad "T4a" "rc=$RC 输出=$OUT"; fi

  # T4b 分隔符非双空格（单空格行）→ 格式红 exit 2
  printf '%s\n' "$H1 ./f1.py" >"$T/m4b"
  OUT=$(bash "$TOOL_ABS" --manifest "$T/m4b" --root "$R1" 2>&1); RC=$?
  if [ "$RC" = 2 ] && echo "$OUT" | grep -q "格式红"; then
    sc_ok "T4b 单空格分隔行被格式红拒绝"
  else sc_bad "T4b" "rc=$RC 输出=$OUT"; fi

  # T5 重复条目 → 格式红 exit 2
  { cat "$M1"; echo "$H1  ./f1.py"; } >"$T/m5"
  OUT=$(bash "$TOOL_ABS" --manifest "$T/m5" --root "$R1" 2>&1); RC=$?
  if [ "$RC" = 2 ] && echo "$OUT" | grep -q "重复条目"; then
    sc_ok "T5 重复条目被格式红拒绝"
  else sc_bad "T5" "rc=$RC 输出=$OUT"; fi

  # T6 --extra：树内多件；缺省不计、--extra 计红、--extra-exclude 归一豁免
  cp -a "$R1" "$T/r6"; printf 'x\n' >"$T/r6/extra.py"
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$T/r6" 2>&1); RC=$?
  if [ "$RC" = 0 ]; then sc_ok "T6a 缺省模式不把树内多件计入差异"; else sc_bad "T6a" "rc=$RC 输出=$OUT"; fi
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$T/r6" --extra 2>&1); RC=$?
  N=$(echo "$OUT" | grep -c "多件: ./extra.py")
  if [ "$RC" = 1 ] && [ "$N" = 1 ]; then sc_ok "T6b --extra 报恰好该多件"; else sc_bad "T6b" "rc=$RC 行数=$N 输出=$OUT"; fi
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$T/r6" --extra-exclude 'extra.py' 2>&1); RC=$?
  if [ "$RC" = 0 ]; then sc_ok "T6c --extra-exclude 裸名归一豁免生效"; else sc_bad "T6c" "rc=$RC 输出=$OUT"; fi

  # T7 零写盘直证：strace %file 全程无写向文件系统调用（O_CREAT/O_WRONLY/O_RDWR/移删改/改时）。
  #   唯一豁免=/dev/tty：bash 运行时作业控制探测（openat O_RDWR|O_NONBLOCK→ENXIO，字符设备、
  #   非文件系统路径、无持久化）——非本工具代码发起；其余任何写向调用（含 /dev/null）都算红。
  if command -v strace >/dev/null 2>&1; then
    strace -f -e trace=%file -o "$T/trace.log" -- bash "$TOOL_ABS" --manifest "$M1" --root "$R1" >"$T/t7.out" 2>&1
    RC=$?
    local BADLINES
    BADLINES=$(grep -E '^[0-9]+ +[a-zA-Z_][a-zA-Z_0-9]*\(' "$T/trace.log" \
               | grep -E ' O_CREAT| O_WRONLY| O_RDWR|(^| )(creat|creat64|unlink|unlinkat|rename|renameat|renameat2|mkdir|mkdirat|rmdir|link|linkat|symlink|symlinkat|truncate|truncate64|utime|utimes|utimensat|fchmod|fchown|fchmodat|fchownat)\(' \
               | grep -v '"/dev/tty"' || true)
    if [ "$RC" = 0 ] && [ -z "$BADLINES" ]; then
      sc_ok "T7 校验路径零写盘（strace %file 无写向调用）"
    else
      sc_bad "T7" "rc=$RC 写向调用（截前 5 行）：$(echo "$BADLINES" | head -5)"
    fi
  else
    info "selfcheck T7 SKIP（本机无 strace，零写盘以代码面无重定向建件+逐行只读为据）"
  fi

  # T8 用法/环境红
  OUT=$(bash "$TOOL_ABS" --root "$R1" 2>&1); RC=$?
  if [ "$RC" = 2 ]; then sc_ok "T8a 缺 --manifest 用法红"; else sc_bad "T8a" "rc=$RC"; fi
  OUT=$(bash "$TOOL_ABS" --manifest "$T/no-such-manifest" --root "$R1" 2>&1); RC=$?
  if [ "$RC" = 3 ]; then sc_ok "T8b 清单不可读环境红"; else sc_bad "T8b" "rc=$RC"; fi
  OUT=$(bash "$TOOL_ABS" --manifest "$M1" --root "$T/no-such-root" 2>&1); RC=$?
  if [ "$RC" = 3 ]; then sc_ok "T8c 目标树缺位环境红"; else sc_bad "T8c" "rc=$RC"; fi

  rm -rf "$T"
  local SC_TOTAL=$((SC_PASS+SC_FAIL))
  if [ "$SC_FAIL" = 0 ]; then
    info "selfcheck ${SC_TOTAL}/${SC_TOTAL} ALL-GREEN"
    exit 0
  else
    red "selfcheck ${SC_FAIL} 红项 / 共 ${SC_TOTAL} 项（见上）"
    exit 1
  fi
}
[ "$MODE" = "selfcheck" ] && selfcheck

# ── 环境前置（exit 3 族）──
[ -n "$MANIFEST" ] || { red "缺 --manifest <清单路径>"; usage; exit 2; }
[ -f "$MANIFEST" ] || { red "清单不可读（非普通文件或不存在）：$MANIFEST"; exit 3; }
[ -r "$MANIFEST" ] || { red "清单无读权限：$MANIFEST"; exit 3; }
[ -n "$ROOT" ] || ROOT="$PWD"
[ -d "$ROOT" ] || { red "目标树缺位（非目录或不存在）：$ROOT"; exit 3; }
MD5BIN=$(command -v md5sum) || { red "环境缺 md5sum"; exit 3; }
export LC_ALL=C

# ── 第一段：清单解析与格式执法（exit 2 族；格式红先于差异判定=fail-loud）──
RE_ENTRY='^([0-9a-f]{32})  (.+)$'
ENTRIES_PATH=(); ENTRIES_MD5=()
declare -A SEEN=()
COMMENTS=0; BLANKS=0; LN=0; FMT_RED=0
while IFS= read -r line || [ -n "$line" ]; do
  LN=$((LN+1))
  case "$line" in
    "#"*) COMMENTS=$((COMMENTS+1)) ;;
    "")   BLANKS=$((BLANKS+1)) ;;
    *[![:space:]]*)
      if [[ "$line" =~ $RE_ENTRY ]]; then
        m="${BASH_REMATCH[1]}"; p="${BASH_REMATCH[2]}"
        if [[ "$p" == *$'\r' ]]; then
          red "格式红：第 $LN 行疑似 CRLF 行尾（条目路径尾带 \\r）：$line"; FMT_RED=1
        else
          case "${p#./}" in
            /*)      red "格式红：第 $LN 行条目为绝对路径（只允许相对路径）：$p"; FMT_RED=1 ;;
            ..|../*|*/../*|*/..) red "格式红：第 $LN 行条目含 .. 路径段：$p"; FMT_RED=1 ;;
            ".")     red "格式红：第 $LN 行条目路径为 .：$p"; FMT_RED=1 ;;
            *)
              if [ -n "${SEEN[$p]:-}" ]; then
                red "格式红：第 $LN 行重复条目：$p"; FMT_RED=1
              else
                SEEN[$p]=1; ENTRIES_MD5+=("$m"); ENTRIES_PATH+=("$p")
              fi ;;
          esac
        fi
      else
        red "格式红：第 $LN 行既非条目行（^[0-9a-f]{32}+两空格+相对路径）也非 # 注释行/空行（注释行统一 # 前缀）：$line"
        FMT_RED=1
      fi ;;
    *) BLANKS=$((BLANKS+1)) ;;
  esac
done <"$MANIFEST"
[ "$FMT_RED" = 0 ] || { red "清单格式红——按规范格式修正清单后再比对（规范见本工具头注与 deploy/adapter/README.md）"; exit 2; }
N=${#ENTRIES_PATH[@]}
[ "$N" -gt 0 ] || { red "清单零条目（全为注释/空行——疑似拿错文件）：$MANIFEST"; exit 2; }

# ── 第二段：逐件存在性 + 只读 md5 批量采集（进程替换喂主 shell while，经 /dev/fd 管道零写盘）──
MISSING_LIST=(); EX_PATH=()
for p in "${ENTRIES_PATH[@]}"; do
  if [ -f "$ROOT/$p" ]; then EX_PATH+=("$p"); else MISSING_LIST+=("$p"); fi
done

declare -A ACTUAL=()
while IFS=$'\t' read -r ap am; do
  [ -n "$ap" ] || continue
  ACTUAL["$ap"]="$am"
done < <( if [ "${#EX_PATH[@]}" -gt 0 ]; then
            cd "$ROOT" && printf '%s\n' "${EX_PATH[@]}" | xargs -r -d '\n' -- md5sum -- \
              | sed -E 's/^([0-9a-f]{32})  (.+)$/\2\t\1/'
          fi )

# ── 第三段：对表（缺件/md5不符逐件列名）──
OK=0; BAD_LIST=()
for i in "${!ENTRIES_PATH[@]}"; do
  p="${ENTRIES_PATH[$i]}"; want="${ENTRIES_MD5[$i]}"
  [ -f "$ROOT/$p" ] || continue
  got="${ACTUAL[$p]:-}"
  if [ -z "$got" ]; then
    red "内部错：在位条目未被 md5 批量结果覆盖（环境红）：$p"; exit 3
  fi
  if [ "$got" = "$want" ]; then OK=$((OK+1)); else BAD_LIST+=("$p"); fi
done

# ── 第四段（可选）：--extra 树内多件对表 ──
EXTRA_LIST=()
if [ "$EXTRA" = 1 ]; then
  declare -A EXCL=()
  if [ -n "$EXTRA_EXCLUDE" ]; then
    ifs_bak="$IFS"; IFS=','
    for x in $EXTRA_EXCLUDE; do
      x="${x#./}"; x="${x%/}"
      [ -n "$x" ] && EXCL["$x"]=1
    done
    IFS="$ifs_bak"
  fi
  TREE=$( cd "$ROOT" && find . -type f ! -path '*__pycache__*' ! -name '*.pyc' | sort ) \
    || { red "目标树列举失败——环境红"; exit 3; }
  ifs_bak="$IFS"; IFS=$'\n'; set -f
  for tp in $TREE; do
    [ -n "$tp" ] || continue
    key="${tp#./}"
    if [ -z "${SEEN[$tp]:-}" ] && [ -z "${EXCL[$key]:-}" ]; then
      EXTRA_LIST+=("$tp")
    fi
  done
  IFS="$ifs_bak"; set +f
fi

# ── 汇总（机器可判 RESULT 行）──
MISS=${#MISSING_LIST[@]}; BAD=${#BAD_LIST[@]}; EXT=${#EXTRA_LIST[@]}
DIFF=$((MISS+BAD+EXT))

for p in "${MISSING_LIST[@]:-}"; do [ -n "$p" ] && red "缺件: $p"; done
for p in "${BAD_LIST[@]:-}";    do [ -n "$p" ] && red "md5不符: $p"; done
for p in "${EXTRA_LIST[@]:-}";  do [ -n "$p" ] && red "多件: $p"; done

info "manifest=$MANIFEST root=$ROOT"
info "条目=$N 注释=$COMMENTS 空行=$BLANKS（注释行已内建过滤，不计数、不当路径解析）"
info "OK=$OK 缺件=$MISS md5不符=$BAD 多件=$EXT"
if [ "$DIFF" = 0 ]; then
  info "RESULT: 0 件差异=通过（exit 0）"
  exit 0
else
  info "RESULT: $DIFF 件差异=失败（缺件=$MISS md5不符=$BAD 多件=$EXT）"
  exit 1
fi
