# overlay 备查正典（0.3.4 面，2026-10-31 备查同步窗）

本目录收录 0.3.4 血统三件正典**全文**，补公开树此前「只有锚值、没有本体」的缺口。
overlay 整面 29 件活树=`deploy/overlay/o12c1-prod/`（对表清单=
`deploy/prod/overlay-md5.txt`）；本目录只额外留身份正典三件，逐件身份/md5/补丁链
总表=[../../README-说明.md](../../README-说明.md)。

| 件 | md5 | 身份 |
|---|---|---|
| `deepseek_v4_backend.py` | `73c80259` | 0.3.4 backend 正典（X6 bake R1 终形） |
| `serving_chat.py` | `9b60a463` | 0.3.4 现役 head 面 serving 正典 |
| `page_map_export.py` | `c0dfe59a` | 0.3.4 新增第 29 源（KV 池页映射引擎侧导出件） |

血统一句话版：

- **backend**：0.3.1 `736fbde5` → 0.3.2 `a1e7c3b5` → r033 `15df9168` → r033d
  `53cc9d61` → **0.3.4 `73c80259`**。终形=X6 bake R1（2026-10-26）自 r033d 基底
  并入上游 hunks #45301/#40424（声明依赖 #45586/#45699）idle-SWA 终形，重锚落四机
  部署面后被 034-lock（2026-10-28）锁档（四机 IDENTICAL）。
- **serving_chat**：镜像 stock `b77a736c`（02-04 机 worker 面沿用）→ 0.3.3 W5 窗
  （2026-10-24）t33-01a recipe-rebase 补丁自 recipe 线 `3151a2ed` 演进为
  **`9b60a463`**（01 机 head 面；+333/−0），此后 X6→034-lock→0.3.4re 全程原值
  承袭未再改。
- **page_map_export**：0.3.4 **全新件**（此前任何代际无此文件、无旧形）。X6 bake R1
  任务 8「A.2 制备」为补引擎侧页映射导出缺口而新建：rank 级 req_to_token 页序列
  聚合 + `page_seq_sha256` 对拍契约；env 门控 `DSV41_PAGE_MAP_EXPORT` **缺省关**
  （不设=snapshot() 返 None，零行为零开销）。入列后 overlay 自 28 源扩为 29 源
  （`overlay-map.tsv` 第 29 行）。

与 0.3.2 增量件（[`../0.3.2/overlay/`](../0.3.2/overlay/NOTES.md)）的关系：那是
**0.3.2 历史定版形**，只用于 0.3.2 整套重建；**禁止**拿它拼 0.3.4 镜像
（绑定律/混形禁忌，0.3.4 镜像×0.3.2 overlay=无档混形）。

红线：本目录=备查（身份对照/审读用），不是运行件分发位。拼源运行一律以发布镜像
（`0.3.4-x6bake-20261026`，网盘发布包 `images/`）+ 整面 overlay 29 件为准，本仓
对自拼栈不做运行保证。
