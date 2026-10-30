#!/usr/bin/env bash
# boot_mvl40exp_r2.sh — VL-NATIVE S5 臂=V4.0exp overlay 复原形驱动（新文件零改共享件；
#   窗=VL-NATIVE-WINCARD-20261013 §7 S5〔d21afc8〕）。
#   派生源=logs/W-OPTA-CLOSELINE-20261010/desk/boot_mvl_uv.sh（md5 313867a2 精化版）
#   逐字承袭：DRY-RUN 强制段/四机守卫/A9 指纹核/失败路径免疫/水位断言/overlay 28 件
#   fail-closed 挂载/SPEC∈{0,k6}+GRAPHS∈{0,1} 映射/ARM_SERVE_EXTRA 面。
#   本窗五处变体（法源=窗卡 §3.1 V4.0exp 臂列）：
#     ①D= 窗日志位→logs/VL-NATIVE-20261013；ARM_ENV_FILE 缺省→arms/VL40EXP-R2-C24T.env
#     ②WATER_MARK_FLOOR_MB 缺省→20480（STDVL-R2 认证形重推导值：R1 认证靴实测谷
#       21461M−1G→1024 倍数下取整；法源=arms/STDVL-K6CG-R2-C24T.env 头注）
#     ③MODEL_DIR 拓扑=boot_mvl_600k_48m.sh 段1 逐字（02=/data 分发源+03/04=NFS dsvl-net；
#       W-OPTA 版 03/04=/data 路径为 10-10 形，10-13 窗卡 §2.1 实测拓扑=C24 版）
#     ④overlay 源=复原树 ~/migrate-assets/vl-native/sglang-overlay.v4vl-79cafec0
#       （28 件正典集合指纹 cbf986df×4 机；归档区只读取件）
#     ⑤靴后新增 mm 直证断言（overlay 形判读线：mm KV 0.10G 预留+multimodal.processors
#       扫描+Multimodal processor concurrency 行；**无 triton_attn 两行**=overlay 形
#       mm 注意力走 dsv4 后端非 triton——锚=WOPTA-VLR2 teardown log 实测 0 命中）
# 用法: DRY_RUN=1 ARM_ENV_FILE=~/luz030-opt-campaign/arms/VL40EXP-R2-C24T.env ARM_TAG=VL40EXP-DRY \
#         bash dev/vl-native/boot_mvl40exp_r2.sh
#       ARM_TAG=VL40EXP-S5 ARM_ENV_FILE=~/luz030-opt-campaign/arms/VL40EXP-R2-C24T.env \
#         bash tools/boot-with-slotlock.sh bash dev/vl-native/boot_mvl40exp_r2.sh
# [UNIFY-COMPUTEPATH 窗内副本 boot_mvl_unify.sh — 派生源=本件（md5 313867a2）；零改在役件]
# boot_mvl_600k_48m.sh — C24-4.8M 形 VL 驱动包装（新增文件，零改共享件；在役
#   boot_mvl_600k.sh（T17 7.2M 形）未覆写）。
#   基=logs/T17-20261006/boot_mvl_600k.sh（=logs/O13B-20261006/boot_mvl_600k.sh
#   e457e564 修正版内容唯 D= 落点差异；原 3ff295f9 的 :319 remote awk \$2 断言壳
#   set -u 转义缺陷已修——O13B-VERDICT 靴1 窗具缺陷 A 判例）。
#   C24 变更四处（法源=用户指令 2026-10-06 C24+OPEN-23 事故注册 98749a4）：
#     ①SERVER_ARGS：--max-total-tokens 7200000→4800000（KV 池 7.2M 压缩到 4.8M；
#       设计点=CTX600k×8 并发恰等 4.8M=600,000×8）；ctx 600000/mrr 12 不变。
#     ②A7 断言同步改：池 pin 必在=4800000+池指纹带 4.8M±2%=[4,704,000,4,896,000]
#       （fail-closed 方向不变；VL 自推 8,847,616=VLW3 楔死前科禁续）。
#     ③水位地板按 4.8M 重推导（推导表=段4b 打印+WINCARD §二）：
#         基线谷 17,847MiB（O13B K5 水位谷，7.2M 形；16384 重钉的法源读数）
#         +池缩释放 16,219MiB（2.4M tok×7,086.75B/机=17.01G）
#         =预测谷 34,066MiB；−1G 安全垫→1024 倍数下取整=32,768
#         ⇒ WATER_MARK_FLOOR_MB 缺省 32768（首靴实测谷−1G 重钉=O13-VERDICT
#         裁定 4 同法；flush 尖峰不在语义内=OPEN-20 同律）。
#     ④靴前 DRY-RUN 段强制（8066bb4 模板修正 C24 落地）：段4b=推导表打印+断言
#       判别力自检（反向用例）；DRY_RUN=1 ⇒ 段2/3（ssh/docker 面）跳过+段4b 后
#       零集群退出；DRY_RUN=0 ⇒ 活靴（段4b 仍必经）。
#   KV 账（每机/每秩同口径，bytes_per_full_token=7,086.75B 实测 O13B/C12 同源）：
#     7.2M 形=7,200,000×7,086.75B=51.02G → 4.8M 形=4,800,000×7,086.75B=34.02G
#     （释放 17.01G/机）；静态自洽：池 34.02G+权重 42.0G（A9 BYTES÷TP4）=76.0G
#     <108.9G=0.90×121 mem-fraction 帽。
#   mm 侧瞬态控制面（OPEN-23=VL mm prefill 中途 NVML/调度器 rw-semaphore 楔死
#     家族正面缓解；INCIDENT-20261006-T17VL-OPEN23 §二.4）：
#     ·分块打分钉=--chunked-prefill-size 4096 断言化（C24-T 断言，防误放大）；
#     ·mm 批默认拒入沿 T17 C3（T61 谓词；K-mm 未闭账）——600k 认证负载全纯文本；
#     ·流式数据处理落点=C24-DOCTRINE §二原则（工程落位待 OPEN-23 深因卡派单）；
#     ·水位地板抬升 32768+靴窗 UMA 中止门 4G 沿基线。
#   红线沿基线：不 drop_caches（纯 MemAvailable 检查）；零 /engram 挂载；
#   PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False 不变（True 禁）；X1 律=
#   零 DSV41_TL_BUDGET_ELEMS；镜像/adapter/overlay 挂载面与产线同构共用（零改）。
# 用法: DRY_RUN=1 ARM_ENV_FILE=~/luz030-opt-campaign/arms/O13B1-VL-SEG65536.env ARM_TAG=C24-VLR2 \
#         bash dev/c24-compat48m/boot_mvl_600k_48m.sh      # 靴前 DRY-RUN（零集群，出口 0=自检绿）
#       ARM_ENV_FILE=~/luz030-opt-campaign/arms/O13B1-VL-SEG65536.env ARM_TAG=C24-VLR2 \
#         bash dev/c24-compat48m/boot_mvl_600k_48m.sh      # 活靴
# 出口: 0=UP+C24-48M-VL 断言组绿（DRY_RUN=1 则=DRY-RUN 段绿零集群退出）；
#       9=断言红/起败（日志已先存后删→boot-fail-logs/）
set -euo pipefail

