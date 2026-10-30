# TOOLS31-BAKE-RESULT-20261013 — LuZ-0.3.1 容器烘焙停机窗结果档

> 法源：BAKE-PENDING-FINAL-GATE.md 案头批全序+TOOLS31-PACKAGE-PLAN §五+ARCHIVE-EXEC1 §五
> 第二批八项+用户窗令（含 G7 追加与 S9 暂缓两裁定）。执行机：<node01>（head）+四机栈；
> 执行窗 2026-10-13 15:27:33Z–17:0xZ UTC（OUTAGE 15:29:52Z→16:53:52Z，两靴窗含沉降
> 1800s×2）。判读线 G1-G6 开窗冻结+G7 用户指令追加冻结（run.log 在档零事后改；执行中
> 勘正 1-6 均量具面/判据场景面缺陷，原行永留可溯）。
> 台账：logs/TOOLS31-BAKE-20261013/（run.log+desk/ 脚本族+boot-checks/+build/+deploy/
> +teardown/+state/）。

## 一、逐门读数（G1-G6 开窗冻结线）

| 门 | 判读 | 读数 |
|---|---|---|
| **G1 冷构建可复现硬门** | **PASS** | NOCACHE=1 双临时标签连跑：cid=658a5fe6436510ed 全等+镜像内 /opt/dsv41 正典集合指纹=d4032092 全等+官方构建三跑全等（image id 异号=Config created 时戳差非内容面，0.2.8 先例 BUILT_AT 只钉 LABEL 面） |
| **G2 boot 门链**（BAKE031 验证靴） | **绿** | rc=0+8899=200+target_verify=**45.17s**（44-46s 健康带内）+banner29:4+池 9,600,000+[fl6_recall] 四容器各 2 行 patched（mode=both）+零漂移拒起 |
| **G3 warm 门** | **绿** | 64k×4 步=3988.2/5948.2/6010.7/5924.9+64k×3 中位 **6114.3 tok/s** ≥5000（FL6-PROMO 同窗参照 6083.0） |
| **G4 四查+真键核+注入面** | **绿** | 四查全套（O12 四秩各一+R1 fail-safe PASS rows=96 ×4+MISMATCH=0+chunk 4096+swa prefix_tails 256/swa_tokens 125,440 直读）+printenv FP8=1 TG=1 R1INK=1 FL6FIX=1 ×4+SPLIT/DETINF unset ×4+注入面成对核对（argv 直读 SPEC6 六参全数在役=SPEC_EXTRA_ARGS :396-398 优先律不因烘焙失效） |
| **G5 smoke+水位+收净** | **绿** | smoke 3/3（北京 temp0）+WATER-RED=0（全窗 min>10G）+8898 收净 000+memcg preboot/postboot/final 全绿 |
| **G6 指纹四件** | **绿** | ①包内五包 MANIFEST 镜像内 md5sum -c 全 OK ②LABEL kit_manifest_md5=629be984cbde1b9a5c9ac2cf4bc9e6f4 四机同值=构建值 ③IMAGE-IDENTITY 镜像内副本=宿主权威件逐字节（c7e96837）④部署面集合指纹四机全等：adapter=**bfd2a901**（按 sitecustomize 55b1e412 现值重算——BAKE 档 2c4baad3 口径过时，重算值在档更替）+overlay=73695876（正典） |
| G7 打包完整性 | 段暂缓承载 | 16:13-16:20Z 实测绿（三件 sha256 实算=伴档全等+CHECKSUMS.manifest sha256sum -c 三行成功；勘正 4 承载）→16:30Z 用户裁定单基座交付 S9 整体暂缓，产物标 DEPRECATED 不入交付清点 |

## 二、烘焙镜像身份（交付资产）

