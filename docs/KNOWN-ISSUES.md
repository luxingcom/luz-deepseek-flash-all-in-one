# 已知现象与质量面（KNOWN ISSUES）

> 本篇收录**已核实**的运行期现象：哪些是已知且可缓解的模型行为，哪些曾被误报为部署缺陷。
> 每条给出：现象原文 → 定位判据 → 缓解方法 → 何时才需要怀疑引擎面。
> 与 `PITFALLS-AND-FAQ.md`（排障词典）的分工：那篇管「部署/运维出了症状怎么查」，本篇管「模型服务质量面的已知现象」。
> 最后更新：2026-10-30。

---

## 1. 思考流重复退化（"hmm 循环"等固定短语循环）

### 现象

模型思考链（reasoning 流）中出现固定短语的循环重复，例：`hmm — hmm: hmm,` 反复出现。
外部站点实测（2026-10-29，4 turn / 216 个 reasoning 块）：

- 思考正文 683,314 字符中出现 `hmm` 共 **16,150 次**（密度 2.4%）；
- 最严重的单块 1,236 次 / 11,797 字符（**10.5%**）；≥10 次的块占 61.6%；
- 密度随会话推进上升：turn 1 仅 0.95%，turn 3 达 **6.50%**（同会话相差 6.8 倍）；
- token 级流式证据显示每个 token 间隔 40-80ms 平稳节拍——是模型在**逐个新生成**，不是客户端回放或拼接；
- 退化块生成耗时显著更长（与生成耗时相关 r≈0.73），单块最长可空转 100 秒以上；最终正文输出正常。

### 定位判据（先分清模型面还是引擎面）

**指向模型/采样面的特征**（本例全部命中）：

- 退化只发生在思考流，正文（text）输出正常；
- 密度随上下文长度与 reasoning effort 档位增长；
- token 间隔平稳（40-80ms），无 0ms 突发或超大抖动；
- 显式下发采样参数（见下）后现象减轻或消失。

**才需要怀疑引擎/部署面的特征**：

- 退化与特定 boot 形/参数面绑定（换形即变）；
- 质量门（GSM8K / needle / qeval）同步变红；
- 正文输出同坏、乱码或截断；
- token 间隔异常（0ms 突发=疑似回放，超大抖动=链路问题）。

### 根因（已核实）

**模型固有行为 × 采样未抑制**，与本项目部署参数无关：

1. 本栈**引擎不注入、不改写任何采样参数**（serve 参数全为容量/调度/解析器类，见
   `deploy/SPEC6-SERVE-REF.md`）；网关缺省面同样不碰采样参数（注入仅
   `chat_template_kwargs.thinking`/`enable_thinking` 思考开关双键）。
2. 模型权重的缺省采样参数（`generation_config.json` 实读）为
   **`temperature=1.0` / `top_p=1.0` / 无重复惩罚**。客户端若不显式发采样参数，
   生效的就是这套最宽松组合。
3. 「最宽松采样 + 超长上下文（≳300-400K 已缓存）+ 高 reasoning effort」的组合，
   是长思考链模型发生短语循环退化的经典工况——采样没有惩罚重复短语的机制时，
   模型一旦陷入某个口头禅循环就会持续生成它。

### 缓解方法（客户端侧，按优先级）

1. **显式下发采样参数，不要依赖缺省**：
   `temperature=0.5~0.7`（不要超过 0.7）、`top_p=0.95`。
   **产品化处置注记（2026-10-30，0.3.4re DF-05）**：本条已产品化为网关
   **保守采样缺省档**——`INJECT_CONSERVATIVE_SAMPLING` 环境开关（**默认 0=关**，
   现行为零变化）开启时，网关对未显式携带采样参数的 POST chat 请求缺省注入
   temperature/top_p/frequency_penalty 三键（建议带 0.6/0.95/0.4，经
   `CONSERVATIVE_TEMPERATURE`/`CONSERVATIVE_TOP_P`/`CONSERVATIVE_FREQUENCY_PENALTY`
   三键可调）；**客户端已显式传任一键则完全不动请求体**（客户端显式传参永远
   优先），开关状态入代理横幅与 METRICS 双计数可审计。配置面见
   `tools/packages/gateway/payload/env/gateway.env.template`，实现面见
   `tools/packages/gateway/payload/concurrency_proxy_v2.py`（docstring DF-05 节）。
