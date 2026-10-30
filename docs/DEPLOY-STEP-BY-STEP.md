# DEPLOY-STEP-BY-STEP — 从零部署执行序（0.3.2 交换机形）

> **承接声明（2026-10-28）**：本文是 [DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) 的换代版。
> DEPLOY-GUIDE 的全部有效内容已按**时间序**重排为一步步的执行序——每步=可复制命令+
> 预期输出+失败先查什么——本文自此作为从零部署的**主路径**；DEPLOY-GUIDE 原文
> **保留不动**，继续作为 0.3.1 历史基线、VL 双臂部署面（其 §9）与总索引用。
> 数值口径以 [UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md)（md5 锚/绑定律/回退表/验收门）
> 与 [deploy/reconstruct/0.3.2/README.md](../deploy/reconstruct/0.3.2/README.md)
> （逐字节重建包，落位面真相源）为法源。
>
> 读者：拿到 4×DGX Spark（交换机以太网形态）+ 本仓、要从零部署到引擎在役的工程师。
> 读法：按节号顺序执行，**不要跳节**；每步红掉时先看该步末尾的"失败先查"。

## 0. 前置与代际声明

**本篇=0.3.2 交换机形（switched flat 双 rail RoCE）**：每机 2 口 HCA 部署对
`rocep1s0f0,roceP2p1s0f1`，env 键面 `B12X_ROCE_TOPOLOGY=switched` +
`LUZ_SWITCH_ROCE_FLAT=1` + `B12X_ROCE_TRAFFIC_CLASS=106`；NCCL 用同一部署对 +
`NCCL_IB_TC=106`。0.3.1 及更早的 4 口 CX-7 hairpin 环网是**历史形**，两形不可混拼。
**环网读者请转 [RING-DEPLOY.md](RING-DEPLOY.md)**（哪些 0.3.2 修复可拿、哪些键必须
留在环网形）。动手前先读 [GETTING-STARTED.md](GETTING-STARTED.md) 的**五个名词**——
不懂那五个词，后面每一步的报错都会看不懂。

**占位符表（全文站点值一律占位，替换后再执行；右列是本仓 0.3.2 参考形值，仅作
对型参考，不构成你站点的值）**：

| 占位符 | 含义 | 本仓 0.3.2 参考形 |
|---|---|---|
| `<H1>~<H4>` | 四机地址，按 rank 顺序（`<H1>`=rank0=head） | 管理段四址互通 |
| `<USER>` | 登录用户（四机同名同家目录） | — |
| `<registry:port>` | 内网 registry 地址 | :5000 |
| `<PORT>` | 生产口（产线流量入口，head 机回环） | 8899 |
| `<TEST_PORT>` | 引擎测试口（量具/验收专用，避开网关转发） | 8898 |
| `<GW_PORT>` | 网关对外车道口 | 8001 |
| `<PREFIX>` | 容器名前缀（拼 `-head`/`-worker`） | r3prod |
| `<repo>` | 本仓 checkout 根目录 | — |

三条纪律先立好，违反任何一条，后面所有读数作废：

1. **一个判读窗内 env/serve/adapter 三元组不许中途切换**；改 env 后必须复靴，热改无效。
2. **拆靴→点火之间沉降 ≥600s**（§7 第五步）；快速重启=首请求 940 级慢窗。
3. **四机必须同批落同一棵树**：adapter/overlay/env 任一面只换 head=混形栈。

外部三项不入 Git、需自备：基座镜像（48.6GB/70 层）、V4.1-Flash-1017 权重（476G）、
engram 分片（约 189G，可用仓内工具从权重重生成）。本仓给出它们的身份指纹与下载后
校验清单（§2、§3）。首次部署前可先在案头跑一次重建包自验：

```bash
bash <repo>/deploy/reconstruct/0.3.2/verify.sh
# 期望：最后一行 RECON-KIT PASS（不需要生产机/权重）
```

## 1. 硬件与系统基线（对版+核验）

### 1.1 对版表

| 项 | 要求 |
|---|---|
| 节点 | 4× NVIDIA DGX Spark（GB10，SM121，ARM aarch64，**UMA 统一内存架构**），TP4 |
| 拓扑 | 双 rail 以太交换机；每机 2 口 HCA 部署对 `rocep1s0f0,roceP2p1s0f1`；管理段四址互通 |
| NVIDIA 驱动 | **580.173.02** |
| 内核 | **6.17.0-1031-nvidia**（arm64） |
| CUDA 面 | **13.0**（容器内经 nvidia-container 注入） |
| nvidia-container-toolkit | **1.19.1** |
| Docker | 稳定版，支持上述 toolkit |
| SSH | head→三 worker 免密（密钥登录） |
| 宿主 C 工具链 | `cc`/`gcc` + `libibverbs` 头文件（b12x 的 C 件首次使用自动编译） |
| 磁盘 | 基座镜像 48.6GB + 权重 476G + engram 约 189G + 备份空间 |
| registry | 四机可达 `<registry:port>` |

四机逐台核验（每台都跑，不要只跑 head）：

```bash
nvidia-smi --query-gpu=driver_version --format=csv,noheader   # 期望：580.173.02
uname -r                                                       # 期望：6.17.0-1031-nvidia
nvidia-smi | sed -n '4p'                                       # 右上角期望：CUDA Version: 13.0
dpkg -l | grep nvidia-container-toolkit | head -1              # 期望：1.19.1
docker info >/dev/null && echo docker-ok                       # 期望：docker-ok
cc --version | head -1                                         # 期望：非空版本行
ls /usr/include/infiniband/verbs.h                             # 期望：该路径存在
for h in <H2> <H3> <H4>; do ssh -o BatchMode=yes "$h" true && echo "$h ok"; done
# 期望：三行 ok（在 <H1> 上执行；任一报 Permission denied = 免密未配好）
```

