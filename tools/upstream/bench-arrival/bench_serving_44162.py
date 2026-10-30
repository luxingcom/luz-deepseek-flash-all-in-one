#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_serving_44162.py — sglang bench_serving 开环 --request-rate 基准的 #44162 修补版载体（薄启动器）。

法源：上游 sgl-project/sglang PR #44162（[Fix] benchmark: Compensate cumulative
request arrival drift；fixes issue #43930；2026-10 时点 open 未合）。缺陷与修法
详见同目录 bench_arrival_guard.py 头注与本目录 README.md。

本件职责：**不重烘镜像、不改上游源码树、不装包**，在 host 侧以运行时覆盖
（runtime override）把 sglang.benchmark.serving 的缺陷版 get_request 换成
#44162 修补版，然后原样透传 bench_serving 全部 CLI 参数——凡开环有限
--request-rate 的延迟/吞吐基准一律经本件跑，避免把到达调度漂移算进引擎回归。
（闭环并发类量具 sd_bench/de_c48/conc_pr_driver 无到达率调度面，不经本件。）

判定与行为：
  - 目标 sglang 的 get_request 为缺陷版 → 注入修补版（get_request_44162），
    打印 PATCHED 后透传 cli_main()；
  - 已含 #44162 修法 → 打印 ALREADY-FIXED 直接透传（不二次包装）；
  - 签名不识 → rc=2 fail-closed 拒跑（不凭猜测放行）；
  - 取不到 sglang（源码树/安装）→ rc=2。

sglang 定位优先级：--sglang-root > $SGLANG_ROOT > ~/sglang-main-src > 已安装包。

RNG 兼容性（#44162 修法的核心关切）：修补函数以被修补模块的 __dict__ 为全局
命名空间 exec（np/time/asyncio 全继承原模块对象），exponential draw 的次数与
顺序、与 consumer 侧 NumPy draw 的 interleaving、以及消费完后的 RNG state 均与
上游修复版一致（最后请求后的多余 draw 保留、terminal sleep 移除）。

退出码：0=bench 正常结束（含 PATCHED/ALREADY-FIXED）；1=bench 自身失败；
2=取证/定位失败（fail-closed）。--selfcheck 恒离线（不 import 真 sglang、不发包）。

用法：
  python3 bench_serving_44162.py [--sglang-root PATH] [--] <bench_serving 原参数...>
  python3 bench_serving_44162.py --selfcheck
示例：
  python3 bench_serving_44162.py --host 127.0.0.1 --port 8899 --backend sglang \\
      --dataset-name sharegpt --request-rate 100 --num-prompts 1000

红线：本件不写任何仓面/产线面；零 git、零引擎/容器生命周期、不动镜像。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from bench_arrival_guard import (  # noqa: E402  （同目录正典件，双面 md5 互证）
    _FIXTURE_FIXED,
    _FIXTURE_VULN,
    _consume,
    _make_fixture_module,
    classify_get_request,
    extract_get_request_source,
    resolve_serving_py,
)

# #44162 修补版 get_request 全文（泊松分支=上游 diff；trace 分支=上游原样，
# 本身已是绝对时刻法不受缺陷影响）。exec 进目标模块 __dict__ 后 np/time/asyncio
# 均为该模块对象（RNG 兼容；见类注）。
PATCH_SRC = '''
async def get_request_44162(
    input_requests,
    request_rate,
    use_trace_timestamps=False,
    slowdown_factor=1.0,
):
    # sglang PR #44162 patched get_request (cumulative absolute arrival deadlines).
    if use_trace_timestamps:
        print(
            "Using trace timestamps for request generation with slowdown factor "
            + str(slowdown_factor)
            + "."
        )
        input_requests.sort(key=lambda r: r.timestamp)
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
                # If the request rate is infinity, then we don't need to wait.
                continue

            # Sample the request interval from the exponential distribution.
            # Keep the final draw for RNG compatibility, but do not wait after
            # the last request since there is no next arrival to schedule.
            interval = np.random.exponential(1.0 / request_rate)
            target_arrival_time += interval
'''


