# Empório da Música — Customer Service Agent

A text-based customer service agent for **Empório da Música**, a fictional musical instrument store in
Campo Grande/MS. It answers on behalf of the store (in Brazilian Portuguese) about the catalog, prices,
promotions, order status, returns, payment, shipping and store policies, using the store's CSV data and
its policies manual.

It is built around one rule from the manual (section 7.1): **never state a price, stock level, deadline or
order status without consulting the system.** The LLM routes the conversation and writes the replies; every
fact comes from a tool, every number with a rule behind it is computed in plain Python, and a few checks in
code back up what the prompt asks for.

- [Quick start](#quick-start) · [Try it](#try-it) · [Example conversations](#example-conversations)
- [Architecture](#architecture) · [Technical decisions](#technical-decisions) · [Assumptions](#assumptions)
- [Tests and evals](#tests-and-evals) · [Known limitations](#known-limitations) · [With more time](#with-more-time)
- [How I used AI assistants](#how-i-used-ai-assistants) · [Repository map](#repository-map)

## Quick start

Requires Python 3.11+ (developed on 3.12) and an API key for any OpenAI-compatible provider. The defaults
target the **Gemini API free tier**: create a key at <https://aistudio.google.com/apikey>.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt   # installs the project (editable) and pytest

copy .env.example .env            # macOS/Linux: cp .env.example .env
# open .env and paste your key after LLM_API_KEY=

python -m emporio_agent --tools --now 2026-02-20T10:00
```

`.env` settings (see `.env.example`):

| Variable | Meaning |
|---|---|
| `LLM_API_KEY` | Provider key. Never committed (`.env` is git-ignored). |
| `LLM_BASE_URL` | OpenAI-compatible endpoint. Default: Gemini's. Any other provider works by changing this. |
| `LLM_MODEL` | Chat model with tool calling. Default `gemini-3.5-flash-lite` (why: [D6](docs/decisions.md)). |
| `EMBEDDING_MODEL` | Embedding model for policy search. Default `gemini-embedding-001`. |
| `LLM_MAX_RPM` | Chat requests per minute the client allows itself (default 12; `0` disables). |

**Free-tier limits you will hit.** On the Gemini free tier this model answers `429` above 15 requests per
minute and after about 500 requests per day. The client paces itself for the first; the second cannot be
worked around (see [D22](docs/decisions.md)). A single conversation costs a handful of requests.

CLI options:

```text
python -m emporio_agent                          interactive chat (commands: /new  /tools  /exit)
  --tools                                        show which tools the agent called
  --now 2026-02-20T10:00                         fix the store clock (see "Try it")
  --resume <session-id>                          continue a saved conversation
  --script file.txt --out transcript.md          replay one customer message per line, write a transcript
```

Sessions and escalation tickets are written to `.conversations/` (git-ignored: they hold customer data).
On Windows set `PYTHONUTF8=1` if accents look garbled in other tools; the CLI already switches to UTF-8.

**HTTP API.** The same agent is available over HTTP for a web widget or a WhatsApp webhook
([D23](docs/decisions.md)):

```bash
uvicorn emporio_agent.api:create_app --factory --port 8000
```

```bash
curl -X POST localhost:8000/chat -H "Content-Type: application/json"      -d '{"message": "Quanto custa o Takamine GD20?"}'
# {"session_id": "9f2c...", "reply": "...", "tools": ["search_products"], "failed": false}
# send "session_id" back in the next request to continue the conversation; GET /health for a liveness check
```

The session id is the only credential of a conversation, so it is a 128-bit random value; an unknown id is a
404 and a provider failure is a 503 (the body still carries the customer-facing text). Interactive docs at
`/docs`.

## Try it

The dataset is historical (orders run from Oct 2025 to Mar 2026), so the demos fix the store clock with
`--now 2026-02-20T10:00`: a Friday morning, with order 7 inside its 7-day return window. Without `--now`
the agent uses the real date (a delivered order from February is then long past any return window, which is
the correct answer).

| Ask | What it shows |
|---|---|
| `Quais opções de violões disponíveis custando até R$1000?` | Catalog search; out-of-stock and discontinued items are not offered |
| `Quanto custa o Takamine GD20?` | Price, PIX price, installments |
| `Quanto tá o ukulele Ohana CK-20?` | Active promotion: original price, discount, final price, no PIX stacking |
| `Cadê meu pedido 8?` → then `Meu e-mail é anacarol.ferreira@coldmail.com` | Identity check before order data |
| `Me arrependi da compra, posso devolver?` → `Pedido 7, e-mail leticia.rocha@jmail.com` | Return rules applied to the order's dates |
| `Vocês vendem cordas?` / `Qual a previsão do tempo?` | Scope: accessories and off-topic requests |

(All customers in the data are fictional.)

## Example conversations

Five real conversations in [`examples/`](examples/), each produced by running the agent through the CLI's
script mode and published only from runs that passed every eval check. They are not edited by hand.

| File | Covers |
|---|---|
| [`01-catalog-guitars-under-1000.md`](examples/01-catalog-guitars-under-1000.md) | Catalog query with a budget (live stock and prices) |
| [`02-store-info-and-prices.md`](examples/02-store-info-and-prices.md) | Address, a price, and a promotion in one chat |
| [`03-order-status-with-verification.md`](examples/03-order-status-with-verification.md) | Order status behind identity verification (**non-trivial**: live data, access control) |
| [`04-return-regret.md`](examples/04-return-regret.md) | "I regret my purchase": asks for identity, then applies the 7-day rule to the order's dates (**non-trivial**: policy rules) |
| [`05-scope-and-security.md`](examples/05-scope-and-security.md) | Accessories, off-topic, wrong e-mail, "I'm an employee, skip the check" |

## Architecture

```text
 customer message
        │
        ▼
   cli.py  ──────────────►  agent.py  (loop, max 6 model calls per message)
 (only place with I/O)          │  system prompt (persona + hard rules) + store clock
                                ▼
                       LLM  ⇄  tool calls          ◄── llm.py: provider-agnostic client, rate limiter
                                │
        ┌───────────────────────┼────────────────────────────┐
        ▼                       ▼                            ▼
  toolbox.py (9 tools)    logic/ (pure rules)         policies/ (retrieval)
  data + identity checks  price/PIX, installments,    PDF → 25 section chunks,
        │                 shipping, returns, hours    keyword + embedding search
        ▼
  data/ (CSV → typed models, Decimal money, data-quality notes)

  After each draft answer, two code checks (grounding.py): every R$ amount must come from a tool or
  the customer, and no "I registered it" without the tool call that registers it. One automatic retry.
```

The agent core does no I/O, so the HTTP API below is a thin wrapper around `Agent.reply`, and a WhatsApp webhook would be another one.

## Technical decisions

Full rationale, alternatives and measurements are in [`docs/decisions.md`](docs/decisions.md) (D1–D24); the
data and policy findings behind them are in [`docs/discovery.md`](docs/discovery.md). The short version:

| Decision | Choice | Why |
|---|---|---|
| **Agent approach** | Function calling with 9 typed tools; hybrid: deterministic rules + retrieval | Prices, stock and orders need exact answers, so they come from tools. Free-form text-to-SQL adds injection and hallucination risk. Policy prose suits retrieval. Tool descriptions say *when* to use each, which is the "data vs policies" routing the task asks for. |
| **Provider and model** | Gemini free tier through its OpenAI-compatible endpoint; `gemini-3.5-flash-lite` | OpenAI was the first choice but the account had no credits, so the provider was swapped by changing `.env`: the client is provider-agnostic ([D12](docs/decisions.md)). The model was picked by measurement: of 6 candidates, 2 were closed to new accounts, one took 198 s for a simple call, one hit `429` after 6 requests, and this one answered in 1.1 s and sustained a burst ([D6](docs/decisions.md)). |
| **Retrieval** | 25 section-level chunks of the manual; BM25 keyword search fused with embedding search; keyword-only fallback when the provider fails | The manual is 8 pages, so a vector database would be over-engineering. Chunks follow the manual's numbering so answers can be traced to a section. Measured: on direct questions both methods hit 18/18 in the top 3; on 10 hard paraphrases the hybrid doubles top-1 accuracy (8/10 vs 4/10), which is why it stays ([D5](docs/decisions.md)). |
| **Rules in code, not in the model** | Price/PIX, installments, shipping, return windows and opening hours are pure Python | The model must not do arithmetic or date math. These functions are unit-tested at their boundaries (day 7 vs 8, R$ 500,00 vs 500,01, 17:59 vs 18:00). |
| **Prompt strategy** | English prompt: persona, tone, tool-first rule, scope, privacy, complaint handling; low temperature; store clock injected every turn | The prompt makes the model behave; the code makes it safe when it does not. Rules that matter are enforced twice. Reply language is pt-BR. |
| **Identity (LGPD)** | Order access needs order number + e-mail or phone of the owner; state is held by the code; locks after 3 failures | Two customers share an e-mail (11 and 43), so e-mail alone cannot prove ownership; "no such order" and "wrong contact" give the identical answer so order numbers cannot be probed ([D16](docs/decisions.md)). |
| **Guards** | Amount grounding and unperformed-action checks, each with one automatic retry | The amount check enforces manual section 7.1 preventively (it never fired in live runs). The action check exists because the failure *was* seen live: "já registrei sua reclamação" with no ticket, about 1 run in 3 ([D17, D21](docs/decisions.md)). |
| **Interface** | Interactive CLI + scripted runner, plus a FastAPI `/chat` endpoint | The task says the focus is the agent working; a CLI reproduces fastest, and script mode generates the example transcripts. The agent core does no I/O, so the HTTP API is a thin wrapper with no duplicated rules ([D7, D23](docs/decisions.md)). |
| **History** | In-memory per session, saved to JSON after each completed turn, `--resume` | Multi-turn coherence (identity verified once, "that one") matters for support; a failed turn is never saved ([D8, D18](docs/decisions.md)). |
| **Data handling** | stdlib `csv` into typed dataclasses; `Decimal` money; UTF-8; reference checks that fail loudly; data-quality notes | 65 products and 20 orders do not justify pandas or a database; fewer dependencies means an easier setup. Both come back with scale (see "With more time"). Stored order totals are reported as-is, never recomputed. |
| **Production model and cost** | Planned, not implemented: a paid tier of the same provider, chosen with cost as a constraint | The free tier (15/min, ~500/day) cannot serve a real store. Rules live in code, so a lite-class model is enough; token use per turn is logged, budget alerts and per-session caps are set, and any larger model must earn its price in the eval suite ([D24](docs/decisions.md)). |

## Assumptions

The statement allows assuming and documenting. These are the ones that change behavior (details in
[`docs/discovery.md`](docs/discovery.md)):

1. **The manual contradicts itself on contact details.** Two phone numbers, `(67) 3341-4444` and `(67) 3321-4500`,
   and two e-mail spellings. I use `3341-4444` (it appears three times, including the official company table)
   and the ASCII `contato@emporiodamusica.com.br`. The store should confirm this.
2. **Installments:** the payment table says R$ 100 minimum for any credit purchase, section 3.1 says R$ 80 for
   4–6x and none above R$ 50 for up to 3x. The specific rule (3.1) wins.
3. **Defects:** the manual says exchange within 30 days of *purchase* (4.2) but also a 90-day legal warranty from
   *receipt* (8.1). The agent states the 30-day exchange, treats days 31–90 as a warranty claim and hands it to
   a human, and after that points to the manufacturer.
4. **Receipt date and channel:** orders carry only `estimated_delivery` and no sales channel. I use the
   estimated delivery as the receipt date and treat every order as online (so the 7-day withdrawal right applies).
5. **"Today":** the data is historical, so the store clock is injectable (`--now`, default real time).
6. **A promotion is "active" only if `is_active = 1`** (the table has no dates). Expired ones are never offered.
7. **"Free shipping above R$ 500"** means strictly above: exactly R$ 500,00 pays the R$ 35,00 fee. Only
   Campo Grande counts as the metro area; other cities need a CEP quote the agent cannot produce, so it does not
   invent a price.
8. **Holidays:** only national holidays are treated as closed days.
9. **A budget filter** ("até R$ 1000") applies to the price the customer actually pays, promotions included.

## Tests and evals

**Offline tests (157, no network):** `pytest`. They cover the data layer against the discovery findings, every
business rule at its boundaries, policy chunking and retrieval, tool behavior and identity checks, the agent loop
with a scripted model, the CLI, the rate limiter, and the eval framework itself.

**Live tests (opt-in):** `pytest -m live` runs the retrieval quality check against the real provider.

**Evals (27 scenarios, real model):** `python evals/run_evals.py` (`--only name ...`, `--repeat N`). Each step
checks behavior, not just wording: which tools were called, whether anyone was verified, and the text. Every reply
also gets implicit checks: the turn did not fail; every R$ amount is grounded; no claimed action without its tool
call; the agent never passes an e-mail or phone the customer did not type; WhatsApp style (no `**`, at most one emoji).

What the evals found, and what they did not finish (honest account):

- Passing was not enough: reading transcripts of a 50/50 run found an order described as "shipped on 15/02" (15/02
  was the *order* date) and a "noted" claim with no tool call. Both are fixed and now caught by checks.
- Real flaws found and fixed: asking for an order number to register a complaint; claiming a registration without
  the tool call (~1 in 3 runs, now guarded, 5/5 afterwards); calling the order tool before having a contact.
- **Last full pass:** 27/27 scenarios (1 run each) passed before the final two fixes. After them only targeted
  re-runs were possible, because the free tier's **500 requests/day** quota ran out. **A full pass on the final
  code was not completed**, and there is no consolidated results file in the repo (I deleted a report polluted by
  the quota errors rather than keep numbers that described the outage). The published examples come from runs that
  passed every check.
- The checks are substring and tool-call assertions. They cannot judge tone or catch every semantic error.

## Known limitations

- **Free-tier quota** (15/min, ~500/day) limits how much anyone can test; latency varies from 1 to 17 s.
- **The HTTP API has no channel authentication, per-customer rate limit or idle-session eviction** (sessions stay in
  memory until restart; saved ones reload from disk). Those belong to the deployment: API gateway, the WhatsApp
  provider's signature check.
- **The guards are narrow:** amounts are checked, dates and percentages are not; action claims use a phrase list.
- **Return windows** rely on the estimated delivery as a proxy for receipt (data limitation).
- **Shipping outside Campo Grande** cannot be priced without a CEP; only carriers and lead times are given.
- **Holidays:** no state/municipal calendar (for example, Campo Grande's anniversary).
- **Retrieval has a known miss:** "o instrumento chegou quebrado" does not surface section 5.2 (damage on delivery).
  The agent still routes it through the return flow or a human, but the manual section is not retrieved.
- **No real integrations:** no WhatsApp, no real ticketing (tickets are lines in a local file), no payment or
  shipping APIs.
- **History is not summarized:** a very long conversation grows the prompt without bound.
- **Local JSON sessions, no channel authentication:** the HTTP API serves several customers at once (worker threads, a lock per session, a thread-safe rate limiter), but sessions live in one process and one folder, so it does not scale across machines, and the channel itself is not authenticated.
- **Data quality is accepted as-is:** orders 3 and 20 have totals that do not match their items, a `coming_soon`
  product appears in a delivered order, and the manual advertises categories the catalog does not have. The agent
  reports what the data says and never claims products the tools do not return.
- **Language:** the agent mirrors the customer's language but was only evaluated in Portuguese.

## With more time

- A WhatsApp webhook next to the existing `/chat` endpoint, with channel authentication and a per-customer rate limit.
- **Production model, with cost in view:** move to a paid tier of the same provider (only `.env` changes), keep a
  lite-class model as the default, log tokens per turn, set a budget alert and a per-session cap, and let a larger
  model in only if the evals show failures the small one cannot fix ([D24](docs/decisions.md)).
- **Scale the data layer:** pandas for analytics over thousands of rows, then SQLite/Postgres once stock and
  orders change during the day or are written by several users. Only the loaders change, because the tools use `Store`.
- **Scale retrieval:** a vector database (pgvector, Qdrant) once the policy corpus is thousands of chunks, is
  updated live or needs metadata filters; with 25 chunks an on-disk embedding cache is exact and free.
- Extend the grounding guard to dates, percentages and deadlines; replace the phrase list with a classifier.
- LLM-as-judge evals for tone and correctness on top of the behavior checks, and a larger retrieval test set.
- A real handoff to a ticketing system, and a state/municipal holiday calendar.
- Conversation summarization, tracing/observability, and a provider fallback when a quota is exhausted.
- Run the full eval suite on every change in CI against a paid-tier key.

## How I used AI assistants

I built this with **Claude Code** (CLI, inside VS Code) as a pair-programming partner. I intended to use Claude
Opus 5.5 (medium effort) for discovery, planning and architecture and Sonnet 5.5 (high effort) for code, but in
practice **every step ran on Sonnet 5.5**; the log says so for each step instead of pretending otherwise.

**How the work was split.** I set the goals, the constraints and the decisions; the assistant read, profiled,
proposed, implemented and ran things. Each phase ended with tests, a commit and an entry in the log:

| # | Step | What the AI did | What I decided |
|---|------|-----------------|----------------|
| 1–3 | Read the challenge, propose an approach, set up the repo | Read the PDF, manual and CSVs; flagged pitfalls; proposed tools + light harness | OpenAI API, harness inside this repo, decisions logged separately from the AI log |
| 4 | Language | Rewrote docs and amended the first commit | Everything in English; the agent still speaks pt-BR |
| 5 | Discovery, requirements, plan | 26 findings with handling, a traceability matrix, 10 bottlenecks | Accepted the assumptions in this README |
| 6–7 | **Provider change** and model choice | Researched the free tier, proposed a provider-agnostic client, measured 6 models | OpenAI had no credits: Gemini free tier; accepted the measured model |
| 8–9 | Data layer and business rules | Typed loaders, pure rules, 45 tests | Section 3.1 wins over the table; the 30/90-day defect split; strictly-above R$ 500 |
| 10 | Policy retrieval | Section chunker, hybrid search, measured it | Kept the hybrid because of the paraphrase result |
| 10 | Architecture question | Said plainly that this is layered, **not** Clean Architecture or FastAPI | Keep it pragmatic; FastAPI deferred (built later, step 16) |
| 11 | Tools, identity, loop, prompt | 9 tools, grounding guard, 48 tests, live smoke runs | Prompt in English |
| 12–13 | CLI and evals | CLI, scripted runner, 27 scenarios, example transcripts | Publish examples only from fully passing runs |
| 14 | Final live round | Found the hallucinated registration; added guards and a rate limiter | Approved the fixes; the quota stopped the last full pass |
| 15 | Review of my justifications | Judged them sound, found a duplicated decision section, an out-of-order one and five stale statuses | Pandas and a vector DB go to "what comes next"; replace CLI-only with an endpoint; paid model in production, with cost kept viable |
| 16 | HTTP API | FastAPI `/chat` and `/health`, 12 tests, a real request; chose a 128-bit session id | Asked for it; confirmed the id choice |
| 17 | Final check-up | Re-read the code, ran tests and lint, found that its own API made the rate limiter unsafe across threads, fixed it with a test | Kept stylistic lint hints out of tested code on delivery day |

**Where the AI was wrong, and what caught it.** Writing this down is part of the point: the AI made real
mistakes, and tests, evals or reading the output caught them.

- A discount of 20% rendered as "2%" (`rstrip("0")` on an integer); the unit test caught it.
- A prefix search let "Stradivarius" find "Stratocaster"; a test caught it.
- The internal correction message listed the rejected prices and was then counted as a valid source for them,
  so an invented price would have passed the guard; a test caught it.
- The count of customers was wrong (49 instead of 50) from counting lines of a file with no trailing newline;
  the loader's test caught it.
- Scripted text replacements silently did nothing (twice); I moved to the Edit tool, which fails loudly.
- It said an order "shipped on 15/02" (the order date) and claimed to have registered things it had not.
  Reading the transcripts caught the first; the live evals caught the second.
- The HTTP API ran the model client from several threads while the rate limiter assumed one; the re-read
  after building the API caught it, and it now has a lock and a test.
- A first real API request failed with HTTP 400 and I blamed the API; the shell's `curl` had mangled an accent.
- A full eval pass was started with `--fresh`, which destroyed the accumulated results file. That was the
  assistant's mistake and it is logged as such.

**Git history.** The history is incremental, with small semantic commits in the order the work happened. There was
one force-push, early and before anything was delivered, to rewrite the first commits in English after I decided
the repository language (step 4); there has been none since.

**Where I overrode or redirected it.** The provider (OpenAI, then Gemini), English-only repo, keeping the
architecture pragmatic, and publishing only passing, unedited transcripts. The complete, numbered account, with
the model used at each step, is in [`docs/ai-workflow.md`](docs/ai-workflow.md).

**Project harness.** `CLAUDE.md` is the project's context file for the assistant: sources of truth, language and
privacy rules, commit rules, commands, the living-docs list and the model policy. Together with `docs/` it is a
lightweight harness: someone new (human or agent) can read `CLAUDE.md`, then `docs/requirements.md`,
`discovery.md`, `decisions.md` and `ai-workflow.md`, and know what was built, why, and what is still open.

## Repository map

```text
src/emporio_agent/
  cli.py api.py agent.py toolbox.py tool_schemas.py prompts.py grounding.py session.py llm.py config.py
  data/        CSV loading, typed models, text helpers
  logic/       pricing, payment, shipping, returns, store hours (pure functions)
  policies/    PDF chunker, hybrid retriever
tests/         offline unit tests (157)          evals/        live behavior evals (27 scenarios)
examples/      5 real conversations               docs/         requirements, discovery, decisions, ai-workflow, plan
data/          the store's CSVs and policies PDF  CLAUDE.md     project context for AI assistants
```
