"""Bounded exact file-backed replacement for EngramEmbedding's owned-row gather.

The original hash, gating, projections, TP all-reduce and model remain unchanged.
Native callback executes IO inside CUDA graphs without calling the CUDA API.
"""
import ctypes as C
import glob
import json
import logging
import os
from pathlib import Path
import struct

import torch

P, U = C.c_void_p, C.c_uint64
_lib = C.CDLL(str(Path(__file__).with_name('librow_store.so')))
_lib.row_store_open.argtypes = [C.c_char_p, U, U, U, U]
_lib.row_store_open.restype = P
_lib.row_store_range.argtypes = [P, U, U]
_lib.row_store_stats.argtypes = [P, C.POINTER(U)]
_lib.row_store_attach_packed.argtypes = [P, C.c_char_p, U]
_lib.row_store_attach_packed.restype = C.c_int
# ENGRAM-GOV (2026-09-30) ABI additions. A pre-gov .so simply lacks them: the
# gates stay inert and the boot log says so once. argtypes are also the gate --
# ctypes exposes unknown symbols only via getattr, never implicitly.
try:
    _lib.row_store_epoch.argtypes = [P]
    _lib.row_store_epoch.restype = U
    _lib.row_store_warm.argtypes = [P, P, U]
    _GOV_ABI = True
except AttributeError:
    _GOV_ABI = False

class Work(C.Structure):
    _fields_ = [('store', P), ('ids', P), ('weights', P), ('scales', P), ('count', U),
                # stats v2 (2026-09-20): flatten width of the caller's
                # [tokens, n_hash_cols] id tensor -> per-slot (= per-n-gram-order)
                # hit/miss split in the .so. 0 disables. ABI-safe append.
                ('slot_mod', U)]

_STORES = []

def _isprime(n):
    """Deterministic Miller-Rabin for the 16-384 M layout primes (no sympy dep)."""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True

def _engram_layout_spans(engram_cfg):
    """(layer_id -> [(prime, order), ...]) replicating engine EngramLayout.build:
    one shared ascending prime sequence above vocab_size-1, drawn in
    (layer, n-gram order, head) order; offsets are a cumsum, so each layer's row
    space is the exact concatenation of its (order-major, head-minor) sub-ranges."""
    vocab = int(engram_cfg['engram_vocab_size'])
    heads = int(engram_cfg['engram_n_heads'])
    orders = int(engram_cfg['engram_max_ngram_size']) - 1
    seen, cur, out = set(), vocab - 1, {}
    for layer_id in engram_cfg['engram_layer_ids']:
        spans = []
        for order in range(2, orders + 2):
            for _ in range(heads):
                cur += 1
                while not _isprime(cur) or cur in seen:
                    cur += 1
                seen.add(cur)
                spans.append((cur, order))
        out[layer_id] = spans
    return out

def _order_shares(spans, lo, hi):
    """Share of a rank's owned row range held by each n-gram order's sub-ranges."""
    out, pos = {}, 0
    for prime, order in spans:
        a, b = pos, pos + prime
        pos = b
        overlap = max(0, min(b, hi) - max(a, lo))
        if overlap:
            out[order] = out.get(order, 0) + overlap
    return {order: share / (hi - lo) for order, share in out.items()}

