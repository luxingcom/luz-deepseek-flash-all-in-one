#!/usr/bin/env bash
# boot_sentinel.sh — F-9 boot 低速哨兵（BOOT-LOWSPEED-ROOTCAUSE-20261010 §4.1 规格，b433d01；
#   总卡 701d2d3 §三 F-9 行登记；W2 每靴试点、W3 验收门 0.7×锚收口）
#
# 【为什么存在】「反复 boot 掉低速」四族分解（调查员 §3.1）中主族 Fam-A=V4.1 流量空窗
#   ≥8h 后首靴 prefill 慢模式（KV-V41 723-1,035 + W1-B1 801-821 两例同签名）——出生即慢、
#   整靴恒慢、重启即愈，历史上靠人眼看窗才发现。本件=把「boot 后 prefill 健康」变成
#   每靴自动采测+横幅+台账的固定步，慢靴第一时间 fail-visible。
#
# 【量具口径（与 W1 探针轮形一致=可比）】sd_bench --mode pr --pr-filler real --sizes 32768，
#   3 发独立调用取中位（prl6 坑①：--runs 在 pr 模式被忽略→3 发=3 次调用）；每调用内建
#   uuid fresh salt（PR-ANCHOR-CONTAMINATION 律）；速率=链 A=prompt_tokens/TTFT（=sd_bench
#   tok_s 键；禁 calib 5.442 换算）。首发单独登记 cold_first 读数（判别数据，勿弃——调查员 §4.1）。
#
# 【判档】对照 per-form 锚表（tools/boot_sentinel_anchors.tsv；锚值纪律=历史健康靴同口径
#   读数带保守下沿，取不到=UNKNOWN 不臆造）：≥0.7×锚=GREEN；0.5-0.7×=WARN；<0.5×锚=[SLOWBOOT] 横幅。
#
# 【fail-visible 不 fail-safe（红线）】慢=横幅+台账，**不 abort、不自动重启**——重启/换靴
#   决策归人/呈裁（U1 教训：未验证绿的环境里自动动作放大问题，FABRIC-SELFHEAL §〇.6 律）。
#   退出码：0=判读完成（任何 verdict 含 SLOWBOOT/ANCHOR-UNKNOWN）；5=守卫红（8899/缺件/无 ARM_TAG）；
#   6=health 不达；7=测量全败（MEASURE-FAIL，如实红，不冒充 SLOWBOOT）。
#
# 【Fam-C 防误报钉面（OPEN-28 教训硬化）】判读前置形+参双核：ARM_ENV_FILE md5（形主键）
#   + SPEC_EXTRA_ARGS 归一指纹（参面，锚行挂 serve_md5——T4PW 四参缺
#   --enable-decoder-swa-bounded-replay 的表观 -49~54% 伪影不得入 SLOWBOOT）。
#   形不在表→ANCHOR-UNKNOWN（告警不判快慢）；形在表参不符/参面缺席→ANCHOR-N/A（同）。
#   量具污染防线：同轮 TTFT 比<0.3=E1 式 radix 命中伪影→弃该发补发 1 次（弃而不隐，入台账）。
#
# 【台账】logs/<ARM_TAG>/state/slowboot-ledger.jsonl（全字段 JSONL）+ 向
#   logs/<ARM_TAG>/state/boot_ledger.txt 追加 SENTINEL 行（调查员 §4.1 台账格式）+
#   SLOWBOOT 时落 state/SLOWBOOT-BANNER.txt 标记件。附带常采 boot 时长（§3.2 弱信号：
#   慢靴 9m08s/9m35s vs 快靴 7m46-7m57s——从 boot_ledger BOOT-START/END 对解析，不作判据）。
#
# 【用法】
#   ARM_TAG=W2-XXX ARM_ENV_FILE=.../PROD-R1STDLL128-spec1.env \
#     SPEC_EXTRA_ARGS="--prefill-decode-interval 16 ... --enable-decoder-swa-bounded-replay ..." \
#     bash tools/boot_sentinel.sh                    # 真跑（引擎须已在 :8898）
#   DRY_RUN=1 ... 同上                               # DRY：打计划不发包不写台账
#   bash tools/boot_sentinel.sh --selfcheck          # 自检（mock sd_bench 快/慢两态+负控，零集群）
# 环境变量：ARM_TAG(必填) CAMPAIGN(必填；2026-10-30 DF-02 家目录默认 __REPO_ROOT__
#   废除——缺参拒跑打印缺什么) SDBENCH(必填；2026-10-30 DF-02 家目录默认
#   __FLEET_ENV_DIR__/bench/sd_bench.py 废除——缺参拒跑；DRY_RUN=1 亦须显式设，
#   免的只是件在位性检查；selfcheck 用 mock 覆盖)
#   ARM_ENV_FILE(形钉面，缺=ANCHOR-N/A 不判快慢) SPEC_EXTRA_ARGS(参钉面)
#   BASE_URL(默认 http://127.0.0.1:8898/v1；含 8899 即拒)
#   ANCHOR_TABLE(默认 tools/boot_sentinel_anchors.tsv) PR_FILLER(默认 real) SIZE(默认 32768)
#   SHOTS(默认 3) STEP_TIMEOUT_S(默认 900) HEALTH_CHECK(默认 1；0=跳过 health 轮询，仅自检用)
#   HEALTH_WAIT_S(默认 600) DRY_RUN(默认 0) RADIX_TTFT_RATIO(默认 0.3)
# 【护栏】8899 硬拒（G5）；不起靴、不 ssh、不 docker、不 flush、不动引擎状态——只发 PR 读数。
set -uo pipefail

