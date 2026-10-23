# T33-10 —— G-CACHE grammar/structured-output cache 有界性静态检查（CPU-only）
#
# 法源：docs/plan/033-TASKBOOK-V2-20261023.md §2.1 A12（:122）、§3.0.1「G-CACHE」行
#       （:343）、T33-10 任务节目标 1/验收门/反例（:433-435, :445-452）、
#       033-W0/NO-GO-REGISTRY.md §三（0.3.4 候选迁移预告：A12 grammar cache 有界化）。
#
# 现状登记（expected xfail, strict=True——这是现状登记，不是修复项）：
#   现役 python/sglang/srt/constrained/base_grammar_backend.py:206
#   `self.cache: Dict[Tuple[str, str], BaseGrammarObject] = {}` 是无界 dict
#   （BaseGrammarBackend 基类，xgrammar/outlines/llguidance/reasoner 各后端继承；
#   set_cache 只写不清、无容量/TTL/LRU 上限），与 CVE-2025-32381（NVD：无界 cache
#   致内存耗尽 DoS，xgrammar 结构化输出路径）同类风险面。
#   有界化属 0.3.4 护栏项；0.3.3 不改产线（反例：为过测改 base_grammar_backend.py
#   直接打回）。
#
# 检查面（本文件唯一一个测试函数；0.3.4 有界化落地后本测试应转 XPASS→删标记升级为
# 正常测试，任务书验收门）：
#   ①锚定：self.cache 确为语法编译缓存（get_cached_or_future_value 读 / set_cache 写）；
#   ②有界性：缓存结构必须有容量（len 比较）/TTL/LRU（move_to_end、popitem、
#     LRUCache/TTLCache/lru_cache 等）任一上限证据；
#   ③CVE-2025-32381 防护点存在：_grammar_key_contains_nul（NUL 字节语法键拒绝，
#     :161-188）必须在基类缓存未命中编译路径（_init_value_dispatch, :263）被调用。
#   ②缺失即红（现状）；③现役已存在（不应缺失，缺失则 reason 需 T33-09 受理更新）。
#
# 运行纪律：CPU-only、无网络、无模型权重、只读源码 AST/文本、<1s；
# 现状红复现：pytest -q tests/quality/test_no_go_grammar_cache.py --runxfail。

import ast

import pytest

from conftest import SGLANG_SRC

BASE_GRAMMAR_BACKEND = (
    SGLANG_SRC + "/python/sglang/srt/constrained/base_grammar_backend.py"
)

# 固定 reason（任务书 §3.0.1/T33-10 节逐字指定，不得改写）
XFAIL_REASON = (
    "现役 grammar cache 无界（base_grammar_backend.py:206），0.3.4 护栏项；0.3.3 不改产线"
)

# 有界性证据 token（容量/TTL/LRU 三选一；大小写不敏感匹配类源码）
BOUND_EVIDENCE_TOKENS = (
    "len(self.cache)",  # 容量上限检查
    "ttl",  # TTL
    "lru",  # LRU
    "move_to_end",  # OrderedDict LRU 淘汰
    "popitem",  # LRU/FIFO 淘汰
    "evict",  # 显式淘汰
    "maxsize",  # 有界构造参数
    "max_cache_size",
    "cache_capacity",
)
# self.cache 赋值右侧出现即视为有界容器的构造器
BOUNDED_CONSTRUCTORS = ("lrucache", "ttlcache", "lru_cache", "fifocache")


