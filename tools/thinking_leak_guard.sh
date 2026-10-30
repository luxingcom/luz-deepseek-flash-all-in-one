#!/bin/bash
# thinking_leak_guard — SGLANG_DEFAULT_THINKING 泄漏面守卫（上游缺陷 host 侧规避执法件）
#
# 【法源】sgl-project/sglang issue #45614（v0.5.22 + DeepSeek-V4.1-Flash-1017 +
#   --reasoning-parser auto + SGLANG_DEFAULT_THINKING=1 时，不带 reasoning_effort 的
#   裸 chat 请求思维链整体漏进 content、reasoning_content=null）。根因=不对称：
#   prompt 侧 _apply_jinja_template 对 thinking 态回退读 SGLANG_DEFAULT_THINKING，
#   解析侧 _get_reasoning_from_request 不读 ⇒ deepseek-v41 解析器 force_reasoning=False。
#   本栈 overlay 同病在档：deploy/overlay/o12c1-prod/serving_chat.py:1794 读该键、
#   :3241 起的 _get_reasoning_from_request 全程不读（sglang environ.py:1462
#   SGLANG_DEFAULT_THINKING = EnvBool(False)——不设=关）。
#
# 【规避双腿（本件执法）】
#   腿① env unset 律：host 一切 env 面不得把 SGLANG_DEFAULT_THINKING 设为真值
#     （=0/false/no/off/空/注释=绿；其余任何值=红）。键不在=EnvBool(False)=模板
#     缺省关 ⇒ 两侧对称无泄漏。这是 issue 建议修法之一「干脆 unset」的机器面。
#   腿② 网关显式键律：裸请求由网关双键注入兜底（INJECT_ENABLE_THINKING=1 ⇒
#     chat_template_kwargs.thinking=true+enable_thinking=true，rc3.8.8 形）——
#     请求带显式键后 prompt/parse 两侧同读真值，env 键即便误设也不触发。这是
#     issue 建议修法之二「网关强制注入」的机器面（01 在役=systemd drop-in
#     inject.conf Environment=INJECT_ENABLE_THINKING=1）。
#   腿③ 客户端锚：我方自有 chat 客户端（ds_gate.py one_chat）恒带
#     chat_template_kwargs.thinking + reasoning_effort 双锚，永不发裸请求。
#
# 【三检查面】
#   R1 env 红线：扫 host env 面（在役 ARM_ENV_FILE 面 ~/migrate-assets/dsv41/env/
#     与 ~/migrate-assets/prod/、repo 面 deploy/env|prod（公开仓）/arms（战役仓）、
#     boot 脚本 r3-boot-arm.sh 双位、/etc/default/concurrency-proxy-v2 与其 unit
#     drop-in——该键对网关属异键）——任何真值声明=红。缺面=INFO 跳过不红。
#   R2 网关注入面：01 在役 drop-in inject.conf 必须 INJECT_ENABLE_THINKING=1；
#     包模板 gateway.env.template 主车道必须 =1（vl 车道钉 =0=呈裁 C3 形）。
#   R3 客户端锚：ds_gate.py 必含 chat_template_kwargs 与 reasoning_effort 两锚。
#
# 【用法】
#   tools/thinking_leak_guard.sh                     # 默认面全扫（只读）
#   tools/thinking_leak_guard.sh --env-dir DIR ...   # 追加/覆盖扫描面（--selfcheck 用）
#   tools/thinking_leak_guard.sh --selfcheck         # 红绿判别力电池（mktemp 夹具，零网络）
# 可覆盖面参数：--env-dir DIR（追加 env 扫描目录）、--boot-script F、--gw-live F
#   （01 drop-in）、--gw-template F（主车道模板）、--gw-vl-template F、--client F。
#
# 【出口】0=绿 / 1=红（任一面红）/ 2=用法错。本件零写零网络零引擎零容器零 sudo
#   （--selfcheck 仅写 mktemp 夹具）。镜像/引擎文件零触碰（长期修法随镜像补丁窗
#   吸收上游建议：_get_reasoning_from_request 回退读该 env，或 prompt 侧对
#   explicit_thinking 类解析器忽略该 env——届时本件退役或转 INFO 观察位）。
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"          # <repo>/tools
ROOT="$(cd "$HERE/.." && pwd)"                 # 仓根（公开仓=luz-034re；战役仓=luz030-opt-campaign）
MA="$HOME/migrate-assets"

ENV_DIRS=""            # --env-dir 追加（可多次）
BOOT_SCRIPTS=""        # --boot-script 追加
GW_LIVE=""             # --gw-live 覆盖（缺省 01 在役 drop-in）
GW_TEMPLATE=""         # --gw-template 覆盖
GW_VL_TEMPLATE=""      # --gw-vl-template 覆盖
CLIENT=""              # --client 覆盖
SELFTEST=0
NODEF=0                # --no-default-faces：只扫显式传入面（--selfcheck 夹具隔离用）

