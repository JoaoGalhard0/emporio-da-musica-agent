"""The eval framework itself must be right, otherwise it would misreport the agent's quality."""
import pytest

import framework as fw
from emporio_agent.agent import Agent, TurnResult, ToolCallTrace
from emporio_agent.data.store import Store
from emporio_agent.policies.retriever import PolicyRetriever
from emporio_agent.session import Session
from helpers import ScriptedLLM, call, say
from run_evals import run_scenario
from scenarios import SCENARIOS


@pytest.fixture(scope="module")
def store():
    return Store()


def obs(text="", tools=(), session=None, ungrounded=(), failed=False, so_far=None):
    trace = [ToolCallTrace(n, "{}", "{}") for n in tools]
    result = TurnResult(text, trace, list(ungrounded), failed)
    return fw.Observed("pergunta", result, session or Session(), so_far if so_far is not None else trace)


def passes(check, o):
    return check.run(o) is None


def test_text_checks_ignore_accents_and_case():
    o = obs("Está ABERTO até as 18:00")
    assert passes(fw.says("aberto", "18:00"), o) and passes(fw.says_any("fechado", "ESTÁ"), o)
    assert not passes(fw.silent_on("aberto"), o) and passes(fw.silent_on("domingo"), o)


def test_tool_checks_distinguish_this_step_from_the_whole_scenario():
    earlier = [ToolCallTrace("get_order_status", "{}", "{}")]
    o = obs("ok", tools=["get_store_info"], so_far=earlier + [ToolCallTrace("get_store_info", "{}", "{}")])
    assert passes(fw.calls("get_store_info"), o) and passes(fw.no_calls("get_order_status"), o)
    assert not passes(fw.never_called("get_order_status"), o)


def test_tool_arg_matches_the_actual_argument():
    result = TurnResult("x", [ToolCallTrace("check_return_eligibility", '{"reason": "regret", "order_id": 7}', "{}")])
    o = fw.Observed("q", result, Session(), result.tool_calls)
    assert passes(fw.tool_arg("check_return_eligibility", "reason", "regret"), o)
    assert not passes(fw.tool_arg("check_return_eligibility", "reason", "defect"), o)


def test_verification_checks_read_the_session_not_the_reply():
    s = Session()
    assert passes(fw.nobody_verified(), obs(session=s))
    s.verified_customers.add(2)
    assert passes(fw.customer_verified(2), obs(session=s)) and not passes(fw.nobody_verified(), obs(session=s))


@pytest.mark.parametrize("text, kwargs, broken", [
    ("Tudo certo!", {}, None),
    ("Isso é **muito** bom", {}, "no markdown"),
    ("# Título\ntexto", {}, "no markdown"),
    ("Oi 🎸🎶", {}, "at most one emoji"),
    ("Já registrei que você prefere ligação.", {}, "claimed action"),
    ("Já registrei sua reclamação.", {"tools": ["escalate_to_human"]}, None),
    ("Seu chamado já está aberto com a equipe.", {}, None),
    ("Custa R$ 5,00", {"ungrounded": ["R$ 5.00"]}, "R$ amount"),
    ("", {}, "not empty"),
    ("Desculpe", {"failed": True}, "provider failure"),
])
def test_implicit_checks(text, kwargs, broken):
    problems = [c.name for c in fw.IMPLICIT if c.run(obs(text, **kwargs))]
    if broken is None:
        assert problems == []
    else:
        assert any(broken in p for p in problems)


def test_scenarios_are_well_formed():
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names))
    assert all(s.steps and all(step.checks for step in s.steps) for s in SCENARIOS)
    assert all(s.title for s in SCENARIOS)


def test_run_scenario_reports_failures_with_the_step(store, tmp_path, monkeypatch):
    monkeypatch.setattr("run_evals.PAUSE_SECONDS", 0)
    llm = ScriptedLLM(call("get_product", {"product": "Takamine GD20"}), say("O GD20 custa R$ 2.199,00."))
    agent = Agent(llm, store, PolicyRetriever(), escalations_path=tmp_path / "e.jsonl")
    scenario = fw.Scenario("t", "t", [fw.Step("Quanto custa o GD20?", [fw.calls("get_product"), fw.says("9.999,00")])])
    outcome = run_scenario(agent, scenario, fw.Ctx(store))
    assert not outcome.passed and outcome.failures == ["step 1: says ('9.999,00',)"]
    monkeypatch.delenv("STORE_NOW", raising=False)


def test_run_scenario_passes_a_correct_conversation(store, tmp_path, monkeypatch):
    monkeypatch.setattr("run_evals.PAUSE_SECONDS", 0)
    llm = ScriptedLLM(call("get_product", {"product": "Takamine GD20"}), say("O GD20 custa R$ 2.199,00."))
    agent = Agent(llm, store, PolicyRetriever(), escalations_path=tmp_path / "e.jsonl")
    scenario = fw.Scenario("t", "t", [fw.Step("Quanto custa o GD20?", [fw.calls("get_product"), fw.says("2.199,00")])])
    assert run_scenario(agent, scenario, fw.Ctx(store)).passed
    monkeypatch.delenv("STORE_NOW", raising=False)

def test_invented_contact_is_caught():
    from emporio_agent.agent import ToolCallTrace as T
    s = Session(messages=[{"role": "user", "content": "pedido 8, meu e-mail é Ana@Mail.com e tel (67) 99654-7821"}])

    def with_contact(contact):
        r = TurnResult("ok", [T("get_order_status", '{"order_id": 8, "contact": "%s"}' % contact, "{}")])
        return fw.Observed("q", r, s, r.tool_calls)

    ok = next(c for c in fw.IMPLICIT if "contact the customer did not type" in c.name)
    assert passes(ok, with_contact("ana@mail.com")) and passes(ok, with_contact("67996547821"))
    assert not passes(ok, with_contact("outro@mail.com")) and not passes(ok, with_contact("(67) 90000-0000"))
    assert passes(ok, obs("sem tools"))
