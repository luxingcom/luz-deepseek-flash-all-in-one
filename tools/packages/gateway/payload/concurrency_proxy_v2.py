#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
concurrency_proxy_v2.py — vLLM 流式感知并发网关（v2.0-rc3，2026-09-06）

rc3.8.6 相对 rc3.8.5 的增强（GW-PATCH-20261015 窗；设计输入=032-ADDENDUM §十一
  A10〔GitHub issue #3，contributor waterliu1981 已落地形〕）：
  /v1/models 响应侧容量广播（②-a）——ADVERTISE_MODEL_CAPACITY=1 时，GET
  /v1/models 与 /v1/models/{id} 的响应体在每个 model 条目补客户端模型发现四键：
  context_length / context_window / max_input_tokens 三扁平键 + limit.context
  嵌套键，取值=条目自带 max_model_len（MODELS_CONTEXT_LEN=0 缺省——引擎真值，
  不写死；红线：声明恒=引擎真值，「调大声明消本地检测」=禁）。缺 max_model_len
  的条目（如 LoRA 行）跳过不写（防 null 污染）。动因：harness 类客户端
  （deepseek-harness/llm-pi-ai）读四扁平字段判定上下文窗，读不到 ⇒ 落默认窗
  262144（低估引擎真值 600000 2.3 倍）⇒ 已完成的成功响应被判
  CONTEXT_WINDOW_EXCEEDED 整轮丢弃 + clampMaxTokensToContext 负数 ⇒ 每请求被
  改写 max_tokens:1（空参数工具调用截断链）。
  三硬门：**纯增量**（不改上游响应本身，仅缺键时补；已有键零触碰——与 ②-b 引擎
  原生面叠加零冲突）/ **幂等**（已带字段=逐字节原样返回）/ **fail-open**（非法
  JSON / 非目标路径 / 无容量来源=原样透传，绝不因本变换回 500）。
  落位=relay_get()（GET/HEAD 免并发槽路，rc3.8.5 全局鉴权门之后调用=不新增绕过
  面）；HEAD 无体=原样透传；缺省 0=行为逐字节零变化（rc3.8.5 等价，
  tests/test_rc386.py 用例 d 判别力电池执法）；引擎零改（直连 8899 逐字节不变）。

