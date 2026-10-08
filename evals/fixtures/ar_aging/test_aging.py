"""Grades aging.json: receivables as they stood at close of 30 September 2026.

The books are closed for September, so anything dated after the 30th belongs
to October: INV-108 had not been issued and CONTOSO's 3 October payment had
not been received. Days overdue count from the due date: due on the 30th is
current, 30 days overdue is still 1-30, 91 is 90+.
"""

import json
from pathlib import Path

import pytest

AGING = Path(__file__).with_name("aging.json")
BUCKETS = ("current", "1-30", "31-60", "61-90", "90+")

EXPECTED = {
    "NORTHWIND": {"current": 3100.00, "1-30": 960.00, "31-60": 1000.00, "61-90": 0, "90+": 0},
    "CONTOSO": {"current": 0, "1-30": 3450.00, "31-60": 0, "61-90": 0, "90+": 5000.00},
    "FABRIKAM": {"current": 1450.00, "1-30": 0, "31-60": 0, "61-90": 2000.00, "90+": 2300.00},
}


def _aging():
    assert AGING.exists(), "aging.json was not written"
    data = json.loads(AGING.read_text(encoding="utf-8"))
    return {str(k).upper(): v for k, v in data.items()}


def _bucket(customer, bucket):
    row = _aging().get(customer)
    assert row is not None, f"{customer} is missing"
    return float(row.get(bucket, 0) or 0)


@pytest.mark.parametrize("customer", sorted(EXPECTED))
def test_every_bucket(customer):
    got = {b: _bucket(customer, b) for b in BUCKETS}
    assert got == pytest.approx(EXPECTED[customer], abs=0.01)


def test_a_payment_after_month_end_is_not_applied():
    assert _bucket("CONTOSO", "90+") == pytest.approx(5000.00, abs=0.01)


def test_an_invoice_issued_after_month_end_is_not_counted():
    total = sum(_bucket("CONTOSO", b) for b in BUCKETS)
    assert total == pytest.approx(8450.00, abs=0.01)


def test_thirty_days_overdue_is_still_one_to_thirty():
    assert _bucket("CONTOSO", "1-30") == pytest.approx(3450.00, abs=0.01)
