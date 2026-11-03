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

## Model policy (set by the author)
- Discovery, planning and architecture decisions: Opus 5.5, medium effort.
- Code implementation: Sonnet 5.5, high effort.

## Commands
Filled in as the project is built (see README).
