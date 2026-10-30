#!/bin/bash
# plainroute_guard_45525.sh — UPSTREAM-45525 规避执法守卫（spec×plain 贪心分叉路由面）
#
# 【法源】sgl-project/sglang issue #45525（[Bug] DeepSeek-V4-Flash: speculative and
#   ordinary decoding produce different greedy outputs；2026-10-21 jiapingW 提交，open
#   零评论无修复）。同 checkpoint、同前缀、T=0 下 DSPARK verify 与普通 decode 的目标
#   logits 不同、贪心 token 分叉（issue 口径：近并列 top-2 ~0.25-0.5 logit 差翻转）；
#   且同一路径重复请求结果也会翻转=责任内核未定位。规避=确定性敏感评测/对拍流量
#   路由到无 DSPARK 的 plain decode 服务（同 checkpoint 双服务对照，报告者即如此
#   对照）；常规业务面（8899 生产 spec 口）不动。
#
# 【非目标与边界】
#   - 不修内核：上游未定位责任内核，跟踪 issue 后再定补丁（见 README「退役条款」）。
#   - 不开 SGLANG_ENABLE_DETERMINISTIC_INFERENCE：RE-CERT-CARD-4 §八全形态禁键
#     （r3-gate-env-lint.sh ①面），house 已裁定不走确定性开关路线——与 issue
#     「同路径重复亦翻转」的观察一致（开关治不了非确定底噪）。
#   - 不动镜像、零容器生命周期动作。本件只读观测：md5sum/grep 文件面 +
#     docker ps/inspect/logs（BL-BYP2 门同制）+ curl /health 只读探活。
#   - plain 路径自身亦非逐位确定（issue 同路径重复翻转）——本规避消除的是
#     「spec×plain 车道差」这一变量；跨靴底噪带判读仍归 biteq_band.py 带语义。
#
# 【四面】
#   G1 参数面（离线恒跑）：①canonical env 件未被本规避改动（md5=gates-034 BL11 钉值
#     4370aab9c501cd0cfd3d89bb0137c433——规避零侵入正典面的直证）；②boot 链 plain
#     开关在位（r3-boot-arm.sh:576 SPEC 条件行逐字在档）；③prod-profile
#     PROD_SPEC_EXTRA_ARGS 无 --speculative 参（plain 服务整套沿用同参不夹带 spec）；
#     ④plain-face 参数件形态（恰 4 键且值面正典）。
#   G2 plain 活体面（状态感知）：r3plain-* 容器不在=N/A（规避未激活，INFO 不红）；
#     在=launch 面（inspect Entrypoint/Cmd/Args + docker logs）--speculative* 计数
#     必须为 0 + 8897 /health=200。红=「plain 服务不 plain」，确定性敏感流量不得发。
#   G3 生产 spec 面旁核（状态感知）：r3prod-* 在役时 head 的 launch 面应仍带
#     --speculative-algorithm DSPARK（常规业务零侵入直证）；不带=WARN 呈报
#     （生产 spec 面被人改动=上位裁量事，不判红）；不在役=INFO 跳过。
#   G4 路由面（武装执法）：DSV45525_DETERMINISM_SENSITIVE=1（评测/对拍窗武装位）时
#     DSV45525_PLAIN_BASE 必须非空、不得指 8899/8001/8888（spec/网关面），且 G2
#     须在役（武装而 plain 不在=车道落空，fail-closed）。未武装=INFO 跳过。
#
# 【用法】
#   tools/upstream/dsp45525-plainroute/plainroute_guard_45525.sh            # 默认面全扫（只读）
#   tools/upstream/dsp45525-plainroute/plainroute_guard_45525.sh --selfcheck
# 可覆盖面参数（--selfcheck 夹具隔离用）：--canonical-env F --canonical-md5 M
#   --boot-arm F --prod-profile F --plain-face F --plain-port N --plain-prefix P
#   --docker-bin PATH --curl-bin PATH --armed-plain-base V --no-default-faces
#   （--no-default-faces：只检显式传入/当前 env 面，跳过缺省路径面）
#
# 【出口】0=全绿或状态感知 N/A / 1=任一面红 / 2=用法错。
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"          # <repo>/tools/upstream/dsp45525-plainroute
MA="${HOME}/migrate-assets"

