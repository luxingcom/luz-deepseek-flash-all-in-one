"""CuTe DSL kernel for the RoCE one-shot all-gather.

Same transport and protocol as the one-shot all-reduce (stage, doorbell,
wait on per-peer, per-HCA stripe flags, advance the epoch) with the reduction
replaced by a strided copy that writes the concatenated output directly:

* ``dim == 0`` concat: ``rows == 1``, output is shard 0, shard 1, ... in order;
* last-dim concat: each shard is ``rows`` rows of ``row_packs`` 16-byte packs
  and shard ``s`` lands at column block ``s`` of every output row, so no
  separate reshape/copy is needed after the collective.

The local shard is copied from the input; peer shards are read in place from
the NIC-written slots with system-scope loads.

Launch grid and message size are runtime scalars.  The host picks a
power-of-two grid from the shard size and hands the kernel that grid's own
staging and tail counters, so small gathers do not pay for the full grid and
gathers may interleave with reductions of any size inside one CUDA graph.

``_RoceAllGatherColumnsLaunch`` (ds41) is a separate specialization for a last-dim
gather of unequal column shards; the plain kernel above is unchanged.
"""

from __future__ import annotations

import functools
from collections.abc import Callable

import cuda.bindings.driver as cuda
import cutlass
import cutlass.cute as cute
from cutlass import Int32, Int64, Uint32

from b12x._lib.compiler import KernelCompileSpec
from b12x._lib.compiler import compile as b12x_compile
from b12x._lib.runtime_control import raise_if_kernel_resolution_frozen
from b12x._lib.utils import current_cuda_stream, make_ptr

from ._cute_intrinsics import (
    atomic_add_relaxed_gpu_u32,
    fence_sc_gpu,
    fence_sc_sys,
    ld_global_v4_u32,
    ld_relaxed_gpu_u32,
    ld_relaxed_sys_u32,
    ld_relaxed_sys_v4_u32,
    spin_until_eq_acquire_sys,
    st_global_v4_u32,
    st_release_gpu_u32,
    st_relaxed_sys_u32,
)

PACK_BYTES = 16
_PREPARED_LAUNCHERS: set[tuple[object, ...]] = set()


