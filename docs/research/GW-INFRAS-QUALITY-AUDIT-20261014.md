# GW-INFRAS-QUALITY-AUDIT-20261014 — 网关与基础设施质量审查（案头六面+修复清单+验证窗卡）

> **性质**：案头代码审查+设计评估（零流量零 boot 零集群动作；生产验证段不在本窗）。
> **法源**：用户裁定原文（2026-10-13）——「网关代码调整需要适配，要落实 vl 调用兼容，各类调用
> 路径的修复，占位符的匹配等。相关网关、通讯等基础设施的服务质量和性能都未进行完整生产环境
> 质量验证测试和修复，排查性能缺陷、模型匹配、重复建设，过度设计的问题后再封包提交更新。」
> **审查对象**：01 机 concurrency-proxy-v2 双实例（8001 文本本尊 pid 30290 / 8002 VL 车道
> pid 148328，同 rc3.8.2 本尊 e1a01162 三拷贝同 md5 亲核）+ 交付仓 gateway 包 + fabric-net
> 包 + gw-verify 五探针。代理本体=Python 源码（非编译件，无反汇编局限）。
> **证据基线**：/proc/<pid>/environ 实核（2026-10-14 00:4x 本地时）、systemctl show 只读查询、
> journal 全量 census、~/gwtest 历史 bench（2026-09-07 rc3.3 时代）、包内件逐行读。

---

## §〇 现役态实核（全部一手实测锚）

### 0.1 实例与进程

| 面 | 主实例（文本车道） | VL 车道 |
|---|---|---|
| unit | concurrency-proxy-v2.service（/etc 件 root:root **600**，mtime 09-24） | concurrency-proxy-vl.service（644，mtime 10-13 20:39；包件 md5 bd6fc3e8 对表落位） |
| pid/启动 | **30290**（10-11 05:20 起，在役 2d19h+） | **148328**（10-13 23:46 起=转正切 8899 后 restart） |
| cgroup | system.slice/concurrency-proxy-v2.service（systemd 托管实证） | 同左（vl） |
| enabled | enabled | enabled |
| drop-in | 99-upstream-v41.conf（UPSTREAM=8899+MAX_CONCURRENCY=16，mtime 09-17）/ inject.conf（INJECT_ENABLE_THINKING=1，09-07）/ zz-queue-timeout.conf（QUEUE_TIMEOUT=5，09-19）——**10-gateway-hardening.conf 未落 v2** | 10-gateway-hardening.conf（在） |
| EnvironmentFile | **/etc/default/concurrency-proxy-v2**（root:root 600；GW_API_KEY 值位） | /opt/aicad-prod/secrets/gateway-vl.env（0600；7 键与模板逐键同面，VL-PROMO §四 md5 728bfa0a） |
| 硬化（systemctl show） | MemoryMax=2G；**ProtectSystem=no / NoNewPrivileges=no** | MemoryMax=2G；ProtectSystem=strict / NoNewPrivileges=yes |

### 0.2 在役运行时 env（/proc 实核，GW_API_KEY 值不打印）

| 键 | 8001 实值 | 8002 实值 | 脚本默认（concurrency_proxy_v2.py:150-166） | 包模板 gateway.env.template | 包模板 vl |
|---|---|---|---|---|---|
| UPSTREAM | 8899 | **8899**（转正后） | 8002 | 8899 | **8898（陈旧）** |
| PORT | 8001 | 8002 | 8001 | 8001 | 8002 |
| MAX_CONCURRENCY | 16 | 8 | 6 | 16 | 8 |
| QUEUE_TIMEOUT | 5 | 20（默认继承） | 20 | **缺键**（→20） | 缺键 |
| FIRST_TOKEN_TIMEOUT | 600 | 600（默认） | 600 | 缺键 | 缺键 |
| CHUNK_IDLE_TIMEOUT | **180** | 600（默认） | 600 | **缺键**（注释写「600 为 rc3.8 O-2 实证值」却不设键） | 缺键 |
| HEARTBEAT_INTERVAL | 5 | 5 | 5 | 缺键 | 缺键 |
| WRITE_TIMEOUT | 60 | 60 | 60 | 60 | 60 |
| TOTAL_STREAM_TIMEOUT | 7200 | 7200 | 7200 | 7200 | 7200 |
| DEDUP_ENABLE | 1 | 0 | 1 | 1 | 0 |
| NONSTREAM_TOTAL_TIMEOUT | 900 | 900（默认） | 900 | 缺键 | 缺键 |
| RETRY_CONNECT | 1 | 1（默认） | 1 | 缺键 | 缺键 |
| INJECT_ENABLE_THINKING | **1**（inject.conf） | 0（默认） | 0 | **缺键（→0，行为反转！）** | 缺键 |
| GW_API_KEY | 在（**仅 14 字符**） | 在 | 空 | 值位空（合规） | 值位空 |

### 0.3 流量画像（journal census；8001=10-11 起 / 8002=10-13 23:46 起）

- **8001**：GET /metrics 2919×200+7711×502（Prometheus 5s 常探引擎指标经网关——**502 与引擎
  停机窗逐分钟吻合**，如 10-14 00:19 起持续 502=当前重测窗在飞占 8899 的直接观测）；GET /health
  81×200+201×502；POST /v1/chat/completions 12×200；/gw/health 401×1；**全窗零 429**（队列
  与 dedup 拒绝双零）；WARNING 仅 4 条=引擎切换窗 upstream connect failed（fail 行为正确留痕）。
- **8002**：POST /v1/chat/completions 13×200+1×502（转正切换窗自然态）；/gw/health 401×3
  +200×2、/gw/metrics 200×4+401×1（管理面鉴权正反双向实证）；/health 3×200+2×502。
