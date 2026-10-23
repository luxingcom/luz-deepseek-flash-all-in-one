# 6.17 回滚证据清单

本目录是 2026-10-22 23:35 UTC 至 2026-10-23 00:57 UTC 的回滚、复测和
内核/驱动版本锁的原始记录。时间均为 UTC。

| 文件 | 内容 |
|---|---|
| `boot-prod-20261022-233453.log` | 6.17 生产启动完整日志；预检、槽锁、启动时自检 42/42 |
| `selfcheck-20261022-234245.log/.tsv` | 启动时 post-boot 42 项自检（warm gate 6463） |
| `selfcheck-20261023-000538.log/.tsv` | 版本锁前最终 post-boot 42 项复检（warm gate 6446） |
| `selfcheck-postboot-final.json` | 上述版本锁前 post-boot 42/42 JSON |
| `selfcheck-fast-latest.json` | 版本锁前 fast 自检 JSON（40/40） |
| `selfcheck-20261023-005415.log/.tsv` | **最终 post-boot**（版本锁 guard 完成后，46/46，warm gate 6415） |
| `selfcheck-20261023-005620.log/.tsv` | **最终 fast**（44/44） |
| `selfcheck-fast-final.json` | 最终 fast 机器可读结果（44/44，00:56:48 UTC） |
| `warm-20261022-234245-1..5.json` | 启动时 64k warm 五次原始读数 |
| `warm-20261023-000538-1..5.json` | 版本锁前最终复检 64k warm 五次原始读数 |
| `warm-20261023-005415-1..5.json` | 版本锁后最终复检 64k warm 五次原始读数 |
| `version-lock/` | 版本锁全套证据：脚本、systemd unit、APT pin/blacklist、四机终态（22 精确锁 + 7 guard，共 29 个 hold）、fast/post-boot 日志、`README.md`、`SHA256SUMS` |
| `last-boot.json` | `boot_rc=0`、`selfcheck_rc=0` |
| `prod-profile.env` | 回滚后生产 profile（6.17 + 580.173.02） |
| `host-01..04.txt` | 版本锁安装前的四机终态（内核、GRUB、驱动、NIC、systemd） |
| `production-state.txt` | 生产 `/health`、`server_info`、容器状态 |
| `pr_*.json` | PR 8k–512k 每档 3 次原始读数 |
| `de_c1.json` / `de_c8.json` | DE mt400 五次原始读数 |
| `gsm8k-20.summary.json` / `.raw.jsonl` | GSM8K 20 题冒烟 |
| `qeval-6.17-rollback.json` / `qeval.log` | qeval 75 题质量门（71/75） |
| `performance-summary.tsv/.json` | 汇总表与机器可读结果 |
| `bench-6.17.log` / `bench-6.17.sh` | 本次复测日志与可重放脚本 |
| `roce-ring-apply.sh` | 修复 `heal-if-down` 误报后的已安装脚本副本 |
| `INCIDENT.md` | 回滚事件时间线、根因与防再发 |
| `SHA256SUMS` | 本目录文件校验和（含 `version-lock/`） |

权威结果：最终 post-boot 为 `selfcheck-20261023-005415.log/.tsv`
（46/46，00:55:42，warm median **6415 tok/s**）；最终 fast 为
`selfcheck-20261023-005620.log/.tsv`（44/44，00:56:48）。四机版本锁终态以
`version-lock/host-01..04.txt` 为准，顶层 `host-01..04.txt` 保留作安装前对照。
