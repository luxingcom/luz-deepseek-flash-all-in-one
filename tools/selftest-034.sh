#!/bin/bash
# selftest-034.sh — 0.3.4 交付包自身完整性检验器（自诊断测试件）
#
# 四段设计：
#   A=比较器单元：对 doctor-034.sh 的 verdict 语义做单元断言（精确串相等 / >=N / <=N 数值比较 /
#     非法输入处理）——被测函数逐字提取自生产 tools/doctor-034.sh（非重写副本）。
#   B=沙箱负例（自反馈闭环证明）：mktemp -d 沙箱复制 doctor-034.sh+config-034.tsv，篡改 7 个代表性
#     期望值（md5×3/键计数×1/精确串×1/数值×2，各类≥1），跑沙箱 doctor --preflight，断言对应行 FAIL+
#     退出码=1+失败提示行出现；trap 保沙箱清理；生产 tools/ 与一切生产面只读零改（前后 md5 快照断言）。
#   C=完整性走查：docs/release/MANIFEST-034LOCK.tsv 逐行复算 md5（段一 live+archive 双面、
#     段二工具冻结锚、尾追记终值行）+ tools/config-034.tsv 全部 CFG 行用其核验命令活体复算对期望；
#     失配逐行列出（授权在案漂移如实标注出处、不降判为绿）。
#   D=降级检测负例（GUARD-DEGRADED-20261029）：mktemp 沙箱合成四机日志形（fork-active/未武装/净形
#     三套+用法错类），经 doctor DG_SYNTH_DIR 测试缝喂沙箱 doctor --post-boot，断言=大声警告行
#     （降级面命中 [DGx]）+多行星号框≥3 行+退出码区分（降级=2/净形=0/用法错=3）。
# 用法：bash tools/selftest-034.sh
# 退出码：0=四段全绿；1=存在 FAIL（逐行列出于 stdout+报告）。
# 红线（随身，违反=即停如实呈报）：零 sudo；零 git 写（git status 只读快照仅取证）；生产面只读零改
#   （B/D 段篡改与合成档仅限沙箱副本与 /tmp）；零容器/引擎启停重启拆栈（只读 docker logs/inspect/ps
#   + curl GET 探活）；零 GPU 载荷；__GATEWAY_HOST__ 网关 GW_SAMPLING_POLICY/K16 两键只读不触；报告与产物密钥
#   一律掩码。
# 新建件仅限：tools/selftest-034.sh（本件）+ docs/plan/034-W1/SELFTEST-<date>.md（报告）。
# 法源：用户 2026-10-29 工单（0.3.4 交付包自诊断测试+守卫降级完善·降级大声警告硬性要求）
#   + D119-②（工具四件套）+ D115（工具复用律）+ GUARD-HARDENING-20261029.md / GUARD-DEGRADED-20261029.md（授权漂移档）。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAMP="$(cd "$HERE/.." && pwd)"
PROD_DOCTOR="$HERE/doctor-034.sh"
PROD_CFG="$HERE/config-034.tsv"
MAN="$CAMP/docs/release/MANIFEST-034LOCK.tsv"
REPORT="$CAMP/tests/SELFTEST-034-$(date -u +%Y%m%d).md"
# 公开树布局注记（0.3.4re 移植形）：原锁包束 archives/034-lock-20261028/ 在公开树不存在，
#   束内 10 件散布 deploy/ 与 docs/；段一 archive 面（束自完整性）改经 pub_path() 按文件名
#   映射到公开树在位件核 md5——脱敏拷贝与内部正典锚 md5 天然不同、未入公开树件缺位，
#   均如实 FAIL 列示（判读见各 FAIL 行注记）。
pub_path(){ # 段一固化件名 → 公开树落位（0.3.4re 移植布局）
  case "$1" in
    CBX1A-CERTM-spec1.env)   printf '%s' "$CAMP/deploy/env/CBX1A-CERTM-spec1.env";;
    .env.tp4)                printf '%s' "$CAMP/deploy/env/.env.tp4";;
    prod-profile.env|overlay-md5.txt) printf '%s' "$CAMP/deploy/prod/$1";;
    guards.conf)             printf '%s' "$CAMP/deploy/kit/guard/guards.conf";;
    overlay-map.tsv|deepseek_v4_backend.py) printf '%s' "$CAMP/deploy/overlay/o12c1-prod/$1";;
    r3-boot-arm.sh)          printf '%s' "$CAMP/deploy/bin/r3-boot-arm.sh";;
    ROLLBACK-PATHS.md)       printf '%s' "$CAMP/docs/runbook/ROLLBACK-PATHS-034.md";;
    concurrency_proxy_v2.py) printf '%s' "$CAMP/tools/packages/gateway/payload/concurrency_proxy_v2.py";;
    proxy.env)               printf '%s' "$CAMP/tools/packages/gateway/proxy.env";;
    *) printf '%s' "$CAMP/$1";;
  esac
}
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=8"

# ── 计数器 ────────────────────────────────────────────────────────────────
A_PASS=0; A_FAIL=0            # 段A 单元断言
B_NEG_TOTAL=0; B_NEG_DET=0; B_ASSERT_FAIL=0   # 段B 负例：篡改数/检出数/断言失败数
D_NEG_TOTAL=0; D_DET=0; D_ASSERT_FAIL=0       # 段D 降级检测负例：用例数/全断言过数/断言失败数
C_CHECKED=0; C_FAILN=0; C_NA=0 # 段C 完整性：执行数/失败数/N/A 数
C_FAILS=()                    # 失配键清单
PROD_DIRTY=0                  # 生产面被改=1（红线违例，硬失败）

RL(){ printf '%s\n' "$*" | tee -a "$REPORT"; }
die(){ echo "[selftest] FATAL: $*" >&2; exit 2; }

