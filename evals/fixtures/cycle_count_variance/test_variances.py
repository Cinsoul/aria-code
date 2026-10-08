"""Grades variances.json: count differences, in eaches, where we counted.

Counters record cases and bundles; the system holds eaches (uom.csv says
how many). A location nobody counted this cycle is not a variance. Stock
found where the system has none is.
"""

import json
from pathlib import Path

VARIANCES = Path(__file__).with_name("variances.json")

EXPECTED = {
    ("A-02-1", "BOX-S"): (500, 480, -20),
    ("A-02-2", "BOX-S"): (0, 25, 25),
    ("B-01-1", "TAPE"): (120, 118, -2),
}


def _rows():
    assert VARIANCES.exists(), "variances.json was not written"
    rows = json.loads(VARIANCES.read_text(encoding="utf-8"))
    assert isinstance(rows, list), "variances.json should be a list of rows"
    return {(r["location"], r["sku"]): (int(r["system"]), int(r["counted"]), int(r["variance"]))
            for r in rows}


def test_every_variance_and_nothing_else():
    assert _rows() == EXPECTED


def test_cases_are_counted_as_eaches():
    assert ("A-01-1", "TAPE") not in _rows()


def test_uncounted_locations_are_not_reported():
    rows = _rows()
    assert ("B-01-2", "LABEL") not in rows
    assert ("B-02-1", "GLUE") not in rows