usage() { sed -n '2,60p' "$0" | sed 's/^# \{0,1\}//' ; }  # 头注即用法

while [ $# -gt 0 ]; do
  case "$1" in
    --env-dir)         ENV_DIRS="$ENV_DIRS $2"; shift 2 ;;
    --boot-script)     BOOT_SCRIPTS="$BOOT_SCRIPTS $2"; shift 2 ;;
    --gw-live)         GW_LIVE="$2"; shift 2 ;;
    --gw-template)     GW_TEMPLATE="$2"; shift 2 ;;
    --gw-vl-template)  GW_VL_TEMPLATE="$2"; shift 2 ;;
    --client)          CLIENT="$2"; shift 2 ;;
    --selfcheck)       SELFTEST=1; shift ;;
    --no-default-faces) NODEF=1; shift ;;
    -h|--help)         usage; exit 0 ;;
    *) echo "用法错：未知参数 $1（-h 看头注）" >&2; exit 2 ;;
  esac
done

RED=0

ok()  { echo "[TLG][OK] $*"; }
red() { echo "[TLG][RED] $*"; RED=1; }
info(){ echo "[TLG][INFO] $*"; }

# ── 值分类器：真值=红（EnvBool 语义取保守面：非明确假形即红）────────────────────
is_false_form() {  # is_false_form <值> → 0=假形（绿）/1=真值（红）
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    ""|0|false|no|off) return 0 ;;
    *)                 return 1 ;;
  esac
}

# ── R1：env 面扫描（env 文件语法：行首键=值；# 整行注释忽略；带尾注的声明行
#    不跳过——值段会被判真值（保守面：宁可误红不可漏红）──────────────────────────
scan_env_file() {  # scan_env_file <文件> → 命中红则置 RED
  local f="$1" ln val
  [ -r "$f" ] || return 0
  while IFS= read -r ln; do
    ln="${ln#"${ln%%[![:space:]]*}"}"                     # 去行首空白
    case "$ln" in
      \#*) continue ;;                                     # 整行注释
      SGLANG_DEFAULT_THINKING=*|export\ SGLANG_DEFAULT_THINKING=*)
        val="${ln#*SGLANG_DEFAULT_THINKING=}"
        if is_false_form "$val"; then
          info "$f: SGLANG_DEFAULT_THINKING=$val（假形=绿，EnvBool(False) 同效）"
        else
          red "$f: SGLANG_DEFAULT_THINKING=$val 真值=#45614 泄漏触发面（prompt 侧读、解析侧不读）——unset 或置假形"
        fi ;;
    esac
  done < "$f"
}

# ── R1（续）：脚本面扫描（boot 脚本里 -e KEY=V / export KEY=V 形，逐处分类）──────
scan_script_file() {  # scan_script_file <文件>
  local f="$1" ln occ val hits=0
  [ -r "$f" ] || return 0
  while IFS= read -r ln; do
    case "$ln" in \#*) continue ;; esac
    for occ in $(printf '%s\n' "$ln" | grep -oE 'SGLANG_DEFAULT_THINKING=[^[:space:]"'"'"']*' || true); do
      hits=$((hits+1)); val="${occ#*=}"
      if is_false_form "$val"; then
        info "$f: 出现 $occ（假形=绿）"
      else
        red "$f: 出现 $occ 真值=#45614 泄漏触发面"
      fi
    done
  done < "$f"
  [ "$hits" -eq 0 ] && info "$f: 无 SGLANG_DEFAULT_THINKING 面（绿）"
}

# ── 缺省面集（存在才扫；缺面=INFO 不红——非本机常态如实报）──────────────────────
default_env_dirs() {
  cat <<EOF
$MA/dsv41/env
$MA/prod
$ROOT/deploy/env
$ROOT/deploy/prod
$ROOT/arms
EOF
}

