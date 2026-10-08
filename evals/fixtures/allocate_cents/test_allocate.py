"""Every cent of a settlement ends up with someone, exactly once.

Rounding each share on its own loses or invents cents: three-way splits of a
dollar come to 99. A refund is a negative total and is split the same way.
"""

import random

import pytest

from allocate import allocate


def test_an_even_split():
    assert allocate(1000, [1, 1]) == [500, 500]


def test_a_dollar_three_ways():
    assert allocate(100, [1, 1, 1]) == [34, 33, 33]


def test_the_leftover_cent_goes_to_the_largest_remainder():
    # Exact shares: 5000.5, 3000.3, 2000.2
    assert allocate(10001, [50, 30, 20]) == [5001, 3000, 2000]


def test_ties_go_to_the_earlier_shares():
    assert allocate(5, [1] * 7) == [1, 1, 1, 1, 1, 0, 0]


def test_a_refund_mirrors_a_charge():
    assert allocate(-100, [1, 1, 1]) == [-34, -33, -33]


def test_shares_always_add_up():
    rng = random.Random(7)
    for _ in range(500):
        total = rng.randint(-10**7, 10**7)
        weights = [rng.randint(0, 1000) for _ in range(rng.randint(1, 9))]
        if not any(weights):
            weights[0] = 1
        shares = allocate(total, weights)
        assert sum(shares) == total
        assert all(isinstance(s, int) for s in shares)


def test_bad_weights_are_rejected():
    with pytest.raises(ValueError):
        allocate(100, [0, 0])
    with pytest.raises(ValueError):
        allocate(100, [2, -1])
