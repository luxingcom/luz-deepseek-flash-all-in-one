#!/bin/bash
# deploy-034.sh — 0.3.4 一键部署编排器（纯编排既有原件，零新引擎逻辑；D115 工具复用律）
#
# 用途：把 0.3.4 固化生产态（D118-③）从停机设计态一键带到引擎在役态，全链自反馈。
# 级序（每级失败即停，打印对应提示行）：
#   S1 doctor --preflight     只读体检（四机连通/r3ctn=0/slotlock/盘空间/镜像在机/配置面 md5 全对/
#                              engram-权重身份一致性〔EQ-05：CFG-68..72=权重三件+mtime 判序+bin 尺寸，
#                              新权重配旧 engram 混态=FAIL 即停拒起〕；引擎在役=拒起门红即停 P0 禁双靴；
#                              preflight 状态感知=在役态设计行 N/A）
#   S2 boot :12 翻 x6bake     参数化单行翻转（.bak+写前/写后 md5 双核+bash -n；目标=profile :20）
#   S3 slotlock→r3-boot-arm   点火（MV-12 ignite-034fix.sh 制式逐字承；SPEC6=profile :10）
#   S4 health 轮询            120min 死线（720×10s，正典件同参）
#   S5 settle 300s            D113-① 新制（health 200 后 300s+正典核对面绿即起；1800s 旧制已废止）
#   S6 capture-boot-evidence  D110 正典件（横幅 8/池指纹/镜像身份/overlay 活体 md5）
#                            + BYPASS ARMED 硬门（[12] 段 armed 合计=8·refusing=0；D121 五步固化③）
#   S7 doctor --post-boot     引擎面自排查（kv_fp4 v41/池指纹/横幅 8/health）
#   S8 网关第五查            EQ-09（四查后追加第五查）：主链三断言 fail-closed——网关 /health=200+
#                            UPSTREAM 车道指向引擎生产口+网关 /v1/models 清单正典（引擎健康≠主链健康：
#                            网关不在点火脚本/槽锁/启动链，仅引擎 health 全绿≠完整主链）；任一红=级失败即停。
#                            本级只读断言零容器/服务生命周期动作（网关启动/重启=网关变更窗职权非本编排器；
#                            纳入 boot-with-slotlock 编排=点火链面另批）
#   S9 汇总报告               logs/S-034-DEPLOY-<ts>/DEPLOY-SUMMARY.md + misfire 台账点火行代录
# 用法：bash tools/deploy-034.sh [--dry-run] [--arm-tag TAG]
#   --dry-run  全程打印不执行：只读级（S1）照跑，动作级（S2-S9）逐条打印将执行的命令
#   --arm-tag  自定义 ARM_TAG（缺省 DEPLOY-034-<UTC 时戳>）
#   第五查旋钮（S8；EQ-09）：GW_URL（默认 http://127.0.0.1:8001）/GW_UPSTREAM_EXPECT（默认
#   http://127.0.0.1:8899——8898=测试线死端口勿指）/GW_UNIT（默认 concurrency-proxy-v2）/GW_KEY
#   （GW_REQUIRE_AUTH=1 在役形 /v1/* 须 Bearer；值经 env 传递零入档）
# 退出码：0=全链绿；1=任一级 FAIL（已停）；2=用法错/前置数据源缺失。
# 拆栈（窗毕/失败止损）：CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash __ASSETS_ROOT__/bin/r3-stop.sh
#   （D8 三查：四机 r3ctn=0+8899=000+8898=000；拆毕把台账第二行落 misfire-class.tsv）
# 红线随身：执行代理零 sudo（启停链内建 drop_caches 既有制式如实记账除外）；判读窗禁切
#   （GW_SAMPLING_POLICY/K16 两键不触）；偏差=停窗如实呈报不即兴。
# 法源：用户 2026-10-28 批文（部署一键化）+ D119-② + D118-③ + D113（静置新制）+ D110（正典件）。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAMP="$(cd "$HERE/.." && pwd)"
PROFILE="__ASSETS_ROOT__/prod/prod-profile.env"
BOOT="__ASSETS_ROOT__/bin/r3-boot-arm.sh"
ENVC="__ASSETS_ROOT__/dsv41/env/CBX1A-CERTM-spec1.env"
MISFIRE="$CAMP/logs/misfire-class.tsv"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8"
DRY=0; ARM_TAG=""
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1;;
    --arm-tag) :;;           # 值经下一循环取
    *) [ "${PREV:-}" = "--arm-tag" ] && ARM_TAG="$a";;
  esac; PREV="$a"
