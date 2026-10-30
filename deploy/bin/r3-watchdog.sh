#!/usr/bin/env bash
# r3-watchdog.hardened.workcopy.sh — H-TTL 加固工作副本（2026-10-04）
# ⚠ WORKCOPY（零部署）：基线=/home/liux***ya/migrate-assets/bin/r3-watchdog.sh（在役，只读未动）；
#   四机分发=INC-20261004-DRIFT 收口后由主会话另派（guardctl+md5 单）。
# 裁定：docs/governance/OOMGATE-HARDENING-PROPOSAL-20261004.md H-TTL（六件之一）。
# 根因：docs/verdicts/OOM-INCIDENT-DEEPDIVE-20261004.md §1.4——hold 契约「≤25min」被饥荒吹成
#   2h28m（05:06:26 touch→07:34:36 rm），health 盲窗被无限延长。
#
# 改动面（唯一=head 哨 hold 消费处；其余逐行同源，零改动）：
#   H-TTL：hold 文件 mtime>25min ⇒ 忽略（hold_active=0）+CRIT 日志。
#     - stat 读龄失败 ⇒ fail-loud：CRIT+按超龄忽略。基线形 `stat … || date +%s` 会把读龄失败
#       静默折算成"年龄=0"=hold 永真（静默错值，教义 #12）——这正是盲窗可被无限延长的守卫侧机制。
#     - 契约不动：hold 语义（≤25min 量具窗）与 touch/rm 生命周期归 census 工具——本件对超龄
#       hold 只「忽略」不「rm」（基线形 rm=代管他件契约文件；忽略即达成 TTL 语义，且重复 CRIT
#       持续可见）。水位红线/health 计数/teardown/worker 分支判据零改。
#   事实登记（报告已载）：01 本机在役副本（mtime 2026-09-30 16:48）已含 rm 形 TTL 块，与
#   DEEPDIVE §1.4「watchdog 侧无 hold 文件 TTL 检查」表述相左（四机实际在役版本以部署时
#   md5 读数为准——部署单含此核验步）；本 workcopy 相对两种在役可能形均成立。
#
# 用法：与基线一致（r3-watchdog.sh head | worker）；电池以 source 方式调 hold_check()。
set -u

ROLE="${1:-}"
INTERVAL=15
FAIL_N=4            # 4×15s=60s health 失败即拆（事故实测跌穿快于 30s 粒度）
BOOT_GRACE=$((15 * 60))     # 靴窗宽限：容器启动后 15 分钟内不要求 health
# 点3（2026-09-30）水位线对齐 0.2.8/0.2.9 实战口径（w6-kit oom_gate：
# `-w 6 -f 1.5 -n 3 --iv 2 -a -e 1`）。主守卫=系统级 oom-gate-monitor（2s
# 采样、止损前带现场快照、PAT 已扩 r3boot-*）；本哨水位=纯兜底位：红线取
# 同值 1.5G 但 3 连确认 @15s（45s ≫ oom_gate 的 6s）——保证实战件先出手、
# 现场取证不丢；本哨只在 oom_gate 失效（服务死/被卸）时兜底拆除。
WATER_M=1500                # 水位红线（MemAvailable MB；= oom_gate -f 1.5）
WATER_WARN_M=6000           # 预警线（= oom_gate -w 6）
WATER_N=3                   # 红线连续确认次数（= oom_gate -n 3；兜底慢环）
# ── 20261030 脱敏：内网值改经环境变量注入，缺参拒跑 ──
HEAD_IP="${HEAD_IP:?缺环境变量 HEAD_IP（head 节点 <mgmt-node-ip>），拒跑}"   # net-rebuild-20261015 镜像同步（旧址已脱敏）
NODE01_HOST="${NODE01_HOST:?缺环境变量 NODE01_HOST（<node01>），拒跑}"
NODE02_HOST="${NODE02_HOST:?缺环境变量 NODE02_HOST（<node02>），拒跑}"
NODE03_HOST="${NODE03_HOST:?缺环境变量 NODE03_HOST（<node03>），拒跑}"
NODE04_HOST="${NODE04_HOST:?缺环境变量 NODE04_HOST（<node04>），拒跑}"
API_PORT=8898
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8)
WORKERS=("${NODE02_HOST}" "${NODE04_HOST}" "${NODE03_HOST}")
INCIDENT_DIR="$HOME/l10-incident"
HOLD_F="/tmp/r3-watchdog-hold"       # 量具 hold：census/kineto 采样窗内暂停 health 计数
HOLD_MAX_S=$((25 * 60))              # hold 契约窗（≤25min；H-TTL 据此忽略超龄）

