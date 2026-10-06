"""/compare runs the strategies it names, over the dates it shows, against a real buy-and-hold.

/compare AAPL MSFT read MSFT as the start date. The local fallback asked the
engine for mean_reversion, breakout, turtle and ma_crossover, names it did not
have, and the engine ran buy-and-hold for each: four identical rows. /peer,
where a stock comparison belongs, showed AAPL's dividend yield as 32% and
compared AAPL with a "peer median" that was AAPL's own PE.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import aria_code.apps.cli.commands.data_cmds as data_cmds
from aria_code.tools import local_finance_tools as lft


def test_an_unknown_strategy_is_refused_not_run_as_buy_and_hold():
    result = lft._backtest_strategy({"symbol": "AAPL", "strategy": "turtle"})
    assert result["success"] is False and "Unknown strategy 'turtle'" in result["error"]
    assert "sma_cross" in result["error"]


@pytest.mark.parametrize("name, runs", [("ma_crossover", "sma_cross"), ("mean_reversion", "rsi_mean_revert"),
                                        ("momentum", "momentum"), ("buy_and_hold", "buy_hold")])
def test_the_names_compare_uses_reach_real_strategies(name, runs):
    assert lft._LOCAL_STRATEGIES[name] == runs


@pytest.mark.parametrize("info, expected", [
    ({"trailingAnnualDividendYield": 0.0031, "dividendYield": 0.32}, 0.31),
    ({"dividendYield": 0.32, "dividendRate": 1.04, "regularMarketPrice": 325.0}, 0.32),
    ({"dividendYield": 0.32}, None),
])
def test_dividend_yield_is_a_percentage_once(info, expected):
    got = lft._dividend_yield_pct(info)
    assert (got is None) if expected is None else round(got, 2) == expected


class _Console:
    def __init__(self):
        self.lines = []

    def print(self, *parts, **_):
        self.lines.append(" ".join(str(p) for p in parts))

    def status(self, *_a, **_k):
        import contextlib
        return contextlib.nullcontext()


def _cli(lang="en"):
    class Cli(data_cmds.DataCommandsMixin):
        pass

    cli = Cli()
    cli.context = SimpleNamespace(has_rich=True, console=_Console())
    cli.terminal = SimpleNamespace(config={"ui_lang": lang, "api_url": "http://127.0.0.1:9"})
    return cli


def test_two_symbols_go_to_peer(monkeypatch):
    cli = _cli()
    seen = []

    async def peer(args):
        seen.append(args)

    cli.cmd_peer = peer
    asyncio.run(cli.cmd_compare("AAPL msft GOOGL"))
    assert seen == ["AAPL MSFT GOOGL"]
    assert any("→ /peer AAPL MSFT GOOGL" in line for line in cli.context.console.lines)


def test_a_bad_date_is_named(monkeypatch):
    errors = []
    monkeypatch.setattr(data_cmds, "print_error", lambda _ctx, msg, hint="": errors.append(msg))
    cli = _cli()
    asyncio.run(cli.cmd_compare("AAPL 2024-13-01"))
    assert errors == ["Not a date: 2024-13-01"]


def test_the_local_fallback_runs_real_strategies_over_the_asked_dates(monkeypatch):
    calls = []

    def fake_backtest(params):
        calls.append(params)
        base = {"momentum": 0.18, "rsi_mean_revert": 0.14, "sma_cross": 0.21, "buy_hold": 0.42}[params["strategy"]]
        return {"success": True, "data": {"annual_return": base, "max_drawdown": -0.15, "sharpe_ratio": base * 5,
                                          "total_trades": 3, "win_rate": 0.5,
                                          "start": "2023-01-03", "end": "2024-12-31"}}

    monkeypatch.setattr(data_cmds, "_get_LOCAL_TOOLS", lambda: {"backtest_strategy": (fake_backtest, "")})
    cli = _cli()
    asyncio.run(cli.cmd_compare("AAPL 2023-01-01 2025-01-01"))
    assert {c["strategy"] for c in calls} == {"momentum", "rsi_mean_revert", "sma_cross", "buy_hold"}
    assert all(c["start"] == "2023-01-01" and c["end"] == "2025-01-01" for c in calls)
    printed = "\n".join(cli.context.console.lines)
    assert "breakout, turtle need the backend" in printed


def test_peer_statistics_leave_the_target_out(monkeypatch):
    infos = {
        "AAPL": {"trailingPE": 38.1, "returnOnEquity": 1.488, "shortName": "Apple", "marketCap": 4.8e12,
                 "regularMarketPrice": 325.0, "sector": "Technology"},
        "MSFT": {"trailingPE": 29.7, "returnOnEquity": 0.34, "shortName": "Microsoft", "marketCap": 3.9e12,
                 "regularMarketPrice": 500.0},
        "GOOGL": {"trailingPE": 17.4, "returnOnEquity": 0.487, "shortName": "Alphabet", "marketCap": 4.2e12,
                  "regularMarketPrice": 250.0},
    }
    monkeypatch.setattr(lft, "yf", SimpleNamespace(Ticker=lambda s: SimpleNamespace(info=infos[s])), raising=False)
    monkeypatch.setattr(lft, "_HAS_YF", True, raising=False)
    result = lft._peer_comparison({"symbol": "AAPL", "peers": ["MSFT", "GOOGL"], "lang": "en"})
    # The median of MSFT and GOOGL (23.55), not AAPL's own 38.1.
    assert result["analysis"][0] == f"PE 38.1x vs peer median {(29.7 + 17.4) / 2:.1f}x → above peers"
    assert "peer average 41.4%" in result["analysis"][1]