| 项 | 值 |
|---|---|
| tag | <registry-host>:5000/dsv41-sglang-optimized:0.3.1（registry 新 repo；lmsysorg/sglang 原位不动；registry 主机已脱敏） |
| image id / registry digest | sha256:79e701ab4658013ce51855cc8ed97b09f892b20287bebd58b204934a1267cfd5 |
| 内容身份 cid | 658a5fe6436510ed（RootFS 层链 sha256 前 16 位；四机全等亲证×4） |
| 体量/层数 | docker images SIZE=48.6GB（共享基座面）/inspect .Size=14,439,685,902B/71 层（70 基座+1 COPY） |
| git 锚 | 90261d5（构建时工作树干净硬断言通过；LABEL git_anchor 同值） |
| kit_manifest_md5（LABEL） | 629be984cbde1b9a5c9ac2cf4bc9e6f4（五包 MANIFEST 拼流算法钉定） |
| 五包指纹（镜像内形态） | fabric-net=5e2a1fb9/selfdiag=5727bf05/selfheal=627fef97/gateway=282b9ad2/cfgmgmt=**cec6920a** |
| 载荷 | /opt/dsv41/packages/ 五包 124 件+/opt/dsv41/docs/ T3 四件+IMAGE-IDENTITY+ARGV-PAIR-REGISTRY+BAKED-BY |
| 排除清单执法 | adapter/overlay（bind mount 真源）+宿主守护件+b12x/nccl/engram+密钥件（镜像内扫 0 真实命中——三处字面命中=gateway 包自检红例夹具假值）+__pycache__/*.bak-*/日志/state |
| 拍扁 argv 成对律 | **零拍扁声明**（镜像不烘任何 argv/环境键面；ENV 仅 DSV41_IMAGE_VERSION=0.3.1 自描述键；ARGV-PAIR-REGISTRY.tsv 双登记+IMAGE-IDENTITY 成对表；外部注入面 G4 实证优先律存活） |
| 分发 | registry push 增量秒级（基座 70 层 blobs 已在库）→02/03/04 pull→四机 cid 对表全等（0.2.8「永不推 registry」律的 0.3.1 承接注记=该律针对 0.2.x 深层基座 pull 前科；本代基座四机 registry pull 亲证可行，律意〔四机同栈构造保证〕经 cid 全等硬核不破） |

## 三、产线复原态亲证（S6）

- 复原靴 BAKE031R：**原基座镜像** <registry-host>:5000/lmsysorg/sglang:main-79cafec0
  （r3prod-head Image= 直证；boot 脚本=~/migrate-assets/bin/r3-boot-arm.sh 原位零触碰
  c051bb41）+**51 键终值形**（ENV51 2ac74586/51 键+sitecustomize 55b1e412+fl6_recall
  b87cbb5e ×4+overlay o12c1-prod 29+SPEC6）。
- 断言面：rc=0+8899=200+banner29:4+池 9.6M+E3A 三断言绿+[fl6_recall] 四容器×2 行+
  四查全套+printenv 四键 ×4+注入面成对绿+smoke 3/3+8898=000+四容器=4+02 两守护在档。
- 注记（如实披露）：复原靴 target_verify=102.85s（G2 健康带 44-46s 外——G2 带冻结于
  BAKE031 验证靴〔45.17s 带内 PASS〕；复原靴读数=复原观察注记位非门控；靴墙 9m21s，
  引擎全断言面绿无功能红；前置差异=S9 docker save ~27G 读盘 I/O 后的第二靴）。烘焙镜像
  退交付资产位（registry 在库），**切产呈裁=用户**。

## 四、T5 第二批八项台账（S7；ARCHIVE-EXEC1 §五清单）

