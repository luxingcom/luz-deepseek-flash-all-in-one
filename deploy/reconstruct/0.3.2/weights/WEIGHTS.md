# 权重与 engram（DeepSeek-V4.1-Flash-1017）

## 1. 权重身份

| 项 | 值 |
|---|---|
| 模型 | `DeepSeek-V4.1-Flash-1017`（84 文件） |
| 总字节 | **510,311,045,870** |
| `config.json` sha256 | `8be45ce0476004a3f529fd896115a4a2e800a129ad2d3ec05b16050f52e21879` |
| `model.safetensors.index.json` sha256 | `74b0686a3d2891980d5e303251b075a3bccae2c2ff650747db2620a649b98fa8` |
| `tokenizer.json` sha256 | `c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b` |
| 分片 | `model-00001-of-00048.safetensors` … `model-00048-of-00048.safetensors`（48 个） |
| 全量校验 | `DeepSeek-V4.1-Flash-1017.sha256`（84 行，ModelScope manifest 口径） |

下载后：

```bash
mkdir -p /data/models/DeepSeek-V4.1-Flash-1017
cd /data/models/DeepSeek-V4.1-Flash-1017
sha256sum -c /path/to/DeepSeek-V4.1-Flash-1017.sha256
# 期望 84/84 OK, bad=0, missing=0（产线实测 625s/01、606s/02）
```

`SHA256SUMS` 与上表同源；模型目录内自带一份，便于 `sha256sum -c SHA256SUMS`。

## 2. 四机路径与秩映射

| 机 | 角色 | 模型源 | engram 目录 | rank |
|---|---|---|---|---|
| <node01>（<mgmt-node-ip>） | head | `/data/models/DeepSeek-V4.1-Flash-1017` | `~/dsv41-engram-1017` | 0 |
| <node02>（<mgmt-node-ip>） | worker | `/data/models/DeepSeek-V4.1-Flash-1017` | `~/dsv41-engram-1017` | 1 |
| <node04>（<mgmt-node-ip>） | worker | `/data/models/dsv41-net`（NFS） | `~/dsv41-engram-1017` | 2 |
| <node03>（<mgmt-node-ip>） | worker | `/data/models/dsv41-net`（NFS） | `~/dsv41-engram-1017` | 3 |

- 03/04 NFS 源：`<nfs-server-ip>:/data/models/DeepSeek-V4.1-Flash-1017`（03）、
  `<nfs-server-ip>:/data/models/DeepSeek-V4.1-Flash-1017`（04）；同时建规范路径符号链接
  `/data/models/DeepSeek-V4.1-Flash-1017 -> dsv41-net`，供守卫的 `SHA256SUMS` 红线解析。
- 01/02 的 NFS 导出：`/data/models/DeepSeek-V4.1-Flash-1017` → `<fabric-ip>/24`、
  `<fabric-ip>/24`、`<mgmt-node-ip>/24`（ro,sync,no_subtree_check）；旧导出行保留。
- boot 的 `WORKERS` 表逐行对应上表；秩映射错位时，代码会找不存在的
  `engram-l{1,14}-r{rank}of4.bin`，起机即失败。

## 3. Engram 分片

| 层 | 行数 | 每秩行区间 | 分片大小 |
|---|---|---|---|
| L1 | 384,006,168 | `rows*rank//4` 到 `rows*(rank+1)//4` | 25,344,411,184 B ×4 |
| L14 | 384,016,682 | 同上 | r0/r2 25,345,104,976 B；r1/r3 25,345,105,240 B |

8 件合计 **202,758,065,168 B**；逐件 sha256 见 `engram-bins-manifest.json`。
分片格式：4096 B 头（magic `DSV41EN1`/layer/lo/hi/rows/264）+ 每行 264 B
（256 B F8_E4M3 weight + 8 B F8_E8M0 scale）。

### 生成

```bash
# 在一台有完整 checkpoint 的机器上（产出 4 秩到 $OUT 与 staging/r{1,2,3}）
OUT=$HOME/dsv41-engram-1017 bash engram-tools/pack_all.sh
# 分发到 02/04/03 并远端校验（主机可用 HOST_R1/R2/R3 覆写）
OUT=$HOME/dsv41-engram-1017 bash engram-tools/distribute.sh
bash engram-tools/build_and_distribute.sh   # 上面两步的串联
```

`pack_all.sh` 会先等 47/48 两个 engram 分片下载完并做 sha256 校验，再按
`--tp 4 --layers 1,14` 打包；`verify_engram.py` 做头/边界/随机行逐字节/全覆盖/
全分片 sha256 校验并重写 `bins-manifest.json`。

### 已有分片

直接用 `engram-bins-manifest.json` 对表：

```bash
python3 engram-tools/verify_engram.py     # 本机 rank0
python3 engram-tools/verify_remote.py     # 四机（rank0 本地 + 1/2/3 ssh）
```

注意：`bins-manifest.json` 是 `verify_engram.py` 的产物；本包提供的
`engram-bins-manifest.json` 已去掉宿主机绝对路径，只保留身份字段，可直接用于
size/sha256 对表。

## 4. 回退

旧模型 `/data/models/DeepSeek-V4.1-Flash`、旧 engram `~/dsv41-engram`、旧 NFS 导出
行均保留；回退只需把 boot 的 `HEAD_MODEL_SRC`/`ENG_HOST_*` 指回旧路径并复靴。
0.3.2 切换报告（2026-10-17）记录了完整回退步骤与 fstab 备份位。
