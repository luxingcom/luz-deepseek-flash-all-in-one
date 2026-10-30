"""Opt-in bounded fresh-prefill admission beside an in-flight chunk.

Only the pinned scheduler candidate loop and PrefillAdder are adapted. Token
memory accounting remains with the engine. The disabled path mutates nothing.
"""
import hashlib
import inspect
import logging
import os
import textwrap

logger = logging.getLogger(__name__)
# Upstream: knapcio v2.5 adapter/prefill_bypass.py (b9ea6dd first, hardened to terminal
# 173-line form). BYPASS-B staging: EXPECTED re-pinned to the 0.3.4 overlay live face
# (T34-06 §五-1; AGPLv3 lineage carried). Patch anchors byte-identical (count==1 x4).
# SGLang f80c91a4b97e52e17fbcff088aa6b47b6270f6b9, dedented inspect source.
EXPECTED = {
    # 0.3.4 BYPASS-B (MV-14) re-pin: overlay live face scheduler.py=3db3275e /
    # schedule_policy.py=4926389a (dedented inspect source). Four of nine pins are
    # byte-identical to the upstream knapcio tree; the five our-tree extensions
    # (delayer wrapper / hicache / beam surfaces) carry new pins.
    ('Scheduler', '_get_new_batch_prefill_raw'): '0d9b04db3d7420897db851c7abb74d5e4a918d67290b36ce7cdda06a1db4468f',
    ('PrefillAdder', 'add_one_req'): '7c5f079f3ec869a8a72552f12fe6a25e89ce9afc24b02d3327e7737a469136ae',
    ('PrefillAdder', '_select_prefill_admission'): '74f78c2cef4f0224668b5093c6e224f265f27a6b1e90653cdf46afc6a612cfa0',
    ('PrefillAdder', '_check_prefill_budget'): '32b96fca7c3461b369252e009e9dfc6aa47086a4db288d598c000cffa0c87a00',
    ('PrefillAdder', '_update_prefill_budget'): '743f8c6b1e89c371e92639f323abd59a5865d395951b45091c4c16fd5536ed55',
    ('PrefillAdder', 'budget_state'): 'e4ef5cbf61b5b550f217b41d3ddd8bc795be5dcfd8cfcc5c3db0243890217eb2',
    ('PrefillAdder', '_commit_prefill_admission'): '6e19326288ee6ea8dbd31a19714f492f231bf8a633fb085fb709333041e0a62c',
    ('PrefillAdder', 'ceil_paged_tokens'): '8d9f6ef01a316bda6dcb05898be904cd6833eaf58d0a0b8782b8c93f5bdf148a',
    ('PrefillAdder', 'add_chunked_req'): '417127c8916d6aaf2157b1dc98614f751a2d3cfa2f4c6574e54728d10cc556d9',
}


def fresh_tokens(req):
    return len(req.full_untruncated_fill_ids) - len(req.prefix_indices)


def bypass_active(scheduler):
    # These modes have additional readiness/admission state. Restrict this
    # experiment to the ordinary TP scheduler and its synchronized token pools.
    return (scheduler.chunked_req is not None
            and scheduler.dllm_config is None
            # The delayer's timeout uses rank-local time. The staged scheduler
            # stores the enabled delayer object rather than a boolean flag.
            and not getattr(scheduler, 'enable_prefill_delayer', False)
            and not getattr(scheduler, 'prefill_delayer', None)
            and not scheduler.enable_priority_preemption
            and not scheduler.enable_lora
            and not scheduler.enable_hicache_storage
            and not scheduler.enable_hierarchical_cache
            and not scheduler.enable_unified_cache_external_linker)


