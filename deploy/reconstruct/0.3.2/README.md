# 0.3.2 生产环境重建包（r032c + A6 + R1 + E16B2 + CBX1A）

> 2026-10-20 定版。目标：只用**本公开仓** + 外部权重/基座镜像，重建
> 4×DGX Spark GB10（SM121 arm64）TP4 的 0.3.2 现役栈。
>
> 本包补的是 `v0.3.2` tag 时公开仓尚未归位的**现役增量件**。版本叙事与性能读数
> 见 [docs/release/0.3.2-RELEASE-NOTE.md](../../../docs/release/0.3.2-RELEASE-NOTE.md)；
> 本包只回答“怎么逐字节重建”。现役 env 与 adapter 装配面已同时公开在顶层
> （`deploy/env/CBX1A-CERTM-spec1.env`、`deploy/adapter/0.3.2-MANIFEST.md5`）；
> 逐步升级/性能复现/回退见 [UPGRADE-0.3.2.md](../../../UPGRADE-0.3.2.md)。

## 0. 结论：缺什么，本包补什么

| 面 | `v0.3.2` tag 时的公开面 | 本包补位 |
|---|---|---|
| adapter | 0.3.1 快照（`sitecustomize` 55b1e412、`kv_fp4` feaaadd4） | 13 件现役增量 + 4 件产线旁挂件；逐件 md5 台账 |
| overlay | `deepseek_v4_backend.py` 736fbde5（0.3.1） | 现役 **a1e7c3b5** 全文 + 补丁 |
| b12x | E16B2 前形；W-E 的 C 层补丁未公开 | `roce_oneshot.py` 035c860c / `_allgather_cute.py` 7253717a / `_roce_proxy.c` 23646e89 |
| env | 51 键 0.3.1 样本 | **CBX1A 56 键 0729e18d** + FB54/E16B1/E16B2 逐级链 |
| 镜像 | 只有 README 镜像行 | r032c 的 **16 件全文 + 补丁 + 构建脚本 + 身份四件** |
| 权重 | `models.d` 的 0.3.0 卡（476G 旧面） | **1017 84 文件 SHA256SUMS** + NFS/秩映射 + engram 8 分片哈希与生成工具 |
| boot | 已公开，但 md5 与产线不同（脱敏+快照头） | 差异说明与还原命令；参面九参/RUN-ARGS 逐字 |

**仍需外部提供、且不应进 Git 的三项**：基座镜像（48.6GB，70 层）、
V4.1-Flash-1017 权重（476G）、engram 分片（约 189G）。本包给出它们的身份指纹、
下载后校验清单与重新生成 engram 的完整工具链。

## 1. 目标指纹（验收基线）

| 件 | 生产值 | 本包对应 |
|---|---|---|
| boot `r3-boot-arm.sh` | md5 **20f22bc6** | 公开件 9ac6e113（多 8 行快照头+3 处用户名掩码；见 §5） |
| env `CBX1A-CERTM-spec1.env` | 56 键 / md5 **0729e18d** | `env/CBX1A-CERTM-spec1.env` |
| adapter 活件树 | 指纹 **b58e49ff**（产线记录 89 件口径；本包按逐文件 md5 验收） | `adapter/files/` 13+4 件 |
| overlay backend | md5 **a1e7c3b5** | `overlay/deepseek_v4_backend.py` |
| b12x `roce_oneshot.py` | **035c860c** | `b12x/roce_oneshot.py` |
| b12x `_allgather_cute.py` | **7253717a** | `b12x/_allgather_cute.py` |
| b12x `_roce_proxy.c` | **23646e89** | `b12x/_roce_proxy.c` |
| IMAGE `0.3.2-r032c` | digest `sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4`；cid `6e379f6fe0531c9c`；71 层 | `image/` |
| 权重 `DeepSeek-V4.1-Flash-1017` | 84 文件 / 510,311,045,870 B；`config.json` `8be45ce0…21879`；index `74b0686a…98fa8` | `weights/` |
| engram 分片 | 8 件 / 202,758,065,168 B；秩映射 01=r0、02=r1、04=r2、03=r3 | `weights/engram-bins-manifest.json` |
| serve 参面 | 九参（A8/A9/W-G `--sleep-on-idle`）；池 9,600,000；ctx 600,000；MRR 16；chunked 4096 | `boot/RUN-ARGS.md` |

## 2. 重建顺序

### 2.0 前置

- 四机：DGX Spark GB10，驱动 580.173.02，内核 6.17.0-1031-nvidia，CUDA 13.0；
  Docker + nvidia-container-toolkit 1.19.1；head→worker 免密。
- 宿主 C 工具链：`gcc`/`cc` + `libibverbs` 头文件（b12x 的 `_roce_proxy.c` 首次
  使用时自动编译为 `.so`，见 `b12x/NOTES.md`）。
