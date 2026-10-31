# Copyright 2023-2024 SGLang Team
# Licensed under the Apache License, Version 2.0
"""MM-TRANSIENT 件7：设备侧 mm 足迹账本 + mm 批后分配器卫生（案头 dev 形，纯 stdlib）。

法源：
- docs/incidents/INCIDENT-20261006-C24VL-OPEN26-MMSTAGING-CRUSH.md §五 主会话翻案裁定
  （22G/机真身=**设备侧（UMA 可见）mm 前向不归还足迹的事件性跳变**；修复路由
  「新增件7 分配器卫生（mm 批后 empty_cache+设备侧足迹账本+定长工作区治理；
  ⚠expandable_segments=True 永禁、False 合法）」；件6 账本只计 host 驻留=复现
  本窗不会跳门，与件7 账本互补双面）
- docs/incidents/OPEN26-DECOMPOSITION-20261006.md §五 分解表残差行+§六 修复面
  路由（件7 必增：「不归还」是本族横贯属性（T13 38G→本窗 26.5G），件2/3 只缩
  增量不解决归还；账本形制对齐件6 >4G 告警/>8G 拒新，计数面=torch cached+
  mem_get_info 差分）+§七 遗留缺口（B1 首跳触发子未钉死=OPEN-23-D3 py-spy
  复现窗闭账输入——本模块 on_jump 挂点即其预留）。

═══ 一、引擎接线锚点（基树 image-src-0.2.8/srt，file:line 逐字核证）═══

- 批前采样：scheduler.py:4255 run_batch 头部（forward_ct 记账后、forward launch
  前）。批含 mm 判定=ScheduleBatch.multimodal_inputs（schedule_batch.py:2351
  声明 Optional[List]、:2819 批级装配、:3518 filter/merge 面）非空即 mm 批。
- 批后采样+卫生：scheduler.py:4599 process_batch_result 入口（本函数=「mm 批
  完成回调」：forward 已返回/copy_done 已门控，位于任何图捕获区间之外，见 §三
  安全论证）。
- 拒新 mm 门：scheduler.py:3223 _add_request_to_queue（与件6 hunk1 同一 funnel
  ——两账本互补双面在此汇合：host 驻留门（件6）+设备足迹门（件7）串联放行）。
- 账本 arm（基线）：scheduler.py:1941-1943「Engine init (graph capture, warmups)
  is done; from here on ...」区（triton_load_watch.mark_serving_started 侧近）——
  基线必须取在图捕获/预热之后，否则捕获期段增长污染基线。
- oom 防护位：同 arm 点（进程早期能写就写；失败 fail-open 见 §四）。

═══ 二、账本口径（H5 修正案的账本化）═══

OPEN26 分解卡 H5：MemAvailable=GB10 UMA 全域（含设备侧分配）——水位哨看到的
22G 崩落即设备侧分配的 UMA 可见面。本账本把该面在**批边界**差分化：

    device_used        = total − free            （mem_get_info；UMA 全域面）
    held               = memory_allocated()      （torch 活张量=「工作区类·持有」）
    cached_segments    = reserved − allocated    （缓存分配器已回收段=「缓存类」，
                                                  empty_cache 唯一可归还部分）
    external           = device_used − reserved  （torch 之外域：cuBLAS/cuDNN 新
                                                  形状工作区、驱动钉住内部分=残差
                                                  行「不可分」面的账本显形）

双计数器（B1 首跳分离观测规格，README §八）：
    ws_delta    = Δheld + Δexternal   （工作区类·批后仍不归还者）
    cache_delta = Δcached_segments    （缓存类=卫生键可归还者）
  ⇒ B 段 22G 跳变下次必被账本抓到：单批 device_delta > jump 阈值（缺省 4G）即
    JUMP 横幅（含双计数器切分），mm 累计足迹 >8G 即拒新 mm（fail-closed）——
    灵敏度对拍：水位哨 10s 周期在 B 段 14s 窗内仅 2 采样，账本=每批边界 1 采样
    （B1 覆盖 d2/d3/m1 ≥3 边界）且带 per-batch 归因。

诚实注记：①mem_get_info 同步宿主（基树自证 mqa_logits_utils.py:69、
dsa_indexer.py:998）⇒ 采样只在批边界、非 forward 路径内；②overlap 模式下
process_batch_result 与下一批 forward 并行（scheduler.py:4294 forward_stream_ctx
面），边界采样可能含下一批在飞分配=归因近似（记档不改判读：跳变检测面不受
影响，幅度归因保守）；③text 批足迹单独累计（text_footprint），不触发 mm 门
——needle 43k 工作区面归 OPEN-23 家族，与 mm 门分账（A 段复合段的分离观测
正靠此分账）。

═══ 三、卫生键与图捕获安全位论证（红线内化）═══

DSV41_MM_ALLOC_HYGIENE=off（缺省）/after_batch：
- off ⇒ 零行为（零 CUDA 调用，自测断言）。
- after_batch ⇒ 仅 mm 批完成回调挂 torch.cuda.empty_cache()（text 批谓词先
  短路=零 CUDA 调用）；每次 fire 前后 NVML memGet_info 对拍记档（无静默路径，
  同 FIX-B v2 教训 scheduler.py:1833-1838）。

图捕获安全位三重论证：
1. **捕获窗与服役窗不相交**：本引擎 CUDA 图捕获只在引擎初始化期
   （scheduler.py:1229「Coordinator was created inside ModelRunner.initialize()
   before CUDA graph capture」→ :1943「Engine init (graph capture, warmups) is
   done」）——服役期 process_batch_result 永不在捕获区间内。
2. **replay 不跨批边界回调**：服役期图 replay 局限于 run_batch 内
   model_worker.forward_batch_generation 调用；process_batch_result 在 forward
   返回后执行。empty_cache 只释放缓存分配器**未用段**（已分配块永不释放=下一
   批在飞张量不受影响）；图私有池内存随图存续，不在 empty_cache 释放面。
3. **结构性 belt（不靠调用点自觉）**：每次 fire 前查
   torch.cuda.is_current_stream_capturing()，为 True 即 skip+记档——即使未来
   出现第二调用路径（FIX-B 审计 P2 教训 scheduler.py:1824-1826「铁令例外不应
   依赖调用点自觉」），捕获期也**永不**触发。

empty_cache 铁律和解（scheduler.py:1815-1820 台账）：在役站点=flush_cache
（is_fully_idle 门内）/continue_generation（操作员显式）/_maybe_idle_release
（唯一新增主动例外）。件7 after_batch=台账第四条，由 OPEN-26 §五翻案裁定明令
增设，护栏五重：①env 缺省 off ②仅 mm 批（text 零开销）③捕获期结构性 belt
④每次 fire NVML 前后对拍记档（无静默路径）⑤非压力反应器——只在确定性的
mm 批完成位 fire，无阈值/压强触发回路（三死法 ec0 冻结/ec131072 看门狗拦/
压强+阈值 SIGABRT 皆压力回路形态，本键无此面）。不动 _maybe_idle_release
及其护栏①。

expandable_segments 红线（⚠True 永禁、False 合法不动）：hygiene 启用即解析
PYTORCH_CUDA_ALLOC_CONF/PYTORCH_ALLOC_CONF，见 expandable_segments:True 即
raise（fail-loud 拒启）——判例=weight_cache/daemon.py:404-420 同形解析
（expandable-segments 分配器与 CUDA IPC 不可共）；本件加禁理由=VMM 段语义
改变 empty_cache 归还行为+OPEN-23 RM 锁风暴家族交互面未勘定。

═══ 四、oom 防护位（哨兵先死教训的进程内化）═══

OPEN-26 定谳 3：水位哨与 TP 观察器在碾压中先死（自身被吞、RED 未及打印）
⇒ 本账本内建于调度器进程（随持有者存活）之外，再加 oom_score_adj 防护位：
arm 时尝试写 /proc/self/oom_score_adj=-1000（S2 规格同值，README §七）。
fail-open：写失败（无特权/只读挂载）只记档一次、绝不 raise——防护位失败
不杀伺服，账本仍在役（只是极端宿主压力下可能随宿主死=诚实降级面）。

依赖注入纪律：本模块零 torch 导入（案头可测），CUDA 面经 cuda_api 适配器
注入（memory_allocated/memory_reserved/mem_get_info/empty_cache/
is_current_stream_capturing/memory_stats 六方法协议）；引擎接线 glue 以
torch.cuda 直配，fake 形见 mm_item7_selftest.py。

═══ 五、OPEN-27 谓词 latched 修正案（2026-10-06 事故注册后增补）═══

法源：docs/incidents/INCIDENT-20261006-L0B4-OPEN27-LEDGER-BLINDSPOT.md
（三重失效定谳 §二.1：设备面 begin/end 批谓词失配〔mm→text〕**全部弃差分**
+hygiene 绑同谓词零 fire——B1 观察面注记实证单图单 chunk 形即触，B3 的
−23G 跳变〔该拦的主事件〕全程不入账、>8G 拒门读盲账=永不触发；设计缺陷=
把「防误账」置于「必拦截」之上）。

latched 语义（本版核心变更面）：
- **mm 批结束即锁存**：end_batch 见 begin 谓词=mm 而 end 谓词=text（引擎
  实形：multimodal_inputs 在 process_batch_result 前已被清）即 latched=true
  （保 pre 采样），差分不再弃；
- **下一批边界必结账**：无论下一批何型（text/idle/mm——idle 批/节奏跳过
  批同样先结，累积面全盲正是主失效），先结账上一 mm 批：入账（kind=mm，
  begin 谓词权威）+JUMP 判定+hygiene fire（on_latched_settle 挂点）；顺序律
  =先入账后 fire（record_hygiene 回冲必须作用在含跳变的足迹上，防双重
  回冲/负足迹——「提前 fire 必红」自测面）；
- **hygiene fire 条件改为「上一批含 mm」**（begin 谓词权威）：mm→ANY 均
  fire；零触仅限 text→text 同型；mm→text 失配批的 fire 移交结账边界；
- 弃差分面收缩：原「失配即弃」废止——mm→ANY 永不弃（必拦截优先于防误
  账）；text→mm 反向失配按 begin 权威入 text 分账（不触发 mm 门/fire）；
- 防误账面不退：捕获 belt/NVML 对拍/账本终态归零断言全保（自测沿+OPEN-27
  增例）。
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Optional, Tuple

# ── 键面 ────────────────────────────────────────────────────────────────────
MM_ALLOC_HYGIENE_ENV = "DSV41_MM_ALLOC_HYGIENE"
MM_FP_WARN_ENV = "DSV41_MM_DEVICE_FOOTPRINT_WARN_BYTES"
MM_FP_LIMIT_ENV = "DSV41_MM_DEVICE_FOOTPRINT_LIMIT_BYTES"
MM_FP_JUMP_ENV = "DSV41_MM_DEVICE_FOOTPRINT_JUMP_BYTES"
MM_LEDGER_SAMPLE_EVERY_ENV = "DSV41_MM_LEDGER_SAMPLE_EVERY"
MM_LEDGER_OOM_GUARD_ENV = "DSV41_MM_LEDGER_OOM_GUARD"
MM_LEDGER_OOM_SCORE_ADJ_ENV = "DSV41_MM_LEDGER_OOM_SCORE_ADJ"

HYGIENE_MODES = ("off", "after_batch")

_GIB = 1024 * 1024 * 1024
DEFAULT_FP_WARN_BYTES = 4 * _GIB   # mm 足迹 >4G 告警（对齐件6 缺省形制）
DEFAULT_FP_LIMIT_BYTES = 8 * _GIB  # mm 足迹 >8G 拒新 mm（fail-closed）
DEFAULT_FP_JUMP_BYTES = 4 * _GIB   # 单批跳变 JUMP 横幅阈值（B1 级事件）

# expandable_segments 红线解析面（weight_cache/daemon.py:404-420 判例同形）
_ALLOC_CONF_ENVS = ("PYTORCH_CUDA_ALLOC_CONF", "PYTORCH_ALLOC_CONF")

# 告警横幅周期（件6 同形：防刷屏但保持可见性——宁可重复不可沉默）
_WARN_REPEAT_EVERY = 64

# 批足迹环（首跳触发子观测的 per-batch 归因环；规格详 README §八）
_DELTA_RING_MAXLEN = 64


# ── 键解析（坏值 fail-loud，同件1/件2/件6 键纪律）─────────────────────────


def parse_hygiene_mode(raw: Optional[str] = None) -> str:
    """解析 DSV41_MM_ALLOC_HYGIENE。缺省 off；坏值 raise 列合法值。"""
    if raw is None:
        raw = os.environ.get(MM_ALLOC_HYGIENE_ENV)
    if raw is None or raw.strip() == "":
        return "off"
    val = raw.strip().lower()
    if val not in HYGIENE_MODES:
        raise ValueError(
            f"{MM_ALLOC_HYGIENE_ENV}={raw!r} 非法（合法值：{HYGIENE_MODES}；"
            f"缺省 off）——fail-loud 拒启，不静默回退"
        )
    return val


def parse_bytes_env(raw: Optional[str], default: int, key: str) -> Optional[int]:
    """字节阈值键：缺省=卡定值；0/off/none/false=None（解除）；负/非整数 raise。"""
    if raw is None:
        raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val in ("0", "off", "none", "false"):
        return None
    try:
        n = int(val)
    except ValueError:
        raise ValueError(
            f"{key}={raw!r} 非法（须为非负整数字节或 0/off 解除）——fail-loud 拒启"
        ) from None
    if n < 0:
        raise ValueError(
            f"{key}={raw!r} 为负（须为非负整数字节或 0/off 解除）——fail-loud 拒启"
        )
    return n


def parse_int_env(
    raw: Optional[str], default: int, key: str, lo: int, hi: int
) -> int:
    """整数键（采样节奏/oom_score_adj）：缺省=卡定值；越界/非整数 raise。"""
    if raw is None:
        raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        n = int(raw.strip())
    except ValueError:
        raise ValueError(
            f"{key}={raw!r} 非法（须为 [{lo},{hi}] 整数）——fail-loud 拒启"
        ) from None
    if not (lo <= n <= hi):
        raise ValueError(
            f"{key}={raw!r} 越界（须为 [{lo},{hi}] 整数）——fail-loud 拒启"
        )
    return n


def parse_bool_env(raw: Optional[str], default: bool, key: str) -> bool:
    """布尔键（oom 防护位）：缺省=卡定值；坏值 raise（不静默猜测操作员意图）。"""
    if raw is None:
        raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val in ("1", "on", "true", "yes"):
        return True
    if val in ("0", "off", "false", "no"):
        return False
    raise ValueError(
        f"{key}={raw!r} 非法（须为 0/off/false/no 或 1/on/true/yes）——fail-loud 拒启"
    )


# ── expandable_segments 红线（⚠True 永禁；False 合法不动）─────────────────


def assert_no_expandable_segments(
    environ: Optional[Dict[str, str]] = None,
) -> None:
    """hygiene 启用前置断言：任一 alloc conf 键含 expandable_segments:True 即
    raise（判例=weight_cache/daemon.py:404-420 _assert_ipc_compatible_allocator
    同形解析；本件禁由=OPEN-26 §五「永禁」红线）。False/缺席=合法不动。

    解析语义与判例一致：逗号分隔字段、key:value、空白容忍、大小写折叠。
    """
    env = os.environ if environ is None else environ
    for var in _ALLOC_CONF_ENVS:
        conf = env.get(var, "")
        for f in conf.split(","):
            key, _, value = f.partition(":")
            if (
                key.strip() == "expandable_segments"
                and value.strip().lower() == "true"
            ):
                raise ValueError(
                    f"{var} 含 expandable_segments:True——MM-TRANSIENT 件7 红线"
                    f"永禁（OPEN-26 §五：VMM 段语义改变 empty_cache 归还行为+"
                    f"OPEN-23 RM 锁家族交互未勘定；IPC 不可共判例="
                    f"weight_cache/daemon.py:404-420）。False 合法、无需设置；"
                    f"hygiene fail-loud 拒启"
                )


# ── oom 防护位（哨兵先死教训；fail-open 写）─────────────────────────────────

def try_apply_oom_score_adj(
    value: int = -1000,
    path: str = "/proc/self/oom_score_adj",
    writer: Optional[Callable[[str, str], None]] = None,
) -> Tuple[bool, str]:
    """尝试写 /proc/self/oom_score_adj=value（缺省 -1000=S2 规格同值）。

    fail-open：任何异常吞为 (False, 原因)——防护位失败不杀伺服（账本仍在役，
    只是极端宿主压力下可能随宿主死=诚实降级面）。writer 可注入（自测面）；
    引擎面默认直写文件。
    """
    if not (-1000 <= value <= 1000):
        return False, f"oom_score_adj={value} 越界（内核合法域 [-1000,1000]）"
    w = writer or (lambda p, s: open(p, "w").write(s))
    try:
        w(path, str(value))
    except Exception as e:  # noqa: BLE001  fail-open 律：防护位永不 raise
        return False, f"写 {path} 失败：{type(e).__name__}: {e}"
    return True, f"oom_score_adj={value} 已置（哨兵先死教训的进程内化）"


# ── 采样与差分模型 ──────────────────────────────────────────────────────────


@dataclass
class FootprintSample:
    """单次批边界设备侧足迹采样（cuda_api 六方法协议的物化）。

    peak_* 为可选增强（memory_stats 面，键形 ".current"/".peak" 后缀——
    scheduler.py:1833-1835 v2 定谳注记）：批内峰值即使归还也在账（首跳
    复合段「needle 43k 工作区瞬态」的正观测面）。None=适配器无此面。
    """
    allocated: int          # torch.cuda.memory_allocated()
    reserved: int           # torch.cuda.memory_reserved()
    device_free: int        # mem_get_info()[0]
    device_total: int       # mem_get_info()[1]
    peak_allocated: Optional[int] = None
    peak_reserved: Optional[int] = None

    @property
    def device_used(self) -> int:
        return self.device_total - self.device_free

    @property
    def cached_segments(self) -> int:
        """缓存分配器已回收段=「缓存类」=empty_cache 唯一可归还部分。"""
        return self.reserved - self.allocated

    @property
    def external(self) -> int:
        """torch 之外域（cuBLAS/驱动钉住=残差行「不可分」面的账本显形）。
        理论 ≥0；负值（其他进程释放/口径瞬态不一致）如实保留由差分吸收。"""
        return self.device_used - self.reserved


@dataclass
class BatchFootprintDelta:
    """一批的批前后差分（「不归还足迹」的 per-batch 物化）。

    kind: 'mm' | 'text'——mm 批入 mm 足迹累计（门与告警面），text 批入
    text_footprint（A 段复合段分离观测的分账面，不触发 mm 门）。
    """
    kind: str
    forward_iter: int
    pre: FootprintSample
    post: FootprintSample
    device_delta: int      # Δ(total−free)：UMA 全域面（水位哨同源）
    held_delta: int        # Δallocated：工作区类·仍持有
    cache_delta: int       # Δ(reserved−allocated)：缓存类（卫生可归还）
    external_delta: int    # Δ(external)：工作区类·torch 外钉住
    peak_alloc_delta: Optional[int] = None  # 批内峰值工作区（复合段观测面）
    ts: float = 0.0

    @property
    def ws_delta(self) -> int:
        """双计数器·工作区类=Δheld+Δexternal（批后仍不归还的工作区足迹）。"""
        return self.held_delta + self.external_delta


def sample_cuda(cuda_api: Any) -> FootprintSample:
    """按六方法协议采样一次。peak 面经 memory_stats()（可选提供；异常=None）。"""
    allocated = int(cuda_api.memory_allocated())
    reserved = int(cuda_api.memory_reserved())
    free_b, total_b = cuda_api.mem_get_info()
    peak_a = peak_r = None
    stats = getattr(cuda_api, "memory_stats", None)
    if callable(stats):
        try:
            st = stats() or {}
            va = st.get("allocated_bytes.all.peak")
            vr = st.get("reserved_bytes.all.peak")
            peak_a = int(va) if isinstance(va, int) else None
            peak_r = int(vr) if isinstance(vr, int) else None
        except Exception:  # noqa: BLE001  观测面永不杀批路径
            peak_a = peak_r = None
    return FootprintSample(
        allocated=allocated,
        reserved=reserved,
        device_free=int(free_b),
        device_total=int(total_b),
        peak_allocated=peak_a,
        peak_reserved=peak_r,
    )


# ── 设备侧足迹账本（观察面+fail-closed 门；件6 同门形）─────────────────────


class DeviceFootprintLedger:
    """设备侧（UMA 可见）mm 前向不归还足迹账本。

    与件6 互补双面：件6 记 host 特征驻留（3.88MiB/图级，复现 OPEN-26 不跳门），
    本账本记设备侧足迹（B 段 22G 级，复现 OPEN-26 **必**跳门——22G≫8G limit）。

    记账协议（引擎接线三挂点，§一锚点）：
      arm()                    引擎初始化毕（基线=捕获/预热后）
      begin_batch(has_mm)      run_batch 头（pre 采样；sample_every 节奏门）
      end_batch(has_mm)        process_batch_result 入口（post 采样+差分入账）
      would_admit_mm()         _add_request_to_queue（fail-closed 拒新 mm）
      record_hygiene(...)      卫生 fire 后（释放量回冲足迹）

    门语义（与件6 同形）：只拦**新 mm 请求**、存量继续、文本不经此门、足迹
    回落门自开。与件6 的差异如实记：设备足迹无 per-item 可加性（分配器域），
    故门条件=当前 mm 累计足迹（不含 pending 项外推——那属件2 的单图上界面）。
    """

    def __init__(
        self,
        cuda_api: Any,
        warn_bytes: Optional[int] = DEFAULT_FP_WARN_BYTES,
        limit_bytes: Optional[int] = DEFAULT_FP_LIMIT_BYTES,
        jump_bytes: Optional[int] = DEFAULT_FP_JUMP_BYTES,
        log: Optional[Callable[[str], None]] = None,
        sample_every: int = 1,
    ) -> None:
        if sample_every < 1:
            raise ValueError(f"sample_every={sample_every} 须 ≥1")
        self.cuda_api = cuda_api
        self.warn_bytes = warn_bytes
        self.limit_bytes = limit_bytes
        self.jump_bytes = jump_bytes
        self._log = log or (lambda msg: None)
        self.sample_every = sample_every
        # 状态
        self.armed = False
        self.baseline: Optional[FootprintSample] = None
        self.mm_footprint = 0          # mm 累计不归还足迹（门/告警面；可负→夹 0 判）
        self.text_footprint = 0        # text 分账（复合段观测；不触发 mm 门）
        self.peak_mm_footprint = 0
        self.n_mm_batches = 0
        self.n_text_batches = 0
        self.n_sampled_batches = 0
        self.warn_banners = 0
        self.jump_banners = 0
        self.rejects = 0
        self.hygiene_freed_bytes = 0   # 卫生累计归还（对拍面）
        self._events_since_banner = 0
        self._warn_active = False      # 上升沿+warn/2 滞回（件6 同形）
        self._pre: Optional[FootprintSample] = None
        self._pre_kind: Optional[str] = None
        self._batch_seq = 0
        self._iter = 0
        self.ring: Deque[BatchFootprintDelta] = deque(maxlen=_DELTA_RING_MAXLEN)
        # py-spy 挂点预留（OPEN-23-D3 复现窗：JUMP 横幅时回调，规格详 README §八；
        # 引擎接线 glue 可挂 dump/栈采样——本模块不自带子进程执行）
        self.on_jump: Optional[Callable[[BatchFootprintDelta], None]] = None
        # ── OPEN-27 谓词 latched 面（模块头 §五修正案）──
        self._latched_pre: Optional[FootprintSample] = None  # mm 批锁存 pre
        self._latched_iter = 0
        self.n_latched = 0             # mm→text 失配锁存次数（OPEN-27 观察面）
        self.n_latched_settled = 0     # 结账次数（下一批边界结账面）
        self.last_batch_had_mm: Optional[bool] = None  # 刚完成批的 begin 谓词
        # （hygiene fire 条件读数面：None=本批无权威谓词〔节奏跳过/未采样〕
        #   ⇒ hygiene 回退 glue end 谓词）
        # latched 结账挂点（hygiene 装配：入账+JUMP 毕即 fire——顺序律 §五）
        self.on_latched_settle: Optional[Callable[[BatchFootprintDelta], None]] = None

    # ── 生命周期 ──
    def arm(self) -> FootprintSample:
        """基线采样（锚=引擎初始化毕 scheduler.py:1943 区）。重复 arm=重定基线
        （重置累计——运维面显式动作，非批路径自动）。"""
        self.baseline = sample_cuda(self.cuda_api)
        self.armed = True
        self.mm_footprint = 0
        self.text_footprint = 0
        self.peak_mm_footprint = 0
        self._warn_active = False
        # OPEN-27：重定基线=清未决锁存（挂点接线保留——装配面非批路径）
        self._latched_pre = None
        self.last_batch_had_mm = None
        self._log(
            f"[MM-TRANSIENT 件7] 账本 arm：基线 device_used="
            f"{self.baseline.device_used}B allocated={self.baseline.allocated}B "
            f"reserved={self.baseline.reserved}B（捕获/预热后取基=段增长不污染）"
        )
        return self.baseline

    # ── 批边界协议（OPEN-27 latched 修正案 §五；begin 谓词权威）──
    @property
    def latch_pending(self) -> bool:
        """上一 mm 批差分已锁存未结账（hygiene fire 移交判据）。"""
        return self._latched_pre is not None

    def begin_batch(self, has_mm: bool, forward_iter: Optional[int] = None) -> None:
        """run_batch 头部挂点。sample_every 节奏：非采样批只递增序号（pre 不
        采样 ⇒ end_batch 该批无差分=节奏降载面，跳变检测灵敏度随之降为
        1/sample_every 批——键文档如实载）。

        OPEN-27 latched 结账面：上一 mm 批（mm→text 失配锁存）在本边界**先
        结账**（入账+JUMP+hygiene fire）——无论本批何型（text/idle/mm）、在
        节奏门之前（结账不受 sample_every 降载：累积面全盲正是主失效）。
        本批 pre 在结账+fire 之后采样（fire 归还量不污染本批差分基线）。"""
        self._batch_seq += 1
        if forward_iter is not None:
            self._iter = forward_iter
        else:
            self._iter = self._batch_seq
        if not self.armed:
            return
        self._settle_latched_locked()
        if (self._batch_seq % self.sample_every) != 0:
            self._pre = None
            self._pre_kind = None
            return
        self._pre = sample_cuda(self.cuda_api)
        self._pre_kind = "mm" if has_mm else "text"

    def _record_delta(
        self,
        kind: str,
        forward_iter: int,
        pre: FootprintSample,
        post: FootprintSample,
    ) -> BatchFootprintDelta:
        """差分入账共通面（matched 即结与 latched 结账同律）：ring+分账累计
        +JUMP/WARN 横幅（_after_batch）。kind=begin 谓词权威值。"""
        delta = BatchFootprintDelta(
            kind=kind,
            forward_iter=forward_iter,
            pre=pre,
            post=post,
            device_delta=post.device_used - pre.device_used,
            held_delta=post.allocated - pre.allocated,
            cache_delta=post.cached_segments - pre.cached_segments,
            external_delta=post.external - pre.external,
            peak_alloc_delta=(
                post.peak_allocated - pre.peak_allocated
                if post.peak_allocated is not None
                and pre.peak_allocated is not None
                else None
            ),
        )
        self.ring.append(delta)
        self.n_sampled_batches += 1
        if kind == "mm":
            self.n_mm_batches += 1
            self.mm_footprint += delta.device_delta
            if self.mm_footprint > self.peak_mm_footprint:
                self.peak_mm_footprint = self.mm_footprint
        else:
            self.n_text_batches += 1
            self.text_footprint += delta.device_delta
        self._after_batch(delta)
        return delta

    def _settle_latched_locked(self) -> Optional[BatchFootprintDelta]:
        """结账锁存的上一 mm 批（OPEN-27 latched 律的结账面；无锁存=None）。

        顺序律：入账（kind=mm，begin 谓词权威）→ JUMP/WARN 横幅 → hygiene
        fire（on_latched_settle 挂点）——先入账后 fire：record_hygiene 回冲
        必须作用在含跳变的足迹上（防双重回冲/负足迹=「提前 fire 必红」的
        机理面）。锁存窗=[mm 批 begin → 本边界]：窗内跳变全归 mm 面（含
        批间 idle 间隙+overlap 下一批在飞分配的归因近似，§二诚实注记 ②
        沿）。"""
        if self._latched_pre is None:
            return None
        pre = self._latched_pre
        it = self._latched_iter
        self._latched_pre = None
        post = sample_cuda(self.cuda_api)
        delta = self._record_delta("mm", it, pre, post)
        self.n_latched_settled += 1
        self.last_batch_had_mm = True
        self._log(
            f"[MM-TRANSIENT 件7] latched 结账：上一 mm 批差分入账 device_delta="
            f"{delta.device_delta:+d}B（mm 累计足迹 {self.mm_footprint}B；锁存窗="
            f"[iter {it}→{self._iter}]）——OPEN-27 谓词 latched 律：mm→ANY 转换"
            f"必入账必 fire（弃差分仅限 text→text 同型）"
        )
        if self.on_latched_settle is not None:
            try:
                self.on_latched_settle(delta)
            except Exception as e:  # noqa: BLE001  卫生挂点不杀批路径（同 on_jump 律）
                self._log(
                    f"[MM-TRANSIENT 件7] on_latched_settle 回调异常（吞，"
                    f"卫生面隔离）：{e}"
                )
        return delta

    def end_batch(self, has_mm: bool) -> Optional[BatchFootprintDelta]:
        """process_batch_result 入口挂点：post 采样+差分入账。返回本批差分
        （未 arm/节奏跳过批/mm→text 失配锁存批=None——后者在下一批边界
        _settle_latched_locked 结账时入账）。

        OPEN-27 谓词语义（begin 权威）：
        - mm→mm 一致：本边界即结（原律保留）；
        - mm→text 失配（引擎实形：multimodal_inputs 在 pbr 前已被清）：mm 批
          结束即锁存（latched=true），下一批边界必结账——永不弃（「必拦截」
          优先于「防误账」，事故定谳 §二.1）；
        - text→mm 反向失配：按 begin 权威入 text 分账（不触发 mm 门/fire）；
        - text→text：同型即结（text 分账沿）。"""
        if not self.armed:
            return None
        # 防御性结账：调用序异常（latched 与新 _pre 并存）时先结旧账再处理本批
        if self._latched_pre is not None and self._pre is not None:
            self._settle_latched_locked()
        if self._pre is None:
            self.last_batch_had_mm = None  # 本批无权威谓词面（节奏跳过批）
            return None
        kind = "mm" if has_mm else "text"
        pre_kind = self._pre_kind
        pre, self._pre, self._pre_kind = self._pre, None, None
        post = sample_cuda(self.cuda_api)
        if pre_kind == "mm" and kind == "text":
            # ── OPEN-27 主失效形：mm 批完成但 end 谓词=text ──
            self._latched_pre = pre
            self._latched_iter = self._iter
            self.n_latched += 1
            self.last_batch_had_mm = True
            self._log(
                f"[MM-TRANSIENT 件7] begin/end 批 mm 谓词不一致（mm→text）：mm "
                f"批完成即锁存差分（latched=true，pre device_used="
                f"{pre.device_used}B iter={self._iter}）——下一批边界先结账"
                f"（入账+JUMP 判定+hygiene fire；OPEN-27 修复：弃差分仅限 "
                f"text→text 同型，本方向永不弃）"
            )
            return None
        if pre_kind == "text" and kind == "mm":
            self._log(
                "[MM-TRANSIENT 件7] begin/end 批谓词反向失配（text→mm）：begin "
                "谓词权威，按 text 批入 text 分账（不触发 mm 门/hygiene fire）"
            )
        self.last_batch_had_mm = pre_kind == "mm"
        return self._record_delta(pre_kind, self._iter, pre, post)

    # ── 横幅/跳变/挂点 ──
    def _after_batch(self, delta: BatchFootprintDelta) -> None:
        # JUMP 横幅（单批跳变>B1 级阈值；kind 双面——A 段 text 复合段同可观测）
        if self.jump_bytes is not None and delta.device_delta > self.jump_bytes:
            self.jump_banners += 1
            self._log(
                f"[MM-TRANSIENT 件7] JUMP {delta.kind} 批 device_used 单批跳变 "
                f"+{delta.device_delta}B > {self.jump_bytes}B "
                f"({MM_FP_JUMP_ENV})；双计数器切分：工作区类 ws="
                f"{delta.ws_delta}B（held={delta.held_delta}B + external="
                f"{delta.external_delta}B）缓存类 cache={delta.cache_delta}B"
                + (
                    f"；批内峰值工作区 Δpeak_alloc={delta.peak_alloc_delta}B"
                    if delta.peak_alloc_delta is not None
                    else ""
                )
                + f"（B1 首跳分离观测面；OPEN-23-D3 py-spy 复现窗触发信号）"
            )
            if self.on_jump is not None:
                try:
                    self.on_jump(delta)  # 挂点预留：复现窗 glue 挂栈采样
                except Exception as e:  # noqa: BLE001  观测挂点永不杀批路径
                    self._log(
                        f"[MM-TRANSIENT 件7] on_jump 回调异常（吞，观测面隔离）：{e}"
                    )
        # WARN 横幅（mm 累计足迹>4G；上升沿+周期再报+warn/2 滞回=件6 同形）
        self._events_since_banner += 1
        if self.warn_bytes is None:
            return
        fp = max(self.mm_footprint, 0)
        if fp > self.warn_bytes:
            if (not self._warn_active) or (
                self._events_since_banner >= _WARN_REPEAT_EVERY
            ):
                self._warn_active = True
                self.warn_banners += 1
                self._events_since_banner = 0
                self._log(
                    f"[MM-TRANSIENT 件7] WARN 设备侧 mm 不归还足迹累计 "
                    f"{self.mm_footprint}B（clamp {fp}B）> {self.warn_bytes}B "
                    f"({MM_FP_WARN_ENV})；mm 批={self.n_mm_batches} "
                    f"text 分账={self.text_footprint}B peak="
                    f"{self.peak_mm_footprint}B hygiene 累计归还="
                    f"{self.hygiene_freed_bytes}B（OPEN-26 B 段 22G 级跳变的"
                    f"运行时可观测化；账本随调度器进程存活）"
                )
        elif fp < self.warn_bytes // 2:
            self._warn_active = False  # 滞回复位（防边界抖动刷屏）

    # ── 卫生回冲 ──
    def record_hygiene(
        self,
        free_before: int,
        free_after: int,
        reserved_before: int,
        reserved_after: int,
    ) -> int:
        """卫生 fire 后调用：NVML 对拍释放量回冲 mm 足迹（门自开面）。

        归因诚实注记：empty_cache 归还的是**全局**缓存段（可能含 text 批出身
        段），回冲全部记 mm 面=对门保守偏松（早开）；如需精确归因须段级遥测
        （OPEN-23-D3 面），案头形不主张。
        """
        released = max(0, free_after - free_before)
        if released:
            self.mm_footprint -= released
            self.hygiene_freed_bytes += released
            self._log(
                f"[MM-TRANSIENT 件7] hygiene 归还 {released}B（reserved "
                f"{reserved_before}B→{reserved_after}B）——mm 足迹回冲至 "
                f"{self.mm_footprint}B（NVML memGetInfo 前后对拍记档，无静默路径）"
            )
            self._after_hygiene_gate_reopen_check()
        return released

    def _after_hygiene_gate_reopen_check(self) -> None:
        # 门在 would_admit_mm 时按当前足迹判（函数式），此处只补滞回复位检查
        if self.warn_bytes is not None and max(self.mm_footprint, 0) < self.warn_bytes // 2:
            self._warn_active = False

    # ── fail-closed 门（件6 同门形；只拦新 mm）──
    def would_admit_mm(self) -> Tuple[bool, str]:
        """新 mm 请求准入门。mm 累计足迹（clamp ≥0）> limit 即拒（无 pending
        外推——设备足迹非 per-item 可加，注见类 docstring）。文本不经此门
        （调用面=mm 分支；缺省 limit=8G：B 段 22G ⇒ B1 中段即拒 m2）。"""
        if self.limit_bytes is None or not self.armed:
            return True, ""
        fp = max(self.mm_footprint, 0)
        if fp <= self.limit_bytes:
            return True, ""
        self.rejects += 1
        reason = (
            f"DSV41 设备侧 mm 不归还足迹累计 {self.mm_footprint}B（clamp {fp}B）"
            f" > limit={self.limit_bytes}B ({MM_FP_LIMIT_ENV})——fail-closed 拒新 "
            f"mm 请求（OPEN-26 B 段 22G/机碾压防护；存量请求不受影响；hygiene "
            f"归还后门自开）"
        )
        self._log(f"[MM-TRANSIENT 件7] REJECT {reason}")
        return False, reason

    # ── 观测 ──
    def snapshot(self) -> dict:
        return {
            "armed": self.armed,
            "baseline": (
                None if self.baseline is None
                else {
                    "device_used": self.baseline.device_used,
                    "allocated": self.baseline.allocated,
                    "reserved": self.baseline.reserved,
                }
            ),
            "mm_footprint": self.mm_footprint,
            "text_footprint": self.text_footprint,
            "peak_mm_footprint": self.peak_mm_footprint,
            "n_mm_batches": self.n_mm_batches,
            "n_text_batches": self.n_text_batches,
            "n_sampled_batches": self.n_sampled_batches,
            "warn_bytes": self.warn_bytes,
            "limit_bytes": self.limit_bytes,
            "jump_bytes": self.jump_bytes,
            "warn_banners": self.warn_banners,
            "jump_banners": self.jump_banners,
            "rejects": self.rejects,
            "hygiene_freed_bytes": self.hygiene_freed_bytes,
            "ring_len": len(self.ring),
            # OPEN-27 latched 观察面
            "latch_pending": self.latch_pending,
            "n_latched": self.n_latched,
            "n_latched_settled": self.n_latched_settled,
        }


# ── mm 批后卫生（批完成回调挂 empty_cache；图捕获安全位 §三论证）──────────


@dataclass
class HygieneRecord:
    """一次 hygiene fire 的 NVML 对拍记录（无静默路径的物化）。"""
    freed_bytes: int                 # free_after − free_before（≥0 才入账）
    free_before: int
    free_after: int
    reserved_before: int
    reserved_after: int
    allocated_before: int
    allocated_after: int
    ts: float = 0.0
    capture_skipped: bool = False


class AllocHygienePolicy:
    """卫生策略：after_batch=mm 批完成回调挂 torch.cuda.empty_cache()。

    零开销契约（自测断言面）：
      - mode=off：after_batch 任何输入零 CUDA 调用（latched 挂点亦不装配）；
      - text→text 同型批（零触面）：零 CUDA 调用；
      - mm 批：mem_get_info×2+empty_cache×1+memory_reserved/allocated×2
        （对拍记档面）。

    OPEN-27 fire 条件修正（模块头 §五）：fire=「上一批含 mm」——begin 谓词
    权威（ledger.last_batch_had_mm，mm→ANY 均 fire；零触仅限 text→text），
    不再绑 glue end 谓词（B1 注记实证其于 pbr 前已被清=零 fire 主失效）。
    mm→text 失配批（ledger.latch_pending）：fire 移交结账边界（on_latched_
    settle 挂点，入账+JUMP 毕即 fire——顺序律；提前 fire 必红）。

    捕获期 belt：is_current_stream_capturing()=True ⇒ skip+记档（结构性红线
    「禁在图内/捕获期触发」——不靠调用点自觉，§三论证第 3 条）。
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        cuda_api: Any = None,
        ledger: Optional[DeviceFootprintLedger] = None,
        log: Optional[Callable[[str], None]] = None,
        environ: Optional[Dict[str, str]] = None,
    ) -> None:
        self.mode = parse_hygiene_mode(mode)
        self.cuda_api = cuda_api
        self.ledger = ledger
        self._log = log or (lambda msg: None)
        # 统计
        self.n_mm_fires = 0
        self.n_text_zero_touch = 0
        self.n_off_zero_touch = 0
        self.n_capture_skips = 0
        self.total_freed_bytes = 0
        self.n_latched_deferred = 0      # mm→text 失配批 fire 移交计数
        self.n_latched_settle_fires = 0  # latched 结账边界 fire 计数（B4 发间
                                         # 断言读数面：fire=0 连续两发即红）
        self.records: Deque[HygieneRecord] = deque(maxlen=64)
        if self.mode != "off":
            # 红线前置断言（fail-loud 拒启；off 模式零行为故不断言）
            assert_no_expandable_segments(environ)
            if cuda_api is None:
                raise ValueError(
                    f"{MM_ALLOC_HYGIENE_ENV}={self.mode} 须提供 cuda_api 适配器"
                )
            if ledger is not None:
                # OPEN-27 latched 结账 fire 挂点（off 零行为=不装配）
                ledger.on_latched_settle = self._fire_on_latched_settle

    def after_batch(self, has_mm: bool, ts: float = 0.0) -> Optional[HygieneRecord]:
        """mm 批完成回调挂点（process_batch_result 入口，pre/post 采样之后）。

        fire 判定（OPEN-27 §五，begin 谓词权威）：
          ledger.latch_pending        ⇒ fire 移交结账边界（本调用零 fire 记
                                      n_latched_deferred——提前 fire 必红）；
          ledger.last_batch_had_mm
            =True  ⇒ fire（mm→ANY 律：刚完成批 begin=mm）；
            =False ⇒ 零触（text→text 同型面）；
            =None  ⇒ 回退 glue end 谓词 has_mm（本批无权威面=节奏跳过批）。
        无 ledger 面（T3 形）沿 has_mm 直判。返回 HygieneRecord（fire/skip 均
        Return 记录；off/零触/移交=None 零记录零调用）。
        """
        if self.mode == "off":
            self.n_off_zero_touch += 1
            return None  # 卫生键 off=零行为（零 CUDA 调用）
        fire = has_mm
        if self.ledger is not None:
            if self.ledger.latch_pending:
                self.n_latched_deferred += 1
                return None  # fire 移交结账边界（顺序律：先入账后 fire）
            authoritative = self.ledger.last_batch_had_mm
            if authoritative is not None:
                fire = authoritative  # begin 谓词权威（mm→ANY fire/text→text 零触）
        if not fire:
            self.n_text_zero_touch += 1
            return None  # text→text 同型批零开销（谓词先短路）
        return self._fire_locked(ts)

    def _fire_on_latched_settle(self, delta: BatchFootprintDelta) -> None:
        """账本 latched 结账挂点（on_latched_settle）：入账+JUMP 已毕，此处
        fire（mm→ANY 律的 fire 面；B4 发间断言读数=n_latched_settle_fires）。"""
        rec = self._fire_locked(0.0)
        if rec is not None and not rec.capture_skipped:
            self.n_latched_settle_fires += 1

    def _fire_locked(self, ts: float) -> HygieneRecord:
        """fire 共通体：belt→NVML 前对拍→empty_cache→NVML 后对拍→记档→
        足迹回冲（after_batch 直发与 latched 结账挂点同律，无静默路径）。"""
        # 捕获期 belt（结构性红线：禁在图内/捕获期触发）
        if self.cuda_api.is_current_stream_capturing():
            self.n_capture_skips += 1
            rec = HygieneRecord(
                freed_bytes=0, free_before=0, free_after=0,
                reserved_before=0, reserved_after=0,
                allocated_before=0, allocated_after=0,
                ts=ts, capture_skipped=True,
            )
            self.records.append(rec)
            self._log(
                "[MM-TRANSIENT 件7] hygiene skip：is_current_stream_capturing()"
                "=True（结构性 belt——捕获期永不触发；此况不应出现于服役路径，"
                "出现即调用位违约，须上报）"
            )
            return rec
        # fire：NVML 前对拍 → empty_cache → NVML 后对拍（无静默路径）
        free_b, _tot_b = self.cuda_api.mem_get_info()
        reserved_b = int(self.cuda_api.memory_reserved())
        allocated_b = int(self.cuda_api.memory_allocated())
        self.cuda_api.empty_cache()
        free_a, _tot_a = self.cuda_api.mem_get_info()
        reserved_a = int(self.cuda_api.memory_reserved())
        allocated_a = int(self.cuda_api.memory_allocated())
        freed = max(0, free_a - free_b)
        self.n_mm_fires += 1
        self.total_freed_bytes += freed
        rec = HygieneRecord(
            freed_bytes=freed,
            free_before=free_b,
            free_after=free_a,
            reserved_before=reserved_b,
            reserved_after=reserved_a,
            allocated_before=allocated_b,
            allocated_after=allocated_a,
            ts=ts,
        )
        self.records.append(rec)
        self._log(
            f"[MM-TRANSIENT 件7] hygiene fire：empty_cache @mm 批边界 归还 "
            f"{freed}B（free {free_b}B→{free_a}B；reserved {reserved_b}B→"
            f"{reserved_a}B；allocated {allocated_b}B→{allocated_a}B 不变"
            f"——只动缓存段不动活张量；NVML 对拍记档）"
        )
        if self.ledger is not None:
            self.ledger.record_hygiene(free_b, free_a, reserved_b, reserved_a)
        return rec

    def snapshot(self) -> dict:
        return {
            "mode": self.mode,
            "n_mm_fires": self.n_mm_fires,
            "n_text_zero_touch": self.n_text_zero_touch,
            "n_off_zero_touch": self.n_off_zero_touch,
            "n_capture_skips": self.n_capture_skips,
            "total_freed_bytes": self.total_freed_bytes,
            # OPEN-27 latched 面
            "n_latched_deferred": self.n_latched_deferred,
            "n_latched_settle_fires": self.n_latched_settle_fires,
        }


