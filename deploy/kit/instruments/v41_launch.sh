#!/bin/bash
# ==============================================================
# v41_launch.sh -- DeepSeek-V4.1-Flash first-boot smoke / switch
#
#   Run ON the target node:   bash v41_launch.sh <node_rank>
#   Inspect without starting: DRYRUN=1 bash v41_launch.sh <node_rank>
#
# This is deliberately NOT the production launcher and deliberately does not
# touch anything production owns:
#   * different container name  (vllm-v41-test-rank<N>, so the 60s healthcheck's
#     `docker rm -f --filter name=tp4-rank` cannot match it)
#   * different port            (8012, never 8001/8002)
#   * different cache volumes   (production's flashinfer-cache-f1 / tilelang-cache-f1
#     are the F1 build's JIT caches; letting this image write into them would
#     poison the rollback path)
#
# Differences vs the production launcher, and why:
#   1. image      -> deepseekv41-flash-0909-engramdisk-fh: the official preview
#                    image plus TWO patches -- Engram disk-mapping, and the
#                    multi-node follower hold ported verbatim from the production
#                    fork. RepoDigest sha256:89e9a38695ca...; patched sources are
#                    byte-identical on all four nodes (core.py e5e7ad9172db,
#                    engram config aeaff1f550e6, engram model 663e3b995406).
#   2. model      -> /data/models/DeepSeek-V4.1-Flash, the VERIFIED original
#                    checkpoint, both Engram layers. No derived config is needed
#                    once the table is mapped rather than allocated.
#   3. k          -> 5   (production VL checkpoint uses 6; V4.1 config has
#                    dspark_block_size=5 so k must be 5)
#   4. gmu        -> 0.83, with --memory 120g (direction-1 hard cap)
#   5. env        -> fabric-level NCCL/IB vars kept; fork-specific VLLM_* tuning
#                    vars dropped because this is the stock upstream image
#   6. NCCL lib   -> PRELOAD PRODUCTION'S ring-only NCCL (see below). NOT optional.
#   7. health     -> ROLE-DEPENDENT, mirroring production: rank 0 answers HTTP on
#                    $PORT, ranks 1-3 are checked by process liveness. A follower
#                    node parks its EngineCore by design (see below) and never
#                    serves HTTP, so an HTTP probe there could not ever pass.
#
# ⚠️ WHY THE ENGRAM PATCH EXISTS (root cause of the 2026-09-10 cluster hang):
#    The engine allocated the Engram table with
#        torch.empty(part_num_embeddings, dim, device="cpu", pin_memory=True)
#    i.e. PINNED host memory. On DGX Spark the host and device share ONE
#    121.63 GiB pool, so "offloading" to host memory frees nothing: the
#    ~23.6 GiB/rank (47 GiB/rank for both layers) is still deducted from that
#    pool, on top of and OUTSIDE the gmu device budget. At gmu 0.83 the pool
#    needed 100.95 + 23.60 = 124.55 GiB and the driver died:
#        NVRM: Out of memory [NV_ERR_NO_MEMORY] (0x00000051) _memdescAllocInternal
#    (journalctl -k -b -1, 2026-09-10 19:49:11; boot -1 ended 19:54:42).
#    The patched engine maps the same rows read-only out of the checkpoint's
#    safetensors shards instead, so the pages are reclaimable and cost the pool
#    nothing. The weight loader verifies the mapping instead of copying into it,
#    which keeps the pages clean. Omitting --engram-config restores the old
#    pinned-memory behaviour exactly (that is the rollback anchor).
#
# ⚠️ WHY THE FOLLOWER HOLD EXISTS (the real cause of the 2026-09-11 first-window
#    failure on ranks 1-3, diagnosed offline by diffing the two images):
#    With --nnodes 4 --tensor-parallel-size 4 the global world size is 4, so
#    nnodes_within_dp == 4 and node_rank_within_dp == node_rank. Only node 0 (the
#    "DP group leader") builds an rpc_broadcast_mq; nodes 1-3 get None and their
#    workers are driven over the cross-node broadcast instead. Upstream expects
#    those nodes to be started with `--headless`, which returns from
#    entrypoints/cli/serve.py before EngineCore is constructed. Production does
#    NOT use --headless -- every node runs the identical `vllm serve` line and
#    only the leader's node carries traffic -- so its fork added a hold right
#    after the executor is built:
#        if vllm_config.parallel_config.node_rank_within_dp != 0:
#            logger.info("Follower node: holding process (leader orchestrates all workers)")
#            while True:
#                time.sleep(3600)
#    The preview image lacked that block, so a follower built its executor, then
#    walked into _initialize_kv_caches and died with
#        AssertionError: collective_rpc should not be called on follower node
#    The derived image carries the production block byte for byte
#    (vllm/v1/engine/core.py), which is why rank 1-3 health is a process probe:
#    the parked EngineCore process is alive and titled VLLM::EngineCore.
#
# ⚠️ NCCL TRAP (cost a second failed first-boot 2026-09-10 19:29Z): the RoCE fabric
#    is a LINE, not a mesh -- subnets give 02<->01, 01<->03, 03<->04, and NO link
#    between 02 and 04. Stock NCCL in the preview image picks a local GID that is
#    not on a common subnet with the peer and dies in QP transition:
#        ibv_modify_qp failed with 110 Connection timed out ... curr state INIT,
#        next state RTR, local GID ::ffff:<fabric-ip>, remote GID ::ffff:<fabric-ip>
#    Production solves this with the custom "ringonly-v5" NCCL (drop-in libnccl
#    2.30.7) + the CPU-pinning shim, exactly as its image labels record
#    (org.aicad.libnccl.md5=51e36db584e5373ccaa060d50d537ed1). We preload the very
#    same artifact, extracted from the production image and md5-matched on all four
#    nodes. Without this, TP4 across these four nodes cannot form a group at all.
#
# ⚠️ MOUNT TRAP (cost one failed first-boot 2026-09-10 19:23Z): an earlier variant
#    served a derived dir built from ABSOLUTE symlinks into the original checkpoint
#    (/models/tokenizer.json -> /data/models/DeepSeek-V4.1-Flash/tokenizer.json).
#    Mounting ONLY the derived dir at /models made all 60 symlinks dangle inside the
#    container, and the run died in the tokenizer with a misleading
#    "Couldn't instantiate the backend tokenizer ... need sentencepiece or tiktoken".
#    Hence BOTH mounts below: the original tree must be visible at its real path.
#    (config.json is a real file, so config-only probes pass and hide this.)
# ==============================================================
set -uo pipefail
export HOME=/home/liux***ya

