# SCAN-REPORT — 密钥与敏感信息扫描报告（推送前硬门）

> 扫描时点：2026-10-13 两轮——首建（175 件）+ **规格升级扩面重扫（1102 件 /
> 86MB：tools 全树+overlay+NCCL 栈+b12x+kit+models.d，N1-N7）**。
> 工具：`grep -rEn` 多模式 + 二进制 `strings` 抽取 + 逐命中人工复核。
> 判据：**任何红命中=该件不入仓或脱敏后入（零容忍）**。

## 扫描模式与结果总表

| # | 模式 | 命中数 | 判定 |
|---|---|---|---|
| P1 | key 字面量：`sk-[A-Za-z0-9]{16,}` / `AKIA[0-9A-Z]{16}` / `ghp_·gho_·github_pat_` / `-----BEGIN … PRIVATE KEY` / `Bearer <20+字符>` | **0** | 绿 |
| P2 | 赋值型凭据：`(api[_-]?key|passwd|password|passphrase|secret|auth[_-]?token|access[_-]?token|client[_-]?secret) [:=] <8+字符值>` | 1（见处置①） | 绿 |
| P3 | `GW_API_KEY` 全出现位值位核（政策=值位必须空） | 全空/占位（处置①②） | 绿 |
| P4 | 集群口令面：`sshpass` / `-pw` / `PasswordAuthentication` / 集群密码值 | **0**（仅「口令零接触」陈述句） | 绿 |
| P5 | `password/passwd` 显式词 | **0** | 绿 |
| P6 | `secret(s)` 词面（排除测试假值/律文陈述） | 0 余量 | 绿 |
| P7 | URL 内嵌凭据 `scheme://user:pass@` | **0** | 绿 |
| P8 | env 件/模板非注释赋值行值域复核 | 全为开关/数值/协议/占位（处置②） | 绿 |
| P9 | 高熵 base64 块（>40 连续字符） | 0（命中皆为路径/文件名串） | 绿 |
| P10 | `token` 词面（人工复核） | 全为 KV/tokenizer 域名词（SGLang 语义），无凭据赋值 | 绿 |
| P11 | 内网 IP/主机名（`dgxspark01-04`/RFC1918 段） | 26 件含 | **政策保留**（处置③） |

## 命中项处置清单（人工复核逐项）

**① `tools/packages/gateway/payload/concurrency_proxy_v2.py:162`**
`GW_API_KEY = os.environ.get("GW_API_KEY", "")` —— 运行期环境读取，缺省空串，
**非凭据值**。同件 :136 文档串 `GW_API_KEY=`（空）。处置=**保留**（代码语义件）。

**② gateway 包 selfcheck/gw-verify 测试假值三处（判别力红例 fixture）**
- `gw-verify.sh:92`：`GW_API_KEY=test-key-not-a-secret`（临时文件注入）
- `gw-verify.sh:105`：`Environment=GW_API_KEY=leaked`（泄漏检测红例）
- `selfcheck/run.sh:48`：`GW_API_KEY=real-secret-here`（占位模板判红例）

均为**显式假值测试夹具**（自检判别力=能检出真值注入的负例），不指向任何真实
凭据；T4 五包 selfcheck 设计在档（TOOLS31-PACKAGES-RESULT）。处置=**保留**
（缺件则自检红例失效）；命名自明（not-a-secret/leaked/here）。

**③ 内网 IP/主机名 26 件**——内网部署文档性质（boot 链主机表/HCA 端口映射/
回退链 md5 表等），按本仓策略**保留**；`deploy/README.md` 已注记对外发布脱敏
预案。涉及件：deploy/bin/ 链、docs/research/ 各档、gateway/cfgmgmt 包 README。

**④ env 件值域**：`deploy/env/` 两件 50/51 键全为功能开关/数值/表值
（HCA 表/对端映射表），无凭据类键；gateway.env.template `GW_API_KEY=<值位空>
`占位（政策态）。

## 集群口令专项

零出现。全部「口令」字样=纪律陈述句（「sudo 零使用口令零接触」等窗档合规行）；
`selfdiag/payload/probes/memsnap.sh:13` 提及 `~/.sudopw` 为**机制路径引用**
（stdin 喂入不落日志），非口令值。

## 结论

