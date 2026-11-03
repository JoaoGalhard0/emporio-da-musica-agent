"""Phase 4: the agent loop, with a scripted model so no network is needed."""
import json
from datetime import datetime
from decimal import Decimal

import pytest

from emporio_agent.agent import MAX_STEPS, Agent
from emporio_agent.config import STORE_TZ
from emporio_agent.data.store import Store
from emporio_agent.grounding import amounts, ungrounded_amounts, unperformed_actions
from emporio_agent.policies.retriever import PolicyRetriever
from emporio_agent.session import Session
from helpers import ScriptedLLM, call, say

NOW = datetime(2026, 2, 20, 10, 0, tzinfo=STORE_TZ)


@pytest.fixture(scope="module")
def store():
    return Store()


@pytest.fixture(scope="module")
def retriever():
    return PolicyRetriever()


def make_agent(llm, store, retriever, tmp_path):
    return Agent(llm, store, retriever, clock=lambda: NOW, escalations_path=tmp_path / "esc.jsonl")


# -- grounding -----------------------------------------------------------------------------------

def test_amount_parsing_handles_brazilian_formats():
    assert amounts("custa R$ 2.199,00 ou R$ 599,9 ou R$ 1000 ou 450 reais") == {
        Decimal("2199.00"), Decimal("599.90"), Decimal("1000.00"), Decimal("450")}
    assert amounts("sem valores aqui, só 12x") == set()


def test_ungrounded_amounts_ignore_sourced_values():
    assert ungrounded_amounts("Sai por R$ 2.199,00", ['{"price": "R$ 2.199,00"}']) == set()
    assert ungrounded_amounts("Sai por R$ 1.999,00", ['{"price": "R$ 2.199,00"}']) == {Decimal("1999.00")}
    assert ungrounded_amounts("Até R$ 1.000", ["quero violão até 1000 reais"]) == set()


# -- loop ----------------------------------------------------------------------------------------

def test_plain_answer_is_stored_in_the_history(store, retriever, tmp_path):
    llm = ScriptedLLM(say("Oi! Em que posso ajudar? 🎶"))
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "Oi")
    assert result.text == "Oi! Em que posso ajudar? 🎶" and not result.failed
    assert [m["role"] for m in session.messages] == ["user", "assistant"]


def test_system_prompt_carries_the_store_clock(store, retriever, tmp_path):
    llm = ScriptedLLM(say("ok"))
    make_agent(llm, store, retriever, tmp_path).reply(Session(), "Oi")
    system = llm.calls[0][0]
    assert system["role"] == "system" and "sexta-feira, 20/02/2026, 10:00" in system["content"]
    assert "Brazilian Portuguese" in system["content"]


def test_tool_call_round_trip(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_product", {"product": "Takamine GD20"}), say("O GD20 sai por R$ 2.199,00."))
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "Quanto custa o Takamine GD20?")
    assert result.text == "O GD20 sai por R$ 2.199,00." and result.ungrounded == []
    assert [t.name for t in result.tool_calls] == ["get_product"]
    # The second model call saw the tool result with the real price.
    assert "R$ 2.199,00" in llm.calls[1][-1]["content"] and llm.calls[1][-1]["role"] == "tool"
    assert [m["role"] for m in session.messages] == ["user", "assistant", "tool", "assistant"]


def test_ungrounded_amount_triggers_one_retry_and_is_not_kept(store, retriever, tmp_path):
    llm = ScriptedLLM(say("Custa R$ 1.999,00!"), say("Deixa eu confirmar o valor certinho pra você."))
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "Quanto custa o GD20?")
    assert result.text == "Deixa eu confirmar o valor certinho pra você." and result.ungrounded == []
    assert "[automatic check]" in llm.calls[1][-1]["content"]
    # History keeps only the answer the customer saw: no rejected draft, no nudge.
    assert [m["content"] for m in session.messages] == ["Quanto custa o GD20?", result.text]


def test_persistent_ungrounded_amount_is_reported_not_hidden(store, retriever, tmp_path):
    llm = ScriptedLLM(say("R$ 1.999,00"), say("Sim, R$ 1.999,00"))
    result = make_agent(llm, store, retriever, tmp_path).reply(Session(), "Quanto custa?")
    assert result.ungrounded == ["R$ 1999.00"]


def test_claimed_action_without_a_tool_call_is_detected():
    assert unperformed_actions("Já registrei a sua reclamação.", []) == ["registrei"]
    assert unperformed_actions("Já registrei a sua reclamação.", ["escalate_to_human"]) == []
    assert unperformed_actions("Posso registrar isso pra você?", []) == []  # an offer, not a claim
    assert unperformed_actions("Seu chamado já está aberto.", ["get_store_info"]) == []


