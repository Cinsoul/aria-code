"""Grades disputes.json: the invoice lines SwiftLine overbilled, against contract.md.

Hidden from the agent: it works from the contract. What the contract says, and
what each wrong reading of it does:

    SL4410002, SL4410012  billed on a 5,000 divisor; the contract's is 6,000   12.60, 10.95
    SL4410005             zone A residential surcharge after Amendment 1 (1 Oct)   3.50
    SL4410006             fuel surcharge charged on the residential surcharge      0.49
    SL4410008             base above the 9.00 minimum the contract sets            1.20
    SL4410009             October fuel at 15.5%; the schedule says 14.0%           0.84

Not disputes, and each one a trap:
    SL4410004  zone A residential on 29 Sep: the amendment is not yet in force
    SL4410010  1.1 kg rounds UP to 1.5 kg; rounding to nearest makes it look overbilled
    SL4410011  underbilled by the carrier; the shipper disputes overbilling only
"""

import json
from pathlib import Path

import pytest

ANSWER = Path(__file__).with_name("disputes.json")

EXPECTED = {
    "SL4410002": 12.60, "SL4410005": 3.50, "SL4410006": 0.49,
    "SL4410008": 1.20, "SL4410009": 0.84, "SL4410012": 10.95,
}


def _answer():
    assert ANSWER.exists(), "disputes.json was not written"
    data = json.loads(ANSWER.read_text(encoding="utf-8"))
    return {str(r["waybill"]): float(r["difference"]) for r in data.get("overbilled") or []}, data


def test_exactly_the_overbilled_lines():
    got, _ = _answer()
    assert set(got) == set(EXPECTED)


@pytest.mark.parametrize("waybill", sorted(EXPECTED))
def test_amount_overbilled(waybill):
    got, _ = _answer()
    assert got.get(waybill) == pytest.approx(EXPECTED[waybill], abs=0.01)


def test_total():
    _, data = _answer()
    assert float(data["total_overbilled"]) == pytest.approx(29.58, abs=0.02)


def test_the_amendment_is_not_applied_before_it_takes_effect():
    got, _ = _answer()
    assert "SL4410004" not in got


def test_chargeable_weight_rounds_up():
    got, _ = _answer()
    assert "SL4410010" not in got