hex32(){ printf '%s' "$1" | grep -oE '[0-9a-f]{32}' | head -1; }

resolve_path(){
  local p; p=$(printf '%s' "$1" | sed 's/（.*$//')   # 剥尾注（…）——路径体全 ASCII
  case "$p" in
    '~'*)            printf '%s' "$HOME${p#\~}";;
    __REPO_ROOT__/*) printf '%s' "$CAMP/${p#__REPO_ROOT__/}";;
    logs/*|tools/*)  printf '%s' "$CAMP/$p";;
    *)               printf '%s' "$p";;
  esac
}

mac_md5(){ # __GATEWAY_HOST__ 只读 md5（macOS md5 -q 主、md5sum 备）
  local p=$1 m
  m=$(ssh -n $SSHOPTS __GATEWAY_HOST__ "md5 -q '$p'" 2>/dev/null)
  [ -n "$m" ] || m=$(ssh -n $SSHOPTS __GATEWAY_HOST__ "md5sum '$p' 2>/dev/null | awk '{print \$1}'" 2>/dev/null)
  printf '%s' "$m"
}

drift_note(){ # 授权在案漂移注记（只标注出处，不降判）
  case "$1" in
    CBX1A-CERTM-spec1.env) echo "授权在案：W-f I8 采用尾行（WD-TUNED-FINAL-20261029 §一：60 键 f9fec92f→61 键 4370aab9，.bak-pre-deopt-adopt-20261029=回退锚；config CFG-04/05=现值锚）；MANIFEST 重钉=重封包相（D124-④，未越序）";;
    prod-profile.env)      echo "授权在案：W-f I8 采用重钉 :8/:9（WD-TUNED-FINAL-20261029 §一/§二：a15da805→77d7fa67）；MANIFEST 重钉=重封包相（D124-④）";;
    gates-034.tsv)         echo "授权在案：W-f 重钉 BL11/BL16（WD-TUNED-FINAL §二）+守卫完善窗 BL-BYP1/2 入册（GUARD-HARDENING §五=c87f8a06 形）；MANIFEST 重钉=重封包相";;
    r3-boot-arm.sh)        echo "非 BL09 双合法集（存储 50700486/点火窗 d41323dd）外形态=漂移，停窗呈报（窗毕须回置 50700486）";;
    capture-boot-evidence.sh) echo "授权在案：D121-③ 增 [12] BYPASS 采集段（config CFG-39=0b9117cb 锚）";;
    deploy-034.sh)         echo "授权在案：GUARD-HARDENING §一（S6 ARMED 硬门+S1 在役拒起门；config CFG-62=现值锚）";;
    verify-034.sh)         echo "授权在案：GUARD-HARDENING §二+主会话 B3/B7 修复（config CFG-63=现值锚）";;
    doctor-034.sh)         echo "授权在案：GUARD-HARDENING §四（状态感知+ISVC）+GUARD-DEGRADED-20261029（降级面检测 DG1..6+大声警告+退出码 2 类；config CFG-64=现值锚）";;
    config-034.tsv)        echo "授权在案：W-f 重钉 CFG-04/05/12/13/14+CFG-65 新行（WD-TUNED §二）+守卫降级窗 CFG-64 重钉+CFG-66/67 新锚（GUARD-DEGRADED-20261029 §四）；MANIFEST 追记未续写=档面缺口（重封包相兑付）";;
    追记:doctor-034.sh|追记:config-034.tsv) echo "授权在案：GUARD-HARDENING §一/§四+GUARD-DEGRADED-20261029；MANIFEST 追记未续写=档面缺口（如实呈报，重封包相以「主会话终检重算为准」追记律补写）";;
    *) echo "未见授权档——需停窗呈报";;
  esac
}

# ── 生产面只读快照（前）──────────────────────────────────────────────────
SNAP_FILES=("$PROD_DOCTOR" "$PROD_CFG" "$HERE/deploy-034.sh" "$HERE/verify-034.sh" \
            "$HERE/gates-034.tsv" "$HERE/capture-boot-evidence.sh" "$MAN" \
            "$CAMP/docs/runbook/ROLLBACK-PATHS-034.md")
SNAP_BEFORE=()
for f in "${SNAP_FILES[@]}"; do SNAP_BEFORE+=("$(md5sum "$f" 2>/dev/null | awk '{print $1}')"); done

# ── 引擎态（只读探测；镜像 doctor:93 分轨判据）────────────────────────────
n01=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -cE '^r3(prod|boot)-' || true)
[[ "$n01" =~ ^[0-9]+$ ]] || n01=0
hcode=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true); hcode=${hcode:-000}
INSVC=0; { [ "$n01" != 0 ] || [ "$hcode" = 200 ]; } && INSVC=1
ARMTAG=$(grep -o 'ARM_TAG=[^ ]*' "$CAMP/.slot-lock" 2>/dev/null | head -1)

# ══ 报告头 ════════════════════════════════════════════════════════════════
mkdir -p "$(dirname "$REPORT")"
{
  echo "# SELFTEST-20261029 — 0.3.4 交付包自身完整性检验（selftest-034.sh 实跑报告）"
  echo
  echo "> **执行**: $(date -u +%FT%TZ) @ $(hostname)（__PROD_HOST_01__）｜**执行件**: tools/selftest-034.sh"
  echo "> **引擎态（只读探测）**: r3ctn01=$n01 health(8899)=$hcode → $([ "$INSVC" = 1 ] && echo 在役 || echo 停机设计态)｜${ARMTAG:-ARM_TAG=<无锁档>}"
  echo "> **红线遵守**: 零 sudo/零 git 写/零容器与引擎启停（只读 docker ps/inspect/logs+curl GET）/零 GPU 载荷/"
  echo "> __GATEWAY_HOST__ 两键只读不触/密钥掩码（本报告仅含 md5 与计数，无密钥面）。新建件=本件+本报告（授权清单内）。"
  echo "> **四段**: A=doctor verdict 比较器单元；B=沙箱负例（自反馈闭环证明）；C=完整性走查（MANIFEST 逐行+config 全 CFG 行活体）；"
  echo "> D=降级检测负例（GUARD-DEGRADED-20261029：合成 fork-active/未武装日志形→断言大声警告行+退出码 2/0/3 区分）。"
  echo
} > "$REPORT"

RL "## §A 比较器单元（被测=生产 doctor-034.sh 的 verdict()，逐字提取非重写）"
RL ""
RL "提取源: \`sed -n '/^verdict(){/,/^}$/p' tools/doctor-034.sh\`（提取体含 \`>=\`/\`<=\` 两分支即视为提取成功）"
RL ""
VERDICT_SRC="$(sed -n '/^verdict(){/,/^}$/p' "$PROD_DOCTOR")"
if [ -z "$VERDICT_SRC" ] || ! printf '%s' "$VERDICT_SRC" | grep -Fq '">="*' || ! printf '%s' "$VERDICT_SRC" | grep -Fq '"<="*'; then
  RL "**提取失败**——verdict 函数未能在生产 doctor-034.sh 中定位，段A 判 FAIL（硬失败）。"
  A_FAIL=$((A_FAIL+1)); C_FAILS+=("A:verdict-extract")
else
  eval "$VERDICT_SRC"   # 纯函数，定义入当前 shell（无副作用）
  RL "| 用例 | got | want | 语义 | 期望判定 | 实测 | 结果 |"
  RL "|---|---|---|---|---|---|---|"
  at(){ # at <id> <got> <want> <期望0真1假> <语义>
    local id=$1 got=$2 want=$3 exp=$4 note=$5 dg dw r
    dg=${got:-<空>}; dw=${want:-<空>}
    if verdict "$got" "$want"; then r=0; else r=1; fi
    if [ "$r" -eq "$exp" ]; then
      A_PASS=$((A_PASS+1)); RL "| $id | \`$dg\` | \`$dw\` | $note | $([ "$exp" = 0 ] && echo 真 || echo 假) | $([ "$r" = 0 ] && echo 真 || echo 假) | PASS |"
    else
      A_FAIL=$((A_FAIL+1)); RL "| $id | \`$dg\` | \`$dw\` | $note | $([ "$exp" = 0 ] && echo 真 || echo 假) | $([ "$r" = 0 ] && echo 真 || echo 假) | **FAIL** |"
    fi
  }
  # 精确串相等
  at A01 200 200 0 "精确串相等（health=200 形，CFG-55）"
  at A02 000 200 1 "精确串不等（设计态端口闭，CFG-42/43）"
  at A03 SGLANG_DSV4_KV_LAYOUT=v41 SGLANG_DSV4_KV_LAYOUT=v41 0 "精确串相等（长参数名，CFG-11）"
  at A04 SGLANG_DSV4_KV_LAYOUT=v41 SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4 1 "精确串不等（KV 布局退化形）"
  at A05 FREE FREE 0 "精确串相等（slotlock，CFG-41）"
  # >=N 数值
  at A06 5 '>=3' 0 ">=N 真"
  at A07 2 '>=3' 1 ">=N 假"
  at A08 3 '>=3' 0 ">=N 边界等值真（CFG-46 >=4 形同族）"
  at A09 4 '>=4' 0 ">=N 边界等值真（CFG-46）"
  # <=N 数值
  at A10 3 '<=5' 0 "<=N 真"
  at A11 6 '<=5' 1 "<=N 假"
  at A12 5 '<=5' 0 "<=N 边界等值真"
  at A13 0 '<=0' 0 "<=0 零值真（CFG-47 fork 残留=0 语义）"
  # 非法输入处理（比较器须判假，不得误判真或抛错外溢）
  at A14 abc '>=3' 1 "非法：got 非纯数字 vs >=N → 假"
  at A15 '' '>=1' 1 "非法：got 空 vs >=N → 假"
  at A16 12x '<=20' 1 "非法：got 含字母尾 vs <=N → 假"
  at A17 0x10 '>=1' 1 "非法：got 十六进制形 vs >=N → 假"
  at A18 '' '<=0' 1 "非法：got 空 vs <=0 → 假（空非数字不得借 <=0 洗白）"
  # 裸串数值面
  at A19 60 60 0 "裸串数值等值真（键计数 60，CFG-05）"
  at A20 61 60 1 "裸串数值不等假（B 段篡改 60→61 语义）"
fi
RL ""
RL "§A 汇总: **unitPass=$A_PASS unitFail=$A_FAIL**"
RL ""

# ══ §B 沙箱负例 ═══════════════════════════════════════════════════════════
RL "## §B 沙箱负例（自反馈闭环证明：篡改沙箱副本期望值 → doctor 必须红）"
RL ""
SBX=$(mktemp -d /tmp/selftest034-sbx.XXXXXX) || die "mktemp 失败"
cleanup(){ [ -n "${SBX:-}" ] && [ -d "$SBX" ] && rm -rf "$SBX"; [ -n "${SBX2:-}" ] && [ -d "$SBX2" ] && rm -rf "$SBX2"; }
trap cleanup EXIT
cp "$PROD_DOCTOR" "$SBX/doctor-034.sh"; cp "$PROD_CFG" "$SBX/config-034.tsv"

# 篡改 7 个代表性期望值（md5×3 / 键计数×1 / 精确串×1 / 数值×2；全部 any 时点行=--preflight 必执行）
# （2026-10-29 守卫降级窗维护注记：CFG-05 篡改值 61→62——产面 CFG-05 已被 W-f I8 采用重钉为 61
#   〔WD-TUNED-FINAL §二〕，61 形不再构成篡改差量；篡改面保持与现产期望值恒差）
T_IDS=(CFG-04 CFG-07 CFG-10 CFG-05 CFG-13 CFG-23 CFG-26)
declare -A T_CAT=(["CFG-04"]=md5 ["CFG-07"]=md5 ["CFG-10"]=md5 ["CFG-05"]=键计数 ["CFG-13"]=精确串 ["CFG-23"]=数值 ["CFG-26"]=数值)
declare -A T_NEW=(["CFG-04"]=ffffffffffffffffffffffffffffffff ["CFG-07"]=eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
       ["CFG-10"]=dddddddddddddddddddddddddddddddd ["CFG-05"]=62 ["CFG-13"]=PROD_ARM_ENV_MD5=TAMPERED-EXACT-STRING \
       ["CFG-23"]=30 ["CFG-26"]=98)
awk -F'\t' -v OFS='\t' 'BEGIN{
  t["CFG-04"]="ffffffffffffffffffffffffffffffff"; t["CFG-07"]="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee";
  t["CFG-10"]="dddddddddddddddddddddddddddddddd"; t["CFG-05"]="62";
  t["CFG-13"]="PROD_ARM_ENV_MD5=TAMPERED-EXACT-STRING"; t["CFG-23"]="30"; t["CFG-26"]="98";
} $1 in t { $5=t[$1] } { print }' "$PROD_CFG" > "$SBX/config-034.tsv"

RL "篡改面（仅沙箱副本 \`$SBX/config-034.tsv\`；生产 config-034.tsv 零改）："
RL ""
RL "| id | 类别 | 生产原期望 | 沙箱篡改值 |"
RL "|---|---|---|---|"
TAMPER_OK=0
for id in "${T_IDS[@]}"; do
  owant=$(awk -F'\t' -v i="$id" '$1==i{print $5}' "$PROD_CFG")
  nwant=$(awk -F'\t' -v i="$id" '$1==i{print $5}' "$SBX/config-034.tsv")
  nline=$(wc -l < "$SBX/config-034.tsv"); pline=$(wc -l < "$PROD_CFG")
  RL "| $id | ${T_CAT[$id]} | \`$owant\` | \`$nwant\` |"
  [ "$nwant" = "${T_NEW[$id]}" ] && [ "$nwant" != "$owant" ] && TAMPER_OK=$((TAMPER_OK+1))
done
B_NEG_TOTAL=${#T_IDS[@]}
if [ "$TAMPER_OK" -ne "$B_NEG_TOTAL" ] || [ "$nline" -ne "$pline" ]; then
  RL "**篡改落地失败**（TAMPER_OK=$TAMPER_OK/${B_NEG_TOTAL} 或行数变 $nline≠$pline）——段B 硬失败。"
  B_ASSERT_FAIL=$((B_ASSERT_FAIL+1))
fi
RL ""
RL "执行: \`bash \$SBX/doctor-034.sh --preflight\`（沙箱件；HERE=沙箱 → 消费沙箱篡改 config；核验命令活读生产实值=只读）"
RL ""
bash "$SBX/doctor-034.sh" --preflight > "$SBX/out.txt" 2>&1; B_RC=$?
RL '```'
RL "$(grep -E '^\[state\]|^== 汇总' "$SBX/out.txt")"
RL '```'
RL ""
yn(){ [ "$1" = 1 ] && printf '✓' || printf '✗'; }
RL "| id | 断言①FAIL 行 | 断言②want=篡改值 | 断言③got=活读实值 | 断言④自反馈提示行 | 断言⑤行内提示文 | 检出 |"
RL "|---|---|---|---|---|---|---|"
for id in "${T_IDS[@]}"; do
  hint=$(awk -F'\t' -v i="$id" '$1==i{print $8}' "$SBX/config-034.tsv")
  fline=$(grep -E "^FAIL $id " "$SBX/out.txt" | head -1)
  a1=0; a2=0; a3=0; a4=0; a5=0; gotv=""
  if [ -n "$fline" ]; then
    a1=1
    printf '%s' "$fline" | grep -Fq "want=${T_NEW[$id]}" && a2=1
    gotv=$(printf '%s' "$fline" | sed -n 's/.*got=\(.*\) want=.*/\1/p'); [ -n "$gotv" ] && a3=1
    grep -A1 -E "^FAIL $id " "$SBX/out.txt" | grep -q '↳ 自反馈:' && a4=1
    grep -Fq "$hint" "$SBX/out.txt" && a5=1
  fi
  if [ $a1$a2$a3$a4$a5 = 11111 ]; then B_NEG_DET=$((B_NEG_DET+1)); d='✓'; else B_ASSERT_FAIL=$((B_ASSERT_FAIL+1)); d='**FAIL**'; fi
  RL "| $id | $(yn $a1) | $(yn $a2) | \`${gotv:-<空>}\` | $(yn $a4) | $(yn $a5) | $d |"
