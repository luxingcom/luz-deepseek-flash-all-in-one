# V4.1 死锁：规避指引与现场取证包（0.3.2 前置随包）— 2026-10-18

> 适用：DeepSeek-V4.1-Flash TP4 生产栈（sglang main-79cafec0 基线族）。
> 事实基线：2026-10-16 站点甲 43h 长稳后调度死锁（四机同点 `v41_indexer/scoring.py:164
> get_deep_gemm_prefill_data`，GPU 已入队 ALLREDUCE 零启动，900s NCCL watchdog 四机同崩）。
> 根因定性=步级隐含宿主同步累积（520d6d0 上游修复方向，0.3.2 修复线承载）。

## 一、规避指引（修复版本到位前）

1. **复现即重启**：既有事实口径——同参面重启后未复现（站点甲 1h+ 正常流量；多站点一致）。
   生产上死锁窗口（watchdog 1800s 崩溃自退出或人工介入）内直接整栈重启即可恢复服务。
2. **升级前窗口建议**：
   - 死锁历史样本=长稳 ≥40h 后首现；若栈龄 >36h 且有维护窗，优先安排滚动重启（零流量窗内
     整栈重启，非单机），可显著降低窗口内撞锁概率。
   - 升级到 0.3.2 修复版（r032b，含上游 520d6d0 最小修复集）前**不必**先重启——修复面在
     引擎步级同步消除，与栈龄无关。
3. **不要做的事**：单机重启（TP4 全环锁死，单机重起会卡 NCCL 握手）；watchdog 期内反复
   探测（dump 阶段 GIL 已失获取能力，额外请求只加噪声）。

## 二、现场取证三件套（py-spy 武装）

死锁疑似（`#running-req` 冻结 + GPU 利用率归零 + 无新日志）时，**在崩溃/重启前**按序采集：

### 2.1 py-spy dump（秒级定帧——第一优先）

```bash
# scheduler 主进程 pid（容器内 1 号或 docker top 找 python 主进程）
docker exec <container> py-spy dump --pid 1
# 宿主直采（容器无 py-spy 时）：pid=$(pgrep -f 'sglang::scheduler' | head -1)
py-spy dump --pid $pid
```

**判别读法**：栈顶落在 `scoring.py:164 get_deep_gemm_prefill_data`（或同族
`get_deep_gemm_decode_data`）＝**本死锁形**（宿主同步等待）；栈顶落在 `ncclCommInit*`/
`ncclLaunchKernel`/allreduce 入口＝**通信初始化/链路面**（另案）。四机各采一份对齐时间戳。

### 2.2 内核态栈（区分「链路停滞」vs「从未开工」）

```bash
for t in /proc/<pid>/task/*/stack; do echo "== $t"; sudo cat $t 2>/dev/null | head -8; done
nvidia-smi --query-compute-apps=pid,used_memory --format=csv   # 进程在卡面+显存持有
# 环网差分（有流量计数=链路曾开工后停滞；全零=从未开工）：
ethtool -S rocep1s0f0 | grep -E 'rx_|tx_' | head; ethtool -S roceP2p1s1f0 | grep -E 'rx_|tx_' | head
```

判别：NCCL 侧 `last started work: -1` + ethtool 计数冻结 = GPU 队列从未启动（本死锁形：
调度线程先卡宿主同步，集合通信无人发起）。

### 2.3 NCCL INFO 低开销窗（需要时）

```bash
# 仅初始化子系统（开销极低，可常开于怀疑窗；ALL 会增大日志量，短窗采集用）
NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=INIT,ALL
# 判读：NCCL version 行（2.30.7 族）；comm/channel 初始化是否四机齐
```

### 2.4 record/top（持续观测，非首采优先级）

```bash
py-spy record -o /tmp/prof.svg --pid $pid --duration 60   # 60s 火焰图
py-spy top --pid $pid                                     # 实时热点
```

## 三、修复线状态（截至本卡）

- 上游修复=sglang `520d6d0`（#41659，含 fc2795b）：prefill/decode 索引器数据构造改整批
  host-lengths 构形+async_h2d，消除步级隐含宿主同步（死锁根因面）。
- 0.3.2 修复镜像 `dsv41-sglang-optimized:0.3.2-r032`（digest `sha256:bd281e6f…631f5`）：
  最小修复集回移植（15 件 +1347/−313）。**当前状态：验收中（G1 单元门拦出依赖闭包漏项，
  r032b 重烘在途）——生产切换以 0.3.2 release notes 验收读数全绿为准**，本卡先随包规避面。
- 切换/回退配方与验收电池：随 0.3.2 release notes 一并发布（boot 单行镜像切指+adapter 同批
  原子律+沉降 ≥1800s 靴序）。

——LuZ 战役 S-FIX-W0 窗编制（法源=INCIDENT-20261016-EXT-V41-DEADLOCK 全档）。
