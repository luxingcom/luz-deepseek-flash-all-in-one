#!/usr/bin/env bash
# r3-boot.sh — R3 梯级：main-79cafec0 引擎 + fabric 资产 + adapter pread engram
#
# 谱系：U1 v1-v8 教训全携（doc92 §五/§六、doc94）——
#   R1 fabric：4-HCA+逐秩 PEER_HCA+ring-only NCCL（fork 库盖 pip 路径同身份；pin 库挂 /opt/ncclpin.so）
#   MoE：humming（SM120 cutlass 128 对齐墙 576 规避）
#   engram：**adapter pread 按需**（论文 A9 部署形态；严禁整体加载——A1/A2）
#   KV：stock 自推池（不设 MAX_TOTAL_TOKENS；R6 才带 fork-v4-fp4）；boot log 核对 full_token
# 硬门：起栈前四机对称 drop_caches + UMA 总账（MemAvailable ≥ 100G）；生产容器守卫。
set -euo pipefail

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
# net-rebuild-20261015 镜像同步：管理段重编址三处通道址→管理段四址（IMAGE/HEAD_IP/WORKERS；
# 语义参数零动；本镜像 vs 产线现役形的参面差〔NCCL 面/A8/A9/环网补丁链退役〕留后续交付同步窗）。
DIST_PORT="20000"
API_PORT="${API_PORT:-8899}"   # L10 用 8898：避开 concurrency-proxy→8899 的活生产转发路径（㉑/㉕ 防污染）
SPEC="${SPEC:-0}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8)
ADAPTER_DIR="$HOME/migrate-assets/dsv41/adapter"          # 持久位（教训㊲）
B12X_DIR="$HOME/migrate-assets/b12x"                       # b12x_next 计算树（fork 验证路径，U2 暂存件）
NCCL_DIR="$HOME/migrate-assets/nccl-ringonly"
NCCLPIN="$HOME/migrate-assets/ncclpin.so"
PIP_NCCL=/opt/sglang/lib/python3.12/site-packages/nvidia/nccl/lib/libnccl.so.2
ENG_HOST_HEAD="$HOME/dsv41-engram"                        # rank0 打包分片
ENG_HOST_WORKER="\$HOME/dsv41-engram"  # rank1/2/3 打包分片（2026-10-10 ENV-UNIFY 四机统一路径）

# rank|host|ip|宿主权重路径|engram 宿主路径（绝对路径，四机同用户）|该秩 PEER_HCA
# 权重面（2026-09-29 事故后定稿）：rank2/3 走 /data/models/dsv41-net = NFS 全量树
# （03←<fabric-ip>=01 主源；04←<fabric-ip>=02 备源，均 ro nfs4 nconnect=4，已入 fstab）。
# stock main 的 filter_duplicate_safetensors_files 在装载前做全 48 分片在位校验——
# 03/04 曾本地置 47/48 尾分片（逐文件直读设计态，2026-10-10 ENV-UNIFY 清理=设计未采用 R-批4）：
# 尾分片已删，47/48 与其余分片同走 NFS 全量树；索引校验全树可见 ⇒ NFS 硬前置不变。
WORKERS=(
  "1|${NODE02_HOST}|${NODE02_IP}|/data/models/DeepSeek-V4.1-Flash|/home/liux***ya/dsv41-engram|0=rocep1s0f1,roceP2p1s0f1;2=rocep1s0f0,roceP2p1s0f0"
  "2|${NODE04_HOST}|${NODE04_IP}|/data/models/dsv41-net|/home/liux***ya/dsv41-engram|1=rocep1s0f0,roceP2p1s0f0;3=rocep1s0f1,roceP2p1s0f1"
  "3|${NODE03_HOST}|${NODE03_IP}|/data/models/dsv41-net|/home/liux***ya/dsv41-engram|0=rocep1s0f0,roceP2p1s0f0;2=rocep1s0f1,roceP2p1s0f1"
)
PEER_HCA_HEAD="1=rocep1s0f1,roceP2p1s0f1;3=rocep1s0f0,roceP2p1s0f0"
HEAD_MODEL_SRC="/data/models/DeepSeek-V4.1-Flash"
CTN_PREFIX="r3boot"
HEAD_CTN="${CTN_PREFIX}-head"
WORKER_CTN="${CTN_PREFIX}-worker"
MOUNT_TGT="/models/DeepSeek-V4.1-Flash"

