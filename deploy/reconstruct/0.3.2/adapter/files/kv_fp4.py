"""FP4-KV port gate and installer (fork-v4-fp4 on main 79cafec0) — R1 dev copy.

[R1-FORMAL 2026-10-19, S-R1-BOOT-20261019] Formalized in-service form (KA-C1
window; base = feaaadd4 R1 deployment form). Deltas vs feaaadd4 (KA-C4 batch):
(1) `_r1_fork_call` output/out_lse now grow-only `_persistent_buffer`s (same
helper as the repack scratch; kernel fully overwrites both tensors in place,
so results are bit-identical by construction); (2) `summary()` banner carries
`r1_formal=1` for boot-log direct evidence. No algorithmic change anywhere.

R1-FP4KV (LuZ-0.3.1 W3): this is the dev-tree copy of the in-service adapter
file (md5 954cab11d611e548fea22baa8b2f7386 at ~/migrate-assets/dsv41/adapter/
kv_fp4.py, READ-ONLY). Deployment = load-window adapter-set replacement
(design card R1-FP4KV-DESIGN-20261011.md sec 6-4). Everything below marked
[R1] is the fork addition; all other lines are byte-identical to the base.

Ports the production fin2 fork's ``SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4`` mode
onto the main tree as an adapter-overlay install: 584 B V4 main/SWA caches +
288 B V41_FP4 ratio-1/2 compressed caches, read through the out-of-kernel
repack bridge (kv_fp4_repack.py) because the SM120/SM121 FlashInfer
sparse-MLA kernel only consumes the 584-byte V4 form. Full map in
96-FP4KV-PORT-DESIGN-20260929.md.

[R1] With ``DSV41_FP4KV_R1_INKERNEL=1`` (strict boolean, default OFF), the
PREFILL face of the fp4 bridge is bypassed: the raw 288B pool + the original
extra_indices/extra_topk_length go to the fi_r1 fork kernel
(``sparse_mla_sm120_fp4`` JitSpec), which consumes the pool in-kernel
(E2M1 x E4M3 decode + per-64-tile requant replica; bit-equal to the repack
path by construction). Decode face and every key-off call keep the in-service
path byte-for-byte. First eligible prefill block is双跑对拍 (fork vs
repack+stock) with torch.equal on output+LSE; mismatch = permanent key-level
fallback + loud banner (A23-beta law). Fork import/JIT failure = same
fallback (fail-loud once).

Gate (default OFF, approval-pending wiring):
    DSV41_FP4KV_PORT=1|on|true   arm the port
    SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4   the mode itself (auto-injected by
        setdefault when the gate arms; an explicit other value wins and the
        layout patches degrade to passthrough -- no mixed state possible).
    SGLANG_DSV4_FP4_BRIDGE_SCRATCH_MB=512   bridge scratch budget (MiB)
    DSV41_FP4_BRIDGE_STATS=0   bridge telemetry period (0 = off)
    [R1] DSV41_FP4KV_R1_INKERNEL=0|1   prefill in-kernel fp4 read (strict
        boolean: any other value refuses to install = refuse-boot law)

Install seams (one install() per sglang module, called from the adapter's
module-exec hook -- the sitecustomize patch is in the design card, pending
approval; until then call kv_fp4.install(module) manually or from a test):
    sglang.srt.mem_cache.deepseek_v4_memory_pool
        select_dsv4_kv_layout: recognize "fork-v4-fp4" -> (V4, "fp4")
        resolve_compressed_kv_layout: (V4, option=fp4) -> V41_FP4 for
            ratio 1/2 (the fp4-rounded latents), V4 for 4/128
        is_valid_kv_layout_pair (module-local rebind): accept the
            bridge-consumed (V4, V41_FP4) pair, mirroring the fork's
            is_valid_fork_kv_layout_pair
    sglang.srt.mem_cache.kv_cache_configurator
        rebind its top-imported select_dsv4_kv_layout (from-import binding)
    sglang.srt.model_executor.pool_configurator
        DSV4PoolConfigurator._compressed_bytes_per_full_token: price ratio-1/2
            slots at the V41_FP4 page bytes (288) instead of self.kv_bytes
            (584) -- the 890 B/full-token accounting -- plus the fork's SM120
            fail-fast (the fp4 pools are only readable through the bridge)
    sglang.kernels.ops.attention.flash_mla_sm120
        wrap flash_mla_with_kvcache_sm120: fp4 extra caches (last dim 288)
        are bridged into the persistent V4 scratch with query slicing before
        the real kernel runs; the SM121 auto policy (which would keep
        everything at V4 fp8) is overridden by the injected mode, not here.

Everything degrades to stock main when the gate is off: install() returns
without touching the module, and the patched functions delegate to the
originals whenever the mode is not "fork-v4-fp4".
"""