# ── 接线装配（引擎 glue 面；键全缺省即零行为）──────────────────────────────


def build_from_env(
    cuda_api: Any,
    log: Optional[Callable[[str], None]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> Tuple[DeviceFootprintLedger, AllocHygienePolicy, Optional[int], bool]:
    """一键装配（引擎 glue 单入口）。

    返回 (ledger, hygiene, oom_score_adj 值或 None, oom_guard_enabled)。
    oom 防护位写入由 glue 在 arm 点显式调 try_apply_oom_score_adj（失败
    fail-open 只记档）。账本恒建（观察面独立于卫生键——同件6「stock 模式
    账本照常在役」律）。
    """
    lg = log or (lambda m: None)
    ledger = DeviceFootprintLedger(
        cuda_api=cuda_api,
        warn_bytes=parse_bytes_env(None, DEFAULT_FP_WARN_BYTES, MM_FP_WARN_ENV),
        limit_bytes=parse_bytes_env(None, DEFAULT_FP_LIMIT_BYTES, MM_FP_LIMIT_ENV),
        jump_bytes=parse_bytes_env(None, DEFAULT_FP_JUMP_BYTES, MM_FP_JUMP_ENV),
        log=lg,
        sample_every=parse_int_env(
            None, 1, MM_LEDGER_SAMPLE_EVERY_ENV, 1, 10**9
        ),
    )
    hygiene = AllocHygienePolicy(
        mode=None, cuda_api=cuda_api, ledger=ledger, log=lg, environ=environ
    )
    guard_on = parse_bool_env(None, True, MM_LEDGER_OOM_GUARD_ENV)
    adj = (
        parse_int_env(None, -1000, MM_LEDGER_OOM_SCORE_ADJ_ENV, -1000, 1000)
        if guard_on else None
    )
    return ledger, hygiene, adj, guard_on
