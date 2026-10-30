#!/usr/bin/env bash
# gate_check_unittest.sh — G-1 gate_check.sh 单元测试（W7-GUARD，2026-10-25）
#
# 测试法：纯注入值（临时 meminfo 文件 + 假 docker 可执行），不做真机降压、不碰真容器。
# 覆盖：pre 门全分支+边界（100/100.1/99.9GiB、非法源）；watch 阈值边界（6/5.9GiB 恰线与破线、
#       判据式非零 Shmem 项）；watch 端到端（dry-run 破线 rc=3、容器消失 rc=0、stop 真调 fake docker、
#       超时 rc=4、非法 -m rc=2）。
# 阈值不可注入（D49 零新参数）——边界由注入的 MemAvailable/有效空闲值构造。
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GATE="$HERE/gate_check.sh"
TMP=$(mktemp -d /tmp/gate-check-ut.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); echo "  ok   $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  FAIL $1"; }

check_rc() {  # $1=期望rc $2=实得rc $3=用例名
  if [ "$1" = "$2" ]; then ok "$3 (rc=$2)"; else bad "$3 期望rc=$1 实得rc=$2"; fi
}

mk_meminfo() {  # $1=MemAvailableKiB $2=MemFreeKiB $3=CachedKiB $4=SReclaimableKiB $5=ShmemKiB
  printf 'MemTotal:       132120000 kB\nMemFree:        %s kB\nMemAvailable:   %s kB\nBuffers:        1000 kB\nCached:         %s kB\nSwapCached:     0 kB\nSReclaimable:   %s kB\nShmem:          %s kB\n' \
    "$2" "$1" "$3" "$4" "$5"
}

echo "== UT-1 pre 门分支+边界（注入 MemAvailable） =="
# 100.0GiB=104857600KiB 恰线 → 应过（>=100GiB）
mk_meminfo 104857600 104857600 0 0 0 > "$TMP/m_exact"
GATE_MEMINFO_FILE="$TMP/m_exact" bash "$GATE" pre >/dev/null 2>&1; check_rc 0 $? "pre 边界恰 100.0GiB → 放行"
# 100.1GiB=104962457KiB → 过
mk_meminfo 104962457 104962457 0 0 0 > "$TMP/m_above"
GATE_MEMINFO_FILE="$TMP/m_above" bash "$GATE" pre >/dev/null 2>&1; check_rc 0 $? "pre 100.1GiB → 放行"
# 99.9GiB=104752742KiB → 拒
mk_meminfo 104752742 104752742 0 0 0 > "$TMP/m_below"
GATE_MEMINFO_FILE="$TMP/m_below" bash "$GATE" pre >/dev/null 2>&1; check_rc 1 $? "pre 边界 99.9GiB → 拒载"
# 极低值 2.9GiB（T4a 事件时刻形态）→ 拒
mk_meminfo 3040851 3040851 0 0 0 > "$TMP/m_crash"
GATE_MEMINFO_FILE="$TMP/m_crash" bash "$GATE" pre >/dev/null 2>&1; check_rc 1 $? "pre 2.9GiB（T4a 崩塌后形态）→ 拒载"
# 非法源（缺 MemAvailable 行）→ 拒（保守）
printf 'MemTotal: 100 kB\n' > "$TMP/m_bad"
GATE_MEMINFO_FILE="$TMP/m_bad" bash "$GATE" pre >/dev/null 2>&1; check_rc 1 $? "pre 非法源（无 MemAvailable）→ 拒"
# 无参数 → rc=2
bash "$GATE" >/dev/null 2>&1; check_rc 2 $? "无参数 → usage rc=2"

echo "== UT-2 watch 阈值判定（注入有效空闲，判据式 MemFree+Cached+SReclaimable-Shmem） =="
# 有效空闲恰 6GiB=6291456KiB（MemFree 单列）→ 不破线
mk_meminfo 104857600 6291456 0 0 0 > "$TMP/w_exact6"
# 有效空闲 5.9GiB=6186598KiB → 破线
mk_meminfo 104857600 6186598 0 0 0 > "$TMP/w_59"
# 判据式非零项：MemFree=5GiB + Cached=2GiB + SReclaimable=1GiB − Shmem=1GiB = 7GiB → 不破线
mk_meminfo 104857600 5242880 2097152 1048576 1048576 > "$TMP/w_formula7"
# 判据式非零项凑 5.9GiB：MemFree=5GiB + Cached=2GiB − Shmem=1.1GiB → 5.9GiB → 破线
mk_meminfo 104857600 5242880 2097152 0 1153434 > "$TMP/w_formula59"

