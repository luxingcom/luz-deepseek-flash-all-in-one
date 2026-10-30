# SGVISION-SURVEY · SGLang 视觉能力三源调查（knapcio 启用法 / 我方 0.2.8 史 / 现役 main 可挂面）— 2026-10-13

> **性质**：案头调查代理件（零 boot/零集群/零流量/零 docker；三源全部只读）。唯一写动作=本件+commit。
> 战役仓=/home/liux***ya/luz030-opt-campaign。三源：A=~/knapcio-v41-audit-20260925/（只读）、
> B=我方 0.2.8/0.3.x 归档区（~/v40exp-branch-20260928/、~/<source-repo> git、
> ~/LuZ-0.3.0-ARCHIVE-20260930/、~/archive-20261001/、~/archive-20261012/、战役仓 git 史与
> logs/）、C=~/sglang-main-src/（main-79cafec0，git 单提交浅克隆、status 干净=纯上游树）。
> 标注律：【实测】=本会话直接读到（文件:行 / git 对象）；【转录】=权威档原文引用；〔推演〕=推导。
> 判定与点火权归主会话。

---

## §0 执行摘要（三大定谳）

1. **knapcio 的 SGLang 视觉=上游原生，不是他自己开的**。他的 VL 启用面全部来自基镜像
   `lmsysorg/sglang:dev-dsv41`（README:61 实锚：生产 canary-roce 镜像=**上游 SGLang `dsv4.1`
   分支 @f80c91a4b**）；他的 boot.py 服务器参数**零视觉旗**（boot.py:288-307 全量实读），
   却在冒烟里断言「full-budget native vision passed」+`image_tokens==1024`（boot.py:159-178）。
   他自己 overlay 的贡献=视觉塔 CuTe 性能核+文本路径 VL 适配件（见 §A）。
2. **我方现役基座 main-79cafec0 已原生含同一套 V4.1 VL 全链，且生产 51 键文本形此刻就以
   multimodal 态在跑**：模型侧 ViT/Aligner（deepseek_v41_vit.py）、处理器侧
   DeepseekV41ImageProcessor（processor-file-free、按类注册到 DeepseekV4ForCausalLM）、
   配置侧 auto-detect（model_config.py:657-669）、启动侧零旗——与 knapcio 同构。
   FL6-PROMO 生产 boot 日志直证 mm 机制在役（logs/FL6-PROMO-20261013/teardown/pre-stop/
   <prod-log>:236-237/:277）。**在役 V4.1-Flash 检查点本体携带
   266 个视觉权重键**（/data/models/DeepSeek-V4.1-Flash 权重索引实测）。「主线无视觉」=
   使用面事实（无图像请求/未认证），非代码面事实。