done
RL ""
# 全局断言：退出码=1；沙箱清理；生产 doctor/config 零改
if [ "$B_RC" -eq 1 ]; then RL "全局断言·退出码=1：**PASS**（实测 rc=$B_RC）"; else B_ASSERT_FAIL=$((B_ASSERT_FAIL+1)); RL "全局断言·退出码=1：**FAIL**（实测 rc=$B_RC）"; fi
pdoc_md5=$(md5sum "$PROD_DOCTOR" | awk '{print $1}'); pcfg_md5=$(md5sum "$PROD_CFG" | awk '{print $1}')
if [ "$pdoc_md5" = "${SNAP_BEFORE[0]}" ] && [ "$pcfg_md5" = "${SNAP_BEFORE[1]}" ]; then
  RL "生产面只读断言（doctor/config md5 前后不变）：**PASS**（$pdoc_md5 / $pcfg_md5）"
else
  PROD_DIRTY=1; RL "生产面只读断言：**FAIL——红线违例即停呈报**"
fi
cleanup
if [ ! -d "$SBX" ]; then RL "沙箱清理断言（rm -rf \$SBX + trap 兜底）：**PASS**（$SBX 已除）"; else B_ASSERT_FAIL=$((B_ASSERT_FAIL+1)); RL "沙箱清理断言：**FAIL**（$SBX 残留）"; fi
RL ""
RL "§B 汇总: **negativeDetected=$B_NEG_DET/$B_NEG_TOTAL**（自反馈闭环证明：篡改期望→doctor 对应行 FAIL+提示行+rc=1）· 断言失败数=$B_ASSERT_FAIL"
RL ""