# 假 docker：alive 形（inspect 成功）/ gone 形（inspect 失败）/ stop 记录形
mk_fake_docker() {  # $1=alive|gone  $2=stop 记录文件
  cat > "$TMP/docker_$1" <<EOF
#!/bin/bash
if [ "\$1" = inspect ]; then [ "$1" = alive ] && exit 0 || exit 1; fi
if [ "\$1" = stop ]; then echo "stop:\$*" >> "$2"; exit 0; fi
exit 0
EOF
  chmod +x "$TMP/docker_$1"
}
mk_fake_docker alive "$TMP/stop_calls"

echo "== UT-3 watch 端到端（fake docker + 注入 meminfo） =="
# 3a dry-run 破线 → rc=3 且不调 stop
: > "$TMP/stop_calls"
GATE_MEMINFO_FILE="$TMP/w_59" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -c ut-container -m dry-run > "$TMP/out3a" 2>&1
check_rc 3 $? "watch dry-run 破线（5.9GiB）→ rc=3"
[ ! -s "$TMP/stop_calls" ] && ok "watch dry-run 未真实调用 docker stop" || bad "watch dry-run 不应调 stop（实得 $(cat "$TMP/stop_calls")）"
grep -q "DRY-RUN" "$TMP/out3a" && ok "watch dry-run 输出含 DRY-RUN 标记" || bad "watch dry-run 缺 DRY-RUN 标记"

# 3b stop 真调 fake docker stop
GATE_MEMINFO_FILE="$TMP/w_59" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -c ut-container -m stop >/dev/null 2>&1
check_rc 3 $? "watch stop 破线 → rc=3"
grep -q "ut-container" "$TMP/stop_calls" && ok "watch stop 已调 docker stop ut-container" || bad "watch stop 未调 stop"

# 3c 恰线 6GiB + 容器在 → 不破线；--max-wait=1 走超时 rc=4
GATE_MEMINFO_FILE="$TMP/w_exact6" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -c ut-container -m dry-run -i 1 --max-wait 1 > "$TMP/out3c" 2>&1
check_rc 4 $? "watch 恰线 6GiB 不破线、容器在 → 超时 rc=4（非破线 3）"
grep -q "BREACH" "$TMP/out3c" && bad "恰线 6GiB 不应 BREACH" || ok "恰线 6GiB 无 BREACH（<6 才触发，边界不触发）"

# 3d 判据式 7GiB（非零 Cached/SReclaimable/Shmem）→ 不破线，容器在超时 rc=4
GATE_MEMINFO_FILE="$TMP/w_formula7" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -c ut-container -m dry-run -i 1 --max-wait 1 >/dev/null 2>&1
check_rc 4 $? "watch 判据式 7GiB（含非零 Shmem 项）→ 不破线（超时 rc=4）"

# 3e 判据式凑 5.9GiB（Shmem 大于 SReclaimable）→ 破线 rc=3
GATE_MEMINFO_FILE="$TMP/w_formula59" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -c ut-container -m dry-run >/dev/null 2>&1
check_rc 3 $? "watch 判据式 5.9GiB（Shmem 抵扣后）→ 破线 rc=3"

# 3f 容器已消失 + 未破线 → rc=0 正常收尾
mk_fake_docker gone "$TMP/stop_calls2"
GATE_MEMINFO_FILE="$TMP/w_exact6" GATE_DOCKER_BIN="$TMP/docker_gone" \
  bash "$GATE" watch -c ut-container -m dry-run > "$TMP/out3f" 2>&1
check_rc 0 $? "watch 容器消失（--rm 毕清）→ rc=0 收尾"
grep -q "WATCH END" "$TMP/out3f" && ok "watch 收尾行 WATCH END 在档" || bad "watch 缺 WATCH END 行"

# 3g 非法 -m → rc=2
GATE_MEMINFO_FILE="$TMP/w_59" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -c ut-container -m nuke >/dev/null 2>&1
check_rc 2 $? "watch -m 非法值 → rc=2"
GATE_MEMINFO_FILE="$TMP/w_59" GATE_DOCKER_BIN="$TMP/docker_alive" \
  bash "$GATE" watch -m dry-run >/dev/null 2>&1
check_rc 2 $? "watch 缺 -c → rc=2"

echo
echo "== 单测汇总: PASS=$PASS FAIL=$FAIL（临时目录 $TMP 已清理） =="
[ "$FAIL" -eq 0 ]