rc3.8.5 相对 rc3.8.4 的增强（AUTH-DEPLOY-20261014 执行窗；设计输入=G1 调查档
  §F 插入点/§G 建议，主会话裁定双层收紧）：
  1. 全局鉴权门 GW_REQUIRE_AUTH（缺省 0=休眠原行为，env 可关）：=1 时除
     /health（探针豁免面——guardctl/daily-smoke 前置依赖语义不变）与 /gw/*
     （维持原门）外一切路径一切方法须 Bearer GW_API_KEY（复用 gw_authorized
     恒时比较语义）。动因：r3 栈引擎 8899 无 --api-key（G1 §B5/§B6），rc2
     「业务路径不代理鉴权（上游 VLLM_API_KEY 负责）」设计假设失效——推理面
     在本门收键。门位置=dispatch 统一分流层（GET/HEAD 分支与 POST
     acquire_or_none 之前、body 读取之前）：流式（L403 handle_stream）与非
     流式（relay_plain）共用同一前置门，GET 名录面（/v1/models）与
     /metrics（prometheus 侧配 bearer_token）同门覆盖；401 计 auth_rejected。
     Authorization 向引擎透传语义不变（fwd_headers 不动）。
  2. 模型名校验 GW_ALLOWED_MODELS（缺省 "deepseek-v4.1-flash"；显式空串=关）：
     POST body 顶层 "model" 字符串值不在白名单 → 404 OpenAI 形错误体
     （model_not_found；对齐 02 网关 _model_not_found 形）。实现=b'"model"'
     字节预检（rc3.4 prefilter 模式——无该键请求零 parse 零成本；非法 JSON
     原样转发走原逻辑）；多模型逗号分隔；别名归一不做（8003 层职责——单一
     事实源）。计 models_rejected。插入点=POST 分支 maybe_inject 之后（G1
     §F-2）。GW_REQUIRE_AUTH=0 且 GW_ALLOWED_MODELS 置空 ⇒ 与 rc3.8.4 行为
     逐字节等价（休眠门，tests/test_rc385.py 用例 d 执法）。

rc3.8.4 相对 rc3.8.3 的修正（G2-RESTORE-20261014 S5 验证窗，2026-10-14）：
  - V2b 413 判读线修复：dispatch 兜底 except 吞 aiohttp HTTPException
    （HTTPRequestEntityTooLarge=64MiB client_max_size 帽）→错译 500；修=语义类异常
    透传（except web.HTTPException: raise）→帽上 body 得规范 413（V2 卡「>64MB 一发
    验 413 优雅」判读线闭合；journal traceback :791 实证）。
rc3.8.3 相对 rc3.8.2 的修正（GW-INFRAS-QUALITY-AUDIT-20261014 修复窗 A6/B1，2026-10-14）：
  A6 relay_get 静默 502 零留痕（except Exception: return 502——/metrics 502 风暴期
      〔引擎停机窗〕成因零可考，audit §2.3）→ 补 log.warning（method/raw_path/异常
      repr，与 relay_plain 同形）；成因留痕=下次停机窗 journal 可判读。
  B1 body_key 前 1MB 帽撤除（audit §1.3 治本定谳）：body 在 dispatch :775 已全量
      驻留，帽的「防全量驻留」注释目标=伪收益（只省一次哈希扫描 ~2ms/MB），代价=
      同图等长异问的 VL 大 body 前缀碰撞→第二发误 429（Retry-After 60s）。全量
      sha256 后 DEDUP=1 可安全复开 VL 车道（呈裁 C2/C3 位）。确定性/键稳定性不受
      影响；开销同量级（audit §4.1③：~2ms/MB）。
  本版=包内修复领先形：01 在役仍 rc3.8.2（e1a01162）——重启/部署窗吸收承载
  （GW-AUDIT A1 在役值/A10 密钥迁出同窗）；吸收时 sources.tsv 锚同日重钉。

rc3.8.2 相对 rc3.8.1 的修正（第二轮交叉审查 L1，2026-09-24）：
  L1 泵送通用异常（中途读失败：RST/ClientPayloadError 等）只 log + upstream_errors，
     不入错误帧 ⇒ producer finally 补干净 DONE，客户端「部分内容 + 正常收尾」
     静默截断（与 rc3.8 修掉的 idle 分支同型，仅漏了这一条）。现补固定文案
     错误帧；与 02 v2.1.3 的 P2-6 成对，端到端不再有静默截断路径。

rc3.8.1 相对 rc3.8 的修正（交叉审查 P2 四条，2026-09-24 深夜）：
  P2-1 错误帧/DONE 入队用 put_nowait，队列满即抛 QueueFull → 被 pump 级
      except Exception 捕获并误计 upstream_errors，且客户端收不到错误帧
      （静默截断回归 rc3.4-A 老病）。修复：统一走 put_frame()，队列满则丢帧
      + 计 queue_full_drops + 留痕，绝不抛出。
  P2-2 tx（已写客户端字节）含心跳注释帧（15B/次，600s 约 1.8KB）→ 计数排除
      HEARTBEAT，使 chunk_idle_bytes_sent 与日志 tx= 反映真实交付字节。
  P2-3 骨架帧缺 created/model（OpenAI ChatCompletionChunk 必填字段，严格解析器
      可能报错）→ 补 created=0 / model=gateway-error；docstring 措辞纠正为
      「AI SDK 系按 choices 严格解析、openai-python 可 lenient 解析」。
  P2-4 本文档段插序违反「最新在顶」惯例 → rc3.8 段与 rc3.8.1 段统一上移。

rc3.8 相对 rc3.7.1 的修正（zcode 流中断 09-24 RCA —— 我方四条中的代理侧三条）：
  O-1 chunk idle 断流零可观测（计数器自增但无日志：受害请求/已发字节不可考）→
      断流瞬间 log.warning（rx=引擎侧已读 / tx=已写客户端字节、耗时）+
      METRICS 增 chunk_idle_bytes_sent（累计）。
  O-2 CHUNK_IDLE_TIMEOUT 默认 180→600：实测单轮 200–420s（14.5 万 token
      reasoning=max），引擎 decode 停顿/排队可超 180s 误伤长生成；env 可调保留。
  O-3 错误帧裸 {"error":…} 会把严格解析 choices 的客户端打出
      errorPhase=stream/reason=unknown（zcode 实测指纹）→ 帧体补 OpenAI
      chunk 骨架（id/object/choices[0].delta），error 键原样保留。
  （客户端侧：长上下文压缩 / reasoningLevel 下调 —— 不在本文件范围）

rc3.7.1 相对 rc3.7（交叉审核 P2-A 修复，2026-09-24）：
  sanitize 的 walk + 重序列化整块包 try/except：孤立代理项（U+D800，
  UnicodeEncodeError）与超深嵌套（RecursionError）此前会把承诺的 fail-open
  变成 500 ⇒ 现在语义收紧为「任何无法安全净化的 body 一律原样返回」。
  同步带入：warning 附 request.path；新增 /gw/metrics 计数键
  image_sanitize_requests（请求数，与发生次数键互补）。

rc3.7 相对 rc3.6.1（2026-09-24 会话中断 RCA 后修复）：
  图像占位符净化 sanitize_image_placeholders：客户端（WorkBuddy CLI）在后续
  轮次把历史图像序列化为字面文本 '<｜deepseek_image｜>'，引擎
  encoding_dsv41.py _validate_no_image_sp_tokens 硬 400（03:53:16 / 04:08:49 /
  04:23:53 UTC 三次同因，用户会话被打断）。图像字节不在请求里、无法复原 ⇒
  降级净化：把文本中的占位符替换为 '[图像]'，请求放行、会话不再中断。
  确定性变换（同 body 恒同输出），先于 maybe_inject 与 body_key 执行；
  字节快路径（body 不含占位符字节串 ⇒ 零 parse 零开销）；非法 JSON 原样返回
  （与 maybe_inject 同约定）；默认 on（SANITIZE_IMAGE_PLACEHOLDER=1，=0 即
  回退现行为）；计数入 /gw/metrics 的 image_placeholders_sanitized。

背景（qwenpaw-internal-error-rca-external-luz045-2026-09-06.md + gateway 专项）：
  长上下文请求 prefill 分钟级 → 下游应用 30s 内容超时误杀 → 重试重新全量 prefill →
  失败风暴。v1 代理（8001→8002，MAX_CONCURRENCY=6）只做并发计数，长 prefill 场景"哑管"。

rc3.6.1 相对 rc3.6：注入路径扩展覆盖 /v1/responses（对齐旧 8003 双注入点——
  金样本实证注入是 reasoning 链源头开关，引擎端无缺省思考链）；
rc3.6 相对 rc3.5.1 的修正（S2：8003 功能下沉，督导批准，尽调结论落地）：
  enable_thinking 注入（原 8003 _inject_enable_thinking）：POST chat 路径 body
    缺省时注入 chat_template_kwargs.enable_thinking=true。默认 off
    （INJECT_ENABLE_THINKING=0 = 现行为零变化）。字节豁免优先（显式管理不
    覆盖不 parse），确定性变换在 body_key 前执行——去重键对注入后 body 计算且
    跨开关各自稳定；非法 JSON 原样返回走原逻辑。

rc3.5.1 相对 rc3.5 的修正（T21 三断言暴露的 P1：取消传播下 finally 清理跳过）：
  P1 CancelledError 在已取消协程内传播时，finally 的 await wait_for(write_eof)
    立即再抛 CancelledError（BaseException，except Exception 捕不住）→ 排在其
    后的 INFLIGHT.pop/active-=1 全部跳过（active 永久漂移+1；DEDUP=on 时键
    泄漏→同 payload 永久 429）。修复：finally 清理顺序反转（同步清理先行，
    write_eof 最后且吞取消），兜底分支同步此修法。

rc3.5 相对 rc3.4 的修正（终审 P0-B：WRITE_TIMEOUT 切流后信号量槽永久泄漏）：
  P0-B finally 的 write_eof 无超时包裹——其内部 drain 不受 WRITE_TIMEOUT 约束，
    慢读客户端在切流后仍不读 → eof drain 永久阻塞 → finally 卡死 →
    dispatch 的 SEM.release 永不执行（实测：6 个慢客户端耗尽 6 槽全站 429
    直至重启）。修复：两处 write_eof（finally + 兜底分支）均包
    wait_for(WRITE_TIMEOUT)，超时放弃 + resp.force_close()（防 aiohttp
    handler 返回后的内部 finish 路径再次 drain 同面阻塞）。

rc3.4 相对 rc3.3 的修正（多角度复审：精简/效率/安全/性能）：
  A 慢客户端静默截断（pump put_nowait 遇队列满丢数据帧，客户端 200+部分
    chunks+正常 EOF 无错误帧）→ 背压化：await q.put（put 与 readany 的
    CHUNK_IDLE 超时分捕获），数据帧零丢弃，等价 v1 直通/TCP 背压语义。
  B is_stream 每请求全量 json.loads（数 MB body 数 ms~数十 ms CPU）→
    "stream" 键字节串 prefilter，无键请求全免解析（语义零变化）。
  F GW_API_KEY 明文 == 比较（时序侧信道）→ hmac.compare_digest。

rc3.3 相对 rc3.2 的修正（终审 🟠×2 + 影子实例实测 P0×1）：
  P0 心跳未实时下发（node01 影子 76K token 实测：TTFT 12.5s 心跳积压同批）→
      消费循环并行化：producer（建连+首字节+泵送）/ consumer（客户端写循环）
      与 resp.prepare 后立即并行运行，长 prefill 期间心跳即写即达；
      TTFT 预算改由 first_seen 事件监管（超时取消 producer，其 finally 保证
      DONE 入队）；本地 T1 用例因走超时分支未覆盖此路径（已补 T19）。
  O-1 TTFT 预算两段串行最坏 2×（connect 段 + first readany 段各用满 600s）→
      first readany 共享 deadline（FIRST_TOKEN_TIMEOUT - 已耗时），总 TTFT 预算
      硬上限 = FIRST_TOKEN_TIMEOUT。
  O-2 unit 中"StartLimit 停转由 vllm 自愈链监控发现"为虚假声明（自愈链只探
      8002）→ unit 注释改真实描述，runbook 补首日人工值守步骤。

rc3 相对 rc2 的修正（三路交叉评审合并：并发/安全/SSE 兼容 + 人工复审）：
  P0-1 慢读客户端无保护 → 新增 WRITE_TIMEOUT（单次写客户端超时）与
       TOTAL_STREAM_TIMEOUT（整流总时长上限），超限断连并全量清理，
       根除"心跳假活 + 信号量槽耗尽"的 DoS 面。
  P0-2 管理端点零鉴权 → GW_API_KEY（未设则不鉴权，兼容内网 v1 形态；设置后
       /gw/* 需 Bearer）。业务路径不代理鉴权（上游 VLLM_API_KEY 负责）。
  P1-1 connect 阶段 TTFT 超时未捕获（wait_for 抛 TimeoutError 穿透早开流）→
       outcome 显式四分支（正常/连接失败/上游拒绝/超时），全部走错误帧+[DONE] 收尾，
       不再向外抛异常。
  P1-2 去重 TOCTOU（检查与登记隔 await prepare）→ INFLIGHT 原子占位（单线程
       事件循环内 check+set 无 await 间隙，天然原子；占位提前到 prepare 之前）。
  P1-3 错误帧信息泄露（拼入上游异常/响应体）→ 固定文案，细节仅入日志。
  P1-4 错误帧后无终止符（OpenAI SDK 挂等）→ 错误帧后追加 data: [DONE]。
  P1-5 is_stream 类型严格化：仅 isinstance(stream, bool) 且 True 才走流式。
  P1-6 client_max_size 512MB→64MB（600K token JSON 实测仅数 MB；防 3GB 峰值）。
  P1-7 去重 Retry-After 15→120s（原值诱导 429 重试风暴）。
  P2   URL 重组改 request.raw_path（防 #/% 解码错位）；移除 Host 硬编码（由
       aiohttp 按 URL 生成）；CookieJar→Dummy（不跨客户端回带 Cookie）；
       relay_plain 按原 method 转发（不再全转 POST）；X-Forwarded-For 追加；
       rejected_429_queue 双计数修复；metrics 增 uptime/版本/queue_now。

rc2 相对 rc1 的修正：心跳提前到转发后立即开始（早开流）；信号量生命周期收敛
dispatch 单点；authorization 头透传恢复；GET/HEAD 原样转发。

功能（G1~G6）：G1 SSE 心跳（HEARTBEAT_INTERVAL，`: keepalive` 注释帧）
  G2 TTFT 预算（FIRST_TOKEN_TIMEOUT）+ 流空闲超时（CHUNK_IDLE_TIMEOUT）
  G3 admission 反压（QUEUE_TIMEOUT → 429+Retry-After）
  G4 等值重试抑制（body sha256 在飞去重 → 429）
  G5 客户端断连传播（cancel 上游）  G6 观测（/gw/metrics）

部署：与 v1 同形（8001→8002）。systemd unit 见 concurrency-proxy-v2.service。
环境变量（默认值）：
  UPSTREAM=http://127.0.0.1:8002  PORT=8001  MAX_CONCURRENCY=6
  QUEUE_TIMEOUT=20   FIRST_TOKEN_TIMEOUT=600   CHUNK_IDLE_TIMEOUT=600
  HEARTBEAT_INTERVAL=5   RETRY_CONNECT=1   NONSTREAM_TOTAL_TIMEOUT=900
  WRITE_TIMEOUT=60   TOTAL_STREAM_TIMEOUT=7200   DEDUP_ENABLE=1   GW_API_KEY=
  INJECT_ENABLE_THINKING=0   SANITIZE_IMAGE_PLACEHOLDER=1
  GW_REQUIRE_AUTH=0   GW_ALLOWED_MODELS=deepseek-v4.1-flash
  ADVERTISE_MODEL_CAPACITY=0   MODELS_CONTEXT_LEN=0（rc3.8.6 容量广播两键）
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time

from aiohttp import ClientSession, ClientTimeout, DummyCookieJar, web

# ---------------------------------------------------------------- 配置
UPSTREAM = os.environ.get("UPSTREAM", "http://127.0.0.1:8002").rstrip("/")
PORT = int(os.environ.get("PORT", "8001"))
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "6"))
QUEUE_TIMEOUT = float(os.environ.get("QUEUE_TIMEOUT", "20"))
FIRST_TOKEN_TIMEOUT = float(os.environ.get("FIRST_TOKEN_TIMEOUT", "600"))
CHUNK_IDLE_TIMEOUT = float(os.environ.get("CHUNK_IDLE_TIMEOUT", "600"))
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5"))
RETRY_CONNECT = int(os.environ.get("RETRY_CONNECT", "1"))
NONSTREAM_TOTAL_TIMEOUT = float(os.environ.get("NONSTREAM_TOTAL_TIMEOUT", "900"))
WRITE_TIMEOUT = float(os.environ.get("WRITE_TIMEOUT", "60"))
TOTAL_STREAM_TIMEOUT = float(os.environ.get("TOTAL_STREAM_TIMEOUT", "7200"))
DEDUP_ENABLE = os.environ.get("DEDUP_ENABLE", "1") == "1"
GW_API_KEY = os.environ.get("GW_API_KEY", "")
# S2 注入下沉（rc3.6）：默认 off——off = 现行为零变化
INJECT_ENABLE_THINKING = os.environ.get("INJECT_ENABLE_THINKING", "0") == "1"
# rc3.7 图像占位符净化：默认 on——本版目的即修复会话中断；=0 回退现行为
SANITIZE_IMAGE_PLACEHOLDER = os.environ.get("SANITIZE_IMAGE_PLACEHOLDER", "1") == "1"
# rc3.8.5 全局鉴权门：默认 0=休眠原行为（rc3.8.4 等价）；=1 时除 /health 与
# /gw/* 外一切路径一切方法过 gw_authorized（Bearer GW_API_KEY 恒时比较）。
GW_REQUIRE_AUTH = os.environ.get("GW_REQUIRE_AUTH", "0") == "1"
# rc3.8.5 模型名白名单：逗号分隔；缺省=引擎真名单值；显式空串=校验关闭。
# 别名归一不做（8003 responses-gateway 层职责——MODEL_ALIAS 单一事实源）。
GW_ALLOWED_MODELS = frozenset(
    m.strip() for m in os.environ.get("GW_ALLOWED_MODELS", "deepseek-v4.1-flash").split(",")
    if m.strip())
# rc3.8.6 响应侧容量广播（②-a/A10）：默认 0=行为逐字节零变化（rc3.8.5 等价）；
# =1 时 relay_get 对 /v1/models(/id) 响应补客户端模型发现四键（见头注）。
ADVERTISE_MODEL_CAPACITY = os.environ.get("ADVERTISE_MODEL_CAPACITY", "0") == "1"
# rc3.8.6 容量值：0=取条目 max_model_len（引擎实值——缺省。红线：声明恒=引擎真值，
# 禁「调大声明消本地检测」反向陷阱）；>0=固定覆盖位（应急面，正常态勿设）。
try:
    MODELS_CONTEXT_LEN = int(os.environ.get("MODELS_CONTEXT_LEN", "0") or "0")
except ValueError:
    MODELS_CONTEXT_LEN = 0
VERSION = "concurrency-proxy-v2-rc3.8.6"

HEARTBEAT = b": keepalive\n\n"          # SSE 注释帧：OpenAI SDK/EventSource 忽略
DONE_MARK = b"data: [DONE]\n\n"         # 错误帧后的终止符（SDK 正常收尾）
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s gwv2 %(message)s",
)
log = logging.getLogger("gwv2")

# ---------------------------------------------------------------- 状态
SEM: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
INFLIGHT: dict[str, float] = {}          # body_sha256 -> 占位时刻（原子占位）
STARTED_AT = time.time()
METRICS = {
    "version": VERSION, "uptime_sec": 0,
    "requests_total": 0, "streams_total": 0,
    "rejected_429_queue": 0, "rejected_429_duplicate": 0,
    "first_token_timeouts": 0, "chunk_idle_timeouts": 0,
    "chunk_idle_bytes_sent": 0, "queue_full_drops": 0,
    "write_timeouts": 0, "stream_total_timeouts": 0,
    "upstream_errors": 0, "client_disconnects": 0,
    "image_placeholders_sanitized": 0, "image_sanitize_requests": 0,
    "internal_retries": 0, "active_streams": 0, "queue_now": 0,
    "queue_wait_peak": 0.0,
    "auth_rejected": 0, "models_rejected": 0,   # rc3.8.5：全局门/模型门计数（G1 §F-3）
    "ttft_buckets": {
        "lt1": 0, "1to5": 0, "5to30": 0, "30to60": 0,
        "60to120": 0, "120to300": 0, "gt300": 0},
    "queue_wait_buckets": {"lt1": 0, "1to10": 0, "gt10": 0},
}
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
        "te", "trailers", "transfer-encoding", "upgrade", "host",
        "content-length", "content-type"}
# authorization 透传（上游 vLLM 鉴权）


def ttft_bucket(v: float) -> None:
    d = METRICS["ttft_buckets"]
    if v < 1: d["lt1"] += 1
    elif v < 5: d["1to5"] += 1
    elif v < 30: d["5to30"] += 1
    elif v < 60: d["30to60"] += 1
    elif v < 120: d["60to120"] += 1
    elif v < 300: d["120to300"] += 1
    else: d["gt300"] += 1


def qbucket(v: float) -> None:
    d = METRICS["queue_wait_buckets"]
    if v < 1: d["lt1"] += 1
    elif v < 10: d["1to10"] += 1
    else: d["gt10"] += 1


# ---------------------------------------------------------------- 工具
async def acquire_or_none() -> float | None:
    t0 = time.monotonic()
    METRICS["queue_now"] += 1
    try:
        timeout = QUEUE_TIMEOUT if QUEUE_TIMEOUT > 0 else 0.001
        await asyncio.wait_for(SEM.acquire(), timeout=timeout)
        wait = time.monotonic() - t0
        qbucket(wait)
        METRICS["queue_wait_peak"] = max(METRICS["queue_wait_peak"], wait)
        return wait
    except asyncio.TimeoutError:
        METRICS["rejected_429_queue"] += 1     # 唯一计数点（dispatch 不再重复计）
        return None
    finally:
        METRICS["queue_now"] -= 1


def fwd_headers(request: web.Request) -> dict:
    out = {}
    for k, v in request.headers.items():
        if k.lower() in _HOP:
            continue                                    # authorization 透传
        out[k] = v
    out["Content-Type"] = request.headers.get("Content-Type", "application/json")
    xff = request.headers.get("X-Forwarded-For")
    out["X-Forwarded-For"] = (
        f"{xff}, {request.remote}" if xff else str(request.remote))
    # Host 不硬编码：aiohttp 按目标 URL 自动生成
    return out


def upstream_url(request: web.Request) -> str:
    return UPSTREAM + request.raw_path        # raw_path 含 query，未解码，防错位


def is_stream(body: bytes) -> bool:
    """仅显式布尔 stream:true 走流式（字符串/数字等真值一律非流式）。
    rc3.4 prefilter：body 无 "stream" 键字节串则跳过 json.loads（语义零变化
    ——无该键的 JSON 与非法 body 原本就返回 False；最常见非流式请求全免解析）。"""
    if b'"stream"' not in body:
        return False
    try:
        v = json.loads(body).get("stream")
        return v is True
    except Exception:
        return False


def maybe_inject(body: bytes, path: str) -> bytes:
    """rc3.6（S2 下沉，原 8003 _inject_enable_thinking）：POST chat 路径缺省注入
    chat_template_kwargs.thinking=true + enable_thinking=true（双键）。
    确定性变换（同 body 恒同输出），在 body_key 之前执行 → 去重键对注入后 body
    计算且跨开关各自稳定。
    字节豁免优先：body 已含任一键（用户显式管理）→ 跳注入跳 parse
    （保 rc3.4 prefilter 收益）；非法 JSON / 非法顶层结构 → 原样返回走原逻辑。
    2026-10-30 修复（外部站点 bug 报告）：此前只注入 enable_thinking，而本栈
    V4.1 族 overlay（serving_chat.py）读取的键是 chat_template_kwargs["thinking"]
    ——单注入 enable_thinking 对 V4.1 族是 no-op（假键）。现双键同注：
    thinking=V4.1 族生效键；enable_thinking=其他模型族兼容键。"""
    if not INJECT_ENABLE_THINKING:
        return body
    if ("/chat/completions" not in path) and ("/responses" not in path):
        return body
    if (b'"enable_thinking"' in body) or (b'"thinking"' in body):
        return body                          # 显式管理：不覆盖（T22 断言 2）
    try:
        obj = json.loads(body)
        if not isinstance(obj, dict):
            return body
        kwargs = obj.get("chat_template_kwargs")
        if not isinstance(kwargs, dict):
            kwargs = {}
        kwargs.setdefault("thinking", True)          # V4.1 族 overlay 读取键
        kwargs.setdefault("enable_thinking", True)   # 其他模型族兼容键
        obj["chat_template_kwargs"] = kwargs
        return json.dumps(obj).encode()
    except Exception:
        return body                          # 非法 body：跳注入，走原转发逻辑


def validate_model(body: bytes) -> str | None:
    """rc3.8.5 模型名白名单预检：返回应拒的模型名（在白名单外），None=放行。
    b'"model"' 字节预检（rc3.4 prefilter 模式）——无该键请求零 parse 零成本；
    预检命中后才 json.loads；非法 JSON / 非法顶层结构 / model 非字符串
    （null/数字等）一律放行走原转发逻辑（上游给出真实 4xx，网关不越俎）。
    别名归一不做：8003 层 MODEL_ALIAS 单一事实源（G1 §G5），本门只认真名。"""
    if not GW_ALLOWED_MODELS:
        return None                          # 显式空串=校验关闭
    if b'"model"' not in body:
        return None                          # 快路径：绝大多数含 model 键才继续
    try:
        obj = json.loads(body)
    except Exception:
        return None                          # 非法 body：原样转发（与 is_stream 同约定）
    if not isinstance(obj, dict):
        return None
    m = obj.get("model")
    if isinstance(m, str) and m not in GW_ALLOWED_MODELS:
        return m
    return None


def resp_404_model(model: str) -> web.Response:
    """OpenAI 形 model_not_found 404（对齐 02 responses-gateway _model_not_found）。
    模型名回显进 message（客户端自报名，json_response 转义兜底）。"""
    return web.json_response(
        {"error": {"message": f"The model `{model}` does not exist.",
                   "type": "invalid_request_error", "code": "model_not_found"}},
        status=404)


# rc3.7 图像占位符净化 -----------------------------------------------
# 客户端在后续轮次把历史图像序列化为字面文本 '<｜deepseek_image｜>'，引擎
# encoding_dsv41._validate_no_image_sp_tokens 硬 400 → 会话被打断。图像字节
# 不在请求里、无法复原 ⇒ 降级净化：占位符替换为 '[图像]'，请求放行。
# 确定性变换，先于 maybe_inject 与 body_key（去重键对净化后 body 计算）；
# 字节快路径：body 不含占位符字节串 ⇒ 零 parse 零开销；非法 JSON 原样返回。
IMAGE_PLACEHOLDER = "<｜deepseek_image｜>"
IMAGE_PLACEHOLDER_REPL = "[图像]"


def sanitize_image_placeholders(body: bytes, path: str) -> bytes:
    if not SANITIZE_IMAGE_PLACEHOLDER:
        return body
    if ("/chat/completions" not in path) and ("/responses" not in path):
        return body
    # 快路径触发器用 ASCII 子串而非占位符原始字节：客户端 JSON 常以
    # ensure_ascii 转义传输（'｜'→'\uff5c'），原始 UTF-8 字节会漏判；
    # 而占位符中的 ASCII 段 "deepseek_image" 在两种形态下都是字面字节。
    # 误报（如提示词里提到该词）仅多一次 parse，walk 不命中即原样返回。
    if b"deepseek_image" not in body:
        return body                          # 快路径：绝大多数请求零成本直通
    try:
        obj = json.loads(body)
    except Exception:
        return body                          # 非法 body：不碰，走原转发逻辑
    count = 0

    def walk(o):
        nonlocal count
        if isinstance(o, str):
            if IMAGE_PLACEHOLDER in o:
                count += o.count(IMAGE_PLACEHOLDER)
                return o.replace(IMAGE_PLACEHOLDER, IMAGE_PLACEHOLDER_REPL)
            return o
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o

    try:
        obj = walk(obj)
        if not count:
            return body                      # 误报：零字节改动（快路径语义）
        out = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except Exception:
        # P2-A（审核发现）：孤立代理项 U+D800 → UnicodeEncodeError、
        # 深嵌套 → RecursionError。任何无法安全净化的 body 一律原样透传，
        # 恢复 fail-open 契约（上游会给出真实的 4xx，而不是网关 500）。
        return body
    # 计数与日志只反映「实际完成净化」的请求（fail-open 放弃的不计）
    METRICS["image_placeholders_sanitized"] += count
    METRICS["image_sanitize_requests"] += 1
    log.warning("rc3.7.1 sanitized %d image placeholder(s) on %s "
                "(client serialized image as text)", count, path)
    return out


def body_key(body: bytes) -> str:
    """去重键：size + 全量 sha256（rc3.8.3-B1 治本：撤前 1MB 帽——body 在 dispatch
    已全量驻留，帽=伪收益（省一次 ~2ms/MB 哈希扫描）而付前缀碰撞正确性面：同图
    等长异问 body 差异在尾段 ⇒ 同键 ⇒ 第二发误 429。全量哈希后 DEDUP=1 可安全
    复开 VL 车道；确定性/键稳定性不受影响（GW-AUDIT §1.3/§4.1③）。"""
    h = hashlib.sha256()
    h.update(str(len(body)).encode() + b":")
    h.update(body)
    return h.hexdigest()


def resp_429(msg: str, wait: int) -> web.Response:
    return web.json_response(
        {"error": {"message": msg, "type": "gateway_admission", "code": 429}},
        status=429, headers={"Retry-After": str(wait)})


def err_frame(etype: str, msg: str) -> bytes:
    """固定文案错误帧 + [DONE] 终止符（细节仅入日志，不入帧）。
    rc3.8：帧体补 OpenAI chunk 骨架——裸 {"error":…} 帧会让按 choices 严格
    解析的客户端（AI SDK 系）产出 errorPhase=stream 的不可判失败。error 键
    原样保留，故按 error 键判错的消费方语义不变。
    rc3.8.1（P2-3）：补 created/model 两个 ChatCompletionChunk 必填字段，
    避免严格校验（pydantic/部分 Java SDK）对缺字段报错。"""
    body = {"error": {"message": msg, "type": etype},
            "id": "gateway-error", "object": "chat.completion.chunk",
            "created": 0, "model": "gateway-error",
            "choices": [{"index": 0, "delta": {}, "finish_reason": None}]}
    return (b"data: " + json.dumps(body).encode() + b"\n\n" + DONE_MARK)


# ---------------------------------------------------------------- 流式
async def handle_stream(request: web.Request, body: bytes,
                        session: ClientSession) -> web.StreamResponse:
    """四阶段：占位去重(原子) → 早开流+心跳 → producer(建连/首字节/TTFT预算/泵送)
    ∥ consumer(客户端写循环) 并行 → 排空收尾。rc3.3：consumer 与阶段2并行，
    心跳实时下发（不再积压到首字节后）；约束：早开流后不向外抛异常（一切失败
    以错误帧+[DONE] 收尾）；信号量由 dispatch 持有；慢读客户端由
    WRITE_TIMEOUT/TOTAL_STREAM_TIMEOUT 兜底。"""
    key = body_key(body)

    # 原子占位（事件循环单线程：check+set 无间隙，TOCTOU 根除）
    if DEDUP_ENABLE:
        if key in INFLIGHT:
            METRICS["rejected_429_duplicate"] += 1
            return resp_429(
                "identical request already in flight (gateway dedup); "
                "retrying restarts full prefill — wait for the in-flight one",
                max(60, int(HEARTBEAT_INTERVAL * 8)))
        INFLIGHT[key] = time.monotonic()
        registered = True
    else:
        registered = False

    resp = web.StreamResponse(status=200, headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Gateway": VERSION,
    })
    try:
        await resp.prepare(request)
    except BaseException:                  # prepare 失败（客户端早断）：占位必须回收
        if registered:                    # （rc3.3 补：此处位于下方 try/finally 之外，
            INFLIGHT.pop(key, None)       #   原样穿透会导致去重键泄漏→同 body 永久 429）
        raise

    METRICS["streams_total"] += 1
    METRICS["active_streams"] += 1
    t0 = time.monotonic()

    upstream = None
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    DONE = object()
    first_seen = asyncio.Event()             # 首字节到达（TTFT 预算监管点）
    stat = {"rx": 0, "tx": 0}    # rc3.8：rx=引擎侧已读字节 tx=已写客户端字节
    tasks: list[asyncio.Task] = []

    def put_frame(frame: object) -> bool:
        """rc3.8.1（P2-1）：错误帧/DONE 入队绝不抛出——队列满（256）时丢帧 +
        计数 + 留痕。原 put_nowait 直抛会被 pump 级 except Exception 捕获，
        既误计 upstream_errors，又让客户端收不到错误帧（静默截断回归）。"""
        try:
            q.put_nowait(frame)
            return True
        except asyncio.QueueFull:
            METRICS["queue_full_drops"] += 1
            log.warning("frame dropped (queue full): %s", request.raw_path)
            return False

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                q.put_nowait(HEARTBEAT)     # 队列满即丢弃：有数据在途等效保活
            except asyncio.QueueFull:
                pass

    async def producer() -> None:
        """rc3.3：建连 + 首字节（共享 TTFT 预算）+ 持续泵送，收敛为单一 producer。
        心跳实时化前提：消费循环（consumer）已并行运行，本任务只管生产。
        any-exit 保证：first_seen 必置位（主流程不被挂死）、DONE 必入队
        （consumer 收尾依据）——全部走 finally，无裸退出路径。"""
        nonlocal upstream
        try:
            # ---- 建连（重试循环；引擎拒绝/连接失败 → 错误帧 + return，DONE 由 finally）
            last_err = ""
            for attempt in range(1 + RETRY_CONNECT):
                try:
                    u = await session.post(
                        upstream_url(request), data=body,
                        headers=fwd_headers(request),
                        timeout=ClientTimeout(total=None, sock_connect=10))
                    if u.status >= 500 and attempt < RETRY_CONNECT:
                        u.release()
                        METRICS["internal_retries"] += 1
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    if u.status != 200:                 # 引擎明确拒绝
                        METRICS["upstream_errors"] += 1
                        log.warning("upstream rejected %s %s body=%.300s",
                                    u.status, request.raw_path, await u.text())
                        u.close()                       # 不留句柄，防误读 error body
                        put_frame(err_frame(
                            "gateway_upstream",
                            "upstream rejected the request (see gateway log)"))
                        return
                    upstream = u
                    break
                except Exception as e:
                    last_err = repr(e)
                    if attempt < RETRY_CONNECT:
                        METRICS["internal_retries"] += 1
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    METRICS["upstream_errors"] += 1
                    log.warning("upstream connect failed %s: %s",
                                request.raw_path, last_err)
                    put_frame(err_frame(
                        "gateway_upstream",
                        "upstream connect failed (see gateway log)"))
                    return

            # ---- 首字节：与建连共享同一 TTFT 预算（以入口 t0 为基准，connect 已
            #      耗时扣除；max(0.1,·) 保证耗尽时极短超时即触发超时分支，无负数/
            #      零 timeout。FIRST_TOKEN_TIMEOUT<=0 = 关闭预算，不限时）
            try:
                if FIRST_TOKEN_TIMEOUT > 0:
                    remaining = max(
                        0.1, FIRST_TOKEN_TIMEOUT - (time.monotonic() - t0))
                    first = await asyncio.wait_for(
                        upstream.content.readany(), timeout=remaining)
                else:
                    first = await upstream.content.readany()
            except asyncio.TimeoutError:
                METRICS["first_token_timeouts"] += 1
                log.warning("first-token timeout %.0fs %s",
                            FIRST_TOKEN_TIMEOUT, request.raw_path)
                put_frame(err_frame(
                    "gateway_first_token_timeout",
                    f"no first token from engine within "
                    f"{FIRST_TOKEN_TIMEOUT:.0f}s (long prefill); "
                    f"do NOT blind-retry with same payload"))
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                METRICS["upstream_errors"] += 1
                log.warning("first read failed %s: %r", request.raw_path, e)
                put_frame(err_frame(
                    "gateway_upstream",
                    "upstream stream failed before first token (see gateway log)"))
                return

            ttft = time.monotonic() - t0
            ttft_bucket(ttft)
            log.info("stream first-token ttft=%.2fs path=%s", ttft, request.path)
            first_seen.set()                  # 首字节到：TTFT 预算监管结束

            # ---- 持续泵送（rc3.4 背压化：await put 阻塞等 consumer 消费，等价引擎
            #      TCP 背压，数据帧零丢弃——慢而未死客户端不再静默截断；
            #      put 无超时（等价 v1 直通语义），readany 仍受 CHUNK_IDLE 约束，
            #      两者分 try 捕获，超时语义互不污染）
            data = first
            stat["rx"] += len(first)
            try:
                while data:
                    await q.put(data)
                    try:
                        data = await asyncio.wait_for(
                            upstream.content.readany(),
                            timeout=CHUNK_IDLE_TIMEOUT)
                    except asyncio.TimeoutError:
                        METRICS["chunk_idle_timeouts"] += 1
                        METRICS["chunk_idle_bytes_sent"] += stat["tx"]
                        # rc3.8：断流必须留痕（此前零日志，受害请求不可考）
                        log.warning(
                            "chunk idle > %.0fs, cut: %s rx=%d tx=%d "
                            "elapsed=%.1fs",
                            CHUNK_IDLE_TIMEOUT, request.path,
                            stat["rx"], stat["tx"], time.monotonic() - t0)
                        put_frame(err_frame(
                            "gateway_chunk_idle",
                            f"upstream stream idle > {CHUNK_IDLE_TIMEOUT:.0f}s "
                            f"after first token"))
                        return
                    stat["rx"] += len(data)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                METRICS["upstream_errors"] += 1
                log.warning("pump error %s: %r", request.path, e)
                # rc3.8.2（审查 L1）：中途读失败此前无错误帧 ⇒ 客户端「部分内容 +
                # 干净 [DONE]」静默截断（idle 分支同型）。固定文案，细节仅入日志。
                put_frame(err_frame(
                    "gateway_upstream",
                    "upstream stream failed mid-flight (see gateway log)"))
        except asyncio.CancelledError:
            raise
        finally:
            first_seen.set()
            await q.put(DONE)                 # 阻塞式保证 DONE 必达（consumer 收尾）

    async def consumer() -> None:
        """rc3.3 心跳实时化核心：resp.prepare 后立即启动的客户端写循环，与
        producer 完全并行——阶段2（建连 + 长 prefill 等待）期间心跳即实时下发，
        不再积压到首字节后同批涌出。"""
        try:
            while True:
                item = await q.get()
                if item is DONE:
                    break
                if time.monotonic() - t0 > TOTAL_STREAM_TIMEOUT:
                    METRICS["stream_total_timeouts"] += 1
                    log.warning("stream total > %.0fs, cut: %s",
                                TOTAL_STREAM_TIMEOUT, request.path)
                    break
                await asyncio.wait_for(resp.write(item), timeout=WRITE_TIMEOUT)
                if item is not HEARTBEAT:     # rc3.8.1（P2-2）：心跳不计入交付字节
                    stat["tx"] += len(item)
        except asyncio.TimeoutError:                     # 写客户端超时（慢读）
            METRICS["write_timeouts"] += 1
            log.warning("client write timeout %.0fs: %s",
                        WRITE_TIMEOUT, request.path)
        except (ConnectionResetError, asyncio.CancelledError):
            METRICS["client_disconnects"] += 1

    hb = asyncio.create_task(heartbeat())
    consumer_t = asyncio.create_task(consumer())
    tasks.extend((hb, consumer_t))

    def finish_err(etype: str, msg: str) -> None:
        put_frame(err_frame(etype, msg))
        put_frame(DONE)                   # 队列满时 producer finally 阻塞 put 兜底

    producer_t = asyncio.create_task(producer())
    tasks.append(producer_t)
    try:
        # ---- 阶段2 预算监管：首字节（first_seen）须在 TTFT 预算内到达。
        #      超时则取消 producer（其 finally 保证 DONE 入队），consumer 收到
        #      错误帧后自然收尾；预算只管到首字节，不约束后续整流时长
        #      （整流由 TOTAL_STREAM_TIMEOUT 管，避免长生成流被 TTFT 误杀）。
        try:
            if FIRST_TOKEN_TIMEOUT > 0:
                await asyncio.wait_for(
                    first_seen.wait(), timeout=FIRST_TOKEN_TIMEOUT)
            else:
                await first_seen.wait()
        except asyncio.TimeoutError:
            producer_t.cancel()
            METRICS["first_token_timeouts"] += 1
            log.warning("first-token timeout %.0fs %s",
                        FIRST_TOKEN_TIMEOUT, request.raw_path)
            finish_err("gateway_first_token_timeout",
                       f"no first token from engine within "
                       f"{FIRST_TOKEN_TIMEOUT:.0f}s (long prefill); "
                       f"do NOT blind-retry with same payload")

        # ---- 阶段3：等 consumer 排空退出（producer 的数据/错误帧/DONE 已入队）
        await consumer_t
        return resp
    except (ConnectionResetError, asyncio.CancelledError):
        METRICS["client_disconnects"] += 1
        raise
    except Exception as e:                              # 兜底：绝不向外裸抛挂死客户端
        log.exception("stream handler error: %r", e)
        try:
            finish_err("gateway_internal", "gateway internal error (see log)")
            await asyncio.wait_for(resp.write_eof(), timeout=WRITE_TIMEOUT)
        except (Exception, asyncio.CancelledError):     # rc3.5.1：含取消（见 finally 注）
            resp.force_close()
        return resp
    finally:
        # rc3.5.1：同步清理先行——CancelledError 传播路径下，finally 内任何 await
        # （含 wait_for(write_eof)）都会立即再抛 CancelledError（BaseException，
        # except Exception 捕不住），原先排在其后的 INFLIGHT.pop/active-=1 会被
        # 全部跳过（active 永久漂移 +1；DEDUP=on 时键泄漏 → 同 payload 永久 429）。
        # 顺序反转后：先完成全部同步清理，write_eof 挪到最后且自吞取消。
        for t in tasks:
            t.cancel()
        if upstream is not None:
            upstream.close()
        if registered:
            INFLIGHT.pop(key, None)
        METRICS["active_streams"] -= 1
        try:
            # rc3.5：write_eof 的内部 drain 不受 WRITE_TIMEOUT 约束（那只管
            # resp.write）——慢读客户端在切流后仍不读 → eof drain 永久阻塞 →
            # finally 卡死 → dispatch 的 SEM.release 永不执行（槽泄漏：6 个慢
            # 客户端耗尽全站并发，直至重启）。超时即放弃，连接由服务端关闭兜底。
            await asyncio.wait_for(resp.write_eof(), timeout=WRITE_TIMEOUT)
        except (Exception, asyncio.CancelledError):
            # 超时/异常/取消路径都 force_close：aiohttp 在 handler 返回后的内部
            # finish 路径会再次尝试 write_eof 并 drain（同一阻塞面）——force_close
            # 使其改为直接 close 连接（非阻塞）。已取消协程内吞 CancelledError
            # 是合法收尾（web_protocol 已在关闭连接，重抛无意义）
            resp.force_close()


# ---------------------------------------------------------------- 非流式
async def relay_plain(request: web.Request, body: bytes,
                      session: ClientSession) -> web.StreamResponse:
    # rc4 流式转发：原实现「整包 await up.read() 后一次性 Response」把大响应
    # （数百 KB 级 SSE 拼接体）全量驻留网关内存且无背压（实测非流式劣化
    # +156%）。改为随读随写：up.content.iter_any() → resp.write（单次写
    # 包 asyncio.wait_for(WRITE_TIMEOUT)，与流式路径同语义）。开流前异常
    # 仍走原 502/504 JSON 分支；prepare 之后无法改写状态码，只能断连兜底。
    resp = None
    try:
        async with session.request(              # 原方法转发（PUT/DELETE/OPTIONS 不破坏）
                request.method, upstream_url(request), data=body,
                headers=fwd_headers(request),
                timeout=ClientTimeout(total=NONSTREAM_TOTAL_TIMEOUT)) as up:
            _skip = {"content-length", "transfer-encoding", "connection",
                     "keep-alive", "te", "trailer", "upgrade"}
            resp = web.StreamResponse(status=up.status, headers={
                k: v for k, v in up.headers.items()
                if k.lower() not in _skip})
            await resp.prepare(request)
            async for chunk in up.content.iter_any():
                await asyncio.wait_for(resp.write(chunk), timeout=WRITE_TIMEOUT)
            await asyncio.wait_for(resp.write_eof(), timeout=WRITE_TIMEOUT)
            return resp
    except asyncio.TimeoutError:
        METRICS["upstream_errors"] += 1
        if resp is None:                          # 开流前：可安全回 504 JSON（原语义）
            return web.json_response(
                {"error": {"message": f"gateway: upstream non-stream timeout "
                                      f">{NONSTREAM_TOTAL_TIMEOUT:.0f}s",
                           "type": "gateway_timeout"}}, status=504)
        log.warning("relay_plain mid-stream timeout %s %s",      # 开流后：断连兜底
                    request.method, request.raw_path)
        resp.force_close()
        return resp
    except ConnectionResetError:
        if resp is not None:
            resp.force_close()
        raise                                     # 客户端断开 → dispatch 计数（原语义）
    except Exception as e:
        METRICS["upstream_errors"] += 1
        log.warning("relay_plain failed %s %s: %r",
                    request.method, request.raw_path, e)
        if resp is None:                          # 开流前：可安全回 502 JSON（原语义）
            return web.json_response(
                {"error": {"message": "upstream connect failed",
                           "type": "gateway_upstream"}}, status=502)
        resp.force_close()                        # 开流后：断连兜底
        return resp


# rc3.8.6 响应侧容量广播（②-a/A10）-----------------------------------------
# 客户端模型发现四键（harness/llm-pi-ai 族读法；值恒=引擎真值 max_model_len）。
CAPACITY_FIELDS = ("context_length", "context_window", "max_input_tokens")


def advertise_model_capacity(body: bytes, path: str) -> bytes:
    """GET /v1/models 与 /v1/models/{id} 响应侧补容量四键（纯增量/幂等/fail-open）。

    取值=条目自带 max_model_len（MODELS_CONTEXT_LEN=0 缺省——引擎真值，不写死）；
    MODELS_CONTEXT_LEN>0=固定覆盖位（应急面）。缺 max_model_len 的条目（如 LoRA
    行）跳过不写（防 null 污染）。仅缺键时补——已有键零触碰（纯增量；与 ②-b
    引擎原生字段叠加时自动原样返回），全文档零改动=原样返回（幂等）。任何异常
    （非法 JSON/非目标结构/序列化失败）=原样透传——绝不因本变换回 500（fail-open）。
    返回：原字节 或 补键后重序列化字节（确定性——同输入恒同输出）。
    """
    if not ADVERTISE_MODEL_CAPACITY:
        return body
    if not (path == "/v1/models" or path.startswith("/v1/models/")):
        return body
    try:
        doc = json.loads(body)
    except Exception:
        return body                       # 非法 JSON：原样透传（fail-open）
    if not isinstance(doc, dict):
        return body
    # 目标条目集：列表形（/v1/models）取 data 列表；单卡形（/v1/models/{id}）
    # 取本体（有 id+object 或 max_model_len 的 dict）；其余结构=不改。
    if isinstance(doc.get("data"), list):
        targets = doc["data"]
    elif "max_model_len" in doc or ("id" in doc and "object" in doc):
        targets = [doc]
    else:
        return body
    changed = False
    for ent in targets:
        if not isinstance(ent, dict):
            continue
        v = MODELS_CONTEXT_LEN if MODELS_CONTEXT_LEN > 0 else ent.get("max_model_len")
        # bool 是 int 子类：显式排除；非数值（null/字符串）=无容量来源→跳过
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        for k in CAPACITY_FIELDS:
            if k not in ent:
                ent[k] = v
                changed = True
        limit = ent.get("limit")
        if limit is None:                  # 缺键/null=无信息：补嵌套键
            ent["limit"] = {"context": v}
            changed = True
        elif isinstance(limit, dict) and "context" not in limit:
            limit["context"] = v
            changed = True
    if not changed:
        return body                       # 幂等：已带字段=逐字节原样
    try:
        return json.dumps(doc, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    except Exception:
        return body                       # 序列化失败：原样透传（fail-open）


async def relay_get(request: web.Request, session: ClientSession) -> web.Response:
    try:
        async with session.get(upstream_url(request), headers=fwd_headers(request),
                               timeout=ClientTimeout(total=30)) as up:
            body = await up.read()
            # rc3.8.6（②-a/A10）：/v1/models(/id) 响应侧容量广播——鉴权门后
            # （dispatch 前置门先于本函数）；HEAD 无体=原样透传；函数内部三硬门。
            if (ADVERTISE_MODEL_CAPACITY and request.method == "GET"
                    and up.status == 200):
                body = advertise_model_capacity(body, request.path)
            return web.Response(status=up.status, content_type=up.content_type,
                                body=body)
    except Exception as e:
        # rc3.8.3-A6：原静默 502 零留痕（/metrics 502 风暴期成因零可考）——补成因
        # 留痕，与 relay_plain 同形（log.warning；细节不入响应体）。
        log.warning("relay_get failed %s %s: %r",
                    request.method, request.raw_path, e)
        return web.json_response(
            {"error": {"message": "upstream failed",
                       "type": "gateway_upstream"}}, status=502)


# ---------------------------------------------------------------- 入口
def gw_authorized(request: web.Request) -> bool:
    if not GW_API_KEY:
        return True
    # 常量时间比较（rc3.4）：防时序侧信道逐字节探测 key
    return hmac.compare_digest(request.headers.get("Authorization", ""),
                               f"Bearer {GW_API_KEY}")


async def dispatch(request: web.Request):
    METRICS["requests_total"] += 1
    if request.path.startswith("/gw/"):
        if not gw_authorized(request):
            return web.json_response(
                {"error": {"message": "unauthorized", "type": "gw_auth"}},
                status=401)
        if request.path == "/gw/health":
            return web.json_response({"status": "ok", "version": VERSION})
        if request.path == "/gw/metrics":
            METRICS["uptime_sec"] = int(time.time() - STARTED_AT)
            return web.json_response(METRICS)
        return web.json_response({"error": "not found"}, status=404)

    # rc3.8.5 全局鉴权门（G1 §F-1 插入点：统一分流层——GET/HEAD 分支与 POST
    # acquire_or_none 之前，body 读取之前）：流式（handle_stream）/非流式
    # （relay_plain）/GET 名录面共用同一前置门。/health 豁免（guardctl 探针面）；
    # /metrics 在门内（prometheus 侧配 bearer_token）；/gw/* 上面已走原门。
    # GW_REQUIRE_AUTH=0 ⇒ 门休眠，行为与 rc3.8.4 逐字节等价。
    if GW_REQUIRE_AUTH and request.path != "/health":
        if not gw_authorized(request):
            METRICS["auth_rejected"] += 1
            return web.json_response(
                {"error": {"message": "unauthorized", "type": "gw_auth"}},
                status=401)

    # GET/HEAD 免并发槽（轻量读，不占推理槽；30s 自身超时）
    if request.method in ("GET", "HEAD"):
        try:
            return await relay_get(request, request.app["client"])
        except Exception:
            return web.json_response(
                {"error": {"message": "upstream failed",
                           "type": "gateway_upstream"}}, status=502)

    wait = await acquire_or_none()
    if wait is None:
        return resp_429(
            f"gateway at capacity (MAX_CONCURRENCY={MAX_CONCURRENCY}); "
            f"engine busy — retry after cool-down", 30)
    try:
        session: ClientSession = request.app["client"]
        body = await request.read()
        if request.method == "POST":
            body = sanitize_image_placeholders(body, request.path)  # rc3.7：先于注入与去重键
            body = maybe_inject(body, request.path)   # rc3.6：注入先于流式判定与去重键
            bad_model = validate_model(body)          # rc3.8.5：模型门（G1 §F-2，maybe_inject 后）
            if bad_model is not None:
                METRICS["models_rejected"] += 1
                log.warning("model rejected %s: %r (allowed=%d)",
                            request.path, bad_model, len(GW_ALLOWED_MODELS))
                return resp_404_model(bad_model)
        if request.method == "POST" and is_stream(body):
            return await handle_stream(request, body, session)
        return await relay_plain(request, body, session)
    except (ConnectionResetError, asyncio.CancelledError):
        METRICS["client_disconnects"] += 1
        raise
    except web.HTTPException:
        raise                                    # rc3.8.4：aiohttp 语义类异常透传（413 帽族）——原兜底吞译 500（G2 S5 V2b 实证）
    except Exception as e:
        log.exception("dispatch failed: %r", e)
        return web.json_response(
            {"error": {"message": "gateway internal error",
                       "type": "gateway_internal"}}, status=500)
    finally:
        SEM.release()


async def make_app() -> web.Application:
    # 64MB：600K token JSON 实测数 MB 级；防超大 body×并发 的内存峰值
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app["client"] = ClientSession(
        timeout=ClientTimeout(total=None),
        cookie_jar=DummyCookieJar())               # 不跨客户端回带 Cookie
    app.router.add_route("*", "/{tail:.*}", dispatch)
    app.on_cleanup.append(_close_session)
    return app


async def _close_session(app: web.Application) -> None:
    await app["client"].close()


def main() -> None:
    auth_face = ("off" if not GW_API_KEY else
                 ("gw+v1-all" if GW_REQUIRE_AUTH else "gw-only"))
    # rc3.8.6：容量广播面（off / on(engine)=取引擎实值 / on(<覆盖值>)）
    capacity_face = ("off" if not ADVERTISE_MODEL_CAPACITY else
                     (f"on({MODELS_CONTEXT_LEN})" if MODELS_CONTEXT_LEN > 0
                      else "on(engine)"))
    log.info("%s %s->%s conc=%d ttft=%.0fs idle=%.0fs hb=%.0fs q=%.0fs "
             "write_to=%.0fs total_to=%.0fs dedup=%s auth=%s models=%s cap=%s",
             VERSION, f"0.0.0.0:{PORT}", UPSTREAM, MAX_CONCURRENCY,
             FIRST_TOKEN_TIMEOUT, CHUNK_IDLE_TIMEOUT, HEARTBEAT_INTERVAL,
             QUEUE_TIMEOUT, WRITE_TIMEOUT, TOTAL_STREAM_TIMEOUT,
             DEDUP_ENABLE, auth_face,
             "|".join(sorted(GW_ALLOWED_MODELS)) if GW_ALLOWED_MODELS else "any",
             capacity_face)
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None,
                shutdown_timeout=60)


if __name__ == "__main__":
    main()
