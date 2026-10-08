"""Grades duties.json: import duty per shipment, in EUR.

The de minimis threshold applies to a shipment's total value in EUR: 150 or
less pays nothing, and above it every line pays. Split per line, every
shipment here would look exempt. A line takes the rate of the longest
matching HS prefix (8471 is 0%, though 84 is 1.7%).
"""

import json
from pathlib import Path

import pytest

DUTIES = Path(__file__).with_name("duties.json")

EXPECTED = {"S1": 2.96, "S2": 0.00, "S3": 0.00, "S4": 12.32, "S5": 0.00}


def _duties():
    assert DUTIES.exists(), "duties.json was not written"
    return {str(k).upper(): float(v) for k, v in json.loads(DUTIES.read_text(encoding="utf-8")).items()}


@pytest.mark.parametrize("shipment", sorted(EXPECTED))
def test_duty(shipment):
    duties = _duties()
    assert shipment in duties, f"{shipment} is missing"
    assert duties[shipment] == pytest.approx(EXPECTED[shipment], abs=0.01)


def test_the_threshold_is_per_shipment_not_per_line():
    assert _duties()["S4"] > 0


def test_the_longest_hs_prefix_wins():
    assert _duties()["S3"] == pytest.approx(0.0, abs=0.01)
