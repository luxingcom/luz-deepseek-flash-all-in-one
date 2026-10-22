# 2026-10-22 生产调优报告与证据

本目录是 2026-10-22 新内核 7.0.0 / 驱动 / NIC 固件 28.50.1002 适配工作的完整记录。

## 文档

- `WORK-REPORT-2026-10-22.md`：工作报告（背景、变更、审计、性能、风险、运维安排）。
- `OPS-RUNBOOK.md`：可直接执行的运维交接清单（巡检、启动、停栈、异常处置、变更控制）。
- `evidence/README.md`：证据文件来源与用途。
- `evidence/SHA256SUMS`：证据文件校验和。

## 现场原始记录位置

以下原始文件仍在生产机用户主目录，未移动：

- `~/r3-boot-prod-20261022-122415.log`（首次生产启动）
- `~/r3-prod-logs/boot-prod-20261022-161712.log`（最终靴）
- `~/r3-prod-logs/selfcheck-latest.json`（最新自检）
- `~/migrate-assets/prod/last-boot.json`（启动结果）
- `/tmp/boot-prod-final-20261022.log`、`/tmp/pr7-final.json` 等（临时原件，已复制到 `evidence/`）

## 结论摘要

生产在线，未回滚；post-boot 38/38 PASS，fast 36/36 PASS；64k warm 中位 5797 tok/s（阈值 5600）；PR 残余差距约 6–13%，已排除本轮所有可测配置项；手动风扇受 Secure Boot/MOK 限制，EC auto 正常。