log()  { printf '[%s] [r3wd-%s] %s\n' "$(date -Is)" "${ROLE:-head}" "$*"; }

teardown() {  # teardown <原因>
  local why="$1" ts; ts=$(date +%Y%m%d-%H%M%S)
  local out="$INCIDENT_DIR/watchdog-${ROLE}-${ts}.log"
  mkdir -p "$INCIDENT_DIR"
  { log "TEARDOWN 触发：$why"
    echo "--- 证据 ---"
    awk '/MemAvailable/{printf "MemAvailable=%dM\n", $2/1024}' /proc/meminfo
    docker ps -a --format '{{.Names}} {{.Status}}' 2>/dev/null | grep r3boot || echo "(local no r3boot)"
    docker inspect -f '{{.Name}} state={{.State.Status}} started={{.State.StartedAt}}' r3boot-head 2>/dev/null
  } > "$out" 2>&1
  log "TEARDOWN 执行（证据落 $out）"
  docker rm -f r3boot-head >/dev/null 2>&1
  for h in "${WORKERS[@]}"; do ssh "${SSH_OPTS[@]}" "$h" "docker rm -f r3boot-worker" >/dev/null 2>&1; done
  log "TEARDOWN 完成（四机）"
}

memavail() { awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo; }
ctn_state() { docker inspect -f '{{.State.Status}}' "$1" 2>/dev/null | tr -d '\r'; }
ctn_age_s() {
  local st; st=$(docker inspect -f '{{.State.StartedAt}}' "$1" 2>/dev/null | tr -d '\r')
  [[ -n "$st" ]] && echo $(( $(date +%s) - $(date -d "$st" +%s) )) || echo 0
}

# ══ H-TTL（2026-10-04 六件加固之一）════════════════════════════════════════════
# hold_check：检 hold 文件龄——≤25min ⇒ HOLD_ACTIVE=1（量具窗，health 计数暂停）；
#             >25min ⇒ 忽略+CRIT（每轮都报=盲窗状态持续可见）；mtime 不可读 ⇒ fail-loud
#             同超龄处理（禁静默折算年龄=0）。不 rm 文件（生命周期归 census 工具）。
# 输出变量：HOLD_ACTIVE（0/1）、HOLD_STALE（0/1——超龄或不可读）。
hold_check() {
  HOLD_ACTIVE=0
  HOLD_STALE=0
  [[ -f "$HOLD_F" ]] || return 0
  local mt="" now="" age=""
  now=${EPOCHSECONDS:-}
  if [[ -z "$now" ]]; then now=$(date +%s); fi
  mt=$(stat -c %Y "$HOLD_F" 2>/dev/null)
  if [[ -z "$mt" || ! "$mt" =~ ^[0-9]+$ ]]; then
    HOLD_STALE=1
    log "CRIT hold 文件存在但 mtime 不可读（stat 失败）——按超龄忽略，恢复 health 计数（H-TTL fail-loud；基线形此处会静默折算年龄=0）"
    return 0
  fi
  age=$(( now - mt ))
  if (( age > HOLD_MAX_S )); then
    HOLD_STALE=1
    log "CRIT hold 文件超龄 ${age}s > ${HOLD_MAX_S}s——忽略（health 计数恢复；文件保留，生命周期归 census 工具）（H-TTL）"
    return 0
  fi
  HOLD_ACTIVE=1
}

