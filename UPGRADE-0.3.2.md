# 升级到 LuZ 0.3.2（0.3.1 基底 + 混合快照）

> 目标读者：已经能跑 0.3.1、或从零搭 4×DGX Spark GB10 TP4 的采用人员。
> 目标：把公开仓的 **0.3.1 整面基底** 与 **0.3.2 现役增量** 合成一套可 boot、
> 可判读、可回退的 0.3.2 栈，并复现 release note 的性能与质量读数。
>
> 设计口径：公开仓**不复制第二套整树**，而是保留 0.3.1 可回退基底，把 0.3.2
> 现役件放在 [`deploy/reconstruct/0.3.2/`](deploy/reconstruct/0.3.2/README.md)，
> 顶层只补一个现役 env 与 adapter 装配账。这就是“0.3.1 基底 + 混合快照”：
> 历史面不被静默覆盖，现役面逐字节可查。

## 0. 目标形态速查

| 面 | 0.3.2 终态 | 验收指纹 |
|---|---|---|
| 网络形态 | 双 rail 以太交换机；每机 **2 口** HCA 部署对 `rocep1s0f0,roceP2p1s0f1`；`B12X_ROCE_TOPOLOGY=switched` + `LUZ_SWITCH_ROCE_FLAT=1` + `TC=106` | env 键面；boot NCCL 段 |
| env | `deploy/env/CBX1A-CERTM-spec1.env`（56 键） | md5 **0729e18d** |
| adapter | 0.3.1 基底 + reconstruct 覆盖；装配后 87 个运行时件 | 活件指纹 **b58e49ff**（89 件记录）；`sitecustomize` **beb131ab**、`kv_fp4` **75062432** |
| overlay backend | `deepseek_v4_backend.py` | **a1e7c3b5** |
| b12x | `roce_oneshot.py` / `_allgather_cute.py` / `_roce_proxy.c` | **035c860c / 7253717a / 23646e89** |
| IMAGE | `dsv41-sglang-optimized:0.3.2-r032c` | digest `sha256:47f6d91ada98…e2ffc4`；71 层（基座 70+1） |
| 权重 | `DeepSeek-V4.1-Flash-1017`（84 文件） | 510,311,045,870 B；`config.json` `8be45ce0…21879` |
| engram | 8 分片 | 202,758,065,168 B；秩映射 01=r0、02=r1、04=r2、03=r3 |
| serve | SPEC6 九参（A8/A9/`--sleep-on-idle`） | 池 9,600,000；ctx 600,000；MRR 16；chunked 4096 |
| boot | `r3-boot-arm.sh` | 产线 **20f22bc6**；公开件 9ac6e113（快照头+掩码） |

> 网络形态说明：0.3.1 及更早的环网形是 4 口 CX-7 hairpin；0.3.2 现役已切
> switched flat 形。两者不可混拼：`B12X_ROCE_TOPOLOGY=switched` 与 4 口裸列
> 同时出现会被 C 层 fail-closed 拒起。历史环网差异档仍在 `switch-fabric` 分支，
> 0.3.2 的交换机增量已并入 main 的 reconstruct 包与 CBX1A env。

## 1. 公开仓形状（先理解，再动手）

| 位置 | 身份 | 用法 |
|---|---|---|
| `deploy/adapter/` | **0.3.1 整面快照**（83 个运行时件 + 3 个仓内文档） | 升级基底；不要直接当 0.3.2 用 |
| `deploy/reconstruct/0.3.2/adapter/files/` | 13 件替换 + 4 件产线旁挂 | 覆盖到基底上，得到 0.3.2 终态 |
| `deploy/env/CBX1A-CERTM-spec1.env` | 0.3.2 现役 env（56 键） | 直接落位；与 kit 内同名件逐字节相同 |
| `deploy/reconstruct/0.3.2/env/` | FB54→E16B1→E16B2→CBX1A 逐级链 + 键差 | 升级/回退的单文件链 |
| `deploy/reconstruct/0.3.2/` | r032c 16 件、overlay、b12x、权重/engram 台账、boot 参面 | 0.3.2 的全部增量 |
| `deploy/overlay/o12c1-prod/` | 29 件 overlay（0.3.1 基底） | 覆盖 backend 后即 0.3.2 |
| `deploy/b12x/` | b12x 计算树（0.3.1 基底） | 覆盖 3 件 RoCE 源码 |

