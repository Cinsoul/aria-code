"""A drawdown is a fall from an earlier high; a year is 252 returns.

The trough has to come after the peak it is measured from: a series that only
goes up has no drawdown, however low it started. 253 daily closes span 252
daily returns, one trading year.
"""

import pytest

from perf import annualized_return, max_drawdown


def test_the_fall_after_the_high_counts():
    assert max_drawdown([100, 80, 120, 90]) == pytest.approx(0.25)


def test_an_earlier_fall_can_be_the_largest():
    assert max_drawdown([100, 50, 200, 150]) == pytest.approx(0.5)


def test_a_rising_series_has_no_drawdown():
    assert max_drawdown([100, 110, 121]) == 0


def test_one_year_of_closes():
    closes = [100.0] * 252 + [110.0]
    assert annualized_return(closes) == pytest.approx(0.10, abs=1e-12)


def test_two_years_of_closes():
    closes = [100.0] * 504 + [121.0]
    assert annualized_return(closes) == pytest.approx(0.10, abs=1e-12)


def test_too_short_to_have_a_return():
    with pytest.raises(ValueError):
        annualized_return([100.0])
    with pytest.raises(ValueError):
        max_drawdown([])
