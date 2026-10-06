"""/portfolio in an English session, with the model the session is set up for.

A live English /portfolio on a Gemini session printed its whole report in
Chinese, asked Ollama (not running) instead of Gemini and showed the
connection error as a raw WARNING log line, then labelled the result both
NEEDS_ATTENTION and HIGH_RISK: the signal maps NEEDS_ATTENTION to SELL, and the
banner turned SELL into HIGH_RISK. The HIGH_RISK icon, an emoji, drew as an
empty box.
"""

from __future__ import annotations

import asyncio
import logging
import re
from types import SimpleNamespace

# The bare root: cmd_portfolio imports agents.portfolio_agent.
from agents.portfolio_agent import PortfolioAgent, _build_key_points, _template_analysis
from aria_code.ui.render.team import VERDICT_STYLE, build_verdict_body

CJK = re.compile(r"[一-鿿，：（）]")

STATS = {
    "valid_symbols": ["AAPL", "MSFT", "NVDA"], "weight_source": "equal", "port_vol_ann": 0.22,
    "div_ratio": 1.57, "high_corr": [{"sym1": "AAPL", "sym2": "MSFT", "corr": 0.74}],
}


def test_key_points_and_template_follow_the_language():
    english = _build_key_points(STATS, "NEEDS_ATTENTION", "en")
    assert english[0].startswith("3 symbols, equal weight")
    assert "Overall: NEEDS_ATTENTION" in english
    assert not CJK.findall(" ".join(english))
    assert not CJK.findall(_template_analysis(["AAPL", "MSFT", "NVDA"], STATS, "en"))
    assert "整体评级: NEEDS_ATTENTION" in _build_key_points(STATS, "NEEDS_ATTENTION")


class _ErrorEvent:
    async def stream(self, *args, **kwargs):
        yield {"type": "error", "message": "Ollama connection failed"}


class _Unreachable:
    async def stream(self, *args, **kwargs):
        raise ConnectionError("Cannot connect to host localhost:11434")
        yield  # pragma: no cover


def test_a_failed_model_call_is_recorded_not_logged_as_a_warning(caplog):
    for llm in (_ErrorEvent(), _Unreachable()):
        agent = PortfolioAgent(llm_provider=llm, lang="en")
        with caplog.at_level(logging.WARNING):
            assert asyncio.run(agent._call_llm("system", "user")) == ""
        assert agent.llm_error
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_the_verdict_travels_with_the_result():
    agent = PortfolioAgent(llm_provider=None, lang="en")
    result = asyncio.run(agent.analyze_portfolio(["AAPL", "MSFT", "NVDA"], dict(STATS)))
    assert result.data_used["verdict"] == "NEEDS_ATTENTION"
    assert result.signal == "SELL"          # the signal alone would have read as HIGH_RISK
    assert not CJK.findall(" ".join(result.key_points))


def test_too_few_symbols_is_explained_in_english():
    result = asyncio.run(PortfolioAgent(lang="en").analyze_portfolio(["AAPL"], {}))
    assert result.analysis == "A portfolio analysis needs at least 2 symbols."


def test_the_banner_uses_text_glyphs_and_the_language():
    for _style, icon in VERDICT_STYLE.values():
        assert all(ord(ch) < 0x2700 or 0x2700 <= ord(ch) <= 0x27BF for ch in icon), icon
        assert "️" not in icon
    assert "confidence 65%" in build_verdict_body("HIGH_RISK", "", 0.65, "en")
    assert "置信度 65%" in build_verdict_body("HIGH_RISK", "", 0.65)


def test_portfolio_uses_the_configured_model_and_the_session_language(monkeypatch, capsys):
    import aria_code.apps.cli.commands.portfolio_cmds as portfolio_cmds
    import aria_code.apps.cli.commands.team as team

    seen = {}

    def provider(config):
        seen["config"] = config
        return None

    banners = []
    monkeypatch.setattr(team, "build_team_llm_provider", provider)
    monkeypatch.setattr(portfolio_cmds, "_print_verdict_banner",
                        lambda verdict, **kw: banners.append((verdict, kw.get("lang"))))

    async def run_portfolio(self, symbols, weights=None):
        seen["lang"] = self.lang
        return await self.analyze_portfolio(symbols, dict(STATS))

    monkeypatch.setattr(PortfolioAgent, "run_portfolio", run_portfolio)

    printed = []
    console = SimpleNamespace(print=lambda *a, **k: printed.append(" ".join(str(x) for x in a)))
    config = {"ui_lang": "en", "model": "gemini-2.5-pro"}

    class Cli(portfolio_cmds.PortfolioCommandsMixin):
        context = SimpleNamespace(has_rich=True, console=console)
        terminal = SimpleNamespace(config=config)

    asyncio.run(Cli().cmd_portfolio("analyze AAPL MSFT NVDA"))
    assert seen == {"config": config, "lang": "en"}
    assert banners == [("NEEDS_ATTENTION", "en")]
    assert not CJK.findall("\n".join(printed)), printed
