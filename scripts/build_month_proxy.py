#!/usr/bin/env python3
"""Build a no-lookahead research baseline from the frozen July cases.

This is explicitly a proxy, not a statement of the user's real fills:
only rows whose case action contains "可做" are eligible; the first eligible
candidate is bought at the next day's open and sold at that day's close.
"""

from __future__ import annotations

import csv
import re
import argparse
from datetime import date
from pathlib import Path

from eltdx import TdxClient

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--month", required=True, help="YYYY-MM")
parser.add_argument("--case-dir", type=Path, help="Alternative frozen case directory")
parser.add_argument("--output-stem", help="Output prefix under results/")
args = parser.parse_args()
MONTH = args.month
CASE_DIR = args.case_dir or ROOT / "cases" / MONTH
OUTPUT_STEM = args.output_stem or MONTH
OUT_ALL = ROOT / "results" / f"{OUTPUT_STEM}-market-outcomes.csv"
OUT_TRADES = ROOT / "results" / f"{OUTPUT_STEM}-proxy-trades.csv"


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return (a / b - 1.0) * 100.0


def f(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def pct_cell(value: str) -> float | None:
    return f(value.replace("%", "").strip()) if value else None


def locked_from_auction(symbol: str, open_change: float | None, drift: float | None) -> bool:
    """Approximate one-word/locked auction from only pre-open fields."""
    if open_change is None or drift is None or abs(drift) > 0.05:
        return False
    # ChiNext/STAR stocks have a 20% daily limit; ordinary stocks have 10%.
    # Keep 5% for ST-style names when the case name makes that explicit.
    limits = (20.0,) if symbol.startswith(("sz30", "sh68")) else (10.0,)
    return any(abs(open_change - limit) <= 0.15 for limit in limits)


def rows_in_table(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        rows.append([x.strip() for x in line.strip().strip("|").split("|")])
    return rows[1:]


def section(text: str, start: str, end: str) -> str:
    match = re.search(re.escape(start) + r".*?\n\n(.*?)\n" + re.escape(end), text, re.S)
    return match.group(1) if match else ""


def load_case(path: Path) -> list[dict[str, object]]:
    text = path.read_text(encoding="utf-8")
    dates = re.search(r"(?:盘后冻结日 D|盘后候选日)：([0-9-]+).*?(?:确认日 D\+1|竞价确认日)：([0-9-]+)", text, re.S)
    if not dates:
        return []
    decision_date, confirmation_date = dates.groups()
    candidate_block = section(text, "## 3. 冻结候选（D 日盘后）", "## 4. D+1 竞价确认") or section(text, "## 二、冻结的盘后候选（不可用 D+1 数据改写）", "## 三、D+1 09:25 前竞价验货")
    auction_block = section(text, "## 4. D+1 竞价确认（截至 09:25）", "## 5. 当日结论与失效条件") or section(text, "## 三、D+1 09:25 前竞价验货", "## 四、结论与失效条件")
    candidates = rows_in_table(candidate_block)
    auction = rows_in_table(auction_block)
    auction_by_symbol = {
        row[0]: {
            "action": row[-1],
            "auction_open_change": pct_cell(row[4]) if len(row) > 4 else None,
            "auction_drift": pct_cell(row[6]) if len(row) > 6 else None,
        }
        for row in auction if row
    }
    result = []
    for rank, row in enumerate(candidates, 1):
        if len(row) < 2 or row[0] in ("", "—"):
            continue
        symbol = row[0]
        auction_info = auction_by_symbol.get(symbol, {})
        action = auction_info.get("action", "不可判断")
        locked = locked_from_auction(
            symbol,
            auction_info.get("auction_open_change"),
            auction_info.get("auction_drift"),
        )
        result.append({
            "decision_date": decision_date,
            "confirmation_date": confirmation_date,
            "rank": rank,
            "symbol": symbol,
            "name": row[1],
            "auction_action": action,
            "auction_open_change": auction_info.get("auction_open_change"),
            "auction_drift": auction_info.get("auction_drift"),
            "locked_auction": "yes" if locked else "no",
            "proxy_eligible": "yes" if "可做" in action and not locked else "no",
        })
    return result


cases = [item for path in sorted(CASE_DIR.glob("*.md")) for item in load_case(path)]
codes = sorted({str(row["symbol"]) for row in cases})

with TdxClient(timeout=20) as client:
    bars = client.bars.get(codes, period="day", start=0, count=80,
                           anchor_date=max(str(row["confirmation_date"]) for row in cases))

all_rows = []
for row in cases:
    series = bars.get(str(row["symbol"]))
    target = date.fromisoformat(str(row["confirmation_date"]))
    bar = next((b for b in getattr(series, "bars", ()) if b.time.date() == target), None) if series else None
    open_price = f(getattr(bar, "open", None)) if bar else None
    high = f(getattr(bar, "high", None)) if bar else None
    low = f(getattr(bar, "low", None)) if bar else None
    close = f(getattr(bar, "close", None)) if bar else None
    row.update({
        "next_open": open_price,
        "next_high": high,
        "next_low": low,
        "next_close": close,
        "proxy_return_pct": pct(close, open_price),
        "proxy_mae_pct": pct(low, open_price),
    })
    all_rows.append(row)

trade_rows = []
by_date: dict[str, list[dict[str, object]]] = {}
for row in all_rows:
    by_date.setdefault(str(row["decision_date"]), []).append(row)
for decision_date, rows in by_date.items():
    eligible = [row for row in rows if row["proxy_eligible"] == "yes" and row["next_open"] is not None]
    if not eligible:
        continue
    chosen = eligible[0]
    trade_rows.append({
        "decision_date": decision_date,
        "confirmation_date": chosen["confirmation_date"],
        "selected_rank": chosen["rank"],
        "symbol": chosen["symbol"],
        "name": chosen["name"],
        "entry_rule": "first candidate whose case action contains 可做 and whose auction is not locked",
        "entry_price": chosen["next_open"],
        "exit_rule": "same-day close",
        "exit_price": chosen["next_close"],
        "return_pct": chosen["proxy_return_pct"],
        "max_adverse_pct": chosen["proxy_mae_pct"],
    })

all_fields = ["decision_date", "confirmation_date", "rank", "symbol", "name", "auction_action", "auction_open_change", "auction_drift", "locked_auction", "proxy_eligible", "next_open", "next_high", "next_low", "next_close", "proxy_return_pct", "proxy_mae_pct"]
trade_fields = ["decision_date", "confirmation_date", "selected_rank", "symbol", "name", "entry_rule", "entry_price", "exit_rule", "exit_price", "return_pct", "max_adverse_pct"]
for output, fields, rows in ((OUT_ALL, all_fields, all_rows), (OUT_TRADES, trade_fields, trade_rows)):
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

print(f"wrote {OUT_ALL} ({len(all_rows)} candidate outcomes)")
print(f"wrote {OUT_TRADES} ({len(trade_rows)} proxy trades)")