main() {
  log "启动（interval=${INTERVAL}s fail_n=${FAIL_N} grace=${BOOT_GRACE}s water=${WATER_M}M hold_ttl=${HOLD_MAX_S}s）"
  fail=0
  wfail=0
  while true; do
    if [[ "$ROLE" == "head" ]]; then
      if [[ "$(ctn_state r3boot-head)" == "running" ]]; then
        m=$(memavail)
        if (( m < WATER_M )); then
          (( wfail += 1 ))
          log "红线 MemAvailable=${m}M < ${WATER_M}M（${wfail}/${WATER_N} 连；主守卫=oom_gate@2s）"
          if (( wfail >= WATER_N )); then
            teardown "head 水位红线 ${WATER_N}×${INTERVAL}s 确认 MemAvailable=${m}M（oom_gate 兜底位）"
          fi
        else
          wfail=0
        fi
        if (( m < WATER_WARN_M )); then
          log "WARN head 水位 ${m}M < ${WATER_WARN_M}M（盯跌速；红线 ${WATER_M}M）"
        fi
        hold_check                       # ★H-TTL：唯一改动点（原内联块抽出为函数）
        if (( $(ctn_age_s r3boot-head) > BOOT_GRACE )); then
          if curl -fsS --max-time 5 "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
            fail=0
          elif (( HOLD_ACTIVE )); then
            (( fail += 1 ))
            log "health 失败 ${fail}/${FAIL_N} 但 hold 活跃（量具采样窗）——不计入楔死判据"
            fail=0
          else
            (( fail += 1 ))
            log "health 失败 ${fail}/${FAIL_N}（MemAvail=${m}M）"
            if (( fail >= FAIL_N )); then
              teardown "head health 连续 ${FAIL_N}×${INTERVAL}s 失败（UMA 楔死形态）"
              fail=0
            fi
          fi
        fi
      else
        fail=0; wfail=0   # 无栈/靴窗：静默
      fi

    elif [[ "$ROLE" == "worker" ]]; then
      if [[ "$(ctn_state r3boot-worker)" == "running" ]]; then
        m=$(memavail)
        if (( m < WATER_M )); then
          (( wfail += 1 ))
          log "红线 MemAvailable=${m}M < ${WATER_M}M（${wfail}/${WATER_N} 连；主守卫=oom_gate@2s）"
          if (( wfail >= WATER_N )); then
            teardown "worker(02) 水位红线 ${WATER_N}×${INTERVAL}s 确认 MemAvailable=${m}M（oom_gate 兜底位）"
          fi
        else
          wfail=0
        fi
        if (( m < WATER_WARN_M )); then
          log "WARN worker 水位 ${m}M < ${WATER_WARN_M}M（盯跌速；红线 ${WATER_M}M）"
        fi
        if curl -fsS --max-time 5 "http://${HEAD_IP}:${API_PORT}/health" >/dev/null 2>&1; then
          fail=0
        else
          (( fail += 1 ))
          log "head health 探测失败 ${fail}/${FAIL_N}（MemAvail=${m}M）"
          if (( fail >= FAIL_N )); then
            # 确认 head 真亡：ssh 不通 或 head 容器非 running；若 head 仍活则留给 head 哨
            if ! ssh "${SSH_OPTS[@]}" "${NODE01_HOST}" "true" 2>/dev/null \
               || [[ "$(ssh "${SSH_OPTS[@]}" "${NODE01_HOST}" "docker inspect -f '{{.State.Status}}' r3boot-head 2>/dev/null" | tr -d '\r')" != "running" ]]; then
              teardown "head 亡故确认（health×${FAIL_N} 失败且 ssh/容器死）——workers 联动拆除"
            else
              log "head health 失败但 head 容器+ssh 存活——交给 head 哨处理，本哨复位"
            fi
            fail=0
          fi
        fi
      else
        fail=0; wfail=0
      fi
    fi
    sleep $INTERVAL
  done
}

# 直接执行才跑主循环（source 形=电池只取 hold_check）
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  ROLE="${1:?usage: r3-watchdog.hardened.workcopy.sh head|worker}"
  main "$@"
fi
