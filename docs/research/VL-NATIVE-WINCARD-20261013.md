# VL-NATIVE-WINCARD · 路径 B 开窗卡（SGLang 基座原生启用 V4.1 视觉 + V4.0exp VL 同基座承载）— 2026-10-13

> **性质**：案头预备窗卡（零 boot/零 docker/零流量/零集群；全源只读，唯一写=本件）。法源=
> docs/research/SGVISION-SURVEY-20261013.md（commit 3260add，本卡全量承接其证据锚）+
> 主会话用户裁定六要点（路径 B 开窗）。标注律同 SURVEY：【实测】/【转录】/〔推演〕。
> boot 段执行不在本窗——本卡只出设计与判读线冻结，点火权归主会话。
> **用户裁定六要点承接**：①SGLang 基座原生启用 V4.1 视觉（knapcio 式，0-2 文件预期）；
> ②V4.0exp VL 也在本基座跑起来（替代 vLLM 容器，凑合态清除）；③单基座交付（网盘分发
> 只含这一个 SGLang 基座容器）；④**测试简化令**（不逐个测试/禁笨办法全电池；验证聚焦=
> 算法验证+工程接线+回归哨兵）；⑤网关 VL 端点路由配套；⑥完成后补充重烘焙。

---

## §0 执行摘要（四大定谳）

1. **V4.1-Flash 开图像的最小参数集=空集（0 旗 0 文件）**。enable_multimodal 缺省 True
   （arg_groups/fields/mm.py:27-31 `Optional[bool]...=None` → model_config.py:531-552 仅四
   问题架构例外，DeepSeek 不在列）；auto-detect 门 `has_dsv41_vision = model_type==
   "deepseek_v41" and vision_n_layers>0`（model_config.py:657-669）→ is_multimodal+
   is_image_understandable 双真；处理器按类自动注册（multimodal/processors/deepseek_v41.py:22
   `models=[DeepseekV4ForCausalLM]`，tokenizer_manager.py:562-572 pkgutil 扫描）；**chat 编码
   图像分支静态在树闭环**（SURVEY 待核①案头闭合，见 §1.2）——与 knapcio 零旗生产实证同构。
2. **生产 51 键文本靴此刻就是 mm 活体**：FL6-PROMO 生产靴（r3prod/8899/SPEC6）日志三直证
   （mm 后端 triton_attn 两行+mm KV 0.10G 预留，<prod-log>:236-237/:277）
   =视觉塔权重已装载（266 视觉键，模型侧 vision=None 才 skip，deepseek_v4.py:5455-5464——
   生产 vision≠None）。⇒「文本靴 vs VL 靴」在 V4.1 线**不是两种代码形态，只是流量形态之差**；
   认证期独立 VL 靴的必要性=隔离 mm×k6×CG 无先例面与 mm 足迹前科（§3.1），非启用需要。
3. **V4.0exp VL 在本基座=归档 overlay 整树复原（非新 graft）**：28 件谱系在
   ~/archive-20261012/overlay-superseded/sglang-overlay.v4vl-79cafec0/（集合指纹 f26c4888，
   MANIFEST.csv:5「若拟重开须按本行整树复原」），判据链（STDVL-K6CG-R2-C24T）全在档；
   检查点四机在位（01=~/models/DeepSeek-V4-Flash-Vision-Exp 48 分片实测在位）。mm 面历史=
   OPEN-26 停飞→L0/L0RETRY 三件根治（发后 ≤5s 满额归还复证）→F7 P2 正式复飞窗**让位未跑**
   →10-09 STDVL 文本定板→10-13 归档。本窗 V4.0exp 臂承载=复原+图像冒烟+正式复飞读数（§2.4）。
4. **网关接线=零改在役 proxy 本尊+第二实例车道**：在役 concurrency-proxy-v2（8001→8899）
   对 image_url 载荷天然透传兼容（rc3.7 净化只咬 `<｜deepseek_image｜>` 字面文本，不咬
   base64 data URL）；VL 车道=新增第二实例 unit（PORT=8002→UPSTREAM=8898，转正后 8899），
   车道制分流替代 content 嗅探=最小改动面（§4）。

---

## §一 面1 · 启用面精定（main-79cafec0，~/sglang-main-src 只读）

### 1.1 serve 参数面（SURVEY §C.1 承接精化）

