"""A numeric code with an exchange suffix is one listing, not a bare ticker.

"0700.HK 行情" was quoted as the symbol HK, "7203.T price" as T (AT&T), and
"600519.SS" became a comparison of 600519 with a stock called SS — though
Aria's own hints tell users to type `/quote 0700.HK`. The HK lookup then
failed with yfinance's bare KeyError, shown as "'currentTradingPeriod'".
"""

from __future__ import annotations

import pytest

import aria_code.apps.cli.handlers.market_handlers as market_handlers
from aria_code.apps.cli.utils.market_detect import _extract_market_symbol, _extract_market_symbols


@pytest.mark.parametrize("question, symbol, symbols", [
    ("0700.HK 行情", "0700.HK", ["0700.HK"]),
    ("0700.hk price", "0700.HK", ["0700.HK"]),
    ("00700.HK", "0700.HK", ["0700.HK"]),
    ("7203.T price", "7203.T", ["7203.T"]),
    ("2330.TW price", "2330.TW", ["2330.TW"]),
    ("compare 0700.HK and 9988.HK", "0700.HK", ["0700.HK", "9988.HK"]),
    ("AAPL vs 0700.HK price", "0700.HK", ["AAPL", "0700.HK"]),
    ("600519.SS", "600519", ["600519"]),
    ("sh600519 vs 000001.SZ", "600519", ["600519", "000001"]),
])
def test_a_coded_listing_is_one_symbol(question, symbol, symbols):
    assert _extract_market_symbol(question) == symbol
    assert _extract_market_symbols(question) == symbols


def test_letters_alone_are_still_tickers():
    assert _extract_market_symbol("分析AAPL") == "AAPL"
    assert _extract_market_symbols("AAPL vs MSFT") == ["AAPL", "MSFT"]


class _NoChart:
    def quote(self, symbol):
        return {"success": False, "error": "'currentTradingPeriod'"}


def test_a_bare_key_error_is_not_shown_to_the_user(monkeypatch):
    real_import = __import__

    def no_yfinance(name, *args, **kwargs):
        if name == "yfinance":
            raise ImportError("offline")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_yfinance)
    monkeypatch.setattr(market_handlers, "_has_mdc_lazy", lambda: True)
    monkeypatch.setattr(market_handlers, "_get_mdc_lazy", lambda: _NoChart())
    monkeypatch.setattr(market_handlers, "_get_provider_key", lambda _provider: "")
    text = market_handlers._try_handle_market_snapshot_analysis("HKX price")["response"]
    assert "currentTradingPeriod" not in text
    assert "the data source returned no valid price" in text