import logging
import os
import sys

_logger = logging.getLogger(__name__)

GATE_ENV = "DSV41_FP4KV_PORT"
MODE_ENV = "SGLANG_DSV4_KV_LAYOUT"
FORK_MODE = "fork-v4-fp4"

# --- [R1] in-kernel prefill key (strict boolean, default OFF) ----------------
R1_ENV = "DSV41_FP4KV_R1_INKERNEL"
_R1_ON = ("1", "on", "true", "yes")
_R1_OFF = ("", "0", "off", "false", "no")


def _parse_r1_key() -> bool:
    """Strict boolean parse; anything outside both sets refuses install
    (refuse-boot law, W5 TAIL_GATHER precedent: silent typo must not arm a
    kernel-swap path nor silently disable an intended arm)."""
    raw = os.environ.get(R1_ENV)
    val = "" if raw is None else raw.strip().lower()
    if val in _R1_ON:
        return True
    if val in _R1_OFF:
        return False
    raise RuntimeError(
        f"{R1_ENV}={raw!r}: strict boolean key ("
        + "|".join(_R1_ON + _R1_OFF or ["1", "0"])
        + "); refusing to install"
    )


def r1_inkernel() -> bool:
    """[R1] The in-kernel prefill key (parse is strict; failure propagates)."""
    return _parse_r1_key()

_ON = ("1", "on", "true", "yes")
_INSTALLED = set()


def enabled() -> bool:
    """The port's gate (DSV41_FP4KV_PORT). Off unless explicitly armed."""
    return os.environ.get(GATE_ENV, "").strip().lower() in _ON


def fork_mode() -> bool:
    """SGLANG_DSV4_KV_LAYOUT resolves to the fork mode."""
    return os.environ.get(MODE_ENV, "v4").strip().lower() == FORK_MODE


def active() -> bool:
    """The port both armed and in fork mode (patches take effect)."""
    return enabled() and fork_mode()


def _deploy_conflict() -> str:
    """GB10-3②/GB10-4①: deployment configs the armed port must refuse. trtllm
    reads compressed pools with no bridge; hicache host transfers assume the
    584 B layout for every pool they move. Both are argv/env facts, so they are
    checked at install time, uniformly by every installer -- a partial install
    (288 pools with no bridge) is the failure mode this exists to prevent."""
    for i, a in enumerate(sys.argv):
        val = ""
        if a == "--dsv4-attn-backend" and i + 1 < len(sys.argv):
            val = sys.argv[i + 1]
        elif a.startswith("--dsv4-attn-backend="):
            val = a.split("=", 1)[1]
        if val.strip().lower() == "trtllm":
            return "--dsv4-attn-backend trtllm reads compressed pools with no bridge"
        # A1-F1/A3-W1: main enables hierarchical/lm cache via CLI flags, not env
        # (SGLANG_ENABLE_HIERARCHICAL_CACHE does not exist on main) -- the env-only
        # scan below let the exact hazard this check exists for slip through.
        if (a == "--enable-hierarchical-cache" or a == "--enable-lmcache"
                or a.startswith("--hicache-")):
            return f"{a}: host transfers assume 584 B pools (CLI flag)"
    hicache = sorted(k for k in os.environ if k.startswith("SGLANG_HICACHE_")
                     or k == "SGLANG_ENABLE_HIERARCHICAL_CACHE")
    if hicache:
        return f"hierarchical-cache env present {hicache[:3]}: host transfers assume 584 B pools"
    return ""


