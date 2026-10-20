# adapter 现役增量（0.3.1 快照 → 0.3.2 终态）

> 产线活件树指纹=`b58e49ff`（89 件口径）。本目录按**逐文件 md5**验收，不依赖
> 该聚合指纹的重算实现。基线=`deploy/adapter/` 的 0.3.1 整面快照（83 个运行时
> 文件 + 3 个仓内文档）。

## 1. 覆盖方式

```bash
cp -a deploy/adapter/ /tmp/adapter-031/
cp -a deploy/reconstruct/0.3.2/adapter/files/. /tmp/adapter-031/
```

`files/` 内的 13 件替换同名文件，另 4 件是产线树里有、但 0.3.1 公开快照未收的
旁挂件。覆盖后运行时面=产线 87 件；公开快照自带的 `MANIFEST.md5`/`README.md`/
`sitecustomize-wire-v2.diff` 三个文档可保留，不参与装载。

## 2. 13 件增量（逐件产线 md5）

| 件 | 0.3.1 | 产线 | 来源窗 | 变更面 |
|---|---|---|---|---|
| `sitecustomize.py` | 55b1e412 | **beb131ab** | A6（10-19） | indexk page 遮蔽：hunk1 页钉 + hunk2 SM12x dense planner 恢复 |
| `kv_fp4.py` | feaaadd4 | **75062432** | R1（10-19） | R1 fork 正式化：持久缓冲顺批 + `r1_formal=1` 横幅；`fi_r1/*` 引擎件零字节 |
| `replicated_split.py` | 49b9bd2a | **7d6f79b0** | E16B2（10-18/19） | 不等长 last-dim columns gather 接线 |
| `roce_ar.py` | 932fe12b | **f61e0183** | W-E（10-16） | `_roce_module_name` 选择门（3 hunks） |
| `build_repack_cuda.sh` | 4746845c | **cd6c7707** | r032c 迁移（10-18） | 构建源同步；公开件仅第 6 行注释路径脱敏 |
| `indexer_hoist.py` | 78a84587 | **69fca588** | r032c 迁移（10-18） | 行锚迁移（`520d6d0` 接口面） |
| `p12_assertion_graph_gather.py` | fe7d8053 | **00039090** | r032c 迁移（10-18） | 四方法签名面断言器迁移 |
| `reference_impl.py` | 29861e87 | **9bfe0111** | r032c 迁移（10-18） | docstring 行锚迁移 |
| `seam_mount.py` | 9c06b11a | **a65797a5** | r032c 迁移（10-18） | 挂载缝 6 方法迁移 |
| `selection_dump.py` | 35905ebe | **b6d356cf** | r032c 迁移（10-18） | 取证量具行锚迁移 |
| `spark_prefill_split.py` | eb53ea12 | **aba8c088** | r032c 迁移（10-18） | 注释/行锚迁移（TPsplit 门本体不涉签名） |
| `sparse_wire.py` | d57656d2 | **0067abc4** | r032c 迁移（10-18） | **断线#2 重钉**：`publish_decode` 全方法重绑 + `topk_transform_paged_from_metadata` 路由 |
| `tl_segment.py` | 6977551f | **b63691cb** | r032c 迁移（10-18） | 行锚迁移 |

**绑定律**：`seam_mount.py`/`sparse_wire.py` 等 adapter 件与 r032c 引擎件必须同批
切换；旧 adapter 覆盖新引擎会静默回退上游修复（最高危）。

## 3. 4 件产线旁挂（公开 0.3.1 快照未收）

| 件 | 产线 md5 | 性质 |
|---|---|---|
| `patches/0001-sparse_table-nonchunked-topk.patch` | e7a797d7 | r032c 上游化件（`topk_transform_paged_from_metadata` 路由）；**非装载闭包**，审计/重建用 |
| `ep1h-manifest.txt` | 559c87f1 | EP1 旧清单（三件 md5），历史留档 |
| `ep1i-manifest.txt` | dc3743c9 | EP1 旧清单变体，历史留档 |
| `sitecustomize.py.f6-lmcert` | 6e1dc3ac | F6/lmcert 变体，非现役装载缝；历史留档 |

## 4. 脱敏说明

`build_repack_cuda.sh` 第 6 行注释原为 `/home/liux***ya/...`，本包改为
`/home/<deploy-user>/...`；这是唯一的人工差异，脚本逻辑零改。因此：

- 产线 md5=`cd6c7707`；
- 本包文件 md5 不同（见根 `MANIFEST.md5`）；
- 其余 12 件代码与产线逐字节相同（`production-md5-exact.txt`）。

## 5. 验收

```bash
bash deploy/reconstruct/0.3.2/verify.sh
# adapter 段应打印 ADAPTER-12-MD5 PASS
```

运行时装载缝检查：容器内 `python -c "import sitecustomize; print(sitecustomize.__file__)"`
指向 adapter 树；boot 日志应出现 A6 page 横幅与 R1 `r1_formal=1` 横幅。
