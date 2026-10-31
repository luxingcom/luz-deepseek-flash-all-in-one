"""indexer_budget 单元测（W2 F-1 案 A 旋钮；案头零集群零 GPU——stub scoring 模块）。

判别力自检律（硬要求=反向用例）：坏输入必须因正确理由变红——
  T1 未设            → 两常量位等 stock（2<<30 / 1<<30）一字不动；
  T2 64MiB           → deep_gemm=67108864、torch=33554432（b//2 比例律）；
  T3 "64MiB" 非整数  → REFUSED+常量不动（fail-closed，不套垃圾值）；
  T4 "0"/"off"       → no-op（显式关）；
  T5 "1"（A5 负对照）→ REFUSED（<1MiB 地板）——拒绝而非静默全量/病态 tile 风暴；
  T6 "-5"/"0x40"     → REFUSED（非纯十进制）；
  T7 sparse_wire 共存 → 先装真 sparse_wire（缺省 128MiB 定板）再设 64MiB 旋钮
                        ⇒ 旋钮压过 128MiB（装载次序=确定性）；
  T8 未设+已 128MiB  → 旋钮 no-op 不回改（sparse_wire 语义原样——产线形保护）；
  T9 锚缺失          → 跳过+出声（fail-closed 不崩）；
  T10 幂等           → 二次 install 不重复改写。
跑法：python3 tests/test_score_budget_knob.py（在 adapter/ 目录下；零依赖）。
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import indexer_budget as ib

KEY = ib.KEY


def stub_module(dg=ib.STOCK_DEEP_GEMM, tw=ib.STOCK_TORCH):
    m = types.ModuleType("sglang.srt.layers.attention.dsv4.v41_indexer.scoring")
    m._DEEP_GEMM_SCORE_BUDGET_BYTES = dg
    m._TORCH_SCORE_BUDGET_BYTES = tw
    return m


def reset():
    ib._INSTALLED.clear()
    ib.STATE.update(action="noop", value=None, why="unset", installed=False,
                    before=(None, None), after=(None, None))


fails = []


def check(tag, cond, detail=""):
    print("%s %s %s" % ("PASS" if cond else "FAIL", tag, detail))
    if not cond:
        fails.append(tag)


with_setenv = lambda k, v: (lambda: (os.environ.__setitem__(k, v) if v is not None
                                     else os.environ.pop(k, None)))

# T1 未设 → 位等 stock
reset(); os.environ.pop(KEY, None)
m = stub_module(); ok = ib.install(m)
check("T1-unset-bit-equal", (not ok) and m._DEEP_GEMM_SCORE_BUDGET_BYTES == 2 << 30
      and m._TORCH_SCORE_BUDGET_BYTES == 1 << 30 and ib.STATE["action"] == "noop",
      "dg=%d tw=%d" % (m._DEEP_GEMM_SCORE_BUDGET_BYTES, m._TORCH_SCORE_BUDGET_BYTES))

# T2 64MiB → 生效（两路径 + b//2）
reset(); os.environ[KEY] = "67108864"
m = stub_module(); ok = ib.install(m)
check("T2-arm-64mib", ok and m._DEEP_GEMM_SCORE_BUDGET_BYTES == 67108864
      and m._TORCH_SCORE_BUDGET_BYTES == 33554432,
      "dg=%d tw=%d" % (m._DEEP_GEMM_SCORE_BUDGET_BYTES, m._TORCH_SCORE_BUDGET_BYTES))

# T3 非整数 → fail-closed
reset(); os.environ[KEY] = "64MiB"
m = stub_module(); ok = ib.install(m)
check("T3-refuse-nonint", (not ok) and m._DEEP_GEMM_SCORE_BUDGET_BYTES == 2 << 30
      and m._TORCH_SCORE_BUDGET_BYTES == 1 << 30
      and ib.STATE["action"] == "refuse" and "non-integer" in ib.STATE["why"],
      "why=%s" % ib.STATE["why"])

# T4 显式 off → no-op
for tok in ("0", "off", " ", ""):
    reset(); os.environ[KEY] = tok
    m = stub_module(); ok = ib.install(m)
    check("T4-off-%r" % tok, (not ok) and m._DEEP_GEMM_SCORE_BUDGET_BYTES == 2 << 30,
          "action=%s" % ib.STATE["action"])
os.environ.pop(KEY, None)

# T5 A5 负对照：1 字节 → REFUSED（<8MiB 地板：引擎行对齐地板下预算无法严格
# 兑现——w2_f1_gear a1 负网格实证），不是静默全量
reset(); os.environ[KEY] = "1"
m = stub_module(); ok = ib.install(m)
check("T5-refuse-1b-floor", (not ok) and ib.STATE["action"] == "refuse"
      and m._DEEP_GEMM_SCORE_BUDGET_BYTES == 2 << 30,
      "why=%s" % ib.STATE["why"])

# T6 非纯十进制 → REFUSED
for tok in ("-5", "0x4000000", "1e6", "1_0", "67108864.0"):
    reset(); os.environ[KEY] = tok
    m = stub_module(); ok = ib.install(m)
    check("T6-refuse-%r" % tok, (not ok) and ib.STATE["action"] == "refuse",
          "why=%s" % ib.STATE["why"])
os.environ.pop(KEY, None)

# 天花：>16GiB 拒
reset(); os.environ[KEY] = str(17 << 30)
m = stub_module(); ok = ib.install(m)
check("T6b-refuse-ceiling", (not ok) and ib.STATE["action"] == "refuse")
os.environ.pop(KEY, None)

# T7 sparse_wire 共存 precedence（真 sparse_wire 模块，缺省 128MiB 定板）
import sparse_wire
reset()
os.environ.pop(sparse_wire.SCORE_BUDGET_ENV, None)   # 其键未设 → 缺省 128MiB
os.environ.pop(KEY, None)
m = stub_module()
sw_ok = sparse_wire.install_scoring(m)
after_sw = (m._DEEP_GEMM_SCORE_BUDGET_BYTES, m._TORCH_SCORE_BUDGET_BYTES)
ib.install(m)                                        # 未设 → 不回改
check("T8-noop-preserves-sparsewire", sw_ok and after_sw == (134217728, 134217728)
      and (m._DEEP_GEMM_SCORE_BUDGET_BYTES, m._TORCH_SCORE_BUDGET_BYTES) == after_sw,
      "after sparse_wire=%s after knob-noop=%s" % (after_sw,
      (m._DEEP_GEMM_SCORE_BUDGET_BYTES, m._TORCH_SCORE_BUDGET_BYTES)))

reset()  # 新 stub（独立 __name__，避 sparse_wire 幂等键吞装）连放两装：sparse_wire 128MiB → 旋钮 64MiB
os.environ[KEY] = "67108864"
m2 = stub_module()
m2.__name__ = "sglang.srt.layers.attention.dsv4.v41_indexer.scoring#t7"
sw2_ok = sparse_wire.install_scoring(m2)
mid = (m2._DEEP_GEMM_SCORE_BUDGET_BYTES, m2._TORCH_SCORE_BUDGET_BYTES)
ib.install(m2)
check("T7-knob-overrides-sparsewire", sw2_ok and mid == (134217728, 134217728)
      and m2._DEEP_GEMM_SCORE_BUDGET_BYTES == 67108864
      and m2._TORCH_SCORE_BUDGET_BYTES == 33554432,
      "sparse_wire 落 %s → 旋钮压成 (%d, %d)"
      % (mid, m2._DEEP_GEMM_SCORE_BUDGET_BYTES, m2._TORCH_SCORE_BUDGET_BYTES))
os.environ.pop(KEY, None)

# T9 锚缺失 → 跳过+出声不崩
reset(); os.environ[KEY] = "67108864"
m = types.ModuleType("sglang.srt.layers.attention.dsv4.v41_indexer.scoring")  # 无常量
ok = ib.install(m)
check("T9-anchors-missing", (not ok) and ib.STATE["action"] == "anchors-missing")
os.environ.pop(KEY, None)

# T10 幂等：二次 install 不再改写（装后改 env 也不生效——import 期语义）
reset(); os.environ[KEY] = "67108864"
m = stub_module(); ib.install(m)
os.environ[KEY] = "2097152"
ok2 = ib.install(m)
check("T10-idempotent", (not ok2) and m._DEEP_GEMM_SCORE_BUDGET_BYTES == 67108864)
os.environ.pop(KEY, None)

# summary 三态可判（off / armed / will-refuse）
reset(); os.environ.pop(KEY, None)
s0 = ib.summary()
os.environ[KEY] = "67108864"; s1 = ib.summary()
os.environ[KEY] = "bogus"; s2 = ib.summary()
os.environ.pop(KEY, None)
check("T11-summary-tri-state", "no-op" in s0 and "ARMED" in s1 and "REFUSE" in s2)

print("=" * 60)
if fails:
    print("SELFCHECK RED：%d 项失败：%s" % (len(fails), fails))
    sys.exit(1)
print("SELFCHECK GREEN：13 检全过（T1-T11，含 5 反向用例 T3/T5/T6×5/T6b）")
