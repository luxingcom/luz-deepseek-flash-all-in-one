# -*- coding: utf-8 -*-
"""r033 A-batch 三补丁（A1/A7/A2）单测（S0 案头批 2026-10-25）.

0 靴纯新增；mock CPU-only（不 import 真 torch/sglang/flashinfer——被测函数源从
应用后文本抽取、以假模块注入 exec；补丁对自建临时基底 git apply）。
法源：S-FIS0-RESULT-20261018.md §二-A1/A2/A7 冻结设计；INV-06 §6.1 F3 行三断言；
F4-BAKE-PLAN-20261025.md §1.1.1 #4-#6 / §1.2；D31（A2 落 overlay 面）。
"""
import ast
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest
import typing as TYPING

REPO = Path(__file__).resolve().parents[2]
PATCHES = REPO / "tools/patches"
SG_SRC = Path.home() / "sglang-main-src"

A1_REL = "python/sglang/srt/mem_cache/deepseek_v4_memory_pool.py"
A7_REL = "python/sglang/srt/model_executor/pool_configurator.py"
A2_REL = "deploy/reconstruct/0.3.2/overlay/deepseek_v4_backend.py"

A1_PATCH = "r033-a1.memory-pool-v41-unlock.patch"
A7_PATCH = "r033-a7.pool-configurator-fp4-pricing.patch"
A2_PATCH = "r033-a2.overlay-backend-fi072-wiring.patch"

# 基底 md5 锚（S0-DESK-BATCH-20261025.md 台账同值）
BASE_MD5 = {
    A1_REL: "a065ddfc49e9d4b9e3d2739e7e44b488",
    A7_REL: "b31e0726cef636fbb291e85e735662dc",
    A2_REL: "a1e7c3b5f769d89d824c2bc0c9145e0c",
}

# 0.7.2 实测常量（fi072-unpacked _execution.py:66 / _policy.py:129-140 亲读）
KV_SCALE_FORMATS_072 = frozenset({"auto", "pow2_fp32", "arbitrary_fp32", "ue8m0_g32"})
KV_SCALE_FORMATS_0618 = frozenset({"auto", "pow2_fp32", "arbitrary_fp32"})


