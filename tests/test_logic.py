"""Phase 2: business rules from the policies manual. Expected values are computed by hand."""
from datetime import date, datetime
from decimal import Decimal as D

import pytest

from emporio_agent.config import STORE_TZ
from emporio_agent.data.store import Store
from emporio_agent.logic.hours import national_holidays, store_status
from emporio_agent.logic.money import brl, format_brl
from emporio_agent.logic.payment import can_combine_payment_methods, installment_plan
from emporio_agent.logic.pricing import quote_price
from emporio_agent.logic.returns import check_return
from emporio_agent.logic.shipping import needs_special_freight, quote_shipping


@pytest.fixture(scope="module")
def store() -> Store:
    return Store()


def at(y, m, d, hh=10, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=STORE_TZ)


# -- money ---------------------------------------------------------------------------------------

def test_brl_rounds_half_up():
    # Banker's rounding (Decimal's default) would give 0.12 and 2.66.
    assert brl(D("0.125")) == D("0.13")
    assert brl(D("2.665")) == D("2.67")


def test_format_brl():
    assert format_brl(D("2199")) == "R$ 2.199,00"
    assert format_brl(D("599.9")) == "R$ 599,90"
    assert format_brl(D("11499")) == "R$ 11.499,00"
    assert format_brl(D("0.5")) == "R$ 0,50"


# -- pricing (P7) --------------------------------------------------------------------------------

def test_price_without_promotion_has_pix_discount(store):
    q = quote_price(store.products[95], store.active_promotion(95))  # Takamine GD20
    assert q.list_price == q.final_price == D("2199.00")
    assert q.promo_percent is None
    assert q.pix_price == D("2089.05")


def test_promotional_price_gets_no_pix_discount(store):
    q = quote_price(store.products[121], store.active_promotion(121))  # Ohana CK-20, 20%
    assert q.list_price == D("549.00")
    assert q.final_price == D("439.20")
    assert q.promo_percent == D("20")
    assert q.pix_price is None


def test_promotion_rounding(store):
    q = quote_price(store.products[94], store.active_promotion(94))  # Taylor 110e, 8%
    assert q.final_price == D("5519.08")


def test_expired_promotion_is_ignored(store):
    q = quote_price(store.products[93], store.active_promotion(93))  # Martin D-28, only expired promos
    assert q.final_price == D("11499.00") and q.promo_percent is None


# -- installments (P3) ---------------------------------------------------------------------------

def counts(amount):
    return [i.count for i in installment_plan(D(amount))]


def test_installments_800():
    plan = installment_plan(D("800"))
    assert [i.count for i in plan] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert plan[7].value == D("100.00")  # 8x of exactly R$ 100 is allowed
    assert plan[2].value == D("266.67")


def test_installments_use_the_3_1_minimums_not_the_table():
    # R$ 560 in 6x is R$ 93.33: allowed by 3.1 (min R$ 80 for 4-6x), forbidden by the table's R$ 100.
    assert counts("560") == [1, 2, 3, 4, 5, 6]
    # 7x would be R$ 80, below the R$ 100 minimum for 7-12x.
    assert 7 not in counts("560")


def test_installments_small_amounts():
    assert counts("99") == [1]  # 2x of 49.50 is below R$ 50
    assert counts("149.9") == [1, 2]  # 3x of 49.97 is below R$ 50
    assert counts("150") == [1, 2, 3]  # 3x of exactly 50.00 is fine
    assert counts("159.9") == [1, 2, 3]  # 4x of 39.98 is below R$ 80


def test_installments_capped_at_12():
    assert counts("12000")[-1] == 12


def test_combined_payment_needs_more_than_2000():
    assert not can_combine_payment_methods(D("2000"))
    assert can_combine_payment_methods(D("2000.01"))


# -- shipping (P8) -------------------------------------------------------------------------------

def test_metro_shipping_threshold():
    exactly = quote_shipping(D("500"), "Campo Grande")
    assert exactly.fee == D("35") and not exactly.is_free  # "above R$ 500" excludes R$ 500.00
    above = quote_shipping(D("500.01"), "campo grande")
    assert above.fee == D("0") and above.is_free
    assert above.eta == "1 a 3 dias úteis"


def test_other_cities_cannot_be_priced_without_cep():
    q = quote_shipping(D("5000"), "Três Lagoas")
    assert q.kind == "other_city" and q.fee is None and not q.is_free
    assert {c["name"] for c in q.carriers} == {"PAC (Correios)", "SEDEX (Correios)", "Jadlog (.package)"}


