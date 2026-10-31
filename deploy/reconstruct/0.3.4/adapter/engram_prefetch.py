"""Engram rows fetched on a side stream as soon as the hash ids exist. Gate ``DSV41_ENGRAM_PREFETCH=1``.

Ported from knapcio's ``adapter/engram_prefetch.py`` (2026-09-24 snapshot), which measured 2.2-2.4 ms
of every 48 ms step as GPU idle in front of the two ``_engram_gather_kernel`` launches on real text
(1.0 ms on sparkDash prose), and a 51.7 -> 49.5 ms step on their fleet. The stall is NVMe latency:
the host callback that serves the lookup reads every cache miss (O_DIRECT 8 KB pread, ~200 us) while
the graph waits, once per Engram layer, and the following all-reduce then waits on the slowest rank.

The host work needs nothing but the ids: the hasher produces both Engram layers' ids at the start of
the forward, ~1 ms of GPU work before layer 1 needs them and ~15 ms before layer 14 does. So the ids
copy, the host lookup and the row copies are forked onto a side stream there, and the layer's gather
joins that stream. Inside a CUDA graph this is an ordinary fork/join branch carrying a host node; the
model, the hasher and the row store are unchanged, and the gather reads the same staging buffers.

Staging is built here with the same layout as ``engram_backend.owned`` -- pin-memory ids [cap] int64,
weights [cap, 256] uint8, scales [cap, 8] uint8, their device copies, and a sequential index -- and
the same ``Work`` record with the same ``slot_mod`` (stats v2 attributes hits per n-gram order; a
prefetched lookup that skipped it would report order 0). ``capacity`` is the next power of two above
the token count, exactly as the synchronous path sizes it, so a captured graph keeps its buffers.

``DSV41_ENGRAM_PREFETCH_CHECK=1`` runs the old synchronous lookup after every prefetched gather and
accumulates the number of gathers whose output differed (logged every DSV41_STATS_SECONDS, expected
0) -- the row store is on NVMe, so "the ids matched" is not the same as "the same bytes came back".
"""
import ctypes as C
import inspect
import logging
import os
import threading
import time

import torch

import engram_backend as eb

logger = logging.getLogger(__name__)
_EMBEDS = []
_state = {"disabled": False, "seen": False}


def enabled():
    return os.environ.get("DSV41_ENGRAM_PREFETCH", "0").strip().lower() not in ("", "0", "off", "false")


def _chunk_lifetime():
    """ENGRAM-GOV: expire row-cache entries at chunked-prefill chunk boundaries."""
    return os.environ.get("DSV41_ENGRAM_CHUNK_LIFETIME", "0").strip().lower() not in ("", "0", "off", "false")


def _warm_rows():
    """ENGRAM-GOV: rows to warm per prefill chunk (0 = off)."""
    try:
        return max(0, int(os.environ.get("DSV41_ENGRAM_PREFETCH_ROWS", "0")))
    except ValueError:
        return 0


def _chunk_min_tokens():
    """Forwards at least this many tokens count as prefill chunks for the
    lifetime/warm gates (decode batches are far below; default 1024 sits between
    cuda-graph decode bs and --chunked-prefill-size 4096)."""
    try:
        return int(os.environ.get("DSV41_ENGRAM_CHUNK_MIN_TOKENS", "1024"))
    except ValueError:
        return 1024


def _checking():
    return os.environ.get("DSV41_ENGRAM_PREFETCH_CHECK", "0").strip() == "1"


