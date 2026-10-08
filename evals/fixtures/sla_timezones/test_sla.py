"""A promise made in Frankfurt and kept in Chicago is compared in one clock.

Cutting the offset off a timestamp turns 17:30 UTC into 12:30 and a late
parcel into an early one. A timestamp without an offset could be any time
and is refused rather than guessed.
"""

import pytest

from sla import hours_late, late_shipments


def test_same_zone():
    assert hours_late("2026-03-10T12:00:00+08:00", "2026-03-10T14:30:00+08:00") == 2.5


def test_late_across_zones():
    assert hours_late("2026-03-10T18:00:00+01:00", "2026-03-10T12:30:00-05:00") == 0.5


def test_on_time_across_zones():
    assert hours_late("2026-03-10T09:00:00+08:00", "2026-03-10T02:00:00+01:00") == 0.0


def test_utc_written_as_z():
    assert hours_late("2026-03-10T09:00:00+08:00", "2026-03-10T03:00:00Z") == 2.0


def test_a_timestamp_without_an_offset_is_refused():
    with pytest.raises(ValueError):
        hours_late("2026-03-10T12:00:00", "2026-03-10T13:00:00+08:00")


def test_late_shipments_use_the_grace_period():
    rows = [
        {"id": "S1", "promised": "2026-03-10T18:00:00+01:00", "delivered": "2026-03-10T12:30:00-05:00"},
        {"id": "S2", "promised": "2026-03-10T18:00:00+01:00", "delivered": "2026-03-10T12:31:00-05:00"},
        {"id": "S3", "promised": "2026-03-10T10:00:00+00:00", "delivered": "2026-03-10T18:00:00+08:00"},
    ]
    assert late_shipments(rows) == ["S2"]
