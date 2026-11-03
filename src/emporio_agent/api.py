"""HTTP front end: the same agent behind a small JSON API, for a web widget or a WhatsApp webhook.

    uvicorn emporio_agent.api:create_app --factory

POST /chat  {"message": "...", "session_id": "<optional>"}  ->  {"session_id", "reply", "tools", "failed"}
GET  /health

Like the CLI, this module only moves text in and out; every rule lives in the agent core.
"""
import re
import threading
import uuid
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from emporio_agent.agent import Agent
from emporio_agent.cli import SESSIONS_DIR, build_agent
from emporio_agent.session import Session

# The id is the only credential of a conversation (verified identity lives in the session), so API
# sessions get a full 128-bit id instead of the 8 characters the CLI uses. The pattern also keeps an
# id from ever becoming a path like "../x" when it is used as a file name.
_SESSION_ID = re.compile(r"^[0-9a-f]{8,32}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, description="omit to start a new conversation")


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tools: list[str] = Field(description="names of the tools the agent called for this message")
    failed: bool = False


def create_app(agent_factory: Callable[[], Agent] = build_agent, sessions_dir: Path = SESSIONS_DIR) -> FastAPI:
    agent = agent_factory()  # fails at startup, not on the first customer, when the key is missing
    app = FastAPI(title="Empório da Música agent", version="0.1.0")
    sessions: dict[str, Session] = {}
    locks: dict[str, threading.Lock] = {}

    def find_session(session_id: str) -> Session:
        if not _SESSION_ID.match(session_id):
            raise HTTPException(404, "Unknown session")
        if session_id not in sessions:
            try:
                sessions[session_id] = Session.load(sessions_dir, session_id)
            except FileNotFoundError:
                raise HTTPException(404, "Unknown session") from None
        return sessions[session_id]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # A plain `def`, so FastAPI runs it in a worker thread: the LLM call blocks and must not stall
    # other customers. The per-session lock keeps two messages of one chat from interleaving.
    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest):
        if request.session_id is None:
            session = Session(id=uuid.uuid4().hex)
            sessions[session.id] = session
        else:
            session = find_session(request.session_id)

        with locks.setdefault(session.id, threading.Lock()):
            result = agent.reply(session, request.message)
            if not result.failed:
                session.save(sessions_dir)

        body = ChatResponse(session_id=session.id, reply=result.text,
                            tools=[t.name for t in result.tool_calls], failed=result.failed)
        # A provider failure is a 503 so a client can retry; the body still carries the customer-facing text.
        return JSONResponse(body.model_dump(), status_code=503) if result.failed else body

    return app