| 面 | 精确行为 | 锚 |
|---|---|---|
| mm 总开关 | `--enable-multimodal`（mm 命名空间）缺省 None→**缺省 True**；仅 Gemma3/Llama4/Step3VL/Inkling 四架构+MIMO_V2 无 vision/audio_config 变体例外 | arg_groups/fields/mm.py:27-31；model_config.py:531-552 |
| auto-detect 门 | `model_type=="deepseek_v41" ∧ vision_n_layers>0` → is_multimodal ∧ is_image_understandable（后者显式 `if is_multimodal and has_dsv41_vision: True`） | model_config.py:657-669 |
| 处理器注册 | is_multimodal → `import_processors("sglang.srt.multimodal.processors")` 自动扫描；DeepseekV41ImageProcessor **按类注册** `models=[DeepseekV4ForCausalLM]`，processor-file-free（读 hf_config+tokenizer；检查点无 preprocessor_config.json 非必需） | tokenizer_manager.py:562-572；processors/deepseek_v41.py:22-33 |
| 图像处理三后端 | `get_mm().image_processor_backend`：auto→rust（rust_extensions._multimodal 的 dsv41.resize_patchify，失败回退 PIL 告警）／pil／gpu（env SGLANG_ENCODER_IMAGE_PROCESSOR_USE_GPU）；缺省 auto | processors/deepseek_v41.py:38-62 |
| mm 注意力后端 | 未设时自动 `triton_attn`（生产日志直证两行） | 生产日志 :236-237；fields/mm.py mm_attention_backend 可选 |
| chunked prefill×mm | `is_multimodal_chunked_prefill_supported`：不支持清单（Grok1V/Llava/Mllama/MossVL/CLIP）**不含 DeepSeek** → 支持；mm 逐项 chunk 感知编码在树（mm_schedule.py `_get_chunked_embedding_by_item` 图 span 不跨 chunk）；Transformers 后端才强制关（scheduler.py:1315-1320，我方 native 不涉） | model_config.py:2356-2371；managers/mm_schedule.py:433-446 |
| 前向 mm 门 | `vision≠None ∧ ¬decode ∧ ¬target_verify ∧ mm_inputs 有` → `_prepare_mm_embeddings`；decode/verify 期 image hash 经 MM_PAD_SHIFT_VALUE masked_fill 还原（**target_verify 结构性豁免=k6 投机与 mm 的共面接口在树**） | deepseek_v4.py:5082-5102 |
| 权重装载 | vision≠None 时 vision./aligner./image_* 与 bias_vl 全装载（skip 仅文本形） | deepseek_v4.py:5455-5464 |
| 视觉塔 TP 面 | VisionAttention `use_qkv_parallel+use_data_parallel`（复制塔，不切 heads）；约束=TP/EP/DP 无 CP/PP/MoE-A2A——我方 TP4+a2a none 满足（knapcio tp3_pad 视觉 heads 垫片=TP3 专用，我方不需要） | deepseek_v41_vit.py:55-71；deepseek_v4.py:4859-4867 |

**结论：V4.1-Flash serve 开图像的最小参数集=∅（零旗零文件）**。可选（非启用必需，首靴
一律不加，登记待用）：`--mm-attention-backend`、`image_processor_backend`（mm_process_config
内）、`--allowed-media-domains`（外源 URL 白名单，安全面）、`--limit-mm-data-per-request`
（防滥用）。**首靴纪律=生产 SERVER_ARGS 逐字复用**（见 §3.2），vl 面零增量。

### 1.2 chat 编码图像分支（SURVEY 待核① **案头闭合**）【实测】

`entrypoints/openai/encoding_dsv41.py` + `serving_chat.py` 全链静态在树：
- `_process_image_blocks`（encoding_dsv41.py:531-562）：image_url content 块 → `<｜deepseek_image｜>`
  占位文本+图像记录表；`_validate_no_image_sp_tokens`（:565-575）拒文本形占位符（=网关 rc3.7
  净化的引擎侧对偶面）；
- `encode_messages(..., return_multi_modal_data=True)` → `(prompt, {"images":[...]})`（:679-705）；
- serving_chat.py:1589-1612（`chat_encoding_spec=="dsv41"` 分支，chat_encoding.py:108-112
  `model_type=="deepseek_v41"` 自动选中）：`media["images"]` 非空 → `if not is_multimodal: raise
  ValueError`（:1601-1602 文本态护栏）→ `image_data.extend(ImageData(url=...))`（:1603-1606）
  → 占位符替换为 image_token_id 129264 实 token（:1607-1611）；
- 响应计费面：`usage.prompt_tokens_details.image_tokens` 全链在树（usage_processor.py:22-113）。

⇒ SURVEY 待核① 的案头答案是**分支完整、无缺口**；残余=动态首冒烟（S3 门 G-V1 承载，
knapcio 同链路 `image_tokens==1024` 断言式）。**0-2 文件判定落定：V4.1 线=0 文件预期**
（若首冒烟红，fallback≤2 件 overlay 候选面=processors/deepseek_v41.py 与
deepseek_v41_image_processing.py，呈裁后定——非预判非预制）。

### 1.3 SURVEY 待核四项消化表

| 待核项 | 本窗处置 | 状态 |
|---|---|---|
| ①「死路」原文考 | SURVEY B.1 已考：逐字原文不存在的物件链定谳（graft 全绿但基座迁移致过时，非技术判负）+0.3.x v4vl 线实证推翻 | **闭**（承 SURVEY） |
| ②dev-dsv41 revision 异同（f80c91a4b vs 79cafec0 VL 面 diff） | **零流量纪律下不可达**（上游 dsv4.1 分支无本地克隆；网络抓取=流量禁项）。界限收窄法：本会话核 knapcio adapter 对基镜像内 API 面的引用（prefill_sp.py:732-743 引 `config.model_type=="deepseek_v41" and vision_n_layers>0`、:986-991 调 `_M["v2"].vision_topk`——**与我方 main 同名同构**）⇒ 两树 VL API 面同源弱证；doc92 管线同源（CUDA 13.0.3/NCCL 2.28.3/sglang-kernel 0.4.7）。残余漂移风险→S3 首冒烟动态闭；若红且疑上游修复缺失→呈裁开网络窗比对（不在本窗） | **收窄+动态闭**（风险 R1 登记） |
| ③encoding 图像分支首冒烟验设计 | §1.2 静态闭+§5 G-V1 动态门（knapcio 双形状图+官方图对+image_tokens 断言） | **静态闭/动态排程** |
| ④mm×k6×CG 三共面 | 静态面：target_verify 豁免+masked_fill 还原（§1.1）+chunk 感知编码（mm_schedule.py）+无调度器禁令（scheduler.py 全扫无 mm×spec 拒绝）⇒ 结构兼容；动态面：无先例→S4 阶梯臂（SPEC0→k6→+CG 逐级，每级轻量复跑） | **静态闭/动态阶梯** |

