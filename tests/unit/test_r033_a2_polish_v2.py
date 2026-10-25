"""r033-A2 打磨批 v2 补丁单测（D41+D46 A2 polish batch, 2026-10-25；CPU-only，零 GPU/零容器）.

被测件：tools/patches/r033-a2.overlay-backend-fi072-wiring-v2.patch
  （v1 件 r033-a2.overlay-backend-fi072-wiring.patch 不动，本套件同时守其 md5 锚）
法源：
  DECISIONS-RESOLVED-20261024.md D46（read_face 拒收→调用点补 caller-supplied scratch）
  与 D41（热路径 import 上提+复用）；CODE-QUALITY-REVIEW-20261025.md §⑤-3（批准改法）。
  内核语义源（flashinfer 0.7.2 只读解包 logs/S-FIS0-STAGING-20261018/fi072-unpacked）：
  attention_plan.h:98（scratch_heads=8 iff H==8 else ceil16）、attention_resolve.cu:144-151
  （allocated split stride=chunk_capacity=ceil(topk/64)+ceil(extra_topk/64)，DSV4 族 tile=64）、
  attention_validation.h:175（scratch 成对律）、_policy.py:64-66（decode 形仅 num_tokens<=64）、
  attention_resolve.cu:119（extra_fp4 无 dual 拒收）。
  宿主树对照：~/sglang-main-src .../flash_mla_sm120.py:643-653（caller scratch 同式推导）。

被测代码的执行方式（案头批制式）：不 import 整个 backend 模块（重依赖面），
从"基底+v2 补丁应用后"的源文本中以 AST 抽取目标函数/语句段，在假体命名空间中
exec——被测的是补丁产物的真实源文本，非复述实现。
"""
import ast
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATCHES = os.path.join(REPO, "tools", "patches")
V2_PATCH = os.path.join(PATCHES, "r033-a2.overlay-backend-fi072-wiring-v2.patch")
V1_PATCH = os.path.join(PATCHES, "r033-a2.overlay-backend-fi072-wiring.patch")
A2_REL = "deploy/reconstruct/0.3.2/overlay/deepseek_v4_backend.py"
BASE_MD5 = "a1e7c3b5f769d89d824c2bc0c9145e0c"
V1_PATCH_MD5 = "a7bc65dadae6cb3fd57f44fe654ebd21"
PATCHED_MD5 = "15df916868e80129a5102b1bbb18575e"

_APPLIED = {}


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _applied_src():
    """基底+v2 应用后源文本（会话内缓存；基底 md5 前置校验）。"""
    if "src" in _APPLIED:
        return _APPLIED["src"]
    tmp = tempfile.mkdtemp(prefix="a2v2-unit-")
    rel = os.path.join(tmp, A2_REL)
    os.makedirs(os.path.dirname(rel), exist_ok=True)
    shutil.copyfile(os.path.join(REPO, A2_REL), rel)
    assert _md5(rel) == BASE_MD5, "overlay 基底 md5 漂移"
    subprocess.run(["git", "init", "-q", "."], cwd=tmp, check=True,
                   capture_output=True)
    r = subprocess.run(["git", "apply", V2_PATCH], cwd=tmp,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    src = open(rel, encoding="utf-8").read()
    assert hashlib.md5(src.encode()).hexdigest() == PATCHED_MD5
    _APPLIED["src"] = src
    _APPLIED["tmp"] = tmp
    return src


def _extract_fn_src(name):
    tree = ast.parse(_applied_src())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            seg = ast.get_source_segment(_applied_src(), node)
            assert seg
            return seg
    raise AssertionError(f"function {name} not found in patched source")


def _extract_scratch_gate_src():
    """读面 D46 scratch 块原文（if q2.shape[0] <= _SM120_DECODE_MAX_TOKENS: … else …）。"""
    tree = ast.parse(_applied_src())
    for node in ast.walk(tree):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and ast.unparse(node.test) == "q2.shape[0] <= _SM120_DECODE_MAX_TOKENS"):
            seg = ast.get_source_segment(_applied_src(), node)
            assert seg
            return _dedent_first_line_stripped(seg)
    raise AssertionError("scratch gate block not found")


def _dedent_first_line_stripped(seg):
    """get_source_segment 首行自 col_offset 起（无缩进）、余行保留原缩进——按余行
    最小公共缩进归零（保持语句原文，仅去公共前缀）。"""
    lines = seg.splitlines()
    body = [l for l in lines[1:] if l.strip()]
    prefix = min((len(l) - len(l.lstrip(" ")) for l in body), default=0)
    out = [lines[0]]
    for l in lines[1:]:
        out.append(l[prefix:] if l.strip() else l)
    return "\n".join(out) + ("\n" if seg.endswith("\n") else "")


