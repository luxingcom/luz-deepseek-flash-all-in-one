"""Verify the packed Engram shards of DeepSeek-V4.1-Flash-1017 against the checkpoint.

Checks, for every (layer, rank): exact size, 4096-byte header (magic/layer/lo/hi/rows/264),
edge + seeded-random row-by-row equality against the safetensors source, full coverage of
[0, rows) with no gap/overlap, and SHA256 of the whole shard. Writes bins-manifest.json.
"""
import hashlib
import json
import os
import random
import struct
import sys

MODEL = os.environ.get("ENGRAM_MODEL", "/data/models/DeepSeek-V4.1-Flash-1017")
OUT = os.environ.get("ENGRAM_OUT", os.path.expanduser("~/dsv41-engram-1017"))
TOOLS = os.path.join(OUT, "tools")
MAGIC = 0x31344E4531565344  # "DSV41EN1"
HEADER = 4096
ROW_BYTES = 264
WEIGHT_BYTES = 256
SCALE_BYTES = 8
TP = 4

cfg = json.load(open(os.path.join(MODEL, "config.json")))["text_config"]
layers = cfg["engram_layer_ids"]
num_emb = cfg["engram_num_embeddings"]
index = json.load(open(os.path.join(MODEL, "model.safetensors.index.json")))["weight_map"]

dirs = {0: OUT, 1: os.path.join(OUT, "staging/r1"),
        2: os.path.join(OUT, "staging/r2"), 3: os.path.join(OUT, "staging/r3")}

manifest = []
failures = []
ranges = {}

for layer, rows in zip(layers, num_emb):
    wname = index[f"layers.{layer}.engram.embed.weight"]
    sname = index[f"layers.{layer}.engram.embed.scale"]
    assert wname == sname, "weight and scale must share a shard"
    shard = os.path.join(MODEL, wname)
    with open(shard, "rb") as f:
        hlen = struct.unpack("<Q", f.read(8))[0]
        hdr = json.loads(f.read(hlen))
        base = 8 + hlen
        w = hdr[f"layers.{layer}.engram.embed.weight"]
        s = hdr[f"layers.{layer}.engram.embed.scale"]
        assert w["shape"] == [rows, WEIGHT_BYTES] and w["dtype"] == "F8_E4M3"
        assert s["shape"] == [rows, SCALE_BYTES] and s["dtype"] == "F8_E8M0"
        wo = base + w["data_offsets"][0]
        so = base + s["data_offsets"][0]

    cover = []
    for rank in range(TP):
        lo, hi = rows * rank // TP, rows * (rank + 1) // TP
        cover.append((lo, hi))
        path = os.path.join(dirs[rank], f"engram-l{layer}-r{rank}of{TP}.bin")
        expected_size = HEADER + (hi - lo) * ROW_BYTES
        if not os.path.exists(path):
            failures.append(f"L{layer} r{rank}: missing {path}")
            continue
        size = os.path.getsize(path)
        if size != expected_size:
            failures.append(f"L{layer} r{rank}: size {size} != {expected_size}")
            continue
        with open(path, "rb") as bf:
            h = bf.read(HEADER)
            magic, h_layer, h_lo, h_hi, h_rows, h_rb = struct.unpack("<6Q", h[:48])
            hdr_ok = (magic == MAGIC and h_layer == layer and h_lo == lo and
                      h_hi == hi and h_rows == rows and h_rb == ROW_BYTES)
            if not hdr_ok:
                failures.append(f"L{layer} r{rank}: bad header "
                                f"{(hex(magic), h_layer, h_lo, h_hi, h_rows, h_rb)}")
                continue
            rng = random.Random(f"{layer}-{rank}")
            picks = {lo, lo + 1, (lo + hi) // 2, hi - 1}
            if hi - lo > 4:
                picks.update(rng.sample(range(lo, hi), 2))
            rows_to_check = sorted(g for g in picks if lo <= g < hi)
            bad = 0
            for g in rows_to_check:
                bf.seek(HEADER + (g - lo) * ROW_BYTES)
                rec = bf.read(ROW_BYTES)
                with open(shard, "rb") as sf:
                    sf.seek(wo + g * WEIGHT_BYTES)
                    wb = sf.read(WEIGHT_BYTES)
                    sf.seek(so + g * SCALE_BYTES)
                    sb = sf.read(SCALE_BYTES)
                if rec != wb + sb:
                    bad += 1
                    failures.append(f"L{layer} r{rank}: row {g} bytes differ from checkpoint")
            digest = hashlib.sha256()
            with open(path, "rb") as hf:
                for chunk in iter(lambda: hf.read(1 << 26), b""):
                    digest.update(chunk)
            sha = digest.hexdigest()
            print(f"L{layer} r{rank}: lo={lo} hi={hi} rows={hi-lo} size={size} "
                  f"hdr_ok={hdr_ok} spot={len(rows_to_check)} bad={bad} sha256={sha}",
                  flush=True)
            manifest.append({"layer": layer, "rank": rank, "path": path,
                             "lo": lo, "hi": hi, "rows": rows, "size": size,
                             "sha256": sha, "spot_bad": bad})

    ranges[layer] = cover
    expect = 0
    for lo, hi in cover:
        if lo != expect:
            failures.append(f"L{layer}: gap/overlap at {lo}, expected {expect}")
        expect = hi
    if expect != rows:
        failures.append(f"L{layer}: coverage ends at {expect}, table has {rows}")

os.makedirs(TOOLS, exist_ok=True)
with open(os.path.join(TOOLS, "bins-manifest.json"), "w") as f:
    json.dump({"model": MODEL, "tp": TP, "layers": layers,
               "num_embeddings": num_emb, "bins": manifest,
               "failures": failures}, f, indent=1)

if failures:
    print(f"RESULT FAIL ({len(failures)} problems)")
    for x in failures:
        print("FAIL", x)
    sys.exit(1)

print(f"RESULT PASS bins={len(manifest)}")