# ══ §D 降级检测负例（GUARD-DEGRADED-20261029；合成 fork-active/未武装日志形→断言大声警告行+退出码）═══
RL "## §D 降级检测负例（合成四机日志形经 DG_SYNTH_DIR 测试缝喂沙箱 doctor --post-boot；生产态零触）"
RL ""
SBX2=$(mktemp -d /tmp/selftest034-dg.XXXXXX) || die "mktemp §D 失败"
cp "$PROD_DOCTOR" "$SBX2/doctor-034.sh"; cp "$PROD_CFG" "$SBX2/config-034.tsv"
mk_synth(){ # mk_synth <dir> <v41行/机> <fork行/机> <armed行/机> —— 合成四机日志（行形=实拍日志族：[kv_fp4] gate 行/passthrough 行/armed 行/横幅行/池指纹行〔head〕）
  local d=$1 v41=$2 fork=$3 armed=$4 f i
  mkdir -p "$d"
  for f in r3prod-head r3prod-worker-__PROD_HOST_02__ r3prod-worker-__PROD_HOST_03__ r3prod-worker-__PROD_HOST_04__; do
    : > "$d/$f.log"
    for i in $(seq 1 "$v41"); do printf '%s\n' '[kv_fp4] gate=1 mode=v41 active=False installed=(none) r1_inkernel=True r1_formal=1' >> "$d/$f.log"; done
    printf '%s\n' "[2026-10-29 00:00:00] DSV41_FP4KV_PORT=1 but SGLANG_DSV4_KV_LAYOUT='v41' is explicit: fp4-KV patches stay passthrough" >> "$d/$f.log"
    for i in $(seq 1 "$fork"); do printf '%s\n' '[kv_fp4] gate=1 mode=fork-v4-fp4 active=True installed=(fp4kv r1 bridge) r1_inkernel=True r1_formal=1' >> "$d/$f.log"; done
    for i in $(seq 1 "$armed"); do printf '%s\n' '[2026-10-29 00:00:00] DSV41_PREFILL_BYPASS armed: at most 2048 total fresh tokens and 32 candidates scanned per in-flight chunk pass; engine token-pool admission retained; fleet qualification pending' >> "$d/$f.log"; done
    if [ "$f" = r3prod-head ]; then
      printf '%s\n' '[2026-10-29 00:00:00 TP0] DSV4 pool sizes: full=9600000, swa=125440, c4=2400000, c128=75000, c4_state=0, c128_state=0' >> "$d/$f.log"
      printf '%s\n' '[2026-10-29 00:00:00 TP0] max_total_num_tokens=9600000, chunked_prefill_size=4096, max_prefill_tokens=16384, max_running_requests=16, context_len=600000, available_gpu_mem=10.34 GB' >> "$d/$f.log"
    fi
    printf '%s\n' '[2026-10-29 00:00:00 TP0] Exact nvme Engram layer=1 rank=0 rows=[0,96001542) cache=2.0GiB (7893344 slots, 16-way, 8.2% of owned rows) scales=0.0GiB io_threads=96 packed=True gov-abi orders=2g:100%' >> "$d/$f.log"
    printf '%s\n' '[2026-10-29 00:00:00 TP0] Exact nvme Engram layer=14 rank=0 rows=[0,96004170) cache=2.0GiB (7893344 slots, 16-way, 8.2% of owned rows) scales=0.0GiB io_threads=96 packed=True gov-abi orders=2g:100%' >> "$d/$f.log"
  done
}
mk_synth "$SBX2/synth-fork"   0 1 2   # fork-active 形（v41 行零+fork active 行在位）
mk_synth "$SBX2/synth-unarm"  1 0 0   # 未武装形（armed 行零）
mk_synth "$SBX2/synth-clean"  1 0 2   # 净形（对照：四机 v41×4/armed 8/横幅 8/池指纹全对）
d_run(){ DG_SYNTH_DIR="$1" bash "$SBX2/doctor-034.sh" --post-boot > "$SBX2/$2.txt" 2>&1; }
d_hit(){ local n; n=$(grep -c "降 级 面 命 中 \[$1\]" "$SBX2/$2.txt" 2>/dev/null); [[ "$n" =~ ^[0-9]+$ ]] || n=0; printf '%s' "$n"; }
d_box(){ local n; n=$(grep -cE '^\*{20,}' "$SBX2/$1.txt" 2>/dev/null); [[ "$n" =~ ^[0-9]+$ ]] || n=0; printf '%s' "$n"; }
d_any(){ local n; n=$(grep -c '降 级 面 命 中' "$SBX2/$1.txt" 2>/dev/null); [[ "$n" =~ ^[0-9]+$ ]] || n=0; printf '%s' "$n"; }
RL "断言面=①大声警告行（降级面命中 [DGx] 登记）②多行星号框 ≥3 行③退出码区分（降级=2/净形=0/用法错=3）④交叉零误报（fork 形伴 DG3/未武装形无 DG1/净形零命中）"
RL ""
RL "| 用例 | 合成形 | ①警告行 | ②星号框 | ③退出码 | ④交叉零误报 | 判定 |"
RL "|---|---|---|---|---|---|---|"
dg_case(){ # dg_case <名> <形述> <dir> <期望DG|-> <期望rc> <交叉断言shell>（期望DG='-'=净形零命中）
  local nm=$1 desc=$2 dir=$3 want=$4 erc=$5 cross="$6" rc a1 a2 a3 a4 d='**FAIL**'
  d_run "$dir" "$nm"; rc=$?
  if [ "$want" = "-" ]; then a1=0; [ "$(d_any "$nm")" -eq 0 ] && a1=1
  else a1=0; [ "$(d_hit "$want" "$nm")" -ge 1 ] && a1=1; fi
  a2=0; if [ "$want" = "-" ]; then [ "$(d_box "$nm")" -eq 0 ] && a2=1; else [ "$(d_box "$nm")" -ge 3 ] && a2=1; fi
  a3=0; [ "$rc" -eq "$erc" ] && a3=1
  a4=0; eval "$cross" && a4=1
  D_NEG_TOTAL=$((D_NEG_TOTAL+1))
  if [ $a1$a2$a3$a4 = 1111 ]; then D_DET=$((D_DET+1)); d='✓'; else D_ASSERT_FAIL=$((D_ASSERT_FAIL+1)); fi
  RL "| $nm | $desc | $(yn $a1)（$([ "$want" = "-" ] && d_any "$nm" || d_hit "$want" "$nm") 行） | $(yn $a2)（$(d_box "$nm") 行） | $(yn $a3)（rc=$rc 望 $erc） | $(yn $a4) | $d |"
}
dg_case D1-fork   "fork-active（v41=0·fork≥1/机）" "$SBX2/synth-fork"  DG1 2 '[ "$(d_hit DG3 D1-fork)" -ge 1 ]'
dg_case D2-unarm  "BYPASS 未武装（armed=0）"       "$SBX2/synth-unarm" DG2 2 '[ "$(d_hit DG1 D2-unarm)" -eq 0 ]'
dg_case D3-clean  "净形（全对对照·零命中）"         "$SBX2/synth-clean" -   0 'grep -q "DEGRADED=0" "$SBX2/D3-clean.txt"'
# D4 退出码类区分：用法错=3（2 已让位降级类——GUARD-DEGRADED 退出码语义）
bash "$SBX2/doctor-034.sh" --bogus-mode > "$SBX2/D4-usage.txt" 2>&1; D4RC=$?
D_NEG_TOTAL=$((D_NEG_TOTAL+1))
if [ "$D4RC" -eq 3 ] && grep -q '用法' "$SBX2/D4-usage.txt"; then D_DET=$((D_DET+1)); d4='✓'; else D_ASSERT_FAIL=$((D_ASSERT_FAIL+1)); d4='**FAIL**'; fi
RL "| D4-usage | 用法错类（--bogus-mode） | —（非降级面） | — | $( [ "$D4RC" -eq 3 ] && printf '✓（rc=3）' || printf '**FAIL**（rc=%s 望 3）' "$D4RC" ) | 用法行=$(grep -q '用法' "$SBX2/D4-usage.txt" && printf ✓ || printf ✗) | $d4 |"
RL ""
RL "§D 汇总: **degradedDetected=$D_DET/$D_NEG_TOTAL**（大声警告行+星号框+退出码 2/0/3 区分全断言）· 断言失败数=$D_ASSERT_FAIL"
RL ""

