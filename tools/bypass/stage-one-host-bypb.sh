#!/bin/bash
# stage-one-host-bypb.sh — BYPASS-B（MV-14）bypass staged 挂载单机件（在目标机本机执行）
# 面=固化面+prefill_bypass 挂载（T34-06 包）：adapter 投递 prefill_bypass.py（knapcio b9ea6dd
# 血统 173 行件，我树重钉 9 哈希+四锚已验 count==1）+ sitecustomize.py scheduler 分支挂 env 门控钩
# （禁用路径零突变）；备份置 adapter 目录外（__ASSETS_ROOT__/dsv41/sitecustomize.py.bak-pre-bypb-20261028）
# ——adapter 面文件数 98→99 如实计；引擎文件（overlay/sglang-main-src）零改。
# env 键注入走 ARM_ENV_FILE 面（点火时 CBX1A-CERTM-spec1-bypB.env 60 键，本件不建）。
# 用法：bash stage-one-host-bypb.sh [PB_SRC]——01 缺省=campaign staging 件；worker 经 scp 落
#       /tmp/prefill_bypass.bypb.py 后以该路径传入。
set -euo pipefail
AD="__ASSETS_ROOT__/dsv41/adapter"
SC="$AD/sitecustomize.py"
BAK="__ASSETS_ROOT__/dsv41/sitecustomize.py.bak-pre-bypb-20261028"
PB_SRC="${1:-__USER_HOME__/__REPO_ROOT__/logs/S-034-BYPASS-B-20261028/staging/prefill_bypass.py}"
m(){ md5sum "$1" | cut -d' ' -f1; }

echo "== $(hostname -s) BYPB stage START $(date -u +%FT%TZ) =="
# ── 0) 写前锚核：sitecustomize=45ca6e3e（四机同值已预检）+ 备份在/不在防重入 ──
[ "$(m $SC)" = "45ca6e3e1ca0eb34c3ff21abb0023571" ] || { echo "PANIC: sitecustomize 写前 $(m $SC) ≠ 45ca6e3e1ca0eb34c3ff21abb0023571"; exit 9; }
[ -f "$AD/prefill_bypass.py" ] && { echo "PANIC: adapter 内已有 prefill_bypass.py（防重入）"; exit 9; }
[ -f "$BAK" ] && { echo "PANIC: 备份已存在（防重入）"; exit 9; }

# ── 1) 备份（adapter 目录外）──
cp -p "$SC" "$BAK"
echo "backup: $BAK 落位 ($(m $BAK))"

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

# ── 3) prefill_bypass.py 投递入 adapter（c4875258）──
cp "$PB_SRC" "$AD/prefill_bypass.py"
[ "$(m $AD/prefill_bypass.py)" = "c487525873cc2c0e09436414efb22115" ] || { echo "PANIC: 投递后 md5 $(m $AD/prefill_bypass.py) ≠ c4875258"; exit 9; }
python3 -m py_compile "$AD/prefill_bypass.py" && rm -rf "$AD/__pycache__"

# ── 4) 后核：sitecustomize 新 md5 + adapter 面（99 件）+ 引擎文件零改 ──
echo "$(hostname -s): sitecustomize=$(m $SC|cut -c1-8) prefill_bypass=$(m $AD/prefill_bypass.py|cut -c1-8) adapter=$(cd $AD && find . -type f ! -path '*__pycache__*' | LC_ALL=C sort | xargs -r md5sum 2>/dev/null | LC_ALL=C sort | md5sum | cut -c1-8)/$(cd $AD && find . -type f ! -path '*__pycache__*' | wc -l) ov_sched=$(m __ASSETS_ROOT__/v4vl/sglang-overlay.o12c1-prod/scheduler.py|cut -c1-8) ov_policy=$(m __ASSETS_ROOT__/v4vl/sglang-overlay.o12c1-prod/schedule_policy.py|cut -c1-8)"
echo "== $(hostname -s) BYPB stage DONE =="
