#!/usr/bin/env python3
"""KV_RECALL_C11 -- 满池 KV 驻留与召回全链判读量具（0 靴纯开发件，2026-10-24）。

法源
  * 任务书 `033-TASKBOOK-V2-20261023.md` :1310（"C11 召回量具"）、§T33-08 目标 4 /
    实施步骤 1 / 验收门（F6-A：C1..C16 六级阶梯、112/112、0 跨会话串值、四 rank
    committed FULL 一致、每 rank FULL 页独立重建、16/16 位置、close 后 slot=0、
    gauge 占用与池账差 ≤0.5%；attempt-notes 完整；负表#15 streaming 口径声明）。
  * 池件定义 `032-MASTER-TASKLIST-20261016.md` C11 行（EV-07-007）：
    C1/2/4/8/12/16 阶梯 + 每流七点随机记录（目标深度 1/10/25/50/75/90/99%）+
    同 key 异值跨会话串值检测 + 四级屏障（before/plateau/after-query/closed）
    四 rank 快照 + 完整页序列独立重建与 SHA/别名/free-list 冲突核对 + 历史
    backing 每位置抽样 ≤1024 bytes + close 后 slot/request-row 归零核；
    满池签收三条件（≥99% 逻辑池 + 评分 + 资源）+ SWA/FULL 分池看。
  * C12 断言面（同表 C12 行 / INV-07 §4.6）：变长文本 + 独立 salt + 冷态声明 +
    阶段记录；pool/MRR/ctx 三期望断言（judge_boot_expectations）。
  * INV-07 §4.4（F6-A 机制与失败模式：把外部 99.492% 当验收线=禁止）；
    EV-07-028/EV-07-049（外部基线 99.492%/112/112 为 E4 带外参照）。

性质与红线
  * 纯 stdlib（hashlib/json），不 import sglang/torch -- CPU-only 可测。
  * 本件是**判读侧**量具：消费窗内采集产出的 JSON 工件（召回记录/屏障快照/页
    重建 manifest/attempt-notes/boot 期望），不定义采集驱动本身（驱动=W6 窗内
    操作单 `033-W1/F6A-IF-PAGE-20261024.md` 的窗侧件）。
  * 外部基线（99.492%/37,312 页等）只作 E4 带外参照回显，**永不作验收线**
    （INV-07 §4.4 失败模式）；验收线用我方签收条件（≥99% 逻辑池等）。
  * 负表#15：bundle 未带 streaming 口径声明 → 判读直接 FAIL（不可豁免）。

输入工件 schema（judge bundle，五段；见 SCHEMA_EXAMPLE）
  recall_records[]  每召回查询一条（stream/position/depth_target_pct/key_hash/
                    expected_sha256/got_sha256/backing_sample/session_epoch）
  barriers[]        四级屏障 × 四 rank 快照（phase/rank/kv_used/kv_total/swa_*/
                    full_*/evictable/protected/session_tail/slots_after_close/
                    request_rows_after_close）
  page_rebuilds[]   每 rank 页序列独立重建 manifest（page_seq_sha256/
                    pages_full/alias_conflicts/free_list_conflicts）
  attempt_notes{}   臂标签/streaming 口径声明/控制面指纹与运行模块指纹分列/
                    水位看护（F6 控制面变异可追溯门 + attempt-notes 留档门）
  boot_expectations{} C12 三期望断言（server_info vs expected: pool/MRR/ctx）
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "DEPTH_TARGETS",
    "N_STREAMS",
    "TOTAL_RECORDS",
    "SIGNING_POOL_PCT",
    "BACKING_SAMPLE_MAX_BYTES",
    "BARRIER_PHASES",
    "judge_bundle",
    "judge_recall_records",
    "judge_barriers",
    "judge_page_rebuilds",
    "judge_attempt_notes",
    "judge_boot_expectations",
    "record_key_sha256",
    "SCHEMA_EXAMPLE",
    "main",
]

DEPTH_TARGETS = (1, 10, 25, 50, 75, 90, 99)  # 每流七点（% 池深）
N_STREAMS = 16
TOTAL_RECORDS = N_STREAMS * len(DEPTH_TARGETS)  # 112
SIGNING_POOL_PCT = 99.0  # 我方满池签收条件（≥99% 逻辑池）；外部 99.492% 仅 E4 参照
BACKING_SAMPLE_MAX_BYTES = 1024
BARRIER_PHASES = ("before", "plateau", "after-query", "closed")

# 外部基线（E4 带外参照；EV-07-049 —— 只回显，永不进判定）
EXTERNAL_BASELINE_E4 = {
    "pool_pct": 99.492,
    "recall": "112/112",
    "cross_session_bleed": 0,
    "committed_full_tokens_per_rank": 9551288,
    "full_pages_per_rank": 37312,
    "positions_per_target": "16/16",
    "slots_after_close": 0,
}

SCHEMA_EXAMPLE = {
    "recall_records": [{
        "stream": 0, "position": 0, "depth_target_pct": 1,
        "key_hash": "k0", "expected_sha256": "<sha256>", "got_sha256": "<sha256>",
        "backing_sample": {"bytes": 1024, "sha256": "<sha256>"},
        "session_epoch": 1,
    }],
    "barriers": [{
        "phase": "plateau", "rank": 0, "kv_used": 9504000, "kv_total": 9600000,
        "swa_free": 3328, "swa_total": 125440, "evictable": 113920,
        "protected": 4096, "session_tail": 4096,
        "full_committed_tokens": 9551288, "full_pages": 37312,
        "slots_after_close": 0, "request_rows_after_close": 16,
    }],
    "page_rebuilds": [{
        "rank": 0, "page_seq_sha256": "<sha256>", "pages_full": 37312,
        "alias_conflicts": 0, "free_list_conflicts": 0, "sha_match_expected": True,
    }],
    "attempt_notes": {
        "arm_tag": "F6A-example",
        "streaming_caliber": "streaming-session off（负表#15 口径声明：本窗未启用 streaming-session）",
        "control_plane_fingerprints": {"ignite.sh": "md5:..."},
        "run_module_fingerprints": {"scheduler.py": "md5:..."},
        "water_watch": {"min_memavailable_mb": 4096, "stops": 0},
    },
    "boot_expectations": {
        "server_info": {"max_total_num_tokens": 9600000, "max_running_requests": 16,
                        "context_length": 600000},
        "expected": {"max_total_num_tokens": 9600000, "max_running_requests": 16,
                     "context_length": 600000},
    },
}


def record_key_sha256(key_hash: str, value: bytes) -> str:
    """采集侧记录值哈希的规范形（SHA-256；判读侧只比对，不采样真值）。"""
    h = hashlib.sha256()
    h.update(str(key_hash).encode("utf-8"))
    h.update(b"\x00")
    h.update(value)
    return h.hexdigest()


def _as_sha(v: Any) -> Optional[str]:
    if isinstance(v, str) and len(v) == 64 and all(
        c in "0123456789abcdef" for c in v.lower()
    ):
        return v.lower()
    return None


def judge_recall_records(
    records: Sequence[Dict[str, Any]],
    total_expected: int = TOTAL_RECORDS,
    streams: int = N_STREAMS,
    depth_targets: Sequence[int] = DEPTH_TARGETS,
) -> List[Tuple[str, bool, str]]:
    """召回记录判读：112/112、各位置 16/16、0 串值、backing 抽样 ≤1024B。"""
    out: List[Tuple[str, bool, str]] = []
    n = len(records)
    out.append(("recall.count==%d" % total_expected, n == total_expected,
                f"got {n}"))
    # 每目标深度 16/16
    by_target: Dict[int, List[Dict[str, Any]]] = {}
    for r in records:
        t = r.get("depth_target_pct")
        if isinstance(t, int):
            by_target.setdefault(t, []).append(r)
    for t in depth_targets:
        got = len(by_target.get(t, []))
        out.append((f"recall.position16/16@depth{t}", got == streams,
                    f"got {got}/{streams}"))
    # 召回命中 / 串值 / 普通未中
    misses = 0
    bleed = 0
    oversize = 0
    bad_schema = 0
    # 串值检测索引：同 key_hash 不同 session_epoch 的 expected 集合
    key_expected_by_epoch: Dict[str, Dict[int, str]] = {}
    for r in records:
        k = r.get("key_hash")
        ep = r.get("session_epoch")
        exp = _as_sha(r.get("expected_sha256"))
        if k is None or exp is None or not isinstance(ep, int):
            bad_schema += 1
            continue
        key_expected_by_epoch.setdefault(str(k), {}).setdefault(ep, exp)
    for r in records:
        k = r.get("key_hash")
        ep = r.get("session_epoch")
        exp = _as_sha(r.get("expected_sha256"))
        got = _as_sha(r.get("got_sha256"))
        bs = r.get("backing_sample")
        if isinstance(bs, dict):
            b = bs.get("bytes")
            if isinstance(b, int) and b > BACKING_SAMPLE_MAX_BYTES:
                oversize += 1
        if k is None or exp is None or got is None:
            continue
        if got == exp:
            continue
        # 同 key 其它 session 的 expected == got ⇒ 跨会话串值
        others = key_expected_by_epoch.get(str(k), {})
        if any(e == got for e_ep, e in others.items() if e_ep != ep):
            bleed += 1
        else:
            misses += 1
    out.append(("recall.hits", misses == 0, f"{n - misses - bleed}/{n} 命中"))
    out.append(("recall.zero-cross-session-bleed", bleed == 0, f"bleed={bleed}"))
    out.append(("recall.backing-sample<=1024B", oversize == 0,
                f"oversize={oversize}"))
    out.append(("recall.schema-wellformed", bad_schema == 0,
                f"bad={bad_schema}"))
    return out


def judge_barriers(
    snaps: Sequence[Dict[str, Any]],
    ranks: Sequence[int] = (0, 1, 2, 3),
    phases: Sequence[str] = BARRIER_PHASES,
    pool_pct: float = SIGNING_POOL_PCT,
) -> List[Tuple[str, bool, str]]:
    """四级屏障判读：相×秩全覆盖、plateau 满池签收 ≥99%、SWA/FULL 分池字段在、
    closed 相 slot=0/request-row 归核。"""
    out: List[Tuple[str, bool, str]] = []
    seen = {(s.get("phase"), s.get("rank")) for s in snaps if isinstance(s, dict)}
    missing = [(p, r) for p in phases for r in ranks if (p, r) not in seen]
    out.append(("barrier.4phase-x-4rank", not missing,
                f"missing={missing[:8]}" if missing else "complete"))
    plateau_pool = []
    swa_fields = 0
    for s in snaps:
        if not isinstance(s, dict) or s.get("phase") != "plateau":
            continue
        used, total = s.get("kv_used"), s.get("kv_total")
        if isinstance(used, int) and isinstance(total, int) and total > 0:
            plateau_pool.append(used / total * 100.0)
        if all(k in s for k in ("swa_free", "swa_total", "evictable",
                                "protected", "session_tail", "full_pages")):
            swa_fields += 1
    min_pool = min(plateau_pool) if plateau_pool else None
    out.append(("barrier.plateau-pool>=%.1f%%" % pool_pct,
                min_pool is not None and min_pool >= pool_pct,
                f"min={min_pool}"))
    out.append(("barrier.swa-full-split-fields", swa_fields == len(ranks),
                f"ranks-with-fields={swa_fields}/{len(ranks)}（低 free≠耗尽："
                "evictable/protected/session_tail 分列）"))
    closed = [s for s in snaps if isinstance(s, dict)
              and s.get("phase") == "closed"]
    slots_ok = all(s.get("slots_after_close") == 0 for s in closed) and bool(closed)
    rows = [s.get("request_rows_after_close") for s in closed
            if isinstance(s, dict)]
    rows_ok = bool(rows) and all(isinstance(v, int) and v > 0 for v in rows)
    out.append(("barrier.closed-slot-zero", slots_ok,
                f"slots={[s.get('slots_after_close') for s in closed]}"))
    out.append(("barrier.closed-request-rows-restored", rows_ok,
                f"rows={rows}"))
    return out


def judge_page_rebuilds(
    manifests: Sequence[Dict[str, Any]],
    ranks: Sequence[int] = (0, 1, 2, 3),
) -> List[Tuple[str, bool, str]]:
    """页重建判读：每 rank 独立重建、SHA 对拍命中、别名/free-list 冲突=0、
    committed FULL 页数跨秩一致。"""
    out: List[Tuple[str, bool, str]] = []
    by_rank = {m.get("rank"): m for m in manifests
               if isinstance(m, dict) and _as_sha(str(m.get("page_seq_sha256")))}
    out.append(("pages.per-rank-rebuild",
                sorted(by_rank) == sorted(ranks),
                f"ranks={sorted(by_rank)}"))
    sha_ok = all(m.get("sha_match_expected") is True for m in by_rank.values())
    out.append(("pages.sha-match", sha_ok and bool(by_rank), "SHA 对拍"))
    alias = sum(int(m.get("alias_conflicts", 0) or 0) for m in by_rank.values())
    fl = sum(int(m.get("free_list_conflicts", 0) or 0) for m in by_rank.values())
    out.append(("pages.zero-alias-conflicts", alias == 0, f"alias={alias}"))
    out.append(("pages.zero-free-list-conflicts", fl == 0, f"free_list={fl}"))
    counts = [m.get("pages_full") for m in by_rank.values()]
    consistent = len(set(counts)) <= 1 and bool(counts)
    out.append(("pages.full-pages-cross-rank-equal", consistent,
                f"pages_full={counts}"))
    return out


def judge_attempt_notes(notes: Any) -> List[Tuple[str, bool, str]]:
    """F6 留档门：attempt-notes 完整 + streaming 口径声明（负表#15）+ 指纹分列。"""
    out: List[Tuple[str, bool, str]] = []
    ok = isinstance(notes, dict)
    out.append(("notes.present", ok, type(notes).__name__))
    if not ok:
        return out
    decl = notes.get("streaming_caliber")
    has_decl = isinstance(decl, str) and len(decl.strip()) >= 8
    out.append(("notes.streaming-caliber-declared(负表#15)", has_decl,
                str(decl)[:60]))
    cpf = notes.get("control_plane_fingerprints")
    rmf = notes.get("run_module_fingerprints")
    sep = isinstance(cpf, dict) and isinstance(rmf, dict) and bool(cpf) and bool(rmf)
    out.append(("notes.control-vs-run-fingerprint-split", sep,
                "控制面/运行模块指纹分列" if sep else "缺列"))
    ww = notes.get("water_watch") or {}
    ww_ok = isinstance(ww, dict) and "min_memavailable_mb" in ww \
        and ww.get("stops") == 0
    out.append(("notes.water-watch-no-stop", ww_ok, str(ww)[:60]))
    out.append(("notes.arm-tag", isinstance(notes.get("arm_tag"), str)
                and bool(notes.get("arm_tag")), str(notes.get("arm_tag"))))
    return out