run_checks() {
  local d f
  echo "== thinking_leak_guard（issue #45614 host 侧规避执法）面扫开始 =="

  # R1 env 面（--no-default-faces 时只扫显式 --env-dir）
  if [ "$NODEF" = 1 ]; then
    for d in $ENV_DIRS; do
      [ -d "$d" ] || info "env 面缺位跳过：$d"
      for f in "$d"/*.env "$d"/concurrency-proxy-v2; do [ -f "$f" ] && scan_env_file "$f"; done
    done
  else
    for d in $(default_env_dirs) $ENV_DIRS /etc/default; do
      if [ -d "$d" ]; then
        for f in "$d"/*.env "$d"/concurrency-proxy-v2; do
          [ -f "$f" ] && scan_env_file "$f"
        done
      else
        info "env 面缺位跳过：$d（非本机常态不红）"
      fi
    done
  fi

  # R1 boot 脚本面（在役位 + repo 快照位；NODEF 时只扫显式 --boot-script）
  if [ "$NODEF" = 1 ]; then
    for f in $BOOT_SCRIPTS; do [ -f "$f" ] && scan_script_file "$f"; done
  else
    for f in $MA/bin/r3-boot-arm.sh $ROOT/deploy/bin/r3-boot-arm.sh $BOOT_SCRIPTS; do
      [ -f "$f" ] && scan_script_file "$f" || info "boot 脚本面缺位跳过：$f"
    done
  fi

  # R2 网关注入面
  local gwl="${GW_LIVE:-/etc/systemd/system/concurrency-proxy-v2.service.d/inject.conf}"
  local gwt="${GW_TEMPLATE:-$ROOT/tools/packages/gateway/payload/env/gateway.env.template}"
  local gwv="${GW_VL_TEMPLATE:-$ROOT/tools/packages/gateway/payload/env/gateway-vl.env.template}"
  if [ -r "$gwl" ]; then
    if grep -qE '^[[:space:]]*Environment=INJECT_ENABLE_THINKING=1([[:space:]]|$)' "$gwl"; then
      ok "R2 在役注入面绿：$gwl = INJECT_ENABLE_THINKING=1（裸请求双键兜底在役）"
    else
      red "R2 在役注入面红：$gwl 无 INJECT_ENABLE_THINKING=1（bare 请求无显式键 ⇒ #45614 面敞开）"
    fi
  else
    info "R2 在役注入面缺位跳过：$gwl（非 01 机常态；Mac 在役面=compose proxy.env，本机不可读不判）"
  fi
  if [ -r "$gwt" ]; then
    if [ "$(grep -E '^INJECT_ENABLE_THINKING=' "$gwt" | head -1 | cut -d= -f2)" = 1 ]; then
      ok "R2 包模板主车道绿：$gwt INJECT_ENABLE_THINKING=1"
    else
      red "R2 包模板主车道红：$gwt INJECT_ENABLE_THINKING≠1（主车道裸请求兜底缺省必须开）"
    fi
  else
    info "R2 包模板缺位跳过：$gwt"
  fi
  if [ -r "$gwv" ]; then
    if [ "$(grep -E '^INJECT_ENABLE_THINKING=' "$gwv" | head -1 | cut -d= -f2)" = 0 ]; then
      ok "R2 vl 模板钉 0 绿：$gwv（VL 车道呈裁 C3 形=0，非主车道不适用注入律）"
    else
      red "R2 vl 模板钉 0 破：$gwv INJECT_ENABLE_THINKING≠0（VL 车道既裁=0，变值须随呈裁重钉本守卫）"
    fi
  else
    info "R2 vl 模板缺位跳过：$gwv"
  fi

  # R3 客户端锚
  local c="${CLIENT:-$HERE/ds_gate.py}"
  if [ -r "$c" ]; then
    if grep -q 'chat_template_kwargs' "$c" && grep -q 'reasoning_effort' "$c"; then
      ok "R3 客户端锚绿：$c 恒带 chat_template_kwargs + reasoning_effort（自有 chat 流量永不裸发）"
    else
      red "R3 客户端锚红：$c 缺 chat_template_kwargs/reasoning_effort 锚（裸请求=#45614 触发形）"
    fi
  else
    info "R3 客户端缺位跳过：$c"
  fi

  echo "== 汇总：$([ $RED -eq 0 ] && echo 绿 || echo 红) =="
  return $RED
}

selfcheck() {  # 红绿判别力电池：mktemp 夹具驱动本件三面，断言退出码
  local T rc=0
  T=$(mktemp -d /tmp/tlg-sc.XXXXXX)
  ok0() { echo "[TLG-SC][OK] $*"; }
  bad() { echo "[TLG-SC][RED] $*"; rc=1; }
  expect() {  # expect <期望 rc> <描述> <<参数…>（夹具隔离：恒注 --no-default-faces，
              #   自检判别力不随宿主在役面状态漂移）
    local want="$1" why="$2"; shift 2
    local out got
    out=$(bash "$0" --no-default-faces "$@" 2>&1); got=$?
    if [ "$got" = "$want" ]; then ok0 "$why（rc=$got）"
    else bad "$why 期望 rc=$want 实得 rc=$got"; printf '%s\n' "$out" | sed 's/^/      /'; fi
  }

  # 夹具：全绿基线（env 面无键；boot 脚本无键；gw 注入=1；vl=0；客户端双锚）
  mkdir -p "$T/envdir"
  : > "$T/envdir/clean.env"
  printf 'OTHER_KEY=1\n# SGLANG_DEFAULT_THINKING=1  （注释行=非声明）\n' > "$T/envdir/comment.env"
  printf '#!/bin/bash\necho boot\n' > "$T/boot.sh"
  printf 'Environment=INJECT_ENABLE_THINKING=1\n' > "$T/inject.conf"
  printf 'INJECT_ENABLE_THINKING=1\nGW_API_KEY=x\n' > "$T/gw.template"
  printf 'INJECT_ENABLE_THINKING=0\n' > "$T/gwvl.template"
  printf 'def one_chat():\n    body = {"chat_template_kwargs": {"thinking": True}}\n    body["reasoning_effort"] = "high"\n' > "$T/client.py"

  # G 组：绿态
  expect 0 "G1 无键 env 面=绿"                    --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  printf 'SGLANG_DEFAULT_THINKING=0\n'            > "$T/envdir/z0.env";   expect 0 "G2 =0 假形=绿"        --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  rm -f "$T/envdir/z0.env"
  printf 'SGLANG_DEFAULT_THINKING=false\n'        > "$T/envdir/zf.env";   expect 0 "G3 =false 假形=绿"    --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  rm -f "$T/envdir/zf.env"
  printf 'SGLANG_DEFAULT_THINKING=\n'             > "$T/envdir/ze.env";   expect 0 "G4 空值=假形绿"      --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  rm -f "$T/envdir/ze.env"

  # R1 组：env 真值判红（值形判别力）
  for v in 1 true TRUE on yes 2; do
    printf 'SGLANG_DEFAULT_THINKING=%s\n' "$v"    > "$T/envdir/bad.env"
    expect 1 "R1 env =$v 真值判红"                --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  done
  printf 'export SGLANG_DEFAULT_THINKING=1\n'    > "$T/envdir/bad.env"
  expect 1 "R1 env export 形判红"                 --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  rm -f "$T/envdir/bad.env"
  printf '#!/bin/bash\ndocker run -e SGLANG_DEFAULT_THINKING=1 img\n' > "$T/boot-bad.sh"
  expect 1 "R1 boot 脚本 -e 真值判红"             --env-dir "$T/envdir" --boot-script "$T/boot.sh" --boot-script "$T/boot-bad.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"

  # R2 组：注入面判别力
  printf 'Environment=INJECT_ENABLE_THINKING=0\n' > "$T/inject0.conf"
  expect 1 "R2 在役注入 =0 判红"                   --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject0.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  printf 'Environment=MAX_CONCURRENCY=16\n'       > "$T/injectnone.conf"
  expect 1 "R2 在役注入缺键判红"                   --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/injectnone.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  printf 'INJECT_ENABLE_THINKING=0\nGW_API_KEY=x\n' > "$T/gw0.template"
  expect 1 "R2 主车道模板 =0 判红"                 --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw0.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  printf 'GW_API_KEY=x\n'                          > "$T/gwnone.template"
  expect 1 "R2 主车道模板缺键判红"                 --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gwnone.template" --gw-vl-template "$T/gwvl.template" --client "$T/client.py"
  printf 'INJECT_ENABLE_THINKING=1\n'              > "$T/gwvl1.template"
  expect 1 "R2 vl 模板翻 1（破呈裁钉 0）判红"      --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl1.template" --client "$T/client.py"

  # R3 组：客户端锚判别力
  printf 'def one_chat():\n    body = {"chat_template_kwargs": {"thinking": True}}\n' > "$T/client-noeffort.py"
  expect 1 "R3 客户端缺 reasoning_effort 锚判红"   --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client-noeffort.py"
  printf 'def one_chat():\n    body = {"messages": []}\n' > "$T/client-bare.py"
  expect 1 "R3 客户端裸请求形判红"                 --env-dir "$T/envdir" --boot-script "$T/boot.sh" --gw-live "$T/inject.conf" --gw-template "$T/gw.template" --gw-vl-template "$T/gwvl.template" --client "$T/client-bare.py"

  # 分类器单元面（直调）
  for v in 1 true TRUE ON yes 2 xyz; do
    if is_false_form "$v"; then bad "分类器：$v 应为真值（红）却判假形"; else ok0 "分类器：$v 判真值（红）"; fi
  done
  for v in 0 false FALSE No OFF ""; do
    if is_false_form "$v"; then ok0 "分类器：'$v' 判假形（绿）"; else bad "分类器：'$v' 应为假形（绿）却判真值"; fi
  done

  rm -rf "$T"
  echo "[TLG-SC] 汇总：$([ $rc -eq 0 ] && echo 全绿 || echo 有红)"
  return $rc
}

if [ "$SELFTEST" = 1 ]; then
  selfcheck
  exit $?
fi
run_checks
exit $?