info() { printf '[+] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }
die()  { printf '[x] %s\n' "$*" >&2; exit 1; }
memavail() { awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo; }

# ── 0. 失败路径免疫（2026-09-29 10:45 OOM 整机重启事故的放大器=楔死容器无人收）──
#    非零退出时：容器日志全量落盘 ~/l10-incident/，然后四机 rm 容器。
#    CUDA/UMA 不进 cgroup（--memory 32g 拦不住），楔死容器会持续吃设备内存直至整机 OOM。
INCIDENT_DIR="$HOME/l10-incident"
cleanup_on_fail() {
  local rc=$?
  trap - EXIT INT TERM
  (( rc == 0 )) && return 0
  mkdir -p "$INCIDENT_DIR"
  echo "[cleanup] rc=$rc — 落盘容器日志并清除容器（防 UMA 楔死续吃）"
  docker logs "$HEAD_CTN" > "$INCIDENT_DIR/head.exit.log" 2>&1 || true
  docker rm -f "$HEAD_CTN" >/dev/null 2>&1 || true
  for w in "${WORKERS[@]}"; do
    IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"
    ssh "${SSH_OPTS[@]}" "$_h" "docker logs $WORKER_CTN" > "$INCIDENT_DIR/worker-$_h.exit.log" 2>&1 || true
    ssh "${SSH_OPTS[@]}" "$_h" "docker rm -f $WORKER_CTN" >/dev/null 2>&1 || true
  done
  echo "[cleanup] 日志在 $INCIDENT_DIR/*.exit.log"
}
trap cleanup_on_fail EXIT

# ── 1. 前置守卫：四机无生产容器、GPU 空闲 ────────────────────────────────────
guard_node() {
  local name="$1" target="$2" out
  if [[ "$target" == "-" ]]; then out=$(docker ps --format '{{.Names}}' 2>/dev/null; nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)
  else out=$(ssh "${SSH_OPTS[@]}" "$target" "docker ps --format '{{.Names}}' 2>/dev/null; nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null" 2>/dev/null) || die "ssh $target 不通"; fi
  local ctns pids
  ctns=$(grep '^dsv41-' <<<"$out" || true); pids=$(grep -E '^[0-9]+$' <<<"$out" | grep -v '^$' || true)
  [[ -n "$ctns" ]] && die "$name 有生产容器: $ctns"
  [[ -n "$pids" ]] && die "$name GPU 被占 (pid: $(echo $pids | tr '\n' ' '))"
  info "$name: 无容器、GPU 空闲"
}
info "== 前置守卫 =="
guard_node "head ${NODE01_HOST}" -
for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"; guard_node "worker $_h" "$_h"; done


# ── 1.5 B2 GID idx3 断言（2026-10-08 三次翻转杀产线实证；fail-closed 拒启）────
# 判读线零改：NCCL_IB_GID_INDEX=3 不动；洞=大声拒启走 FABRIC-GID-REPAIR-RUNBOOK §2。
# （FABRIC-SELFHEAL-DESIGN-20261008 §六；语义=s4_bench 自带预检同判据+端口 ACTIVE 同读）
gid3_check() {  # <ssh目标|->
  local t=$1 bad=""
  local out
  if [[ "$t" == "-" ]]; then out=$(gid3_probe_local); else
    out=$(ssh "${SSH_OPTS[@]}" "$t" "$(declare -f gid3_probe_local); gid3_probe_local"); fi
  bad=$(grep -v '^OK ' <<<"$out" || true)
  [[ -z "$bad" ]] || die "[B2] GID idx3 断言红（拒启；runbook §2 修复后重靴）：
$bad"
  info "[B2] $(grep -c '^OK ' <<<"$out")/4 口 idx3=RoCE v2 在位"
}
gid3_probe_local() {  # 四 HCA：idx3 必须 RoCE v2 非空+端口 ACTIVE
  for c in rocep1s0f0 rocep1s0f1 roceP2p1s0f0 roceP2p1s0f1; do
    g=$(cat /sys/class/infiniband/$c/ports/1/gids/3 2>/dev/null)
    ty=$(cat /sys/class/infiniband/$c/ports/1/gid_attrs/types/3 2>/dev/null)
    st=$(cat /sys/class/infiniband/$c/ports/1/state 2>/dev/null)
    if [[ "$ty" == "RoCE v2" && -n "$g" && "$g" != 0000:0000:0000:0000:0000:0000:0000:0000 \
          && "$st" == *ACTIVE ]]; then echo "OK $c"; else
      echo "HOLE $c idx3=[$g] type=[$ty] state=[$st]"; fi
  done
}
info "== B2 GID 16 口 idx3 断言 =="
gid3_check "-"
for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"; gid3_check "$_h"; done

# ── 2. UMA 总账前置（A1/A2 硬门：严禁整表；起栈前水位 ≥100G）+ 对称 drop_caches ──
info "== UMA 总账 + 四机对称 drop_caches =="
drop_and_check() {  # drop_and_check <显示名> <ssh目标|->
  local name="$1" target="$2" cmd pw
  pw=$(cat ~/.sudopw)
  cmd="printf '%s\n' '$pw' | sudo -S sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; awk '/MemAvailable/{printf \"%d\", \$2/1024}' /proc/meminfo"
  local m
  if [[ "$target" == "-" ]]; then m=$(eval "$cmd"); else m=$(ssh "${SSH_OPTS[@]}" "$target" "$cmd" 2>/dev/null); fi
  [[ "${m:-0}" -ge 100000 ]] || die "$name drop 后 MemAvailable=${m}M < 100G（UMA 总账红，拒起）"
  info "$name drop_caches 后 ${m}M"
}
drop_and_check "head" "-"
for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"; drop_and_check "$_h" "$_h"; done

# ── 3. 资产在位核验（adapter/NCCL/打包分片/权重） ─────────────────────────────
[[ -d "$ADAPTER_DIR" && -f "$ADAPTER_DIR/sitecustomize.py" && -f "$ADAPTER_DIR/engram_backend.py" ]] || die "adapter 资产缺（~/migrate-assets/dsv41/adapter）"
[[ -f "$NCCL_DIR/libnccl.so.2.30.7" && -f "$NCCLPIN" ]] || die "NCCL 资产缺（~/migrate-assets）"
ls "$ENG_HOST_HEAD"/engram-l1-r0of4.bin >/dev/null 2>&1 || die "head 打包分片缺"
for w in "${WORKERS[@]}"; do
  IFS='|' read -r _rk _h _ip _src _eng _ph <<<"$w"
  ssh "${SSH_OPTS[@]}" "$_h" "test -f $_eng/engram-l1-r${_rk}of4.bin && test -f '$ADAPTER_DIR/sitecustomize.py' && test -f '$HOME/migrate-assets/nccl-ringonly/libnccl.so.2.30.7' && test -f '$HOME/migrate-assets/ncclpin.so' && test -f '$HOME/migrate-assets/b12x/b12x_next/__init__.py' && test -f '$_src/config.json'" \
    || die "$_h 资产面缺（adapter/NCCL/b12x_next/分片/权重）"
  info "  $_h 资产面 OK"
done

# ── 4. 公共面 ────────────────────────────────────────────────────────────────
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
  # SGLANG_ENABLE_JIT_DEEPGEMM 默认 True（保留=fork 姿态）。r5-r8 定谳：main 的
  # sparse/candidate indexer 路在 SM121 上三处插线断裂（dense 断言/topk_v2 CPU 标量/
  # metadata None），而 fork 生产根本不用 candidate 系统 ⇒ json 覆盖置 0 走全量 topk
  # （fork 同构：门关+force 开+页 64 铁律）。dg_sm121 门保持关（adapter 留树不武装）。
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
  # ── R3：adapter pread engram（论文 A9 部署形态；严禁整体加载）──
  # b12x-tree 进 PYTHONPATH 次位（sitecustomize 必须首位）；b12x_next=fork 生产验证的
  # MoE 计算路径（W4A8 原位重打包，无 2x 物化）。
  -e PYTHONPATH=/opt/dsv41/adapter:/opt/b12x-tree
  -e DSV41_MOE_B12X_NEXT=1
  -e DSV41_LAUNCHER=tp4
  -e OFFLOAD_MODE=nvme
  -e DSV41_SOURCE="$MOUNT_TGT"
  -e DSV41_CACHE_GIB=1
  -e DSV41_IO_THREADS=96
  -e DSV41_RESIDENT_SCALES=0
  -e DSV41_ENGRAM_PREFETCH=0
  -e DSV41_PACKED_DIR=/engram
  -e NNODES=4
  -e DSV41_STATS_SECONDS=60
  -e SGLANG_ENABLE_DSV41_ENGRAM_HOST_TABLE=0
  # ── 分配器（D 组纪律）──
  -e MALLOC_ARENA_MAX=2
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False
  # A7-S1（预审 P0）：tp3_pad 的 _tp() 缺省读 3 会把 tp4 引擎垫成 heads96/groups12/
  # vocab129408（decode 落垫-64 头回退+attn 权重 ×1.5）。fork 由 boot.py 从 .env
  # 设 TP_SIZE=4 遮蔽；main 树无此 env ⇒ 必须显式落。垫子全惰性，local=16 原生合法。
  -e TP_SIZE=4
  # L10（fp4-KV 回移，M6 判据）：fork-v4-fp4 四缝——layout 选择器/配置器重绑/890 账目/
  # SM120 repack 桥；mode 由 kv_fp4._inject_mode() 自动落 fork-v4-fp4（缺省注入是四缝
  # grep 的首行证据）。池行指纹 bytes_per_full_token≈890。回退=删此单行（banner 17→16，
  # 回 stock fp8 KV）。
  -e DSV41_FP4KV_PORT=1
)