装配后的 adapter 目录=**87 个运行时件**；生产记录是 89 件（多 2 个宿主
`.bak`，不属于运行面）。逐件账见
[`deploy/adapter/0.3.2-MANIFEST.md5`](deploy/adapter/0.3.2-MANIFEST.md5)，
装配步骤见 [`deploy/adapter/0.3.2-ASSEMBLY.md`](deploy/adapter/0.3.2-ASSEMBLY.md)。

## 2. 前置

- 四机：DGX Spark GB10（SM121，arm64，UMA），TP4；head→worker 免密。
- 驱动 **580.173.02**；内核 **6.17.0-1031-nvidia**；CUDA 13.0；
  nvidia-container-toolkit **1.19.1**；Docker 可用。
- 宿主 C 工具链：`cc`/`gcc` + `libibverbs` 头文件（b12x `_roce_proxy.c` 首次
  使用自动编译）。
- 磁盘：基座镜像约 48.6GB；1017 权重 476G；engram 约 189G；另留镜像/备份空间。
- 网络：双 rail 交换机；管理段 `192.168.0.201-204`；registry `192.168.0.202:5000`。
- 纪律：前栈拆靴→点火至少 **600s** 沉降；一个判读窗内 env/serve/adapter 三元组
  不许中途切换。

## 3. 镜像（二选一）

### 3.1 直接拉现役镜像（推荐，身份完全一致）

```bash
docker pull 192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c
docker inspect --format '{{index .RepoDigests 0}}' \
  192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c
# 期望：sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4
docker image inspect -f '{{len .RootFS.Layers}}' \
  192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c
# 期望：71（基座 70 + 单 COPY 层）
```

四机都要有同一镜像（head 拉取后 `docker save`/内网分发均可）；`RepoDigests`
四机必须同值。

### 3.2 从基座重建（可审计/离线）

```bash
# 基座必须先在本地：image id 80e1ea8979c5，70 层
bash <repo>/deploy/reconstruct/0.3.2/image/build-0.3.2-r032c.sh
# 冷构建：NOCACHE=1 ...
# 只做断言不构建：bash .../build-0.3.2-r032c.sh --check
```

脚本用 `image/files/` 的 16 件全文做单 COPY 层，构建后逐件读回 md5、
`py_compile`、13 模块 import 审计、四件 pytest collection。若要用源码补丁审计：

```bash
git -C <sglang-src> checkout 79cafec0
git -C <sglang-src> apply <repo>/deploy/reconstruct/0.3.2/image/79cafec0-to-r032c-16files.patch
# 16 件 md5 必须等于 image/port16-tree-md5-r032c.txt
```

构建产物 digest 只有在**同一基座层链**上才会等于 `47f6d91a…`；换基座/换
构建器会得到不同 digest，此时以“16 件读回 md5 + 71 层 + 单 COPY”为内容判据，
不要拿 digest 硬套。

## 4. 权重与 engram

```bash
# 01/02 本地；03/04 走 NFS 只读位（见 weights/WEIGHTS.md）
sha256sum -c <repo>/deploy/reconstruct/0.3.2/weights/DeepSeek-V4.1-Flash-1017.sha256
# 84 行全 OK；总字节 510,311,045,870
```

engram 已有分片时直接对 `weights/engram-bins-manifest.json` 的 8 个 sha256；
没有时用工具生成（约 189G，耗时数小时）：

```bash
OUT=$HOME/dsv41-engram-1017 \
  bash <repo>/deploy/reconstruct/0.3.2/weights/engram-tools/pack_all.sh
bash <repo>/deploy/reconstruct/0.3.2/weights/engram-tools/build_and_distribute.sh
```

缺权重/分片时 boot 前置检查会拒起，这是预期，不要绕过。

## 5. adapter（0.3.1 基底 + 0.3.2 覆盖）

```bash
# 1) 在临时目录装配，先验收再落位
rm -rf /tmp/adapter-032
cp -a <repo>/deploy/adapter /tmp/adapter-032
cp -a <repo>/deploy/reconstruct/0.3.2/adapter/files/. /tmp/adapter-032/
cd /tmp/adapter-032 && md5sum -c <repo>/deploy/adapter/0.3.2-MANIFEST.md5
# 87/87 OK

# 2) 备份现役树，再整树替换（四机同批）
cp -a <home>/migrate-assets/dsv41/adapter \
     <home>/migrate-assets/dsv41/adapter-bak-pre-032-$(date +%Y%m%d-%H%M%S)
# 用 -a 不用 --delete：保留宿主侧 .bak/现场文件；本版没有“被移除”的运行时件
rsync -a /tmp/adapter-032/ <home>/migrate-assets/dsv41/adapter/
```

