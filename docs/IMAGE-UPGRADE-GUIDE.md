# 镜像升级指南（LuZ 0.3.2 → 0.3.3 → 0.3.4 → 0.3.4re 世代与配套面总览）

> 回答三个问题：**现在有哪些镜像世代、换镜像时哪些配套面必须跟着动、每一步怎么自验。**
> 单一目标：升级后引擎跑的是你想的那个世代，且 BYPASS/overlay/env 三面仍然武装生效。
> 深入某一代的完整移植步骤见 [UPGRADE-0.3.4.md](../UPGRADE-0.3.4.md)；备查件身份对照见
> [deploy/README-说明.md](../deploy/README-说明.md)；bypass 工具用法见
> [tools/bypass/README.md](../tools/bypass/README.md)；术语速查见 [GLOSSARY-PUBLIC.md](GLOSSARY-PUBLIC.md)。

## 〇、一页速查：五联动律（换镜像必随动的配套面）

换镜像**从来不是只换镜像**。一个受支持的运行面=下面五件套同代配套，任何一件落在别的世代都会
出现「能起栈但行为不对」的隐性漂移：

| 面 | 内容 | 自验方法 |
|---|---|---|
| ① 镜像 | tag + RepoDigest（见下表） | `docker image inspect <tag> --format '{{range .RepoDigests}}{{.}}{{end}}'` 对 digest |
| ② boot 镜像行（他处亦称「目行」） | repo 件 `deploy/bin/r3-boot-arm.sh:40` 为注入形 `IMAGE="${IMAGE:?…}"`，tag 实值来自环境变量 IMAGE / prod-profile 的 PROD_IMAGE（同源） | 核 `echo "$IMAGE"`（或 profile 的 PROD_IMAGE）尾部 tag 是否=①的 tag；内部在役件为 :12 字面量形，以 `sed -n '12p'` 核 |
| ③ overlay 整面 | `deploy/overlay/o12c1-prod/` 29 件 + map，对照权威清单 `deploy/prod/overlay-md5.txt` 逐件核 md5 | `cd deploy/overlay/o12c1-prod && md5sum -c ../../prod/overlay-md5.txt` 应 29 行全绿 |
| ④ adapter 面 | 99 件（装钩后武装面口径；基底面=98 前态面 sitecustomize=45ca6e3e、交付锚=deploy/adapter/0.3.4-MANIFEST.md5；回正前现树/GitHub main/网盘包实测 sitecustomize=b4822e37 为 EQ-12 重钉漂移代，回正后以 0.3.4-MANIFEST.md5 为准——2026-10-31 注记）；装载缝 `sitecustomize.py`=dd69c59a（含 bypass 钩）、`prefill_bypass.py`=c4875258 | `bash tools/bypass/install-prefill-bypass.sh`（幂等，装好即 OK） |
| ⑤ env 61 键 | 含第 60 键 `DSV41_PREFILL_BYPASS=2048`、末行（第 61 键）`DSV41_ENGRAM_CACHE_GIB=2`、倒数第三行 `SGLANG_DSV4_KV_LAYOUT=v41` | 数键数+抽查三键值（内容判据，勿套内部 md5 锚） |

## 一、镜像世代表

| 世代 | tag | RepoDigest（sha256，全值） | 层数 | 取处 | 定位 |
|---|---|---|---|---|---|
| 0.3.2 | `0.3.2-r032c`（双 tag） | `47f6d91a…e2ffc4`（全值见 [DEPLOY-GUIDE §0](DEPLOY-GUIDE.md)） | 71 | 重建包自行烘制 | 历史定版 |
| 0.3.3 | `0.3.3-r033c-20261025` | `881f49721c79ae814e8b101f0e3a814d2adf7ef3765617e2ab0e5c1e3b9cafdc` | 72 | registry 冻结面 | 回退级 2（更早一级回退世代） |
| 0.3.3 | `0.3.3-r033d-20261025` / `0.3.3-r033` / `0.3.3-final-20261026`（三 tag 同 digest） | `9e34bd29b1ef02abc41ab8b28f3d3b3e69854bd878210f606d2433c7c8b719d7` | 73 | registry 冻结面 | 回退级 1（首选回退世代） |
| 0.3.4 | `0.3.4-x6bake-20261026`（=final 面） | `80e4c95712f3369ae4c087e1a879a3b63343f0469e5eb5a02aa7513b4968f7d0` | 74 | **网盘发布包** `images/dsv41-sglang-optimized-0.3.4-final-20261028.tar`（`docker load` 即得）或 registry | 现役发布面 |
| 0.3.4re | `0.3.4re-20261030` | `bd225d3de73718ae4f72d1f8e6d4116f5cbfb1fd0190cf4315e77e13efe5c286` | — | 内网 registry（192.168.0.202:5000）；网盘包未含（取件与口径见 [README-说明.md §七](../deploy/README-说明.md)） | 0.3.4 修复重构建（吸收上游 metrics_reporter 等 2 修） |

世代判别最快一招：`docker image inspect <运行中容器镜像> --format '{{index .RepoDigests 0}}'`
对上表 digest，就是哪个世代——**不要信 tag 字面**（tag 可被重打）。

## 二、升级通用九步（任意世代 → 目标世代）

