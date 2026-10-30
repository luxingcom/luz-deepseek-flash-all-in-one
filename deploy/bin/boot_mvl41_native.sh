#!/usr/bin/env bash
# boot_mvl41_native.sh — VL-NATIVE V4.1 原生臂驱动（新文件零改共享件；窗=
#   VL-NATIVE-WINCARD-20261013 §3.2〔d21afc8〕）。
#   基=logs/W-OPTA-CLOSELINE-20261010/desk/boot_mvl_uv.sh（=C24-4.8M 骨架精化版）
#   的 DRY-RUN 强制段/四机守卫/A9 指纹核/失败路径免疫/水位断言全承袭；V4.1 原生臂
#   三处变体：
#     ①去 overlay 段 → **硬断言 SGLANG_OVERLAY_DIR 空**（环境位+臂 env 位双查；
#       与 STDVL 前形「overlay 必带」断言互斥=防臂混挂；§1.2 定谳 V4.1 线=0 文件）。
#     ②MODEL=V4.1-Flash 476G（01/02=/data/models/DeepSeek-V4.1-Flash，
#       03/04=/data/models/dsv41-net NFS；锚=r3-boot-arm.sh WORKERS 拓扑逐字）；
#       A9 指纹=cfg sha256 8be45ce0476004a3/md5 e1e4964ca281289b/48 分片。
#     ③SERVER_ARGS=**生产逐字**（r3-boot-arm.sh:356-393 逐项+SPEC6 六参锚=
#       FL6-PROMO lib.sh:20-21）+SPEC/CG 阶梯由臂 env 映射（§3.2「断言 SERVER_ARGS
#       与生产逐字 diff 仅 SPEC/CG 阶梯位」工程化）：
#         SPEC=0 → 零 spec 参数；SPEC=k6 → --speculative-algorithm DSPARK+SPEC6 六参
#         GRAPHS=0 → --disable-cuda-graph（换出 --cuda-graph-max-bs-decode 16）；
#         GRAPHS=1 → --cuda-graph-max-bs-decode 16（生产逐字位）
#       L3（k6+GRAPHS1）⇒ 与生产 serve 参数面逐字等（vl 面零参数增量=§1.1 的
#       工程化表达）。
#   COMMON_ENV=**生产启动器公共面逐字**（r3-boot-arm.sh:216-283；勘正 2：首靴红实证
#   C24 剥离面缺 DSV41_MOE_B12X_NEXT=1 ⇒ Mxfp4FlashinferCutlassMoEMethod 中间维 576
#   128 对齐墙崩——「零 DSV41_* 性能键」律只辖臂 env=51 键族零注入，启动器公共面
#   =生产同形含 engram pread/FP4KV_PORT/SM121 候选对键+/engram 四秩挂载）。
#   新增 post-UP **mm 三直证断言**（§5 G-V3 承载；生产同款锚=
#   logs/FL6-PROMO-20261013/teardown/pre-stop/<prod-log>:236-237/:277）：
#     mm 后端 triton_attn 两行+mm KV 0.10G 预留行+processors 扫描行，四机逐机在档。
#   池 pin=9,600,000（生产同值 R3.4；±2% 指纹带）；水位地板缺省 6000（VL 靴槽=
#   产线常规线沿袭，§5 G-V4.4）；UMA 靴窗中止门 4G 沿基线；不 drop_caches（窗令红线）。
# 用法: DRY_RUN=1 ARM_ENV_FILE=~/luz030-opt-campaign/arms/VL41N-SPEC0.env ARM_TAG=VL41N-S3 \
#         bash dev/vl-native/boot_mvl41_native.sh      # 靴前 DRY-RUN（零集群，出口 0=自检绿）
#       ARM_TAG=VL41N-S3 ARM_ENV_FILE=~/luz030-opt-campaign/arms/VL41N-SPEC0.env \
#         bash tools/boot-with-slotlock.sh bash dev/vl-native/boot_mvl41_native.sh   # 活靴（槽锁制）
# 出口: 0=UP+VL41N 断言组绿（DRY_RUN=1 则=DRY-RUN 段绿零集群退出）；9=断言红/起败
set -euo pipefail

CAMP="$HOME/luz030-opt-campaign"
D="$CAMP/logs/VL-NATIVE-20261013"
ARM_ENV_FILE="${ARM_ENV_FILE:-$CAMP/arms/VL41N-SPEC0.env}"
ARM_TAG="${ARM_TAG:-VL41N}"
DRY_RUN="${DRY_RUN:-0}"    # 1=靴前 DRY-RUN 段后零集群退出；0=活靴
# ── 20261030 脱敏：以下内网值（registry 主机/管理段地址/节点主机名）改经环境变量注入，缺参拒跑 ──
IMAGE="${IMAGE:?缺环境变量 IMAGE（<registry-host>:5000/lmsysorg/sglang:main-79cafec0），拒跑}"
HEAD_IP="${HEAD_IP:?缺环境变量 HEAD_IP（head 节点 <mgmt-node-ip>），拒跑}"
NODE01_HOST="${NODE01_HOST:?缺环境变量 NODE01_HOST（<node01>），拒跑}"
NODE02_HOST="${NODE02_HOST:?缺环境变量 NODE02_HOST（<node02>），拒跑}"
NODE03_HOST="${NODE03_HOST:?缺环境变量 NODE03_HOST（<node03>），拒跑}"
NODE04_HOST="${NODE04_HOST:?缺环境变量 NODE04_HOST（<node04>），拒跑}"
NODE02_IP="${NODE02_IP:?缺环境变量 NODE02_IP（<mgmt-node-ip>），拒跑}"
NODE03_IP="${NODE03_IP:?缺环境变量 NODE03_IP（<mgmt-node-ip>），拒跑}"
NODE04_IP="${NODE04_IP:?缺环境变量 NODE04_IP（<mgmt-node-ip>），拒跑}"
DIST_PORT="20000"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8)
ADAPTER_DIR="$HOME/migrate-assets/dsv41/adapter"
B12X_DIR="$HOME/migrate-assets/b12x"
NCCL_DIR="$HOME/migrate-assets/nccl-ringonly"
NCCLPIN="$HOME/migrate-assets/ncclpin.so"
PIP_NCCL=/opt/sglang/lib/python3.12/site-packages/nvidia/nccl/lib/libnccl.so.2
ENG_HOST="/home/liux***ya/dsv41-engram"     # ENV-UNIFY 四机统一路径（r3-boot-arm.sh:23-24 同律）
MOUNT_TGT="/models/DeepSeek-V4.1-Flash"                  # 容器内统一路径（A9 PATH=此值）
EXPECT_CFG16="8be45ce0476004a3"                          # config.json sha256 前 16（本窗 01 机实测）
EXPECT_CFGMD5="e1e4964ca281289b"                         # config.json md5 前 16（并录）
EXPECT_NSHARD=48