关键锚：`sitecustomize.py`=**beb131ab**、`kv_fp4.py`=**75062432**、
`replicated_split.py`=**7d6f79b0**、`roce_ar.py`=**f61e0183**、
`seam_mount.py`=**a65797a5**、`sparse_wire.py`=**0067abc4**。产线活件指纹
**b58e49ff**（89 件记录）；本树 87 件 + 生产宿主 2 个 `.bak`，逐件 md5 一致。

唯一人工差异：`build_repack_cuda.sh` 第 6 行注释中的家目录被脱敏，产线
md5=`cd6c7707`，公开装配树=`e1aea6d1`，脚本逻辑零差异。

> **绑定律（最高危）**：`seam_mount.py`/`sparse_wire.py` 与 r032c 引擎件必须
> 同批切换。新镜像配旧 adapter 会静默回退上游修复——能起、能跑，但长稳/位等
> 会出问题。禁止只升一面后开判读窗。

## 6. env

```bash
cp <repo>/deploy/env/CBX1A-CERTM-spec1.env \
   <home>/migrate-assets/dsv41/env/
md5sum <home>/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env   # 0729e18d
grep -c '^[A-Z0-9_]*=' <home>/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env  # 56
```

boot 用 `ARM_ENV_FILE` 指向哪一个文件，就是哪一形；改 env 后必须复靴，热改无效。
0.3.2 回退链（相邻级单文件回指）：

```
CBX1A(56, 0729e18d) → E16B2(56, 5877fcb0) → E16B1(54, d55baa00)
                    → FB54(54, ad635762) → 0.3.1 51 键(2ac74586)
```

三个键在 0.3.2 仍为 `1`，不要按“转正=删键”误删：`DSV41_CERT_HEAD=1`、
`DSV41_FP4KV_R1_INKERNEL=1`、`DSV41_FL6_RECALL_FIX=1`。CBX1A 的注释块保留了
W-C/W-E/W-G 的历史沿革（含“呈裁”字样），是 provenance，不是待办；**不要为了
改注释而改文件**，否则 md5 立刻偏离 `0729e18d`。

## 7. overlay 与 b12x

```bash
# overlay：先落 0.3.1 的 29 件，再覆盖 backend
rsync -a <repo>/deploy/overlay/o12c1-prod/ \
      <home>/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
cp <repo>/deploy/reconstruct/0.3.2/overlay/deepseek_v4_backend.py \
   <home>/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
md5sum <home>/migrate-assets/v4vl/sglang-overlay.o12c1-prod/deepseek_v4_backend.py
# 期望 a1e7c3b5

# b12x：3 件源码落位
cp <repo>/deploy/reconstruct/0.3.2/b12x/roce_oneshot.py \
   <repo>/deploy/reconstruct/0.3.2/b12x/_allgather_cute.py \
   <repo>/deploy/reconstruct/0.3.2/b12x/_roce_proxy.c \
   <home>/migrate-assets/b12x/b12x/comm/roce/
```

`_roce_proxy.c` 由 `_proxy.py` 按源码 sha256 缓存在 `~/.cache/b12x/roce/` 编译；
源码变化会自动触发重建。若手工清了缓存，首靴会多一次编译时间，属正常。

## 8. boot

```bash
ARM_TAG=r3prod \
ARM_ENV_FILE=<home>/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env \
SPEC=1 \
SPEC_EXTRA_ARGS="--prefill-decode-interval 16 --max-queued-requests 32 --min-free-slots-delay 1 --enable-decoder-swa-bounded-replay --reasoning-parser deepseek-v41 --swa-prefix-tails 256" \
  bash <repo>/tools/boot-with-slotlock.sh bash <home>/migrate-assets/bin/r3-boot-arm.sh
```

`SPEC=1` 追加 `--speculative-algorithm DSPARK`；`r3-boot-arm.sh` 的 `SERVER_ARGS`
固定面另含 A8/A9/第九参：

```
--tool-call-parser deepseekv41
--enable-cache-report
--sleep-on-idle
```

易错点：`tool-call-parser` 必须连写 `deepseekv41`；`reasoning-parser` 必须带
连字符 `deepseek-v41`。写反不报错，功能静默缺失——用
`tools/serve_flags_gate.sh` 从运行进程 argv 直证。

