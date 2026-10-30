# SANITIZATION — 线上仓敏感面交叉审核与掩码处置（2026-10-13）

- 触发：用户指令——对已推送 GitHub 的仓库文件开展交叉审核（用户名/网关秘钥/wifi 秘钥/登录秘钥/免密登录令牌），掩码遮蔽处理，受累 md5 认证去除或修改。
- 基线：main 21160cf（tag v0.3.1）→ 本批次后 tag 重指向净化 HEAD；git 全史同步重写（同替换对）。

## 一、审计结论（扫描电池逐类）

| 类别 | 扫描面 | 结论 |
|---|---|---|
| 集群 sudo 口令 | 全树+git 全史（rev-list --all）字面量 | **0 命中** |
| 私钥块（OPENSSH/RSA/EC PRIVATE KEY） | 全树+全史 | **0 命中** |
| 公钥体/authorized_keys/known_hosts | 全树+文件名级 | **0 命中**（无 id_*/authorized_keys/*.pem/*.key 物料文件） |
| 云/网令牌（ghp_/gho_/github_pat_/AKIA/xox/glpat-） | 全树+全史 | 唯一命中=SCAN-REPORT.md 自身的**正则模式文档词**（非凭据值） |
| sk- 长串 | 全树 | 0 命中 |
| GW_API_KEY/GW_KEY 网关秘钥 | 全出现位值位核 | **全空值/运行期 env 读取**；3 处假值（`test-key-not-a-secret`/`leaked`/`real-secret-here`）=gw-verify 判别力 fixture（自检红例），**非真秘钥**，政策保留 |
| wifi 秘钥（psk/wpa/ssid/802-11/wireless） | 全树 | **0 命中** |
| 登录秘钥（passwd/password 赋值广谱） | 全树（排除 fixture/占位/模板假值） | **0 命中** |
| env 形值面 | deploy/env/*.env 全键扫 | 键面规格零凭据值（KEY/TOKEN/SECRET/PASS 类仅功能性参数） |
| ELF 二进制 strings | 全部 7 个 .so（含 NCCL/ncclpin/repack/l2pf/row_store） | **0 命中** |
| sshd 工具件 | tools/ssh-password-login-20261013/ | 纯机制（PasswordAuthentication 切换+侦察 grep），无口令/无 IP/无密钥 |
| **用户名 liux***ya** | 全树 | **44 件命中**（绝对路径 /home/…、systemd `User=`、selfcheck sources.tsv 路径映射、注释）→ **本批掩码** |
| **GitHub 账号名 lux***com** | 全树 | 1 处（GLOSSARY 引用行）→ **本批掩码** |

## 二、处置动作

1. **掩码**：`liux***ya` → `liux***ya`（44 件）、`lux***com` → `lux***com`（1 件）；掩码后全树两类字面量归零。
2. **md5 清单重生成**（受累 7 份，逐行重算，条目数不变）：
   - `deploy/adapter/MANIFEST.md5`（84 条，重验 84/84 成功——sitecustomize.py 无用户名命中，**产线指纹锚 55b1e412 语义不变**）
   - `deploy/kit/MANIFEST.md5`（42 成功+4 缺=oom-gate 让位 selfheal 预期态，沿 B1 批次注记）
   - `tools/packages/{cfgmgmt 52,fabric-net 16,gateway 9,selfdiag 18,selfheal 13}/MANIFEST.md5` 全成功
3. **产线路径清单=脱敏快照声明**：`cfgmgmt/payload/out/env-MANIFEST.md5`、`overlay-MANIFEST.md5`、`boot-chain.md5`、各包 `selfcheck/sources.tsv` 为**产线绝对路径清单**（指向服务器在役位），仓内快照路径已掩码、在仓内不参与校验——到靶机用 `gen-manifests.sh` / `adapter-manifest-regen.sh` / 各 selfcheck 以实际用户重生成。**产线在役件（~/migrate-assets 真源）未动一分**，五包/boot 链在产线上的校验行为零变化。
4. **部署语义注记**：DEPLOY-GUIDE §5 已加注——部署时将 `liux***ya` 替换为实际运行用户（含 systemd `User=` 位）。
5. **git 全史重写**：filter-branch tree-filter 同替换对作用于全部提交；v0.3.1 tag 重指向净化 HEAD 强推；重写后 `refs/original` 删除+reflog 过期+gc prune（旧对象不可达）。

## 三、范围外注记（未处置，另批呈裁）

- **内网 IP**（<registry-host> registry 直链/<fabric-ip>.x/<mgmt-node-ip>.x）：不在本指令五类清单内；registry 直链=镜像获取指令的必要组成（README §二），掩码会破坏部署指引——维持 SCAN-REPORT 政策保留位，如需脱敏另行呈裁。
- gw-verify/selfcheck 三处**假值 fixture**：判别力件（自检红例必须以"看起来像泄漏"的假值触发检测），掩码会使自检失去抓坏能力——保留。