info(){ printf '[+] %s\n' "$*"; }
warn(){ printf '[!] %s\n' "$*" >&2; }
die(){ printf '[x] %s\n' "$*" >&2; exit 9; }
memavail(){ awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo; }

# ── 0. 臂 env 解析+驱动约定键+A4 黑名单 ──────────────────────────────────────
[ -f "$ARM_ENV_FILE" ] || die "ARM_ENV_FILE 缺：$ARM_ENV_FILE"
ARM_KEYVALS=()
# 2026-10-30 修复（外部站点 bug 报告）：尾行守护——env 文件末尾缺换行时 while read
# 会静默丢最后一行（常为关键开关）；lint 件自带同款守护会照常 PASS（split-brain）。
while IFS= read -r line || [ -n "$line" ]; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  ARM_KEYVALS+=("$line")
done < "$ARM_ENV_FILE"
arm_get(){ local k="$1" v; v=$(grep -m1 "^$k=" "$ARM_ENV_FILE" || true); [ -n "$v" ] && echo "${v#*=}" || echo ""; }
CTN_PREFIX="$(arm_get CTN_PREFIX)"; API_PORT="$(arm_get API_PORT)"
SPEC="$(arm_get SPEC)"; GRAPHS="$(arm_get GRAPHS)"; VERIFY="$(arm_get VERIFY)"
[ "$CTN_PREFIX" = r3boot-mvl ] || die "臂 env CTN_PREFIX=$CTN_PREFIX != r3boot-mvl"
[ "$API_PORT" = 8898 ] || die "臂 env API_PORT=$API_PORT != 8898（分面律：VL 测试槽）"
{ [ "$SPEC" = 0 ] || [ "$SPEC" = k6 ]; } || die "臂 env SPEC=$SPEC ∉ {0,k6}（S3=0；S4 阶梯=k6）"
{ [ "$GRAPHS" = 0 ] || [ "$GRAPHS" = 1 ]; } || die "臂 env GRAPHS=$GRAPHS ∉ {0,1}"
[ "$VERIFY" = 1 ]      || die "臂 env VERIFY=$VERIFY != 1"
# V4.1 原生臂硬断言①：零 overlay（环境位+臂 env 位双查；与 STDVL 前形互斥防混挂）
OVERLAY_DIR="$(arm_get SGLANG_OVERLAY_DIR)"
[ -z "$OVERLAY_DIR" ] || die "VL41N 红：臂 env SGLANG_OVERLAY_DIR=$OVERLAY_DIR 非空（V4.1 原生臂零 overlay，§1.2/§九.5）"
[ -z "${SGLANG_OVERLAY_DIR:-}" ] || die "VL41N 红：环境 SGLANG_OVERLAY_DIR=$SGLANG_OVERLAY_DIR 非空（V4.1 原生臂零 overlay）"
# X1 律工程化：臂 env 零 DSV41_TL_BUDGET_ELEMS
grep -q '^DSV41_TL_BUDGET_ELEMS=' <(printf '%s\n' "${ARM_KEYVALS[@]}") && die "X1 红：臂 env 携 DSV41_TL_BUDGET_ELEMS（禁键）"
n_perf=$(printf '%s\n' "${ARM_KEYVALS[@]}" | grep -cE '^(DSV41_|SGLANG_DSV4_)' || true)
[ "$n_perf" = 0 ] || die "VL41N 红：臂 env 携 DSV41_*/SGLANG_DSV4_* 性能键 $n_perf 行（§3.2 零 DSV41_* 性能键=不带 51 键族）"
info "[arm] ARM_TAG=$ARM_TAG CTN=$CTN_PREFIX PORT=$API_PORT SPEC=$SPEC GRAPHS=$GRAPHS VERIFY=$VERIFY（臂 env 生效键 $(printf '%s\n' "${ARM_KEYVALS[@]}" | wc -l) 行=零 DSV41_* 性能键；overlay=∅）"
# A4 env 键黑名单（C24/W-OPTA 同表；生效行口径）
A4_PAT='DSV41_SKIP_NONFINAL_DECODER|DSV41_ENGRAM_[A-Z_]*|DSV41_FP4KV_PORT|DSV41_MOE_B12X_NEXT|DSV41_DG_SPARSE_SM121|SGLANG_ENABLE_DETERMINISTIC_INFERENCE|SGLANG_ENABLE_KERNEL_CENSUS_V2|DSV41_LAUNCHER|DSV41_PACKED_DIR|OFFLOAD_MODE|DSV41_CACHE_GIB|DSV41_CACHE_WAYS|DSV41_IO_THREADS|DSV41_RESIDENT_SCALES|DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES|DSV41_PREFILL_SP|DSV41_HC_FUSED|DSV41_INDEXER_HOIST|DSV41_IDLE_RELEASE|DSV41_WO_A_W8|DSV41_REPLICATED_SPLIT|DSV41_SPEC_SYNC_FREE|DSV41_EAGER_GLUE|DSV41_FOLDED_FENCE|DSV41_DRAFT_HEAD_FP8|DSV41_DRAFT_MAIN_PROJ_SPLIT|DSV41_VERIFY_CAP|DSV41_SHARED_PAD_K|DSV41_ROUTER_LIVE|DSV41_PREFILL_EMPTY_CACHE_TOKENS|DSV41_MOE_B12X_DETERMINISTIC'
n_a4=$(printf '%s\n' "${ARM_KEYVALS[@]}" | grep -cE "^($A4_PAT)=" || true)
[ "$n_a4" = 0 ] || die "A4 红：臂 env 黑名单键命中 $n_a4 行"
info "A4 绿：臂 env 键黑名单零命中+X1 键零出现+overlay 空断言过（V4.1 原生=零 overlay 形）"

