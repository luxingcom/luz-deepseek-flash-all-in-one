#!/usr/bin/env python3
"""Scored quality gate for DS-V4.1-Flash config changes. 75 题集自带、无 LLM 判分。

    python3 qeval.py --key-file ~/luz-gateway.env --key-var API_KEY run before
    ... 改配置、重启 ...
    python3 qeval.py --key-file ... run after
    python3 qeval.py compare qeval-before.json qeval-after.json
    python3 qeval.py --selftest            # 判别力自检（喂坏输入看它因正确理由变红）

75 题自动评分（code 25 / reason 16 / math 14 / json 8 / format 7 / prose 5），无 LLM 判分，
分数可复现。并发 1 运行（批组成固定时 greedy 才 run-to-run 可复现）。

⚠ `--key-file`/`--key-var` 是**顶层**参数（在 `run`/`compare` **之前**）。上面示例曾经写在
  `run` 之后 —— 照抄会 `unrecognized arguments` 退出 2（2026-09-25 两次撞上，第二次还是照着
  这份错示例抄的）。示例必须是能跑的那一种。

**来源与移植说明（2026-09-25）**：题集与判据借自 knapcio 参考项目
（`scripts/qeval.py` + `scripts/qeval_tasks.py`，HEAD `6ea8acb`），逐题未改 —— 这是
"外部质量门"的价值所在：**同一套题、同一套判据**才能与他方数字（EP1 fresh clone 72/75）
对读。移植只改三处，都是我方环境的硬约束：

  ① 端口 8888 → **8899**（本仓网关/引擎端口；测试窗可用 `--url` 覆盖）。
  ② **鉴权**：本仓引擎可带 API key，且 `--key-file`/`--key-var` 读入后**绝不回显**
     （项目纪律）。他方 8888 无鉴权 ⇒ 直接照抄会把 75 题全部 401，而 401 会被读成
     "质量灾难"（全 FAIL）—— 这是本项目最忌讳的"量具沉默却打印数字"族陷阱。
     故本文件把鉴权做成**前置门**（`preflight()`）：401/403 一律判 `AUTH` 并拒绝出分。
  ③ 结果落 `--out-dir`（默认 `~/qeval-results`，可用 `QEVAL_OUT` 覆盖），文件名不变。
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import re
import statistics as st
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qeval_tasks as qt  # noqa: E402

MODEL = "deepseek-v4.1-flash"
DEFAULT_URL = "http://127.0.0.1:8899/v1/chat/completions"
DEFAULT_OUT = os.environ.get("QEVAL_OUT", os.path.expanduser("~/qeval-results"))


# ── 密钥（命中即返回、绝不回显；与本项目 w41_de_triage.py 同源口径）─────────────
def read_key(path, var):
    """从 env 文件读密钥，绝不回显。返回 (值, 是否命中)。"""
    if not path:
        return None, False
    try:
        with open(os.path.expanduser(path), "r", errors="replace") as f:
            for ln in f:
                m = re.match(rf'\s*(?:export\s+)?{re.escape(var)}=(.*?)\s*$', ln)
                if not m:
                    continue
                v = m.group(1)
                # 成对引号（单/双）成对剥掉。★2026-09-25 自检 S1 抓到：只认双引号的旧写法
                # 会把 'k' 整串（含引号）当值送出去 ⇒ 前置门判 AUTH 拒跑（响但不静默，仍须修）。
                if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                    v = v[1:-1]
                if v:
                    return v, True
    except OSError:
        return None, False
    return None, False


def _headers(key):
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


# ── 鉴权/连通前置门（纯分类函数，可被自检单独驱动）──────────────────────────
AUTH, TRANSPORT, OK_ = "AUTH", "TRANSPORT", "OK"


def classify_preflight(status):
    """HTTP 状态码 → 前置门判词。**不猜**：401/403 是鉴权，其余非 2xx 是传输。"""
    if status in (401, 403):
        return AUTH
    if 200 <= status < 300:
        return OK_
    return TRANSPORT


def preflight(url, key, timeout=60):
    """发一条最小请求，判引擎是否可达且鉴权成立。返回 (verdict, detail)。"""
    body = {"model": MODEL, "temperature": 0, "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}]}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=_headers(key))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return classify_preflight(r.status), f"http {r.status}"
    except urllib.error.HTTPError as e:
        return classify_preflight(e.code), f"http {e.code}"
    except Exception as exc:  # 连不上 = 传输面
        return TRANSPORT, f"{type(exc).__name__}: {exc}"


def ask(url, task, timeout, key):
    body = {"model": MODEL, "temperature": 0, "max_tokens": task["max_tokens"],
            "stream": False, "chat_template_kwargs": {"thinking": bool(task["thinking"])},
            # Per-request DSpark acceptance telemetry. Costs no GPU time: the counters are
            # incremented unconditionally and this flag only decides whether they are
            # serialised back onto the response (protocol.py:356/868, serving_chat.py:1906).
            "return_spec_tokens_details": True,
            "messages": [{"role": "user", "content": task["prompt"]}]}
    t0 = time.time()
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=_headers(key))
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    dt = time.time() - t0
    ch = r["choices"][0]
    msg = ch["message"]
    content = msg.get("content") or ""
    n = r["usage"]["completion_tokens"]
    return {"content": content,
            "reasoning_chars": len(msg.get("reasoning_content") or msg.get("reasoning") or ""),
            "finish_reason": ch.get("finish_reason"), "completion_tokens": n,
            "seconds": round(dt, 3), "tok_s": round(n / dt, 2) if dt > 0 else None,
            "spec": (r.get("sglext") or {}).get("spec_tokens_details")}


def score_one(url, task, timeout, key):
    out = {"id": task["id"], "category": task["category"]}
    try:
        out.update(ask(url, task, timeout, key))
    except Exception as exc:
        return {**out, "pass": False, "why": f"request failed: {exc!r}"}
    try:
        ok, why = task["checker"](out["content"])
    except Exception as exc:
        ok, why = False, f"checker raised {exc!r}"
    out["pass"] = bool(ok)
    out["why"] = "" if ok else str(why)[:160]
    return out


def all_requests_failed(results):
    """全部是"请求层失败" ⇒ 这一跑不是质量读数（401/断连/超时的判别保底）。"""
    if not results:
        return False
    return all(str(r.get("why", "")).startswith("request failed") for r in results)


def run(label, url, timeout, concurrency, only, limit, key, out_dir):
    tasks = [t for t in qt.TASKS if not only or t["category"] in only]
    if limit:
        tasks = tasks[:limit]
    verdict, detail = preflight(url, key)
    print(f"preflight: {verdict} ({detail})  key={'<set>' if key else '<none>'}")
    if verdict != OK_:
        print(f"REFUSED: 前置门未过（{verdict}）—— 不出质量分。"
              + (" 引擎需要 API key：--key-file/--key-var。" if verdict == AUTH else
                 " 先确认引擎在跑、URL 正确。"))
        return 2
    print(f"{len(tasks)} tasks, concurrency {concurrency}, {url}")
    t0 = time.time()
    if concurrency > 1:
        with cf.ThreadPoolExecutor(concurrency) as ex:
            results = list(ex.map(lambda t: score_one(url, t, timeout, key), tasks))
    else:
        results = []
        for t in tasks:
            r = score_one(url, t, timeout, key)
            results.append(r)
            print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['id']:<22} {r.get('why','')[:70]}",
                  flush=True)
    wall = time.time() - t0
    if all_requests_failed(results):
        print(f"REFUSED: {len(results)} 题**全部**请求层失败 —— 这不是质量读数（鉴权/连通），"
              f"不出分。样例：{results[0].get('why','')[:120]}")
        return 2
    speeds = [r["tok_s"] for r in results if r.get("tok_s")]
    trunc = sum(1 for r in results if r.get("finish_reason") == "length")
    out = {"label": label, "url": url, "concurrency": concurrency, "wall_s": round(wall, 1),
           "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "median_tok_s": round(st.median(speeds), 2) if speeds else None,
           "truncated": trunc, "results": results}
    npass = sum(1 for r in results if r["pass"])
    print(f"\n{npass}/{len(results)} passed ({100*npass/len(results):.1f}%), "
          f"{trunc} hit the token cap, wall {wall/60:.1f} min, "
          f"median {out['median_tok_s']} tok/s")
    by = {}
    for r in results:
        by.setdefault(r["category"], []).append(r["pass"])
    for c, v in sorted(by.items()):
        print(f"   {c:<8} {sum(v):>2}/{len(v)}")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"qeval-{label}.json")
    json.dump(out, open(path, "w"), indent=1)
    print(f"wrote {path}")
    return 0


def mcnemar_p(b, c):
    """Two-sided exact McNemar: b = pass->fail, c = fail->pass, H0: p = 0.5."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