CAMP="$HOME/luz030-opt-campaign"
D="$CAMP/logs/VL-NATIVE-20261013"
ARM_ENV_FILE="${ARM_ENV_FILE:-$CAMP/arms/VL40EXP-R2-C24T.env}"
ARM_TAG="${ARM_TAG:-VL40EXP-S5}"
DRY_RUN="${DRY_RUN:-0}"    # 1=靴前 DRY-RUN 段（8066bb4）后零集群退出；0=活靴
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
SGLANG_PKG_ROOT="${SGLANG_PKG_ROOT:-/sgl-workspace/sglang/python}"   # W1 包根探针定谳值（seg4/pkgroot-probe.txt：候选 B 族精化）
MOUNT_TGT="/models/DeepSeek-V4-Flash-Vision-Exp"       # 容器内统一路径（A9 PATH=此值）
EXPECT_CFG16="6cd841bdd6702f5e"                        # config.json sha256 前 16（W0 预登记；md5 前缀 c3afdf7706f7cfc5 并录）
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
OVERLAY_DIR="$(arm_get SGLANG_OVERLAY_DIR)"
[ "$CTN_PREFIX" = r3boot-mvl ] || die "臂 env CTN_PREFIX=$CTN_PREFIX != r3boot-mvl"
[ "$API_PORT" = 8898 ] || die "臂 env API_PORT=$API_PORT != 8898（测试口语义）"
{ [ "$SPEC" = 0 ] || [ "$SPEC" = k6 ]; } || die "臂 env SPEC=$SPEC ∉ {0,k6}（UNIFY 窗：0=C24 VL-rev2 形/k6=VL-K6 冻结卡武装）"
{ [ "$GRAPHS" = 0 ] || [ "$GRAPHS" = 1 ]; } || die "臂 env GRAPHS=$GRAPHS ∉ {0,1}（UNIFY 窗：1=decode-CG 臂）"
[ "$VERIFY" = 1 ]      || die "臂 env VERIFY=$VERIFY != 1"
[ -n "$OVERLAY_DIR" ]  || die "臂 env SGLANG_OVERLAY_DIR 缺（VL 首靴必须带 overlay）"
[ -d "$OVERLAY_DIR" ]  || die "overlay 目录缺（四机同路径纪律）：$OVERLAY_DIR"
# X1 律工程化：臂 env 零 DSV41_TL_BUDGET_ELEMS（FC3 pristine 面）
grep -q '^DSV41_TL_BUDGET_ELEMS=' <(printf '%s\n' "${ARM_KEYVALS[@]}") && die "X1 红：臂 env 携 DSV41_TL_BUDGET_ELEMS（禁键）"
info "[arm] ARM_TAG=$ARM_TAG CTN=$CTN_PREFIX PORT=$API_PORT SPEC=$SPEC GRAPHS=$GRAPHS VERIFY=$VERIFY（臂 env 生效键 $(printf '%s\n' "${ARM_KEYVALS[@]}" | wc -l) 行；overlay=$OVERLAY_DIR）"
# A4 env 键黑名单（0731 同表+VL fail-closed 键；生效行口径）
A4_PAT='DSV41_SKIP_NONFINAL_DECODER|DSV41_ENGRAM_[A-Z_]*|DSV41_FP4KV_PORT|DSV41_MOE_B12X_NEXT|DSV41_DG_SPARSE_SM121|SGLANG_ENABLE_DETERMINISTIC_INFERENCE|SGLANG_ENABLE_KERNEL_CENSUS_V2|DSV41_LAUNCHER|DSV41_PACKED_DIR|OFFLOAD_MODE|DSV41_CACHE_GIB|DSV41_CACHE_WAYS|DSV41_IO_THREADS|DSV41_RESIDENT_SCALES|DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES|DSV41_PREFILL_SP|DSV41_HC_FUSED|DSV41_INDEXER_HOIST|DSV41_IDLE_RELEASE|DSV41_WO_A_W8|DSV41_REPLICATED_SPLIT|DSV41_SPEC_SYNC_FREE|DSV41_EAGER_GLUE|DSV41_FOLDED_FENCE|DSV41_DRAFT_HEAD_FP8|DSV41_DRAFT_MAIN_PROJ_SPLIT|DSV41_VERIFY_CAP|DSV41_SHARED_PAD_K|DSV41_ROUTER_LIVE|DSV41_PREFILL_EMPTY_CACHE_TOKENS|DSV41_MOE_B12X_DETERMINISTIC'
A4_ALLOW="${A4_ALLOW:-}"
if [ -n "$A4_ALLOW" ]; then
  _kv=$(printf '%s\n' "${ARM_KEYVALS[@]}" | grep -vE "^($A4_ALLOW)=" || true)
  info "[arm] A4_ALLOW 生效：$A4_ALLOW（白名单键放行，其余黑名单维持）"
