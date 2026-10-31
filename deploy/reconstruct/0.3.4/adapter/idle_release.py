"""FIX-B port for main-79cafece: return stranded allocator memory in fully-idle windows.

Provenance: LuZ-0.2.9 production scheduler carried ``_maybe_idle_release``
(scheduler.py:1806-1888, ``DSV41_IDLE_RELEASE=1`` in .env.tp4) — the stack's only
mechanism that continuously gives device memory back to the driver between bursts.
main-79cafece's ``Scheduler.on_idle`` has no equivalent, and with
``expandable_segments:False`` the per-chunk prefill transients whose widths drift
with the prefix cannot be re-served from smaller cached blocks, so reserved grows
monotonically (the 2026-09-21 four-node OOM lineage; measured 2026-10-01 on this
base: one 8k needle strand ~1.6 GiB, a full battery window walks MemAvailable by
-14 GiB and never returns). On GB10's unified memory reserved == host memory.

This wrap runs AFTER the stock on_idle: when the scheduler reports fully idle and
the caching allocator holds >= ``DSV41_IDLE_RELEASE_MIN_GIB`` (default 1) of cached
bytes, with >= ``DSV41_IDLE_RELEASE_MIN_S`` (default 60) seconds between releases,
it calls ``torch.cuda.empty_cache()``. Decode CUDA graphs live in private pools and
are untouched. Every release is counted; a heartbeat logs cumulative totals every
600 s; any error backs off one window and never breaks on_idle itself. Dormant
unless ``DSV41_IDLE_RELEASE=1``.
"""
import logging
import os
import time

import torch

logger = logging.getLogger(__name__)

_HEARTBEAT_S = 600.0


def install(module):
    if os.environ.get('DSV41_IDLE_RELEASE', '0').strip().lower() not in ('1', 'true', 'on', 'yes'):
        return
    min_bytes = int(float(os.environ.get('DSV41_IDLE_RELEASE_MIN_GIB', '1')) * 2**30)
    min_s = float(os.environ.get('DSV41_IDLE_RELEASE_MIN_S', '60'))
    cls = module.Scheduler
    original = cls.on_idle
    state = {'last': 0.0, 'last_beat': 0.0, 'released': 0, 'freed_gib': 0.0, 'fails': 0}

    def on_idle(self, *args, **kwargs):
        ret = original(self, *args, **kwargs)
        try:
            now = time.monotonic()
            if now - state['last'] < min_s or not self.is_fully_idle():
                return ret
            state['last'] = now
            reserved = torch.cuda.memory_reserved()
            cached = reserved - torch.cuda.memory_allocated()
            if cached < min_bytes:
                return ret
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            freed = reserved - torch.cuda.memory_reserved()
            state['released'] += 1
            state['freed_gib'] += freed / 2**30
            if now - state['last_beat'] >= _HEARTBEAT_S or state['released'] == 1:
                state['last_beat'] = now
                logger.warning(
                    '[DSV41] idle-release wrap: #%d released, cumulative %.2f GiB returned '
                    '(window freed %.2f GiB, cached was %.2f GiB)',
                    state['released'], state['freed_gib'], freed / 2**30, cached / 2**30)
        except Exception as exc:  # housekeeping must never break on_idle
            state['fails'] += 1
            logger.warning('DSV41 idle-release wrap: %s (fails=%d)', exc, state['fails'])
        return ret

    cls.on_idle = on_idle
    logger.warning(
        '[DSV41] idle-release wrap ARMED (min=%.1f GiB cached, interval=%ds)',
        min_bytes / 2**30, min_s)
