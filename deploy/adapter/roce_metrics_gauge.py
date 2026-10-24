"""I14-C 案 B 四 gauge /metrics 读出面（adapter 侧新模块；0 靴纯开发件，2026-10-24）。

法源
  * 任务书 033-TASKBOOK-V2-20261023.md §T33-08 目标 3（案 B 四 gauge 到 /metrics）。
  * INV-07 §1.3（"没有轮询读出面：/metrics 零 RoCE 面"）、§4.2（建议名/失败模式：
    "gauge 注册抛异常导致 boot/metrics 端点失败；标签基数爆炸；读数与日志口径不一致"）；
    R36-b（案 A+B 合并单臂）。
  * P0 冻结件 033-W1/I14C-C11-P0-FREEZE-20261024.md（gauge 名/键面/刷新节奏冻结）。

性质与红线
  * 测量专用、只读：不改任何路由/调度决策；不改 serve 参；不改引擎镜像。
  * 默认关：DSV41_ROCE_METRICS 未设/0 = 零注册零行为（回退=去键）。
  * fail-safe：注册/刷新任何异常只打 REFUSED 横幅并返回 False，绝不 raise 进
    boot/metrics 端点路径（INV-07 §4.2 失败模式 1 的对置面）。
  * 不 import torch；prometheus_client 惰性导入（缺库=REFUSED 不崩）。

机制（为什么是 Gauge.set 而不是自定义 Collector）
  * 引擎 /metrics 走 prometheus_client 多进程模式（PROMETHEUS_MULTIPROC_DIR；
    引擎自有 gauge 均为 multiprocess_mode="mostrecent" 形，见
    sglang/srt/observability/metrics_collector.py）。多进程模式下，子进程注册的
    自定义 Collector 不会被 /metrics scrape 导出；只有经 multiprocess mmap 落盘的
    Gauge/Counter 值才会被 HTTP 进程的 MultiProcessCollector 聚合读出。
  * 故四 gauge 以 Gauge(multiprocess_mode="all") 注册在计数器所在进程
    （scheduler TP 进程；armed 门=本进程 pynccl 面已挂 roce_ar_stats），
    样本自带 pid 标签 = 每 TP 秩一行（秩间可分）；refresh_gauges() 由案 A
    采样点（每 DSV41_ROCE_SYNC_SAMPLE 个结果一次）低频 set()。
    案 A 关 ⇒ 无刷新源 ⇒ 案 B 保持 0 值不变读数 —— 两键同开为 R36-b 冻结臂形。
  * 对拍：scrape 值 vs 路由横幅/ROCE_I14C_SAMPLE 日志由判读侧
    tools/obs/roce_i14c.py cross_check() 离线对表（gauge 单调计数 ≥ 采样日志
    快照为一致；gauge < log 为不一致）。
"""

import os

ROCE_METRICS_ENV = "DSV41_ROCE_METRICS"
GAUGE_NAMES = (
    "roce_ar_communicators",
    "roce_ar_roce_made",
    "roce_ar_roce_routed",
    "roce_ar_nccl_kept",
)
GAUGE_DOCS = {
    "roce_ar_communicators": "RoCE AR communicators seen (I14-C case B, readonly).",
    "roce_ar_roce_made": "RoCE AR runtimes made (I14-C case B, readonly).",
    "roce_ar_roce_routed": "AR calls routed to the RoCE one-shot kernel (I14-C case B).",
    "roce_ar_nccl_kept": "AR calls kept on NCCL (I14-C case B, readonly).",
}

_gauges = None          # name -> prometheus Gauge（已注册面）
_register_failed = False


def _banner_print(line):
    # stdout 横幅（boot-log 取证面）+ stderr 兜底；不用 logging（避免未配置期丢失）。
    print(f"[roce_metrics_gauge] {line}", flush=True)


def armed():
    """门面：DSV41_ROCE_METRICS=1 且本进程已挂 RoCE 计数面（pynccl.roce_ar_stats）。"""
    if os.environ.get(ROCE_METRICS_ENV, "0").strip() != "1":
        return False
    try:
        import sglang.srt.distributed.device_communicators.pynccl as _pynccl
        return getattr(_pynccl, "roce_ar_stats", None) is not None
    except Exception:
        return False


def install_once(gauge_factory=None, registry=None, banner=None):
    """注册四 gauge（幂等；任何失败=REFUSED 横幅 + False，绝不 raise）。

    gauge_factory/registry 可注入（CPU 单测桩）；缺省=prometheus_client
    默认 REGISTRY，Gauge 用 multiprocess_mode="all"（样本按 pid 分列=每秩一行）。
    """
    global _gauges, _register_failed
    banner = banner or _banner_print
    if _gauges is not None:
        return True
    if _register_failed:
        return False
    if not armed():
        return False
    try:
        if gauge_factory is None:
            from prometheus_client import REGISTRY as _prom_registry
            from prometheus_client import Gauge as gauge_factory
            registry = _prom_registry
        _gauges = {}
        for name in GAUGE_NAMES:
            try:
                _gauges[name] = gauge_factory(
                    name=name,
                    documentation=GAUGE_DOCS[name],
                    labelnames=(),
                    multiprocess_mode="all",
                )
            except (TypeError, ValueError):
                # 桩/无多进程环境（如 PROMETHEUS_MULTIPROC_DIR 未设）：退普通 Gauge。
                _gauges[name] = gauge_factory(
                    name=name, documentation=GAUGE_DOCS[name], labelnames=()
                )
        if registry is not None:
            for name in GAUGE_NAMES:
                try:
                    registry.register(_gauges[name])
                except ValueError:
                    pass  # 已注册（幂等重放）
        banner(
            "ARMED 4 gauges multiprocess_mode=all names=%s"
            % ",".join(GAUGE_NAMES)
        )
        return True
    except Exception as exc:  # pragma: no cover - fail-safe seam
        _gauges = None
        _register_failed = True
        banner(f"REFUSED {type(exc).__name__}: {exc}")
        return False


def refresh_gauges(stats_fn=None):
    """把 roce_ar.gauges() 当前值 set() 进四 gauge（幂等惰性注册；fail-safe）。"""
    global _gauges
    if _gauges is None:
        if not install_once():
            return False
    if stats_fn is None:
        try:
            from roce_ar import gauges as _gauges_src
            stats_fn = _gauges_src
        except Exception as exc:
            _banner_print(f"REFUSED stats-source {type(exc).__name__}: {exc}")
            return False
    try:
        values = stats_fn()
        for name in GAUGE_NAMES:
            v = values.get(name)
            if v is not None:
                _gauges[name].set(int(v))
        return True
    except Exception as exc:  # pragma: no cover - fail-safe seam
        _banner_print(f"REFUSED refresh {type(exc).__name__}: {exc}")
        return False


def install_for_hook(module=None):
    """sitecustomize 钩子入口（metrics_collector exec 期）：armed→注册；绝不 raise。"""
    try:
        if install_once():
            return True
    except Exception as exc:  # pragma: no cover - fail-safe seam
        _banner_print(f"REFUSED hook {type(exc).__name__}: {exc}")
    return False


def registered():
    """观测面（单测/审计用）：当前已注册 gauge 名集。"""
    return tuple(sorted(_gauges)) if _gauges else ()