# ── 1. per-machine MODEL_DIR（V4.1-Flash 拓扑=r3-boot-arm.sh WORKERS 逐字：
#        01/02=/data 本地树；03/04=NFS **dsv41-net**〔03←<fabric-ip>=01 主源；
#        04←<fabric-ip>=02 备源；≠dsvl-net=Vision-Exp NFS——预核截获勘正 1〕）────────
declare -A MD=( [${NODE01_HOST}]="/data/models/DeepSeek-V4.1-Flash"
                [${NODE02_HOST}]="/data/models/DeepSeek-V4.1-Flash"
                [${NODE04_HOST}]="/data/models/dsv41-net"
                [${NODE03_HOST}]="/data/models/dsv41-net" )
WORKERS=( "1|${NODE02_HOST}|${NODE02_IP}|0=rocep1s0f1,roceP2p1s0f1;2=rocep1s0f0,roceP2p1s0f0"
          "2|${NODE04_HOST}|${NODE04_IP}|1=rocep1s0f0,roceP2p1s0f0;3=rocep1s0f1,roceP2p1s0f1"
          "3|${NODE03_HOST}|${NODE03_IP}|0=rocep1s0f0,roceP2p1s0f0;2=rocep1s0f1,roceP2p1s0f1" )
PEER_HCA_HEAD="1=rocep1s0f1,roceP2p1s0f1;3=rocep1s0f0,roceP2p1s0f0"
HEAD_CTN="${CTN_PREFIX}-head"; WORKER_CTN="${CTN_PREFIX}-worker"

# ── 2/3. 前置守卫+权重面远端核验（活靴面；DRY_RUN=1 整段跳过=零集群纪律）─────────
if [[ "$DRY_RUN" = 1 ]]; then
  info "[dry-run] 段2/3（前置守卫+A9 远端核验）跳过——DRY-RUN 模式零 ssh/零 docker/零 curl（8066bb4 靴前 DRY-RUN 强制段）"
else
  mkdir -p "$D/boot-checks"
  guard_node(){ local name="$1" target="$2" out
    if [[ "$target" == "-" ]]; then out=$(docker ps --format '{{.Names}}' 2>/dev/null; nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)
    else out=$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$target" "docker ps --format '{{.Names}}' 2>/dev/null; nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null" 2>/dev/null) || die "ssh $target 不通"; fi
    local ctns pids
    ctns=$(grep -E '^r3(boot|prod)-' <<<"$out" || true); pids=$(grep -E '^[0-9]+$' <<<"$out" | grep -v '^$' || true)
    [[ -n "$ctns" ]] && die "$name 有 r3 栈容器: $ctns"
    [[ -n "$pids" ]] && die "$name GPU 被占 (pid: $(echo $pids | tr '\n' ' '))"
    info "  $name: 无 r3 容器、GPU 空"; }
  info "== 前置守卫（无 drop_caches=窗令红线）=="
  guard_node "head ${NODE01_HOST}" "-"
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"; guard_node "worker $_h" "$_h"; done
  m=$(memavail); [ "$m" -ge 100000 ] || die "head MemAvailable=${m}M < 100G"
  info "head MemAvailable=${m}M（≥100G 过）"
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"
    mw=$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "awk '/MemAvailable/{printf \"%d\", \$2/1024}' /proc/meminfo" 2>/dev/null)
    [ "${mw:-0}" -ge 100000 ] || die "$_h MemAvailable=${mw}M < 100G"; info "  $_h MemAvailable=${mw}M"; done

  info "== 权重面远端核验+A9 指纹（零 overlay 面=无 overlay 摘要对表项）=="
  # engram 分片资产核验（r3-boot-arm.sh §3 同律；四机同用户同路径）
  ls "$ENG_HOST"/engram-l1-r0of4.bin >/dev/null 2>&1 || die "head 打包分片缺（$ENG_HOST/engram-l1-r0of4.bin）"
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"
    ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "test -f $ENG_HOST/engram-l1-r${_rk}of4.bin && test -f '$ADAPTER_DIR/sitecustomize.py' && test -f '$HOME/migrate-assets/nccl-ringonly/libnccl.so.2.30.7' && test -f '$HOME/migrate-assets/ncclpin.so' && test -f '$HOME/migrate-assets/b12x/b12x_next/__init__.py'" \
      || die "$_h 资产面缺（adapter/NCCL/b12x_next/分片）"
    info "  $_h 资产面 OK（engram 分片 r${_rk}of4+adapter+NCCL+b12x）"; done
  FP_LOG="$D/boot-checks/a9-fingerprint.txt"; : > "$FP_LOG"; a9fail=0
  fp_one(){ local h="$1" p="$2" out cfg16 cfgmd5 bytes nshard mnt
    if [ "$h" = "${NODE01_HOST}" ]; then out=$(sha256sum "$p/config.json" | awk '{print $1}'; md5sum "$p/config.json" | awk '{print $1}'; du -sb "$p" | awk '{print $1}'; ls "$p"/model-*-of-00048.safetensors 2>/dev/null | wc -l; findmnt -no FSTYPE,SOURCE "$p" 2>/dev/null || echo "local")
    else out=$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$h" "sha256sum '$p'/config.json | awk '{print \$1}'; md5sum '$p'/config.json | awk '{print \$1}'; du -sb '$p' | awk '{print \$1}'; ls '$p'/model-*-of-00048.safetensors 2>/dev/null | wc -l; findmnt -no FSTYPE,SOURCE '$p' 2>/dev/null || echo local" 2>/dev/null); fi
    cfg16=$(sed -n 1p <<<"$out" | cut -c1-16); cfgmd5=$(sed -n 2p <<<"$out" | cut -c1-16); bytes=$(sed -n 3p <<<"$out"); nshard=$(sed -n 4p <<<"$out" | tr -d '[:space:]'); mnt=$(sed -n 5p <<<"$out")
    local ok="OK"
    [ "$cfg16" = "$EXPECT_CFG16" ] || { ok="RED(cfg=$cfg16)"; a9fail=1; }
    [ "$cfgmd5" = "$EXPECT_CFGMD5" ] || { ok="$ok RED(md5=$cfgmd5)"; a9fail=1; }
    [ "$nshard" = "$EXPECT_NSHARD" ] || { ok="$ok RED(nshard=$nshard)"; a9fail=1; }
    printf 'MODEL=deepseek-v4.1-flash CFG=%s(md5:%s) PATH=%s BYTES=%s host=%s mount=%s overlay=NONE %s\n' "$cfg16" "$cfgmd5" "$MOUNT_TGT" "$bytes" "$h" "$mnt" "$ok" | tee -a "$FP_LOG"; }
  fp_one "${NODE01_HOST}" "${MD[${NODE01_HOST}]}"
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"; fp_one "$_h" "${MD[$_h]}"; done
  [ "$a9fail" = 0 ] || { cat "$FP_LOG"; die "A9/权重面红（四机身份漂移）"; }
  info "A9 绿：四机 CFG=$EXPECT_CFG16 逐机相等=注册值；BYTES 记录不判红（元数据级）；overlay=零（原生臂）"
