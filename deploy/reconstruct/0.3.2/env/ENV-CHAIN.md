# env 逐级链（0.3.1 51 键 → CBX1A 56 键）

本包收录四个完整 env，均为“整文件可落位”形；相邻级只差下列键。回退时逐级
回指即可，不需要手工改键。

| 级 | 件 | 键数 | md5 | 相对前级 |
|---|---|---|---|---|
| 0.3.1 在役 | `deploy/env/PROD-R51W5-FL6FIX-spec1.env`（仓内；服务器名 `PROD-R51W5FL6-spec1.env`） | 51 | 2ac74586 | 基线（已在公开仓） |
| FB54 | `env/PROD-FB54-spec1.env` | 54 | **ad635762** | +3 键、−1 键、4 键改值 |
| E16B1 | `env/PROD-E16B1-spec1.env` | 54 | **d55baa00** | 2 键改值（RoCE 聚合尺寸翻倍） |
| E16B2 | `env/PROD-E16B2-spec1.env` | 56 | **5877fcb0** | +2 键（split/compact gather） |
| CBX1A | `env/CBX1A-CERTM-spec1.env` | 56 | **0729e18d** | 1 键改值（CERT M 八元） |

## 1. 51 → FB54（D12 三键 + 交换机/健康面）

新增：

```
B12X_ROCE_TOPOLOGY=switched
B12X_ROCE_TRAFFIC_CLASS=106
LUZ_SWITCH_ROCE_FLAT=1
SGLANG_ENABLE_HEALTH_ENDPOINT_GENERATION=0
```

删除：

```
B12X_ROCE_PEER_HCA_MAPS=<四秩表>     # 由 TOPOLOGY/TRAFFIC_CLASS 取代
```

改值：

```
B12X_ROCE_HCA: rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
            → rocep1s0f0,roceP2p1s0f1
DSV41_CERT_HEAD_DEBUG: 1 → 0
DSV41_CERT_HEAD_LOG_EVERY: 200 → 0
SGLANG_ROCE_MAX_SIZE: 262144 → 524288
```

## 2. FB54 → E16B1（E16B1 双键包络）

```
SGLANG_ROCE_MAX_SIZE: 524288 → 1179648
DSV41_ROCE_GATHER:    524288 → 1179648
```

键面不变（54），单变量=RoCE one-shot 聚合上限翻倍。

## 3. E16B1 → E16B2（T2 件配套）

新增：

```
DSV41_REPLICATED_SPLIT_WINDOW=0
DSV41_SPLIT_COMPACT_GATHER=1
```

键面 56；同窗 b12x 两件 + adapter `replicated_split.py` 切到 `7d6f79b0`。

## 4. E16B2 → CBX1A（终态）

```
DSV41_CERT_HEAD_M: 6 → 6,12,18,24,30,36,42,48
```

单行单变量；对应 `lm_cert.py` 995be63c 的八元 gate。CBX1A 即 0.3.2 终态现役
env（WCBOOT74 复役形）。

## 5. 落位

```bash
cp env/CBX1A-CERTM-spec1.env ~/migrate-assets/dsv41/env/
# 回退一级
cp env/PROD-E16B2-spec1.env ~/migrate-assets/dsv41/env/
# 再退
cp env/PROD-E16B1-spec1.env ~/migrate-assets/dsv41/env/
cp env/PROD-FB54-spec1.env  ~/migrate-assets/dsv41/env/
# 最后回 0.3.1
cp deploy/env/PROD-R51W5-FL6FIX-spec1.env ~/migrate-assets/dsv41/env/PROD-R51W5FL6-spec1.env
```

boot 用 `ARM_ENV_FILE` 指向哪一个，就是哪一形；改 env 后必须复靴，热改无效。

## 6. 键面自检

```bash
grep -c '^[A-Z0-9_]*=' env/CBX1A-CERTM-spec1.env    # 56
md5sum env/CBX1A-CERTM-spec1.env                    # 0729e18d...
```

注意：`DSV41_CERT_HEAD=1`、`DSV41_FP4KV_R1_INKERNEL=1`、`DSV41_FL6_RECALL_FIX=1`
三键在 0.3.2 仍为 `1`（R1 转正不撤键；FL6 面具在役）。不要按“转正=删键”误删。
