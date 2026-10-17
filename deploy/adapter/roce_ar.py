"""I14-A (C1): RoCEnante TP all-reduce face on stock main-79cafec0.

The old fork carried a pure 67-line RoCE delta inside pynccl.py plus two hooks in
parallel_state.py (roce_enabled=(group_name == "tp") at PyNcclCommunicator
construction, maybe_roce_context = pynccl_comm.roce_capture(stream) inside
GroupCoordinator.graph_capture). Stock main-79cafec0 has none of it. This adapter
reimplements that delta as import-time monkey patches, so the RoCE arm needs no
image change:

  install(module)              -- hook on sglang...device_communicators.pynccl
                                  wraps PyNcclCommunicator.__init__ / all_reduce /
                                  outplace_all_reduce, attaches roce_capture() and
                                  _should_roce(), and exports
                                  synchronize_and_check_roce into the module
                                  namespace for the I14-C scheduler wiring.
  install_parallel_state(mod)  -- hook on sglang.srt.distributed.parallel_state
                                  wraps GroupCoordinator.__init__ (remembers the
                                  group_name being built; only "tp" arms RoCE) and
                                  GroupCoordinator.graph_capture (opens the b12x
                                  capture context around the yield, inside the
                                  pynccl/pymscclpp change_state contexts, same
                                  nesting as the fork).
                                  Import-order independent: parallel_state loads
                                  first in the engine (distributed/__init__.py),
                                  pynccl lazily from GroupCoordinator.__init__ --
                                  both hooks arm on the env gates alone.

Routing (fork semantics, kept verbatim): the RoCE one-shot kernel only sees calls
while the pynccl communicator is enabled -- inside CUDA graph capture, or the few
eager sites that enter change_state(enable=True) explicitly. Eligibility is
op == SUM, dtype in (bf16, fp32) and runtime.should_allreduce (<= max_size =
SGLANG_ROCE_MAX_SIZE, 16-byte multiple); everything else falls back to NCCL.
The runtime is created from the TP group's Gloo exchange group at communicator
construction -- i.e. BEFORE any graph capture -- and prepare() compiles the
launchers there, as the b12x capture context requires.

Gates: DSV41_ROCE_RING=1 and SGLANG_ROCE_ALLREDUCE=1 both required at import
(sitecustomize reads them before calling install()); install() re-checks and
refuses loudly unless TP_SIZE=4. On NCCL arms (either key unset) nothing wraps
and this module is inert.
"""
import json
import logging
import os
import weakref
from contextlib import contextmanager, nullcontext

logger = logging.getLogger(__name__)

ROCE_AR_VERSION = "c1-i14a-1"

# Runtimes ever armed (weak: die with their communicator). synchronize_and_check_roce
# walks this set -- same WeakSet the fork kept at pynccl module level.
_roce_runtimes = weakref.WeakSet()

# made/kept counters: communicators seen, runtimes made, AR calls routed to the
# one-shot kernel vs kept on NCCL. stats() is the operator surface.
STATS = {"communicators": 0, "roce_made": 0, "roce_routed": 0, "nccl_kept": 0}

# Set by the GroupCoordinator.__init__ wrap while a coordinator is being built:
# the group_name of THAT construction, so the PyNcclCommunicator.__init__ wrap
# (called synchronously inside it) can replicate the fork's
# roce_enabled=(group_name == "tp") without touching the engine class signature.
_group_name_stack = []

_pynccl_module = None          # the wrapped pynccl module, for the health hook
_ar_dtypes = None              # (bf16, fp32), resolved at install time
_ReduceOp = None               # torch.distributed.ReduceOp, resolved at install time


def _flag(name):
    return os.environ.get(name, "0").strip() == "1"



def _roce_module_name():
    # Switch topology has direct reachability between every peer on both rails.
    # Keep the original RoCE arm, safety hooks, graph lifecycle and health checks;
    # select the image's existing, independently qualified one-shot runtime.
    if _flag('LUZ_SWITCH_ROCE_FLAT'):
        return 'b12x.comm.roce'
    return 'b12x.comm.roce_ring' if _flag('DSV41_ROCE_RING') else 'b12x.comm.roce'


def gates_on():
    """Both import-time gates (DSV41_ROCE_RING, SGLANG_ROCE_ALLREDUCE) set to 1."""
    return _flag("DSV41_ROCE_RING") and _flag("SGLANG_ROCE_ALLREDUCE")


def stats():
    """Counter snapshot plus the armed-runtime count, for banners and audits."""
    return dict(STATS, runtimes=len(_roce_runtimes), version=ROCE_AR_VERSION)