2. **长会话加重复惩罚**：上下文 >200K 或 effort≥high 时加
   `frequency_penalty=0.3~0.5`（或等价 `repetition_penalty=1.05~1.1`）。
3. **适时降 effort 档**：单 turn 思考字符持续超过 ~50K、或会话累计上下文 >300K、
   或观察到同会话内退化密度单调上升——都是降档信号（如 max→high→medium）。
4. **配客户端超时/中止**：`maxTokens` 给到 32768 时，一个退化块可空转 100s+，
   应允许用户中止并重试。
5. **检测口径**（客户端作者可自建）：在 reasoning 流上按块滑窗统计——
   - 填充词密度：如 `\bhmm\b` 次数/千字符，>20 即告警（本例热点块达 105/千字符）；
   - 重复 n-gram 率：4-gram 去重比，窗口 2K 字符；
   - 连续同一短语 ≥5 次即提示「思考可能退化」并允许中止/重试；
   - 遥测记录 `reasoningChars` / 填充词计数 / `ttft` / `generationMs`，
     便于事后对账（外部站点的逐块 CSV 即示范口径）。

### 补充说明

- 本栈质量门（GSM8K ≥0.97、needle 600k、qeval）均在 `temperature=0.6` 短上下文工况验证，
  **不覆盖**「缺省采样 + 超长思考」工况；该工况下的表现没有质量声明，请按上文显式下发参数
  （保守采样档开启态的质量带按 DF-05 验收门另行定标，未定标前开启态读数不作质量声明）。
- 如需进一步归因（排除投机解码在该工况的影响），可做 SPEC=0/SPEC=1 双臂 A/B——
  属于受控测量窗操作，不在本文档范围。

---

## 2. 曾经被误报为缺陷、实际非本仓问题的项（备查）

外部站点踩坑手册中以下指控经逐条核实**不成立**，列出备查（避免下一个采用者重复排查）：

| 手册指控 | 核实结论 |
|---|---|
| 「引擎只绑回环 127.0.0.1，别处探活必 000」 | 两形态并存（2026-10-30 裁定统一）：本仓四个公开 boot 脚本缺省 `--host 0.0.0.0`（引擎口四机可达）；「只绑回环」是参考产线形由部署侧自行收敛的站点改动。两种形态的探活口径：缺省形打 head 机地址即可，回环形必须 ssh 到 head 机打回环（别处 000 属预期）。000 的常见原因仍是打错了机器（不在 head 机上 curl 回环），见 [DEPLOY-STEP-BY-STEP.md](DEPLOY-STEP-BY-STEP.md) §4.5/§8.1 |
| 「仓库里两代表并存、没标哪代在役」 | 在役代际标注在位（README 头部/SPEC6 头部/RING-COMPAT 双列/ENV-CHAIN 演进链）；真实混淆源是个别 0.3.1 期锚表快照未滚动，已随 2026-10-30 治理加注 |
| 「必装织网件不在交付包=缺件」 | 织网/拓扑件历来在基础设施仓（见 README「基础设施仓」段与 `docs/RING-DEPLOY.md` §2），交付包小≠缺件 |
| 「旧文说缓存放大 4 倍收益测不出」 | 本仓无此文本；实测结论相反（见 `docs/RUNTIME-PARAMETERS.md` engram 键条目：扩容收益看淘汰次数） |
| 「拿脱敏仓副本比镜像内烘焙件=账目错」 | 脱敏史已自我披露（`docs/registry/SANITIZATION-20261013.md`）；判件身份的正典顺序见 `UPGRADE-0.3.2.md` §3 |

---

## 3. Grafana 上前缀缓存命中率周期性跳 0（`sglang:cache_hit_rate` gauge 伪零）

**核实日期：2026-10-30；证据来源：上游 sgl-project/sglang issue #45119（修复 PR #45122 open 未合）+ 本栈在役引擎 /metrics 实测快照（计数器有真实流量与命中、同页 gauge=0.0）。**

