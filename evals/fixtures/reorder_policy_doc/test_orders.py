"""Grades orders.json against replenishment_policy.md (hidden from the agent).

Each trap moves a number:
    all 42 days instead of the latest 28     NG-101 300 (right: 192)
    one service level for every class         NG-107 192 (right: 216, class A)
    no case-pack rounding / MOQ               NG-101 191, NG-103 140, NG-107 193, NG-108 67
    ordering a discontinued SKU               NG-105 336 (right: never ordered)
    a number for 10 days of history           NG-106 must be "insufficient_history"
"""

import json
from pathlib import Path

import pytest

ANSWER = Path(__file__).with_name("orders.json")

EXPECTED = {"NG-101": 192, "NG-102": 0, "NG-103": 144, "NG-104": 0, "NG-107": 216, "NG-108": 72}


def _orders():
    assert ANSWER.exists(), "orders.json was not written"
    return {str(k).upper(): v for k, v in json.loads(ANSWER.read_text(encoding="utf-8")).items()}


def _qty(value):
    if isinstance(value, dict):
        value = value.get("order_qty", value.get("quantity", value.get("qty")))
    return value


@pytest.mark.parametrize("sku", sorted(EXPECTED))
def test_order_quantity(sku):
    orders = _orders()
    assert sku in orders, f"{sku} is missing"
    assert int(_qty(orders[sku])) == EXPECTED[sku]


def test_only_the_latest_28_days_count():
    assert int(_qty(_orders()["NG-101"])) == 192


def test_the_service_level_follows_the_abc_class():
    assert int(_qty(_orders()["NG-107"])) == 216


def test_a_discontinued_sku_is_never_ordered():
    value = _orders().get("NG-105", 0)
    assert value in (0, None) or _qty(value) in (0, None)


def test_thin_history_is_flagged_not_guessed():
    value = _orders().get("NG-106")
    if isinstance(value, dict):
        value = value.get("status")
    assert value == "insufficient_history"