def synchronize_and_check_roce(copy_done):
    """Finish this result before checking transport health or consuming output.

    Verbatim semantics of the fork's pynccl module-level hook (consumed there by
    batch_result_processor). Placeholder surface for the I14-C joint-test window:
    wire the scheduler to this once the RoCE arm is stable.
    """
    if copy_done is not None:
        copy_done.synchronize()
    elif _roce_runtimes:
        # Non-overlap paths have no copy event. Complete all forward streams
        # before reading the host failure word; an early check is insufficient.
        import torch

        torch.cuda.synchronize()
    for runtime in tuple(_roce_runtimes):
        runtime.check_health()
        if not getattr(runtime, "_sglang_post_result_logged", False):
            logger.info("ROCE_POST_RESULT_HEALTH %s", json.dumps(runtime.stats()))
            runtime._sglang_post_result_logged = True


def _banner(line):
    # print + logger: the boot-log acceptance reads stdout banners (sitecustomize
    # convention), the logger line lands in the engine log with timestamps.
    print(f"[roce_ar] {line}", flush=True)
    logger.info("ROCE_AR %s", line)


def _should_roce(self, tensor, op):
    """Fork _should_roce: eligible = SUM + (bf16|fp32) + runtime.should_allreduce."""
    roce = getattr(self, "roce", None)
    if roce is None:
        return False
    roce.check_health()
    eligible = (
        op == _ReduceOp.SUM
        and tensor.dtype in _ar_dtypes
        and roce.should_allreduce(tensor)
    )
    if eligible and not self._roce_route_logged:
        nbytes = tensor.numel() * tensor.element_size()
        _banner(
            f"ROCE_TP8_ROUTE rank={self.rank} dtype={tensor.dtype} bytes={nbytes} "
            f"max_size={roce.max_size}"
        )
        self._roce_route_logged = True
    return eligible


def _roce_capture(self, stream):
    """Fork roce_capture: the b12x capture context, or a no-op without a runtime."""
    if getattr(self, "roce", None) is not None:
        return self.roce.capture(stream=stream)
    return nullcontext()


