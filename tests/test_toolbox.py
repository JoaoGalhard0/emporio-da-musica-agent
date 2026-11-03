"""Phase 4: tool behavior, identity verification and the facts the agent is allowed to state."""
import json
from datetime import datetime

import pytest

from emporio_agent.config import STORE_TZ
from emporio_agent.data.store import Store
from emporio_agent.policies.retriever import PolicyRetriever
from emporio_agent.session import MAX_FAILED_VERIFICATIONS, Session
from emporio_agent.toolbox import ToolBox


@pytest.fixture(scope="module")
def store() -> Store:
    return Store()


@pytest.fixture(scope="module")
def retriever() -> PolicyRetriever:
    return PolicyRetriever()  # keyword-only: no network in unit tests


def make_tools(store, retriever, tmp_path, now=datetime(2026, 2, 20, 10, 0, tzinfo=STORE_TZ)):
    session = Session(id="t1")
    return ToolBox(store, retriever, session, clock=lambda: now, escalations_path=tmp_path / "esc.jsonl")


@pytest.fixture
def tools(store, retriever, tmp_path):
    return make_tools(store, retriever, tmp_path)


def run(tb: ToolBox, name: str, **args) -> dict:
    return json.loads(tb.call(name, json.dumps(args)))


# -- catalog -------------------------------------------------------------------------------------

def test_guitars_up_to_1000_are_available_and_sorted(tools, store):
    r = run(tools, "search_products", category="Violões", max_price=1000)
    ids = {p["id"] for p in r["products"]}
    expected = {p.id for p in store.products.values()
                if p.category_id == 5 and p.is_available and p.price <= 1000}
    assert r["total_matches"] == len(expected)
    assert 96 not in ids and 113 not in ids  # out of stock and discontinued
    assert 83 in ids  # Tagima Memphis AC-39, R$ 429,90
    prices = [float(p["price"].removeprefix("R$ ").replace(".", "").replace(",", ".")) for p in r["products"]]
    assert prices == sorted(prices)
    assert len(r["products"]) == 8 and "note" in r  # more than 8 matches: only the cheapest are shown


def test_keywords_match_brand_and_ignore_accents_and_plurals(tools):
    r = run(tools, "search_products", keywords="takamine")
    assert r["total_matches"] == 4 and all("Takamine" in p["name"] for p in r["products"])
    r = run(tools, "search_products", keywords="ukuleles soprano")
    assert r["products"] and all(p["category"] == "Ukuleles" for p in r["products"])


def test_percent_formatting_keeps_round_numbers(tools):
    # Regression: rstrip("0") once turned "20" into "2".
    from emporio_agent.toolbox import _percent
    from decimal import Decimal
    assert _percent(Decimal("20")) == "20%" and _percent(Decimal("10")) == "10%" and _percent(Decimal("12.5")) == "12.5%"


def test_promotion_counts_toward_the_budget(tools):
    # Ohana CK-20 costs R$ 549,00 but R$ 439,20 with its active 20% promotion.
    r = run(tools, "search_products", keywords="Ohana CK-20", max_price=450)
    assert [p["id"] for p in r["products"]] == [121]
    assert r["products"][0]["promotion"] == {"percent": "20%", "name": "Desconto Exclusivo"}


def test_relaxed_search_says_so(tools):
    r = run(tools, "search_products", keywords="Yamaha trompete")
    assert r["products"] and "some of them" in r["note"]


def test_empty_category_is_reported_not_invented(tools):
    r = run(tools, "search_products", category="Instrumentos de Sopro (Metais)")
    assert r["products"] == [] and "no products in category" in r["note"]


def test_price_of_takamine_gd20(tools):
    r = run(tools, "get_product", product="Takamine GD20")
    assert r["id"] == 95 and r["price"] == "R$ 2.199,00" and r["pix_price"] == "R$ 2.089,05"
    assert "promotion" not in r
    assert r["installments"]["max_plan"] == "12x de R$ 183,25 sem juros"


def test_promotional_product_has_no_pix_price(tools):
    r = run(tools, "get_product", product="Ohana CK-20")
    assert r["list_price"] == "R$ 549,00" and r["price"] == "R$ 439,20"
    assert r["promotion"]["percent"] == "20%"
    assert "pix_price" not in r and "does not apply" in r["pix_note"]


def test_unavailable_products_come_with_alternatives(tools):
    out_of_stock = run(tools, "get_product", product="96")
    assert out_of_stock["availability"] == "out_of_stock"
    assert out_of_stock["alternatives"] and all(a["availability"] == "in_stock" for a in out_of_stock["alternatives"])
    assert "No longer" in run(tools, "get_product", product="Shelby SN-7C")["unavailable_note"]
    assert "Not on sale" in run(tools, "get_product", product="Kala KA-ABP-CTG")["unavailable_note"]


