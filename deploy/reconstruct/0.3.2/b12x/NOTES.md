# b12x 增量（0.3.1 → 0.3.2）

3 件现役源码，全部落在 `b12x/comm/roce/`：

| 件 | 0.3.1 | 0.3.2 | 来源 |
|---|---|---|---|
| `roce_oneshot.py` | 2a79d53a | **035c860c** | E16B2（10-18/19）：`columns=` 不等长 last-dim all-gather |
| `_allgather_cute.py` | 6c09156c | **7253717a** | E16B2：columns gather 的 cute 内核 |
| `_roce_proxy.c` | c4393aef | **23646e89** | W-E（10-16）：`B12X_ROCE_TOPOLOGY` fail-closed + `B12X_ROCE_TRAFFIC_CLASS`→`grh.traffic_class` |

## C 件构建

`_proxy.py` 在首次 import 时按源码 sha256 编译，命令等价：

```bash
cc -O2 -std=gnu11 -shared -fPIC -o ~/.cache/b12x/roce/roce_proxy-<sha16>.so \
   _roce_proxy.c -libverbs -lpthread
```

要求：`gcc`/`cc`/`clang` 任一 + `libibverbs` 头文件（`infiniband/verbs.h`）。
缓存目录可用 `B12X_ROCE_CACHE_DIR` 覆写；换 C 件后 sha 变化会自动重编，也可删缓存
强制重编。

## env 依赖

CBX1A 中的在役键：

```
B12X_ROCE_TOPOLOGY=switched
B12X_ROCE_TRAFFIC_CLASS=106
B12X_ROCE_HCA=rocep1s0f0,roceP2p1s0f1
B12X_ROCE_TWO_WAVE_THRESHOLD_BYTES=0
```

`B12X_ROCE_TOPOLOGY` 只接受 `ring`/`switched`，其它值启动即失败（fail-closed）；
`B12X_ROCE_TRAFFIC_CLASS` 缺省回退 `NCCL_IB_TC`，非 [0,255] 整数即失败。

```bash
cp deploy/reconstruct/0.3.2/b12x/{roce_oneshot.py,_allgather_cute.py,_roce_proxy.c} \
   ~/migrate-assets/b12x/b12x/comm/roce/
```

回退：回拷 `deploy/b12x/b12x/comm/roce/` 三件（2a79d53a/6c09156c/c4393aef）+ 清缓存 + 复靴。