# ══ §C 完整性走查 ═════════════════════════════════════════════════════════
RL "## §C 完整性走查"
RL ""
RL "### C1 MANIFEST-034LOCK.tsv 逐行复算（段一 live+archive 双面 / 段二工具冻结锚 / 追记终值行）"
RL ""
RL "| 键 | 对象 | 记录值 | 复算值 | 判定 | 注 |"
RL "|---|---|---|---|---|---|"
c1_fail(){ C_FAILN=$((C_FAILN+1)); C_FAILS+=("$1"); RL "$2"; }
SEG=1
while IFS=$'\t' read -r f1 f2 f3 f4 f5 f6; do
  case "$f1" in ''|'#'*) continue;; esac
  if [ "$f1" = "filename" ]; then continue; fi
  if [ "$f1" = "tool" ]; then SEG=2; continue; fi
  if [ "$SEG" -eq 1 ]; then
    # —— 段一：live 面 ——
    if printf '%s' "$f2" | grep -q __GATEWAY_HOST__; then
      lm=$(mac_md5 "$(resolve_path "$f3")")
    else
      lm=$(md5sum "$(resolve_path "$f3")" 2>/dev/null | awk '{print $1}')
    fi
    allowed=$(printf '%s' "$f4" | grep -oE '[0-9a-f]{32}' | sort -u)
    rec=$(printf '%s' "$allowed" | head -1)
    C_CHECKED=$((C_CHECKED+1))
    if printf '%s\n' "$allowed" | grep -qx "$lm"; then
      extra=""; [ "$(printf '%s\n' "$allowed" | wc -l)" -gt 1 ] && extra="（BL09 双合法允差集内：$([ "$lm" = "$rec" ] && echo 存储形 || echo 点火窗合法态)）"
      RL "| C1-live:$f1 | $f1 | $rec… | $lm | PASS | live 与档一致$extra |"
    else
      # BL09 允差核：档行自带 8-hex 缩写第二合法形（点火形）注记时，以 config CFG-01 双合法归一命令（唯一事实源）裁决
      abbr8=$(printf '%s' "$f4" | sed -E 's/[0-9a-f]{32}//g' | grep -oE '[0-9a-f]{8}' | head -1)
      adj=""
      if [ -n "$abbr8" ] && [ "${lm:0:8}" = "$abbr8" ]; then
        c1cmd=$(awk -F'\t' -v i=CFG-01 '$1==i{print $7}' "$PROD_CFG")
        adj=$(bash -c "$c1cmd" </dev/null 2>/dev/null | head -1)
      fi
      if [ "$adj" = LEGAL ]; then
        RL "| C1-live:$f1 | $f1 | $rec…（+8-hex 缩写第二合法形 $abbr8…） | $lm | PASS | BL09 双合法允差集内（点火窗合法态；CFG-01 双合法归一核=LEGAL） |"
      else
        row="| C1-live:$f1 | $f1 | ${rec:-<无32hex>} | ${lm:-<缺失/不可读>} | **FAIL** | $(drift_note "$f1") |"
        c1_fail "C1-live:$f1" "$row"
      fi
    fi
    # —— 段一：archive 面（公开树在位件对锚；原束内副本面经 pub_path() 落位）——
    apath="$(pub_path "$f1")"
    am=$(md5sum "$apath" 2>/dev/null | awk '{print $1}')
    arec=$(hex32 "$f5")
    C_CHECKED=$((C_CHECKED+1))
    if [ -n "$arec" ] && [ "$am" = "$arec" ]; then
      RL "| C1-arch:$f1 | ${apath#$CAMP/} | $arec | $am | PASS | 公开树在位件与档一致 |"
    else
      c1_fail "C1-arch:$f1" "| C1-arch:$f1 | ${apath#$CAMP/} | ${arec:-<无>} | ${am:-<缺失>} | **FAIL** | 公开树在位件失配或缺位（脱敏拷贝 md5 与内部正典锚天然不同/该件未入公开树=布局缺口如实列示） |"
    fi
  else
    # —— 段二：工具冻结锚 ——
    f4c=$(hex32 "$f4")
    if [ -n "$f4c" ]; then
      tm=$(md5sum "$(resolve_path "$f3")" 2>/dev/null | awk '{print $1}')
      C_CHECKED=$((C_CHECKED+1))
      if [ "$tm" = "$f4c" ]; then
        RL "| C1-tool:$f1 | $f1 | $f4c | $tm | PASS | 冻结锚在位 |"
      else
        c1_fail "C1-tool:$f1" "| C1-tool:$f1 | $f1 | $f4c | ${tm:-<缺失>} | **FAIL** | $(drift_note "$f1") |"
      fi
    elif printf '%s' "$f1" | grep -q gsm8k; then
      anchor8=$(printf '%s' "$f4" | grep -oE '[0-9a-f]{8}' | head -1)
      fm=$(md5sum "$HOME/bench-results/gsm8k-sample500/sample500.jsonl" 2>/dev/null | awk '{print $1}')
      C_CHECKED=$((C_CHECKED+1))
      if [ "${fm:0:8}" = "$anchor8" ]; then
        RL "| C1-tool:$f1 | 冻结帧（8-hex 帧锚） | $anchor8 | ${fm:0:8}（帧文件全值=${fm:0:32}，CFG-33 全锚面） | PASS | 帧锚一致 |"
      else
        c1_fail "C1-tool:$f1" "| C1-tool:$f1 | 冻结帧 | $anchor8 | ${fm:0:8} | **FAIL** | 冻结帧漂移=500q 读数不可比 |"
      fi
    elif printf '%s' "$f4" | grep -qE 'R1EQ2026|Δtf'; then
      RL "| C1-skip:$f1 | $f1 | $(printf '%s' "$f4" | cut -c1-24)… | — | SKIP | 非 md5 文件锚（盐标识/量值口径），由正档与 C2 活体行承载，不在本段复算 |"
    else
      RL "| C1-skip:$f1 | $f1 | $(printf '%s' "$f4" | cut -c1-24)… | — | SKIP | 锚列无可解析 md5——如实注记不臆测 |"
    fi
  fi