公开 boot 件 md5=`9ac6e113`（多 8 行快照头 + 3 处用户名掩码），产线
`20f22bc6`。若要与产线逐字节对表，先确认快照头行号，再去头并把掩码路径换成
实际家目录；不追求 md5 对齐时直接用公开件即可，功能等价。

## 9. 验收门（boot 后先过这一组）

1. `curl -s http://127.0.0.1:8898/health` = 200；网关侧 8899/8001 健康。
2. 四机 `printenv` 与 CBX1A env 逐字；`docker inspect` 的 `Config.Cmd` 含九参。
3. 横幅 `banner complete: 29 gates`；池 `max_total_num_tokens=9600000`；
   O12/R1/FL6/page/CERT 横幅齐。
4. 面指纹四机全等：adapter 树、overlay 29 件、IMAGE digest。
5. `bash <repo>/tools/serve_flags_gate.sh --container r3prod-head --container r3prod-worker`
   退出 0（head/worker 各查；`/health` 200 不能证明 A8/A9 接线）。
6. warm 门：64k×3 中位 ≥5000 tok/s（产线先例 6181.8）。

任一门红→按 OPS-MANUAL 双复原义务处理，不要带红开判读窗。

## 10. 性能复现

> 纪律：绝对值是**同硬件、同钟态、同量具口径**的参考；判读用同机 0.3.1 基线
> 与 release note 锚列，不要跨机/跨钟态/跨 filler 比较。每档至少 3 次独立调用
> 取中位（`sd_bench` 的 `--runs` 在 PR 模式被忽略，不能用它做三次）。
> 引擎测试口=`http://127.0.0.1:8898/v1`（避开网关 8899 的生产转发）。

### 10.1 PR 七档（sparkdash 口径）

```bash
for s in 8192 16384 32768 65536 131072 262144 524288; do
  for i in 1 2 3; do
    python3 <repo>/tools/bench/sd_bench.py \
      --mode pr --sizes "$s" --pr-filler repeated \
      --base-url http://127.0.0.1:8898/v1 --key-file /dev/null \
      --json-out /tmp/pr_${s}_${i}.json
  done
done
```

参考值（0.3.2 判读线，tok/s）：

| 8192 | 16384 | 32768 | 65536 | 131072 | 262144 | 524288 |
|---|---|---|---|---|---|---|
| 5522.5 | 6040.2 | 6271.3 | **6289.3** | 6048.1 | 5427.9 | 4290.0 |

判据：对同机 0.3.1 基线七档全带内（量具默认 ±5%）；64k 峰档的 0.3.2 主张是
不低于 6147.3（release note：6289.3=+2.3%）。绝对 tok/s 受时钟/温度影响，
先记录 `nvidia-smi -q -d CLOCK` 与 warm 态再比。

### 10.2 DE 五档（mt400 正典口径）

```bash
for c in 1 2 4 8 16; do
  python3 <repo>/tools/bench/sd_bench.py \
    --mode de --type prose --concurrency "$c" --max-tokens 400 \
    --runs 5 --warmups 2 \
    --base-url http://127.0.0.1:8898/v1 --key-file /dev/null \
    --json-out /tmp/de_prose_c${c}.json
done
```

参考值（agg_med，mt400）：

| c1 | c2 | c4 | c8 | c16（观察位） |
|---|---|---|---|---|
| 88.64 域（CBX1A 读 88.62） | 128.89 | 168.35 | 242.83 | 357.9 |

判据：c1 全程 ≥84；c4 对锚 ≥+3%（C8 定标 A 轨承诺）；c16 是观察位，不构成
“收益成立”带。DE 数字只与 mt400 正典口径比；**不要拿 mt64/仪表盘数字对照**。

### 10.3 质量门

- GSM8K：≥0.97（0.3.2 复读 0.985-0.99）。驱动器不在本仓：
  `~/dsv41-flash-dgxsparks/bench/gsm8k_dsv41.py --nq 500`，题源与采样态保持
  与 0.3.1 基线同功率；只换栈不换题/温度/并发。
- needle：600k 三探针全中：
  ```bash
  python3 <repo>/tools/needle_probe.py \
    --base http://127.0.0.1:8898 --form r1 --sizes 600000 \
    --json-out /tmp/needle_600k.json
  ```
  重复三次（不同 `--seed`），三次都命中才算 3/3。
- 质量门红时不要用“性能更好”解释；先回退到 0.3.1 同题复测，区分栈回归与题源漂移。

