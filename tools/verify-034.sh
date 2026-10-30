#!/bin/bash
# verify-034.sh — 0.3.4 验收电池器（纯包装既有冻结量具原件；D115 工具复用律）
#
# 用途：引擎在役态下的验收电池（量具/口径/阈值全部冻结自 D112-②b/D113-③c/RB033 载荷单制式）。
# 模式：
#   --smoke  快速验收 = 网关第五查（EQ-09 B0）+ EQ-S（同盐 R1EQ2026 夹心）+ liter C1 512k + DE c1 + 500q 冻结帧
#   --full   全面验收 = --smoke + sd_bench 512k rep（TTFT 锚）+ B25 全形×3 + PPL golden
#   --list   列电池清单与冻结阈值，不执行（零触引擎零写）
# 用法：bash tools/verify-034.sh --smoke|--full|--list [--label L]
# 前置：引擎 health 200 + 引擎面抽查（kv_fp4 v41 终态≥4 行/fork-v4-fp4 残留=0/passthrough≥4 行/
#   BYPASS ARMED 合计≥8·refusing=0——docker logs 四机只读计数，判据与 config-034.tsv
#   CFG-46/47/48/57/58/59 同源；红=拒跑 rc=2：防对 fork 慢带（−15~19%）或未武装面白烧 GPU 载荷；
#   先 bash tools/doctor-034.sh --post-boot 定位）。
# 量具锚：调用前逐量具 md5 断言（config-034.tsv CFG-29..36 同锚），任一失配即拒跑（量具冻结红线：零改动零降门）。
# 第五查 B0（EQ-09，--smoke/--full 同跑；网关不在点火脚本/槽锁/启动链——引擎健康≠主链健康，验收须覆盖完整主链）：
#   ①网关 /health=200（/health=引擎探活透传面〔rc3.8.5+ 鉴权豁免〕：网关活∧引擎经网关活才 200；
#     引擎挂→502/代理挂→000——外部手册部署篇 §20/P6-4 诊断序「先 curl 代理口 health 再打主链入口」）
#   ②代理上游指向正确（外部手册键 UPSTREAM_BASE〔LiteLLM 类 config.yaml〕≡我栈 concurrency_proxy 键
#     UPSTREAM〔env〕；期望=引擎生产口 http://127.0.0.1:8899——8898=测试线死端口勿指；读面=/proc/<MainPID>/
#     environ 同用户只读，退化面=journal 启动横幅 0.0.0.0:PORT->UPSTREAM；两面读不到=红=无法断言即红 fail-closed）
#   ③模型清单正典=网关 /v1/models 与引擎直连 /v1/models 逐 id 一致（静态别名表旧名不出现——§21/P6-5：
#     主链入口静态别名表会列出已下线旧名且旧名照样返回结果，判断在役模型以引擎/网关侧真实清单为准）
#   三断言全 GET 轻探零推理载（零 GPU）；任一红=B0 FAIL（rc=1，非跳过非拒跑）；负例=停代理后本查必红。
#   旋钮：GW_URL（默认 http://127.0.0.1:8001）/GW_UPSTREAM_EXPECT（默认 http://127.0.0.1:8899）/
#   GW_UNIT（默认 concurrency-proxy-v2）/GW_KEY（GW_REQUIRE_AUTH=1 在役形 /v1/* 须 Bearer；值经 env 传递零入档）。
# 冻结阈值（内置，改动=停窗呈批）：
#   liter C1 tok/s：≥3700=PASS（快带）/3450-3700=WARN 边界带/≤3450=FAIL 退化告警（D105-③/D112-②b）
#   DE c1 agg_med：≥91=PASS（锚 1:91.64）/<91=FAIL（同上门）
#   500q accuracy_content：≥0.955=PASS（硬地板 478/500；带 [0.956,0.982] 中枢 0.968=D71-②）/<0.955=FAIL
#   EQ-S：EQGATE-VERDICT=GREEN (6/6)=PASS（盐 seed=R1EQ2026 内建于 eq_capture.py:28）
#   PPL golden：A/A Δtf=0.0000=PASS（确定性面；D118-② 签名逐位同）/|Δ|>0.002=FAIL/之间=WARN
#   TTFT/B25：记录+参照带分类（INFO/WARN，不作硬门——判读树属判读窗职权 D100/D103）
# 退出码：0=电池无 FAIL（WARN 允许）；1=存在 FAIL；2=用法错/量具锚失配/引擎不在线或引擎面抽查红。
# 产物：<out-dir>/VERIFY-REPORT.md（markdown 逐电池判读）+ 原始 JSON/log 同目录。
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAMP="$(cd "$HERE/.." && pwd)"
TOOLS="$CAMP/tools"
SDB_DIR="__DEPLOY_WORKSPACE__/tools/bench"
LIT="$TOOLS/conc_pr_driver.py";         A_LIT="333033ce2fae98b28187d106f7cbb14f"
DE="$TOOLS/de_c48_bench.py";            A_DE="a337f64e835a20b75f905ed5d11d6e4e"
SDB="$SDB_DIR/sd_bench.py";             A_SDB="410f543d4cc363defa66ffd54d190c9a"
GSM="$SDB_DIR/gsm8k_dsv41.py";          A_GSM="72f9197bdcee21f36e995128031a4343"
FRAME="$HOME/bench-results/gsm8k-sample500/sample500.jsonl"; A_FRAME="7e4deefc3dad17a02f56026ff43dd038"
PPLH="$CAMP/logs/S-PPL-AB-20261023/ppl_collect_native.py";   A_PPL="72395d6e4cdcb51c316f0ab6c22115b7"
EQC="$TOOLS/eqgate/eq_capture.py";      A_EQC="f8e3fa182fcac628bc10404024381925"
EQX="$TOOLS/eqgate/eq_compare.py";      A_EQX="5e62291e50eb4285a9531f3fef4e43b1"
LITDIR="$CAMP/corpus/s-eng-lit7"