def _staging(self, indices, count):
    """The staging tuple ``engram_backend.owned`` would build for this shape.

    A mirror, deliberately: if that function's layout changes, this must change with it, so the
    sizes are restated here rather than imported -- and ``_assert_seams`` below refuses to arm
    when the synchronous path no longer has the shape this mirror was written against.
    """
    capacity = 1 << (count - 1).bit_length()
    key = (indices.device.index, capacity)
    if key not in self._staging:
        if torch.cuda.is_current_stream_capturing():
            raise RuntimeError(f"Engram staging {key} must be warmed before graph capture")
        ids = torch.empty(capacity, dtype=torch.int64, pin_memory=True)
        w = torch.empty((capacity, 256), dtype=torch.uint8, pin_memory=True)
        s = torch.empty((capacity, 8), dtype=torch.uint8, pin_memory=True)
        dw, ds = w.to(indices.device), s.to(indices.device)
        sequential = torch.arange(capacity, dtype=torch.int64, device=indices.device)
        self._staging[key] = (ids, w, s, dw, ds, sequential)
        # Boot-visible: under graph replay no Python here runs again, so the capture-time line is
        # the only proof that the fork/join and its host node are inside the captured graph.
        logger.warning(
            "DSV41 Engram prefetch staging %s: capacity=%s rows=%s capturing=%s",
            key, capacity, self.rows, torch.cuda.is_current_stream_capturing())
    ids, w, s, dw, ds, sequential = self._staging[key]
    work_key = (indices.device.index, count)
    if work_key not in self._works:
        self._works[work_key] = eb.Work(self._store, ids.data_ptr(), w.data_ptr(), s.data_ptr(), count)
    return ids, w, s, dw, ds, sequential, self._works[work_key]


