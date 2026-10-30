#!/bin/bash
# doctor-034.sh — 0.3.4 交付态只读自排查器（自反馈=逐参数 PASS/FAIL+失败提示行）
#
# 用途：对 0.3.4 固化生产态做逐参数自排查（期望值唯一来源=tools/config-034.tsv）。
#   --preflight  点火前体检：四机连通 / r3ctn=0×4 / slotlock / 盘空间 / 镜像 digest 在机×4 /
#                MemAvailable≥100G×4（G-1 门镜像） / engram-权重身份一致性（EQ-05：CFG-68..72，
#                混配=FAIL 拒起） / config-034.tsv 时点=pre|any 全行。
#                状态感知（2026-10-29 守卫完善窗）：引擎在役（r3ctn01≠0 或 8899=200）为合法态——
#                设计态行（R3CTN×4/MEM×4/CFG-40/CFG-42）改判 N/A[in-service]（非漂移），另加 ISVC
#                在役身份核（health=200+在役容器镜像=正典 x6bake tag——野栈/错镜像仍红）；
#                点火硬前置「栈净」由 deploy-034.sh S1 在役拒起门显式承载（零降门）；
#                活体引擎面核验（kv_fp4/池指纹/横幅/ARMED）用 --post-boot。
#   --post-boot  点火后核验：引擎 health / kv_fp4 mode=v41 active=False / v41 passthrough 来源 /
#                池指纹（full=9600000/MRR=16/ctx=600000/cps=4096）/ engram 横幅 8 / 时点=any 全行。
#                引擎停机设计态时以 MV-12 修复靴正档（logs/S-034-REPAIR-20261028/）承载判读，
#                每行加 [SRC=archive] 注记（该靴=当前固化面自身的点火证据，D118-②③）。
# 用法：bash tools/doctor-034.sh --preflight
#       bash tools/doctor-034.sh --post-boot
# 【降级面检测（2026-10-29 守卫降级窗 GUARD-DEGRADED-20261029，两模式内建）】降级面清单：
#   DG1 fork-v4-fp4 active（慢带 −15~19%）/ DG2 BYPASS 未武装（首键 TTFT 74s 面）/
#   DG3 v41 键缺失（env/tp4/guards 三配置面+活体行面）/ DG4 engram 横幅<8 / DG5 池指纹漂移 /
#   DG6 镜像 digest 失配——任一命中=多行星号框大字警告（含影响定量+处置指向）+退出码=2 类
#   Exit 非绿；回退双路正典=docs/runbook/ROLLBACK-PATHS-034.md（面→路映射见其 §三）。
# 退出码：0=FAIL 数为 0 且降级面为 0（在役态设计行 N/A 不计 FAIL）；1=存在 FAIL 且无降级面；
#   2=降级面命中（降级运行=类 Exit 非绿）；3=用法错/数据源缺失（原 2；2 自本窗让位降级类）。
# 测试缝：DG_SYNTH_DIR=<目录>（仅 --post-boot 消费）——四机日志改读该目录合成档
#   （r3prod-head.log + r3prod-worker-__PROD_HOST_02_03_04__.log），只跑降级检测不执法 tsv 行；
#   selftest-034.sh §D 用此缝喂合成 fork-active/未武装日志形（生产态零触）。
# 只读声明：零写（不建文件/不落锁——slotlock 探测用只读 fd+非阻塞 flock）、零启停、零 sudo；
#   ssh 一律 -o BatchMode=yes 只读命令；docker 仅 logs/inspect/ps 读面；curl 仅 GET 探活。
# 法源：用户 2026-10-28 批文（每参数自反馈自排查）+ 2026-10-29 工单（降级运行大声警告硬性要求）
#   + D119-② + D118-③（期望值）+ D115（工具复用律）+ D116-④/D118-①②（慢带定量）
#   + MV-13/14（74.191s→1.971s=97.3%）。
#   + 任务书 EQ-05（engram-权重身份一致性断言；源=外部手册部署篇 §59+PITFALLS-AND-FAQ P9-3
#     「engram 是从权重打包出的派生物，新权重配旧 engram=静默质量劣化」；2026-10-30 0.3.4re 修复窗——
#     断言值与判序口径由 config-034.tsv CFG-68..72 行承载，本表=doctor 唯一期望值源律不变）。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$HERE/config-034.tsv"
CAMP="$(cd "$HERE/.." && pwd)"
ARCH="$CAMP/logs/S-034-REPAIR-20261028"     # MV-12 修复验证靴正档（当前固化面自身证据）
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8"
HOSTS="__PROD_HOST_01__ __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__"
PASS=0; FAIL=0

