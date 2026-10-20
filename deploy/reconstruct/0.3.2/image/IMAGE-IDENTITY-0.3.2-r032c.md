# IMAGE-IDENTITY — 0.3.2-r032c（S-FIXC-BITPRESERVE-20261018 位级保持形）

## 身份四件

| 项 | 值 |
|---|---|
| tag（正典/push 实证） | `192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c` |
| 本地孪生 tag | `192.168.5.187:5000/dsv41-sglang-optimized:0.3.2-r032c`（.187 命名连续性；push 通道以 .202 为准） |
| manifest digest（三方一致） | `sha256:47f6d91ada988d7a828be5dd87faeec53b0cd633f617bbfbd850468080e2ffc4`（本地 RepoDigest = docker push 报文 = registry Docker-Content-Digest 亲核 200） |
| 内容身份 cid（RootFS 层链 sha256 前 16） | `6e379f6fe0531c9c`（71 层=基座 70+1） |

## 构成形

- 基座：`192.168.0.202:5000/lmsysorg/sglang:main-79cafec0`（image `80e1ea8979c5`＝现役形；70 层；零 pull）
- 增量：单 COPY 层 71 层；载荷=16 件 → `/sgl-workspace/sglang/{python,test}/…`
- 重演树：`/tmp/bt-r032` @ `f9d89b02`（tree `dab49d96d33839480e30a1d24ac9e6cdb0a9c29d`）＝ r032b（e0693e96）+ 位级保持补件
  （scoring.py 恢复 stock 79cafec0 候选序排序；+16/−5；diff md5 d0dd3341）
- **对 r032b 的镜像级差分证明**：16 件对照 **15 SAME + 1 DIFF（仅 scoring.py 658b69ec→e056f588**；
  `logs/S-FIXC-BITPRESERVE-20261018/inimage/r032b-vs-r032c-16files.txt`）——r032c ≡ r032b + 位级保持单件
- 16 件 md5 台账：`logs/S-FIXC-BITPRESERVE-20261018/closure/port16-tree-md5-r032c.txt`；镜像内读回逐件一致

## LABEL（镜像内读回）

`DSV41_IMAGE_VERSION=0.3.2-r032c` / `DSV41_PORT_BASE=520d6d0+fc2795b+391e665(candidate_block_mask)` / `DSV41_PORT_SCOPE=minimal-deadlock-fix +bit-preserve-selection-order 16 files` / `DSV41_REPLAY_TREE=dab49d96d33839480e30a1d24ac9e6cdb0a9c29d` / `DSV41_BASE_DIGEST=80e1ea8979c5` / `BUILT_AT=2026-10-18T05:20:00Z`

## 门槛读数（G1 门升格口径全承+位级对拍新增）

- 读回校验：镜像内 16 件 md5 与树台账逐字节一致；py_compile 16/16 OK；**import 审计 14/14 OK（fail-closed）**；
  四件套 pytest collection 绿（171 tests 0 error 口径）
- **位级等价对拍（本镜像核心验收）**：stock 基座镜像（79cafec0）与 r032c 双容器（--gpus all，
  GB10/CUDA）同一合成输入（seed 20261018），selection 缓冲 sha256 逐位比对
  **7/7 案例×{面1 write_selection page/raw, 面2 write_page_indices page/raw, 面2b sparse raw-only} 全等 PASS**
  （`logs/S-FIXC-BITPRESERVE-20261018/bitparity/`；探针判别力实证=首轮抓出 page=None 分支排序缺失已修）
- AST 面：dense_blocks 四方法签面＝S3-verify 锚值；scoring write_selection/write_page_indices 签面在档
- 闭包三层面 GREEN：forward/reverse/gap=candidate_blocks 既有；r032b vs r032c 签名 21 符号恒等+import 面 16 项零差
- 零生产触自证：构建前/后 docker ps 逐行 diff（唯一差异=产线容器 Up 时长自然增长）；零 pull/零 reload；
  registry 既有 tag 原样零覆盖，仅新增 0.3.2-r032c

## 复现命令

```bash
bash tools/packages/_bake/build-0.3.2-r032c.sh        # 构建+读回+py_compile+import 审计+collection
docker push 192.168.0.202:5000/dsv41-sglang-optimized:0.3.2-r032c
```

回退：零部署（不 pull 不 reload 生产）——在库待上靴窗（任务书 §12-4 验收门）；r032b 同态在库。