### 现象

Grafana 面板 / `avg_over_time` 查询 / 告警里，前缀缓存命中率在真实值（如 ~0.96）与 0.0 之间
来回跳。缓存实际健康，看起来却像反复「丢缓存」。

### 定位判据

- 只有 **gauge**（`sglang:cache_hit_rate`）在跳 0；同页累计计数器
  `sglang:prefill_effective_tokens_total`（mode=input/device_hit/host_hit/storage_hit）
  持续单调增长且命中计数非零——两面对照即缺陷签名；
- 跳 0 与载荷形态相关：分块 prefill（长 prompt）下一个请求产生多份 prefill 报告，
  绝大多数报告不含命中段，gauge 按「每报告」发布即写出 0.0（上游实测 233 份报告仅
  15.5% 含命中）；
- 引擎侧功能（KV 缓存、radix tree、吞吐/时延）无任何异常——纯计量面缺陷。

### 根因（上游缺陷，非本仓部署问题）

引擎把每份 prefill 报告的当报告命中率直发 gauge：无命中的报告发布 0.0（极端空报告
`total_tokens==0` 时也写 0.0）。gauge 的 per-report 语义与面板期望的窗口语义错配。
上游修复 PR #45122 仅加空报告跳写守卫（作者自注非症状全修），截本篇入册时未合入。

### 缓解方法（监控侧，已落地；镜像不动）

1. **正典口径（推荐）**：改用计数器算窗口命中率——
   `rate(sglang:prefill_effective_tokens_total{mode=~"device_hit|host_hit|storage_hit"}[5m])
   / rate(sglang:prefill_effective_tokens_total[5m])`
   （该计数器 HELP 文档自述即此式）；
2. **gauge 过滤（兜底）**：对 gauge 查询加 `!= 0` 或窗口过滤并保留最后有效值——注意
   真 0% 冷缓存命中会被误持旧值，只可作兜底并带降级注记；
3. **工具面**：`tools/obs/cache_hit_caliber.py` 已内置上述两级口径（两快照窗口/单快照
   累计 + gauge 过滤兜底 + 缺陷签名自动判读），`--lint` 守卫禁止仓内工具裸读 gauge
   判据；仓内既有裸快照记录位（`tools/kvlife_driver.py` MET_KEYS）已加豁免标注，
   快照值只存原始数不作判据；
4. **镜像面后续**：随镜像窗 cherry-pick PR #45122；合入后 gauge 仍为 per-report 语义，
   计数器口径仍是正典（口径纪律详见 `docs/registry/BENCHMARK-SOURCE.md` §十一）。

---

## 4. 开 `--kv-cache-dtype nvfp4` 后长上下文检索隐蔽崩塌（fp8 标定 k/v_scale 被误当 NVFP4 全局 scale）

