#!/usr/bin/env python3
"""Historical, no-lookahead monthly case-study generator.

For each July trading day D, the candidate pool is built only from D data.
Confirmation uses only the next trading day's historical auction observations
through 09:25:00; no next-day bars, closes, or intraday observations are read.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Any

from eltdx import TdxClient

OUT = Path("cases")
START = dt.date(2026, 7, 1)
END = dt.date(2026, 7, 31)


def weekdays(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end-start).days + 1)
            if (start + dt.timedelta(days=i)).weekday() < 5]


def f(x: Any, default: float | None = None) -> float | None:
    try:
        return float(x) if x is not None else default
    except (TypeError, ValueError):
        return default


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b in (None, 0):
        return None
    return (a / b - 1.0) * 100.0


def fmt(x: Any, digits: int = 2) -> str:
    if x is None:
        return "缺失"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def row_dict(row: Any) -> dict[str, Any]:
    # eltdx models expose attributes; keep this intentionally narrow.
    names = ["trading_date", "trading_date_value", "board_level", "code", "name",
             "limit_reason", "limit_reason_extra", "seal_amount", "limit_time",
             "broken_count", "industry", "limit_type", "highest_board_level",
             "market", "full_code"]
    return {n: getattr(row, n, None) for n in names}


def get_bars(client: TdxClient, codes: list[str], date: dt.date) -> dict[str, Any]:
    if not codes:
        return {}
    return client.bars.get(codes, period="day", start=0, count=3,
                           anchor_date=date.isoformat())


def market_environment(client: TdxClient, day: dt.date, limit_rows: list[dict[str, Any]]) -> dict[str, Any]:
    idx = get_bars(client, ["sh000001", "sz399001", "sz399006"], day)
    vals: dict[str, dict[str, Any]] = {}
    for code, series in idx.items():
        bars = list(getattr(series, "bars", ()))
        cur = next((b for b in bars if getattr(b.time, "date", lambda: None)() == day), None)
        prev = None
        for b in bars:
            if getattr(b.time, "date", lambda: None)() < day:
                prev = b
        vals[code] = {
            "close": f(getattr(cur, "close", None)),
            "prev_close": f(getattr(prev, "close", None)),
            "change_pct": pct(f(getattr(cur, "close", None)), f(getattr(prev, "close", None))),
            "amount": f(getattr(cur, "amount", None)),
        }
    ups = sum(1 for r in limit_rows if r.get("limit_type") == 1)
    broken = sum(1 for r in limit_rows if r.get("limit_type") == 3)
    downs = sum(1 for r in limit_rows if r.get("limit_type") == 0)
    denom = ups + broken
    broken_rate = broken / denom * 100 if denom else None
    sh = vals.get("sh000001", {})
    sz = vals.get("sz399001", {})
    cy = vals.get("sz399006", {})
    breadth_balance = ups - downs
    risk_pressure = downs + broken
    index_direction = "上涨" if (sh.get("change_pct") or 0) > 0 else "下跌"
    index_alignment = (
        "三指数共振"
        if all((v.get("change_pct") or 0) > 0 for v in (sh, sz, cy))
        or all((v.get("change_pct") or 0) < 0 for v in (sh, sz, cy))
        else "指数分化"
    )
    if downs > ups or (broken_rate is not None and broken_rate >= 40) or (sh.get("change_pct") is not None and sh["change_pct"] <= -1):
        regime = "退潮/防守"
    elif (sh.get("change_pct") is not None and sh["change_pct"] >= 0 and ups > downs and (broken_rate is None or broken_rate < 30)):
        regime = "进攻/修复"
    elif sh.get("change_pct") is not None and sh["change_pct"] >= 0:
        regime = "分歧/试错"
    else:
        regime = "等待"
    emotion_axis = {
        "breadth_balance": breadth_balance,
        "risk_pressure": risk_pressure,
        "limit_up": ups,
        "limit_down": downs,
        "broken_rate": broken_rate,
        "highest_board": max((r.get("board_level") or 0) for r in limit_rows),
    }
    return {"indices": vals, "limit_up": ups, "broken": broken, "limit_down": downs,
            "broken_rate": broken_rate, "regime": regime,
            "index_direction": index_direction, "index_alignment": index_alignment,
            "breadth_balance": breadth_balance, "risk_pressure": risk_pressure,
            "emotion_axis": emotion_axis}


def display_theme(row: dict[str, Any]) -> str:
    return str(row.get("limit_reason") or row.get("industry") or "缺失")


def enrich_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ups = [row for row in rows if row.get("limit_type") == 1]
    profiles: dict[str, dict[str, Any]] = {}
    for row in ups:
        theme = display_theme(row)
        profile = profiles.setdefault(theme, {"count": 0, "highest_board": 0})
        profile["count"] += 1
        profile["highest_board"] = max(profile["highest_board"], row.get("board_level") or 0)
    market_highest = max((row.get("board_level") or 0) for row in rows) if rows else 0
    for row in rows:
        theme = display_theme(row)
        profile = profiles.get(theme, {"count": 1, "highest_board": row.get("board_level") or 0})
        peer_rows = [peer for peer in ups if display_theme(peer) == theme]
        peer_rows.sort(key=lambda peer: (-(peer.get("board_level") or 0), -(peer.get("seal_amount") or 0), peer.get("limit_time") or "99:99:99"))
        peer_rank = next((i for i, peer in enumerate(peer_rows, 1) if peer.get("full_code") == row.get("full_code")), None)
        board = row.get("board_level") or 0
        facts = []
        if row.get("limit_type") == 3:
            facts.append("炸板/分歧")
        if board == market_highest and board > 0:
            facts.append("市场最高板")
        if peer_rank == 1:
            facts.append("题材前排")
        if board <= 2 and profile["count"] >= 2:
            facts.append("低位题材参与")
        if not facts:
            facts.append("板位接力")
        row.update({
            "theme": theme,
            "theme_count": profile["count"],
            "theme_highest_board": profile["highest_board"],
            "theme_rank": peer_rank,
            "market_highest_board": market_highest,
            "node_facts": ";".join(facts),
        })
    return rows


def pick_candidates(limit_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limit_rows = enrich_candidates(limit_rows)
    ups = [r for r in limit_rows if r.get("limit_type") == 1]
    broken = [r for r in limit_rows if r.get("limit_type") == 3]
    # Higher board, then seal amount, then earlier limit time: a transparent
    # engineering ordering, not a profit probability.
    def key(r: dict[str, Any]):
        return (-(r.get("board_level") or 0), -(r.get("seal_amount") or 0), r.get("limit_time") or "99:99:99")
    ordered = sorted(ups, key=key)[:8]
    if len(ordered) < 8:
        ordered += sorted(broken, key=lambda r: (-(r.get("highest_board_level") or 0), -(r.get("seal_amount") or 0)))[:8-len(ordered)]
    return ordered


def point_at_or_before(points: list[Any], seconds: int) -> Any | None:
    eligible = [p for p in points if getattr(p, "time_seconds", 0) <= seconds]
    return eligible[-1] if eligible else None


def auction_confirmation(client: TdxClient, code: str, next_day: dt.date) -> dict[str, Any]:
    try:
        a = client.helpers.auction_data(code, date=next_day.isoformat(), include_series=True,
                                        include_snapshot=True, include_quote=True)
    except Exception as exc:  # data failure is a conclusion, never an estimate
        return {"code": code, "status": "不可判断", "error": f"{type(exc).__name__}: {exc}"}
    points = list(getattr(getattr(a, "series", None), "points", ()))
    p915 = point_at_or_before(points, 9*3600 + 15*60)
    p920 = point_at_or_before(points, 9*3600 + 20*60)
    p925 = point_at_or_before(points, 9*3600 + 25*60)
    snap = getattr(a, "snapshot_0925", None)
    preclose = f(getattr(a, "pre_close_price", None))
    open_price = f(getattr(a, "open_price", None))
    open_chg = f(getattr(a, "open_change_pct", None))
    if p925 is None or preclose is None:
        return {"code": code, "status": "不可判断", "error": "09:25 或昨收字段缺失"}
    p915_price = f(getattr(p915, "price", None)); p920_price = f(getattr(p920, "price", None)); p925_price = f(getattr(p925, "price", None))
    signed920 = f(getattr(p920, "unmatched_signed_raw", None))
    signed925 = f(getattr(p925, "unmatched_signed_raw", None))
    drift = pct(p925_price, p920_price)
    if open_chg is None:
        open_chg = pct(open_price, preclose)
    # Qualitative pre-open grading; thresholds are explicit engineering rules.
    if open_chg is not None and open_chg >= 2 and (drift is None or drift >= -0.5) and (signed925 is None or signed925 >= 0):
        grade = "超预期"
    elif open_chg is not None and open_chg >= -1.5 and (drift is None or drift >= -1.0):
        grade = "符合预期"
    else:
        grade = "不及预期"
    return {"code": code, "status": grade, "preclose": preclose, "open_price": open_price,
            "open_change_pct": open_chg, "p915_price": p915_price, "p920_price": p920_price,
            "p925_price": p925_price, "p920_unmatched_signed": signed920,
            "p925_unmatched_signed": signed925, "p920_to_p925_pct": drift,
            "series_last_time_used": getattr(p925, "time_label", None)}


def write_case(client: TdxClient, day: dt.date, next_day: dt.date) -> None:
    raw = client.f10.limit_up_down_list(day.isoformat(), day.isoformat(), include_summary=True)
    rows = [row_dict(r) for r in getattr(raw, "rows", ())]
    env = market_environment(client, day, rows)
    candidates = pick_candidates(rows)
    codes = [r.get("full_code") for r in candidates if r.get("full_code")]
    bars = get_bars(client, codes, day)
    confirmations = {c: auction_confirmation(client, c, next_day) for c in codes}
    lines: list[str] = []
    lines += [f"# 小宝1105式历史案例：{day.isoformat()}", "",
              f"- 盘后候选日：{day.isoformat()}（只使用当日及此前数据）",
              f"- 竞价确认日：{next_day.isoformat()}（只读取至 09:25:00）",
              "- 数据源：eltdx==3.2.3 历史接口；未读取竞价确认日 09:25 之后的任何行情。",
              "- 说明：这是按公开框架做的条件化研究，不是小宝1105本人当日持仓或投资建议。", ""]
    lines += ["## 一、D 日盘后环境", "",
              f"- 环境判断：**{env['regime']}**",
              f"- 涨停 {env['limit_up']} 家，炸板 {env['broken']} 家，跌停 {env['limit_down']} 家，炸板率 {fmt(env['broken_rate'])}%",
              f"- 指数方向：{env['index_direction']}；指数关系：{env['index_alignment']}",
              f"- 情绪轴：涨跌停差 {env['breadth_balance']}；风险压力 {env['risk_pressure']}；最高板 {env['emotion_axis']['highest_board']}"]
    for code, v in env["indices"].items():
        lines.append(f"- {code}：收盘 {fmt(v.get('close'))}，涨跌 {fmt(v.get('change_pct'))}%")
    lines += ["", "## 二、冻结的盘后候选（不可用 D+1 数据改写）", "",
              "|代码|名称|节点事实|题材/原因|题材梯队|题材内位置|市场最高板|板位|封单额|D日状态|",
              "|---|---|---|---|---:|---:|---:|---:|---:|---|"]
    if not candidates:
        lines.append("|—|暂无合格候选|涨跌停梯队为空|—|—|暂无合格候选|")
    for r in candidates:
        lines.append(f"|{r.get('full_code')}|{r.get('name')}|{r.get('node_facts')}|{r.get('theme')}|{r.get('theme_count')}|{r.get('theme_rank')}|{r.get('market_highest_board')}|{r.get('board_level') or '炸板'}|{fmt(r.get('seal_amount'),0)}|冻结|")
    lines += ["", "## 三、D+1 09:25 前竞价验货", "",
              "判定口径：超预期=开盘涨幅≥2%且 09:20→09:25 不明显走弱；符合预期=开盘不低于 -1.5% 且不明显走弱；否则不及预期。阈值是透明的工程化排序参数，不是作者原话。", "",
              "|代码|竞价等级|开盘涨跌|09:15价|09:20价|09:25价|09:20未匹配量方向|动作|", "|---|---|---:|---:|---:|---:|---:|---|"]
    doable: list[str] = []
    for r in candidates:
        code = r.get("full_code"); a = confirmations.get(code, {})
        grade = a.get("status", "不可判断")
        action = "不可判断"
        if grade in ("超预期", "符合预期") and env["regime"] not in ("退潮/防守", "等待"):
            action = "可做（仅观察/小仓试错）"; doable.append(code)
        elif grade == "不及预期":
            action = "不做/降级"
        vals = [a.get("open_change_pct"), a.get("p915_price"), a.get("p920_price"), a.get("p925_price"), a.get("p920_unmatched_signed")]
        lines.append(f"|{code}|{grade}|{fmt(vals[0])}%|{fmt(vals[1])}|{fmt(vals[2])}|{fmt(vals[3])}|{fmt(vals[4],0)}|{action}|")
    lines += ["", "## 四、结论与失效条件", ""]
    if doable:
        lines.append("按这套框架，竞价层面可进入观察/试错的候选：" + "、".join(doable) + "。这里的‘可做’不是买入信号，仍需开盘后的主动性、板块跟随和指数共振验证。")
    else:
        lines.append("暂无合格的可做候选：要么竞价不认可/数据不可判断，要么 D 日环境处于防守。管住手本身就是动作。")
    lines += ["", "统一失效条件：竞价转弱、同身位竞争对手反向卡位、板块没有首板/前排扩散、指数与题材不共振、开盘后承接破坏；任何一项出现都应降级或退出。", ""]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{day.isoformat()}.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--end", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    OUT = args.out
    days = weekdays(START, END)
    days = weekdays(args.start, args.end)
    with TdxClient(timeout=20) as client:
        for i, day in enumerate(days):
            next_day = days[i+1] if i+1 < len(days) else day + dt.timedelta(days=1)
            while next_day.weekday() >= 5:
                next_day += dt.timedelta(days=1)
            print(f"[{i+1}/{len(days)}] {day} -> {next_day}", flush=True)
            write_case(client, day, next_day)


if __name__ == "__main__":
    main()