def judge_boot_expectations(
    be: Any,
    expected: Optional[Dict[str, int]] = None,
) -> List[Tuple[str, bool, str]]:
    """C12 三期望断言：boot server_info 的 pool/MRR/ctx 与期望逐值相等。"""
    out: List[Tuple[str, bool, str]] = []
    if not isinstance(be, dict) or not isinstance(be.get("server_info"), dict):
        out.append(("boot.server_info-present", False, type(be).__name__))
        return out
    si = be["server_info"]
    exp = expected or be.get("expected") or {}
    checks = (
        ("boot.pool==expected(max_total_num_tokens)", "max_total_num_tokens"),
        ("boot.mrr==expected(max_running_requests)", "max_running_requests"),
        ("boot.ctx==expected(context_length)", "context_length"),
    )
    for label, key in checks:
        want, got = exp.get(key), si.get(key)
        out.append((label, want is not None and got == want,
                    f"got={got} want={want}"))
    return out


def judge_bundle(bundle: Dict[str, Any]) -> Tuple[bool, List[Tuple[str, bool, str]], Dict[str, Any]]:
    """F6-A/C11/C12 判读编排（全绿才算过；单项明细全量返回）。"""
    if not isinstance(bundle, dict):
        return False, [("bundle.present", False, type(bundle).__name__)], {}
    items: List[Tuple[str, bool, str]] = []
    items += judge_recall_records(bundle.get("recall_records") or [])
    items += judge_barriers(bundle.get("barriers") or [])
    items += judge_page_rebuilds(bundle.get("page_rebuilds") or [])
    items += judge_attempt_notes(bundle.get("attempt_notes"))
    if bundle.get("boot_expectations") is not None:
        items += judge_boot_expectations(bundle["boot_expectations"])
    ok = all(v for _, v, _ in items)
    summary = {
        "total_checks": len(items),
        "failed": [k for k, v, _ in items if not v],
        "external_baseline_e4_reference_only": EXTERNAL_BASELINE_E4,
        "signing_pool_pct": SIGNING_POOL_PCT,
    }
    return ok, items, summary


