"""Grades sla_credit.json against service_agreement.md (hidden from the agent).

October 2026: 56 orders count, 53 on time, 94.64%, so a 10% credit, HKD 12,000.
Each misreading moves at least one number:
    1 and 19 Oct treated as Business Days        47 on time, 83.93%
    "by 14:00" read as "before 14:00"            54 on time, 96.43%, credit 5%
    the typhoon day not excluded                 58 orders, 94.83%
    held orders counted                          58 orders, 93.10%
    a weekend order keeping its clock time       54 on time, 96.43%, credit 5%
"""

import json
from pathlib import Path

import pytest

ANSWER = Path(__file__).with_name("sla_credit.json")


def _answer():
    assert ANSWER.exists(), "sla_credit.json was not written"
    return json.loads(ANSWER.read_text(encoding="utf-8"))


def test_orders_counted():
    assert int(_answer()["eligible_orders"]) == 56


def test_orders_on_time():
    assert int(_answer()["on_time"]) == 53


def test_on_time_rate():
    pct = float(_answer()["on_time_pct"])
    assert (pct * 100 if pct <= 1 else pct) == pytest.approx(94.64, abs=0.005)


def test_credit():
    data = _answer()
    assert float(data["credit_pct"]) in (10, 0.10)
    assert float(data["credit_hkd"]) == pytest.approx(12000, abs=0.5)
