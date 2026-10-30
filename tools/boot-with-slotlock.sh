#!/bin/bash
# boot-with-slotlock.sh — P0 治理：跨会话靴槽锁 wrapper（非侵入，2026-10-02）
#
# 【为什么存在】主计划 §七 P0：13:35:47Z 主会话验证四机净、13:35:48Z 另一会话点火
#   A22-PREFILL-AUDIT 占槽（秒级竞态实锤；当日第二次占用冲突）。四机=单一靴槽，
#   「验证-然后-点火」两步之间的窗口只能靠锁闭合。本 wrapper 不改动任何既有 boot
#   脚本本体（r3-boot-arm.sh 零 diff），点火命令经它转起即受锁保护。
#
# 【治理声明】**任何会话点火 r3boot 栈都必须走本 wrapper**——包括主会话、分支会话、
#   复跑/续跑会话。绕过 wrapper 直接 bash r3-boot-arm.sh = 违反 P0 治理项，等同
#   在无锁状态下争抢四机靴槽；由此产生的双靴竞争（drop_caches 互踩、容器对撞、
#   UMA 双装载超卖）按事故论处。锁对象=四机整簇（一台 r3boot 容器在=槽被占）。
#
# 【语义】
#   1. exec 9>__REPO_ROOT__/.slot-lock; flock -w 10 9  —— fd9 独占锁（10s 等待窗，
#      拿不到=打印现任持有者并拒起）。锁随本 wrapper 进程存续：被 kill -9 也会因 fd
#      关闭而自动释放（内核语义），无死锁面；残留 lockfile 文本仅作取证。
#   2. 持锁后写 pid+ARM_TAG+时间戳（覆盖式，格式对齐既存 .slot-lock 现场形态）。
#   3. 校验四机容器净：docker ps 过滤 r3boot，非净=拒起（锁随进程退出自动释放，
#      残留文本由下一次成功持锁覆盖）。此校验=门1 的锁下原子重放，闭合
#      「验证-点火」竞态窗（flock 与容器检查在同一进程内串行）。
#   4. 运行传入的 boot 命令（前台子进程，转发退出码）。
#      注：此处刻意不用 exec 替换本进程——退出清锁需要 trap 存活于本进程内；
#      fd9 锁的生命周期=wrapper 生命周期，语义等价且可清理。
#   5. trap EXIT/INT/TERM：清锁（写释放标记+截断 pid 行）。
#
# 【用法】
#   ARM_TAG=A23GATE SPEC=1 ARM_ENV_FILE=__REPO_ROOT__/arms/A23-ALPHA-gate.env \
#     bash tools/boot-with-slotlock.sh bash __ASSETS_ROOT__/bin/r3-boot-arm.sh
#   （env 前缀赋值经 wrapper 原样透传给 boot 命令；SPEC_EXTRA_ARGS 同理。）
#   排障：cat __REPO_ROOT__/.slot-lock 看现任 pid/ARM_TAG/时间戳。
#
# 【红出口】2=锁被占（另一会话持槽）；3=四机容器非净；4=adapter 四机对表红（仅
#   ADAPTER_SYNC_CHECK=1 时存在）；其余=透传 boot 命令退出码。
set -uo pipefail

CAMPAIGN="${CAMPAIGN:-__REPO_ROOT__}"
LOCKFILE="${SL_LOCKFILE:-$CAMPAIGN/.slot-lock}"   # SL_LOCKFILE/SL_HOSTS=mock 注入面（SG2_HOSTS 同款形；缺省=在役值零变化）
HOSTS="${SL_HOSTS:-__PROD_HOST_01__ __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__}"
ARM_TAG="${ARM_TAG:-unknown}"

if [ "$#" -lt 1 ]; then
  echo "用法: ARM_TAG=<tag> bash tools/boot-with-slotlock.sh <boot 命令...>" >&2
  exit 2
fi

# ── 1. fd9 独占锁 ──
# 注：append 模式打开（9>>）——若用截断式（9>），竞争失败方的 open 会在 flock 之前抹掉
# 现任持有者凭据（本地模拟实锤）；append 保证败者零写入，胜者持锁后另行截断重写。
exec 9>>"$LOCKFILE"
if ! flock -w 10 9; then
  echo "[slotlock] RED：靴槽锁被占（另一会话点火中，P0 禁双靴）。现任持有者：" >&2
  cat "$LOCKFILE" >&2 2>/dev/null || echo "(lockfile 空/不可读)" >&2
  exit 2
