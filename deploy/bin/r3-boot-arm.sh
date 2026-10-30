#!/usr/bin/env bash
# ── 交付仓快照注记（2026-10-20 参面全同步；非活件）────────────────────────────
# 本件=产线现役形快照镜像（GH-PUSH 遗留-2 兑现）：源形 md5=20f22bc63c63b47ea4a1a0edbafec3b7
# （四机 ~/migrate-assets/bin/ 同体；作者内部 cfgmgmt 包锚=FINGERPRINT 5ebac6ca〔第十五滚〕
#  boot-chain.md5 r3-boot-arm 行同钉——**注意：本仓 tools/packages/cfgmgmt/ 内的 boot-chain.md5
#  是 0.3.1 时点快照（c051bb41），与源形不同钉属已知代际差，勿据彼表判本件漂移**；
#  0.3.2 终态五件套成员，IMAGE 指针=0.3.2-r032c）。
# 2026-10-30 公开面修复（外部站点 bug 报告）：ARM_ENV_FILE 注入循环加尾行守护
#  （env 文件末尾缺换行时旧版静默丢末行）——修复后 md5 以 md5sum 实测为准，
#  变更记录见 CHANGELOG.md 2026-10-30 条。参面=NCCL 部署双 rail 对
# 2026-10-30 EQ-02 修复（0.3.4re 缺陷修复单元；035-W0-TASKBOOK §EQ-02）：ARM_ENV_FILE
#  注入前新增 RoCE 通信聚合双键条件式 fail-closed 断言（SGLANG_ROCE_MAX_SIZE/
#  DSV41_ROCE_GATHER：env 声明两键时在役值必须双双=1179648，回滚值/单边缺键=拒起；
#  未声明〔新代际形〕不断言放行）——把「不许回滚这两键」台账铁律变成机器可执行硬门；
#  md5 以 md5sum 实测为准，变更记录见 CHANGELOG.md 2026-10-30 条。
# 2026-10-30 UP43050 上游缺陷 host 侧规避窗（公开面单元；上游 sglang #43050）：
#  SERVER_ARGS 去 --sleep-on-idle 单参（原第九参；空闲 10-20 分钟后唤醒即死 prefill，
#  _low_ratio_index_topk_dense 唤醒重捕获路径缺 host 同步点——报告者实测同硬件去参即正常；
#  SPEC6 谱 9→8 参、归一指纹回 6b12a445；史注原样保留，参行注释化）。禁参固化面=
#  r3-gate-env-lint.sh EQ-03 禁参组合+tools/serve_flags_gate.sh 缺席判据+
#  deploy/prod/selfcheck-prod.sh 禁参表。md5 以 md5sum 实测为准，变更记录见
#  CHANGELOG.md 2026-10-30 条。
# rocep1s0f0,roceP2p1s0f1+NCCL_IB_TC=106（TOS/PEER_HCA 退役）+环网补丁链全链退役（RETIRED 注记）+
# SERVER_ARGS 八参（A8 --tool-call-parser deepseekv41/A9 --enable-cache-report；原第九参
# --sleep-on-idle 已于 2026-10-30 退役=上游 #43050 idle-wake hang host 侧规避，见 SERVER_ARGS
# 段 RETIRED-UP43050-20261030 注记）
# +D15 五门断言段在役。与源形唯一差异=用户名路径掩码（/home/liux***ya/，三处；源形为实值）。
# 快照律：本仓件不随产线滚动自动更新——后续产线滚动须另开同步窗重钉本注记指纹。
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
IMAGE="${IMAGE:?缺环境变量 IMAGE（<registry-host>:5000/dsv41-sglang-optimized:0.3.2-r032c），拒跑}"
HEAD_IP="${HEAD_IP:?缺环境变量 HEAD_IP（head 节点 <mgmt-node-ip>），拒跑}"
NODE01_HOST="${NODE01_HOST:?缺环境变量 NODE01_HOST（<node01>），拒跑}"
NODE02_HOST="${NODE02_HOST:?缺环境变量 NODE02_HOST（<node02>），拒跑}"
NODE03_HOST="${NODE03_HOST:?缺环境变量 NODE03_HOST（<node03>），拒跑}"
NODE04_HOST="${NODE04_HOST:?缺环境变量 NODE04_HOST（<node04>），拒跑}"
NODE02_IP="${NODE02_IP:?缺环境变量 NODE02_IP（<mgmt-node-ip>），拒跑}"
NODE03_IP="${NODE03_IP:?缺环境变量 NODE03_IP（<mgmt-node-ip>），拒跑}"
NODE04_IP="${NODE04_IP:?缺环境变量 NODE04_IP（<mgmt-node-ip>），拒跑}"
# net-rebuild-20261015: 管理段重编址→管理段四址（IMAGE registry 源/HEAD_IP/WORKERS 三处通道址改新；
# 语义参数零动；registry 同一容器换址，:5000 实测 200。golden MANIFEST.image 同批重锚。）
# net-rebuild-wc-20261015（W-C sglang 起机窗，法源=NCCL 结果档 §S4.2/§S4.3+ADDENDUM §十）：
#   ① NCCL_IB_HCA 4 口裸列→部署双 rail 对 rocep1s0f0,roceP2p1s0f1；新增 NCCL_IB_TC=106；NCCL_IB_TOS=46 退役；
#   ② NCCL_IB_PEER_HCA per-rank 注入退役（键在在役二进制零命中=惰性+用户令弃用变通）；
#   ③ SERVER_ARGS 增 A8/A9 两参（--tool-call-parser deepseekv41 连写+--enable-cache-report）。
#   回退=旧件 .bak-pre-wc 回拷（一键回退指令见 W-C 结果档 §回退）。
# net-rebuild-wc-20261015 复靴段（R1 环网补丁链退役；呈裁①即席授权；单变量=仅此一项）：
#   ① 首靴红根因=环网 fork（ncclpin+ringonly；内含「RING-ONLY rank×设备重映射」需 4 设备空间）
#      与部署双 rail 2 口对硬冲突（WCBOOT44 四秩 vNic 越界实证）⇒ 本滚全链退役：
#      3 条 mount+LD_PRELOAD 行+资产门两处（行内 RETIRED 注记史留）；
#      补丁件本体（~/migrate-assets/ncclpin.so、nccl-ringonly/）零删除封存原位；
#   ② stock pip NCCL 2.30.7 接管（W-B 12 臂同 2 口形全绿载体）；suggested-3 #4/#5
#      （NCCL_ALGO=RING/NCHANNELS）按授权不落（保持）；
#   ③ 回退=旧件 r3-boot-arm.sh.bak-pre-reboot（06b25aac）回拷。
DIST_PORT="20000"
API_PORT="${API_PORT:-8898}"   # doc102：测试窗固定 8898（避开 concurrency-proxy→8899）   # L10 用 8898：避开 concurrency-proxy→8899 的活生产转发路径（㉑/㉕ 防污染）
SPEC="${SPEC:-0}"
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8)
ADAPTER_DIR="$HOME/migrate-assets/dsv41/adapter"          # 持久位（教训㊲）
B12X_DIR="$HOME/migrate-assets/b12x"                       # b12x_next 计算树（fork 验证路径，U2 暂存件）
# RETIRED-net-rebuild-20261015（复靴段 R1 环网补丁链退役；以下三变量无消费方，留档）：
# NCCL_DIR="$HOME/migrate-assets/nccl-ringonly"
# NCCLPIN="$HOME/migrate-assets/ncclpin.so"
# PIP_NCCL=/opt/sglang/lib/python3.12/site-packages/nvidia/nccl/lib/libnccl.so.2
ENG_HOST_HEAD="$HOME/dsv41-engram-1017"                   # rank0 打包分片（MODEL-SWITCH-1017）
ENG_HOST_WORKER="\$HOME/dsv41-engram-1017"  # rank1/2/3 打包分片（MODEL-SWITCH-1017；旧 ~/dsv41-engram 保留回退）

