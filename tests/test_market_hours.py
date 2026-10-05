"""Market sessions are judged on the exchange's clock, not this machine's.

At 09:18 on Monday 2026-10-05 in Shanghai — Sunday 21:18 in New York — the
AAPL snapshot said "Market open", and the context sent to the model said the
US market was open from 09:30 to 16:00 Beijing time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aria_code.apps.cli.market_hours import exchange_for, market_session

BEIJING = timezone(timedelta(hours=8))


def at_beijing(*args):
    return datetime(*args, tzinfo=BEIJING)


@pytest.mark.parametrize("symbol, exchange", [
    ("AAPL", "US"), ("BRK-B", "US"), ("BRK.B", "US"), ("0700.HK", "HK"), ("600519", "CN"),
    ("000001.SZ", "CN"), ("SH600519", "CN"), ("7203.T", "JP"), ("MC.PA", "FR"), ("SAP.DE", "DE"),
    ("BTC-USD", "CRYPTO"), ("SOL-USDT", "CRYPTO"),
    ("^GSPC", None), ("EURUSD=X", None), ("GC=F", None), ("", None),
])
def test_the_exchange_follows_the_symbol(symbol, exchange):
    assert exchange_for(symbol) == exchange


@pytest.mark.parametrize("moment, session", [
    (at_beijing(2026, 10, 5, 9, 18), "closed"),     # Sunday 21:18 in New York
    (at_beijing(2026, 10, 5, 21, 0), "pre"),        # Monday 09:00 in New York
    (at_beijing(2026, 10, 5, 22, 0), "open"),       # Monday 10:00
    (at_beijing(2026, 10, 6, 4, 30), "post"),       # Monday 16:30
    (at_beijing(2026, 10, 6, 9, 0), "closed"),      # Monday 21:00
    (at_beijing(2026, 10, 10, 23, 0), "closed"),    # Saturday
])
def test_the_us_session_is_on_new_york_time(moment, session):
    assert market_session("AAPL", moment) == session


def test_daylight_saving_moves_the_us_open():
    # New York leaves daylight saving on 2026-11-01: the open moves from 21:30
    # to 22:30 Beijing time.
    assert market_session("AAPL", at_beijing(2026, 10, 30, 21, 45)) == "open"
    assert market_session("AAPL", at_beijing(2026, 11, 2, 21, 45)) == "pre"


def test_asian_lunch_breaks_and_hours():
    assert market_session("600519", at_beijing(2026, 10, 12, 10, 0)) == "open"
    assert market_session("600519", at_beijing(2026, 10, 12, 12, 0)) == "closed"
    assert market_session("600519", at_beijing(2026, 10, 12, 15, 30)) == "closed"
    assert market_session("0700.HK", at_beijing(2026, 10, 12, 15, 30)) == "open"
    assert market_session("0700.HK", at_beijing(2026, 10, 12, 12, 30)) == "closed"


def test_crypto_never_closes_and_unknown_says_nothing():
    assert market_session("BTC-USD", at_beijing(2026, 10, 10, 3, 0)) == "24/7"
    assert market_session("^GSPC", at_beijing(2026, 10, 12, 22, 0)) is None


def test_a_machine_without_the_time_zone_gets_no_answer(monkeypatch):
    import aria_code.apps.cli.market_hours as market_hours

    def missing(_name):
        raise LookupError("no tz database")

    monkeypatch.setattr(market_hours, "ZoneInfo", missing)
    assert market_session("AAPL", at_beijing(2026, 10, 12, 22, 0)) is None

