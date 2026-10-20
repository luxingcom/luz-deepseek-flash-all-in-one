# 启动参面（0.3.2 CBX1A 现役形）

## 1. 文件与锚

| 项 | 值 |
|---|---|
| boot 链 | `deploy/bin/r3-boot-arm.sh`（产线 md5 **20f22bc6**；公开件 9ac6e113=多快照头+掩码） |
| env | `env/CBX1A-CERTM-spec1.env`（56 键，md5 **0729e18d**） |
| 容器前缀 | `r3prod`（head=`r3prod-head`，worker=`r3prod-worker`） |
| API | 8899（head），管理/代理 8001 |
| 池 | `--max-total-tokens 9600000`；`--context-length 600000`；`--max-running-requests 16`；`--chunked-prefill-size 4096` |

## 2. 启动命令

```bash
ARM_TAG=r3prod \
ARM_ENV_FILE=$HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env \
SPEC=1 \
SPEC_EXTRA_ARGS="--prefill-decode-interval 16 --max-queued-requests 32 --min-free-slots-delay 1 --enable-decoder-swa-bounded-replay --reasoning-parser deepseek-v41 --swa-prefix-tails 256" \
  bash <repo>/tools/boot-with-slotlock.sh bash $HOME/migrate-assets/bin/r3-boot-arm.sh
```

`SPEC=1` 时 boot 额外追加 `--speculative-algorithm DSPARK`。`r3-boot-arm.sh` 的
`SERVER_ARGS` 固定面另含 A8/A9/第九参：

```
--tool-call-parser deepseekv41
--enable-cache-report
--sleep-on-idle
```

其余固定面：`--moe-runner-backend flashinfer_mxfp4`、
`--json-model-override-args '{"candidate_topk_blocks": 2048}'`、
`--fp8-gemm-backend flashinfer_cutlass`、`--dist-timeout 900`、`--watchdog-timeout 1800`、
`--mem-fraction-static 0.90`、`--enable-metrics`。

**易错点**：`tool-call-parser` 必须写 **`deepseekv41`（连写）**；`reasoning-parser`
必须写 **`deepseek-v41`（连字符）**。写反不报错但功能静默缺失——用
`tools/serve_flags_gate.sh` 从运行进程 argv 直证。

## 3. 四机 WORKERS（boot 内嵌）

| rank | 机 | 管理 IP | 模型源 | engram | HCA 对 |
|---|---|---|---|---|---|
| 0 | dgxspark01 | 192.168.0.201（head） | `/data/models/DeepSeek-V4.1-Flash-1017` | `~/dsv41-engram-1017` | — |
| 1 | dgxspark02 | 192.168.0.202 | `/data/models/DeepSeek-V4.1-Flash-1017` | 同上 | `0=rocep1s0f1,roceP2p1s0f1;2=rocep1s0f0,roceP2p1s0f0` |
| 2 | dgxspark04 | 192.168.0.204 | `/data/models/dsv41-net` | 同上 | `1=rocep1s0f0,roceP2p1s0f0;3=rocep1s0f1,roceP2p1s0f1` |
| 3 | dgxspark03 | 192.168.0.203 | `/data/models/dsv41-net` | 同上 | `0=rocep1s0f0,roceP2p1s0f0;2=rocep1s0f1,roceP2p1s0f1` |

`PEER_HCA_HEAD` 仍有定义但已退役（不再注入）；NCCL 用双 rail 部署对
`rocep1s0f0,roceP2p1s0f1` + `NCCL_IB_TC=106`。

## 4. 起机门与四查

1. 沉降：前栈拆靴→点火 ≥600s（boot 链的 settle gate）。
2. 起机：容器 4 个；`curl -s localhost:8899/health`=200；8001 健康=200。
3. 四查：`printenv` 四机与 env 逐字；横幅 `banner complete: 29 gates`；池
   `max_total_num_tokens=9600000`；O12/R1/FL6/page 横幅齐；面指纹四机全等。
4. warm 门：64k×3 中位 ≥5000 tok/s（产线 6181.8 先例）。
5. 接线闸门：`bash tools/serve_flags_gate.sh --container r3prod-head --container
   r3prod-worker`（head/worker 各查，fail-closed）。

## 5. 回退

- env：CBX1A → E16B2 → FB54 → 0.3.1 51 键，相邻级单文件回指。
- 镜像：boot `IMAGE` 单行回指 `main-79cafec0`（或 r032b）。
- adapter/overlay/b12x：各目录 `.bak`/公开 0.3.1 件回拷 + 复靴。
