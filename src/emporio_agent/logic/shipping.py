from dataclasses import dataclass
from decimal import Decimal

from emporio_agent.data.models import Product
from emporio_agent.data.text import normalize

FREE_SHIPPING_ABOVE = Decimal("500")
FLAT_FEE = Decimal("35")

# The dataset's only city inside the metro area is Campo Grande; the other four customer cities
# (Dourados, Três Lagoas, Corumbá, Ponta Porã) are served by carriers.
METRO_CITIES = {"campo grande"}

CARRIERS = (
    {"name": "PAC (Correios)", "eta": "5 a 12 dias úteis"},
    {"name": "SEDEX (Correios)", "eta": "2 a 5 dias úteis"},
    {"name": "Jadlog (.package)", "eta": "3 a 8 dias úteis"},
)


@dataclass(frozen=True)
class ShippingQuote:
    kind: str  # metro | other_city
    fee: Decimal | None  # None = cannot be computed here (needs the destination CEP)
    is_free: bool
    eta: str | None
    carriers: tuple[dict, ...]
    note: str


def quote_shipping(order_total: Decimal, city: str) -> ShippingQuote:
    if normalize(city) in METRO_CITIES:
        # "Free above R$ 500": exactly R$ 500.00 still pays the fee.
        free = order_total > FREE_SHIPPING_ABOVE
        return ShippingQuote(
            kind="metro",
            fee=Decimal(0) if free else FLAT_FEE,
            is_free=free,
            eta="1 a 3 dias úteis",
            carriers=(),
            note="Delivery by the store's own motoboy; the customer is called before delivery.",
        )
    return ShippingQuote(
        kind="other_city",
        fee=None,
        is_free=False,
        eta=None,
        carriers=CARRIERS,
        note=(
            "Price is calculated from the destination CEP, weight and dimensions; it cannot be "
            "quoted without them. Tracking and insurance are included."
        ),
    )


def needs_special_freight(product: Product) -> bool:
    """Manual 5.2: large instruments (acoustic drum kits, digital pianos, double basses) need an
    individual quote. The catalog has no digital pianos or double basses today, but the check
    stays name-based so a future entry is handled."""
    name = normalize(product.name)
    return "bateria acustica" in name or "piano" in name or "contrabaixo" in name