class _RoceAllGatherLaunch:
    def __init__(
        self,
        world_size: int,
        rank: int,
        threads: int,
        slots: int,
        flag_stride: int,
        hca_count: int,
    ) -> None:
        """Bind one kernel specialization: world size, rank, and layout constants."""
        if int(threads) < int(world_size) * int(hca_count):
            raise ValueError(
                "RoCE kernels need threads >= world_size * hca_count "
                f"(one thread per stripe flag), got threads={threads} "
                f"world_size={world_size} hca_count={hca_count}"
            )
        self._world_size = int(world_size)
        self._rank = int(rank)
        self._threads = int(threads)
        self._slots = int(slots)
        self._flag_stride = int(flag_stride)
        self._hca_count = int(hca_count)

    @cute.jit
    def __call__(
        self,
        input_ptr: cute.Pointer,
        output_ptr: cute.Pointer,
        shard_packs: Int32,
        nbytes: Int32,
        row_packs: Int32,
        recv_base: Int64,
        flag_base: Int64,
        send_base: Int64,
        ctrl_base: Int64,
        slot_bytes: Int64,
        epoch_ptr: Int64,
        stage_counter_ptr: Int64,
        tail_counter_ptr: Int64,
        poison_ptr: Int64,
        spin_limit: Uint32,
        grid_x: Int32,
        stream: cuda.CUstream,
    ) -> None:
        """Host entry: launch the all-gather kernel with runtime scalars."""
        self.kernel(
            input_ptr,
            output_ptr,
            shard_packs,
            nbytes,
            row_packs,
            recv_base,
            flag_base,
            send_base,
            ctrl_base,
            slot_bytes,
            epoch_ptr,
            stage_counter_ptr,
            tail_counter_ptr,
            poison_ptr,
            spin_limit,
        ).launch(
            grid=(grid_x, 1, 1),
            block=[self._threads, 1, 1],
            cluster=(1, 1, 1),
            stream=stream,
        )

    @cute.kernel
    def kernel(
        self,
        input_ptr: cute.Pointer,
        output_ptr: cute.Pointer,
        shard_packs: Int32,
        nbytes: Int32,
        row_packs: Int32,
        recv_base: Int64,
        flag_base: Int64,
        send_base: Int64,
        ctrl_base: Int64,
        slot_bytes: Int64,
        epoch_ptr: Int64,
        stage_counter_ptr: Int64,
        tail_counter_ptr: Int64,
        poison_ptr: Int64,
        spin_limit: Uint32,
    ) -> None:
        """Device kernel: stage, doorbell, wait for peer flags, strided copy, advance the epoch."""
        tidx, _, _ = cute.arch.thread_idx()
        bidx, _, _ = cute.arch.block_idx()
        gdim, _, _ = cute.arch.grid_dim()
        input_base = Int64(input_ptr.toint())
        output_base = Int64(output_ptr.toint())
        epoch = ld_relaxed_gpu_u32(epoch_ptr)
        seq = epoch + Uint32(1)
        slot = Int64(seq & Uint32(1))
        send_slot = send_base + slot * slot_bytes

        index = Int32(bidx) * Int32(self._threads) + Int32(tidx)
        stride = Int32(gdim) * Int32(self._threads)

        # A recorded timeout poisons the runtime: later launches do nothing so
        # the host sees the failure without waiting another spin limit per op.
        # The device poison word (fourth counter) is written by the same waiting
        # threads that write the host error word and only ever goes from 0 to
        # the failed sequence, so a cheap GPU-scope load is enough here.
        poisoned = ld_relaxed_gpu_u32(poison_ptr)
        if poisoned == Uint32(0):
            # 1. stage the local shard into the pinned send slot
            stage_index = index
            while stage_index < shard_packs:
                words = ld_global_v4_u32(
                    input_base + Int64(stage_index) * Int64(PACK_BYTES)
                )
                st_global_v4_u32(
                    send_slot + Int64(stage_index) * Int64(PACK_BYTES),
                    words[0],
                    words[1],
                    words[2],
                    words[3],
                )
                stage_index += stride
            cute.arch.sync_threads()

            # 2. the last block to finish staging rings the proxy doorbell.  One
            # system fence per block after the barrier (cumulative over the
            # staging stores the barrier ordered) replaces one per thread.
            if Int32(tidx) == Int32(0):
                fence_sc_sys()
                prior = atomic_add_relaxed_gpu_u32(stage_counter_ptr, Uint32(1))
                if (prior + Uint32(1)) % Uint32(gdim) == Uint32(0):
                    st_relaxed_sys_u32(ctrl_base + Int64(4), Uint32(nbytes))
                    st_relaxed_sys_u32(
                        ctrl_base + Int64(16) + slot * Int64(4), Uint32(nbytes)
                    )
                    fence_sc_sys()
                    st_relaxed_sys_u32(ctrl_base, seq)

            # 3. wait for every peer's payload-stripe flags
            if Int32(tidx) < Int32(self._world_size * self._hca_count):
                peer = Int32(tidx) // Int32(self._hca_count)
                hca = Int32(tidx) - peer * Int32(self._hca_count)
                if peer != Int32(self._rank):
                    flag_addr = flag_base + (
                        (Int64(peer) * Int64(self._slots) + slot)
                        * Int64(self._hca_count)
                        + Int64(hca)
                    ) * Int64(self._flag_stride)
                    timed_out = spin_until_eq_acquire_sys(flag_addr, seq, spin_limit)
                    if timed_out != Uint32(0):
                        st_relaxed_sys_u32(ctrl_base + Int64(12), Uint32(peer))
                        st_relaxed_sys_u32(ctrl_base + Int64(24), Uint32(hca))
                        st_relaxed_sys_u32(ctrl_base + Int64(8), seq)
                        st_release_gpu_u32(poison_ptr, seq)
            cute.arch.sync_threads()
            # A wait that timed out in this block leaves the peer slot unreliable:
            # skip the data phase so nothing derived from it is stored.
            failed = ld_relaxed_gpu_u32(poison_ptr)
            if failed == Uint32(0):
                # 4. concatenate: shard s occupies column block s of every output row
                out_row_packs = Int32(self._world_size) * row_packs
                for source in cutlass.range_constexpr(self._world_size):
                    copy_index = index
                    while copy_index < shard_packs:
                        row = copy_index // row_packs
                        col = copy_index - row * row_packs
                        dest = output_base + (
                            Int64(row) * Int64(out_row_packs)
                            + Int64(source) * Int64(row_packs)
                            + Int64(col)
                        ) * Int64(PACK_BYTES)
                        if cutlass.const_expr(source == self._rank):
                            words = ld_global_v4_u32(
                                input_base + Int64(copy_index) * Int64(PACK_BYTES)
                            )
                        else:
                            peer_slot = (
                                recv_base
                                + (Int64(source) * Int64(self._slots) + slot)
                                * slot_bytes
                            )
                            words = ld_relaxed_sys_v4_u32(
                                peer_slot + Int64(copy_index) * Int64(PACK_BYTES)
                            )
                        st_global_v4_u32(dest, words[0], words[1], words[2], words[3])
                        copy_index += stride

            # 5. the last block to finish publishes the next epoch
            fence_sc_gpu()
            cute.arch.sync_threads()
            if Int32(tidx) == Int32(0):
                prior = atomic_add_relaxed_gpu_u32(tail_counter_ptr, Uint32(1))
                if (prior + Uint32(1)) % Uint32(gdim) == Uint32(0):
                    fence_sc_gpu()
                    # Every block's timeout store precedes its tail arrival, so the
                    # error word is final here.  A failed sequence keeps the epoch,
                    # which makes every later launch a no-op until the host raises.
                    if ld_relaxed_sys_u32(ctrl_base + Int64(8)) == Uint32(0):
                        st_release_gpu_u32(epoch_ptr, seq)


