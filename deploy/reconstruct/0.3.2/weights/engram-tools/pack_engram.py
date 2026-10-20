"""Repack this rank's owned Engram rows into a local contiguous shard.

In the checkpoint a row's 256 B of weight and its 8 B of scale sit in two tensors
about 98 GB apart, so a cache miss costs two reads into unrelated 4 KiB pages --
and on a worker both of them are NFS round trips to the head. Packing the owned
rows as 264 B records on local disk makes a miss one local read.

Per rank: (rows/tp) * 264 B, about 34 GiB per Engram layer.

Run inside the serving image, where /models is the checkpoint and the output
directory is node-local storage:
    python3 scripts/pack_engram.py --rank 0 --tp 3 --out /engram
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
import time

import numpy

MAGIC = 0x31344E4531565344  # "DSV41EN1"
HEADER_BYTES = 4096
ROW_BYTES = 264
WEIGHT_BYTES = 256
SCALE_BYTES = 8
ENGRAM_LAYERS = (1, 14)


def tensor_span(root: Path, layer_id: int):
    index = json.loads((root / 'model.safetensors.index.json').read_text())['weight_map']
    prefix = f'layers.{layer_id}.engram.embed.'
    name = index[prefix + 'weight']
    assert index[prefix + 'scale'] == name, 'weight and scale must share a shard'
    path = root / name
    with path.open('rb') as f:
        length = struct.unpack('<Q', f.read(8))[0]
        header = json.loads(f.read(length))
    weight, scale = header[prefix + 'weight'], header[prefix + 'scale']
    assert weight['dtype'] == 'F8_E4M3' and scale['dtype'] == 'F8_E8M0'
    assert weight['shape'][1] == WEIGHT_BYTES and scale['shape'][1] == SCALE_BYTES
    base = 8 + length
    return (path, weight['shape'][0],
            base + weight['data_offsets'][0], base + scale['data_offsets'][0])


def pack_layer(root: Path, out_dir: Path, layer_id: int, rank: int, tp: int,
               chunk_rows: int) -> Path:
    path, rows, weight_off, scale_off = tensor_span(root, layer_id)
    lo, hi = rows * rank // tp, rows * (rank + 1) // tp
    count = hi - lo
    target = out_dir / f'engram-l{layer_id}-r{rank}of{tp}.bin'
    partial = target.with_suffix('.partial')
    expected = HEADER_BYTES + count * ROW_BYTES

    if target.exists() and target.stat().st_size == expected:
        print(f'layer {layer_id}: {target} already complete ({expected/2**30:.1f} GiB)',
              flush=True)
        return target

    header = bytearray(HEADER_BYTES)
    struct.pack_into('<6Q', header, 0, MAGIC, layer_id, lo, hi, rows, ROW_BYTES)

    started = time.monotonic()
    written = 0
    with open(path, 'rb', buffering=0) as src, open(partial, 'wb', buffering=0) as dst:
        dst.write(header)
        for start in range(lo, hi, chunk_rows):
            stop = min(start + chunk_rows, hi)
            n = stop - start
            src.seek(weight_off + start * WEIGHT_BYTES)
            weights = src.read(n * WEIGHT_BYTES)
            src.seek(scale_off + start * SCALE_BYTES)
            scales = src.read(n * SCALE_BYTES)
            if len(weights) != n * WEIGHT_BYTES or len(scales) != n * SCALE_BYTES:
                raise SystemExit(f'short read from {path} at row {start}')
            block = numpy.empty((n, ROW_BYTES), dtype=numpy.uint8)
            block[:, :WEIGHT_BYTES] = numpy.frombuffer(
                weights, dtype=numpy.uint8).reshape(n, WEIGHT_BYTES)
            block[:, WEIGHT_BYTES:] = numpy.frombuffer(
                scales, dtype=numpy.uint8).reshape(n, SCALE_BYTES)
            dst.write(block.tobytes())
            written += n
            elapsed = time.monotonic() - started
            rate = written * ROW_BYTES / max(elapsed, 1e-6)
            print(f'layer {layer_id}: {written}/{count} rows '
                  f'({100.0*written/count:5.1f}%) {rate/2**20:.0f} MiB/s', flush=True)
        dst.flush()
        os.fsync(dst.fileno())
    partial.rename(target)
    print(f'layer {layer_id}: wrote {target} ({expected/2**30:.1f} GiB) in '
          f'{time.monotonic()-started:.0f}s', flush=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=os.environ.get('DSV41_SOURCE', '/models/DeepSeek-V4.1-Flash'))
    parser.add_argument('--out', default=os.environ.get('DSV41_PACKED_DIR', '/engram'))
    parser.add_argument('--rank', type=int, default=int(os.environ.get('NODE_RANK', '0')))
    parser.add_argument('--tp', type=int, default=int(os.environ.get('TP_SIZE', '3')))
    parser.add_argument('--chunk-rows', type=int, default=1 << 18)
    parser.add_argument('--layers', default=','.join(str(x) for x in ENGRAM_LAYERS))
    args = parser.parse_args()

    root, out_dir = Path(args.model), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    layers = [int(x) for x in args.layers.split(',') if x.strip()]

    need = 0
    for layer_id in layers:
        _, rows, _, _ = tensor_span(root, layer_id)
        need += HEADER_BYTES + (rows * (args.rank + 1) // args.tp - rows * args.rank // args.tp) * ROW_BYTES
    free = os.statvfs(out_dir).f_bavail * os.statvfs(out_dir).f_frsize
    print(f'rank {args.rank}/{args.tp}: need {need/2**30:.1f} GiB, '
          f'{free/2**30:.1f} GiB free at {out_dir}', flush=True)
    if free < need:
        raise SystemExit(f'not enough space at {out_dir}')

    for layer_id in layers:
        pack_layer(root, out_dir, layer_id, args.rank, args.tp, args.chunk_rows)
    return 0


if __name__ == '__main__':
    sys.exit(main())
