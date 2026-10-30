#!/bin/bash
# R3 窗口（持续迁移模式）：守卫→r3-boot→测量→【栈保持在线，不复产】
set -u
TS=$(date -u +%H%M)
LOG=~/migrate-assets/logs/r3-window-$TS.log
mkdir -p ~/migrate-assets/logs "${LOG%/*}"
E=~/V41-0.2.8-HANDOVER-20260923/window-20260929-r3
mkdir -p "$E"
say() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }
# ── 20261030 脱敏：节点主机名改经环境变量注入，缺参拒跑 ──
NODE01_HOST="${NODE01_HOST:?缺环境变量 NODE01_HOST（<node01>），拒跑}"
NODE02_HOST="${NODE02_HOST:?缺环境变量 NODE02_HOST（<node02>），拒跑}"
NODE03_HOST="${NODE03_HOST:?缺环境变量 NODE03_HOST（<node03>），拒跑}"
NODE04_HOST="${NODE04_HOST:?缺环境变量 NODE04_HOST（<node04>），拒跑}"
say "===== R3 窗口：main+adapter pread engram（$TS）====="

# 生产保持 disabled+stopped（持续模式）；确认一把
for h in "${NODE01_HOST}" "${NODE02_HOST}" "${NODE04_HOST}" "${NODE03_HOST}"; do
  if [ "$h" = "${NODE01_HOST}" ]; then a=$(systemctl --user is-active dsv41-serve.service 2>/dev/null)
  else a=$(ssh -o BatchMode=yes $h "systemctl --user is-active dsv41-serve.service" 2>/dev/null); fi
  [ "$a" = "inactive" ] || { say "★ $h serve 非 inactive（$a）——先停"; [ "$h" = "${NODE01_HOST}" ] && systemctl --user stop dsv41-serve.service || ssh -o BatchMode=yes $h "systemctl --user stop dsv41-serve.service"; }
done
say "生产四机 inactive 确认"

bash ~/migrate-assets/bin/r3-boot.sh >>"$LOG" 2>&1 &
BOOTPID=$!
# 池门（doc94 §G）：起栈期盯 pool 行+水位；红即早拆（在击穿前止损）
say "池门盯梢启动（pin=9600000；红即拆）"
while kill -0 $BOOTPID 2>/dev/null; do
  sleep 10
  avail=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo)
  if [ "${avail:-99999}" -lt 4096 ]; then
    say "★池门红：MemAvailable=${avail}M<4096M —— 早拆止损"
    docker logs r3boot-head >"$E/boot-fail-poolgate.log" 2>&1 || true
    kill $BOOTPID 2>/dev/null; docker rm -f r3boot-head >/dev/null 2>&1
    for h in "${NODE02_HOST}" "${NODE04_HOST}" "${NODE03_HOST}"; do ssh -o BatchMode=yes $h "docker logs r3boot-worker > /tmp/r3-poolgate-$h.log 2>&1; docker rm -f r3boot-worker" >/dev/null 2>&1; done
    say "池门止损完成（日志已落 $E/boot-fail-poolgate.log + worker /tmp/r3-poolgate-*.log）"
    break
  fi
done
wait $BOOTPID 2>/dev/null
brc=$?
say "r3-boot rc=$brc"

if [ $brc -eq 0 ] && curl -fsS -m 3 http://127.0.0.1:8899/health >/dev/null 2>&1; then
  say "健康。陷阱㉟：等 90s 稳定+水位门（4G 口径）..."
  sleep 90
  avail=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo)
  say "head MemAvailable=${avail}M"
  if [ "$avail" -lt 4096 ]; then say "★水位红 ${avail}M——跳过测量保栈"; else
    curl -s -m 60 http://127.0.0.1:8899/v1/chat/completions -H 'Content-Type: application/json' \
      -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"用一句话说明什么是环网。"}],"max_tokens":60}' \
      | python3 -c "import json,sys;d=json.load(sys.stdin);print('chat sanity:',d['choices'][0]['message']['content'][:120])" 2>/dev/null | tee -a "$LOG" >"$E/chat-sanity.txt"
    sleep 20
    curl -s -m 10 http://127.0.0.1:8899/get_server_info >"$E/server-info.json" 2>/dev/null && say "server_info 已存"
    # engram pread 健康统计（adapter DSV41_STATS_SECONDS=60 周期日志）
    say "engram 统计（最近）："; docker logs r3boot-head 2>&1 | grep -iE 'engram|hit|miss' | tail -6 | tee -a "$LOG"
    timeout 900 python3 -B ~/<source-repo>/bench/sd_bench.py --mode de --type prose --concurrency 1 \
      --label r3-c1 --base http://127.0.0.1:8899/v1 --key dummy \
      --json-out "$E/de-c1.json" >"$E/de-c1.txt" 2>&1
    say "de-c1 rc=$? $(python3 -c "import json;d=json.load(open('$E/de-c1.json'));print(d['de'][0]['per'])" 2>/dev/null)"
  fi
  say "== R3 栈保持在线（容器 r3boot-head/workers）。生产保持停位。=="
  say "R3 窗口完成（栈在线）"
  exit 0
fi

say "R3 未起——保现场于 $E/boot-fail.log"
{ docker logs --tail 80 r3boot-head 2>&1; for h in "${NODE02_HOST}" "${NODE04_HOST}" "${NODE03_HOST}"; do echo "== $h"; ssh -o BatchMode=yes $h "docker logs --tail 40 r3boot-worker" 2>&1; done; } >"$E/boot-fail.log" 2>&1
say "boot-fail 关键行："; grep -nE 'Error|assert|Assert|raise|Traceback|drift|refus' "$E/boot-fail.log" | tail -10 | tee -a "$LOG"
docker rm -f r3boot-head >/dev/null 2>&1
for h in "${NODE02_HOST}" "${NODE04_HOST}" "${NODE03_HOST}"; do ssh -o BatchMode=yes $h "docker rm -f r3boot-worker" >/dev/null 2>&1; done
say "容器已拆（生产保持停位，持续模式）。R3 窗口完成（失败收场）"
exit 1