SERVER_ARGS=(
  --model-path "$MOUNT_TGT"
  --served-model-name deepseek-v4.1-flash
  --tp-size 4 --ep-size 1 --nnodes 4
  --dist-init-addr "${HEAD_IP}:${DIST_PORT}"
  --mem-fraction-static 0.90
  --chunked-prefill-size 4096
  --cuda-graph-max-bs-decode 16
  --context-length 600000
  --max-running-requests 16
  # 2026-09-29 事故免疫：死秩快败（缺省 None=无限等；今天 ranks 2/3 死后 head/02
  # 各干等 30+ 分钟直至 01 UMA 螺旋）。900s 覆盖权重装载(~2min)+图捕获，余量充足。
  --dist-timeout 900
  --enable-metrics
  --watchdog-timeout 1800
  # 2026-09-29 二次事故裁定：humming 制备期内存累积（fp8 后处理+逐层重打包）在
  # ~77G/rank 权重驻留之上击穿 121G 机限（02 实测 avail=4.3G@layer19 ⇒ 四机 11:50 重启）。
  # 转 fork 生产同源路径。r6 定谳：fp8.get_quant_method 的 fp4 专家树认的枚举名是
  # flashinfer_mxfp4（SM120/121→Mxfp4FlashinferCutlassMoEMethod→adapter b12x_next 钩面）；
  # flashinfer_cutlass 不在树上⇒裸 Fp8 方法+triton runner 接 fp4 权重⇒形状断言崩。
  --moe-runner-backend flashinfer_mxfp4
  # r9：fork 同构索引器——checkpoint config.json 带 candidate_topk_blocks=2048（fork 视为
  # 未实现字段直接无视；main 实现了但 SM121 插线断裂）。只零 topk ⇒ make_candidate_indexer
  # 早退 dense；block_size=8 必须保留（dense publish_decode 的块几何取模用它，r9 实证）。
  --json-model-override-args '{"candidate_topk_blocks": 0}'
  # r10 census 定谳：无此参 ⇒ resolve_block_fp8_mxfp8_backend 判 UNSUPPORTED（只认显式
  # cutlass/cutedsl）⇒ [32,32]ue8m0 权重不序列化 MXFP8 ⇒ dense 全落 Triton w8a8 =
  # 42.2ms/步（grid160×81+256/36/56×40.7 次/步，204µs/GEMV 病理）。fin2 生产同参：
  # checkpoint 原生 mxfp8 形态 + 此参 + adapter mxfp8_b12x 重路由 cutlass→b12x。
  # 注意与 --moe-runner-backend（r6 判负的 flashinfer_cutlass）是两个不同参数面。
  --fp8-gemm-backend flashinfer_cutlass
  # R3.4（doc94 §G）：无 pin 时 stock main 池按 fraction 吃满只剩 12.1G，UMA 必破。
  # pin=生产同值 9.6M（main fp8 KV ⇒ 池≈17GB/rank，CUDA 总≈45G，余量≈70G）。
  --max-total-tokens 9600000
)
[[ "$SPEC" == "1" ]] && SERVER_ARGS+=(--speculative-algorithm DSPARK) || info "SPEC=0"

