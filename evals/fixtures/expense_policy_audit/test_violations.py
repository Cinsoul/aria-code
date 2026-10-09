"""Grades violations.json against travel_policy.md (hidden from the agent).

Right answer: 131.18 USD disallowed across six items. Each misreading moves it:
    ignoring Amendment 2026-A (HK still Tier 2 after 15 Sep)    256.04
    applying it from the start (HK Tier 1 on 10 Sep)              76.84
    meal limits per item instead of per employee per day         103.95
    receipt threshold on the claimed currency, not USD           104.26  (E-07: GBP 35 = USD 44.10)
"""

import json
from pathlib import Path

import pytest

ANSWER = Path(__file__).with_name("violations.json")

EXPECTED = {"E-02": 17.17, "E-03": 37.17, "E-05": 2.56, "E-07": 44.10, "E-10": 22.68, "E-13": 7.50}


def _answer():
    assert ANSWER.exists(), "violations.json was not written"
    data = json.loads(ANSWER.read_text(encoding="utf-8"))
    items = {str(k).upper(): float(v) for k, v in (data.get("disallowed") or {}).items() if float(v) > 0}
    return items, data


def test_exactly_the_disallowed_items():
    items, _ = _answer()
    assert set(items) == set(EXPECTED)


@pytest.mark.parametrize("expense", sorted(EXPECTED))
def test_amount_disallowed(expense):
    items, _ = _answer()
    assert items.get(expense) == pytest.approx(EXPECTED[expense], abs=0.01)


def test_total():
    _, data = _answer()
    assert float(data["total_disallowed_usd"]) == pytest.approx(131.18, abs=0.02)


def test_the_amendment_applies_from_its_date_only():
    items, _ = _answer()
    assert "E-03" in items and "E-06" not in items


def test_limits_apply_to_converted_amounts():
    items, _ = _answer()
    assert items.get("E-07") == pytest.approx(44.10, abs=0.01) and "E-09" not in items
