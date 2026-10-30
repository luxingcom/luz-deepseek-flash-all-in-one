#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_arrival_guard.py — sglang bench_serving --request-rate 到达漂移缺陷的口径守卫（判别 + lint）。

法源：上游 sgl-project/sglang PR #44162（[Fix] benchmark: Compensate cumulative
request arrival drift；fixes issue #43930；2026-10 时点 open 未合）。缺陷：
`python/sglang/benchmark/serving.py` 的 `get_request` 泊松（finite-rate, 非 trace）
分支把 `await asyncio.sleep(interval)` 放在 yield 之后、以 consumer 恢复 generator
的时刻为起点——consumer 的发包/收流/记账工作与事件循环晚唤醒逐请求累积进到达
间隔，实际 offered load 系统性偏低（上游报告 100 req/s 档实测 ~68 req/s、
400 req/s 档实测 ~190 req/s）。修法（#44162）：累积单调绝对到达时刻
`target_arrival_time`，每次 yield 前只 sleep 剩余时间，迟到请求立即追上而不重置
调度表；terminal sleep 移除但保留最后一次 exponential draw（RNG 兼容）。

本件职责（与同目录 bench_serving_44162.py 配套）：
  1) --check：判别一份 sglang（源码树/安装根/serving.py 单件）的 get_request
     是缺陷版（VULNERABLE）还是已修复版（FIXED）；取不到源/签名不识 = rc2
     fail-closed，不得凭猜测放行。
  2) --lint：扫仓面（.sh/.py/.md/.tsv/.txt/.json/.yaml）里「裸跑 sglang
     bench_serving 且 --request-rate 为有限值」的计量口径——开环有限速率基准
     必须经修补件 bench_serving_44162.py 跑（或带豁免标记），否则 REFUSE。
  3) --selfcheck：离线红绿夹具自检（不 import sglang、不发包、不写仓）。

退出码：0=PASS（含 WARN）；1=FAIL/REFUSE；2=取证失败（fail-closed）。

红线：本件只读产线与仓面；零 git、零引擎/容器生命周期、不动镜像。
用法示例：
  python3 bench_arrival_guard.py --check                          # 缺省 ~/sglang-main-src
  python3 bench_arrival_guard.py --check --path ~/sglang-main-src  # 源码树/安装根/serving.py
  python3 bench_arrival_guard.py --lint /path/to/repo              # 缺省扫双仓 tools+docs
  python3 bench_arrival_guard.py --selfcheck
