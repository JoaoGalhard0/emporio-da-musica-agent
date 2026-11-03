# System design decisions

Format: decision, alternatives considered, rationale. Status is `proposed` until validated by tests
or evals, then `accepted`.

## D1 — LLM provider: Gemini API free tier, through its OpenAI-compatible endpoint
- **Changed on 2026-11-02.** The first choice was the OpenAI API, dropped because the author's
  account has no credits.
- **Alternatives:** OpenAI API (no credits), Claude API (paid), local model via Ollama (no key or
  quota, but weaker tool calling and depends on the evaluator's hardware).
- **Rationale:** Gemini has a free tier that needs no billing, supports function calling and
  embeddings, and handles Portuguese well. Its OpenAI-compatible endpoint lets the code use the
  standard `openai` SDK with a configurable `base_url`, so the provider is **a configuration
  change, not a code change**: an evaluator with an OpenAI key, or a local Ollama, can run the
  project by editing `.env`.
- **Known caveats (from Google's docs and forum reports):** free-tier rate limits are low and
  unconfirmed (third-party sources cite roughly 5–10 requests/minute on flash models); the
  compatibility layer has had gaps in streaming tool calls, so the agent uses non-streaming calls;
  free-tier prompts may be used by the provider, which is acceptable here because all data is fictional.
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
  section (~25 chunks) so every answer can cite "section N". Embeddings (model set by
  `EMBEDDING_MODEL`, served by the same provider) are cached on disk, so the free-tier quota is
  spent once. Rules with arithmetic or dates (installments, PIX, freight, return window,
  opening hours) live in Python, because the model must not do that math. Prose rules (scope,
  warranty exclusions, complaints) come from retrieval.
- **Risk:** retrieval misses a section (B6). Mitigation: top-k=3, evals per topic.
- **Built in phase 3:** 25 chunks (one per numbered section, with the parent title as breadcrumb);
  hybrid search = BM25 keyword + embeddings, fused by reciprocal rank; embeddings cached on disk;
  keyword-only fallback when the provider fails, with a 60 s cooldown so a quota error is not hammered.
- **Measured (2026-11-03, `gemini-embedding-001`, top-3 unless noted):**

  | Query set | Keyword only | Hybrid |
  |-----------|--------------|--------|
  | 18 direct customer questions (top-3) | 18/18 | 18/18 |
  | 18 direct questions (top-1) | 15/18 | 15/18 |
  | 10 hard paraphrases (top-1) | 4/10 | **8/10** |
  | 10 hard paraphrases (top-3) | 8/10 | **9/10** |

  Keyword search alone is enough for questions that reuse the manual's words; embeddings earn their
  place on paraphrases ("comprei ontem e já não quero mais" -> 4.1). Known miss for both:
  "o instrumento chegou quebrado" does not surface 5.2 (damage on delivery).
- **Status:** accepted.

## D6 — Model: `gemini-3.5-flash-lite` (chat) and `gemini-embedding-001` (embeddings)
- **Method:** phase 0 listed the 60 models the key can use and ran `scripts/probe_models.py`
  (one tool-calling request per candidate) plus a 12-request burst on the finalists, on 2026-11-02.
- **Measured results**

  | Model | Tool call on the probe | Latency | Free-tier burst |
  |-------|------------------------|---------|-----------------|
  | `gemini-2.5-flash`, `gemini-2.5-flash-lite` | 404, "no longer available to new users" | — | — |
  | `gemini-3.8-flash` | correct | **198 s** | not tested |
  | `gemini-3.1-flash-lite` | correct | 11.8 s | not tested |
  | `gemini-3.5-flash` | correct | 4.3 s | **429 on the 7th request** (about 5 RPM) |
  | `gemini-3.5-flash-lite` | correct | **1.1 s** | **12/12 ok in 10 s** |

- **Decision:** `gemini-3.5-flash-lite`. It called the tool correctly, is the fastest and is the only
  finalist that sustains a multi-request agent loop on the free tier. `gemini-3.5-flash` stays as an
  optional higher-quality setting via `LLM_MODEL`, but its quota makes it unfit for evals.
- **Embeddings:** `gemini-embedding-001` (stable, 3072 dimensions, probe ok) over
  `gemini-embedding-2`, which is newer with no benefit for ~25 short chunks.
- **Caveat:** quotas observed on one day, for one project; they may differ for the evaluator. The
  client (D12) retries 429s with backoff.
- **Status:** accepted. Re-check against eval results in phase 6.

## D12 — Provider-agnostic LLM client
- **Decision:** one thin wrapper around the OpenAI-compatible chat/embeddings API, configured by
  `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL`. The rest of the code never imports a
  provider-specific SDK.
- **Why:** the provider already had to change once during this project; this keeps the next change
  cheap. Rate-limit handling (retry with backoff, request throttle) lives in this wrapper only.
- **Status:** accepted.

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

## D13 — Business rules are pure Python, resolved once, covered by tests
- **Decision:** pricing/PIX, installments, freight, return eligibility and opening hours are pure
  functions in `src/emporio_agent/logic/`. They take the reference date/time as a parameter and
  return structured results (including the manual section used), which the tools hand to the LLM.
- **Resolved contradictions:**
  - Installments (P3): section 3.1 wins over the table (min R$ 50 up to 3x, R$ 80 for 4-6x, R$ 100
    for 7-12x), so R$ 560 can be paid in 6x.
  - Defects (P4): exchange within 30 days of purchase; from day 31 up to 90 days after receipt it is
    a legal-warranty claim and goes to a human; later, only the manufacturer's warranty.
  - "Free shipping above R$ 500" excludes exactly R$ 500.00.
- **Holidays:** national holidays (fixed dates, Consciência Negra, Good Friday computed from Easter)
  count as closed. State and municipal holidays are not in the material: known limitation.
- **Status:** accepted.

## D14 — Contradictory contact details are fixed at load time, not left to the model
- The manual lists two phone numbers and two e-mail spellings (discovery P1, P2). The chunker rewrites
  the minority values to the chosen ones (`(67) 3341-4444`, `emporiodamusica.com.br`), so retrieval
  cannot show the model both. The PDF stays untouched; the rule is visible in code and tested.
- **Status:** accepted (to be confirmed with the store, see README assumptions).

## D15 — Nine tools, facts only from tool results
- **Tools:** `search_products`, `get_product`, `get_store_info`, `get_order_status`,
  `check_return_eligibility`, `calculate_payment_options`, `estimate_shipping`, `search_policies`,
  `escalate_to_human`. Descriptions say *when* to use each: that is the data-vs-policies routing.
- Money is returned already formatted ("R$ 2.199,00") so the model copies instead of computing.
- Catalog search matches whole words after singularizing ("violões" = "violão"). A 4-letter prefix
  match was tried first and rejected: "Stradivarius" matched "Stratocaster".
- A budget filter ("até R$ 1000") applies to the price the customer pays, promotions included; PIX is a
  payment choice and does not change the filter.
- **Status:** accepted.

## D16 — Identity is code state, locked after 3 misses
- `get_order_status` and `check_return_eligibility` need the order number plus the e-mail or phone of
  the order's owner. Success is stored in `Session.verified_customers` by the tool, never by the model;
  once a customer is verified, their other orders need no re-check, other customers' orders still do.
- An e-mail shared by two customers (11 and 43) cannot prove ownership; the phone can.
- "No such order" and "wrong contact" return the identical answer, so order numbers cannot be probed.
  Three failures lock the session (an already-verified customer keeps access).
- **Status:** accepted.

## D17 — Grounding guard on quoted amounts
- Every R$ amount in the final answer must appear in a tool result or in the customer's own messages
  (`grounding.py`). If not, the model gets one automatic correction request; the rejected draft and the
  request are dropped from the history. If it still fails, the answer is delivered and the amounts are
  reported in the turn result, which the evals assert is empty.
- Why: manual section 7.1 forbids stating prices without consulting the system; the prompt asks for it,
  this makes it checkable.
- **Limitation:** it checks amounts only, not dates, percentages or deadlines.
- **Status:** accepted.

## D18 — History is committed only when a turn completes
- A turn works on a copy of the history; it is appended to the session only after the final answer.
  A provider error or a step limit (6 model calls) leaves the session clean and returns a polite
  fallback message in Portuguese.
- **Status:** accepted.