CANONICAL_ENV=""
CANONICAL_MD5=""
BOOT_ARM=""
PROD_PROFILE=""
PLAIN_FACE=""
PLAIN_PORT=""
PLAIN_PREFIX=""
DOCKER_BIN=""
CURL_BIN=""
ARMED_BASE="__UNSET__"
NODEF=0
SELFTEST=0

usage() { sed -n '2,48p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --canonical-env)     CANONICAL_ENV="$2"; shift 2 ;;
    --canonical-md5)     CANONICAL_MD5="$2"; shift 2 ;;
    --boot-arm)          BOOT_ARM="$2"; shift 2 ;;
    --prod-profile)      PROD_PROFILE="$2"; shift 2 ;;
    --plain-face)        PLAIN_FACE="$2"; shift 2 ;;
    --plain-port)        PLAIN_PORT="$2"; shift 2 ;;
    --plain-prefix)      PLAIN_PREFIX="$2"; shift 2 ;;
    --docker-bin)        DOCKER_BIN="$2"; shift 2 ;;
    --curl-bin)          CURL_BIN="$2"; shift 2 ;;
    --armed-plain-base)  ARMED_BASE="$2"; shift 2 ;;
    --no-default-faces)  NODEF=1; shift ;;
    --selfcheck)         SELFTEST=1; shift ;;
    -h|--help)           usage; exit 0 ;;
    *) echo "[PR45525][用法] 未知参数 $1（-h 看头注）" >&2; exit 2 ;;
  esac
done

[ -z "$CANONICAL_ENV" ]  && CANONICAL_ENV="$MA/dsv41/env/CBX1A-CERTM-spec1.env"
[ -z "$CANONICAL_MD5" ]  && CANONICAL_MD5="4370aab9c501cd0cfd3d89bb0137c433"
[ -z "$BOOT_ARM" ]       && BOOT_ARM="$MA/bin/r3-boot-arm.sh"
[ -z "$PROD_PROFILE" ]   && PROD_PROFILE="$MA/prod/prod-profile.env"
[ -z "$PLAIN_FACE" ]     && PLAIN_FACE="$HERE/plain-face-45525.env"
[ -z "$PLAIN_PORT" ]     && PLAIN_PORT="8897"
[ -z "$PLAIN_PREFIX" ]   && PLAIN_PREFIX="r3plain"
[ -z "$DOCKER_BIN" ]     && DOCKER_BIN="docker"
[ -z "$CURL_BIN" ]       && CURL_BIN="curl"

RED=0
ok()   { echo "[PR45525][OK] $*"; }
red()  { echo "[PR45525][RED] $*"; RED=1; }
info() { echo "[PR45525][INFO] $*"; }
warn() { echo "[PR45525][WARN] $*"; }
miss() { # 缺面=跳过（--no-default-faces 或显式路径不存在）
  echo "[PR45525][INFO] $1（面缺失=跳过不红）"
}

# docker 只读封装（selfcheck 用 shim 替换）
dk_names()  { "$DOCKER_BIN" ps -a --format '{{.Names}}' 2>/dev/null || true; }
dk_launch() { "$DOCKER_BIN" inspect "$1" --format '{{.Config.Entrypoint}} {{.Config.Cmd}} {{.Args}}' 2>/dev/null || true; }
dk_logs()   { "$DOCKER_BIN" logs "$1" 2>&1 || true; }
http_code() { "$CURL_BIN" -s -m 4 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true; }

SPEC_COND_LINE='[[ "$SPEC" == "1" ]] && SERVER_ARGS+=(--speculative-algorithm DSPARK) || info "SPEC=0"'