### 1.4 生产 mm 活体与 VL 服务的差异面（同靴分端口 vs 独立 VL 靴）

- **调度面硬约束**：r3-boot-arm.sh 前置守卫「四机无容器、GPU 空闲」（:103-115）+生产靴
  mem-fraction 0.90/池 9.6M 满驻 ⇒ **双靴并行物理不可能**（STDVL 前形 boot_mvl_uv.sh 同守卫）。
  ⇒ 任何 VL 测试靴=boot 槽独占（OUTAGE 制），「零扰动」的语义=**改面零侵入+槽内独占+拆线
  复原**，不是并行驻留。
- **裁定（推荐已获用户方向背书）**：**认证期独立 VL 靴**（r3boot-mvl 前缀+8898 测试槽，§3）；
  转正后**单靴同端口**——8899 生产靴本身就是 mm 活体，图像流量经网关到 8899（knapcio
  单端点同构，README-upstream.md:13「…and vision, behind one OpenAI-compatible endpoint」）。
  SGLang 无「同靴双端口」形态；「独立 VL 靴」不改变终态架构，只是认证隔离手段。
- 8899 图像开放时机门=**S4 阶梯全绿后**（mm×k6×CG 认证前，网关 VL 车道只指测试靴；R5 登记）。

---

## §二 面2 · V4.0exp VL 盘点（同基座承载面）

### 2.1 检查点盘点【实测】

| 面 | 值 | 锚 |
|---|---|---|
| 检查点本体 | `DeepSeek-V4-Flash-Vision-Exp`（=vLLM S1 镜像同源服务的模型；served name `deepseek-v4-flash-vision-exp`，VLLM045-ARCHAEOLOGY:30） | 本机 ls+考古档 |
| 01 分布源 | `~/models/DeepSeek-V4-Flash-Vision-Exp/` 48 分片全在位+config+generation_config+tokenizer.json（md5 8a8245dc7f6c6bfc 与 V4.1 逐字节同，**垫片缺口已闭**) | 本会话实测 |
| 02/03/04 | 02=/data/models/deepseek-ai/…（分发源沿留）+03/04=NFS dsvl-net（01 本机两目录现为空=回收后态，与 boot 脚本拓扑注记一致） | boot_mvl_600k_48m.sh 段1 注记 |
| config 形态 | **扁平**：model_type=deepseek_v4、arch=DeepseekV4ForCausalLM、43 层、vision_* 平铺 12 键 | config.json 实读 |

### 2.2 与 V4.1 检查点的 VL 差异表【实测 config 对读】

| 维度 | V4.0exp（Vision-Exp） | V4.1-Flash | 承载含义 |
|---|---|---|---|
| model_type/层级 | deepseek_v4 扁平 43 层 | deepseek_v41 嵌套（text 40+vision 32） | V4.0exp 不触发 auto-detect 门 |
| 视觉预算政策 | vision_max_n_token=**384**/min_pixels 147456/max_wh_ratio 8 | max_image_tokens=**1024**/min_pixels 295936 | 冒烟断言值分模型钉（V4.1=1024，V4.0exp 按其 processor 政策） |
| 视觉机制 | 可见窗注意力（compress_ratios 46 项）+bias_vl 路由+image-span 对齐 | 平铺双向 2D RoPE ViT+vl_correction_bias | V4.0exp 语义件 main 全缺 |
| image token | 129264 在词表（tokenizer 同源） | 129264 在词表 | 同 token 面 |
| 词表/骨干 | vocab 129280/dspark_block_size 5/markov 256 | 同 129280/同 5/256 | k 政策同源 |

### 2.3 main-79cafec0 对 V4.0exp 的注册支持（兼容定谳承袭+本会话复核）

deepseek_v41_vit.py/deepseek_v4.py 五处接线全部硬门 `model_type=="deepseek_v41"`
（:4860/:2653/:4290/:4458/:5099）对 deepseek_v4 不可达+可见窗/bias_vl/chunk 对齐 0 命中
（V4VL-COMPAT-SURVEY-20261004 §3 定谳，SURVEY B.2.1 承接）⇒ **V4.0exp 垫片=28 件 v4vl
overlay 整树复原**（registry 接管绕门不改门，G5 路线），非新做非逐件垫。复原源=
~/archive-20261012/overlay-superseded/sglang-overlay.v4vl-79cafec0/（34 件含 5 .bak+10-11
optc 探针改——**复原律=按 overlay-md5-manifest 28 件对表取件**，非整目录直用；集合指纹
f26c4888；CG-β 回滚坐标 backend 4d7c6d2c=认证态在此谱系内）。