```bash
# 1) 取镜像并对 digest（网盘包：docker load；registry：docker pull）
docker load -i images/dsv41-sglang-optimized-0.3.4-final-20261028.tar   # 或 docker pull <registry>/<名>:<tag>
docker image inspect 192.168.0.202:5000/dsv41-sglang-optimized:<tag> \
  --format '{{range .RepoDigests}}{{.}}{{end}}'                          # 对世代表全值

# 2) prod-profile 重钉镜像两行：PROD_IMAGE=<registry/repo>:<新tag>（全路径形）/
#    PROD_IMAGE_DIGEST=<上面读到的 digest>

# 3) 换 boot 镜像行指向新世代：repo 形 r3-boot-arm.sh 经 IMAGE 环境变量取值——改完第 2 步
#    的 PROD_IMAGE（或导出 IMAGE=<registry/repo>:<新tag>）即完成；内部站直接跑
#    tools/deploy-034.sh 会自动翻行并留备份

# 4) overlay 整面同步到目标世代面并自验
cd deploy/overlay/o12c1-prod && md5sum -c ../../prod/overlay-md5.txt    # 期望 29 行全绿

# 5) adapter 面核验/补装（幂等）
bash tools/bypass/install-prefill-bypass.sh                              # 期望 OK（幂等）或完成 98→99
#    注：缺省 ADAPTER_DIR=$HOME/migrate-assets/dsv41/adapter（内部四机在役位）；无该位的机
#    须以 ADAPTER_DIR=<供给面目录绝对路径> 覆盖运行，裸跑必 PANIC exit 9=防呆（2026-10-31 注）

# 6) env 面核验：61 键、第 60 键 BYPASS=2048、末行（第 61 键）ENGRAM_CACHE_GIB=2、倒数第三行 KV_LAYOUT=v41 在位

# 7) 起栈（boot 链），沉降至 health=200

# 8) BYPASS 武装核验
bash tools/bypass/bypass-armed-gate.sh -H "<其余三机>"                   # 期望每机 armed ≥1 ∧ refusing=0

# 9) 引擎面体检（内部站=doctor-034/verify-034 工具链；外部站按 DEPLOY-GUIDE 验收节）
```

## 三、世代专项注意

- **0.3.2/0.3.3 → 0.3.4**：配套面变化最大的一跳（v41 三联 KV 固化 + BYPASS 采用 + 61 键 env +
  overlay 28→29 件新增 page_map_export），完整移植步骤=**[UPGRADE-0.3.4.md](../UPGRADE-0.3.4.md)**
  （本指南是其总入口，不重复其正文）。
- **0.3.4（x6bake/final）→ 0.3.4re**：只动①镜像（digest 80e4c957→bd225d3d）与②boot 镜像行；
  ③overlay（清单 6c98cf8c）④adapter⑤env **三面不变**。判别=digest 与 boot 横幅；行为差异=
  0.3.4 吸收的上游修复（metrics_reporter 等 2 项）。**注意**：`0.3.4re` 镜像尚未入网盘包，
  网盘包内镜像仍是 0.3.4-final——取件与包时点差异见 [README-说明.md §七](../deploy/README-说明.md)。
- **跨世代回退**：回退路双径（整代回退/单差回置）见 [runbook/ROLLBACK-PATHS-034.md](runbook/ROLLBACK-PATHS-034.md)；
  回退同样要过上面第 4/5/8 步的面核验，不是只换镜像。

## 四、BYPASS 与镜像/overlay 的匹配原理（为什么有时 armed 会消失）

适配件 `prefill_bypass.py` 内钉的是 scheduler / PrefillAdder **九个方法源**的 sha256，
不是整文件 md5。因此：

- overlay 的 `scheduler.py` 从锁档形 `3db3275e`（采用窗锁定的定版）演进到现役 `4a7822a6` 后**仍能武装**——
  演进没有动被钉的方法源；
- 将来任何被钉方法源变动，适配**拒绝武装**并在日志给出 `refusing to arm … source drift`——
  这是 fail-closed 设计（宁可不加速也不盲跑），处置口径=[tools/bypass/README.md §四](../tools/bypass/README.md)；
- armed 行是「钩已触发+九哈希全中+重编译毕」的综合直证，**有它才算适配生效**；
  `refusing-to-arm=0` 而一条 armed 都没有=多半钩没装或 env 键没带，不是「安静地正常」。

## 五、常见坑（症状 → 根因）

| 症状 | 根因与处置 |
|---|---|
| 换了镜像但行为没变 | boot 镜像行没换（PROD_IMAGE / IMAGE 环境变量仍指旧 tag）——起栈脚本仍拉旧镜像。做第 2/3 步 |
| 起栈后速度/质量异常 | overlay 面漂了（镜像 21/29 预烘焙≠整面；不挂 overlay 的栈不是受支持构型，见 [README-说明.md §7.2](../deploy/README-说明.md)）。做第 4 步 |
| 没有 armed 行也没有 refusing | 钩没装（sitecustomize 仍前态）或 env 键缺失。做第 5/6 步 |
| `refusing to arm … source drift` | overlay 面被换成适配未钉过的方法源形。先 `md5sum -c` 对表；确属新世代演进则适配需重钉（=适配作者发布钉了新方法源哈希的新版；提 issue，勿手改 EXPECTED） |
| 四机一台 refusing 其余正常 | 该机 overlay/adapter 面单机漂移。逐机对表，勿整批重装了事 |
| `docker logs` 里 armed 限额不是 2048/32 | env 键值被改——armed 行原文即读数；确认 61 键面后再判 |