| # | 项 | 处置 | 证据 |
|---|---|---|---|
| 1 | adapter 38 .bak-*（排除 r1recert 永不入档） | mv→~/archive-20261012/adapter-bak-ladder/；四机同摘（worker 先存后删=01 归档副本+哈希列预核全等 3217862016b7 ×4）；adapter-sync --check 四机全等绿；.bak 残留=1（r1recert 在场直证） | deploy/s7/adapter-bak-{list,pre-01,pre-*,post}.md5+adapter-sync-check.log |
| 2 | env/PROD-A22B-spec1.env.bak-prod-rs-20261003 | mv→env-superseded/（d9ea4995 双核；双源=arms/ 在仓）；cfgmgmt 三联动（env-MANIFEST 43ef4c4b 11 件净面落盘+包 MANIFEST 再生成+VERSION cec6920a→c4fb0c3e+TOOL-ANCHORS 三行同日更新） | payload/out/env-MANIFEST.md5+VERSION+TOOL-ANCHORS |
| 3 | b12x/comm.bak-prerocenante-r2 | **S3 停机窗内毕**（25 件/768,316B/41c02bc0；五路扫描全绿+mv 原子+md5 双核+三件套） | deploy/s3-b12x-comm-{pre,post}.md5 |
| 4 | dsv41/tests 2 件 | 逐件裁=归档（五路+活件引用零命中；md5 6cc46d02/5d45b76c 双核；空目录 rmdir） | pre-r3-scripts/tests/ |
| 5 | logs 八次级窗（F6PRIME 742M/F7TRIMODEL 686M/A0-base 481M/A2b-c1-roce 475M/H2LADDER 433M/A23-E0 337M/V2CERT 285M/H4READ 285M） | mv→~/archive-20261012/logs/（逐窗先/后 md5 全等；跟踪件 266 个随收窗 commit 删除登记；W5-STAGE2/R1-PROMO2/R1-FULLGATE/COMBO=定型证据链留库不档） | deploy/s7/logs-*-*.md5+git D 266 |
| 6 | bin/r3-boot.sh 红线席 | **呈裁不动照登记**（exec1 §二.5 原状态承接） | INDEX.md 呈裁行 |
| 7 | 顶层 h1-dev-hc_fused-repinned.py git mv | 呈裁位承接（exec1 §五.6 原状态；未动） | — |
| 8 | 20 个 t/*-done 分支+plan §四指纹门增补 | 呈裁登记（分支清理留 r1 tag 后；指纹门增补=呈裁项） | — |

- cfgmgmt selfcheck F6 转绿（OK28/UNKNOWN1→**OK29/UNKNOWN0**：ADAPTER-MANIFEST 终态
  55b1e412 回填位闭合=PENDING-FL6-FINAL 清）；五包 selfcheck 复跑全绿（29/37/26/16/29）。
- 归档三件套续记：MANIFEST.csv +5 行+INDEX.md 第二批两段+RESTORE.md 恢复行 ×4 面。

## 五、S9 打包段（暂缓待重烘焙——用户裁定单基座交付）

16:13-16:20Z 按追加令执行毕（bake tar 14.4G+vl tar 12.9G+repo 快照 89M+CHECKSUMS.manifest
三行 sha256sum -c 成功+README-DIST.md；G7 实测绿）→16:30Z 用户裁定**整体暂缓**：①VL 镜像
tar 不再打包（凑合态清除，V4.1 视觉将原生启用到 SGLang 基座）②烘焙镜像将因视觉启用
**补充重烘焙**，最终打包以重烘焙镜像为准。已产物标 DEPRECATED（~/luz-0.3.1-dist/
DEPRECATED-20261013.md）不删除不入交付清点（实占 ≈25G 压缩层形态；后续清理窗处理）。
本窗烘焙镜像仍然有效=51 键形验证+交付资产先例位。

## 六、git 动作（本窗）

| 动作 | 内容 |
|---|---|
| 开窗 commit | 判读线 G1-G6 冻结块（run.log+lib.sh+s0_open.sh） |
| 配方 commit 90261d5 | RECIPE-0.3.1+build-0.3.1.sh+IMAGE-IDENTITY-0.3.1+ARGV-PAIR-REGISTRY.tsv（=镜像 git 锚） |
| 收窗 commit | 本档+S7 三联动五件（cfgmgmt MANIFEST/VERSION/out×2）+TOOL-ANCHORS+IMAGE-IDENTITY 回填+窗档 logs/TOOLS31-BAKE-20261013/+266 跟踪件删除登记（路径限定） |

## 七、如实披露与勘正台账

1. **勘正 1**：S1 首跑 r3-stop 漏 CTN_PREFIX=r3prod（no-op 拆测试线名空间，产线零扰动；
   修正调用单次重跑）。
2. **勘正 2**：S4 首跑 fingerprint4_fl6 承袭开窗态判据（期望 4 容器）vs 停机窗 preboot
   正确期望 0——boot 未点火零扰动，判据加参量后重跑。
3. **勘正 3**：lib 裁剪漏携 banner_e3a 函数（E3A 三断言读数在 banner-faces+fourcheck 双面
   在档全绿；函数补位供 S6）。
4. **勘正 4**：S9b 伴档解析收 DONE 标记行（重跑三件实算全等+清单三行成功；GATE-REDS
   原行作废承载）。
5. **勘正 5**（本窗最重要控制流披露）：S7 adapter 预核 diff=md5sum 全行比对遇绝对/相对
   路径恒不等假阳性，且「停手取证」守卫只 log 未 exit——**fail-closed 意图未接线**；零
   损失三重实证（归档 md5 双核+哈希列四机全等+adapter-sync 绿）。守卫接线缺陷入档=后续
   窗脚本族复盘项。
6. **勘正 6**：S7b 首跑 gen-manifests/admregen 缺省 stdout 模式未落盘（显式 --out 重跑，
   三联动重做；cfgmgmt 指纹终值 c4fb0c3e）。
7. 镜像内置 cfgmgmt=cec6920a（烘焙时点形态）vs S7b 后仓内 c4fb0c3e：**窗内时序设计内**
   （S7 复原后承载）——差集=env-MANIFEST 43ef4c4b+ADAPTER-MANIFEST 终态+VERSION 重钉，
   属包台账刷新非载荷缺陷；重烘焙窗自然携带新指纹。
8. 复原靴 target_verify=102.85s 注记（见 §三）。

——TOOLS31-BAKE 执行代理 / 2026-10-13。