**硬门通过：红命中 0；全仓无任何真实凭据值。** 可推送（remote 待用户供）。
重扫触发律：任何后续 commit 前重跑 P1-P7/N1-N7；新增 gateway/env 类件必过 P3。

---

## 扩面重扫（规格升级后，N1-N7，1102 件含二进制）

| # | 模式 | 命中数 | 判定 |
|---|---|---|---|
| N1 | key 字面量全仓（含 -I 文本抽取） | 0（唯一命中=本报告自引模式行） | 绿 |
| N2 | 二进制 strings：ncclpin.so+libnccl.so.2.30.7（ELF×2） | 0 hits/件 | 绿 |
| N3 | 赋值型凭据（扩面重跑 P2） | 0 | 绿 |
| N4 | Authorization/Token 头+token 赋值（tools/overlay/kit 扩面） | 全为 KV/tokenizer 域名词，零凭据赋值 | 绿 |
| N5 | `~/.sudopw`/sshpass 机制引用 | 6 处=机制路径（r3-boot 链/kit 量具/pw-login-test——口令恒从宿主文件读入，绝不打印/不入仓）；**零口令值** | 绿 |
| N6 | URL 内嵌凭据+高熵串（新面） | 0 | 绿 |
| N7 | 宿主密钥件混入防线（`.env*` 全清点） | 7 件全为键面规格：deploy/env 两形+cfgmgmt 回退链库四形（md5 对表 FORM-REGISTRY 全中：15767aa6/8c8c166d/99e7ec92/34977bf0）+gateway 模板（GW_API_KEY 值位空）——零密钥值类 | 绿 |

**API_KEY 机制专项**（kit 量具 v41_kfix_ab/v41_dose_ladder/guard gen_probe）：
API_KEY 一律 `grep` 自宿主在役 env 文件（`.env.tp4-600k` 等，umask 077 面）——
机制引用零值；该类宿主件不在仓（N7 清点直证）。

**ssh-password-login-20261013/ 工具件专项**：三脚本+README=sshd 配置运维件
（就地改 99-hardening.conf 两值+备份回退+pty 判死验证；初版撤除用一次性修正
脚本已随 M4 去过程史删除——2026-10-13）；口令仅经 `~/.sudopw`
机制通道，输出一律 `***` 替换；零凭据值、零配置内容泄点（备份件在宿主
/var/backups）。保留处置。


---

## 附：线上仓敏感面交叉审核与掩码处置（2026-10-13，用户指令批）

用户点名五类（用户名/网关秘钥/wifi 秘钥/登录秘钥/免密登录令牌）全树+git 全史交叉
复审：真凭据类**零命中**（sudo 口令/私钥块/公钥体/云网令牌真值/wifi/env 值面/ELF
strings 全 0；GW_API_KEY 全空值；3 处假值=判别力 fixture 政策保留）。唯一实质项=
用户名 44 件+GitHub 账号名 1 处→已掩码（`liux***ya`/`lux***com`），受累 md5 清单
7 份逐行重生成，git 全史 filter-branch 同步重写+tag 重钉。逐类结论表/处置动作/
产线锚语义声明/范围外注记=**docs/registry/SANITIZATION-20261013.md**。

---

## 0.3.2 tag 清洁门（2026-10-20，`v0.3.2` 打标前）

**受检树**：0.3.2 定版维护 commit `de93725`（`c52a560` 之后的一致性/可用性维护；
tag `v0.3.2` 指向记录本节的收尾 commit）。**方法**：`git archive` 隔离检出
（1233 件/91MB），不依赖工作树；密钥面+语法+链接+临时代码全在隔离树重跑。