done < "$MAN"
# —— 追记终值行（末条承接=追记时间序语义；主会话 2026-10-29 修复 head→tail）——
for pair in "doctor-034.sh:PROD_DOCTOR" "config-034.tsv:PROD_CFG"; do
  nm=${pair%%:*}; var=${pair#*:}
  zv=$(grep -oE "$nm 终值=[0-9a-f]{32}" "$MAN" | tail -1 | grep -oE '[0-9a-f]{32}')
  cm=$(md5sum "${!var}" 2>/dev/null | awk '{print $1}')
  C_CHECKED=$((C_CHECKED+1))
  if [ -n "$zv" ] && [ "$cm" = "$zv" ]; then
    RL "| C1-追记:$nm | $nm（MANIFEST 追记终值） | $zv | $cm | PASS | 追记终值=现值 |"
  else
    c1_fail "C1-追记:$nm" "| C1-追记:$nm | $nm（MANIFEST 追记终值） | ${zv:-<无>} | $cm | **FAIL** | $(drift_note "追记:$nm") |"
  fi
done
RL ""
RL "### C2 config-034.tsv 全部 CFG 行活体复算（逐行核验命令实跑；期望判定=doctor verdict 同源语义）"
RL ""
RL "引擎态分轨（镜像 doctor:72-75）：$([ "$INSVC" = 1 ] && echo "在役 → CFG-40/CFG-42 设计态行 N/A[in-service]（非漂移）" || echo "停机设计态 → 全行执法")"
RL ""
RL "| id | 时点 | 活体复算 got | want | 判定 |"
RL "|---|---|---|---|---|"
while IFS=$'\t' read -r id phase face param want loc cmd hint; do
  case "$id" in ''|'#'*) continue;; esac
  # 表头行律：doctor tsv_rows 以「时点∈{pre,post,any}」筛行天然跳过表头（时点列=『时点』非合法值）；本走查同律
  { [ "$phase" = pre ] || [ "$phase" = post ] || [ "$phase" = any ]; } || continue
  got=$(bash -c "$cmd" </dev/null 2>/dev/null)
  got="$(printf '%s' "$got" | head -1 | sed 's/[[:space:]]*$//')"
  if [ "$INSVC" = 1 ] && { [ "$id" = CFG-40 ] || [ "$id" = CFG-42 ]; }; then
    C_NA=$((C_NA+1)); RL "| $id | $phase | ${got:-<空>} | $want | N/A[in-service] |"
    continue
  fi
  C_CHECKED=$((C_CHECKED+1))
  if verdict "$got" "$want"; then
    RL "| $id | $phase | \`${got:-<空>}\` | \`$want\` | PASS |"
  else
    c1_fail "C2:$id" "| $id | $phase | \`${got:-<空>}\` | \`$want\` | **FAIL** | $(printf '%s' "$hint" | cut -c1-40)… |"
  fi