fi

# ── 2. 持锁凭据（持锁后截断重写——此刻独占，截断安全）──
NOW=$(date -u +%FT%TZ)
printf 'pid=%s\nARM_TAG=%s\nstart=%s\n' "$$" "$ARM_TAG" "$NOW" >"$LOCKFILE"
echo "[slotlock] 持锁 pid=$$ ARM_TAG=$ARM_TAG start=$NOW"

# ── 3. 四机容器净校验（锁下重放门1；红=拒起）──
# 反向判别自检：喂「01 机残留 r3boot-head」形态 → docker ps 过滤行数 1>0 → 拒起 exit 3——
# 红因=槽被占（正确理由）；grep -c 计容器名行而非 docker ps 头行（-a 不用：只认运行态）。
notclean=0
for H in $HOSTS; do
  # ⚠grep -c 语义陷阱（17:53Z T50 首战假拒起，教义第 10 例家族）：零匹配时 grep -c 打印 "0"
  # 且 exit 1 ⇒ 原 `|| echo '?'` 把 n 污染成 "0\n?"（≠0）→ 净机永拒起。修正=裸捕获后数值
  # 校验：非数字（ssh 失败/空输出）→ '?' 走 fail-closed 拒起语义不变；≥1=真占用拒起不变。
  n=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$H" "docker ps --format '{{.Names}}' 2>/dev/null | grep -c r3boot" 2>/dev/null)
  [[ "$n" =~ ^[0-9]+$ ]] || n='?'
  if [ "${n:-0}" != 0 ]; then
    echo "[slotlock] RED：$H 有 r3boot 容器在跑（n=$n）——槽非净，拒起（先拆后点，或与持有者会话协调）" >&2
    notclean=1
  fi
done
if [ "$notclean" = 1 ]; then
  printf 'released=%s(abort:cluster-not-clean)\n' "$(date -u +%FT%TZ)" >&9 2>/dev/null || true
  exit 3
fi
echo "[slotlock] 四机容器净（docker ps 无 r3boot）"

# ── 3.5 可选前置核：adapter 权威源四机对表（ADAPTER_SYNC_CHECK=1 才跑；缺省关=零行为变化）──
#     ENV-GOVERNANCE-20261010 落实件：DEPLOY-SPLIT-OPEN 根因=adapter 各机自挂而部署只落
#     单机。镜像无烘件 ⇒ bind mount 是唯一供给面。本核=点火前红门（fail-closed，exit 4）：
#     四机 __ASSETS_ROOT__/dsv41/adapter 对 01 权威源 md5 对表（排除 __pycache__）。
#     对表红=先跑 tools/adapter-sync.sh --apply（部署窗纪律）再点火。缺省不跑=既有
#     ARM_TAG 流程逐字不变（含 8899 产线复原靴与一切测试臂）。
if [ "${ADAPTER_SYNC_CHECK:-0}" = "1" ]; then
  echo "[slotlock] ADAPTER_SYNC_CHECK=1 → adapter 四机对表前置核"
  if ! bash "$CAMPAIGN/tools/adapter-sync.sh" --check; then
    echo "[slotlock] RED：adapter 四机对表红——拒起（tools/adapter-sync.sh --apply 后再点火）" >&2
    printf 'released=%s(abort:adapter-sync-red)\n' "$(date -u +%FT%TZ)" >&9 2>/dev/null || true
    exit 4
  fi
fi

