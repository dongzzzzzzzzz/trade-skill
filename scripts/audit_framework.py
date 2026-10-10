#!/usr/bin/env python3
"""Audit the four pre-auction layers without changing production rules.

This report is intentionally descriptive. It measures whether the existing
case labels contain enough information to explain candidate outcomes; it does
not search for a profitable threshold and does not rewrite SKILL.md.
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
    if value is None:
        return None
    try:
        return float(value.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def table_block(text: str, starts: tuple[str, ...]) -> str:
    for start in starts:
        match = re.search(re.escape(start) + r".*?\n\n(.*?)(?=\n## )", text, re.S)
        if match:
            return match.group(1)
    return ""


def table_rows(block: str) -> tuple[list[str], list[list[str]]]:
    lines = [line for line in block.splitlines() if line.startswith("|")]
    lines = [line for line in lines if not line.startswith("|---")]
    if not lines:
        return [], []
    parse = lambda line: [cell.strip() for cell in line.strip().strip("|").split("|")]
    return parse(lines[0]), [parse(line) for line in lines[1:]]


def parse_case(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    date_match = re.search(
        r"(?:盘后冻结日 D|盘后候选日)：([0-9-]+).*?(?:确认日 D\+1|竞价确认日)：([0-9-]+)",
        text,
        re.S,
    )
    if not date_match:
        raise ValueError(f"cannot parse dates: {path}")
    decision_date, confirmation_date = date_match.groups()
    env_match = re.search(r"(?:结论|环境判断)：\*\*(.*?)\*\*", text)
    counts_match = re.search(
        r"涨停\s+([0-9.]+).*?炸板\s+([0-9.]+).*?跌停\s+([0-9.]+).*?炸板率\s+([0-9.]+)%",
        text,
        re.S,
    )
    env_counts = {
        "limit_up": number(counts_match.group(1)) if counts_match else None,
        "broken": number(counts_match.group(2)) if counts_match else None,
        "limit_down": number(counts_match.group(3)) if counts_match else None,
        "broken_rate": number(counts_match.group(4)) if counts_match else None,
    }

    ladder_block = table_block(text, ("## 2. D 日题材与梯队",))
    ladder_header, ladder_rows = table_rows(ladder_block)
    ladders: dict[str, dict] = {}
    if ladder_header:
        for row in ladder_rows:
            if len(row) < 3 or row[0] in ("", "主题/原因"):
                continue
            ladders[row[0]] = {
                "count": number(row[1]),
                "highest_board": number(row[2]),
            }

    candidate_block = table_block(
        text,
        (
            "## 3. 冻结候选（D 日盘后）",
            "## 二、冻结的盘后候选（不可用 D+1 数据改写）",
        ),
    )
    candidate_header, candidate_rows = table_rows(candidate_block)
    candidates = []
    modern = "节点" in candidate_header
    for rank, row in enumerate(candidate_rows, 1):
        if len(row) < 2 or row[0] in ("", "—"):
            continue
        if modern:
            node, theme, day_change = row[2], row[3], number(row[4])
            board = number(re.search(r"[0-9]+", node).group(0)) if re.search(r"[0-9]+", node) else None
        else:
            theme, board, day_change = row[2], number(row[3]), None
            node = None
        ladder = ladders.get(theme, {})
        candidates.append({
            "decision_date": decision_date,
            "confirmation_date": confirmation_date,
            "rank": rank,
            "symbol": row[0],
            "name": row[1],
            "theme": theme,
            "theme_count": ladder.get("count"),
            "theme_highest_board": ladder.get("highest_board"),
            "node": node,
            "board": board,
            "day_change": day_change,
            "environment": env_match.group(1) if env_match else "缺失",
            **env_counts,
        })
    return {
        "decision_date": decision_date,
        "confirmation_date": confirmation_date,
        "environment": env_match.group(1) if env_match else "缺失",
        **env_counts,
        "candidates": candidates,
    }


def mean(values: list[float]) -> float | None:
    return round(statistics.mean(values), 4) if values else None


def load_outcomes(path: Path) -> dict[tuple[str, str], dict]:
    with path.open(encoding="utf-8") as handle:
        return {(row["decision_date"], row["symbol"]): row for row in csv.DictReader(handle)}


def run(months: list[str], output: Path, report: Path) -> None:
    cases = {}
    for month in months:
        for path in sorted((ROOT / "cases" / month).glob("*.md")):
            case = parse_case(path)
            cases[case["decision_date"]] = case

    joined = []
    for case in cases.values():
        next_case = cases.get(case["confirmation_date"])
        for candidate in case["candidates"]:
            outcome = load_outcomes(ROOT / "results" / f"{case['decision_date'][:7]}-market-outcomes.csv").get(
                (case["decision_date"], candidate["symbol"]), {}
            )
            action = outcome.get("auction_action", "")
            candidate.update({
                "next_environment": next_case["environment"] if next_case else "缺失",
                "proxy_return_pct": number(outcome.get("proxy_return_pct")),
                "proxy_mae_pct": number(outcome.get("proxy_mae_pct")),
                "auction_action": action,
                "eligible": "yes" if "可做" in action else "no",
            })
            joined.append(candidate.copy())

    fields = [
        "decision_date", "confirmation_date", "environment", "next_environment",
        "limit_up", "broken", "limit_down", "broken_rate", "rank", "symbol", "name",
        "theme", "theme_count", "theme_highest_board", "node", "board", "day_change",
        "auction_action", "eligible", "proxy_return_pct", "proxy_mae_pct",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(joined)

    def group_stats(key: str, rows: list[dict]) -> list[dict]:
        groups = defaultdict(list)
        for row in rows:
            if row["eligible"] == "yes" and row["proxy_return_pct"] is not None:
                groups[row.get(key) or "缺失"].append(row["proxy_return_pct"])
        return [
            {"group": group, "n": len(values), "sum": round(sum(values), 4), "mean": mean(values)}
            for group, values in sorted(groups.items(), key=lambda item: str(item[0]))
        ]

    def board_bucket(row: dict) -> str:
        board = row.get("board")
        if board is None:
            return "缺失"
        if board <= 1:
            return "低位/首板"
        if board <= 3:
            return "中位/二至三板"
        return "高位/四板以上"

    for row in joined:
        row["board_bucket"] = board_bucket(row)
        row["theme_breadth_bucket"] = (
            "孤立/缺失" if row.get("theme_count") in (None, 1) else "有同题材梯队"
        )

    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 盘后框架误判审计",
        "",
        "这是一份诊断报告，不是新交易规则。它只使用冻结案例与独立保存的次日结果，检查当前 Skill 是否真的记录了环境、情绪、节点和候选池所需要的信息。",
        "",
        "## 一、当前框架的结构性缺口",
        "",
        "- 环境只有单日指数涨跌、涨停/跌停数量和炸板率，缺少连续状态、前一日情绪方向和指数与题材是否共振。",
        "- 情绪没有独立字段，连板溢价、中位股负反馈、跌停扩散、炸板次日反馈没有进入状态判断。",
        "- 节点字段在 7 月案例中是自然语言，在 8 月案例中基本退化为板位，无法检验穿越、断板、爆量、破局、补涨和卡位。",
        "- 候选池的默认排序是板位、封单额、封板时间，排序变量并不等于主线强度、核心辨识度或节点适配度。",
        "- 当前结果主要是开盘到收盘代理，不能证明盘后判断本身正确，只能用于发现明显失配。",
        "",
        "## 二、可验证分组结果",
    ]
    for title, key in (
        ("环境标签", "environment"),
        ("环境到次日环境的转移", "next_environment"),
        ("候选板位", "board_bucket"),
        ("题材是否有梯队", "theme_breadth_bucket"),
        ("候选排序位置", "rank"),
    ):
        lines += ["", f"### {title}", "", "| 分组 | 可做候选数 | 收益合计 | 平均收益 |", "|---|---:|---:|---:|"]
        for item in group_stats(key, joined):
            lines.append(f"| {item['group']} | {item['n']} | {item['sum']}% | {item['mean']}% |")

    missing_node = sum(1 for row in joined if not row.get("node"))
    missing_theme = sum(1 for row in joined if row.get("theme_count") is None)
    lines += [
        "",
        "## 三、这轮不能直接下的结论",
        "",
        f"- {missing_node}/{len(joined)} 个候选没有结构化节点字段；在这个缺口修复前，不能声称已经进化了节点理解。",
        f"- {missing_theme}/{len(joined)} 个候选无法映射到题材梯队；题材发酵与孤立异动的评估目前不完整。",
        "- 不能把某个分组收益较好直接改写成规则，因为当前样本没有真实用户成交，且环境和节点字段存在缺失。",
        "",
        "## 四、下一轮正确方向",
        "",
        "1. 先把环境重构为‘指数状态 + 情绪状态 + 主线状态’三条轴，而不是一个标签。",
        "2. 为每个候选记录节点类型、所在梯队、同题材竞争、是否核心、是否补涨，以及它在当日主线中的位置。",
        "3. 用这些状态组合解释为什么同样是进攻日，有的适合高位核心，有的只适合低位试错。",
        "4. Challenger 只能改变一个框架层的定义，并保留候选，不允许用硬过滤掩盖判断失败。",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


parser = argparse.ArgumentParser()
parser.add_argument("--months", nargs="+", default=["2026-07", "2026-08"])
parser.add_argument("--output", type=Path, default=ROOT / "results/framework-audit.csv")
parser.add_argument("--report", type=Path, default=ROOT / "evolution/FRAMEWORK_AUDIT.md")
args = parser.parse_args()
run(args.months, args.output, args.report)
print(f"wrote {args.output}")
print(f"wrote {args.report}")
