# GLOSSARY-PUBLIC — 公开术语表（新人随查）

> 目标读者：第一次接触本项目的工程师。每条=一句话通俗定义+「详见」链接，
> 不预设你知道任何内部历史。
>
> 收录原则：只收在公开档里实际出现、且新人第一周大概率会撞上的术语；
> **不收内部战役代号**（窗号、阶段编号、冒烟代号之类一律不收）。
> 若某术语在内部档案中另有旧称，词条内注明「内部档案中或称 X」，
> 方便你回看旧材料时对上号。
>
> 本表不出现任何内网 IP 与主机名；站点专属值按自己环境替换
> （占位符约定见 [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) 卷首二）。
> 三十分钟入门导览见 [GETTING-STARTED.md](GETTING-STARTED.md)。
> 全表共 44 条，按五个主题分组：集群与网络 / 部署面 / 运行面 / 量测面 / 治理面。

---

## 一、集群与网络
- **TP4**
  张量并行 4 路：把模型的权重张量切到四台机器上、每台各算四分之一再经机间通信汇总，对外表现为一台推理服务器。详见：[DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §1
- **UMA 统一内存**
  GB10 芯片的 CPU 与 GPU 共享同一块物理内存的架构；副作用是常规工具（nvidia-smi 显存栏、ps、容器 cgroup）读不到 GPU 侧占用，显示 N/A 不是故障。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §5.2
- **RoCE 环网**
  0.3.1 代历史网络形态：四台机的网卡口两两直连成一个环、中间没有交换机，对向数据靠邻居机的网卡硬件转发。详见：[RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md) §1 · [RING-DEPLOY.md](RING-DEPLOY.md)
- **hairpin**
  环网形态里铺在中间机网卡上的「原地折返」转发规则（tc flower 形式），让没有直连链路的对向两机能通；铺设工具在基础设施兄弟仓。详见：[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P1-1
- **PFC**
  无损以太网的优先级流控机制，是 RoCE 不丢包的底层前提；交换机形态把集群流量放进特定流量类（参考形 TC=106）来配合交换机的 PFC/优先级规划。详见：[RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md) §3
- **in_hw**
  tc 规则「真正下发到网卡硬件」的标志位（in_hw=1）；环网黄金态=每机恰 2 条 in_hw，in_hw=0 说明规则只落在软件里、等于没装。详见：[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P1-1
- **PEER_HCA_MAPS**（`B12X_ROCE_PEER_HCA_MAPS`）
  环网形态逐秩声明「到每个对端机器走哪个网卡口」的属主映射表，必须按本机秩位生成、照抄邻机的值必挂；交换机形态不用此键。详见：[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P1-3 · [RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md) §1
- **交换机 flat 形**
  0.3.2 起现役网络形态（0.3.3/0.3.4 同形）：每机两口上联以太交换机，通信走 C 层 flat/one-shot 运行时（拓扑键选 switched）；与环网形整套互斥、不可混拼。详见：[RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md) §1

## 二、部署面
- **形 / 形三元组**
  一次可启动、可判读的完整配置身份 = env 键面 + serve 参数 + adapter/overlay 面，三面同批对齐才算一形，任何改动必须三面一起动。详见：[README.md](../README.md) §三 · [GETTING-STARTED.md](GETTING-STARTED.md) §1.1
- **env 面**
  三元组第一面：一份几十键的环境变量文件（现役 0.3.4 参考形 61 键；0.3.2 历史形 56 键），把网络拓扑、内存配比、各优化开关全部钉死；改后必须复靴，热改无效。详见：[RUNTIME-PARAMETERS.md](RUNTIME-PARAMETERS.md) · [deploy/README.md](../deploy/README.md)
- **serve 参数（SPEC）**
  三元组第二面：boot 时传给引擎进程的命令行参数谱，现役为八参（调度间隔、排队上限、推理/思考流两个 parser、缓存上报等），由 boot 脚本固定面注入；第九参 `--sleep-on-idle` 空闲降耗 2026-10-30 因上游缺陷退役（九参谱转史档，禁参三门拦截）。详见：[deploy/SPEC6-SERVE-REF.md](../deploy/SPEC6-SERVE-REF.md)
- **adapter**
  三元组第三面的一半：boot 时注入 SGLang 进程的自研优化件集合（0.3.2 装配 87 个运行时件；0.3.4 现役 99 件＝98 个修复固化件+BYPASS 采用新增 1 件，98 件为 2026-10-28 锁档时点值；公开树交付=98 前态面〔0.3.4-MANIFEST.md5 逐件锚、*.py 口径 71 件〕，99=装钩器后在役口径——2026-10-31 代际注记），经 sitecustomize.py 装载缝挂入，与引擎镜像按绑定律同批切换。详见：[deploy/adapter/README.md](../deploy/adapter/README.md)
- **overlay（影子挂载）**
  三元组第三面的另一半：宿主目录里的上游同名源码文件，boot 时逐个挂进容器盖住镜像内版本（挂载计数 fail-closed 断言），从而不改镜像修正上游行为。详见：[DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §5 · [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P2-2
- **engram**
  从模型权重派生的 8 分片预计算工件（约 189G、按四机秩位分发的宿主生成物），boot 前置检查发现缺分片即拒起，属「部署期一次算好换启动确定性」的设计。详见：[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §4
- **ARM_ENV_FILE**
  boot 时的 env 文件指针变量：它指向哪份 env 文件，本靴就是哪一形——判断「现在跑的什么形」先看它，再 md5 实测对表。详见：[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §6/§8
- **靴槽锁**
  保证四机整簇同一时刻只有一个 boot 流程的文件锁（点火必须经锁包装器转起）；点火返回码 2 常见原因是锁被占，而不是启动失败。详见：[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P2-8/P2-9
- **沉降**
  拆掉旧栈到点燃新栈之间强制等待的纪律，等内存与页缓存回落，否则新靴读数被旧栈残留污染。时长两口径：手工部署序 ≥600 秒；工具序（deploy-034 S5）按新制 300 秒；更旧的 1800 秒制已废。详见：[DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §7 · [DEPLOY-STEP-BY-STEP.md](DEPLOY-STEP-BY-STEP.md) §0/§7
- **四查**
  boot 后的四步验收：health 探活 200、四机环境变量与 env 文件逐字一致、横幅直读判在役态、四机面指纹全等；漏跑等于白烧一靴。详见：[DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §7 · [UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §9
- **横幅**
  boot 日志里逐项打印的配置自述（约 29 道门 + 各优化面在役态 + KV 池总量），直读即可判断「起的是不是预期形」，是四查第三查的对象。详见：[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §9
- **池指纹**
  boot 横幅里 KV 池 token 总量（参考形 9.6M）落在期望带内的断言：池对不对是整套内存/缓存配比是否按预期形启动的指纹。详见：[DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §8
- **面指纹**
  adapter 树、overlay 件、镜像 digest 等各面在四机上必须逐件全等；四查第四查的对象，任何一机偏离即形不齐。详见：[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §9

## 三、运行面
- **网关与车道**
  并发代理网关把引擎口转成对外服务口并按端口分车道（文本车道为主，视觉车道已撤除留回退线；鉴权、背压、模型容量补全）；引擎绑定两形态——公开 boot 件缺省 0.0.0.0（四机可达），参考产线形收敛为只绑 head 机回环（此时探活/量具须 ssh 到 head 机打回环）；引擎测试口与网关口是两个口，用途分工明确。详见：[DEPLOY-STEP-BY-STEP.md](DEPLOY-STEP-BY-STEP.md) §4.5 · [CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §0.2
- **cache per-store**
  某些缓存配额键的语义是「每层一份」额度（整机=键值×层数），且对应守卫只告警不阻起——「没报警所以没事」不成立，要自己按层数乘完再对上限。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §5.3
- **radix 前缀缓存**
  引擎按前缀树缓存已算过的提示前缀：同一提示第二次起整段命中、秒回假绿；性能量测必须防它，手发请求靠 nonce。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §3.3
- **nonce**
  手发测试请求时塞进提示词开头的唯一随机串（如时间戳），用来击穿前缀缓存、保证每次都真算；量具已内置，手 curl 不享受。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §3.3
- **warm 门**
  开判读窗前的最后一道门：预热请求后同档三发取中位，达到下限算绿、达到入役线才算可对外（参考形阈值见正档）；红了不开窗。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §2.6 · [DEPLOY-GUIDE.md](DEPLOY-GUIDE.md) §7
- **判读窗**
  一段只许跑一套形态三元组、不许中途切 env/serve/adapter 的量测期；窗内切参=该窗读数作废重跑。详见：[UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §2/§10
- **水位（water_m）**
  跑长上下文量具前对 head 机真实可用内存（MemAvailable）设的门槛线，低于即整档跳过不采信；有效线恒记入输出 JSON 的 water_m 字段，按字段判读不凭印象。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §4.3

## 四、量测面
- **sd_bench**
  本仓自研的 PR/DE 主量具（测量口径逐项对齐社区基准 sparkDash 并经对表审计），一切吞吐读数的正典出处。详见：[tools/bench/README.md](../tools/bench/README.md)
- **PR / DE**
  两大吞吐维度：PR 量长提示灌入多快（prefill，按七档尺寸报 tok/s），DE 量吐字多快（decode，按并发档报单流与聚合）；两者都只与同口径读数比。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §2.1-§2.2
- **GSM8K / needle / qeval**
  三件质量门：GSM8K 数学题准确率（发布口径 500 题）、needle 600k 长上下文找针（三次全中才算过）、qeval 75 题改配置前后对照（看劣化数不是绝对分）。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §2.3-§2.5
- **filler 三档**
  构造长提示的三种填充方式（repeated 重复单元 / random 随机词汤 / real 真实文本），三档读数互不可比，发布档主列固定用 repeated 口径。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §3.4
- **agg / per**
  DE 的两个读数口径：per=单条流自己的吐字速度，agg=整批聚合吞吐；单流读数还随内容类型大幅漂移，报数必须带类型与并发。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §1.1/§3.5/§3.7
- **冷态税**
  批次里最先跑的那一发被系统性砸低的效应（首靴未热、缓存未就位），实例中能低至正常带一半以下；对策=每档至少三次独立调用取中位。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §3.1-§3.2
- **锚 / 锚表**
  判读用的参考读数列（锚）及其汇总表：对表前先核对锚属于哪一代引擎、哪个网络形态、哪种量具口径，锚与读数不同口径不许比。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §2 · [README.md](../README.md) §一
- **臂 / A-B 窗**
  臂=在役形态不动、另起一套独立配置并行验证的安排（如文本臂/视觉臂）；A-B 窗=把差异缩到最小、在相邻判读窗间对照两形读数的实验安排，A/B 必须在新代引擎上做。详见：[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P4-2 · [CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §3.8
- **三不比**
  读数互比的三条禁区：跨量具不比（算式不同）、跨填充不比（三档口径差一成起）、跨代际不比（旧代结论换代即失效），外加跨网络形态不比。详见：[CALIBER-AND-MEASUREMENT.md](CALIBER-AND-MEASUREMENT.md) §6.2

## 五、治理面
- **代际**
  本仓同时保留多代并存的档案（0.3.1、0.3.2 与 0.3.4，环网与交换机），同一键不同代取值不同；对表、抄配置、看旧报告前必须先认它的代际。详见：[PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) 卷首一
- **fail-closed**
  「证据不足就拒绝放行」的校验哲学：校验不了、断言不齐、缺件缺证一律判红拒起，而不是默认放行——与「没报警=没事」的直觉相反。详见：[deploy/SPEC6-SERVE-REF.md](../deploy/SPEC6-SERVE-REF.md) · [RING-0.3.2-COMPAT.md](RING-0.3.2-COMPAT.md)
- **判负不进形**
  试过并被判负的改动只留档、不进现役形态（例：曾判负的 serve 参数变体永不进谱）；判负记录的价值是防止下一代重新踩同一坑。详见：[deploy/SPEC6-SERVE-REF.md](../deploy/SPEC6-SERVE-REF.md) 头注
- **永禁键**
  判负且被明确禁止再启用的键或参数值，重新出现在配置里会被 lint 门拒起，属于判负不进形的加重档。详见：[CHANGELOG.md](../CHANGELOG.md) · [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P2-6
- **兄弟仓**
  同作者的基础设施配套仓（mesh 硬件转发层、环网织网工具、NCCL ring-only 优化包等）：交付包里 grep 不到的装载件常在那里，缺件先读交付仓 README 的基础设施段再下结论。详见：[README.md](../README.md) §四 · [PITFALLS-AND-FAQ.md](PITFALLS-AND-FAQ.md) P1-1
- **交付快照**
  离线发布网盘包里的整仓快照 tar（含 .git 历史），配合逐件校验清单用于断网环境整仓复原；大文件不走代码托管平台的发布资产，统一走网盘通道。详见：[README.md](../README.md) §二
- **基线回滚点**
  把现役镜像固化成 registry 常驻 tag 加离线 tar 加恢复脚本的回滚锚：任何时候都可以一键回到这个已知良好的整栈状态。详见：[CHANGELOG.md](../CHANGELOG.md) 头部 · [UPGRADE-0.3.2.md](../UPGRADE-0.3.2.md) §11

---

> 维护约定：新术语进入公开档时同步补一条；每条只留一句话定义，超出一句的内容
> 属于正档，本表只负责指路。新词条入表前自查两点：是否出现在公开档里、
> 是否只是内部战役代号——后者不收。