- **结论**：8001 现役独占职责已收缩为「观测中继（Prometheus /metrics+health）+本地 smoke」，
  用户入口面已由 Mac mini M6 :8001 承担（GATEWAY-MIGRATION §六/§九；其 UPSTREAM=24001 隧道
  直达 8899，不经 01:8001）——见 §五.2 舰队三实例。

---

## §一面1 · VL 调用兼容深审（用户点名①）

代理本体逐路径审（锚=tools/packages/gateway/payload/concurrency_proxy_v2.py，与 01 在役
/opt/aicad-prod/scripts/ 同 md5 e1a01162 亲核；sources.tsv 对表绿）：

### 1.1 多 content part（text+image_url 混合）转发保真 — **判绿**
POST 链为「字节透传为体、按需解析为用」：`sanitize_image_placeholders`（:306-351）快路径触发器
=ASCII `b"deepseek_image"`（:315），image_url 真载荷（base64 data URL/https URL）不含该串
⇒零 parse 零改写直通；即便误触发（提示词提及），walk 不命中 `<｜deepseek_image｜>` 即**零字节
原样返回**（:337-339）。`is_stream`（:257-267）虽 json.loads 全量解析但**只读不写**——判定后
转发的是原始 body 字节，content 数组结构零重序列化零畸变。`maybe_inject`（:270-293）VL 车道
INJECT_ENABLE_THINKING=0 ⇒ :276 直接返回原 body。**端到端实证**：VL-PROMO-20261013 §四
「车道冒烟读数与直连逐字同=零内容畸变」+ VL-NATIVE-RESULT §四 S6 端到端全绿。

### 1.2 base64 大 body 缓冲/超时/内存面 — **判绿带两注记**
- 大小帽：`client_max_size=64MB`（:796）；超帽=aiohttp 层 413 优雅（wincard R7 已登记；
  V4.1 min_pixels 295936/max_image_tokens 1024 政策自带钳制+T13 16000×9000 降采样受理先例）。
- 缓冲：`await request.read()` 全量驻留（:775）——单请求 1 份主缓冲+aiohttp 发送侧（bytes 直写
  无额外全量拷），8 并发×64MB 最坏 ≈1GB 量级 < MemoryMax 2G（drop-in 限面有效但贴近；实际
  图像 MB 级，裕量足）。
- 超时对长 prefill 适配：VL 车道 FIRST_TOKEN_TIMEOUT=600/CHUNK_IDLE_TIMEOUT=600/
  NONSTREAM_TOTAL_TIMEOUT=900（默认值继承）；V4.1 图像 prefill 秒级（1024 图 token 上限政策）
  ⇒TTFT 预算 600s 裕量充分；S2 直连首发 5.22s/车道暖 0.61s（VL-PROMO §四）实证带内。
- 注记①：无 chunked 流式转发（整 body 缓冲）——设计事实非缺陷，64MB 帽下可接受。
- 注记②：两车道 CHUNK_IDLE/NONSTREAM 皆为默认继承非显式钉值——env 模板未显式承载
  （见 §三 A9/呈裁 C5）。

### 1.3 DEDUP_ENABLE=0 治标/治本定谳 — **判：当前治标正确，治本路径一行可达**
- 机理确认：`body_key`（:357-362）=size+**前 1MB** 分块 sha256（MAX_HASH_BYTES=1<<20，:354）。
  VL 窗判读「1MB 前缀碰撞风险」成立：**同图+等长异问**双发（body>1MB、差异在尾段）⇒同键⇒第二
  发误 429（Retry-After 60s，:399-402）。size 参与键使碰撞窗窄，但多 MB VL body 下非纯理论。
- **关键事实**：body 在 :775 已**全量驻留内存**——1MB 帽「防超大 body 全量驻留」的注释目标
  （:358）实为伪收益：省的只是一次哈希扫描（sha256 ~2ms/MB），付出的却是前缀碰撞正确性面。
  **治本=全量哈希**：`h.update(body)` 去帽一行改（确定性/键稳定性不受影响），DEDUP_ENABLE=1
  即可安全复开 VL 车道；文本长上下文（本战役 600K token 工作流 body 数 MB、系统提示+历史高度
  共享）同险同闭。
- 现役面：8001 DEDUP=1 在役（文本面理论风险=同前缀碰撞，等长约束下窗口极窄）；8002 DEDUP=0
  规避正确。**全窗 journal 零 429**（队列+dedup 双零）⇒dedup 生产收益未证（§六三桶）。

### 1.4 usage 字段透传 — **判绿**
流式=逐字节泵送（:537-560，rx→queue→resp.write 零解析）；非流式=iter_any 随读随写
（:693-695）。`usage.prompt_tokens_details.image_tokens` 全链零畸变——VL-NATIVE G-V1
满额断言 1024/1024 精确命中+官方对 633 动态计费带内（经 :8002 车道与直连逐字同）双实证。

### 1.5 流式图像请求路径 — **判绿**
stream=true 图像请求走 handle_stream（:386-670）：rc3.3 producer/consumer 并行+心跳实时化、
rc3.4 背压化 put（数据帧零丢弃）、TTFT 预算 first_seen 监管（:611-630）、错误帧 OpenAI chunk
骨架+created/model 必填（:371-382，rc3.8.1 P2-3）。S6 端到端（:8002 流式）+本窗 journal
13×200 在案。rc3.5.1 取消传播下同步清理先行（:646-658）——槽/键泄漏类前科均已修在册。

---

## §二面2 · 各类调用路径盘点修复（用户点名②）

### 2.1 路径×处理函数×行为×在役证据全表