RANK="${1:?usage: bash v41_launch.sh <node_rank 0..3>}"

# ── 20261030 脱敏：节点主机名/管理段地址/registry 改经环境变量注入，缺参拒跑 ──
NODE01_HOST="${NODE01_HOST:?缺环境变量 NODE01_HOST（<node01>），拒跑}"
NODE02_HOST="${NODE02_HOST:?缺环境变量 NODE02_HOST（<node02>），拒跑}"
NODE03_HOST="${NODE03_HOST:?缺环境变量 NODE03_HOST（<node03>），拒跑}"
NODE04_HOST="${NODE04_HOST:?缺环境变量 NODE04_HOST（<node04>），拒跑}"
NODE01_IP="${NODE01_IP:?缺环境变量 NODE01_IP（<mgmt-node-ip>），拒跑}"
NODE02_IP="${NODE02_IP:?缺环境变量 NODE02_IP（<mgmt-node-ip>），拒跑}"
NODE03_IP="${NODE03_IP:?缺环境变量 NODE03_IP（<mgmt-node-ip>），拒跑}"
NODE04_IP="${NODE04_IP:?缺环境变量 NODE04_IP（<mgmt-node-ip>），拒跑}"
IMG="${IMG:?缺环境变量 IMG（<registry-host>:5000/vllm/vllm-openai:deepseekv41-flash-0909-engramdisk-fh），拒跑}"

case "$(hostname)" in
  "$NODE01_HOST") MYIP="$NODE01_IP" ;;
  "$NODE02_HOST") MYIP="$NODE02_IP" ;;
  "$NODE03_HOST") MYIP="$NODE03_IP" ;;
  "$NODE04_HOST") MYIP="$NODE04_IP" ;;
  *) echo "unknown host $(hostname)" >&2; exit 2 ;;
esac
# production topology keeps rank placement r0=01/r1=02/r2=04/r3=03; same placement below (IP 已脱敏)
case "$RANK" in
  0) EXPECT="$NODE01_IP" ;;
  1) EXPECT="$NODE02_IP" ;;
  2) EXPECT="$NODE04_IP" ;;
  3) EXPECT="$NODE03_IP" ;;
  *) echo "rank must be 0..3" >&2; exit 2 ;;
esac
if [ "$MYIP" != "$EXPECT" ]; then
  echo "ABORT: rank $RANK belongs to $EXPECT but this host is $MYIP ($(hostname))" >&2
  exit 2
fi

NAME="vllm-v41-test-rank${RANK}"
MODEL_DIR="/data/models/DeepSeek-V4.1-Flash"
PORT=8012
GMU="${GMU:-0.83}"
K=5
# Engram tables are MAPPED out of the checkpoint instead of being allocated in
# pinned host memory. That is what makes the full table affordable: the pages are
# reclaimable, so the ~47 GiB does not come out of the shared host/device pool
# (it was that overcommit that hung the cluster on 2026-09-10). Dropping this flag
# restores the upstream pinned-memory behaviour exactly.
if [ -z "${ENGRAM_CONFIG:-}" ]; then
  ENGRAM_CONFIG='{"disk_offload": true}'
