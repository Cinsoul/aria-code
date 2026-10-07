"""/report asks for the report in the session's language.

The prompt was Chinese only and ended "用中文输出", so an English session got a
Chinese report; with the model unavailable, the Chinese prompt matched the
chart-analysis route and a Chinese chart summary was saved as the report.
"""

from __future__ import annotations

import re
from datetime import datetime

from aria_code.apps.cli.commands.report import build_markdown_report_prompt

CJK = re.compile(r"[一-鿿]")
DATA = {"price": 529.3, "change_pct": 0.4, "rsi": 76.3, "macd": 9.51, "ma20": 504.7, "ma60": 493.4}
QUALITY = {"status": "complete", "stale": False, "providers": ["yfinance"]}


def _prompt(lang, **extra):
    return build_markdown_report_prompt(symbol="MSFT", report_type="standard", market_data=DATA,
                                        data_quality=QUALITY, now=datetime(2026, 10, 7), lang=lang, **extra)


def test_english_prompt():
    text = _prompt("en")
    assert not CJK.findall(text), CJK.findall(text)
    assert "# MSFT Research Report" in text and "**Date**: 2026-10-07" in text
    assert "Price" in text and "529.3" in text
    assert "use only the fields below" in text and "Write in English." in text
    assert "- Provider chain: yfinance" in text


def test_missing_data_is_named_in_english():
    text = build_markdown_report_prompt(symbol="MSFT", report_type="brief", market_data={},
                                        data_quality={}, now=datetime(2026, 10, 7), lang="en")
    assert "must not invent prices or indicators" in text and "brief edition" in text


def test_chinese_is_unchanged_by_default():
    text = build_markdown_report_prompt(symbol="MSFT", report_type="standard", market_data=DATA,
                                        data_quality=QUALITY, now=datetime(2026, 10, 7))
    assert text.startswith("为 MSFT 生成一份专业 Markdown 投研报告") and text.endswith("用中文输出。")