def _refuse_conflicts() -> bool:
    why = _deploy_conflict()
    if why:
        _logger.error("DSV41_FP4KV_PORT armed but %s -- refusing install", why)
        return True
    return False


def _inject_mode() -> None:
    """The SM121 auto-mode override point: arm implies the fork mode unless the
    operator set an explicit (winning) SGLANG_DSV4_KV_LAYOUT."""
    if MODE_ENV not in os.environ:
        os.environ[MODE_ENV] = FORK_MODE
        _logger.info(
            "%s=1: injected %s=%s (SM121 auto policy would stay V4 fp8)",
            GATE_ENV, MODE_ENV, FORK_MODE,
        )
    elif not fork_mode():
        _logger.warning(
            "%s=1 but %s=%r is explicit: fp4-KV patches stay passthrough",
            GATE_ENV, MODE_ENV, os.environ[MODE_ENV],
        )


def install_environ_keys() -> bool:
    """Best-effort: register the bridge env keys on sglang's Envs class so
    `envs.<KEY>.get()` works like on the fork. Returns True when registered.
    kv_fp4_repack reads the process env directly, so this is discoverability,
    not a dependency."""
    try:
        from sglang.srt.environ import Envs, EnvInt
    except Exception as exc:  # pragma: no cover - sglang not importable offline
        _logger.debug("environ key registration skipped: %s", exc)
        return False
    for key, default in (
        ("SGLANG_DSV4_FP4_BRIDGE_SCRATCH_MB", 512),
        ("DSV41_FP4_BRIDGE_STATS", 0),
    ):
        if not hasattr(Envs, key):
            field = EnvInt(default)
            field.name = key  # __set_name__ only fires for class-body decls
            setattr(Envs, key, field)
    return True


# --- layout patches (memory_pool namespace) ---------------------------------


def install_memory_pool(module) -> bool:
    """Patch select/resolve/pair-validity in sglang.srt.mem_cache.
    deepseek_v4_memory_pool. Idempotent; inert when the gate is off."""
    if not enabled() or module.__name__ in _INSTALLED:
        return False
    if _refuse_conflicts():
        return False
    _inject_mode()
    KVLayout = module.KVLayout
    orig_select = module.select_dsv4_kv_layout
    orig_resolve = module.resolve_compressed_kv_layout
    orig_valid = module.is_valid_kv_layout_pair

    def select_dsv4_kv_layout():
        # The fork mode keeps the 584 B V4 main/SWA caches (the only layout
        # our FlashInfer reader accepts) and flags the compressed pools fp4;
        # every other mode goes to the stock selector untouched.
        if fork_mode():
            return KVLayout.V4, "fp4"
        return orig_select()

    def resolve_compressed_kv_layout(kv_layout, compress_ratio, option=None):
        if kv_layout is KVLayout.V4 and option == "fp4" and fork_mode():
            # Ratio-1/2 latents are e2m1-rounded by the model, so V41_FP4 is
            # lossless for them; ratio 4/128 are not fp4-rounded and stay V4.
            return KVLayout.V41_FP4 if compress_ratio in (1, 2) else KVLayout.V4
        return orig_resolve(kv_layout, compress_ratio, option)

    def is_valid_kv_layout_pair(kv, extra_kv):
        if kv is KVLayout.V4 and extra_kv is KVLayout.V41_FP4 and fork_mode():
            return True  # consumed through the SM120/121 repack bridge
        return orig_valid(kv, extra_kv)

    module.select_dsv4_kv_layout = select_dsv4_kv_layout
    module.resolve_compressed_kv_layout = resolve_compressed_kv_layout
    module.is_valid_kv_layout_pair = is_valid_kv_layout_pair
    _INSTALLED.add(module.__name__)
    # Self-healing order: a from-importer that bound the stock selector before
    # this patch (import order is normally memory_pool first, but a test or a
    # reordered import can flip it) is rebound to the patched one now.
    import sys

    bound = sys.modules.get("sglang.srt.mem_cache.kv_cache_configurator")
    if bound is not None and bound.select_dsv4_kv_layout is orig_select:
        bound.select_dsv4_kv_layout = select_dsv4_kv_layout
    _logger.info(
        "kv_fp4: memory_pool patched (fork-v4-fp4; V4 main/SWA + V41_FP4 ratio-1/2)"
    )
    return True