MODE=""; LABEL="verify-034"
while [ $# -gt 0 ]; do case "$1" in
  --smoke|--full|--list) MODE="$1";;
  --label) shift; LABEL="${1:-$LABEL}";;
  *) :;;
esac; shift; done
PASS=0; FAIL=0; WARN=0
v_ok(){ PASS=$((PASS+1)); echo "PASS $1 $2"; echo "| $1 | PASS | $2 |" >> "$REPORT"; }
v_bad(){ FAIL=$((FAIL+1)); echo "FAIL $1 $2"; echo "| $1 | FAIL | $2 |" >> "$REPORT"; }
v_warn(){ WARN=$((WARN+1)); echo "WARN $1 $2"; echo "| $1 | WARN | $2 |" >> "$REPORT"; }
md5of(){ md5sum "$1" 2>/dev/null | awk '{print $1}'; }

battery_list(){
cat <<'EOF'
== verify-034 电池清单（冻结形=RB033 run-payloads 载荷单制式）==
[smoke]
  B0 GW5      网关第五查（EQ-09）：网关 /health 200+UPSTREAM 车道指向+清单正典 → 三断言全绿（fail-closed）
  B1 EQ-S      同盐 R1EQ2026 夹心 capture pre/post+compare  → GREEN (6/6)
  B2 liter C1  conc_pr_driver --size 524288 --conc 1 --runs 1（早值）→ ≥3700 PASS/≤3450 FAIL（3450-3700 WARN）
  B3 DE c1     de_c48_bench --tiers 1 --runs 5 --warmups 2 --arb-rounds 3 --anchors 1:91.64 → ≥91 PASS
  B4 500q      gsm8k_dsv41 --nq 500 --data sample500.jsonl（帧 7e4deefc）→ ≥0.955 地板 PASS
[full 追加]
  B5 TTFT      sd_bench --mode pr --sizes 524288 --pr-filler repeated --runs 1 → 记录+参照（RB033 118.6s/W-b 87.6s）
  B6 B25×3     同 sd_bench ×3 取中位 → 分类：≥5500 快带佐证/≤3840 慢带佐证/中间 过渡带（WARN 注记）
  B7 PPL       ppl_collect_native --panel short|long --arm A1|A2 → A/A Δtf=0.0000 PASS（>0.002 FAIL）
量具 md5 锚（任一失配拒跑）：liter 333033ce/DE a337f64e/sd_bench 410f543d/gsm8k 72f9197b/
  帧 7e4deefc/PPL 72395d6e/eq f8e3fa18+5e62291e（详见 tools/config-034.tsv CFG-29..36）
[前置门（电池前，红=拒跑 rc=2）]
  P0 health    /health=200
  P1 锚        量具 md5 全对（CFG-29..36）
  P2 引擎面    kv_fp4 mode=v41 active=False 四机≥4 行（CFG-46）/fork-v4-fp4 active=True=0（CFG-47）/
               passthrough 来源≥4 行（CFG-48）/BYPASS armed 合计≥8·refusing=0（CFG-57/58/59）
EOF
}