def test_special_freight(store):
    assert needs_special_freight(store.products[139])  # Bateria Acústica Yamaha
    assert not needs_special_freight(store.products[95])  # a guitar


# -- store hours (P11) ---------------------------------------------------------------------------

def test_open_during_weekday_hours():
    s = store_status(at(2026, 3, 10, 10))  # Tuesday
    assert s.is_open and s.today_hours == "09:00 às 18:00" and s.next_open is None


def test_closing_time_is_exclusive():
    assert store_status(at(2026, 3, 10, 17, 59)).is_open
    s = store_status(at(2026, 3, 10, 18, 0))
    assert not s.is_open and s.next_open == at(2026, 3, 11, 9)


def test_saturday_closes_at_13():
    assert store_status(at(2026, 3, 14, 12, 59)).is_open
    s = store_status(at(2026, 3, 14, 13, 0))
    assert not s.is_open and s.next_open == at(2026, 3, 16, 9)  # skips Sunday


def test_before_opening_reopens_same_day():
    s = store_status(at(2026, 3, 10, 7, 30))
    assert not s.is_open and s.next_open == at(2026, 3, 10, 9)


def test_sunday_closed():
    s = store_status(at(2026, 3, 15, 11))
    assert not s.is_open and s.today_hours is None and s.next_open == at(2026, 3, 16, 9)


def test_national_holidays_are_closed():
    assert date(2026, 4, 3) in national_holidays(2026)  # Good Friday, Easter is April 5, 2026
    assert date(2026, 11, 2) in national_holidays(2026)
    s = store_status(at(2026, 11, 2, 10))  # a Monday that is a holiday
    assert not s.is_open and s.is_holiday and s.next_open == at(2026, 11, 3, 9)


# -- returns (P4, P9, D7, D8) --------------------------------------------------------------------
# Order 7: delivered, estimated delivery 2026-02-17, placed 2026-02-03.

def test_regret_within_seven_days(store):
    d = check_return(store.orders[7], "regret", date(2026, 2, 20))
    assert d.eligible and d.outcome == "eligible" and d.rule == "4.1"
    assert d.deadline == date(2026, 2, 24) and d.days_left == 4
    assert "10 business days" in d.handling


def test_regret_last_day_is_still_valid_and_next_is_not(store):
    assert check_return(store.orders[7], "regret", date(2026, 2, 24)).eligible
    late = check_return(store.orders[7], "regret", date(2026, 2, 25))
    assert not late.eligible and late.outcome == "window_expired" and not late.needs_human


def test_preference_exchange_uses_same_seven_days(store):
    d = check_return(store.orders[7], "preference", date(2026, 2, 22))
    assert d.eligible and d.rule == "4.3" and "availability" in d.handling


def test_defect_within_30_days_of_purchase(store):
    assert check_return(store.orders[7], "defect", date(2026, 3, 5)).eligible  # day 30
    d = check_return(store.orders[7], "defect", date(2026, 3, 5))
    assert d.deadline == date(2026, 3, 5) and d.days_left == 0


def test_defect_between_30_and_90_days_goes_to_a_human(store):
    d = check_return(store.orders[7], "defect", date(2026, 3, 6))  # day 31
    assert d.outcome == "warranty_claim" and d.needs_human and not d.eligible
    assert d.deadline == date(2026, 5, 18)  # receipt + 90 days
    assert check_return(store.orders[7], "defect", date(2026, 5, 18)).outcome == "warranty_claim"


def test_defect_after_legal_warranty_points_to_manufacturer(store):
    d = check_return(store.orders[7], "defect", date(2026, 5, 19))
    assert d.outcome == "manufacturer_warranty" and not d.needs_human


@pytest.mark.parametrize(
    "order_id, outcome",
    [(8, "not_received_yet"), (9, "not_received_yet"), (13, "not_received_yet"), (17, "order_cancelled")],
)
def test_orders_not_delivered_cannot_be_returned(store, order_id, outcome):
    d = check_return(store.orders[order_id], "regret", date(2026, 3, 1))
    assert d.outcome == outcome and not d.eligible


def test_not_received_orders_hand_over_to_a_human(store):
    assert check_return(store.orders[8], "regret", date(2026, 3, 1)).needs_human
    assert not check_return(store.orders[17], "regret", date(2026, 3, 1)).needs_human


def test_invalid_reason_is_rejected(store):
    with pytest.raises(ValueError):
        check_return(store.orders[7], "whatever", date(2026, 2, 20))
