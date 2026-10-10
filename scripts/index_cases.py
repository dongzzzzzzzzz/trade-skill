#!/usr/bin/env python3
"""Create a compact index of frozen July cases for Darwin review."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = ROOT / "cases" / "2026-07"
OUT = ROOT / "results" / "2026-07-case-index.csv"

rows = ["decision_date,confirmation_date,candidate_count,has_auction_section"]
for path in sorted(CASE_DIR.glob("*.md")):
    text = path.read_text(encoding="utf-8")
    dates = re.search(r"盘后冻结日 D：([0-9-]+).*?确认日 D\+1：([0-9-]+)", text, re.S)
    candidates = re.search(r"## 3\. 冻结候选.*?\n\n(.*?)(?=\n## 4\.)", text, re.S)
    count = max(0, len(re.findall(r"^\|[^|]+\|[^|]+\|", candidates.group(1), re.M)) - 1) if candidates else 0
    decision, confirmation = dates.groups() if dates else (path.stem, "")
    rows.append(f"{decision},{confirmation},{count},{'yes' if '## 4.' in text else 'no'}")

OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(rows) - 1} cases)")
