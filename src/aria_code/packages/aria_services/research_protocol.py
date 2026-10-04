"""Financial-research grounding policy shared by Aria adapters."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping


_MARKET_IDENTIFIER = re.compile(
    r"\b[A-Z]{1,5}(?:\.[A-Z]{1,4})?\b|\b\d{6}(?:\.(?:SH|SZ|SS|HK))?\b"
)
_FINANCIAL_SUBJECTS = (
    "stock", "share", "equity", "market", "portfolio", "holding", "fund",
    "option", "bond", "forex", "crypto", "price", "volume", "valuation",
    "股票", "股价", "行情", "市场", "持仓", "组合", "基金", "期权", "债券",
    "外汇", "加密", "成交量", "估值", "市值", "财报", "基本面",
)
_EVIDENCE_INTENTS = (
    "analyze", "analysis", "forecast", "predict", "recommend", "buy", "sell",
    "current", "latest", "today", "trend", "risk", "target", "outlook",
    "this week", "how's", "how is", "doing", "performance",
    "分析", "预测", "推荐", "买入", "卖出", "最新", "当前", "今天", "走势",
    "趋势", "风险", "目标价", "前景", "成交量", "全面分析",
    "本周", "这周", "近期", "怎么样", "表现", "看法", "值得",
)
_GROUNDING_TOOL_FRAGMENTS = (
    "market", "quote", "price", "ohlcv", "fundamental", "filing", "news",
    "factor", "risk", "backtest", "portfolio", "prediction", "signal",
    "regime", "financial", "earnings", "valuation", "macro", "flow",
)


def _names_an_instrument(text: str) -> bool:
    """A ticker, code or company the finance pack recognises, or a named company.

    This used to be a bare regex, \\b[A-Z]{1,5}\\b: it took "API" and "CSV"
    for tickers ("analyze the API latency trend" was gated as a market
    question and refused without market data), and missed "分析AAPL" — no word
    boundary between 析 and A — and every company named in Chinese.
    """
    try:
        from aria_code.packs import activate_packs, load_builtin_packs

        load_builtin_packs()
        if any(a.pack == "finance" for a in activate_packs(text)):
            return True
    except Exception:
        if _MARKET_IDENTIFIER.search(text):
            return True
    try:
        from aria_code.apps.cli.intent_signals import _ENTITY_TERMS
    except Exception:
        return False
    lowered = text.lower()
    return any(term in lowered for term in _ENTITY_TERMS)


def requires_financial_evidence(query: str) -> bool:
    """Return whether a request needs current external financial evidence."""
    text = str(query or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if not any(term in lowered for term in _EVIDENCE_INTENTS):
        return False
    return any(term in lowered for term in _FINANCIAL_SUBJECTS) or _names_an_instrument(text)


def grounding_tool_names(tool_schemas: Iterable[Mapping]) -> frozenset[str]:
    """Select registered tools whose outputs can ground a financial conclusion."""
    names: set[str] = set()
    for schema in tool_schemas:
        function = schema.get("function") if isinstance(schema, Mapping) else None
        name = str(
            (function or {}).get("name")
            if isinstance(function, Mapping)
            else schema.get("name", "")
        )
        canonical = name.rsplit("__", 1)[-1].lower()
        if name and any(fragment in canonical for fragment in _GROUNDING_TOOL_FRAGMENTS):
            names.add(name)
    return frozenset(names)