fi

# ── 4. 公共面（M0731 剥离律 21 项；零 overlay 挂载=V4.1 原生臂）────────────────
DOCKER_HW=(
  --network host --ipc host --privileged --cap-add IPC_LOCK --gpus all
  --memory 32g --memory-swap 32g
  --ulimit memlock=-1 --ulimit stack=67108864
  --device /dev/infiniband:/dev/infiniband
  -v "$NCCL_DIR":/opt/nccl-ringonly:ro
  -v "$NCCLPIN":/opt/ncclpin.so:ro
  -v "$NCCL_DIR/libnccl.so.2.30.7":"$PIP_NCCL":ro
  -v "$ADAPTER_DIR":/opt/dsv41/adapter:ro
  -v "$B12X_DIR":/opt/b12x-tree:ro
)
COMMON_ENV=(
  -e NCCL_NET=IB
  -e NCCL_IB_HCA=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
  -e NCCL_IB_GID_INDEX=3
  -e NCCL_SOCKET_IFNAME=enP7s7
  -e GLOO_SOCKET_IFNAME=enP7s7
  -e NCCL_DEBUG=WARN
  -e NCCL_DEBUG_SUBSYS=INIT
  -e HF_HUB_OFFLINE=1
  -e SGLANG_ENABLE_JIT_DEEPGEMM=1
  -e "LD_PRELOAD=/opt/ncclpin.so $PIP_NCCL"
  -e NCCL_ALGO=RING -e NCCL_BUFFSIZE=8388608 -e NCCL_CROSS_NIC=1
  -e NCCL_CUMEM_ENABLE=0 -e NCCL_CUMEM_HOST_ENABLE=0
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_MERGE_NICS=0 -e NCCL_IB_RETRY_CNT=7
  -e NCCL_IB_SUBNET_AWARE_ROUTING=1 -e NCCL_IB_TIMEOUT=1000 -e NCCL_IB_TOS=46
  -e NCCL_IGNORE_CPU_AFFINITY=1 -e NCCL_LL128_BUFFSIZE=-2
  -e NCCL_MAX_NCHANNELS=4 -e NCCL_MIN_NCHANNELS=4
  -e NCCL_NET_PLUGIN=none -e NCCL_P2P_DISABLE=1
  -e NCCL_PROTO=LL,LL128,Simple -e NCCL_SET_THREAD_NAME=1 -e NCCL_SHM_DISABLE=1
  -e NCCL_TUNER_THRESHOLD=40960 -e NCCL_VERSION=2.28.3-1
  -e PYTHONPATH=/opt/dsv41/adapter:/opt/b12x-tree
  -e DSV41_MOE_B12X_NEXT=1
  -e DSV41_LAUNCHER=tp4
  -e OFFLOAD_MODE=nvme
  -e DSV41_SOURCE="$MOUNT_TGT"
  -e DSV41_CACHE_GIB=1
  -e DSV41_IO_THREADS=96
  -e DSV41_RESIDENT_SCALES=0
  -e DSV41_ENGRAM_PREFETCH=1
  -e DSV41_ENGRAM_PREFETCH_ROWS=4096
  -e DSV41_ENGRAM_CHUNK_LIFETIME=1
  -e DSV41_ENGRAM_CACHE_GIB=1
  -e DSV41_CACHE_WAYS=16
  -e DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES=134217728
  -e DSV41_DG_SPARSE_SM121=1
  -e DSV41_PACKED_DIR=/engram
  -e NNODES=4
  -e DSV41_STATS_SECONDS=60
  -e SGLANG_ENABLE_DSV41_ENGRAM_HOST_TABLE=0
  -e MALLOC_ARENA_MAX=2
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False
  -e TP_SIZE=4
  -e DSV41_FP4KV_PORT=1
)
# 注：本面=r3-boot-arm.sh COMMON_ENV（:216-283）逐字（勘正 2：首靴红实证 C24 剥离面
#   缺 DSV41_MOE_B12X_NEXT=1 ⇒ Mxfp4FlashinferCutlassMoEMethod 576 中间维 128 对齐墙
#   崩——「零 DSV41_* 性能键」律只辖臂 env〔51 键族零注入〕，启动器公共面=生产同形；
#   boot-fail-logs/head.exit.log ValueError 面在档）。「臂 env 注入」叠在上=仅 5 约定键。
# 臂 env 注入（r3-boot-arm.sh 同律：逐行 docker -e；A4/性能键已核零命中）
for line in "${ARM_KEYVALS[@]}"; do COMMON_ENV+=(-e "$line"); info "[arm] +env ${line%%=*}"; done