# ── 4. 退出清锁（trap；boot 命令作为前台子进程，退出码透传）──
cleanup(){
  local rc=$?
  printf 'released=%s(rc=%s)\n' "$(date -u +%FT%TZ)" "$rc" >&9 2>/dev/null || true
  flock -u 9 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[slotlock] 点火：$*"
"$@"
rc=$?
echo "[slotlock] boot 命令退出 rc=$rc（锁释放中）"

# ── 5. 可选后置步：F-9 boot 低速哨兵（BOOT_SENTINEL=1 才跑；缺省关=零行为变化）──
#     b433d01 §4.1 挂点：boot rc=0 且 8898=200（哨兵内含 health 轮询）后自动采测。
#     fail-visible：哨兵横幅+台账（logs/<ARM_TAG>/state/），不 abort 不自动重启；
#     其退出码不透传——本 wrapper 退出码恒=boot 命令 rc（公共工具零行为扰动）。
#     形/参钉面取当前环境：ARM_TAG/ARM_ENV_FILE/SPEC_EXTRA_ARGS（点火前缀赋值即透传至此）。
if [ "${BOOT_SENTINEL:-0}" = "1" ] && [ "$rc" = 0 ]; then
  echo "[slotlock] BOOT_SENTINEL=1 → F-9 哨兵后置步（3 发中位对 per-form 锚判档；fail-visible）"
  bash "$CAMPAIGN/tools/boot_sentinel.sh"
  echo "[slotlock] 哨兵退出 rc=$?（不透传；boot rc=$rc 不变）"
fi

# ── 6. 后置步：misfire-class 相位标签（S-HYG-MICRO-20261018 授权包 3；fail-visible 只落痕零行为改）──
#     S-SETTLE-IMPL §四 P2 实施位：boot 退出时按「停靴相位+容器形态」三类判别落台账，
#     为 settle_gate_v2 P1（--epoch 上次真拆靴起算）提供自动判别面。三类（判据三要素同落痕备查）：
#       clean-teardown = rc=0 → 完整服役正常拆靴（沉降钟自此靴重置=正当）；
#       misfire-config = rc≠0 + load-phase（boot 日志无「R3 栈 UP」=health 未过即停）+ 形态缺参
#                        （CTN_PREFIX 未设→r3boot-* 默认形，S-FIX-W0 R4 形）→ 本靴不算真拆靴：
#                        沉降钟基准不重置——输出面提示 --epoch 上次真拆靴即测即放（授权包 3 明令）；
#       peer-wait-race = rc≠0 其余（带参装载期停/serve 后停=竞态·红带族）→ 照旧走门（1800s 律）。
#     相位证据字串=「R3 栈 UP」（r3-boot-arm.sh health 200 后首打印，boot stdout 必现）；
#     日志定位=BOOT_LOG 显式路径优先，否则按 ARM_TAG 于 $CAMPAIGN/logs/*/boot/ glob 最新；
#     缺日志=phase unknown 如实记，不强行归类。MISFIRE_CLASS=0 关；台账=MISFIRE_CLASS_LEDGER
#     覆盖（缺省 $CAMPAIGN/logs/misfire-class.tsv 追加式）。退出码恒=boot 命令 rc（零行为扰动）。
misfire_class() {
  local rc="$1" phase form cls blog
  if [ "${MISFIRE_CLASS:-1}" != "1" ]; then return 0; fi
  if [ -n "${CTN_PREFIX:-}" ]; then form="param:$CTN_PREFIX"; else form="missing-param(r3boot-default)"; fi
  phase="unknown(无日志)"
  blog="${BOOT_LOG:-}"
  if [ -z "$blog" ] && [ "$ARM_TAG" != "unknown" ]; then
    blog=$(ls -t "$CAMPAIGN"/logs/*/boot/*"$ARM_TAG"*.log 2>/dev/null | head -1)
  fi
  if [ -n "$blog" ] && [ -f "$blog" ]; then
    if grep -q 'R3 栈 UP' "$blog" 2>/dev/null; then phase="post-health"; else phase="load-phase"; fi
  fi
  if [ "$rc" = 0 ]; then cls="clean-teardown"
  elif [ "$phase" = "load-phase" ] && [ -z "${CTN_PREFIX:-}" ]; then cls="misfire-config"
  elif [ "$phase" = "unknown(无日志)" ]; then cls="unknown"
  else cls="peer-wait-race"; fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$ARM_TAG" "$rc" "$phase" "$form" "$cls" \
    >>"${MISFIRE_CLASS_LEDGER:-$CAMPAIGN/logs/misfire-class.tsv}"
  echo "[slotlock] misfire-class=$cls（rc=$rc phase=$phase form=$form；台账=${MISFIRE_CLASS_LEDGER:-$CAMPAIGN/logs/misfire-class.tsv}）"
  if [ "$cls" = "misfire-config" ]; then
    echo "[slotlock] HINT：misfire-config 型不重置沉降钟基准——settle_gate_v2 --epoch <上次真拆靴epoch> 即测即放（S-SETTLE P1 法），勿再盲等 1800s（032 授权包 3）"
  fi
}
misfire_class "$rc"
exit "$rc"
