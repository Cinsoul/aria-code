from billing.invoice import invoice_orders


def test_mid_month_orders():
    assert "O-1003" in invoice_orders("C-PACIFIC", 2026, 10)
    assert "O-2002" in invoice_orders("C-LONDON", 2026, 10)
