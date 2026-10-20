# serve_flags_gate — 起栈链接线闸门（issue #4 采纳件）

> 用途：证明**正在跑的 serve 进程 argv 里真的接了旗标**，而不是"镜像里支持"或
> "env/源码里出现过"。issue
> [#4](https://github.com/luxingcom/luz-deepseek-flash-all-in-one/issues/4)
> 的根因分类：`--tool-call-parser` / `--enable-cache-report` 这类接线漏了，
> `/health` 仍 200、`/v1/models` 照常，**没有任何红灯**——本闸门把"接线"变成可断言对象。

## 判据

| 旗标 | 期望 | 缺了会怎样 |
|---|---|---|
| `--tool-call-parser deepseekv41` | 参数与值**成对精确匹配**（`deepseek-v41` 连字符形判红） | DeepSeek 原生 DSML 工具调用以纯文本吐出，静默降级 |
| `--enable-cache-report` | flag 存在 | `usage.prompt_tokens_details.cached_tokens` 恒 `null`，面板缓存命中恒 0% |

判据全程用 `case` 匹配，**不经 `cmd | grep -q` 取 rc**（防管道末端假绿）；任一份取证
缺失即整体 `rc=1`；取证失败（容器不在/读不到 argv）`rc=2`（fail-closed）。

## 用法

```bash
# 1) 容器内 argv（head + worker 必须各查，R7：角色差异）
tools/serve_flags_gate.sh --container r3boot-head --container r3boot-worker

# 2) 已落盘的 argv（NUL 分隔；离线复核/取证包）
tools/serve_flags_gate.sh --argv-file /tmp/r3boot-head.argv

# 3) 运行时自省（更强：能抓 argv 写了但没绑定的值）
tools/serve_flags_gate.sh --api http://127.0.0.1:30000

# 4) 闸门自检（R1-R7 反向用例，不需要活栈）
tools/serve_flags_gate.sh --self-test
```

退出码：`0`=全过 / `1`=有 FAIL / `2`=用法或取证失败。

## R1-R7 覆盖（issue #4 §3）

| # | 用例 | 自检期望 |
|---|---|---|
| R1 | 删 `--tool-call-parser` | `rc≠0` |
| R2 | 删 `--enable-cache-report` | `rc≠0` |
| R3 | 静态串在源码/注释、argv 不在 | `rc≠0` |
| R4 | 正控制：旗标都在 | `rc=0` |
| R5 | 值拼错（`deepseek-v41`） | `rc≠0` |
| R6 | 判据不依赖管道末端 rc | 直接判据仍 `rc≠0` |
| R7 | head 接了、worker 没接 | 整体 `rc≠0` |

`--self-test` 逐条跑并输出 PASS/FAIL；这是闸门自身的判别力证明，可随交付面复跑。

## 边界

- 本工具**只读**，不进恢复链、不重启服务（避免自锁）。
- 它是**交付面补充件**，不改产线 boot 快照（`deploy/bin/r3-boot-arm.sh` 保持
  与产线同体；接线由 SERVER_ARGS 固定面承载，闸门负责证伪）。
- 容器内 `/proc/1/cmdline` 取的是 PID 1（容器入口即 serve 进程）；若以
  `sh -c` 包壳启动，PID 1 是 shell，应改用 `--api` 模式或取实际 serve PID。
