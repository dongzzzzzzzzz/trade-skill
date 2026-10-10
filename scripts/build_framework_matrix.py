#!/usr/bin/env python3
"""Build a descriptive matrix for evolving the pre-auction framework.

The matrix separates market-state diagnostics from candidate selection. It is
not an optimizer and intentionally produces no trading rule.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def number(value: str | None) -> float | None:
    try:
        return float(value.replace("%", "").strip()) if value else None
    except ValueError:
        return None


def parse_case(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    dates = re.search(
        r"(?:盘后冻结日 D|盘后候选日)：([0-9-]+).*?(?:确认日 D\+1|竞价确认日)：([0-9-]+)",
        text,
        re.S,
    )
    env = re.search(r"(?:结论|环境判断)：\*\*(.*?)\*\*", text)
    index = re.search(r"指数方向：([^；]+)；指数关系：([^\n]+)", text)
    emotion = re.search(r"情绪轴：涨跌停差 ([^；]+)；风险压力 ([^；]+)；最高板 ([^\n]+)", text)
    if not dates:
        raise ValueError(path)
    candidates_block = re.search(r"## 二、冻结的盘后候选.*?\n\n(.*?)(?=\n## )", text, re.S)
    candidates = []
    if candidates_block:
        lines = [line for line in candidates_block.group(1).splitlines() if line.startswith("|")]
        lines = [line for line in lines if not line.startswith("|---")]
        for line in lines[1:]:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 10 or not re.match(r"^(sh|sz)\d{6}$", cells[0]):
                continue
            candidates.append({
                "symbol": cells[0],
                "name": cells[1],
                "node_facts": cells[2],
                "theme_count": number(cells[4]),
                "theme_rank": number(cells[5]),
                "market_highest_board": number(cells[6]),
                "board": number(cells[7]),
            })
    return {
        "decision_date": dates.group(1),
        "confirmation_date": dates.group(2),
        "environment": env.group(1) if env else "缺失",
        "index_direction": index.group(1) if index else "缺失",
        "index_alignment": index.group(2) if index else "缺失",
        "breadth_balance": number(emotion.group(1)) if emotion else None,
        "risk_pressure": number(emotion.group(2)) if emotion else None,
        "highest_board": number(emotion.group(3)) if emotion else None,
        "candidates": candidates,
    }


def read_outcomes(path: Path) -> dict[tuple[str, str], dict]:
    with path.open(encoding="utf-8") as handle:
        return {(row["decision_date"], row["symbol"]): row for row in csv.DictReader(handle)}


def transition(previous: dict | None, current: dict) -> str:
    if not previous:
        return "首日/不可判断"
    breadth_delta = (current["breadth_balance"] or 0) - (previous["breadth_balance"] or 0)
    risk_delta = (current["risk_pressure"] or 0) - (previous["risk_pressure"] or 0)
    if breadth_delta > 0 and risk_delta < 0:
        return "情绪修复"
    if breadth_delta < 0 and risk_delta > 0:
        return "情绪恶化"
    if breadth_delta > 0 or risk_delta < 0:
        return "局部修复"
    if breadth_delta < 0 or risk_delta > 0:
        return "局部恶化"
    return "情绪横盘"


def run(months: list[str], case_root: Path, output: Path, report: Path) -> None:
    all_cases = []
    for month in months:
        for path in sorted((case_root / month).glob("*.md")):
            all_cases.append(parse_case(path))
    all_cases.sort(key=lambda item: item["decision_date"])

    outcomes = {
        month: read_outcomes(ROOT / "results" / f"008-{month}-market-outcomes.csv")
        for month in months
    }
    matrix = []
    previous = None
    for case in all_cases:
        rows = []
        for candidate in case["candidates"]:
            outcome = outcomes[case["decision_date"][:7]].get((case["decision_date"], candidate["symbol"]), {})
            if "可做" not in outcome.get("auction_action", ""):
                continue
            ret = number(outcome.get("proxy_return_pct"))
            if ret is not None:
                rows.append(ret)
        matrix.append({
            "decision_date": case["decision_date"],
            "confirmation_date": case["confirmation_date"],
            "environment": case["environment"],
            "index_direction": case["index_direction"],
            "index_alignment": case["index_alignment"],
            "emotion_transition": transition(previous, case),
            "breadth_balance": case["breadth_balance"],
            "risk_pressure": case["risk_pressure"],
            "highest_board": case["highest_board"],
            "candidate_count": len(case["candidates"]),
            "eligible_count": len(rows),
            "eligible_positive_rate": round(sum(value > 0 for value in rows) / len(rows), 4) if rows else None,
            "best_eligible_return_pct": max(rows) if rows else None,
            "median_eligible_return_pct": statistics.median(rows) if rows else None,
            "worst_eligible_return_pct": min(rows) if rows else None,
            "eligible_return_sum_pct": sum(rows) if rows else 0.0,
            "eligible_returns": ";".join(str(round(value, 4)) for value in rows),
        })
        previous = case

    fields = list(matrix[0]) if matrix else []
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(matrix)

    def grouped(key: str) -> list[tuple[str, list[dict]]]:
        groups = defaultdict(list)
        for row in matrix:
            groups[row[key] or "缺失"].append(row)
        return sorted(groups.items(), key=lambda item: str(item[0]))

    def fmt(value: float | None) -> str:
        return "缺失" if value is None else f"{value:.2f}"

    lines = [
        "# 环境、情绪、节点与候选池矩阵",
        "",
        "本矩阵只做框架诊断，不把任何分组结果直接变成买卖规则。它把‘环境判断错误’与‘候选选择错误’分开。",
        "",
        "## 日级机会质量",
        "",
        "| 日期 | 环境 | 情绪变化 | 可做数 | 正收益率 | 最好 | 中位 | 最差 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in matrix:
        lines.append(
            f"| {row['decision_date']} | {row['environment']} | {row['emotion_transition']} | "
            f"{row['eligible_count']} | {fmt(row['eligible_positive_rate'] * 100 if row['eligible_positive_rate'] is not None else None)}% | "
            f"{fmt(row['best_eligible_return_pct'])}% | {fmt(row['median_eligible_return_pct'])}% | {fmt(row['worst_eligible_return_pct'])}% |"
        )

    for title, key in (("环境分组", "environment"), ("情绪变化分组", "emotion_transition"), ("指数关系分组", "index_alignment")):
        lines += ["", f"## {title}", "", "| 分组 | 天数 | 可做候选数 | 收益合计 | 最好机会均值 | 中位机会均值 |", "|---|---:|---:|---:|---:|---:|"]
        for group, rows in grouped(key):
            candidates = [r for r in rows if r["eligible_count"]]
            returns = [r["eligible_return_sum_pct"] for r in rows]
            best = [r["best_eligible_return_pct"] for r in candidates]
            medians = [r["median_eligible_return_pct"] for r in candidates]
            lines.append(f"| {group} | {len(rows)} | {sum(r['eligible_count'] for r in rows)} | {fmt(sum(returns))}% | {fmt(statistics.mean(best) if best else None)}% | {fmt(statistics.mean(medians) if medians else None)}% |")

    lines += [
        "",
        "## 解释边界",
        "",
        "- 如果某环境下‘最好机会’仍经常为正，但当前首选收益很差，主要问题在候选池/排序，不应先否定环境。",
        "- 如果某环境下大多数候选的最好机会和中位机会都很差，才有理由重做环境或情绪状态定义。",
        "- 节点适配必须在候选层比较，不能用‘高位/低位’单变量替代节点；下一步要补充穿越、断板、爆量、破局、补涨和卡位的历史序列事实。",
    ]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


parser = argparse.ArgumentParser()
parser.add_argument("--months", nargs="+", default=["2026-07", "2026-08"])
parser.add_argument("--case-root", type=Path, default=ROOT / "evolution/experiments/008-cases")
parser.add_argument("--output", type=Path, default=ROOT / "results/framework-matrix.csv")
parser.add_argument("--report", type=Path, default=ROOT / "evolution/FRAMEWORK_MATRIX.md")
args = parser.parse_args()
run(args.months, args.case_root, args.output, args.report)
print(f"wrote {args.output}")
print(f"wrote {args.report}")