### 10.4 C8 聚合（可选）

`sd_bench --mode de --type prose --concurrency 1/2/4` 的聚合锚参考：
C1=3757.7、C2=2849.8、C4=1571.0（C4/C1=0.418）。这是定标读数，不是 0.3.3 的
改善承诺；判读位与口径见 release note §2.3。

## 11. 回退

| 面 | 动作 |
|---|---|
| 镜像 | `deploy/bin/r3-boot-arm.sh` 第 20 行 `IMAGE=` 单行回指 `main-79cafec0`（或 r032b）；复靴 |
| env | `ARM_ENV_FILE` 回指 E16B2→E16B1→FB54→0.3.1 51 键；单文件整替，不手改 |
| adapter | `rsync -a --delete <home>/migrate-assets/dsv41/adapter-bak-pre-032-<ts>/ <home>/migrate-assets/dsv41/adapter/`；复靴 |
| overlay/b12x | 回拷 0.3.1 基底件（`deploy/overlay/o12c1-prod/` 原 backend；`deploy/b12x/` 原三件）；清 b12x 编译缓存 |
| boot 参 | 去 `--sleep-on-idle` / A8/A9 的旧 boot 件回拷（若有 `.bak`） |

回退后同样跑 boot 四查+接线闸门；旧形 A8/A9 未接线时闸门应红——这是预期判别，
不是回归。回退完成前不要开流量。

## 12. 故障排查

| 现象 | 先查 | 处置 |
|---|---|---|
| boot 前置拒起 | 84 文件权重、8 分片 engram、adapter/NCCL/b12x 四项在场 | 按缺项补；不要跳过前置门 |
| IMAGE digest 不等于 `47f6d91a…` | 基座是否 `80e1ea8979c5`/70 层；是否单 COPY | 用 16 件读回 md5+71 层作内容判据；换回正确基座重烘 |
| adapter 装配 md5 失败 | 是否先复制了 0.3.1 基底，再覆盖 kit | 从干净基底重装配；`build_repack_cuda.sh` 一行差异属预期 |
| boot 横幅缺 page/R1 | `sitecustomize.py` 是否 beb131ab；adapter 是否四机同树 | 重落 adapter，复靴；不要只改 head |
| 接线闸门红 | `tool-call-parser` 是否连写；`--enable-cache-report` 是否在 argv | 修 boot 参面；`/health` 200 不代表接线成功 |
| PR 64k 低于参考 | 是否冷靴、时钟/温度、filler 是否 repeated | 先 warm 64k×2；记录钟态；同机 0.3.1 对照 |
| DE c1 低 | 是否 mt400（`--max-tokens 400`）、是否 c1 单流 | 按 10.2 口径重跑；不要与 mt64 比 |
| 长稳异常/位等漂移 | 镜像与 adapter 是否同批；`seam_mount`/`sparse_wire` 版本 | 按绑定律同批切换；必要时整栈回退 |

## 13. 外部边界

以下三项**不入 Git**，不是缺件：

1. 基座镜像（48.6GB/70 层，image `80e1ea8979c5`）；
2. 1017 权重（476G，84 文件；受分发许可约束）；
3. engram 分片（约 189G，宿主生成物；包内工具可重建）。

除此之外，r032c 修复、A6/R1、E16B2/CBX1A、overlay/b12x、adapter 装配与
boot 参面均可由公开仓逐字节重建。自验：

```bash
bash <repo>/deploy/reconstruct/0.3.2/verify.sh   # 期望 RECON-KIT PASS
```

## 14. 相关档

- [0.3.2 release note](docs/release/0.3.2-RELEASE-NOTE.md)（性能/质量/回退正典）
- [重建包 README](deploy/reconstruct/0.3.2/README.md)（逐件重建细节）
- [adapter 装配](deploy/adapter/0.3.2-ASSEMBLY.md) · [adapter 增量谱系](deploy/reconstruct/0.3.2/adapter/NOTES.md)
- [env 逐级链](deploy/reconstruct/0.3.2/env/ENV-CHAIN.md)
- [boot 参面](deploy/reconstruct/0.3.2/boot/RUN-ARGS.md)
- [部署指南](docs/DEPLOY-GUIDE.md) · [switch-fabric 分支](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/tree/switch-fabric)
- [CHANGELOG](CHANGELOG.md) · [FORM-REGISTRY](docs/registry/FORM-REGISTRY-031.md)
