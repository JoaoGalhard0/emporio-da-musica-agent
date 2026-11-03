"""The agent loop: LLM with tools, bounded steps, and a check on quoted amounts."""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from emporio_agent.config import store_now
from emporio_agent.data.store import Store
from emporio_agent.grounding import ungrounded_amounts
from emporio_agent.policies.retriever import PolicyRetriever
from emporio_agent.prompts import build_system_prompt
from emporio_agent.session import Session
from emporio_agent.toolbox import ESCALATIONS_PATH, ToolBox

log = logging.getLogger(__name__)

MAX_STEPS = 6  # LLM round trips per customer message; bounds latency and free-tier quota use

_UNAVAILABLE = (
    "Desculpe, estou com uma instabilidade aqui no momento e não consegui verificar isso agora. "
    "Pode tentar de novo em instantes? Se preferir, a equipe atende pelo (67) 3341-4444."
)
_TOO_MANY_STEPS = (
    "Não consegui concluir essa consulta direito. Posso pedir para alguém da equipe te ajudar? "
    "A gente responde em até 24 horas úteis."
)
_NUDGE = (
    "[automatic check] Your draft quotes these amounts that no tool returned and the customer did not "
    "mention: {amounts}. Call the right tool to get real values, or rewrite the answer without those "
    "amounts. Do not do arithmetic on prices yourself."
)


class ChatModel(Protocol):
    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2) -> dict: ...


@dataclass
class ToolCallTrace:
    name: str
    arguments: str
    result: str


@dataclass
class TurnResult:
    text: str
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    ungrounded: list[str] = field(default_factory=list)  # amounts quoted without a source, after the retry
    failed: bool = False


class Agent:
    def __init__(self, llm: ChatModel, store: Store, retriever: PolicyRetriever,
                 clock: Callable[[], datetime] = store_now, escalations_path: Path = ESCALATIONS_PATH):
        self.llm, self.store, self.retriever = llm, store, retriever
        self.clock, self.escalations_path = clock, escalations_path

    def reply(self, session: Session, user_text: str) -> TurnResult:
        toolbox = ToolBox(self.store, self.retriever, session, self.clock, self.escalations_path)
        system = {"role": "system", "content": build_system_prompt(self.clock())}
        # Work on a copy: the session only keeps messages once the turn has succeeded, so an API
        # failure in the middle never leaves a half-finished tool exchange in the history.
        turn: list[dict] = [{"role": "user", "content": user_text}]
        trace: list[ToolCallTrace] = []
        draft_at: int | None = None  # where the rejected draft sits in `turn`, if one was rejected
        nudge: dict | None = None

        try:
            for _ in range(MAX_STEPS):
                message = self.llm.chat([system, *session.messages, *turn], toolbox.schemas())
                calls = message.get("tool_calls") or []
                if calls:
                    turn.append(message)
                    for call in calls:
                        result = toolbox.call(call["function"]["name"], call["function"].get("arguments", ""))
                        trace.append(ToolCallTrace(call["function"]["name"], call["function"].get("arguments", ""), result))
                        turn.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                    continue

                text = (message.get("content") or "").strip()
                # The nudge lists the rejected amounts, so it must never count as a source for them.
                sources = [m["content"] for m in [*session.messages, *turn]
                           if m.get("role") in ("tool", "user") and m is not nudge
                           and isinstance(m.get("content"), str)]
                loose = ungrounded_amounts(text, sources)
                if loose and draft_at is None:
                    listing = ", ".join(f"R$ {a}" for a in sorted(loose))
                    log.info("Ungrounded amounts in draft, asking the model to fix: %s", listing)
                    draft_at = len(turn)
                    nudge = {"role": "user", "content": _NUDGE.format(amounts=listing)}
                    turn.extend([message, nudge])
                    continue

                if draft_at is not None:
                    # Drop the draft and the nudge: the history keeps only what the customer saw.
                    del turn[draft_at : draft_at + 2]
                turn.append({"role": "assistant", "content": text})
                session.messages.extend(turn)
                return TurnResult(text, trace, [f"R$ {a}" for a in sorted(loose)])
        except Exception:
            log.exception("LLM call failed")
            return TurnResult(_UNAVAILABLE, trace, failed=True)

        return TurnResult(_TOO_MANY_STEPS, trace, failed=True)


def tool_trace_json(trace: list[ToolCallTrace]) -> str:
    return json.dumps([{"tool": t.name, "arguments": t.arguments} for t in trace], ensure_ascii=False)