fi
# MML: context length for this boot. 600000 is the production value.
MML="${MML:-600000}"
NSEQ="${NSEQ:-8}"

# --- preconditions -----------------------------------------------------
[ -f "$MODEL_DIR/config.json" ] || { echo "ABORT: $MODEL_DIR/config.json missing" >&2; exit 2; }
EL=$(python3 -c "import json;print(json.load(open('$MODEL_DIR/config.json'))['text_config']['engram_layer_ids'])")
# Both Engram layers: with disk mapping the table costs no memory, and keeping
# the layer set identical to the checkpoint keeps EngramLayout's prime order
# (layer 14's primes are drawn after layer 1's) exactly as trained.
[ "$EL" = "[1, 14]" ] || { echo "ABORT: engram_layer_ids=$EL (want [1, 14])" >&2; exit 2; }
docker image inspect "$IMG" >/dev/null 2>&1 || { echo "ABORT: image absent on this node" >&2; exit 2; }
# All three patches must actually be in the image on THIS node. Checking the
# files rather than trusting the tag costs a second and turns a 4-node boot
# failure into an immediate abort.
SP=/usr/local/lib/python3.12/dist-packages
docker run --rm --entrypoint /bin/sh "$IMG" -c \
  "grep -q 'Follower node: holding process' $SP/vllm/v1/engine/core.py && \
   grep -q 'engram_disk_backed' $SP/vllm/models/deepseek_v4_1/common/engram.py && \
   grep -q '_ENGRAM_RECLAIM_MAPPINGS' $SP/vllm/models/deepseek_v4_1/common/engram.py" \
  || { echo "ABORT: image $IMG is missing follower-hold, engram-disk, or engram-reclaim" >&2; exit 2; }
# the Engram shards are mapped from these two files, so they must exist here
for f in model-00047-of-00048.safetensors model-00048-of-00048.safetensors; do
  [ -f "$MODEL_DIR/$f" ] || { echo "ABORT: Engram shard $f missing" >&2; exit 2; }
done
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "ABORT: $NAME already exists; remove it first (docker rm -f $NAME)" >&2
  exit 2
fi

# dedicated JIT caches: never share the F1 (production) caches
for d in flashinfer-cache-v41 tilelang-cache-v41 vllm-cache-v41; do mkdir -p "/home/liux***ya/$d"; done
mkdir -p /home/liux***ya/vllm-logs /tmp/vllm-crash

# fabric-level env only (see header note 5)
ENV=(
  -e NCCL_ALGO=RING -e NCCL_NET=IB
  -e NCCL_IB_HCA=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
  -e NCCL_IB_GID_INDEX=3 -e NCCL_IB_TOS=46 -e NCCL_IB_MERGE_NICS=0
  -e NCCL_IB_SUBNET_AWARE_ROUTING=1 -e NCCL_IB_TIMEOUT=1000 -e NCCL_IB_RETRY_CNT=7
  -e NCCL_CUMEM_HOST_ENABLE=0 -e NCCL_CROSS_NIC=1
  -e NCCL_MIN_NCHANNELS=4 -e NCCL_MAX_NCHANNELS=4 -e NCCL_TUNER_THRESHOLD=40960
  -e NCCL_SET_THREAD_NAME=1 -e NCCL_IGNORE_CPU_AFFINITY=1 -e NCCL_BUFFSIZE=8388608
  -e NCCL_NET_PLUGIN=none -e NCCL_DEBUG=INFO
  -e NCCL_DEBUG_FILE=/var/log/vllm/v41-nccl-%h.log
  -e NCCL_SOCKET_IFNAME=enP7s7 -e GLOO_SOCKET_IFNAME=enP7s7
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID
  -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
  -e FLASHINFER_DISABLE_VERSION_CHECK=1
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
  -e VLLM_ENGINE_ITERATION_TIMEOUT_S=1800
  -e VLLM_DISABLE_PYNCCL=1
  -e VLLM_HOST_IP="$MYIP"
  -e NODE_RANK="$RANK"
  -e MASTER_ADDR="$NODE01_IP" -e MASTER_PORT=26001
  -e PYTHONFAULTHANDLER=1
  # --- multi-node role/topology vars, copied from production's proven
  #     ~/w6-kit/w6_env.txt, for parity with the working stack. NOTE: these were
  #     NOT the first-window failure cause -- adding them changed nothing. The
  #     real cause was the missing follower hold in the image (see header note).
  -e VLLM_DP_MASTER_IP="$NODE01_IP"
  -e VLLM_TOPO_SAME_NODE_MAP=0,1,2,3
  -e VLLM_USE_FLASHINFER_SAMPLER=1
  -e VLLM_USE_BREAKABLE_CUDAGRAPH=1
  -e VLLM_PREFIX_CACHE_RETENTION_INTERVAL=8192
  -e VLLM_DSPARK_MARKOV_REPL=0
  -e TORCH_CUDA_ARCH_LIST=12.1a
)

