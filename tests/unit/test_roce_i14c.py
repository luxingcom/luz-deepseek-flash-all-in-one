"""ROCE_I14C CPU 单测（I14-C 案 A/B 开发批；0 靴，mock 数据驱动，2026-10-24）.

法源: 033-TASKBOOK-V2-20261023.md §T33-08 目标 3/验收门; INV-07 §1.3/§4.2/§4.3;
      W4-WINDOW-REPORT-20261024.md §3.3/§七-10（AST 名覆盖标准门）.
被测件: tools/obs/roce_i14c.py（canonical）与
        tools/patches/i14c-scheduler-roc-sync.patch +
        tools/patches/i14c-adapter-gauges.patch（呈裁接线件，未应用）。
不 import sglang/torch/GPU/prometheus；单次 <60s。运行:
  /tmp/w0venv/bin/python -m pytest -q tests/unit/test_roce_i14c.py -o cache_dir=/tmp/w0cache
"""

import ast
import builtins
import importlib.util
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import types

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODULE_PATH = os.path.join(REPO, "tools", "obs", "roce_i14c.py")
PATCH_SCHED = os.path.join(REPO, "tools", "patches", "i14c-scheduler-roc-sync.patch")
PATCH_ADAPTER = os.path.join(REPO, "tools", "patches", "i14c-adapter-gauges.patch")
SCHED_REL = "deploy/overlay/o12c1-prod/scheduler.py"
RA_REL = "deploy/adapter/roce_ar.py"
SC_REL = "deploy/adapter/sitecustomize.py"
MG_REL = "deploy/adapter/roce_metrics_gauge.py"

_spec = importlib.util.spec_from_file_location("roce_i14c", MODULE_PATH)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

BEG = "# ---- i14c-canonical: begin"
END = "# ---- i14c-canonical: end"
_canon_src = open(MODULE_PATH, encoding="utf-8").read()
_canon_block = _canon_src[_canon_src.index(BEG): _canon_src.index(END)]
CANON_CLASS_SRC = "\n".join(
    ln for ln in _canon_block.splitlines()
    if not ln.startswith("# ---- i14c-canonical")
).strip()


# ---- 被测件存在性 ------------------------------------------------------------
def test_canonical_module_and_patches_exist():
    assert os.path.isfile(MODULE_PATH)
    assert os.path.isfile(PATCH_SCHED)
    assert os.path.isfile(PATCH_ADAPTER)
    for p in (PATCH_SCHED, PATCH_ADAPTER):
        head = open(p, encoding="utf-8").read(300)
        assert "呈裁件" in head, p


# ---- 采样器核心行为 ----------------------------------------------------------
class FakeEvent:
    def __init__(self, done=True, boom=False):
        self.done, self.boom, self.checks = done, boom, 0

    def query(self):
        if self.boom:
            raise RuntimeError("query boom")
        return self.done


class Result:
    def __init__(self, ev=None):
        self.copy_done = ev


def test_sampler_every_n_gate():
    hits = []
    s = m.RoceSyncSampler(every=3, check_fn=lambda cd: hits.append(cd))
    for _ in range(9):
        s.observe(Result(FakeEvent()))
    assert s.observations == 9 and s.checked == 3 and len(hits) == 3


def test_sampler_query_gating_skips_busy_without_sync():
    hits = []
    s = m.RoceSyncSampler(every=1, check_fn=hits.append)
    for _ in range(5):
        s.observe(Result(FakeEvent(done=False)))
    assert s.checked == 0 and s.skipped_busy == 5 and not hits


def test_sampler_query_exception_swallowed():
    s = m.RoceSyncSampler(every=1, check_fn=lambda cd: None)
    s.observe(Result(FakeEvent(boom=True)))
    assert s.errors == 1 and s.checked == 0


def test_sampler_check_fn_exception_swallowed():
    def boom(cd):
        raise RuntimeError("check boom")

    s = m.RoceSyncSampler(every=1, check_fn=boom)
    s.observe(Result(FakeEvent()))
    assert s.checked == 1 and s.errors == 1


def test_sampler_no_copy_done_counted():
    s = m.RoceSyncSampler(every=1)
    s.observe(Result())
    s.observe(object())
    assert s.no_copy_done == 2 and s.checked == 0


