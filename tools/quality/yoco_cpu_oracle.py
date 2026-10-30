#!/usr/bin/env python3
"""YoCo L1 style CPU oracle for DSV4 SWA / sparse-prefill metadata (T33-04, W0).

Cross-checks ("对拍") the production overlay metadata derivations against an
independent analytic reference, YoCo L1 style (SWA pivots / visible keys /
store slots / compressed key ranges). Pure CPU: no weights, no GPU, no
containers, no network. Single run well under 60 s.

对拍双方
  ARM-I (implementation) -- production overlay code, executed on CPU:
    * deploy/overlay/v4vl-79cafec0/dsv4_visible_window.py
        compute_visible_window_overrides / image_span_aligned_extend_end /
        image_span_cut_point / has_visible_window_span -- called directly
        (module is torch-free by design, dsv4_visible_window.py:14-15).
    * deploy/overlay/{v4vl-79cafec0,o12c1-prod}/dsv4_sparse_prefill_utils.py
        build_swa_token_ids / combine_topk_swa_indices /
        SparsePrefillChunkCache.build -- the torch-level wrapper logic
        (asserts, widths, buffer allocation, eff_window, workspace bases,
        cumsums) is the REAL production code; only the two triton kernels are
        emulated 1:1 on CPU (see _emu_* below, transcribed verbatim from
        deploy/overlay/*/dsv4_sparse_prefill_kernels.py with file:line cites).
        Triton kernels cannot launch without a GPU; the emulation is the only
        way to exercise the wrappers CPU-only. Emulation fidelity is itself
        covered by --selfcheck mutations M1/M4/M5 (which must turn the oracle
        red, proving the comparison path has teeth).

  ARM-R (reference) -- independent analytic derivation, written from the
    documented specifications only (set arithmetic over per-position visible
    domains), never calling the implementation:
    * visible domain: window(i) = [max(0, i-(W-1)), i] causal; inside an image
      span [max(0, i-(W-1)-max(0,left_i-(W-1))), span_end)
      (dsv4_visible_window.py:8-12 docstring).
    * request SWA union (pivots / keep-tokens): [max(0, seq_len-extend-W+1),
      seq_len), length min(seq_len, extend+W-1) (dsv4_sparse_prefill_utils.py
      build_swa_token_ids docstring, o12c1:225-239 / v4vl:233-247).
      YoCo L1 formula mapping: lo = max(pos-window+1, spec.N-keep_tokens, 0)
      (DeepInfer yoco_equiv.py:116-119 via INV-03 §2.2); here keep_tokens ~
      extend+W-1 at request granularity, pos-window+1 at query granularity,
      and the span left-shift max(0,left-(W-1)) is the VL extension.
    * store slots: pos -> req_to_token[req_pool_idx, pos] -> full_to_swa[id]
      (kernel comments dsv4_sparse_prefill_kernels.py:30-36).
    * compressed key ranges: topk_len = min((pos+1)//COMPRESS_RATIO, topk);
      topk rows rebased by +compressed_base[r], invalid entries stay -1;
      SWA segment rebased swa_base[r] + (pos - gather_start) + j; row length
      topk_len + swa_len; width padded to a multiple of 128
      (SPARSE_PREFILL_TOPK_ALIGNMENT, dsv4_sparse_prefill_utils.py:45-47).

Production constants used as cited contract inputs (not re-derived):
    SWA_WINDOW = 128        deepseek_v4_backend.py:141 (v4vl) / :138 (o12c1)
    page_size  = 256        deepseek_v4_backend.py:1128 (v4vl)
    chunked prefill 4096    deploy/bin/r3-boot-arm.sh SERVER_ARGS
    DIM_NOPE=448/DIM_ROPE=64  sglang kernels dequant_k_cache.py:19-20

Usage:
    python3 tools/quality/yoco_cpu_oracle.py                 # run all fixtures
    python3 tools/quality/yoco_cpu_oracle.py --filter vw     # substring filter
    python3 tools/quality/yoco_cpu_oracle.py --selfcheck     # + mutation tests
    python3 tools/quality/yoco_cpu_oracle.py --json out.json # machine summary

Exit code 0 iff every check passes (and, under --selfcheck, every mutation is
caught). Evidence level: E1 (亲读 file:line + 亲跑只读命令; kernels emulated).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "yoco_l1"

OVERLAY_V4VL = REPO_ROOT / "deploy" / "overlay" / "v4vl-79cafec0"
OVERLAY_O12C1 = REPO_ROOT / "deploy" / "overlay" / "o12c1-prod"

# Engine contract constants (cited, not derived):
SPARSE_PREFILL_TOPK_ALIGNMENT = 128  # dsv4_sparse_prefill_utils.py:47
DIM_NOPE, DIM_ROPE = 448, 64         # sglang dequant_k_cache.py:19-20


# --------------------------------------------------------------------------
# Results bookkeeping
# --------------------------------------------------------------------------

class Results:
    def __init__(self):
        self.checks = []  # (case_id, name, ok, detail)

    def check(self, case_id, name, ok, detail=""):
        self.checks.append((case_id, name, bool(ok), detail))
        return bool(ok)

    @property
    def n_pass(self):
        return sum(1 for c in self.checks if c[2])

    @property
    def n_fail(self):
        return sum(1 for c in self.checks if not c[2])

    def failures(self):
        return [c for c in self.checks if not c[2]]


# --------------------------------------------------------------------------
# Module loading (stub sglang deps; overlay utils imports only 3 sglang names)
# --------------------------------------------------------------------------

def _install_sglang_stubs() -> None:
    """Inject minimal sglang.* modules so the overlay utils import without the
    full sglang dependency chain (FL6 stub pattern, tests/fl6-recall). The
    three imported names carry the real engine semantics, cited:
      ceil_align(x, y) = ceil_div(x, y) * y   sglang/srt/utils/common.py:4302-4304
      DIM_NOPE/DIM_ROPE = 448/64              kernels .../dequant_k_cache.py:19-20
    """
    def new_mod(name):
        m = ModuleType(name)
        sys.modules[name] = m
        return m

    for name in (
        "sglang",
        "sglang.kernels",
        "sglang.kernels.ops",
        "sglang.kernels.ops.attention",
        "sglang.kernels.ops.attention.dsv4",
        "sglang.srt",
    ):
        new_mod(name)

    utils = new_mod("sglang.srt.utils")
    utils.ceil_align = lambda x, y: ((x + y - 1) // y) * y  # common.py:4302-4304

    deq = new_mod("sglang.kernels.ops.attention.dsv4.dequant_k_cache")
    deq.DIM_NOPE, deq.DIM_ROPE = DIM_NOPE, DIM_ROPE

    spk = new_mod("sglang.kernels.ops.attention.dsv4.sparse_prefill_kernels")
    spk._build_swa_token_ids_kernel = None      # replaced after utils import
    spk._combine_topk_swa_indices_kernel = None


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Triton kernel emulations -- verbatim transcription of the overlay kernels.
# dsv4_sparse_prefill_kernels.py (v4vl 118 lines / o12c1 107 lines).
# --------------------------------------------------------------------------

class _GridKernel:
    """triton kernel objects are subscripted kernel[grid](args...)."""

    def __init__(self, fn):
        self._fn = fn

    def __getitem__(self, grid):
        def launch(*args, **kwargs):
            return self._fn(grid, *args, **kwargs)

        return launch


def _emu_build_swa_token_ids(grid, out, first_pos, gather_lens, offsets,
                             req_pool_indices, req_to_token,
                             req_to_token_stride, full_to_swa):
    """Transcription of _build_swa_token_ids_kernel (both overlay trees
    identical): dsv4_sparse_prefill_kernels.py:11-36."""
    r2t_flat = req_to_token.reshape(-1)  # triton pointer arithmetic analog
    for batch_idx in range(grid[0]):
        fp = int(first_pos[batch_idx])
        gl = int(gather_lens[batch_idx])
        out_off = int(offsets[batch_idx])
        rpi = int(req_pool_indices[batch_idx])
        for i in range(gl):
            pos = fp + i
            full_id = int(r2t_flat[rpi * req_to_token_stride + pos])
            out[out_off + i] = int(full_to_swa[full_id])


def _emu_combine_v4vl(grid, combined, c_stride, lens, topk, t_stride,
                      qsl, qpos, seq_lens, gather_lens, cbase, swabase,
                      win_starts, win_lens, *, top_k, COMPRESS_RATIO,
                      WINDOW_SIZE, SWA_BLOCK, PADDED_TOP_K, HAS_SWA_WIN):
    """Transcription of _combine_topk_swa_indices_kernel, v4vl-79cafec0
    dsv4_sparse_prefill_kernels.py:40-118 (HAS_SWA_WIN branch :84-91)."""
    base = int(qsl[0])
    combined_flat = combined.reshape(-1)
    topk_flat = topk.reshape(-1)
    for batch_idx in range(grid[0]):
        query_start = int(qsl[batch_idx]) - base
        query_end = int(qsl[batch_idx + 1]) - base
        seq_len = int(seq_lens[batch_idx])
        gather_len = int(gather_lens[batch_idx])
        compressed_base = int(cbase[batch_idx])
        swa_base = int(swabase[batch_idx])
        gather_start = seq_len - gather_len
        for token_idx in range(query_start, query_end):
            pos = int(qpos[token_idx])
            topk_len = min((pos + 1) // COMPRESS_RATIO, top_k)
            if HAS_SWA_WIN:
                swa_len = int(win_lens[token_idx])
                swa_start = int(win_starts[token_idx])
            else:
                swa_len = min(pos + 1, WINDOW_SIZE)
                swa_start = pos - swa_len + 1
            assert topk_len <= PADDED_TOP_K and swa_len <= SWA_BLOCK
            row = token_idx * int(c_stride)
            trow = token_idx * int(t_stride)
            for j in range(topk_len):
                v = int(topk_flat[trow + j])
                combined_flat[row + j] = v + compressed_base if v >= 0 else -1
            for j in range(swa_len):
                combined_flat[row + topk_len + j] = (
                    swa_base + j + swa_start - gather_start
                )
            lens[token_idx] = topk_len + swa_len


def _emu_combine_o12c1(grid, combined, c_stride, lens, topk, t_stride,
                       qsl, qpos, seq_lens, gather_lens, cbase, swabase,
                       *, top_k, COMPRESS_RATIO, WINDOW_SIZE, PADDED_TOP_K):
    """Transcription of _combine_topk_swa_indices_kernel, o12c1-prod
    dsv4_sparse_prefill_kernels.py:40-106 (causal-only arm)."""
    base = int(qsl[0])
    combined_flat = combined.reshape(-1)
    topk_flat = topk.reshape(-1)
    for batch_idx in range(grid[0]):
        query_start = int(qsl[batch_idx]) - base
        query_end = int(qsl[batch_idx + 1]) - base
        seq_len = int(seq_lens[batch_idx])
        gather_len = int(gather_lens[batch_idx])
        compressed_base = int(cbase[batch_idx])
        swa_base = int(swabase[batch_idx])
        gather_start = seq_len - gather_len
        for token_idx in range(query_start, query_end):
            pos = int(qpos[token_idx])
            topk_len = min((pos + 1) // COMPRESS_RATIO, top_k)
            swa_len = min(pos + 1, WINDOW_SIZE)
            assert topk_len <= PADDED_TOP_K and swa_len <= WINDOW_SIZE
            row = token_idx * int(c_stride)
            trow = token_idx * int(t_stride)
            for j in range(topk_len):
                v = int(topk_flat[trow + j])
                combined_flat[row + j] = v + compressed_base if v >= 0 else -1
            for j in range(swa_len):
                combined_flat[row + topk_len + j] = (
                    swa_base + j + pos - swa_len + 1 - gather_start
                )
            lens[token_idx] = topk_len + swa_len


# Mutation hooks for --selfcheck (None = faithful transcription).
MUTATION = {"name": None}


class _EmuBuild:
    def __getitem__(self, grid):
        def launch(*args, **kwargs):
            (out, first_pos, gather_lens, offsets, rpi, r2t, stride,
             f2s) = args
            if MUTATION["name"] == "M2_pivot_off_by_one":
                # SWA pivot off by one: gather one extra position per request
                # (may overrun the buffer -- that counts as caught too).
                gather_lens = gather_lens + 1
            if MUTATION["name"] == "M3_slot_identity":
                # Bypass full_to_swa: identity slot map.
                r2t_flat = r2t.reshape(-1)
                for b in range(grid[0]):
                    fp = int(first_pos[b])
                    gl = int(gather_lens[b])
                    off = int(offsets[b])
                    r = int(rpi[b])
                    for i in range(gl):
                        out[off + i] = int(r2t_flat[r * int(stride) + fp + i])
                return
            return _emu_build_swa_token_ids(
                grid, out, first_pos, gather_lens, offsets, rpi, r2t,
                int(stride), f2s)
        return launch


class _EmuCombineV4VL:
    def __getitem__(self, grid):
        def launch(*args, **kwargs):
            if MUTATION["name"] == "M1_window_off_by_one":
                qpos = args[6]
                args = list(args)
                args[6] = (qpos - 1).to(qpos.dtype)
                args = tuple(args)
            if MUTATION["name"] == "M4_topk_floor":
                kwargs = dict(kwargs)
                kwargs["COMPRESS_RATIO"] = kwargs["COMPRESS_RATIO"] + 1
            if MUTATION["name"] == "M5_no_compressed_base":
                args = list(args)
                args[9] = torch_zeros_like(args[9])
                args = tuple(args)
            return _emu_combine_v4vl(grid, *args, **kwargs)
        return launch


class _EmuCombineO12C1:
    def __getitem__(self, grid):
        def launch(*args, **kwargs):
            if MUTATION["name"] == "M1_window_off_by_one":
                qpos = args[6]
                args = list(args)
                args[6] = (qpos - 1).to(qpos.dtype)
                args = tuple(args)
            if MUTATION["name"] == "M4_topk_floor":
                kwargs = dict(kwargs)
                kwargs["COMPRESS_RATIO"] = kwargs["COMPRESS_RATIO"] + 1
            if MUTATION["name"] == "M5_no_compressed_base":
                args = list(args)
                args[9] = torch_zeros_like(args[9])
                args = tuple(args)
            return _emu_combine_o12c1(grid, *args, **kwargs)
        return launch


def torch_zeros_like(t):
    import torch
    return torch.zeros_like(t)


# --------------------------------------------------------------------------
# Load the three production modules
# --------------------------------------------------------------------------

def load_production_modules():
    import torch  # noqa: F401  (needed by sparse utils)

    _install_sglang_stubs()
    vw = _load_module(OVERLAY_V4VL / "dsv4_visible_window.py",
                      "oracle_overlay_visible_window_v4vl")
    sp_v4vl = _load_module(
        OVERLAY_V4VL / "dsv4_sparse_prefill_utils.py",
        "oracle_overlay_sparse_utils_v4vl")
    sp_o12 = _load_module(
        OVERLAY_O12C1 / "dsv4_sparse_prefill_utils.py",
        "oracle_overlay_sparse_utils_o12c1")
    # Swap the triton kernel symbols for CPU emulations. The wrapper bodies
    # (asserts / widths / buffers / cumsums / bases) stay 100% production.
    sp_v4vl._combine_topk_swa_indices_kernel = _EmuCombineV4VL()
    sp_v4vl._build_swa_token_ids_kernel = _EmuBuild()
    sp_o12._combine_topk_swa_indices_kernel = _EmuCombineO12C1()
    sp_o12._build_swa_token_ids_kernel = _EmuBuild()
    return vw, sp_v4vl, sp_o12


# --------------------------------------------------------------------------
# Synthetic multimodal stubs (duck-typed to iter_image_spans' requirements,
# dsv4_visible_window.py:24-40: mm_items[].is_image()/offsets/
# model_specific_data{"perm","types"})
# --------------------------------------------------------------------------

class _MMItem:
    def __init__(self, offsets, is_img=True):
        self.offsets = [tuple(o) for o in offsets]
        self._is_img = is_img
        self.model_specific_data = {"perm": [0], "types": ["image"]}

    def is_image(self):
        return self._is_img


class _MMInput:
    def __init__(self, items):
        self.mm_items = list(items)


def build_mm_input(req):
    items = []
    if req.get("image_offsets"):
        items.append(_MMItem(req["image_offsets"]))
    for off in req.get("non_image_offsets", []):
        items.append(_MMItem([off], is_img=False))
    return _MMInput(items) if items else None


# --------------------------------------------------------------------------
# ARM-R: independent analytic reference (no calls into ARM-I modules)
# --------------------------------------------------------------------------

def raw_spans(req):
    """Raw image blocks [start, end) from fixture offsets. iter_image_spans
    (dsv4_visible_window.py:39-40) yields (start, end+1); the +1 is the
    compression padding row."""
    return [(int(s), int(e) + 1) for s, e in req.get("image_offsets", [])]


def effective_span(s, e_plus1):
    """_iter_visible_window_spans (dsv4_visible_window.py:59-60): padding is
    causal, IMAGE_START lands at position 3 mod 4 -> span start shifted to
    start + 3 - start%4."""
    return s + 3 - s % 4, e_plus1


def ref_visible_domain(pos, W, eff_spans):
    """YoCo L1 style analytic visible domain of query `pos`.

    Causal:   [max(0, pos-(W-1)), pos]            (docstring :11-12)
    In span:  [max(0, pos-(W-1)-max(0,left-(W-1))), span_end)  (docstring :8)
    """
    for s, e in eff_spans:
        if s <= pos < e:
            left = pos - s
            lo = max(0, pos - (W - 1) - max(0, left - (W - 1)))
            return lo, e  # half-open [lo, span_end)
    lo = max(0, pos - (W - 1))
    return lo, pos + 1  # half-open [lo, pos]


def ref_visible_windows(req, W, padded_num_tokens):
    """Reference for compute_visible_window_overrides: per-token (start, len)
    lists plus padding rows (0, 1) (dsv4_visible_window.py:90-92, 119-122)."""
    prefix, extend = int(req["prefix_len"]), int(req["extend_len"])
    eff = [effective_span(s, e) for s, e in raw_spans(req)]
    starts, lens = [], []
    for pos in range(prefix, prefix + extend):
        lo, hi = ref_visible_domain(pos, W, eff)
        starts.append(lo)
        lens.append(hi - lo)
    pad = max(0, padded_num_tokens - len(starts))
    starts += [0] * pad
    lens += [1] * pad
    return starts, lens


def ref_swa_union(req, W):
    """Request-level SWA union via set arithmetic over per-query visible
    domains (keep-tokens analog; must equal the contiguous pivot range)."""
    prefix, extend = int(req["prefix_len"]), int(req["extend_len"])
    seq = int(req["seq_len"])
    eff = [effective_span(s, e) for s, e in raw_spans(req)]
    union = set()
    for pos in range(prefix, prefix + extend):
        lo, hi = ref_visible_domain(pos, W, eff)
        union.update(range(lo, hi))
    gather_len = min(seq, extend + W - 1)
    pivot = seq - gather_len
    contiguous = set(range(pivot, seq))
    return union, pivot, gather_len, contiguous


def ref_slot_map(pool, req):
    """Fixture-defined synthetic pool mapping (INPUT metadata shared by both
    arms): full_id(pos) via req_to_token row formula; swa_id(full_id) via
    full_to_swa vector formula. Injective on the used domain."""
    base = int(pool["row_base"])
    stride = int(pool["row_stride"])
    full_pool = int(pool["full_pool"])
    M, Q = int(pool["swa_mult"]), int(pool["swa_mod"])
    rpi = int(req["req_pool_index"])

    def full_id(pos):
        return (base + rpi * 1013 + pos * stride) % full_pool

    def swa_id(fid):
        return (fid * M) % Q

    return full_id, swa_id


def ref_combined_row(pos, topk_row, topk, ratio, compressed_base, swa_base,
                     gather_start, swa_lo, swa_hi):
    """Reference combined row (compressed key range + SWA segment).

    topk_len  = min((pos+1)//ratio, topk)                 (kernel :83)
    topk seg  = topk_row[j] >= 0 ? topk_row[j]+base : -1  (kernel :96-106)
    swa seg   = swa_base + (swa_lo..swa_hi) - gather_start (kernel :108-116)
    row len   = topk_len + swa_len
    """
    topk_len = min((pos + 1) // ratio, topk)
    swa_len = swa_hi - swa_lo
    row = {}
    for j in range(topk_len):
        v = topk_row[j]
        row[j] = v + compressed_base if v >= 0 else -1
    for j in range(swa_len):
        row[topk_len + j] = swa_base + (swa_lo + j) - gather_start
    return row, topk_len + swa_len, topk_len


def ref_combined_width(topk, eff_window):
    """Width = ceil_align(topk + eff_window, 128) (utils:45-47,108-111)."""
    need = topk + eff_window
    return ((need + SPARSE_PREFILL_TOPK_ALIGNMENT - 1)
            // SPARSE_PREFILL_TOPK_ALIGNMENT) * SPARSE_PREFILL_TOPK_ALIGNMENT


def fixture_topk_matrix(num_rows, width, c_max, seed=7):
    """Synthetic per-query compressed top-k (INPUT metadata): valid entries
    in [0, c_max), -1 sprinkled inside the valid prefix (docstring
    utils:133-135 'Invalid entries within topk_len must be -1')."""
    matrix = []
    for r in range(num_rows):
        row = []
        for j in range(width):
            h = (seed + r * 131 + j * 17) % 1009
            if h % 11 == 0:
                row.append(-1)
            else:
                row.append(h % max(c_max, 1))
        matrix.append(row)
    return matrix


# --------------------------------------------------------------------------
# Case runners
# --------------------------------------------------------------------------

def run_visible_window_case(vw, case, res):
    import torch  # noqa: F401

    cid = case["case_id"]
    W = int(case["swa_window"])
    reqs = case["requests"]
    mm_inputs = [build_mm_input(r) for r in reqs]
    prefix = [int(r["prefix_len"]) for r in reqs]
    extend = [int(r["extend_len"]) for r in reqs]
    padded = int(case.get("padded_num_tokens",
                          sum(prefix) + sum(extend)))

    expect = case.get("expect", "match")
    if expect == "value_error":
        try:
            vw.compute_visible_window_overrides(
                mm_inputs=mm_inputs, extend_prefix_lens=prefix,
                extend_seq_lens=extend, swa_window=W,
                padded_num_tokens=padded)
            res.check(cid, "partial_span_raises", False,
                      "expected ValueError for span crossing the prefill "
                      "range, none raised")
        except ValueError as e:
            res.check(cid, "partial_span_raises",
                      "crosses" in str(e), f"ValueError: {e}")
        return

    if expect == "none":
        out = vw.compute_visible_window_overrides(
            mm_inputs=mm_inputs, extend_prefix_lens=prefix,
            extend_seq_lens=extend, swa_window=W, padded_num_tokens=padded)
        res.check(cid, "text_chunk_returns_none", out is None, f"out={out!r}")
        # Chunk-boundary helpers still work on raw spans of such requests.
        helper_chunk_boundary_checks(vw, case, res)
        return

    out = vw.compute_visible_window_overrides(
        mm_inputs=mm_inputs, extend_prefix_lens=prefix,
        extend_seq_lens=extend, swa_window=W, padded_num_tokens=padded)
    res.check(cid, "overrides_not_none", out is not None)
    if out is None:
        return
    got_starts, got_lens = out

    # Reference arm + cross-check per request.
    ref_starts, ref_lens = [], []
    for r in reqs:
        s, l = ref_visible_windows(r, W, 0)
        ref_starts += s
        ref_lens += l
    pad = padded - len(ref_starts)
    ref_starts += [0] * max(0, pad)
    ref_lens += [1] * max(0, pad)

    res.check(cid, "visible_starts_match", got_starts == ref_starts,
              first_diff(got_starts, ref_starts, "starts"))
    res.check(cid, "visible_lens_match", got_lens == ref_lens,
              first_diff(got_lens, ref_lens, "lens"))
    res.check(cid, "total_len_is_padded", len(got_starts) == padded,
              f"len={len(got_starts)} padded={padded}")

    # Padding rows carry (0, 1) (dsv4_visible_window.py:90-92,119-122).
    live = sum(extend)
    if padded > live:
        res.check(cid, "padding_rows_0_1",
                  got_starts[live:] == [0] * (padded - live)
                  and got_lens[live:] == [1] * (padded - live))

    # Window matrix invariants (independent of either arm).
    ok_dom, ok_nonneg = True, True
    for r in reqs:
        eff = [effective_span(s, e) for s, e in raw_spans(r)]
        for pos in range(int(r["prefix_len"]),
                         int(r["prefix_len"]) + int(r["extend_len"])):
            lo, hi = ref_visible_domain(pos, W, eff)
            if not (lo <= pos < hi):
                ok_dom = False
            if lo < 0:
                ok_nonneg = False
    res.check(cid, "visible_domain_contains_query", ok_dom)
    res.check(cid, "visible_start_nonneg", ok_nonneg)

    helper_chunk_boundary_checks(vw, case, res)


def helper_chunk_boundary_checks(vw, case, res):
    """image_span_aligned_extend_end / image_span_cut_point vs reference
    (dsv4_visible_window.py:126-141)."""
    cid = case["case_id"]
    for i, req in enumerate(case["requests"]):
        mm = build_mm_input(req)
        spans = raw_spans(req)
        for x in req.get("boundary_probes", []):
            x = int(x)
            expected = x
            for s, e in spans:
                if s < expected < e:
                    expected = s
            got = vw.image_span_aligned_extend_end(mm, x)
            res.check(cid, f"aligned_extend_end[r{i}]({x})",
                      got == expected, f"got={got} want={expected}")
            cut_exp = expected if expected < x else None
            cut_got = vw.image_span_cut_point(mm, x)
            res.check(cid, f"cut_point[r{i}]({x})", cut_got == cut_exp,
                      f"got={cut_got} want={cut_exp}")


def run_has_visible_span_case(vw, case, res):
    cid = case["case_id"]
    mm_inputs = [build_mm_input(r) for r in case["requests"]]
    prefix = [int(r["prefix_len"]) for r in case["requests"]]
    extend = [int(r["extend_len"]) for r in case["requests"]]
    got = vw.has_visible_window_span(mm_inputs, prefix, extend)
    want = False
    for r in case["requests"]:
        p, e = int(r["prefix_len"]), int(r["extend_len"])
        for s, eend in raw_spans(r):
            if p <= s and eend <= p + e:
                want = True
    res.check(cid, "has_visible_window_span", got == want,
              f"got={got} want={want}")


def build_pool_tensors(case):
    """Synthetic req_to_token / full_to_swa tensors from fixture metadata."""
    import torch
    pool = int(case["pool"]["full_pool"])
    max_seq = max(int(r["seq_len"]) for r in case["requests"])
    n_rows = max(int(r["req_pool_index"]) for r in case["requests"]) + 1
    req_to_token = torch.zeros((n_rows, max_seq), dtype=torch.int32)
    for r in range(n_rows):
        for pos in range(max_seq):
            req_to_token[r, pos] = (
                case["pool"]["row_base"] + r * 1013
                + pos * case["pool"]["row_stride"]) % pool
    f2s = torch.zeros(pool, dtype=torch.int64)
    for fid in range(pool):
        f2s[fid] = (fid * case["pool"]["swa_mult"]) % case["pool"]["swa_mod"]
    return req_to_token, f2s


def run_swa_store_case(sp, case, res, tree):
    """build_swa_token_ids: SWA pivots (keep-tokens), store slots, offsets."""
    import torch
    cid = f"{case['case_id']}[{tree}]"
    W = int(case["swa_window"])
    reqs = case["requests"]
    seq = torch.tensor([int(r["seq_len"]) for r in reqs], dtype=torch.int32)
    ext = torch.tensor([int(r["extend_len"]) for r in reqs],
                       dtype=torch.int32)
    rpi = torch.tensor([int(r["req_pool_index"]) for r in reqs],
                       dtype=torch.int32)
    req_to_token, f2s = build_pool_tensors(case)
    total_ref = sum(min(int(r["seq_len"]),
                        int(r["extend_len"]) + W - 1) for r in reqs)

    token_ids, first_pos, gather_lens, offsets = sp.build_swa_token_ids(
        seq_lens=seq, extend_seq_lens=ext, req_pool_indices=rpi,
        req_to_token=req_to_token, full_to_swa=f2s, swa_window=W,
        total_swa=total_ref)

    got_ids = token_ids.tolist()
    got_first = first_pos.tolist()
    got_lens = gather_lens.tolist()
    got_off = offsets.tolist()

    want_first, want_lens, want_ids = [], [], []
    union_ok = True
    for r in reqs:
        union, pivot, glen, contiguous = ref_swa_union(r, W)
        if union != contiguous:
            union_ok = False
        want_first.append(pivot)
        want_lens.append(glen)
        fm, sm = ref_slot_map(case["pool"], r)
        for i in range(glen):
            want_ids.append(sm(fm(pivot + i)))
        # Keep-tokens boundaries (YoCo lo-form floor) on the reference side.
        assert pivot == max(0, int(r["seq_len"]) - (int(r["extend_len"])
                                                    + W - 1))

    res.check(cid, "swa_pivot_match", got_first == want_first,
              first_diff(got_first, want_first, "first_pos"))
    res.check(cid, "swa_gather_len_match", got_lens == want_lens,
              first_diff(got_lens, want_lens, "gather_lens"))
    res.check(cid, "store_slots_match", got_ids == want_ids,
              first_diff(got_ids, want_ids, "token_ids"))
    res.check(cid, "union_is_contiguous_pivot_range", union_ok)
    res.check(cid, "offsets_cumsum_closure",
              got_off[0] == 0 and got_off[-1] == total_ref
              and all(got_off[i + 1] - got_off[i] == got_lens[i]
                      for i in range(len(reqs)))
              and len(got_off) == len(reqs) + 1,
              f"offsets={got_off}")
    res.check(cid, "total_swa_equals_sum",
              token_ids.shape[0] == total_ref)


def run_combine_case(sp, case, res, tree, with_swa_win):
    """combine_topk_swa_indices: compressed key ranges + SWA segment +
    128-alignment + lens, on both overlay trees."""
    import torch
    cid = f"{case['case_id']}[{tree}]"
    W = int(case["swa_window"])
    reqs = case["requests"]
    ratio = int(case["combine"]["compress_ratio"])
    topk = int(case["combine"]["topk"])
    width_in = int(case["combine"].get("topk_width", max(topk, 1)))

    seq = torch.tensor([int(r["seq_len"]) for r in reqs], dtype=torch.int32)
    ext = torch.tensor([int(r["extend_len"]) for r in reqs],
                       dtype=torch.int32)
    qlens = ext.clone()
    qsl = torch.zeros(len(reqs) + 1, dtype=torch.int32)
    qsl[1:] = torch.cumsum(qlens, dim=0)
    if case["combine"].get("qsl_base_offset"):
        qsl += int(case["combine"]["qsl_base_offset"])  # cross-chunk offset
    num_tokens = int(ext.sum().item())
    qpos = torch.zeros(num_tokens, dtype=torch.int32)
    i = 0
    for r in reqs:
        for pos in range(int(r["prefix_len"]),
                         int(r["prefix_len"]) + int(r["extend_len"])):
            qpos[i] = pos
            i += 1

    gather_lens = torch.minimum(seq, ext + (W - 1)).to(torch.int32)
    c_max = max(int(seq.max().item()) // ratio, 1)
    compressed_base = (torch.arange(len(reqs), dtype=torch.int32) * c_max)
    swa_off = torch.zeros(len(reqs) + 1, dtype=torch.int32)
    swa_off[1:] = torch.cumsum(gather_lens, dim=0).to(torch.int32)
    swa_base = (len(reqs) * c_max + swa_off[:-1]).to(torch.int32)

    topk_mat = torch.tensor(
        fixture_topk_matrix(num_tokens, width_in, c_max,
                            seed=int(case["combine"].get("seed", 7))),
        dtype=torch.int32)

    kw = {}
    if with_swa_win:
        ws, wl = [], []
        for r in reqs:
            eff = [effective_span(s, e) for s, e in raw_spans(r)]
            for pos in range(int(r["prefix_len"]),
                             int(r["prefix_len"]) + int(r["extend_len"])):
                lo, hi = ref_visible_domain(pos, W, eff)
                ws.append(lo)
                wl.append(hi - lo)
        kw["swa_win_starts"] = torch.tensor(ws, dtype=torch.int32)
        kw["swa_win_lens"] = torch.tensor(wl, dtype=torch.int32)
        kw["swa_win_max_len"] = max(wl)

    combined, lens = sp.combine_topk_swa_indices(
        topk_indices=topk_mat, query_start_loc=qsl, query_pos=qpos,
        seq_lens=seq, gather_lens=gather_lens,
        compressed_base=compressed_base, swa_base=swa_base,
        window_size=W, compress_ratio=ratio, topk=topk, **kw)

    # ---- reference arm -------------------------------------------------
    eff_window = W
    if with_swa_win:
        eff_window = max(W, kw["swa_win_max_len"])
    want_width = ref_combined_width(topk, eff_window)
    got = combined.tolist()
    got_lens = lens.tolist()
    topk_rows = topk_mat.tolist()

    ok_shape = (combined.shape == (num_tokens, want_width))
    ok_align = want_width % SPARSE_PREFILL_TOPK_ALIGNMENT == 0
    ok_rows, ok_lens, ok_pad = True, True, True
    ok_bounds = True
    workspace_size = len(reqs) * c_max + int(gather_lens.sum().item())
    i = 0
    for ri, r in enumerate(reqs):
        gather_start = int(r["seq_len"]) - int(gather_lens[ri])
        eff = [effective_span(s, e) for s, e in raw_spans(r)]
        for pos in range(int(r["prefix_len"]),
                         int(r["prefix_len"]) + int(r["extend_len"])):
            if with_swa_win:
                lo, hi = ref_visible_domain(pos, W, eff)
            else:
                lo = max(0, pos - (W - 1))
                hi = pos + 1
            row, rowlen, _ = ref_combined_row(
                pos, topk_rows[i], topk, ratio, int(compressed_base[ri]),
                int(swa_base[ri]), gather_start, lo, hi)
            want_row = [-1] * want_width
            for j, v in row.items():
                want_row[j] = v
            if got[i] != want_row:
                ok_rows = False
            if got_lens[i] != rowlen:
                ok_lens = False
            for j in range(rowlen, want_width):
                if got[i][j] != -1:
                    ok_pad = False
            # -1 inside the topk prefix is the invalid-entry sentinel
            # (utils:133-135 'Invalid entries within topk_len must be -1');
            # every other index must land in the flat workspace.
            for v in got[i][:rowlen]:
                if v == -1:
                    continue
                if v < 0 or v >= workspace_size:
                    ok_bounds = False
            i += 1

    res.check(cid, "combined_shape_and_width", ok_shape and ok_align,
              f"shape={tuple(combined.shape)} want=({num_tokens},"
              f"{want_width}) align128={ok_align}")
    res.check(cid, "compressed_and_swa_rows_match", ok_rows)
    res.check(cid, "combined_lens_match", ok_lens)
    res.check(cid, "minus1_padding_outside_prefix", ok_pad)
    res.check(cid, "indices_within_workspace", ok_bounds,
              f"workspace={workspace_size}")


def run_chunkcache_case(sp_v4vl, sp_o12, case, res):
    """Full SparsePrefillChunkCache.build (production builder) + c0
    precompute, both overlay trees; cross-tree causal equality."""
    import torch
    W = int(case["swa_window"])
    reqs = case["requests"]
    seq = torch.tensor([int(r["seq_len"]) for r in reqs], dtype=torch.int32)
    ext = torch.tensor([int(r["extend_len"]) for r in reqs],
                       dtype=torch.int32)
    rpi = torch.tensor([int(r["req_pool_index"]) for r in reqs],
                       dtype=torch.int32)
    req_to_token, f2s = build_pool_tensors(case)
    num_qo = int(ext.sum().item())
    qpos = torch.zeros(num_qo, dtype=torch.int32)
    i = 0
    for r in reqs:
        for pos in range(int(r["prefix_len"]),
                         int(r["prefix_len"]) + int(r["extend_len"])):
            qpos[i] = pos
            i += 1
    total_swa = sum(min(int(r["seq_len"]),
                        int(r["extend_len"]) + W - 1) for r in reqs)
    max_seq = int(seq.max().item())

    for sp, tree in ((sp_v4vl, "v4vl"), (sp_o12, "o12c1")):
        cid = f"{case['case_id']}[{tree}]"
        cache = sp.SparsePrefillChunkCache.build(
            seq_lens=seq, extend_seq_lens=ext, query_lens=ext.clone(),
            query_pos=qpos, req_pool_indices=rpi,
            req_to_token=req_to_token, full_to_swa=f2s,
            swa_window_size=W, swa_page_size=int(case["swa_page_size"]),
            num_qo_tokens=num_qo, max_seq_len=max_seq,
            total_swa=total_swa)

        # query_start_loc cumsum (real builder code).
        res.check(cid, "query_start_loc_cumsum",
                  cache.query_start_loc.tolist()
                  == [0] + list(torch.cumsum(ext, 0).tolist()))
        # SWA union pivots / slots vs reference.
        want_first = [r["seq_len"] - min(r["seq_len"],
                                         r["extend_len"] + W - 1)
                      for r in reqs]
        res.check(cid, "swa_first_pos", cache.swa_first_pos.tolist()
                  == want_first)
        want_ids = []
        for r in reqs:
            fm, sm = ref_slot_map(case["pool"], r)
            pivot = r["seq_len"] - min(r["seq_len"],
                                       r["extend_len"] + W - 1)
            for k in range(min(r["seq_len"], r["extend_len"] + W - 1)):
                want_ids.append(sm(fm(pivot + k)))
        res.check(cid, "swa_token_ids", cache.swa_token_ids.tolist()
                  == want_ids)

        # c0 precompute: topk=0 -> compressed range empty, row = SWA only
        # (utils:418-437). eff window = W (no visible overrides here).
        width = ref_combined_width(0, W)
        ok_c0 = (cache.c0_combined_indices.shape
                 == (num_qo, width))
        got = cache.c0_combined_indices.tolist()
        got_lens = cache.c0_combined_lens.tolist()
        i = 0
        for ri, r in enumerate(reqs):
            gather_start = r["seq_len"] - int(cache.swa_gather_lens[ri])
            sb = int(cache.swa_offsets[ri])
            for pos in range(r["prefix_len"],
                             r["prefix_len"] + r["extend_len"]):
                swa_len = min(pos + 1, W)
                want_row = [-1] * width
                for j in range(swa_len):
                    want_row[j] = sb + (pos - swa_len + 1 + j) - gather_start
                if got[i] != want_row or got_lens[i] != swa_len:
                    ok_c0 = False
                i += 1
        res.check(cid, "c0_swa_only_precompute", ok_c0,
                  f"width={width}")

    # Cross-tree: causal combine outputs must agree between overlay trees.
    a = sp_v4vl.SparsePrefillChunkCache.build(
        seq_lens=seq.clone(), extend_seq_lens=ext.clone(),
        query_lens=ext.clone(), query_pos=qpos.clone(),
        req_pool_indices=rpi.clone(), req_to_token=req_to_token.clone(),
        full_to_swa=f2s.clone(), swa_window_size=W,
        swa_page_size=int(case["swa_page_size"]), num_qo_tokens=num_qo,
        max_seq_len=max_seq, total_swa=total_swa)
    b = sp_o12.SparsePrefillChunkCache.build(
        seq_lens=seq.clone(), extend_seq_lens=ext.clone(),
        query_lens=ext.clone(), query_pos=qpos.clone(),
        req_pool_indices=rpi.clone(), req_to_token=req_to_token.clone(),
        full_to_swa=f2s.clone(), swa_window_size=W,
        swa_page_size=int(case["swa_page_size"]), num_qo_tokens=num_qo,
        max_seq_len=max_seq, total_swa=total_swa)
    res.check(case["case_id"], "cross_tree_causal_c0_equal",
              a.c0_combined_indices.tolist()
              == b.c0_combined_indices.tolist()
              and a.c0_combined_lens.tolist() == b.c0_combined_lens.tolist(),
              "v4vl vs o12c1 drift")


def run_coverage_invariant_case(case, res, tree):
    """SparsePrefillChunkCache docstring invariant (v4vl utils:340-344):
    every visible window of a fully-contained span lies inside the union
    gather [seq_len-extend-(W-1), seq_len)."""
    cid = f"{case['case_id']}[{tree}]"
    W = int(case["swa_window"])
    ok = True
    for r in case["requests"]:
        union, pivot, glen, _ = ref_swa_union(r, W)
        eff = [effective_span(s, e) for s, e in raw_spans(r)]
        for pos in range(int(r["prefix_len"]),
                         int(r["prefix_len"]) + int(r["extend_len"])):
            lo, hi = ref_visible_domain(pos, W, eff)
            if any(p not in union for p in range(lo, hi)):
                ok = False
    res.check(cid, "visible_subset_of_union_gather", ok)


def first_diff(a, b, label):
    if a == b:
        return ""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"{label}[{i}]: got={x} want={y}"
    return f"{label}: length {len(a)} vs {len(b)}"


# --------------------------------------------------------------------------
# Fixture dispatch
# --------------------------------------------------------------------------

def run_case(vw, sp_v4vl, sp_o12, case, res):
    kind = case["kind"]
    if kind == "visible_window":
        run_visible_window_case(vw, case, res)
    elif kind == "has_visible_span":
        run_has_visible_span_case(vw, case, res)
    elif kind == "swa_store":
        for sp, tree in ((sp_v4vl, "v4vl"), (sp_o12, "o12c1")):
            run_swa_store_case(sp, case, res, tree)
    elif kind == "combine":
        run_combine_case(sp_v4vl, case, res, "v4vl",
                         with_swa_win=bool(case["combine"].get("swa_win")))
        run_combine_case(sp_o12, case, res, "o12c1", with_swa_win=False)
        run_coverage_invariant_case(case, res, "v4vl")
    elif kind == "chunkcache":
        run_chunkcache_case(sp_v4vl, sp_o12, case, res)
    else:
        raise ValueError(f"unknown case kind {kind!r}")


def run_suite(vw, sp_v4vl, sp_o12, fixtures, res, filt=None):
    for fx in sorted(fixtures):
        if filt and filt not in fx.name:
            continue
        case = json.loads(fx.read_text())
        run_case(vw, sp_v4vl, sp_o12, case, res)


# --------------------------------------------------------------------------
# Selfcheck: mutation sensitivity (each mutation must be CAUGHT by the suite)
# --------------------------------------------------------------------------

MUTATIONS = [
    ("M1_window_off_by_one",
     "emu combine shifts query pos by -1 (window drops newest token)"),
    ("M2_pivot_off_by_one",
     "emu build gather_len +1 (SWA pivot off by one)"),
    ("M3_slot_identity",
     "emu build bypasses full_to_swa (identity slot map)"),
    ("M4_topk_floor", "emu combine COMPRESS_RATIO+1 (topk_len floor wrong)"),
    ("M5_no_compressed_base",
     "emu combine zeroes compressed_base (rebase lost)"),
    ("M6_ref_window_uses_W",
     "reference visible-window formula uses W instead of W-1 "
     "(mutates ARM-R; the REAL production function must then mismatch)"),
    ("M7_ref_width_64",
     "reference combined width aligned to 64 instead of 128"),
]


def run_selfcheck(vw, sp_v4vl, sp_o12, fixtures):
    print("== selfcheck: baseline suite must be green ==")
    base = Results()
    run_suite(vw, sp_v4vl, sp_o12, fixtures, base)
    print(f"baseline: {base.n_pass} passed, {base.n_fail} failed")
    if base.n_fail:
        for c in base.failures():
            print(f"  FAIL {c[0]}/{c[1]} {c[3]}")
        return False, base, []

    print("== selfcheck: mutations must each be caught ==")
    mut_results = []
    all_caught = True
    for name, desc in MUTATIONS:
        MUTATION["name"] = name
        r = Results()
        err = None
        try:
            if name == "M6_ref_window_uses_W":
                r = run_m6(vw, sp_v4vl, sp_o12, fixtures)
            elif name == "M7_ref_width_64":
                r = run_m7(vw, sp_v4vl, sp_o12, fixtures)
            else:
                run_suite(vw, sp_v4vl, sp_o12, fixtures, r)
        except Exception as e:  # a crash under mutation is also a red
            err = f"{type(e).__name__}: {e}"
        finally:
            MUTATION["name"] = None
        caught = r.n_fail > 0 or err is not None
        n_red = r.n_fail if err is None else -1
        all_caught = all_caught and caught
        mut_results.append((name, caught, n_red, desc))
        note = f" ({err})" if err else ""
        print(f"  {name}: {'CAUGHT' if caught else 'MISSED'} "
              f"({n_red} failing checks){note} -- {desc}")
    return all_caught, base, mut_results


def run_m6(vw, sp_v4vl, sp_o12, fixtures):
    """M6: reference visible-window formula uses W instead of W-1. The real
    production compute_visible_window_overrides must then mismatch."""
    global ref_visible_domain
    res = Results()
    orig = ref_visible_domain

    def mutated(pos, W, eff_spans):
        for s, e in eff_spans:
            if s <= pos < e:
                left = pos - s
                lo = max(0, pos - W - max(0, left - W))
                return lo, e
        lo = max(0, pos - W)
        return lo, pos + 1

    try:
        ref_visible_domain = mutated
        run_suite(vw, sp_v4vl, sp_o12, fixtures, res)
    finally:
        ref_visible_domain = orig
    return res


def run_m7(vw, sp_v4vl, sp_o12, fixtures):
    """M7: reference width alignment 64 instead of the 128 contract."""
    global ref_combined_width
    res = Results()
    orig = ref_combined_width

    def mutated(topk, eff_window):
        need = topk + eff_window
        return ((need + 63) // 64) * 64

    try:
        ref_combined_width = mutated
        run_suite(vw, sp_v4vl, sp_o12, fixtures, res)
    finally:
        ref_combined_width = orig
    return res


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selfcheck", action="store_true",
                    help="also run mutation-sensitivity selfcheck")
    ap.add_argument("--filter", default=None,
                    help="only run fixtures whose filename contains SUBSTR")
    ap.add_argument("--fixtures", default=str(FIXTURE_DIR),
                    help="fixture directory (default: tools/quality/fixtures"
                         "/yoco_l1)")
    ap.add_argument("--json", default=None, dest="json_out",
                    help="write machine-readable summary to PATH")
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    fixtures = sorted(Path(args.fixtures).glob("*.json"))
    if not fixtures:
        print(f"no fixtures found in {args.fixtures}", file=sys.stderr)
        return 2

    vw, sp_v4vl, sp_o12 = load_production_modules()

    # Contract constants imported from the real production modules (E1).
    assert sp_v4vl.SPARSE_PREFILL_TOPK_ALIGNMENT == 128, "utils:47 drifted"
    assert sp_v4vl.WORKSPACE_DIM == DIM_NOPE + DIM_ROPE == 512, \
        "dequant_k_cache DIM_NOPE/DIM_ROPE drifted"

    res = Results()
    run_suite(vw, sp_v4vl, sp_o12, fixtures, res, filt=args.filter)

    ok = res.n_fail == 0
    print(f"cases: {len(fixtures)} fixture files, "
          f"{res.n_pass} checks passed, {res.n_fail} failed")
    for cid, name, _, detail in res.failures():
        print(f"  FAIL {cid}/{name} {detail}")

    mut = []
    if args.selfcheck:
        caught, base, mut = run_selfcheck(vw, sp_v4vl, sp_o12, fixtures)
        ok = ok and caught and base.n_fail == 0

    elapsed = time.perf_counter() - t0
    print(f"elapsed: {elapsed:.2f}s (CPU-only; budget <60s)")

    if args.json_out:
        payload = {
            "tool": "yoco_cpu_oracle.py",
            "task": "T33-04 CPU oracle (YoCo L1 style)",
            "fixtures": [f.name for f in fixtures],
            "checks_total": len(res.checks),
            "checks_passed": res.n_pass,
            "checks_failed": res.n_fail,
            "mutations": [
                {"name": n, "caught": c, "failing_checks": f, "desc": d}
                for n, c, f, d in mut
            ],
            "elapsed_s": round(elapsed, 3),
            "status": "PASS" if ok else "FAIL",
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2))
        print(f"json summary -> {args.json_out}")

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
