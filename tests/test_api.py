"""The HTTP front end, driven by a scripted model (no network)."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from emporio_agent.agent import Agent
from emporio_agent.api import create_app
from emporio_agent.config import STORE_TZ
from emporio_agent.data.store import Store
from emporio_agent.policies.retriever import PolicyRetriever
from helpers import ScriptedLLM, call, say

NOW = datetime(2026, 2, 20, 10, 0, tzinfo=STORE_TZ)


@pytest.fixture(scope="module")
def store():
    return Store()


@pytest.fixture(scope="module")
def retriever():
    return PolicyRetriever()


def client_for(llm, store, retriever, tmp_path):
    agent = Agent(llm, store, retriever, clock=lambda: NOW, escalations_path=tmp_path / "esc.jsonl")
    return TestClient(create_app(lambda: agent, sessions_dir=tmp_path))


def test_health(store, retriever, tmp_path):
    client = client_for(ScriptedLLM(), store, retriever, tmp_path)
    assert client.get("/health").json() == {"status": "ok"}


def test_new_conversation_returns_a_long_session_id_and_the_tools_used(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_store_info", {"topic": "address"}), say("Estamos na Av. Afonso Pena."))
    client = client_for(llm, store, retriever, tmp_path)

    body = client.post("/chat", json={"message": "Qual o endereço da loja?"}).json()

    assert body["reply"] == "Estamos na Av. Afonso Pena."
    assert body["tools"] == ["get_store_info"]
    assert body["failed"] is False
    assert len(body["session_id"]) == 32
    assert (tmp_path / f"{body['session_id']}.json").exists()


def test_second_message_continues_the_same_history(store, retriever, tmp_path):
    llm = ScriptedLLM(say("Olá! Como posso ajudar?"), say("Claro, me conta mais."))
    client = client_for(llm, store, retriever, tmp_path)

    first = client.post("/chat", json={"message": "Oi"}).json()
    client.post("/chat", json={"message": "Quero um violão", "session_id": first["session_id"]})

    texts = [m.get("content") for m in llm.calls[1]]
    assert "Oi" in texts and "Olá! Como posso ajudar?" in texts


def test_session_survives_a_server_restart(store, retriever, tmp_path):
    first = client_for(ScriptedLLM(say("Olá!")), store, retriever, tmp_path)
    session_id = first.post("/chat", json={"message": "Oi"}).json()["session_id"]

    llm = ScriptedLLM(say("De novo por aqui."))
    restarted = client_for(llm, store, retriever, tmp_path)
    assert restarted.post("/chat", json={"message": "Voltei", "session_id": session_id}).status_code == 200
    assert "Olá!" in [m.get("content") for m in llm.calls[0]]


@pytest.mark.parametrize("session_id", ["deadbeefdeadbeefdeadbeefdeadbeef", "../secrets", "ZZZZZZZZ", "abc"])
def test_unknown_or_malformed_session_is_404(store, retriever, tmp_path, session_id):
    client = client_for(ScriptedLLM(), store, retriever, tmp_path)
    response = client.post("/chat", json={"message": "Oi", "session_id": session_id})
    assert response.status_code == 404


@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "x" * 2001}])
def test_invalid_message_is_422(store, retriever, tmp_path, payload):
    client = client_for(ScriptedLLM(), store, retriever, tmp_path)
    assert client.post("/chat", json=payload).status_code == 422


def test_provider_failure_is_503_with_the_customer_facing_text_and_is_not_saved(store, retriever, tmp_path):
    client = client_for(ScriptedLLM(RuntimeError("429")), store, retriever, tmp_path)

    response = client.post("/chat", json={"message": "Oi"})

    assert response.status_code == 503
    assert response.json()["failed"] is True
    assert "instabilidade" in response.json()["reply"]
    assert list(tmp_path.glob("*.json")) == []
