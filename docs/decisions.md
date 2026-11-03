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
- **Status:** accepted (validated by the live evals, D20).

## D3 — Repository language: English
- All code, docs, prompts and commit messages are in English. The agent replies to customers in
  Brazilian Portuguese (store audience), switching language only if the customer does.
- **Status:** accepted.

## D4 — Data layer: stdlib `csv` + typed dataclasses, no pandas, no database
- **Alternatives:** pandas, SQLite.
- **Rationale:** 65 products and 20 orders do not justify either; fewer dependencies means an easier
  setup for the evaluator. Money uses `Decimal`; `specs` JSON is parsed at load; files are UTF-8.
- **When this stops being right:** pandas earns its place for analytics over thousands of rows
  (sales reports, bulk imports); a database (SQLite, then Postgres) when the data is written by
  several users at once, changes during the day (real stock, real orders) or no longer fits in
  memory. Until then the loaders are the only code that would change, because the tools talk to
  `Store`, not to the files.
- **Status:** accepted.

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
- **When a vector database becomes right:** with 25 chunks, an in-memory index plus an on-disk
  embedding cache is exact and free. A vector store (pgvector, Qdrant) pays off once the corpus is
  thousands of chunks, is updated while running, or needs filtering by metadata (product line,
  policy version). The retriever's interface (`search(query) -> sections`) would not change.
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

## D7 — Interface: interactive CLI (+ scripted runner for evals), then an HTTP API (D23)
- **Alternatives:** API (FastAPI), notebook, simple web UI.
- **Rationale:** the statement says the focus is the agent working. A CLI is the fastest to
  reproduce; a non-interactive runner reuses the same agent core to generate the example
  transcripts. The agent core has no I/O, so other front ends are thin wrappers: the HTTP API
  was added later exactly that way (D23).
- **Status:** accepted.

## D8 — Conversation history: in-memory per session, persisted to JSON
- **Rationale:** multi-turn coherence (e.g. identity verified once, "that one" refers to the last
  product) is part of a good support experience. Persisting to `.conversations/<session>.json`
  allows resuming a chat. Verified identity is session state, never inferred by the model.
- **Status:** accepted.

## D9 — Prompt strategy: persona + hard rules + tool-first, low temperature
- **Rules in the prompt:** reply in pt-BR with the store's tone; never state price, stock, deadline
  or order status without a tool result; show original price + discount % for promotions; redirect
  accessories; refuse off-topic; escalate complaints and exceptions to a human; never reveal other
  customers' data.
- **Why not rely on the prompt alone:** the critical rules are also enforced in code (identity check
  in the order tools, price/PIX logic, eligibility math), so a prompt failure cannot leak data or
  invent numbers.
- **Status:** accepted (the guards D17 and D21 came from failures seen live).

## D10 — Reference time is injected
- `STORE_TODAY` / `now` is a parameter, default real time in America/Campo_Grande. Examples use a
  fixed date for reproducibility. Needed because the dataset is historical (discovery D8).
- **Status:** accepted.

## D11 — Verification before order access
- Order tools require the order id plus the customer's email **or** phone, matched against the order
  owner (discovery D9). Failures return a generic message that does not confirm whether the order exists.
- **Status:** accepted (privacy rule from manual section 9).

## D12 — Provider-agnostic LLM client
- **Decision:** one thin wrapper around the OpenAI-compatible chat/embeddings API, configured by
  `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDING_MODEL`. The rest of the code never imports a
  provider-specific SDK.
- **Why:** the provider already had to change once during this project; this keeps the next change
  cheap. Rate-limit handling (retry with backoff, request throttle) lives in this wrapper only.
- **Status:** accepted.

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

## D19 — CLI details (builds on D7 and D8)
- One module (`cli.py`) does all I/O; `python -m emporio_agent` chats, `--resume ID` continues a
  saved session, `--now ISO` fixes the store clock, `--tools` shows tool calls.
- **Scripted mode** (`--script file.txt --out file.md`) replays one customer message per line through
  the same agent and writes a Markdown transcript with the tool calls. The example conversations are
  produced this way, so they are real runs and reproducible, not hand-written.
- The session is saved after every completed turn (a crash loses nothing) and never after a failed
  one. Sessions and escalation tickets live in `.conversations/`, which is git-ignored because it
  holds customer data.
- The CLI sets stdout/stdin to UTF-8, because the default Windows code page garbles accents.
- The project is pip-installable (`pyproject.toml`, `requirements.txt` = `-e .[dev]`) so a fresh
  clone runs with two commands.
- **FastAPI:** built afterwards as a thin wrapper, see D23.
- **Status:** accepted.

## D20 — Evals check behavior, not wording
- **Framework** (`evals/`): scripted customer conversations; each step has checks on the tools called,
  the session state (who is verified) and the reply text. 27 scenarios cover the four scenarios
  suggested in the challenge plus identity attacks, prompt injection, scope and complaints.
