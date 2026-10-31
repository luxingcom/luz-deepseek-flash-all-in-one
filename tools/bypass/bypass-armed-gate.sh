#!/bin/bash
# bypass-armed-gate.sh — BYPASS（prefill_bypass）挂载生效断言（点火后核验门）
#
# 断言语义（对每台参与机）：
#   1) docker logs 内 "DSV41_PREFILL_BYPASS armed: at most <LIMIT> total fresh tokens
#      and <SCAN> candidates" 行计数 ≥1 —— armed 行=sitecustomize 钩已触发+9 个方法源
#      哈希全中+五处补丁锚逐个 count==1+exec 重编译毕，适配生效的唯一直证；
#   2) "refusing to arm" 行计数 =0 —— 拒绝武装=适配未生效（fail-closed 设计）。
# 任一机未过=FAIL（零载荷复核诊断后再处置，勿盲跑载荷）。
#
# 用法（head 机本机执行；worker 机经 ssh BatchMode 免密查）：
#   bash bypass-armed-gate.sh [-l 2048] [-s 32] [-c r3prod-head] [-w r3prod-worker]
#                             [-H "host02 host03 host04"]
# 环境变量等价覆盖：BYPASS_LIMIT / BYPASS_SCAN / HEAD_CONTAINER / WORKER_CONTAINER / WORKER_HOSTS
# 缺省：LIMIT=2048、SCAN=32、head=r3prod-head、worker 容器=r3prod-worker、无 worker 主机
# （单机部署不传 -H 即只查本机；四机 TP4 部署传 -H "其余三台主机名或 IP"）。
set -u

LIMIT="${BYPASS_LIMIT:-2048}"
SCAN="${BYPASS_SCAN:-32}"
HEAD_CTN="${HEAD_CONTAINER:-r3prod-head}"
WORKER_CTN="${WORKER_CONTAINER:-r3prod-worker}"
HOSTS="${WORKER_HOSTS:-}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8"

while getopts "l:s:c:w:H:h" opt; do
  case "$opt" in
    l) LIMIT="$OPTARG" ;;
    s) SCAN="$OPTARG" ;;
    c) HEAD_CTN="$OPTARG" ;;
    w) WORKER_CTN="$OPTARG" ;;
    H) HOSTS="$OPTARG" ;;
    h) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "用法见 -h"; exit 3 ;;
  esac
done
ARMED_PAT="DSV41_PREFILL_BYPASS armed: at most ${LIMIT} total fresh tokens and ${SCAN} candidates"

# report_one 标签 logs命令 —— 打印一机两计数+样本行；两判据全过返回 0
report_one(){
  local label="$1" logscmd="$2" armed refuse
  armed=$(eval "$logscmd" | grep -c "$ARMED_PAT" || true)
  refuse=$(eval "$logscmd" | grep -c 'refusing to arm' || true)
  echo "-- $label --"
  echo "armed(${LIMIT}/${SCAN}) 行计数（期望 ≥1）: ${armed}"
  echo "refusing-to-arm 行计数（期望 0）: ${refuse}"
  eval "$logscmd" | grep 'DSV41_PREFILL_BYPASS' | head -2
  [ "$armed" -ge 1 ] && [ "$refuse" = 0 ]
}

PASS=1
echo "== BYPASS 挂载生效断言 @ $(date -u +%FT%TZ)（head=$HEAD_CTN worker=$WORKER_CTN hosts=[$HOSTS]）=="
report_one "head（本机 $HEAD_CTN）" "docker logs $HEAD_CTN 2>&1" || PASS=0
for h in $HOSTS; do
  report_one "worker $h（$WORKER_CTN）" "$SSH $h 'docker logs $WORKER_CTN 2>&1'" || PASS=0
done

if [ "$PASS" = 1 ]; then
  echo "bypass ARMED 断言 PASS（全部参与机武装生效）"
  exit 0
else
  echo "bypass ARMED 断言 FAIL=停窗条款（零载荷复核诊断：先查 armed/refusing 行上下文与 env 键 DSV41_PREFILL_BYPASS，再查 adapter 面；排查节见本目录 README.md）"
  exit 9
fi
