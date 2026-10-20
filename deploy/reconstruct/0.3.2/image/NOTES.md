# r032c 镜像增量（16 件）

## 1. 身份

| 项 | 值 |
|---|---|
| 目标 tag | `192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c` |
| manifest digest | `sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4` |
| 内容身份 cid | `6e379f6fe0531c9c`（RootFS 层链 sha256 前 16） |
| 层数 | 71 = 基座 70 + 1 COPY |
| 基座 | `192.168.0.202:5000/lmsysorg/sglang:main-79cafec0`（image `80e1ea8979c5`） |
| 上游基线 | `sgl-project/sglang@79cafec0` |
| 重演树 | `/tmp/bt-r032@f9d89b02`，tree `dab49d96d33839480e30a1d24ac9e6cdb0a9c29d` |

## 2. 16 件与来源

| 补丁层 | commit | 内容 |
|---|---|---|
| 上游 prefill indexer | `295c3097` | raw selection / row-pair schedule ids / no host syncs（PR #41659） |
| fp4 闭包 | `b9cf2026` | `fp4_indexer` 依赖闭包（`520d6d0`） |
| dense block 闭包 | `e0693e96` | `candidate_block_mask@391e665` 闭包 |
| 位级保持 | `f9d89b02` | `scoring.py` 恢复 stock 候选序排序；对 r032b 仅此 1 件差分 |

逐件 md5=`port16-tree-md5-r032c.txt`；文件全文在 `files/`（按
`python/sglang/...`、`test/registered/...` 原路径），补丁在
`79cafec0-to-r032c-16files.patch`。

## 3. 重建（二选一）

### A. 用全文直接构建（推荐，最接近产线烘法）

```bash
docker image inspect 192.168.0.202:5000/lmsysorg/sglang:main-79cafec0 >/dev/null
bash build-0.3.2-r032c.sh            # 构建 + 读回 + py_compile + import + collection
```

脚本只做 `FROM 基座` + 单 `COPY rootfs/ /sgl-workspace/sglang/`，并断言：
基座 ID `80e1ea8979c5`、层数 = 基座+1、16 件读回 md5 对表、`py_compile` 16/16、
13 模块 import 全 OK、四件套 pytest collection 绿。

### B. 用补丁从上游重建（审计用）

```bash
git clone https://github.com/sgl-project/sglang.git sglang
git -C sglang checkout 79cafec0
# 先核 stock 16 件与 stock16-md5.txt 全等，再打补丁
git -C sglang apply --check /path/to/79cafec0-to-r032c-16files.patch
git -C sglang apply /path/to/79cafec0-to-r032c-16files.patch
# 结果 16 件 md5 必须等于 port16-tree-md5-r032c.txt
```

补丁已在公开基线上 `git apply --check` PASS；结果与 `files/` 逐字节相同（16/16）。

## 4. 镜像内读回

```bash
docker run --rm --network none <tag> bash -c \
  'cd /sgl-workspace/sglang && md5sum python/sglang/kernels/ops/attention/dsv4/candidate_blocks.py ...'
```

产线读回记录=16/16 对表；LABEL 断言：

```
DSV41_IMAGE_VERSION=0.3.2-r032c
DSV41_PORT_BASE=520d6d0+fc2795b+391e665(candidate_block_mask)
DSV41_PORT_SCOPE=minimal-deadlock-fix +bit-preserve-selection-order 16 files
DSV41_REPLAY_TREE=dab49d96d33839480e30a1d24ac9e6cdb0a9c29d
DSV41_BASE_DIGEST=80e1ea8979c5
BUILT_AT=2026-10-18T05:20:00Z
```

## 5. 边界

- **digest 不能脱离基座复算**：`47f6…ffc4` 是“基座 70 层 + 1 COPY 层”的函数。
  用不同基座（即使源码同为 79cafec0）构建，内容身份会变。
- 构建脚本默认 `BASE` 指向内网 registry；公开环境改 `BASE=`（或先 `docker tag`）
  并把基座 ID 断言用 `SKIP_BASE_ID=1` 放行——此时 digest 只用于追溯，不声称与产线同值。
- 测试件（4 个 `test/...`）随镜像层分发，仅用于 collection 门；不参与运行时。

## 6. 原始烘制脚本

`build-0.3.2-r032c.orig.sh` 是产线窗的原始脚本（含内部 registry/tag 与
`$HOME/luz030-opt-campaign` 工作路径），只作 provenance；公开环境重建请用
`build-0.3.2-r032c.sh`（同一单 COPY 配方，staging 改为本包全文件）。
