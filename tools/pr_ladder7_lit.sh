#!/usr/bin/env bash
# pr_ladder7_lit.sh — liter 口径 PR 七档阶梯量具（正典基卡；R13-a 转正件）
#
# 【世系与转正】S-ENG-EXEC-20261018 窗内变体件（tools/pr_ladder6_lit.sh 四 bug 勘误形：
#   ①run_step 经 `timeout "$@"` 执行 bash 函数恒 rc127；②run_pr warmup 512t 无冻结档
#   ValueError；③warmup 回落 filler='liter' 不认；④sparkdash 无锚档 delta=None 崩）——
#   主会话裁定 R13-a（台账§十三）转正为新基卡；本件=S-LOCKCLEAN-20261020 卫生窗落位形：
#   DRV_PY 改指 tools/ 正典位（原窗内硬编码路径）+SIZES 缺省七档（R13-a 附注：B22 实锤
#   六档缺省对七档 manifest selfcheck 拒跑 rc=5×2）+对照锚升 A6-ANCHOR-7 列（R21-a）+
#   LIT_DIR 缺省指 corpus/s-eng-lit7（七档冻结语料正典位）。pr_ladder6_lit 原件归档不删
#   （~/archive-tools-20261007/luz030-lit-ladder/）。
#
# 【直驱法定档】lit_driver.py（tools/ 正典位，与本件内嵌 DRIVER 逐字节同体〔本件每跑
#   自写回=自校验〕）可独立直驱：E11/L2OFF 窗「pr_l6lit rc127 零发包」事故的法定补跑
#   路径自窗内副本升为正典档——`python3 tools/lit_driver.py run <base> <lit_dir> <sizes>
#   <filler> <label> <json-out>` 三步法直调，无需经本壳。
#
# 【为什么存在】用户令 2026-10-17：「engram缓存大小…重复单词命中率偏高，得到的 PR
#   测试结果偏高，需采用文学作品作为对照测试」。prl6 现行锚口径 filler=repeated
#   （" the"×N）在 Engram 行缓存上命中膨胀（MiaAI-Lab#21：虚增 16-42%）——本件提供
#   liter（冻结公版文学）口径的七档阶梯，与 repeated 对照列同靴成对，构成
#   S-ENG-LADDER 实验矩阵（docs/research/S-ENG-LADDER-DESIGN-20261017.md §三/§四）。
#
# 【零触声明】tools/pr_ladder6.sh（ed303431）零触；~/dsv41-flash-dgxsparks/bench/
#   sd_bench.py 零触——liter 口径经「import 复用 + 模块级替换 build_pr_prompt」实现
#   （计时/warmup/GEN8/TTFT/JSON 形态全部同源于 sd_bench.run_pr，无复制漂移面）。
#
# 【口径（判读线冻结律：新口径=新列预登记）】
#   liter     = 冻结文学填充（corpus/s-eng-lit7/frozen，md5 见 MANIFEST.json；七档
#               互不嵌套；header 含 fresh salt 防跨档前缀缓存共享）。锚域=A6-ANCHOR-7
#               liter 列（R21-a：4674.0/5095.7/5242.0/5285.3/5071.2/4635.0/3771.2）。
#   sparkdash = 对照轮（repeated）。对照锚缺省=A6-ANCHOR-7 sparkdash 列（R21-a：
#               5522.5/6040.2/6271.3/6289.3/6048.1/5427.9/4290.0；band ±8%——MS1017-D4 先例）。
#   本件不跑 random/real 口径（sd_bench CLI 亦不认 liter——故走内联驱动器）。
#
# 【三步法】与 pr_ladder6 同构：A 首发（七档一次调用）+ B 暖重（每档单独）+
#   C 仲裁×3（轮间档序左旋换位；--runs 在 pr 模式被忽略=prl6 坑①，故必为独立调用）。
#   liter 文本确定性（同档每次同文本）：暖重/仲裁步的行缓存命中回升=口径内语义，
#   与 repeated 口径的暖重语义同位（判读只取 C 仲裁中位，A/B 为过程面）。
#
# 【量具坑（沿 prl6 四坑+E13 四勘误）】①--runs no-op；②8899 硬拒；③结果提取一律
#   python 解析 JSON、禁 grep 文本锚定；④先 mkdir 再重定向；⑤bash 函数不可经
#   timeout exec（E13 勘误①：DRIVER 落 .py 文件直调）。
#
# 【用法】
#   ARM_TAG=SENG1G bash tools/pr_ladder7_lit.sh                # 真跑（引擎须已在 :8898）
#   ARM_TAG=selftest LIT_SELFCHECK=1 bash tools/pr_ladder7_lit.sh   # 判别力自检（不连引擎）
#   ARM_TAG=selftest DRY_RUN=1 bash tools/pr_ladder7_lit.sh    # 干跑：只打印命令
# 环境变量：
#   ARM_TAG(默认 unknown)      臂标签 → logs/<ARM_TAG>/prl6lit/<ts>/
#   BASE_URL(默认 http://127.0.0.1:8898/v1)  引擎口（含 8899 即拒跑）
#   BENCH_REPO(默认 ~/dsv41-flash-dgxsparks)  sd_bench.py 所在仓（只读 import）
#   CAMPAIGN(默认 ~/luz030-opt-campaign)
#   LIT_DIR(默认 $CAMPAIGN/corpus/s-eng-lit7)  七档冻结语料根（MANIFEST.json+frozen/）
#   SIZES(默认 "8192 16384 32768 65536 131072 262144 524288")  七档（A6-ANCHOR-7 对齐；
#               R13-a 附注：缺省与 manifest 档集必须一致，否则 selfcheck 拒跑）
#   REPEATED_PASS(默认 1)      =0 只跑 liter 轮（省时；对照轮缺=判卡记缺口）
#   STEP_TIMEOUT_S(默认 900)   单次调用超时护栏
#   PR_BAND_PCT(默认 8)        带内判据 ±%（对齐 MS1017-D4 band 8.0 先例）
#   ANCHORS(默认 A6-ANCHOR-7 sparkdash 列)  sparkdash 对照轮锚（liter 轮走 liter 列锚）
#
# 【输出】$OUTDIR/：prl_{cal}_first.json / prl_{cal}_warm_{sz}.json /
#   prl_{cal}_arb{1,2,3}_{sz}.json、pr_ladder6_lit.log、water.txt、
#   prl6lit_summary.json + prl6lit_summary.tsv、PR-LADDER6-LIT-DONE 标记行。
# 【护栏】8899 硬拒；逐调用 timeout（python 文件直调层）；DRY_RUN；LIT_SELFCHECK
#   不连引擎；不起靴、不碰集群——只对 :8898 发 PR 请求；冻结语料 md5 每跑必验（败即拒跑）。
set -uo pipefail