else
  _kv=$(printf '%s\n' "${ARM_KEYVALS[@]}")
fi
n_a4=$(printf '%s\n' "${_kv}" | grep -cE "^($A4_PAT)=" || true)
[ "$n_a4" = 0 ] || die "A4 红：臂 env 黑名单键命中 $n_a4 行"
info "A4 绿：臂 env 键黑名单零命中+X1 键零出现"

# ── 0b. overlay 28 件影子挂载面（VL 增量①；fail-closed；本地盘核=DRY-RUN 亦过）──
declare -A OV_MAP=(           # 平铺键→容器内 sglang 相对路径（源=REGRAFT-RECON-20261005.tsv 列1/列2）
  [dsv4_attn_metadata_kernels.py]="kernels/ops/attention/dsv4_attn_metadata_kernels.py"
  [dsv4_sparse_prefill_kernels.py]="kernels/ops/attention/dsv4/sparse_prefill_kernels.py"
  [layernorm_mhc.py]="kernels/ops/layernorm/mhc.py"
  [arg_pipeline.py]="srt/arg_groups/pipeline.py"
  [overrides.py]="srt/arg_groups/overrides.py"
  [deepseek_v4_hook.py]="srt/arg_groups/deepseek_v4_hook.py"
  [tbo_two_batch_overlap.py]="srt/batch_overlap/two_batch_overlap.py"
  [model_config.py]="srt/configs/model_config.py"
  [encoding_dsv4.py]="srt/entrypoints/openai/encoding_dsv4.py"
  [serving_chat.py]="srt/entrypoints/openai/serving_chat.py"
  [deepseek_v4_backend.py]="srt/layers/attention/deepseek_v4_backend.py"
  [dsv4_sparse_prefill_utils.py]="srt/layers/attention/dsv4/sparse_prefill_utils.py"
  [dsv4_visible_window.py]="srt/layers/attention/dsv4/visible_window.py"
  [moe_hash_topk.py]="srt/layers/moe/hash_topk.py"
  [moe_mega_moe.py]="srt/layers/moe/mega_moe.py"
  [moe_topk.py]="srt/layers/moe/topk.py"
  [schedule_batch.py]="srt/managers/schedule_batch.py"
  [schedule_policy.py]="srt/managers/schedule_policy.py"
  [scheduler.py]="srt/managers/scheduler.py"
  [dp_attn.py]="srt/managers/scheduler_components/dp_attn.py"
  [forward_batch_info.py]="srt/model_executor/forward_batch_info.py"
  [deepseek_v2.py]="srt/models/deepseek_v2.py"
  [deepseek_v4_model.py]="srt/models/deepseek_v4.py"
  [deepseek_v4_dspark.py]="srt/models/deepseek_v4_dspark.py"
  [deepseek_v4_vit.py]="srt/models/deepseek_v4_vit.py"
  [deepseek_v4_vl.py]="srt/models/deepseek_v4_vl.py"
  [mm_processor_deepseek_v4_vl.py]="srt/multimodal/processors/deepseek_v4_vl.py"
  [hf_processor.py]="srt/utils/hf_transformers/processor.py"
)
[ "${#OV_MAP[@]}" -eq 28 ] || die "overlay 映射表条目=${#OV_MAP[@]} != 28"
OV_OVERLAYS=()
ov_n=0
for flat in "${!OV_MAP[@]}"; do
  [ -f "$OVERLAY_DIR/$flat" ] || die "overlay 缺件（fail-closed）：$OVERLAY_DIR/$flat"
  OV_OVERLAYS+=(-v "$OVERLAY_DIR/$flat:$SGLANG_PKG_ROOT/sglang/${OV_MAP[$flat]}:ro")
  ov_n=$((ov_n + 1))
