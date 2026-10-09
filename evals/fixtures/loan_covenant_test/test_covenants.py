"""Grades covenants.json: the 30 Sep 2026 covenant test (hidden from the agent).

Relevant Period = the four quarters to 2026-Q3. EBITDA before Exceptional
Items is 5,595; Exceptional Items are 1,630 but the add-back is capped at 10%
(559.5), so Consolidated EBITDA is 6,154.5. Total Net Debt includes lease
liabilities: 17,000 + 2,300 + 2,050 - 950 = 20,400. Leverage 3.31x breaches
the 3.25x limit; interest cover 5.86x complies.

The misreadings that matter most turn a breach into compliance:
    add-back uncapped        leverage 2.82  "compliant"
    lease liabilities left out  2.98        "compliant"
    Q3 annualised (x4)       leverage 3.43, cover 5.50
"""

import json
from pathlib import Path

import pytest

ANSWER = Path(__file__).with_name("covenants.json")


def _answer():
    assert ANSWER.exists(), "covenants.json was not written"
    return json.loads(ANSWER.read_text(encoding="utf-8"))


def test_consolidated_ebitda():
    assert float(_answer()["consolidated_ebitda"]) == pytest.approx(6154.5, abs=0.6)


def test_total_net_debt_includes_leases():
    assert float(_answer()["total_net_debt"]) == pytest.approx(20400, abs=0.6)


def test_leverage_ratio():
    assert float(_answer()["leverage"]) == pytest.approx(3.31, abs=0.005)


def test_interest_cover():
    assert float(_answer()["interest_cover"]) == pytest.approx(5.86, abs=0.005)


def test_the_leverage_covenant_is_breached():
    assert _answer()["leverage_compliant"] is False


def test_the_interest_cover_covenant_is_met():
    assert _answer()["interest_cover_compliant"] is True