ARM_TAG="${ARM_TAG:-unknown}"
DRY_RUN="${DRY_RUN:-0}"
LIT_SELFCHECK="${LIT_SELFCHECK:-0}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8898/v1}"
BENCH_REPO="${BENCH_REPO:-$HOME/dsv41-flash-dgxsparks}"
CAMPAIGN="${CAMPAIGN:-$HOME/luz030-opt-campaign}"
LIT_DIR="${LIT_DIR:-$CAMPAIGN/corpus/s-eng-lit7}"
SIZES="${SIZES:-8192 16384 32768 65536 131072 262144 524288}"
REPEATED_PASS="${REPEATED_PASS:-1}"
STEP_TIMEOUT_S="${STEP_TIMEOUT_S:-900}"
PR_BAND_PCT="${PR_BAND_PCT:-8}"
ANCHORS="${ANCHORS:-8192:5522.5 16384:6040.2 32768:6271.3 65536:6289.3 131072:6048.1 262144:5427.9 524288:4290.0}"

# ── 护栏：生产口绝对隔离（G5）+ 依赖自检 ─────────────────────────────────
case "$BASE_URL" in
  *8899*) echo "ABORT: BASE_URL 含 8899（生产口，G5 绝对隔离）: $BASE_URL" >&2; exit 5 ;;
esac
SD_DIR="$BENCH_REPO/bench"
[ -f "$SD_DIR/sd_bench.py" ] || { echo "ABORT: 缺 $SD_DIR/sd_bench.py" >&2; exit 5; }
[ -f "$LIT_DIR/MANIFEST.json" ] || { echo "ABORT: 缺 $LIT_DIR/MANIFEST.json（先跑 build_staging.py）" >&2; exit 5; }
command -v python3 >/dev/null || { echo "ABORT: 无 python3" >&2; exit 5; }

