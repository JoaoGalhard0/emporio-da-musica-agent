"""Enforce manual section 7.1 in code: never state a price the system did not provide.

Every R$ amount in the agent's answer must appear in a tool result of the conversation or in the
customer's own messages. The prompt asks for this; this check is what makes it reliable.
"""
import re
from decimal import Decimal
from typing import Iterable

_AMOUNT = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_REAIS = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*reais", re.IGNORECASE)


def amounts(text: str) -> set[Decimal]:
    found = set()
    for whole, cents in _AMOUNT.findall(text):
        found.add(Decimal(whole.replace(".", "") + "." + (cents or "0").ljust(2, "0")))
    for whole in _REAIS.findall(text):
        found.add(Decimal(whole.replace(".", "")))
    return found


def ungrounded_amounts(answer: str, sources: Iterable[str]) -> set[Decimal]:
    """Amounts quoted in `answer` that appear in none of `sources` (tool outputs, user messages)."""
    allowed: set[Decimal] = set()
    for source in sources:
        allowed |= amounts(source)
    return amounts(answer) - allowed
