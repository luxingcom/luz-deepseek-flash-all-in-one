#!/usr/bin/env bash
# gate_check.sh — G-1 装载前置门 + 装载期运行中止（W7-GUARD，2026-10-25）
#
# 法源：
#   DECISIONS-RESOLVED-20261024.md 第十批 D49-P1（已裁）：G-1 = ①前置门 MemAvailable≥100GiB
#   （对齐 r3-boot-arm.sh:9 现行四机硬门，零新参数）+ ③装载期运行中止（有效空闲<6GiB 即中止）。
#   PLAN-REVISION-POST-INCIDENT-20261025.md §4-G1/§8-P1；INCIDENT-01-OUTAGE-20261025.md §2-R1/T4a
#   （20:48:50 avail 107.47GB → 9 秒后有效空闲 2.9GiB——纯低位止损无济于事，护栏必须前移）。
#
# 有效空闲口径 = MemFree + Cached + SReclaimable − Shmem（KiB）
#   —— 与 __GUARDS_KIT_DIR__/oom-gate/oom_gate.sh:63 eff_idle_kb()/117 判定式逐字对齐；
#   watch 线 6GiB 即 oom-gate 现行 warn 线（D49-P1 ③「现 warn 线」原文口径）。
#
# 用法：
#   gate_check.sh pre
#       装载前置门：MemAvailable ≥ 100GiB → rc=0 放行；否则 rc=1 拒载（stdout 一行判定文）。
#   gate_check.sh watch -c <容器名> [-m dry-run|stop] [-i <轮询秒>] [--max-wait <秒>]
#       装载期轮询：有效空闲 < 6GiB → 执行中止动作后 rc=3；
#       被 watch 容器消失（装载毕清/自退）→ rc=0 正常收尾；超过 --max-wait → rc=4。
#       -m dry-run（默认）= 只记录「将 docker stop <容器>」不动作；-m stop = 真实 docker stop。
#
# 退出码：pre: 0=过门 / 1=拒载 / 2=用法错；watch: 0=正常收尾 / 3=破线中止 / 4=超时 / 2=用法错
#
# 测试接缝（仅单测注入用，阈值本身无任何可调参数——D49「零新参数」）：
#   GATE_MEMINFO_FILE  覆盖 /proc/meminfo 读取源（默认 /proc/meminfo）
#   GATE_DOCKER_BIN    覆盖 docker 可执行（默认 docker；watch 单测替换假 docker 用）
#   GATE_NOW           覆盖时间戳（默认 date -u +%Y-%m-%dT%H:%M:%SZ）
set -uo pipefail

PRE_MIN_KIB=$((100 * 1048576))    # 前置门 100GiB（对齐 r3-boot-arm.sh:9 UMA 总账硬门）
WATCH_MIN_KIB=$((6 * 1048576))    # 运行中止线 6GiB（oom-gate warn 线口径）

MEMINFO="${GATE_MEMINFO_FILE:-/proc/meminfo}"
DOCKER_BIN="${GATE_DOCKER_BIN:-docker}"
TAG="[gate_check]"

ts() { printf '%s' "${GATE_NOW:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"; }

# 单字段读数（KiB）——pre 门用
memavail_kib() {
  awk '/^MemAvailable:/{print $2}' "$MEMINFO"
}

# 有效空闲（KiB）——watch 用；判据同 oom_gate.sh:63 eff_idle_kb()
eff_free_kib() {
  awk '/^MemFree:/{f=$2}/^Cached:/{c=$2}/^SReclaimable:/{s=$2}/^Shmem:/{m=$2}END{print f+c+s-m}' "$MEMINFO"
}

kib_to_gib() {  # KiB → GiB 保留 2 位
  awk -v k="$1" 'BEGIN{printf "%.2f", k/1048576}'
}

usage() {
  sed -n '2,30p' "$0" | grep -E '^#   |^# 用法|^# 退出码' | sed 's/^# \{0,1\}//'
  exit 2
}