# ── 内联驱动器：import 复用 sd_bench + liter 口径替换 ──────────────────────
# 形态：driver.py <mode> <base_url> <lit_dir> <sizes> <filler> <label> <json-out>
#   mode = selfcheck | run
# selfcheck（不连引擎）：md5 复验 + liter 判别力断言 + 坏参数必红；
# run：warmup 512t + 六档串行（sd_bench.run_pr 同源路径），JSON 形态与 CLI 等价。
DRIVER="$(
  cat <<'PY'
import hashlib, json, os, sys
sys.path.insert(0, os.environ["SD_DIR"])
import sd_bench  # 只读 import：计时/TTFT/warmup/JSON 形态全同源

mode, base_url, lit_dir, sizes_s, filler, label, json_out = sys.argv[1:8]
sizes = [int(x) for x in sizes_s.split()] if sizes_s else []
man = json.load(open(os.path.join(lit_dir, "MANIFEST.json"), encoding="utf-8"))
_tiers = {t["target_tokens"]: t for t in man["tiers"]}

def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def _lit_ok():
    return all(_md5(os.path.join(lit_dir, "frozen", t["file"])) == t["md5"]
               for t in man["tiers"])

_orig = sd_bench.build_pr_prompt

def _lit_prompt(target_tokens, salt, filler="liter"):
    # header/footer 与 sd_bench 原口径逐字节同源（selfcheck 断言）；body=冻结文学
    # 文本截 fill*4 chars（字符基准与 repeated/random 同口径：FILLER_UNIT 4 chars）。
    header = f"[prefill-bench {salt}]\nIgnore the filler below. Reply with the single word OK.\n"
    footer = "\nReply OK."
    fill = max(1, target_tokens - sd_bench.estimate_tokens(header + footer))
    t = _tiers.get(target_tokens)
    if t is None:
        raise ValueError(f"liter 口径无冻结档 {target_tokens}（先扩 build_staging.py SIZES）")
    body = open(os.path.join(lit_dir, "frozen", t["file"]), encoding="utf-8").read()
    if len(body) < fill * 4:
        raise ValueError(f"冻结件不足：档 {target_tokens} 需 {fill*4}c 实有 {len(body)}c")
    return header + body[:fill * 4] + footer

def _patched(target_tokens, salt, filler="repeated"):
    # E13-EXEC 勘误2: run_pr warmup=512t 无冻结档原被拦截即 ValueError; warmup 回落原口径
    if filler == "liter" and target_tokens in _tiers:
        return _lit_prompt(target_tokens, salt)
    return _orig(target_tokens, salt, "repeated" if filler == "liter" else filler)

sd_bench.build_pr_prompt = _patched