| 路径 | 方法 | 代码路径 | 转发行为 | 超时 | 在役证据 |
|---|---|---|---|---|---|
| /v1/chat/completions（流） | POST | sanitize(:777)→inject(:778)→is_stream(:779)→handle_stream(:780) | 字节透传+信号量+SSE 泵送 | TTFT 600/idle 600/write 60/total 7200 | 8001 12×200；8002 13×200 |
| /v1/chat/completions（非流） | POST | 同上→relay_plain(:781) | 原方法转发+流式回写 | NONSTREAM 900/write 60 | S6 冒烟非流式 200 在案 |
| /v1/responses | POST | 同链（inject 注入点含 :278） | 同上 | 同上 | 在役零流量（保留无害） |
| /v1/models、/health、/metrics 等 GET | GET/HEAD | dispatch :759-766→relay_get(:724-733) | 直转+整读回传，**免并发槽** | 30s | /metrics 5s 常探在役 |
| /gw/health、/gw/metrics | GET | dispatch :747-757 | 本地应答+GW_API_KEY Bearer（hmac.compare_digest :741-742） | — | 401 正反双向实证 ×2 实例 |
| /gw/* 未知 | * | :757 | 本地 404 | — | — |
| PUT/DELETE/OPTIONS | * | relay_plain（原方法，:684） | 直转 | NONSTREAM 900 | 在役零流量 |

### 2.2 回退/超时/重试语义
- **502/504 分级**：非流式开流前=502/504 JSON（:697-719）；开流后=force_close 断连兜底
  （:704-721）；流式=早开流后一切失败收敛为错误帧+[DONE]（rc3.3 契约），中途读失败补错误帧
  （rc3.8.2 L1 修——静默截断路径清零）。
- **上游停机窗行为（journal 实证）**：引擎停 ⇒ GET /health+/metrics 秒级 502（正确快败，
  无挂死）；POST ⇒「upstream connect failed」错误帧+WARNING 留痕 4 条；恢复即自愈
  （10-14 00:19 分界前后 200/502 逐分钟切换清晰）。**无熔断/半开**：停机期每探针仍独立建连——
  观测面量极小（5s 一发 GET）可接受，登记不改建。
- **重试语义=一处重复计费注记**：RETRY_CONNECT=1 ⇒ 建连异常或**响应 status≥500** 时重试一次
  （:461-488，internal_retries 计数）。connect 失败重试无害；**POST 5xx 重试=引擎可能已耗
  prefill 后网关全量重发**——重复推理计费面（图像 prefill 重则代价放大）。429 无自动重试 ✓
  （等待客户端，Retry-After 60/30s 语义正确）。处置=建议档 B5（注记或 VL 车道关 5xx 重试）。
- **心跳/保活**：HEARTBEAT 5s SSE 注释帧（:444-450），AI SDK/OpenAI SDK 兼容忽略；rc3.3 起
  长预填期实时下发（node01 76K token TTFT 12.5s 实测先例在 docstring :90-94）。

### 2.3 健康探测与验证器缺陷（必修承载，详见修复清单 A4/A5/A6）
- **gw-verify P1 探针语义错**（gw-verify.sh:79-85）：无 key POST 业务路径期待 401/403——但
  网关契约=业务路径不代理鉴权（proxy :105-106/:745-757，鉴权归上游 VLLM_API_KEY）。上游无 key
  时该探针**实际触发一次真推理**（max_tokens=1「ping」）且必然 200=误判红。S6 已实证此型
  （VL-NATIVE-RESULT §四「P1-auth 红=rc3.8.2 契约设计面…穿透 200」）——「拒答零上游载」
  注记与契约不符。
- **gw-verify P2 打点序无效**（gw-verify.sh:87）：「17 并发 health 打点→期待 ≥1 发 429」——
  GET/HEAD 在 dispatch :759-766 **免并发槽**（信号量之前返回），health 打点永远不占槽⇒永不
  429。信号量验证须 POST 面。
- **relay_get 静默 502 零留痕**（proxy :730-733）：`except Exception: return 502` 无 log——
  /metrics 502 风暴期（引擎停机窗）成因零可考，本次审查亦只能靠分界时间戳旁证归因。

---

## §三面3 · 占位符匹配（用户点名③）——**本审查最大发现区**

### 3.1 包模板 vs 生产实值差异表（§〇.2 全表引申）

| # | 差异 | 危害定性 | 档 |
|---|---|---|---|
| D1 | 主实例 CHUNK_IDLE_TIMEOUT=**180** 在役（主 unit 09-24 定格）vs rc3.8 O-2 实证值 600（「实测单轮 200-420s…180s 误伤长生成」proxy :28-29）——rc3.8 修了默认值但 unit 显式 180 压过；包模板注释写 600 却**不设键** | 在役主车道携带 rc3.8 已修掉的误伤病值（潜在；当前窗口零流式长生成故未爆发，journal 零 chunk idle 记录=未实现风险非假风险） | **必修 A1** |
| D2 | 包模板缺 INJECT_ENABLE_THINKING 键（→默认 0）vs 8001 在役=1（inject.conf） | 按包部署=文本车道思考链**静默关闭**（rc3.6「注入是 reasoning 链源头开关，引擎端无缺省思考链」）=行为反转 | **必修 A2** |
| D3 | 包模板缺 QUEUE_TIMEOUT（→20）vs 8001 在役=5（zz drop-in） | 部署后准入等待语义漂移（5→20s） | 必修 A3（随 A2 同文件） |
| D4 | 包 unit EnvironmentFile=/opt/aicad-prod/secrets/gateway.env——**该文件 01 不存在**（实测 No such file）；现役主实例密钥位=/etc/default/concurrency-proxy-v2（root 600） | 包 unit 直接 daemon-reload+restart=**启动失败**（EnvironmentFile 无 `-` 容缺前缀，systemd 硬失败）；且包 unit 从未部署到 01（在役 unit=09-24 原件 root 600 非包件 8dc5ecc4） | **必修 A7**（部署序） |
| D5 | 主实例 GW_API_KEY **值在 unit**（root:600 自挡，GATEWAY-MIGRATION §1.1「值在 unit env」在案）+**仅 14 字符**（§7.3 已列轮换位「32+」） | SMOK_KEY 前科律违约（包红线「值绝不入 unit」）+弱密钥 | **必修 A10**（随重启窗迁 EnvironmentFile+轮换） |
| D6 | 10-gateway-hardening.conf 只落 VL 服务；主实例 ProtectSystem=no/NoNewPrivileges=no（systemctl show 实证；MemoryMax=2G 主 unit 自带故资源面无缺） | 硬化不对齐：包声明的落位（README「落位 …v2.service.d/」）未兑现于本尊 | **必修 A8** |
| D7 | VL 模板 UPSTREAM=8898（认证期文）vs 生产实值 8899（转正后，VL-PROMO S2 单行改+restart 在案） | 模板陈旧态；照抄模板=指回已拆线的 8898 | **必修 A9**（注记双态） |
| D8 | 主实例配置三通道（主 unit Environment= 14 键全文 + drop-in×3 + /etc/default env 文件）vs 包目标态单通道 | 配置真源发散：改一处漏两处的漂移温床（D1 即其产物） | 建议 B3（随 A10 重启窗收敛） |
| D9 | 硬化 drop-in 头注仍写「concurrency-proxy-v2.service drop-in」却落位 vl 目录 | 化妆性漂移 | 建议 B6 |
| D10 | gw-verify --offline 只 lint v2 unit+单一 env（gw-verify.sh:62-65） | VL unit/env 双件零 lint 面 | 建议 B4 |

### 3.2 判读
占位符面的总体定谳：**包内模板「值位空」密钥纪律全绿（selfcheck F5 执法在），但「键面」与
生产实态存在 3 处缺键+2 处部署序陷阱**——即占位符匹配的真实缺口不在「值」在「键」与「落位序」。
D2/D4 两处若照包直接部署=行为反转/启动失败，属封包前必须修。

---

## §四面4 · 性能缺陷排查（用户点名④）

### 4.1 架构与每请求开销
- **单进程 asyncio 单线程**（web.run_app :816）：并发=协程级；16+8 槽远非网关瓶颈（引擎
  MAX_RUNNING_REQUESTS=16 才是限片面，99-upstream drop-in 注记对齐在案）。
- **事件循环阻塞点**（同步 CPU 段逐项）：①sanitize 快路径=memchr 子串扫（GB/s 级，忽略）；
  ②**is_stream 全量 json.loads——流式请求必付**（body 含 `"stream"` 字节即 parse 全文，
  :261-266）：MB 级 VL body ~10-100ms 级阻塞，8 并发 VL 同时到达最坏 ~1s 级抖动扩散至其他
  在飞流（单循环串行化）——**rc3.4 prefilter 只免了无 stream 键的请求，VL 流式全命中 parse**；
  ③body_key sha256 前 1MB ~2ms（全量哈希治本后 ~2ms/MB，同量级）；④日志同步写 journal
  （当前量级 12 发/分，忽略）；⑤/gw/metrics JSON 序列化（5s 一发，忽略）。
- **拷贝面**：request.read() 主缓冲 1 份+aiohttp bytes 直写≈1-2 副本/请求（§1.2）；无多余
  全量重序列化路径（sanitize 命中时才重序列化且 VL 真载荷不命中）。
- **连接面**：单 ClientSession+keep-alive 池+DummyCookieJar（:797-799）——GET /metrics 5s
  常探复用池连接 ✓；非流式 `async with session.request` 出池还池 ✓；流式尾 upstream.close()
  （流不可还池，必要开销）✓。**无每请求新建连缺陷**。

### 4.2 历史对照数据（唯一在档；~/gwtest 2026-09-07 rc3.3 时代）
- B1 TTFT 中位：直连 94.1ms vs 经网关 96.4ms=**+2.32ms**；total 197.7→249.1ms（rc3.3 早期
  心跳积压形，后续 rc 修）。
- B3 大 body（404 路径零推理）：1MB +2.9ms / 4MB +5.2ms / 16MB +31.7ms（旧 relay 整读形；
  后 b3 复测 4MB ≈0ms/-46ms、16MB +3653ms=当时非流式劣化 +156% 病——现 relay_plain rc4 流式
  回写已重构，proxy :676-695）。
- B2 并发：rc3.3 修复前 2×/4× 塌（11.9/0.0 tps）→修复后平价（14.1/14.0、9.8/9.8）。
- **判读**：rc3.3 时代网关小请求开销 ms 级、大 body 病已修；但 **rc3.8.2 现役形态零经/不经
  网关对照数据**——用户「未进行完整生产环境质量验证」判词的实证基础；新立带=§七验证窗卡 V4。

### 4.3 与生产实测对照
现役唯一可参照：VL-PROMO §四「直连首发 mm 冷路径 5.22s vs 车道暖 0.61s」（冷热差归因 mm 缓存
非网关）；sparkDash PR 4k arb 族=引擎面指标不经网关路径。**网关前后时延带=空档**（V4 承载）。

---

## §五面5 · 重复建设排查（用户点名⑤）

### 5.1 两实例制（8001+8002）评估 — **判：现状合理，合并=呈裁**
- 事实：代理单 UPSTREAM 无 content 分流/后端表/路径重写（catch-all `/{tail:.*}` :800；wincard
  §4.1 同判）；车道差异=MAX_CONCURRENCY 16/8+DEDUP 1/0+QUEUE_TIMEOUT 5/20——**这些键是
  全局单值，双车道差异只能靠第二实例承载** ⇒ 两实例制=「零代码改动的最小改动面」的必然产物
  （wincard §4.3 裁定链）。
- 转正后两实例指向**同一 upstream 8899**：合并为单实例需代码加 per-lane 并发/dedup（或
  `b'"image_url"'` 字节预检路由——wincard §4.3 已登记 v2.1 呈裁件）。合并收益=减一套 unit/
  env/探针/metrics 运维面；成本=proxy 本尊 md5 变更触发「同日再吸收+TOOL-ANCHORS 三联动」
  在役升级纪律+重验窗。**呈裁 C1**（不自行裁定）。

### 5.2 舰队第三实例（Mac mini M6 :8001）— **判：迁移中间态，收敛已列待办**
GATEWAY-MIGRATION §六/§九：Mac 栈已跑同款 proxy（UPSTREAM=24001 隧道直达 8899）；01:8001
保留原因=「生产 API 在役」（§九.1），但 journal 实证其现役流量已收缩为观测中继+本地 smoke
（3 天 12 发 chat）。**W4 收尾（停 01:8001 或 Mac proxy 改指）=已列用户排期位**——非新重复
建设，属迁移中间态；本审查注记其依赖关系：停 01:8001 前 Mac Prometheus /metrics 靶须改指
（现经 01:8001 中继）。**呈裁 C4**。

### 5.3 包职能重叠 — **判绿（零重叠）**
- fabric-net 守护族（fabric-guard/sentinel/gid-heal/restore-gate）=NCCL/HCA/carrier/引擎死态
  域：grep 全件零 8001/8899/gateway/proxy 引用（实测）。
- selfheal（oom-gate/watchdog）=引擎 OOM 域；selfdiag（census/四查门禁/judge）=boot 与
  判读域——均与网关层无交叠。
- 健康探测多路（gw-verify P4 vs Prometheus /health 5s 常探 vs selfdiag four_check 8899 直查）
  =三层各管一层（部署验证/常观测/引擎门禁），判合理非重复。
- **gw-verify vs selfcheck 内部小重复**：selfcheck F4/F5（run.sh:38-52）以弱化 grep 重复
  lint unit/env 面（gw-verify --offline 已 lint 同面）——层级不同（包完整性 vs 部署配置
  有效性）可接受，注记 B4 顺带收敛。

### 5.4 gw-verify 五探针 vs selfcheck — 详 §2.3（P1/P2 缺陷为真问题，非重复问题）。

---

## §六面6 · 过度设计排查（用户点名⑥）——rc3.x 功能三桶

| 功能（rc 谱系） | 桶 | 依据 |
|---|---|---|
| 信号量准入 G3（QUEUE_TIMEOUT→429） | 生产在用 | 双实例 MAX_CONCURRENCY 在役；零 429=未触顶非未用 |
| SSE 心跳 G1（5s 注释帧） | 生产在用 | 流式长预填必需（rc3.3 P0 前科） |
| TTFT/chunk-idle/write/total 超时族 G2 | 生产在用 | rc3.5/3.8 两次生产事故修复载体 |
| 错误帧 OpenAI 骨架（rc3.8 O-3/3.8.1） | 生产在用 | AI SDK 严格解析兼容必需 |
| /gw/metrics 观测面 G6 | 生产在用 | Prometheus 在抓（旧栈在案+观测中继流量在役） |
| /gw/* 鉴权（GW_API_KEY+hmac） | 生产在用 | 401 正反双向实证 ×2 |
| sanitize_image_placeholders（rc3.7） | 生产在用 | 三次会话中断 RCA 在案；=引擎 _validate 的网关对偶面，VL 车道正确默认 on |
| enable_thinking 注入（rc3.6） | 8001 在用 | inject.conf 在役=思考链源头开关（D2 即其配置漂移风险面） |
| **等值重试抑制 dedup G4** | **在用但收益未证+机理缺陷** | 全窗零触发（journal 零 429）⇒生产收益未证；前缀哈希机理缺陷（§1.3）⇒治本（全量哈希）后保留或**呈裁裁撤 C2** |
| RETRY_CONNECT 5xx 重试 | 在用但带代价 | 重复计费面（§2.2）；connect 失败重试半收益——B5 注记 |
| INJECT 于 VL 车道 | 未用（=0） | 车道差异是否故意=**呈裁 C3** |
| /v1/responses 注入点（rc3.6.1） | 未用 | 引擎在役零流量；保留无害（引擎暴露即激活） |
| **并发限制双轨**（drop-in Environment= 与 env 模板同键） | 配置面重复 | 迁移后须拆 drop-in 三件（99-upstream/inject/zz）入 env 单通道——B3 承载；注意 systemd 语义=EnvironmentFile 覆盖 Environment=，双轨期以 env 文件为真源 |
| 鉴权双层面（网关 /gw/* + 引擎业务面） | 合理非过度 | 分层正确：网关管管理面、引擎管推理面（rc3 P0-2 契约）；注记=引擎 8899 绑 0.0.0.0 直达面（GATEWAY-MIGRATION §7.3 🔴）=网关外旁路风险，属引擎窗议程非本包 |
| 统计面 ttft/queue 分桶计数族 | 在用 | /gw/metrics 消费中 |

**过度设计判定**：无「纯未用+无收益」的冗余功能件；候选裁撤仅 dedup 一项且以治本修复为优先
（裁撤为次选）。真正的冗余在**配置通道**（三通道/D 系）而非功能面。

---

## §七 生产质量验证窗卡（简版；boot/流量面=执行窗）

> 互斥排程（硬约束）：**重测窗在飞占用 8899**（journal 10-14 00:19 起 /metrics 持续 502=
> 引擎停/换靴直接观测）⇒ 网关验证窗排其**复原靴四查绿之后**；本窗卡判读线冻结、点火权归主会话。

| 面 | 设计 | 判读线草案 |
|---|---|---|
| V1 并发压测面 | 修正版 P2 序：8001 梯 8→16→17 并发 POST（stream 假 body max_tokens=1）+8002 梯 4→8→9；读 /gw/metrics | N+1 发必 429；queue_wait_peak 有界（<QUEUE_TIMEOUT）；收尾 active_streams=0（槽零泄漏）；Retry-After 语义在 |
| V2 VL 大 body 面 | 1/4/16/64MB base64 图像 body 经 8002（+>64MB 一发验 413 优雅）；RSS 峰值采样 | 全 200；TTFT 秒级；RSS 峰 <1.5G（MemoryMax 2G 界内）；413 零挂死；与直连 8899 同图读数逐字同（零畸变复证） |
| V3 故障注入面 | 上游失效演练（窗口专用：与引擎窗协调或 8898 测试槽模拟上游）：停 30s→观察→复起 | GET 秒级 502；POST 错误帧+[DONE] 收尾（无静默截断）；复起自愈；journal 留痕含成因（A6 修复后） |
| V4 时延对照面 | 经/不经网关同负载对照：文本 3 档（小/76K/600K 级）TTFT+total+图像 2 档；arb 式 3 发中位 | TTFT 中位增量 <5ms 级立新带（借 gwtest B1 先例 +2.32ms）；total 增量 <3%；rc3.8.2 带外=记录呈裁 |
| V5 观测复证面 | /gw/metrics 全计数族读数；prometheus 靶复绿 | /metrics 200 复现；dedup/queue 计数与压测注入量对账（C2 裁定依据）；零 queue_full_drops |

**封包门**：A 系必修全绿+V1-V4 判读线过（或带外项呈裁有档）→ 方进封包提交（用户裁定「排查
…后再封包提交更新」的执行序承载）。

---

## §八 修复清单（三档汇总）

### 必修（封包前必须修；全部案头可完成件+标注执行窗动作件）
> 状态列=2026-10-14 修复窗执行注记（✅案头已修/⏸留执行窗）；详证=§十修复记录。
| # | 内容 | 类型 | 状态 |
|---|---|---|---|
| A1 | 主实例 CHUNK_IDLE_TIMEOUT 180→600：主 unit env 行改值（**重启窗生效**，与 A10 同窗）+ 包 gateway.env.template 显式补 `CHUNK_IDLE_TIMEOUT=600` 键（注释已写值却缺键的错配闭合） | 案头改件+重启窗 | ✅键面已补（模板:12）；在役 180→600=⏸重启窗 |
| A2 | 包模板补 `INJECT_ENABLE_THINKING=1`（8001 形键面闭合；防包部署静默关思考链）；VL 模板补 `INJECT_ENABLE_THINKING=0` 显式注记 | 案头改件 | ✅双模板已补（主:16/vl:13）+lint 域检查执法（T7 族） |
| A3 | 包模板补 `QUEUE_TIMEOUT=5`（对齐在役 zz drop-in 值） | 案头改件 | ✅已补（模板:8）+域检查 [1,300] |
| A4 | gw-verify P2 打点序修正：GET 免并发槽事实（proxy :759-766）写明+改 17 并发 POST 序（或改判读语义为引擎面限流对照） | 案头改件 | ✅头注+P2 输出改 POST 序（8001 梯 8→16→17/8002 梯 4→8→9+免槽注记） |
| A5 | gw-verify P1 探针语义修正：撤「无 key 业务 POST 必 401」误断言（网关契约=业务路径不代理鉴权，proxy :105-106）；401 断言收敛到 /gw/*（已有）；注记上游 key 契约面 | 案头改件 | ✅P1 改打 /gw/health（401 绿/200=裸奔红）+契约注记；业务 POST 探针撤除 |
| A6 | relay_get 静默 502 补 log.warning（proxy :730-733；成因留痕=下次停机窗可判读） | 案头改件（proxy md5 变更→同日再吸收三联动） | ✅已补（rc3.8.3；三联动重钉 31746cb1+在役面核联动零 md5 绑定） |
| A7 | 部署序注记/修复：包 unit 落 01 前必须先建 /opt/aicad-prod/secrets/gateway.env（现不存在→直接部署=启动失败）；README 部署面分发注记补此序（或 unit 加 `-` 容缺前缀+首验注记） | 案头改件 | ✅README 序改「先 env 后 unit」+双 unit 注记；`-` 前缀弃用（快败优于静默误指 8002，注记在案） |
| A8 | 10-gateway-hardening.conf 补落 /etc/systemd/system/concurrency-proxy-v2.service.d/（主实例 ProtectSystem/NoNewPrivileges 现值 no） | 部署窗动作 | ⏸部署窗（本窗零在役触碰；B6 头注通用化已备双实例落位） |
| A9 | VL 模板 UPSTREAM 8898→8899（或双态注记：认证期 8898/转正态 8899——生产已是后者） | 案头改件 | ✅已改 8899+双态注记（8898 已拆线警告） |
| A10 | 主实例 GW_API_KEY：值迁出 unit 入 EnvironmentFile（0600）+轮换 32+ 字符（SMOK_KEY 律+14 字符双违；GATEWAY-MIGRATION §7.3 轮换位承接） | 重启窗动作 | ⏸重启窗（本窗零在役触碰） |

### 建议（性能优化/精简；随窗顺带）
> 状态列=2026-10-14 修复窗逐项评估处置（✅已做/◐半做/⏸留窗+理由）。
| # | 内容 | 状态 |
|---|---|---|
| B1 | body_key 全量哈希治本（proxy :361 去 `[:MAX_HASH_BYTES]` 切片）：前缀碰撞类全闭+DEDUP=1 可安全复开 VL 车道（治本优于 C2 裁撤） | ✅已做（rc3.8.3-B1，与 A6 同 md5 变更事件；MAX_HASH_BYTES 零残引；确定性/开销同量级 §4.1③） |
| B2 | is_stream 字节级正则预检（`"stream"\s*:\s*true` 匹配先行，未中再 json.loads 回退）：VL 流式 MB 级 body 每请求全量 parse 的循环阻塞消解 | ⏸留验证窗（判读：is_stream 只读不写转发零畸变〔§1.1〕=非正确性缺陷纯性能面；预检语义需实测覆盖〔字符串内嵌 `"stream": true` 误中等边界〕，本窗零验证能力不盲改分类逻辑） |
| B3 | 主实例配置三通道收敛单通道（drop-in 三件键面并入 gateway.env 后摘除；注意 EnvironmentFile 覆盖 Environment= 的 systemd 语义=迁移期真源切换点） | ⏸重启窗承载（在役 systemd 面=零在役触碰禁区；与 A10 同窗） |
| B4 | gw-verify --offline 补 lint vl unit+vl env 双件；lint_env 补 DEDUP_ENABLE/QUEUE_TIMEOUT 域检查；selfcheck F4/F5 与 lint 面去弱重复 | ◐主体已做（--offline 第二实参 lint vl env+vl unit 无条件 lint+域检查 QUEUE[1,300]/DEDUP·INJECT{0,1}+T6/T7 红绿例；F4/F5 弱重复**保留**——§5.3 判层级不同可接受，改门面=低值风险面） |
| B5 | RETRY_CONNECT 5xx 重试的重复计费注记入 README；可选 VL 车道 RETRY_CONNECT=0（图像 prefill 重） | ◐README 红线注记 4 已入；VL 模板 RETRY_CONNECT=0 **不设**（偏离在役现值=行为变化，V2 验证窗裁定；模板保持与在役同面） |
| B6 | 硬化 drop-in 头注通用化（去「v2 专属」措辞，双实例通用件）；VL 模板头部「认证期 8898」段落随 A9 同步 | ✅已做（双 .d 落位注记+VL 头注转正态改写） |
| B7 | payload/__pycache__ 本地产物清理（不在 MANIFEST 不在 git——防误纳；.gitignore 补面） | ✅已做（pycache 已清；.gitignore 既有 `__pycache__/`+`*.pyc` 全局面=补面已足，零新增行） |

### 呈裁（结构性/裁定面；不自行裁定）
| # | 内容 |
|---|---|
| C1 | 两实例合并单实例（proxy v2.1 per-lane 并发/dedup 或 image_url 嗅探路由——wincard §4.3 呈裁位承接）vs 维持两实例制 |
| C2 | dedup 裁撤 vs B1 治本保留（裁定依据=V5 窗 rejected_429_duplicate 对账读数） |
| C3 | VL 车道 INJECT_ENABLE_THINKING 是否对齐 8001=1（VL 思考链需求面） |
| C4 | 01:8001 去留（W4 收敛位：Mac:8001 已承用户入口；停前 Mac Prometheus /metrics 靶须改指） |
| C5 | VL 车道 CHUNK_IDLE/NONSTREAM/FIRST_TOKEN 显式钉值（现默认继承；显式化=防未来默认值变更漂移） |

---

## §九 局限与如实注记

1. 01 主 unit（root:600）正文未直读——其 14 键 Environment= 全文经 systemctl show -p
   Environment 只读查询获得（值面完整）；GW_API_KEY 值按纪律全程未读取未打印（仅存性+长度）。
2. journal 覆盖窗=当前保留段（8001 自 10-11、VL 自 10-13 23:46）；「零 429/零 chunk idle」
   结论限此窗，历史段不可考。
3. ~/gwtest bench 为 rc3.3 时代（09-07）数据，rc3.8.2 无档——V4 立新带为本审查明确建议而非
   已有事实。
4. 引擎侧（8899 SGLang）鉴权/绑定面问题（0.0.0.0 直达旁路）=GATEWAY-MIGRATION §7.3 在案
   呈裁位，属引擎窗议程，本审查仅注记不重复立项。
5. Fabric/NCCL 栈（fabric-net+ring-only+mesh）审查=包职能面 grep 实核（零网关交叠）；其
   判读线/守护机理未逐行深审（用户六面焦点=网关与调用路径；fabric 面无在案事故线索）。

---

## §十 修复窗执行记录（2026-10-14 案头；A 系承接+B 系处置）

> 执行面=tools/packages/gateway/ 包内件（战役仓源）；零在役动作零流量零 systemd 操作
> （本机=01/<node01>，在役双实例全程未触碰）。逐项验证证据在列。

### 10.1 改件清单与验证证据

| 项 | 改件 | 验证 |
|---|---|---|
| A1/A2/A3 | env/gateway.env.template 补 CHUNK_IDLE_TIMEOUT=600（键+错配闭合注记）+INJECT_ENABLE_THINKING=1+QUEUE_TIMEOUT=5 | 模板键↔proxy os.environ.get 全键交叉核：10 键零重复零未识别；--offline 填值形 verdict=0 |
| A2(vl) | env/gateway-vl.env.template 补 INJECT_ENABLE_THINKING=0（显式+呈裁 C3 注记） | 同上交叉核 8 键零异常；T6 vl 模板占位判红 |
| A9 | 同上件 UPSTREAM 8898→8899+双态注记（8898 已拆线警告） | lint UPSTREAM 形合法绿（D1 例 verdict=0） |
| A4/A5 | payload/gw-verify.sh：P1 改打 /gw/health（401 绿/000 无法判/200=GW_API_KEY 未设裸奔红/余码红）+契约注记（业务路径不代理鉴权）；P2 输出改并发 POST 打点序（8001 梯 8→16→17/8002 梯 4→8→9+GET 免槽事实注记）；头注/红线段同步 | bash -n 绿；--selfcheck 七例全 OK（T1-T7）；无参用法面 rc=2 形不变；--live 未跑（零流量纪律，判读语义经干跑核） |
| B4 | 同上件：--offline 增第二实参 lint vl env+vl unit 无条件 lint（vl-unit-lint 面）+lint_env 域检查 QUEUE_TIMEOUT[1,300]/DEDUP_ENABLE{0,1}/INJECT_ENABLE_THINKING{0,1}（键在才查） | D1（主+vl 填值）verdict=0；D2（占位）verdict=1 config-lint；D3（vl QUEUE=9999）verdict=1 **vl-config-lint** 面命中；T6 vl unit 绿+T7 越域红 |
| A6/B1 | payload/concurrency_proxy_v2.py 升 **rc3.8.3**：relay_get except 补 log.warning（method/raw_path/%r，与 relay_plain 同形）；body_key 撤前 1MB 帽（MAX_HASH_BYTES 删零残引）；docstring 谱系段+VERSION 串 | py_compile 绿；grep MAX_HASH_BYTES 零命中；rc3.8.2 仅存谱系史段 |
| A7 | README 部署面分发注记改「先 env 后 unit」序（env 先建→--offline 验绿→落 unit→daemon-reload）+快败设计理由注记；双 unit 补部署序注记（`-` 容缺前缀**弃用**：快败优于裸默认值静默误指 8002 旧上游） | systemd-analyze verify 双 unit rc=0 零告警 |
| B5 | README 红线注记 4：RETRY_CONNECT 5xx 重试=重复推理计费面注记+VL 车道可选 =0 留 V2 裁定 | 文面注记（无行为面） |
| B6 | units/10-gateway-hardening.conf 头注通用化（v2/vl 双 .d 落位注记） | systemd-analyze verify 含 drop-in 引用面零告警 |
| B7 | payload/__pycache__ 清理；.gitignore 既有 `__pycache__/`+`*.pyc`=补面已足零新增 | git status 零 pycache 面；MANIFEST/regen 算式本就排除 |

### 10.2 三联动重钉（A6 proxy md5 变更承载）

- **MANIFEST.md5** 再生成（regen-manifest.sh；11 件）——proxy 新 md5=**9cf978d2**（rc3.8.3）。
- **VERSION**：PKG_VERSION=0.3.2-gwfix1 / FINGERPRINT=**31746cb1** / GIT_ANCHOR=2acc7f3
  （审查基线；改件=本窗 commit 承载，封包窗重钉）/ TOOL_ANCHORS_SYNC=2026-10-14。
- **TOOL-ANCHORS.md** gateway 行同日更新（含 rc3.8.3 领先形与在役态注记）。
- **在役部署面核联动（A6 注记承载）**：双在役 unit ExecStart=纯路径引用
  （/opt/aicad-prod/scripts/concurrency_proxy_v2.py）**零 md5 绑定**；drop-in 零绑定
  ⇒包内 md5 变更不触发在役 unit 联动。~/gateway-migration-staging/proxy/ 副本仍
  e1a01162（三拷贝之一）——**重启/部署窗吸收时须同面同步+sources.tsv 锚同日重钉**
  （selfcheck F3/pkg_sources_check 执法，包领先态现为预期绿注记形）。

### 10.3 selfcheck 终验（全绿）

`bin/gateway selfcheck`：**OK=16 RED=0 UNKNOWN=0，exit 0**（五件套+MANIFEST 11 件
md5sum -c 全绿+指纹对表 31746cb1+在役源锚 e1a01162 绿+F1 七例+F2 py_compile/谱系
rc3.8.3+F3 包领先在役注记绿+F4/F5 红绿双例）。

### 10.4 遗留与承载面（如实注记）

1. **重启窗承载**（A1 在役半+A8 drop-in 落位+A10 密钥迁出+轮换+B3 三通道收敛+rc3.8.3
   在役吸收）：与重测窗互斥排程（§七约束），点火权归主会话。
2. **交付仓同步**：tools/packages/gateway/=战役仓源；交付仓烘焙位
   （/opt/dsv41/packages/gateway/，本机无此位=烘焙机面）**须随封包窗同步拷贝**——
   本窗零交付仓动作（封包窗承载）。
3. B2（is_stream 预检）留验证窗：非正确性缺陷（§1.1 判只读零畸变），预检语义边界
   需实测覆盖，V4 时延对照窗可顺带承载。
4. VL 模板 RETRY_CONNECT=0（B5 可选半）留 V2：模板现保持与在役同面（不设键=默认 1）。
5. F4/F5 弱重复保留（B4 半）：§5.3 判层级不同可接受；收敛=低值风险面不顺带。

——GW-INFRAS 案头审查代理 / 2026-10-14（零流量零 boot；判读线冻结块=§七 V1-V5；呈主会话
核准后 A 系进修复窗、§七进验证窗排程）。**修复窗执行代理同日追加 §十**（A1-A7/A9 案头
全落+B1/B4/B5/B6/B7 处置在案+A8/A10/B2/B3 留窗注记；selfcheck 全绿 exit 0）。