# ── SERVER_ARGS：生产逐字面（r3-boot-arm.sh:356-393 逐项）+ 阶梯映射 ───────────
PROD_BASE=(
  --model-path "$MOUNT_TGT"
  --served-model-name deepseek-v4.1-flash
  --tp-size 4 --ep-size 1 --nnodes 4
  --dist-init-addr "${HEAD_IP}:${DIST_PORT}"
  --mem-fraction-static 0.90
  --chunked-prefill-size 4096
  --cuda-graph-max-bs-decode 16
  --context-length 600000
  --max-running-requests 16
  --dist-timeout 900
  --enable-metrics
  --watchdog-timeout 1800
  --moe-runner-backend flashinfer_mxfp4
  --json-model-override-args '{"candidate_topk_blocks": 2048}'
  --fp8-gemm-backend flashinfer_cutlass
  --max-total-tokens 9600000
)
SPEC6_ARGS=(--prefill-decode-interval 16 --max-queued-requests 32 --min-free-slots-delay 1 --enable-decoder-swa-bounded-replay --reasoning-parser deepseek-v41 --swa-prefix-tails 256)
SERVER_ARGS=("${PROD_BASE[@]}")
# GRAPHS 阶梯位：0=换出 --cuda-graph-max-bs-decode 16 → --disable-cuda-graph；1=生产逐字位保持
if [ "$GRAPHS" = 0 ]; then
  _filt=(); _skip=0
  for _a in "${SERVER_ARGS[@]}"; do
    if [ "$_skip" = 1 ]; then _skip=0; continue; fi
    if [ "$_a" = "--cuda-graph-max-bs-decode" ]; then _skip=1; continue; fi
    _filt+=("$_a")
  done
  SERVER_ARGS=("${_filt[@]}" --disable-cuda-graph)
fi
# SPEC 阶梯位：k6=生产 SPEC6 形（DSPARK+六参；锚=FL6-PROMO lib.sh SPEC5/SPEC6 逐字）
if [ "$SPEC" = k6 ]; then
  SERVER_ARGS+=(--speculative-algorithm DSPARK "${SPEC6_ARGS[@]}")
fi

# ── 参数层断言（fail-closed 前移；生产逐字继承面+阶梯位双向校验）────────────────
ARGS_STR="$(printf '%s ' "${SERVER_ARGS[@]}")"
grep -qF -- "--model-path $MOUNT_TGT"                <<<"$ARGS_STR" || die "VL41N 红：model-path≠$MOUNT_TGT"
grep -qF -- '--served-model-name deepseek-v4.1-flash' <<<"$ARGS_STR" || die "VL41N 红：served-model-name≠deepseek-v4.1-flash"
grep -qF -- '--tp-size 4 --ep-size 1 --nnodes 4'     <<<"$ARGS_STR" || die "VL41N 红：tp/ep/nnodes≠4/1/4"
grep -qF -- "--dist-init-addr ${HEAD_IP}:${DIST_PORT}" <<<"$ARGS_STR" || die "VL41N 红：dist-init-addr 位漂移"
grep -qF -- '--mem-fraction-static 0.90'             <<<"$ARGS_STR" || die "VL41N 红：mem-fraction≠0.90"
grep -qF -- '--chunked-prefill-size 4096'            <<<"$ARGS_STR" || die "VL41N-T 红：chunked-prefill≠4096（mm prefill 分块打分钉）"
grep -qF -- '--context-length 600000'                <<<"$ARGS_STR" || die "VL41N 红：context-length≠600000"
grep -qF -- '--max-running-requests 16'              <<<"$ARGS_STR" || die "VL41N 红：mrr≠16（生产同值）"
grep -qF -- '--dist-timeout 900'                     <<<"$ARGS_STR" || die "VL41N 红：dist-timeout≠900"
grep -qF -- '--enable-metrics'                       <<<"$ARGS_STR" || die "VL41N 红：enable-metrics 缺"
grep -qF -- '--watchdog-timeout 1800'                <<<"$ARGS_STR" || die "VL41N 红：watchdog-timeout≠1800"
grep -qF -- '--moe-runner-backend flashinfer_mxfp4'  <<<"$ARGS_STR" || die "VL41N 红：moe-runner-backend≠flashinfer_mxfp4"
grep -qF -- '--json-model-override-args {"candidate_topk_blocks": 2048}' <<<"$ARGS_STR" || die "VL41N 红：json-model-override-args 位漂移（生产逐字）"
grep -qF -- '--fp8-gemm-backend flashinfer_cutlass'  <<<"$ARGS_STR" || die "VL41N 红：fp8-gemm-backend≠flashinfer_cutlass"
grep -qF -- '--max-total-tokens 9600000'             <<<"$ARGS_STR" || die "VL41N 红：池 pin≠9600000（生产同值 R3.4；VL 自推 8,847,616=楔死前科禁续）"
grep -qE -- '--cuda-graph-backend|--enable-prefill-cuda-graph|--enable-decode-cuda-graph' <<<"$ARGS_STR" && die "A5 红：显式图 backend 指定"
# 阶梯位双向校验
if [ "$GRAPHS" = 1 ]; then
  grep -qF -- '--cuda-graph-max-bs-decode 16' <<<"$ARGS_STR" || die "A5 红：GRAPHS=1 而 --cuda-graph-max-bs-decode 16 缺（生产逐字位）"
  grep -qF -- '--disable-cuda-graph'          <<<"$ARGS_STR" && die "A5 红：GRAPHS=1 而 --disable-cuda-graph 在"