def test_sampler_every_must_be_positive():
    with pytest.raises(ValueError):
        m.RoceSyncSampler(every=0)


def test_sampler_log_payload_shape_and_stats():
    logs = []
    s = m.RoceSyncSampler(
        every=1, log_fn=lambda fmt, *a: logs.append(fmt % a),
        stats_fn=lambda: {"roce_routed": 7, "nccl_kept": 3},
    )
    pay = s.observe(Result(FakeEvent()))
    assert len(logs) == 1 and logs[0].startswith("ROCE_I14C_SAMPLE {")
    assert pay["roce_ar"]["roce_routed"] == 7
    rec = json.loads(logs[0][len("ROCE_I14C_SAMPLE "):])
    assert rec["checked"] == 1 and "skipped_busy" in rec


# ---- gauge 面 ----------------------------------------------------------------
def test_gauges_from_stats_mapping():
    g = m.gauges_from_stats(
        {"communicators": 1, "roce_made": 1, "roce_routed": 10, "nccl_kept": 5}
    )
    assert g == {"roce_ar_communicators": 1, "roce_ar_roce_made": 1,
                 "roce_ar_roce_routed": 10, "roce_ar_nccl_kept": 5}
    assert m.gauges_from_stats(None) == {n: None for n in m.GAUGE_NAMES}
    assert m.gauges_from_stats({"communicators": "x"})[
        "roce_ar_communicators"] is None


def test_validate_gauges_negative_controls():
    ok = m.gauges_from_stats(
        {"communicators": 0, "roce_made": 0, "roce_routed": 0, "nccl_kept": 0}
    )
    assert m.validate_gauges(ok) == []
    assert m.validate_gauges({}) == [f"{n}:missing" for n in m.GAUGE_NAMES]
    assert m.validate_gauges({"roce_ar_nccl_kept": -1}) == [
        "roce_ar_communicators:missing", "roce_ar_roce_made:missing",
        "roce_ar_roce_routed:missing", "roce_ar_nccl_kept:negative",
    ]


def test_gauge_audit_monotonic_and_regression():
    aud = m.GaugeAudit()
    g1 = m.gauges_from_stats(
        {"communicators": 1, "roce_made": 1, "roce_routed": 10, "nccl_kept": 5}
    )
    g2 = dict(g1, roce_ar_roce_routed=11)
    g3 = dict(g2, roce_ar_roce_routed=9)
    assert aud.feed(g1) == [] and aud.feed(g2) == []
    assert any("regressed" in x for x in aud.feed(g3))
    assert any("regressed" in x for x in aud.violations)


def test_render_parse_roundtrip_and_pid_variant():
    g = m.gauges_from_stats(
        {"communicators": 1, "roce_made": 1, "roce_routed": 10, "nccl_kept": 5}
    )
    text = m.render_prometheus(g)
    got = m.parse_scrape(text)
    assert all(abs((got[n] or 0) - g[n]) < 1e-9 for n in m.GAUGE_NAMES)
    pid_text = (
        'roce_ar_roce_routed{pid="1"} 10\n'
        'roce_ar_roce_routed{pid="2"} 12\n# comment\n'
    )
    assert m.parse_scrape(pid_text)["roce_ar_roce_routed"] == 12.0


def test_cross_check_agrees_when_gauge_ge_log():
    g = m.gauges_from_stats(
        {"communicators": 1, "roce_made": 1, "roce_routed": 10, "nccl_kept": 5}
    )
    assert m.cross_check(g, {"roce_routed": 10, "nccl_kept": 5}) == []
    bad = m.cross_check(g, {"roce_routed": 11, "nccl_kept": 5})
    assert any("roce_ar_roce_routed" in x for x in bad)


# ---- scheduler face（SCHEDULER_FACE_SOURCE exec 求值）------------------------
class _FakeLogger:
    def __init__(self):
        self.lines = []

    def info(self, *a, **k):
        self.lines.append(a[0] % a[1:] if len(a) > 1 else a[0])


