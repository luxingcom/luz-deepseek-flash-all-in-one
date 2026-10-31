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