# rank|host|ip|宿主权重路径|engram 宿主路径（绝对路径，四机同用户）|该秩 PEER_HCA（**末列已退役史档**：
# net-rebuild-wc-20261015 起不再注入 NCCL_IB_PEER_HCA——键在在役 ringonly 2.30.7/ncclpin.so 零命中=惰性，
# 且用户令弃用 per-rank HCA 变通，走正常网面修复；列保留作环网期史档）
# 权重面（2026-09-29 事故后定稿）：rank2/3 走 /data/models/dsv41-net = NFS 全量树
# （03←<fabric-ip>=01 主源；04←<fabric-ip>=02 备源，均 ro nfs4 nconnect=4，已入 fstab）。
# net-rebuild-20261015: 上行 NFS 源址为旧编址记载，fstab 四机实况未证（L4 §三.5.h 待查项）——本窗仅注记不改语义。
# stock main 的 filter_duplicate_safetensors_files 在装载前做全 48 分片在位校验——
# 03/04 曾本地置 47/48 尾分片（逐文件直读设计态，2026-10-10 ENV-UNIFY 清理=设计未采用 R-批4）：
# 尾分片已删，47/48 与其余分片同走 NFS 全量树；索引校验全树可见 ⇒ NFS 硬前置不变。
WORKERS=(
  "1|${NODE02_HOST}|${NODE02_IP}|/data/models/DeepSeek-V4.1-Flash-1017|/home/liux***ya/dsv41-engram-1017|0=rocep1s0f1,roceP2p1s0f1;2=rocep1s0f0,roceP2p1s0f0"
  "2|${NODE04_HOST}|${NODE04_IP}|/data/models/dsv41-net|/home/liux***ya/dsv41-engram-1017|1=rocep1s0f0,roceP2p1s0f0;3=rocep1s0f1,roceP2p1s0f1"
  "3|${NODE03_HOST}|${NODE03_IP}|/data/models/dsv41-net|/home/liux***ya/dsv41-engram-1017|0=rocep1s0f0,roceP2p1s0f0;2=rocep1s0f1,roceP2p1s0f1"
)
PEER_HCA_HEAD="1=rocep1s0f1,roceP2p1s0f1;3=rocep1s0f0,roceP2p1s0f0"  # net-rebuild-wc-20261015：本变量退役（不再注入；保留史档）
HEAD_MODEL_SRC="/data/models/DeepSeek-V4.1-Flash-1017"
# CTN_PREFIX 可被环境覆盖（PROD-RS-20261003 名隔离：生产用 r3prod-*，
# 避开 r3-watchdog 对精确名 r3boot-head/r3boot-worker 的管辖；缺省 r3boot
# =测试线行为逐字不变）。
CTN_PREFIX="${CTN_PREFIX:-r3boot}"
HEAD_CTN="${CTN_PREFIX}-head"
WORKER_CTN="${CTN_PREFIX}-worker"
MOUNT_TGT="/models/DeepSeek-V4.1-Flash"

# ── FlashInfer autotune golden 表（AUTOTUNE-GOLDEN-20260930；缺省全惰性）────
# fin2 0.2.8 遗留病在新基座的形态：autotune 表只活在容器层（/root/.cache/sglang/
# flashinfer/autotune/ 无宿主挂载 ⇒ docker rm 即失），每靴全量重调优 ⇒ 靴间
# tactic 彩票（A1-D3 c8-16 +3% / U31 wall +2.1% 反复判 boot 噪声的候选方差源）。
# stock main 已自带表机制（sglang/srt/model_executor/runner/flashinfer_autotune.py:
# 137-175 路径=$SGLANG_CACHE_DIR/flashinfer/autotune/<fi_ver>/<arch>/<key16>/
# rank_tp<r>_pp<p>_dp<d>.json；SGLANG_FLASHINFER_AUTOTUNE_CACHE 缺省 True=
# environ.py:1095；上下文退出无条件 save_configs=flashinfer_autotune.py:297-298），
# 缺的只是宿主持久位+四秩自审。本段不改引擎行为，只补资产面：
#   捕获 AUTOTUNE_CAPTURE=1：空 work 挂载让引擎产新表，靴后四机采收冻结 MANIFEST；
#   生产 AUTOTUNE_GOLDEN=1 ：golden→work 种子 + 四秩（含 rank0）在位/加载自审。
# 两门都关时零行为差（无新挂载/无新 env/无新检查）。门变量是启动器 env，
# 不走 ARM_ENV_FILE（那只进容器 env，启动器侧不生效）。
AUTOTUNE_GOLDEN="${AUTOTUNE_GOLDEN:-0}"
AUTOTUNE_CAPTURE="${AUTOTUNE_CAPTURE:-0}"
AT_GOLDEN_DIR="${AUTOTUNE_GOLDEN_DIR:-$HOME/migrate-assets/flashinfer-golden}"
AT_TABLE="$AT_GOLDEN_DIR/table"        # 金文库（冻结；四机同步，同 adapter 纪律）
AT_MANIFEST="$AT_GOLDEN_DIR/MANIFEST.json"
AT_MD5="$AT_GOLDEN_DIR/table.md5"      # md5sum -c 格式，覆盖 table/**
AT_WORK="$AT_GOLDEN_DIR/work"          # 每靴 rw 副本（挂进容器；golden 本体永不挂载）
AT_REL=""                              # <fi_ver>/<arch>/<key16>（从 MANIFEST 读）
if [[ "$AUTOTUNE_GOLDEN" == "1" && "$AUTOTUNE_CAPTURE" == "1" ]]; then
  die "AUTOTUNE_GOLDEN 与 AUTOTUNE_CAPTURE 互斥（先捕获靴产表，再生产靴用表）"
fi
AT_ON=0; [[ "$AUTOTUNE_GOLDEN" == "1" || "$AUTOTUNE_CAPTURE" == "1" ]] && AT_ON=1
at_remote() {  # at_remote <ssh目标|-> <cmd>——cmd 内 $AT_* 由本侧展开（四机同用户同路径）
  if [[ "$1" == "-" ]]; then bash -c "$2"; else ssh "${SSH_OPTS[@]}" "$1" "$2"; fi
}

