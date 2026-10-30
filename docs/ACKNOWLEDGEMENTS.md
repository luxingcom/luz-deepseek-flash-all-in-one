# 致谢（ACKNOWLEDGMENTS）

> **件性质**：GitHub 交付页致谢正文名（D124-⑤「提供完整性能报告和致谢内容」落位；主会话定稿）。
> 每项一句话贡献+链接位；详细血统（采纳在役/判负留库/参照对比/政策依据四态、111 条逐条底册）
> 见 [`docs/release/ACKNOWLEDGEMENTS-DRAFT-20261013.md`](docs/release/ACKNOWLEDGEMENTS-DRAFT-20261013.md)。
> 措辞原则：无论好坏、无论是否用到，凡被本战役参照过即如实致谢；判负/不吸收项以「负结论入档」致谢。

## 致谢名单

| # | 项目 | 一句话贡献 | 链接位 |
|---|---|---|---|
| 1 | **knapcio**（同硬件同模型的开源调优产线） | **prefill_bypass 血统与 DE 优化参照**：其 v2.4 `DSV41_PREFILL_BYPASS=256` 小请求准入实现是我方 0.3.4 BYPASS 采用面（2048，首键 TTFT 74.191s→1.971s）的血统源；其 v2.5 measured-switch 方法论与 not-adopted 清单、Engram NVMe keepalive 机理、c16 逐档单 run 样本纪律为我方 DE 回归调查与 DEOPT 调优序列的直接参照（只借机理不借数字） | https://github.com/knapcio/DeepSeek-V4.1-Flash-4x-DGX-Spark-TP4 |
| 2 | **Soulmate-Halo/heterogeneous-gpu-pd-lab**（异构 PD 分离实验室） | **异构 PD 调度参照**：其 PD 前门代理控制面模式（~490 行 room 表+块表查询+prompt 摘要闸）与 DSV4.1-Flash KV 字节几何第三方常数表为对照蓝本；其「配置留空→静默退化不报错」教训是我方 RDMA 口计数差分制式（I3 采纳入正典）的直接依据（其顶层无 LICENSE——只学模式不抄代码） | https://github.com/Soulmate-Halo/heterogeneous-gpu-pd-lab |
| 3 | **MiaAI-Lab/sparkDash** | **性能口径定义 v1.8.6**：本仓一切 PR/DE 阶梯读数的量具口径（PrefillBench/DecodeBench/LlmStreaming/llmPrompts 四定义源件，md5 在档）即对齐其 v1.8.6 归档源码；九项对表全 PASS 判例在档（`docs/verdicts/SPARKDASH-ALIGN-20261006.md`） | https://github.com/MiaAI-Lab/sparkDash |
| 4 | **sglang 上游**（sgl-project/sglang） | **引擎基座**：本战役全部栈基于上游 main `79cafece` 镜像线，0.3.x 各代优化均以其源码为核证基座；其 PR/issue 谱系（块稀疏打分、长 prefill 稳定性、SM12x 缺口清单等）为持续的参照与回馈渠道 | https://github.com/sgl-project/sglang |
| 5 | **DeepSeek 模型与权重** | **模型本体与规范基准**：DeepSeek-V4.1-Flash 官方检查点（48 shards safetensors）为生产模型本体，其技术报告（52 页）是我方部署参数对账的规范基准——凡与论文冲突处以论文为准 | https://github.com/deepseek-ai （DeepSeek-V4.1-Flash 模型页位） |
| 6 | **判例制式**（本战役方法学） | **方法学引用**：本战役一切性能/质量判读均以在档判例为法源——单变量 A/B、量具冻结、冻结阈值不降门、对正典锚 IN-BAND ±3% 判级、跨 era 只报告不判红、判负留库禁重开；判例库（`docs/verdicts/`）与决策台账（D 系号）使本页每个数值可溯源 | [`docs/verdicts/`](docs/verdicts/) |

## 附：其他依赖与基础设施（一句话）

- **flashinfer 0.7.2**：引擎 KV/attention 内核正典依赖——v41 面直调其原生分支即快带来源（其 SM120 include 缺件曾致我方 repack 桥慢带，根因与防复发在档）。
- **社区同行与田野情报**：MiaAI-Lab 主仓 issues（量具膨胀披露、环网恢复笔记、TP 拓扑实测）、sparkring、tonyd2wild、dnhkng 等船队的实测与负结论——完整名单见上方底册。
- **基础设施**：内部集群（4×DGX Spark GB10）、内部 registry 与内部网关节点——多级镜像回退与双 rail 对称承载的承载面；内网细节按掩码律泛化（本页零密钥零内网地址）。

—— GitHub 页面员（D124 GitHub 页面相）/ 2026-10-29 / 深版底册=docs/release/ACKNOWLEDGEMENTS-DRAFT-20261013.md（111 条，四态口径）。
