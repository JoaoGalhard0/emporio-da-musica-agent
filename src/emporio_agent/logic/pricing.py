from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.data.models import Product, Promotion
from emporio_agent.logic.money import brl

PIX_DISCOUNT = Decimal("5")


@dataclass(frozen=True)
class PriceQuote:
    list_price: Decimal
    final_price: Decimal  # what the customer pays by card, debit or boleto
    promo_percent: Decimal | None
    promo_name: str | None
    pix_price: Decimal | None  # None when PIX gets no extra discount
    pix_note: str


def quote_price(product: Product, promotion: Promotion | None) -> PriceQuote:
    """Manual 6.2: promotions do not stack, and the 5% PIX discount never applies to a promo price.

    The promotion passed in must already be the one in force (`Store.active_promotion`).
    """
    list_price = brl(product.price)
    if promotion is not None:
        final = brl(list_price * (Decimal(100) - promotion.discount_percent) / Decimal(100))
        return PriceQuote(
            list_price=list_price,
            final_price=final,
            promo_percent=promotion.discount_percent,
            promo_name=promotion.description,
            pix_price=None,
            pix_note="PIX discount does not apply to promotional prices (promotions do not stack).",
        )
    return PriceQuote(
        list_price=list_price,
        final_price=list_price,
        promo_percent=None,
        promo_name=None,
        pix_price=brl(list_price * (Decimal(100) - PIX_DISCOUNT) / Decimal(100)),
        pix_note="5% discount for paying with PIX.",
    )