def install_kv_cache_configurator(module) -> bool:
    """Rebind the top-imported select_dsv4_kv_layout in
    sglang.srt.mem_cache.kv_cache_configurator (a `from` import binds its own
    name, so patching the source module is not enough)."""
    if not enabled() or module.__name__ in _INSTALLED:
        return False
    if _refuse_conflicts():
        return False
    _inject_mode()
    if not _ensure_memory_pool_patched():
        return False
    import sglang.srt.mem_cache.deepseek_v4_memory_pool as _mp
    module.select_dsv4_kv_layout = _mp.select_dsv4_kv_layout
    _INSTALLED.add(module.__name__)
    return True


def _ensure_memory_pool_patched() -> bool:
    """The layout patches are the port's root: every other seam reads layouts
    through memory_pool's selectors (pool_configurator does an in-function
    import of them), so an armed gate with an unpatched memory_pool would feed
    'fork-v4-fp4' to the stock selector and crash. Call this from each
    installer; returns True when the root patch is in place."""
    try:
        import sglang.srt.mem_cache.deepseek_v4_memory_pool as _mp
    except Exception as exc:
        _logger.warning("kv_fp4: memory_pool import failed: %s", exc)
        return False
    if _mp.__name__ in _INSTALLED:
        return True
    return install_memory_pool(_mp)


def install_pool_configurator(module) -> bool:
    """Patch DSV4PoolConfigurator accounting: ratio-1/2 slots priced at the
    V41_FP4 page bytes (288) instead of self.kv_bytes (584) -- this is the
    890 B/full-token ledger ((288+68) x 2.5) -- plus the fork's SM120
    fail-fast."""
    if not enabled() or module.__name__ in _INSTALLED:
        return False
    if _refuse_conflicts():
        return False
    _inject_mode()
    if not _ensure_memory_pool_patched():
        return False
    cls = getattr(module, "DSV4PoolConfigurator", None)
    if cls is None or not hasattr(cls, "_compressed_bytes_per_full_token"):
        _logger.warning("kv_fp4: DSV4PoolConfigurator anchor missing; no patch")
        return False
    orig = cls._compressed_bytes_per_full_token

    def _compressed_bytes_per_full_token(self, ratio):
        if ratio in (1, 2) and active():
            from sglang.srt.mem_cache.deepseek_v4_memory_pool import (
                resolve_compressed_kv_layout,
                select_dsv4_kv_layout,
            )

            layout, option = select_dsv4_kv_layout()
            layout = resolve_compressed_kv_layout(layout, ratio, option)
            page_size = self.page_size // ratio
            kv_b = layout.page_bytes(page_size) / page_size  # 288.0 exactly
            # Fail fast: the fp4 compressed pools are readable only through
            # the SM120/121 repack bridge (mirror of the fork's assert).
            try:
                from sglang.srt.runtime_context import get_platform

                assert get_platform().is_sm120, (
                    "SGLANG_DSV4_KV_LAYOUT=fork-v4-fp4 (V41_FP4 compressed KV) "
                    "requires the SM120/121 sparse-MLA reader; the repack bridge "
                    "is SM120-only"
                )
            except ImportError:
                pass
            return (kv_b + self.low_ratio_index_bytes) / ratio
        return orig(self, ratio)

    cls._compressed_bytes_per_full_token = _compressed_bytes_per_full_token
    _INSTALLED.add(module.__name__)
    _logger.info("kv_fp4: DSV4PoolConfigurator low-ratio accounting at V41_FP4 bytes")
    return True