done
ov_str=$(printf '%s\n' "${OV_OVERLAYS[@]}" | grep -c ":$SGLANG_PKG_ROOT/sglang/" || true)
[ "$ov_n" = 28 ] || die "overlay 件计数=$ov_n != 28"
[ "$ov_str" = 28 ] || die "overlay 挂载串计数=$ov_str != 28（元素计 ${#OV_OVERLAYS[@]} 含 -v 旗标对）"
info "[overlay] 28 件本地在位 OK → 影子挂载根 $SGLANG_PKG_ROOT/sglang"

# ── 1. per-machine MODEL_DIR（01=~/models 本地；02/03/04=/data 本地——§4-3 取舍定谳：
#        02 home 侧同名目录为空壳【实测 ls 空】，真树在 /data 侧〔config sha256 已核 6cd841bdd6702f5e〕）──
declare -A MD=( [${NODE01_HOST}]="/home/liux***ya/models/DeepSeek-V4-Flash-Vision-Exp"
                [${NODE02_HOST}]="/data/models/deepseek-ai/DeepSeek-V4-Flash-Vision-Exp"
                [${NODE04_HOST}]="/data/models/dsvl-net"
                [${NODE03_HOST}]="/data/models/dsvl-net" )
WORKERS=( "1|${NODE02_HOST}|${NODE02_IP}|0=rocep1s0f1,roceP2p1s0f1;2=rocep1s0f0,roceP2p1s0f0"
          "2|${NODE04_HOST}|${NODE04_IP}|1=rocep1s0f0,roceP2p1s0f0;3=rocep1s0f1,roceP2p1s0f1"
          "3|${NODE03_HOST}|${NODE03_IP}|0=rocep1s0f0,roceP2p1s0f0;2=rocep1s0f1,roceP2p1s0f1" )
PEER_HCA_HEAD="1=rocep1s0f1,roceP2p1s0f1;3=rocep1s0f0,roceP2p1s0f0"
HEAD_CTN="${CTN_PREFIX}-head"; WORKER_CTN="${CTN_PREFIX}-worker"

# ── 2/3. 前置守卫+权重面/overlay 远端核验（活靴面；DRY_RUN=1 整段跳过=零集群纪律）─
if [[ "$DRY_RUN" = 1 ]]; then
  info "[dry-run] 段2/3（前置守卫+A9/overlay 远端核验）跳过——DRY-RUN 模式零 ssh/零 docker/零 curl（8066bb4 靴前 DRY-RUN 强制段；overlay 28 件本地核已过）"
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

  info "== 权重面+overlay 远端核验+A9 指纹 =="
  FP_LOG="$D/boot-checks/a9-fingerprint.txt"; : > "$FP_LOG"; a9fail=0
  ov_digest(){ local tgt="$1" d names
    names=$(printf '%s\n' "${!OV_MAP[@]}" | sort)
    if [[ "$tgt" == "-" ]]; then d=$(cd "$OVERLAY_DIR" && md5sum $names | md5sum | cut -d' ' -f1)
    else d=$(printf '%s\n' "$names" | ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$tgt" "cd '$OVERLAY_DIR' && xargs md5sum | md5sum | cut -d' ' -f1" 2>/dev/null) || d=""; fi
    echo "${d:-REMOTE_FAIL}"; }
  OV_DIG_HEAD=$(ov_digest "-")
  fp_one(){ local h="$1" p="$2" out cfg16 cfgmd5 bytes nshard mnt ovd
    if [ "$h" = "${NODE01_HOST}" ]; then out=$(sha256sum "$p/config.json" | awk '{print $1}'; md5sum "$p/config.json" | awk '{print $1}'; du -sb "$p" | awk '{print $1}'; ls "$p"/model-*-of-00048.safetensors 2>/dev/null | wc -l; findmnt -no FSTYPE,SOURCE "$p" 2>/dev/null || echo "local")
    else out=$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$h" "sha256sum '$p'/config.json | awk '{print \$1}'; md5sum '$p'/config.json | awk '{print \$1}'; du -sb '$p' | awk '{print \$1}'; ls '$p'/model-*-of-00048.safetensors 2>/dev/null | wc -l; findmnt -no FSTYPE,SOURCE '$p' 2>/dev/null || echo local" 2>/dev/null); fi
    cfg16=$(sed -n 1p <<<"$out" | cut -c1-16); cfgmd5=$(sed -n 2p <<<"$out" | cut -c1-16); bytes=$(sed -n 3p <<<"$out"); nshard=$(sed -n 4p <<<"$out" | tr -d '[:space:]'); mnt=$(sed -n 5p <<<"$out")
    ovd=$(ov_digest "$h")
    local ok="OK"
    [ "$cfg16" = "$EXPECT_CFG16" ] || { ok="RED(cfg=$cfg16)"; a9fail=1; }
    [ "$cfgmd5" = "c3afdf7706f7cfc5" ] || { ok="$ok RED(md5=$cfgmd5)"; a9fail=1; }
    [ "$nshard" = "$EXPECT_NSHARD" ] || { ok="$ok RED(nshard=$nshard)"; a9fail=1; }
    { [ "$ovd" = "$OV_DIG_HEAD" ] && [ "$ovd" != "REMOTE_FAIL" ]; } || { ok="$ok RED(overlay=$ovd)"; a9fail=1; }
    printf 'MODEL=deepseek-v4-flash-vision-exp CFG=%s(md5:%s) PATH=%s BYTES=%s host=%s mount=%s overlay_dig=%s %s\n' "$cfg16" "$cfgmd5" "$MOUNT_TGT" "$bytes" "$h" "$mnt" "${ovd:0:12}" "$ok" | tee -a "$FP_LOG"; }
  fp_one "${NODE01_HOST}" "${MD[${NODE01_HOST}]}"
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"; fp_one "$_h" "${MD[$_h]}"; done
  [ "$a9fail" = 0 ] || { cat "$FP_LOG"; die "A9/权重/overlay 面红（四机身份或 overlay 漂移）"; }
  info "A9 绿：四机 CFG=$EXPECT_CFG16 逐机相等=注册值；overlay 28 件四机同摘要；BYTES 记录不判红（元数据级）"
fi

# ── 4. 公共面（M0731 剥离律 21 项+VL 增量：overlay 28 件挂载）─────────────────
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
  "${OV_OVERLAYS[@]}"
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
  -e DSV41_SOURCE="$MOUNT_TGT"
  -e NNODES=4
  -e DSV41_STATS_SECONDS=60
  -e MALLOC_ARENA_MAX=2
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:False
  -e TP_SIZE=4
)
# 臂 env 注入（r3-boot-arm.sh 同律：逐行 docker -e；A4 已核零命中）
for line in "${ARM_KEYVALS[@]}"; do COMMON_ENV+=(-e "$line"); info "[arm] +env ${line%%=*}"; done