[ "$MODE" = --list ] && { battery_list; exit 0; }
case "$MODE" in --smoke|--full) :;; *) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; echo "用法: bash tools/verify-034.sh --smoke|--full|--list"; exit 2;; esac

# ── 前置：引擎在线 ──
H=$(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8899/health 2>/dev/null || true)
[ "$H" = 200 ] || { echo "[verify] 引擎不在线（health=$H）——先 bash tools/deploy-034.sh 起栈再验收"; exit 2; }

# ── 量具锚断言（冻结红线）──
ANCH=0
chk_anchor(){ got=$(md5of "$1"); if [ "$got" = "$2" ]; then echo "ANCHOR OK  $(basename "$1") $(echo "$2" | cut -c1-8)"; else echo "ANCHOR BAD $(basename "$1") got=${got:-<缺>} want=$2（量具冻结红线：拒跑）"; ANCH=1; fi; }
chk_anchor "$LIT" "$A_LIT"; chk_anchor "$DE" "$A_DE"; chk_anchor "$SDB" "$A_SDB"; chk_anchor "$GSM" "$A_GSM"
chk_anchor "$FRAME" "$A_FRAME"; chk_anchor "$PPLH" "$A_PPL"; chk_anchor "$EQC" "$A_EQC"; chk_anchor "$EQX" "$A_EQX"
[ "$ANCH" = 0 ] || exit 2

# ── 引擎面抽查（docker logs 四机只读计数；判据与 config-034.tsv CFG-46/47/48/57/58/59 同源；
#    红=拒跑：防对 fork-v4-fp4 慢带（−15~19%）或 BYPASS 未武装面白烧 GPU 载荷——先 doctor --post-boot 定位）──
m4(){ # m4 <pattern> [ci] —— head+02-04 worker 四机 docker logs 计数（只读；非数字归 0 防假绿）
  local pat="$1" ci="${2:-}" t=0 v g="grep -c"
  [ -n "$ci" ] && g="grep -ci"
  v=$(docker logs r3prod-head 2>&1 | $g "$pat" || true); [[ "$v" =~ ^[0-9]+$ ]] || v=0; t=$((t+v))
  for h in __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__; do
    v=$(ssh -n -o BatchMode=yes -o ConnectTimeout=8 "$h" "docker logs r3prod-worker 2>&1 | $g \"$pat\"" 2>/dev/null || true)
    [[ "$v" =~ ^[0-9]+$ ]] || v=0; t=$((t+v))
  done
  printf '%s' "$t"
}
ENG=0
eng_bad(){ ENG=1; echo "ENGFACE BAD $1"; }
V41=$(m4 'mode=v41 active=False'); FK=$(m4 'mode=fork-v4-fp4 active=True'); PT=$(m4 'is explicit: fp4-KV patches stay passthrough')
ARM=$(m4 'DSV41_PREFILL_BYPASS armed:'); REF=$(m4 'refusing to arm' ci)
[ "$V41" -ge 4 ]  && echo "ENGFACE OK   kv_fp4 v41 四机=${V41}行（CFG-46 同源）"      || eng_bad "kv_fp4 v41=${V41}行<4（CFG-46：fork-v4-fp4 退化面风险）"
[ "$FK" -eq 0 ]   && echo "ENGFACE OK   fork-v4-fp4 active=True 残留=${FK}（CFG-47）"  || eng_bad "fork-v4-fp4 残留=${FK}>0（CFG-47：慢带退化面活体）"
[ "$PT" -ge 4 ]   && echo "ENGFACE OK   v41 passthrough 来源四机=${PT}行（CFG-48）"    || eng_bad "passthrough=${PT}行<4（CFG-48：注入链断）"
[ "$ARM" -ge 8 ]  && echo "ENGFACE OK   BYPASS armed 合计=${ARM}（CFG-57/58：≥8=2/机×4）" || eng_bad "BYPASS armed=${ARM}<8（CFG-57/58：未武装——env 键 CFG-56/钩 CFG-60 面先核）"
[ "$REF" -eq 0 ]  && echo "ENGFACE OK   refusing-to-arm=${REF}（CFG-59）"              || eng_bad "refusing-to-arm=${REF}>0（CFG-59：守卫拒因，查 bypass-armed-gate 断言档）"
[ "$ENG" = 0 ] || { echo "[verify] 引擎面抽查红——拒跑电池（禁烧 GPU 载荷）；定位: bash $HERE/doctor-034.sh --post-boot"; exit 2; }