done
[ -z "$ARM_TAG" ] && ARM_TAG="DEPLOY-034-$(date -u +%Y%m%d-%H%M%S)"

[ -f "$PROFILE" ] || { echo "[deploy] 缺 $PROFILE"; exit 2; }
[ -f "$BOOT" ]    || { echo "[deploy] 缺 $BOOT"; exit 2; }
source "$PROFILE"    # 单一事实源：PROD_IMAGE / PROD_BOOT_SCRIPT_MD5 / PROD_SPEC_EXTRA_ARGS / …
MD5_STORE="50700486996405514a3f2f07b11feb48"                              # D118-③ 存储态
MD5_IGNITE="d41323ddac5743b54c00ad2ec3097d13"                             # :12 翻 x6bake 合法态（gates-034 BL09 注记）
TAG_FROM="0.3.2-r032c"; TAG_TO="${PROD_IMAGE##*:}"
BAK="$BOOT.bak-pre-deploy034-$(date -u +%Y%m%dT%H%MZ)"
STAGE_N=0
stage(){ STAGE_N=$((STAGE_N+1)); echo; echo "===== [S$STAGE_N] $1 @ $(date -u +%FT%TZ) ====="; }
die1(){ echo "[deploy] 级 S$STAGE_N FAIL=即停 @ $(date -u +%FT%TZ)"; echo "[deploy] ↳ 自反馈: $1"; exit 1; }
run(){ if [ "$DRY" = 1 ]; then echo "[dry-run] 将执行: $*"; else "$@"; fi; }

# ── S1 只读体检 ──
stage "doctor --preflight（只读体检）"
# 在役拒起门（P0 禁双靴；doctor 状态感知化〔在役态设计行 N/A〕后，「栈净」硬前置由本门显式承载=零降门）
n01=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -cE '^r3(prod|boot)-' || true)
hc=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true); hc=${hc:-000}
echo "[deploy] EQ-05 前置：engram-权重身份一致性断言随 preflight 执法（CFG-68..72=权重三件+mtime 判序+bin 尺寸；混配=FAIL 即停拒起——须重生成 engram 或跑质量锚定性后再部署）"
if [ "$DRY" = 1 ]; then
  if [ "$n01" != 0 ] || [ "$hc" = 200 ]; then
    echo "[dry-run] 在役拒起门=红（r3ctn01=$n01 health=$hc）——实跑将在此停止（P0 禁双靴：先拆栈再部署）；演练继续走完全链打印"
  fi
  echo "[dry-run] 将执行（只读级照跑）: bash $HERE/doctor-034.sh --preflight"
  if bash "$HERE/doctor-034.sh" --preflight; then :; else
    echo "[dry-run] ⚠ preflight 存在 FAIL——实跑将在此停止（S2 起不执行）；演练继续走完全链打印"
  fi
else
  if [ "$n01" != 0 ] || [ "$hc" = 200 ]; then die1 "引擎在役（r3ctn01=$n01 health=$hc）——P0 禁双靴拒起；先拆栈: CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash __ASSETS_ROOT__/bin/r3-stop.sh（D8 三查）+台账第二行落 $MISFIRE，再重新部署"; fi
  bash "$HERE/doctor-034.sh" --preflight || die1 "preflight 存在 FAIL——逐行修复（每行已带失败提示）后再点火"