def locate_sglang_python(explicit=None):
    """返回应插入 sys.path 的 sglang python 根（源码树 python/ 或安装根）；找不到 None。"""
    cands = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("SGLANG_ROOT"):
        cands.append(os.environ["SGLANG_ROOT"])
    cands.append(os.path.expanduser("~/sglang-main-src"))
    for c in cands:
        c = os.path.abspath(os.path.expanduser(c))
        if resolve_serving_py(c):
            if os.path.isdir(os.path.join(c, "python", "sglang")):
                return os.path.join(c, "python")
            if os.path.isdir(os.path.join(c, "sglang")):
                return c
    return None


def get_module_source(mod, func_name):
    """运行时取模块函数源码文本；取不到（内联/exec 件）返回 None。"""
    import inspect

    fn = getattr(mod, func_name, None)
    if fn is None:
        return None
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return None


def patch_module(serving, source_provider=get_module_source):
    """对 serving 模块应用 #44162 修补。

    返回 ('PATCHED' | 'ALREADY-FIXED' | 'UNKNOWN', detail)。
    source_provider(mod, name) 抽象出源码获取以便离线自检注入 fake。
    """
    src = source_provider(serving, "get_request")
    if src is None:
        return "UNKNOWN", "取不到 get_request 源码（inspect 失败）"
    verdict = classify_get_request(src)
    if verdict == "FIXED":
        return "ALREADY-FIXED", "目标模块已含 #44162 修法，直接透传"
    if verdict != "VULNERABLE":
        return "UNKNOWN", "get_request 签名不识（非缺陷版亦非 #44162 形）"
    # exec 进模块自身 __dict__：np/time/asyncio 继承模块对象（RNG 兼容），
    # get_request_44162 落进模块命名空间后重绑 get_request（serving.py 内
    # 调用点为模块全局名查找，替换即生效）。
    ns = serving.__dict__
    exec(compile(PATCH_SRC, "<sglang_pr44162_patch>", "exec"), ns)
    ns["get_request"] = ns["get_request_44162"]
    return "PATCHED", "已注入 get_request_44162 并重绑 get_request"


