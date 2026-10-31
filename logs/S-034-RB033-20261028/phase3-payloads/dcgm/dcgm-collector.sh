#!/bin/bash
# dcgm-collector.sh — RB033 靴窗 :9400+RDMA 抓档（MV-6/MV-7 collector 制式；
# W 换 S-034-RB033-20261028/phase3-payloads/dcgm）
# 指标面=在役五族（GPU_UTIL/SM_CLOCK/POWER_USAGE/GPU_TEMP/TOTAL_ENERGY_CONSUMPTION）
#   +观测面扩行 MEM_COPY_UTIL/PCIE_REPLAY_COUNTER（exporter 已曝；D110-③ 观测面工具非量具）
#   +RDMA data 计数器行×4 口（/sys/class/infiniband/*/ports/1/counters/port_{rcv,xmit}_data；
#     零触采样方案拍1 可选观测行）。60s 周期四机，起止由调用方控，marks.log 对齐。
# 用法：dcgm-collector.sh start|stop
set -u
W=$HOME/luz030-opt-campaign/logs/S-034-RB033-20261028/phase3-payloads/dcgm
PIDF=$W/collector.pid
mkdir -p $W
case ${1:-} in
start)
  if [ -f "$PIDF" ] && kill -0 "$(cat $PIDF)" 2>/dev/null; then echo "already running pid=$(cat $PIDF)"; exit 0; fi
  nohup bash -c '
    W=$HOME/luz030-opt-campaign/logs/S-034-RB033-20261028/phase3-payloads/dcgm
    SSH="ssh -o BatchMode=yes -o ConnectTimeout=8"
    Q="curl -s -m 6 localhost:9400/metrics | grep -E \"DCGM_FI_DEV_(TOTAL_ENERGY_CONSUMPTION|GPU_TEMP|SM_CLOCK|POWER_USAGE|GPU_UTIL|MEM_COPY_UTIL|PCIE_REPLAY_COUNTER)\"; echo --rdma--; for d in rocep1s0f0 rocep1s0f1 roceP2p1s0f0 roceP2p1s0f1; do C=/sys/class/infiniband/\$d/ports/1/counters; [ -d \$C ] && echo \"\$d rcv_data=\$(cat \$C/port_rcv_data) xmit_data=\$(cat \$C/port_xmit_data)\"; done"
    echo "dcgm-collector start $(date -u +%FT%TZ)"
    while :; do
      ts=$(date -u +%FT%TZ)
      echo "=== $ts ===" >> $W/dcgm-dgxspark01.log
      bash -c "$Q" >> $W/dcgm-dgxspark01.log 2>&1
      for h in dgxspark02 dgxspark03 dgxspark04; do
        echo "=== $ts ===" >> $W/dcgm-$h.log
        $SSH $h "$Q" >> $W/dcgm-$h.log 2>&1
      done
      sleep 60
    done
  ' > $W/collector-driver.log 2>&1 &
  echo $! > "$PIDF"
  echo "dcgm-collector started pid=$(cat $PIDF) @ $(date -u +%FT%TZ)"
  ;;
stop)
  if [ -f "$PIDF" ]; then
    PID=$(cat $PIDF); kill "$PID" 2>/dev/null && echo "stopped pid=$PID"
    rm -f "$PIDF"
  else
    echo "no pidfile"
  fi
  echo "dcgm-collector stop $(date -u +%FT%TZ)"
  ;;
*)
  echo "usage: dcgm-collector.sh start|stop"; exit 2 ;;
esac