def _install_fake_flashinfer(*, fail=False):
    """sys.modules 假体 0.7.2 面（调用方以 mock.patch.dict(sys.modules) 包裹以复原）；
    fail=True 时 import 即炸（fail-closed 面测）。"""
    fake = types.ModuleType("flashinfer")
    mla = types.ModuleType("flashinfer.mla")
    sm = types.ModuleType("flashinfer.mla._sparse_mla_sm120")
    if fail:
        def _boom(*a, **k):
            raise ImportError("simulated: no 0.7.2 face")
        sm.__getattr__ = _boom
    else:
        sm._DECODE_DSV4_1_DISPATCH = object()
        sm._sparse_mla_sm120_paged_attention = object()
        sm.dsv41_fp8_quantize_append_sparse_mla_cache = object()
    fake.mla = mla
    mla._sparse_mla_sm120 = sm
    sys.modules["flashinfer"] = fake
    sys.modules["flashinfer.mla"] = mla
    sys.modules["flashinfer.mla._sparse_mla_sm120"] = sm
    return sm


def _exec_probe(ns):
    """exec 探针函数（含模块级三全局的种子）。"""
    exec(compile(_extract_fn_src("_dsv41_fi072_native_available"),
                 "<a2v2-probe>", "exec"), ns)
    return ns


def _exec_shapes_fn(ns=None):
    ns = ns if ns is not None else {}
    exec(compile(_extract_fn_src("_dsv41_fi072_decode_scratch_shapes"),
                 "<a2v2-shapes>", "exec"), ns)
    return ns


class _Shape:
    def __init__(self, *dims):
        self.shape = tuple(dims)
        self.device = "fakecuda:0"


class _FakeTorch:
    """torch.empty 记录假体（dtype 以标识对象出现）。"""
    bfloat16 = "bf16"
    float32 = "fp32"
    uint8 = "u8"

    def __init__(self):
        self.allocs = []

    def empty(self, shape, dtype=None, device=None):
        t = _RecTensor(tuple(shape), dtype, device)
        self.allocs.append(t)
        return t


class _RecTensor:
    def __init__(self, shape, dtype, device):
        self.shape, self.dtype, self.device = shape, dtype, device


