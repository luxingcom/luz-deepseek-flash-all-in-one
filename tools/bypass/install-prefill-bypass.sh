#!/bin/bash
# install-prefill-bypass.sh — 把 prefill_bypass 适配件装入 adapter 面（在目标机本机执行）
#
# 这是 BYPASS 采用面（BL-BYP1 口径）的现役装钩器，完成两件事：
#   1) adapter 的 sitecustomize.py scheduler 分支挂 env 门控钩（DSV41_PREFILL_BYPASS
#      有值才生效；禁用路径零突变）——前态 45ca6e3e → 后态 dd69c59a（确定性插入，
#      后态 md5 硬断言）；
#   2) prefill_bypass.py 正典件（c4875258）投递入 adapter 目录，文件数 98→99。
# 引擎文件（overlay / sglang 源树）零改；备份置 adapter 目录外；已有钩=幂等通过。
#
# 历史存档提示：本目录的 stage-one-host-bypb.sh 是 2026-10-28 BYPASS-B 窗的一次性
# staging 原件（含脱敏占位符，不可直接运行），现役操作一律用本件。
#
# 用法：
#   bash install-prefill-bypass.sh [PB_SRC]
# 环境变量（可覆盖缺省）：
#   ADAPTER_DIR   缺省 $HOME/migrate-assets/dsv41/adapter
#   OVERLAY_DIR   可选：仅装后回显参考；未设则跳过（engine 树本件零改）
set -euo pipefail

AD="${ADAPTER_DIR:-$HOME/migrate-assets/dsv41/adapter}"
SC="$AD/sitecustomize.py"
BAK="${AD%/*}/sitecustomize.py.bak-pre-bypb"
PB_SRC="${1:-$(cd "$(dirname "$0")" && pwd)/prefill_bypass.py}"

SC_PRE="45ca6e3e1ca0eb34c3ff21abb0023571"   # 未挂钩前态（0.3.2 装配面 sitecustomize）
SC_POST="dd69c59a1098b735dd20e8aec1baaee9"  # 挂钩后态（现役 adapter 面装载缝）
PB_MD5="c487525873cc2c0e09436414efb22115"   # prefill_bypass.py 正典件

m(){ md5sum "$1" | cut -d' ' -f1; }

echo "== $(hostname -s) prefill_bypass 安装 START $(date -u +%FT%TZ) =="

# ── 0) 前态三查：装载缝锚 / 幂等面 / 防重入 ──
cur="$(m "$SC" 2>/dev/null || true)"
case "$cur" in
  "$SC_POST")
    # 已是挂钩后态：幂等通过，只核适配件在位
    [ "$(m "$AD/prefill_bypass.py" 2>/dev/null || true)" = "$PB_MD5" ] \
      || { echo "PANIC: 钩已在（sitecustomize=dd69c59a）但 prefill_bypass.py 缺失或 md5 失配"; exit 9; }
    echo "OK（幂等）: sitecustomize 已为挂钩后态 dd69c59a 且 prefill_bypass.py=c4875258 在位，无需操作"
    exit 0
    ;;
  "$SC_PRE")
    : # 合法前态，继续
    ;;
  "")
    echo "PANIC: 找不到 $SC（ADAPTER_DIR 设对了吗？）"; exit 9
    ;;
  *)
    echo "PANIC: sitecustomize 写前 $(m "$SC") ≠ 前态 $SC_PRE 也非后态 $SC_POST=面漂移，停手呈报"; exit 9
    ;;
esac
[ -f "$AD/prefill_bypass.py" ] && { echo "PANIC: adapter 内已有 prefill_bypass.py（防重入——前态不应有此件）"; exit 9; }
[ -f "$BAK" ] && { echo "PANIC: 备份已存在 $BAK（防重入）"; exit 9; }
[ "$(m "$PB_SRC")" = "$PB_MD5" ] || { echo "PANIC: PB_SRC 件 md5 $(m "$PB_SRC") ≠ 正典 $PB_MD5（本仓 tools/bypass/prefill_bypass.py 即正典件）"; exit 9; }

# ── 1) 备份（adapter 目录外）──
cp -p "$SC" "$BAK"
echo "backup: $BAK 落位 ($(m "$BAK"))"

# ── 2) sitecustomize scheduler 分支挂 env 门控钩（python 精确插入；锚行 count==1 断言）──
python3 - "$SC" <<'PYEOF'
import sys, hashlib
p = sys.argv[1]
src = open(p).read()
anchor = ("            from idle_release import install as install_idle_release\n"
          "            install_idle_release(module)\n")
assert src.count(anchor) == 1, 'scheduler-branch anchor count != 1'
assert 'prefill_bypass' not in src, 'hook already present (idempotent guard)'
hook = (
"            # BYPASS-B (MV-14, T34-06): knapcio prefill_bypass staged mount (b9ea6dd\n"
"            # lineage, EXPECTED re-pinned to 0.3.4 overlay live face). Env-gated on\n"
"            # DSV41_PREFILL_BYPASS; the disabled path mutates nothing.\n"
"            if os.environ.get('DSV41_PREFILL_BYPASS', '').strip():\n"
"                from prefill_bypass import install as install_prefill_bypass\n"
"                install_prefill_bypass(module)\n")
out = src.replace(anchor, anchor + hook)
open(p, 'w').write(out)
compile(out, p, 'exec')
print('sitecustomize hook inserted; compile PASS; new md5=%s' % hashlib.md5(out.encode()).hexdigest())
PYEOF

# ── 3) prefill_bypass.py 投递入 adapter（c4875258 硬断言）──
cp "$PB_SRC" "$AD/prefill_bypass.py"
[ "$(m "$AD/prefill_bypass.py")" = "$PB_MD5" ] || { echo "PANIC: 投递后 md5 $(m "$AD/prefill_bypass.py") ≠ $PB_MD5"; exit 9; }
python3 -m py_compile "$AD/prefill_bypass.py" && rm -rf "$AD/__pycache__"

# ── 4) 后核：装载缝后态 md5 + adapter 面件数与指纹 + 引擎文件零改回显 ──
[ "$(m "$SC")" = "$SC_POST" ] || { echo "PANIC: 挂钩后 sitecustomize=$(m "$SC") ≠ 期望后态 $SC_POST（插入非确定性，停手呈报）"; exit 9; }
n=$(find "$AD" -type f ! -path '*__pycache__*' | wc -l)
fp=$(cd "$AD" && find . -type f ! -path '*__pycache__*' | LC_ALL=C sort | xargs -r md5sum 2>/dev/null | LC_ALL=C sort | md5sum | cut -c1-8)
echo "$(hostname -s): sitecustomize=$(m "$SC" | cut -c1-8) prefill_bypass=$(m "$AD/prefill_bypass.py" | cut -c1-8) adapter=${fp}/${n} 件（件数=磁盘实数仅回显非断言；锁档在役全文件口径期望 99 件，公开仓供给面=91+1 装钩件，两者差=包外宿主件——面验收以清单 md5sum -c 为准）"
if [ -n "${OVERLAY_DIR:-}" ] && [ -f "${OVERLAY_DIR:-}/scheduler.py" ]; then
  echo "overlay 回显: scheduler=$(m "$OVERLAY_DIR/scheduler.py" | cut -c1-8) schedule_policy=$(m "$OVERLAY_DIR/schedule_policy.py" | cut -c1-8)（仅供参考，engine 树本件零改）"
fi
echo "== $(hostname -s) prefill_bypass 安装 DONE（点火时设 DSV41_PREFILL_BYPASS=2048 武装；核验用本目录 bypass-armed-gate.sh）=="