done < <(grep -v '^#' "$PROD_CFG" | grep -v '^$')
RL ""

# ══ 生产面只读终断言 ══════════════════════════════════════════════════════
RL "## 生产面只读终断言（全窗 md5 快照前后比对）"
RL ""
RL "| 对象 | 窗前 md5 | 窗后 md5 | 判定 |"
RL "|---|---|---|---|"
i=0
for f in "${SNAP_FILES[@]}"; do
  am2=$(md5sum "$f" 2>/dev/null | awk '{print $1}')
  if [ "$am2" = "${SNAP_BEFORE[$i]}" ]; then RL "| ${f#$CAMP/} | ${SNAP_BEFORE[$i]} | $am2 | PASS（零改） |"
  else PROD_DIRTY=1; RL "| ${f#$CAMP/} | ${SNAP_BEFORE[$i]} | $am2 | **FAIL（被改——红线违例）** |"; fi
  i=$((i+1))
done
RL ""
RL "git 只读取证（零 git 写）：\`git status --porcelain\` 快照（本窗新增授权件=selftest+本报告，均未 add/commit）："
RL ""
RL '```'
git -C "$CAMP" status --porcelain 2>/dev/null | sed 's/^/  /' | tee -a "$REPORT"
RL '```'
RL ""

# ══ 汇总 ═════════════════════════════════════════════════════════════════
TOTAL_FAIL=$((A_FAIL + B_ASSERT_FAIL + D_ASSERT_FAIL + C_FAILN + PROD_DIRTY))
SELF_MD5=$(md5sum "${BASH_SOURCE[0]}" | awk '{print $1}')
{
  echo "## 结果汇总"
  echo
  echo "- **§A 比较器单元**: unitPass=$A_PASS unitFail=$A_FAIL（被测=生产 doctor verdict 提取体）"
  echo "- **§B 沙箱负例**: negativeDetected=$B_NEG_DET/$B_NEG_TOTAL（自反馈闭环证明成立与否）· 断言失败=$B_ASSERT_FAIL"
  echo "- **§D 降级检测负例**: degradedDetected=$D_DET/$D_NEG_TOTAL（合成 fork-active/未武装/净形/用法错四类）· 断言失败=$D_ASSERT_FAIL"
  echo "- **§C 完整性走查**: integrityChecked=$C_CHECKED · integrityFail=$C_FAILN · N/A[in-service]=$C_NA · SKIP(非 md5 锚)=$(grep -c 'C1-skip' "$REPORT")"
  echo "- **生产面只读**: PROD_DIRTY=$PROD_DIRTY（0=全程零改）"
  echo "- **selftest md5（建成后终值）**: \`$SELF_MD5\`"
  echo "- **退出码**: $([ "$TOTAL_FAIL" -eq 0 ] && echo 0（四段全绿） || echo 1（存在 FAIL，逐行如上——授权在案漂移已标注档源，未授权漂移=停窗呈报）)"
  echo
  if [ "$C_FAILN" -gt 0 ]; then
    echo "**integrityFail 清单（$C_FAILN 项）**:"
    echo
    for k in "${C_FAILS[@]}"; do echo "- \`$k\`"; done
    echo
    echo "判读：上列失配中标注「授权在案」者=GUARD-HARDENING-20261029/D121 已档漂移（现值锚以 config-034.tsv"
    echo "CFG-62/63/64 等行为准），**不作绿判、如实列示**；锁档束内副本（C1-arch 面）与未授权漂移若红=束自完整"
    echo "性破/野漂移，须停窗呈报。MANIFEST 追记未续写守卫完善窗新终值=档面缺口，建议下窗以「主会话终检重算为准」"
    echo "追记律补写。"
    echo
  fi
} >> "$REPORT"

echo "== selftest-034 汇总: A:$A_PASS/$((A_PASS+A_FAIL)) B:$B_NEG_DET/$B_NEG_TOTAL(断言失败=$B_ASSERT_FAIL) D:$D_DET/$D_NEG_TOTAL(断言失败=$D_ASSERT_FAIL) C:checked=$C_CHECKED fail=$C_FAILN na=$C_NA dirty=$PROD_DIRTY → exit $([ "$TOTAL_FAIL" -eq 0 ] && echo 0 || echo 1) =="
echo "报告: $REPORT"
echo "selftest md5: $SELF_MD5"
[ "$TOTAL_FAIL" -eq 0 ] && exit 0 || exit 1