class TestPatchMechanics(unittest.TestCase):
    """补丁机械面：基底锚/双面 apply/py_compile/逆向回退/v1 件不动。"""

    def test_base_and_v1_untouched(self):
        self.assertEqual(_md5(os.path.join(REPO, A2_REL)), BASE_MD5)
        self.assertEqual(_md5(V1_PATCH), V1_PATCH_MD5)

    def test_apply_check_compile_reverse(self):
        tmp = tempfile.mkdtemp(prefix="a2v2-mech-")
        try:
            rel = os.path.join(tmp, A2_REL)
            os.makedirs(os.path.dirname(rel), exist_ok=True)
            shutil.copyfile(os.path.join(REPO, A2_REL), rel)
            subprocess.run(["git", "init", "-q", "."], cwd=tmp, check=True,
                           capture_output=True)
            r = subprocess.run(["git", "apply", "--check", V2_PATCH], cwd=tmp,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            subprocess.run(["git", "apply", V2_PATCH], cwd=tmp, check=True)
            self.assertEqual(_md5(rel), PATCHED_MD5)
            r = subprocess.run([sys.executable, "-m", "py_compile", rel],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            subprocess.run(["git", "apply", "-R", V2_PATCH], cwd=tmp, check=True)
            self.assertEqual(_md5(rel), BASE_MD5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_p5_face_same_patched_bytes(self):
        """活体 harness 制式：从 attention 目录取 -p5 应用，产物逐字节同全路径面。"""
        tmp = tempfile.mkdtemp(prefix="a2v2-p5-")
        try:
            att = os.path.join(tmp, "attention")
            os.makedirs(att, exist_ok=True)
            shutil.copyfile(os.path.join(REPO, A2_REL),
                            os.path.join(att, "deepseek_v4_backend.py"))
            subprocess.run(["git", "init", "-q", "."], cwd=att, check=True,
                           capture_output=True)
            r = subprocess.run(["git", "apply", "-p5", "--check", V2_PATCH],
                               cwd=att, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            subprocess.run(["git", "apply", "-p5", V2_PATCH], cwd=att, check=True)
            self.assertEqual(_md5(os.path.join(att, "deepseek_v4_backend.py")),
                             PATCHED_MD5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestScratchShapes(unittest.TestCase):
    """D46 形状推导全分支（内核语义源对照；禁测试形状硬编码=对任意输入成立）。"""

    @classmethod
    def setUpClass(cls):
        cls.fn = staticmethod(_exec_shapes_fn()["_dsv41_fi072_decode_scratch_shapes"])

    def test_scratch_heads_rule_attention_plan_h98(self):
        """H==8 特例=8；否则 ceil16（attention_plan.h:98 decode_scratch_heads）。"""
        for h, want in [(8, 8), (1, 16), (9, 16), (15, 16), (16, 16), (17, 32),
                        (24, 32), (32, 32), (33, 48), (48, 48), (64, 64),
                        (65, 80), (128, 128)]:
            out, _ = self.fn(1, h, 64, 0, 512)
            self.assertEqual(out[1], want, f"H={h}")

    def test_num_splits_rule_attention_resolve_cu_144_151(self):
        """split stride=ceil(topk/64)+ceil(extra_topk/64)（DSV4 族 tile=64；含非整除边界）。"""
        for topk in (1, 63, 64, 65, 127, 128, 511, 512, 513, 1024, 2048):
            for extra in (0, 1, 63, 64, 65, 128, 512, 1024):
                out, _ = self.fn(7, 32, topk, extra, 512)
                want = -(-topk // 64) + -(-extra // 64)
                self.assertEqual(out[2], want, f"topk={topk} extra={extra}")

    def test_extra_absent_equals_zero_width(self):
        """extra 缺席（ratio-0 层）语义=extra_topk 0：仅主链 splits。"""
        out, _ = self.fn(64, 32, 512, 0, 512)
        self.assertEqual(out, (64, 32, 8, 512))

    def test_live_error_instance_derivation(self):
        """a2-live-v2.json 报错实例 [64,32,16,512]/[64,32,16] 是本规则的一例（非硬编码源）。"""
        out, lse = self.fn(64, 32, 512, 512, 512)
        self.assertEqual(out, (64, 32, 16, 512))
        self.assertEqual(lse, (64, 32, 16))

    def test_shapes_pair_relation_and_dv_passthrough(self):
        for dv in (512, 1024):
            out, lse = self.fn(3, 17, 65, 63, dv)
            self.assertEqual(lse, out[:3])
            self.assertEqual(out[3], dv)
            self.assertEqual(out[1], 32)  # ceil16(17)
            self.assertEqual(out[2], 2 + 1)

    def test_heads_padded_runtime_invariance(self):
        """头数取运行时 q2 实宽（decode 64 头 pad 形）：64→64，与内核 m.heads 同源。"""
        out, _ = self.fn(64, 64, 512, 512, 512)
        self.assertEqual(out[1], 64)

    def test_reference_impl_agrees_with_host_sglang_face(self):
        """宿主树 flash_mla_sm120.py:643-653 caller-scratch 同式（extra>0 加项/缺省 0）。"""
        for topk in (64, 512, 513):
            for extra in (0, 64, 512):
                host = (topk + 63) // 64 + (((extra + 63) // 64) if extra > 0 else 0)
                out, _ = self.fn(2, 32, topk, extra, 512)
                self.assertEqual(out[2], host)


class TestProbeHoisting(unittest.TestCase):
    """D41 import 上提语义等价：绑定=调用点 import 的同一对象；fail-closed；缓存。"""

    def test_failclosed_bindings_stay_none(self):
        with mock.patch.dict(sys.modules):
            self._drop_fi()
            ns = {"_DSV41_FI072_NATIVE": None, "_FI072_PA": None,
                  "_FI072_WRITER": None}
            _exec_probe(ns)
            self.assertIs(ns["_dsv41_fi072_native_available"](), False)
            self.assertIsNone(ns["_FI072_PA"])
            self.assertIsNone(ns["_FI072_WRITER"])

    def test_success_binds_the_072_symbols_identity(self):
        """绑定名与 flashinfer 符号同一性（=v1 调用点 import 语义的上提等价）。"""
        with mock.patch.dict(sys.modules):
            sm = _install_fake_flashinfer()
            ns = {"_DSV41_FI072_NATIVE": None, "_FI072_PA": None,
                  "_FI072_WRITER": None}
            _exec_probe(ns)
            self.assertIs(ns["_dsv41_fi072_native_available"](), True)
            self.assertIs(ns["_FI072_PA"],
                          sm._sparse_mla_sm120_paged_attention)
            self.assertIs(ns["_FI072_WRITER"],
                          sm.dsv41_fp8_quantize_append_sparse_mla_cache)

    def test_cached_second_call_no_reimport(self):
        with mock.patch.dict(sys.modules):
            sm = _install_fake_flashinfer()
            ns = {"_DSV41_FI072_NATIVE": None, "_FI072_PA": None,
                  "_FI072_WRITER": None}
            _exec_probe(ns)
            self.assertIs(ns["_dsv41_fi072_native_available"](), True)
            before = (ns["_FI072_PA"], ns["_FI072_WRITER"])
            # 换面后二跑：缓存命中，不重 import、绑定稳定
            sm._sparse_mla_sm120_paged_attention = object()
            sm.dsv41_fp8_quantize_append_sparse_mla_cache = object()
            self.assertIs(ns["_dsv41_fi072_native_available"](), True)
            self.assertEqual((ns["_FI072_PA"], ns["_FI072_WRITER"]), before)

    def test_reset_after_face_change_recovers_failclosed(self):
        with mock.patch.dict(sys.modules):
            _install_fake_flashinfer(fail=True)
            ns = {"_DSV41_FI072_NATIVE": None, "_FI072_PA": None,
                  "_FI072_WRITER": None}
            _exec_probe(ns)
            self.assertIs(ns["_dsv41_fi072_native_available"](), False)
            self.assertIsNone(ns["_FI072_PA"])

    @staticmethod
    def _drop_fi():
        for k in ("flashinfer", "flashinfer.mla",
                  "flashinfer.mla._sparse_mla_sm120"):
            sys.modules.pop(k, None)


class TestScratchPinReuse(unittest.TestCase):
    """D46+D41 scratch pin 复用：exec 读面 scratch 块原文（补丁产物真实源文本）。"""

    def _run_gate(self, self_obj, q2, swa_idx, extra_idx, shapes_fn, ft):
        ns = {
            "_SM120_DECODE_MAX_TOKENS": 64,
            "_dsv41_fi072_decode_scratch_shapes": shapes_fn,
            "torch": ft,
            "self": self_obj,
            "q2": q2, "swa_idx": swa_idx, "extra_idx": extra_idx,
        }
        exec(compile(_extract_scratch_gate_src(), "<a2v2-scratch-gate>", "exec"), ns)
        return ns.get("mid_out"), ns.get("mid_lse")

    def test_decode_allocates_derived_pair_and_reuses(self):
        shapes_fn = _exec_shapes_fn()["_dsv41_fi072_decode_scratch_shapes"]
        ft = _FakeTorch()
        holder = types.SimpleNamespace(head_dim_v=512)
        q2, swa, extra = _Shape(64, 32, 512), _Shape(64, 512), _Shape(64, 512)
        m1, l1 = self._run_gate(holder, q2, swa, extra, shapes_fn, ft)
        self.assertEqual(m1.shape, (64, 32, 16, 512))
        self.assertEqual(l1.shape, (64, 32, 16))
        self.assertEqual(m1.dtype, "bf16")
        self.assertEqual(l1.dtype, "fp32")
        self.assertEqual(len(ft.allocs), 2)
        # 同形状二跑：pin 命中，零新分配，返回同对象（graph capture 地址稳定面）
        m2, l2 = self._run_gate(holder, q2, swa, extra, shapes_fn, ft)
        self.assertEqual(len(ft.allocs), 2)
        self.assertIs(m1, m2)
        self.assertIs(l1, l2)

    def test_new_shape_pins_new_entry_old_kept(self):
        shapes_fn = _exec_shapes_fn()["_dsv41_fi072_decode_scratch_shapes"]
        ft = _FakeTorch()
        holder = types.SimpleNamespace(head_dim_v=512)
        self._run_gate(holder, _Shape(64, 32, 512), _Shape(64, 512),
                       _Shape(64, 512), shapes_fn, ft)
        m, l = self._run_gate(holder, _Shape(32, 32, 512), _Shape(32, 512),
                              _Shape(32, 512), shapes_fn, ft)
        self.assertEqual(m.shape, (32, 32, 16, 512))
        self.assertEqual(len(ft.allocs), 4)  # 仅新形状两分配
        self.assertEqual(len(holder._dsv41_fi072_mid_scratch), 2)  # 旧形状仍 pin

    def test_extra_none_ratio0_layer(self):
        """ratio-0 层（无 extra cache）：splits 仅主链；pair 正常供应。"""
        shapes_fn = _exec_shapes_fn()["_dsv41_fi072_decode_scratch_shapes"]
        ft = _FakeTorch()
        holder = types.SimpleNamespace(head_dim_v=512)
        m, l = self._run_gate(holder, _Shape(64, 32, 512), _Shape(64, 512),
                              None, shapes_fn, ft)
        self.assertEqual(m.shape, (64, 32, 8, 512))
        self.assertEqual(l.shape, (64, 32, 8))

    def test_prefill_form_passes_none_pair(self):
        """>64 行=预填形：成对 None（内核忽略 scratch 元数据；成对律 attention_validation.h:175）。"""
        shapes_fn = _exec_shapes_fn()["_dsv41_fi072_decode_scratch_shapes"]
        ft = _FakeTorch()
        holder = types.SimpleNamespace(head_dim_v=512)
        m, l = self._run_gate(holder, _Shape(128, 32, 512), _Shape(128, 512),
                              None, shapes_fn, ft)
        self.assertIsNone(m)
        self.assertIsNone(l)
        self.assertEqual(len(ft.allocs), 0)


class TestCallFaceAst(unittest.TestCase):
    """v2 调用面 AST 断言（与战役 AST 门同判据；套件自含可独立重跑）。"""

    def setUp(self):
        self.tree = ast.parse(_applied_src())
        self.src = _applied_src()

    def test_single_pa_call_via_bound_name_with_nine_kwargs(self):
        pa = [n for n in ast.walk(self.tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "_FI072_PA"]
        self.assertEqual(len(pa), 1)
        kws = {k.arg: k.value for k in pa[0].keywords if k.arg}
        for kw in ("kv_scale_format", "topk_length", "attn_sink",
                   "extra_kv_cache", "extra_indices", "extra_topk_length",
                   "extra_fp4", "mid_out", "mid_lse"):
            self.assertIn(kw, kws)
        self.assertEqual(ast.literal_eval(kws["kv_scale_format"]), "ue8m0_g32")
        self.assertIsInstance(kws["mid_out"], ast.Name)
        self.assertIsInstance(kws["mid_lse"], ast.Name)
        self.assertIsInstance(kws["extra_fp4"], ast.Compare)  # extra_u8 is not None
        self.assertEqual(pa[0].args[0].id, "q2")

    def test_no_auto_literal_and_no_direct_pa_calls(self):
        self.assertNotIn('kv_scale_format="auto"', self.src)
        direct = [n for n in ast.walk(self.tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "_sparse_mla_sm120_paged_attention"]
        self.assertEqual(direct, [])

    def test_no_imports_in_hot_functions(self):
        """D41：store_cache/_forward_attention 体内无 flashinfer/SM120 相关 import。"""
        for fname in ("store_cache", "_forward_attention"):
            fn = next(n for n in ast.walk(self.tree)
                      if isinstance(n, ast.FunctionDef) and n.name == fname)
            seg = ast.get_source_segment(self.src, fn) or ""
            self.assertNotIn("from flashinfer", seg, fname)
            self.assertNotIn("import flashinfer", seg, fname)

    def test_sm120_alias_avoids_unboundlocal_shadow(self):
        """别名 _SM120_DECODE_MAX_TOKENS 与 stock 函数内 SM120_DECODE_MAX_TOKENS 并存。"""
        mod_imports = [n for n in self.tree.body if isinstance(n, ast.ImportFrom)
                       and any(a.asname == "_SM120_DECODE_MAX_TOKENS"
                               for a in n.names)]
        self.assertEqual(len(mod_imports), 1)
        fn = next(n for n in ast.walk(self.tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_forward_attention")
        local_binds = set()
        for n in ast.walk(fn):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                if isinstance(n, ast.ImportFrom):
                    local_binds.update(a.asname or a.name for a in n.names)
                else:
                    local_binds.update((a.asname or a.name).split(".")[0]
                                       for a in n.names)
        self.assertNotIn("_SM120_DECODE_MAX_TOKENS", local_binds)
        self.assertNotIn("_FI072_PA", local_binds)
        self.assertNotIn("_FI072_WRITER", local_binds)
        self.assertIn("SM120_DECODE_MAX_TOKENS", local_binds)  # stock 原位不动

    def test_v1_literals_superseded(self):
        """v1 形态字面已被替换（mid None 字面/裸 True/原名直呼不再在调用面）。"""
        self.assertNotIn("mid_out=None,", self.src)
        self.assertNotIn("extra_fp4=True,", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
