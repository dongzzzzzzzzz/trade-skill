# trade-skill
小宝 1105 交易 Skill 的个人进化仓库。

这个仓库的目标不是把 `SKILL.md` 写得更像一篇复盘，而是让它在固定的信息边界内，逐步提高：

`盘后候选 -> 次日竞价确认 -> 可执行排序 -> 实际结果`

当前仓库包含：

- `SKILL.md`：当前 Champion 初始版本。
- `cases/2026-07/`：2026 年 7 月逐日回放案例。每个案例只使用 D 日盘后信息和 D+1 09:25 前竞价信息。
- `evolution/`：Darwin 的进化协议、晋级规则和人工确认边界。
- `results/`：把案例转成真实执行结果前需要补充的记录。
- `test-prompts.json`：给 Darwin 使用的交易场景测试集。
- `scripts/`：案例索引和结果模板生成工具。

## 当前状态

7 月案例已经完成“盘后冻结候选 + 次日竞价验货”，但还没有你的真实成交、买入价、卖出价和持有结果。因此当前只能作为 `v0` 规则基线，不能据此宣称收益提升，也不能直接让 Darwin 以默认 9 维 Skill 分数晋级交易规则。

下一步是补齐 `results/2026-07-outcomes.csv`，再开始 Champion / Challenger 对照进化。

## 使用 Darwin

在支持 Darwin Skill 的 Agent 中执行：

```text
请进化本仓库的 SKILL.md。
目标是提高盘后候选排序、次日竞价确认和最终可执行买入的结果，不是提高通用文字评分。
先读取 evolution/EVOLUTION_PROTOCOL.md、evolution/CASE_SCHEMA.md、test-prompts.json 和 results/。
每轮只修改一个核心交易假设，使用同一批案例比较 Champion 与 Challenger。
没有结果数据的案例只能用于规则一致性检查，不能作为收益晋级证据。
```
