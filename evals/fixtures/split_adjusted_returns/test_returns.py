"""Grades returns.json: price return of each holding, 30 Jun to 30 Sep 2026.

NOVA split 4-for-1 and ORBT did a 1-for-10 reverse split during the quarter.
Comparing raw closes reports NOVA down 70% and ORBT up 980%; neither moved
that much. Adjusted, NOVA returned 18%, ORBT 8%, PIKE (no split) 6%.
"""

import json
from pathlib import Path

import pytest

RETURNS = Path(__file__).with_name("returns.json")

EXPECTED = {"NOVA": 0.18, "ORBT": 0.08, "PIKE": 0.06}


def _returns():
    assert RETURNS.exists(), "returns.json was not written"
    data = json.loads(RETURNS.read_text(encoding="utf-8"))
    return {str(k).upper(): v for k, v in data.items()}


def _fraction(symbol):
    value = _returns().get(symbol)
    assert value is not None, f"{symbol} is missing"
    value = float(value)
    # Accept 0.18 or 18 (a percent); nothing in this book is a real 18x.
    return value / 100 if abs(value) > 2 else value


@pytest.mark.parametrize("symbol", sorted(EXPECTED))
def test_return(symbol):
    assert _fraction(symbol) == pytest.approx(EXPECTED[symbol], abs=0.0005)


def test_a_forward_split_is_not_a_crash():
    assert _fraction("NOVA") > 0

