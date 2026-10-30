#!/usr/bin/env bash
# r3-stop.sh — 拆 r3boot 栈（head 本机 + 三 worker），供臂间轮换
# PROD-RS-20261003 名隔离：CTN_PREFIX 可被环境覆盖（生产栈=r3prod-*，
# 缺省 r3boot =测试线行为逐字不变）。
# [DF-03·0.3.4re·20261030] 收尾内建硬断言：上方 removed 行只是 docker rm 的
# 回显，前缀不匹配时会「全绿而产线纹丝不动」（升级篇-12 事故在案），自报不
# 作成功依据；成功唯一依据=文末硬断言（目标前缀容器=0 + head 端口 000），
# 任一不满足即 exit 1 并明示禁止进入沉降/点火（对齐公开仓 UPGRADE-0.3.2.md §15 第 3-4 步）。
set -u
# ── 20261030 脱敏：节点主机名改经环境变量注入，缺参拒跑 ──
NODE01_HOST="${NODE01_HOST:?缺环境变量 NODE01_HOST（<node01>），拒跑}"
NODE02_HOST="${NODE02_HOST:?缺环境变量 NODE02_HOST（<node02>），拒跑}"
NODE03_HOST="${NODE03_HOST:?缺环境变量 NODE03_HOST（<node03>），拒跑}"
NODE04_HOST="${NODE04_HOST:?缺环境变量 NODE04_HOST（<node04>），拒跑}"
CTN_PREFIX="${CTN_PREFIX:-r3boot}"
CTN="${CTN_PREFIX}-worker"
docker rm -f "${CTN_PREFIX}-head" >/dev/null 2>&1 && echo "[+] head removed" || echo "[.] head 无"
for h in "${NODE02_HOST}" "${NODE04_HOST}" "${NODE03_HOST}"; do
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$h" "docker rm -f $CTN" >/dev/null 2>&1 && echo "[+] $h worker removed" || echo "[.] $h worker 无"
done
sleep 3; echo "== 残留检查（自报面，不作成功依据）=="
docker ps --format '{{.Names}}' | grep -E "${CTN_PREFIX}-|dsv41" || echo "本机无残留"

# ── [DF-03] 停栈内建硬断言（0.3.4re 固化；无条件执行，不可跳过）──
# 手册铁律（UPGRADE-0.3.2 §15 第 4 步）：停栈必须硬断言、不许信自报。
# 断言两件：①四机目标前缀容器数=0（^CTN_PREFIX-；本机 <node01> + ssh 其余三机）；
#           ②head 端口 /health 返回 000（curl 连接失败形；8899 缺省 + 8898 L10 线，
#             API_PORT 显式另给时加测该口——boot 侧 API_PORT 缺省 8899、L10 用 8898）。
# 任一不满足 ⇒ 大声报 + exit 1，明示禁止进入沉降/点火。
# 旧 R3_STOP_VERIFY 开关自此作废：设了也被接受并被忽略，断言恒跑（兼容历史命令行）。
# curl 全带 --max-time（L6 挂起族纪律）；docker/ssh 探测不可用按红处理（fail-closed）。
esc_pfx=$(printf '%s' "$CTN_PREFIX" | sed 's/[][\.*^$(){}?+|]/\\&/g')
vfail=0
echo "== [DF-03] 停栈硬断言（目标前缀=${CTN_PREFIX}）=="
for H in "${NODE01_HOST}" "${NODE02_HOST}" "${NODE03_HOST}" "${NODE04_HOST}"; do
  if [[ "$H" == "${NODE01_HOST}" ]]; then
    if names=$(docker ps -a --format '{{.Names}}' 2>/dev/null); then
      n=$(printf '%s\n' "$names" | grep -cE "^${esc_pfx}-" || true)
    else
      n='?'   # docker 探测失败=无法断言，按红
    fi
  else
    n=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$H" "docker ps -a --format '{{.Names}}' 2>/dev/null | grep -cE '^${esc_pfx}-'; exit \${PIPESTATUS[0]:-1}" 2>/dev/null)
    if [[ $? -ne 0 ]]; then n='?'; fi   # ssh 断连或对端 docker 失败=按红
  fi
  [[ "$n" =~ ^[0-9]+$ ]] || n='?'
  echo "[DF-03] $H ${CTN_PREFIX}-* 容器 n=$n"
  [[ "$n" = 0 ]] || vfail=1
done
p_list=""
if command -v curl >/dev/null 2>&1; then
  p_list="8899 8898"
  ap="${API_PORT:-8899}"
  case " $p_list " in *" $ap "*) ;; *) p_list="$p_list $ap" ;; esac
else
  echo "[DF-03] curl 不可用——端口断言无法执行，按红处理" >&2
  vfail=1
fi
for P in $p_list; do
  pc=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${P}/health" || true); pc=${pc:-000}
  echo "[DF-03] 127.0.0.1:${P}/health http_code=${pc}（期望 000=连接失败）"
  [[ "$pc" == 000 ]] || vfail=1
done
if [[ "$vfail" = 1 ]]; then
  echo "[DF-03][RED] 停栈硬断言失败（目标前缀容器≠0 或 head 端口≠000 或探测不可用）——禁止进入沉降/点火；请先查明残留/前缀错误并处置后重跑本脚本" >&2
  exit 1
fi
echo "[DF-03] 停栈硬断言 PASS（四机 ${CTN_PREFIX}-* 容器=0 + head 端口 000）——可按手册进入沉降计时（≥600s）后再点火"
exit 0
