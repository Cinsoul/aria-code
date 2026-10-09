"""Grades tracking.py against docs/WEBHOOKS.md (hidden from the agent).

The traps: comparing occurred_at as text (a +08:00 time "later" on the page
is earlier in fact), a non-constant-time or prefix-less signature check, a
one-sided timestamp window, re-applying duplicates, and letting a late
in_transit overwrite delivered.
"""

import hashlib
import hmac

from tracking import Tracker, verify

SECRET = b"whsec_test_7c1f"
BODY = b'{"event_id":"evt_01"}'


def sign(ts, body=BODY, secret=SECRET):
    return "v1=" + hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def ev(eid, status, at, shipment="SL1"):
    return {"event_id": eid, "shipment_id": shipment, "status": status, "occurred_at": at}


def test_a_valid_signature():
    assert verify(BODY, sign(1_800_000_000), 1_800_000_000, 1_800_000_100, SECRET)


def test_signature_needs_its_prefix_and_the_right_key():
    raw = sign(1_800_000_000)[3:]
    assert not verify(BODY, raw, 1_800_000_000, 1_800_000_000, SECRET)
    assert not verify(BODY, sign(1_800_000_000, secret=b"other"), 1_800_000_000, 1_800_000_000, SECRET)
    assert not verify(BODY + b" ", sign(1_800_000_000), 1_800_000_000, 1_800_000_000, SECRET)


def test_the_timestamp_window_is_300_seconds_either_way():
    ts = 1_800_000_000
    assert verify(BODY, sign(ts), ts, ts + 300, SECRET)
    assert not verify(BODY, sign(ts), ts, ts + 301, SECRET)
    assert verify(BODY, sign(ts), ts, ts - 300, SECRET)
    assert not verify(BODY, sign(ts), ts, ts - 301, SECRET)


def test_events_apply_in_order():
    t = Tracker()
    assert t.handle(ev("e1", "picked_up", "2026-10-08T08:00:00+00:00")) == "applied"
    assert t.handle(ev("e2", "in_transit", "2026-10-08T09:00:00+00:00")) == "applied"
    assert t.status("SL1") == "in_transit"
    assert t.status("SL9") is None


def test_a_duplicate_has_no_effect():
    t = Tracker()
    t.handle(ev("e1", "in_transit", "2026-10-08T09:00:00+00:00"))
    t.handle(ev("e2", "out_for_delivery", "2026-10-08T10:00:00+00:00"))
    assert t.handle(ev("e1", "in_transit", "2026-10-08T09:00:00+00:00")) == "duplicate"
    assert t.status("SL1") == "out_for_delivery"


def test_times_are_compared_across_offsets():
    t = Tracker()
    # 10:00+00:00 is later than 16:30+08:00 (08:30 UTC), though not as text.
    assert t.handle(ev("e1", "out_for_delivery", "2026-10-08T10:00:00+00:00")) == "applied"
    assert t.handle(ev("e2", "in_transit", "2026-10-08T16:30:00+08:00")) == "stale"
    assert t.status("SL1") == "out_for_delivery"
    # 05:00-07:00 is 12:00 UTC: later, so it applies.
    assert t.handle(ev("e3", "delivery_failed", "2026-10-08T05:00:00-07:00")) == "applied"


def test_the_same_instant_applies():
    t = Tracker()
    t.handle(ev("e1", "in_transit", "2026-10-08T09:00:00+00:00"))
    assert t.handle(ev("e2", "out_for_delivery", "2026-10-08T17:00:00+08:00")) == "applied"


def test_unknown_status_is_ignored_but_seen():
    t = Tracker()
    t.handle(ev("e1", "in_transit", "2026-10-08T09:00:00+00:00"))
    assert t.handle(ev("e2", "teleported", "2026-10-08T10:00:00+00:00")) == "ignored"
    assert t.status("SL1") == "in_transit"
    assert t.handle(ev("e2", "teleported", "2026-10-08T10:00:00+00:00")) == "duplicate"


def test_delivered_is_terminal_except_for_returned():
    t = Tracker()
    t.handle(ev("e1", "delivered", "2026-10-08T12:00:00+00:00"))
    assert t.handle(ev("e2", "out_for_delivery", "2026-10-08T13:00:00+00:00")) == "ignored"
    assert t.status("SL1") == "delivered"
    assert t.handle(ev("e3", "returned", "2026-10-09T09:00:00+00:00")) == "applied"
    assert t.handle(ev("e4", "in_transit", "2026-10-09T10:00:00+00:00")) == "ignored"
    assert t.status("SL1") == "returned"


def test_shipments_are_tracked_separately():
    t = Tracker()
    t.handle(ev("a1", "delivered", "2026-10-08T12:00:00+00:00", shipment="SL1"))
    assert t.handle(ev("b1", "picked_up", "2026-10-08T08:00:00+00:00", shipment="SL2")) == "applied"
    assert t.status("SL2") == "picked_up"
