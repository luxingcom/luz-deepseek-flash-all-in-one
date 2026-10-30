#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nvfp4_needle_gate — nvfp4 KV cache「剥 scales 手术」上线验收门（d50/d500 needle 检索）。

法源（sgl-project/sglang issue #42369 报告口径）：剥 scales 前 needle 检索
d50=1/4、d500=0/4（长上下文检索隐蔽崩塌，短 prompt 全正常）；剥 scales 走动态
scale 路径后 d50=4/4、d500=4/4。故本门=开门（--kv-cache-dtype nvfp4）前的硬验收：
**术后两档必须各自 4/4 全中**，任何一针不中或证据缺失（SKIP）即红——无证据不得
放行（与 needle_probe 自身 gate 语义同源）。

档位口径声明：d50/d500 按 issue 报告语境取「50K/500K token 文档档位」（报告者
2×16GB 卡开 nvfp4 KV 的动机即塞下超长上下文；其生产实录=185K prefill 在役）。
两档缺省 --sizes 50000 500000、每档 --repeats 4 针（seed 播种复现），全部可参数
覆盖——若上游报告后续澄清 d50/d500 为他义（如埋深），改 --sizes/--depth 即可，
判据（每档全中）不变。

实现：薄包装战役正典件 tools/needle_probe.py（形态感知门/水位门/魔码埋针/判 PASS
全复用，本件零重复实现）；每（档×seed）一次调用取单针证据，聚合判门。

用法：
  python3 nvfp4_needle_gate.py --base http://127.0.0.1:8899 --phase pre-strip   # 剥前取证（预期红=诊断证据）
  python3 nvfp4_needle_gate.py --base http://127.0.0.1:8899 --phase post-strip  # 剥后验收门（须全绿）
  python3 nvfp4_needle_gate.py --selfcheck                                     # 离线聚合器/组装自检（不发包）