def selfcheck():
    ok = True
    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        ok = ok and cond
    need(_lit_ok(), "冻结语料 md5 与 MANIFEST 逐件一致")
    need(sorted(_tiers) == sorted(sizes), "冻结档位与 SIZES 一致")
    p1, p2 = _lit_prompt(8192, "abcd1234"), _lit_prompt(8192, "abcd1234")
    need(p1 == p2, "liter 同参数逐字节可复现")
    r = _orig(8192, "abcd1234", "repeated")
    need(p1.startswith("[prefill-bench abcd1234]\n") == r.startswith("[prefill-bench abcd1234]\n"),
         "liter header 与原口径同源（salt 位）")
    need(p1.endswith("\nReply OK.") and r.endswith("\nReply OK."), "footer 同源")
    need(sd_bench.estimate_tokens(p1) >= 8192 - 64, "liter 覆盖目标 token（同基准±64）")
    body = p1.split("OK.\n", 1)[1].rsplit("\nReply OK.", 1)[0]
    need(body.count(" the the the the") == 0, "liter 非重复填充形态（' the'×4 无）")
    lines = [ln for ln in body.splitlines() if ln.strip()]
    dup = len(lines) - len(set(lines))
    import collections as _c
    max_rep = _c.Counter(lines).most_common(1)[0][1]
    need(len(lines) and dup / len(lines) < 0.02 and max_rep <= 16,
         f"liter 行重复有界（重复行 {dup}/{len(lines)}={100.0*dup/len(lines):.1f}%，"
         f"单行最多 {max_rep} 次；repeated 口径=单行数万次/占比~100% ⇒ 判别力两侧成立）")
    p8, p16 = _lit_prompt(8192, "ffff5678"), _lit_prompt(16384, "ffff5678")
    need(not p16.startswith(p8.split("OK.\n",1)[1][:2000] or "\x00"),
         "档间不嵌套（8k 文本非 16k 前缀——冻结切片游标单调）")
    pa, pb = _lit_prompt(8192, "aaaa0000"), _lit_prompt(8192, "bbbb0000")
    need(pa.split("OK.\n",1)[1] == pb.split("OK.\n",1)[1] and pa != pb,
         "跨 salt body 恒定（冻结确定性）而 prompt 异（salt 防前缀缓存共享）")
    try:
        _lit_prompt(4096, "x")
        need(False, "无冻结档必红")
    except ValueError:
        need(True, "无冻结档必红（4096 未冻结）")
    import inspect
    need(inspect.signature(_patched).parameters["filler"].default == "repeated",
         "替换层缺省=repeated（对未 patch 调用方向零漂移）")
    print("LIT-SELFCHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if mode == "selfcheck":
    sys.exit(selfcheck())
c = sd_bench.Client(base_url, "", timeout_s=max(120, 131072 * 8 // 1000))
data = {"label": label, "pr": sd_bench.run_pr(c, sizes, filler=filler)}
print(json.dumps(data, ensure_ascii=False))
if json_out:
    open(json_out, "w").write(json.dumps(data, ensure_ascii=False, indent=1))
PY
)"

# ── E13-EXEC 变体勘误（量具原件零触；本窗新件）：lit_run 为 bash 函数，
#    原 run_step 经 `timeout ... "$@"` 执行函数=127 必红（首跑实锤；S-ENG-PREP 未触此面）。
#    修法=DRIVER 落 .py 文件，三处调用改直调 python3（timeout 可跑文件）；其余逐字同源。
#    正典位（S-LOCKCLEAN-20261020 转正）：DRV_PY=tools/lit_driver.py（git 在册正典件；
#    每跑以内嵌 DRIVER 写回+md5 比对=自校验，漂移即拒跑）——原窗内硬编码路径退役。
DRV_PY="$CAMPAIGN/tools/lit_driver.py"
if [ -f "$DRV_PY" ]; then
  # 正典双源自校验：git 在册 lit_driver.py 与本件内嵌 DRIVER 逐字节比对，漂移即拒跑
  cmp -s "$DRV_PY" <(printf '%s\n' "$DRIVER") || { echo "ABORT: tools/lit_driver.py 与本件内嵌 DRIVER 漂移（正典双源不一致；先对表再跑）" >&2; exit 5; }
else
  printf '%s\n' "$DRIVER" > "$DRV_PY"
fi

# ── 自检门（每跑必过：md5 复验败即拒跑）───────────────────────────────────
run_driver() {  # run_driver <mode> <filler> <label> <json-out>；sizes 恒取 $SIZES
  local mode="$1" fil="$2" lab="${3:-}" out="${4:-}"
  SD_DIR="$SD_DIR" python3 -c "$DRIVER" "$mode" "$BASE_URL" "$LIT_DIR" "$SIZES" "$fil" "$lab" "$out"
}

if [[ "$LIT_SELFCHECK" == "1" ]]; then
  SD_DIR="$SD_DIR" python3 -c "$DRIVER" selfcheck "$BASE_URL" "$LIT_DIR" "$SIZES" liter "" "" || exit $?
fi
run_driver selfcheck liter >/dev/null || { echo "ABORT: 冻结语料 md5 复验失败（先 build_staging.py --verify-only）" >&2; exit 5; }

# ── 输出目录：先 mkdir 再重定向（坑④）────────────────────────────────────
TS="$(date +%Y%m%d-%H%M%S)"
OUTDIR="$CAMPAIGN/logs/$ARM_TAG/prl6lit/$TS"
mkdir -p "$OUTDIR"
ln -sfn "$OUTDIR" "$CAMPAIGN/logs/$ARM_TAG/prl6lit/latest" 2>/dev/null || true
LOG="$OUTDIR/pr_ladder6_lit.log"
: > "$LOG"

log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"; }
water() {
  awk '/^MemAvailable:/{printf "%dMB", int($2/1024)}' /proc/meminfo 2>/dev/null || echo "?"
}

run_step() {
  local desc="$1"; shift
  log "$desc"
  log "  CMD: $*"
  if [[ "$DRY_RUN" == "1" ]]; then
    log "  (DRY_RUN: skip)"
    return 0
  fi
  if timeout "$STEP_TIMEOUT_S" "$@" >> "$LOG" 2>&1; then
    log "  rc=0 (water=$(water))"
  else
    local rc=$?
    log "  rc=$rc  WARN: 段失败/超时(${STEP_TIMEOUT_S}s)，续跑但判定卡须记缺口"
    return "$rc"
  fi
}

lit_run() {  # lit_run <filler> <label> <json-out> <sizes...>
  local fil="$1" lab="$2" out="$3"; shift 3
  SD_DIR="$SD_DIR" python3 -c "$DRIVER" run "$BASE_URL" "$LIT_DIR" "$*" "$fil" "$lab" "$out"
}

log "== pr_ladder7_lit 启动 ARM_TAG=$ARM_TAG OUTDIR=$OUTDIR DRY_RUN=$DRY_RUN =="
log "sizes=[$SIZES] 对照锚=[$ANCHORS] band=±${PR_BAND_PCT}% repeated_pass=$REPEATED_PASS"
log "口径注: liter=冻结文学(MANIFEST md5 已验,NEW-TIER首跑建锚); sparkdash=repeated对照(1017锚); 两列互不可比"
echo "phase=pre water=$(water)" >> "$OUTDIR/water.txt"

CALS=(liter)
if [[ "$REPEATED_PASS" == "1" ]]; then CALS+=(sparkdash); fi

read -r -a SIZE_ARR <<< "$SIZES"
N=${#SIZE_ARR[@]}

for ci in "${!CALS[@]}"; do
  cal="${CALS[$ci]}"
  fil="liter"; [[ "$cal" == "sparkdash" ]] && fil="repeated"
  log "-- 口径轮 cal=$cal filler=$fil --"

  run_step "[$cal] A 首发（六档串行,每档 fresh salt）" \
    env SD_DIR="$SD_DIR" python3 "$DRV_PY" run "$BASE_URL" "$LIT_DIR" "$SIZES" "$fil" "prl6lit-$cal-first" "$OUTDIR/prl_${cal}_first.json"

  for sz in "${SIZE_ARR[@]}"; do
    run_step "[$cal] B 暖重 $sz" \
      env SD_DIR="$SD_DIR" python3 "$DRV_PY" run "$BASE_URL" "$LIT_DIR" "$sz" "$fil" "prl6lit-$cal-warm-$sz" "$OUTDIR/prl_${cal}_warm_${sz}.json"
  done

  for r in 1 2 3; do
    rot=$(( (r - 1) % N ))
    order=("${SIZE_ARR[@]:rot}" "${SIZE_ARR[@]:0:rot}")
    log "[$cal] C 仲裁轮 $r 档序(换位)= ${order[*]}"
    for sz in "${order[@]}"; do
      run_step "[$cal] C 仲裁 $r 档 $sz" \
        env SD_DIR="$SD_DIR" python3 "$DRV_PY" run "$BASE_URL" "$LIT_DIR" "$sz" "$fil" "prl6lit-$cal-arb$r-$sz" "$OUTDIR/prl_${cal}_arb${r}_${sz}.json"
      case "$sz" in 131072|262144) echo "post-arb$r-$sz water=$(water)" >> "$OUTDIR/water.txt" ;; esac
    done
  done
  echo "phase=post-$cal water=$(water)" >> "$OUTDIR/water.txt"
done

# ── 汇总判定：python 解析 JSON（坑③）─────────────────────────────────────
python3 - "$OUTDIR" "$SIZES" "$ANCHORS" "$PR_BAND_PCT" "$REPEATED_PASS" "$DRY_RUN" "$ARM_TAG" "${CALS[@]}" <<'PY' | tee -a "$LOG"
import json, os, statistics, sys

outdir, sizes_s, anchors_s, band, rep_pass, dry, arm = sys.argv[1:8]
cals = sys.argv[8:]
sizes = [int(x) for x in sizes_s.split()]
anchors = {}
for kv in anchors_s.split():
    k, _, v = kv.partition(":")
    anchors[int(k)] = float(v)
band = float(band)

def row_of(path, target):
    try:
        for r in json.load(open(path))["pr"]:
            if r["target"] == target:
                return r
    except Exception:
        pass
    return None

tsv = [("caliber\ttier\tfirst\twarm\tarb1\tarb2\tarb3\tarb_med\tspread%\tanchor\t"
        "delta%\tttft_med_s\tckpt:prompt_tokens\tverdict")]
MODEL_NOTE = "liter 列无模型外推（γ1 模型=repeated 口径拟合，不跨口径引用）"
for cal in cals:
    for sz in sizes:
        f = row_of(os.path.join(outdir, f"prl_{cal}_first.json"), sz)
        w = row_of(os.path.join(outdir, f"prl_{cal}_warm_{sz}.json"), sz)
        arbs = [row_of(os.path.join(outdir, f"prl_{cal}_arb{r}_{sz}.json"), sz) for r in (1, 2, 3)]
        g = lambda r, k: (r or {}).get(k)
        arb_vals = [r["tok_s"] for r in arbs if r and r.get("tok_s")]
        arb_med = round(statistics.median(arb_vals), 1) if arb_vals else None
        spread = (round(100.0 * (max(arb_vals) - min(arb_vals)) / arb_med, 1)
                  if len(arb_vals) == 3 and arb_med else None)
        anch = anchors.get(sz) if cal == "sparkdash" else None
        delta = (round(100.0 * (arb_med - anch) / anch, 1)
                 if (arb_med is not None and anch is not None) else None)
        ttfts = [r["ttft_s"] for r in arbs if r and r.get("ttft_s") is not None]
        ttft_med = round(statistics.median(ttfts), 3) if ttfts else None
        pts = [r["prompt_tokens"] for r in arbs if r and r.get("prompt_tokens")]
        pt = int(statistics.median(pts)) if pts else None
        if dry == "1":
            verdict = "DRY-RUN"
        elif arb_med is None:
            verdict = "MISSING(判卡记缺口)"
        elif cal == "liter":
            verdict = "NEW-TIER(首跑建锚=本靴C中位)"
        elif delta is None:
            verdict = "NEW-TIER(无锚档同靴建锚)"   # E13-EXEC 勘误4: 524288 档锚缺 delta=None 原 abs(None) 崩
        elif abs(delta) <= band:
            verdict = "IN-BAND"
        else:
            verdict = "OUT-OF-BAND(小增益须census族帐背书,G2)"
        fmt = lambda v: "-" if v is None else v
        tsv.append("\t".join(str(x) for x in (
            cal, sz, fmt(g(f, "tok_s")), fmt(g(w, "tok_s")),
            fmt(g(arbs[0], "tok_s")), fmt(g(arbs[1], "tok_s")), fmt(g(arbs[2], "tok_s")),
            fmt(arb_med), fmt(spread), fmt(anch), fmt(delta),
            fmt(ttft_med), fmt(pt), verdict)))

table = "\n".join(tsv)
print(table)
print(f"# {MODEL_NOTE}")
summary = {"arm_tag": arm, "dry_run": dry == "1", "calibers": cals, "sizes": sizes,
           "anchors_sparkdash": {str(k): v for k, v in anchors.items()},
           "band_pct": band, "repeated_pass": rep_pass == "1",
           "caliber_note": ("liter=冻结文学填充(corpus/s-eng-lit MANIFEST md5,NEW-TIER首跑建锚,"
                            "与repeated互不可比); sparkdash=repeated对照(1017新锚列,band±8%)"),
           "discipline": ("三步法=首发+暖重+仲裁×3(独立调用); 仲裁轮间档序左旋换位; "
                          "liter文本确定性=冻结件,body跨salt恒定,header salt防前缀缓存共享")}
for cal in cals:
    for sz in sizes:
        row = [t for t in tsv[1:] if t.split("\t")[0] == cal and int(t.split("\t")[1]) == sz]
        if row:
            parts = dict(zip(tsv[0].split("\t"), row[0].split("\t")))
            summary.setdefault("rows", []).append(parts)
with open(os.path.join(outdir, "prl6lit_summary.json"), "w") as fp:
    json.dump(summary, fp, ensure_ascii=False, indent=1)
with open(os.path.join(outdir, "prl6lit_summary.tsv"), "w") as fp:
    fp.write(table + "\n")
print(f"summary json/tsv -> {outdir}/prl6lit_summary.{{json,tsv}}")
PY
py_rc=$?
echo "phase=post-summary water=$(water)" >> "$OUTDIR/water.txt"
log "== pr_ladder6_lit 完（summary rc=$py_rc）=="
echo "PR-LADDER6-LIT-DONE $OUTDIR"
exit "$py_rc"
