"""Grades eur_totals.json: each invoice in EUR at the rate on its own date.

rates.csv quotes EURxxx — units of the currency per one euro — so a USD
amount is divided by EURUSD, not multiplied. There are no rates for the
weekend: F-203 (Saturday) uses Friday's, the last one published before it,
never Monday's. An EUR invoice is already in euros.
"""

import json
from pathlib import Path

import pytest

TOTALS = Path(__file__).with_name("eur_totals.json")

EXPECTED = {
    "F-201": 5000.00, "F-202": 2470.59, "F-203": 990.83, "F-204": 950.00,
    "F-205": 4687.50, "F-206": 1000.00, "F-207": 2465.75,
}


def _totals():
    assert TOTALS.exists(), "eur_totals.json was not written"
    return json.loads(TOTALS.read_text(encoding="utf-8"))


def _invoice(no):
    invoices = _totals().get("invoices") or {}
    assert no in invoices, f"{no} is missing"
    return float(invoices[no])


@pytest.mark.parametrize("no", sorted(EXPECTED))
def test_invoice_in_eur(no):
    assert _invoice(no) == pytest.approx(EXPECTED[no], abs=0.01)


def test_a_weekend_invoice_uses_the_last_rate_before_it():
    assert _invoice("F-203") == pytest.approx(990.83, abs=0.01)


def test_the_total():
    assert float(_totals()["total_eur"]) == pytest.approx(17564.67, abs=0.05)