else
  grep -qF -- '--disable-cuda-graph'          <<<"$ARGS_STR" || die "A5 红：GRAPHS=0 未落实"
  grep -qE -- '--cuda-graph-max-bs'           <<<"$ARGS_STR" && die "A5 红：GRAPHS=0 而 cuda-graph-max-bs 在"
fi
if [ "$SPEC" = 0 ]; then
  n_spec=$(grep -cE -- '--speculative-algorithm' <<<"$ARGS_STR" || true); [ "$n_spec" = 0 ] || die "A6 红：SPEC=0 而 spec 参数数=$n_spec"
  grep -qE -- '--(reasoning|tool-call)-parser' <<<"$ARGS_STR" && die "A2 红：SPEC=0 而 parser 显式指定"
  grep -qE -- '--enable-(decoder|encoder)-swa-bounded-replay' <<<"$ARGS_STR" && die "A1 红：SPEC=0 而 bounded-replay 旗标在"
else
  n_spec=$(grep -cE -- '--speculative-algorithm' <<<"$ARGS_STR" || true); [ "$n_spec" = 1 ] || die "A6 红：SPEC=k6 而 spec 参数数=$n_spec≠1"
  grep -qF -- '--speculative-algorithm DSPARK' <<<"$ARGS_STR" || die "A6 红：非 DSPARK"
  for _pa in "${SPEC6_ARGS[@]}"; do
    case "$_pa" in --*) grep -qF -- "$_pa" <<<"$ARGS_STR" || die "A6 红：SPEC6 六参缺位：$_pa";; esac
  done
fi
# 与生产逐字 diff 仅 SPEC/CG 阶梯位（§3.2 断言工程化）：L3 形全量等价核
if [ "$SPEC" = k6 ] && [ "$GRAPHS" = 1 ]; then
  _prod_full="$(printf '%s\n' "${PROD_BASE[@]}" --speculative-algorithm DSPARK "${SPEC6_ARGS[@]}" | sort | md5sum | cut -d' ' -f1)"
  _mine="$(printf '%s\n' "${SERVER_ARGS[@]}" | sort | md5sum | cut -d' ' -f1)"
  [ "$_prod_full" = "$_mine" ] || die "VL41N 红：k6+CG1 级 SERVER_ARGS 与生产全量面不等价（vl 面零参数增量红线）"
  info "L3 全量等价核绿：k6+CG1 级=生产 serve 参数面逐字（零 vl 增量）"
fi
n_ov=$(printf '%s\n' "${DOCKER_HW[@]}" | grep -c ':/sgl-workspace/sglang/sglang/' || true); [ "$n_ov" = 0 ] || die "A8 红：DOCKER_HW overlay 挂载行=$n_ov ≠0（V4.1 原生臂零 overlay）"
[ -f "$ENG_HOST/engram-l1-r0of4.bin" ] || die "A8 红：engram rank0 分片缺（$ENG_HOST；生产同形面=adapter pread 挂载四秩承载，勘正 2）"
grep -q 'expandable_segments:True' <<<"$(printf '%s\n' "${COMMON_ENV[@]}")" && die "红：expandable_segments:True（GB10 NaN 双禁）"
grep -qE '^(DSV41_MOE_B12X_NEXT=1|-e DSV41_MOE_B12X_NEXT=1)$' <<<"$(printf '%s\n' "${COMMON_ENV[@]}")" || die "勘正 2 断言：COMMON_ENV 缺 DSV41_MOE_B12X_NEXT=1（576 对齐墙免疫键，生产同形）"
info "参数层断言全绿（生产逐字 15 位+阶梯位双向+零 overlay+零 engram+allocator 禁项零；vl 面零参数增量）"
# 水位断言（fail-closed 参数位；VL 靴槽=floor 6000 沿产线常规线，§5 G-V4.4）
WATER_MARK_FLOOR_MB="${WATER_MARK_FLOOR_MB:-6000}"
POOL_FINGERPRINT_EXPECT="${POOL_FINGERPRINT_EXPECT:-9600000}"

# ── 4b. 靴前 DRY-RUN 段（强制；段内零 ssh/零 docker/零 curl）─────────────────────
info "== VL41N 形推导表（V4.1-Flash 476G/池 9.6M pin/ctx600k/mrr16/chunk4096；mm 面原生启用）=="
info "  生产同形面：mem-fraction 0.90+池 pin 9,600,000（R3.4 注记=main fp8 KV 池≈17GB/rank，CUDA 总≈45G，余量≈70G）"
info "  mm 启用面：enable_multimodal 缺省 True+auto-detect 门（deepseek_v41 ∧ vision_n_layers>0）→零参数零文件（§1.1）"
info "  阶梯面：L1=SPEC0/GRAPHS0（本靴）→L2=k6/GRAPHS0→L3=k6/CG-bs16=生产全量形；每级 G-V1 轻量复跑（§7 S4）"
info "  水位地板=${WATER_MARK_FLOOR_MB}M（产线常规线沿袭）+UMA 靴窗中止门 4G+mm 足迹哨=F7 J6 判读线（>8G 拒新 mm 即停窗）"
info "  靴后 mm 三直证=triton_attn 两行+mm KV 0.10G 预留+processors 扫描（四机逐机；生产同款锚 :236-237/:277）"
# ② 断言判别力自检（反向用例：坏输入=4.8M 旧池/131072 旧 ctx/mrr12 旧值/chunk 16384）
ST_BAD='--model-path x --served-model-name y --max-total-tokens 4800000 --context-length 131072 --max-running-requests 12 --chunked-prefill-size 16384 --disable-cuda-graph'
grep -qE -- '--max-total-tokens 9600000'   <<<"$ST_BAD" && die "自检红：池断言对 4.8M 旧值无判别力"
grep -qE -- '--context-length 600000'      <<<"$ST_BAD" && die "自检红：ctx 断言对 131072 旧值无判别力"
grep -qE -- '--max-running-requests 16'    <<<"$ST_BAD" && die "自检红：mrr 断言对 12 旧值无判别力"
grep -qE -- '--chunked-prefill-size 4096'  <<<"$ST_BAD" && die "自检红：chunk 钉对 16384 无判别力"
# 池指纹带自检（9.6M±2%=[9,408,000,9,792,000]；4.8M/7.2M/VL 自推 8,847,616 必在带外）
lo_t=$((POOL_FINGERPRINT_EXPECT*98/100)); hi_t=$((POOL_FINGERPRINT_EXPECT*102/100))
[ "$lo_t" = 9408000 ] && [ "$hi_t" = 9792000 ] || die "自检红：池指纹带算术错 lo=$lo_t hi=$hi_t（期 [9408000,9792000]）"
for _bad_v in 4800000 7200000 8847616; do
  { [ "$_bad_v" -ge "$lo_t" ] && [ "$_bad_v" -le "$hi_t" ]; } && die "自检红：池指纹带 [${lo_t},${hi_t}] 含前科值 $_bad_v（带宽过宽）"
