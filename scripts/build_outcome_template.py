#!/usr/bin/env python3
"""Expand frozen case tables into a fillable per-candidate outcome CSV."""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "2026-07"
OUT = ROOT / "results" / "2026-07-outcomes.csv"

FIELDS = [
    "decision_date", "confirmation_date", "rank", "symbol", "auction_action",
    "executable", "selected_rank", "entry_time", "entry_price", "exit_time",
    "exit_price", "return_pct", "max_adverse_pct", "user_action", "error_type",
    "lesson",
]


def table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    return rows[1:]  # discard header


def section(text: str, start: str, end: str) -> str:
    match = re.search(re.escape(start) + r"\n\n(.*?)\n" + re.escape(end), text, re.S)
    return match.group(1) if match else ""


def parse_case(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    dates = re.search(r"盘后冻结日 D：([0-9-]+).*?确认日 D\+1：([0-9-]+)", text, re.S)
    if not dates:
        return []
    decision_date, confirmation_date = dates.groups()
    candidates = table_rows(section(text, "## 3. 冻结候选（D 日盘后）", "## 4. D+1 竞价确认"))
    auction = table_rows(section(text, "## 4. D+1 竞价确认（截至 09:25）", "## 5. 当日结论与失效条件"))
    auction_by_symbol = {row[0]: row[-1] for row in auction if row}
    output = []
    for rank, row in enumerate(candidates, 1):
        if len(row) < 2 or row[0] in ("—", ""):
            continue
        symbol = row[0]
        output.append({
            "decision_date": decision_date,
            "confirmation_date": confirmation_date,
            "rank": str(rank),
            "symbol": symbol,
            "auction_action": auction_by_symbol.get(symbol, "unknown"),
            "executable": "unknown",
            "selected_rank": "",
            "entry_time": "",
            "entry_price": "",
            "exit_time": "",
            "exit_price": "",
            "return_pct": "",
            "max_adverse_pct": "",
            "user_action": "unknown",
            "error_type": "",
            "lesson": "",
        })
    return output


rows = [row for path in sorted(CASE_DIR.glob("*.md")) for row in parse_case(path)]
with OUT.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
print(f"wrote {OUT} ({len(rows)} candidate rows)")