# ---------------------------------------------------------------- 工具
def _md5(p: Path) -> str:
    import hashlib

    return hashlib.md5(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def applied():
    """自建临时基底→git apply 三补丁→{rel: 应用后文本}；模块级一次。"""
    tmp = Path(tempfile.mkdtemp(prefix="r033ab-test-"))
    out = {}
    try:
        sg = tmp / "sglang"
        dl = tmp / "delivery"
        for rel in (A1_REL, A7_REL):
            (sg / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(SG_SRC / rel, sg / rel)
        (dl / A2_REL).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / A2_REL, dl / A2_REL)
        for rel in (A1_REL, A7_REL, A2_REL):
            root = sg if not rel.startswith("deploy/") else dl
            want = BASE_MD5[rel]
            assert _md5(root / rel) == want, f"基底漂移 {rel}"
            patch = str(PATCHES / {"python/sglang/srt/mem_cache/deepseek_v4_memory_pool.py": A1_PATCH,
                                   "python/sglang/srt/model_executor/pool_configurator.py": A7_PATCH,
                                   A2_REL: A2_PATCH}[rel])
            r = subprocess.run(["git", "apply", "--check", patch], cwd=root,
                               capture_output=True, text=True)
            assert r.returncode == 0, f"{rel} --check 非干净：{r.stderr}"
            subprocess.run(["git", "apply", patch], cwd=root, check=True)
            out[rel] = (root / rel).read_text(encoding="utf-8")
        yield out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _extract_fn(src: str, name: str) -> str:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            seg = ast.get_source_segment(src, node)
            assert seg
            return seg
    raise AssertionError(f"function {name} not found")


def _exec_fn(fn_src: str, ns: dict):
    exec(compile(fn_src, "<patched-fn>", "exec"), ns)
    return ns


class _FakeDispatch:
    """_DecodeDispatchEnvelope 0.7.2 谓词对象同构：(h,k) in iff 1<=h<=128 and k>=min_topk."""

    def __init__(self, min_topk=1, max_heads=128):
        self.min_topk, self.max_heads = min_topk, max_heads

    def __contains__(self, pair):
        h, k = pair
        return 1 <= h <= self.max_heads and k >= self.min_topk


def _install_fake_fi072(monkeypatchlike, *, formats=KV_SCALE_FORMATS_072,
                        dispatch=None, fail=False):
    fake = types.ModuleType("flashinfer")
    mla = types.ModuleType("flashinfer.mla")
    sm = types.ModuleType("flashinfer.mla._sparse_mla_sm120")
    if fail:
        def _boom(*a, **k):
            raise ImportError("simulated: no flashinfer")
        fake.__getattr__ = _boom
        mla.__getattr__ = _boom
        sm.__getattr__ = _boom
        monkeypatchlike.setitem(sys.modules, "flashinfer", fake)
        monkeypatchlike.setitem(sys.modules, "flashinfer.mla", mla)
        monkeypatchlike.setitem(sys.modules, "flashinfer.mla._sparse_mla_sm120", sm)
        return
    sm._KV_SCALE_FORMATS = formats
    sm._DECODE_DSV4_1_DISPATCH = dispatch if dispatch is not None else _FakeDispatch()
    # A2 探针还 import 这两个 0.7.2-only 符号（writer + 读入口）
    sm._sparse_mla_sm120_paged_attention = object()
    sm.dsv41_fp8_quantize_append_sparse_mla_cache = object()
    fake.mla = mla
    mla._sparse_mla_sm120 = sm
    monkeypatchlike.setitem(sys.modules, "flashinfer", fake)
    monkeypatchlike.setitem(sys.modules, "flashinfer.mla", mla)
    monkeypatchlike.setitem(sys.modules, "flashinfer.mla._sparse_mla_sm120", sm)


class FakeKVLayout:
    """kv_layout.py 同构最小假体：bytes_per_token + page_bytes（page_align=576）。"""

    PAGE_ALIGN = 576

    def __init__(self, name, bpt):
        self.name, self._bpt = name, bpt

    @property
    def bytes_per_token(self):
        return self._bpt

    def page_bytes(self, page_size):
        raw = page_size * self._bpt
        return -(-raw // self.PAGE_ALIGN) * self.PAGE_ALIGN


KV4 = FakeKVLayout("V4", 584)
KV41 = FakeKVLayout("V41", 528)
KV41FP4 = FakeKVLayout("V41_FP4", 288)


def _stock_resolve(kv_layout, compress_ratio, option=None):
    """deepseek_v4_memory_pool.resolve_compressed_kv_layout 逐字语义（stock 79cafec0）。"""
    if kv_layout is KV4:
        assert option in (None, "fp8"), "the V4 main cache only pairs with V4 caches"
        return KV4
    assert kv_layout is KV41, f"{kv_layout} is not a main-cache layout"
    if option == "fp8":
        return KV41
    if option == "fp4":
        return KV41FP4
    return KV41FP4 if compress_ratio in (1, 2) else KV41


class FakeTorch:
    """select_dsv4_kv_layout 依赖面最小假体。"""

    class cuda:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def get_device_capability():
            return FakeTorch._cap

    _cap = (12, 1)

    class version:
        cuda = "13.0"


def _install_fake_mp_chain(monkeypatchlike, leaf):
    """A7 被测函数体内 `from sglang.srt.mem_cache.deepseek_v4_memory_pool import ...`
    的导入链假体：父包逐级入 sys.modules，叶=leaf。"""
    sg = types.ModuleType("sglang")
    srt = types.ModuleType("sglang.srt")
    mc = types.ModuleType("sglang.srt.mem_cache")
    sg.srt = srt
    srt.mem_cache = mc
    mc.deepseek_v4_memory_pool = leaf
    monkeypatchlike.setitem(sys.modules, "sglang", sg)
    monkeypatchlike.setitem(sys.modules, "sglang.srt", srt)
    monkeypatchlike.setitem(sys.modules, "sglang.srt.mem_cache", mc)
    monkeypatchlike.setitem(sys.modules,
                            "sglang.srt.mem_cache.deepseek_v4_memory_pool", leaf)


# ---------------------------------------------------------------- A1
class TestA1:
    def test_a1_probe_positive_072(self, applied, monkeypatch):
        """断言②正路径：0.7.2 面（ue8m0_g32 在值域+(32,512)∈envelope）→探针 True。"""
        _install_fake_fi072(monkeypatch)
        ns = {}
        _exec_fn(_extract_fn(applied[A1_REL], "flashmla_supports_v41_kv_layouts"), ns)
        assert ns["flashmla_supports_v41_kv_layouts"]() is True

    def test_a1_probe_negative_0618_and_absent(self, applied, monkeypatch):
        """断言②负路径：0.6.18 值域（无 ue8m0_g32）→False；import 失败→False（fail-closed）。"""
        _install_fake_fi072(monkeypatch, formats=KV_SCALE_FORMATS_0618)
        ns = {}
        _exec_fn(_extract_fn(applied[A1_REL], "flashmla_supports_v41_kv_layouts"), ns)
        assert ns["flashmla_supports_v41_kv_layouts"]() is False
        _install_fake_fi072(monkeypatch, fail=True)
        ns2 = {}
        _exec_fn(_extract_fn(applied[A1_REL], "flashmla_supports_v41_kv_layouts"), ns2)
        assert ns2["flashmla_supports_v41_kv_layouts"]() is False

    def test_a1_sm121_unlock_select_v41(self, applied, monkeypatch):
        """冻结第①点行为：SM121（major 12）+探针 True + mode=v41 → V41 被选中。"""
        _install_fake_fi072(monkeypatch)
        probe_src = _extract_fn(applied[A1_REL], "flashmla_supports_v41_kv_layouts")
        sel_src = _extract_fn(applied[A1_REL], "select_dsv4_kv_layout")
        envs = types.SimpleNamespace(
            SGLANG_DSV4_KV_LAYOUT=types.SimpleNamespace(get=lambda: "v41"),
            SGLANG_DSV4_COMPRESSED_KV_LAYOUT=types.SimpleNamespace(get=lambda: "auto"),
        )
        ns = {"envs": envs, "KVLayout": types.SimpleNamespace(V4=KV4, V41=KV41),
              "torch": FakeTorch, "logger": types.SimpleNamespace(
                  warning=lambda *a, **k: None),
              "Tuple": TYPING.Tuple, "Optional": TYPING.Optional}
        exec(compile(probe_src, "<probe>", "exec"), ns)
        exec(compile(sel_src, "<select>", "exec"), ns)
        assert ns["select_dsv4_kv_layout"]() == (KV41, "auto")

    def test_a1_negative_sm90_still_rejected(self, applied, monkeypatch):
        """负路径：major 9（不在 (10,12)）→ v41 显式模式仍 assert 拒绝。"""
        _install_fake_fi072(monkeypatch)
        probe_src = _extract_fn(applied[A1_REL], "flashmla_supports_v41_kv_layouts")
        sel_src = _extract_fn(applied[A1_REL], "select_dsv4_kv_layout")
        envs = types.SimpleNamespace(
            SGLANG_DSV4_KV_LAYOUT=types.SimpleNamespace(get=lambda: "v41"),
            SGLANG_DSV4_COMPRESSED_KV_LAYOUT=types.SimpleNamespace(get=lambda: "auto"),
        )
        ns = {"envs": envs, "KVLayout": types.SimpleNamespace(V4=KV4, V41=KV41),
              "torch": FakeTorch, "logger": types.SimpleNamespace(
                  warning=lambda *a, **k: None),
              "Tuple": TYPING.Tuple, "Optional": TYPING.Optional}
        exec(compile(probe_src, "<probe>", "exec"), ns)
        exec(compile(sel_src, "<select>", "exec"), ns)
        FakeTorch._cap = (9, 0)
        try:
            with pytest.raises(AssertionError):
                ns["select_dsv4_kv_layout"]()
        finally:
            FakeTorch._cap = (12, 1)


# ---------------------------------------------------------------- A7
class TestA7:
    def _pricing_fn(self, applied):
        ns = {"__name__": "x"}
        _exec_fn(_extract_fn(applied[A7_REL], "_compressed_bytes_per_full_token"), ns)
        return ns["_compressed_bytes_per_full_token"]

    def _fake_self(self, kv_bytes=584, page_size=256, low_ratio_index_bytes=68):
        fake_mp = types.ModuleType("sglang.srt.mem_cache.deepseek_v4_memory_pool")
        fake_self = types.SimpleNamespace(
            kv_bytes=kv_bytes,
            page_size=page_size,
            low_ratio_index_bytes=low_ratio_index_bytes,
            c4_shrink_factor=1,
            indexer_bytes_per_token=68,
            _get_paged_kv_bytes_per_token=lambda ratio=0: (
                KV4.page_bytes(page_size) / page_size if ratio == 0
                else _stock_resolve(KV4, ratio, None).page_bytes(page_size // ratio)
                / (page_size // ratio)
            ),
        )
        return fake_self, fake_mp

    def test_a7_ratio12_priced_at_288(self, applied, monkeypatch):
        """断言①行为：v41 下 ratio-1/2 按 V41_FP4 288 计价（356/178），非 kv_bytes 584。"""
        fake_self, fake_mp = self._fake_self()
        _install_fake_mp_chain(monkeypatch, fake_mp)
        fake_mp.select_dsv4_kv_layout = lambda: (KV41, "auto")
        fake_mp.resolve_compressed_kv_layout = _stock_resolve
        fn = self._pricing_fn(applied)
        assert fn(fake_self, 1) == pytest.approx((288.0 + 68) / 1)
        assert fn(fake_self, 2) == pytest.approx((288.0 + 68) / 2)

    def test_a7_full_ledger_91225(self, applied, monkeypatch):
        """冻结账式：stage_owner_layers {1:[20],2:[2,8,14]} → (288+68)*2.5*41/40 = 912.25。"""
        fake_self, fake_mp = self._fake_self()
        _install_fake_mp_chain(monkeypatch, fake_mp)
        fake_mp.select_dsv4_kv_layout = lambda: (KV41, "auto")
        fake_mp.resolve_compressed_kv_layout = _stock_resolve
        fn = self._pricing_fn(applied)
        owners = {1: [20], 2: [2, 8, 14]}
        raw = sum(fn(fake_self, r) * len(ls) for r, ls in owners.items())
        assert raw == pytest.approx(890.0)
        assert raw * 41 / 40 == pytest.approx(912.25)

    def test_a7_stock_variant_differs_and_ratio4_untouched(self, applied, monkeypatch):
        """负路径双验：584 派生变体（禁值族）≠ 288 派生值；ratio-4/128 走 stock 原路不变。"""
        fake_self, fake_mp = self._fake_self()
        _install_fake_mp_chain(monkeypatch, fake_mp)
        fake_mp.select_dsv4_kv_layout = lambda: (KV41, "auto")
        fake_mp.resolve_compressed_kv_layout = _stock_resolve
        fn = self._pricing_fn(applied)
        patched_sum = sum(fn(fake_self, r) * len(ls)
                          for r, ls in {1: [20], 2: [2, 8, 14]}.items())
        stock_sum = (584 + 68) * 2.5
        assert stock_sum == pytest.approx(1630.0)
        assert patched_sum != pytest.approx(stock_sum)
        # ratio-4：走 stock _get_paged_kv_bytes_per_token(4)（V4 解析链），行为不变
        assert fn(fake_self, 4) == pytest.approx(
            1 / (4 * 1) * (KV4.page_bytes(256 // 4) / (256 // 4)) + 1 / 4 * 68)
        assert fn(fake_self, 128) == pytest.approx(
            1 / 128 * (KV4.page_bytes(256 // 128) / (256 // 128)))


# ---------------------------------------------------------------- A2
class TestA2:
    def test_a2_explicit_literals_and_call_shape(self, applied):
        """断言③行为：kv_scale_format="ue8m0_g32" 字面 + extra_fp4=True 显式 + pa 调用形态。"""
        src = applied[A2_REL]
        assert src.count('kv_scale_format="ue8m0_g32"') >= 1
        assert src.count("extra_fp4=True") >= 1
        assert 'kv_scale_format="auto"' not in src
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and ((isinstance(n.func, ast.Name) and n.func.id == "_sparse_mla_sm120_paged_attention")
                      or (isinstance(n.func, ast.Attribute) and n.func.attr == "_sparse_mla_sm120_paged_attention"))]
        assert len(calls) == 1
        kw = {k.arg: k.value for k in calls[0].keywords}
        assert ast.literal_eval(kw["kv_scale_format"]) == "ue8m0_g32"
        assert ast.literal_eval(kw["extra_fp4"]) is True
        assert ast.literal_eval(kw["mid_out"]) is None
        assert ast.literal_eval(kw["mid_lse"]) is None

    def test_a2_store_face_writer_and_fallback(self, applied):
        """store 面行为：V41+0.7.2 → dsv41_fp8_quantize_append_sparse_mla_cache；stock 回退保留。"""
        src = applied[A2_REL]
        assert "dsv41_fp8_quantize_append_sparse_mla_cache(" in src
        tree = ast.parse(src)
        store = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "store_cache":
                store = node
        assert store is not None
        sseg = ast.get_source_segment(src, store)
        assert "pool.kv_layout is KVLayout.V41 and _dsv41_fi072_native_available()" in sseg
        assert "set_swa_key_buffer_radix_fused(" in sseg  # stock 回退（负路径路径在位）

    def test_a2_probe_failclosed_and_cached(self, applied, monkeypatch):
        """探针行为：import 失败→False（fail-closed）；假 0.7.2 面→True 且缓存二跑一致。"""
        ns = {"_DSV41_FI072_NATIVE": None}
        _exec_fn(_extract_fn(applied[A2_REL], "_dsv41_fi072_native_available"), ns)
        fn = ns["_dsv41_fi072_native_available"]
        monkeypatch.delitem(sys.modules, "flashinfer", raising=False)
        monkeypatch.delitem(sys.modules, "flashinfer.mla", raising=False)
        monkeypatch.delitem(sys.modules, "flashinfer.mla._sparse_mla_sm120", raising=False)
        ns["_DSV41_FI072_NATIVE"] = None  # 复位缓存
        assert fn() is False
        _install_fake_fi072(monkeypatch)
        ns["_DSV41_FI072_NATIVE"] = None
        assert fn() is True
        assert fn() is True  # 缓存二跑

    def test_a2_reverse_apply_clean(self, applied, tmp_path):
        """可回退性：应用后文本对补丁 git apply -R 干净（D31 overlay 单文件回退面）。"""
        rel = A2_REL
        base = tmp_path / "delivery" / rel
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text(applied[rel], encoding="utf-8")
        r2 = subprocess.run(
            ["git", "apply", "-R", str(PATCHES / A2_PATCH)],
            cwd=str(tmp_path / "delivery"), capture_output=True, text=True)
        assert r2.returncode == 0, r2.stderr
        assert _md5(base) == BASE_MD5[rel], "回退后应逐字节回到 a1e7c3b5 基底"
