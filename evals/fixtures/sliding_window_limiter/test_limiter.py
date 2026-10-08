"""The carrier counts any 10 seconds, not 10-second blocks.

A fixed window lets a burst at the end of one block and another at the
start of the next through together — twice the limit, and a 429.
"""

import pytest

from limiter import RateLimiter


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_the_limit_holds_within_a_window():
    clock = Clock()
    rl = RateLimiter(3, 10, clock)
    assert [rl.allow() for _ in range(4)] == [True, True, True, False]


def test_no_burst_across_a_window_boundary():
    clock = Clock()
    rl = RateLimiter(3, 10, clock)
    assert rl.allow()
    clock.now = 9.0
    assert rl.allow() and rl.allow()
    clock.now = 10.5          # the call at 0 has expired; the two at 9 have not
    assert rl.allow() is True
    assert rl.allow() is False


def test_refused_calls_do_not_count():
    clock = Clock()
    rl = RateLimiter(3, 10, clock)
    assert all(rl.allow() for _ in range(3))
    clock.now = 5.0
    assert not rl.allow() and not rl.allow()
    clock.now = 10.0
    assert [rl.allow() for _ in range(4)] == [True, True, True, False]


def test_bad_settings_are_rejected():
    with pytest.raises(ValueError):
        RateLimiter(0, 10)
    with pytest.raises(ValueError):
        RateLimiter(3, 0)
