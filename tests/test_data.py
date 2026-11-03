"""Phase 1: the data layer must reproduce the findings in docs/discovery.md (section B)."""
from datetime import date
from decimal import Decimal

import pytest

from emporio_agent.config import store_now, store_today
from emporio_agent.data.store import Store
from emporio_agent.data.text import normalize, tokens


@pytest.fixture(scope="module")
def store() -> Store:
    return Store()


def test_row_counts(store):
    assert len(store.products) == 65
    assert len(store.orders) == 20
    assert len(store.customers) == 50
    assert len(store.categories) == 9


def test_accents_load_correctly(store):
    # D11: files are UTF-8; a wrong codec would produce "Aço" as mojibake.
    assert store.products[86].name == "Tagima Dallas Tuner Aço Natural"
    assert store.customers[9].city == "Dourados"
    assert store.customers[11].city == "Três Lagoas"


def test_money_is_decimal(store):
    assert store.products[95].price == Decimal("2199")
    assert store.products[81].price == Decimal("599.9")
    assert isinstance(store.orders[4].total, Decimal)


def test_specs_are_parsed(store):
    assert store.products[81].specs["strings"] == "nylon"


def test_availability_is_not_just_status(store):
    assert store.products[96].status == "active" and not store.products[96].is_available  # D2
    assert not store.products[113].is_available  # discontinued
    assert not store.products[130].is_available  # coming soon
    assert store.products[95].is_available


def test_only_active_promotions_count(store):
    # D4: four active promotions, expired ones are ignored.
    active = {p.product_id: p.discount_percent for p in store.promotions if p.is_active}
    assert active == {127: 10, 121: 20, 90: 18, 94: 8}
    assert store.active_promotion(121).discount_percent == Decimal("20")
    assert store.active_promotion(93) is None  # two expired promos, none in force
    assert store.active_promotion(95) is None  # Takamine GD20 has no promotion


def test_empty_categories(store):
    # P5: the manual advertises woodwinds, brass and orchestral strings; the catalog has none.
    used = {p.category_id for p in store.products.values()}
    assert {6, 7, 8}.isdisjoint(used)


def test_order_fields(store):
    shipped = store.orders[8]
    assert shipped.status == "shipped" and shipped.tracking_code == "BRJL5544332BR"
    assert shipped.estimated_delivery == date(2026, 2, 28)
    pending = store.orders[13]
    assert pending.tracking_code is None and pending.estimated_delivery is None
    assert store.orders[18].notes == "Item fora de estoque no momento do pedido"
    assert [i.product_id for i in store.orders[15].items] == [82, 106]


def test_stored_totals_are_kept_not_recomputed(store):
    # D5
    assert store.orders[3].total == Decimal("3450")
    assert store.orders[20].total == Decimal("1400")


def test_quality_notes_reproduce_discovery(store):
    notes = "\n".join(store.quality_notes)
    assert "order 3: stored total 3450 != item sum 3498" in notes
    assert "order 20: stored total 1400 != item sum 1488" in notes
    assert "order 3: contains coming_soon product 130" in notes
    assert "product 96: active but out of stock" in notes
    assert "customers [11, 43] share the email bruno.martins@jmail.com" in notes
    # Exactly the two mismatched totals, nothing else.
    assert sum("stored total" in n for n in store.quality_notes) == 2


def test_duplicate_email_resolves_to_different_owners(store):
    # D9: verification by email alone would be ambiguous.
    owners = [c.id for c in store.customers.values() if c.email == "bruno.martins@jmail.com"]
    assert owners == [11, 43]


def test_normalize_and_tokens():
    assert normalize("  Violão  BARÍTONO ") == "violao baritono"
    assert tokens("Takamine GD20!") == ["takamine", "gd20"]


def test_store_clock_override(monkeypatch):
    monkeypatch.setenv("STORE_NOW", "2026-03-10T14:30")
    assert store_now().hour == 14 and store_now().tzinfo is not None
    assert store_today() == date(2026, 3, 10)
