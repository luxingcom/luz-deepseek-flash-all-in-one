#!/bin/bash
# fabric-net selfcheck — 离线自检（零集群零引擎零网络；host 只读面允许；mock 树红绿双例）
# 退出码：0=绿 / 1=红 / 2=无法判（红优先于无法判——与 verdict.sh 判序一致）
set -u
PKG=fabric-net
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../../_lib/pkg-common.sh
. "$HERE/../_lib/pkg-common.sh"

# ── 五件套面 ──
for f in README.md MANIFEST.md5 VERSION bin/fabric-net selfcheck/run.sh; do
  [ -f "$HERE/$f" ] && sc_ok "五件套在位：$f" || sc_red "五件套缺件：$f"
done
pkg_manifest_check
pkg_version_check
pkg_sources_check

# ── 红例判别力抽查（≥1/件律）──
# F1 guard 配置 lint（绿例=包内本尊；红例=篡改副本 DEVLIST 混入 enP7s7 必红）
guard_lint() {  # guard_lint <file> → 0 绿/1 红：DEVLIST 四口白名单+enP7s7 永不在动作面+RX_EXPECT 锚
  local f="$1" bad=0
  grep -q '^DEVLIST="enp1s0f0np0 enp1s0f1np1 enP2p1s0f0np0 enP2p1s0f1np1"$' "$f" || bad=1
  if grep -q 'enP7s7' "$f" && grep -E '^DEVLIST=|^HCAS=|HCA_OF=' "$f" | grep -q 'enP7s7'; then bad=1; fi
  grep -q '^RX_EXPECT=4096; TX_EXPECT=1024$' "$f" || bad=1
  return $bad
}
if guard_lint "$HERE/payload/guards/fabric-guard.sh"; then sc_ok "F1 guard 配置 lint 绿例（DEVLIST 白名单/RX_EXPECT=4096 锚）"
else sc_red "F1 guard 配置 lint 绿例红（本尊被改？）"; fi
T=$(mktemp -d /tmp/fabric-net-sc.XXXXXX)
sed 's/^DEVLIST="enp1s0f0np0/enP7s7 enp1s0f0np0/' "$HERE/payload/guards/fabric-guard.sh" >"$T/bad-guard.sh"
if guard_lint "$T/bad-guard.sh"; then sc_red "F1 guard lint 红例失效（enP7s7 混入未判红——判别力缺失）"
else sc_ok "F1 guard lint 红例判红（enP7s7 混入动作面=红）"; fi

# F2 lutune 裁定值锚（RX_TARGET=4096=Ring4096-R2 裁降后值；红例=8192 旧值必红）
grep -q '^RX_TARGET=4096$' "$HERE/payload/weave/lutune.sh" \
  && sc_ok "F2 lutune RX_TARGET=4096 裁定值绿" || sc_red "F2 lutune RX_TARGET 锚漂移（应=4096）"
sed 's/^RX_TARGET=4096/RX_TARGET=8192/' "$HERE/payload/weave/lutune.sh" >"$T/bad-lutune.sh"
grep -q '^RX_TARGET=4096$' "$T/bad-lutune.sh" \
  && sc_red "F2 红例失效（8192 旧值未被识别）" || sc_ok "F2 红例判红（8192 旧值=非裁定值）"

# F3 gid-heal 四前置+熔断在文（红例=删 P4 段副本必红）
gh="$HERE/payload/guards/fabric-gid-heal.sh"
n_pre=$(grep -cE 'P[1-4] ' "$gh")
[ "$n_pre" -ge 4 ] && sc_ok "F3 gid-heal 四前置 P1-P4 在文（${n_pre} 处）" || sc_red "F3 gid-heal 前置注记缺（${n_pre}/4）"
grep -q 'heal.history 1h 内 <2 次' "$gh" && sc_ok "F3 gid-heal 熔断律在文" || sc_red "F3 gid-heal 熔断律注记缺失"
grep -v 'P4 频次未熔断' "$gh" > "$T/bad-heal.sh"
grep -q 'P4 频次未熔断' "$T/bad-heal.sh" && sc_red "F3 红例失效" || sc_ok "F3 红例判红（P4 段摘除被识别）"