def test_scheduler_face_default_off_returns_none():
    ns = {"os": os, "json": json, "logger": _FakeLogger(),
          "RoceSyncSampler": m.RoceSyncSampler}
    exec(compile(m.SCHEDULER_FACE_SOURCE, "<i14c-face>", "exec"), ns)
    saved = dict(os.environ)
    try:
        os.environ.pop(m.ENV_SAMPLE, None)
        assert ns["_make_roce_i14c_sampler"]() is None
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_scheduler_face_refused_without_pynccl_surface():
    ns = {"os": os, "json": json, "logger": _FakeLogger(),
          "RoceSyncSampler": m.RoceSyncSampler}
    exec(compile(m.SCHEDULER_FACE_SOURCE, "<i14c-face>", "exec"), ns)
    saved = dict(os.environ)
    try:
        os.environ[m.ENV_SAMPLE] = "64"
        assert ns["_make_roce_i14c_sampler"]() is None
        assert any("REFUSED" in str(x) for x in ns["logger"].lines)
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_scheduler_face_armed_with_fake_modules():
    fake_pkg = types.ModuleType("sglang")
    fake_srt = types.ModuleType("sglang.srt")
    fake_dist = types.ModuleType("sglang.srt.distributed")
    fake_dc = types.ModuleType("sglang.srt.distributed.device_communicators")
    fake_pynccl = types.ModuleType(
        "sglang.srt.distributed.device_communicators.pynccl")
    checks = []

    def fake_check(copy_done):
        checks.append(copy_done)

    fake_pynccl.synchronize_and_check_roce = fake_check
    fake_dc.pynccl = fake_pynccl
    fake_mg = types.ModuleType("roce_metrics_gauge")
    refreshes = []
    fake_mg.refresh_gauges = lambda: refreshes.append(1) or True
    fake_ra = types.ModuleType("roce_ar")
    fake_ra.stats = lambda: {"roce_routed": 1, "nccl_kept": 2}
    mods = {
        "sglang": fake_pkg, "sglang.srt": fake_srt,
        "sglang.srt.distributed": fake_dist,
        "sglang.srt.distributed.device_communicators": fake_dc,
        "sglang.srt.distributed.device_communicators.pynccl": fake_pynccl,
        "roce_metrics_gauge": fake_mg, "roce_ar": fake_ra,
    }
    saved_mods = {k: sys.modules.get(k) for k in mods}
    saved_env = dict(os.environ)
    ns = {"os": os, "json": json, "logger": _FakeLogger(),
          "RoceSyncSampler": m.RoceSyncSampler}
    try:
        sys.modules.update(mods)
        os.environ[m.ENV_SAMPLE] = "2"
        exec(compile(m.SCHEDULER_FACE_SOURCE, "<i14c-face>", "exec"), ns)
        observe = ns["_make_roce_i14c_sampler"]()
        assert callable(observe)
        evs = [FakeEvent() for _ in range(4)]
        for ev in evs:
            observe(Result(ev))
        assert checks == evs[1::2] and len(refreshes) == 2
        assert any("ARMED" in str(x) for x in ns["logger"].lines)
    finally:
        os.environ.clear()
        os.environ.update(saved_env)
        for k, v in saved_mods.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


# ---- 呈裁补丁：应用/可逆/逐字一致/编译 ---------------------------------------
def _apply_patches(tmpdir, reverse=False):
    order = [PATCH_SCHED, PATCH_ADAPTER]
    for path in (reversed(order) if reverse else order):
        cmd = ["patch", "-p1", "-i", path] + (["-R"] if reverse else [])
        r = subprocess.run(cmd, cwd=tmpdir, capture_output=True, text=True,
                           env=dict(os.environ, LC_ALL="C"))
        assert r.returncode == 0, (path, r.stdout[-400:], r.stderr[-400:])