SERVER_ARGS=(
  --model-path "$MOUNT_TGT"
  --served-model-name deepseek-v4-flash-vision-exp
  --tp-size 4 --ep-size 1 --nnodes 4
  --dist-init-addr "${HEAD_IP}:${DIST_PORT}"
  --mem-fraction-static 0.90
  --chunked-prefill-size 4096
  --context-length 600000
  --max-total-tokens 4800000
  --max-running-requests 12
  --dist-timeout 900
  --enable-metrics
  --watchdog-timeout 1800
  --moe-runner-backend flashinfer_mxfp4
  --fp8-gemm-backend flashinfer_cutlass
)
# UNIFY 窗：GRAPHS 双态（0=--disable-cuda-graph 在；1=摘旗标=CG-on，首靴不设 --cuda-graph-max-bs）
[[ "$GRAPHS" == 1 ]] || SERVER_ARGS+=(--disable-cuda-graph)
# UNIFY 窗：SPEC 双态映射（0=零 spec 参数〔C24 VL-rev2〕；k6=DSPARK+num_speculative_tokens=6〔VL-K6 冻结卡 A6 反转，γ=5 检查点自洽零触碰〕）
if [ "$SPEC" = k6 ]; then
  SERVER_ARGS+=(--speculative-algorithm DSPARK --speculative-num-draft-tokens 6)
fi
# UNIFY 窗增量：ARM_SERVE_EXTRA serve 参位（SPS 表路径/compact+align 三件套等分臂单键）
ARM_SERVE_EXTRA="${ARM_SERVE_EXTRA:-}"
if [ -n "$ARM_SERVE_EXTRA" ]; then read -r -a _ASE <<< "$ARM_SERVE_EXTRA"; SERVER_ARGS+=("${_ASE[@]}"); info "[arm] +serve-extra ${_ASE[*]}"; fi

# ── A1/A2/A3/A5/A6/A7/A8 参数层断言（fail-closed 前移；C24-48M-VL 同步改）──
ARGS_STR="$(printf '%s ' "${SERVER_ARGS[@]}")"
grep -qE -- '--enable-(decoder|encoder)-swa-bounded-replay' <<<"$ARGS_STR" && die "A1 红：bounded-replay 旗标在 SERVER_ARGS"
grep -qE -- '--(reasoning|tool-call)-parser' <<<"$ARGS_STR" && die "A2 红：parser 显式指定（deepseek-v41 系=A2 黑名单）"
grep -qE -- '--json-model-override-args' <<<"$ARGS_STR" && die "A3 红：json 注入键在 SERVER_ARGS（candidate/engram 族不适用）"
grep -qE -- '--cuda-graph-backend|--enable-prefill-cuda-graph|--enable-decode-cuda-graph' <<<"$ARGS_STR" && die "A5 红：显式图 backend 指定"
grep -qE -- '--max-total-tokens 4800000' <<<"$ARGS_STR" || die "C24-48M-VL 红：池 pin≠4800000（C24 形显式钉，C24-WINCARD §一；VL 自推 8,847,616=VLW3 楔死前科禁续）"
grep -qE -- '--context-length 600000' <<<"$ARGS_STR" || die "C24-48M-VL 红：context-length≠600000"
grep -qE -- '--max-running-requests 12' <<<"$ARGS_STR" || die "C24-48M-VL 红：mrr≠12（C12 形沿用）"
grep -qE -- '--chunked-prefill-size 4096' <<<"$ARGS_STR" || die "C24-T 红：chunked-prefill≠4096（mm prefill 分块打分/瞬态控制面钉，C24-DOCTRINE §二=OPEN-23 缓解面）"
if [ "$GRAPHS" = 1 ]; then
  grep -qE -- '--disable-cuda-graph' <<<"$ARGS_STR" && die "A5 红：GRAPHS=1 而 --disable-cuda-graph 在 ARGS"
  grep -qE -- '--cuda-graph-max-bs' <<<"$ARGS_STR" && die "A5 红：首靴不设 --cuda-graph-max-bs（stock 自推）"
