from dataclasses import dataclass, field
from datetime import date, timedelta

from emporio_agent.data.models import Order

WITHDRAWAL_DAYS = 7  # 4.1, counted from receipt
DEFECT_EXCHANGE_DAYS = 30  # 4.2, counted from purchase
LEGAL_WARRANTY_DAYS = 90  # 8.1, counted from receipt
PREFERENCE_DAYS = 7  # 4.3

REASONS = ("regret", "defect", "preference")

CONDITIONS = (
    "Product in its original packaging, unused, with all accessories and manuals.",
    "Not eligible: custom setups or special adjustments made to order, items sold as "
    "'final sale' in clearance promotions, and wind instrument mouthpieces (hygiene).",
)


@dataclass(frozen=True)
class ReturnDecision:
    reason: str
    outcome: str
    eligible: bool
    rule: str  # manual section the answer rests on
    receipt_date: date | None
    deadline: date | None
    days_left: int | None
    needs_human: bool
    explanation: str
    conditions: tuple[str, ...] = field(default=CONDITIONS)
    handling: str | None = None


def _no_decision(reason, outcome, rule, explanation, needs_human=False) -> ReturnDecision:
    return ReturnDecision(
        reason=reason, outcome=outcome, eligible=False, rule=rule, receipt_date=None,
        deadline=None, days_left=None, needs_human=needs_human, explanation=explanation,
    )


def check_return(order: Order, reason: str, today: date) -> ReturnDecision:
    """Apply the manual's return rules (sections 4 and 8) to one order on a given day.

    The dataset has no real delivery date, so `estimated_delivery` stands in for the receipt date
    (docs/discovery.md D7). It also has no sales channel, so every order is treated as online, which
    is what makes the 7-day withdrawal right apply.
    """
    if reason not in REASONS:
        raise ValueError(f"reason must be one of {REASONS}")

    if order.status == "cancelled":
        return _no_decision(reason, "order_cancelled", "-", "The order was already cancelled; there is nothing to return.")
    if order.status in ("pending", "confirmed", "shipped"):
        # The withdrawal and preference windows only start on receipt, so nothing has expired.
        return _no_decision(
            reason, "not_received_yet", "4.1",
            f"The order is '{order.status}' and has not been received yet. The 7-day window starts "
            "on receipt. To cancel an order that has not been delivered, a human agent must handle it.",
            needs_human=True,
        )

    receipt = order.estimated_delivery
    if receipt is None:
        return _no_decision(
            reason, "no_delivery_date", "4.1",
            "The delivery date is unknown, so the window cannot be computed; a human must check.",
            needs_human=True,
        )

    since_receipt = (today - receipt).days
    since_purchase = (today - order.order_date).days

    if reason in ("regret", "preference"):
        rule = "4.1" if reason == "regret" else "4.3"
        window = WITHDRAWAL_DAYS if reason == "regret" else PREFERENCE_DAYS
        deadline = receipt + timedelta(days=window)
        left = (deadline - today).days
        within = 0 <= since_receipt <= window
        handling = (
            "Full refund to the original payment method within 10 business days; return freight is "
            "paid by the store."
            if reason == "regret"
            else "Subject to availability of the desired product; any price difference is charged "
            "or refunded."
        )
        return ReturnDecision(
            reason=reason,
            outcome="eligible" if within else "window_expired",
            eligible=within,
            rule=rule,
            receipt_date=receipt,
            deadline=deadline,
            days_left=max(left, 0) if within else None,
            needs_human=False,
            explanation=(
                f"Received on {receipt:%d/%m/%Y}; the {window}-day window ends on {deadline:%d/%m/%Y}."
                + ("" if within else " That date has passed.")
            ),
            handling=handling,
        )

    # reason == "defect"
    if since_purchase <= DEFECT_EXCHANGE_DAYS:
        deadline = order.order_date + timedelta(days=DEFECT_EXCHANGE_DAYS)
        return ReturnDecision(
            reason=reason, outcome="eligible", eligible=True, rule="4.2",
            receipt_date=receipt, deadline=deadline,
            days_left=(deadline - today).days, needs_human=False,
            explanation=f"Manufacturing defects can be exchanged within 30 days of purchase "
            f"(until {deadline:%d/%m/%Y}). Damage from misuse, drops, humidity or unauthorized "
            "changes is not covered.",
            handling="Exchange of the product.",
        )
    legal_end = receipt + timedelta(days=LEGAL_WARRANTY_DAYS)
    if today <= legal_end:
        # 4.2 sends the customer to the manufacturer after 30 days while 8.1 grants a 90-day legal
        # warranty from receipt (discovery P4). Both are stated and a human decides.
        return ReturnDecision(
            reason=reason, outcome="warranty_claim", eligible=False, rule="4.2/8.1",
            receipt_date=receipt, deadline=legal_end, days_left=(legal_end - today).days,
            needs_human=True,
            explanation="The 30-day exchange period has passed, but the 90-day legal warranty "
            f"against manufacturing defects still runs until {legal_end:%d/%m/%Y}. The store can "
            "intermediate the claim with the manufacturer on request.",
            handling="Hand over to a human agent to open the warranty claim.",
        )
    return ReturnDecision(
        reason=reason, outcome="manufacturer_warranty", eligible=False, rule="4.2/8.2",
        receipt_date=receipt, deadline=legal_end, days_left=None, needs_human=False,
        explanation="The 30-day exchange and 90-day legal warranty periods have ended. Only the "
        "manufacturer's own warranty (6 months to 2 years, see the warranty certificate) may apply; "
        "the store can intermediate on request.",
        handling="Offer to intermediate with the manufacturer.",
    )