done
# 黑名单断言自检（A1 旗标坏输入必命中）
grep -qE -- '--enable-(decoder|encoder)-swa-bounded-replay' <<<"$ST_BAD --enable-decoder-swa-bounded-replay" || die "自检红：A1 黑名单正则不咬坏旗标"
# overlay 空断言互斥判别力自检（STDVL 形键必被位模式咬中=拒起面在）
printf 'SGLANG_OVERLAY_DIR=/tmp/x\n' | grep -q '^SGLANG_OVERLAY_DIR=' || die "自检红：overlay 空断言对 STDVL 形键无判别力"
printf 'DSV41_PREFILL_SP=1\n'        | grep -qE '^(DSV41_|SGLANG_DSV4_)' || die "自检红：性能键零面断言对 DSV41_* 键无判别力"
info "断言判别力自检绿（反向用例 9 组全咬：池/ctx/mrr/chunk/指纹带×3（4.8M+7.2M+自推 8.85M）/A1 黑名单）"
if [[ "$DRY_RUN" = 1 ]]; then
  info "DRY-RUN 完成（臂 env+A4/X1/性能键零面+overlay 空+参数层 15 位+阶梯双向+推导表+自检全绿）——零集群退出（未触 ssh/docker/curl）"
  exit 0
fi
info "DRY-RUN 段过（活靴继续；本段输出已入日志）"

# ── 5. 失败路径免疫（先存后删→boot-fail-logs/）────────────────────────────────
cleanup_on_fail(){
  local rc=$?; trap - EXIT INT TERM
  (( rc == 0 )) && return 0
  mkdir -p "$D/boot-fail-logs"
  echo "[cleanup] rc=$rc — 先存容器日志后删容器（防 UMA 楔死续吃）"
  docker logs "$HEAD_CTN" > "$D/boot-fail-logs/head.exit.log" 2>&1 || true
  docker rm -f "$HEAD_CTN" >/dev/null 2>&1 || true
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ph <<<"$w"
    ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "docker logs $WORKER_CTN" > "$D/boot-fail-logs/worker-$_h.exit.log" 2>&1 || true
    ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "docker rm -f $WORKER_CTN" >/dev/null 2>&1 || true; done
  echo "[cleanup] 日志在 $D/boot-fail-logs/*.exit.log"; }
trap cleanup_on_fail EXIT

# ── 6. 起 workers（per-machine MODEL_DIR；零 overlay 同形四秩）──────────────────
info "== 起 workers =="
for w in "${WORKERS[@]}"; do
  IFS='|' read -r rank host ip phca <<<"$w"
  src="${MD[$host]}"
  ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "docker rm -f $WORKER_CTN >/dev/null 2>&1 || true"
  REMOTE_CMD=(docker run -d --name "$WORKER_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}"
              -e "NCCL_IB_PEER_HCA=$phca"
              -v "$src:$MOUNT_TGT:ro"
              -v "$ENG_HOST:/engram:ro"
              "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" --node-rank "$rank")
  REMOTE_STR="$(printf '%q ' "${REMOTE_CMD[@]}")"
  ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "$REMOTE_STR" || die "worker rank $rank docker run 失败"
  sleep 8
  state="$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "docker inspect -f '{{.State.Running}}' $WORKER_CTN 2>/dev/null" | tr -d '\r')"
  if [[ "$state" != "true" ]]; then
    warn "worker rank $rank ($host) 起后即死："; ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "docker logs --tail 30 $WORKER_CTN" 2>&1 || true
    die "worker rank $rank 起败"; fi
  info "  rank $rank @ $host 存活（MODEL_DIR host=$src→容器 $MOUNT_TGT；零 overlay 原生形；/engram pread 挂载）"
done

# ── 7. 起 head ──
info "== 起 head (rank 0, API :$API_PORT) =="
docker rm -f "$HEAD_CTN" >/dev/null 2>&1 || true
docker run -d --name "$HEAD_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}" \
  -e "NCCL_IB_PEER_HCA=$PEER_HCA_HEAD" \
  -v "${MD[${NODE01_HOST}]}:$MOUNT_TGT:ro" \
  -v "$ENG_HOST:/engram:ro" \
  "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" \
  --node-rank 0 --host 0.0.0.0 --port "$API_PORT"
sleep 8
[[ "$(docker inspect -f '{{.State.Running}}' "$HEAD_CTN" 2>/dev/null)" == "true" ]] || { docker logs --tail 30 "$HEAD_CTN" 2>&1 || true; die "head 起败"; }
info "head 存活"