def install(module):
    raw = os.environ.get('DSV41_PREFILL_BYPASS', '').strip()
    if not raw:
        return False
    try:
        limit = int(raw)
        if limit <= 0:
            raise ValueError
    except ValueError:
        logger.warning('DSV41_PREFILL_BYPASS: refusing to arm; expected a positive fresh-token limit')
        return False
    scan_raw = os.environ.get('DSV41_PREFILL_BYPASS_SCAN', '32').strip()
    try:
        scan_limit = int(scan_raw)
        if scan_limit <= 0:
            raise ValueError
    except ValueError:
        logger.warning('DSV41_PREFILL_BYPASS: refusing to arm; '
                       'DSV41_PREFILL_BYPASS_SCAN must be a positive candidate limit')
        return False
    cls = getattr(module, 'Scheduler', None)
    adder_cls = getattr(module, 'PrefillAdder', None)
    if getattr(cls, '_dsv41_prefill_bypass', False):
        return False
    try:
        sources = {}
        for (owner, name), digest in EXPECTED.items():
            target = cls if owner == 'Scheduler' else adder_cls
            source = textwrap.dedent(inspect.getsource(getattr(target, name)))
            if hashlib.sha256(source.encode()).hexdigest() != digest:
                raise ValueError(f'{owner}.{name} source drift')
            sources[(owner, name)] = source
        original_raw = cls._get_new_batch_prefill_raw
        source = sources[('Scheduler', '_get_new_batch_prefill_raw')]
        patches = [
            ('    # Check if the grammar is ready in the grammar queue\n',
             '    _dsv41_scan = _dsv41_bypass_active(self)\n'
             '    # Check if the grammar is ready in the grammar queue\n'),
            ('        self.chunked_req = adder.add_chunked_req(self.chunked_req)\n\n'
             '    if self.enable_lora:\n',
             '        self.chunked_req = adder.add_chunked_req(self.chunked_req)\n\n'
             '    # Bypass only while the chunk remains in flight. A final chunk uses\n'
             '    # the stock residual compute budget for ordinary queue admission.\n'
             '    _dsv41_scan = _dsv41_scan and self.chunked_req is not None\n'
             '    adder._dsv41_bypass_pass = _dsv41_scan\n'
             '    adder._dsv41_bypass_remaining = _dsv41_limit if _dsv41_scan else 0\n\n'
             '    if self.enable_lora:\n'),
            ('    # Get requests from the waiting queue to a new prefill batch\n'
             '    for req in self.waiting_queue:\n',
             '    # Get requests from the waiting queue to a new prefill batch\n'
             '    _dsv41_bypass_scanned = 0\n'
             '    for req in self.waiting_queue:\n'),
            ('        req.init_next_round_input(self.tree_cache)\n',
             '        if _dsv41_scan and _dsv41_bypass_scanned >= _dsv41_scan_limit:\n'
             '            break\n'
             '        req.init_next_round_input(self.tree_cache)\n'
             '        if _dsv41_scan:\n'
             '            _dsv41_bypass_scanned += 1\n'
             '            if not (0 <= _dsv41_fresh_tokens(req) <= _dsv41_limit):\n'
             '                continue\n'),
            ('            break\n\n    if mamba_allocator is not None:',
             '            if (_dsv41_scan and not added\n'
             '                    and _dsv41_bypass_scanned < _dsv41_scan_limit):\n'
             '                running_batch.batch_is_full = False\n'
             '                continue\n'
             '            break\n\n    if mamba_allocator is not None:'),
        ]
        for old, new in patches:
            if source.count(old) != 1:
                raise ValueError('candidate-loop anchor drift')
            source = source.replace(old, new)
        namespace = dict(original_raw.__globals__, _dsv41_bypass_active=bypass_active,
                         _dsv41_fresh_tokens=fresh_tokens, _dsv41_limit=limit,
                         _dsv41_scan_limit=scan_limit)
        exec(compile('from __future__ import annotations\n' + source,
                     '<dsv41-prefill-bypass>', 'exec'), namespace)
        patched_raw = namespace['_get_new_batch_prefill_raw']
        original_add = adder_cls.add_one_req
        original_select = adder_cls._select_prefill_admission
    except (AttributeError, TypeError, OSError, ValueError, SyntaxError) as exc:
        logger.warning('DSV41_PREFILL_BYPASS: refusing to arm; %s', exc)
        return False

    def select(self, *args, **kwargs):
        admission = original_select(self, *args, **kwargs)
        if (getattr(self, '_dsv41_bypass_candidate', False)
                and getattr(admission, 'is_chunked', False)):
            # Memory may fit only part of the request. Never create a second
            # chunked_req while the engine owns an in-flight one.
            return original_add.__globals__['AddReqResult'].OTHER
        return admission

    def add(self, req, has_chunked_req, truncation_align_size):
        if (not getattr(self, '_dsv41_bypass_pass', False)
                or not has_chunked_req or self.rem_chunk_tokens is None):
            return original_add(self, req, has_chunked_req, truncation_align_size)
        fresh = fresh_tokens(req)
        if not (0 <= fresh <= limit) or self.dllm_config is not None or req.sampling_params.ignore_eos:
            return original_add.__globals__['AddReqResult'].OTHER
        if fresh > getattr(self, '_dsv41_bypass_remaining', 0):
            return original_add.__globals__['AddReqResult'].OTHER
        saved = self.rem_chunk_tokens
        allowance = max(saved, self.ceil_paged_tokens(fresh))
        self.rem_chunk_tokens = allowance
        self._dsv41_bypass_candidate = True
        try:
            # The stock _select_prefill_admission calls _check_prefill_budget
            # before committing. Only the compute chunk cap is extended; the
            # pool, offsets, decode reserve, and page overhead stay untouched.
            result = original_add(self, req, has_chunked_req, truncation_align_size)
            if self.can_run_list and req is self.can_run_list[-1]:
                self._dsv41_bypass_remaining -= fresh
            return result
        finally:
            charged = allowance - self.rem_chunk_tokens
            self.rem_chunk_tokens = saved - charged
            self._dsv41_bypass_candidate = False

    # Publish only after all fingerprints and compilation have succeeded.
    adder_cls._select_prefill_admission = select
    adder_cls.add_one_req = add
    cls._get_new_batch_prefill_raw = patched_raw
    cls._dsv41_prefill_bypass = True
    logger.warning('DSV41_PREFILL_BYPASS armed: at most %d total fresh tokens and %d '
                   'candidates scanned per in-flight chunk pass; engine token-pool '
                   'admission retained; fleet qualification pending', limit, scan_limit)
    return True