class _RoceAllGatherColumnsLaunch:
    """Uneven last-dim all-gather ("columns"): rank ``s`` contributes ``col_packs[s]``
    16-byte packs per row and they land at pack ``sum(col_packs[:s])`` of every output
    row (row stride ``sum(col_packs)``), so a gather of unequal column shards needs no
    pad before the collective and no reorder or cat after it.

    Same transport, doorbell, flag wait and epoch protocol as ``_RoceAllGatherLaunch``;
    each rank sends only its own ``rows * col_packs[rank]`` packs (the proxy stripes
    whatever byte count the doorbell carries and always writes every stripe flag, so
    senders may use different sizes).  The local shard is read from a strided input:
    ``in_row_packs`` packs per input row, the shard starting at pack ``in_col_off``, so a
    rank whose GEMM output is wider than its own columns sends a view without a copy.
    The column layout is a compile-time constant of the specialization.
    """

    def __init__(
        self,
        world_size: int,
        rank: int,
        threads: int,
        slots: int,
        flag_stride: int,
        hca_count: int,
        col_packs: tuple[int, ...],
    ) -> None:
        """Bind one kernel specialization: world, rank, layout constants and the column layout."""
        if int(threads) < int(world_size) * int(hca_count):
            raise ValueError(
                "RoCE kernels need threads >= world_size * hca_count "
                f"(one thread per stripe flag), got threads={threads} "
                f"world_size={world_size} hca_count={hca_count}"
            )
        col_packs = tuple(int(c) for c in col_packs)
        if len(col_packs) != int(world_size) or min(col_packs) < 1:
            raise ValueError(
                f"col_packs needs one positive pack count per rank, got {col_packs}"
            )
        self._world_size = int(world_size)
        self._rank = int(rank)
        self._threads = int(threads)
        self._slots = int(slots)
        self._flag_stride = int(flag_stride)
        self._hca_count = int(hca_count)
        self._col_packs = col_packs
        self._col_offs = tuple(sum(col_packs[:s]) for s in range(len(col_packs)))
        self._out_row_packs = sum(col_packs)

    @cute.jit
    def __call__(
        self,
        input_ptr: cute.Pointer,
        output_ptr: cute.Pointer,
        rows: Int32,
        in_row_packs: Int32,
        in_col_off: Int32,
        nbytes: Int32,
        recv_base: Int64,
        flag_base: Int64,
        send_base: Int64,
        ctrl_base: Int64,
        slot_bytes: Int64,
        epoch_ptr: Int64,
        stage_counter_ptr: Int64,
        tail_counter_ptr: Int64,
        poison_ptr: Int64,
        spin_limit: Uint32,
        grid_x: Int32,
        stream: cuda.CUstream,
    ) -> None:
        """Host entry: launch the columns all-gather kernel with runtime scalars."""
        self.kernel(
            input_ptr,
            output_ptr,
            rows,
            in_row_packs,
            in_col_off,
            nbytes,
            recv_base,
            flag_base,
            send_base,
            ctrl_base,
            slot_bytes,
            epoch_ptr,
            stage_counter_ptr,
            tail_counter_ptr,
            poison_ptr,
            spin_limit,
        ).launch(
            grid=(grid_x, 1, 1),
            block=[self._threads, 1, 1],
            cluster=(1, 1, 1),
            stream=stream,
        )

    @cute.kernel
    def kernel(
        self,
        input_ptr: cute.Pointer,
        output_ptr: cute.Pointer,
        rows: Int32,
        in_row_packs: Int32,
        in_col_off: Int32,
        nbytes: Int32,
        recv_base: Int64,
        flag_base: Int64,
        send_base: Int64,
        ctrl_base: Int64,
        slot_bytes: Int64,
        epoch_ptr: Int64,
        stage_counter_ptr: Int64,
        tail_counter_ptr: Int64,
        poison_ptr: Int64,
        spin_limit: Uint32,
    ) -> None:
        """Device kernel: stage the compact local shard, doorbell, wait, scatter into columns, advance."""
        tidx, _, _ = cute.arch.thread_idx()
        bidx, _, _ = cute.arch.block_idx()
        gdim, _, _ = cute.arch.grid_dim()
        input_base = Int64(input_ptr.toint())
        output_base = Int64(output_ptr.toint())
        epoch = ld_relaxed_gpu_u32(epoch_ptr)
        seq = epoch + Uint32(1)
        slot = Int64(seq & Uint32(1))
        send_slot = send_base + slot * slot_bytes

        index = Int32(bidx) * Int32(self._threads) + Int32(tidx)
        stride = Int32(gdim) * Int32(self._threads)
        my_packs = Int32(self._col_packs[self._rank])
        local_packs = rows * my_packs

        poisoned = ld_relaxed_gpu_u32(poison_ptr)
        if poisoned == Uint32(0):
            # 1. stage the compact local shard (row-major, my_packs per row) into the send slot
            stage_index = index
            while stage_index < local_packs:
                row = stage_index // my_packs
                col = stage_index - row * my_packs
                words = ld_global_v4_u32(
                    input_base
                    + (Int64(row) * Int64(in_row_packs) + Int64(in_col_off) + Int64(col))
                    * Int64(PACK_BYTES)
                )
                st_global_v4_u32(
                    send_slot + Int64(stage_index) * Int64(PACK_BYTES),
                    words[0],
                    words[1],
                    words[2],
                    words[3],
                )
                stage_index += stride
            cute.arch.sync_threads()

            # 2. the last block to finish staging rings the proxy doorbell (own byte count)
            if Int32(tidx) == Int32(0):
                fence_sc_sys()
                prior = atomic_add_relaxed_gpu_u32(stage_counter_ptr, Uint32(1))
                if (prior + Uint32(1)) % Uint32(gdim) == Uint32(0):
                    st_relaxed_sys_u32(ctrl_base + Int64(4), Uint32(nbytes))
                    st_relaxed_sys_u32(
                        ctrl_base + Int64(16) + slot * Int64(4), Uint32(nbytes)
                    )
                    fence_sc_sys()
                    st_relaxed_sys_u32(ctrl_base, seq)

            # 3. wait for every peer's payload-stripe flags
            if Int32(tidx) < Int32(self._world_size * self._hca_count):
                peer = Int32(tidx) // Int32(self._hca_count)
                hca = Int32(tidx) - peer * Int32(self._hca_count)
                if peer != Int32(self._rank):
                    flag_addr = flag_base + (
                        (Int64(peer) * Int64(self._slots) + slot)
                        * Int64(self._hca_count)
                        + Int64(hca)
                    ) * Int64(self._flag_stride)
                    timed_out = spin_until_eq_acquire_sys(flag_addr, seq, spin_limit)
                    if timed_out != Uint32(0):
                        st_relaxed_sys_u32(ctrl_base + Int64(12), Uint32(peer))
                        st_relaxed_sys_u32(ctrl_base + Int64(24), Uint32(hca))
                        st_relaxed_sys_u32(ctrl_base + Int64(8), seq)
                        st_release_gpu_u32(poison_ptr, seq)
            cute.arch.sync_threads()
            failed = ld_relaxed_gpu_u32(poison_ptr)
            if failed == Uint32(0):
                # 4. scatter: source s fills packs [col_offs[s], col_offs[s] + col_packs[s]) of every row
                for source in cutlass.range_constexpr(self._world_size):
                    src_packs = Int32(self._col_packs[source])
                    src_total = rows * src_packs
                    copy_index = index
                    while copy_index < src_total:
                        row = copy_index // src_packs
                        col = copy_index - row * src_packs
                        dest = output_base + (
                            Int64(row) * Int64(self._out_row_packs)
                            + Int64(self._col_offs[source])
                            + Int64(col)
                        ) * Int64(PACK_BYTES)
                        if cutlass.const_expr(source == self._rank):
                            words = ld_global_v4_u32(
                                input_base
                                + (
                                    Int64(row) * Int64(in_row_packs)
                                    + Int64(in_col_off)
                                    + Int64(col)
                                )
                                * Int64(PACK_BYTES)
                            )
                        else:
                            peer_slot = (
                                recv_base
                                + (Int64(source) * Int64(self._slots) + slot)
                                * slot_bytes
                            )
                            words = ld_relaxed_sys_v4_u32(
                                peer_slot + Int64(copy_index) * Int64(PACK_BYTES)
                            )
                        st_global_v4_u32(dest, words[0], words[1], words[2], words[3])
                        copy_index += stride

            # 5. the last block to finish publishes the next epoch
            fence_sc_gpu()
            cute.arch.sync_threads()
            if Int32(tidx) == Int32(0):
                prior = atomic_add_relaxed_gpu_u32(tail_counter_ptr, Uint32(1))
                if (prior + Uint32(1)) % Uint32(gdim) == Uint32(0):
                    fence_sc_gpu()
                    if ld_relaxed_sys_u32(ctrl_base + Int64(8)) == Uint32(0):
                        st_release_gpu_u32(epoch_ptr, seq)