else
  grep -qE -- '--disable-cuda-graph' <<<"$ARGS_STR" || die "A5 红：GRAPHS=0 未落实"
fi
if [ "$SPEC" = 0 ]; then
  n_spec=$(grep -cE -- '--speculative-algorithm' <<<"$ARGS_STR" || true); [ "$n_spec" = 0 ] || die "A6 红：SPEC=0 而 spec 参数数=$n_spec"
else
  n_spec=$(grep -cE -- '--speculative-algorithm' <<<"$ARGS_STR" || true); [ "$n_spec" = 1 ] || die "A6 红：SPEC=k6 而 spec 参数数=$n_spec≠1"
  grep -qE -- '--speculative-algorithm DSPARK' <<<"$ARGS_STR" || die "A6 红：非 DSPARK"
  grep -qE -- '--speculative-num-draft-tokens 6' <<<"$ARGS_STR" || die "A6 红：k≠6（VL-K6 冻结卡：k=6 显式钉=--speculative-num-draft-tokens 6；CLI 键名以引擎 server_args 为准）"
  n_g=$(grep -cE -- '--(dspark-block-size|draft-sample-method|num-draft-tokens)' <<<"$ARGS_STR" || true); [ "$n_g" = 0 ] || die "A6 红：γ/k3 面键被显式设置（O11-γ 冻结）"
fi
grep -q '/engram' <<<"$(printf '%s\n' "${DOCKER_HW[@]}")" && die "A8 红：/engram 挂载存在"
n_ov=$(printf '%s\n' "${DOCKER_HW[@]}" | grep -c ":$SGLANG_PKG_ROOT/sglang/" || true); [ "$n_ov" = 28 ] || die "A8 红：DOCKER_HW overlay 挂载行=$n_ov != 28"
grep -q 'expandable_segments:True' <<<"$(printf '%s\n' "${COMMON_ENV[@]}")" && die "红：expandable_segments:True（GB10 NaN 双禁）"
info "A1/A2/A3/A5/A6/A7/A8 参数层断言全绿（黑名单零命中+ctx 600000+池 4.8M+mrr12+chunk4096 钉+图全关+零 spec+零 engram+overlay 28+allocator 禁项零）"
# C24-48M-VL 水位断言（fail-closed 参数位；4.8M 重推导值——推导表见段4b；首靴实测谷−1G 重钉）
# VL-NATIVE S5：水位地板缺省=20480（STDVL-R2 认证形重推导值；头注变体②）
WATER_MARK_FLOOR_MB="${WATER_MARK_FLOOR_MB:-20480}"    # R1 认证靴实测谷 21461−1G→1024 倍数下取整
POOL_FINGERPRINT_EXPECT="${POOL_FINGERPRINT_EXPECT:-4800000}"

# ── 4b. 靴前 DRY-RUN 段（强制；8066bb4 模板修正=C24 落地；段内零 ssh/零 docker/零 curl）──
#   ①C24-4.8M 容量账+水位地板推导表打印（判读入册输入=WINCARD §一/§二同源）
#   ②断言判别力自检=反向用例（新断言纪律：喂坏输入必红——对 7.2M 旧值/旧缺省无判别力=自检红）
#   ③DRY_RUN=1 ⇒ 此处零集群退出（出口 0）；DRY_RUN=0 ⇒ 活靴继续（本段输出已入日志=靴前必经）
info "== C24-4.8M 推导表（VL 线；bytes_per_full_token=7,086.75B 实测 O13B/C12 同源）=="
info "  KV 池账（每机）：7.2M 形=7,200,000×7,086.75B=51.02G → 4.8M 形=4,800,000×7,086.75B=34.02G（释放 17.01G/机）"
info "  静态自洽：池 34.02G+权重 42.0G（A9 BYTES÷TP4）=76.0G < 108.9G=0.90×121（mem-fraction 帽内，余 32.9G workspace）"
info "  水位地板=${WATER_MARK_FLOOR_MB}M（STDVL-R2 认证形重推导=R1 认证靴实测谷 21461−1G→1024 倍数下取整）"
info "  容量设计点：4.8M=600k×8（8 并发满驻恰等）；mrr=12 ⇒ 600k×12=7.2M 超池由 admission/排队吸收（DOCTRINE §三）"
info "  mm 瞬态控制面（OPEN-23 家族）：chunk4096 断言钉+水位地板 ${WATER_MARK_FLOOR_MB}+UMA 靴窗中止门 4G+VL 窗 mm 足迹哨（F7 J6：>8G 拒新 mm 即停窗）"
# ② 断言判别力自检（反向用例：坏输入=7.2M 旧池/131072 旧 ctx/mrr16 旧值/chunk 16384）
ST_BAD='--model-path x --served-model-name y --max-total-tokens 7200000 --context-length 131072 --max-running-requests 16 --chunked-prefill-size 16384 --disable-cuda-graph'
grep -qE -- '--max-total-tokens 4800000'   <<<"$ST_BAD" && die "自检红：池断言对 7.2M 旧值无判别力"
grep -qE -- '--context-length 600000'      <<<"$ST_BAD" && die "自检红：ctx 断言对 131072 旧值无判别力"
grep -qE -- '--max-running-requests 12'    <<<"$ST_BAD" && die "自检红：mrr 断言对 16 旧值无判别力"
grep -qE -- '--chunked-prefill-size 4096'  <<<"$ST_BAD" && die "自检红：chunk 钉对 16384 无判别力"
# 池指纹带自检（UNIFY 窗：仅缺省 4800000 时做硬编码组；重推导形〔POOL_FINGERPRINT_EXPECT≠4800000〕跳过——新带已由重推导法立带）
lo_t=$((POOL_FINGERPRINT_EXPECT*98/100)); hi_t=$((POOL_FINGERPRINT_EXPECT*102/100))
if [ "$POOL_FINGERPRINT_EXPECT" = 4800000 ]; then
  [ "$lo_t" = 4704000 ] && [ "$hi_t" = 4896000 ] || die "自检红：池指纹带算术错 lo=$lo_t hi=$hi_t（期 [4704000,4896000]）"