def _class_source(tree, source, class_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node, ast.get_source_segment(source, node)
    return None, None


def _cache_assignment(cls_node, source):
    """定位 __init__ 内对 self.cache 的赋值（AnnAssign/Assign），返回 (行号, 右侧源码)。"""
    for stmt in ast.walk(cls_node):
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and isinstance(
            stmt.value, ast.AST
        ):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "cache"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    return stmt.lineno, ast.get_source_segment(source, stmt.value)
    return None, None


def _method_body_source(cls_node, source, method_name):
    for stmt in cls_node.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == method_name:
            return ast.get_source_segment(source, stmt)
    return None


def _calls_named(method_src, callee_name):
    for node in ast.walk(ast.parse(method_src)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == callee_name
        ):
            return True
    return False


@pytest.mark.xfail(strict=True, reason=XFAIL_REASON)
def test_grammar_cache_bounded_with_cve_protection():
    """G-CACHE：grammar cache 必须有界 + CVE-2025-32381 防护点存在（静态检查）。"""
    with open(BASE_GRAMMAR_BACKEND, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    cls_node, cls_src = _class_source(tree, source, "BaseGrammarBackend")
    assert cls_node is not None, "BaseGrammarBackend 类缺失（锚定失败）"

    # ---- ①锚定：self.cache 是语法编译缓存（读写路径都在基类上）----
    get_src = _method_body_source(cls_node, source, "get_cached_or_future_value")
    set_src = _method_body_source(cls_node, source, "set_cache")
    assert get_src and "self.cache.get(" in get_src, (
        "锚定失败：get_cached_or_future_value 必须读 self.cache"
    )
    assert set_src and "self.cache[" in set_src, (
        "锚定失败：set_cache 必须写 self.cache"
    )

    # ---- ②有界性（现状红点）+ ③CVE-2025-32381 防护点：先收集，后统一断言 ----
    lineno, rhs = _cache_assignment(cls_node, source)
    assert lineno is not None, "锚定失败：__init__ 必须初始化 self.cache"
    rhs_lower = (rhs or "").lower()
    cls_lower = cls_src.lower()
    bound_hits = [t for t in BOUND_EVIDENCE_TOKENS if t in cls_lower]
    bounded_constructor = any(c in rhs_lower for c in BOUNDED_CONSTRUCTORS)
    # 有界判定：类体含容量/TTL/LRU 证据 token，或 self.cache 直接构造为有界容器。
    # 现状两者皆无：rhs={}（:206 无界 dict）且类体零命中 → 登记红。
    bounded = bool(bound_hits) or bounded_constructor

    # CVE-2025-32381 防护点：NUL 字节语法键拒绝函数存在，且在基类缓存未命中
    # 编译路径 _init_value_dispatch 内被调用（而非仅定义未接线）。
    nul_guard_defined = "_grammar_key_contains_nul" in source and any(
        isinstance(node, ast.FunctionDef)
        and node.name == "_grammar_key_contains_nul"
        for node in ast.walk(tree)
    )
    init_dispatch_src = _method_body_source(cls_node, source, "_init_value_dispatch")
    nul_guard_wired = bool(init_dispatch_src) and _calls_named(
        init_dispatch_src, "_grammar_key_contains_nul"
    )

    findings = []
    if not bounded:
        findings.append(
            f"无界 grammar cache：base_grammar_backend.py:{lineno} "
            f"self.cache = {rhs!r}（登记基准 :206），类体内容量/TTL/LRU 上限证据均缺"
            f"（bound_hits={bound_hits}, bounded_constructor={bounded_constructor}）"
        )
    if not (nul_guard_defined and nul_guard_wired):
        findings.append(
            "CVE-2025-32381 防护点缺失：_grammar_key_contains_nul 未定义或未接入"
            " _init_value_dispatch 编译路径"
        )

    assert not findings, (
        "G-CACHE 现状红："
        + ("；".join(findings) if findings else "无发现")
        + "。0.3.4 护栏项；0.3.3 不改产线（G-CACHE↔A12，"
        "CVE-2025-32381=NVD 无界 cache 内存耗尽 DoS；本测试只登记现状）。"
        + (
            " 附：CVE-2025-32381 防护点（NUL 拒绝）现役存在——不缺。"
            if nul_guard_defined and nul_guard_wired
            else ""
        )
    )