### 2.4 k∈{3,6} 硬约束承载 + mm 复飞史（V4.0exp 臂的判据来源）

- k6=两模型 dspark_block_size 5→k6 同源（V4.0exp STDVL-K6CG 已认证先例+V4.1 生产 SPEC6
  在役）；k3=vLLM 世系 vision-MTP γ 语义（LUZ045 §78）——**k3 禁外推律沿袭**（VL-COMPUTEPATH
  §A.1），本窗不承载 k3。
- **mm 面史（必读）**：OPEN-26（10-06 vlimg 后 ~22G/机四机同步崩落=设备侧 mm 前向足迹
  事件性跳变，池余量假说证伪）→停飞→L0/L0RETRY 三件（件2 ViT 流式分块主修+件7 分配器
  卫生+件6 账本）根治实证（J5=OPEN-26 复现形全 200 不楔死，发后 ≤5s 满额归还；L0RETRY-
  VERDICT §一）→F7 P2 VL-A1 正式复飞窗 **10-08 让位未跑**→10-09 STDVL 文本定板（de_prose/
  de_code 63.16/113.21=**文本读数**非图面，bench/STDVL-K6CG-R1/de_prose_c1.json 实读确认）
  →10-13 overlay 归档。⇒ **本窗 V4.0exp 臂的图像面=正式复飞承载位**（图冒烟+足迹三账本
  观察沿 F7 J4-J6 判读线），判据链全部现成。

---

## §三 面3 · VL boot 形设计

### 3.1 前形对照（STDVL 前形 vs 原生路径）