def install_flash_mla_sm120(module) -> bool:
    """Wrap the SM120/121 sparse-MLA entry point with the fp4 repack bridge.

    This is the port's one structural deviation from the fork: fin2 spliced
    the bridge at the backend call site (its _flash_mla_sm120_once seam); on
    main the call is inline in a ~200-line _forward_attention with no method
    seam, but it is a function-local import, so patching the module attribute
    intercepts every call with the same arguments the fork's seam saw. The
    bridge sees the 4D (pages, page_size, 1, 288) view the backend built, so
    the source page size (256 for ratio-1 / 128 for ratio-2) is derivable.
    Passthrough (same object, same return) for every non-fp4 call."""
    if not enabled() or module.__name__ in _INSTALLED:
        return False
    if _refuse_conflicts():
        return False
    _inject_mode()
    if not _ensure_memory_pool_patched():
        return False
    orig = module.flash_mla_with_kvcache_sm120
    import torch

    from kv_fp4_repack import (
        bridge_max_rows,
        bridge_note_call,
        bridge_note_slices,
        bridge_slice_bounds,
        bridge_stats_period,
        bridge_time_enabled,
        repack_fp4_extra_to_v4,
    )

    try:
        from sglang.kernels.ops.attention.dsv4.kv_layout import KVLayout

        fp4_bpt = KVLayout.V41_FP4.bytes_per_token  # 288
    except Exception:
        fp4_bpt = 288

    # [R1] strict key parse at install: bogus value refuses boot here.
    _r1 = {
        "armed": _parse_r1_key(),
        "available": None,  # None = untried; True = fork usable; False = permanent fallback
        "checked": False,   # fail-safe dual-run done
    }

    def _r1_fork_call(mod, kwargs, rows=None):
        """One fork-kernel prefill call. Mirrors _flash_mla_sm120_prefill
        (flash_mla_sm120.py:215-267) with the extra tensors passed RAW.
        ``rows`` limits the call to the first N query rows (per-query softmax
        independence = the bridge slicing law), used by the fail-safe gate."""
        import torch

        import fi_r1

        q = kwargs["q"]
        if rows is not None:
            q = q[:rows]
        q2 = q.squeeze(1) if q.ndim == 4 else q
        k_cache = kwargs["k_cache"]
        kv_u8 = k_cache.view(torch.uint8) if k_cache.dtype != torch.uint8 else k_cache
        src_pbs = k_cache.shape[1] if k_cache.ndim >= 3 else mod._PBS_SRC
        idx = kwargs["indices"]
        idx = idx.squeeze(1) if idx.dim() == 3 else idx
        if rows is not None:
            idx = idx[:rows]
        kv_64 = (
            mod._split_kv_pages_to_64(kv_u8, src_pbs, touched_indices=idx)
            if src_pbs != mod._PBS_DST
            else kv_u8
        )
        extra = kwargs["extra_k_cache"]
        extra_u8 = extra.view(torch.uint8) if extra.dtype != torch.uint8 else extra
        eidx = kwargs["extra_indices_in_kvcache"]
        eidx = eidx.squeeze(1) if eidx.dim() == 3 else eidx
        if rows is not None:
            eidx = eidx[:rows]
        etl = kwargs.get("extra_topk_length")
        if rows is not None and etl is not None:
            etl = etl[:rows]
        tl = kwargs.get("topk_length")
        if rows is not None and tl is not None:
            tl = tl[:rows]
        num_tokens, num_heads, _ = q2.shape
        # [R1-FORMAL/KA-C4] grow-only persistent buffers: the fork kernel
        # fully overwrites output and out_lse in place (same contract as the
        # stock FFI out-params the base form fed fresh empty tensors to), so
        # reuse is bit-identical by construction while removing the 2x
        # per-call allocation of the ~68 MiB variable-size output.
        from kv_fp4_repack import _persistent_buffer

        output = _persistent_buffer(
            "r1:prefill:out",
            (num_tokens, num_heads, kwargs["head_dim_v"]),
            torch.bfloat16,
            q2.device,
        )
        out_lse = _persistent_buffer(
            "r1:prefill:lse",
            (num_tokens, num_heads),
            torch.float32,
            q2.device,
        )
        scale = kwargs.get("softmax_scale")
        if scale is None:
            scale = q.shape[-1] ** (-0.5)
        fi_r1.r1_fp4kv_prefill(
            q2,
            kv_64,
            idx,
            output,
            out_lse,
            scale,
            topk_length=tl,
            attn_sink=kwargs.get("attn_sink"),
            extra_kv_cache=extra_u8,
            extra_indices=eidx,
            extra_topk_length=etl,
        )
        return output, out_lse

    def _r1_oracle_call(mod, kwargs, rows):
        """Repack+stock-kernel oracle on the same prefix rows (the in-service
        path's exact arithmetic: repack_fp4_extra_to_v4 + the stock FFI with
        identity ids). Same-input oracle law (design card sec 4.3)."""
        import torch

        from flashinfer.mla._sparse_mla_sm120 import _sparse_mla_sm120_paged_attention

        from kv_fp4_repack import repack_fp4_extra_to_v4

        q = kwargs["q"][:rows]
        q2 = q.squeeze(1) if q.ndim == 4 else q
        k_cache = kwargs["k_cache"]
        kv_u8 = k_cache.view(torch.uint8) if k_cache.dtype != torch.uint8 else k_cache
        src_pbs = k_cache.shape[1] if k_cache.ndim >= 3 else mod._PBS_SRC
        idx = kwargs["indices"]
        idx = idx.squeeze(1) if idx.dim() == 3 else idx
        idx = idx[:rows]
        kv_64 = (
            mod._split_kv_pages_to_64(kv_u8, src_pbs, touched_indices=idx)
            if src_pbs != mod._PBS_DST
            else kv_u8
        )
        extra = kwargs["extra_k_cache"]
        extra_u8 = extra.view(torch.uint8) if extra.dtype != torch.uint8 else extra
        eidx = kwargs["extra_indices_in_kvcache"]
        eidx = eidx.squeeze(1) if eidx.dim() == 3 else eidx
        src_pool_pbs = extra.shape[1]
        scratch, bridged = repack_fp4_extra_to_v4(extra_u8, eidx[:rows], src_pool_pbs)
        etl = kwargs.get("extra_topk_length")
        if etl is not None:
            etl = etl[:rows]
        tl = kwargs.get("topk_length")
        if tl is not None:
            tl = tl[:rows]
        num_tokens, num_heads, _ = q2.shape
        output = q2.new_empty(
            (num_tokens, num_heads, kwargs["head_dim_v"]), dtype=torch.bfloat16
        )
        out_lse = torch.empty(
            (num_tokens, num_heads), dtype=torch.float32, device=q2.device
        )
        scale = kwargs.get("softmax_scale")
        if scale is None:
            scale = q.shape[-1] ** (-0.5)
        _sparse_mla_sm120_paged_attention(
            q2,
            kv_64,
            idx,
            output,
            out_lse,
            scale,
            topk_length=tl,
            attn_sink=kwargs.get("attn_sink"),
            extra_kv_cache=scratch,
            extra_indices=bridged,
            extra_topk_length=etl,
            mid_out=None,
            mid_lse=None,
        )
        return output, out_lse

    def _r1_failsafe(mod, kwargs):
        """First-eligible-block dual-run gate: fork vs repack+stock on a
        bounded prefix; torch.equal on output AND LSE. Mismatch or fork-side
        exception = permanent fallback + loud banner (A23-beta law)."""
        import torch

        rows = min(int(kwargs["q"].shape[0]), 256)
        try:
            f_out, f_lse = _r1_fork_call(mod, kwargs, rows)
            o_out, o_lse = _r1_oracle_call(mod, kwargs, rows)
            ok = bool(
                torch.equal(f_out, o_out) and torch.equal(f_lse, o_lse)
            )
        except Exception as exc:  # noqa: BLE001 - any failure falls back
            _logger.error(
                "DSV41_FP4KV_R1_INKERNEL fail-safe dual-run raised (%s: %s); "
                "PERMANENT KEY-LEVEL FALLBACK to the repack bridge for this "
                "process",
                type(exc).__name__,
                exc,
            )
            _r1["available"] = False
            _r1["checked"] = True
            return
        _r1["checked"] = True
        if not ok:
            _logger.error(
                "DSV41_FP4KV_R1_INKERNEL fail-safe MISMATCH on first prefill "
                "block (fork vs repack+stock outputs differ); PERMANENT "
                "KEY-LEVEL FALLBACK to the repack bridge for this process"
            )
            _r1["available"] = False
        else:
            _r1["available"] = True
            _logger.info(
                "DSV41_FP4KV_R1_INKERNEL fail-safe dual-run PASS (rows=%d): "
                "fork kernel bit-equal to repack+stock on output+LSE", rows
            )

    def _r1_try_prefill(mod, kwargs):
        """Route a prefill-shaped fp4 call to the fork kernel. Returns the
        entry-shaped return value, or None when the path is (now) disabled —
        the caller then falls through to the in-service bridge body."""
        if _r1["available"] is False:
            return None
        if not _r1["checked"]:
            _r1_failsafe(mod, kwargs)
            if _r1["available"] is False:
                return None
        try:
            out, _lse = _r1_fork_call(mod, kwargs)
        except Exception as exc:  # noqa: BLE001
            _logger.error(
                "DSV41_FP4KV_R1_INKERNEL fork call failed after fail-safe pass "
                "(%s: %s); PERMANENT KEY-LEVEL FALLBACK to the repack bridge",
                type(exc).__name__,
                exc,
            )
            _r1["available"] = False
            return None
        return (out.unsqueeze(1), None)

    def flash_mla_with_kvcache_sm120(**kwargs):
        extra = kwargs.get("extra_k_cache")
        if extra is None or not fork_mode():
            return orig(**kwargs)
        if extra.shape[-1] != fp4_bpt:
            return orig(**kwargs)
        # GB10-3①: independent platform check at the first real 288 input.
        # The pool-accounting patch above already fails fast, but a
        # half-installed state (root patched, accounting patch missing) must
        # not silently feed 288 B pages to a platform with no 584 reader.
        from sglang.srt.runtime_context import get_platform

        if not get_platform().is_sm120:
            raise RuntimeError(
                "DSV41_FP4KV_PORT: 288 B/token V41_FP4 extra cache reached the "
                "sparse-MLA entry on a non-SM120/121 platform; the V4-584 "
                "reader only ships on sm120/121 -- refusing instead of misreading"
            )
        # A raw 288 B/token V41_FP4 extra cache reached the SM120/121
        # sparse-MLA kernel; it reads the 584-byte V4 form only, so bridge it.
        # [R1] key-armed prefill face: consume the pool in-kernel instead
        # (fail-safe gated; None = fell back → the bridge body below).
        if (
            _r1["armed"]
            and kwargs["q"].shape[0] > module.SM120_DECODE_MAX_TOKENS
        ):
            routed = _r1_try_prefill(module, kwargs)
            if routed is not None:
                return routed
        q = kwargs["q"]
        extra_indices = kwargs["extra_indices_in_kvcache"]
        extra_topk_lengths = kwargs.get("extra_topk_length")
        indices = kwargs.get("indices")
        topk_length = kwargs.get("topk_length")
        attn_sink = kwargs.get("attn_sink")
        src_page_size = extra.shape[1]  # 256 (ratio-1) / 128 (ratio-2)

        slice_bounds = bridge_slice_bounds(q.shape[0], extra_indices.shape[-1])
        bridge_note_slices(len(slice_bounds) - 1)
        # Telemetry only (DSV41_FP4_BRIDGE_STATS, off by default). real_rows
        # needs a host sync on topk_lengths, so it is taken for eager extends
        # only -- never inside graph capture.
        _nq = q.shape[0]
        _topk = int(extra_indices.shape[-1])
        _real, _t0, _tmid, _t1 = -1, None, None, None
        if (
            extra_topk_lengths is not None
            and _nq > module.SM120_DECODE_MAX_TOKENS
            and not torch.cuda.is_current_stream_capturing()
            and bridge_time_enabled()
        ):
            _real = int(extra_topk_lengths.clamp(max=_topk).sum().item())
            _t0 = torch.cuda.Event(enable_timing=True)
            _tmid = torch.cuda.Event(enable_timing=True)
            _t1 = torch.cuda.Event(enable_timing=True)
            _t0.record()
        if len(slice_bounds) == 2:
            scratch, bridged = repack_fp4_extra_to_v4(
                extra, extra_indices, src_page_size
            )
            if _tmid is not None:
                _tmid.record()
            out = orig(
                **dict(kwargs, extra_k_cache=scratch, extra_indices_in_kvcache=bridged)
            )
        else:
            parts = []
            for lo, hi in zip(slice_bounds[:-1], slice_bounds[1:]):
                scratch, bridged = repack_fp4_extra_to_v4(
                    extra, extra_indices[lo:hi], src_page_size
                )
                kwargs_slice = dict(
                    kwargs,
                    q=q[lo:hi],
                    extra_k_cache=scratch,
                    extra_indices_in_kvcache=bridged,
                )
                if indices is not None:
                    kwargs_slice["indices"] = indices[lo:hi]
                if topk_length is not None:
                    kwargs_slice["topk_length"] = topk_length[lo:hi]
                if extra_topk_lengths is not None:
                    kwargs_slice["extra_topk_length"] = extra_topk_lengths[lo:hi]
                parts.append(orig(**kwargs_slice)[0])
            if _tmid is not None:
                _tmid.record()
            out = parts[0] if len(parts) == 1 else torch.cat(parts, dim=0)
            out = (out,)  # keep the kernel's indexable return shape
        if _t0 is None:
            if bridge_stats_period():
                bridge_note_call(_nq, _topk, -1, 0.0, 0.0)
        else:
            _t1.record()
            torch.cuda.synchronize()
            bridge_note_call(
                _nq, _topk, _real,
                _t0.elapsed_time(_tmid) * 1000.0,
                _tmid.elapsed_time(_t1) * 1000.0,
            )
        return out

    module.flash_mla_with_kvcache_sm120 = flash_mla_with_kvcache_sm120
    _INSTALLED.add(module.__name__)
    _logger.info(
        "kv_fp4: fp4->V4 repack bridge installed at flash_mla_sm120 entry "
        "(max_rows=%d)", bridge_max_rows(),
    )
    return True


