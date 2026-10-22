# 生产运维交接清单（r3prod / 7.0.0）

- 配套报告：`WORK-REPORT-2026-10-22.md`
- 适用：`dgxspark01`–`dgxspark04`，TP4，`r3prod`，`deepseek-v4.1-flash`
- 基线：内核 `7.0.0-1019-nvidia`、固件 `28.50.1002`、RX ring `4096`、buffer `523296`、GPU 默认频率/EC auto
- 当前状态：生产在线，post-boot 38/38 PASS，fast 36/36 PASS

## 1. 每班必看（5 分钟）

```bash
# 1) 栈与健康
docker ps --format '{{.Names}} {{.Status}}' | grep '^r3prod'
curl -fsS http://127.0.0.1:8899/health

# 2) 最新自检（必须无 FAIL）
python3 - <<'PY'
import json, os
p = os.path.expanduser('~/r3-prod-logs/selfcheck-latest.json')
d = json.load(open(p))
print(d['timestamp'], d['mode'], 'fails=', d['fails'])
for c in d['checks']:
    if c['status'] != 'PASS': print(c)
PY

# 3) 单元与温度
systemctl is-active prod-selfcheck.timer roce-ring-check.timer
nvidia-smi --query-gpu=temperature.gpu,clocks.sm,clocks.max.sm,power.draw,utilization.gpu --format=csv,noheader
```

通过标准：

- 四机容器在线；`/health` 为 200。
- 最新自检 `fails=0`；最近一次 post-boot 为 38/38。
- GPU 温度低于 90°C，无 `SW Power Cap` / `HW Thermal Slowdown`。
- `prod-selfcheck.timer` 仅在 head 上 active；`roce-ring-check.timer` 四机 active。

## 2. 启动（唯一入口）

```bash
bash ~/migrate-assets/prod/boot-prod.sh
cat ~/migrate-assets/prod/last-boot.json
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot
```

要求：

- 启动前确认没有 `r3prod`/`r3boot` 容器、8899 端口空闲。
- 启动脚本会自行校验 env md5/56 键、28 overlay、recipe、四机 adapter 指纹、镜像 digest、内核白名单、NIC profile 和端口净空；任何一项不符会拒绝启动。
- `last-boot.json` 必须是 `boot_rc=0`、`selfcheck_rc=0`。
- 不允许绕过 `boot-prod.sh` 直接调用 `r3-boot-arm.sh` 或手工 `docker run`。

## 3. 停栈

```bash
CTN_PREFIX=r3prod R3_STOP_VERIFY=1 bash ~/migrate-assets/bin/r3-stop.sh
```

停栈后如需改 NIC：

```bash
sudo /usr/local/sbin/roce-ring-apply.sh check
sudo /usr/local/sbin/roce-ring-apply.sh apply
sudo systemctl restart roce-ring-boot.service   # oneshot 已 active 时不能依赖 start
```

`heal-if-down` 在容器运行时拒绝写配置；不要在栈运行时执行 `apply`。

## 4. 周期检查

```bash
# 日常快检（与 timer 相同）
bash ~/migrate-assets/prod/selfcheck-prod.sh --fast

# 每周低峰或怀疑性能回退
bash ~/migrate-assets/prod/selfcheck-prod.sh --perf

# 每次启动后
bash ~/migrate-assets/prod/selfcheck-prod.sh --post-boot
```

- `--fast`：36 项；`--post-boot`：38 项（多 recipe 探针 + warm gate）。
- warm gate = 5 次 64k PR，丢弃第一次冷读，取后四次中位；阈值 5600 tok/s。
- 单次 PR 波动约 ±5%，不要用一次数字判定回归。

## 5. 异常处置

| 告警/现象 | 确认 | 处置 |
|---|---|---|
| NIC 自检 FAIL | 栈是否在运行 | 栈停：`restart roce-ring-boot.service`；栈在：记录，排维护窗，禁止热写 |
| env / overlay / adapter FAIL | md5、manifest、四机指纹 | 不启动；按 manifest 修复后复跑 `--post-boot` |
| GPU >90°C | `nvidia-smi` 降频标志、EC 风扇 | 降载或停机检查；不要用 `nvfancontrol`（MOK 未注册） |
| warm <5600 | 冷读、并发、NIC 计数、GPU 时钟 | 重测 5 次；仍低则收集日志，逐项排查，禁止同时改多个变量 |
| 自检 timer 红 | timer 用户、SSH、栈状态 | 以 timer 配置的运维账号手工跑 `--fast`；root 跨机运行会假失败 |
| 手动风扇需求 | MOK 状态 | 只能在维护窗由安全/平台在控制台注册 MOK；不关闭 Secure Boot |
| 需要改基线 | 变更单/维护窗 | 改 `prod-profile.env` → 启动 → post-boot → 记录；禁止直接改运行容器 |

## 6. 变更控制

1. 任何基线变更必须有维护窗和变更单。
2. 只改 `~/migrate-assets/prod/prod-profile.env` 及对应 manifest，不同时改多个变量。
3. 改完必须走 `boot-prod.sh` 重启，不能只改文件。
4. 启动后跑 `--post-boot`，保存 `last-boot.json`、自检 TSV/JSON 和 warm 原始 JSON。
5. 性能/质量变更需附 PR 七档、DE c1/c8、GSM8K 与 needle 结果；正式验收前补跑完整 500 题 GSM8K。

## 7. 禁止项

- 禁止自动回滚内核、自动降级 NIC 固件。
- 禁止栈运行时写 ring/buffer/PFC。
- 禁止绕过 `boot-prod.sh` 起栈。
- 禁止未审批修改 netplan、`oom-gate-monitor`、`r3-watchdog-worker`。
- 禁止把 sudo 密码、模型凭据 写入日志、报告、仓库或命令行参数。
- 禁止为手动风扇关闭 Secure Boot。

## 8. 交接签字

| 角色 | 姓名/工号 | 日期 | 备注 |
|---|---|---|---|
| 平台负责人 |  |  | 基线确认 |
| 当班运维 |  |  | 巡检接收 |
| 性能/模型 |  |  | warm/质量门 |
| 网络安全 |  |  | MOK/固件策略 |
