"""Tiny eval framework: scripted customer conversations with checks on behavior, not only wording.

A check inspects the tools the agent called, the session state (who is verified) and the reply text.
Every step also gets the implicit checks in `IMPLICIT`, which encode rules that must always hold.
"""
import re
from dataclasses import dataclass, field
from typing import Callable

from emporio_agent.agent import ToolCallTrace, TurnResult
from emporio_agent.data.store import Store
from emporio_agent.data.text import normalize
from emporio_agent.grounding import unperformed_actions
from emporio_agent.session import Session

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


@dataclass
class Ctx:
    """Lets scenarios refer to real customer data (e-mails, phones) without hardcoding it."""

    store: Store

    def email(self, customer_id: int) -> str:
        return self.store.customers[customer_id].email

    def phone(self, customer_id: int) -> str:
        return self.store.customers[customer_id].phone


@dataclass
class Observed:
    user: str
    result: TurnResult
    session: Session
    calls_so_far: list[ToolCallTrace]  # every tool call from the start of the scenario to this step

    @property
    def reply(self) -> str:
        return normalize(self.result.text)

    @property
    def step_tools(self) -> list[str]:
        return [c.name for c in self.result.tool_calls]


@dataclass
class Check:
    name: str
    fn: Callable[[Observed], bool]

    def run(self, obs: Observed) -> str | None:
        return None if self.fn(obs) else self.name


# -- checks --------------------------------------------------------------------------------------

def calls(*names: str) -> Check:
    return Check(f"calls {', '.join(names)}", lambda o: all(n in o.step_tools for n in names))


def calls_any(*names: str) -> Check:
    return Check(f"calls one of {', '.join(names)}", lambda o: any(n in o.step_tools for n in names))


def no_calls(*names: str) -> Check:
    return Check(f"does not call {', '.join(names)}", lambda o: not any(n in o.step_tools for n in names))


def never_called(*names: str) -> Check:
    return Check(
        f"never called {', '.join(names)} so far",
        lambda o: not any(c.name in names for c in o.calls_so_far),
    )


def says(*parts: str) -> Check:
    return Check(f"says {parts}", lambda o: all(normalize(p) in o.reply for p in parts))


def says_any(*parts: str) -> Check:
    return Check(f"says any of {parts}", lambda o: any(normalize(p) in o.reply for p in parts))


def silent_on(*parts: str) -> Check:
    return Check(f"does not say {parts}", lambda o: not any(normalize(p) in o.reply for p in parts))


def customer_verified(*ids: int) -> Check:
    return Check(f"customers {ids} verified", lambda o: set(ids) <= o.session.verified_customers)


def nobody_verified() -> Check:
    return Check("nobody verified", lambda o: not o.session.verified_customers)


def tool_arg(tool: str, key: str, expected) -> Check:
    def fn(o: Observed) -> bool:
        import json
        for c in o.result.tool_calls:
            if c.name == tool and json.loads(c.arguments or "{}").get(key) == expected:
                return True
        return False

    return Check(f"{tool}({key}={expected!r})", fn)


def _claims_action_without_tool(o: Observed) -> bool:
    """Independent check of the final reply, using the same phrase list as the agent's own guard:
    the guard retries once, this verifies that the answer the customer actually saw is clean."""
    return bool(unperformed_actions(o.result.text, o.step_tools))


def _contact_was_typed_by_customer(o: Observed) -> bool:
    """The model may only pass an e-mail/phone it was given. Inventing one would be guessing at
    someone's identity, which is the attack the verification exists to stop."""
    import json
    typed = " ".join(m["content"] for m in o.session.messages
                     if m["role"] == "user" and isinstance(m.get("content"), str))
    typed_text, typed_digits = typed.lower(), re.sub(r"\D", "", typed)
    for c in o.result.tool_calls:
        contact = json.loads(c.arguments or "{}").get("contact")
        if not contact:
            continue
        if "@" in contact:
            if contact.lower() not in typed_text:
                return False
        elif re.sub(r"\D", "", contact) not in typed_digits:
            return False
    return True


# Rules that apply to every reply of every scenario.
IMPLICIT = [
    Check("never passes a contact the customer did not type", _contact_was_typed_by_customer),
    Check("no claimed action without the tool call that does it", lambda o: not _claims_action_without_tool(o)),
    Check("turn completed (no provider failure)", lambda o: not o.result.failed),
    Check("every R$ amount comes from a tool or the customer", lambda o: not o.result.ungrounded),
    Check("reply is not empty", lambda o: bool(o.result.text.strip())),
    Check("no markdown **bold** or # headings (WhatsApp style)",
          lambda o: "**" not in o.result.text and not re.search(r"^#{1,6} ", o.result.text, re.M)),
    Check("at most one emoji", lambda o: len(_EMOJI.findall(o.result.text)) <= 1),
]


# -- scenarios -----------------------------------------------------------------------------------

@dataclass
class Step:
    user: str | Callable[[Ctx], str]
    checks: list[Check] = field(default_factory=list)

    def text(self, ctx: Ctx) -> str:
        return self.user(ctx) if callable(self.user) else self.user


@dataclass
class Scenario:
    name: str
    title: str
    steps: list[Step]
    now: str = "2026-02-20T10:00"  # Friday 10:00, store open
    example: str | None = None  # file stem in examples/ if this run is published as an example
