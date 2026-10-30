# tests/quality/ —— 0.3.3 CPU 质量测试（W0 起）

## 所有权（任务书 §3.0.1，唯一作者 T33-01C；T33-10 复用 fixture，不得复制）

| 文件 | 内容 | 结果口径 |
|---|---|---|
| `conftest.py` | 共享 fixture：`tokenizer_v41_local` / `encoding_dsv41` / `mock_sampling_params` / `detector_chunks` / `baseline_prompt_hash`（另附 `tokenizer_production_1017`、`dsv41_detector_cls`） | T33-10 的 `test_no_go_*.py` 直接复用 |
| `test_tok_contract.py` | G-TOK：产线 1017 tokenizer 只读核对 + 本机同源副本 + hash 白名单；官方 `<｜image｜>` 仅对照 | passed（1017 已直读确认）+ 1 xfail（字面特殊 token 静默转 added token） |
| `test_max_tokens_matrix.py` | K16 定稿语义 5 case（executable spec）+ 现役缺口登记 | 5 case passed + 4 xfail（131072 放行/131073 400/512k pin 日志/Max 缺省档，属 T33-01A） |
| `test_response_format_positive.py` | 正例：首条 system 注入、json_schema/json_object、tools 并存 | 3 passed + 2 xfail（dsv41 接线、regex 变体，属 T33-01A） |
| `test_dsml_stream.py` | 8 档 chunk 正常调用、bare invoke、marker 跨 chunk 切分；字面 DSML 误判/吞尾登记 | passed（24 正常调用位）+ 9 xfail（修复归 T33-01B 0.3.4） |
| `test_known_defects.py` | defer_loading/prefix 已知缺陷逐条登记 + wo_eos 原语 pass | 1 passed + 4 xfail（修复归 T33-01B 0.3.4） |
| `test_no_go_render_contract.py`（T33-10） | G-RF 负向护栏：缺省 body 逐字节不变；`SGLANG_DSV41_RF_INJECT` 未开不注入 schema；tools 在场禁双重约束 | 1 passed（必须 pass，无 xfail 掩盖） |
| `test_no_go_grammar_cache.py`（T33-10） | G-CACHE 静态检查：grammar cache 必须有界 + CVE-2025-32381 防护点存在（锚定 `base_grammar_backend.py:206` 无界 dict） | 1 xfail（`strict=True`，reason 固定；`--runxfail` 现状红；0.3.4 护栏项） |

T33-10 自有文件（2026-10-23 交付，作者=W0 执行子代理 R-TEST）：上表末两行；正例与已知缺陷
登记归 T33-01C，负向护栏/有界性登记归 T33-10，互不重复（任务书 §3.0）。

## 运行

CPU-only、无网络、无模型权重加载（tokenizer 仅解析 JSON 的 added_tokens 表）、单次 <60s。
本机系统 python 无 pytest（PEP 668），用 /tmp 临时 venv 运行（不触碰系统/仓库环境）：

```bash
python3 -m venv /tmp/w0venv
/tmp/w0venv/bin/pip install pytest
cd /home/<deploy-user>/luz-deepseek-flash-all-in-one
PYTHONDONTWRITEBYTECODE=1 /tmp/w0venv/bin/python -m pytest -q tests/quality/ \
    -o cache_dir=/tmp/pytest-cache-quality
```

`-o cache_dir` 与 `PYTHONDONTWRITEBYTECODE=1` 保证不在交付仓留 `.pytest_cache`/`__pycache__`。

T33-10 本门计数口径（任务书 T33-10 验收门）：

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/w0venv/bin/python -m pytest -q tests/quality/test_no_go_*.py \
    -o cache_dir=/tmp/w0cache          # 期望：1 passed（G-RF）+ 1 xfailed（G-CACHE），退出码 0
# xfail reason 单列：加 -rx；G-CACHE 现状红：加 --runxfail（期望 FAIL，退出码非 0）
```

若 G-CACHE 意外 XPASS：strict xfail 转红，须删除 xfail 标记并升级为正常测试后重跑本门。

若环境已有 pytest：`python3 -m pytest -q tests/quality/` 即可（无第三方依赖，全 stdlib）。

## fixture 交付说明（给 T33-10）

同目录测试自动获得 fixture；跨目录引用时把本目录加入 `sys.path` 后 `import conftest`。
路径可用环境变量覆盖：`T33C_SGLANG_SRC` / `T33C_TOKENIZER_V41_LOCAL` / `T33C_TOKENIZER_PROD_1017`。

- `baseline_prompt_hash`（session）：缺省 messages 的 dsv41 prompt 及其 sha256——
  G-RF「缺省 body 逐字节不变」的对照基准。
- `encoding_dsv41`（session）：dsv41 编码器模块（stdlib-only，直接 import 可调用）。
- `detector_chunks`：`[1,2,3,5,7,11,23,1000]`。
- `mock_sampling_params()`：`SimpleNamespace(max_new_tokens=..., ...)` 工厂。
- `tokenizer_v41_local` / `tokenizer_production_1017`：只读 tokenizer 契约视图
  （`entry_by_id/entry_by_content/flag/sha256`），不加载权重。

## 纪律

- 只读：模型目录（/data/models、~/models）与 SGLang 源码树（~/sglang-main-src）仅读；
  生产 env 文件只按行提取 `SGLANG_MAX_NEW_TOKENS_LIMIT`，不读其余行。
- 不启容器/GPU/引擎；不写 git；不替换 tokenizer（NG-08）。
- 已知缺陷一律 `xfail(strict=True)` + reason，不静默跳过；`--runxfail` 可看现状红。
