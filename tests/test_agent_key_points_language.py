"""An English /team gets English findings from every analyst.

The analysts' one-line findings and their no-model templates were Chinese
only — "距MA20 -0.5%", "MACD死叉，空头压力", "年化波动率 24.8%", "估值：PE=38.0x" —
under English agent names. The macro template also stated "当前货币政策偏宽松，
流动性充裕" (policy loose, liquidity ample) as fact, with no data behind it.
"""

from __future__ import annotations

import re

import pytest

from aria_code.agents.financial import earnings, fundamental, macro, news, risk, technical

CJK = re.compile(r"[一-鿿]")


def _all(texts):
    return " | ".join(texts if isinstance(texts, list) else [texts])


HISTORY = {"rsi": 28, "ma20": 333.3, "macd": -1.2, "macd_signal": 0.4, "macd_hist": -1.6, "pattern": "十字星"}


@pytest.mark.parametrize("make", [
    lambda lang: technical._extract_key_points(HISTORY, 331.8, lang=lang),
    lambda lang: technical._template_analysis("AAPL", 331.8, HISTORY, lang=lang),
    lambda lang: risk._template_risk("AAPL", {"ann_vol": 24.8, "max_dd": -13.8, "sharpe": 1.61}, lang=lang),
    lambda lang: news._build_key_points([{"age_days": 1}], {"upgrade": 2}, lang=lang),
    lambda lang: news._template_analysis("AAPL", [{"age_days": 1, "title": "Apple ships"}], {"upgrade": 1}, lang=lang),
    lambda lang: earnings._build_key_points({"price_reaction_pct": -1.2, "revenue_trend": [{"revenue": 110}, {"revenue": 100}]},
                                            {"pct_surprise": 6.9}, "BUY", lang=lang),
    lambda lang: earnings._template_analysis("AAPL", {}, {"pct_surprise": 6.9}, "beat", lang=lang),
    lambda lang: fundamental._template_fundamental("AAPL", 38.0, 45.1, 148.8, 16.4, lang=lang),
    lambda lang: macro._template_macro("AAPL", {"^GSPC": {"change_pct": -0.3}}, lang=lang),
])
def test_english_findings_have_no_chinese_and_chinese_ones_are_kept(make):
    assert not CJK.search(_all(make("en"))), _all(make("en"))
    assert CJK.search(_all(make("zh")))


def test_the_risk_agent_lists_english_points():
    import asyncio

    agent = risk.RiskAgent(llm_provider=None, data_router=None, lang="en")
    data = {"quote": {"price": 331.8}, "metrics": {"ann_vol": 24.8, "max_dd": -13.8, "sharpe": 1.61}}
    result = asyncio.run(agent.analyze("AAPL", data))
    assert result.key_points and not CJK.search(_all(result.key_points)), result.key_points


def test_the_macro_template_claims_nothing_it_was_not_given():
    for lang in ("en", "zh"):
        text = macro._template_macro("AAPL", {}, lang=lang)
        assert "宽松" not in text and "流动性充裕" not in text and "accommodative" not in text


def test_the_synthesis_line_follows_the_language():
    import io

    from rich.console import Console

    from aria_code.ui.render.team import render_agent_synthesis_leaf

    console = Console(file=io.StringIO(), color_system=None)
    render_agent_synthesis_leaf(console, "HOLD", 0.45, 81.9, lang="en")
    assert "confidence 45%" in console.file.getvalue() and "took 81.9s" in console.file.getvalue()