3. **我方 0.2.8 的 V4.0exp graft 没有死在技术上，死在谱系更替上**：0928 graft 全绿（静态
   五门）但「待测试窗」期间基座 0929/30 迁往 79cafec0，ep1u 形 graft 整体过时；tokenizer
   垫片硬缺口 8/31 后已实质闭合（tokenizer 文件补入检查点、与 V4.1 逐字节同）；10-05 以
   REGRAFT 重嫁接到 79cafec0（126/127 hunk 落位）→ VLW2W3 双面电池 11/11 绿 →
   STDVL-K6CG-R1/R2-C24T 定板（VL prose 63.16=126%/VL code 112.93=125%，
   031-FINAL-PERF-REPORT:69-70）→ **10-13 13:52 v4vl overlay 随归档第一批移入
   ~/archive-20261012/overlay-superseded/**（MANIFEST 第 5 行，可整树复原）。

> ⚠ **对任务书的两处如实勘正**（证据在 §B.2-§B.3/§C.1-§C.2）：①现役 VL 定板形 STDVL-K6CG-R1 的
> 126%/125% 读数产自 **SGLang 栈**（main-79cafec0+v4vl overlay 28 件影子挂载，
> logs/RATIFY-CG-20260909/desk/boot_mvl_uv.sh:48 实锚 IMAGE=<registry-host>:5000/lmsysorg/
> sglang:main-79cafec0），并非 vLLM 镜像读数；②vllm-openai:LuZ0.4.5-…-VL-S1-20260910b
> =vLLM VL 十三轮世系（09-10 建），09-11 晚切 dsv41 后停备回退（VLLM045-ARCHAEOLOGY
> §A.1 资产⑤转录），现为历史/备份栈。用户「通过加入一个 vllm 模型来实现视觉」的表述与
> 战役档案存在错位，按档案定谳如上，不臆造。

---

## §A 源A：knapcio 社区仓（~/knapcio-v41-audit-20260925/，2026-09-25 审计克隆）

### A.1 仓性质与模型

- 仓=`knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4`（origin remote 实锚），MiaAI-Lab
  b12x 谱系兄弟仓：**部署 overlay 仓，非 SGLang fork**。git log tip=58f2321（v2.3 results）。
- 服务模型=HF `deepseek-ai/DeepSeek-V4.1-Flash` @revision fb2764a5（start.sh:99 实锚），
  3x/4x DGX Spark，TP4/EP1（boot.py:291-294）。

### A.2 视觉启用方式（核心定谳）

| 面 | 证据 |
|---|---|
| **基镜像原生 VL** | Dockerfile:1-2 `FROM lmsysorg/sglang:dev-dsv41`；README.md:61 生产 canary-roce 镜像=「upstream SGLang `dsv4.1` branch at `f80c91a4b`」；README-upstream.md:13「…tool calling **and vision**, behind one OpenAI-compatible endpoint」 |
| **零视觉启动旗** | boot.py:288-307 服务器参数全量：model-path/served-name/tp/ep/attention-backend/moe-runner/mem-fraction/chunked-prefill/context-length/max-running-requests/cuda-graph/speculative/tool-call/reasoning parser 等，**无任何 --enable-multimodal / --enabled-mm-\* / vlm 旗**；mm 面唯 EXTRA_SGLANG_ARGS 逃逸口（boot.py:342-344，默认空） |
| **原生视觉冒烟断言** | boot.py:159-178：构造 3024×588 双形状图 → image_url(base64 data URL) → 断言输出含 red/circle/blue/square + `prompt_tokens_details.image_tokens==1024`（「full-budget」）→ `save('smoke-vision.json')` +「Structured output, tool round trip and full-budget native vision passed.」；start.sh:26 `smoke = arithmetic (+ optional tools/vision)` |
| **overlay 对引擎树的全部侵入** | Dockerfile:8 仅 1 件内核拷贝（flash_mla_sm120.py→sglang/kernels/ops/attention/）+ PYTHONPATH adapter（sitecustomize 挂钩），**视觉零 graft** |

### A.3 他家自己的视觉面贡献（性能/文本路径适配，非启用件）

1. **视觉塔 CuTe 核**：`runtime/b12x_next/b12x_next/norm/vision.py`（185 行，「CuTe support
   operations for the **replicated V4.1 vision tower**」：rope/merge/gelu 三算子，行列=launch
   标量）+ `norm/_vision_preparation.py`（静态几何编译契约）+ `preparation/catalog.py:71`
   （`op_qualname='norm.vision'` 注册）。加入于 commit 0102f5c（2026-09-24，EP_SIZE=1 大提交）。
2. **文本路径 VL 适配**（model_type 无关的正确性/性能件）：
   - `adapter/tp3_pad.py:81-90`：读 `hf.vision_config`，TP 整除性不足时 vision heads 上取整垫片；
   - `adapter/prefill_sp.py:732-743`：`config.model_type=="deepseek_v41" and vision_n_layers>0`
     时 image_token_id 位置 `torch.where` 还原（engram 路径）；
   - `adapter/prefill_sp.py:986-991`：路由器带 `e_score_correction_bias_vl` 时调
     `_M["v2"].vision_topk`（:494 实锚 `_M["v2"]=sglang.srt.models.deepseek_v2`——**即基镜像
     内 SGLang 原生 vision_topk**，他家只做调用侧适配）。
3. tests/test_prefill_sp_moe8_gpu.py:24-27/:374/:388：vision_topk 分片位等测试（对
   `v2.vision_topk` 的正确性测试，非自研实现）。

### A.4 定谳

**knapcio 在 SGLang 上跑的是 DeepSeek-V4.1-Flash 原生 VL（图像输入 1024 token 满额），
启用方式=用带上游 dsv4.1 分支 VL 的基镜像+零启动旗；他家自研件是视觉塔性能核与文本路径
适配，不构成「启用」本身。** 他**没有**在 SGLang 上跑 V4.0exp/Vision-Exp（仓内零
Vision-Exp 痕迹；VL 镜像 vLLM 线他家也无）。dev-dsv41 与我方 main-79cafec0 的 revision
异同未核（零 docker 纪律），但 doc92 实锚两镜像「同管线」（CUDA 13.0.3/NCCL 2.28.3/
sglang-kernel 0.4.7 同源），且我方基座的 VL 全链已直接在树验证（§C）——该未核项不承载结论。

---

## §B 源B：我方历史两段（0.2.8 V4.0exp graft 时代 + 0.3.x v4vl/STDVL 时代）

### B.1 0.2.8 时代（2026-09-28）物件链【实测 git 对象】

- 权威工作区 `~/v40exp-branch-20260928/`：`pr37253.diff`（36 文件）、`pr-hunks/`、`graft/`、
  `graft-report.txt`（24 共享文件 hunk 计数）、`pr-branch/`（yhyang201/sglang @d5a3b77 sparse
  克隆，git log tip=`d5a3b77 Clean up DeepSeek V4 vision metadata`）、`worktree/`。
- fork 仓 `~/<source-repo>` 分支 `v40exp-20260928`：
  - `ab669c1 feat(v40exp): V4.0exp(Vision-Exp) 文本骨干分支——计算路径调查+静态验证+首启保守臂`；
  - `36ae8da feat(v40exp): PR #37253 视觉件 hunk-graft 到 ep1u——V4.0exp Vision 臂就绪（待测试窗）`，
    含 **`sglang-overlay.v40exp-vision/`（28 平铺文件，97,277 行插入）** + 移植方案
    `docs/V40EXP-VISION-PORT-PLAN-20260928.md` + static_verify.py + visible_window 单测。
- **PR#37253 定性**（方案 doc §0 原文转录）：「PR #37253（d5a3b77，yhyang201，dev/dsv4-vision）
  是社区唯一的 V4.0exp 完整实现，**上游 main 从未合入**。已将其全部 28 个源文件 hunk-graft
  到 ep1u 基座之上，16 文件自动干净套用+11 文件手工消解 reject+1 文件自动全过。静态验证全绿
  （VL wrapper/ViT/processor/visible_window 全链 import、registry 接管
  `DeepseekV4ForCausalLM→deepseek_v4_vl`、visible_window 单测 9/9、mm 门）。」
- **graft 面**（36ae8da 文件账【实测】）：4 新文件照搬（visible_window/deepseek_v4_vit/
  deepseek_v4_vl/mm_processor_deepseek_v4_vl）+24 共享文件 hunk；机制三线=可见窗注意力
  （swa_win_starts/lens）、bias_vl 路由（hash 层 tid2eid+非 hash 层 per-row 双偏置）、
  调度 chunk 边界 image-span 对齐。
- **tokenizer 垫片=当时唯一硬缺口**（方案 doc §3.1 原文）：V4.0exp 权重目录无 tokenizer 文件；
  设计 shim 目录（新目录：48 个 safetensors 符号链接+config/generation 拷贝+tokenizer.json/
  tokenizer_config.json 拷自 V4.1-Flash；`<｜deepseek_image｜>`=129264 已核实词表在位）。
- **垫片缺口现状=已实质闭合**【转录 V4VL-COMPAT-SURVEY-20261004 §1.4+本会话复跑】：
  检查点 `~/models/DeepSeek-V4-Flash-Vision-Exp/` 的 tokenizer.json/tokenizer_config.json
  与 V4.1 **逐字节相同**（md5 8a8245dc…，文件 8/31 14:45 后补入），shim 目录不再必需。
- **「SGLang 视觉死路」判定原文考**：全档 grep（LuZ-0.3.0-ARCHIVE doc00-100 + 战役仓 git
  --grep 死路/baked7f1）**未命中逐字原文**——标待核。物件链支撑的事实定谳：0928 graft 全绿
  但停在「待测试窗」；0929/30 U0 基座迁移 79cafec0（doc92：nightly-dev-20260929-79cafec0
  四机钉板）使 ep1u 形 graft 整体过时（backend 5293→4126 行重构面全 DIFF，6e38414 转录）；
  同期 VL 生产=baked7f1（vLLM VL final 镜像 357e2f8e36ae，74C-IMAGE-INVENTORY:22 实锚
  「baked7f1=VL final」）。「死路」判定应理解为**该 graft 形态对 0.2.8 交付线不再值得开窗**，
  非 SGLang VL 本身不可行——后者被 0.3.x v4vl 线实证推翻（B.2）。

### B.2 0.3.x 时代：v4vl 重嫁接→STDVL 定板→10-13 归档【实测+转录】

1. **V4VL-COMPAT-SURVEY-20261004**（战役 commit 6e38414）：检查点四机全在位零布机；
   引擎 79cafec0 文本面原生一等；视觉面五处 `model_type=="deepseek_v41"` 硬门对
   `model_type=deepseek_v4` 的 Vision-Exp 全部不可达+缺可见窗/bias_vl/单 chunk 对齐
   （V4VL 语义必需件 0 命中）→ 走「wrapper 接管绕开五门、不改门」路线（G5）。
2. **REGRAFT-REPORT-20261005**（opt1-dev/model_compat_20261004/v4vl_regraft/）：28 平铺件
   重嫁接到 79cafec0：4/4 新文件直携逐字节同+24/24 共享件 127 hunk→**126 落位**
   （113 干净+10 fuzz 错位审计重落+3 reject 手工消解+1 OPEN-1）；静态五门全绿
   （py_compile 28/28、D2 差分 0 真新增、registry 接管、visible_window 9/9、对账表 28 行）。
   最高风险件 deepseek_v4_backend.py（5293→4126 重构）13 hunk 全落位。
3. **实跑实证**：VLW2R 靴四机横幅（crash1-logs 2026-10-05）；OPEN-7/8/9 三修复闭
   （overlay-md5-manifest 注记：cp_v2 改名闭合/sm120 win-override/serving_chat dsv4 分支）；
   **VLW3 楔死事故**（OPEN-12）定谳=内存压力中介（8.85M 池多占+mm 足迹 ~46G 不归还→
   UMA 楔死），修复=池重裁 4.8M+memguard 产品化，非代码缺陷（94fc6b8/9840460 转录）；
   **VLW2W3 双面电池 11/11 图请求全 200**（官方双图对+自建三档 9 图含 3.18k tok 多图长文）+
   文本面 GSM8K 0.93+位等三对照双绿（commit fa36a61）。
4. **STDVL 定板**：STDVL-K6CG-R1（RATIFY-CG-20261009：k6+GRAPHS=1+池 pin 4,800,000+stock
   图梯；prose 63.16 同值/code +0.25% 带内）→ R2-C24T（C24 三钉纠回+ctx600000/mrr12/
   chunk4096+水位 20480，W-OPTA-CLOSELINE S8 认证+NFS 形复核双绿，TOOL-ANCHORS:43-44）。
   **0.3.1 四线达成 135/118/126/125%**（031-FINAL-PERF-REPORT:69-70/:196）——VL 两线即
   126%/125%，SGLang 栈。
5. **10-13 归档**：ARCHIVE-EXEC1（2026-10-13 13:52-13:54Z）把 `~/migrate-assets/v4vl/
   sglang-overlay.v4vl-79cafec0/`（34 件含 5 .bak+optc 探针改，集合指纹 f26c4888）整体 mv 到
   `~/archive-20261012/overlay-superseded/`（MANIFEST.csv 第 5 行：「VL 时代旧 overlay 谱系」；
   **复原律=若拟重开须按本行整树复原**）。CG-β 终止窗回滚坐标（backend 97b1174f→4d7c6d2c）
   在该谱系内（INDEX §特别标记 1）。现役 overlay 只余 cgbeta-a/o12c1-prod/optc-o12sched
   （backend 736fbde5，文本线）。
6. **谱系判定**：归档动机=T5 归档批次（引用扫描 fail-closed 判「superseded」）+CG-β 终止，
   **非 VL 线技术判负**——STDVL 形判据链/J0 电池/boot 链（dev/c24-compat48m/
   boot_mvl_600k_48m.sh）全部在档可复跑。

### B.3 vLLM VL 世系（现「凑合」位的实体）

- 镜像 `LuZ0.4.5-DeepSeek-v4-Flash-DGXspark-TP4-Ring-VL-S1-20260910b`（0098a90d4e52，
  09-10 建；baked7f1=357e2f8e36ae VL final 前代）：vllm 0.26.1.dev0+gd3d3b2cca+
  `vllm/models/deepseek_v4/nvidia/vl_model.py`（DeepseekV4ForConditionalGeneration）
  【转录 VLLM045-ARCHAEOLOGY §A.1 资产①②，A 级 docker 直读】。
- 09-11 晚切 dsv41（SGLang）后停备回退，NAS 有 tar 备份（同档资产⑤）。
- 十三轮定稿（VL 镜像四机+三审计+k∈{3,6} 硬约束）即此世系的由来；k3 起步=dspark
  vision-MTP 语义（γ 约束），k6=SGLang 线 STDVL 形（0731 同构）。

---

## §C 源C：现役 main-79cafec0 可挂面盘点（~/sglang-main-src/，纯上游树）

### C.1 V4.1 VL 全链在树清单【实测，文件:行】

| 层 | 件 | 锚 |
|---|---|---|
| 视觉塔 | `python/sglang/srt/models/deepseek_v41_vit.py`（「DeepSeek-V4.1 vision tower and aligner」，PatchEmbed/2D RoPE/Attention(VisionAttention, use_data_parallel=True)） | :1-2/:60-72；由 deepseek_v4.py:178 import |
| 模型接线 | `models/deepseek_v4.py`：vision+aligner+image_start/end/newline 实例化（约束「TP/EP/DP、无 CP/PP/MoE A2A」——我方 TP4+a2a none 满足）；vl_correction_bias；EngramHasher image_token_id；image-token hidden 还原；MM_PAD_SHIFT_VALUE 重映射 | :4860-4874/:2653-2654/:4290-4293/:4458-4466/:5099-5102 |
| 前向 mm 门 | `self.vision is not None ∧ ¬decode ∧ ¬target_verify ∧ mm_inputs 非 None` → `_prepare_mm_embeddings`（文本批永不进视觉路径） | :5082-5091 |
| get_image_feature | aligner(vision(patches,h,w)) → image_start/features/newline/image_end span 拼装（shared MM cache/chunk scheduler 面） | :4990-5008 |
| 权重装载 | 文本形（vision is None）自动 skip `vision./aligner./image_*` 与 `.gate.e_score_correction_bias_vl`（skip_group） | :5455-5464 |
| 路由 | `models/deepseek_v2.py`：`from sglang.srt.multimodal.dsv41.vl_routing import vision_topk`；`e_score_correction_bias_vl` 参数+两处路由调用 | :191/:502-507/:1028-1029/:1280-1281 |
| 处理器 | `multimodal/processors/deepseek_v41.py`：`DeepseekV41ImageProcessor`，**models=[DeepseekV4ForCausalLM] 按类注册**；processor-file-free（读 hf_config+tokenizer）；patchify 三后端 pil/rust/gpu（rust=rust_extensions._multimodal 的 dsv41.resize_patchify，失败回退 PIL） | :15-16/:22-33/:40-66 |
| 图像处理 | `multimodal/deepseek_v41_image_processing.py`（image_token_types/patchify_image{,_rust}/prepare_image_gpu/GPU_PLAN_KEY） | 目录实列 |
| 配置归一 | `configs/deepseek_v41.py`：`normalize_deepseek_v41_config` 弹出 text_config 合并+vision_config 十键折平（num_hidden_layers→vision_n_layers 等）+**architectures `DeepseekV41ForCausalLM`→`DeepseekV4ForCausalLM` 改牌**+model_type 钉 deepseek_v41 | :5-17/:23-40 |
| mm 开关 | `configs/model_config.py`：`has_dsv41_vision = model_type=="deepseek_v41" and vision_n_layers>0` → is_multimodal/is_image_understandable；`enable_multimodal` 缺省 **True**（仅四个问题架构例外，DeepSeek 不在列）→ **零启动旗自动开** | :657-669/:531-552 |
| 启动接线 | `managers/tokenizer_manager.py`：is_multimodal → `import_processors("sglang.srt.multimodal.processors")`（pkgutil 自动扫注册）→ `get_mm_processor`（PROCESSOR_MAPPING 按类名对 architectures） | :562-572；multimodal_processor.py:17-43/:45-74 |
| registry | `models/registry.py` 新制=自动 import sglang.srt.models 包扫 EntryClass（deepseek_v4.py:5773 EntryClass=[DeepseekV4ForCausalLM]）——**09 月「registry 零 v41 VL 注册」记忆锚按 main 现状证伪**：注册面按类非按 VL 名，VL 处理器另线自动注册 | registry.py:22-26 |

### C.2 在役生产 51 键形（0731 线 FL6-PROMO，2026-10-13 13:25 boot）mm 活性直证【实测日志】

logs/FL6-PROMO-20261013/teardown/pre-stop/<prod-log>：
- :94 server_args 全量：`model_path=/models/DeepSeek-V4.1-Flash`、`enable_multimodal: None`
  （=缺省 True 路径）、DSPARK k=6（speculative_num_draft_tokens=6）、decode CG full bs16、
  chunked_prefill 4096、池 9,600,000；
- :230 processor 包扫描在跑（mimo_v2 import error 被 ignore=非致死）；
- :236-237 `Multimodal attention backend not set. Use triton_attn.`；
- :277 `Reserving 0.10 GB of the KV budget for post-sizing multimodal allocations`。
⇒ **生产文本线此刻即以 multimodal 态运行**（处理器注册+mm 注意力后端+mm KV 预算三直证）。
V4VL-COMPAT-SURVEY §3.2 的「生产应已 is_multimodal=True 起服」推演 hereby 落实证。

### C.3 在役检查点 VL 资产【实测 /data/models/DeepSeek-V4.1-Flash】

- config.json：architectures=`["DeepseekV41ForCausalLM"]`、model_type=deepseek_v41、嵌套
  text_config（model_type=deepseek_v41_text）+**vision_config（num_hidden_layers=32**、
  hidden 1024、patch 14、downsample 3、max_image_tokens 1024、min_pixels 295936）、
  image_token_id=129264；
- 权重索引：**266 个视觉键**（vision.patch_embed/vision.blocks.0-31/vision.norm/aligner.
  w1/w2）+`layers.{6,14,22}.ffn.gate.bias_vl` 等路由偏置键；
- tokenizer.json added_tokens：**129264=`<｜deepseek_image｜>`** 在位（128799=`<｜System｜>`）；
- 目录含 inference/{vision.py,image_processor.py,model.py}（厂商参考实现）与 encoding/。
- 缺件：无 preprocessor_config.json/processor_config.json——**v41 处理器 processor-file-free
  设计下非必需**（§C.1 处理器行；V4VL-COMPAT-SURVEY §3.1 同判）。
- 对照：~/models/deepseek-v4-flash-0731/config.json=model_type deepseek_v4、零 vision 键
  （纯文本，两模型中的另一个）。

### C.4 overlay/adapter 面兼容盘点【实测】

- 生产 overlay o12c1-prod（~/migrate-assets/v4vl/sglang-overlay.o12c1-prod/，29 件）：
  model_config.py 与上游逐字节同（本会话 md5 cmp）；**4 个空 VL 占位**
  （deepseek_v4_vit/deepseek_v4_vl/dsv4_visible_window/mm_processor_deepseek_v4_vl，即
  PR#37253 时代文件名——上游原生件 deepseek_v41_vit.py/deepseek_v41.py 处理器**不在
  overlay map、不被触碰**）＝占位防误挂语义，非禁用上游 VL。
- adapter 面：prefill_sp（W5 件 32cf9abf）T61 谓词=mm 批不走 split 路径回退 stock
  （V4VL-COMPAT-SURVEY §3.4：引擎真身=deepseek_v4.py:5082-5091 forward 门，adapter 镜像
  谓词 `_dc_mm_inputs_present` 在 prefill_sp）——为 mm 批设计的回退件已在产。
- scheduler 面：o12c1-prod scheduler.py:198-199 import mm_utils/multimodal_processor
  （=上游面随基座携带，O12 三键+PD-decode MM abort 守卫共存）。

### C.5 可挂面缺口（如实）〔待核清单〕

1. **chat 编码路径的图像语义**（encoding_dsv41.py/serving_chat 对 image_url content 的
   v41 分支行为）：knapcio 同链路已证可行，但其基座=dsv4.1 分支 @f80c91a4b，与我方
   main-79cafec0 存在漂移面——首次冒烟即验，案头不可闭。
2. **mm×k6×CG 三共面**：VL-K6 §五曾设 k6×mm 禁混靴；STDVL-K6CG-R1 后在 V4.0exp VL 线
   证 k6+CG+mm 可共（RATIFY-CG-20261009）——但那是 v4vl overlay 线；**V4.1 原生 VL 线的
   mm×k6×CG 无先例**，需专窗认证（或首臂 SPEC=0 走 STDVL 同法阶梯）。
3. mm 足迹不归还前科（VLW3 ~46G）：V4.1 线池 9.6M/水位门与 mm 并载的预算重推导
   （O13B 卡 §四同法，VL bytes/tok 低 10.7% 的账可参照）。
4. single-chunk prefill 约束（厂商语义）：v41 处理器/scheduler 的 chunk 对齐面在树
   （is_multimodal_chunked_prefill_supported，model_config.py:708 起）——具体政策首靴核。

---

## §D 三源对照总表

| 维度 | knapcio（源A） | 我方 v4vl/STDVL 线（源B） | 我方 V4.1 原生面（源C） |
|---|---|---|---|
| 服务模型 | DeepSeek-V4.1-Flash（HF 快照，含视觉权重） | DeepSeek-V4-Flash-Vision-Exp（V4.0exp，157G，四机在位） | /data/models/DeepSeek-V4.1-Flash（生产在役，含 266 视觉键） |
| model_type | deepseek_v41 | **deepseek_v4**（扁平 config） | deepseek_v41（嵌套，normalize 折平） |
| 引擎支持来源 | 上游 dsv4.1 分支基镜像原生 | **PR#37253 graft（上游未合）** 28 件 overlay | **上游 main-79cafec0 原生在树** |
| 启用动作 | 零旗（auto-detect） | overlay 影子挂载 28 件+boot_mvl 链 | 理论零旗（auto-detect 已在生产日志活体直证） |
| 性能自研件 | 视觉塔 CuTe 核+文本路径适配 | O13 分幅/admission 等沿 VL 线移植 | 生产 51 键全套（R1/W5/O12/LL128/FL6）已活 |
| 认证状态 | boot 冒烟（1024 token 满额断言） | **J0 双面电池全绿+四线 126/125% 定板** | 未认证（mm 机制活但无图像请求史） |
| 现状 | 在跑（v2.3，2026-09-29 验证） | overlay 10-13 归档（可整树复原） | 在役文本线=潜在一日启用面 |

---

## §E 方案卡（呈裁）

### 路径 B（推荐首位）：knapcio 式原生启用——在现役 V4.1-Flash 主线上开图像服务

- **内容**：零引擎改动（或 ≤2 件 overlay 补 chat 编码缺口，呈裁后定），生产臂 env 零新键
  预期（knapcio 零旗实证）；在 8898 旁路臂（r3boot 前缀+独立 CTN/端口纪律同 M0731 先例）
  对 /data/models/DeepSeek-V4.1-Flash 发图像请求。
- **工作量**：案头 0.5 窗（encoding_dsv41/serving_chat 图像分支走查+§C.5 清单核）+
  冒烟窗 1（knapcio 式双形状图冒烟+image_tokens 计数断言+文本回归 canary）+认证窗 1
  （VL 专测电池+J0 式判据）≈ **2-2.5 窗**。文件面 0-2 件。
- **技术风险**：①chat 编码缺口（首冒烟即知，fallback=overlay 补 1-2 件）；②mm×k6×CG
  无先例（阶梯：首臂 SPEC=0+GRAPHS 照 STDVL 首启律，再 k6，再 CG——每步 J0 复跑）；
  ③mm 足迹水位（O13B §四账法重推，水位 floor 首靴重钉同律）；④楔死前科=环境态非代码
  （memguard 已产品化在 QA 线）。
- **验证门**：冒烟门=形状描述语义对+image_tokens 满额（1024 政策）+纯文本 canary 带内；
  认证门=VL 双面电池（T13 形：官方图对+多图长文+4xx 优雅）+GSM8K/DE 文本零回归三查+
  位等对照（图/文各一路）；**k∈{3,6} 承载**=k6 为 V4.1 在役 spec 形（dspark_block_size=5
  →k6），mm 共载认证窗明示；k3=vLLM 世系形禁外推（VL-COMPUTEPATH §A.1 律）。
- **51 键形兼容**：预期零键新增、零 overlay 改动；mm KV 0.10G 预算已在役（日志:277）；
  T61 谓词/O12 MM abort 守卫在产=adapter 面已有 mm 容忍设计。**与「凑合」现状的本质差**：
  视觉进 SGLang 主线旗舰模型，双栈（vLLM VL 备份）可退役或降为对照。

### 路径 A（次位）：复活 v4vl graft 面（Vision-Exp 模型线复原）

- **内容**：按 MANIFEST 第 5 行整树复原 ~/archive-20261012/overlay-superseded/
  sglang-overlay.v4vl-79cafec0/ → ~/migrate-assets/v4vl/（集合指纹 f26c4888 对表）+
  boot 链（dev/c24-compat48m/boot_mvl_600k_48m.sh）+env（arms/STDVL-K6CG-R2-C24T.env
  77af51e8）+模型 ~/models/DeepSeek-V4-Flash-Vision-Exp（四机在位）。
- **工作量**：复原+对表 0.5 窗+首靴 1 窗+电池复认证 1 窗 ≈ **2.5-3 窗**（判据链全部在档
  可复用，无新案头）。
- **技术风险**：①overlay 维护税=每次基座升级重放 graft（126 hunk 面）；②VL 线 scheduler
  为 v4vl 谱系（无 O12 调度三键件）→ 与文本线优化栈分叉维持；③CG-β 回滚坐标在谱系内
  （backend 4d7c6d2c 态=R1/R2 认证态，复原即正确态，但须防 W-optD「重开要件」误叠）；
  ④mm 足迹/池重裁已定（4.8M+水位 20480），J0 先例直接承袭。
- **验证门**：STDVL-R2-C24T J0 判据逐字复跑（池 4.8M±2%+三钉横幅+DE 带+GSM8K≥0.92+
  err=0+水位 20480）；k∈{3,6}：k6 形（已认证先例）。
- **51 键形兼容**：独立 19 键 env/8898 端口/独立 CTN 前缀——与 50/51 键文本形并存在案
  （F7'/L2PF 联合窗先例），零互扰。
- **定位**：若产品要求=继续服务 Vision-Exp（V4.0exp）检查点，此路径是唯一已认证答案；
  若要求=旗舰 V4.1-Flash 带视觉，则被路径 B 全面优于（零 graft、零维护税、主线合一）。

### 路径 C（基线对照位）：维持双栈现状

- **内容**：VL 继续走现役定板形（STDVL-R2-C24T，SGLang；或按需复原路径 A）+vLLM
  LuZ0.4.5-VL-S1-20260910b 备份栈不动。
- **工作量**：0 窗。风险=「凑合」现状延续（用户原话）：双栈运维面+镜像维护+vLLM 线
  性能天花板（0.4.5 fork 停更）。
- **价值**：作为 B/A 认证窗的对照读数位（跨栈禁混比律下只作记录性对照，sparkDash 同口径
  带外推禁令照旧）。

### 呈裁推荐序

**B → A → C**。B 以最低工作量（2-2.5 窗、0-2 文件）把视觉带进 SGLang 主线旗舰模型，
直接回应「SGLang 上的视觉需要启用」的用户目标，且有 knapcio 同链路生产实证+我方生产
日志 mm 活体直证双背书；A 作为 Vision-Exp 线复原备选（已认证判据链，重开成本低但
维护税永续）；C 降为对照位。若主会话裁决 B 开窗：首臂=SPEC0+零新键+8898 旁路+knapcio
式冒烟，J0 判据沿 STDVL 先例重锚。

---

## §F 引用清单（本件全部一手锚）

- 源A：~/knapcio-v41-audit-20260925/{Dockerfile:1-8, README.md:12/:15/:61, boot.py:99/:159-178/:288-307/:342-344, start.sh:26/:99/:102, adapter/tp3_pad.py:81-90, adapter/prefill_sp.py:494/:732-743/:986-991, runtime/b12x_next/b12x_next/norm/{vision.py:1-5,_vision_preparation.py:1-4}, preparation/catalog.py:71, tests/test_prefill_sp_moe8_gpu.py:24-27, git:0102f5c(2026-09-24)}
- 源B：~/<source-repo> git:{ab669c1,36ae8da+stat,docs/V40EXP-VISION-PORT-PLAN-20260928.md §0/§3.1/§4/§5}；~/v40exp-branch-20260928/{pr37253.diff,graft-report.txt,pr-branch@d5a3b77}；~/LuZ-0.3.0-ARCHIVE-20260930/{92-…:8/:45,74C-…:22}；~/archive-20261012/{INDEX.md,MANIFEST.csv:5-6}；~/archive-20261012/overlay-superseded/sglang-overlay.v4vl-79cafec0/（34 件实列）；战役仓 git:{6e38414,fa36a61,94fc6b8,9840460}；opt1-dev/model_compat_20261004/{V4VL-COMPAT-SURVEY-20261004.md §1.3/:1.4/§3.1-3.4/§4,v4vl_regraft/REGRAFT-REPORT-20261005.md §0-§2}；docs/{taskcards/MODEL-COMPAT-TASKBOOK-20261005.md,taskcards/O13B-VL-PORT-CARD-20261006.md,research/VL-PERFOPT-CARRYOVER-20261008.md §A,research/VLLM045-ARCHAEOLOGY-20261008.md:26/:38/:49,research/031-FINAL-PERF-REPORT-20261009.md:69-70/:196,TOOL-ANCHORS.md:43-44,inventories/FORM-REGISTRY-031.md}；logs/RATIFY-CG-20261009/desk/boot_mvl_uv.sh:48/:102-143
- 源C：~/sglang-main-src/python/sglang/srt/{models/deepseek_v41_vit.py:1-2/:60-72, models/deepseek_v4.py:178/:2653-2654/:4290-4293/:4458-4466/:4860-4874/:4990-5008/:5082-5102/:5455-5464/:5773, models/deepseek_v2.py:191/:502-507/:1028-1029/:1280-1281, configs/deepseek_v41.py:5-58, configs/model_config.py:531-552/:657-708, multimodal/processors/deepseek_v41.py:15-66, multimodal/deepseek_v41_image_processing.py, multimodal/dsv41/vl_routing.py, managers/tokenizer_manager.py:562-572, managers/multimodal_processor.py:17-74, models/registry.py:22-26}
- 生产直证：logs/FL6-PROMO-20261013/teardown/pre-stop/<prod-log>:94/:230/:236-237/:277；/data/models/DeepSeek-V4.1-Flash/{config.json,权重索引 266 视觉键+bias_vl,tokenizer.json added_tokens 129264}；~/models/{deepseek-v4-flash-0731,DeepSeek-V4-Flash-Vision-Exp}/config.json；~/migrate-assets/v4vl/sglang-overlay.o12c1-prod/{overlay-map.tsv 29 行,4 空占位,model_config.py md5=上游同}
- 待核清单：「SGLang 视觉死路」判定逐字原文未定位（B.1）；dev-dsv41 与 79cafec0 的 revision 异同（零 docker 纪律）；encoding_dsv41 图像分支行为（首冒烟验）；V4.1 线 mm×k6×CG 三共面（专窗）。

——SGVISION 调查代理 / 2026-10-13
