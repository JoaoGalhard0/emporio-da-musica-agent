from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def brl(amount: Decimal) -> Decimal:
    """Round to cents the way a price tag does (half up), not banker's rounding."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def format_brl(amount: Decimal) -> str:
    """pt-BR formatting without depending on the machine's locale: R$ 1.234,50."""
    whole, cents = f"{brl(amount):.2f}".split(".")
    groups = f"{int(whole):,}".replace(",", ".")
    return f"R$ {groups},{cents}"
