# overlay 增量（0.3.1 → 0.3.2）

现役 overlay 仍是 29 个活件；唯一变化是 `deepseek_v4_backend.py`：

| 件 | 0.3.1 | 0.3.2 |
|---|---|---|
| `deepseek_v4_backend.py` | 736fbde5 | **a1e7c3b5** |

- 来源：S-FIX-W0c 上靴窗（2026-10-18）的 S3′+import 预检 9/9 形。
- 同一 md5 也出现在 r032c 镜像的 `python/sglang/srt/layers/attention/deepseek_v4_backend.py`
  （见 `image/port16-tree-md5-r032c.txt`），即 overlay 挂载面与镜像面一致。
- 部署位：`~/migrate-assets/v4vl/sglang-overlay.o12c1-prod/`，目录保留 29 个活件
  （产线另有两个 `.bak-pre-w0b/w0c` 备份，本包不收）。
- boot 链的 overlay 计数断言按 28 个影子挂载 + 1 个映射表工作；替换单文件不改变件数。

```bash
cp deploy/reconstruct/0.3.2/overlay/deepseek_v4_backend.py \
   ~/migrate-assets/v4vl/sglang-overlay.o12c1-prod/
```

回退：回拷 `deploy/overlay/o12c1-prod/deepseek_v4_backend.py`（736fbde5）+ 复靴。