def _slot_mod(indices):
    """Flatten width of the caller's [tokens, n_hash_cols] id tensor; 0 disables the split."""
    return (indices.numel() // indices.shape[0]) if indices.dim() > 1 and indices.shape[0] > 0 else 0


def _prefetch(self, indices):
    count = indices.numel()
    self._pending = None
    if not count or self.rows == 0:
        return
    if self._side is None:
        if torch.cuda.is_current_stream_capturing():
            raise RuntimeError("Engram prefetch stream must exist before graph capture")
        self._side = torch.cuda.Stream(device=indices.device)
    ids, w, s, dw, ds, sequential, work = _staging(self, indices, count)
    work.slot_mod = _slot_mod(indices)
    if not _state["seen"]:
        _state["seen"] = True
        logger.warning("DSV41 Engram prefetch first payload: ids=%s rows=%s", count, self.rows)
    main = torch.cuda.current_stream(indices.device)
    self._side.wait_stream(main)  # fork: the hash ids are ready on main
    with torch.cuda.stream(self._side):
        ids[:count].copy_(indices.reshape(-1), non_blocking=True)
        error = eb._cuda.cudaLaunchHostFunc(self._side.cuda_stream,
                                            C.cast(eb._lib.row_store_lookup, eb.P), C.addressof(work))
        if error:
            raise RuntimeError(f"CUDA Engram host callback failed: {error}")
        dw[:count].copy_(w[:count], non_blocking=True)
        ds[:count].copy_(s[:count], non_blocking=True)
    self._pending = (indices.data_ptr(), tuple(indices.shape), count, dw, ds, sequential)


def _prefetch_all(hash_ids):
    if _state["disabled"] or hash_ids.dim() != 3 or hash_ids.shape[0] == 0:
        return
    for emb in _EMBEDS:
        if emb._hash_index is None:
            continue
        _prefetch(emb, hash_ids[:, emb._hash_index])


_warm_state = {"busy": False}


def _warm_all(hash_ids):
    """Snapshot each layer's owned, deduped id set for this chunk and pread it
    into the caches on a daemon thread (one chunk in flight at a time). Rows are
    immutable, so a gather racing a half-finished warm only re-reads what it
    misses; the per-set locks in the .so keep the fills safe."""
    limit = _warm_rows()
    if _warm_state["busy"]:
        return
    snapshots = []
    for emb in _EMBEDS:
        if emb._hash_index is None:
            continue
        flat = hash_ids[:, emb._hash_index].reshape(-1)
        host = flat.detach().cpu()
        owned = host[(host >= emb.row_start) & (host < emb.row_start + emb.rows)]
        snapshots.append((emb._store, torch.unique(owned)[:limit]))

    def run():
        try:
            for store, uniq in snapshots:
                count = int(uniq.numel())
                if not count:
                    continue
                buf = torch.empty(count, dtype=torch.int64, pin_memory=True)
                buf.copy_(uniq)
                eb.warm_store(store, buf, count)
        except Exception as exc:  # noqa: BLE001 - a warm failure must not wedge the latch
            logger.warning("DSV41 Engram warm chunk failed: %r", exc)
        finally:
            _warm_state["busy"] = False

    _warm_state["busy"] = True
    threading.Thread(target=run, daemon=True, name="engram-warm").start()


def _gov_chunk(input_ids, hash_ids, pf):
    """ENGRAM-GOV chunk-boundary work, run once per forward from the hasher seam:
    prefill-sized forwards bump the cache epoch (rows cached for an earlier
    chunk become stale-first victims) and warm this chunk's row set; the
    side-stream fork stays gated by DSV41_ENGRAM_PREFETCH. Decode-sized forwards
    do neither -- their working set is small, hot and must not be aged."""
    prefill_chunk = (input_ids.dim() > 0 and input_ids.numel() >= _chunk_min_tokens())
    if prefill_chunk and _chunk_lifetime():
        for emb in _EMBEDS:
            eb.bump_epoch(emb._store)
    if prefill_chunk and _warm_rows() > 0 and hash_ids.dim() == 3:
        _warm_all(hash_ids)
    if pf:
        _prefetch_all(hash_ids)


def _assert_seams(EngramEmbedding, Engram, EngramHasher):
    """Refuse to arm on a drifted engine: an inert prefetch is invisible in a DE number.

    The two seams that only exist once a module is built -- ``Engram.layer_hash_index`` (which
    keys the hash-id column) and ``Engram.embed`` -- are checked in ``Engram.__init__``'s own
    source instead of on the class, because they are set per instance there.
    """
    for cls, names in ((EngramEmbedding, ("_owned_rows", "_empty")),
                       (Engram, ("forward",)),
                       (EngramHasher, ("forward",))):
        missing = [n for n in names if not hasattr(cls, n)]
        if missing:
            raise RuntimeError(f"engram-prefetch: {cls.__name__} is missing {missing}; seam moved")
    # inspect.getsource works for classes defined in a file; a stub built in a test has one too,
    # so this check is exercisable rather than decorative.
    try:
        source = inspect.getsource(Engram.__init__)
    except (OSError, TypeError):
        source = ""
    if source:
        for anchor in ("self.layer_hash_index =", "self.embed = EngramEmbedding("):
            if anchor not in source:
                raise RuntimeError(
                    f"engram-prefetch: {Engram.__name__}.__init__ no longer sets {anchor!r}; "
                    "seam moved")
    for name in ("Work", "_cuda", "_lib", "P"):
        if not hasattr(eb, name):
            raise RuntimeError(f"engram-prefetch: engram_backend has no {name}; seam moved")
    if not hasattr(eb._lib, "row_store_lookup"):
        raise RuntimeError("engram-prefetch: librow_store.so has no row_store_lookup")


def install(module) -> bool:
    pf = enabled()
    lifetime, warm = _chunk_lifetime(), _warm_rows() > 0
    if not (pf or lifetime or warm):
        return False
    EngramEmbedding, Engram, EngramHasher = module.EngramEmbedding, module.Engram, module.EngramHasher
    # Idempotence first: after the first install Engram.__init__ *is* our wrapper, so the seam
    # checks below would read the wrapper's source and refuse their own output.
    for cls, attr in ((EngramEmbedding, "_dsv41_engram_prefetch"),
                      (Engram, "_dsv41_engram_prefetch"),
                      (EngramHasher, "_dsv41_engram_prefetch")):
        if getattr(cls, attr, False):
            return False
    if pf:
        _assert_seams(EngramEmbedding, Engram, EngramHasher)
    elif lifetime or warm:
        # The GOV gates ride the same hasher seam but never touch staging.
        missing = [n for n in ("forward",) if not hasattr(EngramHasher, n)]
        if missing or not hasattr(eb, "_lib"):
            raise RuntimeError(f"engram-gov: seam moved ({EngramHasher.__name__} missing {missing})")
        if not getattr(eb, "_GOV_ABI", False):
            logger.warning("DSV41 Engram GOV gates need a rebuilt librow_store.so "
                           "(row_store_epoch/row_store_warm absent); lifetime/warm inert")
    for cls in (EngramEmbedding, Engram, EngramHasher):
        setattr(cls, "_dsv41_engram_prefetch", True)

    orig_init = EngramEmbedding.__init__

    def init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self._hash_index = None
        self._pending = None
        self._side = torch.cuda.Stream() if torch.cuda.is_available() else None
        self._check_acc = None
        _EMBEDS.append(self)

    EngramEmbedding.__init__ = init
    orig_eng_init = Engram.__init__

    def eng_init(self, *args, **kwargs):
        orig_eng_init(self, *args, **kwargs)
        self.embed._hash_index = self.layer_hash_index

    Engram.__init__ = eng_init
    orig_owned = EngramEmbedding._owned_rows
    check = _checking()

    if pf:
        def owned(self, indices):
            p = self._pending
            if not p or p[0] != indices.data_ptr() or p[1] != tuple(indices.shape) or p[2] != indices.numel():
                return orig_owned(self, indices)
            self._pending = None
            from sglang.kernels.ops.embeddings.engram_gather import engram_gather

            _, _, count, dw, ds, sequential = p
            torch.cuda.current_stream(indices.device).wait_stream(self._side)  # join
            out = self._empty(indices)
            engram_gather(dw.data_ptr(), ds.data_ptr(), sequential[:count], out.view(-1, 256), 256, 32)
            if check:
                reference = orig_owned(self, indices)
                if self._check_acc is None:
                    self._check_acc = torch.zeros((), dtype=torch.int64, device=indices.device)
                self._check_acc += (out != reference).any().to(torch.int64)
            return out

        EngramEmbedding._owned_rows = owned
    orig_forward = EngramHasher.forward

    def forward(self, input_ids, forward_batch):
        hash_ids = orig_forward(self, input_ids, forward_batch)
        try:
            _gov_chunk(input_ids, hash_ids, pf)
        except Exception as exc:  # noqa: BLE001
            if not _state["disabled"]:
                _state["disabled"] = True
                logger.warning("DSV41 Engram prefetch/gov disabled after error: %r", exc)
            for emb in _EMBEDS:
                emb._pending = None
        return hash_ids

    EngramHasher.forward = forward
    logger.warning(
        "DSV41 Engram prefetch%s ARMED%s",
        ("+gov" if (lifetime or warm) else ""),
        (": fork/join rows on a side stream after the hasher%s"
         " (CHECK mode: the synchronous lookup is re-run and compared)" if check else
         "; gov gates only (prefetch fork off)") if not pf else
        ("; gov: chunk_lifetime=%s warm_rows=%s" % (_chunk_lifetime(), _warm_rows())),
    )
    if check:
        period = float(os.getenv("DSV41_STATS_SECONDS", "60"))

        def loop():
            while True:
                time.sleep(period)
                counts = [int(e._check_acc.item()) if e._check_acc is not None else -1 for e in _EMBEDS]
                logger.warning(
                    "DSV41 Engram prefetch CHECK: gathers differing from the synchronous path "
                    "per layer = %s", counts)

        threading.Thread(target=loop, daemon=True, name="engram-prefetch-check").start()
    return True


def summary() -> str:
    return ("gate=%s armed=%s embeds=%s gov(lifetime=%s warm_rows=%s min_tokens=%s)"
            % (os.environ.get("DSV41_ENGRAM_PREFETCH", "(unset)"), enabled(), len(_EMBEDS),
               _chunk_lifetime(), _warm_rows(), _chunk_min_tokens()))