PRIMARY = ("code", "reason", "math")      # what "quality" means here, per the owner
SECONDARY = ("json", "format")            # instruction following: reported, not decisive
GUARD = ("prose",)                        # objective degeneration only, never a quality score


def _block(ids, ra, rb, cats):
    kept = broke = fixed = bf = 0
    flips = []
    for i in ids:
        if ra[i]["category"] not in cats:
            continue
        pa_, pb_ = ra[i]["pass"], rb[i]["pass"]
        if pa_ and pb_:
            kept += 1
        elif pa_ and not pb_:
            broke += 1; flips.append(("BROKE", i, rb[i].get("why", "")))
        elif pb_:
            fixed += 1; flips.append(("fixed", i, ra[i].get("why", "")))
        else:
            bf += 1
    return kept, broke, fixed, bf, flips


def _line(tag, kept, broke, fixed, bf):
    n = kept + broke + fixed + bf
    if n == 0:
        return None
    before, after = kept + broke, kept + fixed
    rel = (after - before) / before * 100 if before else 0.0
    p = mcnemar_p(broke, fixed)
    print(f"{tag:<28} {before:>3}/{n} -> {after:>3}/{n}   "
          f"kept {kept:>3}  BROKE {broke:>3}  fixed {fixed:>3}  both-fail {bf:>3}   "
          f"{rel:+6.1f}%   p={p:.3f}")
    return rel, p, broke, fixed


