"""Booking against the dock's real free time.

Back-to-back windows are one window — a 2-hour unload fits across them.
Night shifts run past midnight, and the roster spreadsheet drops leading
zeros, so "9:00" sorts after "10:00" as text.
"""

import pytest

from windows import merge_windows


def test_overlapping_windows_merge():
    assert merge_windows([("08:00", "10:00"), ("09:30", "11:00")]) == [("08:00", "11:00")]


def test_touching_windows_merge():
    assert merge_windows([("08:00", "10:00"), ("10:00", "12:00")]) == [("08:00", "12:00")]


def test_times_without_a_leading_zero():
    got = merge_windows([("9:00", "9:30"), ("10:00", "11:00"), ("8:00", "9:15")])
    assert got == [("08:00", "09:30"), ("10:00", "11:00")]


def test_a_night_shift_crosses_midnight():
    got = merge_windows([("22:00", "02:00"), ("01:00", "03:00"), ("12:00", "13:00")])
    assert got == [("00:00", "03:00"), ("12:00", "13:00"), ("22:00", "24:00")]


def test_not_a_time_of_day():
    with pytest.raises(ValueError):
        merge_windows([("25:00", "26:00")])