| # | 检查 | 结果 |
|---|---|---|
| T1 | 私钥块 / AWS / GitHub token / OpenAI key / Bearer / URL 内嵌凭据 | **0**（唯一 `scheme://user:pass@` 命中=本报告自身的模式文档行） |
| T2 | 用户名/邮箱/电话真值 | **0**（仅 `liux***ya`/`lux***com` 掩码形） |
| T3 | `~/.sudopw` 机制引用 | 28 处，全为机制路径（stdin 喂入、不打印、不入仓）；**零口令值**——沿 2026-10-13 政策保留 |
| T4 | 赋值型凭据 | 16 处人工复核：全部为本报告自引/判别力 fixture（`test-key-not-a-secret`/`real-secret-here`/`GW_API_KEY` 空值）；零真值 |
| T5 | 二进制面 | 7 件（NCCL ring-only 库+ncclpin+adapter `.so` 三件）；ELF `strings` 无凭据命中 |
| T6 | 大件 | 最大 `deploy/nccl/nccl-ringonly/libnccl.so.2.30.7` 60.5MB（<100MB GitHub 单文件上限；历史已在仓） |
| T7 | 临时/构建残留 | `*.pyc`/`__pycache__`/`*.log`/`*.bak`/`*.orig`/`*.rej` **0** |
| T8 | shell 语法 | 105 件 `bash -n` **0 fail** |
| T9 | Python 语法 | 全树 `compile()` **0 error** |
| T10 | 相对文档链接 | **0 坏链**（修 1 处 b12x 上游 doc 引用） |
| T11 | 起栈接线闸门自检 | `tools/serve_flags_gate.sh --self-test` R1-R7 **全 PASS** |
| T12 | 量具自检 | `sd_bench.py --selfcheck` **21/21 PASS** |
| T13 | 五包 selfcheck | 全包 **RED=0**（cfgmgmt 19/0/12、fabric-net 21/0/8、gateway 16/0/0、selfdiag 21/0/16、selfheal 18/0/11；UNKNOWN=宿主在役件不在隔离树，按 `sc_summary` 红优先于无法判语义 rc=2） |
| T14 | 版本面一致性 | README=0.3.2 定版+系列总览；致谢计数 111；`deploy/README` 标注混合快照边界；无残留「当前产线在役」旧断言 |

**结论：tag 清洁门 PASS**——零真凭据/零 PII 真值/零临时代码；保留项（`~/.sudopw`
机制引用、判别力 fixture、内网 IP、在仓 NCCL 二进制）均为已裁定政策面，不因本次
打标改变。重扫触发律沿前文：任何后续 commit 前重跑 T1-T4。


---

## 0.3.2 重建包清洁门（2026-10-20，`v0.3.2-recon` 打标前）

**受检面**：新增 `deploy/reconstruct/0.3.2/`（70 件/1.8MB）+ 同步改动的 8 份文档。
**方法**：包内 `MANIFEST.md5` + `verify.sh` 全量自验；密钥/用户名/临时代码/语法/
链接独立复扫。

| # | 检查 | 结果 |
|---|---|---|
| R1 | 包内 `MANIFEST.md5` | **69/69 PASS**（MANIFEST 自身不计） |
| R2 | `verify.sh`（env/adapter/overlay/b12x/image/weights/补丁/负向自检） | **RECON-KIT PASS** |
| R3 | 私钥块 / GitHub/OpenAI token / sudo 口令 / 赋值型凭据 | **0**（`verify.sh` 自身模式行除外） |
| R4 | 未掩码家目录（`/home/<8+位小写用户>`） | **0**；`adapter/build_repack_cuda.sh` 注释位=`/home/<deploy-user>` |
| R5 | 用户点名删除的 aria2 RPC 令牌 / `ms1017` | **0**（带宽优先辅助件未收，非重建闭包） |
| R6 | shell 语法 | 7 件 `bash -n` **0 fail** |
| R7 | Python 语法 | 34 件 `.py` `compile()` **0 error**（16 镜像件+engram 工具+包内件） |
| R8 | 临时/构建残留 | `*.pyc`/`__pycache__`/`*.log`/`*.bak`/`*.rej` **0** |
| R9 | 大件 | 最大 170KB（`common.py`/overlay backend）；**无二进制、无大文件新增** |
| R10 | 相对链接（17 份 md） | **0 坏链** |
| R11 | 补丁可应用性 | adapter/overlay/b12x 对公开 0.3.1 基线 `git apply --check` **PASS**；image 补丁对 `79cafec0` 16 件 **PASS** |
| R12 | 逐件复算 | adapter 12 件、overlay 1 件、b12x 3 件、image 16 件应用后 md5 **全等产线** |

**结论：重建包清洁门 PASS**。包内零真凭据、零未掩码用户名、零临时件；唯一人工
差异=`build_repack_cuda.sh` 注释路径脱敏（运行逻辑零改，还原后 md5=cd6c7707）。
