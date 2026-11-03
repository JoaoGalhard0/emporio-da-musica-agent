"""The tools the LLM can call. Each handler returns plain JSON-able data.

All facts the agent states come from here, and all money is returned already formatted ("R$ 2.199,00")
so the model copies it instead of computing it (see grounding.py).
"""
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from emporio_agent.config import REPO_ROOT, store_now
from emporio_agent.data.models import Order, Product
from emporio_agent.data.store import Store
from emporio_agent.data.text import STOPWORDS, normalize, tokens
from emporio_agent.logic.hours import store_status
from emporio_agent.logic.money import format_brl
from emporio_agent.logic.payment import can_combine_payment_methods, installment_plan
from emporio_agent.logic.pricing import quote_price
from emporio_agent.logic.returns import check_return
from emporio_agent.logic.shipping import needs_special_freight, quote_shipping
from emporio_agent.policies.retriever import PolicyRetriever
from emporio_agent.session import Session
from emporio_agent.tool_schemas import build_schemas

ESCALATIONS_PATH = REPO_ROOT / ".conversations" / "escalations.jsonl"

# Canonical store facts. Phone and e-mail follow the resolution of the manual's contradictions
# (docs/discovery.md P1, P2).
STORE_INFO = {
    "name": "Empório da Música",
    "tagline": "Sua música começa aqui.",
    "address": "Rua 14 de Maio, 3200 — Centro, Campo Grande/MS, CEP 79202-333",
    "phone_whatsapp": "(67) 3341-4444",
    "email": "contato@emporiodamusica.com.br",
    "opening_hours": "Segunda a sexta, 09:00 às 18:00; sábado, 09:00 às 13:00; domingo e feriados fechado.",
    "scope": "The store sells ONLY musical instruments. It does not sell accessories (strings, picks, "
    "cables, cases, pedals, amplifiers).",
}

_WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
_STATUS_PT = {
    "pending": "pendente", "confirmed": "confirmado", "shipped": "enviado",
    "delivered": "entregue", "cancelled": "cancelado",
}
# Same wording for "no such order" and "wrong contact": the answer must not reveal which one it was.
_NOT_VERIFIED = {
    "verified": False,
    "message": "Could not verify this order with the data provided. Ask the customer to double-check "
    "the order number and to give the phone number registered on the order. Do not say whether the "
    "order exists.",
}


def _stem(token: str) -> str:
    """Singularize so "violões"/"violão" and "ukuleles"/"ukulele" meet. Whole words only: a prefix
    match would let "Stradivarius" hit "Stratocaster"."""
    if token.endswith("oes"):
        return token[:-3] + "ao"
    return token[:-1] if token.endswith("s") and len(token) > 3 else token


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _fmt_date(d: date | None) -> str | None:
    return d.strftime("%d/%m/%Y") if d else None


def _fmt_dt(dt: datetime) -> str:
    return f"{_WEEKDAYS[dt.weekday()]}, {dt:%d/%m/%Y} às {dt:%H:%M}"


def _percent(value: Decimal) -> str:
    text = f"{value:f}"
    return (text.rstrip("0").rstrip(".") if "." in text else text) + "%"


