"""A schedule the customer can pay to exactly zero.

The rate is annual; interest accrues monthly. Rounding every payment to the
cent leaves a few cents over or under at the end — the last payment settles
them, so the books close at 0.00 and the principal column adds up.
"""

import pytest

from loan import schedule


def test_the_monthly_payment():
    rows = schedule(10000, 0.06, 12)
    assert len(rows) == 12
    assert rows[0][0] == pytest.approx(860.66)
    assert rows[0][1] == pytest.approx(50.00)


def test_the_balance_ends_at_zero():
    assert schedule(10000, 0.06, 12)[-1][3] == 0


def test_the_last_payment_settles_the_rounding():
    assert schedule(10000, 0.06, 12)[-1][0] == pytest.approx(860.70)


def test_principal_and_interest_add_up():
    rows = schedule(10000, 0.06, 12)
    assert sum(r[2] for r in rows) == pytest.approx(10000, abs=0.005)
    assert sum(r[1] for r in rows) == pytest.approx(327.96, abs=0.005)


def test_an_interest_free_loan():
    assert [r[0] for r in schedule(1000, 0, 3)] == pytest.approx([333.33, 333.33, 333.34])