# ── 5. 起 workers（每秩 PEER_HCA+分片挂载） ────────────────────────────────────
info "== 起 workers =="
for w in "${WORKERS[@]}"; do
  IFS='|' read -r rank host ip src eng phca <<<"$w"
  ssh "${SSH_OPTS[@]}" "$host" "docker rm -f $WORKER_CTN >/dev/null 2>&1 || true"
  REMOTE_CMD=(docker run -d --name "$WORKER_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}"
              -e "NCCL_IB_PEER_HCA=$phca"
              -v "$src:$MOUNT_TGT:ro"
              -v "$eng:/engram:ro"
              "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" --node-rank "$rank")
  REMOTE_STR="$(printf '%q ' "${REMOTE_CMD[@]}")"
  ssh "${SSH_OPTS[@]}" "$host" "$REMOTE_STR" || die "worker rank $rank docker run 失败"
  sleep 8
  state="$(ssh "${SSH_OPTS[@]}" "$host" "docker inspect -f '{{.State.Running}}' $WORKER_CTN 2>/dev/null" | tr -d '\r')"
  if [[ "$state" != "true" ]]; then
    warn "worker rank $rank ($host) 起后即死："; ssh "${SSH_OPTS[@]}" "$host" "docker logs --tail 30 $WORKER_CTN" 2>&1 || true
    die "worker rank $rank 起败"
  fi
  info "  rank $rank @ $host 存活（PEER_HCA 已注入，/engram 已挂）"