def _dummy(dtype, alignment: int):
    """A CUDA tensor of ``dtype`` used to trace launcher argument types."""
    return make_ptr(dtype, 16, cute.AddressSpace.gmem, assumed_align=alignment)


def _process_key(
    world_size: int,
    rank: int,
    threads: int,
    slots: int,
    flag_stride: int,
    hca_count: int,
    device_index: int,
) -> tuple[object, ...]:
    """Cache key of one compiled launcher specialization."""
    return (
        int(world_size),
        int(rank),
        int(threads),
        int(slots),
        int(flag_stride),
        int(hca_count),
        int(device_index),
    )


def is_launcher_prepared(*key) -> bool:
    """True when the launcher for ``key`` is already compiled."""
    return _process_key(*key) in _PREPARED_LAUNCHERS


@functools.cache
def get_launcher(
    world_size: int,
    rank: int,
    threads: int,
    slots: int,
    flag_stride: int,
    hca_count: int,
    device_index: int,
) -> Callable[..., None]:
    """Compile the launcher for ``key`` once and return it."""
    process_key = _process_key(
        world_size, rank, threads, slots, flag_stride, hca_count, device_index
    )
    del device_index
    launch = _RoceAllGatherLaunch(
        world_size, rank, threads, slots, flag_stride, hca_count
    )
    cache_key = (
        int(world_size),
        int(rank),
        int(threads),
        int(slots),
        int(flag_stride),
        int(hca_count),
    )
    raise_if_kernel_resolution_frozen(
        "cute.compile", target=launch, cache_key=cache_key
    )
    raw = b12x_compile(
        launch,
        _dummy(cutlass.Uint32, 16),
        _dummy(cutlass.Uint32, 16),
        1,
        16,
        1,
        16,
        16,
        16,
        16,
        4096,
        16,
        16,
        16,
        16,
        1,
        1,
        current_cuda_stream(),
        compile_spec=KernelCompileSpec.from_key("comm.roce.allgather", 4, cache_key),
    )

    def run(
        input_address: int,
        output_address: int,
        shard_packs: int,
        nbytes: int,
        row_packs: int,
        recv_base: int,
        flag_base: int,
        send_base: int,
        ctrl_base: int,
        slot_bytes: int,
        epoch_address: int,
        stage_counter_address: int,
        tail_counter_address: int,
        poison_address: int,
        spin_limit: int,
        grid_x: int,
    ) -> None:
        """Launch the compiled kernel with runtime scalar arguments."""
        raw(
            make_ptr(
                cutlass.Uint32, input_address, cute.AddressSpace.gmem, assumed_align=16
            ),
            make_ptr(
                cutlass.Uint32, output_address, cute.AddressSpace.gmem, assumed_align=16
            ),
            int(shard_packs),
            int(nbytes),
            int(row_packs),
            int(recv_base),
            int(flag_base),
            int(send_base),
            int(ctrl_base),
            int(slot_bytes),
            int(epoch_address),
            int(stage_counter_address),
            int(tail_counter_address),
            int(poison_address),
            int(spin_limit),
            int(grid_x),
            current_cuda_stream(),
        )

    _PREPARED_LAUNCHERS.add(process_key)
    return run


