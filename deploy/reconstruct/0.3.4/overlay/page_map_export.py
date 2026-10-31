"""DSV41 KV 池页映射引擎侧导出件（A.2 · E10-3 闭合制备 · X6 bake R1 2026-10-26）

法源：T34-05-X6-BAKE-WINDOW §五（A.2 搭车件设计）；F6-A 判 #8 RED×3 根因=
引擎不导出页映射（W6 §3.2 #8；D28 裁=E10-3 引擎面缺口）。本件=overlay 第 29
源制备件——**本窗只制备不激活**（overlay-map 扩行/调用点接线候重锚窗）。

env 门控（I14-C/SCHED_STATS 先例制式；D20 测量旗永不入产线缺省态）：
  DSV41_PAGE_MAP_EXPORT —— 缺省未设/空 = export_enabled()=False =
  snapshot() 即时返回 None（零行为零开销面）；设为目录路径 = 快照 JSONL
  追加写 <dir>/page-map-r<rank>.jsonl。

对拍契约（与窗侧量具 kv_recall_c11.py 判 #8 page_rebuilds[] 形）：
  - 页序列正典串 = ",".join(str(int(p)) for p in pages)
  - page_seq_sha256 = hashlib.sha256(正典串 utf-8).hexdigest()
  - manifest 行字段：rank/tag/ts/page_seq_sha256/pages_full/pages_total/
    alias_conflicts/free_list_conflicts/seq_source
  窗侧工具消费（judge #8 的 sha_match_expected 实证化）=激活窗配套
  （量具只读 compare 增量，判据面不变）。

导出面（rank 级 page→request/seq 映射的聚合形）：
  - 数据源=ReqToTokenPool.req_to_token（行=请求槽，值=token 槽位）；
    pages_full=去重后已分配页数；alias_conflicts=同页出现于多请求行（应 0）；
    free_list_conflicts=已分配页仍见于分配器 free 表（应 0；需传 allocator）。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional, Sequence

_ENV_KEY = "DSV41_PAGE_MAP_EXPORT"


def export_enabled() -> bool:
    """门控：DSV41_PAGE_MAP_EXPORT 未设/空 → False（缺省关=零行为）。"""
    return bool(os.environ.get(_ENV_KEY, "").strip())


def canonical_page_seq(pages: Sequence[int]) -> str:
    """页序列正典串（窗侧对拍契约形）。"""
    return ",".join(str(int(p)) for p in pages)


def page_seq_sha256(pages: Sequence[int]) -> str:
    return hashlib.sha256(canonical_page_seq(pages).encode("utf-8")).hexdigest()


def snapshot(
    req_to_token_pool: Any,
    *,
    rank: int,
    tag: str = "",
    page_size: int = 1,
    kv_allocator: Any = None,
    active_rows: Optional[Sequence[int]] = None,
) -> Optional[dict]:
    """采一份 rank 级页映射快照；门控关时零行为返回 None。

    - active_rows：参与对拍的请求槽行号（缺省=free_slots 之外的全部行——
      即已分配行；调用点接线时以 scheduler 在役请求表为准传入更精确行集）。
    - kv_allocator：可选（paged/base 形）；提供时核 free_list_conflicts。
    """
    if not export_enabled():
        return None
    pool_rows = req_to_token_pool.req_to_token
    size = int(getattr(req_to_token_pool, "size", pool_rows.shape[0] - 1))
    if active_rows is None:
        free = set(
            int(s) for s in getattr(req_to_token_pool, "free_slots", []) or []
        )
        active_rows = [r for r in range(1, size + 1) if r not in free]
    pages: list[int] = []
    seen: dict[int, int] = {}
    alias_conflicts = 0
    import torch  # 容器/引擎环境内延迟导入

    for row in active_rows:
        vals = pool_rows[int(row)]
        vals = vals[vals > 0]
        if vals.is_cuda:
            vals = vals.to("cpu", non_blocking=False)
        for slot in vals.tolist():
            page = int(slot) // max(int(page_size), 1)
            if page in seen and seen[page] != int(row):
                alias_conflicts += 1
            seen.setdefault(page, int(row))
            pages.append(page)
    free_list_conflicts = 0
    if kv_allocator is not None:
        free_pages = getattr(kv_allocator, "free_pages", None)
        if free_pages is not None:
            if isinstance(free_pages, torch.Tensor):
                free_set = set(free_pages.tolist())
            else:
                free_set = set(int(p) for p in free_pages)
            free_list_conflicts = sum(1 for p in seen if p in free_set)
    manifest = {
        "rank": int(rank),
        "tag": str(tag),
        "ts": time.time(),
        "page_seq_sha256": page_seq_sha256(pages),
        "pages_full": len(seen),
        "pages_total": len(pages),
        "alias_conflicts": alias_conflicts,
        "free_list_conflicts": free_list_conflicts,
        "seq_source": "req_to_token_pool.req_to_token",
    }
    out_dir = os.environ[_ENV_KEY].strip()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"page-map-r{int(rank)}.jsonl")
    with open(out_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, sort_keys=True) + "\n")
    return manifest