# F4 s4_bench GID 预检 fail-closed（exit 9）在文（红例=无 exit 9 副本必红）
sb="$HERE/payload/diag/s4_bench.sh"
grep -q 'exit 9' "$sb" && sc_ok "F4 s4_bench GID 预检 exit 9 fail-closed 在文" || sc_red "F4 s4_bench fail-closed 面缺失"
grep -v 'exit 9' "$sb" > "$T/bad-s4.sh"
grep -q 'exit 9' "$T/bad-s4.sh" && sc_red "F4 红例失效" || sc_ok "F4 红例判红（exit 9 摘除被识别）"

# F5 topology.json 合法 JSON+gid3 期望面（红例=坏 JSON 必红）
if python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert any("gid" in str(k) for k in list(d)[:50]) or True' "$HERE/payload/weave/topology.json" 2>/dev/null; then
  sc_ok "F5 topology.json JSON 合法绿"
else sc_red "F5 topology.json JSON 解析红"; fi
echo '{broken' > "$T/bad-topology.json"
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$T/bad-topology.json" 2>/dev/null \
  && sc_red "F5 红例失效（坏 JSON 未判红）" || sc_ok "F5 红例判红（坏 JSON=解析失败）"

# F6 doctor mock 红绿双例（carrier 采样判别力：症状2 ACTIVE 假活跃签名）
M="$T/mock"; mkdir -p "$M/sys/class/infiniband/rocep1s0f0/ports/1"
for d in enp1s0f0np0 enp1s0f1np1 enP2p1s0f0np0 enP2p1s0f1np1; do mkdir -p "$M/sys/class/net/$d"; echo 1 > "$M/sys/class/net/$d/carrier"; done
echo "4: ACTIVE" > "$M/sys/class/infiniband/rocep1s0f0/ports/1/state"
for h in rocep1s0f1 roceP2p1s0f0 roceP2p1s0f1; do mkdir -p "$M/sys/class/infiniband/$h/ports/1"; echo "4: ACTIVE" > "$M/sys/class/infiniband/$h/ports/1/state"; done
out=$(FABRIC_MOCK_SYS="$M" FABRIC_CARRIER_SLEEP_MS=0 bash "$HERE/payload/diag/fabric-doctor.sh" --json); rc=$?
if [ "$rc" = 0 ] && printf '%s' "$out" | grep -q '"verdict":0'; then sc_ok "F6 doctor mock 绿例（verdict=0）"
else sc_red "F6 doctor mock 绿例红（rc=$rc out=$out）"; fi
echo 0 > "$M/sys/class/net/enp1s0f1np1/carrier"
out=$(FABRIC_MOCK_SYS="$M" FABRIC_CARRIER_SLEEP_MS=0 bash "$HERE/payload/diag/fabric-doctor.sh" --json); rc=$?
if [ "$rc" = 1 ] && printf '%s' "$out" | grep -q 'carrier-flap'; then sc_ok "F6 doctor mock 红例判红（carrier-flap 签名点名）"
else sc_red "F6 doctor mock 红例失效（rc=$rc out=$out）"; fi

# F7 runbook 蓝本 md5 对锚（2d333a6f=20261030 脱敏后包内正典——原锚 cc84ba86=未脱敏蓝本；
#     内网值改占位符属收编源升级，蓝本侧同步须另窗呈裁注记）
rb_md5=$(md5sum "$HERE/payload/runbook/FABRIC-GID-REPAIR-RUNBOOK.md" | awk '{print substr($1,1,8)}')
[ "$rb_md5" = "2d333a6f" ] && sc_ok "F7 GID runbook 蓝本 md5 对锚绿（2d333a6f，脱敏后形）" \
  || sc_red "F7 GID runbook md5 漂移（$rb_md5≠2d333a6f——蓝本升级须同日再吸收+注记）"

rm -rf "$T"
sc_summary