[ -f "$CFG" ] || { echo "[doctor] 数据源缺失: $CFG"; exit 3; }

# ── 结果登记 ─────────────────────────────────────────────────────────────
ok(){ PASS=$((PASS+1)); printf 'PASS %-7s %s\n' "$1" "$2"; }
bad(){ FAIL=$((FAIL+1)); printf 'FAIL %-7s %s: got=%s want=%s\n  ↳ 自反馈: %s\n' "$1" "$2" "${3:-<空>}" "$4" "$5"; }
NA=0
na(){ NA=$((NA+1)); printf 'N/A %-7s %s\n' "$1" "$2"; }
INSVC=0   # 引擎在役态标记（--preflight 分轨判读用；--post-boot 不消费）

# ── 降级面登记与大声警告（GUARD-DEGRADED-20261029；任一命中=多行星号框+退出码 2）──
BAR='********************************************************************************'
RB="$CAMP/docs/runbook/ROLLBACK-PATHS-034.md"   # 回退双路正典（A=0.3.3 全回退/B=W-d 面单差回置）
DEG=0; DEG_FACES=""
degraded(){ # degraded <DGx> <现象面> <影响定量> <处置指向> —— 大声警告：多行星号框大字
  DEG=$((DEG+1)); DEG_FACES="$DEG_FACES$1 "
  printf '%s\n' "$BAR" \
    "******  ⚠⚠⚠ 降 级 面 命 中 [$1] $2  ⚠⚠⚠" \
    "******  影响定量: $3" \
    "******  处置指向: $4" \
    "******  回退双路正典: $RB（A=0.3.3 全回退 / B=W-d 修复面调优单差回置；面→路映射=其 §三）  ******" \
    "$BAR"
}

