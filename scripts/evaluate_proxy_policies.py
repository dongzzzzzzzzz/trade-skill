#!/usr/bin/env python3
"""Compare deterministic candidate-action policies on the same July cases."""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "2026-07-market-outcomes.csv"
OUT = ROOT / "results" / "2026-07-policy-comparison.csv"

rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))
dates = sorted({row["decision_date"] for row in rows})

policies = {
    "champion_user_execution": lambda row: "可做" in row["auction_action"] and row["locked_auction"] != "yes",
    "challenger_positive_open_fallback": lambda row: (
        "可做" in row["auction_action"]
        and row["locked_auction"] != "yes"
        and row["auction_open_change"]
        and float(row["auction_open_change"]) >= 0.5
    ),
    "challenger_promote_observe": lambda row: ("可做" in row["auction_action"] or "观察，不抢一致" in row["auction_action"]) and row["locked_auction"] != "yes",
    "challenger_promote_all_observe": lambda row: ("可做" in row["auction_action"] or "观察" in row["auction_action"]) and row["locked_auction"] != "yes",
}

result = []
for name, eligible in policies.items():
    chosen = []
    for decision_date in dates:
        day_rows = [row for row in rows if row["decision_date"] == decision_date]
        candidates = [row for row in day_rows if eligible(row) and row["next_open"]]
        if candidates:
            chosen.append(candidates[0])
    returns = [float(row["proxy_return_pct"]) for row in chosen]
    maes = [float(row["proxy_mae_pct"]) for row in chosen]
    result.append({
        "policy": name,
        "trades": len(chosen),
        "sum_return_pct": round(sum(returns), 6),
        "mean_return_pct": round(statistics.mean(returns), 6) if returns else "",
        "median_return_pct": round(statistics.median(returns), 6) if returns else "",
        "win_count": sum(value > 0 for value in returns),
        "loss_count": sum(value < 0 for value in returns),
        "worst_return_pct": round(min(returns), 6) if returns else "",
        "mean_mae_pct": round(statistics.mean(maes), 6) if maes else "",
        "selected_dates": ";".join(row["decision_date"] for row in chosen),
        "selected_symbols": ";".join(row["symbol"] for row in chosen),
    })

fields = list(result[0])
with OUT.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(result)

for row in result:
    print(row)
print(f"wrote {OUT}")