def compare(pa, pb):
    a, b = json.load(open(pa)), json.load(open(pb))
    ra = {r["id"]: r for r in a["results"]}
    rb = {r["id"]: r for r in b["results"]}
    ids = [t["id"] for t in qt.TASKS if t["id"] in ra and t["id"] in rb]
    print(f"paired on {len(ids)} tasks: {a['label']} -> {b['label']}\n")
    print(f"{'':<28} {'before':>7} {'after':>7}")
    pk, pbk, pf, pbf, pflips = _block(ids, ra, rb, PRIMARY)
    prim = _line("PRIMARY code+reason+math", pk, pbk, pf, pbf)
    sk, sbk, sf, sbf, sflips = _block(ids, ra, rb, SECONDARY)
    _line("secondary json+format", sk, sbk, sf, sbf)
    gk, gbk, gf, gbf, gflips = _block(ids, ra, rb, GUARD)
    _line("guard prose (degeneration)", gk, gbk, gf, gbf)

    percat = {}
    for i in ids:
        c = ra[i]["category"]
        d = percat.setdefault(c, [0, 0, 0, 0])
        pa_, pb_ = ra[i]["pass"], rb[i]["pass"]
        d[0 if (pa_ and pb_) else 1 if pa_ else 2 if pb_ else 3] += 1
    print(f"\n{'category':<9}{'kept':>6}{'broke':>7}{'fixed':>7}{'both-fail':>11}")
    for c, d in sorted(percat.items()):
        print(f"{c:<9}{d[0]:>6}{d[1]:>7}{d[2]:>7}{d[3]:>11}")

    allflips = pflips + sflips + gflips
    if allflips:
        print("\nflips:")
        for kind, i, why in allflips:
            print(f"  {kind:<6} {i:<22} {why[:80]}")

    sa, sb = a.get("median_tok_s"), b.get("median_tok_s")
    rel, p, broke, fixed = prim
    print()
    if gbk:
        print(f"GUARD TRIPPED: {gbk} prose task(s) degenerated -- inspect before accepting.")
    if sa and sb:
        spd = 100 * (sb / sa - 1)
        print(f"median single-stream {sa} -> {sb} tok/s ({spd:+.1f}%)")
        if rel < -0.5 and spd > 0:
            print(f"TRADE: {abs(rel):.1f}% of code+reasoning for {spd:+.1f}% speed"
                  f"{'' if p <= 0.05 else '  -- but the quality drop is within noise at this sample size'}")
        elif spd > 0 and rel >= -0.5:
            print(f"FREE: {spd:+.1f}% speed, primary quality unchanged (p={p:.3f})")
    n_prim = pk + pbk + pf + pbf
    print(f"\nresolution: {n_prim} primary tasks. A net loss of 5 with no gains is p={mcnemar_p(5,0):.3f}; "
          f"below ~4 net breaks this harness cannot separate the change from noise.")
    if a.get("concurrency", 1) > 1 or b.get("concurrency", 1) > 1:
        print("NOTE: a run used concurrency > 1; some flips may be batching noise, not the config.")
    return 0


