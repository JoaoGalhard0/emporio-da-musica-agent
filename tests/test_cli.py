"""Phase 5: the command line front end, driven by a scripted model (no network, no real stdin)."""
import os
from datetime import datetime

import pytest

from emporio_agent.agent import Agent
from emporio_agent.cli import chat_loop, main, read_script, run_script, to_markdown
from emporio_agent.config import STORE_TZ
from emporio_agent.data.store import Store
from emporio_agent.llm import LLMNotConfigured
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


def agent_with(llm, store, retriever, tmp_path):
    return Agent(llm, store, retriever, clock=lambda: NOW, escalations_path=tmp_path / "esc.jsonl")


def feed(*lines):
    it = iter(lines)

    def read(_prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return read


class Out(list):
    def __call__(self, text):
        self.append(text)

    @property
    def text(self):
        return "\n".join(self)


def test_chat_loop_answers_and_saves_the_session(store, retriever, tmp_path):
    out = Out()
    agent = agent_with(ScriptedLLM(say("Oi! Em que posso ajudar?")), store, retriever, tmp_path)
    session = chat_loop(agent, Session(id="s1"), tmp_path, feed("oi", "/exit"), out)
    assert "Assistant: Oi! Em que posso ajudar?" in out.text
    assert Session.load(tmp_path, "s1").messages == session.messages
    assert "--resume s1" in out.text


def test_eof_ends_the_chat_cleanly(store, retriever, tmp_path):
    out = Out()
    chat_loop(agent_with(ScriptedLLM(), store, retriever, tmp_path), Session(), tmp_path, feed(), out)
    assert "saved" not in out.text  # nothing was said, nothing to save


def test_commands_do_not_reach_the_model_and_tools_can_be_shown(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_store_info", {}), say("Estamos abertos até as 18h."))
    out = Out()
    chat_loop(agent_with(llm, store, retriever, tmp_path), Session(), tmp_path,
              feed("/tools", "", "vocês estão abertos?", "/exit"), out)
    assert "(tool calls shown)" in out.text and "[tool] get_store_info({})" in out.text
    assert len(llm.calls) == 2  # only the real question and its tool round trip


def test_new_command_starts_a_fresh_session(store, retriever, tmp_path):
    llm = ScriptedLLM(say("a"), say("b"))
    out = Out()
    first = Session(id="old")
    chat_loop(agent_with(llm, store, retriever, tmp_path), first, tmp_path, feed("um", "/new", "dois", "/exit"), out)
    assert len(first.messages) == 2  # "dois" went to the new session, not the old one
    assert "(new session" in out.text


def test_failed_turn_is_not_saved(store, retriever, tmp_path):
    out = Out()
    agent = agent_with(ScriptedLLM(RuntimeError("503")), store, retriever, tmp_path)
    session = chat_loop(agent, Session(id="s2"), tmp_path, feed("oi", "/exit"), out)
    assert "instabilidade" in out.text and session.messages == []
    assert not (tmp_path / "s2.json").exists()


def test_resume_continues_with_the_previous_history(store, retriever, tmp_path):
    first = ScriptedLLM(say("Olá!"))
    chat_loop(agent_with(first, store, retriever, tmp_path), Session(id="r1"), tmp_path, feed("oi", "/exit"), Out())

    second = ScriptedLLM(say("De nada."))
    out = Out()
    chat_loop(agent_with(second, store, retriever, tmp_path), Session.load(tmp_path, "r1"), tmp_path,
              feed("obrigado", "/exit"), out)
    assert "Resuming session r1" in out.text
    sent = second.calls[0]  # system + the earlier exchange + the new message
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]


# -- script mode ---------------------------------------------------------------------------------

def test_read_script_skips_comments_and_blank_lines(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# Catalog question\n\n# a note\nviolões até 1000\nE com PIX?\n", encoding="utf-8")
    assert read_script(f) == ("Catalog question", ["violões até 1000", "E com PIX?"])


def test_markdown_transcript_shows_tool_calls(store, retriever, tmp_path):
    llm = ScriptedLLM(call("get_product", {"product": "Takamine GD20"}), say("Sai por R$ 2.199,00."))
    turns = run_script(agent_with(llm, store, retriever, tmp_path), Session(), ["Quanto custa o Takamine GD20?"])
    md = to_markdown("Price check", turns, NOW, "scripted")
    assert md.startswith("# Price check")
    assert "**Customer:** Quanto custa o Takamine GD20?" in md
    assert '`get_product({"product": "Takamine GD20"})`' in md
    assert "**Assistant:** Sai por R$ 2.199,00." in md
    assert "20/02/2026 10:00" in md and "`scripted`" in md


# -- main() --------------------------------------------------------------------------------------

def test_main_script_mode_writes_the_transcript(store, retriever, tmp_path, monkeypatch):
    monkeypatch.delenv("STORE_NOW", raising=False)
    script = tmp_path / "in.txt"
    script.write_text("# Hours\nEstão abertos?\n", encoding="utf-8")
    out_file = tmp_path / "out" / "t.md"
    agent = agent_with(ScriptedLLM(say("Sim!")), store, retriever, tmp_path)
    code = main(["--script", str(script), "--out", str(out_file), "--now", "2026-02-20T10:00"],
                agent_factory=lambda: agent, write=Out())
    assert code == 0 and "**Assistant:** Sim!" in out_file.read_text(encoding="utf-8")
    assert os.environ["STORE_NOW"] == "2026-02-20T10:00"
    monkeypatch.delenv("STORE_NOW", raising=False)


def test_main_script_mode_exits_nonzero_when_a_turn_fails(store, retriever, tmp_path):
    script = tmp_path / "in.txt"
    script.write_text("oi\n", encoding="utf-8")
    agent = agent_with(ScriptedLLM(RuntimeError("down")), store, retriever, tmp_path)
    assert main(["--script", str(script), "--out", str(tmp_path / "t.md")], agent_factory=lambda: agent, write=Out()) == 1


def test_main_reports_missing_configuration(tmp_path):
    def broken():
        raise LLMNotConfigured("Missing in .env: LLM_API_KEY (see .env.example)")

    out = Out()
    assert main([], agent_factory=broken, write=out) == 2
    assert "Configuration error" in out.text and "LLM_API_KEY" in out.text


def test_main_rejects_a_bad_clock_and_an_unknown_session(store, retriever, tmp_path):
    out = Out()
    assert main(["--now", "yesterday"], agent_factory=lambda: None, write=out) == 2
    agent = agent_with(ScriptedLLM(), store, retriever, tmp_path)
    assert main(["--resume", "nope", "--sessions-dir", str(tmp_path)], agent_factory=lambda: agent, write=out) == 2
    assert "No saved session" in out.text
