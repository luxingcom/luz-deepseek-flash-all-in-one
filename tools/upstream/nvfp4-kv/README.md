# tools/upstream/nvfp4-kv/ — nvfp4 KV cache 复用 fp8 标定 k/v_scale 的 host 侧规避三件套

> 法源：sgl-project/sglang [issue #42369](https://github.com/sgl-project/sglang/issues/42369)
> （`--kv-cache-dtype nvfp4` 时引擎静默加载 checkpoint 里 fp8 标定〔`kv_cache_scheme.num_bits=8`，
> amax/448 几何〕的逐层 `*.self_attn.{k,v}_scale` 张量当 NVFP4 全局 scale〔amax/6 几何〕
> =约 75 倍失配；无校验、无日志、无修复 release）。host 侧规避=把「开门前几何一致性」
> 变成可断言对象：**不开门就不用手术；要开门必须先过守卫与验收门**。
> 落点双面同件（md5 一致互证）：战役仓 `luz030-opt-campaign/tools/upstream/nvfp4-kv/`
> 与公开仓 `luz-034re/tools/upstream/nvfp4-kv/`；`SOURCE-MD5.txt` 为互证锚。

## 三件套与用法

| 件 | 职责 | 用法 | 退出码 |
|---|---|---|---|
| `nvfp4_kv_scale_guard.py` | serve 参数 lint + checkpoint 联合守卫（加载期校验代位，fail-closed） | `python3 nvfp4_kv_scale_guard.py [--argv "..."] [--serve-file F] [--model-dir D]`；`--selfcheck` | 0=PASS/WARN；1=FAIL；2=取证失败 |
| `nvfp4_strip_kv_scales.py` | 剥 scales 手术：删 `*.self_attn.{k,v}_scale`（缺省广义=一切 `*.k_scale/.v_scale`）+重写 header offsets+`kv_cache_scheme` 置 null，走动态 scale 路径 | `python3 nvfp4_strip_kv_scales.py --model-dir D [--apply] [--exact-only]`；`--selfcheck` | 0=成功/无可剥；1=术后校验红；2=用法/取证失败 |
| `nvfp4_needle_gate.py` | 手术上线验收门：d50/d500 needle 检索（薄包装正典件 `tools/needle_probe.py`） | `python3 nvfp4_needle_gate.py --base URL --phase pre-strip\|post-strip`；`--selfcheck` | 0=门绿/取证完成；1=门红；2=取证失败 |

守卫判定矩阵（runtime `--kv-cache-dtype` × checkpoint 面）：

| runtime | checkpoint 面 | 判定 |
|---|---|---|
| nvfp4 | 带 k/v_scale 且 scheme.num_bits≠4（含缺省） | **FAIL**（issue 命中态：先手术+过 needle 门） |
| nvfp4 | 带 k/v_scale 且 num_bits=4 | PASS（ModelOpt NVFP4-KV 正当标定形，不误杀） |
| nvfp4 | 无张量、scheme=null | PASS（动态 scale 路径=报告者生产验证形） |
| nvfp4 | 无张量、num_bits=8 | WARN（无错用发生，建议置 null 消歧） |
| 非 nvfp4/未启用 | 任意 | PASS（几何不命中；附开门前置提示） |
| nvfp4 | 未给 `--model-dir` | rc=2（fail-closed，不得放行） |

## 开门制式（上线流程）

1. **剥前取证**：`nvfp4_needle_gate.py --phase pre-strip`——issue 报告口径为 d50=1/4、
   d500=0/4（预期红，即缺陷诊断证据；本相位恒不放行）。
2. **守卫定谳**：`nvfp4_kv_scale_guard.py --argv "<serve argv>" --model-dir <ckpt>`——
   判据①红（命中态）才需要手术；判据③绿则无需手术。
3. **手术**：`nvfp4_strip_kv_scales.py --model-dir <ckpt>`（dry-run 看计划面）→ `--apply`
   （原件 `.bak-pre-nvfp4strip` 字节保真留底；术后内建逐张量 md5 校验；台账
   `nvfp4-strip-manifest-*.json` 在档）。
4. **复守卫**：守卫复跑须转判据③绿（无张量+scheme=null）。
5. **验收门**：`nvfp4_needle_gate.py --phase post-strip`——**两档各自 4/4 全中**方放行
   （issue 报告剥后口径 4/4+4/4）；任一针 FAIL/SKIP=门红（无证据不得放行）。
6. 两绿后始可开 `--kv-cache-dtype nvfp4`；开门后守卫以 argv 模式常备复查。

档位口径：d50/d500 按 issue 报告语境取 50K/500K token 文档档位（报告者 2×16GB 卡开
nvfp4 KV 的动机即塞下超长上下文），缺省 `--sizes 50000 500000 --repeats 4 --depth 0.5`，
全部可参数覆盖；判据（每档全中）与档位参数解耦。

## 当前生产态取证（2026-10-30 建件窗，只读亲核）

- 生产 checkpoint `/data/models/DeepSeek-V4.1-Flash-1017`：48 分片 header 亲读，
  k/v_scale 张量=0、`kv_cache_scheme` 无声明（守卫与手术件双具实测在档输出）。
- serve 参数面（`r3-boot-arm.sh` SERVER_ARGS + `prod-profile.env` SPEC_EXTRA_ARGS + env 面）：
  无 `--kv-cache-dtype`（KV cache 走 fp8 几何，env `SGLANG_DSV4_KV_LAYOUT=v41` 为 KV
  布局键、另一参数面）。
- 结论：**当前栈不命中缺陷态，无需手术**；三件套作为「未来开 nvfp4 KV」的前置
  断言面与工具箱常备（V4.1-Flash 官方架构口径含 FP4 KV，开门动机真实存在）。

## 红线与边界

- 三件全只读产线（手术件 `--apply` 仅对显式给出的 `--model-dir` 动盘，且自带备份与
  校验；不在本目录对任何在役面预设写动作）。零 git、零引擎/容器生命周期动作、
  不动镜像（上游缺陷的根因在引擎 load_weights 面与 checkpoint 面，host 侧只做
  规避，不改引擎源码）。
- `nvfp4_needle_gate.py` 仅向 `--base` 发探针请求；依赖正典件 `tools/needle_probe.py`
  （两面同构接口：`--form/--sizes/--seed/--depth/--json-out`）。
- 自检全部离线（合成 safetensors/config/聚合样本，tmpdir 内，不发包不写仓）。

## 升级关注（退役条件）

上游把「加载期 num_bits×运行时 dtype 校验 + 不匹配告警跳过回落动态 scale」发布后
（issue 报告者诉求的泛化双向检查；关联 PR #42419 一类），对新 checkpoint 本手术
退役：届时引擎自身会拒载/回退，守卫判据①的命中态不再可能静默发生。判据②
（num_bits=4 正当形）语义与上游一致，长青保留。升级窗以
`tools/upstream/deepseek-recipe-pypi-probe.sh` 同款的版本跟踪/CHANGELOG 核对面承接。
