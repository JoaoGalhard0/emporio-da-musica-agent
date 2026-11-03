from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.logic.money import brl

MAX_INSTALLMENTS = 12
COMBINED_PAYMENT_MIN = Decimal("2000")


def _min_installment(n: int) -> Decimal:
    """Manual 3.1. The payment table in section 3 says R$ 100 for any credit purchase, which
    contradicts 3.1 for 4-6x; the specific rule (3.1) wins, see docs/discovery.md P3."""
    if n <= 3:
        return Decimal("50")  # "no minimum, except below R$ 50.00"
    if n <= 6:
        return Decimal("80")
    return Decimal("100")


@dataclass(frozen=True)
class Installment:
    count: int
    value: Decimal


def installment_plan(amount: Decimal) -> list[Installment]:
    """Every credit-card option allowed for `amount`; 1x is always allowed."""
    plan = [Installment(1, brl(amount))]
    for n in range(2, MAX_INSTALLMENTS + 1):
        if amount / n < _min_installment(n):
            # Installment values only shrink as n grows, so no later n can qualify either.
            break
        plan.append(Installment(n, brl(amount / n)))
    return plan


def can_combine_payment_methods(amount: Decimal) -> bool:
    """Manual 3.1: e.g. PIX + card, only for purchases above R$ 2,000.00."""
    return amount > COMBINED_PAYMENT_MIN