- 本仓 clone 到任意目录；下文 `<repo>` 指仓根，`<home>` 指部署用户家目录。

### 2.1 镜像（二选一）

**A. 直接拉内网在役镜像（最省事，身份完全一致）**

```bash
docker pull <registry-host>:5000/dsv41-sglang-optimized:0.3.2-r032c
docker inspect --format '{{index .RepoDigests 0}}' \
  <registry-host>:5000/dsv41-sglang-optimized:0.3.2-r032c
# 必须等于 sha256:47f6d91a…e2ffc4
```

**B. 从基座重建（可审计/离线）**

```bash
# 基座：<registry-host>:5000/lmsysorg/sglang:main-79cafec0（image 80e1ea8979c5，70 层）
bash <repo>/deploy/reconstruct/0.3.2/image/build-0.3.2-r032c.sh
```

脚本用 `image/files/` 的 16 件全文（无需打补丁）做单 COPY 层，构建后逐件读回
md5、`py_compile`、13 模块 import 审计、四件套 pytest collection。详细= 
`image/NOTES.md`。若要用源码补丁审计：`git apply` `image/79cafec0-to-r032c-16files.patch`
到 `sgl-project/sglang@79cafec0`，结果的 16 件 md5 必须等于 `image/port16-tree-md5-r032c.txt`。

### 2.2 adapter

```bash
# 公开仓的 0.3.1 快照先落到生产位
rsync -a <repo>/deploy/adapter/ <home>/migrate-assets/dsv41/adapter/
# 覆盖 13 件现役增量 + 4 件产线旁挂件
cp -a <repo>/deploy/reconstruct/0.3.2/adapter/files/. <home>/migrate-assets/dsv41/adapter/
```

验收：13 件替换件中 12 个代码件 md5 与 `adapter/production-md5-exact.txt` 全等；
`build_repack_cuda.sh` 仅第 6 行注释路径脱敏（产线 cd6c7707，公开件不同，见
`adapter/NOTES.md`）。整树装配后 87 件可用
`deploy/adapter/0.3.2-MANIFEST.md5` 一次验收。装载缝仍是
`sitecustomize.py`=**beb131ab**；R1 件 `kv_fp4.py`=**75062432**。

### 2.3 overlay

```bash
rsync -a <repo>/deploy/overlay/o12c1-prod/ <home>/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
cp -a <repo>/deploy/reconstruct/0.3.2/overlay/deepseek_v4_backend.py \
      <home>/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
```

目录应为 29 个活件（不含 `.bak-pre-w0b/w0c`）；backend md5=**a1e7c3b5**。

### 2.4 b12x

```bash
cp -a <repo>/deploy/reconstruct/0.3.2/b12x/roce_oneshot.py \
      <repo>/deploy/reconstruct/0.3.2/b12x/_allgather_cute.py \
      <repo>/deploy/reconstruct/0.3.2/b12x/_roce_proxy.c \
      <home>/migrate-assets/b12x/b12x/comm/roce/
```

`_proxy.py` 按源码 sha256 缓存在 `~/.cache/b12x/roce/` 编译；改完 C 件后删缓存或让
sha 变化自然触发重编译。C 件提供 `B12X_ROCE_TOPOLOGY=switched` 与
`B12X_ROCE_TRAFFIC_CLASS=106` 的语义；这两个键在 CBX1A env 中在役。

### 2.5 权重与 engram

```bash
# 1) 84 文件落到 /data/models/DeepSeek-V4.1-Flash-1017（01/02 本地；03/04 NFS）
sha256sum -c <repo>/deploy/reconstruct/0.3.2/weights/DeepSeek-V4.1-Flash-1017.sha256
# 2) engram：任一机生成 4 秩分片（约 189G），分发后按 manifest 校验
OUT=$HOME/dsv41-engram-1017 \
  bash <repo>/deploy/reconstruct/0.3.2/weights/engram-tools/pack_all.sh
bash <repo>/deploy/reconstruct/0.3.2/weights/engram-tools/build_and_distribute.sh
```

已有产线 engram 分片时，直接用 `engram-bins-manifest.json` 的 8 个 sha256 对表，
不必重跑。NFS 导出、03/04 挂载、秩映射、回退=见 `weights/WEIGHTS.md`。

### 2.6 boot 与 env

```bash
# env 落位
cp <repo>/deploy/reconstruct/0.3.2/env/CBX1A-CERTM-spec1.env \
   <home>/migrate-assets/dsv41/env/
# boot 链落位（公开件；产线用户名按 §5 还原）
cp <repo>/deploy/bin/r3-boot-arm.sh <home>/migrate-assets/bin/
ARM_TAG=r3prod \
ARM_ENV_FILE=<home>/migrate-assets/dsv41/env/CBX1A-CERTM-spec1.env \
  bash <repo>/tools/boot-with-slotlock.sh bash <home>/migrate-assets/bin/r3-boot-arm.sh
```

