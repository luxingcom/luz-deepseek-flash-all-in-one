#!/bin/bash
# capture-boot-evidence.sh — 正典 boot 核对面采集件（横幅 grep 取面缺陷族一次性修复件）
#
# 法源：D109-⑧ 工队列（缺陷族第 5 例止损）；D107-①/D109-④ 裁定先例（取面缺陷假阳性=零载荷中止+裁量续窗）。
# 修复面（对 staged prfrb 形两处）：
#   1) 横幅 grep 模式 `Exact nvme Engram .* (layer=1|14) `（双空格永零配）→ `Exact nvme Engram layer=(1|14) `
#      （实测形：`[2026-10-27 15:37:46 TP0] Exact nvme Engram layer=1 rank=0 …`——对 MV-7 fix2 存档横幅 8/8 匹配直证）
#   2) 末行清点 `grep -c` 零配 exit 1 会带垮脚本退出码 → `|| true` + 判读提示行。
# 性质：观测面采集工具（非量具——E10-10/U5 冻结不涉，P-1 同族论证 D104-④）。
# 用法：bash tools/capture-boot-evidence.sh <输出目录>   （缺省=当前目录）
# 期望：横幅 8/8（4 秩×层 1/14 七字段）；池指纹 full=9600000/MRR=16/ctx=600000/cps=4096；
#       [arm]+env 60 行（BYPASS 采用后 60 键=D121）；[gate]=0；health 200；镜像 .Config.Image=0.3.4-x6bake-20261026/.Image=80e4c957…；
#       overlay 七件活体 md5 同 R1 台账；[12] BYPASS armed 断言 2/机合计 8、拒 arm 0（D121 五步固化③）。
set -u
W="${1:-.}"
mkdir -p "$W"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8"
echo "[boot-evidence] 轮询 /health 首 200 start $(date -u +%FT%TZ)"
FIRST200=""
for i in $(seq 1 720); do
  CODE=$(curl -s -m 4 -o /dev/null -w "%{http_code}" http://127.0.0.1:8899/health 2>/dev/null || true)
  if [ "$CODE" = "200" ]; then FIRST200=$(date -u +%s); break; fi
  sleep 10
done
if [ -z "$FIRST200" ]; then echo "[boot-evidence] REFUSE: 120min 内 health 未达 200"; exit 21; fi
echo "$FIRST200" > "$W/health-first200.epoch"
echo "[boot-evidence] health 首 200 @ epoch=$FIRST200（$(date -u -d @$FIRST200 +%FT%TZ)）"
OUT=$W/boot-evidence.log
{
echo "== boot evidence @ $(date -u +%FT%TZ) =="
echo "-- [1] [arm] +env 行数（期望 60=产 env 形 D121 采用后；keepalive 键不在）--"
docker logs r3prod-head 2>&1 | grep -c '^\[arm\] +env ' || true
docker logs r3prod-head 2>&1 | grep '^\[arm\] +env ' | grep -E 'ENGRAM_KEEPALIVE|ENGRAM_CACHE_GIB|PAGE_MAP' || echo "(keepalive 键零现=净面 ✓；PAGE_MAP 键零现=缺省关 ✓)"
echo "-- [2] gate 段零激活核（期望 0）--"
docker logs r3prod-head 2>&1 | grep -c '^\[gate\]' || true
echo "-- [3] L1-L7 池账行（head）--"
docker logs r3prod-head 2>&1 | grep -E "DSV4 pool sizes|max_total_num_tokens" | head -6
echo "-- [4] host-share 守卫告警计数（期望 0；head）--"
docker logs r3prod-head 2>&1 | grep -ciE "host.?share" || true
echo "-- [5] engram 横幅 8 行（4 秩×层1/14；七字段）--"
echo "-- head (rank0) --"
docker logs r3prod-head 2>&1 | grep -E "Exact nvme Engram layer=(1|14) " | head -4
for h in __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__; do
  echo "-- $h --"
  $SSH $h 'docker logs r3prod-worker 2>&1' | grep -E "Exact nvme Engram layer=(1|14) " | head -4
  $SSH $h 'docker logs r3prod-worker 2>&1 | grep -cE "^Traceback|CUDA (error|assert)|illegal memory"' | sed 's/^/CUDA\/Traceback count=/'
done
echo "-- [6] /server_info 活体 --"
curl -s -m 8 http://127.0.0.1:8899/server_info | head -c 600; echo
echo "-- [7] /health --"
curl -s -m 4 -o /dev/null -w "health=%{http_code}\n" http://127.0.0.1:8899/health
echo "-- [8] head CUDA/Traceback --"
docker logs r3prod-head 2>&1 | grep -cE "^Traceback|CUDA (error|assert)|illegal memory" || true
echo "-- [9] 镜像身份核（期望 .Config.Image=0.3.4-x6bake-20261026 / .Image=80e4c957…）--"
docker inspect r3prod-head --format '{{.Config.Image}} {{.Image}}' 2>/dev/null
for h in __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__; do $SSH $h 'docker inspect r3prod-worker --format "{{.Config.Image}} {{.Image}}"' 2>/dev/null; done
echo "-- [10] overlay 面容器内活体 md5（期望 73c80259/5b5ced03/982a0ad0/c0dfe59a）--"
docker exec r3prod-head md5sum /sgl-workspace/sglang/python/sglang/srt/layers/attention/deepseek_v4_backend.py /sgl-workspace/sglang/python/sglang/srt/models/deepseek_v4.py /sgl-workspace/sglang/python/sglang/kernels/ops/layernorm/mhc.py /sgl-workspace/sglang/python/sglang/srt/mem_cache/page_map_export.py 2>&1
echo "-- [11] X6 吸收面容器内 md5（期望 f8d15a4b/a89046ef/c356e4e6）--"
docker exec r3prod-head md5sum /sgl-workspace/sglang/python/sglang/srt/managers/schedule_batch.py 2>/dev/null || true
docker exec r3prod-head md5sum /sgl-workspace/sglang/python/sglang/kernels/ops/attention/dsv4/request_window_copy.py 2>&1
docker exec r3prod-head md5sum /sgl-workspace/sglang/python/sglang/srt/model_executor/model_runner_components/ngram_embedding_manager.py 2>&1
echo "-- [12] BYPASS 采用面（D121 五步固化③：armed 断言行期望 2/机合计 8；拒 arm 行期望 0；此处打全行入档供尾段清点）--"
echo "-- head bypb --"
docker logs r3prod-head 2>&1 | grep "DSV41_PREFILL_BYPASS armed:" || true
docker logs r3prod-head 2>&1 | grep -i "refusing to arm" || true
for h in __PROD_HOST_02__ __PROD_HOST_03__ __PROD_HOST_04__; do
  echo "-- $h bypb --"
  $SSH $h 'docker logs r3prod-worker 2>&1' | grep "DSV41_PREFILL_BYPASS armed:" || true
  $SSH $h 'docker logs r3prod-worker 2>&1' | grep -i "refusing to arm" || true
done
} > "$OUT" 2>&1
cat "$OUT"
echo "-- 横幅 8/8 清点 --"
N=$(grep -cE "Exact nvme Engram layer=(1|14) " "$OUT" || true)
echo "banner_count=${N:-0}（期望 8；<8=查 $OUT [5] 段，勿按零配即判 RED——本件模式已对实测横幅形校准）"
echo "-- BYPASS ARMED 清点（[12] 段：四机 armed 合计期望 8；refusing 合计期望 0）--"
A=$(grep -c "DSV41_PREFILL_BYPASS armed:" "$OUT" || true); R=$(grep -ci "refusing to arm" "$OUT" || true)
echo "armed_count=${A:-0} refusing_count=${R:-0}"
