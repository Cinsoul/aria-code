"""Capital calls and distributions land on real dates, not once a year.

A fund that returns 5% in six months has earned about 10% a year. Treating
each cash flow as one period apart reports something else entirely.
"""

from datetime import date

import pytest

from cashflows import xirr


def test_one_year_exactly():
    assert xirr([(date(2026, 1, 1), -1000), (date(2027, 1, 1), 1100)]) == pytest.approx(0.10, abs=1e-6)


def test_half_a_year():
    flows = [(date(2026, 1, 1), -1000), (date(2026, 7, 2), 1050)]
    assert xirr(flows) == pytest.approx(1.05 ** (365 / 182) - 1, abs=1e-6)


def test_several_flows_in_any_order():
    flows = [
        (date(2026, 3, 15), 300),
        (date(2026, 1, 10), -1000),
        (date(2026, 9, 30), -500),
        (date(2027, 2, 1), 1400),
    ]
    assert xirr(flows) == pytest.approx(0.2076015909, abs=1e-6)


def test_no_sign_change_has_no_rate():
    with pytest.raises(ValueError):
        xirr([(date(2026, 1, 1), -100), (date(2026, 6, 1), -50)])
