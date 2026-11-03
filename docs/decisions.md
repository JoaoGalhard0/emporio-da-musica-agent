# System design decisions

Format: decision, alternatives considered, rationale. Status is `proposed` until validated by tests
or evals, then `accepted`.

## D1 — LLM provider: OpenAI API
- **Alternatives:** Claude API, Gemini free tier, local model via Ollama.
- **Rationale:** the author has OpenAI credits; function calling is mature and fits the case.
- **Status:** accepted. Exact model: see D6.

## D2 — Approach: function calling with typed tools, hybrid retrieval
- **Alternatives:** pure RAG over everything, free-form text-to-SQL agent, generic ReAct loop.
- **Rationale:** structured questions (price, stock, orders) need exact answers; free-form SQL adds
  injection and hallucination risk; policy text is short prose that suits retrieval. A small set of
  typed tools bounds what the model can do and makes "when to consult data vs policies" explicit.
- **Status:** proposed.

## D3 — Repository language: English
- All code, docs, prompts and commit messages are in English. The agent replies to customers in
  Brazilian Portuguese (store audience), switching language only if the customer does.
- **Status:** accepted.

## D4 — Data layer: stdlib `csv` + typed dataclasses, no pandas, no database
- **Alternatives:** pandas, SQLite.
- **Rationale:** 65 products and 20 orders do not justify either; fewer dependencies means an easier
  setup for the evaluator. Money uses `Decimal`; `specs` JSON is parsed at load; files are UTF-8.
- **Status:** proposed.

## D5 — Policies: section-level chunks + embedding search, numbers computed in code
- **Alternatives:** whole manual in the system prompt; keyword/BM25 only.
- **Rationale:** the manual is short, so retrieval is cheap and stays inspectable. Chunk by manual
  section (~25 chunks) so every answer can cite "section N". Embeddings (`text-embedding-3-small`)
  are cached on disk. Rules with arithmetic or dates (installments, PIX, freight, return window,
  opening hours) live in Python, because the model must not do that math. Prose rules (scope,
  warranty exclusions, complaints) come from retrieval.
- **Risk:** retrieval misses a section (B6). Mitigation: top-k=3, evals per topic.
- **Status:** proposed.

## D6 — Model: a "mini"-class OpenAI model with tool use, chosen from the key's real model list
- **Rationale:** the task is tool routing plus short answers; a small model keeps cost and latency
  low. Decision is finalized in phase 0 after listing the models the key can access, and recorded
  here with the measured eval results. `OPENAI_MODEL` makes it swappable.
- **Status:** proposed, finalize in phase 0.

## D7 — Interface: interactive CLI (+ scripted runner for evals)
- **Alternatives:** API (FastAPI), notebook, simple web UI.
- **Rationale:** the statement says the focus is the agent working. A CLI is the fastest to
  reproduce; a non-interactive runner reuses the same agent core to generate the example
  transcripts. The agent core has no I/O, so a WhatsApp/API front end can be added later.
- **Status:** proposed.

## D8 — Conversation history: in-memory per session, persisted to JSON
- **Rationale:** multi-turn coherence (e.g. identity verified once, "that one" refers to the last
  product) is part of a good support experience. Persisting to `.conversations/<session>.json`
  allows resuming a chat. Verified identity is session state, never inferred by the model.
- **Status:** proposed.

## D9 — Prompt strategy: persona + hard rules + tool-first, low temperature
- **Rules in the prompt:** reply in pt-BR with the store's tone; never state price, stock, deadline
  or order status without a tool result; show original price + discount % for promotions; redirect
  accessories; refuse off-topic; escalate complaints and exceptions to a human; never reveal other
  customers' data.
- **Why not rely on the prompt alone:** the critical rules are also enforced in code (identity check
  in the order tools, price/PIX logic, eligibility math), so a prompt failure cannot leak data or
  invent numbers.
- **Status:** proposed.

## D10 — Reference time is injected
- `STORE_TODAY` / `now` is a parameter, default real time in America/Campo_Grande. Examples use a
  fixed date for reproducibility. Needed because the dataset is historical (discovery D8).
- **Status:** accepted.

## D11 — Verification before order access
- Order tools require the order id plus the customer's email **or** phone, matched against the order
  owner (discovery D9). Failures return a generic message that does not confirm whether the order exists.
- **Status:** accepted (privacy rule from manual section 9).
