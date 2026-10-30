# 证据文件索引

所有文件均为 2026-10-22 调优窗口的记录副本，未修改内容；`SHA256SUMS` 可校验。
原始日志同时保留在 `~/r3-prod-logs`、`/tmp` 和 `~/migrate-assets/prod`。

| 文件 | 来源/用途 |
|---|---|
| `pr7-final.json` | 最终靴 PR 8k–512k 原始结果 |
| `pr7-capoff.json` | 解除 GPU 锁频后的 PR 对比 |
| `pr7-buf523296.json` | buffer 恢复 523296 后的 PR 对比 |
| `de-final-c1.json` | DE 并发 1，五次结果 |
| `de-final-c8.json` | DE 并发 8，五次结果 |
| `gsm8k-final-summary.json` | GSM8K 20 题冒烟汇总 |
| `needle-final.json` | needle 8k/32k/64k/128k 结果 |
| `boot-prod-final-20261022.log` | 最终生产靴启动 + post-boot 自检 |
| `boot-prod-buf523296.log` | buffer 523296 启动靴 |
| `boot-prod-ec131072.log` | empty-cache 阈值 131072 测试靴 |
| `selfcheck-postboot-20261022-162719.log/.tsv` | 最终靴 38 项自检 |
| `selfcheck-fast-20261022-163826.log/.tsv` | 最新 fast 36 项自检 |
| `selfcheck-latest-fast.json` | 最新自检 JSON |
| `warm-20261022-162719-1..5.json` | 5 次 64k warm 原始值（第一次冷读） |
| `gpu-pr7.csv` | 解除锁频后 GPU 时钟/温度/功耗采样 |
| `gpu-pr7-buf.csv` | buffer 523296 时采样 |
| `gpu-pr7-final.csv` | 最终靴采样 |
| `last-boot.json` | 启动 rc、env md5、boot 脚本 md5 |

注：GPU CSV 无表头，列顺序为时间、SM 时钟、温度、功耗、利用率。