# ── G1 参数面 ─────────────────────────────────────────────────────────────
g1() {
  echo "== G1 参数面（离线恒跑）=="
  # ① canonical env 未被改动（BL11 钉值互证）
  if [ -r "$CANONICAL_ENV" ]; then
    m=$(md5sum "$CANONICAL_ENV" | awk '{print $1}')
    if [ "$m" = "$CANONICAL_MD5" ]; then
      ok "G1① canonical env 原样（md5=${m:0:8}…=BL11 钉值）——规避零侵入正典 env 面"
    else
      red "G1① canonical env md5=$m ≠ 钉值 $CANONICAL_MD5（正典面漂移：plain 派生基准失效且 BL11 门将红；停窗呈报，勿以本规避名义改 canonical）"
    fi
  else
    miss "G1① canonical env 不可读：$CANONICAL_ENV"
  fi
  # ② boot 链 plain 开关在位
  if [ -r "$BOOT_ARM" ]; then
    if grep -Fq "$SPEC_COND_LINE" "$BOOT_ARM"; then
      ok "G1② boot 链 plain 开关在位（SPEC≠1 ⇒ 不加 --speculative-algorithm DSPARK；ARM 链内置，零镜像改动）"
    else
      red "G1② boot 链 SPEC 条件行失配（r3-boot-arm.sh:576 形）——plain 开关被改动，SPEC=0 不再保证普通 decode 路径；停窗呈报"
    fi
  else
    miss "G1② boot 链脚本不可读：$BOOT_ARM"
  fi
  # ③ PROD_SPEC_EXTRA_ARGS 无 --speculative 参
  if [ -r "$PROD_PROFILE" ]; then
    line=$(grep -m1 '^PROD_SPEC_EXTRA_ARGS=' "$PROD_PROFILE" || true)
    if [ -z "$line" ]; then
      miss "G1③ prod-profile 无 PROD_SPEC_EXTRA_ARGS 键"
    elif printf '%s' "$line" | grep -q -- '--speculative'; then
      red "G1③ PROD_SPEC_EXTRA_ARGS 携带 --speculative 参：plain 窗若沿用该参包将把 spec 夹带进 plain 服务；先清参再开窗"
    else
      ok "G1③ PROD_SPEC_EXTRA_ARGS 无 --speculative 参（plain 服务可整套沿用同参，与生产仅差 spec 一面）"
    fi
  else
    miss "G1③ prod-profile 不可读：$PROD_PROFILE"
  fi
  # ④ plain-face 参数件形态（恰 4 键且值面正典）
  if [ -r "$PLAIN_FACE" ]; then
    n=$(grep -c '^[A-Za-z_][A-Za-z0-9_]*=' "$PLAIN_FACE")
    a=$(grep -c '^CTN_PREFIX=r3plain$' "$PLAIN_FACE")
    b=$(grep -c "^API_PORT=$PLAIN_PORT\$" "$PLAIN_FACE")
    c=$(grep -c '^SPEC=0$' "$PLAIN_FACE")
    d=$(grep -c "^DSV45525_PLAIN_BASE=http://127.0.0.1:$PLAIN_PORT\$" "$PLAIN_FACE")
    if [ "$n" = 4 ] && [ "$a" = 1 ] && [ "$b" = 1 ] && [ "$c" = 1 ] && [ "$d" = 1 ]; then
      ok "G1④ plain-face 参数件形态正典（4 键：CTN_PREFIX=r3plain/API_PORT=$PLAIN_PORT/SPEC=0/DSV45525_PLAIN_BASE）"
    else
      red "G1④ plain-face 参数件形态漂移（键计数=$n 期望 4；CTN_PREFIX=$a API_PORT=$b SPEC=$c PLAIN_BASE=$d 各期望 1）——激活制式与守卫判据脱钩；对照本目录 README 复原"
    fi
  else
    miss "G1④ plain-face 参数件不可读：$PLAIN_FACE"
  fi
}