def _columns_process_key(
    world_size: int,
    rank: int,
    threads: int,
    slots: int,
    flag_stride: int,
    hca_count: int,
    device_index: int,
    col_packs: tuple[int, ...],
) -> tuple[object, ...]:
    """Cache key of one compiled columns-gather specialization (tagged apart from the plain gather)."""
    return ("columns",) + _process_key(
        world_size, rank, threads, slots, flag_stride, hca_count, device_index
    ) + (tuple(int(c) for c in col_packs),)


def is_columns_launcher_prepared(*key) -> bool:
    """True when the columns-gather launcher for ``key`` is already compiled."""
    return _columns_process_key(*key) in _PREPARED_LAUNCHERS


@functools.cache
def get_columns_launcher(
    world_size: int,
    rank: int,
    threads: int,
    slots: int,
    flag_stride: int,
    hca_count: int,
    device_index: int,
    col_packs: tuple[int, ...],
) -> Callable[..., None]:
    """Compile the columns-gather launcher for ``key`` once and return it."""
    col_packs = tuple(int(c) for c in col_packs)
    process_key = _columns_process_key(
        world_size, rank, threads, slots, flag_stride, hca_count, device_index, col_packs
    )
    launch = _RoceAllGatherColumnsLaunch(
        world_size, rank, threads, slots, flag_stride, hca_count, col_packs
    )
    cache_key = (
        int(world_size),
        int(rank),
        int(threads),
        int(slots),
        int(flag_stride),
        int(hca_count),
        tuple(col_packs),
    )
    raise_if_kernel_resolution_frozen(
        "cute.compile", target=launch, cache_key=cache_key
    )
    raw = b12x_compile(
        launch,
        _dummy(cutlass.Uint32, 16),
        _dummy(cutlass.Uint32, 16),
        1,
        1,
        0,
        16,
        1,
        16,
        16,
        16,
        4096,
        16,
        16,
        16,
        16,
        1,
        1,
        current_cuda_stream(),
        compile_spec=KernelCompileSpec.from_key(
            "comm.roce.allgather_columns", 1, cache_key
        ),
    )

    def run(
        input_address: int,
        output_address: int,
        rows: int,
        in_row_packs: int,
        in_col_off: int,
        nbytes: int,
        recv_base: int,
        flag_base: int,
        send_base: int,
        ctrl_base: int,
        slot_bytes: int,
        epoch_address: int,
        stage_counter_address: int,
        tail_counter_address: int,
        poison_address: int,
        spin_limit: int,
        grid_x: int,
    ) -> None:
        """Launch the compiled kernel with runtime scalar arguments."""
        raw(
            make_ptr(
                cutlass.Uint32, input_address, cute.AddressSpace.gmem, assumed_align=16
            ),
            make_ptr(
                cutlass.Uint32, output_address, cute.AddressSpace.gmem, assumed_align=16
            ),
            int(rows),
            int(in_row_packs),
            int(in_col_off),
            int(nbytes),
            int(recv_base),
            int(flag_base),
            int(send_base),
            int(ctrl_base),
            int(slot_bytes),
            int(epoch_address),
            int(stage_counter_address),
            int(tail_counter_address),
            int(poison_address),
            int(spin_limit),
            int(grid_x),
            current_cuda_stream(),
        )

    _PREPARED_LAUNCHERS.add(process_key)
    return run


__all__ = [
    "PACK_BYTES",
    "get_columns_launcher",
    "get_launcher",
    "is_columns_launcher_prepared",
    "is_launcher_prepared",
]
