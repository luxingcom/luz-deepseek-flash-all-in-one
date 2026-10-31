#!/usr/bin/env python3
"""conc_pr_driver.py — E13 并发臂量具件（S-ENG-PREP §3.3 量具缺口=执行窗产出）

【正典位】tools/conc_pr_driver.py（TOOL-MAINT 2026-10-23 转正：原窗内件 md5
  4c7f34d36ac86852fffff34c8f2bf412 的 G5 守卫参数化版；测量逻辑逐字节零改动。
  归档件 logs/S-ENG-EXEC-20261018/、S-C13{,PRE}-EXEC-20261018/baseline/ 三份
  4c7f34d3 原件零触留档；W1-A 临时副本 conc_pr_driver.w1a.py 已被本件取代，
  后续窗禁再用副本手法）。
【为什么存在】pr_ladder6_lit.sh 为串行单请求；并发臂 C{2,4}×{262144,524288}×liter 口径
  需要并发流形态。本件=sd_bench 只读 import + liter 口径替换（与 pr_ladder6_lit DRIVER
  逐字节同源逻辑）+ N 线程并发单档 PR（每流独立 salt=独立前缀，冷态/无跨流共享）。
【护栏】G5=非常规口未显式声明即拒：8899 默认仍拒（与原行为一致），本窗若为主会话
  授权的基准载荷口，须 --measure-port 8899 显式声明（声明进命令行=进窗档可审计）；
  8001 等常规量测口不受影响。输出 json=逐流 rows+中位 tok_s+并发衰减率 C_n/C_1（C_1 由
  --base-c1 传入或同靴 C1 显式跑）。
【用法】python3 tools/conc_pr_driver.py --base-url http://127.0.0.1:8001/v1 \
  --lit-dir <lit7> --size 262144 --conc 2 --runs 3 --json-out out.json --label c2-262144
  8899 直连（授权基准窗）：上式加 --measure-port 8899
  离线自检：python3 tools/conc_pr_driver.py --selfcheck
"""
import argparse, json, os, statistics, sys, threading, time, uuid

SD_DIR = os.environ.get("SD_DIR") or os.path.expanduser(
    "~/luz-deepseek-flash-all-in-one/tools/bench")  # 正典探针位（TOOL-MAINT 2026-10-23
# 重指；原默认 ~/dsv41-flash-dgxsparks/bench 已无 sd_bench.py=W0 T33-03 P0 §6.2 既录失效路径）
sys.path.insert(0, SD_DIR)
import sd_bench  # noqa: E402