# ── G2 plain 活体面（状态感知）+ G3 生产 spec 旁核 ────────────────────────
g2g3() {
  echo "== G2 plain 活体面（状态感知）=="
  names=$(dk_names)
  n_plain=$(printf '%s\n' "$names" | grep -c "^${PLAIN_PREFIX}-" || true)
  if [ "$n_plain" = 0 ]; then
    info "G2 plain 服务未部署（${PLAIN_PREFIX}-* 容器计数=0）——规避未激活=N/A 不红；激活制式见本目录 README（专门窗：source plain-face-45525.env 走既有 boot 链）"
    G2_UP=0
  else
    G2_UP=1
    head_ctn="${PLAIN_PREFIX}-head"
    if ! printf '%s\n' "$names" | grep -q "^${head_ctn}$"; then
      red "G2 ${PLAIN_PREFIX}-* 容器在（$n_plain 个）但 ${head_ctn} 不在——命名面异常，launch 面无法断言；停窗呈报"
    else
      launch=$(dk_launch "$head_ctn")
      c1=$(printf '%s' "$launch" | grep -c -- '--speculative' || true)
      c2=$(dk_logs "$head_ctn" | grep -c -- '--speculative' || true)
      if [ "$c1" = 0 ] && [ "$c2" = 0 ]; then
        ok "G2 plain head launch 面零 --speculative（inspect=$c1 logs=$c2）——真 plain decode 路径，确定性敏感流量可发"
      else
        red "G2 plain head launch 面携带 --speculative（inspect=$c1 logs=$c2）——「plain 服务不 plain」：该口不得承载确定性敏感流量；查开窗参数（SPEC 必须=0）"
      fi
      hc=$(http_code "http://127.0.0.1:${PLAIN_PORT}/health")
      if [ "$hc" = 200 ]; then
        ok "G2 plain 口 :$PLAIN_PORT /health=200"
      else
        red "G2 plain 口 :$PLAIN_PORT /health=$hc（期望 200）——服务未就绪或口面错指；确定性敏感流量不得发"
      fi
    fi
  fi
  echo "== G3 生产 spec 面旁核（状态感知）=="
  n_prod=$(printf '%s\n' "$names" | grep -c '^r3prod-' || true)
  if [ "$n_prod" = 0 ]; then
    info "G3 生产栈未在役（r3prod-* 计数=0）——旁核跳过"
  elif ! printf '%s\n' "$names" | grep -q '^r3prod-head$'; then
    info "G3 r3prod-* 在（$n_prod 个）但 r3prod-head 不在——旁核跳过（命名面异常另呈报）"
  else
    pl=$(dk_launch r3prod-head)
    s=$(printf '%s' "$pl" | grep -c -- '--speculative-algorithm DSPARK' || true)
    if [ "$s" -ge 1 ]; then
      ok "G3 生产 head 仍带 --speculative-algorithm DSPARK——常规业务面（8899 spec 口）零侵入，规避只做旁路不改主干"
    else
      warn "G3 生产 head launch 面未见 --speculative-algorithm DSPARK——生产 spec 面已被改动（非本规避所为；常规业务是否去 spec 属上位裁量），如实呈报主会话"
    fi
  fi
}

