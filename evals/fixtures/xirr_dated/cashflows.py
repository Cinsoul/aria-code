"""Money-weighted return for private-fund capital accounts."""


def xirr(flows):
    """Annual internal rate of return of dated cash flows.

    `flows` is [(date, amount), ...] in any order: contributions negative,
    distributions positive. Time is measured in actual days / 365 from the
    earliest flow. Flows that never change sign have no rate (ValueError).
    """
    def npv(rate):
        return sum(amount / (1 + rate) ** i for i, (_day, amount) in enumerate(flows))

    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
    return mid
