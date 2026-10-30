# tools/upstream/dsp45525-plainroute/ — DSPARK spec×plain 贪心分叉的 host 侧路由规避件

> 法源：sgl-project/sglang [issue #45525](https://github.com/sgl-project/sglang/issues/45525)
> （[Bug] DeepSeek-V4-Flash: speculative and ordinary decoding produce different
> greedy outputs；2026-10-21 提交，open、零评论、无修复）。同 checkpoint、同前缀、
> T=0 下 DSPARK verify 与普通 decode 的目标 logits 不同、贪心 token 分叉（近并列
> top-2 约 0.25-0.5 logit 差翻转）；且**同一路径重复请求结果也会翻转**——责任
> 内核未定位。报告者环境=H20×8/TP4/dsv4/marlin/fp8 KV/v0.5.22，与 我栈
> DGX Spark/flashinfer_mxfp4 不同型，但缺陷族（speculative×DeepSeek V4 贪心
> 分叉）与我栈 spec 算法同为 DSPARK——按同族预防面落地。
>
> 规避语义（host 侧，零镜像改动）：**对确定性敏感的评测/对拍流量路由到无 DSPARK
> 的 plain decode 服务（同 checkpoint 双服务，报告者即如此对照取证）；常规业务
> 面（8899 生产 spec 口）不动**。因普通路径亦非确定（issue 同路径重复翻转），
> 本规避消除的是「spec×plain 车道差」这一变量，**不追 spec 开关当唯一解释**、
> 不作确定性承诺——跨靴底噪带判读仍归 `tools/biteq_band.py` 带语义（贪心硬等/
> top_logprob 带内）。
>
> 落点双面同件（md5 一致互证，`SOURCE-MD5.txt` 为锚）：战役仓
> `luz030-opt-campaign/tools/upstream/dsp45525-plainroute/` 与公开仓
> `luz-034re/tools/upstream/dsp45525-plainroute/`；改件须双面同批同改并重算
> SOURCE-MD5（`tools/upstream/nvfp4-kv/` 同制）。登记面：战役仓
> `docs/TOOL-ANCHORS.md`；公开仓 `docs/KNOWN-ISSUES.md` §5。

## 件与用法

| 件 | 职责 | 用法 | 出口 |
|---|---|---|---|
| `plain-face-45525.env` | env/serve 参数面：plain 服务 boot 调用面 4 键（CTN_PREFIX/API_PORT/SPEC/DSV45525_PLAIN_BASE） | 专门窗 `source` 后走激活制式；零执行零点火 | — |
| `plainroute_guard_45525.sh` | 守卫：G1 参数面 / G2 plain 活体面（状态感知） / G3 生产 spec 旁核 / G4 路由武装执法 | `bash plainroute_guard_45525.sh`；`--selfcheck` | 0/1/2 |
| `plainroute_lint_45525.sh` | lint：L1 确定性敏感件纪律在位 / L2 双面同件+SOURCE-MD5 对表 / L3 登记在册 | `bash plainroute_lint_45525.sh`；`--selfcheck` | 0/1/2 |

## 规避原理（为什么是路由，不是开关）

1. boot 链已内建 plain 开关，**零镜像改动即可双服务**：`r3-boot-arm.sh:576`
   `[[ "$SPEC" == "1" ]] && SERVER_ARGS+=(--speculative-algorithm DSPARK) || …`
   ——生产点火恒 `SPEC=1`（`deploy-034.sh:107-109`），plain 服务=同链 `SPEC=0`；
   `migrate-assets/dsv41/boot.py` 世系等价键为 `SPEC_ALGO=off`（:316/:341）。
2. `PROD_SPEC_EXTRA_ARGS`（prod-profile.env:10）实测不含任何 `--speculative*`
   参——plain 服务可整套沿用同参，与生产**仅差 spec 一面**，符合 issue 报告者
   「同 checkpoint 对照」的取证语义。
3. 不开 `SGLANG_ENABLE_DETERMINISTIC_INFERENCE`：RE-CERT-CARD-4 §八全形态禁键
   （`r3-gate-env-lint.sh` ①面机器拒起）。issue 已证同路径重复亦翻转——确定性
   开关治不了非确定底噪，反而引入新变量。
4. 口面：8899=引擎生产 spec 口（`deploy-034.sh:109` API_PORT）/ 8898=测试线死口
   / 8001=网关（upstream→8899）/ 8888=boot.py 缺省。**plain 口=8897**（2026-10-30
   建件窗全树 grep 零占用亲证）。容器前缀 `r3plain` 独立于 `r3prod/r3boot`——
   deploy-034 S1 在役拒起门只数 `^r3(prod|boot)-`，**双服务并存即设计**（plain
   旁路不触生产栈、不受拒起门拦）。

## 激活制式（专门窗内，非本件职权——本件零点火）

1. **开窗前**：`bash tools/upstream/dsp45525-plainroute/plainroute_guard_45525.sh`
   全绿（G1 四判据全中=参数面就绪）。
2. **起 plain 服务**（窗职权）：`source tools/upstream/dsp45525-plainroute/plain-face-45525.env`
   后按生产同制调用既有 boot 链（`CTN_PREFIX=$CTN_PREFIX API_PORT=$API_PORT
   SPEC=$SPEC ARM_ENV_FILE=<正典 env 原件不动>` 走 boot-with-slotlock 形；正典
   env=CBX1A-CERTM-spec1.env 的 61 键对 plain 同样适用——draft/spec 专属键在无
   speculative 时不生效，保证「仅差 spec 一面」）。资源注意：双服务并存=两份
   权重/KV 面显存占用，窗内以四机余量为前提，不足则按停机设计态换靴开 plain。
3. **复跑守卫**：G2 面=「plain head launch 面零 --speculative + :8897 /health=200」
   必绿（红=plain 不 plain，禁发流量）；G3 面=生产 head 仍带 DSPARK（零侵入直证）。
4. **评测/对拍窗武装路由**：`DSV45525_DETERMINISM_SENSITIVE=1` +
   `DSV45525_PLAIN_BASE=http://127.0.0.1:8897`，流量侧
   `--url "$DSV45525_PLAIN_BASE"`（ds_gate 形）或
   `--base-url "$DSV45525_PLAIN_BASE/v1"`（de_c48 形工具）。G4 面 fail-closed：
   未设锚/锚指 8899/8001/8888/plain 不在役=红，确定性敏感流量不得开跑。
5. **窗毕**：拆 plain 栈（`CTN_PREFIX=r3plain` 对应 stop 链，窗职权）；守卫复跑
   回「G2=N/A」态；台账照 misfire/窗档制式留痕。

## 当前态（2026-10-30 建件窗只读亲核）

- 生产 spec 面在役语义不变：`deploy-034.sh:107-109` 点火恒 `SPEC=1`（8899=
  DSPARK spec 口），本规避**不改动任何生产面**（canonical env md5 仍=gates-034
  BL11 钉值 `4370aab9…`，守卫 G1①互证）。
- plain 服务**未部署**（r3plain-* 零容器）——规避处于「参数面+执法面就绪、
  活体面 N/A」态；确定性敏感流量的现行纪律仍为既有测试线制（`ds_gate.py:82-84`
  8898 缺省+8899 硬拒、`t62c_anchor_gsm8k.sh:23` 红线行），lint L1 面执法防漂移。
- 性能面件（`de_c48_bench.py` 直连 8899）**不入本规避约束**：吞吐/时延读数非
  确定性敏感，spec 口正典位不变。

## 退役条款

- 上游定位责任内核并发布修复（issue 转 closed/修复 release）后：评估直接升级
  镜像窗吸收补丁；本 kit 的 G2/G4 活体面转 INFO 观察位，L1/L2/L3 静态面保留
  （纪律与双面律独立于本缺陷存续）。
- 若后续在役实测发现我栈 plain 路径贪心亦跨请求翻转（issue 同路径观察），对照
  读数按 biteq 带语义归档，**不得**据此单方面追改 boot/镜像——呈报主会话随
  issue 态定补丁窗。