# ── G4 路由面（武装执法）──────────────────────────────────────────────────
g4() {
  echo "== G4 路由面（武装执法）=="
  armed="${DSV45525_DETERMINISM_SENSITIVE:-0}"
  if [ "$armed" != 1 ]; then
    info "G4 未武装（DSV45525_DETERMINISM_SENSITIVE=${armed:-空}）——路由面跳过；评测/对拍窗开跑前须 =1（fail-closed）"
    return 0
  fi
  base="$ARMED_BASE"
  [ "$base" = "__UNSET__" ] && base="${DSV45525_PLAIN_BASE:-}"
  if [ -z "$base" ]; then
    red "G4 已武装但 DSV45525_PLAIN_BASE 为空——确定性敏感流量无路由锚即会落回缺省口（ds_gate 缺省 8898/de_c48 缺省 8899=spec 生产口）；先 source 本目录 plain-face-45525.env 再开窗"
    return 0
  fi
  if printf '%s' "$base" | grep -Eq ':(8899|8001|8888)(/|$)'; then
    red "G4 DSV45525_PLAIN_BASE=$base 指向 8899（spec 生产口）/8001（网关→8899）/8888（boot.py 缺省）之一——确定性敏感流量禁指 spec/网关面（issue #45525 正是 spec×plain 车道分叉）；改指 plain 口 :$PLAIN_PORT"
    return 0
  fi
  if [ "${G2_UP:-0}" != 1 ]; then
    red "G4 已武装且路由锚=$base 合规，但 plain 服务未在役（G2=N/A）——车道落空；先按激活制式起 plain 服务再发确定性敏感流量"
    return 0
  fi
  ok "G4 武装态路由合规：DSV45525_PLAIN_BASE=$base（plain 口 :$PLAIN_PORT 在役）"
}