# ── pre 模式 ────────────────────────────────────────────────────────────────
do_pre() {
  local avail rc
  avail=$(memavail_kib)
  if [ -z "$avail" ] || [ "$avail" -le 0 ] 2>/dev/null; then
    echo "${TAG} $(ts) PRE FAIL meminfo 不可读或 MemAvailable 非法（src=${MEMINFO}）" >&2
    return 1
  fi
  if [ "$avail" -ge "$PRE_MIN_KIB" ]; then
    echo "${TAG} $(ts) PRE PASS MemAvailable=$(kib_to_gib "$avail")GiB >= 100GiB（r3-boot 硬门口径）"
    return 0
  else
    echo "${TAG} $(ts) PRE REFUSE MemAvailable=$(kib_to_gib "$avail")GiB < 100GiB ⇒ 拒载（rc=1）"
    return 1
  fi
}

# ── watch 模式 ──────────────────────────────────────────────────────────────
# 参数：-c 容器名（必填） -m dry-run|stop -i 轮询秒(默认2) --max-wait 秒(默认3600)
do_watch() {
  local cname= mode=dry-run ivsec=2 maxwait=3600
  while [ $# -gt 0 ]; do
    case "$1" in
      -c) cname="${2:?}"; shift 2 ;;
      -m) mode="${2:?}"; shift 2 ;;
      -i) ivsec="${2:?}"; shift 2 ;;
      --max-wait) maxwait="${2:?}"; shift 2 ;;
      *) echo "${TAG} watch 未知参数 $1" >&2; return 2 ;;
    esac
  done
  if [ -z "$cname" ]; then echo "${TAG} watch 需要 -c <容器名>" >&2; return 2; fi
  case "$mode" in dry-run|stop) ;; *) echo "${TAG} -m 仅接受 dry-run|stop（收到 '$mode'）" >&2; return 2 ;; esac

  local start=$(date +%s) eff rc
  echo "${TAG} $(ts) WATCH START container=${cname} mode=${mode} iv=${ivsec}s 线=有效空闲<6GiB 判据=MemFree+Cached+SReclaimable-Shmem"
  while :; do
    # 被看容器已消失（装载毕清/自退/他杀）→ 正常收尾
    if ! "$DOCKER_BIN" inspect -f '{{.State.Running}}' "$cname" >/dev/null 2>&1; then
      eff=$(eff_free_kib)
      echo "${TAG} $(ts) WATCH END container=${cname} 已退出，收尾时有效空闲=$(kib_to_gib "$eff")GiB"
      return 0
    fi
    eff=$(eff_free_kib)
    if [ -z "$eff" ] || [ "$eff" -le 0 ] 2>/dev/null; then
      echo "${TAG} $(ts) WATCH meminfo 不可读或有效空闲非法（src=${MEMINFO}）——保守视为破线" >&2
      eff=0
    fi
    if [ "$eff" -lt "$WATCH_MIN_KIB" ]; then
      echo "${TAG} $(ts) WATCH BREACH 有效空闲=$(kib_to_gib "$eff")GiB < 6GiB ⇒ 中止动作（mode=${mode}）"
      if [ "$mode" = stop ]; then
        "$DOCKER_BIN" stop -t 10 "$cname" && echo "${TAG} $(ts) WATCH docker stop ${cname} 已执行" \
          || echo "${TAG} $(ts) WATCH docker stop ${cname} 失败（docker 面不可用？）——rc 仍按破线计" >&2
      else
        echo "${TAG} $(ts) WATCH [DRY-RUN] 将执行 docker stop -t 10 ${cname}（本次不动作）"
      fi
      return 3
    fi
    sleep "$ivsec"
    [ $(( $(date +%s) - start )) -ge "$maxwait" ] && {
      echo "${TAG} $(ts) WATCH TIMEOUT 超 --max-wait=${maxwait}s（有效空闲=$(kib_to_gib "$eff")GiB 未破线）"
      return 4
    }
  done
}

# ── 分发 ────────────────────────────────────────────────────────────────────
case "${1:-}" in
  pre)   shift; do_pre ;;
  watch) shift; do_watch "$@" ;;
  *)     usage ;;
esac