@pytest.fixture(scope="module")
def applied_tree(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("i14c_apply")
    for rel in (SCHED_REL, RA_REL, SC_REL):
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(os.path.join(REPO, rel), dst)
    _apply_patches(str(tmp))
    yield tmp


def test_patches_apply_and_compile(applied_tree):
    for rel in (SCHED_REL, RA_REL, SC_REL, MG_REL):
        py_compile.compile(str(applied_tree / rel), doraise=True)


def test_patches_reverse_apply_restores_bytes(tmp_path):
    tmp = tmp_path / "reverse"
    originals = {}
    for rel in (SCHED_REL, RA_REL, SC_REL):
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = os.path.join(REPO, rel)
        shutil.copyfile(src, dst)
        originals[rel] = open(src, "rb").read()
    _apply_patches(str(tmp))
    _apply_patches(str(tmp), reverse=True)
    for rel in (SCHED_REL, RA_REL, SC_REL):
        assert (tmp / rel).read_bytes() == originals[rel], rel


def _applied_defs(tree, rel):
    src = open(os.path.join(tree, rel), encoding="utf-8").read()
    tree_ast = ast.parse(src)
    out = {}
    for node in ast.walk(tree_ast):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in (
            "RoceSyncSampler", "_make_roce_i14c_sampler", "gauges"
        ) and node.name not in out:
            out[node.name] = ast.get_source_segment(src, node)
    return out


def test_scheduler_patch_inserts_canonical_class_verbatim(applied_tree):
    got = _applied_defs(applied_tree, SCHED_REL)["RoceSyncSampler"]
    assert got.strip() == CANON_CLASS_SRC.strip()


def test_scheduler_patch_factory_text_identity(applied_tree):
    got = _applied_defs(applied_tree, SCHED_REL)["_make_roce_i14c_sampler"]
    assert got.strip() == m.SCHEDULER_FACE_SOURCE.strip()


def test_adapter_patch_gauges_text_identity(applied_tree):
    got = _applied_defs(applied_tree, RA_REL)["gauges"]
    assert got.strip() == m.ADAPTER_GAUGES_SOURCE.strip()


def test_applied_scheduler_init_and_observe_wiring(applied_tree):
    src = open(os.path.join(applied_tree, SCHED_REL), encoding="utf-8").read()
    assert "self._roce_i14c = _make_roce_i14c_sampler()" in src
    assert "self._roce_i14c = None  # I14-C (T33-08): 案 A/B 默认关" in src
    assert ("if self._roce_i14c is not None:\n"
            "            self._roce_i14c(result)") in src


def test_applied_sitecustomize_hook_fail_safe_form(applied_tree):
    src = open(os.path.join(applied_tree, SC_REL), encoding="utf-8").read()
    assert "sglang.srt.observability.metrics_collector" in src
    assert "install_for_hook" in src
    assert "DSV41_ROCE_METRICS" in src
    ast.parse(src)  # 结构合法


# ---- 新模块 roce_metrics_gauge.py（从补丁应用产物 exec）----------------------
@pytest.fixture(scope="module")
def mg_module(applied_tree):
    src = open(os.path.join(applied_tree, MG_REL), encoding="utf-8").read()
    mod = types.ModuleType("roce_metrics_gauge_under_test")
    exec(compile(src, MG_REL, "exec"), mod.__dict__)
    return mod


@pytest.fixture(autouse=True)
def _reset_mg_globals(mg_module):
    yield
    mg_module._gauges = None
    mg_module._register_failed = False


class FakeGauge:
    def __init__(self, name, documentation=None, labelnames=None, **kw):
        self.name, self.docs, self.values = name, documentation, []
        self.kw = kw

    def set(self, v):
        self.values.append(v)


def test_metrics_gauge_default_off_no_register(mg_module, monkeypatch):
    monkeypatch.delenv(mg_module.ROCE_METRICS_ENV, raising=False)
    assert mg_module.armed() is False
    assert mg_module.install_once() is False
    assert mg_module.registered() == ()


def test_metrics_gauge_install_and_refresh_with_fake_factory(mg_module, monkeypatch):
    made = []

    def factory(name, documentation=None, labelnames=None, **kw):
        g = FakeGauge(name, documentation, labelnames, **kw)
        made.append(g)
        return g

    monkeypatch.setenv(mg_module.ROCE_METRICS_ENV, "1")
    monkeypatch.setattr(mg_module, "armed", lambda: True, raising=False)
    assert mg_module.install_once(gauge_factory=factory) is True
    assert len(made) == 4
    assert mg_module.registered() == tuple(sorted(mg_module.GAUGE_NAMES))
    assert mg_module.install_once(gauge_factory=factory) is True  # 幂等
    ok2 = mg_module.refresh_gauges(
        stats_fn=lambda: {"roce_ar_communicators": 1, "roce_ar_roce_made": 1,
                          "roce_ar_roce_routed": 10, "roce_ar_nccl_kept": 5}
    )
    assert ok2
    by_name = {g.name: g for g in made}
    assert by_name["roce_ar_roce_routed"].values == [10]
    assert by_name["roce_ar_nccl_kept"].values == [5]


def test_metrics_gauge_refresh_fail_safe_on_bad_stats(mg_module, monkeypatch):
    monkeypatch.setenv(mg_module.ROCE_METRICS_ENV, "1")
    monkeypatch.setattr(mg_module, "armed", lambda: True, raising=False)
    assert mg_module.install_once(gauge_factory=FakeGauge) is True

    def bad_stats():
        raise RuntimeError("stats boom")

    assert mg_module.refresh_gauges(stats_fn=bad_stats) is False  # 不 raise


# ---- AST 名覆盖标准门（W4 §3.3 裁定；S-W5PREP v2 收集器逻辑泛化复刻）---------
def _patch_inserted_lines(patch_path, target_rel):
    """补丁对 target_rel 的 new 侧插入行号集（+++ b/ 定文件；hunk 头连续计）。"""
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    out = set()
    cur = None
    in_target = False
    for raw in open(patch_path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("+++ b/"):
            in_target = (line == "+++ b/" + target_rel)
            cur = None
            continue
        if not in_target:
            continue
        m2 = hunk_re.match(line)
        if m2:
            cur = int(m2.group(1))
            continue
        if cur is None:
            continue
        if line.startswith("+"):
            out.add(cur)
            cur += 1
        elif line.startswith("-"):
            pass
        else:
            cur += 1
    return out


def _defined_names(tree):
    names = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                names.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            for d in node.decorator_list:
                for n2 in ast.walk(d):
                    if isinstance(n2, ast.Name):
                        names.add(n2.id)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.comprehension):
            for n2 in ast.walk(node.target):
                if isinstance(n2, ast.Name):
                    names.add(n2.id)
    return names


def test_ast_name_coverage_gate_scheduler_patch():
    """标准门：scheduler 补丁插入面全部裸名 ⊆ imports ∪ builtins ∪ 绑定。"""
    src = open(os.path.join(REPO, SCHED_REL), encoding="utf-8").read()
    tree = ast.parse(src)
    ins = _patch_inserted_lines(PATCH_SCHED, SCHED_REL)
    assert len(ins) > 100, f"插入面过小: {len(ins)}"
    required = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        and getattr(n, "lineno", 0) in ins
    }
    missing = sorted(required - _defined_names(tree))
    assert not missing, f"插入面缺覆盖裸名: {missing}"


