"""Admission gate: request-level T×L budget rejection (INCIDENT-20260930-15:17).

Second-incident verdict refinement: the 13:26/15:17 OOMs were BOTH triggered by
long-prompt prefills whose engram row-read storm (order-rank structural misses)
consumes host memory far ahead of any scoring-time gate. The sparse_wire budget
gate only guards the DECODE scoring choke point; prefill scoring is tile-budgeted
(2GiB) and never trips it. A hand-rolled client bypassing tool-side gates has no
engine-side defense — this adapter is that defense.

Mechanism: wrap TokenizerManager._validate_one_request (battle-tested ValueError
→ HTTP 400 path) and reject any request whose input token count exceeds
    DSV41_TL_BUDGET_ELEMS // DSV41_TL_ROW_CHUNK      (default 2.0e8 // 4096 = 48828)
— the same law the client-side needle gate and the decode scoring gate use.

Always-on per the 2026-09-30 user ruling; DSV41_TL_BUDGET_ELEMS=off/0 disarms
(shared key with sparse_wire so one switch governs the whole T×L defense line).
When the sparse indexer lands (G3-K), raise the budget deliberately.
"""
import logging
import os

_logger = logging.getLogger("admission_gate")

BUDGET_ENV = "DSV41_TL_BUDGET_ELEMS"
ROW_CHUNK_ENV = "DSV41_TL_ROW_CHUNK"
DEFAULT_BUDGET = 2 * 10**8
DEFAULT_ROW_CHUNK = 4096


def _budget():
    raw = os.environ.get(BUDGET_ENV)
    if raw is None:
        return DEFAULT_BUDGET
    raw = raw.strip().lower()
    if raw in ("off", "0", "", "false"):
        return None
    try:
        return int(float(raw))
    except ValueError:
        return DEFAULT_BUDGET


def _row_chunk():
    try:
        rc = int(os.environ.get(ROW_CHUNK_ENV, "").strip())
        return rc if rc > 0 else DEFAULT_ROW_CHUNK
    except ValueError:
        return DEFAULT_ROW_CHUNK


def install(module) -> bool:
    cls = getattr(module, "TokenizerManager", None)
    orig = getattr(cls, "_validate_one_request", None) if cls else None
    if orig is None:
        _logger.warning("admission_gate: TokenizerManager._validate_one_request "
                        "anchor missing; no admission gate")
        return False

    if getattr(orig, "_admission_gate_wrapped", False):
        return False

    def _validate_one_request(self, obj, input_ids):
        budget = _budget()
        if budget is not None and input_ids is not None:
            limit = budget // _row_chunk()
            n = len(input_ids)
            if n > limit:
                raise ValueError(
                    f"Request rejected by dense T×L admission gate: input "
                    f"{n} tokens > limit {limit} (budget {budget:,} elems ÷ "
                    f"row-chunk {_row_chunk()}). Long-context requires the "
                    f"sparse indexer; raise DSV41_TL_BUDGET_ELEMS only with "
                    f"explicit approval."
                )
        return orig(self, obj, input_ids)

    _validate_one_request._admission_gate_wrapped = True
    cls._validate_one_request = _validate_one_request
    _logger.info("admission_gate: armed at "
                 "TokenizerManager._validate_one_request "
                 "(default %s elems ÷ %s rows; %s=off disarms)",
                 format(DEFAULT_BUDGET, ","), DEFAULT_ROW_CHUNK, BUDGET_ENV)
    return True


def summary() -> str:
    b = _budget()
    return (f"budget={'off' if b is None else format(b, ',')} "
            f"row_chunk={_row_chunk()} "
            f"limit={'off' if b is None else format(b // _row_chunk(), ',')} tok")