fi

# ── S2 boot :12 翻 x6bake（env/tp4/guards/overlay/adapter 已固化=preflight 全对，唯 boot 一面）──
stage "boot :12 翻 x6bake（$TAG_FROM → $TAG_TO）"
m(){ md5sum "$BOOT" | awk '{print $1}'; }
cur=$(m)
if [ "$cur" = "$MD5_IGNITE" ]; then
  echo "[deploy] boot 已处点火窗合法态（$(echo $cur | cut -c1-8)）——幂等跳过翻转"
elif [ "$cur" != "$MD5_STORE" ]; then
  die1 "boot 写前 md5=$cur 非 $MD5_STORE（存储态）非 $MD5_IGNITE（窗内态）=漂移，停窗呈报勿翻转"
else
  run cp -p "$BOOT" "$BAK"
  run sed -i "s|^IMAGE=\"__REGISTRY_HOST__:__REGISTRY_PORT__/dsv41-sglang-optimized:$TAG_FROM\"|IMAGE=\"$PROD_IMAGE\"|" "$BOOT"
  run bash -n "$BOOT"
  if [ "$DRY" = 0 ]; then
    [ "$(m)" = "$MD5_IGNITE" ] || die1 "翻转后 md5=$(m) ≠ $MD5_IGNITE——回置: cp -p $BAK $BOOT（写前锚已 .bak 留证）"
    echo "[deploy] boot=$MD5_IGNITE OK（:12=$(sed -n 12p "$BOOT" | sed 's/.*optimized://;s/"//') ; 回置=sed :12 复 $TAG_FROM 或回拷 $BAK）"
  fi
fi

# ── S3 点火（slotlock → r3-boot-arm.sh；MV-12 制式）──
stage "slotlock → r3-boot-arm.sh 点火（ARM_TAG=$ARM_TAG）"
TS=$(date -u +%Y%m%d-%H%M%S)
W="$CAMP/logs/S-034-DEPLOY-$TS"; run mkdir -p "$W"
run bash -c "cd $CAMP && env SGLANG_OVERLAY_DIR=__ASSETS_ROOT__/v4vl/sglang-overlay.o12c1-prod \
    ARM_TAG='$ARM_TAG' CTN_PREFIX=r3prod API_PORT=8899 SPEC=1 \
    ARM_ENV_FILE='$ENVC' SPEC_EXTRA_ARGS='$PROD_SPEC_EXTRA_ARGS' \
    BOOT_LOG='$W/ignite.log' \
    bash tools/boot-with-slotlock.sh bash $BOOT"
rc=$?
if [ "$DRY" = 0 ]; then
  echo "$rc" > "$W/ignite-rc.txt"
  [ "$rc" = 0 ] || die1 "点火 rc=$rc——查 $W/ignite.log 与 slotlock 持锁者；止损拆栈: CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash __ASSETS_ROOT__/bin/r3-stop.sh"
  printf '%s\t%s\t0\tunknown(无日志)\tparam:r3prod\tdeploy-034 ignition\n' "$(date -u +%FT%TZ)" "$ARM_TAG" >> "$MISFIRE" && echo "[deploy] misfire 台账点火行代录 → $MISFIRE"
fi

# ── S4 health 轮询（120min 死线）──
stage "health 轮询（http://127.0.0.1:8899/health，死线 120min）"
if [ "$DRY" = 1 ]; then
  echo "[dry-run] 将执行: 720×10s 轮询 /health 至 200（正典件 capture-boot-evidence.sh 同参）"