fi
{ [ 7200000 -ge "$lo_t" ] && [ 7200000 -le "$hi_t" ]; } && die "自检红：池指纹带 [${lo_t},${hi_t}] 含 7.2M 旧值（带宽过宽）"
{ [ 8847616 -ge "$lo_t" ] && [ 8847616 -le "$hi_t" ]; } && die "自检红：池指纹带含 VL 自推 8,847,616（楔死前科值漏防）"
# 黑名单断言自检（A1 旗标坏输入必命中）
grep -qE -- '--enable-(decoder|encoder)-swa-bounded-replay' <<<"$ST_BAD --enable-decoder-swa-bounded-replay" || die "自检红：A1 黑名单正则不咬坏旗标"
info "断言判别力自检绿（反向用例 7 组全咬：池/ctx/mrr/chunk/指纹带×2（7.2M+自推 8.85M）/A1 黑名单）"
if [[ "$DRY_RUN" = 1 ]]; then
  info "DRY-RUN 完成（臂 env+A4/X1+overlay 28+参数层断言+推导表+自检全绿）——零集群退出（未触 ssh/docker/curl；8066bb4 前向修正）"
  exit 0
fi
info "DRY-RUN 段过（活靴继续；本段输出已入日志）"

# ── 5. 失败路径免疫（先存后删→boot-fail-logs/）──────────────────────────────
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

# ── 6. 起 workers（per-machine MODEL_DIR+overlay 28 件同挂）──────────────────
info "== 起 workers =="
for w in "${WORKERS[@]}"; do
  IFS='|' read -r rank host ip phca <<<"$w"
  src="${MD[$host]}"
  ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "docker rm -f $WORKER_CTN >/dev/null 2>&1 || true"
  REMOTE_CMD=(docker run -d --name "$WORKER_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}"
              -e "NCCL_IB_PEER_HCA=$phca"
              -v "$src:$MOUNT_TGT:ro"
              "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" --node-rank "$rank")
  REMOTE_STR="$(printf '%q ' "${REMOTE_CMD[@]}")"
  ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "$REMOTE_STR" || die "worker rank $rank docker run 失败"
  sleep 8
  state="$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "docker inspect -f '{{.State.Running}}' $WORKER_CTN 2>/dev/null" | tr -d '\r')"
  if [[ "$state" != "true" ]]; then
    warn "worker rank $rank ($host) 起后即死："; ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$host" "docker logs --tail 30 $WORKER_CTN" 2>&1 || true
    die "worker rank $rank 起败"; fi
  info "  rank $rank @ $host 存活（MODEL_DIR host=$src→容器 $MOUNT_TGT；overlay 28 件同挂；零 engram 面）"
done

# ── 7. 起 head ──
info "== 起 head (rank 0, API :$API_PORT) =="
docker rm -f "$HEAD_CTN" >/dev/null 2>&1 || true
docker run -d --name "$HEAD_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}" \
  -e "NCCL_IB_PEER_HCA=$PEER_HCA_HEAD" \
  -v "${MD[${NODE01_HOST}]}:$MOUNT_TGT:ro" \
  "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" \
  --node-rank 0 --host 0.0.0.0 --port "$API_PORT"
sleep 8
[[ "$(docker inspect -f '{{.State.Running}}' "$HEAD_CTN" 2>/dev/null)" == "true" ]] || { docker logs --tail 30 "$HEAD_CTN" 2>&1 || true; die "head 起败"; }
info "head 存活"

# ── 8. 健康轮询（≤45 分钟；靴窗 UMA 水位中止门 4G）───────────────────────────
dump_all(){ echo "---- head 尾 40 ----"; docker logs --tail 40 "$HEAD_CTN" 2>&1 || true
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ph <<<"$w"
    echo "---- $_h 尾 30 ----"; ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "docker logs --tail 30 $WORKER_CTN" 2>&1 || true; done; }
