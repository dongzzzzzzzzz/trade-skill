# Experiment 007: 盘后先过滤孤立异动

## 假设

当前 Champion 的盘后候选排序本质上是：

```text
所有涨停股 -> 板位 -> 封单额 -> 封板时间
```

这会把孤立公告、单票异动和没有梯队的题材，与真正有发酵的主线放在同一个池子里。Challenger 只做一个改动：

- 盘后只保留当日显示题材至少出现 2 只涨停股的候选；
- 在剩余候选中继续使用 Champion 原来的板位、封单额、封板时间排序；
- 竞价确认和用户的顺序递补规则全部不变。

这不是“买第二名”，而是改变盘后候选池的定义：先要求题材有梯队，再谈个股前排。

## 结果

使用同一版案例生成器，分别生成 Champion 与 `mainline_breadth` Challenger，再使用相同的竞价、递补和开盘到收盘代理口径：

| 数据集 | Champion | Challenger | Challenger 交易数 |
|---|---:|---:|---:|
| 2026-07 训练集 | `+0.744%` | `-3.963%` | 8 |
| 2026-08 时间外验证集 | `-36.524%` | `-26.472%` | 15 |

Challenger 在 8 月少亏约 `10.052` 个百分点，但在 7 月训练集明显变差，不能晋级。它把“有梯队”误当成了必要条件，过滤掉了部分单点破局或独立核心机会。

## 归档状态

该 Challenger 已经拒绝，不再作为案例生成器的生产 picker。重跑材料保留在实验目录中，用于复盘“硬过滤会删除有效破局票”的失败路径。

已完成的重跑材料：

- `evolution/experiments/007-cases/champion-2026-07/`
- `evolution/experiments/007-cases/champion-2026-08/`
- `evolution/experiments/007-cases/2026-07/`
- `evolution/experiments/007-cases/2026-08/`
- `results/007-champion-2026-07-policy-comparison.csv`
- `results/007-champion-2026-08-policy-comparison.csv`
- `results/007-2026-07-policy-comparison.csv`
- `results/007-2026-08-policy-comparison.csv`

结论：拒绝 Challenger，不修改主 `SKILL.md`。下一轮应测试“主线有梯队优先，但允许满足明确破局条件的孤立核心进入候选”，而不是继续使用二元硬过滤。