else
  FIRST200=""
  for i in $(seq 1 720); do
    CODE=$(curl -s -m 4 -o /dev/null -w "%{http_code}" http://127.0.0.1:8899/health 2>/dev/null || true)
    [ "$CODE" = 200 ] && { FIRST200=$(date -u +%s); break; }
    sleep 10
  done
  [ -n "$FIRST200" ] || die1 "120min 内 health 未达 200——查 $W/ignite.log 与 docker logs r3prod-head；止损拆栈命令同上"
  echo "$FIRST200" > "$W/health-first200.epoch"
  echo "[deploy] health 首 200 @ $(date -u -d @$FIRST200 +%FT%TZ)"
fi

# ── S5 settle 300s（D113-① 新制）──
stage "settle 300s（health 200 后 300s；D113-① 新制）"
if [ "$DRY" = 1 ]; then echo "[dry-run] 将执行: 等待至 health-first200.epoch+300s 后复探 health"; else
  DEADLINE=$(( $(cat "$W/health-first200.epoch") + 300 )); NOW=$(date -u +%s)
  (( NOW < DEADLINE )) && { W8=$((DEADLINE-NOW)); echo "[deploy] settle 余 ${W8}s"; sleep "$W8"; }
  C=$(curl -s -m 4 -o /dev/null -w "%{http_code}" http://127.0.0.1:8899/health 2>/dev/null || true)
  [ "$C" = 200 ] || die1 "settle 后 health=$C 非 200——查 docker logs r3prod-head；止损拆栈命令同上"
  echo "[deploy] settle 完（health=200）"
fi

# ── S6 正典 boot 核对面采集（横幅 8/8 + BYPASS ARMED 硬门）──
stage "capture-boot-evidence.sh（D110 正典件）+ BYPASS ARMED 硬门"
BELOG="$W/boot/boot-evidence.log"
if [ "$DRY" = 1 ]; then
  echo "[dry-run] 将执行: bash $HERE/capture-boot-evidence.sh $W/boot"
  echo "[dry-run] 将断言: 横幅 8/8（[5] 段）+ BYPASS ARMED armed 合计=8·refusing=0（[12] 段；D121 五步固化③）——不满足=die1 即停"
else
  bash "$HERE/capture-boot-evidence.sh" "$W/boot"
  B=$(grep -cE "Exact nvme Engram layer=(1|14) " "$BELOG" 2>/dev/null || true)
  [ "$B" = 8 ] || die1 "横幅 ${B}/8——查 $BELOG [5] 段（勿按零配即判 RED，正典件已对实测横幅形校准）"
  echo "[deploy] 横幅 8/8 ✓（正典核对面绿）"
  # BYPASS ARMED 硬门（D121 五步固化③；判据源=boot-evidence.log [12] 段/gates-034.tsv BL-BYP2：
  #   四机 armed 合计=8〔2/机〕且 refusing-to-arm=0；armed/refusing 任一不满足=即停，与 CFG-57/58/59 同源）
  A=$(grep -c "DSV41_PREFILL_BYPASS armed:" "$BELOG" 2>/dev/null || true)
  R=$(grep -ci "refusing to arm" "$BELOG" 2>/dev/null || true)
  { [ "$A" = 8 ] && [ "$R" = 0 ]; } || die1 "BYPASS ARMED ${A:-0}/8（期望 8=2/机×4）refusing=${R:-0}（期望 0）——查 $BELOG [12] 段；armed<8=未武装（env 键 CFG-56 未达容器/sitecustomize 钩 CFG-60 断/组件导入败）；refusing>0=守卫拒因（候选池/新鲜度界超限，查 bypass-armed-gate 逐机断言档）；分机拆面以 S7 doctor CFG-57/58 为准"
  echo "[deploy] BYPASS ARMED 8/8 + refusing=0 ✓（D121 ③硬门绿）"
fi

# ── S7 引擎面自排查 ──
stage "doctor --post-boot（引擎面自排查）"
if [ "$DRY" = 1 ]; then echo "[dry-run] 将执行: bash $HERE/doctor-034.sh --post-boot"; else
  bash "$HERE/doctor-034.sh" --post-boot || die1 "post-boot 存在 FAIL（逐行已带提示；v41/fork 判据=慢带教训硬门）——呈报处置，勿留栈盲跑"
fi

# ── S8 网关第五查（EQ-09：四查〔health/printenv/横幅/面指纹〕后追加第五查；口径=035-W0 任务书
#    EQ-09+外部手册部署篇 §20/§21〔PITFALLS P6-4/P6-5 同源〕；全 GET 轻探零推理载零 GPU）──
stage "网关第五查（EQ-09：网关 /health+UPSTREAM 车道+清单正典）"
GW_URL="${GW_URL:-http://127.0.0.1:8001}"; GW_EXPECT="${GW_UPSTREAM_EXPECT:-http://127.0.0.1:8899}"
GW_UNIT="${GW_UNIT:-concurrency-proxy-v2}"; GW_KEY="${GW_KEY:-}"
GW_EXPECT=${GW_EXPECT%/}
if [ "$DRY" = 1 ]; then
  echo "[dry-run] 将断言（EQ-09 三面）: ①$GW_URL/health=200（引擎探活透传面：网关活∧引擎经网关活才 200） ②网关 UPSTREAM=$GW_EXPECT（/proc MainPID environ 同用户只读，退化=journal 启动横幅；读不到=红） ③$GW_URL/v1/models 与 $GW_EXPECT/v1/models 逐 id 一致（GW_REQUIRE_AUTH 形须 GW_KEY）——任一红=die1 即停（引擎健康≠主链健康）"
else
  GW5BAD=0; STALE=""; MISSG=""
  # ① 网关 /health（rc3.8.5+ /health=鉴权豁免的引擎探活透传面）
  GHC=$(curl -s -m 6 -o /dev/null -w '%{http_code}' "$GW_URL/health" 2>/dev/null || true); GHC=${GHC:-000}
  [ "$GHC" = 200 ] && echo "[deploy] 网关 /health=200 ✓（主链全绿透传面）" || GW5BAD=1
  # ② UPSTREAM 车道指向（外部手册键 UPSTREAM_BASE≡我栈键 UPSTREAM；同用户 /proc 只读为主，journal 横幅退化）
  GWUP=""
  GWPID=$(systemctl show "$GW_UNIT" -p MainPID --value 2>/dev/null | tr -d '[:space:]')
  if [[ "$GWPID" =~ ^[0-9]+$ ]] && [ "$GWPID" -gt 0 ]; then
    GWUP=$(tr '\0' '\n' < "/proc/$GWPID/environ" 2>/dev/null | grep -m1 '^UPSTREAM=' | cut -d= -f2- || true)
  fi
  if [ -z "$GWUP" ]; then
    GWUP=$(journalctl -u "$GW_UNIT" --no-pager 2>/dev/null | grep -oE '0\.0\.0\.0:[0-9]+->https?://[^ ]+' | tail -1 | sed 's/^.*->//' || true)
  fi
  GWUP=${GWUP%/}
  if [ -n "$GWUP" ] && [ "$GWUP" = "$GW_EXPECT" ]; then echo "[deploy] 网关 UPSTREAM=$GWUP ✓（车道指向=引擎生产口正典）"
  else GW5BAD=1; fi
  # ③ 模型清单正典（引擎直连 ↔ 网关逐 id 对照；静态别名表旧名不出现）
  gwargs=(); [ -n "$GW_KEY" ] && gwargs=(-H "Authorization: Bearer $GW_KEY")
  EIDS=$(curl -s -m 6 "$GW_EXPECT/v1/models" 2>/dev/null | python3 -c 'import json,sys
try: print("\n".join(sorted(m["id"] for m in json.load(sys.stdin)["data"])))
except Exception: sys.exit(1)' 2>/dev/null || true)
  GIDS=$(curl -s -m 6 "${gwargs[@]}" "$GW_URL/v1/models" 2>/dev/null | python3 -c 'import json,sys
try: print("\n".join(sorted(m["id"] for m in json.load(sys.stdin)["data"])))
except Exception: sys.exit(1)' 2>/dev/null || true)
  if [ -n "$EIDS" ] && [ -n "$GIDS" ]; then
    STALE=$(comm -13 <(printf '%s\n' "$EIDS") <(printf '%s\n' "$GIDS") | tr '\n' ',' | sed 's/,$//')
    MISSG=$(comm -23 <(printf '%s\n' "$EIDS") <(printf '%s\n' "$GIDS") | tr '\n' ',' | sed 's/,$//')
    if [ -z "$STALE" ] && [ -z "$MISSG" ]; then echo "[deploy] 网关 /v1/models 与引擎在役清单逐 id 一致 ✓（静态别名旧名零出现）"
    else GW5BAD=1; fi
  else GW5BAD=1; fi
  [ "$GW5BAD" = 0 ] && echo "[deploy] 网关第五查绿（EQ-09：/health 200+UPSTREAM 正典+清单一致——点火验收覆盖完整主链）" || \
    die1 "网关第五查红（EQ-09：引擎健康≠主链健康——主链断面验收不绿；/health=$GHC·UPSTREAM=${GWUP:-读不到}·清单引擎侧=${EIDS:+可读}网关侧=${GIDS:+可读}${STALE:+·网关多列=$STALE}${MISSG:+·网关少列=$MISSG}）。自反馈: 排障序=外部手册部署篇 §20/P6-4（先 curl 代理口 health 再打主链入口 /v1/models，从主链底部指向往上查，勿只看引擎 health 即下结论）；网关 401=GW_REQUIRE_AUTH 形须 GW_KEY env；UPSTREAM 指错=网关 env 面（gateway 包 staging 同步面；8898=测试线死端口/8002=脚本缺省假车道）；网关启动/重启=网关变更窗职权非本编排器（boot-with-slotlock 纳入=EQ-09 另批分支）；探针件=gw 包 gw-verify.sh --live（GW_URL/GW_KEY 同参）"
fi

# ── S9 汇总报告 ──
stage "汇总报告"
SUM="$W/DEPLOY-SUMMARY.md"
if [ "$DRY" = 1 ]; then
  echo "[dry-run] 将写入: $SUM（级序/时戳/ARM_TAG/md5 链/doctor 汇总/验收与拆栈指引）"
  echo "[dry-run] 将代录 misfire 点火行（实跑时落 $MISFIRE）"
  echo "[deploy] --dry-run 全程走通（S1 实跑只读，S2-S9 打印不执行）——可以实跑"
  exit 0
fi
{
echo "# DEPLOY-034 汇总 @ $(date -u +%FT%TZ)"
echo "- ARM_TAG: \`$ARM_TAG\`；证据目录: \`$W\`"
echo "- 级序: S1 preflight → S2 :12 翻 x6bake（$( [ -f "$BAK" ] && echo "备份=$BAK" || echo "幂等跳过（已窗内态）")）→ S3 点火 → S4 health → S5 settle 300s → S6 正典核对面（横幅 8/8 + BYPASS ARMED 8/8·refusing=0）→ S7 post-boot → S8 网关第五查（EQ-09：/health+UPSTREAM 车道+清单正典，fail-closed）"
echo "- 静置制式: D113-① 新制（health 200+300s+正典核对面绿）；点火窗 boot=$MD5_IGNITE（窗毕回置 $MD5_STORE）"
echo "## 下一步"
echo "1. 验收电池: \`bash $HERE/verify-034.sh --smoke\`（或 \`--full\`）"
echo "2. 拆栈回设计态: \`CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash __ASSETS_ROOT__/bin/r3-stop.sh\`（D8 三查）+ boot :12 回置（sed 复 $TAG_FROM 或回拷 $BAK）+ 台账第二行落 $MISFIRE"
} | tee "$SUM"
echo "[deploy] 全链绿（S1-S9）——引擎在役 @ 8899"
exit 0