OUT="$CAMP/logs/S-034-VERIFY-$(date -u +%Y%m%d-%H%M%S)"; mkdir -p "$OUT"/{gw,perf,eqgate,bench,ppl,b25}
REPORT="$OUT/VERIFY-REPORT.md"
{ echo "# verify-034 $MODE 报告 @ $(date -u +%FT%TZ)（label=$LABEL）"; echo; echo "| 电池 | 判 | 读数 |"; echo "|---|---|---|"; } > "$REPORT"

# ── B0 网关第五查（EQ-09：引擎健康≠主链健康——网关不在点火链，验收序列须覆盖完整主链；fail-closed）──
echo "== B0 网关第五查（EQ-09 三断言）@ $(date -u +%FT%TZ) =="
GW_URL="${GW_URL:-http://127.0.0.1:8001}"; GW_EXPECT="${GW_UPSTREAM_EXPECT:-http://127.0.0.1:8899}"
GW_UNIT="${GW_UNIT:-concurrency-proxy-v2}"; GW_KEY="${GW_KEY:-}"
GW_EXPECT=${GW_EXPECT%/}; B0BAD=0
# ① 网关 /health（主链全绿透传面：网关活∧引擎经网关活才 200）
GHC=$(curl -s -m 6 -o /dev/null -w '%{http_code}' "$GW_URL/health" 2>/dev/null || true); GHC=${GHC:-000}
if [ "$GHC" = 200 ]; then echo "GW5 OK   网关 /health=200（网关活∧引擎经网关活=主链全绿）"
else B0BAD=1; echo "GW5 BAD  网关 /health=$GHC（000=代理不在/挂·502=上游引擎断——引擎健康≠主链健康；P6-4 排障序：先 curl 代理口 health 再打主链入口）"; fi
# ② UPSTREAM 车道指向（同用户 /proc 只读面为主，journal 启动横幅为退化面；两面读不到=红）
GWUP=""
GWPID=$(systemctl show "$GW_UNIT" -p MainPID --value 2>/dev/null | tr -d '[:space:]')
if [[ "$GWPID" =~ ^[0-9]+$ ]] && [ "$GWPID" -gt 0 ]; then
  GWUP=$(tr '\0' '\n' < "/proc/$GWPID/environ" 2>/dev/null | grep -m1 '^UPSTREAM=' | cut -d= -f2- || true)
fi
if [ -z "$GWUP" ]; then
  GWUP=$(journalctl -u "$GW_UNIT" --no-pager 2>/dev/null | grep -oE '0\.0\.0\.0:[0-9]+->https?://[^ ]+' | tail -1 | sed 's/^.*->//' || true)