# ── 比较器：裸串=精确相等；>=N / <=N =数值 ────────────────────────────────
verdict(){
  local got="$1" want="$2"
  if [[ "$want" == ">="* ]]; then
    [[ "$got" =~ ^[0-9]+$ ]] && (( got >= ${want#>=} ))
  elif [[ "$want" == "<="* ]]; then
    [[ "$got" =~ ^[0-9]+$ ]] && (( got <= ${want#<=} ))
  else
    [ "$got" = "$want" ]
  fi
}

# ── TSV 行执行器（id 时点 面 参数 期望值 位置 命令 提示）──────────────────
run_row(){
  local id=$1 phase=$2 face=$3 param=$4 want=$5 loc=$6 cmd=$7 hint=$8 src="${9:-}"
  local got rc
  got=$(bash -c "$cmd" </dev/null 2>/dev/null); rc=$?
  got="$(printf '%s' "$got" | head -1 | sed 's/[[:space:]]*$//')"
  if verdict "$got" "$want"; then
    ok "$id" "$face/$param${9:+ ${9}}"
  else
    bad "$id" "$face/$param" "$got" "$want" "$hint"
  fi
}

tsv_rows(){
  local want_phase=$1 src_note="${2:-}"
  while IFS=$'\t' read -r id phase face param want loc cmd hint; do
    case "$id" in ''|'#'*) continue;; esac
    [ "$phase" = "$want_phase" ] || continue
    # 在役态设计行分轨（CFG-40 栈净/CFG-42 端口闭=点火前语义；在役期望 200 由 ISVC 行承载）
    if [ "$INSVC" = 1 ] && [ "$want_phase" = pre ] && { [ "$id" = CFG-40 ] || [ "$id" = CFG-42 ]; }; then
      na "$id" "$face/$param（设计态行·在役 N/A，非漂移；在役判读=ISVC 行/--post-boot）"
      continue
    fi
    run_row "$id" "$phase" "$face" "$param" "$want" "$loc" "$cmd" "$hint" "$src_note"
  done < <(grep -v '^#' "$CFG" | grep -v '^$')
}

# ── 内建只读原语 ─────────────────────────────────────────────────────────
ssh_ro(){ if [ "$1" = __PROD_HOST_01__ ]; then shift; bash -c "$*" 2>/dev/null; else $SSH "$1" "$(shift; echo "$@")" 2>/dev/null; fi; }

r3ctn(){ local h=$1; local n; n=$(ssh_ro "$h" "docker ps -a --format '{{.Names}}' | grep -cE '^r3(prod|boot)-' || true"); [[ "$n" =~ ^[0-9]+$ ]] || n='?'; printf '%s' "$n"; }
disk_gb(){ local h=$1; ssh_ro "$h" "df -BG --output=avail / | tail -1 | tr -dc '0-9'"; }
mem_gb(){ local h=$1; ssh_ro "$h" "awk '/MemAvailable/{print int(\$2/1048576)}' /proc/meminfo"; }
img_digest(){ local h=$1; ssh_ro "$h" "docker image inspect __REGISTRY_HOST__:__REGISTRY_PORT__/dsv41-sglang-optimized:0.3.4-x6bake-20261026 --format '{{index .RepoDigests 0}}' | sed 's/.*@//'"; }

# ── 降级面检测原语（只读；DG_SYNTH_DIR=合成档测试缝〔selftest §D〕时四机日志改读本地合成档）──
gc(){ local n; n=$(grep "$@" 2>/dev/null || true); [[ "$n" =~ ^[0-9]+$ ]] || n=0; printf '%s' "$n"; }
m4(){ # m4 <pat> [grep 标志，缺省 c] —— head 本机 + 02-04 worker ssh 四机 docker logs 只读计数
  local pat="$1" fl="${2:-c}" t=0 v f h
  if [ -n "${DG_SYNTH_DIR:-}" ]; then
    for f in r3prod-head.log r3prod-worker-__PROD_HOST_02__.log r3prod-worker-__PROD_HOST_03__.log r3prod-worker-__PROD_HOST_04__.log; do
      v=$(grep -$fl "$pat" "$DG_SYNTH_DIR/$f" 2>/dev/null || true); [[ "$v" =~ ^[0-9]+$ ]] || v=0; t=$((t+v))
    done
  else
    v=$(docker logs r3prod-head 2>&1 | grep -$fl "$pat" || true); [[ "$v" =~ ^[0-9]+$ ]] || v=0; t=$((t+v))
    for h in __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__; do
      v=$($SSH -n "$h" "docker logs r3prod-worker 2>&1 | grep -$fl \"$pat\"" 2>/dev/null || true)
      [[ "$v" =~ ^[0-9]+$ ]] || v=0; t=$((t+v))
    done
  fi
  printf '%s' "$t"
}
mh(){ # mh <pat> [grep 标志] —— head 单机面（池指纹族=CFG-49..53 同源单机判读面）
  local pat="$1" fl="${2:-c}" v
  if [ -n "${DG_SYNTH_DIR:-}" ]; then v=$(grep -$fl "$pat" "$DG_SYNTH_DIR/r3prod-head.log" 2>/dev/null || true)
  else v=$(docker logs r3prod-head 2>&1 | grep -$fl "$pat" || true); fi
  [[ "$v" =~ ^[0-9]+$ ]] || v=0; printf '%s' "$v"
}

# ── 降级面扫描（GUARD-DEGRADED-20261029；清单与映射法源=用户 2026-10-29 工单+ROLLBACK-PATHS.md）──
degraded_scan_config(){ # 配置三联面+采用键/钩面（两模式恒执法；判据与 CFG-06/08/11/56/60 同源）
  local E="__ASSETS_ROOT__/dsv41/env/CBX1A-CERTM-spec1.env"
  local T="__FLEET_ENV_DIR__/.env.tp4"
  local G="__GUARDS_KIT_DIR__/guard/guards.conf"
  local S="__ASSETS_ROOT__/dsv41/adapter/sitecustomize.py"
  local g161 HM
  # DG1/DG3 · env 面（fork 行在位=DG1；v41 独立行缺失=DG3）
  if   [ "$(gc -c '^SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4$' "$E")" -gt 0 ]; then degraded DG1 "fork-v4-fp4 配置面·env（SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4 行在位）" "慢带 −15~19%（KVARM1 实测 liter C1 −15.7%/DE c1 −7.5% vs RB033；D116-④/D118-①② 双向单键证据链）" "停窗呈报勿起栈；:62 行值回 v41（或回拷 .bak 链）后 doctor 复检；引擎面=--post-boot"
  elif [ "$(gc -c '^SGLANG_DSV4_KV_LAYOUT=v41$' "$E")" -lt 1 ]; then degraded DG3 "v41 键缺失·env 面（:62 独立行不在）" "同 DG1 慢带 −15~19%（v41 钉松动=fork 退化面风险）" "停窗呈报勿起栈；env :62 回 v41 独立行后复检"
  fi
  # DG1/DG3 · tp4 面（:87）
  if   [ "$(gc -c 'SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4' "$T")" -gt 0 ]; then degraded DG1 "fork-v4-fp4 配置面·tp4 :87" "同上慢带 −15~19%" "停窗呈报；:87 EXTRA_DOCKER_ENV 值回 v41（c4f13f93 慢带形勿留）后复检"
  elif [ "$(gc -c 'SGLANG_DSV4_KV_LAYOUT=v41' "$T")" -lt 1 ]; then degraded DG3 "v41 钉缺失·tp4 面（:87）" "同 DG3" "停窗呈报；tp4 :87 回 v41 后复检"
  fi
  # DG1/DG3 · guards 面（在役位 :161 envpin）
  g161=$(sed -n '161p' "$G" 2>/dev/null | grep -o 'SGLANG_DSV4_KV_LAYOUT=[a-z0-9-]*' | head -1)
  if   [[ "$g161" == *fork-v4-fp4* ]]; then degraded DG1 "fork-v4-fp4 配置面·guards :161 envpin（got=$g161）" "同上慢带 −15~19%（与 env/tp4 三联面失耦）" "停窗呈报；在役位 __GUARDS_KIT_DIR__/guard/guards.conf :161 值回 v41（勿钉 kit/deploy 下副本）后复检"
  elif [ "$g161" != "SGLANG_DSV4_KV_LAYOUT=v41" ]; then degraded DG3 "v41 钉缺失·guards 面（:161 got=${g161:-<空>}）" "同 DG3" "停窗呈报；guards :161 envpin 回 v41 后复检"
  fi
  # DG2 · BYPASS 采用键（env :63）+ sitecustomize 钩面（dd69c59a=钩插入后锚）
  [ "$(gc -c '^DSV41_PREFILL_BYPASS=2048$' "$E")" -ge 1 ] || degraded DG2 "BYPASS 未武装·配置面（env :63 DSV41_PREFILL_BYPASS=2048 独立行缺失）" "首键 TTFT 回 74s 慢带（MV-13/14：武装面 1.971s vs 未武装 74.191s=改善 97.3% 丢失）" "停窗呈报；env :63 回 DSV41_PREFILL_BYPASS=2048 后复检；活体 armed 面=--post-boot"
  HM=$(md5sum "$S" 2>/dev/null | awk '{print $1}')
  [ "$HM" = "dd69c59a1098b735dd20e8aec1baaee9" ] || degraded DG2 "BYPASS 未武装·钩面（sitecustomize.py md5=${HM:-<空>}≠dd69c59a=钩丢失静默不武装）" "同上首键 TTFT 74s 面（45ca6e3e 旧锚=钩丢失形）" "停窗呈报；adapter sitecustomize.py 回 dd69c59a 形（正典副本 tools/bypass/ 互证）后复检"
}
degraded_scan_live(){ # 引擎活体面（post-boot 活体 / preflight 在役旁核；合成缝=合成档判读；判据与 CFG-46..59 同源）
  local V41 FK PT ARM REF BAN POOL MTT MRR CTX CPS CIMG
  V41=$(m4 'mode=v41 active=False'); FK=$(m4 'mode=fork-v4-fp4 active=True')
  PT=$(m4 "is explicit: fp4-KV patches stay passthrough")
  ARM=$(m4 'DSV41_PREFILL_BYPASS armed:'); REF=$(m4 'refusing to arm' ci)
  BAN=$(m4 'Exact nvme Engram layer=(1|14) ' Ec)
  POOL=$(mh 'DSV4 pool sizes: full=9600000, swa=125440, c4=2400000, c128=75000')
  MTT=$(mh 'max_total_num_tokens=9600000'); MRR=$(mh 'max_running_requests=16')
  CTX=$(mh 'context_len=600000'); CPS=$(mh 'chunked_prefill_size=4096')
  [ "$FK" -gt 0 ] && degraded DG1 "fork-v4-fp4 active（活体·四机计数=$FK 行>0）" "慢带 −15~19% 立即生效（KVARM1 实测 liter C1 −15.7%/DE c1 −7.5% vs RB033；verify 阈值 3450-3700 告警带）" "立即停窗呈报勿盲跑载荷；配置三联面核 doctor 降级 DG1/DG3 配置面行；处置映射=ROLLBACK-PATHS.md §三 DG1 行"
  [ "$V41" -lt 4 ] && degraded DG3 "v41 终态面缺失（活体·四机计数=$V41<4；passthrough 来源行=$PT）" "同 DG1 慢带 −15~19%（v41 未四机全量 active 或注入链断）" "停窗呈报；env/tp4/guards 三联面先核（degraded_scan_config 行）；注入链断=CFG-48 行定位"
  { [ "$ARM" -lt 8 ] || [ "$REF" -gt 0 ]; } && degraded DG2 "BYPASS 未武装/拒武装（活体·armed=$ARM/8·refusing=$REF）" "首键 TTFT 回 74s 慢带（MV-13/14 实测 74.191s→1.971s=97.3% 改善丢失；armed<8=env 键 CFG-56/钩 CFG-60 面，refusing>0=守卫拒因）" "停窗呈报；查 bypass-armed-gate 逐机断言档；配置面=doctor 降级 DG2 配置面行"
  [ "$BAN" -lt 8 ] && degraded DG4 "engram 横幅 <8（活体·四机计数=$BAN/8）" "engram 装载面异常（cache/slots/16-way/io_threads=96/packed=True 七字段核对面=正典件 [5] 段）" "停窗呈报；正典采集件 capture-boot-evidence.sh 复采 [5] 段定位分机；处置映射=ROLLBACK-PATHS.md §三 DG4 行"
  { [ "$POOL" -lt 1 ] || [ "$MTT" -lt 1 ] || [ "$MRR" -lt 1 ] || [ "$CTX" -lt 1 ] || [ "$CPS" -lt 1 ]; } && degraded DG5 "池指纹漂移（活体·full行=$POOL·mtt=$MTT·mrr=$MRR·ctx=$CTX·cps=$CPS）" "池配置面漂移（912.25 不变式守护面：full=9600000/MRR=16/ctx=600000/cps=4096；needle 599040 帧依赖 ctx）" "停窗呈报；doctor CFG-49..53 行逐面定位（env/server-args 面）；处置映射=ROLLBACK-PATHS.md §三 DG5 行"
  if [ -z "${DG_SYNTH_DIR:-}" ]; then # 合成缝无容器假设——DG6 活体面只在真活体判读（防合成态假红）
    CIMG=$(docker inspect r3prod-head --format '{{.Config.Image}}' 2>/dev/null || true)
    [ "$CIMG" = "__REGISTRY_HOST__:__REGISTRY_PORT__/dsv41-sglang-optimized:0.3.4-x6bake-20261026" ] || degraded DG6 "镜像 digest/身份面（在役容器 .Config.Image=${CIMG:-<空>}≠正典 x6bake tag）" "8899 被非正典 tag 栈占用（野栈/测试栈/镜像被覆写重推）——载荷读数全部不可信" "停窗呈报（P0 禁双靴）；镜像面=docker pull 正典 tag 后复检（IMG-1 门）；拆栈走专门窗"
  fi
}

MODE="${1:-}"
case "$MODE" in
--preflight)
  echo "== doctor-034 --preflight（点火前只读体检）@ $(date -u +%FT%TZ) =="
  # 0) 引擎状态感知分轨（在役=合法态：设计态行 N/A 判读非漂移；点火硬前置「栈净」由 deploy S1 在役拒起门显式承载=零降门）
  n01=$(r3ctn __PROD_HOST_01__); hcode=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true); hcode=${hcode:-000}
  INSVC=0; { [ "$n01" != 0 ] || [ "$hcode" = 200 ]; } && INSVC=1
  if [ "$INSVC" = 1 ]; then
    echo "[state] 引擎在役（r3ctn01=$n01 health=$hcode）——设计态行（R3CTN×4/MEM×4/CFG-40/CFG-42）按在役 N/A 判读（非漂移）；活体引擎面核验=--post-boot；点火前置=deploy-034 S1 在役拒起门"
    if [ "$hcode" = 200 ]; then ok ISVC "引擎 health=200（在役态；=CFG-42 的在役倒置判读）"; else bad ISVC "引擎 health（在役态）" "$hcode" "200" "在役但 health 非 200（崩溃/半启栈）——docker logs r3prod-head 定位；拆栈处置走专门窗（r3-stop 禁即兴）"; fi
    CIMG=$(docker inspect r3prod-head --format '{{.Config.Image}}' 2>/dev/null || true)
    if [ "$CIMG" = "__REGISTRY_HOST__:__REGISTRY_PORT__/dsv41-sglang-optimized:0.3.4-x6bake-20261026" ]; then
      ok ISVC "在役容器镜像=正典 x6bake tag（{{.Config.Image}}）"
    else
      bad ISVC "在役容器镜像 tag" "${CIMG:-<空>}" "0.3.4-x6bake-20261026" "8899 被非正典 tag 栈占用（野栈/测试栈）——呈报处置（P0 禁双靴；拆栈走专门窗）"
      degraded DG6 "镜像 digest/身份面（在役容器 .Config.Image=${CIMG:-<空>}≠正典 x6bake tag）" "8899 被非正典 tag 栈占用（野栈/测试栈/镜像被覆写重推）——载荷读数全部不可信" "停窗呈报（P0 禁双靴）；docker pull 正典 tag 后复检（IMG-1 门）；拆栈走专门窗"
    fi
  else
    echo "[state] 引擎停机设计态——设计态行全量执法"
  fi
  # 1) 四机连通（状态无关行，恒执法）
  for h in $HOSTS; do
    if [ "$($SSH "$h" 'echo ok' 2>/dev/null)" = ok ]; then ok NET "$h ssh 连通"; else bad NET "$h ssh 连通" timeout ok "检查网络/BatchMode 免密；点火硬前置"; fi
  done
  # 2) r3ctn=0 ×4（D8 制式；设计态行——在役 N/A）
  for h in $HOSTS; do n=$(r3ctn "$h"); if [ "$INSVC" = 1 ]; then na R3CTN "$h 容器数=${n}（设计态行·在役 N/A）"; elif [ "$n" = 0 ]; then ok R3CTN "$h 容器=0"; else bad R3CTN "$h 容器非净" "$n" 0 "先拆净: CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash __ASSETS_ROOT__/bin/r3-stop.sh（D8 三查）"; fi; done
  # 3) slotlock（状态无关行：在役期 HELD=另一靴冲突，恒执法）
  L="$CAMP/.slot-lock"
  if [ ! -f "$L" ]; then ok SLOT "slotlock=FREE(无锁文件)"
  elif (exec 9<"$L"; flock -n 9) 2>/dev/null; then ok SLOT "slotlock=FREE"
  else bad SLOT "slotlock 靴槽锁" HELD FREE "另一会话点火中（P0 禁双靴）：cat $L 看持有者 pid/ARM_TAG 协调，勿强拆"; fi
  # 4) 盘空间（状态无关行；阈值 30G=镜像 49G 已在库+trace cap 1G+裕量；低于即拒）
  for h in $HOSTS; do g=$(disk_gb "$h"); if [[ "$g" =~ ^[0-9]+$ ]] && (( g >= 30 )); then ok DISK "$h 盘余=${g}G"; else bad DISK "$h 盘余" "${g:-?}G" ">=30G" "清理 docker 悬空层/旧 trace 后重试；不足将阻断装载与证据落盘"; fi; done
  # 5) MemAvailable ≥100G ×4（r3-boot 链 G-1 硬门镜像前置读，零 sudo；设计态行——在役态内存由引擎合法持有=N/A）
  for h in $HOSTS; do g=$(mem_gb "$h"); if [ "$INSVC" = 1 ]; then na MEM "$h MemAvailable=${g}G（设计态行·在役 N/A——G-1 门在下次点火前复判）"; elif [[ "$g" =~ ^[0-9]+$ ]] && (( g >= 100 )); then ok MEM "$h MemAvailable=${g}G"; else bad MEM "$h MemAvailable" "${g:-?}G" ">=100G" "r3-boot 链 G-1 硬门将拒（≥100GiB）；查大进程/缓存占用，禁手 drop_caches（链内既有制式自理）"; fi; done
  # 6) 镜像 digest 在机 ×4（状态无关行；失配=降级面 DG6）
  for h in $HOSTS; do d=$(img_digest "$h"); if [ "$d" = "sha256:80e4c95712f3369ae4c087e1a879a3b63343f0469e5eb5a02aa7513b4968f7d0" ]; then ok IMG "$h RepoDigest=80e4c957…f7d0"; else bad IMG "$h 镜像 digest" "${d:-<空>}" "sha256:80e4c957…f7d0" "镜像被覆写/未 pull：docker pull __REGISTRY_HOST__:__REGISTRY_PORT__/dsv41-sglang-optimized:0.3.4-x6bake-20261026 后复检（IMG-1 门）"; degraded DG6 "镜像 digest 失配·$h（RepoDigest=${d:-<空>}≠80e4c957…f7d0）" "镜像被覆写/重推——点火将载错镜像，载荷读数不可信（registry 两版共存零删除=可重拉自愈）" "docker pull __REGISTRY_HOST__:__REGISTRY_PORT__/dsv41-sglang-optimized:0.3.4-x6bake-20261026 后复检（IMG-1 门/CFG-28）"; fi; done
  # 7) 配置面（config-034.tsv 时点=pre 与 any）——含 EQ-05 engram-权重身份一致性（CFG-68..72）：
  #    权重身份三件（分片数/config.json sha256 前16/分片总字节）+ engram 分片 mtime 对派生输入
  #    （model-00047/00048，pipeline.log 实证打包前逐件 sha256 校验的二进制输入）判序 + bin 尺寸
  #    对表（bins-manifest.json 登记值）；任一红=FAIL→deploy S1 die1 拒起（fail-closed；在役旁核同执法）
  tsv_rows pre
  tsv_rows any
  # 8) 降级面检测（GUARD-DEGRADED-20261029：配置面恒执法；在役态加扫活体面）
  degraded_scan_config
  if [ "$INSVC" = 1 ]; then
    echo "[degraded] 引擎在役——加扫活体面（fork active/v41/armed/横幅/池指纹/镜像身份）"
    degraded_scan_live
  else
    echo "[degraded] 引擎停机设计态——活体面（fork active/armed/横幅/池指纹）此态不可检，活体判读用 --post-boot；配置面已全扫"
  fi
  ;;
--post-boot)
  echo "== doctor-034 --post-boot（点火后核验/停机态档证）@ $(date -u +%FT%TZ) =="
  # 引擎在位判定（01 本机）；DG_SYNTH_DIR=合成档测试缝（selftest §D）——只跑降级检测不执法 tsv 行
  n01=$(r3ctn __PROD_HOST_01__); hcode=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true); hcode=${hcode:-000}
  if [ -n "${DG_SYNTH_DIR:-}" ]; then
    echo "[SRC=synth] DG_SYNTH_DIR=$DG_SYNTH_DIR——合成日志面（测试缝）：四机日志改读合成档，仅执法降级面检测（配置面+合成引擎面）；post/any 行不执法"
    degraded_scan_config
    degraded_scan_live
  elif [ "$n01" != 0 ] || [ "$hcode" = 200 ]; then
    echo "[SRC=live] 引擎在位（r3ctn01=$n01 health=$hcode）——活体直读"
    tsv_rows post
    tsv_rows any
    degraded_scan_config
    degraded_scan_live
  elif [ -f "$ARCH/phase2-boot/boot-evidence.log" ] && [ -f "$ARCH/phase2-boot/fidelity-gate-kvfp4.log" ]; then
    echo "[SRC=archive] 引擎停机设计态——以 MV-12 修复靴正档承载判读（$ARCH；该靴=当前固化面自身点火证据 D118-②③）"
    FG="$ARCH/phase2-boot/fidelity-gate-kvfp4.log"; BE="$ARCH/phase2-boot/boot-evidence.log"
    # 档内自描述报告行（含「出现次数」的计数行）非证据行，计数须排除（CFG-46/47 假 FAIL 修复，PACKAGE-ACCEPTANCE 缺口1）
    a(){ printf '%s' "$(grep "$1" "$2" 2>/dev/null | grep -v '出现次数' | wc -l)"; }
    ae(){ printf '%s' "$(grep -cE "$1" "$2" 2>/dev/null || true)"; }
    v41=$(a 'mode=v41 active=False' "$FG"); fork=$(a 'mode=fork-v4-fp4 active=True' "$FG")
    pt=$(a "is explicit: fp4-KV patches stay passthrough" "$FG")
    banner=$(ae 'Exact nvme Engram layer=(1|14) ' "$BE")
    pool=$(a 'DSV4 pool sizes: full=9600000, swa=125440, c4=2400000, c128=75000' "$BE")
    mtt=$(a 'max_total_num_tokens=9600000' "$BE"); mrr=$(a 'max_running_requests=16' "$BE")
    ctx=$(a 'context_len=600000' "$BE"); cps=$(a 'chunked_prefill_size=4096' "$BE")
    hlth=$(a 'health=200' "$BE")
    verdict "$v41" ">=4"    && ok CFG-46 "引擎面/kv_fp4 mode=v41 active=False=${v41}行" || bad CFG-46 "引擎面/kv_fp4 mode=v41 active=False" "$v41" ">=4" "档证 v41 行不足；引擎下次点火用 doctor --post-boot 活体重判（退化面=fork-v4-fp4 慢带 −15~19%）"
    verdict "$fork" "<=0"   && ok CFG-47 "引擎面/fork-v4-fp4 active=True 残留=${fork}" || bad CFG-47 "引擎面/fork-v4-fp4 active=True 残留" "$fork" "0" "档证含 fork 活跃态=与固化面 v41 证据矛盾；复核档源"
    verdict "$pt" ">=4"     && ok CFG-48 "引擎面/v41 passthrough 来源行=${pt}" || bad CFG-48 "引擎面/v41 passthrough 来源行" "$pt" ">=4" "注入链断证；活体复判"
    verdict "$pool" ">=1"   && ok CFG-49 "引擎面/池指纹 full=9600000 pin 行" || bad CFG-49 "引擎面/池指纹 full=9600000 pin 行" "$pool" ">=1" "池配置面漂移证；活体复判（912.25 不变式守护面）"
    verdict "$mtt" ">=1"    && ok CFG-50 "引擎面/max_total_num_tokens=9600000" || bad CFG-50 "引擎面/max_total_num_tokens=9600000" "$mtt" ">=1" "池指纹主门漂移；活体复判"
    verdict "$mrr" ">=1"    && ok CFG-51 "引擎面/max_running_requests=16" || bad CFG-51 "引擎面/max_running_requests=16" "$mrr" ">=1" "MRR 漂移；活体复判"
    verdict "$ctx" ">=1"    && ok CFG-52 "引擎面/context_len=600000" || bad CFG-52 "引擎面/context_len=600000" "$ctx" ">=1" "上下文面漂移（needle 599040 帧依赖）；活体复判"
    verdict "$cps" ">=1"    && ok CFG-53 "引擎面/chunked_prefill_size=4096" || bad CFG-53 "引擎面/chunked_prefill_size=4096" "$cps" ">=1" "prefill 分块面漂移；活体复判"
    verdict "$banner" "8"   && ok CFG-54 "引擎面/engram 横幅=8" || bad CFG-54 "引擎面/engram 横幅" "$banner" "8" "engram 装载面异常（七字段核对面见正典件 [5] 段）；活体复判"
    verdict "$hlth" ">=1"   && ok CFG-55 "引擎面/health=200(档证)" || bad CFG-55 "引擎面/health=200" "$hlth" ">=1" "档证缺 health 200 行；活体复判"
    # 降级面分类（档证态同登记表判读；ARMED 面=活体判读设计〔CFG-57 提示同源〕档证不承载=零假红）
    [ "$fork" -gt 0 ] && degraded DG1 "fork-v4-fp4 active=True 档证残留（$fork 行）" "慢带 −15~19%（与固化面 v41 证据矛盾；档源先复核）" "复核档源 logs/S-034-REPAIR-20261028/；下次点火后 --post-boot 活体重判"
    [ "$v41" -lt 4 ] && degraded DG3 "v41 终态档证行不足（$v41<4；passthrough=$pt）" "同 DG1 慢带 −15~19%" "活体复判（doctor --post-boot）；配置三联面本行下方配置扫描承载"
    { [ "$pool" -lt 1 ] || [ "$mtt" -lt 1 ] || [ "$mrr" -lt 1 ] || [ "$ctx" -lt 1 ] || [ "$cps" -lt 1 ]; } && degraded DG5 "池指纹档证漂移（full行=$pool·mtt=$mtt·mrr=$mrr·ctx=$ctx·cps=$cps）" "池配置面漂移（912.25 不变式守护面）" "活体复判（CFG-49..53 行定位）"
    [ "$banner" -lt 8 ] && degraded DG4 "engram 横幅档证 <8（$banner/8）" "engram 装载面异常（七字段核对面=正典件 [5] 段）" "活体复判（正典采集件 [5] 段定位分机）"
    degraded_scan_config
    tsv_rows any "[SRC=archive 伴随面]"
  else
    echo "[doctor] 引擎停机且 MV-12 正档缺失（$ARCH）——post-boot 不可核，全 FAIL 如实呈报"
    for id in CFG-46 CFG-47 CFG-48 CFG-49 CFG-50 CFG-51 CFG-52 CFG-53 CFG-54 CFG-55; do bad "$id" "引擎面/不可核" "<无活体无档>" "-" "先 doctor --preflight 全绿后 bash tools/deploy-034.sh 点火，再跑 --post-boot"; done
    echo "[degraded] 活体面此态不可检（无活体无档=数据源缺失非降级断言）；配置面仍全扫"
    degraded_scan_config
    tsv_rows any "[SRC=archive 伴随面]"
  fi
  ;;
*)
  sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  echo "用法: bash tools/doctor-034.sh --preflight | --post-boot"
  exit 3
  ;;
esac

echo "== 汇总: PASS=$PASS N/A=$NA FAIL=$FAIL DEGRADED=$DEG @ $(date -u +%FT%TZ) =="
if [ "$DEG" -gt 0 ]; then
  printf '%s\n' "$BAR" \
    "******  ⚠⚠⚠ 降 级 运 行 —— 降级面清单: [$DEG_FACES]（共 $DEG 面）  ⚠⚠⚠" \
    "******  本运行退出码=2（降级=类 Exit 非绿：区别于 0=全绿 / 1=仅 FAIL / 3=用法错）  ******" \
    "******  回退双路正典: $RB  ******" \
    "******  　A=0.3.3 全回退（ROLLBACK-TO-033.md 承载）/ B=W-d 修复面调优单差回置；降级面→路径映射=其 §三  ******" \
    "$BAR"
  exit 2
fi
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