退出码：0=门绿（post-strip 两档各 4/4）/pre-strip 取证采集完成；1=门红（任一档
不满足全中或证据缺失）；2=用法/取证失败（fail-closed）。
红线：本件只向 --base 发 needle 探针请求；零写仓（JSON 落 --out-dir）、零 git、
不触引擎与容器生命周期。
"""
import argparse
import json
import os
import subprocess
import sys
import time

ISSUE_URL = "https://github.com/sgl-project/sglang/issues/42369"
TOOL_VER = "nvfp4-needle-gate/1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROBE = os.path.join(HERE, "..", "..", "needle_probe.py")


def build_probe_argv(probe, base, model, form, size, seed, depth, json_out):
    """单针调用的 argv 组装（selfcheck N4 的断言对象）。"""
    return [sys.executable, probe, "--base", base, "--model", model, "--form", form,
            "--sizes", str(size), "--seed", seed, "--depth", str(depth),
            "--json-out", json_out]


def run_one_probe(argv, timeout_s):
    """跑一针；返回 (ok, parsed_json_or_None, err)。rc≠0 或 JSON 不可解析=取证失败。"""
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return False, None, "探针超时（%ds）" % timeout_s
    if cp.returncode != 0:
        return False, None, "needle_probe rc=%d：%s" % (
            cp.returncode, (cp.stderr or cp.stdout).strip().splitlines()[-1] if (cp.stderr or cp.stdout).strip() else "")
    try:
        data = json.loads(cp.stdout[cp.stdout.rfind("{"):]) if "{" in cp.stdout else None
    except Exception:
        data = None
    if data is None and os.path.exists(argv[-1]):
        try:
            data = json.load(open(argv[-1], encoding="utf-8"))
        except Exception:
            data = None
    if not isinstance(data, dict) or "rows" not in data:
        return False, None, "needle_probe 输出不可解析（JSON 缺 rows）"
    return True, data, ""


def tally(rows, size):
    """单针 tally：该档 1 行，PASS=1 中，FAIL=0 中（证据在），SKIP=证据缺失。"""
    for r in rows:
        if r.get("target_tokens") == size:
            st = r.get("status")
            return {"pass": 1 if st == "PASS" else 0,
                    "fail": 1 if st == "FAIL" else 0,
                    "skip": 1 if st == "SKIP" else 0,
                    "status": st, "reason": r.get("reason", "")}
    return {"pass": 0, "fail": 0, "skip": 1, "status": "SKIP",
            "reason": "needle_probe 返回中无该档行（形态/水位门整档放空）"}


def aggregate(per_size, repeats, phase):
    """聚合判门：post-strip=每档 pass==repeats 且 skip==0；pre-strip=只汇总（门恒记
    gate_pass=False 不放行，rc 按“采集完成”计 0）。返回 (gate_pass, verdict_lines)。"""
    lines = []
    gate = (phase == "post-strip")
    if phase != "post-strip":
        gate = False  # 剥前取证不构成放行依据，恒不放行
    for size in sorted(per_size, key=int):
        agg = per_size[size]
        ok = (agg["pass"] == repeats and agg["skip"] == 0)
        lines.append("  档 d%s（%s tokens）：%d/%d 中、SKIP %d、FAIL %d —— %s"
                     % (int(size) // 1000, size, agg["pass"], repeats,
                        agg["skip"], agg["fail"],
                        "全中" if ok else "未全中/证据缺失"))
        gate = gate and ok
    return gate, lines


def run(args):
    if not args.base:
        print("FATAL 缺 --base（引擎/base URL），无法发针（fail-closed）")
        return 2
    probe = os.path.expanduser(args.needle_probe)
    if not os.path.exists(probe):
        print("FATAL needle_probe 缺位：%s（--needle-probe 可覆盖）" % probe)
        return 2
    out_dir = os.path.expanduser(args.out_dir) if args.out_dir else os.path.join(
        "logs", "nvfp4-needle-gate", time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    os.makedirs(out_dir, exist_ok=True)

    per_size = {str(s): {"pass": 0, "fail": 0, "skip": 0} for s in args.sizes}
    fatal = 0
    for size in args.sizes:
        for i in range(1, args.repeats + 1):
            seed = "nvfp4gate-%s-%d-%d" % (args.phase, size, i)
            jout = os.path.join(out_dir, "d%d-s%d.json" % (size, i))
            argv = build_probe_argv(probe, args.base, args.model, args.form,
                                    size, seed, args.depth, jout)
            ok, data, err = run_one_probe(argv, args.timeout)
            if not ok:
                print("FATAL 档 d%d 第 %d 针取证失败：%s" % (size // 1000 if size >= 1000 else size, i, err))
                fatal += 1
                continue
            t = tally(data["rows"], size)
            per_size[str(size)]["pass"] += t["pass"]
            per_size[str(size)]["fail"] += t["fail"]
            per_size[str(size)]["skip"] += t["skip"]
            print("[gate] d%s 第 %d 针：%s%s" % (
                size // 1000 if size >= 1000 else size, i, t["status"],
                "（%s）" % t["reason"] if t["reason"] else ""))
    if fatal:
        print("== 取证失败 %d 针（fail-closed），不判门 ==")
        return 2

    gate, lines = aggregate(per_size, args.repeats, args.phase)
    print("== nvfp4_needle_gate（%s 相位；判据=issue #42369 剥后口径 4/4+4/4）==" % args.phase)
    for ln in lines:
        print(ln)
    summary = {"tool": TOOL_VER, "issue": ISSUE_URL, "phase": args.phase,
               "base": args.base, "form": args.form, "sizes": args.sizes,
               "repeats": args.repeats, "depth": args.depth,
               "per_size": per_size, "gate_pass": gate,
               "gate_semantics": ("post-strip=每档全中方放行" if args.phase == "post-strip"
                                  else "pre-strip=取证记录，恒不放行（预期红=诊断证据）")}
    spath = os.path.join(out_dir, "gate-summary.json")
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("== 判定：%s（汇总在档 %s）==" % (
        "门绿（可开门：nvfp4_kv_scale_guard 判据③须同绿）" if gate and args.phase == "post-strip"
        else "门未放行", spath))
    if args.phase == "post-strip":
        return 0 if gate else 1
    return 0


# ── 离线自检（不发包）：聚合判别力 + argv 组装 + 语义 ──
def selfcheck():
    n_pass = 0
    total = 5

    def rows(status):
        return [{"target_tokens": 50000, "status": status}]

    # N1：剥后 4/4+4/4 → 门绿
    per = {"50000": {"pass": 4, "fail": 0, "skip": 0},
           "500000": {"pass": 4, "fail": 0, "skip": 0}}
    gate, _ = aggregate(per, 4, "post-strip")
    n_pass += gate
    print("%s N1 剥后 4/4+4/4→门绿" % ("PASS" if gate else "FAIL"))

    # N2：3/4（issue 剥前口径同型）→ 门红
    per = {"50000": {"pass": 3, "fail": 1, "skip": 0},
           "500000": {"pass": 0, "fail": 4, "skip": 0}}
    gate, _ = aggregate(per, 4, "post-strip")
    ok = not gate
    n_pass += ok
    print("%s N2 3/4+0/4（=issue 剥前口径）→门红" % ("PASS" if ok else "FAIL"))

    # N3：SKIP=证据缺失 → 门红（无证据不得放行）
    per = {"50000": {"pass": 3, "fail": 0, "skip": 1},
           "500000": {"pass": 4, "fail": 0, "skip": 0}}
    gate, _ = aggregate(per, 4, "post-strip")
    ok = not gate
    n_pass += ok
    print("%s N3 SKIP 一针=证据缺失→门红（fail-closed）" % ("PASS" if ok else "FAIL"))

    # N4：argv 组装——form/sizes/seed/json-out 全部就位（500K 档走 r1 形态门是
    #     needle_probe 侧职责，本件只保证参数面完整传递）
    argv = build_probe_argv("/p/needle_probe.py", "http://h:1", "m", "r1",
                            500000, "s1", 0.5, "/o.json")
    ok = ("--form" in argv and argv[argv.index("--form") + 1] == "r1"
          and argv[argv.index("--sizes") + 1] == "500000"
          and argv[argv.index("--seed") + 1] == "s1"
          and argv[-1] == "/o.json")
    n_pass += ok
    print("%s N4 探针 argv 组装（form=r1/sizes/seed/json-out 全就位）" % ("PASS" if ok else "FAIL"))

    # N5：pre-strip 相位恒不放行（取证 ≠ 验收）
    per = {"50000": {"pass": 4, "fail": 0, "skip": 0},
           "500000": {"pass": 4, "fail": 0, "skip": 0}}
    gate, _ = aggregate(per, 4, "pre-strip")
    ok = not gate
    n_pass += ok
    print("%s N5 pre-strip 全中也不放行（取证相位≠验收相位）" % ("PASS" if ok else "FAIL"))

    print("== selfcheck 结束：%d/%d ==" % (n_pass, total))
    return 0 if n_pass == total else 1


def build_parser():
    ap = argparse.ArgumentParser(description="nvfp4 剥 scales 手术 needle 验收门（issue #42369）")
    ap.add_argument("--base", help="引擎 base URL（如 http://127.0.0.1:8899；selfcheck 外必填）")
    ap.add_argument("--model", default="deepseek-v4.1-flash")
    ap.add_argument("--form", default="r1",
                    help="needle_probe 形态（缺省 r1=600K 上限，500K 档所需；换栈按 --form 正典登记改）")
    ap.add_argument("--sizes", type=int, nargs="+", default=[50000, 500000],
                    help="文档档位（token；缺省 d50/d500=50000 500000）")
    ap.add_argument("--repeats", type=int, default=4, help="每档针数（缺省 4，issue 口径）")
    ap.add_argument("--depth", type=float, default=0.5)
    ap.add_argument("--phase", choices=["pre-strip", "post-strip"], default="post-strip")
    ap.add_argument("--out-dir")
    ap.add_argument("--needle-probe", default=DEFAULT_PROBE)
    ap.add_argument("--timeout", type=int, default=1800, help="单针超时秒（500K 档 prefill 长）")
    ap.add_argument("--selfcheck", action="store_true", help="离线自检（不发包）")
    return ap


def main():
    args = build_parser().parse_args()
    if args.selfcheck:
        return selfcheck()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
