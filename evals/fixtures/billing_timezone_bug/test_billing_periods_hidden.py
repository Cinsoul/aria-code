"""Grades the billing-period fix (hidden from the agent).

An order belongs to the month it was placed in, in the customer's own time
zone. The traps: a fixed -8 h offset is wrong for Los Angeles from March to
November (PDT is -7 h) and on the night daylight saving ends; and the bug is
not Pacific-only: London (BST) and Shanghai customers have month-end orders
too.
"""

from billing.invoice import invoice_orders


def o(oid, cid, at):
    return {"order_id": oid, "customer_id": cid, "placed_at": at}


def test_the_reported_order_moves_to_september():
    assert "O-1002" in invoice_orders("C-PACIFIC", 2026, 9)
    assert "O-1002" not in invoice_orders("C-PACIFIC", 2026, 10)


def test_daylight_saving_time_is_honoured():
    # 07:30Z on 1 Oct is 00:30 PDT on 1 Oct: October. A fixed -8 h says 30 Sep.
    rows = [o("X1", "C-PACIFIC", "2026-10-01T07:30:00Z")]
    assert invoice_orders("C-PACIFIC", 2026, 10, rows) == ["X1"]


def test_the_night_daylight_saving_ends():
    # 1 Nov 2026, 07:30Z is 00:30 PDT on 1 Nov (PST starts at 02:00 local): November.
    rows = [o("X2", "C-PACIFIC", "2026-11-01T07:30:00Z"),
            o("X3", "C-PACIFIC", "2026-12-01T07:30:00Z")]   # 23:30 PST on 30 Nov
    assert invoice_orders("C-PACIFIC", 2026, 11, rows) == ["X2", "X3"]


def test_london_summer_time():
    # 23:30Z on 30 Sep is 00:30 BST on 1 Oct.
    assert "O-2001" in invoice_orders("C-LONDON", 2026, 10)
    assert "O-2001" not in invoice_orders("C-LONDON", 2026, 9)


def test_shanghai():
    # 17:00Z on 30 Sep is 01:00 on 1 Oct in Shanghai.
    assert "O-3001" in invoice_orders("C-SHANGHAI", 2026, 10)


def test_an_order_well_inside_september_stays():
    assert "O-1001" in invoice_orders("C-PACIFIC", 2026, 9)