"""

import argparse
import os
import re
import sys
import tempfile

# ---------------------------------------------------------------------------
# 判别器
# ---------------------------------------------------------------------------

# 缺陷签名（泊松分支）：draw interval 后直接睡 interval（起点=consumer 恢复时刻）。
_SIG_VULN = re.compile(
    r"interval\s*=\s*np\.random\.exponential\(\s*1\.0\s*/\s*request_rate\s*\)"
    r"[\s\S]{0,200}?await\s+asyncio\.sleep\(interval\)",
    re.S,
)
# 修复签名（#44162）：绝对到达时刻累积 + yield 前 sleep 剩余时间。
_SIG_FIXED_TARGET = re.compile(r"target_arrival_time\s*\+=")
_SIG_FIXED_PRE = re.compile(
    r"sleep_duration\s*=\s*target_arrival_time\s*-\s*time\.perf_counter\(\)"
)


def extract_get_request_source(text):
    """从 serving.py 全文提取 async def get_request(...) 的函数体源码块。

    用括号/缩进不敏感的逐行深度计数（async def 起行到下一个同缩进顶层 def/class
    或文件尾）。取不到返回 None。
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^async\s+def\s+get_request\s*\(", ln):
            start = i
            break
    if start is None:
        return None
    base_indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() == "":
            out.append(ln)
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= base_indent and ln.strip() and not ln.lstrip().startswith(")"):
            # 回到函数体同缩进的下一顶层定义即止（含闭括号行归并容忍）。
            if re.match(r"^(async\s+)?def\s|^class\s+", ln.lstrip()):
                break
        out.append(ln)
    return "\n".join(out)


def classify_get_request(func_src):
    """判别 get_request 源码：'FIXED' / 'VULNERABLE' / 'UNKNOWN'。"""
    if not func_src or "def get_request" not in func_src:
        return "UNKNOWN"
    has_fixed = bool(_SIG_FIXED_TARGET.search(func_src)) and bool(
        _SIG_FIXED_PRE.search(func_src)
    )
    has_vuln = bool(_SIG_VULN.search(func_src))
    if has_fixed and not has_vuln:
        return "FIXED"
    if has_vuln and not has_fixed:
        return "VULNERABLE"
    if has_fixed and has_vuln:
        # 两种签名并存：泊松分支若仍带 terminal sleep(interval) 即未修完整。
        return "VULNERABLE"
    return "UNKNOWN"


def resolve_serving_py(path):
    """路径解析：serving.py 单件 / sglang 源码树根 / 安装根 → serving.py 绝对路径。"""
    p = os.path.abspath(os.path.expanduser(path))
    if os.path.isfile(p):
        return p
    candidates = [
        os.path.join(p, "python", "sglang", "benchmark", "serving.py"),  # 源码树
        os.path.join(p, "sglang", "benchmark", "serving.py"),            # 安装根/PYTHONPATH 面
        os.path.join(p, "benchmark", "serving.py"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def default_serving_py():
    """缺省探测：$SGLANG_ROOT → ~/sglang-main-src → 已安装包 → None。"""
    env_root = os.environ.get("SGLANG_ROOT")
    for cand in [env_root, os.path.expanduser("~/sglang-main-src")]:
        if cand:
            got = resolve_serving_py(cand)
            if got:
                return got
    try:
        import importlib.util

        spec = importlib.util.find_spec("sglang")
        if spec and spec.submodule_search_locations:
            got = resolve_serving_py(list(spec.submodule_search_locations)[0])
            if got:
                return got
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# lint：--request-rate 使用纪律
# ---------------------------------------------------------------------------

_BENCH_CMD = re.compile(
    r"bench_serving|sglang\.benchmark\.serving|sglang\.bench_serving"
)
_RATE_FLAG = re.compile(r"--request-rate(\s+|=)([^\s\"']+)")
_EXEMPT = re.compile(r"bench-arrival:\s*(patched|closed-loop|doc)")

_LINT_SUFFIXES = {".sh", ".py", ".md", ".tsv", ".txt", ".json", ".yaml", ".yml"}

# 工具本体（自描述必然含 bench_serving/--request-rate 字样，不适用 lint）。
_LINT_SELFILES = {"bench_arrival_guard.py", "bench_serving_44162.py"}


def _finite_rate(val):
    try:
        f = float(val)
    except (TypeError, ValueError):
        return True  # 非数值（变量名等）按有限速率对待（fail-closed）
    return f != float("inf")


def lint_file(path, findings):
    """单件扫描：bench_serving 命令 ±3 行内出现有限 --request-rate 且无豁免标记即记 findings。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as e:
        findings.append((path, 0, "READ-FAIL", str(e)))
        return
    n = len(lines)
    for i, ln in enumerate(lines):
        if not _BENCH_CMD.search(ln):
            continue
        lo, hi = max(0, i - 3), min(n, i + 4)
        ctx = "".join(lines[lo:hi])
        if _EXEMPT.search(ctx):
            continue
        for j in range(lo, hi):
            m = _RATE_FLAG.search(lines[j])
            if m and _finite_rate(m.group(2)):
                findings.append(
                    (
                        path,
                        j + 1,
                        "OPEN-LOOP-UNPATCHED",
                        "bench_serving 有限 --request-rate=%s 开环口径未经 #44162 修补件"
                        "（bench_serving_44162.py）或豁免标记（bench-arrival: patched/"
                        "closed-loop/doc）" % m.group(2),
                    )
                )


def lint_paths(paths):
    findings = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isfile(p):
            if os.path.basename(p) not in _LINT_SELFILES:
                lint_file(p, findings)
        elif os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in (".git", "__pycache__", "node_modules")
                ]
                for f in sorted(files):
                    if os.path.splitext(f)[1] in _LINT_SUFFIXES and f not in _LINT_SELFILES:
                        lint_file(os.path.join(root, f), findings)
        else:
            findings.append((p, 0, "PATH-MISSING", "路径不存在"))
    # 去重（同文件同行同码只记一次）
    seen = set()
    uniq = []
    for it in findings:
        key = it[:3]
        if key not in seen:
            seen.add(key)
            uniq.append(it)
    return uniq


def default_lint_targets():
    """缺省扫双仓（战役仓 + 公开面）的 tools 与 docs 面。"""
    home = os.path.expanduser("~")
    cands = [
        os.path.join(home, "luz030-opt-campaign", "tools"),
        os.path.join(home, "luz030-opt-campaign", "docs"),
        os.path.join(home, "luz-034re", "tools"),
        os.path.join(home, "luz-034re", "docs"),
    ]
    return [c for c in cands if os.path.isdir(c)]


# ---------------------------------------------------------------------------
# selfcheck（离线，不 import sglang、不发包、不写仓）
# ---------------------------------------------------------------------------

# 夹具：缺陷版（本仓基线 79cafec0 泊松分支同构）与修复版（#44162 同构）。
_FIXTURE_VULN = '''
async def get_request(input_requests, request_rate, use_trace_timestamps=False, slowdown_factor=1.0):
    if use_trace_timestamps:
        for request in input_requests:
            yield request
    else:
        input_requests_iter = iter(input_requests)
        for request in input_requests_iter:
            yield request
            if request_rate == float("inf"):
                continue
            interval = np.random.exponential(1.0 / request_rate)
            # The next request will be sent after the interval.
            await asyncio.sleep(interval)
'''

_FIXTURE_FIXED = '''
async def get_request(input_requests, request_rate, use_trace_timestamps=False, slowdown_factor=1.0):
    if use_trace_timestamps:
        for request in input_requests:
            yield request
    else:
        target_arrival_time = time.perf_counter()
        input_requests_iter = iter(input_requests)
        for request in input_requests_iter:
            if request_rate != float("inf"):
                sleep_duration = target_arrival_time - time.perf_counter()
                if sleep_duration > 0:
                    await asyncio.sleep(sleep_duration)
            yield request
            if request_rate == float("inf"):
                continue
            interval = np.random.exponential(1.0 / request_rate)
            target_arrival_time += interval
'''

_PATCH_SRC = '''
async def get_request_44162(input_requests, request_rate, use_trace_timestamps=False, slowdown_factor=1.0):
    # —— #44162 修补版（泊松分支绝对到达时刻法；trace 分支与上游原样一致）——
    if use_trace_timestamps:
        start_time = time.perf_counter()
        trace_start_time_ms = input_requests[0].timestamp if input_requests else 0
        for request in input_requests:
            trace_time_s = (request.timestamp - trace_start_time_ms) / 1000.0
            target_arrival_time = start_time + (trace_time_s * slowdown_factor)
            sleep_duration = target_arrival_time - time.perf_counter()
            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)
            yield request
    else:
        target_arrival_time = time.perf_counter()
        input_requests_iter = iter(input_requests)
        for request in input_requests_iter:
            if request_rate != float("inf"):
                # Compensate for late wake-ups and work done by the consumer.
                sleep_duration = target_arrival_time - time.perf_counter()
                if sleep_duration > 0:
                    await asyncio.sleep(sleep_duration)
            yield request
            if request_rate == float("inf"):
                continue
            # Sample the request interval from the exponential distribution.
            # Keep the final draw for RNG compatibility, but do not wait after
            # the last request since there is no next arrival to schedule.
            interval = np.random.exponential(1.0 / request_rate)
            target_arrival_time += interval
'''


class _FakeRandom:
    def __init__(self, seq):
        self.seq = list(seq)
        self.calls = 0

    def exponential(self, scale):
        v = self.seq[self.calls] if self.calls < len(self.seq) else 0.0
        self.calls += 1
        return v


class _FakeNp:
    """确定性 np.random.exponential 序列（离线验证到达时刻表与 RNG draw 序）。"""

    def __init__(self, seq):
        self.random = _FakeRandom(seq)

    @property
    def calls(self):
        return self.random.calls


class _FakeTime:
    def __init__(self):
        self.now = 1000.0

    def perf_counter(self):
        return self.now


class _FakeAsyncio:
    def __init__(self, clock):
        self.clock = clock
        self.sleep_log = []

    async def sleep(self, d):
        self.sleep_log.append((self.clock.now, d))
        self.clock.now += max(0.0, d)  # 理想精确唤醒（晚唤醒另测）
        return None


def _make_fixture_module():
    import types

    mod = types.ModuleType("fake_serving_fixture")
    clock = _FakeTime()
    mod.np = _FakeNp([0.010] * 64)
    mod.time = clock
    mod.asyncio = _FakeAsyncio(clock)
    mod.clock = clock
    return mod


async def _consume(gen, clock, work):
    arrivals = []
    async for r in gen:
        arrivals.append(clock.now)
        clock.now += work  # consumer 的发包/记账工作（缺陷版把它累进到达间隔）
    return arrivals


def selfcheck():
    import asyncio
    import types

    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    # 一、判别器红绿
    check("classify vuln fixture", classify_get_request(_FIXTURE_VULN) == "VULNERABLE",
          classify_get_request(_FIXTURE_VULN))
    check("classify fixed fixture", classify_get_request(_FIXTURE_FIXED) == "FIXED",
          classify_get_request(_FIXTURE_FIXED))
    check("classify unknown (no func)", classify_get_request("") == "UNKNOWN")
    # 本仓基线真件（若在盘）应判 VULNERABLE——离线可选证。
    base = default_serving_py()
    if base and os.path.isfile(base):
        with open(base, "r", encoding="utf-8", errors="replace") as fh:
            src = extract_get_request_source(fh.read())
        check("classify local checkout (%s)" % os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(base)))),
              classify_get_request(src) in ("VULNERABLE", "FIXED", "UNKNOWN"),
              classify_get_request(src))
    else:
        check("classify local checkout SKIP (no sglang on host)", True, "host 无 sglang 源/包，判别器夹具面已覆盖")

    # 二、源码提取器
    full = "import x\n\n\n" + _FIXTURE_VULN.strip() + "\n\n\ndef calculate_metrics():\n    pass\n"
    got = extract_get_request_source(full)
    check("extractor pulls get_request block", got is not None and "await asyncio.sleep(interval)" in got)

    # 三、语义验证（假时钟，确定性 exponential 序列=gap 常数）。
    # 场景 B（work < gap，主区分场景）：consumer 每请求工作 4ms，泊松 gap 10ms。
    n, work, gap = 20, 0.004, 0.010
    t0 = 1000.0

    mod_v = _make_fixture_module()
    ns_v = dict(mod_v.__dict__)
    exec(compile(_FIXTURE_VULN, "<vuln_fixture>", "exec"), ns_v)
    arr_v = asyncio.run(_consume(ns_v["get_request"](list(range(n)), 1.0 / gap), mod_v.clock, work))

    mod_p = _make_fixture_module()
    ns_p = dict(mod_p.__dict__)
    exec(compile(_PATCH_SRC, "<patch_fixture>", "exec"), ns_p)
    arr_p = asyncio.run(_consume(ns_p["get_request_44162"](list(range(n)), 1.0 / gap), mod_p.clock, work))

    # 缺陷版：到达 i = i*(gap+work)——consumer 工作逐请求累进到达间隔（漂移随 n 线性）。
    check("B vuln arrivals lag by work*i (last=%.4fs vs ideal %.4fs)" % (arr_v[-1] - t0, gap * (n - 1)),
          all(abs((a - t0) - (gap + work) * i) < 1e-9 for i, a in enumerate(arr_v)))
    # 修补版：到达 i = i*gap——工作吃进 gap 剩余，到达表=名义时刻表（漂移=0）。
    check("B patched arrivals hit ideal schedule (last=%.4fs)" % (arr_p[-1] - t0),
          all(abs((a - t0) - gap * i) < 1e-9 for i, a in enumerate(arr_p)))

    # 场景 C（work > gap，消费端饱和）：物理上限=消费率，修补版=上限连发，缺陷版更慢一拍。
    work_c = 0.05
    mod_vc = _make_fixture_module()
    ns_vc = dict(mod_vc.__dict__)
    exec(compile(_FIXTURE_VULN, "<vuln_c>", "exec"), ns_vc)
    arr_vc = asyncio.run(_consume(ns_vc["get_request"](list(range(n)), 1.0 / gap), mod_vc.clock, work_c))
    mod_pc = _make_fixture_module()
    ns_pc = dict(mod_pc.__dict__)
    exec(compile(_PATCH_SRC, "<patch_c>", "exec"), ns_pc)
    arr_pc = asyncio.run(_consume(ns_pc["get_request_44162"](list(range(n)), 1.0 / gap), mod_pc.clock, work_c))
    check("C saturation: patched = consumer-rate cap (i*%.3f)" % work_c,
          all(abs((a - t0) - work_c * i) < 1e-9 for i, a in enumerate(arr_pc)))
    check("C saturation: vuln slower than cap (i*%.3f)" % (work_c + gap),
          all(abs((a - t0) - (work_c + gap) * i) < 1e-9 for i, a in enumerate(arr_vc))
          and arr_vc[-1] > arr_pc[-1])

    # 四、RNG 兼容：同序列 draws 下两版调用数一致（最后 draw 保留，与上游修法同）。
    check("RNG draw count preserved (v=%d p=%d)" % (mod_v.np.calls, mod_p.np.calls),
          mod_v.np.calls == mod_p.np.calls == n)

    # 五、晚唤醒（sleep 每次多醒 20ms > gap 10ms）：迟到立即追上、不重置时刻表、
    #    追平后恢复按表睡（上游 #44162 测试族 test_overdue_requests_catch_up_then_resume_schedule）。
    class _LateAsyncio(_FakeAsyncio):
        async def sleep(self, d):
            self.sleep_log.append((self.clock.now, d))
            self.clock.now += max(0.0, d) + 0.02
            return None

    mod_l = _make_fixture_module()
    mod_l.asyncio = _LateAsyncio(mod_l.clock)
    ns_l = dict(mod_l.__dict__)
    ns_l["asyncio"] = mod_l.asyncio
    exec(compile(_PATCH_SRC, "<patch_late>", "exec"), ns_l)
    n_l = 6
    arr_l = asyncio.run(_consume(ns_l["get_request_44162"](list(range(n_l)), 1.0 / gap), mod_l.clock, 0.0))
    late = mod_l.asyncio
    # 不变量①：每次 sleep 的终点（now+d）都落在名义时刻表 {t0+gap*i} 上（不漂移）。
    on_schedule = all(
        any(abs((t + d) - (t0 + gap * i)) < 1e-9 for i in range(n_l))
        for t, d in late.sleep_log
    )
    # 不变量②：到达永不早于名义时刻表对应项（不抢跑）。
    no_early = all(a >= t0 + gap * i - 1e-9 for i, a in enumerate(arr_l))
    # 不变量③：每次晚醒 20ms 内追平（落后有界，不随 n 累积）。
    bounded = all((a - (t0 + gap * i)) <= 0.02 + 1e-9 for i, a in enumerate(arr_l))
    check("late wakeups: sleep endpoints on nominal schedule", on_schedule,
          "sleeps=%s" % [(round(t - t0, 4), round(d, 4)) for t, d in late.sleep_log])
    check("late wakeups: no early arrivals", no_early, str([round(a - t0, 4) for a in arr_l]))
    check("late wakeups: lag bounded by single oversleep", bounded,
          str([round(a - t0 - gap * i, 4) for i, a in enumerate(arr_l)]))
    # 对照：缺陷版同场景 gap 被拉成 gap+oversleep（offered rate ≈ 1/3）。
    mod_vl = _make_fixture_module()
    mod_vl.asyncio = _LateAsyncio(mod_vl.clock)
    ns_vl = dict(mod_vl.__dict__)
    ns_vl["asyncio"] = mod_vl.asyncio
    exec(compile(_FIXTURE_VULN, "<vuln_late>", "exec"), ns_vl)
    arr_vl = asyncio.run(_consume(ns_vl["get_request"](list(range(n_l)), 1.0 / gap), mod_vl.clock, 0.0))
    check("late wakeups: vuln gaps stretch to gap+oversleep",
          all(abs((a - t0) - (gap + 0.02) * i) < 1e-9 for i, a in enumerate(arr_vl)),
          str([round(a - t0, 4) for a in arr_vl]))

    # 六、inf 速率：零等待、零 draw。
    mod_i = _make_fixture_module()
    ns_i = dict(mod_i.__dict__)
    exec(compile(_PATCH_SRC, "<patch_inf>", "exec"), ns_i)
    arr_i = asyncio.run(_consume(ns_i["get_request_44162"](list(range(3)), float("inf")), mod_i.clock, 0.0))
    check("inf rate: no wait no draw", mod_i.clock.now == 1000.0 and mod_i.np.calls == 0 and len(arr_i) == 3)

    # 七、lint 红绿（tmpdir 内，不写仓）。
    with tempfile.TemporaryDirectory() as td:
        bad = os.path.join(td, "run_bad.sh")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("python -m sglang.benchmark.serving --host 127.0.0.1 --request-rate 100\n")
        good_patched = os.path.join(td, "run_good.sh")
        with open(good_patched, "w", encoding="utf-8") as fh:
            fh.write("python3 bench_serving_44162.py -- python -m sglang.benchmark.serving --request-rate 100  # bench-arrival: patched\n")
        good_inf = os.path.join(td, "run_inf.sh")
        with open(good_inf, "w", encoding="utf-8") as fh:
            fh.write("python -m sglang.bench_serving --request-rate inf\n")
        good_doc = os.path.join(td, "notes.md")
        with open(good_doc, "w", encoding="utf-8") as fh:
            fh.write("上游缺陷：`bench_serving --request-rate 100` 漂移。<!-- bench-arrival: doc -->\n")
        f1 = lint_paths([bad])
        check("lint flags bare open-loop run", any(x[2] == "OPEN-LOOP-UNPATCHED" for x in f1), str(f1))
        f2 = lint_paths([good_patched])
        check("lint passes patched marker", not any(x[2] == "OPEN-LOOP-UNPATCHED" for x in f2), str(f2))
        f3 = lint_paths([good_inf])
        check("lint passes inf rate", not any(x[2] == "OPEN-LOOP-UNPATCHED" for x in f3), str(f3))
        f4 = lint_paths([good_doc])
        check("lint passes doc marker", not any(x[2] == "OPEN-LOOP-UNPATCHED" for x in f4), str(f4))
        f5 = lint_paths([os.path.join(td, "nope")])
        check("lint missing path -> PATH-MISSING", any(x[2] == "PATH-MISSING" for x in f5), str(f5))

    n_pass = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, detail if detail != "" else ""))
    total = len(results)
    print("SELFCHECK %s n=%d fail=%d" % ("PASS" if n_pass == total else "FAIL", total, total - n_pass))
    print("（本行 n=实际执行断言数，为权威数）")
    return 0 if n_pass == total else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="判别 sglang get_request 缺陷态")
    ap.add_argument("--path", default=None,
                    help="--check 的目标：serving.py 单件 / sglang 源码树根 / 安装根（缺省自动探测）")
    ap.add_argument("--lint", nargs="*", default=None, metavar="PATH",
                    help="扫仓面 --request-rate 使用纪律（缺省双仓 tools+docs）")
    ap.add_argument("--selfcheck", action="store_true", help="离线自检")
    args = ap.parse_args()

    if args.selfcheck:
        return selfcheck()

    if args.check:
        target = resolve_serving_py(args.path) if args.path else default_serving_py()
        if not target:
            print("[rc2] FAIL-CLOSED: 取不到 serving.py（--path 给源码树根/安装根/单件；或设 SGLANG_ROOT）")
            return 2
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            print("[rc2] FAIL-CLOSED: 读 %s 失败：%s" % (target, e))
            return 2
        src = extract_get_request_source(text)
        verdict = classify_get_request(src)
        if verdict == "VULNERABLE":
            print("[rc1] VULNERABLE: %s 的 get_request 泊松分支带累积到达漂移（sleep(interval) 以" % target)
            print("      consumer 恢复时刻为起点；上游 #44162 未合/未含）。开环 --request-rate 基准")
            print("      必须经 bench_serving_44162.py 跑（该件会运行时替换为本修补版）。")
            return 1
        if verdict == "FIXED":
            print("[rc0] FIXED: %s 已含 #44162 修法（target_arrival_time 累积 + yield 前 sleep 剩余）。" % target)
            print("      开环基准可直接跑；bench_serving_44162.py 将自动透传（ALREADY-FIXED）。")
            return 0
        print("[rc2] FAIL-CLOSED: %s 的 get_request 签名不识（非缺陷版亦非 #44162 形），" % target)
        print("      不得凭猜测放行；请人工核对该函数后更新判别器夹具。")
        return 2

    if args.lint is not None:
        targets = args.lint if args.lint else default_lint_targets()
        findings = lint_paths(targets)
        if not findings:
            print("[rc0] LINT PASS：目标面无「未经修补的有限 --request-rate 开环口径」。")
            return 0
        for path, lineno, code, msg in findings:
            print("[rc1] %s:%d  %s  %s" % (path, lineno, code, msg))
        print("REFUSE：以上命中须改经 bench_serving_44162.py 跑，或加豁免标记")
        print("       （# bench-arrival: patched / closed-loop / doc）后复扫。")
        return 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
