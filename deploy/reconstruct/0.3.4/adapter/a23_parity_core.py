"""A23 prefill-AR parity core: tolerance-band math and probe report types.

DESIGN.md §4 (bit-equality strategy) made precise and CPU-testable:

* B-face (deterministic bit-equal form): a RoCEnante all-reduce output must be
  bitwise equal to a canonical-order reference (fixed rank order, fp32
  accumulation, ONE final rounding back to bf16).  This module OWNS that
  reference so the fake tests and the cluster probe cannot drift apart.
* A-face (pre-registered tolerance band vs NCCL): a bf16 four-way sum under
  any NCCL order (<=3 intermediate roundings) differs from the fixed-order
  single-rounding form by at most MAX_ULP; the probe reports a histogram and
  the pre-registered pass/red lines decide.
* Three known-pathology tensors (DESIGN.md §4.3 reverse cases) prove the
  probe has discriminating power: it MUST see a nonzero diff on the order
  sensitive case, and MUST see zero on the order invariant cases.

Zero GPU, zero numpy, zero torch at import: the reference kernels here are
pure-Python bf16/fp32 emulations used for band verification; the cluster
probe (probe_a23_ar_parity.py) re-uses the same thresholds on real tensors.
"""
from __future__ import annotations

import math
import struct
from typing import Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Pre-registered band (DESIGN.md §4.3; frozen at design time, zero edits in
# window -- the win card cites these constants verbatim).
# ---------------------------------------------------------------------------

# bf16: 1 sign + 8 exponent + 7 stored mantissa bits -> ulp relative bound 2**-7.
BF16_MANTISSA_BITS = 7
FP32_MANTISSA_BITS = 23

# A-face pass line: median <= 1 ulp, max <= 3 ulp, P(diff > 2 ulp) == 0.
A_FACE_MAX_ULP = 3
A_FACE_MEDIAN_ULP = 1
A_FACE_TAIL_ULP = 2  # no element may exceed this many ulp (P(>2)==0).

# Byte band of the routing face (must mirror a23_prefill_ar.py defaults).
DEFAULT_PREFILL_MIN_BYTES = 8 * 1024 * 1024   # 8 MiB: 819-token boundary @5120x2B
DEFAULT_PREFILL_MAX_BYTES = 42 * 1024 * 1024  # 42 MiB: covers 4096x5120x2B=40MiB + margin


# ---------------------------------------------------------------------------
# IEEE754 bit helpers (pure python; doubles carry fp32 exactly, bf16 via bits)
# ---------------------------------------------------------------------------

def bf16_ulp_at(x: float) -> float:
    """ulp of a positive float in bf16 terms (2**-7 relative inside a binade)."""
    if x == 0.0:
        return 2.0 ** (-126 - BF16_MANTISSA_BITS)  # smallest subnormal-ish bound
    e = math.floor(math.log2(abs(x)))
    return 2.0 ** (e - BF16_MANTISSA_BITS)


def fp32_ulp_at(x: float) -> float:
    """ulp of a float in fp32 terms."""
    if x == 0.0:
        return 2.0 ** (-126 - FP32_MANTISSA_BITS)
    e = math.floor(math.log2(abs(x)))
    return 2.0 ** (e - FP32_MANTISSA_BITS)


def diff_in_ulps_bf16(a: float, b: float, scale: Optional[float] = None) -> int:
    """Distance between two bf16-representable values counted in bf16 ulps.

    ``scale`` is the ACCUMULATION scale (max |x_i| over the four rank inputs
    and |sum|).  The pre-registered bound is stated at that scale, not at the
    final magnitude: under catastrophic cancellation the final sum is tiny
    while the rounding error is set by the operand magnitudes -- normalizing
    at |sum| would make the bound unfalsifiable, which is exactly what a
    pre-registered band must not be.  Default (scale=None) falls back to
    max(|a|, |b|) for the order-invariant sanity cases.
    """
    if a == b:
        return 0
    base = scale if scale is not None else max(abs(a), abs(b))
    if base == 0.0:
        base = 1.0
    ulp = bf16_ulp_at(base)
    return int(round(abs(a - b) / ulp))


def accumulation_scale(values: Sequence[float], result: Optional[float] = None) -> float:
    """max(|x_i|, |result|): the magnitude that sets the rounding error floor."""
    scale = max((abs(v) for v in values), default=0.0)
    if result is not None:
        scale = max(scale, abs(result))
    return scale if scale > 0.0 else 1.0


# ---------------------------------------------------------------------------
# Canonical-order reference (B-face target): fixed rank order, fp32
# accumulate, ONE final rounding.  Pure-python emulation for band tests.
# ---------------------------------------------------------------------------

def canonical_sum_bf16_ref(values: Sequence[float]) -> float:
    """sum(values) in rank order with an fp32 accumulator, rounded once to bf16.

    This is the numeric form the b12x one-shot kernel claims (_oneshot_cute.py:
    fixed rank order, fp32 `_accumulate_words`, single `_store_accumulator`).
    """
    acc = 0.0
    for v in values:
        acc = _fp32_round(acc + v)
    return _bf16_round(acc)


def nccl_order_sum_bf16_ref(values: Sequence[float], start: int) -> float:
    """Ring-order sum: cyclic order starting at `start`, bf16 rounding per hop.

    Stands in for the NCCL ring shape (order moves with the owning rank,
    intermediate results round to bf16 between hops).  Only used to *derive and
    verify* the band on known inputs; the real NCCL behaviour is measured by
    the cluster probe, never assumed from this emulation.
    """
    n = len(values)
    acc = _bf16_round(values[start % n])
    for k in range(1, n):
        v = values[(start + k) % n]
        acc = _bf16_round(_fp32_round(acc + v))
    return acc


# --- rounding emulations (struct-based, exact) ------------------------------

def _fp32_round(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def _bf16_round(x: float) -> float:
    """Round-to-nearest-even a double to bf16 representable value (via fp32 bits)."""
    f = _fp32_round(x)
    bits = struct.unpack("I", struct.pack("f", f))[0]
    lsb = (bits >> 16) & 1
    rounded = (bits + 0x7FFF + lsb) & 0xFFFF0000
    # overflow to inf is not a band case we care to emulate precisely
    return struct.unpack("f", struct.pack("I", rounded))[0]


# ---------------------------------------------------------------------------
# Known pathologies (DESIGN.md §4.3 reverse cases -- probe discriminating power)
# ---------------------------------------------------------------------------

def pathology_order_sensitive() -> List[float]:
    """Case 1: [1.0, 2^-9, 2^-9, 2^-9] -- order difference lands in >=1 ulp.

    Canonical rank order (fp32 acc, one rounding) keeps the three tiny terms
    and lands 1 ulp above 1.0; a ring order that meets 1.0 first rounds the
    tinies away hop by hop and stays at 1.0 (see the fake tests, which pin the
    emulated values).  The probe MUST measure a nonzero diff here or it has no
    discriminating power (probe red, A22 assertion doctrine reverse case).
    """
    tiny = 2.0 ** -9
    return [1.0, tiny, tiny, tiny]


def pathology_order_invariant() -> List[float]:
    """Case 2: powers of two summing inside one binade -- any order is exact."""
    return [0.5, 0.25, 0.125, 0.0625]


def pathology_zero() -> List[float]:
    """Case 2b: identical values / zeros => strict bit equality under any order."""
    return [0.0, 0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# Probe report (shared by fake tests' verdict logic and the cluster probe)
# ---------------------------------------------------------------------------

class BandReport:
    """A-face histogram verdict container with the pre-registered lines built in."""

    def __init__(self, ulp_counts: Dict[int, int], label: str = ""):
        self.ulp_counts = ulp_counts
        self.label = label
        self.n = sum(ulp_counts.values())

    # -- pre-registered lines (DESIGN.md §4.3) --------------------------------

    @property
    def max_ulp(self) -> int:
        return max(self.ulp_counts) if self.ulp_counts else 0

    @property
    def median_ulp(self) -> int:
        if not self.n:
            return 0
        half, acc, ks = self.n / 2.0, 0, sorted(self.ulp_counts)
        for k in ks:
            acc += self.ulp_counts[k]
            if acc >= half:
                return k
        return ks[-1]

    @property
    def pass_line(self) -> bool:
        return (
            self.max_ulp <= A_FACE_MAX_ULP
            and self.median_ulp <= A_FACE_MEDIAN_ULP
            and all(k <= A_FACE_TAIL_ULP for k in self.ulp_counts)
        )

    @property
    def red_line(self) -> bool:
        return self.max_ulp > A_FACE_MAX_ULP

    def as_dict(self) -> Dict[str, object]:
        return {
            "label": self.label,
            "n": self.n,
            "ulp_histogram": {str(k): v for k, v in sorted(self.ulp_counts.items())},
            "max_ulp": self.max_ulp,
            "median_ulp": self.median_ulp,
            "pass_line": self.pass_line,
            "red_line": self.red_line,
        }


def band_report_from_diffs(diffs: Sequence[float], magnitudes: Sequence[float],
                           label: str = "") -> BandReport:
    """Build a BandReport from elementwise |a-b| against |sum| magnitudes."""
    counts: Dict[int, int] = {}
    for d, m in zip(diffs, magnitudes):
        ulp = bf16_ulp_at(m if m != 0 else 1.0)
        k = int(math.ceil(d / ulp - 1e-12)) if d > 0 else 0
        counts[k] = counts.get(k, 0) + 1
    return BandReport(counts, label)


# ---------------------------------------------------------------------------
# Band predicate for the routing face (mirror of a23_prefill_ar._in_prefill_band)
# ---------------------------------------------------------------------------

def in_prefill_band(nbytes: int,
                    min_bytes: int = DEFAULT_PREFILL_MIN_BYTES,
                    max_bytes: int = DEFAULT_PREFILL_MAX_BYTES) -> bool:
    """True when nbytes falls in the A23 prefill routing band.

    Group-consistency: depends only on the byte count (shape/dtype derived),
    never on pointers or rank -- every TP rank takes the same decision.
    """
    return min_bytes <= nbytes <= max_bytes and nbytes % 16 == 0


def decode_band_disjoint(decode_cap: int = 262144,
                         min_bytes: int = DEFAULT_PREFILL_MIN_BYTES) -> bool:
    """A22B decode face [0, 262144] must not overlap the prefill band."""
    return min_bytes > decode_cap


__all__ = [
    "A_FACE_MAX_ULP", "A_FACE_MEDIAN_ULP", "A_FACE_TAIL_ULP",
    "DEFAULT_PREFILL_MIN_BYTES", "DEFAULT_PREFILL_MAX_BYTES",
    "bf16_ulp_at", "fp32_ulp_at", "diff_in_ulps_bf16", "accumulation_scale",
    "canonical_sum_bf16_ref", "nccl_order_sum_bf16_ref",
    "pathology_order_sensitive", "pathology_order_invariant", "pathology_zero",
    "BandReport", "band_report_from_diffs",
    "in_prefill_band", "decode_band_disjoint",
]