def install(module):
    """Wrap PyNcclCommunicator on the pynccl module. Inert on NCCL arms.

    MUST be installed before roce_gather.install on the same class: roce_gather's
    __init__ wrap reads self.roce in its post-init, and this adapter is the one
    that creates it (last-installed wrap runs outermost).
    """
    global _pynccl_module, _ar_dtypes, _ReduceOp

    if not gates_on():
        return False  # NCCL arm: not even a banner, same discipline as roce_gather

    tp_size = os.environ.get("TP_SIZE", "").strip()
    if tp_size != "4":
        _banner(
            f"REFUSED: TP_SIZE={tp_size!r} (need 4); TP all-reduce stays on NCCL. "
            f"version={ROCE_AR_VERSION}"
        )
        return False

    import torch

    cls = module.PyNcclCommunicator
    _ar_dtypes = (torch.bfloat16, torch.float32)
    _ReduceOp = module.ReduceOp  # torch.distributed.ReduceOp, as pynccl imports it
    orig_init, orig_ar, orig_out_ar = cls.__init__, cls.all_reduce, cls.outplace_all_reduce

    def __init__(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        # Fork hunk: every communicator carries roce=None until the TP one arms.
        self.roce = None
        self._roce_route_logged = False
        STATS["communicators"] += 1
        if not _group_name_stack or _group_name_stack[-1] != "tp":
            return  # fork: roce_enabled=(group_name == "tp")
        if self.world_size == 1:
            return
        if not (_flag("SGLANG_ROCE_ALLREDUCE") or _flag("SGLANG8_ROCE_ALLREDUCE")):
            return
        import importlib

        from sglang.srt.distributed.utils import StatelessProcessGroup

        if self.world_size not in (4, 8) or isinstance(self.group, StatelessProcessGroup):
            raise RuntimeError("RoCEnante route needs the TP4/TP8 Gloo exchange group")
        mod_name = _roce_module_name()
        roce_mod = importlib.import_module(mod_name)
        max_size = int(os.environ.get("SGLANG_ROCE_MAX_SIZE", str(512 * 1024)))
        self.roce = roce_mod.AllReduce.from_exchange_group(
            exchange_group=self.group,
            device=self.device,
            max_size=max_size,
            max_gather_bytes=0,
        )
        self.roce.prepare((torch.bfloat16, torch.float32))
        if len(self.roce.hca_names) < 1:
            raise RuntimeError("RoCEnante found no active RoCE interface")
        if len(self.roce.hca_names) == 1:
            logger.warning("ROCE single-rail: %s", self.roce.hca_names)
        _roce_runtimes.add(self.roce)
        STATS["roce_made"] += 1
        # Fork log line, kept verbatim for census comparability; print so the
        # boot-log acceptance sees it even before logging is configured.
        ready = f"ROCE_TP8_READY {json.dumps(self.roce.stats())}"
        print(f"[roce_ar] {ready}", flush=True)
        logger.info("%s", ready)

    def all_reduce(self, tensor, op=_ReduceOp.SUM):
        if self.disabled:
            return  # pynccl disabled = outside the graph window: NCCL, as main
        if _should_roce(self, tensor, op):
            assert tensor.device == self.device, (
                f"this nccl communicator is created to work on {self.device}, "
                f"but the input tensor is on {tensor.device}"
            )
            STATS["roce_routed"] += 1
            self.roce.all_reduce(tensor, out=tensor, stream=self._resolve_stream())
            return
        STATS["nccl_kept"] += 1
        return orig_ar(self, tensor, op)

    def outplace_all_reduce(self, in_tensor, out_tensor=None, op=_ReduceOp.SUM):
        if self.disabled:
            return None
        if _should_roce(self, in_tensor, op):
            if out_tensor is None:
                out_tensor = torch.empty_like(in_tensor)
            STATS["roce_routed"] += 1
            return self.roce.all_reduce(
                in_tensor, out=out_tensor, stream=self._resolve_stream()
            )
        STATS["nccl_kept"] += 1
        return orig_out_ar(self, in_tensor, out_tensor, op)

    cls.__init__, cls.all_reduce, cls.outplace_all_reduce = __init__, all_reduce, outplace_all_reduce
    cls.roce_capture, cls._should_roce = _roce_capture, _should_roce
    # Fork-lineage consumers import this from pynccl; I14-C wires the scheduler to it.
    module.synchronize_and_check_roce = synchronize_and_check_roce
    module.roce_ar_stats = stats
    _pynccl_module = module
    _banner(
        f"armed pynccl face: backend={_roce_module_name().rsplit('.', 1)[-1]} "
        f"max_size={os.environ.get('SGLANG_ROCE_MAX_SIZE', str(512 * 1024))} "
        f"hca={os.environ.get('B12X_ROCE_HCA', '(auto)')} "
        f"peer_maps={'set' if os.environ.get('B12X_ROCE_PEER_HCA_MAPS') else '(auto)'} "
        f"two_wave={os.environ.get('B12X_ROCE_TWO_WAVE_THRESHOLD_BYTES', '(default)')} "
        f"version={ROCE_AR_VERSION}"
    )
    return True


def install_parallel_state(module):
    """Wrap GroupCoordinator on the parallel_state module. Inert on NCCL arms.

    Import-order independent (DOA fix, t/C1-fix-import-order): the real engine
    loads parallel_state FIRST -- sglang/srt/distributed/__init__.py imports it
    at module scope, and pynccl only loads later, lazily, from inside
    GroupCoordinator.__init__ (parallel_state.py:447, construction of the
    communicator two lines below). So this hook must arm on the env gates alone;
    it must NOT require the pynccl face to be armed already. The wraps here do
    not touch the pynccl face: __init__ only records the group_name being built,
    and graph_capture reads pynccl_comm.roce at capture time -- by then pynccl
    has loaded and either armed a runtime (capture context opens) or refused
    (every communicator has roce=None, this wrap is a pure passthrough).

    Stack semantics hold in both orders because communicator construction always
    happens inside a GroupCoordinator.__init__ that the __init__ wrap has
    already pushed the group_name for: pynccl-first has both wraps in place
    before any construction; parallel_state-first has the pynccl module load
    (and its hook) happen at parallel_state.py:447, still inside the pushed
    window, before the L472 construction.
    """
    if not gates_on():
        return False

    cls = module.GroupCoordinator
    orig_init, orig_gc = cls.__init__, cls.graph_capture

    def __init__(self, *args, **kwargs):
        # Both engine call sites pass group_name= as a keyword (init_world_group
        # "world", init_model_parallel_group the TP/Attn/MoE names).
        _group_name_stack.append(kwargs.get("group_name"))
        try:
            orig_init(self, *args, **kwargs)
        finally:
            _group_name_stack.pop()

    @contextmanager
    def graph_capture(self, graph_capture_context=None, stream=None):
        with orig_gc(self, graph_capture_context, stream) as ctx:
            comm = getattr(self, "pynccl_comm", None)
            roce = getattr(comm, "roce", None) if comm is not None else None
            if roce is None:
                yield ctx
                return
            with roce.capture(stream=ctx.stream):
                yield ctx

    cls.__init__, cls.graph_capture = __init__, graph_capture
    _banner(
        f"armed parallel_state face (group gate + capture ctx; passthrough until "
        f"the pynccl face arms a runtime) version={ROCE_AR_VERSION}"
    )
    return True