# direction-1 hard cap: container RAM must never exceed 120G. Note a `#` comment
# may NOT appear inside the `docker run` continuation below -- it swallows the
# rest of the logical line, including the image and the command.
# Kept as its own string so DRYRUN=1 can print exactly what the container runs.
SERVE_CMD="export LD_PRELOAD='/opt/libncclpin.so /opt/nccl-ringonly/libnccl.so.2' && vllm serve /models \
    --served-model-name deepseek-v41-flash \
    --kv-cache-dtype fp8_ds_mla \
    --max-model-len ${MML} --max-num-seqs ${NSEQ} --max-num-batched-tokens 4096 \
    --gpu-memory-utilization ${GMU} \
    --disable-custom-all-reduce \
    --load-format safetensors \
    --language-model-only \
    --engram-config '${ENGRAM_CONFIG}' \
    --trust-remote-code \
    --distributed-executor-backend mp --distributed-timeout-seconds 1800 \
    --speculative-config '{\"method\":\"dspark\",\"num_speculative_tokens\":${K},\"draft_sample_method\":\"probabilistic\"}' \
    --port ${PORT} \
    --tensor-parallel-size 4 --nnodes 4 --node-rank ${RANK} \
    --master-addr "$NODE01_IP" --master-port 26001"

if [ "${DRYRUN:-0}" = "1" ]; then
  echo "--- env that would be injected ($(( ${#ENV[@]} / 2 )) vars) ---"
  printf '  %s\n' "${ENV[@]}" | paste - - | sed 's/^/  /'
  echo "--- serve command that would run in $NAME ---"
  echo "$SERVE_CMD"
  echo "--- engram config (must be valid JSON once the inner quotes are stripped) ---"
  python3 -c "import json,sys; print(json.loads('''${ENGRAM_CONFIG}'''))" \
    || { echo "ABORT: ENGRAM_CONFIG is not valid JSON" >&2; exit 2; }
  exit 0
fi

# Role-dependent liveness, mirroring production (head: HTTP, workers: process).
# A follower (rank != 0) parks in EngineCore before the API server ever becomes
# ready, so probing it over HTTP would mark a perfectly healthy container
# unhealthy -- and anything acting on "unhealthy" would tear the TP group down.
if [ "$RANK" = "0" ]; then
  HEALTH_CMD="curl -sf -o /dev/null -m 30 http://127.0.0.1:${PORT}/health || exit 1"
else
  HEALTH_CMD="pgrep -f VLLM::EngineCore >/dev/null 2>&1 || exit 1"
fi

docker run -d --name "$NAME" \
  --gpus all --privileged --shm-size 64g \
  --ulimit memlock=-1 --ulimit nofile=1048576 \
  --ipc=host --network host --cpuset-cpus=1-19 \
  --memory 120g --memory-swap 120g \
  "${ENV[@]}" \
  -v /data/models:/data/models:ro \
  -v "$MODEL_DIR":/models:ro \
  -v /home/liux***ya/nccl-ringonly-v41:/opt/nccl-ringonly:ro \
  -v /opt/aicad-prod/lib/libncclpin.so:/opt/libncclpin.so:ro \
  -v /home/liux***ya/vllm-logs:/var/log/vllm \
  -v /home/liux***ya/flashinfer-cache-v41:/root/.cache/flashinfer:rw \
  -v /home/liux***ya/tilelang-cache-v41:/root/.cache/tilelang:rw \
  -v /home/liux***ya/vllm-cache-v41:/root/.cache/vllm:rw \
  --health-cmd "$HEALTH_CMD" \
  --health-interval 30s --health-timeout 35s --health-retries 5 --health-start-period 1800s \
  --log-opt max-size=100m --log-opt max-file=3 \
  --entrypoint /bin/bash \
  "$IMG" -lc "$SERVE_CMD"

rc=$?
echo "[v41] rank${RANK} $NAME start rc=${rc} model=$MODEL_DIR gmu=$GMU k=$K port=$PORT mml=$MML nseq=$NSEQ engram=${ENGRAM_CONFIG}"
echo "[v41] role=$([ "$RANK" = 0 ] && echo leader || echo follower) health=\"$HEALTH_CMD\""
exit $rc