# DF-02（2026-10-30）：两参原为家目录默认（__REPO_ROOT__、
#   __FLEET_ENV_DIR__/bench/sd_bench.py）——外部站点 $HOME 下无作者路径必失锚，
#   改必设显式参数；守卫段缺参即拒跑（fail-closed 打印缺什么），绝不带错默认静默跑。
CAMPAIGN="${CAMPAIGN:-}"
ARM_TAG="${ARM_TAG:-}"
ARM_ENV_FILE="${ARM_ENV_FILE:-}"
SPEC_EXTRA_ARGS="${SPEC_EXTRA_ARGS:-}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8898/v1}"
SDBENCH="${SDBENCH:-}"
ANCHOR_TABLE="${ANCHOR_TABLE:-$CAMPAIGN/tools/boot_sentinel_anchors.tsv}"
PR_FILLER="${PR_FILLER:-real}"
SIZE="${SIZE:-32768}"
SHOTS="${SHOTS:-3}"
STEP_TIMEOUT_S="${STEP_TIMEOUT_S:-900}"
HEALTH_CHECK="${HEALTH_CHECK:-1}"
HEALTH_WAIT_S="${HEALTH_WAIT_S:-600}"
DRY_RUN="${DRY_RUN:-0}"
RADIX_TTFT_RATIO="${RADIX_TTFT_RATIO:-0.3}"

# ── selfcheck 分支（零集群：mock sd_bench 快/慢两态+负控，全部走本件全路径）──
if [ "${1:-}" = "--selfcheck" ]; then
  python3 - "$0" <<'PYSELF'
import json, os, shutil, subprocess, sys, tempfile, textwrap

SCRIPT = os.path.abspath(sys.argv[1])
CAMP_ROOT = os.path.dirname(os.path.dirname(SCRIPT))            # 真仓（取真实锚表/env 面核）
ENV43 = os.path.expanduser("__ASSETS_ROOT__/dsv41/env/PROD-R1STDLL128-spec1.env")
ENV_F2 = os.path.join(CAMP_ROOT, "arms/F2-EMPTYCACHE0-spec1.env")
ARGS5 = ("--prefill-decode-interval 16 --max-queued-requests 32 --min-free-slots-delay 1 "
         "--enable-decoder-swa-bounded-replay --reasoning-parser deepseek-v41")
ARGS4 = ARGS5.replace("--enable-decoder-swa-bounded-replay ", "")   # Fam-C 参面缺参负控（T4PW 形态）