失败先查：驱动/内核不对版→**先对版再继续**（后面每一步都踩在这面上）；ssh 不通→
密钥面（密码登录是运维应急面，凭据不入仓）。

### 1.2 UMA 架构三件事（先知道，免得白查一轮）

1. **`nvidia-smi` 若干字段 N/A 属正常**。GB10 是统一内存架构，`memory.used`、
   `Current/Max Power Limit` 等字段常显示 `N/A`——这不是故障，不要据此报"显存读不到"
   或"限功率被设错"。
2. **功耗上限显示不能反推降频**。`96% util / 28~31W / SM 时钟低于上限`看着像被限功耗，
   实测往往不是。判定降频只有一条路：

   ```bash
   nvidia-smi -q -d PERFORMANCE | grep -A8 "Clocks Event Reasons"
   # 期望：Performance State: P0；Clocks Event Reasons 各项全 Not Active
   ```

   功耗计数器非零只说明历史上碰过功率墙，要与 Clocks Event Reasons 一起读。
3. **内存观测口径**：`free` 第 4 列是纯空闲，引擎起来后会被页缓存吃剩 1~3 GiB，看着
   像要 OOM；真实可用在 `/proc/meminfo` 的 `MemAvailable`。GPU 侧占用常规工具
   （nvidia-smi/ps RSS/cgroup）读不到（显示 N/A），唯一可靠量法见
   [CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §5；**禁止**用
   `--mem-fraction-static 0.90` × 总内存倒推"剩多少给 OS"——那个比例是"在可用内存里
   拿 N% 建静态区"，据此倒推会凭空造出数。boot 前置的 UMA 总账判据是四机
   `MemAvailable` 足量（boot 件头注参考线 ≥100G）：

   ```bash
   awk '/^MemAvailable:/{print $2/1024" MiB"}' /proc/meminfo   # 四机各跑一次，记录该值
   ```

### 1.3 四机角色表（rank→机位）

| rank | 机位 | 角色 | 权重源 |
|---|---|---|---|
| 0 | `<H1>` | head（API/探活都在它） | 本地盘 |
| 1 | `<H2>` | worker | 本地盘 |
| 2 | `<H3>` | worker | NFS 只读位 |
| 3 | `<H4>` | worker | NFS 只读位 |

注：产线快照的 boot 件内嵌 WORKERS 表里 rank2/rank3 与主机名末位是**交叉**的
（四号机=rank2、三号机=rank3，属有意布线）。从零部署时你要按自己四机的实际地址
改写 boot 件内的 `WORKERS` 三行、`HEAD_IP` 与 `IMAGE`（§6.4）；改完后公开件 md5
`9ac6e113` 自然不再适用，属预期——对表以功能参面为准。

## 2. 拉镜像

### 2.1 通道与命令（二选一）

**A. 直接拉现役镜像（推荐，身份完全一致）**——四机逐台：

```bash
docker pull <registry:port>/dsv41-sglang-optimized:0.3.2-r032c
docker inspect --format '{{index .RepoDigests 0}}' \
  <registry:port>/dsv41-sglang-optimized:0.3.2-r032c
# 期望：sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4
docker image inspect -f '{{len .RootFS.Layers}}' \
  <registry:port>/dsv41-sglang-optimized:0.3.2-r032c
# 期望：71（=基座 70 + 单 COPY 层）
for h in <H2> <H3> <H4>; do ssh "$h" docker inspect --format '{{index .RepoDigests 0}}' \
  <registry:port>/dsv41-sglang-optimized:0.3.2-r032c; done
# 期望：三行输出与 head 的 RepoDigest 逐字相同（四机必须同值）
```

head 拉取后也可 `docker save | ssh … docker load` 内网分发，但**分发完必须重跑上面
四机 RepoDigest 对表**。

**B. 从基座重建（可审计/离线）**——基座先在本地：
`<registry:port>/lmsysorg/sglang:main-79cafec0`（48.6GB，image id `80e1ea8979c5`，
70 层，基座钉 digest `sha256:0f075735…cf3ae`）。

```bash
bash <repo>/deploy/reconstruct/0.3.2/image/build-0.3.2-r032c.sh          # 构建+读回门
NOCACHE=1 bash <repo>/deploy/reconstruct/0.3.2/image/build-0.3.2-r032c.sh # 冷构建
bash <repo>/deploy/reconstruct/0.3.2/image/build-0.3.2-r032c.sh --check   # 只断言不构建
```

期望：构建后 16 件读回 md5 全对 + `py_compile` 过 + 13 模块 import 审计过 + 四件
pytest collection 过（脚本自带这些门）。

### 2.2 镜像身份三种判据

| 判据 | 表值 | 说明 |
|---|---|---|
| ① RepoDigest | `sha256:47f6d91a…e2ffc4` | **豁免规则一句话**：digest 是"基座层链+1 COPY 层"的函数，换基座/换构建器必得不同 digest——此时以"16 件读回 md5 + 71 层 + 单 COPY"为内容判据，**不要拿 digest 硬套** |
| ② 层数 | 71（基座 70+1） | **口径坑**：`docker inspect` 报的层数常比作者口径**多 1**；同名镜像在两机上显示的本地 ID 也可能不同（containerd 索引 digest 与 overlay2 config digest 显示口径不同），digest 相同即内容相同，非漂移。对表前先统一口径 |
| ③ 逐层哈希 | 前 70 层逐层相同 | digest/层数对不上时的定性命令（见下） |

```bash
docker inspect --format '{{range .RootFS.Layers}}{{println .}}{{end}}' <IM_A> >/tmp/LA.txt
docker inspect --format '{{range .RootFS.Layers}}{{println .}}{{end}}' <IM_B> >/tmp/LB.txt
diff <(head -70 /tmp/LA.txt) <(head -70 /tmp/LB.txt)
# 期望：输出为空 = 同一基座；多出的层是你自己烘的载荷层
```

前 70 层相同 ⇒ 基座同源已证；再看载荷层改没改运行期（进容器
`cd <引擎源码目录> && git diff --stat` 为空=零运行期改动），再核 16 件读回 md5。
报告时**三层说清**：层哈希同不同 / 源文件 md5 同不同 / 差的是内容还是仅身份与层数。

失败先查：digest 不等→基座是否 `80e1ea8979c5`/70 层、是否单 COPY；层数 72=多烘了
一层载荷；四机 RepoDigest 不一致→分发不完整，重拉。

## 3. 权重与 engram 落位

### 3.1 权重落位与 84 文件核验

| 机 | 路径 | 内容 |
|---|---|---|
| `<H1>`/`<H2>` | `/data/models/DeepSeek-V4.1-Flash-1017/` | 1017 权重本地盘 |
| `<H3>`/`<H4>` | `/data/models/dsv41-net/`（符号链接 `/data/models/DeepSeek-V4.1-Flash-1017` 指向它） | 同权重 NFS 只读位（ro nfs4，源=你站点 NFS 源，已入 fstab） |

NFS 导出、挂载、秩映射的完整做法见
[`deploy/reconstruct/0.3.2/weights/WEIGHTS.md`](../deploy/reconstruct/0.3.2/weights/WEIGHTS.md)。

```bash
cd /data/models/DeepSeek-V4.1-Flash-1017
sha256sum -c <repo>/deploy/reconstruct/0.3.2/weights/DeepSeek-V4.1-Flash-1017.sha256 | grep -c ': OK$'
# 期望：84（四机各跑一次；NFS 机在同一挂载树跑）
sha256sum -c <repo>/deploy/reconstruct/0.3.2/weights/DeepSeek-V4.1-Flash-1017.sha256 | grep -v ': OK$'
# 期望：无输出（有输出行=该文件损坏/缺件，重传该文件）
find . -type f | wc -l                        # 期望：84
find . -type f -printf '%s\n' | awk '{s+=$1} END{print s}'
# 期望：510311045870
```

### 3.2 权重身份三件（对注册卡）

换模型/换批次前必核三件，逐项对
[`deploy/models.d/`](../deploy/models.d/README.md) 的注册卡（v41-prod 卡）：

```bash
find /data/models/DeepSeek-V4.1-Flash-1017 -type f | wc -l     # ① 分片数：84
sha256sum /data/models/DeepSeek-V4.1-Flash-1017/config.json | cut -c1-16
# ② config 指纹前 16：8be45ce0476004a3
find /data/models/DeepSeek-V4.1-Flash-1017 -type f -printf '%s\n' | awk '{s+=$1} END{print s}'
# ③ 总字节：510311045870
```

boot 横幅的权重身份门也按此判：指纹行 `MODEL=… CFG=… PATH=… BYTES=…` 与卡上登记值
逐字段相等方算靴成；不等=形面红。

### 3.3 engram 落位（8 分片）

engram 是宿主生成物（L1/L14 各 4 秩，共 8 件、202,758,065,168 B），落
`$HOME/dsv41-engram-1017/`，四机同路径；秩映射按 rank0→r0、rank1→r1、rank2→r2、
rank3→r3 分发。**已有产线分片**时直接对 `weights/engram-bins-manifest.json` 的
8 个 sha256，不必重跑；**没有**时在任一机生成（约 189G，耗时数小时）：

```bash
OUT=$HOME/dsv41-engram-1017 \
  bash <repo>/deploy/reconstruct/0.3.2/weights/engram-tools/pack_all.sh
bash <repo>/deploy/reconstruct/0.3.2/weights/engram-tools/build_and_distribute.sh
# 之后四机各跑：ls $HOME/dsv41-engram-1017/engram-*.bin | wc -l   # 期望 8
```

缺权重或分片时 boot 前置检查会拒起——这是**预期**，不要绕过门。

> **换权重 ≠ 换 engram（P0 级警示）**。engram 是从权重打包出的派生物；换权重不换
> engram = 新权重配旧权重派生的 wkv 混跑。**引擎不会报错**——boot 绿、契约过都不
> 代表无恙，推理质量可能静默劣化。换权重后必须二选一：从新权重重生成 engram，或跑
> 质量锚对比旧读数定性。判新旧=engram 文件 mtime 对权重下载/生成时间。详见
> [RUNTIME-PARAMETERS.md](RUNTIME-PARAMETERS.md) §4。

0.3.1 旧树（旧权重 476G + 旧 engram 48G）在切换时**原样保留**，是回退路，不要清理。

## 4. 服务面落位

### 4.1 本仓→服务器路径映射总表

| 本仓 | 服务器落位 | 说明 |
|---|---|---|
| `deploy/bin/` | `$HOME/migrate-assets/bin/` | boot 链 `r3-boot-arm.sh` + gate 四件 + `r3-stop.sh`/watchdog |
| `deploy/adapter/` + `deploy/reconstruct/0.3.2/adapter/files/` | `$HOME/migrate-assets/dsv41/adapter/` | 0.3.1 基底+覆盖=**87 个运行时件**（§4.2） |
| `deploy/env/CBX1A-CERTM-spec1.env` | `$HOME/migrate-assets/dsv41/env/` | 0.3.2 现役 env（§5） |
| `deploy/overlay/o12c1-prod/` + `deploy/reconstruct/0.3.2/overlay/` | `$HOME/migrate-assets/v4vl/sglang-overlay.o12c1-prod/`（=容器内 `SGLANG_OVERLAY_DIR`） | 29 件=28 活件影子挂载+1 映射表（§4.3） |
| `deploy/reconstruct/0.3.2/b12x/` 三件 | `$HOME/migrate-assets/b12x/b12x/comm/roce/` | flat/交换机运行时（§4.4） |
| `deploy/kit/` | `$HOME/w6-kit/`（或烘入镜像 `/opt/dsv41/kit/`） | guard 守卫族+量具 |
| `tools/packages/` 五包 | 各包 README 的部署位（如网关→`/opt/aicad-prod/`） | fabric-net/selfdiag/selfheal/gateway/cfgmgmt（含 systemd 单元面） |
| `deploy/nccl/nccl-ringonly/`+`ncclpin.so` | （0.3.2 交换机形**不需要**） | 环网形遗留件已全链退役封存；仅做环网回退时按 [RING-DEPLOY.md](RING-DEPLOY.md) 落位 |

VL 双臂 overlay 树、网关 VL 车道等非默认在役面见 [DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §9。

### 4.2 adapter 整批装配（绑定律）

先在临时目录装配、验收通过再落位；**四机同批**执行：

```bash
rm -rf /tmp/adapter-032
cp -a <repo>/deploy/adapter /tmp/adapter-032
cp -a <repo>/deploy/reconstruct/0.3.2/adapter/files/. /tmp/adapter-032/
cd /tmp/adapter-032 && md5sum -c <repo>/deploy/adapter/0.3.2-MANIFEST.md5 | grep -c ': OK$'
# 期望：87（87/87 OK；build_repack_cuda.sh 公开件与产线仅第 6 行注释家目录不同，
# 属预期唯一人工差异，逻辑零差）
# 备份现役树（首次部署无现役树可跳过），再整树替换：
cp -a $HOME/migrate-assets/dsv41/adapter \
     $HOME/migrate-assets/dsv41/adapter-bak-$(date +%Y%m%d-%H%M%S)
rsync -a /tmp/adapter-032/ $HOME/migrate-assets/dsv41/adapter/
# 落位后四机各跑一次 md5sum -c 复验（rsync -a 不用 --delete：保留宿主 .bak，本版无被移除件）
```

终态锚（抽核）：装载缝 `sitecustomize.py`=**beb131ab**、R1 件 `kv_fp4.py`=**75062432**、
`replicated_split.py`=**7d6f79b0**、`roce_ar.py`=**f61e0183**、`seam_mount.py`=**a65797a5**、
`sparse_wire.py`=**0067abc4**；产线活件树指纹 `b58e49ff`（89 件口径=87 运行时件+2 宿主
`.bak`）。逐件谱系见
[`deploy/reconstruct/0.3.2/adapter/NOTES.md`](../deploy/reconstruct/0.3.2/adapter/NOTES.md)，
装配步骤见 [`deploy/adapter/0.3.2-ASSEMBLY.md`](../deploy/adapter/0.3.2-ASSEMBLY.md)。

> **绑定律（最高危）**：`seam_mount.py`/`sparse_wire.py` 等 adapter 件与 r032c 引擎件
> 是**同一批**，必须同窗切换、四机一起。新镜像配旧 adapter 会**静默回退上游修复**——
> 能起、能跑，但长稳/位等出问题。少换任一件=`ImportError` 起不来，且**报错只指向
> 一个模块名，看不出少了一批**（先例：清单 13 件只换 5 件，起不来，报错只点 1 个
> 模块名）。拿不到整批就整批不动。

### 4.3 overlay 影子件

```bash
rsync -a <repo>/deploy/overlay/o12c1-prod/ \
      $HOME/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
cp <repo>/deploy/reconstruct/0.3.2/overlay/deepseek_v4_backend.py \
   $HOME/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
md5sum $HOME/migrate-assets/v4vl/sglang-overlay.o12c1-prod/deepseek_v4_backend.py
# 期望：a1e7c3b5 开头
ls $HOME/migrate-assets/v4vl/sglang-overlay.o12c1-prod/ | wc -l   # 期望：29（28 活件+overlay-map.tsv）
```

boot 链对 overlay 有挂载计数断言（`ov_n` 门==28，fail-closed）。注意 overlay 是**运行期
盖在镜像内引擎路径之上**的影子面：镜像里换对了，overlay 里的同名旧件照样盖回去——
这是 ImportError 的第三来源（§9）。

### 4.4 b12x 与 NCCL 件

```bash
cp <repo>/deploy/reconstruct/0.3.2/b12x/roce_oneshot.py \
   <repo>/deploy/reconstruct/0.3.2/b12x/_allgather_cute.py \
   <repo>/deploy/reconstruct/0.3.2/b12x/_roce_proxy.c \
   $HOME/migrate-assets/b12x/b12x/comm/roce/
```

锚：`roce_oneshot.py`=**035c860c**、`_allgather_cute.py`=**7253717a**、
`_roce_proxy.c`=**23646e89**。`_roce_proxy.c` 由 `_proxy.py` 按源码 sha256 缓存在
`~/.cache/b12x/roce/` 自动编译；手工清缓存后首靴多一次编译时间，属正常。这 3 件是
**flat/交换机运行时**，提供 `B12X_ROCE_TOPOLOGY=switched` 与
`B12X_ROCE_TRAFFIC_CLASS=106` 的 C 层语义。

NCCL 面：0.3.2 交换机形用**镜像内 stock pip NCCL 2.30.7** 接管，boot 参面注入
`NCCL_IB_HCA=<部署对>` + `NCCL_IB_TC=106` 即可；0.3.1 环网形的 ring-only 库与
`ncclpin.so` 注入链已退役（件原位封存、不再是 boot 前置）。从零部署交换机形
**不需要**落 NCCL 补丁件。

## 5. env 落位与自检三件

```bash
cp <repo>/deploy/env/CBX1A-CERTM-spec1.env $HOME/migrate-assets/dsv41/env/
# 自检三件：
grep -c '^[A-Z0-9_]*=' $HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env
# 期望：56（键数）
md5sum $HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env
# 期望：0729e18d 开头（md5 锚）
tail -c 1 $HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env | xxd
# 期望：00000000: 0a                                     （尾字节=换行）
```

三件缺一不可：

- **键数 56 / md5 `0729e18d`**：与 `deploy/reconstruct/0.3.2/env/` 同名件逐字节相同；
  md5 偏离=文件被动过（哪怕只改注释），先找原因再继续。
- **尾字节 `0a` 检查**：boot 链自 2026-10-30 起已加尾行守护（旧版 `while read` 注入
  会在文件末尾缺换行时**静默丢掉最后一行**，引擎回落源码缺省值、什么错都不报），但
  仍建议每次落位后自检——旧版脚本或其他消费者可能仍丢末行。若补了尾换行：md5 会变，
  锚表同步更新；补换行**不改运行中容器**，必须重靴才生效。

要点：boot 用 `ARM_ENV_FILE` 指向哪一个文件就是哪一形，改 env 后必须复靴；三个键
（`DSV41_CERT_HEAD=1`、`DSV41_FP4KV_R1_INKERNEL=1`、`DSV41_FL6_RECALL_FIX=1`）在
0.3.2 仍为 `1`，**不要按"转正=删键"误删**；不要为了改注释改文件。回退链为相邻级
单文件整替：CBX1A(56)→E16B2(56)→E16B1(54)→FB54(54)→0.3.1 51 键，逐级键差见
[`deploy/reconstruct/0.3.2/env/ENV-CHAIN.md`](../deploy/reconstruct/0.3.2/env/ENV-CHAIN.md)。

## 6. 首次点火

### 6.1 点火前两查

```bash
crontab -l | grep reboot
# 期望：无输出。head 机常配 @reboot 自启（开机后等 worker 可达即点火），
# 它会与你的手动点火抢同一把靴槽——有该行则先确认它不会在你的点火窗口内触发。
mkdir -p ~/luz030-opt-campaign
# wrapper 缺省锁位在该目录（全新机器无此目录时锁文件打开失败即拒起）；
# 也可用 CAMPAIGN=<任一可写目录> 覆写。
```

### 6.2 boot 命令与逐参解释

```bash
ARM_TAG=<PREFIX> \
CTN_PREFIX=<PREFIX> \
ARM_ENV_FILE=$HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env \
SPEC=1 \
SPEC_EXTRA_ARGS="--prefill-decode-interval 16 --max-queued-requests 32 --min-free-slots-delay 1 --enable-decoder-swa-bounded-replay --reasoning-parser deepseek-v41 --swa-prefix-tails 256" \
  bash <repo>/tools/boot-with-slotlock.sh bash $HOME/migrate-assets/bin/r3-boot-arm.sh
```

| 参 | 语义 |
|---|---|
| `ARM_TAG` | 本次靴的标签（写进锁凭据与日志，供跨会话对质） |
| `CTN_PREFIX` | 容器名前缀。**必须显式=你的产线前缀**——脚本缺省 `r3boot` 是测试线名；不显式设，产线停栈/守卫按另一前缀找容器（§7 的事故源） |
| `ARM_ENV_FILE` | 形 env 指针——指向哪一形就是哪一形 |
| `SPEC=1` | 追加 `--speculative-algorithm DSPARK`（投机解码） |
| `SPEC_EXTRA_ARGS` | SPEC 六参（见下） |
| `bash tools/boot-with-slotlock.sh` | 靴槽锁 wrapper，**任何会话点火都必须走它**（见 6.3） |

SPEC 六参：`--prefill-decode-interval 16`、`--max-queued-requests 32`、
`--min-free-slots-delay 1`、`--enable-decoder-swa-bounded-replay`（flag）、
`--reasoning-parser deepseek-v41`（**连字符**）、`--swa-prefix-tails 256`。
boot 件的 `SERVER_ARGS` 固定面另含第九参族的另外三参：
`--tool-call-parser deepseekv41`（**连写**！与 reasoning 侧写法互不通用，写反不报错、
功能静默缺失）、`--enable-cache-report`、`--sleep-on-idle`；以及池面固定参
`--max-total-tokens 9600000`、`--context-length 600000`、`--max-running-requests 16`、
`--chunked-prefill-size 4096`。全参面见
[`deploy/reconstruct/0.3.2/boot/RUN-ARGS.md`](../deploy/reconstruct/0.3.2/boot/RUN-ARGS.md)
与 [`deploy/SPEC6-SERVE-REF.md`](../deploy/SPEC6-SERVE-REF.md)。

### 6.3 靴槽锁语义与 BOOT_EXIT=2 定性

四机=**单一靴槽**：一台容器在跑=槽被占。双靴（另一会话/自启任务并发点火）=
drop_caches 互踩、容器对撞、UMA 双装载超卖，**按事故论处**。wrapper 持 fd9 flock
（10s 等待窗），拿不到锁即 `BOOT_EXIT=2` 拒起。见到 `BOOT_EXIT=2` **先三步定性，
别急着排查自己的改动**：

```bash
docker ps --format '{{.Names}}' | grep <PREFIX>          # ① 容器是不是已被别人点起来
docker inspect <ctn> --format '{{.State.StartedAt}}'      # ② 与锁文件里 start= 时刻是否对齐
cat ~/luz030-opt-campaign/.slot-lock                      #    （现任 pid/ARM_TAG/时间戳）
ssh <H1> 'docker exec <ctn> sh -c "tr \"\\0\" \"\\n\" < /proc/1/cmdline"' | grep -A1 '^--'
# ③ 运行中的是不是你要的新配置（值在旗标名的下一行）
```

两个假信号别当真：`ps -p <pid>` 常返回"进程已退出"（点完火就退了）；锁目录空/锁已
释放**不等于没点过火**。可选前置核：`ADAPTER_SYNC_CHECK=1` 让 wrapper 在点火前先做
adapter 四机对表（红=先跑 `tools/adapter-sync.sh --apply` 再点火）。

### 6.4 公开 boot 件的站点适配

公开 `r3-boot-arm.sh`（md5 `9ac6e113`）与产线（`20f22bc6`）功能逐字等价，差异=8 行
快照头+3 处用户名掩码。落到 `$HOME/migrate-assets/bin/` 后按你站点改三处：`IMAGE=`
镜像全名、`HEAD_IP=`、`WORKERS` 三行（rank|主机|IP|权重路径|engram 路径）。改完 md5
不再对 `9ac6e113` 属预期；逐字节对表法见
[`deploy/reconstruct/0.3.2/README.md`](../deploy/reconstruct/0.3.2/README.md) §5。

### 6.5 起机过程与期望输出

wrapper 与 boot 链是串行门序，期望依次打印：

```text
[slotlock] 持锁 pid=… ARM_TAG=<PREFIX> start=…
[slotlock] 四机容器净（docker ps 无 r3boot）
[+] == 前置守卫 ==            → 四行 "head/worker …: 无容器、GPU 空闲"
[B2] 16/4 口 idx3=RoCE v2 在位（四机各 4 口）
[D15] …/2 iface PFC prio3+5+trust dscp+mtu9000 在位（四机各 2 口）
net doctor OK（HCA 部署对逐口 ACTIVE + socket 接口在位）
[+] … 资产面 OK（四机：adapter/b12x_next/分片/权重在场）
→ 容器创建、权重装载（约 2 分钟）、图捕获 → 横幅与 Engine startup timings
```

任一门红即 `die` 拒起——先按门名查（§9 前五行），补齐后重走 §7 的停机窗流程再点火。

## 7. 停机窗五步（每次重靴都用，不是首次专用）

> 这五步是**纪律**，不是建议。跳第 4 步=可能对着一台还在跑的机器再点火；跳第 5 步
> =首请求进 940 级慢窗（warm 前 879/938/940，warm 后 5972+，差一个数量级）。

**第 1 步·备份四件**（四机都做；重靴之后旧形就不存在了，"改后再补"是空话）：

```bash
ts=$(date +%Y%m%d-%H%M%S)
cp -a $HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env ~/bak-env-$ts
cp -a $HOME/migrate-assets/bin/r3-boot-arm.sh ~/bak-boot-$ts.sh
cp -a $HOME/migrate-assets/v4vl/sglang-overlay.o12c1-prod ~/bak-overlay-$ts
md5sum $HOME/migrate-assets/dsv41/adapter/sitecustomize.py > ~/bak-adapter-anchor-$ts.txt
cd $HOME/migrate-assets/dsv41/adapter && md5sum -c <repo>/deploy/adapter/0.3.2-MANIFEST.md5 \
  | grep -c ': OK$'                                            # 期望：87（adapter 清单即备份凭据）
```

**第 2 步·存旧栈日志（删容器前必存，删了就没了）**：

```bash
ssh <H1> "docker logs <PREFIX>-head > ~/stack-head-$ts.log 2>&1"
for h in <H2> <H3> <H4>; do ssh "$h" "docker logs <PREFIX>-worker > ~/stack-$h-$ts.log 2>&1"; done
# 期望：四个日志文件非空（wc -l 各>0）
```

**第 3 步·停栈（前缀必须显式）**：

```bash
CTN_PREFIX=<PREFIX> R3_STOP_VERIFY=1 bash <repo>/deploy/bin/r3-stop.sh
```

两个要点：①**`CTN_PREFIX` 必须显式=你的产线前缀**——脚本缺省前缀是测试线名，
有旧测试栈残留在跑时它会打 `[+] head removed` 四行全绿，而**产线容器纹丝不动**
（在案事故形态）；②停栈三查（四机容器=0 + 双端口 000）**要 `R3_STOP_VERIFY=1` 才
生效**，缺省整节不执行。

**第 4 步·硬断言（不信任何脚本自报）**：

```bash
for h in <H1> <H2> <H3> <H4>; do
  ssh "$h" "docker ps -a --format '{{.Names}}' | grep -c '^<PREFIX>-'" ; done
# 期望：四行 0；任一非 0 → exit 中止，绝不进沉降
ssh <H1> 'curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:<PORT>/health'
# 期望：000（同查 <GW_PORT> 与 <TEST_PORT> 也应 000）
```

任一不满足就中止排查——否则沉降 600s 后会对着一台还在跑的机器再点火。顺手核净：
四机 `MemAvailable` 充裕、`nvidia-smi --query-compute-apps=pid` 为空（拦到的 PID 先
`[ -d /proc/<pid> ]` 核活死，瞬时残留不阻碍起栈）。

**第 5 步·沉降 ≥600s（禁以"容器已净"替代计时，就是静候）**：

```bash
date -u +%FT%TZ; sleep 600; date -u +%FT%TZ   # 记录起止时刻入台账
```

多靴切换（连续换形）建议 ≥30min。沉降完直接接 §6.2 点火。

## 8. boot 后验收（全绿才开流量）

### 8.1 四查

```bash
# ① health 200（引擎只绑回环——必须在 head 机上打；在管理机 curl 127.0.0.1 得 000
#    的第一反应是"我打错机器了"，不是"引擎死了"）
ssh <H1> 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<PORT>/health'    # 200
ssh <H1> 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<GW_PORT>/health' # 200
# ② printenv 键面逐字（四机容器各跑；期望零 MISMATCH 行）
while IFS='=' read -r k v; do
  [ "$(ssh <H1> "docker exec <PREFIX>-head printenv $k")" = "$v" ] || echo "MISMATCH $k"
done < <(grep '^[A-Z0-9_]*=' $HOME/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env)
# ③ 横幅直证
ssh <H1> 'docker logs <PREFIX>-head 2>&1' > /tmp/boot-head.log
grep -c 'banner complete: 29 gates' /tmp/boot-head.log     # 1
grep -c 'max_total_num_tokens=9600000' /tmp/boot-head.log  # 1（池门）
grep -c 'r1_formal=1' /tmp/boot-head.log                    # ≥1（R1 在役）
# ④ 面指纹四机全等
for h in <H1> <H2> <H3> <H4>; do
  ssh "$h" 'cd "$HOME/migrate-assets/dsv41/adapter" && LC_ALL=C find . -type f \
    ! -name "*.bak*" | sort | xargs md5sum | md5sum'; done
# 期望：四行输出完全相同；overlay 目录同理再跑一遍
```

横幅第③查有个**假报坑**：判读横幅要取**组件源码里的 `print` 串**再 grep——按文档里
写的名字 grep 可能得 0 行（大小写/缩写不同），然后误报"横幅缺失"。O12/R1/FL6/page/
CERT 五族横幅都要在役态可见。

### 8.2 warm 门（boot rc=0 且 200 之后的第一动作）

先 warm 请求步 64k×2，再正式 warm 门 64k×3——**3 次独立调用取中位**（`--runs` 在
PR 模式被忽略，不能靠它做三次）：

```bash
for i in 1 2 3; do
  python3 <repo>/tools/bench/sd_bench.py --mode pr --sizes 65536 --pr-filler repeated \
    --base-url http://127.0.0.1:<TEST_PORT>/v1 --key-file /dev/null \
    --json-out /tmp/warm_64k_$i.json
done
python3 -c 'import json,statistics;print(statistics.median(
  [json.load(open(f"/tmp/warm_64k_{i}.json"))["pr"][0]["tok_s"] for i in (1,2,3)]))'
# 期望：中位 ≥4500 绿（<4500=红，不起测）；产线入役线 ≥5000（先例 6181.8）
```

坑清单：首靴第一发偏低是常态（冷态税），别拿第一发下结论；手发请求必须自己加 nonce
（同提示第二次起被 radix 前缀缓存吃掉=假绿）；`repeated` 填充比真实文本虚增约 10%，
锚值与跨环境比对先对齐口径。

### 8.3 接线闸门（`/health` 200 不能证明接线）

```bash
bash <repo>/tools/serve_flags_gate.sh --container <PREFIX>-head --container <PREFIX>-worker
# 期望：退出码 0（head 与 worker 必须各查——角色差异；闸门只读、fail-closed）
bash <repo>/tools/serve_flags_gate.sh --self-test    # R1-R7 判别力回归，期望全 PASS
```

判据=运行进程 argv 直证 `--tool-call-parser deepseekv41`（连写，`deepseek-v41` 形判红）
与 `--enable-cache-report`。接线漏了 `/health` 照样 200、`/v1/models` 照常、**没有任何
红灯**——所以这扇门 fail-closed。用法细节见
[`tools/serve_flags_gate.README.md`](../tools/serve_flags_gate.README.md)。

### 8.4 启动耗时健康带（免费预测哨兵）

```bash
grep -A4 'Engine startup timings' /tmp/boot-head.log | grep target_verify
# 期望：target_verify 落在 44-46s 健康带
```

先例分离度 2/2：49s 绿 / 102s 红。**>75s=红带靴预测**——红带现形即**停靴取证**，
不连发重试。

### 8.5 功能面必测（形面全绿 ≠ 功能合同好）

带 `tools` 的 chat、流式、非流式、长上下文**各一发**，按真实使用方式打真请求
（经引擎测试口）。P0 实锤先例：一轮审计 env 键逐字对、参齐、横幅正常、面指纹全等
⇒"无 P0"；换真请求一测，**工具调用解析器没配、模型吐出的工具调用标记漏成明文**。

```bash
ssh <H1> 'curl -s http://127.0.0.1:<TEST_PORT>/v1/chat/completions' -d '{
  "model": "deepseek-v4.1-flash",
  "messages": [{"role": "user", "content": "查一下北京明天的天气"}],
  "tools": [{"type": "function", "function": {
    "name": "get_weather",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                   "required": ["city"]}}}]}'
# 非流式判据：choices[0].message.tool_calls 成型（name=get_weather、arguments 为合法
# JSON）；content 里出现裸的工具调用标记文本 = 解析器没接上（P0，回 §8.3 查接线）
# 流式一发：同请求加 "stream": true，判据 data: 增量块连续、以 [DONE] 收尾
# 长上下文一发：用"检索题"（如"只回答文中标记后四位"），别用"计数题"——思考链会把
# max_tokens 吃光，content 空串+finish=length 是预算问题不是链路问题（判据：看
# usage.completion_tokens 是否撞上限）
```

## 9. 常见首次失败对照表

| 现象 | 先查什么 | 处置/口径 |
|---|---|---|
| 前置拒起"有生产容器/GPU 被占" | `docker ps`；`nvidia-smi --query-compute-apps=pid`，拦到的 PID 先 `[ -d /proc/<pid> ]` 核活死 | 瞬时占用不阻碍起栈；真占用先清掉/协调，不绕门 |
| B2 GID idx3 红（HOLE 行） | `/sys/class/infiniband/<HCA>/ports/1/gids/3` 的 type+gid+ndev 三件套；全零 `::`=该口没 IPv4 | 把 IPv4 加回来并四机复查后重靴 |
| D15 PFC 红 | `mlnx_qos -i <口>`：pfc 应 `0 0 0 1 0 1 0 0`、trust dscp、mtu 9000 | 先恢复 lossless 面再靴 |
| net doctor 红（port 非 ACTIVE/缺 socket 口） | HCA 部署对逐口 `/sys/class/infiniband/<HCA>/ports/1/state` 应 `4: ACTIVE` | 物理口/接口名问题，修物理面 |
| 资产面缺拒起 | adapter 目录、engram 分片、权重路径是否在位 | 按缺项补（§3/§4），不要跳过前置门 |
| 横幅缺页（page/R1/CERT 缺） | `sitecustomize.py` 是否 `beb131ab`；adapter 是否四机同树 | 重落 adapter 复靴；**不要只改 head** |
| `ImportError: cannot import name 'X'` | 三种来源：①镜像不对（digest/层数，§2.2）②adapter 少件（整批 13 件换齐没有）③**overlay 盖回**——先 md5 比对站点 overlay 件与容器内同名件，两侧必须同值 | 通用律：报错指向只在某版存在的符号时，先查 overlay/adapter 这类运行期覆盖面，别只怀疑镜像 |
| 探活 000 | 你在不在 head 机上（引擎绑回环是刻意形） | 一切探活 `ssh <H1> 'curl … 127.0.0.1:<PORT>…'` |
| `BOOT_EXIT=2` | 靴槽锁被占——§6.3 三步定性（是不是别人/自起点了火） | 与持有者会话协调；两个假信号（ps 退出/锁已空）别当真 |
| 接线闸门红 | `deepseekv41` 是否连写、`--enable-cache-report` 是否在 argv | 修 boot 参面复靴；`/health` 200 不代表接线成功 |
| printenv 少最后一键 | env 尾字节（§5 第三件） | 补 `0a`、更新锚表、复靴 |
| warm 门红 | 是否冷靴、时钟/温度（`nvidia-smi -q -d CLOCK`）、是否真 3 次取中位 | 先 warm 64k×2 复测；仍红再按 [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) 排 |
| PR/DE 某格暴跌 | 是不是批次里最先跑的那格（冷态税能低到近一半） | 复测取中位，别直接报回归；曲线单调性才是干净信号 |
| 高并发越并越慢的非单调塌陷 | 通信聚合两键是否被回滚（`SGLANG_ROCE_MAX_SIZE`/`DSV41_ROCE_GATHER` 应 1179648） | 新代引擎**不许回滚这两键**（回滚先例 c8 −96%）；单请求也掉=慢路径指纹 |

## 10. 下一步

| 你要做什么 | 去 |
|---|---|
| 量性能/质量（PR 七档、DE 五档、GSM8K、needle 的口径与判读） | [CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) |
| 出了症状查原因（排障词典） | [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) |
| 换模型/改参数（权重三件、换权重≠换 engram、键语义） | [RUNTIME-PARAMETERS.md](RUNTIME-PARAMETERS.md) |
| 已知现象与既往判例 | [KNOWN-ISSUES.md](KNOWN-ISSUES.md) |
| 升级/性能复现/回退正典 | [UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) |
| boot/复原/回退规程法源 | [runbook/OPS-MANUAL-031.md](runbook/OPS-MANUAL-031.md) |
| 形三元组与部署面指纹权威表 | [registry/FORM-REGISTRY-031.md](registry/FORM-REGISTRY-031.md) |
| 0.3.2 全量差异与读数主表 | [release/0.3.2-RELEASE-NOTE.md](release/0.3.2-RELEASE-NOTE.md) |

——DEPLOY-STEP-BY-STEP / 2026-10-28（承接 DEPLOY-GUIDE.md，按时间序重排为从零主路径）
