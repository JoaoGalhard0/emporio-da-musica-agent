"""Enforce manual section 7.1 in code: never state a price the system did not provide.

Every R$ amount in the agent's answer must appear in a tool result of the conversation or in the
customer's own messages. The prompt asks for this; this check is what makes it reliable.
"""
import re
from decimal import Decimal
from typing import Iterable

from emporio_agent.data.text import normalize

_AMOUNT = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")
_REAIS = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*reais", re.IGNORECASE)


def amounts(text: str) -> set[Decimal]:
    found = set()
    for whole, cents in _AMOUNT.findall(text):
        found.add(Decimal(whole.replace(".", "") + "." + (cents or "0").ljust(2, "0")))
    for whole in _REAIS.findall(text):
        found.add(Decimal(whole.replace(".", "")))
    return found


# First-person claims of a completed action. The only action the agent can actually perform is
# registering a ticket (escalate_to_human); it cannot send, forward or edit anything else.
ACTION_CLAIMS = ("registrei", "anotei", "abri um chamado", "abri um atendimento", "abri o chamado",
                 "abri uma solicitacao", "enviei", "encaminhei", "acrescentei", "adicionei", "atualizei")


def unperformed_actions(answer: str, tools_called: Iterable[str]) -> list[str]:
    """Actions the answer says were done although no tool call in this turn did them.

    Seen in live evals: "já registrei sua reclamação" without calling escalate_to_human, plus an
    invented ticket number. The prompt forbids it; this check makes it reliable.
    """
    if "escalate_to_human" in set(tools_called):
        return []
    text = normalize(answer)
    return [claim for claim in ACTION_CLAIMS if claim in text]


def ungrounded_amounts(answer: str, sources: Iterable[str]) -> set[Decimal]:
    """Amounts quoted in `answer` that appear in none of `sources` (tool outputs, user messages)."""
    allowed: set[Decimal] = set()
    for source in sources:
        allowed |= amounts(source)
    return amounts(answer) - allowed