| 面 | STDVL 前形（boot_mvl_600k_48m.sh/boot_mvl_uv.sh） | 本窗原生形（V4.1 臂） | V4.0exp 臂 |
|---|---|---|---|
| overlay | 28 件影子挂载（fail-closed 缺件拒启） | **零 overlay**（§1.2 定谳） | 28 件复原挂载（§2.3） |
| model | Vision-Exp 157G/池 4.8M/水位 20480 | V4.1-Flash 476G/**生产同形**（池 9.6M pin/ctx600k/mrr16/chunk4096/SPEC6 六参） | STDVL-R2-C24T 形逐字 |
| SPEC/GRAPHS | SPEC0（R1 后 k6+GRAPHS1 定板） | **阶梯：SPEC0+GRAPHS0 → k6 → +decode CG bs16**（§1.3④） | k6+CG（已认证形直入） |
| CTN/口 | r3boot-mvl/8898 | **同**（r3boot-mvl/8898） | 同 |
| 断言组 | 池指纹带+水位地板+DRY-RUN 段+反向用例自检 | 承袭骨架+**新增 mm 三直证断言**（§5 G-V3） | 承袭 STDVL 断言组+mm 直证 |

### 3.2 落位设计（新文件零改共享件；boot 段=S2/S3 执行窗动作）

- **驱动**：`dev/vl-native/boot_mvl41_native.sh`（新文件；基=boot_mvl_600k_48m.sh 骨架：
  DRY-RUN 强制段/守卫/A9 指纹核/失败路径免疫/水位断言全承袭；去 overlay 段=V4.1 臂硬断言
  `SGLANG_OVERLAY_DIR` **空**——与 STDVL 前形「overlay 必带」断言互斥，防臂混挂）。
  SERVER_ARGS=生产逐字（--model-path /models/DeepSeek-V4.1-Flash --served-model-name
  deepseek-v4.1-flash --tp 4 --ep 1 --nnodes 4 --mem-fraction-static 0.90
  --chunked-prefill-size 4096 --cuda-graph-max-bs-decode 16 --context-length 600000
  --max-running-requests 16 --max-total-tokens 9600000 --moe-runner-backend
  flashinfer_mxfp4 --fp8-gemm-backend flashinfer_cutlass --json-model-override-args
  '{"candidate_topk_blocks": 2048}'，锚=r3-boot-arm.sh:356-393）+SPEC/CG 阶梯由臂 env 映射；
  **vl 面零参数增量**（§1.1 最小参数集=∅ 的工程化表达=断言「SERVER_ARGS 与生产逐字 diff
  仅 SPEC/CG 阶梯位」）。
- **臂 env**：`arms/VL41N-SPEC0.env` 新建（键面=CTN_PREFIX=r3boot-mvl/API_PORT=8898/SPEC=0/
  GRAPHS=0/VERIFY=1；**零 DSV41_* 性能键**——VL 认证臂不带 51 键族，与 STDVL 前形 19 键制
  同法但更简：V4.1 原生臂不需要 VL overlay 指针与 RoCE 增强键）。回退链：摘臂 env=无靴
  （测试槽不留驻）；生产 51 键形不涉本臂任何键。
- **端口表（现役占用实测）**：8899=产线文本（r3prod）；8898=测试靴槽（分面律，OPS-MANUAL
  :7-8；STDVL 先例）→ **VL 认证靴=8898**；8897=零占用（**备用**：若主会话要求 VL 口与
  通用测试槽解耦则启用，本卡缺省不启用）；8001=网关文本车道；8002/8003=v1 时代退役口
  （零占用）→ VL 网关车道=8002（§4）；20000=dist-init；5000=registry。
- **systemd**：VL 靴**不建 unit**（沿 r3-boot 制：一次性驱动脚本+槽锁 boot-with-slotlock.sh
  包裹+OUTAGE 台账； boots are event-scheduled not daemons）。网关侧才涉 unit（§4.3）。

---

## §四 面4 · 网关接线设计（tools/packages/gateway/ + 在役 concurrency-proxy-v2）

### 4.1 现状（面账）【实测】

在役=01 机 concurrency-proxy-v2 rc3.8.2（:8001→UPSTREAM 8899，MAX_CONCURRENCY=16；01
/opt/aicad-prod/scripts/ 在役本尊，包内=e1a01162 同 md5 收编副本）。路由面=catch-all
`/{tail:.*}` 全透传（concurrency_proxy_v2.py:800），**无 content-type 分流、无后端表、无
路径重写**；POST 链=rc3.7 图像占位净化→rc3.6 注入（默认 off）→流式判定→转发。

### 4.2 图像请求兼容性判读（零改动可行性）

- rc3.7 `sanitize_image_placeholders`（:306-351）：快路径触发器=ASCII `b"deepseek_image"`
  （:315）——image_url 真载荷（base64 data URL/https URL）**不含**该串⇒不误触发；即便误
  报（提示词提及），walk 不命中占位符即零字节直返（:337-339）。⇒ **8001 车道今天就功能
  上可透传图像请求到 8899**（转正后零改动即用）。
- 边界登记（R3/R4）：`client_max_size=64MB`（:796）对多图 base64 大图=上限（V4.1 政策
  min_pixels 295936/max 1024 tok 自带钳制，T13 16000×9000 超尺寸先例=降采样受理，风险低）；
  `body_key` 去重只哈希前 1MB（:354-362）——同尺寸同前缀异图双发有伪 429 理论面（size 前缀
  参与键，实际碰撞窗极窄；登记不预防性改码，VL 车道可 DEDUP_ENABLE=0 规避）。

### 4.3 VL 接线最小改动方案（车道制；判读线冻结）

1. **形态**：第二实例 `concurrency-proxy-vl.service`（unit 文件=在役 unit 同模板改
   Description/EnvironmentFile 指针；同 rc3.8.2 本尊副本零代码改动）+ `gateway-vl.env`
   模板（`UPSTREAM=http://127.0.0.1:8898`（认证期）/转正后 `8899`、`PORT=8002`、
   MAX_CONCURRENCY=8（图像 prefill 重，车道减半）、`DEDUP_ENABLE=0`（R4 规避）、
   **GW_API_KEY=值位空红线沿袭**——值只落宿主 0600 secrets 位，禁入包/unit/镜像/日志，
   SMOK_KEY 前科律+gw 包 README 红线注记 1 逐字适用）。
2. **路由规则=车道制（客户端按端口分流），不做网关内 content 嗅探**：理由①proxy 本尊
   md5 漂移=在役升级纪律负担（README 红线注记 3）；②嗅探=对每 POST 全量 parse（rc3.4
   prefilter 收益面损失）；③简化令下最小改动面=零代码件。**后续可选升级位**（不在本窗）：
   proxy v2.1 加 `b'"image_url"'` 字节预检→VL upstream 的前置规则（呈裁件）。
3. **健康探针**：gw-verify 五探针制沿袭（P1 health/P2 429/P3 metrics/P4 journal/P5 上游
   失效）+VL 车道专属两断言：`curl :8002/gw/health` 版本行 + `curl :8002/gw/metrics`
   `requests_total≥1`（图像探针请求命中直证）。
4. **部署面**：unit/drop-in=宿主部署面分发件不入镜像（00-BAKED 律，gw 包 README 头注）；
   落位动作（daemon-reload/enable）=S6 执行窗动作；02 机两守护（pid 3535/3536）绝对不动。

---

## §五 面5 · 验证门设计（测试简化令承载；判读线冻结块）

> **禁项重申（用户裁定④逐字承载）**：不做全电池（T17 C 节/COMBO 面不复跑）、不做分型
> 单因子、不逐项测试。验证聚焦三面=算法验证（图像输入数值/语义正确性）+工程接线（端点/
> mm 解析/日志直证启用）+回归哨兵（51 键形零改动+关键指标不回归）。

### G-V1 VL 冒烟门（算法验证主门；V4.1 臂首靴=S3，阶梯每级=S4 轻量复跑）

- **冒烟集（3-5 张代表图，双源合成）**：①knapcio 双形状图（PIL 绘 3024×588 红圆+蓝方，
  断言语义=输出含 red/circle/blue/square+左右次序——boot.py:165-172 逐字式）；②T13 官方
  2 图对选 1（carrots 文本形态；md5 与模型仓官方件同，vl_battery_t17.py:70-78）；③自建
  OCR 图（s3_digits_742「图写了哪三个数字」）；④自建双图比较（d2「第二张比第一张多几根」
  ——跨图计数=更强语义判据）。判据=**逐项语义正确（人工/规则双判）+HTTP 200+零引擎异常**。
- **满额断言**：`usage.prompt_tokens_details.image_tokens == 1024`（V4.1 政策；knapcio
  同式断言）。V4.0exp 臂按其 384 政策另行核（不跨模型对表数值，只对各自政策满额）。
- **文本 canary**：smoke 3/3（北京 temp0，FL6-PROMO lib.sh:233-242 同式）同靴必绿——
  mm 靴文本面无回归的槽内自证。
- **位等对照（可选加做，若时窗富余）**：同图同题三发 content 逐字节等（T13 位等三对照式）
  ——非全电池，单点验证确定性。

### G-V2 算法对拍门（若历史留档可及）

- V4.1 臂 vs knapcio 冒烟语义（同双形状图同断言集——跨栈**语义面**对拍，禁数值对表）；
- V4.1 臂 vs V4.0exp 臂官方图对语义等价（同图同题，语义判非分值判）；vLLM S1 历史输出
  无留档在案（VLLM045-ARCHAEOLOGY 只有镜像/部署档）——**如实注记：无 vLLM 输出可拍，
  不追补跑**（简化令）。

### G-V3 工程接线直证门（每项精确 grep；`docker logs r3boot-mvl-{head,worker}` ×4 机）

| 直证项 | 精确模式 | 判 |
|---|---|---|
| mm 后端注册 | `grep -E "Multimodal attention backend not set. Use triton_attn.|Using triton_attn as multimodal attention backend."` | 两行在（生产同款 :236-237） |
| mm KV 预算 | `grep "Reserving 0.10 GB of the KV budget for post-sizing multimodal allocations"` | 行在（:277 同款） |
| processor 扫描 | `grep "multimodal.processors"` （扫描在跑即证 import_processors 执行；mimo_v2 import-error ignore=已知无害） | ≥1 行 |
| 图像 token 计数 | 响应体 `usage.prompt_tokens_details.image_tokens`（==1024）+`prompt_tokens` 较纯文本 canary 增量≈图 token 数 | 数值在带 |
| 视觉塔前向 | G-V1 语义正确性即前向直证（塔坏=语义必崩；无专用 INFO 日志，不造假门） | 语义绿即证 |
| 网关路由命中 | `curl :8002/gw/metrics`→`requests_total≥1`+journal `gwv2` 行；转正态另拍 `:8001` 透传图像 200 | 计数+200 |
| mm 能力面 | `curl :8898/model_info` 图像能力字段（is_image_understandable 广告位，model_config.py:700-708 注释） | 字段真 |

### G-V4 回归哨兵门（非全电池；S7 复原段一次过）

1. **8899 四查一次**（FL6-PROMO four_check 同式）：banner29:4+池 9,600,000+R1 fail-safe
   PASS rows=96 ×4+MISMATCH=0/chunk 4096+smoke 3/3——**VL 窗全程未触生产靴的直接复证**；
2. **DE c1 一点**（`sd_bench --mode de --type code --concurrency 1`，对 V4.1 锚带
   [76.9,80.0]（models.d/v41-prod.md §e）；带外=记录呈裁不停窗）——VL 靴占卡期测于
   拆线复原后；若窗口排程为产线在役期（VL 靴=同卡独占则必在 OUTAGE 后），四查+DE 于
   复原靴后执行；
3. **51 键形零改动直证**：printenv 四机 FP8=1/TG=1/R1INK=1/FL6FIX=1 ×4 复核+ENV51
   md5 2ac74586 对表+sitecustomize 55b1e412/fl6_recall b87cbb5e ×4 对表（指纹面零动）；
4. **水位门**：全窗 water-10s 带+WATER-RED=0+四机 min≥floor（VL 靴槽=floor 6000 沿产线
   线；mm 发观察沿 F7 J6：>4G 告警记录继续/**>8G 拒新 mm 即停窗**）+8898 拆线后收净 000。

### V4.0exp 臂附加门（G-V5，复飞承载）

官方 2 图对+自建 3 图（s1/s3/d2 精简版）全 200 语义对+**mm 足迹三账本观察**（件6 host+
件7 latched 设备足迹+水位 10s 带；判读线沿 L0RETRY J4-J6/F7 §四冻结线逐字）——=F7 P2
让位未跑的正式复飞读数位，非新设计。

---

## §六 面6 · 重烘焙面预估（最终交付前补充窗；BAKE 边界律承接）

- **VL 启用改动面归类**：V4.1 线=参数/ENV/boot 面（0 文件）→**不进镜像**（bind mount
  恒真律：adapter/overlay/ENV/boot 全宿主真源，RECIPE-0.3.1 §一/§三）；若 fallback 触发
  ≤2 件代码→overlay/adapter 面（**仍不进镜像**，集合指纹重算+FORM-REGISTRY 登记）；
  V4.0exp overlay 复原=宿主 overlay 面（同律不入镜像）。
- **会进镜像的唯一增量**=gateway 包改动（若 §4.3 VL 车道 unit+env 模板入包）：
  payload/units/concurrency-proxy-vl.service+env/gateway-vl.env.template 两新件→MANIFEST.md5
  变→LABEL kit_manifest_md5 重算（五包拼流算法钉定）。
- **重烘焙窗最小内容清单（供主会话排程）**：①gateway 包两新件+VERSION 刷新+MANIFEST
  重算；②文档集刷新（T3 四件之 FORM-REGISTRY-031 增 VL 形条目+本卡入 docs 集）；③
  IMAGE-IDENTITY 代际重算回填（sha256/体量/LABEL；RECIPE 新代或 0.3.1-rev1 呈裁定名）；
  ④G1 冷构建双跑内容身份+G6 指纹四件复跑；⑤交付位=**单基座容器不变**（ruling ③：网盘
  分发包只含 main-79cafec0 系这一个 SGLang 基座容器；vLLM VL 镜像族不再入交付位=
  凑合态清除的资产面表达，历史 tar 备份位不动）。
- **窗口依赖**：TOOLS31-BAKE-20261013 窗闭后（boot 槽互斥）；若 VL fallback 触发 overlay
  件则烘焙窗顺延至 fallback 定谳后。

---

## §七 执行序（S0-S7；boot 槽等待烘焙窗闭的衔接）

| 步 | 内容 | 前置 | 窗型 |
|---|---|---|---|
| S0 | 本卡呈核（主会话核准判读线冻结块） | — | 案头（已完成） |
| S1 | 排程衔接：**等 TOOLS31-BAKE 窗闭**（G2 boot 门链占用 boot 槽）+OUTAGE 制开窗登记+回退预案挂接（s_rollback 同法制） | S0 核准 | 案头 |
| S2 | 落位：`dev/vl-native/boot_mvl41_native.sh`+`arms/VL41N-SPEC0.env` 新建+`DRY_RUN=1` 自检绿（段 4b 推导表+反向用例；零 ssh/docker/curl） | S1 | 案头+本机 |
| S3 | V4.1 臂首靴（r3boot-mvl/8898/SPEC0/GRAPHS0，生产 SERVER_ARGS 逐字）→G-V3 mm 三直证→G-V1 冒烟门（双形状+官方对+OCR+双图+canary+image_tokens==1024） | S2 | **boot 槽（OUTAGE）** |
| S4 | 阶梯臂：k6（+SPEC6 六参）→+decode CG bs16，每级=G-V1 轻量复跑（官方 2 图对+canary+image_tokens）+池指纹/水位断言；任一级红=回上一级态呈裁 | S3 绿 | boot 槽（续） |
| S5 | V4.0exp 臂：overlay 28 件整树复原（MANIFEST 第 5 行律+28 件 md5 对表）→STDVL-R2 形靴→G-V5（图冒烟+足迹三账本=正式复飞读数） | S4 绿（或并行呈裁） | boot 槽（续） |
| S6 | 网关 VL 车道：第二实例 unit+env 0600 落位→gw-verify 五探针+VL 两断言→图像请求经 :8002 端到端→（S4 全绿后）转正呈裁：车道 UPSTREAM 切 8899 + 8899 图像开放 | S5 | 01 机部署窗（零集群扰动） |
| S7 | 复原+回归哨兵：拆 VL 靴（8898 收净 000）→生产复原靴（r3prod/ENV51/SPEC6）→G-V4 四查+DE c1+指纹三面对表+水位终面→落档（FORM-REGISTRY VL 形条目+models.d 两卡更新）→重烘焙窗呈裁（§六清单） | S6 | boot 槽（闭）+案头 |

---

## §八 风险登记

| # | 风险 | 量级 | 缓解/判读线 |
|---|---|---|---|
| R1 | dev-dsv41（f80c91a4b）与 79cafec0 的 VL 面漂移（上游分支或含 main 未合 VL 修复；零流量不可达） | 中 | §1.3② 收窄（knapcio adapter 引用面同构弱证+管线同源）；S3 首冒烟动态闭；红且疑上游缺失→呈裁开网络窗比对，fallback≤2 件 overlay |
| R2 | mm×k6×CG 三共面无先例（V4.1 线） | 中 | §1.3④ 静态兼容+ S4 阶梯逐级+每级轻量复跑；红=回退上一级态呈裁 |
| R3 | mm 足迹事件性跳变（OPEN-26 家族）跨线转移 | 中 | V4.1 塔实现异于 v4vl（原生 vs overlay）但 UMA 设备面前科同族：S3-S4 每级水位哨 10s 带+F7 J6 判读线（>8G 拒新 mm 即停窗）+qmg floor 6000+UMA 靴窗中止门 4G 沿袭 |
| R4 | 网关去重 1MB 前缀伪碰撞（图像大 body） | 低 | VL 车道 DEDUP_ENABLE=0；8001 主车道维持现行为（登记不预防性改码） |
| R5 | 8899 生产图像流量开放时机 | 中 | 硬门=S4 阶梯全绿+主会话呈裁；开放前网关 VL 车道只指 8898；生产端 mm 面（T61 谓词+mm KV 0.10G+O12 MM abort 守卫）在役即拦但**不依赖其兜底做认证** |
| R6 | V4.0exp 复原树含 5 .bak+optc 探针改 | 低 | 复原律=28 件 manifest 对表取件（§2.3），非整目录直用；集合指纹对表 f26c4888 子集校验 |
| R7 | 64MB body 帽对多图大 base64 | 低 | V4.1 min_pixels/max_image_tokens 政策钳制+T13 超尺寸先例（降采样受理）；超帽=网关 413 优雅（aiohttp 层），登记不扩帽 |
| R8 | VL 靴与生产靴槽互斥排程冲突（BAKE 窗/fl6 类转正窗插队） | 低 | S1 排程衔接+boot-with-slotlock 槽锁+OUTAGE 台账；VL 窗可让位（非紧急资产） |

---

## §九 51 键形兼容面声明（零改动承诺的精确边界）

1. **ENV51/51 键零触碰**：VL 全部改动=新文件（boot 驱动/臂 env/gateway unit/env 模板/
   本卡），不修改 ENV51（PROD-R51W5FL6-spec1.env，md5 2ac74586/51 键）、不增删其键；
   VL 臂 env 与生产臂 env 键面互斥（VL 臂零 DSV41_* 性能键）。
2. **生产 SERVER_ARGS 零增量**：图像启用=∅ 参数集（§1.1）——转正后 8899 面向图像时
   serve 参数面与今日逐字相同；mm KV 0.10G 预留+T61 谓词+O12 MM abort 守卫已在役，
   零新增防御件要求。
3. **指纹三面不动**：sitecustomize 55b1e412/fl6_recall b87cbb5e/overlay o12c1-prod 29 件
   （正典 736fbde5）——S7 G-V4.3 对表直证；adapter/overlay 真源律下镜像面亦零动（§六）。
4. **回退链不受影响**：两级回退（摘 51 键→休眠原版；摘接线→2c4baad3 原形）语义与本窗
   无交集；VL 靴拆线=8898 收净 000 即生产面复原完成的最小义务。
5. **o12c1-prod 4 空 VL 占位语义澄清**（SURVEY §C.4 承接）：占位防误挂 PR 时代文件名，
   上游原生件（deepseek_v41_vit.py/deepseek_v41.py 处理器）不在 overlay map 零触碰——
   本窗 V4.1 臂**不带任何 overlay**与该语义一致；V4.0exp 臂 overlay=独立目录复原件，
   与 o12c1-prod map 无交集。

---

## §十 引用清单（本卡新增一手锚；SURVEY §F 全量沿用不重录）

- 源码（~/sglang-main-src/python/sglang/srt/）：arg_groups/fields/mm.py:27-120；configs/
  model_config.py:531-552/:657-708/:2320-2371；managers/tokenizer_manager.py:560-582；
  multimodal/processors/deepseek_v41.py:1-135（全文）；managers/mm_schedule.py:433-446；
  managers/scheduler.py:199/:874/:1315-1320；entrypoints/openai/{encoding_dsv41.py:515-605/
  :679-705, chat_encoding.py:108-140, serving_chat.py:1505-1612, usage_processor.py:22-113}；
  models/deepseek_v41_vit.py:1-120；models/deepseek_v4.py:4859-4867/:4982-5008/:5082-5102/
  :5455-5464
- 生产/boot/臂：~/migrate-assets/bin/r3-boot-arm.sh:12/:38-45/:103-115/:356-433；logs/
  FL6-PROMO-20261013/{desk/lib.sh:15-25/:233-242, desk/s3_boot.sh, teardown/pre-stop/
  <prod-log>:230-237/:277-279}；dev/c24-compat48m/
  boot_mvl_600k_48m.sh（全文）；logs/RATIFY-CG-20260909/{desk/boot_mvl_uv.sh:48-118,
  READINGS.md:85-135, bench/STDVL-K6CG-R1/de_prose_c1.json}；arms/STDVL-K6CG-R2-C24T.env；
  tools/packages/cfgmgmt/payload/env/PROD-R51W5-spec1.env（50 键面）；models.d/{v41-prod.md,
  v4-vl-exp.md（§e/§f/§g/§h mm 停飞史）}
- 网关/烘焙：tools/packages/gateway/{README.md, payload/concurrency_proxy_v2.py:302-351/
  :354-362/:745-800/:794-802, payload/units/, payload/env/gateway.env.template}；
  tools/packages/_bake/RECIPE-0.3.1.md（§一-§五）；docs/runbooks/OPS-MANUAL-031.md:7-8/:115
- 模型/归档：~/models/DeepSeek-V4-Flash-Vision-Exp/{config.json vision_* 12 键,
  tokenizer.json md5 8a8245dc7f6c6bfc+129264}；/data/models/DeepSeek-V4.1-Flash/config.json
  （嵌套 text 40/vision 32/max_image_tokens 1024）；~/archive-20261012/MANIFEST.csv:5-6；
  docs/verdicts/L0RETRY-VERDICT-20261006.md §一；logs/T17-20261006/{battery_t17_b1vl.sh:94-98,
  vl_battery_t17.py:70-112}；docs/taskcards/F7-TRIMODEL-CARD-20261008.md §四（J4-J6 判读线）
- 历史：docs/research/VLLM045-ARCHAEOLOGY-20261008.md:26-31/:79（vLLM S1=Vision-Exp 模型
  +k3 起步史）

——VL-NATIVE 案头预备代理 / 2026-10-13（判读线冻结块=G-V1/G-V3/G-V4/水位门；呈主会话核准后 S1 起）
