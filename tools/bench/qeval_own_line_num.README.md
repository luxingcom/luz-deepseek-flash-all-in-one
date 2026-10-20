# qeval_own_line_num.patch — qeval extract_final_number 独占纯数字行优先

工单：qeval 答案数字提取（`extract_final_number`）旧版语义=「尾部 answer 标记面取
末数」，会把尾随例证数字当答案——如模型答 `**96**` 后跟说明行 `(computed as
8 * 12)` 时旧版取 12 而非 96。本补丁把语义改为「题目所求数字优先」：文本中存在
**独占一行的纯数字**（markdown 修饰符容许：`**96**`/`> 96`/`` `96` `` 等）时取
最后一个独占行数字；不存在时行为与旧版完全一致（答案标记面取末数）。

## 应用

```
patch -p1 -d <qeval 工具仓根> < qeval_own_line_num.patch
```
（对 `bench/qeval/qeval_tasks.py` 一处改动，+11/−1；已验证对未修基线干净应用。）

## 改动内容（1 处）

- 新增 `_OWN_LINE_NUM` 正则（多行模式，行首尾容许空白与 markdown 修饰符）；
  `extract_final_number` 先查独占行数字（取最后一个，千分位逗号剥除），无命中再
  落回旧答案标记面逻辑——纯增量分支，无独占行时零行为差。

## 判别与自检

- 微核判别：旧版答 `**96**\n(computed as 8 * 12)` → **12**（错）；新版 → **96**。
- `qeval.py --selftest` 15/15 全绿（含新增用例）；答案标记面（无独占行）行为不变。

## 出处与致谢

- 同式实现先行：knapcio v2.3（`_OWN_LINE_NUM` 独占行优先，6 行同式）。
- 引入后建议重跑一次基线（数字提取语义变化会影响含例证数字样本的读数）。
