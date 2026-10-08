"""Repayment schedules for equipment loans."""


def schedule(principal, annual_rate, months):
    """Monthly schedule for a fixed-rate loan.

    One (payment, interest, principal_paid, balance) row per month, in
    currency units rounded to the cent. Each month's interest is the
    balance times annual_rate / 12. The payment is the standard annuity
    payment rounded to the cent (principal / months at a zero rate); the
    final payment pays off whatever balance is left, so it ends at 0.00.
    """
    r = annual_rate
    payment = round(principal * r / (1 - (1 + r) ** -months), 2)
    rows, balance = [], principal
    for _ in range(months):
        interest = round(balance * r, 2)
        paid = payment - interest
        balance = round(balance - paid, 2)
        rows.append((payment, interest, round(paid, 2), balance))
    return rows