# ── 8. 健康轮询（≤35 分钟；靴窗 UMA 水位中止门 4G）+ mm 三直证 ─────────────────
dump_all(){ echo "---- head 尾 40 ----"; docker logs --tail 40 "$HEAD_CTN" 2>&1 || true
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ph <<<"$w"
    echo "---- $_h 尾 30 ----"; ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "docker logs --tail 30 $WORKER_CTN" 2>&1 || true; done; }
mm_log(){ # <target|-> <ctn>：四机 mm 三直证计数行（G-V3；判读=逐机三面≥1）
  local tgt="$1" ctn="$2" log
  if [[ "$tgt" == "-" ]]; then log="$(docker logs "$ctn" 2>&1 | tr '\r' '\n')"; else log="$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$tgt" "docker logs $ctn 2>&1" 2>/dev/null | tr '\r' '\n')"; fi
  local t1 t2 kv pr
  t1=$(grep -cF 'Multimodal attention backend not set. Use triton_attn.' <<<"$log" || true)
  t2=$(grep -cF 'Using triton_attn as multimodal attention backend.' <<<"$log" || true)
  kv=$(grep -cF 'Reserving 0.10 GB of the KV budget for post-sizing multimodal allocations' <<<"$log" || true)
  pr=$(grep -cF 'multimodal.processors' <<<"$log" || true)
  echo "$tgt mm_triton_notset=$t1 mm_triton_using=$t2 mm_kv010=$kv mm_processors=$pr"; }
info "轮询 health（≤35 分钟；V4.1-Flash 476G〔01/02 本地+03/04 NFS〕；mm 原生启用=enable_multimodal 缺省 True）"
deadline=$(( $(date +%s) + 2100 ))
while (( $(date +%s) < deadline )); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    info "== VL41N 栈 UP：http://$HEAD_IP:$API_PORT（V4.1 原生零 overlay+SPEC=$SPEC+GRAPHS=$GRAPHS，CTN=$CTN_PREFIX）=="
    docker logs "$HEAD_CTN" 2>&1 | grep -E 'max_total_num_tokens=|available_gpu_mem=|Load weight end' | tail -3 || true
    # 池指纹断言（9.6M±2%）
    pool=$(docker logs "$HEAD_CTN" 2>&1 | grep -oE 'max_total_num_tokens=[0-9]+' | tail -1 | cut -d= -f2)
    [ -n "$pool" ] || die "VL41N 红：池指纹不可读"
    lo=$((POOL_FINGERPRINT_EXPECT*98/100)); hi=$((POOL_FINGERPRINT_EXPECT*102/100))
    [ "$pool" -ge "$lo" ] && [ "$pool" -le "$hi" ] || die "VL41N 红：池指纹 $pool ∉ [$lo,$hi]"
    # 水位断言（四机 ≥ floor；产线常规线 6000）
    m=$(memavail); [ "$m" -ge "$WATER_MARK_FLOOR_MB" ] || die "VL41N 红：head MemAvailable=${m}M < ${WATER_MARK_FLOOR_MB}M"
    for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ph <<< "$w"
      mw=$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "awk '/MemAvailable/{printf \"%d\", \$2/1024}' /proc/meminfo" 2>/dev/null)
      [ "${mw:-0}" -ge "$WATER_MARK_FLOOR_MB" ] || die "VL41N 红：$_h MemAvailable=${mw}M < ${WATER_MARK_FLOOR_MB}M"; info "  $_h MemAvailable=${mw}M"; done
    # mm 三直证断言（G-V3 承载；四机逐机三面≥1+triton 两行合计≥2 机型面）
    info "== mm 三直证（四机逐机；生产同款锚 FL6-PROMO pre-stop log :236-237/:277）=="
    MM_LOG="$D/boot-checks/mm-direct-${ARM_TAG}.txt"; : > "$MM_LOG"; mmfail=0
    mm_log "-" "$HEAD_CTN" | tee -a "$MM_LOG"
    for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"; mm_log "$_h" "$WORKER_CTN" | tee -a "$MM_LOG"; done
    while read -r ln; do
      case "$ln" in
        *mm_triton_notset*)
          _h=$(awk '{print $1}' <<<"$ln"); _t1=$(grep -oE 'mm_triton_notset=[0-9]+' <<<"$ln" | cut -d= -f2)
          _t2=$(grep -oE 'mm_triton_using=[0-9]+' <<<"$ln" | cut -d= -f2)
          _kv=$(grep -oE 'mm_kv010=[0-9]+' <<<"$ln" | cut -d= -f2)
          _pr=$(grep -oE 'mm_processors=[0-9]+' <<<"$ln" | cut -d= -f2)
          { [ "${_t1:-0}" -ge 1 ] && [ "${_t2:-0}" -ge 1 ] && [ "${_kv:-0}" -ge 1 ] && [ "${_pr:-0}" -ge 1 ]; } || { warn "mm 直证缺面：$ln"; mmfail=1; }
          ;;
      esac
    done < "$MM_LOG"
    [ "$mmfail" = 0 ] || { cat "$MM_LOG"; die "VL41N mm 三直证红（四机逐机 triton 两行+KV 0.10G+processors 扫描有缺面）"; }
    info "mm 三直证绿（四机逐机=triton_attn 两行+mm KV 0.10G 预留+processors 扫描全在档）"
    info "VL41N 断言组绿（池指纹 $pool∈[$lo,$hi]+ctx 600000+mrr 16+四机水位≥${WATER_MARK_FLOOR_MB}M+mm 三直证四机全）"
    exit 0
  fi
  st="$(docker inspect -f '{{.State.Status}}' "$HEAD_CTN" 2>/dev/null)"
  [[ "$st" != "running" ]] && { warn "head 退出"; dump_all; die "VL41N 首靴失败"; }
  m=$(memavail)
  if (( m < 4000 )); then warn "head 靴窗 MemAvailable=${m}M < 4000M — UMA 超卖中止"; dump_all; die "UMA 水位红线（靴窗）"; fi
  sleep 10
done
warn "超时"; dump_all; die "VL41N 健康超时"
