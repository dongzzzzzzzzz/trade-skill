# 案例与结果字段

## 输入案例

`cases/` 中的 Markdown 是给 Skill 的可见输入，至少要能定位：

- `decision_date`：盘后候选日。
- `confirmation_date`：次日竞价日。
- D 日环境与候选顺序。
- D+1 截至 09:25 的竞价状态。
- 每只候选的竞价动作和失效条件。

## 结果记录

`results/2026-07-outcomes.csv` 每行代表一个“候选在一个案例中的可执行结果”，而不是只记录第一名。

字段含义：

| 字段 | 含义 |
|---|---|
| decision_date | D 日日期 |
| confirmation_date | D+1 日期 |
| rank | D 日冻结排序 |
| symbol | 标的代码 |
| auction_action | 案例中记录的竞价动作 |
| executable | 你当时是否会实际买入，填 `yes/no/unknown` |
| selected_rank | 如果实际递补，最终买入队列位置 |
| entry_time | 实际或模拟买入时间 |
| entry_price | 实际或模拟买入价 |
| exit_time | 卖出时间 |
| exit_price | 卖出价 |
| return_pct | 实际收益率 |
| max_adverse_pct | 持仓期间最大不利波动 |
| user_action | 你的真实动作：`buy/wait/skip/sell` |
| error_type | `environment/emotion/node/auction/rank/fallback/timing/fit/none` |
| lesson | 对下一轮 Skill 的一句可执行教训 |

`unknown` 必须保留，不能为了让评测跑起来而猜测你的真实动作。
