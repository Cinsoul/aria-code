from money import line_total, to_cents


def test_whole_cents():
    assert to_cents("19.99") == 1999


def test_float_error_does_not_leak():
    # 2.675 is 2.67499999... as a float; rounding the float gives 267.
    assert to_cents("2.675") == 268


def test_line_total():
    assert line_total("0.10", 3) == 30