参面九参、WORKERS 四行、D15 五门、四查与 warm 门=见 `boot/RUN-ARGS.md`。

## 3. 目录说明

| 路径 | 内容 |
|---|---|
| `env/` | CBX1A 56 键现役 + FB54/E16B1/E16B2 逐级链 + `ENV-CHAIN.md` |
| `adapter/files/` | 13 件增量 + 4 件产线旁挂（`patches/0001`、EP1 旧清单、F6 变体） |
| `adapter/adapter-0.3.1-to-0.3.2.patch` | 从公开 0.3.1 快照到现役的 unified diff |
| `overlay/` | 现役 backend 全文 + 补丁 |
| `b12x/` | 3 件现役源码 + 补丁 + C 构建说明 |
| `image/files/` | r032c 的 16 件全文（按 `python/…`/`test/…` 原路径） |
| `image/*.patch` | `79cafec0 → f9d89b02` 的 16 件补丁（审计/源码重建用） |
| `image/build-0.3.2-r032c.sh` | 从基座构建 r032c 的公开配方（含读回与语法/import/collection 门） |
| `weights/` | 84 文件 SHA256SUMS、engram 8 分片清单、生成/分发/校验工具 |
| `boot/RUN-ARGS.md` | 九参、WORKERS、env 链、门禁 |
| `verify.sh` | 本包自验（不需要生产机/权重） |

## 4. 验证

```bash
bash <repo>/deploy/reconstruct/0.3.2/verify.sh
```

覆盖：包内 `MANIFEST.md5`、env 键数/md5、adapter 12 件生产 md5、overlay/b12x
生产 md5、镜像 16 件台账、权重 84 行 + engram 8 分片哈希、三层补丁对公开基线的
`git apply --check`。期望最后一行 `RECON-KIT PASS`。

运行时另验：boot 后 `curl -s localhost:8899/health`=200；`printenv` 四机与 env
逐字；`banner complete: 29 gates`；池 9,600,000；`bash tools/serve_flags_gate.sh
--container <head容器>` 退出 0（issue #4）。

## 5. 脱敏与 md5 差异（必读）

- 公开仓按既有政策把用户名掩码为 `liux***ya`；`boot` 公开件另带 8 行快照注记。
  因此**公开 boot 件 md5=9ac6e113，产线=20f22bc6**，功能逐字等价。还原：
  `sed '2,9d' deploy/bin/r3-boot-arm.sh | sed "s#/home/liux\*\*\*ya#<home>#g"`。
- `adapter/build_repack_cuda.sh` 仅第 6 行注释里的家目录改成
  `/home/<deploy-user>`；产线 md5 cd6c7707，公开件不同，运行逻辑零差异。
- 内网 IP/主机名（管理段四址、NFS 段与节点主机名）已于 20261030 脱敏为占位符
  （`<mgmt-node-ip>`/`<nfs-server-ip>`/`<node0N>` 等；boot 脚本侧改环境变量注入）。
- 本包**零凭据**：无 sudo 口令、无私钥、无 API key、无 registry 登录串。

## 6. 变更谱系（单变量）

| 窗 | 日期 | 单变量 | 结果指纹 |
|---|---|---|---|
| S-FIX-W0c | 10-18 | IMAGE 单行切 r032c；同批 adapter 迁移 9 件 + overlay backend | adapter 0c4a3a52 / overlay a1e7c3b5 |
| A6 | 10-19 | `sitecustomize.py` 55b1e412→beb131ab | 50626b18 |
| R1 | 10-19 | `kv_fp4.py` feaaadd4→75062432；`fi_r1/*` 引擎件零字节 | aa5f8854 |
| E16B1 | 10-18/19 | env 两键（RoCE max/gather 524288→1179648） | d55baa00 |
| E16B2 | 10-18/19 | b12x 2 件 + adapter `replicated_split.py` + env 2 键 | 5877fcb0 / b58e49ff |
| CBX1A | 10-19 | env 单行 `CERT_HEAD_M=6,12,…,48` | 0729e18d（终态） |

## 7. 仍不可由本仓独立完成的部分

1. **基座镜像**：48.6GB、70 层，公开仓不分发；无它则无法复算 r032c 的 digest
   （digest 是“基座层链 + 1 COPY 层”的函数）。基座身份=image `80e1ea8979c5`。
2. **权重**：476G，受分发许可约束，不分发；本包只给 84 文件 SHA256SUMS。
3. **engram**：189G 宿主生成物；本包给生成工具 + 8 分片哈希，已有分片可直接对表。
4. 硬件/驱动/内核版本不在仓内；见 DEPLOY-GUIDE §2。

这四项之外，adapter/overlay/b12x/env/镜像增量/boot 参面均可由本仓逐字节重建。
