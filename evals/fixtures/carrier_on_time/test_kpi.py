"""Grades kpi.json: on-time delivery per carrier for September 2026.

The scan feed repeats rows (D-003, D-010, D-020 appear more than once); a
shipment counts once. Cancelled shipments are not deliveries. A shipment
still in transit after its promised date has already missed it and counts as
late; one still in transit before its promised date is not counted yet.
Delivered on the promised date is on time.
"""

import json
from pathlib import Path

import pytest

KPI = Path(__file__).with_name("kpi.json")

EXPECTED = {"SWIFT": (5, 0.6), "HARBOR": (5, 0.6), "TERRA": (6, 5 / 6)}


def _kpi():
    assert KPI.exists(), "kpi.json was not written"
    data = json.loads(KPI.read_text(encoding="utf-8"))
    return {str(k).upper(): v for k, v in data.items()}


def _rate(carrier):
    row = _kpi().get(carrier)
    assert row is not None, f"{carrier} is missing"
    rate = float(row["on_time_rate"])
    return rate / 100 if rate > 1 else rate


@pytest.mark.parametrize("carrier", sorted(EXPECTED))
def test_on_time_rate(carrier):
    assert _rate(carrier) == pytest.approx(EXPECTED[carrier][1], abs=0.001)


@pytest.mark.parametrize("carrier", sorted(EXPECTED))
def test_shipments_counted_once_cancellations_excluded(carrier):
    assert int(_kpi()[carrier]["shipments"]) == EXPECTED[carrier][0]


def test_an_overdue_parcel_in_transit_is_late():
    # SWIFT is 0.8 if D-005 (due 25 Sep, not delivered) is left out.
    assert _rate("SWIFT") == pytest.approx(0.6, abs=0.001)