info "轮询 health（≤45 分钟；VL 157G/四机本地读；mm 批默认拒入=OPEN-23 家族止损沿 T17 C3）"
deadline=$(( $(date +%s) + 2700 ))
while (( $(date +%s) < deadline )); do
  if curl -fsS --max-time 3 "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    info "== VL 栈 UP：http://$HEAD_IP:$API_PORT（overlay 影子挂载+GRAPHS=$GRAPHS+SPEC=$SPEC+C24-4.8M-VL 形，CTN=$CTN_PREFIX）=="
    docker logs "$HEAD_CTN" 2>&1 | grep -E 'max_total_num_tokens=|available_gpu_mem=|Load weight end' | tail -3 || true
    # C24-48M-VL 池指纹断言（4.8M±2% token 对齐余差容差，O10B ①/O13/O13B 同律）
    pool=$(docker logs "$HEAD_CTN" 2>&1 | grep -oE 'max_total_num_tokens=[0-9]+' | tail -1 | cut -d= -f2)
    [ -n "$pool" ] || die "C24-48M-VL 红：池指纹不可读"
    lo=$((POOL_FINGERPRINT_EXPECT*98/100)); hi=$((POOL_FINGERPRINT_EXPECT*102/100))
    [ "$pool" -ge "$lo" ] && [ "$pool" -le "$hi" ] || die "C24-48M-VL 红：池指纹 $pool ∉ [$lo,$hi]"
    # C24-48M-VL 水位断言（四机 MemAvailable ≥ WATER_MARK_FLOOR_MB；首靴读数入册=地板重钉输入）
    m=$(memavail); [ "$m" -ge "$WATER_MARK_FLOOR_MB" ] || die "C24-48M-VL 红：head MemAvailable=${m}M < ${WATER_MARK_FLOOR_MB}M"
    for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ph <<< "$w"
      mw=$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$_h" "awk '/MemAvailable/{printf \"%d\", \$2/1024}' /proc/meminfo" 2>/dev/null)
      [ "${mw:-0}" -ge "$WATER_MARK_FLOOR_MB" ] || die "C24-48M-VL 红：$_h MemAvailable=${mw}M < ${WATER_MARK_FLOOR_MB}M"; info "  $_h MemAvailable=${mw}M"; done
    # VL-NATIVE S5 增量：mm 直证断言（overlay 形判读线；勘正 4：concurrency 行=head
    #   侧 tokenizer-manager 专属行〔实测 fail-log 19:55:54 head=1/workers=0；VLR2 先例
    #   同形〕⇒ 判读分面=KV 0.10G+processors 逐机≥1+concurrency 仅 head≥1；
    #   triton_attn 两行=overlay 形 0 命中〔mm 注意力走 dsv4 后端〕故不设该断言）
    info "== mm 直证（overlay 形；四机逐机+concurrency 头位分面）=="
    MM_LOG="$D/boot-checks/mm-direct-${ARM_TAG}.txt"; : > "$MM_LOG"; mmfail=0
    mm_log(){ local tgt="$1" ctn="$2" log
      if [[ "$tgt" == "-" ]]; then log="$(docker logs "$ctn" 2>&1 | tr '\r' '\n')"; else log="$(ssh -o ConnectTimeout=8 "${SSH_OPTS[@]}" "$tgt" "docker logs $ctn 2>&1" 2>/dev/null | tr '\r' '\n')"; fi
      local kv pr cc
      kv=$(grep -cF 'Reserving 0.10 GB of the KV budget for post-sizing multimodal allocations' <<<"$log" || true)
      pr=$(grep -cF 'multimodal.processors' <<<"$log" || true)
      cc=$(grep -cF 'Multimodal processor concurrency enabled' <<<"$log" || true)
      echo "$tgt mm_kv010=$kv mm_processors=$pr mm_concurrency=$cc"; }
    mm_log "-" "$HEAD_CTN" | tee -a "$MM_LOG"
    for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ph <<<"$w"; mm_log "$_h" "$WORKER_CTN" | tee -a "$MM_LOG"; done
    while read -r ln; do
      case "$ln" in
        *mm_kv010=*)
          _kv=$(grep -oE 'mm_kv010=[0-9]+' <<<"$ln" | cut -d= -f2)
          _pr=$(grep -oE 'mm_processors=[0-9]+' <<<"$ln" | cut -d= -f2)
          _cc=$(grep -oE 'mm_concurrency=[0-9]+' <<<"$ln" | cut -d= -f2)
          { [ "${_kv:-0}" -ge 1 ] && [ "${_pr:-0}" -ge 1 ] && { [ "${_cc:-0}" -ge 1 ] || [ "$(awk '{print $1}' <<<"$ln")" != "-" ]; }; } || { warn "mm 直证缺面：$ln"; mmfail=1; }
          ;;
      esac
    done < "$MM_LOG"
    [ "$mmfail" = 0 ] || { cat "$MM_LOG"; die "VL40EXP mm 直证红（KV 0.10G+processors 逐机+concurrency 头位 有缺面）"; }
    info "mm 直证绿（overlay 形：四机逐机 KV 0.10G+processors 扫描+head processor-concurrency 全在档）"
    info "C24-48M-VL 断言组绿（池指纹 $pool∈[$lo,$hi] + ctx 600000 + mrr 12 + 四机水位≥${WATER_MARK_FLOOR_MB}M + mm 直证四机全）"
    exit 0
  fi
  st="$(docker inspect -f '{{.State.Status}}' "$HEAD_CTN" 2>/dev/null)"
  [[ "$st" != "running" ]] && { warn "head 退出"; dump_all; die "VL C24-4.8M 首靴失败"; }
  m=$(memavail)
  if (( m < 4000 )); then warn "head 靴窗 MemAvailable=${m}M < 4000M — UMA 超卖中止"; dump_all; die "UMA 水位红线（靴窗）"; fi
  sleep 10
done
warn "超时"; dump_all; die "VL C24-4.8M 健康超时"
