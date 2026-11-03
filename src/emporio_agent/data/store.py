import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio_agent.config import DATA_DIR
from emporio_agent.data.models import (
    Category,
    Customer,
    Order,
    OrderItem,
    Product,
    Promotion,
)

_CSV_PREFIX = "desafio_tecnico_ai_eng - "


def _read(data_dir: Path, name: str) -> list[dict[str, str]]:
    # Explicit UTF-8: the default console encoding on Windows would garble accents.
    with open(data_dir / f"{_CSV_PREFIX}{name}.csv", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _opt(value: str) -> str | None:
    return value.strip() or None


def _opt_date(value: str) -> date | None:
    return date.fromisoformat(value) if value.strip() else None


class DataError(ValueError):
    """The CSVs reference something that does not exist; fail loudly instead of answering wrongly."""


class Store:
    """In-memory view of the store's CSVs, plus the data-quality notes found while loading."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.categories = {
            int(r["category_id"]): Category(int(r["category_id"]), r["name"], r["description"])
            for r in _read(data_dir, "categories")
        }
        self.products = {
            int(r["product_id"]): Product(
                id=int(r["product_id"]),
                name=r["name"],
                price=Decimal(r["price_brl"]),
                category_id=int(r["category_id"]),
                description=r["description"],
                stock=int(r["stock_quantity"]),
                status=r["status"],
                specs=json.loads(r["specs"]),
                created_at=date.fromisoformat(r["created_at"]),
            )
            for r in _read(data_dir, "products")
        }
        self.promotions = [
            Promotion(
                id=int(r["promotion_id"]),
                product_id=int(r["product_id"]),
                discount_percent=Decimal(r["discount_percent"]),
                description=r["description"],
                is_active=r["is_active"] == "1",
            )
            for r in _read(data_dir, "promotions")
        ]
        self.customers = {
            int(r["customer_id"]): Customer(
                int(r["customer_id"]), r["name"], r["phone"], r["email"], r["city"]
            )
            for r in _read(data_dir, "customers")
        }

        items_by_order: dict[int, list[OrderItem]] = defaultdict(list)
        for r in _read(data_dir, "order_items"):
            items_by_order[int(r["order_id"])].append(
                OrderItem(int(r["order_id"]), int(r["product_id"]), int(r["quantity"]))
            )
        self.orders = {
            int(r["order_id"]): Order(
                id=int(r["order_id"]),
                customer_id=int(r["customer_id"]),
                order_date=date.fromisoformat(r["order_date"]),
                status=r["status"],
                total=Decimal(r["total_brl"]),
                payment_method=r["payment_method"],
                tracking_code=_opt(r["tracking_code"]),
                estimated_delivery=_opt_date(r["estimated_delivery"]),
                notes=_opt(r["notes"]),
                items=tuple(items_by_order[int(r["order_id"])]),
            )
            for r in _read(data_dir, "orders")
        }

        self._check_references()
        self.quality_notes = self._find_quality_notes()

    # -- lookups ---------------------------------------------------------------------------------

    def category_name(self, category_id: int) -> str:
        return self.categories[category_id].name

    def active_promotion(self, product_id: int) -> Promotion | None:
        """The promotion currently in force, if any. Expired ones (is_active=0) are never offered."""
        active = [p for p in self.promotions if p.product_id == product_id and p.is_active]
        return max(active, key=lambda p: p.discount_percent, default=None)

    def customer_of(self, order: Order) -> Customer:
        return self.customers[order.customer_id]

    # -- integrity -------------------------------------------------------------------------------

    def _check_references(self) -> None:
        for p in self.products.values():
            if p.category_id not in self.categories:
                raise DataError(f"product {p.id}: unknown category {p.category_id}")
        for promo in self.promotions:
            if promo.product_id not in self.products:
                raise DataError(f"promotion {promo.id}: unknown product {promo.product_id}")
        for o in self.orders.values():
            if o.customer_id not in self.customers:
                raise DataError(f"order {o.id}: unknown customer {o.customer_id}")
            for it in o.items:
                if it.product_id not in self.products:
                    raise DataError(f"order {o.id}: unknown product {it.product_id}")

    def _find_quality_notes(self) -> list[str]:
        """Inconsistencies the agent must live with (see docs/discovery.md), kept testable."""
        notes: list[str] = []
        for o in self.orders.values():
            computed = sum(
                (self.products[i.product_id].price * i.quantity for i in o.items), Decimal(0)
            )
            if computed != o.total:
                notes.append(f"order {o.id}: stored total {o.total} != item sum {computed}")
            for i in o.items:
                prod = self.products[i.product_id]
                if prod.status != "active":
                    notes.append(f"order {o.id}: contains {prod.status} product {prod.id}")
        for p in self.products.values():
            if p.status == "active" and p.stock == 0:
                notes.append(f"product {p.id}: active but out of stock")
        by_email = Counter(c.email for c in self.customers.values())
        for email, n in by_email.items():
            if n > 1:
                ids = sorted(c.id for c in self.customers.values() if c.email == email)
                notes.append(f"customers {ids} share the email {email}")
        return notes
