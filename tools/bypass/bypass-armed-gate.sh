#!/bin/bash
# bypass-armed-gate.sh — BYPASS-B（MV-14）bypass 挂载生效断言（boot 门项；T34-06 §三）
# 期望（四机）：docker logs 各 ≥1 行
#   "DSV41_PREFILL_BYPASS armed: at most 2048 total fresh tokens and 32 candidates"
#   （armed 行=sitecustomize 钩已触发+9 哈希全中+四锚 count==1+exec 重编译毕——适配生效直证）；
#   "refusing to arm" 计数=0（拒绝武装=适配未生效）。
# 未过=停窗条款（零载荷拆栈带诊断复呈，misfire 口径 D110-①b 先例）。
set -u
W=__USER_HOME__/__REPO_ROOT__/logs/S-034-BYPASS-B-20261028
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8"
OUT=$W/phase2-boot/bypass-armed-gate.log
{
echo "== BYPASS-B（MV-14）bypass 挂载生效断言 @ $(date -u +%FT%TZ) =="
echo "-- r3prod-head (01) --"
echo "armed(2048/32) 行计数（期望 ≥1）: $(docker logs r3prod-head 2>&1 | grep -c 'DSV41_PREFILL_BYPASS armed: at most 2048 total fresh tokens and 32 candidates' || true)"
echo "refusing-to-arm 行计数（期望 0）: $(docker logs r3prod-head 2>&1 | grep -c 'refusing to arm' || true)"
docker logs r3prod-head 2>&1 | grep 'DSV41_PREFILL_BYPASS' | head -2
for h in __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__; do
  echo "-- $h worker --"
  echo "armed(2048/32) 行计数（期望 ≥1）: $($SSH $h 'docker logs r3prod-worker 2>&1' | grep -c 'DSV41_PREFILL_BYPASS armed: at most 2048 total fresh tokens and 32 candidates' || true)"
  echo "refusing-to-arm 行计数（期望 0）: $($SSH $h 'docker logs r3prod-worker 2>&1' | grep -c 'refusing to arm' || true)"
  $SSH $h 'docker logs r3prod-worker 2>&1' | grep 'DSV41_PREFILL_BYPASS' | head -2
done
} 2>&1 | tee "$OUT"
ARMED=$(grep -c "行计数（期望 ≥1）: [1-9]" "$OUT" || true)
REFUSE=$(grep -c "行计数（期望 0）: [1-9]" "$OUT" || true)
echo "== 判读：armed 段命中=$ARMED（期望 4）/refusing 段命中=$REFUSE（期望 0）==" | tee -a "$OUT"
[ "$ARMED" = "4" ] && [ "$REFUSE" = "0" ] && echo "bypass ARMED 断言 PASS（四机武装生效）" | tee -a "$OUT" || { echo "bypass ARMED 断言 FAIL=停窗条款（零载荷拆栈带诊断复呈）" | tee -a "$OUT"; exit 9; }
exit 0