def _patch_new_file_content(patch_path, target_rel):
    """从补丁 new-file 段提取新文件内容（/dev/null → b/rel 形）。"""
    lines = []
    in_target = False
    for raw in open(patch_path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.startswith("+++ b/"):
            in_target = (line == "+++ b/" + target_rel)
            continue
        if line.startswith("--- "):
            in_target = False
            continue
        if not in_target:
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines) + ("\n" if lines else "")


def test_ast_name_coverage_gate_adapter_patch():
    for rel in (RA_REL, SC_REL, MG_REL):
        if os.path.isfile(os.path.join(REPO, rel)):
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
        else:
            # 新文件（呈裁件内 /dev/null 形）：从补丁提取后同门覆盖。
            src = _patch_new_file_content(PATCH_ADAPTER, rel)
        tree = ast.parse(src)
        ins = _patch_inserted_lines(PATCH_ADAPTER, rel)
        if not ins:
            continue  # 零插入面目标（防御）
        required = {
            n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
            and getattr(n, "lineno", 0) in ins
        }
        missing = sorted(required - _defined_names(tree))
        assert not missing, f"{rel} 插入面缺覆盖裸名: {missing}"


# ---- canonical selfcheck 直跑 -------------------------------------------------
def test_canonical_selfcheck():
    r = subprocess.run(
        [sys.executable, MODULE_PATH, "--selfcheck"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SELFCHK ROCE_I14C ok" in r.stdout
