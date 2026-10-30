# contract_probe_selftest — EQ-04 契约量具离线自测 fixture 台账

`tools/contract_probe.py --selftest` 的离线数据面（零网络、不打真请求）。
台账=`manifest.json`（逐条 file/kind/expect/expect_keywords），fixture 正文为两大类：

- **正例**（expect=PASS）：结构化 `tool_calls` 完整、流式分片可拼装回完整调用、
  检索题 finish=stop 且正文非空且答中魔码——量具须判过；
- **负例**（expect=FAIL）：外部手册部署篇 §41 的 P0 形——工具调用标记漏成 content
  明文（DeepSeek 官方边界符族，流式负例特意把标记**跨分片切开**以证明「先拼装后扫描」
  能力）、arguments 非合法 JSON、finish=length、正文为空——量具须判负且判读词命中
  （expect_keywords 逐词对 findings 文本做子串断言）。

## 维护律

1. 新增/改 fixture 必须同步登记 `manifest.json`；selftest E 段做盘上文件↔台账
   一一对应校验，孤儿文件或空挂条目即 SELFCHECK FAIL（fail-closed）。
2. fixture 是**判读逻辑的规约样本**，不是抓包存档：改的是量具判读线时才动这里，
   并保持每类至少 1 正 1 负。
3. 站点特有明文标记不要塞进 fixture——运行面用 `--extra-marker` 传入，判读面
   检测表随 `--json-out` 落盘供审计。