- **Implicit checks on every reply:** the turn did not fail; every R$ amount is grounded (D17); no
  Markdown bold or headings (WhatsApp style); at most one emoji; no first-person claim of an action
  ("registrei", "abri um chamado") without the tool call that performs it; and the agent never
  passes an e-mail or phone the customer did not type.
- The framework has its own offline tests: an eval with a bug would misreport the agent.
- **Known limit:** checks look for substrings and tool calls. They cannot judge tone or catch every
  semantic error, which is why the example transcripts were also read by a human (see ai-workflow).
- **Examples are published only from runs that passed every check**, unedited, by the runner itself.
- **Status:** accepted.

## D21 — A claimed action needs the tool call that performs it
- Live evals showed the model saying "já registrei sua reclamação" (and inventing a ticket number)
  without calling `escalate_to_human`, in about 1 of 3 runs, although the prompt forbids it.
- `grounding.unperformed_actions` detects first-person claims ("registrei", "anotei", "abri um
  chamado", "encaminhei"...) when no `escalate_to_human` call happened in the turn. The agent loop
  then gives the model one automatic correction request, same mechanism as the amount guard (D17);
  the rejected draft is dropped from the history, and a persistent claim is reported in the turn result.
- Result: the complaint scenario went from 2/3 to 5/5 live runs.
- **Limit:** a phrase list; it will not catch every wording.
- **Status:** accepted.

## D22 — Pacing the provider: 15 requests/minute and 500 requests/day on the free tier
- **Measured on 2026-11-03:** `gemini-3.5-flash-lite` answers 429 above **15 chat requests per
  minute** and, after about 500 requests, **for the rest of the day** ("retry in 11h41m"). Earlier
  phase 0 numbers (12 in a row) were below the minute limit. The daily limit was exhausted by development
  and eval runs, which blocked the last full eval run.
- `RateLimiter` in `llm.py` keeps chat calls under `LLM_MAX_RPM` (default 12) with a sliding window,
  so a minute-limit 429 is avoided instead of recovered from. It cannot help with the daily limit.
- A full eval pass costs roughly 130 requests; the whole suite fits in one day, development and
  repeated runs together do not. Anyone evaluating on a free key should expect this.
- **Status:** accepted.

## D23 — HTTP API: a thin FastAPI wrapper over the same agent
- **Why:** a customer-facing channel (web widget, WhatsApp webhook) speaks HTTP, not a terminal. The
  agent core already does no I/O (D7), so `api.py` only moves text in and out; no rule was duplicated.
- **Contract:** `POST /chat {message, session_id?}` returns `{session_id, reply, tools, failed}`;
  `GET /health`. Run with `uvicorn emporio_agent.api:create_app --factory`.
- **Session id is the credential.** Verified identity lives in the session (D16), so whoever holds the
  id continues a verified conversation. API sessions therefore use a full 128-bit random id (the CLI's
  8 characters are not enough once the id travels over a network), unknown or malformed ids get a 404
  (the client cannot pick its own id, and `../x` never reaches the file system).
- **Concurrency:** the endpoint is a plain `def`, so FastAPI runs it in a worker thread and a slow LLM
  call does not stall other customers; a per-session lock stops two messages of one chat from
  interleaving. Sessions are persisted exactly like the CLI (after a completed turn, never after a failed one).
- **Failure:** a provider failure is HTTP 503 (clients can retry) and the body still carries the
  customer-facing fallback text.
- **Not built, on purpose:** authentication of the channel itself, rate limiting per customer, and
  eviction of idle sessions from memory. Those belong to the deployment (API gateway, WhatsApp
  provider signature check) and are listed in the README limitations.
- **Verified:** 12 offline tests with a scripted model, plus one real request against the Gemini
  free tier (tool called, grounded answer).
- **Status:** accepted.

## D24 — Production: a paid model, with cost as a constraint
- **Why not the free tier in production:** 15 requests/minute and about 500/day (D22) cannot serve a
  real store, and free-tier terms on availability and on how customer messages may be used differ from paid ones
  (to be checked against the provider's terms, since conversations hold customer data). A paid tier
  of the same provider is the lowest-risk change: only `.env` changes (D12).
- **Cost is a design input, not an afterthought.** What keeps the bill small:
  - the arithmetic and policy rules are code, so the model never needs to be a "big" reasoning model;
  - a `flash-lite`-class model is the default; a larger one is only worth it if evals show failures
    the small one cannot fix (the same eval suite is the gate, D20);
  - at most `MAX_STEPS` = 6 model calls per message, and one automatic retry per guard;
  - the system prompt is identical across turns, so provider-side prompt caching applies where offered;
  - embeddings are computed once and cached on disk (D5).
- **Cost model:** a turn costs 2-4 chat requests (tool call, then answer), and a full eval pass about
  130 requests (D22). Multiply the tokens logged per turn by the provider's current price list to get
  cost per conversation; that number is to be measured before launch, not assumed here.
- **Before launch:** log tokens per turn, set a monthly budget alert and a per-session message cap,
  and re-run the evals on the chosen paid model. Switching models is a configuration change plus an
  eval run, never a code change.
- **Status:** proposed (a plan, not implemented: this prototype runs on the free tier).
