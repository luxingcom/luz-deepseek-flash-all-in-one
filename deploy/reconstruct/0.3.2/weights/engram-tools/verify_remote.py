"""Verify the distributed Engram shards on the three worker nodes and rank0 locally.

20261030 脱敏：远端主机改经环境变量 HOST_R1/HOST_R2/HOST_R3 注入（<node02>/<node04>/<node03>
的 <nfs-server-ip> 侧地址），缺参拒跑。
"""
import hashlib
import json
import os
import subprocess

TOOLS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(TOOLS)


def _required_env(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"缺少环境变量 {name}（内网值已脱敏为 <nfs-server-ip> 占位），拒跑")
    return value


HOSTS = {1: _required_env("HOST_R1"), 2: _required_env("HOST_R2"), 3: _required_env("HOST_R3")}
REMOTE_DIR = os.environ.get("ENGRAM_REMOTE_DIR", "dsv41-engram-1017")

man = json.load(open(os.path.join(TOOLS, "bins-manifest.json")))
bins = {(b["layer"], b["rank"]): b for b in man["bins"]}
failures = []

for (layer, rank), b in sorted(bins.items()):
    name = f"engram-l{layer}-r{rank}of4.bin"
    if rank == 0:
        path = os.path.join(OUT, name)
        size, sha = os.path.getsize(path), None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 26), b""):
                h.update(chunk)
        sha = h.hexdigest()
    else:
        host = HOSTS[rank]
        out = subprocess.check_output(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
             f"cd ~/{REMOTE_DIR} && stat -c %s {name} && sha256sum {name}"],
            text=True)
        size_line, sha_line = out.strip().splitlines()[:2]
        size = int(size_line)
        sha = sha_line.split()[0]
    ok = size == b["size"] and sha == b["sha256"]
    print(f"L{layer} r{rank}: size={size} sha256={sha} {'OK' if ok else 'MISMATCH'}",
          flush=True)
    if not ok:
        failures.append(f"L{layer} r{rank}: size/sha mismatch on rank {rank}")

if failures:
    print(f"RESULT FAIL ({len(failures)})")
    for f in failures:
        print("FAIL", f)
    raise SystemExit(1)
print(f"RESULT PASS bins={len(bins)}")