# ── selfcheck（离线红绿电池：mktemp 夹具 + docker/curl shim，零网络零容器）──
selfcheck() {
  local T rc_fail=0 rc_pass=0
  T="$(mktemp -d)" || { echo "[PR45525][SELFTEST] mktemp 失败"; exit 1; }
  # canonical/boot/profile/face 夹具
  echo "k=v" > "$T/canon.env"
  echo "$SPEC_COND_LINE" > "$T/boot.sh"
  printf 'PROD_SPEC_EXTRA_ARGS="--prefill-decode-interval 16"\n' > "$T/profile.env"
  cp "$PLAIN_FACE" "$T/face.env"
  canon_md5=$(md5sum "$T/canon.env" | awk '{print $1}')
  # docker shim：两态（plain 无 / plain 有且干净），curl shim 恒 200
  printf '#!/bin/sh\ncase "$1" in\n  ps) [ "${SHIM_PLAIN:-0}" = 1 ] && echo "r3plain-head" || echo "";;\n  inspect) echo "/bin/bash boot.sh";;\n  logs) echo "launch: python -m sglang.launch_server --port 8897";;\nesac\nexit 0\n' > "$T/docker.sh"
  printf '#!/bin/sh\necho 200\n' > "$T/curl.sh"
  chmod +x "$T/docker.sh" "$T/curl.sh"
  # 用例 1：全绿基线（canonical 亲值+boot 行+无 spec 参+face 正典+无容器）
  out=$(bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1)
  if [ "$?" = 0 ] && printf '%s' "$out" | grep -q '\[OK\] G1①' && printf '%s' "$out" | grep -q 'G2 plain 服务未部署'; then
    echo "[PR45525][SELFTEST] 用例1 全绿基线：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例1 全绿基线：FAIL（输出：$out）"; rc_fail=$((rc_fail+1)); fi
  # 用例 2：canonical md5 漂移→红
  out=$(bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "deadbeefdeadbeefdeadbeefdeadbeef" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '\[RED\] G1①'; then
    echo "[PR45525][SELFTEST] 用例2 canonical 漂移必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例2 canonical 漂移必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 3：boot 链 SPEC 行失配→红（正法开关被动过=判别力负例）
  echo "SPEC=1 always" > "$T/boot-bad.sh"
  out=$(bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot-bad.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '\[RED\] G1②'; then
    echo "[PR45525][SELFTEST] 用例3 plain 开关失配必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例3 plain 开关失配必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 4：EXTRA 参夹带 --speculative→红
  printf 'PROD_SPEC_EXTRA_ARGS="--speculative-algorithm DSPARK"\n' > "$T/profile-bad.env"
  out=$(bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile-bad.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '\[RED\] G1③'; then
    echo "[PR45525][SELFTEST] 用例4 EXTRA 夹带 spec 必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例4 EXTRA 夹带 spec 必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 5：plain-face 形态漂移→红
  printf 'CTN_PREFIX=r3plain\nAPI_PORT=8897\nSPEC=1\n' > "$T/face-bad.env"
  out=$(bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face-bad.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '\[RED\] G1④'; then
    echo "[PR45525][SELFTEST] 用例5 plain-face 漂移必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例5 plain-face 漂移必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 6：plain 容器在+干净 launch+health 200→G2 OK
  out=$(SHIM_PLAIN=1 bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q 'G2 plain head launch 面零 --speculative'; then
    echo "[PR45525][SELFTEST] 用例6 plain 在役干净面：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例6 plain 在役干净面：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 7：plain 容器 launch 夹带 --speculative→红（「plain 不 plain」负例）
  printf '#!/bin/sh\ncase "$1" in\n  ps) [ "${SHIM_PLAIN:-0}" = 1 ] && echo "r3plain-head" || echo "";;\n  inspect) echo "--speculative-algorithm DSPARK";;\n  logs) echo "serve --speculative-algorithm DSPARK";;\nesac\nexit 0\n' > "$T/docker-bad.sh"
  chmod +x "$T/docker-bad.sh"
  out=$(SHIM_PLAIN=1 bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker-bad.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'G2 plain head launch 面携带'; then
    echo "[PR45525][SELFTEST] 用例7 plain 不 plain 必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例7 plain 不 plain 必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 8：武装+路由锚空→红（fail-closed 判别力）
  out=$(env DSV45525_DETERMINISM_SENSITIVE=1 DSV45525_PLAIN_BASE= bash "$0" \
        --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '\[RED\] G4.*PLAIN_BASE 为空'; then
    echo "[PR45525][SELFTEST] 用例8 武装无锚必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例8 武装无锚必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 9：武装+锚指 8899→红
  out=$(env DSV45525_DETERMINISM_SENSITIVE=1 DSV45525_PLAIN_BASE=http://127.0.0.1:8899 bash "$0" \
        --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '\[RED\] G4.*8899'; then
    echo "[PR45525][SELFTEST] 用例9 锚指 spec 口必红：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例9 锚指 spec 口必红：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  # 用例 10：武装+锚合规+plain 在役→绿（整链正例）
  out=$(env DSV45525_DETERMINISM_SENSITIVE=1 DSV45525_PLAIN_BASE=http://127.0.0.1:8897 \
        SHIM_PLAIN=1 bash "$0" --canonical-env "$T/canon.env" --canonical-md5 "$canon_md5" \
        --boot-arm "$T/boot.sh" --prod-profile "$T/profile.env" --plain-face "$T/face.env" \
        --docker-bin "$T/docker.sh" --curl-bin "$T/curl.sh" 2>&1); rc=$?
  if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q 'G4 武装态路由合规'; then
    echo "[PR45525][SELFTEST] 用例10 武装整链正例：PASS"; rc_pass=$((rc_pass+1))
  else echo "[PR45525][SELFTEST] 用例10 武装整链正例：FAIL（rc=$rc）"; rc_fail=$((rc_fail+1)); fi
  rm -rf "$T"
  echo "[PR45525][SELFTEST] 判别力电池：$rc_pass PASS / $rc_fail FAIL（10 例，离线零网络零容器）"
  [ "$rc_fail" = 0 ] || exit 1
}

if [ "$SELFTEST" = 1 ]; then selfcheck; exit $?; fi

g1
g2g3
g4
if [ "$RED" = 0 ]; then
  echo "[PR45525] 守卫全绿（含状态感知 N/A 面）"
  exit 0
else
  echo "[PR45525] 守卫存在红面（见上；红=确定性敏感流量不得开跑，逐行处置后复跑）"
  exit 1
fi
