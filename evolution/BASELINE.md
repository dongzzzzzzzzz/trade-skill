# v0 Proxy Baseline

本文件记录第一轮 Darwin 之前的研究基线，不代表用户真实成交。

## 代理执行口径

- 只把案例竞价动作中明确出现“可做”的候选视为可执行。
- 每个交易日按冻结候选顺序选第一只可执行候选。
- 按次日开盘价模拟买入。
- 按次日收盘价模拟卖出。
- `max_adverse_pct` 使用次日最低价相对开盘价的跌幅。
- 没有可执行候选的日期记为空仓。

## 为什么先用代理口径

7 月案例目前没有完整的真实成交记录。这个基线的用途是让 Darwin 有一个可复现的 Champion 对照，不把研究代理误称为用户收益。

真实结果补齐后，应以 `results/2026-07-outcomes.csv` 覆盖代理结果，并重新进行 Champion / Challenger 对照。

## 运行

```bash
python scripts/build_proxy_baseline.py
```

输出：

- `results/2026-07-market-outcomes.csv`：85 个候选的次日 OHLC 与代理结果。
- `results/2026-07-proxy-trades.csv`：按当前规则真正会选中的每日代理交易。