def _fmt_report(ok: bool, items: List[Tuple[str, bool, str]], summary: Dict[str, Any]) -> str:
    lines = [f"== KV_RECALL_C11 判读 {'GREEN' if ok else 'RED'} =="]
    for k, v, d in items:
        lines.append(f"[{'PASS' if v else 'FAIL'}] {k}  ({d})")
    lines.append(f"summary: {json.dumps(summary, ensure_ascii=False)}")
    return "\n".join(lines)


def _selfcheck() -> int:
    """--selfcheck：合成全绿走查 + 六类负对照必须各自被检出。"""
    checks = 0

    def need(cond: bool, what: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            raise SystemExit(f"SELFCHK KV_RECALL_C11 FAIL: {what}")

    def make_bundle(with_miss=False, with_bleed=False, drop_phase=None,
                    sha_break=False, no_streaming_decl=False, low_pool=False):
        ex = SCHEMA_EXAMPLE
        records = []
        for s in range(16):
            for i, t in enumerate((1, 10, 25, 50, 75, 90, 99)):
                exp = record_key_sha256(f"k{s}-{i}", f"value-{s}-{i}".encode())
                got = exp
                if with_miss and s == 0 and t == 50:
                    got = record_key_sha256("zzz", b"absent")
                records.append({
                    "stream": s, "position": i, "depth_target_pct": t,
                    "key_hash": f"k{s}-{i}", "expected_sha256": exp,
                    "got_sha256": got,
                    "backing_sample": {"bytes": 1024, "sha256": exp},
                    "session_epoch": 1,
                })
        if with_bleed:
            # 同 key 跨 session epoch 异值：epoch2 的召回拿回 epoch1 的值 = 串值。
            # 占用 stream1 的 depth90/depth99 两槽，总数保持 112。
            key = "ksplit"
            exp1 = record_key_sha256(key, b"session-one-value")
            exp2 = record_key_sha256(key, b"session-two-value")
            records = [r for r in records
                       if not (r["stream"] == 1 and r["depth_target_pct"] in (90, 99))]
            records.append({
                "stream": 1, "position": 5, "depth_target_pct": 90,
                "key_hash": key, "expected_sha256": exp1,
                "got_sha256": exp1,
                "backing_sample": {"bytes": 1024, "sha256": exp1},
                "session_epoch": 1,
            })
            records.append({
                "stream": 1, "position": 6, "depth_target_pct": 99,
                "key_hash": key, "expected_sha256": exp2,
                "got_sha256": exp1,
                "backing_sample": {"bytes": 1024, "sha256": exp1},
                "session_epoch": 2,
            })
        barriers = []
        for phase in ("before", "plateau", "after-query", "closed"):
            if drop_phase == phase:
                continue
            for rank in range(4):
                used = 9504000 if not low_pool else 8640000
                barriers.append({
                    "phase": phase, "rank": rank, "kv_used": used,
                    "kv_total": 9600000, "swa_free": 3328,
                    "swa_total": 125440, "evictable": 113920,
                    "protected": 4096, "session_tail": 4096,
                    "full_committed_tokens": 9551288, "full_pages": 37312,
                    "slots_after_close": 0 if phase == "closed" else None,
                    "request_rows_after_close": 16,
                })
        rebuilds = []
        for rank in range(4):
            sha = record_key_sha256("page-seq", f"rank{rank}".encode())
            if sha_break and rank == 2:
                sha = record_key_sha256("page-seq", b"drift")
            rebuilds.append({
                "rank": rank, "page_seq_sha256": sha, "pages_full": 37312,
                "alias_conflicts": 0, "free_list_conflicts": 0,
                "sha_match_expected": not (sha_break and rank == 2),
            })
        notes = dict(ex["attempt_notes"])
        if no_streaming_decl:
            notes.pop("streaming_caliber")
        return {
            "recall_records": records, "barriers": barriers,
            "page_rebuilds": rebuilds, "attempt_notes": notes,
            "boot_expectations": ex["boot_expectations"],
        }

    # 1) 全绿走查。
    ok, items, summary = judge_bundle(make_bundle())
    need(ok, f"全绿走查（failed={summary['failed']}）")
    need(summary["total_checks"] >= 20, "判读项覆盖")

    # 2) 负对照：召回未中。
    ok2, items2, _ = judge_bundle(make_bundle(with_miss=True))
    need(not ok2 and any(k == "recall.hits" for k, v, _ in items2 if not v),
         "召回未中检出")

    # 3) 负对照：跨会话串值。
    ok3, items3, _ = judge_bundle(make_bundle(with_bleed=True))
    need(not ok3 and any("bleed" in k for k, v, _ in items3 if not v),
         "串值检出")

    # 4) 负对照：屏障相缺失。
    ok4, items4, _ = judge_bundle(make_bundle(drop_phase="plateau"))
    need(not ok4 and any(k.startswith("barrier.4phase") for k, v, _ in items4
                         if not v), "屏障缺失检出")
    ok4b, items4b, _ = judge_bundle(make_bundle(low_pool=True))
    need(not ok4b and any("pool>=" in k for k, v, _ in items4b if not v),
         "满池签收未达检出")

    # 5) 负对照：页重建 SHA 漂移。
    ok5, items5, _ = judge_bundle(make_bundle(sha_break=True))
    need(not ok5 and any("sha" in k for k, v, _ in items5 if not v),
         "SHA 漂移检出")

    # 6) 负对照：streaming 口径声明缺失（负表#15 硬停）。
    ok6, items6, _ = judge_bundle(make_bundle(no_streaming_decl=True))
    need(not ok6 and any("streaming-caliber" in k for k, v, _ in items6 if not v),
         "负表#15 检出")

    # 7) 外部基线只回显不判定。
    need("external_baseline_e4_reference_only" in summary, "E4 参照回显")

    print(f"SELFCHK KV_RECALL_C11 ok checks={checks}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selfcheck":
        return _selfcheck()
    if argv and argv[0] == "judge" and len(argv) >= 2:
        with open(argv[1], encoding="utf-8") as f:
            bundle = json.load(f)
        ok, items, summary = judge_bundle(bundle)
        print(_fmt_report(ok, items, summary))
        return 0 if ok else 1
    print(__doc__.splitlines()[0])
    print("usage: kv_recall_c11.py --selfcheck | judge <bundle.json>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
