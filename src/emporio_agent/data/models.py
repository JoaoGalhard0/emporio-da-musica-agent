from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    description: str


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    price: Decimal
    category_id: int
    description: str
    stock: int
    status: str  # active | discontinued | coming_soon
    specs: dict
    created_at: date

    @property
    def is_available(self) -> bool:
        # "active" alone is not enough: product 96 is active with zero stock.
        return self.status == "active" and self.stock > 0


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    discount_percent: Decimal
    description: str
    is_active: bool  # promotions carry no dates, only this flag


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItem:
    order_id: int
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    order_date: date
    status: str  # pending | confirmed | shipped | delivered | cancelled
    total: Decimal  # as stored; never recomputed (orders 3 and 20 differ from their item sums)
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...] = field(default=())
