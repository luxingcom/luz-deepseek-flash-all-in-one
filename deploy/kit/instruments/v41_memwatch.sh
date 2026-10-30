#!/bin/bash
# v41_memwatch.sh — 四机内存瞬态量具（宿主侧，高频采样）
#
# 为什么存在（2026-09-22，用户令）：旧阶梯只记「剂量结束时的 MemAvailable」一个点，
# 而 9/21 事故与 600K 形态的失效模式全是「**过程**中的瞬态峰值」——峰值不在起点也
# 不在终点，单点采样必然看不见。本量具 250ms 一发，逐机留全序列。
#
# 口径 = 与生产地板守卫 oom_gate.sh **逐字节同款**：
#     有效空闲(eff_idle) = MemFree + Cached + SReclaimable − Shmem     [KiB]
# 另单独留 MemFree 与 MemAvailable：
#   · MemFree —— 设备侧（驱动 _memdescAllocInternal）看的是它，不是 MemAvailable
#     （页缓存占着 MemFree 时驱动会分配失败 ⇒ 0x51 族行；见 2026-09-11「页缓存=
#     设备内存残留真身」）。
#   · MemAvailable —— 历史日志（Boot5/Boot6 剂量、monitor）用的口径，留一列保证
#     跨靴可比（不与守卫口径混用，只在报告里并列展示）。
#     （`Boot5`/`Boot6` 是**靴次代号**，含义见 ~/w6-kit/GLOSSARY.md）
#
# 用法（单机）：
#   v41_memwatch.sh loop <out.tsv> [interval_s=0.25] [max_s=7200]   # 采样循环（前台）
#   v41_memwatch.sh mark <out.tsv> <tag>                            # 本机打标记
#   v41_memwatch.sh stop <out.tsv>                                  # 本机请求停止
#   v41_memwatch.sh at <host> <mark|stop|fetch> <out.tsv> [tag]     # 远端同一动作
#   v41_memwatch.sh start <host> <out.tsv> [iv] [max]               # 远端后台起采样
#   v41_memwatch.sh fetch <host> <out.tsv>                          # cat 远端文件
# 行格式：
#   #HOST <hostname> <epoch_s>
#   S <epoch_ms> <eff_idle_kb> <memfree_kb> <cached_kb> <sreclaim_kb> <shmem_kb> <memavail_kb>
#   M <epoch_ms> <tag>
#   #END <epoch_s> <samples>
# ★远端动作一律走 at/start（★2026-09-22 踩过的坑：mark/stop 只有本地实现 ⇒ 四机
#   只有 head 有标记，报告对 3/4 台机器"沉默通过"——量具自己必须先被量）。
set -uo pipefail

sample_line() {  # $1=now_ms
  awk -v ms="$1" '
    /^MemFree:/{f=$2} /^Cached:/{c=$2} /^SReclaimable:/{s=$2} /^Shmem:/{m=$2} /^MemAvailable:/{a=$2}
    END{printf "S %s %d %d %d %d %d %d\n", ms, f+c+s-m, f, c, s, m, a}' /proc/meminfo
}

now_ms() { date +%s%3N; }

# 远端 ssh 侧的脚本路径必须绝对：$0 可能是相对路径（在远端 cwd 下不存在）。
SELF="$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")"

is_local() {
  local h="$1"
  [ "$h" = "$(hostname)" ] || [ "$h" = localhost ] || [ "$h" = "$(hostname -s)" ] || [ "$h" = "$(hostname -f)" ] \
    || [ "$h" = "$(saddr "$h")" ]
}