tmp = tempfile.mkdtemp(prefix="sentinel-selfcheck-")
mock = os.path.join(tmp, "mock_sd_bench.py")   # mock：按 MOCK_MODE+调用序号出快/慢/带内/radix/败态
open(mock, "w").write(textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys
    argv = sys.argv[1:]
    jo = argv[argv.index("--json-out") + 1]
    mode = os.environ.get("MOCK_MODE", "fast")
    cnt_f = os.path.join(os.path.dirname(jo), "callcount")
    n = 1
    if os.path.exists(cnt_f):
        n = int(open(cnt_f).read().strip()) + 1
    open(cnt_f, "w").write(str(n))
    if mode == "fail":
        print("mock fail rc=1", file=sys.stderr); sys.exit(1)
    ttft, toks = 8.2, 4290.0            # 健康态（W1-B2 L0005 hot 35185/8.202 同量级）
    if mode == "slow":  ttft, toks = 43.9, 801.0    # W1-B1 探针慢靴域
    if mode == "warn":  ttft, toks = 16.0, 2200.0   # 0.5-0.7×带内
    if mode == "radix" and n == 2: ttft, toks = 1.0, 35185.0  # 第2发 radix 伪影（TTFT 比 0.12<0.3）
    row = {"target": 32768, "prompt_tokens": 35185, "ttft_s": ttft,
           "tok_s": round(toks, 1), "filler": "real", "label": f"mock-{mode}-{n}"}
    json.dump({"pr": [row]}, open(jo, "w"))
    print(f"mock sd_bench mode={mode} call#{n} tok_s={toks}")
'''))
os.chmod(mock, 0o755)

results = []
def note(ok, msg, why="-"):
    results.append((msg, bool(ok), why)); print(f"  [{'PASS' if ok else 'FAIL'}] {msg}"
                                                 + ("" if ok else f"：{why}"))

def run_case(name, env_extra, want_rc=None, must_have=(), must_not_have=(), tmpwin=None):
    """跑一件全路径用例；断言=输出字面含/不含+退出码（红因必须落字面）。"""
    env = dict(os.environ, CAMPAIGN=tmp, SDBENCH=mock,
               ANCHOR_TABLE=os.path.join(CAMP_ROOT, "tools/boot_sentinel_anchors.tsv"),
               ARM_TAG=tmpwin or f"SC-{name}", HEALTH_CHECK="0",
               BASE_URL="http://127.0.0.1:8898/v1", STEP_TIMEOUT_S="60")
    env.update(env_extra)
    p = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=300)
    out = p.stdout + p.stderr
    why = []
    for s in must_have:
        if s not in out: why.append(f"缺字面[{s}]")
    for s in must_not_have:
        if s in out: why.append(f"禁字面现[{s}]")
    if want_rc is not None and p.returncode != want_rc:
        why.append(f"rc={p.returncode}≠{want_rc}")
    note(not why, name, "; ".join(why) or "OK")
    return out

def ledger_of(win):
    p = os.path.join(tmp, "logs", win, "state", "slowboot-ledger.jsonl")
    if not os.path.exists(p): return None
    return json.loads(open(p).read().strip().splitlines()[-1])

print("== F-9 boot_sentinel selfcheck（DRY 全路径+mock 快/慢两态判别力+锚 UNKNOWN/参不符负控；零集群零流量）==")

# S0 DRY 全路径：真实锚表+产线 43 键 env；打计划（3 发命令面）不发包不写台账（负控：台账不得现）
win = "SC-S0"
run_case("S0-dry-全路径", dict(DRY_RUN="1", ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS5), want_rc=0,
         must_have=("DRY-RUN", "form=2de48070", "anchor=3700", "serve=d3a0159a",
                    "--mode pr --pr-filler real --sizes 32768", "shot3"),
         must_not_have=("[SLOWBOOT]",), tmpwin=win)
note(not os.path.exists(os.path.join(tmp, "logs", win, "state", "slowboot-ledger.jsonl")),
     "S0-dry-零台账写入(负控)", "DRY 态竟写台账")

# S1 mock 快态 → GREEN + 形/参钉面+口径+cold_first 入台账
win = "SC-S1"
run_case("S1-快态-GREEN", dict(ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS5, MOCK_MODE="fast"),
         want_rc=0, must_have=("[SENTINEL] GREEN", "ratio=1.1595", "2de48070"),
         must_not_have=("[SLOWBOOT]",), tmpwin=win)
rec = ledger_of(win)
note(rec and rec.get("verdict") == "GREEN", "S1-台账 verdict=GREEN")
note(rec and rec["form"]["env_md5"] == "2de48070" and rec["form"]["nkeys"] == 43,
     "S1-台账形钉面 env_md5=2de48070/43键", f"实得 {rec and rec['form'].get('env_md5')}/{rec and rec['form'].get('nkeys')}")
note(rec and rec["form"]["serve_md5"] == "d3a0159a", "S1-台账参钉面 serve_md5=d3a0159a",
     f"实得 {rec and rec['form'].get('serve_md5')}")
note(rec and rec["shots"][0].get("cold_first") is True, "S1-台账首发 cold_first 登记")
note(rec and rec["caliber"]["filler"] == "real" and rec["caliber"]["size"] == 32768,
     "S1-台账口径 real/32768（与 W1 探针同形）")
note(rec and rec["anchor"] and rec["anchor"]["anchor"] == 3700.0, "S1-台账锚行 3700 带来源入档")

# S2 mock 慢态 → SLOWBOOT 横幅+台账+boot_ledger SENTINEL 行+标记件（判别力=同管线唯变 mock 值）
win = "SC-S2"
os.makedirs(os.path.join(tmp, "logs", win, "state"), exist_ok=True)
open(os.path.join(tmp, "logs", win, "state", "boot_ledger.txt"), "w").write(
    "[2026-10-10T00:21:33Z] BOOT-START W1-B1\n[2026-10-10T00:31:08Z] BOOT-END W1-B1 rc=0\n")
run_case("S2-慢态-SLOWBOOT", dict(ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS5, MOCK_MODE="slow"),
         want_rc=0, must_have=("[SLOWBOOT] boot 低速哨兵判红", "ratio=0.2165", "不拦服务、不自动重启",
                               "801.0", "非 Fam-C"), tmpwin=win)
rec = ledger_of(win)
note(rec and rec.get("verdict") == "SLOWBOOT" and abs(rec["ratio"] - 0.2165) < 0.005,
     "S2-台账 verdict=SLOWBOOT ratio=801/3700≈0.2165")
note(rec and rec.get("boot_dur_s") == 575, "S2-台账 boot_dur_s=575（§3.2 弱信号常采）",
     f"实得 {rec and rec.get('boot_dur_s')}")
bl = open(os.path.join(tmp, "logs", win, "state", "boot_ledger.txt")).read()
note("SENTINEL SLOWBOOT" in bl and "form=2de48070" in bl,
     "S2-boot_ledger SENTINEL 行（rate/anchor/form 面）")
note(os.path.exists(os.path.join(tmp, "logs", win, "state", "SLOWBOOT-BANNER.txt")),
     "S2-SLOWBOOT-BANNER.txt 标记件在档")

# S3 WARN 带（0.5-0.7×）→ WARN 行非横幅
run_case("S3-带内-WARN", dict(ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS5, MOCK_MODE="warn"),
         want_rc=0, must_have=("[SENTINEL] WARN", "ratio=0.5946"), must_not_have=("判红",), tmpwin="SC-S3")

# S4 形不在表（F-2 臂 env=唯键差 8192→0 形）→ ANCHOR-UNKNOWN 不判快慢（Fam-C 负控：慢值在手也不判红）
win = "SC-S4"
run_case("S4-形不在表-ANCHOR-UNKNOWN", dict(ARM_ENV_FILE=ENV_F2, SPEC_EXTRA_ARGS=ARGS5, MOCK_MODE="slow"),
         want_rc=0, must_have=("ANCHOR-UNKNOWN", "先补锚", "不判快慢"),
         must_not_have=("哨兵判红",), tmpwin=win)
note(ledger_of(win) and ledger_of(win).get("verdict") == "ANCHOR-UNKNOWN",
     "S4-台账 verdict=ANCHOR-UNKNOWN（速率 801 在档但不判快慢）")

# S5 形在表参不符（四参缺 bounded-replay=T4PW Fam-C 形态）→ ANCHOR-N/A 不判快慢
win = "SC-S5"
run_case("S5-参面不符-ANCHOR-N/A", dict(ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS4, MOCK_MODE="slow"),
         want_rc=0, must_have=("ANCHOR-N/A", "参", "不判快慢"), must_not_have=("哨兵判红",), tmpwin=win)
note(ledger_of(win) and ledger_of(win).get("verdict") == "ANCHOR-N/A",
     "S5-台账 verdict=ANCHOR-N/A（T4PW 形参伪影面拦下）")

# S5b 参面缺席（未传 SPEC_EXTRA_ARGS）→ ANCHOR-N/A（无法核参不判快慢）
win = "SC-S5b"
run_case("S5b-参面缺席-ANCHOR-N/A", dict(ARM_ENV_FILE=ENV43, MOCK_MODE="slow"),
         want_rc=0, must_have=("ANCHOR-N/A", "不判快慢"), must_not_have=("哨兵判红",), tmpwin=win)

# S6 radix 命中伪影（第2发 TTFT 比<0.3）→ 弃发补发，判读仍绿（弃而不隐）
win = "SC-S6"
run_case("S6-radix伪影-弃发补发", dict(ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS5, MOCK_MODE="radix"),
         want_rc=0, must_have=("[SENTINEL] GREEN", "radix 命中伪影"), tmpwin=win)
rec = ledger_of(win)
sus = [s for s in (rec or {"shots": []})["shots"] if s.get("radix_suspect")]
note(bool(sus) and any(s.get("refire") for s in rec["shots"]),
     "S6-台账伪影发弃置+补发在档（弃而不隐）")
note(bool(sus) and sus[0].get("tok_s") == 35185.0 and rec["med_tok_s"] == 4290.0,
     "S6-伪影巨值 35185 未入中位（med=4290）")

# S7 负控四连：坏输入必须因正确理由变红
run_case("S7a-8899 拒(负控)", dict(ARM_ENV_FILE=ENV43, BASE_URL="http://127.0.0.1:8899/v1"),
         want_rc=5, must_have=("ABORT: BASE_URL 含 8899",), tmpwin="SC-S7a")
run_case("S7b-测量全败-MEASURE-FAIL(负控)", dict(ARM_ENV_FILE=ENV43, SPEC_EXTRA_ARGS=ARGS5, MOCK_MODE="fail"),
         want_rc=7, must_have=("MEASURE-FAIL", "不冒充 SLOWBOOT"), must_not_have=("哨兵判红",), tmpwin="SC-S7b")
run_case("S7c-缺锚表(负控)", dict(ARM_ENV_FILE=ENV43, ANCHOR_TABLE=os.path.join(tmp, "no-such.tsv")),
         want_rc=5, must_have=("ABORT: 缺锚表",), tmpwin="SC-S7c")
run_case("S7d-无 ARM_TAG(负控)", dict(ARM_ENV_FILE=ENV43, ARM_TAG=""), want_rc=5,
         must_have=("ABORT: ARM_TAG 未设",), tmpwin="SC-S7d")

n_pass = sum(1 for _, ok, _ in results if ok)
print(f"== selfcheck 结果：{n_pass}/{len(results)} PASS ==")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if n_pass == len(results) else 1)
PYSELF
sc_rc=$?
echo "== boot_sentinel --selfcheck 退出 rc=$sc_rc =="
exit "$sc_rc"
fi

# ── 守卫（红=正确理由拒跑；负控自检 S7 面向此处）─────────────────────────
# DF-02（2026-10-30）缺参拒跑置于一切守卫之首：CAMPAIGN/SDBENCH 家目录默认已废除，
#   缺参=exit 5 并打印缺什么（fail-closed；非 8899 门/锚表门等更早截流）。
if [ -z "$CAMPAIGN" ]; then
  echo "ABORT: CAMPAIGN 未设（DF-02 家目录默认 __REPO_ROOT__ 已废除；例 CAMPAIGN=__REPO_ROOT__）" >&2; exit 5; fi
if [ -z "$SDBENCH" ]; then
  echo "ABORT: SDBENCH 未设（DF-02 家目录默认 __FLEET_ENV_DIR__/bench/sd_bench.py 已废除；例 SDBENCH=<sd_bench.py 绝对路径>；DRY_RUN=1 亦须显式设）" >&2; exit 5; fi
case "$BASE_URL" in *8899*)
  echo "ABORT: BASE_URL 含 8899（生产口，G5 绝对隔离）: $BASE_URL" >&2; exit 5 ;; esac
if [ -z "$ARM_TAG" ] || [ "$ARM_TAG" = "unknown" ]; then
  echo "ABORT: ARM_TAG 未设（台账按 logs/<ARM_TAG>/ 落账，须窗名）" >&2; exit 5; fi
if [ ! -f "$ANCHOR_TABLE" ]; then
  echo "ABORT: 缺锚表 $ANCHOR_TABLE" >&2; exit 5; fi
if [ "$DRY_RUN" != "1" ] && [ ! -f "$SDBENCH" ]; then
  echo "ABORT: 缺 sd_bench $SDBENCH（DRY_RUN=1 可免）" >&2; exit 5; fi
command -v python3 >/dev/null || { echo "ABORT: 无 python3" >&2; exit 5; }


# ── health 轮询（挂载面契约：boot rc=0 且 8898=200 后才测；调查员 §4.1）──
if [ "$HEALTH_CHECK" = "1" ]; then
  RROOT="${BASE_URL%/v1}"; code=""
  for _ in $(seq 1 $((HEALTH_WAIT_S / 15 + 1))); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$RROOT/health" 2>/dev/null)
    [ "$code" = "200" ] && break; sleep 15
  done
  if [ "$code" != "200" ]; then
    echo "[SENTINEL] MEASURE-SKIP：health ${HEALTH_WAIT_S}s 内未达 200（code=${code:-none}）——不测不判（fail-visible 如实红）" >&2
    exit 6
  fi
  echo "[SENTINEL] health 200（$RROOT/health）→ 采测开始"
fi

# ── 主路径：形/参钉面→锚查→3 发采测→radix 防线→判档→横幅+台账（python 单点落）──
WIN_DIR="$CAMPAIGN/logs/$ARM_TAG"
mkdir -p "$WIN_DIR/state"   # 教义：mkdir 先于写（prl6 坑④）
SENTINEL_WIN_DIR="$WIN_DIR"
export CAMPAIGN ARM_TAG ARM_ENV_FILE SPEC_EXTRA_ARGS BASE_URL SDBENCH ANCHOR_TABLE \
  PR_FILLER SIZE SHOTS STEP_TIMEOUT_S DRY_RUN RADIX_TTFT_RATIO SENTINEL_WIN_DIR

python3 - <<'PYMAIN'
import datetime as dt
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time

win = os.environ["SENTINEL_WIN_DIR"]
g = lambda k, d="": os.environ.get(k, d)
ARM_TAG, DRY = g("ARM_TAG"), g("DRY_RUN") == "1"
FILLER, SIZE, SHOTS_N = g("PR_FILLER", "real"), g("SIZE", "32768"), int(g("SHOTS", "3"))
SDBENCH, BASE_URL, ANCHOR_TABLE = g("SDBENCH"), g("BASE_URL"), g("ANCHOR_TABLE")
SERVE_RAW, RADIX_R = g("SPEC_EXTRA_ARGS"), float(g("RADIX_TTFT_RATIO", "0.3"))
STEP_TIMEOUT, GREEN_AT, SLOW_AT = int(g("STEP_TIMEOUT_S", "900")), 0.7, 0.5
LEDGER = os.path.join(win, "state", "slowboot-ledger.jsonl")
BOOT_LEDGER = os.path.join(win, "state", "boot_ledger.txt")
BANNER_FILE = os.path.join(win, "state", "SLOWBOOT-BANNER.txt")
ts_now = lambda: dt.datetime.now(dt.timezone.utc).strftime("%FT%TZ")

# ── 1. 形/参钉面（Fam-C 防误报：env md5 主键 + serve 参归一指纹 + gates 横幅面）──
form = {"env_file": None, "env_md5": None, "nkeys": None, "keyset_md5": None,
        "critical": {}, "serve_raw": SERVE_RAW[:160], "serve_md5": None, "gates": None,
        "pin_ok": False, "pin_reason": "no-env-file"}
envf = g("ARM_ENV_FILE")
if envf:
    if os.path.isfile(envf):
        raw = open(envf, "rb").read()
        form["env_file"], form["env_md5"] = envf, hashlib.md5(raw).hexdigest()[:8]
        kv = dict(re.findall(r"^([A-Za-z_][A-Za-z0-9_.]*)=(.*)$", raw.decode(errors="replace"), re.M))
        form["nkeys"] = len(kv)
        form["keyset_md5"] = hashlib.md5(" ".join(sorted(kv)).encode()).hexdigest()[:8]
        form["critical"] = {k: kv[k] for k in (
            "DSV41_PREFILL_EMPTY_CACHE_TOKENS", "DSV41_ENGRAM_CACHE_GIB",
            "DSV41_HC_FUSED", "DSV41_INDEXER_HOIST") if k in kv}
        form["pin_ok"], form["pin_reason"] = True, "ok"
    else:
        form["pin_reason"] = "env-file-missing"
if SERVE_RAW.strip():
    form["serve_md5"] = hashlib.md5(" ".join(sorted(SERVE_RAW.split())).encode()).hexdigest()[:8]
else:
    form["serve_md5"] = "EMPTY"
# gates 横幅面（best-effort：窗 boot-checks kv-banner；30/31 兼容均合法，仅入台账不入判据）
try:
    bdir = os.path.join(win, "boot-checks")
    cands = sorted([os.path.join(bdir, f) for f in os.listdir(bdir) if f.endswith("kv-banner.txt")],
                   key=os.path.getmtime)
    if cands:
        m = re.findall(r"banner complete: (\d+) gates", open(cands[-1], errors="replace").read())
        if m: form["gates"] = int(m[-1])
except OSError:
    pass

# ── 2. boot 时长常采（§3.2 弱信号：boot_ledger 最后 START/END 对；不作判据）──
boot_dur_s = None
try:
    starts, ends = [], []
    for ln in open(BOOT_LEDGER, errors="replace"):
        if "BOOT-START" in ln: starts.append(ln.split("]")[0].lstrip("["))
        elif "BOOT-END" in ln: ends.append(ln.split("]")[0].lstrip("["))
    if starts and ends:
        t0 = dt.datetime.fromisoformat(starts[-1].replace("Z", "+00:00"))
        t1 = dt.datetime.fromisoformat(ends[-1].replace("Z", "+00:00"))
        boot_dur_s = round((t1 - t0).total_seconds())
except (OSError, ValueError):
    pass

# ── 3. 锚表查表（通配 *；特异行优先；不臆造：取不到=UNKNOWN，形在表参不符=N/A）──
rows = []
for ln in open(ANCHOR_TABLE, encoding="utf-8"):
    if ln.startswith("#") or not ln.strip() or ln.startswith("env_md5"):
        continue
    c = ln.rstrip("\n").split("\t")
    if len(c) == 10:
        rows.append(dict(zip(("env_md5", "serve_md5", "filler", "size", "anchor", "band_lo",
                              "band_hi", "status", "form", "provenance"), c)))
num = lambda r: float(r["anchor"]) if r and re.match(r"^\d+(\.\d+)?$", r["anchor"] or "") else None

anchor, anch_reason, lookup, pin_mismatch = None, None, "no-form-pin", False
if form["pin_ok"]:
    def hit(r):
        return (r["env_md5"] in ("*", form["env_md5"])
                and r["serve_md5"] in ("*", form["serve_md5"])
                and r["filler"] in ("*", FILLER)
                and r["size"] in ("*", SIZE))
    cands = sorted([r for r in rows if hit(r)],
                   key=lambda r: (r["env_md5"] == "*", r["serve_md5"] == "*",
                                  r["filler"] == "*", r["size"] == "*"))
    same_form = [r for r in rows if r["env_md5"] == form["env_md5"]]
    if cands and num(cands[0]) is not None and cands[0]["status"] == "OK":
        anchor = cands[0]
        lookup = f"row:{form['env_md5']}/{cands[0]['serve_md5']}/{FILLER}/{SIZE}"
    else:
        src = cands[0] if cands else None
        if same_form and form["serve_md5"] == "EMPTY":
            pin_mismatch, anch_reason = True, \
                f"serve-face-absent：形 {form['env_md5']} 在表但未传 SPEC_EXTRA_ARGS——参面无法核（T4PW 教训：缺 --enable-decoder-swa-bounded-replay 曾表观 -49~54%），不判快慢"
        elif same_form and not any(r["serve_md5"] in ("*", form["serve_md5"]) and
                                   r["filler"] in ("*", FILLER) and r["size"] in ("*", SIZE)
                                   for r in same_form):
            pin_mismatch, anch_reason = True, \
                f"serve-mismatch：形 {form['env_md5']} 在表但参指纹 {form['serve_md5']} 与锚行不符——形/参伪影面（Fam-C），不判快慢"
        else:
            anch_reason = f"{src['form'] if src else 'form-not-in-table'}：{src['provenance'] if src else '形无锚行'}"
else:
    anch_reason = f"no-form-pin（{form['pin_reason']}）——无 ARM_ENV_FILE 钉面，不判快慢"

# ── 4. 3 发采测（首发=cold_first；DRY=打计划不发包；radix 防线=TTFT 比<R 弃发补发 1 次）──
shot_dir = os.path.join(win, "state", "sentinel", time.strftime("%Y%m%d-%H%M%S"))
os.makedirs(shot_dir, exist_ok=True)
shots = []
def fire(i, label, cold=False, refire=False):
    jo = os.path.join(shot_dir, f"shot{i}.json")
    cmd = [sys.executable, SDBENCH, "--base-url", BASE_URL, "--key-file", "/dev/null",
           "--mode", "pr", "--pr-filler", FILLER, "--sizes", SIZE,
           "--label", label, "--json-out", jo]
    print(f"[SENTINEL] {'DRY ' if DRY else ''}shot{i}: {' '.join(cmd)}", flush=True)
    if DRY:
        return {"shot": i, "cold_first": cold, "dry": True}
    rec = {"shot": i, "cold_first": cold, "refire": refire, "json": jo}
    try:
        rc = subprocess.call(cmd, timeout=STEP_TIMEOUT)
    except subprocess.TimeoutExpired:
        rc = -9
    if rc != 0:
        rec["error"] = f"rc={rc}"; return rec
    try:
        row = (json.load(open(jo)).get("pr") or [None])[0]
    except (OSError, json.JSONDecodeError):
        row = None
    if not row:
        rec["error"] = "no-pr-row"; return rec
    rec.update({k: row.get(k) for k in ("prompt_tokens", "ttft_s", "tok_s", "chars_per_token")})
    return rec

for i in range(1, SHOTS_N + 1):
    shots.append(fire(i, f"sentinel-{ARM_TAG}-s{i}", cold=(i == 1)))
if not DRY:
    # radix 污染防线（E1 式即时重放判别：同轮 TTFT 比<RADIX_R=命中伪影）——弃而不隐，每发至多补 1 次
    for idx, s in enumerate(shots):
        if not s.get("ttft_s"):
            continue
        peers = [t["ttft_s"] for j, t in enumerate(shots) if j != idx and t.get("ttft_s")]
        if peers and s["ttft_s"] < RADIX_R * statistics.median(peers):
            s["radix_suspect"] = round(s["ttft_s"] / statistics.median(peers), 3)
            print(f"[SENTINEL] shot{s['shot']} TTFT 比 {s['radix_suspect']}<{RADIX_R} =radix 命中伪影→弃发补发", flush=True)
            shots.append(fire(len(shots) + 1, f"sentinel-{ARM_TAG}-s{s['shot']}r", refire=True))

# ── 5. 判档（≥0.7 GREEN；0.5-0.7 WARN；<0.5 SLOWBOOT；无锚/形参不符不判）──
usable = [s for s in shots if s.get("tok_s") and not s.get("radix_suspect")]
med = round(statistics.median([s["tok_s"] for s in usable]), 1) if usable else None
a_num = num(anchor)
ratio = round(med / a_num, 4) if (med is not None and a_num) else None
if DRY:
    verdict = "DRY-RUN"
elif med is None:
    verdict = "MEASURE-FAIL"
elif a_num is None:
    verdict = "ANCHOR-N/A" if pin_mismatch else "ANCHOR-UNKNOWN"
else:
    verdict = "GREEN" if ratio >= GREEN_AT else ("WARN" if ratio >= SLOW_AT else "SLOWBOOT")

rec = {"ts": ts_now(), "arm_tag": ARM_TAG, "dry": DRY, "verdict": verdict,
       "med_tok_s": med, "ratio": ratio,
       "anchor": (dict(anchor, anchor=a_num) if anchor else None),
       "anchor_reason": anch_reason, "anchor_lookup": lookup,
       "form": form,
       "caliber": {"filler": FILLER, "size": int(SIZE), "shots": SHOTS_N,
                   "rate_chain": "A=prompt_tokens/TTFT", "radix_ttft_ratio": RADIX_R,
                   "note": "与 W1 探针轮形一致=可比（pr_degrade_probe_draft 同 CLI 面）"},
       "shots": shots, "boot_dur_s": boot_dur_s,
       "thresholds": {"green_ge": GREEN_AT, "slowboot_lt": SLOW_AT},
       "base_url": BASE_URL, "sdbench": SDBENCH}

# ── 6. 横幅+台账（fail-visible：SLOWBOOT=大横幅；UNKNOWN/N/A=告警；不 abort 不重启）──
a_fmt = int(a_num) if (a_num is not None and a_num == int(a_num)) else a_num
sentinel_line = (f"[{rec['ts']}] SENTINEL {verdict} rate={med} "
                 f"anchor={a_fmt if a_num else 'UNKNOWN'} ratio={ratio} "
                 f"form={form['env_md5'] or '?'}/serve={form['serve_md5']}/gates={form['gates']} "
                 f"boot_dur={boot_dur_s}")

if verdict == "SLOWBOOT":
    b = "\n".join([
        "═" * 68,
        f"[SLOWBOOT] boot 低速哨兵判红：prefill 速率 < {SLOW_AT}× 形锚（F-9 fail-visible）",
        f"  速率={med} tok/s（{len(usable)} 发中位，{FILLER} {SIZE}，链A=prompt_tokens/TTFT）",
        f"  形锚={a_num:g}（{anchor['form']}；带 {anchor['band_lo']}-{anchor['band_hi']}）⇒ ratio={ratio}",
        f"  形钉面=env {form['env_md5']}/{form['nkeys']}键 serve={form['serve_md5']} gates={form['gates']}"
        "（形参相符——非 Fam-C 形参伪影）",
        f"  boot_dur={boot_dur_s}s（弱信号对照 §3.2：慢靴 548-575s vs 快靴 466-477s）",
        f"  台账={LEDGER}（SENTINEL 行已入 boot_ledger；横幅存 SLOWBOOT-BANNER.txt）",
        "  ── 处置纪律（fail-visible 不 fail-safe）──",
        "  不拦服务、不自动重启——重启/换靴决策归人/呈裁（U1 教训）",
        "  四族判别：Fam-A 长空窗首靴（查 V4.1 流量空窗≥8h?→F-10 热身协议 tools/boot_warmup.sh）；",
        "  Fam-B 靴内累积（看后续轮斜率）；Fam-D fabric（查 fabric-guard 告警）；",
        "  Fam-C 已由形+参钉面排除（见上钉面行）。",
        "═" * 68])
    print(b, flush=True)
    if not DRY:
        open(BANNER_FILE, "w", encoding="utf-8").write(b + "\n")
elif verdict == "GREEN":
    print(f"[SENTINEL] GREEN rate={med} anchor={a_num:g} ratio={ratio} "
          f"form={form['env_md5']}/{form['nkeys']}键 serve={form['serve_md5']} gates={form['gates']} "
          f"boot_dur={boot_dur_s}s（≥{GREEN_AT}×锚）", flush=True)
elif verdict == "WARN":
    print(f"[SENTINEL] WARN rate={med}（{SLOW_AT}-{GREEN_AT}×锚带内）anchor={a_num:g} ratio={ratio} "
          f"form={form['env_md5']} gates={form['gates']}——复测一轮；仍带内=呈裁", flush=True)
elif verdict == "MEASURE-FAIL":
    print(f"[SENTINEL] MEASURE-FAIL：{SHOTS_N} 发全败（明细入台账 {LEDGER}）——"
          "不判快慢不冒充 SLOWBOOT（fail-visible 如实红）", flush=True)
elif verdict == "DRY-RUN":
    print(f"[SENTINEL] DRY：判档未执行（3 发计划+锚查路径已打印）——would-append 台账行见下", flush=True)
else:
    print(f"[SENTINEL] {verdict}：{anch_reason}", flush=True)
    print(f"[SENTINEL] {verdict} ⇒ 不判快慢（Fam-C 防误报：先补锚/核形参，再复测）——"
          f"速率读数仍入台账（rate={med}）", flush=True)

if DRY:
    print(f"[SENTINEL] DRY：不写台账。would-append boot_ledger 行：", flush=True)
    print(f"  {sentinel_line}", flush=True)
else:
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(BOOT_LEDGER, "a", encoding="utf-8") as f:
        f.write(sentinel_line + "\n")
    print(f"[SENTINEL] 台账已落：{LEDGER}（shots 明细={shot_dir}/）", flush=True)

print(json.dumps({"done": True, "verdict": verdict, "med_tok_s": med, "ratio": ratio,
                  "ledger": LEDGER, "boot_ledger_line": sentinel_line}))
sys.exit(7 if verdict == "MEASURE-FAIL" else 0)
PYMAIN
rc=$?
exit "$rc"
