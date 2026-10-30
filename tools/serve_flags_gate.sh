#!/bin/bash
# serve_flags_gate.sh — 证明"起栈链真的把旗标接进去了"（issue #4 采纳件）
#
# 判据取**生效值**（跑着的进程 argv / 运行时自省），不取源码或 env 里的静态串。
# fail-closed：缺一个即 rc≠0；判据全程用 case 匹配，不经管道取 rc（防管道末端假绿）。
#
# 2026-10-30 UP43050 增缺席判据：--sleep-on-idle 为禁参（上游 sglang #43050：
# GB10+DSv4.1-Flash+DSPARK 空闲 10-20 分钟后被任意请求唤醒即死 prefill，
# py-spy 卡 _low_ratio_index_topk_dense 唤醒重捕获路径；报告者实测去参即正常）。
# 该参**在场即 FAIL**——防 .bak-pre-wg 单参回退面/手拼 SPEC_EXTRA_ARGS 重新引入。
#
# 用法：
#   tools/serve_flags_gate.sh --container r3boot-head --container r3boot-worker
#   tools/serve_flags_gate.sh --argv-file /tmp/argv.txt
#   tools/serve_flags_gate.sh --api http://127.0.0.1:30000        # /get_server_info 面
#   tools/serve_flags_gate.sh --self-test                        # R1-R8 反向用例
#
# 退出码：0=全过；1=有 FAIL；2=用法/取证失败（fail-closed）。
set -u

PAIR_FLAG="--tool-call-parser"
PAIR_VALUE="deepseekv41"
BARE_FLAG="--enable-cache-report"
# UP43050-20261030：禁参（在场=FAIL；缺席=OK）。判据方向与其余两参相反。
BAN_FLAG="--sleep-on-idle"
FAIL=0
CHECKED=0

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

# 单份 argv 判定：$1=argv 字符串（NUL 已转空格），$2=标签
check_argv() {
  local raw="$1" label="$2"
  local argv=" $raw "
  local rc=0
  CHECKED=$((CHECKED + 1))

  case "$argv" in
    *" $PAIR_FLAG $PAIR_VALUE "*) echo "OK   [$label] $PAIR_FLAG $PAIR_VALUE" ;;
    *" $PAIR_FLAG "*) echo "FAIL [$label] $PAIR_FLAG 存在但值不是 $PAIR_VALUE（引擎可能静默回落默认 parser）"; rc=1 ;;
    *) echo "FAIL [$label] 缺少 $PAIR_FLAG $PAIR_VALUE（起栈链未接线）"; rc=1 ;;
  esac

  case "$argv" in
    *" $BARE_FLAG "*) echo "OK   [$label] $BARE_FLAG" ;;
    *) echo "FAIL [$label] 缺少 $BARE_FLAG（usage.prompt_tokens_details.cached_tokens 将恒 null）"; rc=1 ;;
  esac

  # UP43050-20261030 缺席判据（方向相反：在场=FAIL，缺席=OK）。
  case "$argv" in
    *" $BAN_FLAG "*) echo "FAIL [$label] $BAN_FLAG 在场（上游 sglang #43050：GB10+DSv4.1-Flash+DSPARK 空闲唤醒即死 prefill 挂起；host 侧规避=该参必须缺席——查 boot SERVER_ARGS/SPEC_EXTRA_ARGS/旧件回拷面）"; rc=1 ;;
    *) echo "OK   [$label] $BAN_FLAG 缺席（UP43050 规避在位）" ;;
  esac

  [ "$rc" -eq 0 ] || FAIL=$((FAIL + 1))
  return "$rc"
}

argv_from_container() {
  local ctr="$1" out rc
  out=$(docker exec "$ctr" sh -c "tr '\\0' ' ' < /proc/1/cmdline" 2>/dev/null)
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$out" ]; then
    echo "FAIL [$ctr] 取证失败：读不到 /proc/1/cmdline（容器不在、或无权限）" >&2
    return 2
  fi
  printf '%s' "$out"
}

argv_from_api() {
  local url="$1"
  curl -sf --max-time 10 "$url/get_server_info" 2>/dev/null \
    | python3 - "$PAIR_VALUE" <<'PY'
import json, sys
try:
    info = json.load(sys.stdin)
except Exception as exc:
    print("ARGV_API_UNPARSABLE:%s" % exc, file=sys.stderr)
    sys.exit(2)
wanted = sys.argv[1]
parser = info.get("tool_call_parser")
report = info.get("enable_cache_report")
argv = []
if parser == wanted:
    argv += ["--tool-call-parser", parser]
elif parser:
    argv += ["--tool-call-parser", parser]
if report is True:
    argv.append("--enable-cache-report")
# UP43050 缺席判据尽力取证：/get_server_info 若暴露 sleep_on_idle（顶层或
# server_args 嵌套两种形都认），为真即回放禁参 token 让 BAN_FLAG 判据红。
# 字段不暴露（老代际形）时该模式对禁参为盲——缺席判据的权威取证面=argv 两模式。
sa = info.get("server_args") if isinstance(info.get("server_args"), dict) else {}
if info.get("sleep_on_idle") is True or sa.get("sleep_on_idle") is True:
    argv.append("--sleep-on-idle")
print(" ".join(argv))
PY
}

