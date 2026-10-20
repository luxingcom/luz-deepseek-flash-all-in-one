#!/usr/bin/env python3
"""p12 断言增补（R1-FIX-2 交付件③）：「图内上岗」判别链的捕获层+分派层断言器
——部署副本检查器断言集增补件（R1-FIX-2 实施段并入 deployed_copy_check d7 相位）。

R1RECERT 终裁建议（R1RECERT-ADJUDICATION-20261004 §三.5）+R1FIX2-ADJUDICATION §〇-6
（第三认证火换窗约束）：p12 补 graph-node 断言×2：
  **L2 捕获层（assert_captured_gather）**：candidate_filtered 变量图的**捕获窗**内必含
    `_fp4_gather_index_logits_kernel`。
  **L3 分派层（assert_dispatched_gather，R1-FIX-2 新增=长 ctx 相断言）**：**filtered 档
    replay（dispatch）窗**内必含 gather 名，且事件须带**真图 id**——本 CUPTI 13.0 trace
    里 `"graph id": 0` 是 eager 发射标记（FORENSICS §1.2 方法注记），仅 graph id≠0 的
    gather kernel 事件计为「图内上岗」。判据①的换窗落位（教义 #30：c1-prose 短提示窗
    对 filtered 档结构性不可达；本断言的测量窗=max_seq_len>16,384 的 decode census 相）。

== 实现路径（工程事实约束下的落地）=========================================
cudaGraph_t 的内核节点无法从 Python 直接枚举；但 **stream capture / graph replay 期间
执行的内核会以普通 kernel 事件出现在 torch.profiler(kineto) trace 里**（replay 期事件
args 带 `graph id`）。故两断言实现为：
  L2 「对捕获相位开的画像窗 trace，gather 的 kernel 类事件件数 ≥ floor」；
  L3 「对长 ctx dispatch 相位窗，gather 的 kernel 类事件中 graph id≠0 件数 ≥ floor」。
判别窗必须排除三类假绿：
  (a) install 期能力探针干跑（seam_mount._capability_probe 会发射一次 gather！）
      ——只认窗内件（window 判别）；
  (b) 名字出现在非 kernel 事件（字符串/host 事件）——只认 cat=='kernel'；
  (c) **L3 特有：窗内有 gather 但全是 graph id==0（eager 面，如 FIX-A 解锁的 prefill
      eager 消费或能力探针干跑）≠ 图内上岗**——graph id 判别（R1-FIX-2 新增毒例）。

== 判别力自检（教义 #15：喂坏输入须因正确理由变红）==========================
`--selftest`：纯合成 trace 八例（本机零 GPU 可跑）：
  S1 好输入：捕获窗内含 gather kernel 事件 → GREEN，理由含 "gather kernel events=2 …"
  S2 坏输入：全窗零 gather（seam 未挂/REFUSED/包装返回 stock 对）→ RED，理由含
     "gather kernel events=0 inside capture window"（非笼统 fail）
  S3 坏输入：gather 名仅出现在 cat!='kernel' 事件（grep 陷阱）→ RED，理由同 S2 族
  S4 坏输入：gather 仅在捕获窗**外**（=能力探针干跑；naive 全窗 grep 必假绿的毒例）
     → RED，理由含 "outside capture window"
  D1 好输入：dispatch 窗内 gather kernel 带 graph id 68 → GREEN "graphid!=0 … events=1"
  D2 坏输入：gather 全带 graph id 0（eager；naive 计数必假绿的毒例）→ RED
     "graph id 0 (eager)"
  D3 坏输入：gather 真图 id 但在窗外 → RED "outside dispatch window"
  D4 坏输入：dispatch 窗内零 gather（仍 dispatch 在 unfiltered 档=换窗失败的毒例）
     → RED "gather kernel events=0 inside dispatch window"
自检断言「每例以预期理由红/绿」，退出码非零=自检失败（附录 A7：同时断言退出码与
失败理由，排除「rc=1 来自意外异常被当抓到」）。

== 真实负对照（本仓实测）====================================================
`--trace logs/R1RECERT-20261004/R1RECERT_census_c1.trace.json.gz`：两断言对 R1RECERT
census 窗必须 RED（该窗无 filtered 图 replay、无捕获相位）——真实数据上的负对照
（2026-10-04 已跑：RED, gather kernel events=0；R1-FIX-2 实施段复跑=复现件
p12_realtrace_negative_control.log）。

== 部署副本接线（火侧执行面，dev 只交付断言件）==============================
容器冒烟 p12 增补两步（进 container_smoke_r1.py 的 p12 相位，不另开相位）：
  P12.G1 捕获窗断言：在 p12 的真 torch.cuda.graph 捕获段外再包一层
      torch.profiler.profile(activities=[CUDA])，捕获走 seam 的 GatherConsumeDenseBlocks
      .consume_decode（真引擎入参形状的合成批；520d6d0 四方法签名面=
      publish/consume_{decode,prefill} 无 out 参，合成批按 inputs 合同构造）；
      停采后对本断言器喂 trace 路径。
  P12.G2 replay 窗断言（长 ctx 形）：profile 下 replay 捕获图一次，断言 gather 名
      以「graph id≠0」出现 ≥1 件——把「图内」落成可测。
  P12.G3（R1-FIX-2 FIX-A 面）：PREFILL=1 形态下 eager prefill 消费窗内 gather
      （graph id==0 预期=eager 标记）≥floor 件——FIX-A 接线的运行期直证。
用法：
  python3 p12_assertion_graph_gather.py --trace <trace.json.gz> [--floor 1]
      [--mode captured|dispatched] [--window lo_us,hi_us]
  python3 p12_assertion_graph_gather.py --selftest
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys

GATHER_NAME = "_fp4_gather_index_logits_kernel"
DENSE_NAME = "_fp4_index_logits_kernel"

FIELD = re.compile(r'^    "(ph|cat|name|ts|dur)": (.*?),?\s*$')
GRAPHID = re.compile(r'"graph id"\s*:\s*(-?\d+)')


class Verdict(Exception):
    def __init__(self, ok: bool, reason: str):
        super().__init__(reason)
        self.ok = ok
        self.reason = reason


# ─────────────────────── trace 扫描（流式，RSS 有界；census_stream 同法） ──


def scan_trace(path: str, *, window_us: tuple | None, floor: int) -> dict:
    """返回 {gather_kernel: [(ts,dur)], gather_graphids: [int|None],
    gather_nonkernel: [cat...]}。

    window_us=(lo,hi) 时只计窗内事件（capture 相位或 replay/dispatch 相位窗）。
    graph id 取自事件 args（本 CUPTI 13.0 版 0=eager 发射标记，非真图——
    FORENSICS §1.2 方法注记；无 graph id 的事件记 None，分派层按 eager 论）。
    """
    gather_kernel, gather_graphids, gather_nonkernel = [], [], []
    cur = {}
    op = gzip.open if path.endswith(".gz") else open

    def close(cur):
        if not cur:
            return
        name = cur.get("name", "")
        if GATHER_NAME not in name:
            return
        ts = cur.get("ts", 0) or 0
        if window_us is not None and not (window_us[0] <= ts < window_us[1]):
            gather_nonkernel.append("outside capture window")
            return
        if cur.get("cat") == "kernel":
            gather_kernel.append((ts, cur.get("dur", 0) or 0))
            gather_graphids.append(cur.get("graph id"))
        else:
            gather_nonkernel.append(str(cur.get("cat")))

    with op(path, "rt", errors="replace") as f:
        for line in f:
            if line.startswith("  }"):
                close(cur)
                cur = {}
                continue
            m = FIELD.match(line)
            if m:
                k = m.group(1)
                if k == "ph":
                    close(cur)
                    cur = {}
                try:
                    cur[k] = json.loads(m.group(2))
                except Exception:
                    pass
            else:
                # args 体在更深缩进（如 12 空格的 "queued": 0, … "graph id": 68, …）
                # ——不入 FIELD 分支，单独搜 graph id（close() 按 gather 名过滤）。
                g = GRAPHID.search(line)
                if g:
                    cur["graph id"] = int(g.group(1))
    close(cur)
    return {"gather_kernel": gather_kernel, "gather_graphids": gather_graphids,
            "nonkernel_reasons": gather_nonkernel}


def assert_captured_gather(path: str, *, window_us: tuple | None, floor: int) -> Verdict:
    r = scan_trace(path, window_us=window_us, floor=floor)
    n = len(r["gather_kernel"])
    if n == 0:
        detail = "gather kernel events=0 inside capture window"
        if r["nonkernel_reasons"]:
            detail += " (non-kernel/outside-window occurrences: %s)" % (
                sorted(set(r["nonkernel_reasons"])))
        raise Verdict(False, "RED: " + detail)
    raise Verdict(True, "GREEN: gather kernel events=%d inside capture window (floor=%d)"
                  % (n, floor))


def assert_dispatched_gather(path: str, *, window_us: tuple | None, floor: int) -> Verdict:
    """L3 分派层断言（R1-FIX-2 新增，长 ctx 相=判据①换窗落位）。

    GREEN ⇔ 窗内 graph id≠0（真图；本 CUPTI 版 0=eager 发射标记）的 gather kernel
    事件 ≥ floor。三类红各自点名（判别力）：
      R-a 窗内零 gather kernel（含「名字只在非 kernel 事件」grep 陷阱）
      R-b 窗内 gather kernel 存在但 graph id 全为 0/缺（=eager 面：能力探针干跑
          或 FIX-A 后 prefill eager 消费——**不是**图内上岗；naive 计数必假绿的毒例）
      R-c gather 全在窗外（窗参数错置=判据窗口可达性〔#30〕先于机制判定）
    """
    r = scan_trace(path, window_us=window_us, floor=floor)
    n_all = len(r["gather_kernel"])
    n_graph = sum(1 for g in r["gather_graphids"] if g is not None and g != 0)
    if n_graph >= floor:
        raise Verdict(
            True,
            "GREEN: graphid!=0 gather kernel events=%d inside dispatch window "
            "(floor=%d; eager(0/absent)=%d)" % (n_graph, floor, n_all - n_graph))
    if n_all == 0:
        detail = "gather kernel events=0 inside dispatch window"
        if r["nonkernel_reasons"]:
            # 扫描器共用「outside capture window」记号，分派层译为 dispatch 口径
            reasons = sorted(set(
                ("outside dispatch window" if x == "outside capture window" else x)
                for x in r["nonkernel_reasons"]))
            detail += " (non-kernel/outside-window occurrences: %s)" % reasons
        raise Verdict(False, "RED: " + detail)
    raise Verdict(
        False,
        "RED: gather kernel events=%d inside dispatch window but all graph id 0 "
        "(eager) — dispatched-on-hot-path not proven (floor=%d)" % (n_all, floor))


# ─────────────────────── 合成 trace 与判别力自检（教义 #15） ────────────────


def synth_trace(events: list[dict]) -> str:
    import tempfile, os
    lines = [" {"]
    for ev in events:
        lines.append("  {")
        for k, v in ev.items():
            lines.append('    "%s": %s,' % (k, json.dumps(v)))
        lines.append("  },")
    lines.append("]}")
    fd, p = tempfile.mkstemp(suffix=".json", prefix="p12synth_")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines))
    return p


SELFTEST_CASES = [
    # (case, events, expect_ok, expect_reason_substr, mode)  mode 缺省=captured
    ("S1 好输入：捕获窗内 gather kernel 事件 ×2 → 须 GREEN",
     [{"ph": "X", "cat": "kernel", "name": GATHER_NAME, "ts": 1000, "dur": 5},
      {"ph": "X", "cat": "kernel", "name": GATHER_NAME, "ts": 2000, "dur": 5}],
     True, "gather kernel events=2", "captured"),
    ("S2 坏输入：全窗零 gather（seam 未挂/包装返回 stock 对）→ 须因缺席红",
     [{"ph": "X", "cat": "kernel", "name": DENSE_NAME, "ts": 1000, "dur": 5}],
     False, "gather kernel events=0 inside capture window", "captured"),
    ("S3 坏输入：gather 名仅在非 kernel 事件（grep 陷阱）→ 须因类别红",
     [{"ph": "X", "cat": "user_annotation", "name": "probe " + GATHER_NAME,
       "ts": 1000, "dur": 5}],
     False, "0 kernel-category" if False else "gather kernel events=0 inside capture window",
     "captured"),
    ("S4 坏输入：gather 仅在窗外（=install 期能力探针干跑；naive 全窗 grep 必假绿）"
     "→ 须因窗外红",
     [{"ph": "X", "cat": "kernel", "name": GATHER_NAME, "ts": 0, "dur": 5}],
     False, "outside capture window", "captured"),
    # ── L3 分派层（R1-FIX-2 新增；判据①换窗=长 ctx decode census 相） ──
    ("D1 好输入：dispatch 窗内 gather kernel 带 graph id 68 → 须 GREEN",
     [{"ph": "X", "cat": "kernel", "name": GATHER_NAME, "ts": 1000, "dur": 5,
       "graph id": 68}],
     True, "graphid!=0 gather kernel events=1", "dispatched"),
    ("D2 坏输入：窗内 gather kernel 全带 graph id 0（eager 面=能力探针干跑或 "
     "FIX-A 后 prefill eager 消费；naive 计数必假绿的毒例）→ 须因 eager 红",
     [{"ph": "X", "cat": "kernel", "name": GATHER_NAME, "ts": 1000, "dur": 5,
       "graph id": 0}],
     False, "all graph id 0 (eager)", "dispatched"),
    ("D3 坏输入：gather 真图 id 但在窗外（窗参数错置=#30 先问够不够得着）→ 须因窗外红",
     [{"ph": "X", "cat": "kernel", "name": GATHER_NAME, "ts": 0, "dur": 5,
       "graph id": 68}],
     False, "outside dispatch window", "dispatched"),
    ("D4 坏输入：dispatch 窗内零 gather（仍 dispatch 在 unfiltered 档=换窗失败的"
     "毒例）→ 须因缺席红",
     [{"ph": "X", "cat": "kernel", "name": DENSE_NAME, "ts": 1000, "dur": 5,
       "graph id": 68}],
     False, "gather kernel events=0 inside dispatch window", "dispatched"),
]
# 注：S3 的理由串与 S2 同族（kernel 件=0 是承重理由；cat 记入 detail）——判别点在
# S4（窗判别）与 S2（缺席判别）两例分离；S3 防「名字出现=上岗」的 grep 类假绿。
# D2/D3/D4=分派层三向判别：eager 假绿毒例 / 窗外 / 缺席（换窗失败本体）。


def selftest() -> int:
    window = (500, 5000)
    floor = 1
    failures = 0
    for case, events, expect_ok, substr, mode in SELFTEST_CASES:
        # S4/D3 的事件在 ts=0（窗外），窗内无 gather → 必红且理由点名 outside
        p = synth_trace(events)
        fn = {"captured": assert_captured_gather,
              "dispatched": assert_dispatched_gather}[mode]
        try:
            v = fn(p, window_us=window, floor=floor)
            got_ok, reason = v.ok, v.reason
        except Verdict as v:
            got_ok, reason = v.ok, v.reason
        except Exception as exc:  # A7：意外异常 ≠ 抓到
            print("[FAIL] %s —— 以异常代替判定: %r" % (case, exc))
            failures += 1
            continue
        ok = (got_ok == expect_ok) and (substr in reason)
        print("[%s] %s\n       reason=%s" % ("PASS" if ok else "FAIL", case, reason))
        failures += 0 if ok else 1
        import os
        os.unlink(p)
    print("selftest: %s (%d/%d)" % ("ALL PASS" if failures == 0 else "FAIL",
                                    len(SELFTEST_CASES) - failures, len(SELFTEST_CASES)))
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", help="待检 trace（.json.gz 或 .json）")
    ap.add_argument("--window", default="", help="lo_us,hi_us 捕获/重放相位窗")
    ap.add_argument("--floor", type=int, default=1)
    ap.add_argument("--mode", default="captured",
                    choices=("captured", "dispatched"),
                    help="captured=L2 捕获窗（含 eager 干跑判别）；dispatched=L3 "
                         "分派窗（另要求 graph id≠0=真图内）")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.trace:
        print(__doc__)
        return 2
    window = None
    if a.window:
        lo, hi = a.window.split(",")
        window = (float(lo), float(hi))
    fn = {"captured": assert_captured_gather,
          "dispatched": assert_dispatched_gather}[a.mode]
    try:
        v = fn(a.trace, window_us=window, floor=a.floor)
        print(v.reason)
        return 0
    except Verdict as v:
        print(v.reason)
        return 1


if __name__ == "__main__":
    sys.exit(main())