info() { printf '[+] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }
die()  { printf '[x] %s\n' "$*" >&2; exit 1; }
memavail() { awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo; }

# ── 0. 失败路径免疫（2026-09-29 10:45 OOM 整机重启事故的放大器=楔死容器无人收）──
#    非零退出时：容器日志全量落盘 ~/l10-incident/，然后四机 rm 容器。
#    CUDA/UMA 不进 cgroup（--memory 32g 拦不住），楔死容器会持续吃设备内存直至整机 OOM。
INCIDENT_DIR="$HOME/l10-incident"
# D15 门③ 账：本靴创建容器 Id（cleanup 只清本靴 Id；空=未起/非本靴——superseded 不落枪判据）
HEAD_CID=""
declare -A WORKER_CID=()
cleanup_on_fail() {
  local rc=$?
  trap - EXIT INT TERM
  (( rc == 0 )) && return 0
  mkdir -p "$INCIDENT_DIR"
  echo "[cleanup] rc=$rc — 落盘容器日志并清除容器（防 UMA 楔死续吃；D15 门③=只清本靴 Id）"
  # D15 门③ superseded 不落枪（承 ext-switch control.py:39-40 / node.py:49-52
  #   「A superseded start must never tear down a newer experimental boot」）：
  #   现行容器 Id ≠ 本靴捕获 Id ⇒ 已被新靴替换——不落盘不清除（不落枪）。
  local cur wcur wcid
  cur=$(docker inspect -f '{{.Id}}' "$HEAD_CTN" 2>/dev/null || true)
  if [[ -n "${HEAD_CID:-}" && "$cur" == "$HEAD_CID" ]]; then
    docker logs "$HEAD_CTN" > "$INCIDENT_DIR/head.exit.log" 2>&1 || true
    docker rm -f "$HEAD_CID" >/dev/null 2>&1 || true
  else
    echo "[cleanup][superseded] head 非本靴容器（本靴 Id=${HEAD_CID:-未起}/现行=${cur:-无}）——不落枪（新靴拒拆）"
  fi
  for w in "${WORKERS[@]}"; do
    IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"
    wcid="${WORKER_CID[$_h]:-}"
    wcur=$(ssh "${SSH_OPTS[@]}" "$_h" "docker inspect -f '{{.Id}}' $WORKER_CTN 2>/dev/null" || true)
    if [[ -n "$wcid" && "$wcur" == "$wcid" ]]; then
      ssh "${SSH_OPTS[@]}" "$_h" "docker logs $WORKER_CTN" > "$INCIDENT_DIR/worker-$_h.exit.log" 2>&1 || true
      ssh "${SSH_OPTS[@]}" "$_h" "docker rm -f $wcid" >/dev/null 2>&1 || true
    else
      echo "[cleanup][superseded] worker $_h 非本靴容器（本靴 Id=${wcid:-未起}/现行=${wcur:-无}）——不落枪"
    fi
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

# ── 1.6 D15 门② PFC 位级断言 + trust dscp（2026-10-16）────────────────────────
# 法源=ext-switch node.py:29-33 模式承接；**真值取我方**：PFC=0 0 0 1 0 1 0 0
# （prio3+5）≠ 外部 prio3-only 单口形——盲抄外部 mask=误红合法靴（借模式不借值）。
# 同判据在役件=dualplane-guard v1.3 :90-93（PRECOND c7b7ea1a59cf）+aicad-roce-tune
# （QoS 主机权威）；本门=起靴前置断言（红=先 roce-tune 恢复 lossless 再靴）。
# 设备=部署对 enp1s0f0np0+enP2p1s0f1np1（NCCL_IB_HCA 承载面 2 口；四口平面面
# 归 dualplane-guard 在役自检）。
pfc_probe_local() {  # 部署对 2 口：mtu=9000 + trust dscp + PFC 8 位逐位（解析式承 guard:90-93）
  local ifc mq pfc tr mtu
  for ifc in enp1s0f0np0 enP2p1s0f1np1; do
    mtu=$(cat "/sys/class/net/$ifc/mtu" 2>/dev/null)
    mq=$(mlnx_qos -i "$ifc" 2>/dev/null)
    pfc=$(echo "$mq" | awk '$1=="enabled"{print $2,$3,$4,$5,$6,$7,$8,$9; exit}')
    tr=$(echo "$mq" | awk '/trust state/{sub(/.*: /,""); print; exit}')
    if [[ "$mtu" == "9000" && "$tr" == "dscp" && "$pfc" == "0 0 0 1 0 1 0 0" ]]; then
      echo "OK $ifc pfc=[$pfc] trust=$tr mtu=$mtu"
    else
      echo "HOLE $ifc pfc=[$pfc] trust=[$tr] mtu=[$mtu]"
    fi
  done
}
pfc_check() {  # <ssh目标|->
  local t=$1 out bad
  if [[ "$t" == "-" ]]; then out=$(pfc_probe_local); else
    out=$(ssh "${SSH_OPTS[@]}" "$t" "$(declare -f pfc_probe_local); pfc_probe_local"); fi
  bad=$(grep -v '^OK ' <<<"$out" || true)
  [[ -z "$bad" ]] || die "[D15] PFC 位级断言红（拒启；先 aicad-roce-tune 恢复 lossless 再靴）：
$bad"
  info "[D15] $(grep -c '^OK ' <<<"$out")/2 iface PFC prio3+5+trust dscp+mtu9000 在位"
}
info "== D15 门② PFC 位级断言（prio3+5/trust dscp/mtu9000）=="
pfc_check "-"
for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"; pfc_check "$_h"; done

# ── 1.7 D15 门⑤（K5 doctor 网络双检并入，2026-10-18 重锚版）──────────────────
# 法源=ext-knapcio files/doctor-network.sh（51 行，只读核借模式）+EXT-KNAPCIO-SWITCH
# CANDIDATES K5 行（S-GOV2 裁定：四门→五门，第五门=K5 并入 D15）。
# 判据=**读 state 不读 rate**（/sys/class/infiniband/<HCA>/ports/1/state 文件读数，
# 外部注记原文 "deliberately checks port 1"）：NCCL_IB_HCA 部署对 2 口（rocep1s0f0+
# roceP2p1s0f1，真值源=本脚本 COMMON_ENV :245 现役值，与门② PFC 硬编码同法）逐口
# state=='4: ACTIVE'；+ socket 接口（NCCL_SOCKET_IFNAME=enP7s7，:248 同源）存在。
# 红=拒启（fail-closed=DOCTOR_STRICT 恒 1 形：boot 前置即 blocking——外部 doctor 缺省
# 警告+DOCTOR_STRICT=1 才 block，我方并入 boot 前置=恒 block 语义）。
# 外部教训注记：接口名四节点不同名 ⇒ Gloo init 杀 rank（"Unable to find address for"）。
net_doctor_local() {  # HCA 部署对逐口 port1 ACTIVE + socket 接口存在（读 state 不读 rate）
  local hca st bad=0
  for hca in rocep1s0f0 roceP2p1s0f1; do
    st=$(cat "/sys/class/infiniband/$hca/ports/1/state" 2>/dev/null || true)
    if [[ "$st" == "4: ACTIVE" ]]; then
      echo "OK $hca port1=${st}"
    else
      echo "HOLE $hca port1=${st:-missing}（期望 4: ACTIVE）"
      bad=1
    fi
  done
  if [[ -d "/sys/class/net/enP7s7" ]]; then
    echo "OK socket-if enP7s7 在位"
  else
    echo "HOLE socket-if enP7s7 缺（GLOO/NCCL_SOCKET_IFNAME 承载面）"
    bad=1
  fi
  return "$bad"
}
net_doctor_check() {  # <ssh目标|->
  local t=$1 out bad
  if [[ "$t" == "-" ]]; then out=$(net_doctor_local); else
    out=$(ssh "${SSH_OPTS[@]}" "$t" "$(declare -f net_doctor_local); net_doctor_local"); fi
  bad=$(grep -v '^OK ' <<<"$out" || true)
  [[ -z "$bad" ]] || die "[D15-⑤] doctor 网络双检红（拒启；HCA 失活/接口缺=起机静默前置拦）：
$bad"
  info "[D15-⑤] $(grep -c '^OK ' <<<"$out")/3 doctor 面（HCA×2 ACTIVE+socket-if）在位"
}
info "== D15 门⑤ K5 doctor 网络双检（HCA ACTIVE+socket 接口；读 state 不读 rate）=="
net_doctor_check "-"
for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"; net_doctor_check "$_h"; done

# ── 2. UMA 总账前置（A1/A2 硬门：严禁整表；起栈前水位 ≥100G）+ 对称 drop_caches ──
info "== UMA 总账 + 四机对称 drop_caches =="
drop_and_check() {  # drop_and_check <显示名> <ssh目标|->
  local name="$1" target="$2" cmd pw
  pw=$(cat ~/.sudopw)
  # D15 门①（KiB 形 UMA 门，承 ext-switch node.py:35-36 同式：raw KiB ≥100_000_000）：
  #   既有 MB 形 ≥100000 保留=双形互证（KiB=字节级口径，不吃 awk 取整）。
  cmd="printf '%s\n' '$pw' | sudo -S sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; awk '/MemAvailable/{print \$2}' /proc/meminfo"
  local mkib m
  if [[ "$target" == "-" ]]; then mkib=$(eval "$cmd"); else mkib=$(ssh "${SSH_OPTS[@]}" "$target" "$cmd" 2>/dev/null); fi
  m=$(( ${mkib:-0} / 1024 ))
  [[ "${mkib:-0}" -ge 100000000 ]] || die "$name drop 后 MemAvailable=${mkib}KiB < 100_000_000KiB（D15 门① KiB 形 UMA 门，拒起）"
  [[ "${m:-0}" -ge 100000 ]] || die "$name drop 后 MemAvailable=${m}M < 100G（UMA 总账红，拒起）"
  info "$name drop_caches 后 ${m}M（KiB=${mkib}；双形门绿）"
}
drop_and_check "head" "-"
for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"; drop_and_check "$_h" "$_h"; done

# ── 3. 资产在位核验（adapter/NCCL/打包分片/权重） ─────────────────────────────
[[ -d "$ADAPTER_DIR" && -f "$ADAPTER_DIR/sitecustomize.py" && -f "$ADAPTER_DIR/engram_backend.py" ]] || die "adapter 资产缺（~/migrate-assets/dsv41/adapter）"
# RETIRED-net-rebuild-20261015：环网补丁资产门退役（stock NCCL 接管；补丁件仍原位封存但不再为 boot 前置）
# [[ -f "$NCCL_DIR/libnccl.so.2.30.7" && -f "$NCCLPIN" ]] || die "NCCL 资产缺（~/migrate-assets）"
ls "$ENG_HOST_HEAD"/engram-l1-r0of4.bin "$ENG_HOST_HEAD"/engram-l14-r0of4.bin >/dev/null 2>&1 || die "head 打包分片缺（L1/L14）"
for w in "${WORKERS[@]}"; do
  IFS='|' read -r _rk _h _ip _src _eng _ph <<<"$w"
  # net-rebuild-wc-20261015 复靴段：环网补丁资产两 clause（nccl-ringonly/ncclpin）退役（同上行资产门注）
  ssh "${SSH_OPTS[@]}" "$_h" "test -f $_eng/engram-l1-r${_rk}of4.bin && test -f $_eng/engram-l14-r${_rk}of4.bin && test -f '$ADAPTER_DIR/sitecustomize.py' && test -f '$HOME/migrate-assets/b12x/b12x_next/__init__.py' && test -f '$_src/config.json'" \
    || die "$_h 资产面缺（adapter/b12x_next/分片/权重）"
  info "  $_h 资产面 OK"
done

# ── 3.5 autotune golden 四秩预检 + work 种子（含 rank0——fin2 病根=只查 worker）──
if (( AT_ON )); then
  info "== autotune golden 预检（四秩含 rank0）=="
  if [[ "$AUTOTUNE_GOLDEN" == "1" ]]; then
    [[ -f "$AT_MANIFEST" && -f "$AT_MD5" ]] \
      || die "golden 缺 MANIFEST/table.md5（$AT_GOLDEN_DIR）——先 AUTOTUNE_CAPTURE=1 捕获并四机同步"
    # 代际门：跨镜像/flashinfer 版本的旧表会被 load_configs 整表硬拒
    # （autotuner.py:2657+ _metadata 六字段硬失配=静默跳过→靴内重调优）。
    [[ "$(python3 -c "import json;print(json.load(open('$AT_MANIFEST'))['image'])")" == "$IMAGE" ]] \
      || die "golden 表属别的镜像（MANIFEST.image≠$IMAGE）——冻结纪律：重新捕获，禁复用"
    AT_REL="$(python3 -c "import json;m=json.load(open('$AT_MANIFEST'));print('%s/%s/%s'%(m['fi_version'],m['arch'],m['cache_key']))")"
    [[ -n "$AT_REL" ]] || die "MANIFEST 解析失败（fi_version/arch/cache_key）"
    # 四机在位+内容一致（head=rank0 本地查；worker 逐台 ssh 查——启动器级四秩自审）
    at_check() { at_remote "$1" "cd '$AT_GOLDEN_DIR' && md5sum -c table.md5 --quiet" >/dev/null 2>&1; }
    at_check - || die "head(rank0) golden 表在位/md5 核验失败（fin2 假阳性病位：rank0 缺表毒化整组）"
    info "  rank0 @ head golden OK（$AT_REL）"
    for w in "${WORKERS[@]}"; do
      IFS='|' read -r rk _h _ip _ _ _ph <<<"$w"
      at_check "$_h" || die "rank$rk@$_h golden 表在位/md5 核验失败——四机同步后再起（拒起=防缺表秩进 TP 锁步）"
      info "  rank$rk @ $_h golden OK"
    done
    # 种子 work（rw）：save_configs 每上下文退出无条件重写 + 分化 unlink
    # （flashinfer_autotune.py:247）都落在 work 副本内，golden 本体零接触。
    at_seed() { at_remote "$1" "rm -rf '$AT_WORK' && mkdir -p '$AT_WORK' && cp -a '$AT_TABLE/.' '$AT_WORK/'"; }
  else
    at_seed() { at_remote "$1" "rm -rf '$AT_WORK' && mkdir -p '$AT_WORK'"; }  # 捕获：空表冷调
  fi
  at_seed - || die "head work 种子失败"
  for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"
    at_seed "$_h" || die "$_h work 种子失败"; done
  info "  work 副本就绪（rw 挂载 → /root/.cache/sglang/flashinfer/autotune）"
fi


# ── 4. 公共面 ────────────────────────────────────────────────────────────────
DOCKER_HW=(
  --network host --ipc host --privileged --cap-add IPC_LOCK --gpus all
  --memory 32g --memory-swap 32g
  --ulimit memlock=-1 --ulimit stack=67108864
  --device /dev/infiniband:/dev/infiniband
# RETIRED-net-rebuild-20261015（复靴段 R1）：环网补丁链三挂载退役（stock NCCL 接管；回退=.bak-pre-reboot）
#  -v "$NCCL_DIR":/opt/nccl-ringonly:ro
#  -v "$NCCLPIN":/opt/ncclpin.so:ro
#  -v "$NCCL_DIR/libnccl.so.2.30.7":"$PIP_NCCL":ro
  -v "$ADAPTER_DIR":/opt/dsv41/adapter:ro
  -v "$B12X_DIR":/opt/b12x-tree:ro
)
COMMON_ENV=(
  -e NCCL_NET=IB
  # net-rebuild-wc-20261015（W-B §S4.2 必改①②；判读基座换代）：
  # HCA 4 口裸列→部署双 rail 对（rocep1s0f0=rail0/enp1s0f0np0 + roceP2p1s0f1=rail1/enP2p1s0f1np1，
  # 跨 PCIe 域各取一；W-B §S3.3：4 口形 twin 分区面间歇黑洞且不增带宽，2 口=同 196Gb/s 物理封顶）。
  # NCCL_IB_TC=106 新增=唯一生效标记杆（→DSCP26→交换机 SP3/TC3/PFC prio3 受保护档；
  # W-B A1：TC46/106 NCCL 层零差+per-priority 计数器生效核）。
  -e NCCL_IB_HCA=rocep1s0f0,roceP2p1s0f1
  -e NCCL_IB_TC=106
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
# RETIRED-net-rebuild-20261015（复靴段 R1）：LD_PRELOAD 环网补丁退役（下行为史档）
#  -e "LD_PRELOAD=/opt/ncclpin.so $PIP_NCCL"
  -e NCCL_ALGO=RING -e NCCL_BUFFSIZE=8388608 -e NCCL_CROSS_NIC=1
  -e NCCL_CUMEM_ENABLE=0 -e NCCL_CUMEM_HOST_ENABLE=0
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_MERGE_NICS=0 -e NCCL_IB_RETRY_CNT=7
  -e NCCL_IB_SUBNET_AWARE_ROUTING=1 -e NCCL_IB_TIMEOUT=1000
  # net-rebuild-wc-20261015：NCCL_IB_TOS=46 退役（W-B §S4.2 必改③——键在 2.30.7 三二进制零命中=惰性，
  # wire 实证流出网 prio0 无标记；回退=补 -e NCCL_IB_TOS=46 或旧件 .bak-pre-wc 回拷）。
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
  # INCIDENT-13:26/15:17 修复（F-4 转部署默认，用户裁定缓存存活/用量须控）：
  # CHUNK_LIFETIME=chunk 边界 epoch 失效（fake +20.5pt 命中保持）；
  # PREFETCH=1+ROWS=4096=chunk 头行集 side-stream 预热（砍盘读风暴主体）；
  # CACHE_GIB=1=显式每层顶（废除 //2 隐除；守卫超 min(4GiB,10%MemAvail) 告警）。
  -e DSV41_ENGRAM_PREFETCH=1
  -e DSV41_ENGRAM_PREFETCH_ROWS=4096
  -e DSV41_ENGRAM_CHUNK_LIFETIME=1
  -e DSV41_ENGRAM_CACHE_GIB=1
  # 点3（2026-09-30）fork 生产实战键采纳：WAYS=16 行缓路数（fork 生产值，
  # row_store 上限 16；缺省 4=驱逐过粗）；LOGITS 预算=128MiB（变更 #16 系
  # 2GiB→512M→128M 定板，sparse_wire.install_scoring 接管 main 树行块常量）。
  -e DSV41_CACHE_WAYS=16
  -e DSV41_DENSE_INDEXER_LOGITS_BUDGET_BYTES=134217728
  # P0 修复配套（2026-10-01）：SM121 候选对承接（sparse 探针拒→DenseBlocks int32 块表）。
  # 与 topk:2048 成对——没有此件，main 的 sparse_table 非 chunked 路径会把 CPU 哑元喂核。
  -e DSV41_DG_SPARSE_SM121=1
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
# ── 产化件后端键登记（AUD-3 S1-2，2026-10-01）────────────────────────────
# repack 桥后端两键不入 COMMON_ENV（默认 auto=hybrid 即产化默认，A0H 锚已立）：
#   DSV41_FP4KV_REPACK_BACKEND={triton,cuda,auto}   # auto=n 阈值 hybrid 派发
#   DSV41_FP4KV_REPACK_CUDA_MIN_N=<int>             # 默认 2048；负值=恒 cuda（勿用）
# 注入纪律：两键只准经 ARM_ENV_FILE（四秩一致+留痕）；禁止单机手工 docker -e
# （四秩分叉虽位等无恙但 census 迹线不对称）。相关：DSV41_REPLAY_GUARD（默认 on，
# features 门自激活，P1 bounded-replay 卡配套件）。

# ── [QA-GATES L8·D-env] boot 期 env lint 拒绝门（2026-10-05 QAVLW2 固化；追加式缺省 no-op）──
# GATE_FORM 未设=整段跳过（生产/既有臂行为逐字不变）；火卡显式带 GATE_FORM 即激活拒绝门：
# 对 ARM_ENV_FILE 过三禁令+形态键黑名单+键面合同（--form v2|r1prime|v40731；未知形态=拒绝）。
# lint 器=r3-gate-env-lint.sh（D2 md5 锚 5337c6cf9cb8aa6c893ad1b97094660d）；红=拒起（fail-closed）。
if [[ -n "${GATE_FORM:-}" ]]; then
  if [[ -n "${ARM_ENV_FILE:-}" && -f "$ARM_ENV_FILE" ]]; then
    bash "$HOME/migrate-assets/bin/r3-gate-env-lint.sh" --form "$GATE_FORM" "$ARM_ENV_FILE" \
      || die "[gate] env-lint REFUSE（form=$GATE_FORM file=$ARM_ENV_FILE）——拒绝起栈（GATE-MATRIX L8 fail-closed）"
    echo "[gate] env-lint PASS（form=$GATE_FORM file=$ARM_ENV_FILE）"
  else
    echo "[gate] GATE_FORM=$GATE_FORM 而 ARM_ENV_FILE 缺位——无注入面可 lint（COMMON_ENV 固有面不适用臂 lint）"
  fi
fi

# ── [EQ-02·红线断言族] RoCE 通信聚合双键条件式 fail-closed 门（2026-10-30 0.3.4re EQ-02）──
# 法源=035-W0-TASKBOOK-20261030 §EQ-02（外部手册升级篇 §14 A/B/A 实测：两键回滚即
# c8 −96% 非单调塌陷；此前台账铁律「不许回滚这两键」无机器执行力）+RUNTIME-PARAMETERS
# §1.9 两键绑定律（在役值均 1179648）。代际分形=条件式断言（勿做无条件断言）：
#   ① env（ARM_ENV_FILE）声明两键（生效行）→ 在役值必须双双=1179648；任一回滚值
#      （524288/262144 等历史档位）=die 拒起（fail-closed）；
#   ② 单边声明（其一缺）→ 两键绑定律破裂=「清理多余参数」式砍键指纹，die 拒起；
#   ③ 两键均未声明（新代际形：RoCE 聚合面整族退役的 env，如 VL41N 系）→ 不断言放行。
# ARM_ENV_FILE 缺位=无注入面（两键不在 COMMON_ENV 固有面）→ 不断言。绿=横幅自报在役值
# （boot 四查可直证）。读法与注入循环同口径（逐行 KEY=VAL；# 注释行跳过；尾行守护同款）。
if [[ -n "${ARM_ENV_FILE:-}" && -f "$ARM_ENV_FILE" ]]; then
  _eq02_max=""; _eq02_gather=""
  while IFS= read -r _eq02_line || [ -n "$_eq02_line" ]; do
    [[ -z "$_eq02_line" || "$_eq02_line" == \#* ]] && continue
    [[ "$_eq02_line" == "SGLANG_ROCE_MAX_SIZE="* ]] && _eq02_max="${_eq02_line#SGLANG_ROCE_MAX_SIZE=}"
    [[ "$_eq02_line" == "DSV41_ROCE_GATHER="* ]] && _eq02_gather="${_eq02_line#DSV41_ROCE_GATHER=}"
  done < "$ARM_ENV_FILE"
  _eq02_n=0
  [[ -n "$_eq02_max" ]] && _eq02_n=$((_eq02_n+1))
  [[ -n "$_eq02_gather" ]] && _eq02_n=$((_eq02_n+1))
  if [[ $_eq02_n -eq 2 ]]; then
    [[ "$_eq02_max" = 1179648 && "$_eq02_gather" = 1179648 ]] \
      || die "[EQ-02] RoCE 聚合双键断言红（拒起；fail-closed）：SGLANG_ROCE_MAX_SIZE=$_eq02_max / DSV41_ROCE_GATHER=$_eq02_gather ≠ 在役值 1179648——回滚即 c8 −96% 非单调塌陷（RUNTIME-PARAMETERS §1.9 绑定律；035-W0 EQ-02）；恢复两键=1179648 后重靴"
    info "[EQ-02] RoCE 聚合双键在役断言 PASS：SGLANG_ROCE_MAX_SIZE=DSV41_ROCE_GATHER=1179648（$ARM_ENV_FILE）"
  elif [[ $_eq02_n -eq 1 ]]; then
    die "[EQ-02] RoCE 聚合双键断言红（拒起；fail-closed）：单边声明 SGLANG_ROCE_MAX_SIZE=${_eq02_max:-缺} / DSV41_ROCE_GATHER=${_eq02_gather:-缺}——两键绑定律破裂（清理式砍键指纹；RUNTIME-PARAMETERS §1.9）；两键同补=1179648 或同退役（新代际形）后重靴"
  else
    info "[EQ-02] RoCE 聚合双键未声明（新代际形）——条件式门不断言，放行（$ARM_ENV_FILE）"
  fi
fi

# ── ARM 注入面（doc102 W1 单变量开臂）：ARM_ENV_FILE 每行一个 KEY=VAL，注入 COMMON_ENV ──
# 2026-10-30 修复（外部站点 bug 报告）：read 循环加尾行守护 || [ -n "$line" ]——
# env 文件末尾缺换行时 while read 会静默丢掉最后一行（恰常为关键开关），且
# r3-gate-env-lint.sh 的 lint 循环自带同款守护会照常 PASS，形成"lint 绿但键丢"。
if [[ -n "${ARM_ENV_FILE:-}" && -f "$ARM_ENV_FILE" ]]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" || "$line" == \#* ]] && continue
    COMMON_ENV+=(-e "$line")
    echo "[arm] +env $line"
  done < "$ARM_ENV_FILE"
fi
ARM_TAG="${ARM_TAG:-baseline}"
echo "[arm] ARM_TAG=$ARM_TAG SPEC=$SPEC"

# ── [VL-W1·overlay 支持] SGLANG_OVERLAY_DIR 影子挂载面（2026-10-05 QAVLW2 追加；缺省空=no-op）──
# 0928 机制的 r3 移植（OVERLAY-ENV-REVIEW §1-4）：驱动包装环境提供宿主目录（ARM_ENV_FILE 行
# 只进 docker -e 不产生宿主挂载）。空=整段跳过（生产/既有臂行为逐字不变）；非空=fail-closed：
# 目录/映射表缺=拒起；映射表逐行 28 件 -v 影子挂载进 DOCKER_HW（head 与 worker REMOTE_CMD
# 共用=四秩同挂）；任一件缺=拒起；worker 远端在位核验（docker -v 对缺源会静默建目录=前置拦）；
# 挂载计数断言==28。包根=容器内 import 定谳（seg4 探针 /sgl-workspace/sglang/python）。
SGLANG_OVERLAY_DIR="${SGLANG_OVERLAY_DIR:-}"
if [[ -n "$SGLANG_OVERLAY_DIR" ]]; then
  SGLANG_OVERLAY_MAP="${SGLANG_OVERLAY_MAP:-$SGLANG_OVERLAY_DIR/overlay-map.tsv}"
  SGLANG_PKG_ROOT="${SGLANG_PKG_ROOT:-/sgl-workspace/sglang/python}"
  [[ -d "$SGLANG_OVERLAY_DIR" ]] || die "[overlay] 目录缺：$SGLANG_OVERLAY_DIR"
  [[ -r "$SGLANG_OVERLAY_MAP" ]] || die "[overlay] 映射表缺：$SGLANG_OVERLAY_MAP"
  ov_n=0
  while IFS=$'\t' read -r ov_flat ov_rel; do
    [[ -n "${ov_flat:-}" && "$ov_flat" != \#* ]] || continue
    [[ -f "$SGLANG_OVERLAY_DIR/$ov_flat" ]] || die "[overlay] 缺件（fail-closed）：$SGLANG_OVERLAY_DIR/$ov_flat"
    DOCKER_HW+=(-v "$SGLANG_OVERLAY_DIR/$ov_flat:$SGLANG_PKG_ROOT/sglang/$ov_rel:ro")
    ov_n=$((ov_n + 1))
  done < "$SGLANG_OVERLAY_MAP"
  [[ "$ov_n" -eq 28 ]] || die "[overlay] 挂载计数=$ov_n ≠28（映射表行数异常）"
  for w in "${WORKERS[@]}"; do
    IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"
    ov_r=$(ssh "${SSH_OPTS[@]}" "$_h" "test -d '$SGLANG_OVERLAY_DIR' && test -r '$SGLANG_OVERLAY_MAP' && cut -f1 '$SGLANG_OVERLAY_MAP' | grep -v -e '^#' -e '^\$' | sort | (cd '$SGLANG_OVERLAY_DIR' && xargs -I{} test -f {})" 2>/dev/null) \
      || die "[overlay] $_h 远端在位核验红（目录/映射表/任一件缺；fail-closed）"
    info "  [overlay] $_h 28 件远端在位 OK"
  done
  info "[overlay] $SGLANG_OVERLAY_DIR → 28 件影子挂载至 $SGLANG_PKG_ROOT/sglang（四秩同挂）"
fi

# ── autotune golden 挂载面（AT_ON 才注入；缺省零行为差）──
# 注：必须 rw。save_configs 在每个 autotune 上下文退出时无条件重写表
# （flashinfer_autotune.py:297-298），ro 挂载会在 tempfile.mkstemp 即崩。
if (( AT_ON )); then
  DOCKER_HW+=(-v "$AT_WORK":/root/.cache/sglang/flashinfer/autotune:rw)
  # 显式钉住表复用（缺省本就是 True=environ.py:1095；显式=防未来缺省翻转后静默退化为 runs/ 一次性表）
  COMMON_ENV+=(-e SGLANG_FLASHINFER_AUTOTUNE_CACHE=1)
  info "[autotune-golden] mode=${AUTOTUNE_CAPTURE:+capture}${AUTOTUNE_GOLDEN:+prod} work=$AT_WORK"
fi

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
  # P0 修复（2026-10-01 定谳）：topk:0 曾为绕 SM121 断线的权宜——它使 make_candidate_indexer
  # 早退 dense，而该 dense 绕行面=前向正确性 P0 真身（GSM8K 72%→97.5%、XQ7→X7Q 相邻换位、
  # needle 0/3→3/3；判别链见 docs/incidents/INCIDENT-20260930-QUALITY-P0-forward-corruption.md）。
  # checkpoint 原生 config 即 2048（候选池 2048×8=16384=模型一部分，doc102 硬边界）。
  # SM121 侧由 adapter sparse_wire 的 DenseBlocks 候选对承接（DSV41_DG_SPARSE_SM121=1，
  # #40352 int32 块表=论文近似形态，arch==10 断言→REFUSED→候选语义保留）。
  --json-model-override-args '{"candidate_topk_blocks": 2048}'
  # r10 census 定谳：无此参 ⇒ resolve_block_fp8_mxfp8_backend 判 UNSUPPORTED（只认显式
  # cutlass/cutedsl）⇒ [32,32]ue8m0 权重不序列化 MXFP8 ⇒ dense 全落 Triton w8a8 =
  # 42.2ms/步（grid160×81+256/36/56×40.7 次/步，204µs/GEMV 病理）。fin2 生产同参：
  # checkpoint 原生 mxfp8 形态 + 此参 + adapter mxfp8_b12x 重路由 cutlass→b12x。
  # 注意与 --moe-runner-backend（r6 判负的 flashinfer_cutlass）是两个不同参数面。
  --fp8-gemm-backend flashinfer_cutlass
  # R3.4（doc94 §G）：无 pin 时 stock main 池按 fraction 吃满只剩 12.1G，UMA 必破。
  # pin=生产同值 9.6M（main fp8 KV ⇒ 池≈17GB/rank，CUDA 总≈45G，余量≈70G）。
  --max-total-tokens 9600000
  # ── net-rebuild-wc-20261015：A8/A9 接线（0.3.2 ADDENDUM §十；boot 参面单键新增，不改源码、
  #    不动既有六参——SPEC6 谱 6→8 参；SPEC6-SERVE-REF 表第 7/8 行同批补）──
  # A8（issue #1）：DSML 原生工具调用不成型根因=serving.py tool_call_parser 缺省 None+
  #   _tool_call_parsing_active() 门禁整链旁路。正字法铁律：tool_call 侧**必须连写** deepseekv41；
  #   deepseek-v41（连字符）是 reasoning parser 写法、本参不认（第 5 行 --reasoning-parser 照旧不动）。
  #   只对带 tools 请求生效；无 tools 请求行为零变化。验收=issue 复现 curl 三路径 tool_calls 成型。
  --tool-call-parser deepseekv41
  # A9（issue #2）：enable_cache_report 缺省 False（serving.py:189-192+serving_chat.py:796 硬门）
  #   ⇒ usage.prompt_tokens_details 恒 null。接线=cached_tokens 随响应返回（可观测性面附加字段，
  #   零计算路径；knapcio v2.4 生产栈同款交叉印证）。验收=cached_tokens 非 null（同前缀二发）。
  --enable-cache-report
  # ── NET-WG-SLEEPIDLE-20261016（引擎参数微调窗；来源=用户令 2026-10-16）：V1=空闲面单键——
  #    SGLang 调度器空闲忙转吃满 1 个核、墙插 +10–12W/台（四台约 40–48W 可省）。
  #    镜像已核支持：main-79cafec0 内 `python3 -m sglang.launch_server --help` 含
  #    "--sleep-on-idle  Reduce CPU usage when sglang is idle."。
  #    参面单键新增、不改源码、不动既有八参——SPEC6 谱 8→9 参（SPEC6-SERVE-REF 表同批补行，
  #    九参归一指纹重算预登记）。行为面：仅空闲态降 CPU，请求路径零变化。
  #    回退=去此单行重靴（或 .bak-pre-wg 还原；零 env 耦合、零 A8/A9 面耦合）。
  # ── RETIRED-UP43050-20261030（上游缺陷 host 侧规避窗；法源=上游 sglang #43050
  #    https://github.com/sgl-project/sglang/issues/43050）：与我栈完全同构的报告——
  #    GB10/SM121/UMA×3 DGX Spark + DSv4.1-Flash + DSPARK speculative + NCCL 2.32.3
  #    + --sleep-on-idle：空闲 10-20 分钟后被任意请求（含健康探测）唤醒即进入死 prefill，
  #    py-spy 卡 _low_ratio_index_topk_dense（indexer_chunked_v3.py:181）的
  #    prefill_empty_cache 唤醒重捕获路径，疑似唤醒后缺一处 host 同步点；无修复 PR。
  #    报告者实测：同一硬件去掉 --sleep-on-idle 后空闲期完全正常 ⇒ 本窗退役该参
  #    （W-G 窗省 CPU 收益让位可用性；SPEC6 谱 9→8 参，归一指纹回 6b12a445）。
  #    替代面：如需回收空闲资源，走低峰期主动 /release_memory 或定时重启（勿用自动
  #    idle-sleep）。禁参三面固化：env-lint EQ-03 禁参组合（值面注入位拒起）+
  #    tools/serve_flags_gate.sh 缺席判据（argv 在场即 FAIL）+ selfcheck-prod 禁参表。
  #    升级镜像时优先吸收 #45397/#46636 一类 idle 路径修复，并在补丁镜像里守卫 wake
  #    路径的 host-sync 后，方可在复评窗重议此参。史注（W-G 窗原注记）上方原样保留。
  # RETIRED-UP43050-20261030: --sleep-on-idle  ← 原参行在此，退役=注释化，勿回拷
  #    .bak-pre-wg 单参回退面（该回退=重新引入 #43050 idle-wake hang）。
)
[[ "$SPEC" == "1" ]] && SERVER_ARGS+=(--speculative-algorithm DSPARK) || info "SPEC=0"

# ── ARM SERVER_ARGS 注入面（doc102 W1 S1-prep 方案）：SPEC_EXTRA_ARGS 空格分词追加；缺省 no-op ──
if [[ -n "${SPEC_EXTRA_ARGS:-}" ]]; then
  read -r -a _SEA <<< "$SPEC_EXTRA_ARGS"
  SERVER_ARGS+=("${_SEA[@]}")
  echo "[arm] +server-args ${_SEA[*]}"
fi

# ── 5. 起 workers（每秩 PEER_HCA+分片挂载） ────────────────────────────────────
info "== 起 workers =="
for w in "${WORKERS[@]}"; do
  IFS='|' read -r rank host ip src eng phca <<<"$w"
  ssh "${SSH_OPTS[@]}" "$host" "docker rm -f $WORKER_CTN >/dev/null 2>&1 || true"
  # net-rebuild-wc-20261015：NCCL_IB_PEER_HCA=-e 注入行退役（见 WORKERS 头注；不再注入）。
  REMOTE_CMD=(docker run -d --name "$WORKER_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}"
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
  WORKER_CID["$host"]="$(ssh "${SSH_OPTS[@]}" "$host" "docker inspect -f '{{.Id}}' $WORKER_CTN 2>/dev/null" || true)"
  info "  rank $rank @ $host 存活（/engram 已挂；NCCL_IB_PEER_HCA 已退役不复注入；D15 门③ Id=${WORKER_CID[$host]:0:12}）"
done

# ── 6. 起 head ───────────────────────────────────────────────────────────────
info "== 起 head (rank 0, API :$API_PORT) =="
docker rm -f "$HEAD_CTN" >/dev/null 2>&1 || true
# net-rebuild-wc-20261015：NCCL_IB_PEER_HCA（head 侧）注入行退役，不再注入。
docker run -d --name "$HEAD_CTN" "${DOCKER_HW[@]}" "${COMMON_ENV[@]}" \
  -v "$HEAD_MODEL_SRC:$MOUNT_TGT:ro" \
  -v "$ENG_HOST_HEAD:/engram:ro" \
  "$IMAGE" python3 -m sglang.launch_server "${SERVER_ARGS[@]}" \
  --node-rank 0 --host 0.0.0.0 --port "$API_PORT"
sleep 8
[[ "$(docker inspect -f '{{.State.Running}}' "$HEAD_CTN" 2>/dev/null)" == "true" ]] || { docker logs --tail 30 "$HEAD_CTN" 2>&1 || true; die "head 起败"; }
HEAD_CID="$(docker inspect -f '{{.Id}}' "$HEAD_CTN" 2>/dev/null || true)"
info "head 存活（D15 门③ 本靴 Id=${HEAD_CID:0:12}）"

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
    # ── D15 门④ /server_info 取参面真值断言（承 ext control.py:28-33 模式：断言值取自
    #    真参面；**真值从 SERVER_ARGS 数组读**，不硬编码抄本——参面单键改动本门自动跟随）──
    _argval() { local k="$1" i; for ((i=0;i<${#SERVER_ARGS[@]};i++)); do
        [[ "${SERVER_ARGS[i]}" == "$k" ]] && { printf '%s' "${SERVER_ARGS[i+1]}"; return 0; }; done; return 1; }
    si=$(curl -fsS --max-time 15 "http://127.0.0.1:${API_PORT}/server_info" 2>/dev/null) \
      || { dump_all; die "D15 门④ /server_info 不可读"; }
    _si_num() { grep -oE "\"$1\":[ ]*[0-9]+" <<<"$si" | head -1 | grep -oE '[0-9]+$'; }
    tok=$(_si_num max_total_num_tokens); ctx=$(_si_num context_length); mrr=$(_si_num max_running_requests)
    arg_tok=$(_argval --max-total-tokens) || { dump_all; die "D15 门④ SERVER_ARGS 无 --max-total-tokens"; }
    arg_ctx=$(_argval --context-length) || { dump_all; die "D15 门④ SERVER_ARGS 无 --context-length"; }
    arg_mrr=$(_argval --max-running-requests) || { dump_all; die "D15 门④ SERVER_ARGS 无 --max-running-requests"; }
    arg_mdl=$(_argval --served-model-name) || arg_mdl=""
    [[ -n "$tok" && "$tok" -ge "$arg_tok" ]] || { dump_all; die "D15 门④ max_total_num_tokens=${tok:-?} < 取参面 ${arg_tok}（SERVER_ARGS --max-total-tokens）"; }
    [[ "$ctx" == "$arg_ctx" ]] || { dump_all; die "D15 门④ context_length=${ctx:-?} ≠ 取参面 ${arg_ctx}"; }
    [[ "$mrr" == "$arg_mrr" ]] || { dump_all; die "D15 门④ max_running_requests=${mrr:-?} ≠ 取参面 ${arg_mrr}"; }
    if [[ -n "$arg_mdl" ]]; then
      curl -fsS --max-time 15 "http://127.0.0.1:${API_PORT}/v1/models" 2>/dev/null \
        | grep -q "\"id\":[ ]*\"$arg_mdl\"" || { dump_all; die "D15 门④ /v1/models 无 served-model-name=$arg_mdl"; }
    fi
    info "D15 门④ /server_info 真值断言绿（tok=$tok≥$arg_tok ctx=$ctx mrr=$mrr mdl=$arg_mdl；取参面=SERVER_ARGS）"
    # ── 7.5 autotune 四秩加载自审（AT_ON；证据行=每秩自身 boot log）──
    # 证据链：per-rank "Running FlashInfer autotune with cache: …rank_tp<r>_pp…" 必现
    # （flashinfer_autotune.py:263，plain logger.info 每进程各打一条）；
    # "per-rank caches disagree"=表分化 unlink 已发生（flashinfer_autotune.py:242-247）；
    # 生产靴出现 "[AutoTuner]: Tuning "进度条=golden 未全覆盖该桶、靴内补调优（WARN）。
    if (( AT_ON )); then
      info "== autotune 四秩自审（含 rank0）=="
      at_rank_audit() {  # <rank> <target|->  → 0 绿 / 1 红
        local rk="$1" tgt="$2" log=""
        if [[ "$tgt" == "-" ]]; then log="$(docker logs "$HEAD_CTN" 2>&1)"; else log="$(ssh "${SSH_OPTS[@]}" "$tgt" "docker logs $WORKER_CTN" 2>&1)"; fi
        if ! grep -q "Running FlashInfer autotune with cache: .*rank_tp${rk}_pp" <<<"$log"; then
          warn "rank$rk boot log 无 autotune cache 证据行（表未按秩加载）"; return 1; fi
        if grep -q "per-rank caches disagree" <<<"$log"; then
          warn "rank$rk 报告四秩表分化（divergence unlink+重调优已发生）"; return 1; fi
        if [[ "$AUTOTUNE_GOLDEN" == "1" ]] && grep -q "\[AutoTuner\]: Tuning " <<<"$log"; then
          warn "rank$rk 靴内补调优（golden 未全覆盖，已写入 work 副本——采收补冻或接受 WARN）"; fi
        return 0
      }
      at_red=0
      at_rank_audit 0 - || at_red=1
      for w in "${WORKERS[@]}"; do IFS='|' read -r rk _h _ip _ _ _ph <<<"$w"
        at_rank_audit "$rk" "$_h" || at_red=1; done
      if (( at_red )); then dump_all; die "autotune 四秩自审红——缺表秩毒化 TP 锁步（fin2 病形态），拒交付"; fi
      info "四秩 autotune 证据行齐全（rank0-3 全绿）"
      # 表漂移回查：work 内本秩文件 md5 对 golden（重写=补调优/代际翻转）
      if [[ "$AUTOTUNE_GOLDEN" == "1" ]]; then
        at_ver_now="$(at_remote - "ls '$AT_WORK'" | head -1)"
        [[ "$at_ver_now" == "${AT_REL%%/*}" ]] \
          || warn "work 出现新版本目录 $at_ver_now≠${AT_REL%%/*}——flashinfer 代际已变，表被整表拒载+重调优：按冻结纪律重新捕获"
        g0="$(grep "rank_tp0_" "$AT_MD5" 2>/dev/null | awk '{print $1}')"
        w0="$(at_remote - "md5sum '$AT_WORK/$AT_REL/rank_tp0_pp0_dp0.json' 2>/dev/null" | awk '{print $1}' || true)"
        [[ -n "$g0" && "$g0" == "$w0" ]] || warn "rank0 work 表 md5 漂移（$w0 vs $g0）——本靴有重写，评估是否补冻"
      fi
    fi
    # ── 7.6 捕获采收（AUTOTUNE_CAPTURE=1）：四机 work 表 → golden+MANIFEST ──
    if [[ "$AUTOTUNE_CAPTURE" == "1" ]]; then
      info "== autotune golden 捕获采收（四机 rank_tp0-3）=="
      mkdir -p "$AT_TABLE"
      at_got=0
      at_pull() {  # <rank> <target|->：把该秩 work 表收进 golden（保 relpath）
        local rk="$1" tgt="$2" rel
        rel="$(at_remote "$tgt" "find '$AT_WORK' -name 'rank_tp${rk}_pp*_dp0.json' | head -1")"
        [[ -n "$rel" ]] || { warn "rank$rk work 表未找到（该秩未落表？）"; return 1; }
        rel="${rel#"$AT_WORK"/}"
        mkdir -p "$AT_TABLE/$(dirname "$rel")"
        at_remote "$tgt" "cat '$AT_WORK/$rel'" > "$AT_TABLE/$rel" || return 1
        info "  rank$rk ← ${rel}"
      }
      at_pull 0 - && at_got=$((at_got+1))
      for w in "${WORKERS[@]}"; do IFS='|' read -r rk _h _ip _ _ _ph <<<"$w"
        at_pull "$rk" "$_h" && at_got=$((at_got+1)); done
      (( at_got == 4 )) || { warn "只收到 $at_got/4 秩表——golden 未冻结（查上告警）"; }
      if (( at_got == 4 )); then
        ( cd "$AT_GOLDEN_DIR" && find table -name '*.json' | sort | xargs md5sum > table.md5 )
        AT_FIRST="$(find "$AT_TABLE" -name 'rank_tp0_pp0_dp0.json' | head -1)"
        python3 - "$AT_MANIFEST" "$AT_FIRST" "$IMAGE" <<'PYEOF'
import json, sys, os, glob, datetime
mani_p, first, image = sys.argv[1], sys.argv[2], sys.argv[3]
rel = os.path.relpath(first, os.path.dirname(mani_p))          # table/<ver>/<arch>/<key>/rank_tp0…json
fi_ver, arch, key = rel.split(os.sep)[1:4]
meta = json.load(open(first)).get("_metadata", {})
entries = {}
for f in sorted(glob.glob(os.path.join(os.path.dirname(mani_p), "table", fi_ver, arch, key, "rank_tp*.json"))):
    d = json.load(open(f))
    entries[os.path.basename(f)] = len([k for k in d if not k.startswith("_")])
json.dump({"created": datetime.datetime.now().isoformat(timespec="seconds"),
           "image": image, "fi_version": fi_ver, "arch": arch, "cache_key": key,
           "entries": entries, "metadata": meta,
           "note": "冻结纪律：image/fi_version 任一变化=重新捕获（load_configs _metadata 硬门）"},
          open(mani_p, "w"), indent=2, ensure_ascii=False)
print("  MANIFEST: fi=%s arch=%s key=%s entries=%s gpu=%s" % (fi_ver, arch, key, entries, meta.get("gpu")))
PYEOF
        info "golden 冻结完成：$AT_GOLDEN_DIR（MANIFEST.json+table.md5）"
        info "四机同步（手动执行，同 adapter 六件纪律）："
        for w in "${WORKERS[@]}"; do IFS='|' read -r _rk _h _ip _ _ _ph <<<"$w"
          info "  rsync -a $AT_GOLDEN_DIR/ $_h:$AT_GOLDEN_DIR/"; done
      fi
    fi
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
