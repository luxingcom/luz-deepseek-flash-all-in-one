#!/usr/bin/env python3
"""bench 族 URL 参数与拒起面共享构造处（EQ-11：量具参数面统一）。

背景（部署篇-36 → EQ-11）：同族量具的 URL 参数互不相同——qeval `run --url` 要
全路径（…/v1/chat/completions）、sd_bench `--base-url` 到 /v1、gsm8k `--base`
不带 /v1（且不识别 --base-url）——写错时 argparse 拒起被管道 grep 吃成空输出。
本模块把两件事收敛到**唯一构造处**（各量具不再各自拼 URL / 各自报错）：

  1) `v1_base()` / `chat_completions()`：URL 三形通吃归一——origin
     （http://h:p）、v1 基（http://h:p/v1）、全路径（…/v1/chat/completions）
     一律归一为 v1 基；请求 URL = v1 基 + "/chat/completions"。错 URL 形
     （非 http(s)、无 host）→ 首行 `ERROR[<prog>]: …` 到 stderr、exit 2。
  2) `BenchArgumentParser.error()`：argparse 拒起时**首行**打可 grep 错误摘要
     （`ERROR[<prog>]: <argparse message>`）到 stderr、exit 2——管道里
     `… 2>&1 | grep ERROR` 必命中；取代默认的「usage 多行在前、错误在末行」
     形态（后者在管道下变静默空输出，量具命令看着像跑过了）。

兼容纪律（冻结量具面）：对历史上**正确**的传参（sd_bench 带 /v1、gsm8k 不带
/v1、qeval 全路径），归一后的请求 URL 与旧版逐字节相同；只把历史上必 404/405
的错形（sd_bench 全路径、gsm8k 带 /v1、qeval 根路径）修复为可用。输出 schema
零变更。

自检：sd_bench --selfcheck §EQ-11 与 qeval --selftest S11-S13 直接驱动本模块
（三形归一、错形必红、首行 ERROR 摘要、旧正确形逐字节不变）。
"""
import argparse
import sys
from urllib.parse import urlsplit

ERR_PREFIX = "ERROR"  # 拒起首行错误摘要的稳定可 grep 前缀


def fail(prog, message, code=2):
    """显式失败（EQ-11 契约）：首行 `ERROR[<prog>]: <message>` → stderr，exit code（非零）。"""
    print(f"{ERR_PREFIX}[{prog}]: {message}", file=sys.stderr, flush=True)
    sys.exit(code)


class BenchArgumentParser(argparse.ArgumentParser):
    """argparse 拒起面统一：首行可 grep 错误摘要 + 显式 exit 2（usage 移到摘要之后）。

    子命令解析器自动同类（add_subparsers 的 parser_class 缺省=type(self)），
    故 qeval 的 run/compare 子命令拒起同享本契约。"""

    def error(self, message):
        print(f"{ERR_PREFIX}[{self.prog}]: {message}", file=sys.stderr, flush=True)
        self.print_usage(sys.stderr)
        self.exit(2)


def v1_base(value, *, flag, prog):
    """URL 参数归一（共享构造处）：三形通吃 → v1 基（scheme://host[:port]/v1）。

    规则（唯一拼接律）：尾 `/` 剥离；尾 `/chat/completions` 剥离；路径为空
    （origin 形）补 `/v1`；其余路径（自定义挂载）原样保留自担。错形（scheme
    非 http/https 或 host 为空）→ fail()（首行 ERROR 摘要、exit 2）。"""
    v = (value or "").strip()
    sp = urlsplit(v)
    if sp.scheme not in ("http", "https") or not sp.netloc:
        fail(prog, f"{flag} 值不是合法 http(s) URL（got {value!r}）——接受三形："
                   "origin（http://127.0.0.1:8899）/ v1 基（http://127.0.0.1:8899/v1）/"
                   "全路径（http://127.0.0.1:8899/v1/chat/completions）")
    path = sp.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    if not path:
        path = "/v1"
    return f"{sp.scheme}://{sp.netloc}{path}"


def chat_completions(value, *, flag, prog):
    """请求 URL 构造（共享构造处）：v1_base(value) + "/chat/completions"。"""
    return v1_base(value, flag=flag, prog=prog) + "/chat/completions"