_INSTALLERS = {
    "sglang.srt.mem_cache.deepseek_v4_memory_pool": install_memory_pool,
    "sglang.srt.mem_cache.kv_cache_configurator": install_kv_cache_configurator,
    "sglang.srt.model_executor.pool_configurator": install_pool_configurator,
    "sglang.kernels.ops.attention.flash_mla_sm120": install_flash_mla_sm120,
}


def install(module) -> bool:
    """Dispatch by module name; the sitecustomize hook form (default off)."""
    installer = _INSTALLERS.get(getattr(module, "__name__", ""))
    if installer is None:
        return False
    return installer(module)


def verify_all_installed() -> None:
    """Boot-end completeness check (A1-F3): an armed gate with any seam still
    un-installed is a half-install -- 288 pools with no bridge, or a bridge over
    stock pools -- and both misread silently. Call once after the engine's
    module graph is imported (sitecustomize wiring / t44); raises on gap."""
    if not enabled():
        return
    missing = sorted(n.rsplit(".", 1)[-1] for n in _INSTALLERS
                     if n not in _INSTALLED)
    if missing:
        raise RuntimeError(
            f"DSV41_FP4KV_PORT armed but seams not installed: {missing} "
            "-- refusing to run half-installed"
        )


def summary() -> str:
    """Banner fact line: gate, mode, and which seams took, without a GPU."""
    try:
        r1 = f"r1_inkernel={_parse_r1_key()}"
    except RuntimeError as exc:
        r1 = f"r1_inkernel=INVALID({exc})"
    return (
        f"gate={os.environ.get(GATE_ENV, '(off)')} "
        f"mode={os.environ.get(MODE_ENV, '(v4 default)')} "
        f"active={active()} "
        f"installed={','.join(sorted(_INSTALLED)) or '(none)'} "
        f"{r1} r1_formal=1"
    )