def _cache_budget_bytes(tp_size):
    """Per-store cache budget. ENGRAM-GOV 2026-09-30.

    DSV41_ENGRAM_CACHE_GIB is the explicit per-store top: what you write is what
    each Engram layer's store gets -- no hidden division -- and the boot line
    projects the per-host total (per-store x len(engram_layer_ids)). Legacy
    DSV41_CACHE_GIB keeps its historical per-host/2-layers/ranks semantics; the
    explicit key exists because implicit division drifts (0.2.8 precedent:
    approved 1 GiB vs an env pin at 4, archive doc82 CACHE-MEMSTAB #18)."""
    explicit = os.getenv('DSV41_ENGRAM_CACHE_GIB', '')
    if explicit:
        return int(float(explicit) * 2**30)
    # DSV41_CACHE_GIB is the per-host budget, split across the Engram layers
    # and the ranks that share that host's RAM. Upstream ran every TP rank in
    # one box, so it divided by tp_size; on the Spark triangle each node runs
    # a single rank and dividing by tp_size silently gave each node a third of
    # the cache it was asked for.
    ranks_per_host = max(1, tp_size // max(1, int(os.getenv('NNODES', '1'))))
    return int(float(os.getenv('DSV41_CACHE_GIB', '64')) * 2**30) // (2*ranks_per_host)

def _warn_cache_share(budget, n_layers):
    """Boot-time guard against the 0.2.8 class of runaway cache: warn when the
    projected per-host Engram total exceeds min(4 GiB, 10% of MemAvailable)
    (floor 0.5 GiB). 4 GiB/host is the documented 0.2.8 crash point (archive
    doc82 CACHE-MEMSTAB #18), so it caps even huge-RAM hosts."""
    try:
        total_gib = budget * n_layers / 2**30
        avail_kib = 0
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    avail_kib = int(line.split()[1])
                    break
        cap = max(0.5, min(4.0, 0.10 * avail_kib / 2**20))
        if total_gib > cap:
            logging.getLogger(__name__).warning(
                'Engram cache host-share guard: %.2f GiB/store x %d layers = '
                '%.1f GiB exceeds cap %.1f GiB (min(4, 10%% MemAvailable)) — '
                'this is the 0.2.8 4GiB-crash class; cut DSV41_ENGRAM_CACHE_GIB',
                budget / 2**30, n_layers, total_gib, cap)
    except Exception:  # noqa: BLE001 - a guard must never block the boot
        pass

# Stats ABI v2: buffer is 45 words; a legacy 9-word .so leaves the tail zeroed
# (ctypes zero-fills), which _stats reports via extended=False.
_STATS_MAGIC = 0x454E4752  # 'ENGR'

def _stats(store):
    out = (U * 45)()
    _lib.row_store_stats(store, out)
    d = dict(hits=out[0], misses=out[1], reads=out[2], cache_bytes=out[3],
             slots=out[4], scale_bytes=out[5], ways=out[6], threads=out[7],
             packed=bool(out[8]))
    d['extended'] = out[44] == _STATS_MAGIC
    if d['extended']:
        d.update(evictions=out[9], unique_ids=out[10], slot_mod=out[11],
                 per_slot=[(out[12 + 2*k], out[13 + 2*k]) for k in range(16)])
    return d

def _report():
    """Miss rate and read volume decide decode latency here; log them."""
    import threading
    import time
    period = float(os.getenv('DSV41_STATS_SECONDS', '60'))
    if period <= 0:
        return
    log = logging.getLogger(__name__)
    # ENGRAM-GOV watermarks: a window below the hit floor or over the read
    # ceiling is the disk-read storm signature (INCIDENT-20260930-1327: hit
    # 83.3/30.7/3.4/1.8% across TP ranks on a 229K needle). log.warning so the
    # existing boot-log monitoring surface greps it. 0 disables either side.
    hit_floor = float(os.getenv('DSV41_ENGRAM_HIT_ALARM', '50'))
    read_ceiling = int(float(os.getenv('DSV41_ENGRAM_READ_ALARM', '100000')))
    min_lookups = int(float(os.getenv('DSV41_ENGRAM_ALARM_MIN_LOOKUPS', '5000')))
    def loop():
        previous = {}
        while True:
            time.sleep(period)
            for store, layer_id, rank in _STORES:
                now = _stats(store)
                was = previous.get(layer_id)
                previous[layer_id] = now
                if was is None:
                    continue
                hits = now['hits'] - was['hits']
                misses = now['misses'] - was['misses']
                total = hits + misses
                if not total:
                    continue
                reads_d = now['reads'] - was['reads']
                # slots==0 means budget==0: the C hit path is skipped entirely
                # and hit_rate would print a permanent, misleading 0.0%.
                hit_rate = ('%.1f%%' % (100.0*hits/total)
                            if now['slots'] else 'n/a (cache off)')
                extra = ''
                if now.get('extended') and was.get('extended'):
                    sm = now['slot_mod']
                    if sm:
                        parts = []
                        for k in range(sm):
                            dh = now['per_slot'][k][0] - was['per_slot'][k][0]
                            dm = now['per_slot'][k][1] - was['per_slot'][k][1]
                            dt = dh + dm
                            if dt:
                                # slot == hash column of a [T, n_hash_cols]
                                # flatten -> n-gram order = column + 2
                                parts.append('%d-gram=%.1f%%(%s)'
                                             % (k + 2, 100.0*dh/dt, dt))
                        if parts:
                            extra = ' orders=[%s]' % ', '.join(parts)
                    extra += ' evictions=%s unique_rows=%s' % (
                        now['evictions'] - was['evictions'],
                        now['unique_ids'] - was['unique_ids'])
                log.info('Engram rank=%s layer=%s lookups=%s hit_rate=%s reads=%s '
                         'cache=%.1fGiB(%s-way) scales=%.1fGiB threads=%s packed=%s%s',
                         rank, layer_id, total, hit_rate, reads_d,
                         now['cache_bytes']/2**30, now['ways'],
                         now['scale_bytes']/2**30, now['threads'], now['packed'],
                         extra)
                if now['slots'] and total >= min_lookups:
                    pct = 100.0*hits/total
                    if ((hit_floor > 0 and pct < hit_floor)
                            or (read_ceiling > 0 and reads_d >= read_ceiling)):
                        log.warning(
                            'Engram STORM-SUSPECT rank=%s layer=%s hit=%.1f%% '
                            'reads=%s evictions=%s — high-order n-gram quadrant '
                            'pressure (TP row-range x order-major id layout; '
                            'see ENGRAM-GOV-20260930 taskcard)',
                            rank, layer_id, pct, reads_d,
                            now['evictions'] - was['evictions'])
    threading.Thread(target=loop, daemon=True, name='engram-stats').start()

def _register_store(store, layer_id, rank):
    _STORES.append((store, layer_id, rank))
    if len(_STORES) == 1:
        _report()

def bump_epoch(store):
    """ENGRAM-GOV chunk lifetime: advance one store's epoch; rows inserted in
    earlier chunks become stale-first eviction victims (soft invalidation)."""
    if _GOV_ABI:
        return _lib.row_store_epoch(store)
    return 0

def warm_store(store, ids, count):
    """ENGRAM-GOV prefill prefetch: pool-pread `count` pinned int64 ids through
    the normal miss path so the layer gathers find them resident. `ids` must be
    a pinned CPU int64 tensor of at least `count` elements."""
    if _GOV_ABI and count > 0:
        _lib.row_store_warm(store, ids.data_ptr(), count)

def _load_cudart():
    paths = []
    paths += glob.glob('/usr/local/cuda*/targets/aarch64-linux/lib/libcudart.so*')
    paths += glob.glob('/usr/local/cuda*/targets/x86_64-linux/lib/libcudart.so*')
    paths += glob.glob('/usr/local/cuda/lib64/libcudart.so*')
    paths += glob.glob('/usr/local/lib/python*/dist-packages/nvidia/cuda_runtime/lib/libcudart.so*')
    paths += glob.glob('/usr/local/lib/python*/site-packages/nvidia/cuda_runtime/lib/libcudart.so*')
    seen, errors = set(), []
    for path in paths:
        if path in seen or path.endswith('.a') or not os.path.isfile(path):
            continue
        seen.add(path)
        try:
            lib = C.CDLL(path)
            lib.cudaLaunchHostFunc.argtypes = [P, P, P]
            lib.cudaLaunchHostFunc.restype = C.c_int
            return lib
        except OSError as exc:
            errors.append(f'{path}: {exc}')
    raise RuntimeError('libcudart.so not found (need CUDA runtime for Engram host callbacks). Tried: '
                       + '; '.join(errors or paths or ['<none>']))

try:
    _cuda = _load_cudart()
except RuntimeError:  # ENGRAM-GOV: import stays introspectable offline; the
    _cuda = None      # engine host resolves it lazily on the first gather

def install(module):
    cls = module.EngramEmbedding
    def init(self, num_embeddings, dim, layer_id):
        torch.nn.Module.__init__(self)
        assert dim == 256
        self.dim, self.tp_size = dim, module.get_parallel().tp_size
        rank = module.get_parallel().tp_rank
        self.row_start = num_embeddings * rank // self.tp_size
        end = num_embeddings * (rank + 1) // self.tp_size
        self.rows, self.host_table = end - self.row_start, None
        root = Path(os.environ['DSV41_SOURCE'])
        index = json.loads((root/'model.safetensors.index.json').read_text())['weight_map']
        prefix = f'layers.{layer_id}.engram.embed.'
        filename = root/index[prefix+'weight']
        assert index[prefix+'weight'] == index[prefix+'scale']
        with filename.open('rb') as f:
            length = struct.unpack('<Q', f.read(8))[0]
            header = json.loads(f.read(length))
        w, s = header[prefix+'weight'], header[prefix+'scale']
        assert w['shape'] == [num_embeddings, 256] and w['dtype'] == 'F8_E4M3'
        assert s['shape'] == [num_embeddings, 8] and s['dtype'] == 'F8_E8M0'
        # DSV41_CACHE_GIB is the per-host budget, split across the Engram layers
        # and the ranks that share that host's RAM. Upstream ran every TP rank in
        # one box, so it divided by tp_size; on the Spark triangle each node runs
        # a single rank and dividing by tp_size silently gave each node a third of
        # the cache it was asked for.
        budget = _cache_budget_bytes(self.tp_size)
        self._store = _lib.row_store_open(str(filename).encode(), num_embeddings,
            8+length+w['data_offsets'][0], 8+length+s['data_offsets'][0], budget)
        if not self._store:
            raise RuntimeError(f'Could not open Engram backing shard: {filename}')
        _lib.row_store_range(self._store, self.row_start, end)
        # A repacked local shard, when present, makes every miss a single local
        # read; without it we fall back to the checkpoint (NFS on a worker).
        packed_dir = os.environ.get('DSV41_PACKED_DIR', '')
        if packed_dir:
            shard = Path(packed_dir)/f'engram-l{layer_id}-r{rank}of{self.tp_size}.bin'
            if shard.exists():
                _lib.row_store_attach_packed(self._store, str(shard).encode(), layer_id)
        _register_store(self._store, layer_id, rank)
        # ENGRAM-GOV boot surface: the rank's n-gram order blend (TP quadrant x
        # order-major id layout decides which rank storms on long prompts) and
        # the cache governance keys actually in force.
        gov = 'gov-abi' if _GOV_ABI else 'gov-abi MISSING (rebuild librow_store.so)'
        shares = ''
        try:
            cfg = json.loads((root/'config.json').read_text())
            for cfg_key in ('text_config',):
                cfg = cfg.get(cfg_key, cfg)
            spans = _engram_layout_spans(cfg)[layer_id]
            _warn_cache_share(budget, len(cfg['engram_layer_ids']))
            shares = ' orders=' + ','.join(
                '%dg:%.0f%%' % (order, 100.0*share)
                for order, share in sorted(_order_shares(spans, self.row_start, end).items()))
        except Exception:  # noqa: BLE001 - boot surface only
            pass
        self._staging = {}
        self._works = {}
        # The loader sees names but never allocates/copies the complete tables.
        self.weight = torch.nn.Parameter(torch.empty(0, dtype=torch.float8_e4m3fn), requires_grad=False)
        self.scale = torch.nn.Parameter(torch.empty(0, dtype=torch.float8_e8m0fnu), requires_grad=False)
        def validate_weight(param, source):
            expected = w if param is self.weight else s
            if list(source.shape) != expected['shape']:
                raise ValueError('Engram checkpoint shape mismatch')
        self.weight.weight_loader = validate_weight
        self.scale.weight_loader = validate_weight
        stats = _stats(self._store)
        logging.getLogger(__name__).info(
            'Exact %s Engram layer=%s rank=%s rows=[%s,%s) cache=%.1fGiB '
            '(%s slots, %s-way, %.1f%% of owned rows) scales=%.1fGiB io_threads=%s '
            'packed=%s %s%s',
            os.getenv('OFFLOAD_MODE', 'nvme'), layer_id, rank, self.row_start, end,
            stats['cache_bytes']/2**30, stats['slots'], stats['ways'],
            100.0*stats['slots']/max(1, self.rows), stats['scale_bytes']/2**30,
            stats['threads'], stats['packed'], gov, shares)

    def owned(self, indices):
        from sglang.kernels.ops.embeddings.engram_gather import engram_gather
        count = indices.numel()
        if not count:
            return self._empty(indices)
        capacity = 1 << (count - 1).bit_length()
        key = (indices.device.index, capacity)
        if key not in self._staging:
            if torch.cuda.is_current_stream_capturing():
                raise RuntimeError(f'Engram staging {key} must be warmed before graph capture')
            ids = torch.empty(capacity, dtype=torch.int64, pin_memory=True)
            w = torch.empty((capacity, 256), dtype=torch.uint8, pin_memory=True)
            s = torch.empty((capacity, 8), dtype=torch.uint8, pin_memory=True)
            dw, ds = w.to(indices.device), s.to(indices.device)
            sequential = torch.arange(capacity, dtype=torch.int64, device=indices.device)
            self._staging[key] = (ids, w, s, dw, ds, sequential)
        ids, w, s, dw, ds, sequential = self._staging[key]
        work_key = (indices.device.index, count)
        if work_key not in self._works:
            self._works[work_key] = Work(self._store, ids.data_ptr(), w.data_ptr(), s.data_ptr(), count)
        work = self._works[work_key]
        global _cuda
        if _cuda is None:
            _cuda = _load_cudart()
        # stats v2: flatten width of [tokens, n_hash_cols] -> per-order split.
        # Constant per shape; writing it here (also under graph capture) keeps
        # replays attributed exactly like the captured call.
        work.slot_mod = (indices.numel() // indices.shape[0]
                         if indices.dim() > 1 and indices.shape[0] > 0 else 0)
        ids[:count].copy_(indices.reshape(-1), non_blocking=True)
        error = _cuda.cudaLaunchHostFunc(torch.cuda.current_stream().cuda_stream,
            C.cast(_lib.row_store_lookup, P), C.addressof(work))
        if error:
            raise RuntimeError(f'CUDA Engram host callback failed: {error}')
        dw[:count].copy_(w[:count], non_blocking=True)
        ds[:count].copy_(s[:count], non_blocking=True)
        out = self._empty(indices)
        engram_gather(dw.data_ptr(), ds.data_ptr(), sequential[:count], out.view(-1, 256), 256, 32)
        return out
    cls.__init__ = init
    cls._owned_rows = owned
