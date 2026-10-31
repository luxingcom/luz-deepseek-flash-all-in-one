"""Reject requests the decoder SWA bounded replay cannot serve, before they reach the engine.

boot.py always launches with --enable-decoder-swa-bounded-replay: past the last kv_source layer a
prefill runs only over its last window of rows. DeepseekV4Model._check_late_layer_tail_readers
then raises ValueError inside the forward for a request that wants prompt logprobs
(logprob_start_len < prompt length, e.g. /generate with logprob_start_len=0 or a completions
echo+logprobs request) or the hidden states of every prompt token. That exception is raised in
the scheduler process: all four ranks exit and the server is down until a restart.

Upstream validates the same case for the encoder variant only (TokenizerManager.
_validate_one_request, "encoder SWA replay cannot return cached prompt logprobs"). This hook
adds the decoder variant there, so such a request gets an HTTP 400 and the engine keeps serving.
Requests that ask for output logprobs only (chat logprobs=true, logprob_start_len -1 / None /
the prompt length) are unaffected. Gate: DSV41_REPLAY_GUARD (default on).
"""
import logging
import os

logger = logging.getLogger(__name__)


def enabled():
    return os.environ.get('DSV41_REPLAY_GUARD', '1').strip().lower() not in ('0', 'off', 'false', 'no', '')


def check(obj, input_ids, bounded_replay):
    """Raise ValueError when the bounded replay cannot serve this generate request."""
    if not bounded_replay or input_ids is None:
        return
    n = len(input_ids)
    start = getattr(obj, 'logprob_start_len', None)
    if getattr(obj, 'return_logprob', False) and isinstance(start, int) and 0 <= start < n:
        raise ValueError(
            'prompt logprobs are not available on this server (decoder SWA bounded replay): '
            f'logprob_start_len={start} < prompt length {n}; omit logprob_start_len or set it '
            'to the prompt length')
    if getattr(obj, 'return_hidden_states', False) is True:
        raise ValueError(
            'hidden states of every prompt token are not available on this server (decoder SWA '
            'bounded replay); use return_hidden_states="last"')


def install(module):
    if not enabled():
        return
    cls = module.TokenizerManager
    if getattr(cls._validate_one_request, '_dsv41_replay_guard', False):
        return
    original = cls._validate_one_request

    def _validate_one_request(self, obj, input_ids):
        try:
            bounded = bool(module.get_exec().features.enable_decoder_swa_bounded_replay)
        except Exception:  # noqa: BLE001
            bounded = True
        if type(obj).__name__ == 'GenerateReqInput':
            check(obj, input_ids, bounded)
        return original(self, obj, input_ids)

    _validate_one_request._dsv41_replay_guard = True
    cls._validate_one_request = _validate_one_request
    logger.info('DSV41_REPLAY_GUARD: prompt-logprob / full-hidden-state requests rejected with 400 '
                'under decoder SWA bounded replay')