def selfcheck():
    import asyncio
    import types

    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    # 一、fake serving（缺陷版）→ PATCHED，且重绑生效。
    mod = _make_fixture_module()
    ns0 = dict(mod.__dict__)
    exec(compile(_FIXTURE_VULN, "<fake_serving_src>", "exec"), ns0)
    fake = types.ModuleType("fake_serving")
    fake.__dict__.update(ns0)
    fake.__file__ = "<fake>"  # inspect.getsource 会失败 → 走可注入 source_provider
    provider_calls = {}

    def fake_provider(m, name):
        provider_calls[name] = provider_calls.get(name, 0) + 1
        return _FIXTURE_VULN if name == "get_request" else None

    status, detail = patch_module(fake, source_provider=fake_provider)
    check("vulnerable module -> PATCHED", status == "PATCHED", "%s (%s)" % (status, detail))
    check("get_request rebound to patched impl",
          fake.__dict__.get("get_request") is fake.__dict__.get("get_request_44162"))

    # 二、修补后语义（假时钟确定性序列）：到达表=名义 gap 表（work 吃进 gap）。
    n, work, gap, t0 = 20, 0.004, 0.010, 1000.0
    arr = asyncio.run(_consume(fake.get_request(list(range(n)), 1.0 / gap), mod.clock, work))
    check("patched arrivals hit ideal schedule (last=%.4fs)" % (arr[-1] - t0),
          all(abs((a - t0) - gap * i) < 1e-9 for i, a in enumerate(arr)))
    check("RNG draws via module np object (n draws kept)", mod.np.calls == n,
          "calls=%d" % mod.np.calls)

    # 三、fake serving（已修复版）→ ALREADY-FIXED，函数不动。
    mod_f = _make_fixture_module()
    ns_f = dict(mod_f.__dict__)
    exec(compile(_FIXTURE_FIXED, "<fake_fixed_src>", "exec"), ns_f)
    fake_f = types.ModuleType("fake_serving_fixed")
    fake_f.__dict__.update(ns_f)
    orig_fn = fake_f.get_request
    status_f, detail_f = patch_module(
        fake_f, source_provider=lambda m, name: _FIXTURE_FIXED if name == "get_request" else None
    )
    check("fixed module -> ALREADY-FIXED", status_f == "ALREADY-FIXED", detail_f)
    check("fixed module function untouched", fake_f.get_request is orig_fn)

    # 四、UNKNOWN（源码取不到）→ fail-closed。
    fake_u = types.ModuleType("fake_serving_unknown")
    status_u, detail_u = patch_module(fake_u, source_provider=lambda m, name: None)
    check("unknown source -> UNKNOWN (fail-closed)", status_u == "UNKNOWN", detail_u)

    # 五、PATCH_SRC 本体判别器自证：注入文本即 #44162 形。
    patched_src = PATCH_SRC.replace("get_request_44162", "get_request")
    check("PATCH_SRC classifies FIXED", classify_get_request(patched_src) == "FIXED",
          classify_get_request(patched_src))

    # 六、定位器：缺省候选缺位不崩（返回 None 或有效根，取决于宿主）。
    root = locate_sglang_python()
    check("locator returns None-or-existing-root",
          root is None or os.path.isdir(root), str(root))

    # 七、本件与 guard 的补丁同源性：两版泊松分支去注释规范化后代码级一致。
    from bench_arrival_guard import _PATCH_SRC as guard_patch

    def _poisson_core(src):
        marker = "target_arrival_time = time.perf_counter()"
        if marker not in src:
            return []
        body = src[src.index(marker):]
        out = []
        for ln in body.splitlines():
            code = ln.split("#", 1)[0].rstrip()
            if code.strip():
                out.append(code.strip())
        return out

    check("guard/launcher poisson cores code-identical",
          _poisson_core(guard_patch) == _poisson_core(PATCH_SRC))

    n_pass = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", name, detail if detail != "" else ""))
    total = len(results)
    print("SELFCHECK %s n=%d fail=%d" % ("PASS" if n_pass == total else "FAIL", total, total - n_pass))
    print("（本行 n=实际执行断言数，为权威数）")
    return 0 if n_pass == total else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selfcheck" in argv:
        return selfcheck()

    explicit_root = None
    passthrough = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--sglang-root":
            if i + 1 >= len(argv):
                print("[rc2] --sglang-root 需要一个路径参数")
                return 2
            explicit_root = argv[i + 1]
            i += 2
            continue
        if a.startswith("--sglang-root="):
            explicit_root = a.split("=", 1)[1]
            i += 1
            continue
        if a == "--":
            i += 1
            passthrough.extend(argv[i:])
            break
        passthrough.append(a)
        i += 1

    root = locate_sglang_python(explicit_root)
    if root is None:
        print("[rc2] FAIL-CLOSED: 定位不到 sglang（--sglang-root 给源码树根（含 python/sglang）")
        print("      或安装根；或设 SGLANG_ROOT；缺省候选 ~/sglang-main-src）。开环基准不得")
        print("      在无 #44162 判定的情况下放行。")
        return 2
    if root not in sys.path:
        sys.path.insert(0, root)

    try:
        import sglang.benchmark.serving as serving  # noqa: E401
    except Exception as e:  # 取证失败即拒跑
        print("[rc2] FAIL-CLOSED: import sglang.benchmark.serving 失败（root=%s）：%r" % (root, e))
        return 2

    status, detail = patch_module(serving)
    if status == "UNKNOWN":
        print("[rc2] FAIL-CLOSED: %s；不得凭猜测放行，人工核对该函数后更新判别器。" % detail)
        return 2
    print("[bench_serving_44162] %s：%s" % (status, detail))
    print("[bench_serving_44162] sglang root=%s；透传参数：%d 个" % (root, len(passthrough)))

    sys.argv = [sys.argv[0]] + passthrough
    return serving.cli_main()


if __name__ == "__main__":
    sys.exit(main())