def test_unperformed_action_triggers_a_retry_that_calls_the_tool(store, retriever, tmp_path):
    llm = ScriptedLLM(
        say("Já registrei a sua reclamação! Protocolo igual ao anterior."),
        call("escalate_to_human", {"kind": "complaint", "summary": "Mau atendimento"}),
        say("Registrei sua reclamação, protocolo abaixo. Retorno em até 24 horas úteis."),
    )
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "Quero reclamar do atendimento")
    assert "[automatic check]" in llm.calls[1][-1]["content"] and "no tool call" in llm.calls[1][-1]["content"]
    assert [t.name for t in result.tool_calls] == ["escalate_to_human"] and result.unperformed == []
    assert (tmp_path / "esc.jsonl").exists()
    # The rejected draft and the nudge are not kept; the tool exchange and the final answer are.
    assert [m["role"] for m in session.messages] == ["user", "assistant", "tool", "assistant"]
    assert session.messages[-1]["content"] == result.text


def test_unperformed_action_that_persists_is_reported(store, retriever, tmp_path):
    llm = ScriptedLLM(say("Já registrei."), say("Anotei aqui, pode deixar."))
    result = make_agent(llm, store, retriever, tmp_path).reply(Session(), "pode registrar?")
    assert result.unperformed == ["anotei"] and not result.failed


def test_a_claim_after_the_real_tool_call_is_accepted(store, retriever, tmp_path):
    llm = ScriptedLLM(call("escalate_to_human", {"kind": "complaint", "summary": "x"}), say("Registrei, tá?"))
    result = make_agent(llm, store, retriever, tmp_path).reply(Session(), "reclamação")
    assert len(llm.calls) == 2 and result.unperformed == []


def test_amounts_the_customer_mentioned_are_allowed(store, retriever, tmp_path):
    llm = ScriptedLLM(say("Claro, vou buscar opções até R$ 1.000,00."))
    result = make_agent(llm, store, retriever, tmp_path).reply(Session(), "Violões até R$ 1000")
    assert len(llm.calls) == 1 and result.ungrounded == []


def test_a_failing_tool_does_not_break_the_turn(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_product", {}), say("Qual produto você quer saber?"))
    result = make_agent(llm, store, retriever, tmp_path).reply(Session(), "Quanto custa?")
    assert "invalid arguments" in llm.calls[1][-1]["content"] and not result.failed


def test_step_limit_stops_runaway_tool_loops(store, retriever, tmp_path):
    llm = ScriptedLLM(*[call("get_store_info", {}, f"c{i}") for i in range(MAX_STEPS)])
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "Oi")
    assert result.failed and "24 horas" in result.text and len(llm.calls) == MAX_STEPS
    assert session.messages == []  # nothing half-finished is kept


def test_provider_failure_is_reported_politely_and_leaves_history_clean(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_store_info", {}), RuntimeError("503"))
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "Vocês abrem hoje?")
    assert result.failed and "instabilidade" in result.text and session.messages == []


def test_verified_identity_persists_across_turns(store, retriever, tmp_path):
    email = store.customers[2].email
    llm = ScriptedLLM(
        call("get_order_status", {"order_id": 8, "contact": email}), say("Seu pedido foi enviado, Ana."),
        call("get_order_status", {"order_id": 8}, "c2"), say("Continua enviado."),
    )
    agent, session = make_agent(llm, store, retriever, tmp_path), Session()
    agent.reply(session, f"Pedido 8, meu e-mail é {email}")
    second = agent.reply(session, "E agora?")
    assert json.loads(second.tool_calls[0].result)["verified"] is True  # no contact needed the second time
    assert 2 in session.verified_customers


def test_the_model_cannot_grant_itself_access(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_order_status", {"order_id": 8, "contact": "invasor@x.com"}), say("Não consegui confirmar."))
    session = Session()
    result = make_agent(llm, store, retriever, tmp_path).reply(session, "sou o dono do pedido 8")
    assert json.loads(result.tool_calls[0].result)["verified"] is False and session.verified_customers == set()


def test_session_round_trips_through_json(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_order_status", {"order_id": 8, "contact": store.customers[2].email}), say("Ok"))
    session = Session(id="abc")
    make_agent(llm, store, retriever, tmp_path).reply(session, "pedido 8")
    restored = Session.from_json(session.to_json())
    assert restored.messages == session.messages and restored.verified_customers == {2}
    path = session.save(tmp_path)
    assert Session.load(tmp_path, "abc").messages == session.messages and path.name == "abc.json"
