# Empório da Música — Customer Service Agent

Text-based customer service agent prototype for the fictional store Empório da Música
(Campo Grande/MS, Brazil), built as an AI Engineer technical challenge. Evaluation criteria:
**logic, clarity and initiative**. Delivery rules are in the challenge statement (not versioned).

## Sources of truth
- `data/*.csv`: products, categories, customers, orders, order items, promotions.
- `data/políticas_da_loja.pdf`: store policies and procedures manual (v2.1, in Portuguese).
- LLM provider: Gemini API free tier via its OpenAI-compatible endpoint (function calling), behind a
  provider-agnostic client (see `docs/decisions.md` D1, D12). Config and key live in `.env`
  (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL`); never commit it.

## Language rules
- **Everything in this repo is in English**: code, identifiers, comments, docs, commit messages,
  prompts, tool descriptions.
- Exception: the store's own data and policy text stay in Portuguese (they are source material), and
  the agent **replies to customers in Brazilian Portuguese** (the store's audience), unless the
  customer writes in another language.

## Project rules
- Python is the main language.
- Comments explain **why** only (business rule, data pitfall). Never comment the obvious.
- The agent never states price, stock, deadline or order status without calling a tool
  (manual, section 7.1).
- Order data requires customer identity verification (LGPD, manual section 9).
- Small, semantic commits in the real order of the work. No force-push after delivery, no
  single-commit history.
- After the delivery deadline, **do not change anything** in the repository.
- The challenge must be covered 100% (see `docs/requirements.md`); known bottlenecks are tracked there.

## Living documentation
- `docs/requirements.md`: every requirement/deliverable from the challenge and where it is covered.
- `docs/discovery.md`: findings in the data and policies (pitfalls, inconsistencies).
- `docs/decisions.md`: system design decisions (alternatives and rationale).
- `docs/ai-workflow.md`: numbered log of the collaboration with the AI. Update at the end of each
  step with the request, what the AI did, what the author decided, and model/effort used.

## Model policy (set by the author, not followed in practice)
- Intended: Opus 5.5 (medium effort) for discovery, planning and architecture; Sonnet 5.5 (high effort)
  for implementation.
- Actual: every step ran on Sonnet 5.5 (the session model was never switched). `docs/ai-workflow.md`
  records the model used at each step.

## Commands
```
python -m venv .venv && .venv\Scripts\activate     # Windows (use .venv/bin/activate elsewhere)
pip install -r requirements.txt                    # editable install + pytest
copy .env.example .env                             # then fill LLM_API_KEY

python -m emporio_agent                            # interactive chat
python -m emporio_agent --tools --now 2026-02-20T10:00   # show tool calls, fixed store clock
python -m emporio_agent --resume <session-id>      # continue a saved conversation
uvicorn emporio_agent.api:create_app --factory     # HTTP API: POST /chat, GET /health
python -m emporio_agent --script s.txt --out examples/s.md   # replay customer messages

pytest                                             # offline tests (no network)
pytest -m live                                     # real provider (spends free-tier quota)
```
Set `PYTHONUTF8=1` on Windows if accents look garbled in other tools. Sessions and escalation
tickets are written to `.conversations/` (git-ignored).