fi
GWUP=${GWUP%/}
if [ -n "$GWUP" ] && [ "$GWUP" = "$GW_EXPECT" ]; then echo "GW5 OK   UPSTREAM=$GWUP（车道指向=引擎生产口正典）"
elif [ -n "$GWUP" ]; then B0BAD=1; echo "GW5 BAD  UPSTREAM=$GWUP ≠ $GW_EXPECT（车道指错——8898=测试线死端口/8002=脚本缺省假车道；P6-4：排障从主链底部指向往上查）"
else B0BAD=1; echo "GW5 BAD  UPSTREAM 读不到（unit=$GW_UNIT MainPID=${GWPID:-0} environ 不可读且 journal 无启动横幅）——无法断言即红（fail-closed）"; fi
# ③ 模型清单正典（引擎直连 ↔ 网关逐 id 对照；静态别名表旧名混入=红；原件落 $OUT/gw/ 供判读）
gwargs=(); [ -n "$GW_KEY" ] && gwargs=(-H "Authorization: Bearer $GW_KEY")
curl -s -m 6 "${gwargs[@]}" "$GW_URL/v1/models" > "$OUT/gw/models-via-gw.json" 2>/dev/null || true
EIDS=$(curl -s -m 6 "$GW_EXPECT/v1/models" 2>/dev/null | python3 -c 'import json,sys
try: print("\n".join(sorted(m["id"] for m in json.load(sys.stdin)["data"])))
except Exception: sys.exit(1)' 2>/dev/null || true)
GIDS=$(python3 -c 'import json,sys
try: print("\n".join(sorted(m["id"] for m in json.load(open(sys.argv[1]))["data"])))
except Exception: sys.exit(1)' "$OUT/gw/models-via-gw.json" 2>/dev/null || true)
if [ -z "$EIDS" ] || [ -z "$GIDS" ]; then B0BAD=1
  echo "GW5 BAD  模型清单不可判（引擎侧=${EIDS:+可读}·网关侧=${GIDS:+可读}——网关 401=GW_REQUIRE_AUTH 形须 GW_KEY env；原件 $OUT/gw/models-via-gw.json）"
else
  STALE=$(comm -13 <(printf '%s\n' "$EIDS") <(printf '%s\n' "$GIDS") | tr '\n' ',' | sed 's/,$//')
  MISSG=$(comm -23 <(printf '%s\n' "$EIDS") <(printf '%s\n' "$GIDS") | tr '\n' ',' | sed 's/,$//')
  if [ -z "$STALE" ] && [ -z "$MISSG" ]; then
    echo "GW5 OK   网关 /v1/models 与引擎在役清单逐 id 一致（$(printf '%s\n' "$EIDS" | wc -l) 条；静态别名旧名零出现——清单以网关为正典，P6-5）"
  else
    B0BAD=1; echo "GW5 BAD  清单不一致：网关多列=${STALE:-无}（静态别名旧名混入）/网关少列=${MISSG:-无}（在役模型缺席）——清单以网关 /v1/models 为正典（P6-5）"
  fi
fi
if [ "$B0BAD" = 0 ]; then v_ok B0-GW5 "网关三断言全绿（/health 200+UPSTREAM=$GW_EXPECT+清单一致；EQ-09 第五查——引擎健康≠主链健康缺口已闭）"
else v_bad B0-GW5 "网关第五查红（主链断面验收不绿——引擎健康≠主链健康）；排障=P6-4 序（先代理口后主链入口）/gw 包 gw-verify.sh --live（GW_URL/GW_KEY 同参）"; fi

# ── B1 EQ-S（同盐夹心）──
echo "== B1 EQ-S（pre）@ $(date -u +%FT%TZ) =="
EQ_GATE_DIR="$OUT/eqgate" python3 "$EQC" capture pre  > "$OUT/eqgate/pre.log" 2>&1; echo "eqs-pre rc=$?"

run_b2_b3(){
  echo "== B2 liter C1（早值）@ $(date -u +%FT%TZ) =="
  python3 "$LIT" --base-url http://127.0.0.1:8899/v1 --lit-dir "$LITDIR" \
    --size 524288 --conc 1 --runs 1 --measure-port 8899 \
    --json-out "$OUT/perf/liter_524288_c1_early.json" --label "$LABEL-lit-c1-early" > "$OUT/perf/lit-c1-early.log" 2>&1 \
    || { v_bad B2-liter "驱动失败（$OUT/perf/lit-c1-early.log）"; return; }
  LITV=$(python3 -c "import json;d=json.load(open('$OUT/perf/liter_524288_c1_early.json'));print(d.get('tok_s_median'))" 2>/dev/null || true)
  if [ -z "$LITV" ]; then v_bad B2-liter "读数缺失（tok_s_median 无值）"
  elif awk "BEGIN{exit !($LITV>=3700)}"; then v_ok B2-liter "tok_s=$LITV（≥3700 快带）"
  elif awk "BEGIN{exit !($LITV<=3450)}"; then v_bad B2-liter "tok_s=$LITV ≤3450 退化告警（慢带=fork-v4-fp4 退化面族；先 doctor --post-boot 核 v41 面）"
  else v_warn B2-liter "tok_s=$LITV 落 3450-3700 边界带（D105-③：如实标界+第二靴提案制式）"; fi

  echo "== B3 DE c1 @ $(date -u +%FT%TZ) =="
  mkdir -p "$OUT/bench/dec48-early"
  python3 "$DE" --arm-tag "$LABEL" --tiers 1 --runs 5 --warmups 2 --arb-rounds 3 \
    --anchors "1:91.64" --out-dir "$OUT/bench/dec48-early" > "$OUT/bench/dec48-early/de-main.log" 2>&1 \
    || { v_bad B3-DE "驱动失败（$OUT/bench/dec48-early/de-main.log）"; return; }
  DEV=$(python3 -c "
import json
d=json.load(open('$OUT/bench/dec48-early/de48_summary.json'))
t=d.get('tiers') or []
print(t[0].get('agg_med') if t else '')" 2>/dev/null || true)
  if [ -z "$DEV" ]; then v_warn B3-DE "agg_med 解析为空（判读以 de48_summary 原件为准：$OUT/bench/dec48-early/）"
  elif awk "BEGIN{exit !($DEV>=91)}"; then v_ok B3-DE "c1 agg_med=$DEV（≥91，锚 91.64）"
  else v_bad B3-DE "c1 agg_med=$DEV <91（退化告警，与 liter 门同族）"; fi
}
run_b2_b3

# ── B4 500q 冻结帧 ──
echo "== B4 500q（帧 7e4deefc）@ $(date -u +%FT%TZ) =="
timeout 5400 python3 "$GSM" --nq 500 --data "$FRAME" \
  --out-raw "$OUT/bench/gsm8k-500-raw.jsonl" --out-summary "$OUT/bench/gsm8k-500-summary.json" > "$OUT/bench/gsm8k-500.log" 2>&1
rc4=$?
if [ $rc4 -ne 0 ] && [ ! -s "$OUT/bench/gsm8k-500-summary.json" ]; then
  v_bad B4-500q "驱动 rc=$rc4（$OUT/bench/gsm8k-500.log）"
else
  ACC=$(python3 -c "import json;d=json.load(open('$OUT/bench/gsm8k-500-summary.json'));print(d['accuracy_content'])" 2>/dev/null || true)
  COR=$(python3 -c "import json;d=json.load(open('$OUT/bench/gsm8k-500-summary.json'));print('%s/%s err=%s'%(d['correct_content'],d['nq'],d['err']))" 2>/dev/null || true)
  if [ -z "$ACC" ]; then v_bad B4-500q "summary 未生成/解析失败"
  elif awk "BEGIN{exit !($ACC>=0.955)}"; then v_ok B4-500q "accuracy=$ACC（$COR；≥0.955 地板过，带 [0.956,0.982]）"
  else v_bad B4-500q "accuracy=$ACC <0.955 硬地板（478/500；带外=停窗呈报）"; fi
fi

# ── full 追加 ──
if [ "$MODE" = --full ]; then
  echo "== B5 TTFT 锚 @ $(date -u +%FT%TZ) =="
  python3 "$SDB" --mode pr --sizes 524288 --pr-filler repeated --runs 1 \
    --base-url http://127.0.0.1:8899/v1 --label "$LABEL-ttft-512k" \
    --json-out "$OUT/perf/ttft_repeated_524288.json" > "$OUT/perf/sdbench-ttft.log" 2>&1 \
    || { v_bad B5-TTFT "驱动失败"; } 
  TTFT=$(python3 -c "
import json;d=json.load(open('$OUT/perf/ttft_repeated_524288.json'))
rows=[r for r in d.get('pr',[]) if r['target']==524288]
print('%s tok/s ttft %ss'%(rows[0].get('tok_s'),rows[0].get('ttft_s')) if rows else '')" 2>/dev/null || true)
  [ -n "$TTFT" ] && v_warn B5-TTFT "$TTFT（记录+参照：RB033 4421.3 tok/s、118.6s；W-b 87.6s——不作硬门）" || v_bad B5-TTFT "读数缺失"

  echo "== B6 B25 全形×3 @ $(date -u +%FT%TZ) =="
  B25FAIL=0
  for r in 1 2 3; do
    python3 "$SDB" --mode pr --sizes 524288 --pr-filler repeated --runs 1 \
      --base-url http://127.0.0.1:8899/v1 --label "$LABEL-b25-r$r" \
      --json-out "$OUT/b25/pr_repeated_524288_$r.json" >> "$OUT/b25/pr-512k-rep.log" 2>&1 || B25FAIL=1
  done
  B25=$(python3 -c "
import json,statistics,glob
vals=[]
for f in sorted(glob.glob('$OUT/b25/pr_repeated_524288_*.json')):
    d=json.load(open(f))
    for row in d.get('pr',[]):
        if row['target']==524288 and row.get('tok_s'): vals.append(row['tok_s'])
print(statistics.median(vals) if vals else '')" 2>/dev/null || true)
  if [ "$B25FAIL" = 1 ] || [ -z "$B25" ]; then v_bad B6-B25 "驱动失败或读数缺失（$OUT/b25/）"
  elif awk "BEGIN{exit !($B25>=5500)}"; then v_warn B6-B25 "中位=$B25 tok/s（A 域≥5500 快带佐证；W-a 锚 5983.6/M2 5789.8）"
  elif awk "BEGIN{exit !($B25<=3840)}"; then v_warn B6-B25 "中位=$B25 tok/s（B-C 域≤3840 慢带佐证；era-B 带 3656.7-3657.6——与 liter 门联判）"
  else v_warn B6-B25 "中位=$B25 tok/s（过渡带 3840-5500；不作硬门）"; fi

  echo "== B7 PPL golden @ $(date -u +%FT%TZ) =="
  PPLFAIL=0
  for arm in A1 A2; do for panel in short long; do
    python3 "$PPLH" --panel $panel --arm $arm --out "$OUT/ppl/${arm}-${panel}.json" > "$OUT/ppl/${arm}-${panel}.log" 2>&1 || PPLFAIL=1
  done; done
  DTF=$(python3 -c "
import json,math
def tf(arm,panel):
    j=json.load(open(f'$OUT/ppl/{arm}-{panel}.json'))
    v=[it['nll'] for it in j['items'] if it.get('nll') is not None]
    return sum(v)/len(v) if v else float('nan')
print('%+.4f|%+.4f'%(tf('A2','short')-tf('A1','short'), tf('A2','long')-tf('A1','long')))" 2>/dev/null || true)
  if [ "$PPLFAIL" = 1 ] || [ -z "$DTF" ]; then v_bad B7-PPL "驱动失败或读数缺失（$OUT/ppl/）"
  else
    DS=$(echo "$DTF" | cut -d'|' -f1); DL=$(echo "$DTF" | cut -d'|' -f2)
    MAG=$(python3 -c "print('%.6f'%max(abs(float('$DS')),abs(float('$DL'))))" 2>/dev/null || echo 9)
    if awk "BEGIN{exit !($MAG<=0.00005)}"; then v_ok B7-PPL "A/A Δtf short=${DS} long=${DL}（=0.0000 确定性面签名）"
    elif awk "BEGIN{exit !($MAG>0.002)}"; then v_bad B7-PPL "A/A Δtf short=${DS} long=${DL} >0.002（确定性面破——停窗呈报）"
    else v_warn B7-PPL "A/A Δtf short=${DS} long=${DL}（0.0000-0.002 之间，注记复跑）"; fi
  fi
fi

# ── EQ-S post+compare（夹心后）──
echo "== B1 EQ-S（post+compare）@ $(date -u +%FT%TZ) =="
EQ_GATE_DIR="$OUT/eqgate" python3 "$EQC" capture post > "$OUT/eqgate/post.log" 2>&1; echo "eqs-post rc=$?"
python3 "$EQX" "$OUT/eqgate" > "$OUT/eqgate/compare.log" 2>&1
if grep -q "EQGATE-VERDICT=GREEN (6/6)" "$OUT/eqgate/compare.log" 2>/dev/null; then
  v_ok B1-EQS "GREEN 6/6（盐 R1EQ2026；逐字对照明细 $OUT/eqgate/compare.log）"
else
  v_bad B1-EQS "非 GREEN 6/6（$(grep -h VERDICT "$OUT/eqgate/compare.log" 2>/dev/null || echo 无判读行)）——明细 $OUT/eqgate/compare.log"
fi

echo; echo "== verify-034 $MODE 汇总: PASS=$PASS WARN=$WARN FAIL=$FAIL @ $(date -u +%FT%TZ) =="
echo "== 报告: $REPORT ；原始读数: $OUT ==" >> "$REPORT"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
