"""/earnings SYMBOL: the next report, the last four against estimates, and the quarterly numbers.

/earnings handed off to /report, which wrote a general technical-analysis
report: price, moving averages, RSI. Nothing about earnings. This shows
what the command names, from yfinance: the next report date with the
consensus range, reported EPS against the estimate for recent quarters, and
revenue, net income and diluted EPS by quarter. `/earnings SYMBOL --report`
still writes the Markdown report.
"""

from __future__ import annotations

import math
from typing import Any, Optional


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def fetch_earnings(symbol: str, ticker: Any = None) -> dict:
    """Earnings data for ``symbol`` from yfinance (or the ``ticker`` object given)."""
    import logging

    # yfinance logs "HTTP Error 404 …" straight to the terminal for a symbol
    # without earnings; the answer below says so in a sentence instead.
    yf_log = logging.getLogger("yfinance")
    previous = yf_log.level
    yf_log.setLevel(logging.CRITICAL)
    try:
        return _fetch_earnings(symbol, ticker)
    finally:
        yf_log.setLevel(previous)


def _fetch_earnings(symbol: str, ticker: Any = None) -> dict:
    if ticker is None:
        try:
            import yfinance as yf
        except ImportError:
            return {"success": False, "error": "yfinance is not installed"}
        ticker = yf.Ticker(symbol)
    out: dict = {"success": True, "symbol": symbol.upper(), "history": [], "quarters": [], "next": {}}

    try:
        dates = ticker.earnings_dates
    except Exception:
        dates = None
    if dates is not None and not getattr(dates, "empty", True):
        for when, row in dates.sort_index(ascending=False).iterrows():
            reported = _num(row.get("Reported EPS"))
            estimate = _num(row.get("EPS Estimate"))
            if reported is None:
                continue
            surprise = _num(row.get("Surprise(%)"))
            if surprise is None and estimate:
                surprise = (reported - estimate) / abs(estimate) * 100
            out["history"].append({"date": str(when)[:10], "estimate": estimate, "reported": reported,
                                   "surprise_pct": surprise})
            if len(out["history"]) == 4:
                break

    try:
        calendar = ticker.calendar or {}
    except Exception:
        calendar = {}
    if isinstance(calendar, dict) and calendar:
        upcoming = calendar.get("Earnings Date") or []
        out["next"] = {
            "date": str(upcoming[0]) if upcoming else None,
            "eps_avg": _num(calendar.get("Earnings Average")),
            "eps_low": _num(calendar.get("Earnings Low")),
            "eps_high": _num(calendar.get("Earnings High")),
            "revenue_avg": _num(calendar.get("Revenue Average")),
        }

    try:
        income = ticker.quarterly_income_stmt
    except Exception:
        income = None
    if income is not None and not getattr(income, "empty", True):
        for column in list(income.columns)[:5]:
            def field(name: str) -> Optional[float]:
                return _num(income.at[name, column]) if name in income.index else None
            revenue, net = field("Total Revenue"), field("Net Income")
            out["quarters"].append({
                "period": str(column)[:10], "revenue": revenue, "net_income": net,
                "eps": field("Diluted EPS"),
                "net_margin": net / revenue * 100 if revenue and net is not None else None,
            })

    if not (out["history"] or out["quarters"] or out["next"]):
        return {"success": False, "symbol": symbol.upper(),
                "error": f"No earnings data for {symbol.upper()} (ETFs, indices and some non-US listings have none)"}
    return out


def _money(value: Optional[float]) -> str:
    if value is None:
        return "—"
    for size, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= size:
            return f"{value / size:.2f}{unit}"
    return f"{value:,.0f}"


def render_earnings(data: dict, console, lang: str = "en") -> None:
    from rich.padding import Padding
    from rich.table import Table

    zh = str(lang).lower().startswith("zh")
    T = (lambda a, b: a) if zh else (lambda a, b: b)
    symbol = data.get("symbol", "")
    console.print()
    console.print(f"  [bold]{symbol} {T('财报', 'earnings')}[/bold]  [dim]yfinance[/dim]")

    nxt = data.get("next") or {}
    if nxt.get("date"):
        parts = [f"{T('下次财报', 'Next report')} {nxt['date']}"]
        if nxt.get("eps_avg") is not None:
            band = (f" ({nxt['eps_low']:.2f}–{nxt['eps_high']:.2f})"
                    if nxt.get("eps_low") is not None and nxt.get("eps_high") is not None else "")
            parts.append(f"{T('EPS 一致预期', 'EPS consensus')} {nxt['eps_avg']:.2f}{band}")
        if nxt.get("revenue_avg"):
            parts.append(f"{T('营收预期', 'revenue consensus')} {_money(nxt['revenue_avg'])}")
        console.print("  [dim]" + " · ".join(parts) + "[/dim]")

    history = data.get("history") or []
    if history:
        console.print()
        table = Table(box=None, show_header=True, header_style="bold", padding=(0, 2))
        table.add_column(T("公布日", "Reported"))
        table.add_column(T("EPS 预期", "EPS est."), justify="right")
        table.add_column(T("EPS 实际", "EPS actual"), justify="right")
        table.add_column(T("超预期", "Surprise"), justify="right")
        for row in history:
            surprise = row.get("surprise_pct")
            colour = "green" if (surprise or 0) > 0 else "red" if (surprise or 0) < 0 else "dim"
            table.add_row(row["date"], f"{row['estimate']:.2f}" if row.get("estimate") is not None else "—",
                          f"{row['reported']:.2f}",
                          f"[{colour}]{surprise:+.1f}%[/{colour}]" if surprise is not None else "—")
        console.print(Padding(table, (0, 0, 0, 2)))
        beats = sum(1 for r in history if (r.get("surprise_pct") or 0) > 0)
        console.print(f"  [dim]{T(f'近 {len(history)} 次中 {beats} 次超预期', f'Beat the estimate in {beats} of the last {len(history)}')}[/dim]")

    quarters = data.get("quarters") or []
    if quarters:
        console.print()
        table = Table(box=None, show_header=True, header_style="bold", padding=(0, 2))
        table.add_column(T("季度末", "Quarter"))
        table.add_column(T("营收", "Revenue"), justify="right")
        table.add_column(T("净利润", "Net income"), justify="right")
        table.add_column(T("净利率", "Net margin"), justify="right")
        table.add_column(T("稀释 EPS (GAAP)", "Diluted EPS (GAAP)"), justify="right")
        for q in quarters:
            table.add_row(q["period"], _money(q.get("revenue")), _money(q.get("net_income")),
                          f"{q['net_margin']:.1f}%" if q.get("net_margin") is not None else "—",
                          f"{q['eps']:.2f}" if q.get("eps") is not None else "—")
        console.print(Padding(table, (0, 0, 0, 2)))
        console.print(f"  [dim]{T('上表 EPS 为公司公布的调整后口径，此处为 GAAP 稀释口径，两者可能不同', 'EPS above is as reported against estimates (adjusted); here it is GAAP diluted, which can differ')}[/dim]")
        if len(quarters) == 5 and quarters[0].get("revenue") and quarters[4].get("revenue"):
            yoy = quarters[0]["revenue"] / quarters[4]["revenue"] * 100 - 100
            console.print(f"  [dim]{T('最近一季营收同比', 'Latest quarter revenue year on year')} {yoy:+.1f}%[/dim]")
    console.print(f"  [dim]{T('完整报告：', 'Full report: ')}/earnings {symbol} --report[/dim]")
    console.print()


__all__ = ["fetch_earnings", "render_earnings"]