# ── 判别力自检：喂坏输入看它**因正确理由**变红；绿相也必须可达 ──────────────────
def selftest():
    import http.server
    import tempfile
    cases = []

    def case(name, want, got, why=""):
        cases.append((name, want == got, f"want={want} got={got} {why}"))

    # S1 密钥命中 / S2 无文件
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
        f.write("# comment\nAPI_KEY='sekret-abc'\nOTHER=1\n")
        kp = f.name
    k, hit = read_key(kp, "API_KEY")
    case("S1 read_key 命中（含引号）", ("sekret-abc", True), (k, hit))
    case("S2 read_key 缺文件 ⇒ 未命中而非异常", (None, False), read_key("/nonexistent/x.env", "API_KEY"))
    case("S2b 变量名不匹配 ⇒ 未命中", (None, False), read_key(kp, "API_KEY_X"))
    os.unlink(kp)

    # S3-S5 前置门分类（纯函数：绿/两种红都可达，且理由不可互换）
    case("S3 401 ⇒ AUTH", AUTH, classify_preflight(401))
    case("S4 403 ⇒ AUTH", AUTH, classify_preflight(403))
    case("S5 500 ⇒ TRANSPORT（不许误判成 AUTH）", TRANSPORT, classify_preflight(500))
    case("S5b 200 ⇒ OK", OK_, classify_preflight(200))

    # S6-S7 真起一个本地假服务器，判前置门与"全请求失败"保底
    class H(http.server.BaseHTTPRequestHandler):
        mode = "ok"

        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self.rfile.read(n)
            if H.mode == "401":
                self.send_response(401); self.end_headers(); self.wfile.write(b'{"error":"Unauthorized"}')
                return
            payload = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                       "usage": {"completion_tokens": 1}}
            b = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    purl = f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
    H.mode = "ok"
    case("S6 假服务器 200 ⇒ 前置门 OK", OK_, preflight(purl, "k")[0])
    H.mode = "401"
    case("S7 假服务器 401 ⇒ 前置门 AUTH（不出分）", AUTH, preflight(purl, "k")[0])
    # S8 "全请求失败" 保底：不带 key 打 401 服务器时，run() 必须判 refused
    bad = [score_one(purl, qt.TASKS[0], 5, "k") for _ in range(3)]
    case("S8 全请求失败可识别（不许出分）", True, all_requests_failed(bad))
    good = [{"id": "x", "pass": True, "why": ""}]
    case("S8b 有真读数时**不**误判为全失败", False, all_requests_failed(good))
    srv.shutdown()

    # S9 题集完整性 + 绿相/红相可达（用真实 checker 驱动）
    case("S9 题集 75 题且 checker 可调用", True,
         len(qt.TASKS) == 75 and all(callable(t["checker"]) for t in qt.TASKS))
    fmt = [t for t in qt.TASKS if t["category"] == "format"]
    bad_txt = "definitely not the requested format, no markers at all"
    ok_red = all(not t["checker"](bad_txt)[0] for t in fmt[:3])
    case("S9b format 题对乱答**变红**", True, ok_red)

    # S10 McNemar 边界（0 vs 0 ⇒ p=1；5 vs 0 ⇒ 小）
    case("S10 mcnemar(0,0)=1.0", 1.0, mcnemar_p(0, 0))
    case("S10b mcnemar(5,0) < 0.1", True, mcnemar_p(5, 0) < 0.1)

    npass = sum(1 for _, ok_, _ in cases if ok_)
    for name, ok_, why in cases:
        print(f"  {'PASS' if ok_ else 'FAIL'}  {name}" + ("" if ok_ else f"   [{why}]"))
    print(f"\nselftest {npass}/{len(cases)}")
    return 0 if npass == len(cases) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="判别力自检（不连引擎）")
    ap.add_argument("--key-file", default=os.path.expanduser("~/luz-gateway.env"))
    ap.add_argument("--key-var", default="API_KEY")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    s = ap.add_subparsers(dest="cmd")
    r = s.add_parser("run"); r.add_argument("label")
    r.add_argument("--url", default=DEFAULT_URL)
    r.add_argument("--timeout", type=float, default=900)
    r.add_argument("--concurrency", type=int, default=1)
    r.add_argument("--only", default="", help="comma-separated categories")
    r.add_argument("--limit", type=int, default=0, help="first N tasks (smoke test)")
    c = s.add_parser("compare"); c.add_argument("a"); c.add_argument("b")
    n = ap.parse_args()
    if n.selftest:
        sys.exit(selftest())
    if n.cmd == "run":
        key, hit = read_key(n.key_file, n.key_var)
        if not hit:
            print(f"note: {n.key_var} 未在 {n.key_file} 命中（不回显任何值）", file=sys.stderr)
        sys.exit(run(n.label, n.url, n.timeout, n.concurrency,
                     [x for x in n.only.split(",") if x], n.limit, key, n.out_dir))
    elif n.cmd == "compare":
        sys.exit(compare(n.a, n.b))
    else:
        ap.print_help()
        sys.exit(64)