# 远端寻址（2026-09-22 事故后加）：`ssh <node02>` 走 ~/.ssh/config 的
# `Hostname <fabric-ip>`（NVIDIA Sync 写的管理网 IP），管理网 sshd 不可达时 ssh 干等
# 超时 ⇒ 远端动作静默失败、只留 0 字节采样文件（本量具曾因此丢掉整机的整轮数据）。
# /etc/hosts 里的集群侧真身是 192.168.5.x：一律用 `-o HostName=<集群 IP>` 覆盖 config
# （命令行 -o 优先于 config），User/IdentityFile/known_hosts 仍按别名解析。
saddr() {
  local h="$1" ip
  is_local_raw "$h" && { printf '%s' "$h"; return; }
  ip="$(getent hosts "$h" 2>/dev/null | awk 'NR==1{print $1}')"
  [[ -n "$ip" ]] || ip="$h"
  printf '%s' "$ip"
}
is_local_raw() { [ "$1" = "$(hostname)" ] || [ "$1" = localhost ] || [ "$1" = "$(hostname -s)" ] || [ "$1" = "$(hostname -f)" ]; }
ssh_to() { local h="$1"; shift; ssh -n -o ConnectTimeout=8 -o "HostName=$(saddr "$h")" "$h" "$@"; }

case "${1:-}" in
loop)
  out="${2:?out 文件}"; iv="${3:-0.25}"; max="${4:-7200}"
  stopf="$out.stop"
  rm -f "$stopf"
  { printf '#HOST %s %s\n' "$(hostname)" "$(date +%s)"; } >>"$out"
  t0=$(date +%s); n=0
  while :; do
    [ -f "$stopf" ] && break
    [ $(( $(date +%s) - t0 )) -gt "$max" ] && break
    sample_line "$(now_ms)" >>"$out"
    n=$((n+1))
    sleep "$iv"
  done
  printf '#END %s %s\n' "$(date +%s)" "$n" >>"$out"
  rm -f "$stopf"
  ;;
mark)
  out="${2:?out 文件}"; tag="${3:?tag}"
  printf 'M %s %s\n' "$(now_ms)" "$tag" >>"$out"
  ;;
stop)
  out="${2:?out 文件}"
  : > "$out.stop"
  ;;
fetch)
  # rc 必须可信：调用方（阶梯 mw_fetch）靠 rc + 采样点数判「取回是否成功」。
  # 远端不可达时 ssh 返 255，cat 失败返 1 —— 两者都不许当 0 处理。
  host="${2:?host}"; f="${3:?远端文件}"
  if is_local "$host"; then cat "$f" 2>/dev/null; else ssh_to "$host" "cat '$f'" 2>/dev/null; fi
  ;;
at)  # 远端/本机同动作分发：at <host> <mark|stop|fetch> <out> [tag]
  host="${2:?host}"; shift 2
  if is_local "$host"; then
    exec bash "$SELF" "$@"
  else
    ssh_to "$host" "bash '$SELF' $(printf '%q ' "$@")" 2>/dev/null
  fi
  ;;
start)
  host="${2:?host}"; f="${3:?远端文件}"; iv="${4:-0.25}"; max="${5:-7200}"
  if is_local "$host"; then
    setsid nohup bash "$SELF" loop "$f" "$iv" "$max" </dev/null >/dev/null 2>&1 &
  else
    ssh_to "$host" "setsid nohup bash '$SELF' loop '$f' '$iv' '$max' </dev/null >/dev/null 2>&1 & " 2>/dev/null
    # 起停核查：静默失败的 start 会让该机 0 采样，而报告只按有数据的机器算 ⇒
    # 「部分通过」= 缺机裸奔。等采样真的落盘再返 0（最多 6s）。
    i_c=0; i_ok=0
    for i in 1 2 3 4 5 6; do
      sleep 1
      i_c="$(ssh_to "$host" "grep -c '^S ' '$f' 2>/dev/null" 2>/dev/null)"
      [[ "$i_c" =~ ^[0-9]+$ ]] && [ "$i_c" -gt 0 ] && { i_ok=1; break; }
    done
    [[ "$i_ok" == 1 ]] || {
      printf '⛔ 远端采样未起来：%s（addr=%s，集群 IP 可达性/sshd 两件事都要查）\n' "$host" "$(saddr "$host")" >&2
      exit 4; }
  fi
  ;;
*)
  grep -E '^# (用法|口径)' "$0" | sed 's/^# //'; exit 2 ;;
esac