def _payment_pt(method: str) -> str:
    if method.startswith("credit_"):
        return f"cartão de crédito em {method.removeprefix('credit_')}"
    return {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto bancário"}.get(method, method)


class ToolBox:
    def __init__(self, store: Store, retriever: PolicyRetriever, session: Session,
                 clock: Callable[[], datetime] = store_now, escalations_path: Path = ESCALATIONS_PATH):
        self.store, self.retriever, self.session = store, retriever, session
        self.clock, self.escalations_path = clock, escalations_path
        self._handlers = {
            "search_products": self.search_products,
            "get_product": self.get_product,
            "get_store_info": self.get_store_info,
            "get_order_status": self.get_order_status,
            "check_return_eligibility": self.check_return_eligibility,
            "calculate_payment_options": self.calculate_payment_options,
            "estimate_shipping": self.estimate_shipping,
            "search_policies": self.search_policies,
            "escalate_to_human": self.escalate_to_human,
        }

    def schemas(self) -> list[dict]:
        return build_schemas([c.name for c in self.store.categories.values()])

    def call(self, name: str, arguments: str | dict) -> str:
        """Run one tool call; always returns a JSON string, never raises into the agent loop."""
        handler = self._handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"unknown tool '{name}'"})
        try:
            args = json.loads(arguments) if isinstance(arguments, str) and arguments.strip() else (arguments or {})
            return json.dumps(handler(**args), ensure_ascii=False)
        except TypeError as exc:  # wrong or missing arguments
            return json.dumps({"error": f"invalid arguments for {name}: {exc}"})
        except Exception as exc:
            return json.dumps({"error": f"{name} failed: {type(exc).__name__}: {exc}"})

    # -- catalog ---------------------------------------------------------------------------------

    def _summary(self, p: Product) -> dict:
        q = quote_price(p, self.store.active_promotion(p.id))
        availability = (
            "in_stock" if p.is_available
            else "discontinued" if p.status == "discontinued"
            else "coming_soon" if p.status == "coming_soon"
            else "out_of_stock"
        )
        out = {
            "id": p.id, "name": p.name, "category": self.store.category_name(p.category_id),
            "availability": availability, "stock": p.stock,
            "list_price": format_brl(q.list_price), "price": format_brl(q.final_price),
        }
        if q.promo_percent is not None:
            out["promotion"] = {"percent": _percent(q.promo_percent), "name": q.promo_name}
        if q.pix_price is not None:
            out["pix_price"] = format_brl(q.pix_price)
        return out

    def _haystack(self, p: Product) -> set[str]:
        text = " ".join([p.name, p.description, self.store.category_name(p.category_id),
                         *(str(v) for v in p.specs.values())])
        return {_stem(t) for t in tokens(text)}

    def search_products(self, keywords: str = "", category: str | None = None, max_price: float | None = None,
                        min_price: float | None = None, only_available: bool = True) -> dict:
        wanted = [_stem(t) for t in tokens(keywords) if t not in STOPWORDS]
        candidates = []
        for p in self.store.products.values():
            if category and normalize(self.store.category_name(p.category_id)) != normalize(category):
                continue
            if only_available and not p.is_available:
                continue
            quote = quote_price(p, self.store.active_promotion(p.id))
            # The customer's budget is what they pay, so promotions count; PIX is a payment choice.
            if max_price is not None and quote.final_price > Decimal(str(max_price)):
                continue
            if min_price is not None and quote.final_price < Decimal(str(min_price)):
                continue
            candidates.append((p, quote.final_price))

        hits, relaxed = candidates, False
        if wanted:
            hay = {p.id: self._haystack(p) for p, _ in candidates}
            hits = [(p, pr) for p, pr in candidates if all(w in hay[p.id] for w in wanted)]
            if not hits:  # no product has every word: fall back to any word and say so
                hits = [(p, pr) for p, pr in candidates if any(w in hay[p.id] for w in wanted)]
                relaxed = bool(hits)
        hits.sort(key=lambda item: item[1])

        result = {"total_matches": len(hits), "products": [self._summary(p) for p, _ in hits[:8]]}
        if len(hits) > 8:
            result["note"] = "Only the 8 cheapest are shown; ask the customer to narrow the search."
        if relaxed:
            result["note"] = "No product matches every keyword; these match some of them."
        if not hits:
            result["note"] = (
                "Nothing matches in the current catalog. Offer to broaden the filters, or suggest a "
                "different category. Never claim products that are not listed here."
            )
            if category and not any(normalize(self.store.category_name(p.category_id)) == normalize(category)
                                    for p in self.store.products.values()):
                result["note"] = f"The catalog currently has no products in category '{category}'."
        return result

    def _resolve_product(self, ref: str | int) -> tuple[Product | None, list[Product]]:
        text = str(ref).strip()
        if text.isdigit() and int(text) in self.store.products:
            return self.store.products[int(text)], []
        wanted = [_stem(t) for t in tokens(text) if t not in STOPWORDS]
        if not wanted:
            return None, []
        matches = [p for p in self.store.products.values() if all(w in self._haystack_name(p) for w in wanted)]
        exact = [p for p in matches if normalize(p.name) == normalize(text)]
        if len(exact) == 1:
            return exact[0], []
        if len(matches) == 1:
            return matches[0], []
        return None, matches

    def _haystack_name(self, p: Product) -> set[str]:
        return {_stem(t) for t in tokens(p.name)}

    def get_product(self, product: str | int) -> dict:
        p, candidates = self._resolve_product(product)
        if p is None:
            if candidates:
                return {"found": False, "ambiguous": True,
                        "message": "Several products match; ask the customer which one.",
                        "candidates": [self._summary(c) for c in candidates[:6]]}
            return {"found": False, "message": "No product with that name. Try search_products with keywords."}

        promo = self.store.active_promotion(p.id)
        quote = quote_price(p, promo)
        plan = installment_plan(quote.final_price)
        out = self._summary(p)
        out.update({
            "found": True,
            "description": p.description,
            "specs": p.specs,
            "installments": {
                "max": plan[-1].count,
                "max_plan": f"{plan[-1].count}x de {format_brl(plan[-1].value)} sem juros",
            },
            "special_freight": needs_special_freight(p),
        })
        if quote.pix_price is None:
            out["pix_note"] = quote.pix_note
        if not p.is_available:
            same = [c for c in self.store.products.values()
                    if c.category_id == p.category_id and c.is_available and c.id != p.id]
            same.sort(key=lambda c: abs(c.price - p.price))
            out["unavailable_note"] = {
                "discontinued": "No longer part of the catalog: offer equivalent models.",
                "coming_soon": "Not on sale yet: do not promise a date or take it as available.",
            }.get(p.status, "Temporarily out of stock: offer similar models that are available.")
            out["alternatives"] = [self._summary(c) for c in same[:3]]
        return out

    # -- store -----------------------------------------------------------------------------------

    def get_store_info(self) -> dict:
        now = self.clock()
        status = store_status(now)
        in_catalog = sorted({self.store.category_name(p.category_id) for p in self.store.products.values()
                             if p.is_available})
        out = dict(STORE_INFO)
        out["categories_in_catalog"] = in_catalog
        out["now"] = _fmt_dt(now)
        out["open_now"] = status.is_open
        out["today_hours"] = status.today_hours
        out["is_national_holiday_today"] = status.is_holiday
        out["next_opening"] = _fmt_dt(status.next_open) if status.next_open else None
        return out

    # -- orders (identity-protected) --------------------------------------------------------------

    def _authorize(self, order_id: int, contact: str | None) -> tuple[Order | None, dict | None]:
        """Order access rule (D11): order number + e-mail or phone of the order's owner."""
        order = self.store.orders.get(int(order_id))
        # Proving who you are once covers all of that customer's orders, not other customers'.
        if order is not None and order.customer_id in self.session.verified_customers:
            return order, None
        if self.session.locked:
            return None, {"verified": False, "locked": True,
                          "message": "Too many failed verifications. Do not retry; offer a human agent "
                          "(escalate_to_human) or the store's phone."}
        if not contact:
            return None, {"verified": False, "verification_required": True,
                          "message": "Ask the customer for the e-mail or phone registered on the order."}

        if order is not None and self._contact_matches(order, contact):
            self.session.verified_customers.add(order.customer_id)
            return order, None
        self.session.failed_verifications += 1
        return None, dict(_NOT_VERIFIED)

    def _contact_matches(self, order: Order, contact: str) -> bool:
        owner = self.store.customer_of(order)
        if "@" in contact:
            shared = sum(c.email.lower() == owner.email.lower() for c in self.store.customers.values()) > 1
            # Two customers share an e-mail (discovery D9): it cannot prove ownership of an order.
            return not shared and contact.strip().lower() == owner.email.lower()
        given, known = _digits(contact), _digits(owner.phone)
        return len(given) >= 10 and given[-10:] == known[-10:]

    def get_order_status(self, order_id: int, contact: str | None = None) -> dict:
        order, problem = self._authorize(order_id, contact)
        if problem:
            return problem
        customer = self.store.customer_of(order)
        today = self.clock().date()
        out = {
            "verified": True,
            "customer_first_name": customer.name.split()[0],
            "order_id": order.id,
            "status": order.status,
            "status_pt": _STATUS_PT[order.status],
            "order_date": _fmt_date(order.order_date),
            "items": [{"product": self.store.products[i.product_id].name, "quantity": i.quantity}
                      for i in order.items],
            "total": format_brl(order.total),
            "payment": _payment_pt(order.payment_method),
        }
        if order.tracking_code:
            out["tracking_code"] = order.tracking_code
            out["tracking_hint"] = "Can be followed on the Correios or Jadlog website."
        if order.estimated_delivery:
            out["estimated_delivery"] = _fmt_date(order.estimated_delivery)
        if order.notes:
            out["notes"] = order.notes
        out["status_explanation"] = {
            "pending": "Order received and not confirmed yet; there is no tracking code yet.",
            "confirmed": "Order confirmed and not shipped yet; the tracking code is sent by e-mail and "
            "WhatsApp as soon as it ships.",
            "shipped": "Order shipped; use the tracking code.",
            "delivered": "Order delivered.",
            "cancelled": "Order cancelled; the reason is in notes.",
        }[order.status]
        if order.status == "shipped" and order.estimated_delivery and order.estimated_delivery < today:
            out["warning"] = "The delivery estimate has passed: offer to escalate to a human agent."
        return out

    def check_return_eligibility(self, order_id: int, reason: str, contact: str | None = None) -> dict:
        order, problem = self._authorize(order_id, contact)
        if problem:
            return problem
        d = check_return(order, reason, self.clock().date())
        out = {
            "verified": True, "order_id": order.id, "reason": d.reason, "outcome": d.outcome,
            "eligible": d.eligible, "policy_section": d.rule, "explanation": d.explanation,
            "conditions": list(d.conditions),
        }
        for key, value in (("received_on", d.receipt_date), ("deadline", d.deadline)):
            if value:
                out[key] = _fmt_date(value)
        if d.days_left is not None:
            out["days_left"] = d.days_left
        if d.handling:
            out["handling"] = d.handling
        if d.needs_human:
            out["next_step"] = "Call escalate_to_human; do not promise the outcome."
        return out

    # -- payment, shipping, policies, escalation -------------------------------------------------

    def calculate_payment_options(self, amount: float) -> dict:
        try:
            value = Decimal(str(amount))
        except InvalidOperation:
            return {"error": "amount must be a number"}
        plan = installment_plan(value)
        return {
            "amount": format_brl(value),
            "credit_card_installments": [{"count": i.count, "value": format_brl(i.value)} for i in plan],
            "max_installments": plan[-1].count,
            "can_combine_payment_methods": can_combine_payment_methods(value),
            "pix": "5% off the list price when paying with PIX; it does not apply to promotional prices.",
            "boleto": "Paid in full; clears within 3 business days.",
        }

    def estimate_shipping(self, order_total: float, city: str, product: str | None = None) -> dict:
        quote = quote_shipping(Decimal(str(order_total)), city)
        out = {"region": "metro_campo_grande" if quote.kind == "metro" else "other_city", "note": quote.note}
        if quote.kind == "metro":
            out.update({"fee": format_brl(quote.fee), "free_shipping": quote.is_free,
                        "delivery_time": quote.eta,
                        "rule": "Free above R$ 500,00; otherwise a flat fee of R$ 35,00."})
        else:
            out.update({"fee": "needs the destination CEP to quote", "carriers": list(quote.carriers)})
        if product:
            p, _ = self._resolve_product(product)
            if p and needs_special_freight(p):
                out["special_freight"] = "Large instrument: freight needs an individual quote."
        return out

    def search_policies(self, query: str) -> dict:
        hits = self.retriever.search(query, 3)
        if not hits:
            return {"results": [], "note": "Nothing in the manual matches; offer a human agent."}
        return {"results": [{"section": h.chunk.section, "title": h.chunk.breadcrumb, "text": h.chunk.text}
                            for h in hits]}

    def escalate_to_human(self, kind: str, summary: str, order_id: int | None = None,
                          customer_contact: str | None = None) -> dict:
        now = self.clock()
        self.escalations_path.parent.mkdir(parents=True, exist_ok=True)
        ticket = f"T{now:%Y%m%d%H%M%S}-{self.session.id}"
        record = {"ticket": ticket, "created": now.isoformat(), "kind": kind, "summary": summary,
                  "order_id": order_id, "customer_contact": customer_contact, "session": self.session.id}
        with open(self.escalations_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"ticket": ticket, "response_time": "A human agent will reply within 24 business hours."}