**核实日期：2026-10-30；证据来源：上游 sgl-project/sglang [issue #42369](https://github.com/sgl-project/sglang/issues/42369)（无修复 release；关联 PR #42419 未合）+ 本栈 serve 参数面与生产 checkpoint 只读亲核（见「缓解方法」末段）。**

### 现象

以 `--kv-cache-dtype nvfp4` 服务「带 fp8 标定 KV scales 的 checkpoint」时，长上下文
检索隐蔽崩塌：needle 式评测得分崩（上游报告 d50=1/4、d500=0/4）、答案复读；短
prompt、工具调用、视觉路径与启动日志全部正常，行为跨靴确定，且**没有任何一行日志
提到 scales**——除 needle 式评测外无物能察觉。

### 定位判据

- 组合签名：runtime `--kv-cache-dtype nvfp4` × checkpoint
  `quantization_config.kv_cache_scheme.num_bits=8`（fp8 标定）且权重文件里带逐层
  `*.self_attn.{k,v}_scale` 张量（per-layer `[1]` 标量）；
- 症状只出现在长上下文检索面，短上下文/工具调用/健康检查全绿。

### 根因（上游缺陷，非本仓部署问题）

引擎经 `maybe_remap_kv_scale_name` / 模型 `load_weights` 在 nvfp4 运行时 dtype 下
仍加载 fp8 标定的 k/v_scale 张量并当作 NVFP4 全局 scale 使用——fp8 标定是
amax/448 几何、NVFP4 全局 scale 是 amax/6 几何，整体约 **75 倍失配**，且加载期
无 num_bits × 运行时 dtype 校验、无告警。上游尚未发布修复。

### 缓解方法（host 侧，已落地；镜像不动）

上游缺陷根因在引擎加载面，host 侧不做源码改写，而是把「开门前置校验+正法手术+
上线验收」工具化（`tools/upstream/nvfp4-kv/` 三件套，与战役仓正典件双面同 md5）：

1. **守卫（加载期校验代位）**：`nvfp4_kv_scale_guard.py` 联合 lint serve 参数面
   （argv/boot/profile/env）与 checkpoint 面（safetensors headers + config），对
   「nvfp4 × fp8 标定 scales」组合 fail-closed 判红；对 num_bits=4 正当标定形与
   剥离形（动态 scale 路径）放行；runtime 未启用时作为开门前置断言面常备。
2. **剥 scales 手术（上游报告者生产验证的正法）**：`nvfp4_strip_kv_scales.py`
   缺省 dry-run；`--apply` 从 `model*.safetensors` 删除
   `*.self_attn.{k,v}_scale`（缺省广义含一切 `*.k_scale/.v_scale`）并重写 header
   offsets、把 `kv_cache_scheme` 置 null——其余张量数据字节级原样保留（内建逐张量
   md5 校验+原件 `.bak` 留底+手术台账），术后引擎走动态 scale 路径。
3. **上线验收门**：`nvfp4_needle_gate.py`（d50/d500 两档各 4 针，剥后必须 4/4+4/4
   方放行；剥前相位只取证不放行）。
4. **当前生产态（2026-10-30 亲核）**：本栈 serve 参数面无 `--kv-cache-dtype`
   （KV cache 走 fp8 几何），生产 checkpoint 48 分片 header 亲读零
   k/v_scale 张量、无 `kv_cache_scheme` 声明——**不命中缺陷态，无需手术**；三件套
   为「未来开 nvfp4 KV」的前置断言面。上游发布「加载期校验+不匹配回落动态」后，
   手术对新 checkpoint 退役（详见该目录 `README.md` 升级关注节）。

## 5. DSPARK 投机解码与普通解码的贪心输出分叉（确定性敏感流量须走 plain 车道）

**核实日期：2026-10-30；证据来源：上游 sgl-project/sglang [issue #45525](https://github.com/sgl-project/sglang/issues/45525)（[Bug] DeepSeek-V4-Flash: speculative and ordinary decoding produce different greedy outputs；2026-10-21 提交，open 零评论无修复）+ 本栈 boot 链/serve 参数面/容器活体只读亲核（见「缓解方法」末段）。**

### 现象

同 checkpoint、同前缀、temperature=0 下，DSPARK 投机解码的 verify 路径与普通
decode 路径产出**不同的目标 logits 与不同的贪心 token**（上游报告近并列 top-2
约 0.25–0.5 logit 差、胜者翻转）；且**同一路径重复请求结果也会翻转**——即不稳
定性并非投机执行独有，责任内核尚未定位。对拍、贪心锚定等确定性敏感评测在此
栈上做 spec 车道与 plain 车道的交叉读数会得到伪差异。

### 定位判据

- 组合签名：speculative 解码开启（`--speculative-algorithm DSPARK`）×贪心
  （T=0）× 对拍/逐位比较类流量；
- 上游环境为 H20×8/TP4/dsv4/marlin/fp8 KV/v0.5.22，与本栈（DGX Spark/
  flashinfer_mxfp4）不同型——本栈按同族缺陷（speculative×DeepSeek V4 贪心
  分叉，spec 算法同为 DSPARK）作预防面处置，未声称本栈已复现；
- 同路径重复请求也翻转=非确定底噪，与 spec 开关无一一对应关系。

### 根因（上游缺陷，非本仓部署问题）

责任内核未定位（上游 open 零评论）。本仓**不做**引擎侧追因与补丁，也不开
`SGLANG_ENABLE_DETERMINISTIC_INFERENCE` 确定性开关（内部裁定禁键；且上游观察
已证明同路径重复亦翻转，开关治不了底噪）。

### 缓解方法（host 侧，已落地；镜像不动）

确定性敏感的评测/对拍流量**路由到无 DSPARK 的 plain decode 服务**（同
checkpoint 双服务，上游报告者即如此对照取证）；常规业务（生产 spec 口）不动。
落地件=`tools/upstream/dsp45525-plainroute/`（与战役仓正典件双面同 md5）：

1. **env/serve 参数面（`plain-face-45525.env`）**：plain 服务 boot 调用面 4 键
   ——`CTN_PREFIX=r3plain`（独立容器前缀，双服务并存即设计）、`API_PORT=8897`
   （全树零占用口）、`SPEC=0`（boot 链既有开关：非 1 即不加
   `--speculative-algorithm DSPARK`，零镜像改动）、`DSV45525_PLAIN_BASE`
   （客户端路由锚）。`PROD_SPEC_EXTRA_ARGS` 实测不含任何 `--speculative*` 参，
   plain 服务整套沿用同参，与生产**仅差 spec 一面**。
2. **守卫（`plainroute_guard_45525.sh`）**：G1 参数面（canonical env 与基线门
   钉值互证=零侵入、boot 链 SPEC 开关逐字在位、EXTRA 参无 spec 夹带、参数件
   形态）；G2 plain 活体面（状态感知：plain 容器 launch 面零 `--speculative`
   +8897 健康方为绿）；G3 生产 spec 面旁核（只读直证生产口仍带 DSPARK=常规
   业务零侵入）；G4 路由武装执法（评测窗 `DSV45525_DETERMINISM_SENSITIVE=1`
   时路由锚缺失/错指/车道落空=红，fail-closed）。
3. **lint（`plainroute_lint_45525.sh`）**：确定性敏感工具（`ds_gate.py` 的
   8899 生产口硬拒、`t62c_anchor_gsm8k.sh` 的测试线红线）纪律行在位防漂移；
   kit 双面同件+`SOURCE-MD5.txt` 对表；登记行在册。性能面工具直连生产口
   （吞吐/时延读数非确定性敏感）不入约束。
4. **当前态（2026-10-30 亲核）**：守卫实面全绿——生产容器仍带
   `--speculative-algorithm DSPARK`（只读 inspect 直证，零侵入）；plain 服务
   未部署（规避处于「参数面+执法面就绪、活体面待专门窗」态），确定性敏感
   流量维持既有测试线纪律。上游定位责任内核并发布修复后，活体面转观察位
   （该目录 `README.md` 退役条款）。

## 6. bench_serving 开环 `--request-rate` 长压测 offered load 系统性偏低（到达漂移）

**核实日期：2026-10-30；证据来源：上游 sgl-project/sglang [PR #44162](https://github.com/sgl-project/sglang/pull/44162)（fixes issue #43930；open 未合）+ 本栈本地主干 checkout 只读亲核（见「缓解方法」末段）。**

### 现象

用上游 `bench_serving` 以有限 `--request-rate` 跑开环基准（延迟/吞吐长压测）时，
实际请求到达率随请求数累积落后于名义值，且请求数越多落后越多——上游报告
100 req/s 档实测仅 ~68 req/s（−32%）、400 req/s 档实测仅 ~190 req/s（−52%）。
后果：队列深度、TTFT/延迟分位、吞吐全部在错误的负载点上采样，长压测读数整体
失真（系统性偏置，不可事后折算修正——漂移量依赖 consumer 每请求工作时长）。

### 定位判据

- 组合签名：`python/sglang/benchmark/serving.py` 的 `get_request` 泊松分支
  （非 trace、`request_rate` 有限）中 `interval = np.random.exponential(1.0 / request_rate)`
  之后紧跟 `await asyncio.sleep(interval)`（睡起点=consumer 恢复 generator 的
  时刻，而非该请求的绝对到达时刻）；
- 只影响开环有限速率口径；`--request-rate inf`、闭环并发类量具、trace replay
  分支（`--use-trace-timestamps`，本身即绝对时刻法）不受影响。

### 根因（上游缺陷，非本仓部署问题）

sleep 以「consumer 恢复 generator」为起点，而 consumer 在两次 pull 之间要做
发包、收流、记账等工作，事件循环唤醒还有晚醒开销——这些时间逐请求累进到达
间隔，等效于把 consumer 工作时长加进每个 gap，累积成到达漂移。上游修法
（#44162）：维护累积单调绝对到达时刻 `target_arrival_time`（每个 interval 累加
进去），yield 请求前只 sleep `target - now` 的剩余量；迟到请求立即追上而不重置
时刻表；移除最后一个请求后的 terminal sleep 但保留该次 exponential draw
（RNG 兼容）。本缺陷在 bench 客户端，与引擎镜像无关。

### 缓解方法（host 侧，已落地；镜像不动）

压测口径侧落地（`tools/upstream/bench-arrival/` 两件套，与战役仓正典件双面同
md5，`SOURCE-MD5.txt` 互证）：

1. **修补版载体**：`bench_serving_44162.py`（薄启动器）——凡开环有限速率基准
   一律经它跑：定位 sglang 源码树/安装根（缺位 rc2 fail-closed），判别
   `get_request`；缺陷版则**运行时注入 #44162 修补版**（exec 进模块自身
   `__dict__`，np/time/asyncio 继承模块对象=draw 序与 RNG state 兼容）并原样
   透传全部 CLI 参数；已修复面自动 ALREADY-FIXED 透传。上游源码树/镜像零改动。
   <!-- bench-arrival: patched -->
2. **口径守卫**：`bench_arrival_guard.py`——`--check` 判别任一 sglang 面的
   缺陷态（VULNERABLE/FIXED/UNKNOWN 三态 fail-closed）；`--lint` 扫仓面「裸跑
   bench_serving 且 `--request-rate` 有限值」的口径=REFUSE，豁免标记
   `bench-arrival: patched/closed-loop/doc`。
3. **本仓正典量具不受影响（2026-10-30 grep 亲核）**：sd_bench（CFG-31 锚）/
   de_c48_bench（CFG-32）/conc_pr_driver（CFG-30）均闭环并发驱动、零到达率
   调度面，现行读数无本缺陷偏置；本套=未来开环基准（PR 复测、SLO 校验、与
   上游数字对齐）的前置口径面。本地 sglang 主干 checkout（79cafec0）
   `benchmark/serving.py:1111-1123` 守卫实测 VULNERABLE（rc1，输出在档）。
4. **退役条件**：上游 #44162 合入发布后 `--check` 转 FIXED ⇒ 启动器自动透传，
   本套转维持态（判别器 FIXED 语义长青）。同窗关联 #46504（多轮输入 token 计
   serving metrics）、#47050（timed-trace replay）。

## 7. 0.3.4re 修复批后仍开放的事项（引擎侧呈批位与已知残留）

**登记日期：2026-10-30；来源：0.3.4re 缺陷修复批收口呈报（任务书
`035-W0-TASKBOOK-20261030.md` DF/EQ 章逐项依赖注记）——以下事项本批**未修**，
均需独立批文与专门窗口，列出备查防「看到修复批就以为全清了」。**

| 事项 | 一句话 | 为什么没随 0.3.4re 批修 | 处置去向 |
|---|---|---|---|
| DF-06 spec 三列接线 | census 面板 `d_spec_steps`/`d_verified`/`d_accept_rate` 三列结构性空载（`is_target_verify` 在 spec-v2 形 decode 路径从未为真），投机接受率物理面读数缺失 | 根因在引擎侧接线面，属引擎在役面（overlay/镜像通道），需停机窗+判读窗+批文 | 0 靴开发可先行（staging 账外），活体读数随首个在役验证窗搭车 |
| DF-07 引擎页映射导出 | F6-A 满池召回判读 27/30 有条件闭合的残余 3 FAIL，根因=引擎不导出页映射，KV 页级重建审计留人工缺口 | 引擎导出面属镜像/引擎在役面（可与上游 #44557 组同域并案） | 先随在役窗搭车复跑 F6-A judge #8 确认缺口仍在，再对表补导出面 |
| DF-08 grammar cache 有界化 | grammar cache 写入面现状≈零、属前瞻性前置安全件（CVE-2025-32381 同类风险面） | 案头方案已备档，但方案采纳/投递通道/缺省上限与 env 键名三项呈批位未批 | 批后实施（TTL/上限，env 64 保守起点实测定标），G-CACHE xfail 护栏随窗翻转 |
| DF-09 B15 FP4 漂移核查 | FP4 编码漂移 B>C>A 序在 0.3.3 只登记未核查，跨产线读数对照的精度口径带未定义差 | 核查采证属判读窗（量具运行），不单开窗口 | 与 KV/SWA 精度判词窗合窗（顶层全等、items 级 2.5e-7 微差界） |
| DF-10 DSML 修复面 | T33-01B/01C 字面解析/defer_loading 过滤/prefix 续写三面修复挂在条件位 | 条件位纪律：须「真实客户流量证据+协议兼容评审」先行，条件不满足不主动消耗窗口 | 条件满足后按候选 memo 执行并逐条翻转 20 条 xfail |
| DF-11 N=193 eager 观察 | eager 面 N=193 Lt ws>0 非图内（与 A2 绿基线同形，判非缺陷） | 观察位维持即达标 | 仅当 0.3.5 图捕获窗（W4/W6）触碰该面时对表复评 |
| boot 断言族产线验证靴 | EQ-02/EQ-03/UP43050 等新断言与禁参的 boot md5 连带 BL/CFG 行重钉+四机同步核+同靴抽测 | boot 链变更生效核对需停机窗+判读窗 | 随下次停机窗承载（负例拒起直证+DE c8/PR 64k 锚 ±5% 抽测） |
| 公开树 fabric-restore-gate.sh | DF-02 参数化新形只落战役仓，公开树该件仍为旧形 | fabric-net payload 整面同步未随本批 | 待 fabric-net 整面同步窗（同步时连带 README 适配清单核对） |
| EQ-13 交付物未随公开树 | `r3-gate-engram-quota.sh`（selfdiag 包）等 EQ-13 文件面只在战役仓 `tools/packages/selfdiag/`，公开树 `tools/packages/` 无 selfdiag 包 | selfdiag 整包未随移植批入公开树（CHANGELOG EQ-13 节如实标注战役仓面） | 待 selfdiag 包整面公开窗；公开树使用者暂无该 guard |
| 脱敏存量面（主机名/内部路径） | 0.3.1/0.3.2 期历史存量件（证据档、旧报告、工具缺省值）中仍保留 `dgxspark01-04`/`macgw` 主机名与 `migrate-assets`/`luz030-opt-campaign`/`dsv41-flash-dgxsparks` 内部路径（旧 10-13 扫描「政策保留」面；0.3.4re 移植件零命中；内网 IP 全树已清零） | 按密钥扫描策略保留（清单=`SCAN-REPORT.md`）；主机名/路径不属密钥面，清理涉存量证据件完整性 | 如需零命中口径，另批整树脱敏窗（会改写历史证据件） |
| 公开树 `.bak` 备份件 | `deploy/bin/r3-stop.sh.bak-pre-df03-20261030`（DF-03 单元明示留档）与 `deploy/b12x/` 存量 4 件 `.bak`（`comm.bak-prerocenante-r2`+`roce_ring/` 下 3 件 `.bak-pre-k1b`） | DF-03 件有 CHANGELOG 登记；b12x 存量件为历史窗留档、不属装配面 | b12x 存量件无处置注记，是否移出公开树待发布收口批裁定 |

上游镜像补丁类（备方案未实施，随镜像窗承载）：#45122（cache_hit_rate 空报告
跳写，见 §3）、UP42369 修复 release（见 §4）、UP45525 责任内核定位（见 §5）、
UP43050 idle 路径修复（见 CHANGELOG UP43050 节「升级面指引」）。

---

*本篇由 2026-10-30 公开仓文档治理批次建立；新增已知现象请按「现象→判据→根因→缓解」四段式追加，并注明核实日期与证据来源。*