done

# ── 6. 起 head ───────────────────────────────────────────────────────────────
info "== 起 head (rank 0, API :$API_PORT) =="
docker rm -f "$HEAD_CTN" >/dev/null 2>&1 || true
docker run -d --name "$HEAD_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}" \
  -e "NCCL_IB_PEER_HCA=$PEER_HCA_HEAD" \
  -v "$HEAD_MODEL_SRC:$MOUNT_TGT:ro" \
  -v "$ENG_HOST_HEAD:/engram:ro" \
  "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" \
  --node-rank 0 --host 0.0.0.0 --port "$API_PORT"
sleep 8
[[ "$(docker inspect -f '{{.State.Running}}' "$HEAD_CTN" 2>/dev/null)" == "true" ]] || { docker logs --tail 30 "$HEAD_CTN" 2>&1 || true; die "head 起败"; }
info "head 存活"

# ── 7. 健康轮询（≤20 分钟）+ boot log 池核对 ─────────────────────────────────
dump_all() {
  echo "---- head 尾 40 ----"; docker logs --tail 40 "$HEAD_CTN" 2>&1 || true
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"
    echo "---- $_h 尾 30 ----"; ssh "${SSH_OPTS[@]}" "$_h" "docker logs --tail 30 $WORKER_CTN" 2>&1 || true; done
}
info "轮询 health（≤20 分钟）"
deadline=$(( $(date +%s) + 1200 ))
while (( $(date +%s) < deadline )); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    info "== R3 栈 UP：http://$HEAD_IP:$API_PORT（main+pread engram，spec=$SPEC）=="
    docker logs "$HEAD_CTN" 2>&1 | grep -E 'full_token|max_total|KV cache|token.*pool' | tail -5 || true
    exit 0
  fi
  st="$(docker inspect -f '{{.State.Status}}' "$HEAD_CTN" 2>/dev/null)"
  [[ "$st" != "running" ]] && { warn "head 退出"; dump_all; die "R3 裸靴失败"; }
  # UMA 水位中止门（仅靴窗内生效；池门水位红线 4G）：靴期跌破=引擎装载体超卖，
  # 再等只会进驱动重试楔死螺旋（10:14 沉默→10:45 OOM 的 30 分钟空窗就是它）。
  m=$(memavail)
  if (( m < 4000 )); then
    warn "head 靴窗 MemAvailable=${m}M < 4000M — UMA 超卖，立即中止防楔死"
    dump_all; die "R3 UMA 水位红线（靴窗）"
  fi
  sleep 10
done
warn "超时"; dump_all; die "R3 健康超时"