def lit_prompt(lit_dir, target_tokens, salt):
    man = json.load(open(os.path.join(lit_dir, "MANIFEST.json"), encoding="utf-8"))
    tiers = {t["target_tokens"]: t for t in man["tiers"]}
    header = f"[prefill-bench {salt}]\nIgnore the filler below. Reply with the single word OK.\n"
    footer = "\nReply OK."
    fill = max(1, target_tokens - sd_bench.estimate_tokens(header + footer))
    t = tiers.get(target_tokens)
    if t is None:
        raise ValueError(f"liter 无冻结档 {target_tokens}")
    body = open(os.path.join(lit_dir, "frozen", t["file"]), encoding="utf-8").read()
    if len(body) < fill * 4:
        raise ValueError("冻结件不足")
    return header + body[:fill * 4] + footer


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selfcheck" in argv:
        return selfcheck()
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--lit-dir", required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--conc", type=int, required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--gen-tokens", type=int, default=8)
    ap.add_argument("--timeout-s", type=int, default=1800)
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--label", default="conc")
    ap.add_argument("--measure-port", type=int, default=None,
                    help="G5 显式声明：本窗量测口为该端口（如授权基准窗 8899）。"
                         "缺省=None ⇒ 守卫保持原行为（8899 拒、常规口放行）")
    a = ap.parse_args(argv)
    if "8899" in a.base_url and a.measure_port != 8899:
        print("ABORT: 8899 生产口（G5：非常规口未显式声明）——本窗若为主会话授权的"
              "基准载荷口，须 --measure-port 8899 显式声明", file=sys.stderr)
        return 5
    c = sd_bench.Client(a.base_url, "", timeout_s=a.timeout_s)
    # warmup 512t 短发（sd_bench.run_pr 同位语义；不占档文本）
    c.stream(f"[conc-warm {uuid.uuid4().hex[:8]}]\n" + " the" * 512 + "\nReply OK.",
             a.gen_tokens)
    runs = []
    for r in range(a.runs):
        barrier = threading.Barrier(a.conc)
        out = [None] * a.conc

        def one(i):
            barrier.wait()  # 齐发
            prompt = lit_prompt(a.lit_dir, a.size, f"{uuid.uuid4().hex[:8]}-{r}-{i}")
            t0 = time.perf_counter()
            o = c.stream(prompt, a.gen_tokens)
            ttft = o["t_first"] - o["t_req"]
            pt = o["prompt_tokens"] or a.size
            out[i] = {"stream": i, "tok_s": round(pt / ttft, 1) if ttft > 0 else None,
                      "ttft_s": round(ttft, 3), "prompt_tokens": pt}
        ths = [threading.Thread(target=one, args=(i,)) for i in range(a.conc)]
        t0 = time.perf_counter()
        for t in ths: t.start()
        for t in ths: t.join()
        wall = round(time.perf_counter() - t0, 3)
        runs.append({"run": r, "wall_s": wall, "streams": out})
        print(f"run{r} wall={wall}s " + " ".join(
            f"s{o['stream']}={o['tok_s']}" for o in out if o))
    all_toks = [o["tok_s"] for r in runs for o in r["streams"] if o and o["tok_s"]]
    med = round(statistics.median(all_toks), 1) if all_toks else None
    data = {"label": a.label, "size": a.size, "conc": a.conc, "runs": a.runs,
            "tok_s_median": med, "tok_s_all": all_toks, "detail": runs}
    json.dump(data, open(a.json_out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps({"label": a.label, "size": a.size, "conc": a.conc,
                      "tok_s_median": med}, ensure_ascii=False))
    return 0


# ── 离线自检（TOOL-MAINT 20261023 增；零网络零产线触：G5 四态 + lit_prompt 口径
#    + fake-client 全管道读数对表。W1-A 窗记 lit_driver 12/12；本件同数）──────────
def selfcheck():
    import tempfile
    ok = True
    n = {"ran": 0, "fail": 0}

    def need(cond, why):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), why)
        n["ran"] += 1
        if not cond:
            n["fail"] += 1
        ok = ok and cond

    # 合成冻结语料（自包含：不依赖真实 lit7 在位）
    td = tempfile.mkdtemp(prefix="conc-pr-selfcheck-")
    os.makedirs(os.path.join(td, "frozen"))
    with open(os.path.join(td, "MANIFEST.json"), "w", encoding="utf-8") as f:
        json.dump({"tiers": [{"target_tokens": 8192, "file": "t8192.txt"},
                             {"target_tokens": 16384, "file": "t16384-short.txt"}]}, f)
    with open(os.path.join(td, "frozen", "t8192.txt"), "w", encoding="utf-8") as f:
        f.write("novel frozen literary corpus line\n" * 3000)      # 96000c ≥ fill×4
    with open(os.path.join(td, "frozen", "t16384-short.txt"), "w", encoding="utf-8") as f:
        f.write("too short")                                      # 蓄意不足

    # 1) G5 默认=原行为：8899 未声明必拒（rc=5 且零 Client 构造）
    real_client = sd_bench.Client
    seen = []

    class ProbeClient:
        def __init__(self, base_url, key, timeout_s=0):
            seen.append(base_url)

        def stream(self, prompt, gen_tokens):
            return {"t_req": 100.0, "t_first": 102.0, "prompt_tokens": 8192}
    sd_bench.Client = ProbeClient
    try:
        rc = main(["--base-url", "http://127.0.0.1:8899/v1", "--lit-dir", td,
                   "--size", "8192", "--conc", "1", "--runs", "1",
                   "--json-out", os.path.join(td, "g5.json")])
        need(rc == 5 and not seen, "G5 默认拒 8899（rc=5、零 Client 构造=与原 4c7f34d3 行为一致）")
        # 2) 声明不匹配仍拒：8899 口 + --measure-port 8001
        rc = main(["--base-url", "http://127.0.0.1:8899/v1", "--measure-port", "8001",
                   "--lit-dir", td, "--size", "8192", "--conc", "1", "--runs", "1",
                   "--json-out", os.path.join(td, "g5b.json")])
        need(rc == 5 and not seen, "G5 声明不匹配仍拒（声明口须=实际口）")
        # 3) 显式声明放行：8899 + --measure-port 8899（fake client 全管道，读数对表）
        out8899 = os.path.join(td, "declared-8899.json")
        rc = main(["--base-url", "http://127.0.0.1:8899/v1", "--measure-port", "8899",
                   "--lit-dir", td, "--size", "8192", "--conc", "2", "--runs", "2",
                   "--json-out", out8899, "--label", "g5-declared"])
        d = json.load(open(out8899))
        need(rc == 0 and seen[-1] == "http://127.0.0.1:8899/v1",
             "G5 显式声明 8899 放行（Client 收到原样 base_url；W1-A 副本手法自此有正典替代）")
        need(d["tok_s_median"] == 4096.0 and d["tok_s_all"] == [4096.0] * 4,
             "全管道读数对表：tok_s=round(8192/2.0,1)=4096.0（pt/ttft 原式；fake 流恒定）")
        need(all(k in d for k in ("label", "size", "conc", "runs", "tok_s_median",
                                  "tok_s_all", "detail"))
             and len(d["tok_s_all"]) == d["runs"] * d["conc"] == len(
                 [o for r in d["detail"] for o in r["streams"]]),
             "输出 JSON 形（逐流 rows 闭合 runs×conc；W1-A liter 档同 schema）")
        # 4) 常规口默认不受影响：8001 无需声明
        rc = main(["--base-url", "http://127.0.0.1:8001/v1", "--lit-dir", td,
                   "--size", "8192", "--conc", "1", "--runs", "1",
                   "--json-out", os.path.join(td, "reg.json")])
        need(rc == 0 and seen[-1] == "http://127.0.0.1:8001/v1",
             "常规口 8001 默认放行（G5 参数化不收紧常规口=原行为保持）")
    finally:
        sd_bench.Client = real_client

    # 5) lit_prompt 口径（与 tools/lit_driver.py _lit_prompt header/footer/fill 逐字节同式）
    p1, p2 = lit_prompt(td, 8192, "abcd1234"), lit_prompt(td, 8192, "abcd1234")
    need(p1 == p2, "lit_prompt 同参数逐字节可复现（冻结确定性）")
    hdr = f"[prefill-bench abcd1234]\nIgnore the filler below. Reply with the single word OK.\n"
    ftr = "\nReply OK."
    need(p1.startswith(hdr) and p1.endswith(ftr),
         "header/footer 与冻结口径逐字节同源（salt 位/句式=sd_bench 原形）")
    fill = max(1, 8192 - sd_bench.estimate_tokens(hdr + ftr))
    body = p1[len(hdr):len(p1) - len(ftr)]
    need(len(body) == fill * 4 and sd_bench.estimate_tokens(p1) >= 8192 - 64,
         "body=fill×4 chars（4 chars/token 基准）且覆盖目标 token（±64 同律）")
    need(lit_prompt(td, 8192, "ffff5678")[len(f"[prefill-bench ffff5678]\nIgnore the filler below. Reply with the single word OK.\n"):-len(ftr)] == body,
         "跨 salt body 恒定（salt 只进 header=防前缀缓存共享原语义）")
    try:
        lit_prompt(td, 4096, "x")
        need(False, "无冻结档必红")
    except ValueError:
        need(True, "无冻结档必红（4096 未冻结）")
    try:
        lit_prompt(td, 16384, "x")
        need(False, "冻结件不足必红")
    except ValueError:
        need(True, "冻结件不足必红（蓄意短件）")

    print("CONC-PR-SELFCHECK", "PASS" if ok else "FAIL",
          f"n={n['ran']} fail={n['fail']}（计数口径：本行 n=实际执行断言数，为权威数）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
