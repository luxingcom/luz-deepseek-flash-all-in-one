# tools/bypass/ — BYPASS（prefill_bypass）采用面

> 回答一个问题：**这个目录里的件是什么、哪些是现役工具、怎么和发布的镜像/overlay/env 配套用。**
> 世代对齐总表与完整升级流程见 [docs/IMAGE-UPGRADE-GUIDE.md](../../docs/IMAGE-UPGRADE-GUIDE.md)。

## 一、目录内容与身份

| 件 | 身份 | 现役可用？ |
|---|---|---|
| `prefill_bypass.py` | **正典适配件**（md5 `c4875258…`）：in-flight chunk 旁的有界新 prefill 准入适配。knapcio b9ea6dd 血统 173 行 + 本树 9 个方法源哈希重钉。**勿改一字**——adapter 面指纹按此件锚定 | ✅（作为正典件被引用） |
| `install-prefill-bypass.sh` | **装钩器（现役工具）**：把上件装入 adapter 目录并给 `sitecustomize.py` 挂 env 门控钩（前态 `45ca6e3e` → 后态 `dd69c59a`，md5 硬断言；幂等可重跑） | ✅ |
| `bypass-armed-gate.sh` | **武装核验门（现役工具）**：点火后断言各参与机 `armed` 行 ≥1 ∧ `refusing to arm` =0；参数化（限额/扫描数/容器名/worker 主机均可覆盖） | ✅ |
| `stage-one-host-bypb.sh` | **历史存档**：2026-10-28 BYPASS-B 采用窗的一次性 staging 原件（含脱敏占位符 `__ASSETS_ROOT__` 等，**不可直接运行**）。现役操作一律用上面的装钩器 | ❌（存档） |
| `SOURCE-MD5.txt` | 全目录血统台账：每件的出处、内部窗编号与沿革注记（含正典件与现役工具的溯源行）；台账本身非可运行件 | ❌（台账） |

## 二、适配契约（和镜像/overlay/env 的配对面）

- **env 键**：`DSV41_PREFILL_BYPASS=2048`（61 键 env 的第 60 键；不设或非正整数=不武装、
  零突变）；`DSV41_PREFILL_BYPASS_SCAN` 缺省 32（每轮在飞 chunk 旁最多扫的候选数）。
- **adapter 面**：`sitecustomize.py` 挂钩后态 `dd69c59a`（装载缝）+ 本目录正典件
  `c4875258` 入 adapter 目录（面件数 98→99）。装钩器一键完成并自验。装钩基底=
  `deploy/adapter` **98 前态正典面**（公开树交付形；逐件锚=`deploy/adapter/0.3.4-MANIFEST.md5`：
  磁盘供给 **91 件**=71 \*.py+20 非 py、sitecustomize 前态=`45ca6e3e`；「98 件」为锁档
  在役全文件口径，与仓面 91 之差=包外宿主件另计，两口径对账=deploy/adapter/README.md
  计数谱系节），c4875258 入面后**磁盘 91→92 件**（锁档在役全文件口径 98→99）。
  〔2026-10-31 复核批措辞修正：原句把 98/99 锁档全文件口径直安在公开树目录上，与
  0.3.4-MANIFEST.md5 实记 91 件相左，现两口径并记。〕
- **overlay 面**：适配件内 EXPECTED 钉的是 scheduler / PrefillAdder **九个方法源**的
  sha256（dedent 后 inspect 源），不是整文件 md5——所以 overlay 的 `scheduler.py`
  从锁档形 `3db3275e` 演进到现役 `4a7822a6` 后**仍能武装**（演进未动被钉的方法源）。
  将来任何一方法源变动 → 适配**拒绝武装**（`refusing to arm` + `source drift` 日志），
  这是 fail-closed 设计，不是故障。
- **镜像**：armed 行是「sitecustomize 钩触发 + 九哈希全中 + 五处补丁锚逐个 count==1 + exec 重编译毕」
  的综合直证，跨 0.3.4 系镜像（`x6bake/final` 80e4c957、`0.3.4re` bd225d3d）在上述
  overlay/adapter/env 面下均成立。

## 三、现役操作（三步）

```bash
# 1) 装钩（每台参与机各跑一次；幂等，已装面直接 OK）
bash tools/bypass/install-prefill-bypass.sh
#    （缺省 ADAPTER_DIR=$HOME/migrate-assets/dsv41/adapter，可用环境变量覆盖）

# 2) 点火时 env 带 DSV41_PREFILL_BYPASS=2048（61 键 env 已含；ARM_ENV_FILE=点火时注入容器的
#    env 文件路径，机制见 [DEPLOY-GUIDE](../../docs/DEPLOY-GUIDE.md)，单测可用它换面）

# 3) 点火后核武装（head 机执行；四机 TP4 传 -H）
bash tools/bypass/bypass-armed-gate.sh -H "worker02 worker03 worker04"
#    期望：每机 armed 行计数 ≥1、refusing-to-arm =0，末行 PASS
```

## 四、排查（armed 不出现 / refusing 非 0）

1. `docker logs <容器> 2>&1 | grep DSV41_PREFILL_BYPASS`——有 `refusing to arm` 行的，
   行内原因即答案：`source drift`=overlay 面被换过（先 `cd deploy/overlay/o12c1-prod &&
   md5sum -c ../../prod/overlay-md5.txt` 对表——清单内是裸文件名，须先 cd 进 overlay 目录）；`anchor drift`=方法源结构变（属适配面换代，勿硬绕）。
2. 一条 armed 行都没有、也没有 refusing——多半是钩没装（`sitecustomize` 仍为前态）或 env
   键未带上：重跑装钩器（幂等），再核 env。
3. 两台以上机器同时 refusing 而单机正常——先核四机 overlay/adapter 面是否一致
   （逐机 `md5sum` 对表），勿只看单机。
