"""Retry what can succeed next time, and nothing else.

A 400 or a parsing bug retried three times is three times as slow and hides
the real error behind "gave up". After the last attempt there is nothing left
to wait for.
"""

import pytest

from fetch import with_retries


class Flaky:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_recovers_from_transient_failures():
    sleeps = []
    call = Flaky(ConnectionError(), TimeoutError(), "ok")
    assert with_retries(call, sleep=sleeps.append) == "ok"
    assert sleeps == [0.5, 1.0]


def test_a_bad_request_is_not_retried():
    sleeps = []
    call = Flaky(ValueError("bad tracking number"), "ok")
    with pytest.raises(ValueError, match="bad tracking number"):
        with_retries(call, sleep=sleeps.append)
    assert call.calls == 1
    assert sleeps == []


def test_gives_up_with_the_last_error_and_no_final_wait():
    sleeps = []
    call = Flaky(TimeoutError("1"), TimeoutError("2"), TimeoutError("3"))
    with pytest.raises(TimeoutError, match="3"):
        with_retries(call, attempts=3, sleep=sleeps.append)
    assert call.calls == 3
    assert sleeps == [0.5, 1.0]


def test_at_least_one_attempt():
    with pytest.raises(ValueError):
        with_retries(lambda: "ok", attempts=0, sleep=lambda _s: None)