def test_ambiguous_and_unknown_products(tools):
    r = run(tools, "get_product", product="Yamaha")
    assert r["ambiguous"] and len(r["candidates"]) > 1
    assert run(tools, "get_product", product="Stradivarius")["found"] is False


def test_large_instruments_flag_special_freight(tools):
    assert run(tools, "get_product", product="Yamaha Kit 1 Studio")["special_freight"] is True


# -- store info ----------------------------------------------------------------------------------

def test_store_info_open_on_a_weekday_morning(tools):
    r = run(tools, "get_store_info")
    assert r["open_now"] is True and r["phone_whatsapp"] == "(67) 3341-4444"
    assert r["now"] == "sexta-feira, 20/02/2026 às 10:00"
    assert "Instrumentos de Sopro (Metais)" not in r["categories_in_catalog"]


def test_store_info_closed_on_sunday(store, retriever, tmp_path):
    tb = make_tools(store, retriever, tmp_path, datetime(2026, 2, 22, 11, 0, tzinfo=STORE_TZ))
    r = run(tb, "get_store_info")
    assert r["open_now"] is False and r["next_opening"] == "segunda-feira, 23/02/2026 às 09:00"


# -- identity verification (D9, D11) -------------------------------------------------------------

def test_order_requires_a_contact(tools):
    r = run(tools, "get_order_status", order_id=8)
    assert r["verified"] is False and r["verification_required"] is True


def test_correct_email_or_phone_unlocks_the_order(store, retriever, tmp_path):
    owner = store.customers[2]  # owner of order 8
    by_email = make_tools(store, retriever, tmp_path)
    assert run(by_email, "get_order_status", order_id=8, contact=owner.email.upper())["verified"] is True
    by_phone = make_tools(store, retriever, tmp_path)
    digits = "55" + "".join(ch for ch in owner.phone if ch.isdigit())  # with country code
    assert run(by_phone, "get_order_status", order_id=8, contact=digits)["verified"] is True


def test_wrong_contact_and_unknown_order_look_identical(tools):
    wrong = run(tools, "get_order_status", order_id=8, contact="alguem@jmail.com")
    unknown = run(tools, "get_order_status", order_id=999, contact="alguem@jmail.com")
    assert wrong == unknown and wrong["verified"] is False
    assert "exists" in wrong["message"]  # instructs the model not to confirm existence


def test_another_customers_contact_does_not_open_the_order(store, tools):
    assert run(tools, "get_order_status", order_id=1, contact=store.customers[14].email)["verified"] is False


def test_shared_email_cannot_prove_ownership(store, retriever, tmp_path):
    # Customers 11 and 43 share an e-mail; order 10 belongs to 11.
    owner = store.customers[11]
    by_email = make_tools(store, retriever, tmp_path)
    assert run(by_email, "get_order_status", order_id=10, contact=owner.email)["verified"] is False
    by_phone = make_tools(store, retriever, tmp_path)
    assert run(by_phone, "get_order_status", order_id=10, contact=owner.phone)["verified"] is True


def test_verification_covers_the_customers_other_orders_only(store, tools):
    owner = store.customers[7]  # orders 2 and 20
    assert run(tools, "get_order_status", order_id=2, contact=owner.email)["verified"] is True
    assert run(tools, "get_order_status", order_id=20)["verified"] is True  # same customer, no contact needed
    assert run(tools, "get_order_status", order_id=1)["verified"] is False  # someone else's order


def test_too_many_failures_lock_the_session(store, tools):
    for _ in range(MAX_FAILED_VERIFICATIONS):
        run(tools, "get_order_status", order_id=8, contact="x@y.com")
    r = run(tools, "get_order_status", order_id=8, contact=store.customers[2].email)  # now correct
    assert r["verified"] is False and r["locked"] is True


def test_lock_does_not_revoke_an_already_verified_customer(store, tools):
    run(tools, "get_order_status", order_id=8, contact=store.customers[2].email)
    for _ in range(MAX_FAILED_VERIFICATIONS):
        run(tools, "get_order_status", order_id=1, contact="x@y.com")
    assert run(tools, "get_order_status", order_id=8)["verified"] is True


# -- order content -------------------------------------------------------------------------------

def test_shipped_order(store, tools):
    r = run(tools, "get_order_status", order_id=8, contact=store.customers[2].email)
    assert r["status_pt"] == "enviado" and r["customer_first_name"] == "Ana"
    assert r["tracking_code"] == "BRJL5544332BR" and r["estimated_delivery"] == "28/02/2026"
    assert r["total"] == "R$ 349,90" and r["payment"] == "cartão de débito"
    assert r["items"] == [{"product": "Kala KA-C Concert Mogno", "quantity": 1}]
    assert "warning" not in r