# 自检用探针：跑判据但不把负控制计入全局 FAIL
probe_rc() {
  local saved=$FAIL
  FAIL=0
  check_argv "$1" "$2" >/dev/null
  local rc=$?
  FAIL=$saved
  return "$rc"
}

self_test() {
  echo "== serve_flags_gate self-test（issue #4 R1-R7 + UP43050 R8）=="
  local rc
  local good="--reasoning-parser deepseek-v41 --max-queued-requests 32 --tool-call-parser deepseekv41 --enable-cache-report"

  probe_rc "${good/--tool-call-parser deepseekv41/}" "R1 删 --tool-call-parser"; rc=$?
  [ "$rc" -ne 0 ] && echo "PASS R1 负控制 rc=$rc" || { echo "FAIL R1 负控制应 rc≠0"; FAIL=$((FAIL+1)); }

  probe_rc "${good/--enable-cache-report/}" "R2 删 --enable-cache-report"; rc=$?
  [ "$rc" -ne 0 ] && echo "PASS R2 负控制 rc=$rc" || { echo "FAIL R2 负控制应 rc≠0"; FAIL=$((FAIL+1)); }

  # R3：静态串只出现在注释/源码，不进 argv
  probe_rc "--reasoning-parser deepseek-v41 --max-queued-requests 32" "R3 静态串在、argv 不在"; rc=$?
  [ "$rc" -ne 0 ] && echo "PASS R3 负控制 rc=$rc" || { echo "FAIL R3 负控制应 rc≠0"; FAIL=$((FAIL+1)); }

  probe_rc "$good" "R4 正控制"; rc=$?
  [ "$rc" -eq 0 ] && echo "PASS R4 正控制 rc=0" || { echo "FAIL R4 正控制应 rc=0"; FAIL=$((FAIL+1)); }

  probe_rc "${good/deepseekv41/deepseek-v41}" "R5 值拼错"; rc=$?
  [ "$rc" -ne 0 ] && echo "PASS R5 值拼错 rc=$rc" || { echo "FAIL R5 值拼错应 rc≠0"; FAIL=$((FAIL+1)); }

  # R6：判据不接管道取 rc（本闸门用 case）；管道形态下直接判据仍须红
  probe_rc "${good/--tool-call-parser deepseekv41/}" "R6 直接判据"; rc=$?
  [ "$rc" -ne 0 ] && echo "PASS R6 直接判据 rc=$rc（与管道形态解耦）" || { echo "FAIL R6 直接判据应 rc≠0"; FAIL=$((FAIL+1)); }

  # R7：角色差异——head 全、worker 缺，整体必须红
  probe_rc "$good" "R7 head"; local r_head=$?
  probe_rc "${good/--enable-cache-report/}" "R7 worker"; local r_worker=$?
  [ "$r_head" -eq 0 ] && [ "$r_worker" -ne 0 ] && echo "PASS R7 角色差异（head=0/worker≠0）" \
    || { echo "FAIL R7 角色差异应 head=0 且 worker≠0"; FAIL=$((FAIL+1)); }

  # R8（UP43050-20261030）：禁参 --sleep-on-idle 在场必须红（缺席判据判别力证明）
  probe_rc "$good --sleep-on-idle" "R8 禁参在场"; rc=$?
  [ "$rc" -ne 0 ] && echo "PASS R8 禁参在场 rc=$rc" || { echo "FAIL R8 禁参在场应 rc≠0"; FAIL=$((FAIL+1)); }

  echo "== self-test 结束：FAIL=$FAIL =="
  [ "$FAIL" -eq 0 ]
}

API_URL=""
ARGV_FILES=()
CONTAINERS=()
MODE="live"

while [ $# -gt 0 ]; do
  case "$1" in
    --self-test) MODE="self"; shift ;;
    --api) [ $# -ge 2 ] || usage; API_URL="$2"; shift 2 ;;
    --argv-file) [ $# -ge 2 ] || usage; ARGV_FILES+=("$2"); shift 2 ;;
    --container) [ $# -ge 2 ] || usage; CONTAINERS+=("$2"); shift 2 ;;
    -h|--help) usage ;;
    *) echo "未知参数: $1" >&2; usage ;;
  esac
done

if [ "$MODE" = "self" ]; then
  self_test
  exit $?
fi

if [ ${#ARGV_FILES[@]} -eq 0 ] && [ ${#CONTAINERS[@]} -eq 0 ] && [ -z "$API_URL" ]; then
  echo "至少给一个取证源：--container / --argv-file / --api" >&2
  usage
fi

for f in "${ARGV_FILES[@]:-}"; do
  [ -n "$f" ] || continue
  [ -r "$f" ] || { echo "FAIL [$f] 文件不可读" >&2; exit 2; }
  check_argv "$(tr '\0' ' ' < "$f")" "$f"
done

for c in "${CONTAINERS[@]:-}"; do
  [ -n "$c" ] || continue
  argv=$(argv_from_container "$c") || exit 2
  check_argv "$argv" "$c"
done

if [ -n "$API_URL" ]; then
  argv=$(argv_from_api "$API_URL") || exit 2
  check_argv "$argv" "$API_URL/get_server_info"
fi

echo "== 判定：取证 $CHECKED 份，FAIL=$FAIL =="
[ "$FAIL" -eq 0 ]