def test_shipped_order_past_its_estimate_asks_for_escalation(store, retriever, tmp_path):
    tb = make_tools(store, retriever, tmp_path, datetime(2026, 3, 5, 10, 0, tzinfo=STORE_TZ))
    r = run(tb, "get_order_status", order_id=8, contact=store.customers[2].email)
    assert "escalate" in r["warning"]


def test_confirmed_and_pending_orders_have_no_tracking(store, tools):
    confirmed = run(tools, "get_order_status", order_id=9, contact=store.customers[6].email)
    assert "tracking_code" not in confirmed and "not shipped" in confirmed["status_explanation"]
    pending = run(tools, "get_order_status", order_id=13, contact=store.customers[8].email)
    assert "tracking_code" not in pending and pending["payment"] == "PIX"


def test_cancelled_order_shows_reason(store, tools):
    r = run(tools, "get_order_status", order_id=17, contact=store.customers[15].email)
    assert r["notes"] == "Pedido cancelado pelo cliente antes do processamento"


# -- returns -------------------------------------------------------------------------------------

def test_regret_within_window(store, tools):
    r = run(tools, "check_return_eligibility", order_id=7, reason="regret", contact=store.customers[14].email)
    assert r["eligible"] is True and r["deadline"] == "24/02/2026" and r["days_left"] == 4
    assert "next_step" not in r


def test_return_requires_verification(tools):
    r = run(tools, "check_return_eligibility", order_id=7, reason="regret")
    assert r["verified"] is False


def test_warranty_gray_zone_asks_for_a_human(store, retriever, tmp_path):
    tb = make_tools(store, retriever, tmp_path, datetime(2026, 4, 1, 10, 0, tzinfo=STORE_TZ))
    r = run(tb, "check_return_eligibility", order_id=7, reason="defect", contact=store.customers[14].email)
    assert r["outcome"] == "warranty_claim" and "escalate_to_human" in r["next_step"]


# -- payment, shipping, policies, escalation -----------------------------------------------------

def test_payment_options(tools):
    r = run(tools, "calculate_payment_options", amount=800)
    assert r["max_installments"] == 8 and r["can_combine_payment_methods"] is False
    assert r["credit_card_installments"][-1] == {"count": 8, "value": "R$ 100,00"}


def test_shipping(tools):
    assert run(tools, "estimate_shipping", order_total=499.99, city="Campo Grande")["fee"] == "R$ 35,00"
    assert run(tools, "estimate_shipping", order_total=500.01, city="campo grande")["free_shipping"] is True
    far = run(tools, "estimate_shipping", order_total=900, city="Dourados", product="Yamaha Kit 1 Studio")
    assert far["region"] == "other_city" and "CEP" in far["fee"] and "individual quote" in far["special_freight"]


def test_policy_search(tools):
    r = run(tools, "search_policies", query="Me arrependi da compra, posso devolver?")
    assert r["results"][0]["text"] and any("4.1" in x["title"] for x in r["results"])
    assert "note" in run(tools, "search_policies", query="xyzzy qwerty")


def test_escalation_writes_a_ticket(tools, tmp_path):
    r = run(tools, "escalate_to_human", kind="complaint", summary="Cliente reclama do atraso", order_id=8)
    assert r["ticket"].startswith("T20260220100000-") and "24 business hours" in r["response_time"]
    line = json.loads((tmp_path / "esc.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["kind"] == "complaint" and line["order_id"] == 8 and line["ticket"] == r["ticket"]


# -- dispatcher ----------------------------------------------------------------------------------

def test_bad_calls_return_errors_instead_of_raising(tools, store):
    assert "unknown tool" in json.loads(tools.call("hack", "{}"))["error"]
    assert "invalid arguments" in json.loads(tools.call("get_product", "{}"))["error"]
    bad_reason = json.dumps({"order_id": 7, "reason": "x", "contact": store.customers[14].email})
    assert "failed" in json.loads(tools.call("check_return_eligibility", bad_reason))["error"]
    assert "error" in json.loads(tools.call("get_product", "{not json"))


def test_schemas_list_every_tool_and_the_real_categories(tools, store):
    schemas = tools.schemas()
    assert {s["function"]["name"] for s in schemas} == set(tools._handlers)
    enum = next(s for s in schemas if s["function"]["name"] == "search_products")["function"]["parameters"]["properties"]["category"]["enum"]
    assert enum == [c.name for c in store.categories.values()] and len(enum) == 9
