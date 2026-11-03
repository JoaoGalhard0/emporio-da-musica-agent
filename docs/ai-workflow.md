# AI collaboration log

Chronological record of how I used AI coding assistants in this project. Each step says what I
asked, what the AI did, and **what I decided**. Tool: Claude Code (CLI, inside VS Code).

Model policy I set: Opus 5.5 (medium effort) for discovery, planning and architecture;
Sonnet 5.5 (high effort) for implementation.

| # | Step | Model / effort |
|---|------|----------------|
| 1 | Reading the challenge statement, policies and CSVs | Sonnet 5.5 (initial session) |
| 2 | Approach and harness proposal | Sonnet 5.5 (initial session) |
| 3 | Repository setup and docs structure | Sonnet 5.5 (initial session) |
| 4 | Language correction (English everywhere) | Sonnet 5.5 |
| 5 | Discovery, requirements traceability and implementation plan | Sonnet 5.5 (see note) |

> Note: the initial steps ran in the first session, before I fixed the model policy above.

## Step 1 — Reading the material
- **I asked:** for context on the challenge and an opinion on how to approach it.
- **AI did:** read the challenge PDF, the policies manual and the CSV headers; flagged initial pitfalls
  (two different phone numbers in the manual, PIX not stacking with promotions, identity
  verification for orders, store does not sell accessories).
- **I decided:** treat those pitfalls as discovery and test material.

## Step 2 — Approach and harness
- **AI proposed:** function calling with typed tools over the data, simple policy search (short
  manual, no heavy vector store), CLI, and a lightweight harness instead of the full one.
- **I decided:** use the OpenAI API; keep the harness **inside** the main repo (extract it to a
  separate repo only if time allows, with a pinned tag); log AI decisions here, separate from system
  decisions (`docs/decisions.md`).

## Step 3 — Repository setup
- **I asked:** create the `emporio-da-musica-agent` repo, run `git init`, and create a `.env` for my key.
- **AI did:** `.gitignore`, `.env` (empty) and `.env.example`, `CLAUDE.md`, docs skeleton.
- **I decided:** the challenge PDF stays out of the repo; the key is never committed.

## Step 4 — Language correction
- **I asked:** make everything in the project English and fix the first commit.
- **AI did:** rewrote the docs and `CLAUDE.md` in English and amended the first commit locally.
- **I decided:** repo artifacts in English; the agent still answers customers in Brazilian Portuguese.

## Step 5 — Discovery, requirements and plan
- **I asked:** discover the data and the PDFs, plan the implementation, and make sure 100% of the
  challenge requirements are covered, with bottlenecks identified.
- **AI did:** profiled all CSVs and cross-checked orders vs items vs products vs promotions; read the
  manual line by line; produced `discovery.md` (13 data findings, 13 policy findings, with handling),
  `requirements.md` (traceability matrix + 10 bottlenecks) and `plan.md` (phases, evals, layout).
  Notable catches: conflicting phone numbers, conflicting installment and defect rules, duplicate
  email (customers 11/43), orders 3 and 20 with totals that do not match their items, an "active"
  product with zero stock, and a `coming_soon` product inside delivered orders.
- **Decided / pending my review:** the assumptions in discovery P1–P4, D7, D8.
- **Model note:** this step ran on Sonnet 5.5 because I had not switched to Opus 5.5 yet; I will
  review the plan with Opus before coding starts.

## Step 6 — Provider change (OpenAI to Gemini free tier)
- **I asked:** switch the LLM provider because my OpenAI account has no credits; pick the best free
  option from the ones the AI had listed.
- **AI did:** searched the current Gemini free-tier limits and OpenAI-compatibility docs; proposed
  Gemini via its OpenAI-compatible endpoint and a provider-agnostic client, so a provider change is
  a config change. Updated D1, D5, D6, D12, bottleneck B1 and the env files.
- **I decided:** Gemini free tier. Open risk the AI flagged: low, unconfirmed free-tier rate limits.
- **Model note:** Sonnet 5.5.

## Step 7 — Phase 0: environment and model choice
- **I asked:** start phase 0 and decide the models after putting my key in `.env`.
- **AI did:** created the venv and pinned `requirements.txt`; wrote `scripts/probe_models.py`; listed
  the 60 models my key can use; tested tool calling on six candidates and burst-tested two finalists.
  Found that the 2.5 models are closed to new users, `gemini-3.8-flash` took 198 s for one call, and
  `gemini-3.5-flash` returns 429 after 6 requests. Recommended `gemini-3.5-flash-lite`.
- **I decided:** accepted the measured recommendation (results are in `docs/decisions.md` D6).
- **Model note:** Sonnet 5.5. The key was read from `.env` by the scripts and never printed.

## Step 8 — Phase 1: data layer
- **I asked:** proceed after pushing the corrected history (I ran the force-push myself).
- **AI did:** typed models, a `Store` loader (UTF-8, `Decimal`, reference checks that fail loudly,
  data-quality notes), accent-insensitive text helpers, an injectable store clock (`STORE_NOW`), and 13
  tests that reproduce the discovery findings.
- **A mistake the tests caught:** the discovery said 49 customers (counted with `wc -l` on a file with
  no trailing newline); the loader says 50. I fixed the test and the discovery doc.
- **Model note:** Sonnet 5.5.

## Step 9 — Phase 2: business rules
- **I asked:** proceed to phase 2.
- **AI did:** pure-function rules for price/PIX, installments, freight, returns and opening hours,
  with 32 tests whose expected values were worked out by hand before running (45 tests in total).
- **AI-proposed choices I accepted:** section 3.1 over the payment table for installments; the 30/90-day
  defect split with a human handoff; treating "above R$ 500" as strictly greater; national holidays as
  closed days (a real-date run on 2026-11-02 correctly reports the store closed).
- **Model note:** Sonnet 5.5.

## Step 10 — Phase 3: policy retrieval
- **I asked:** proceed to phase 3 (and, earlier, whether we follow SOLID / Clean Architecture / FastAPI;
  I chose to keep the pragmatic layered design and defer FastAPI).
- **AI did:** extracted the PDF with `pypdf` layout mode, chunked it into 25 sections, built hybrid
  retrieval (BM25 + embeddings, rank fusion, disk cache, keyword fallback) and a provider-agnostic
  `LLMClient`. Measured keyword vs hybrid on 18 direct and 10 paraphrased questions.
- **Problems found along the way (and fixed):**
  1. Gemini's compatibility layer returns `index=None` on embeddings; sorting by it crashed, and the
     retry on every search burned the free-tier quota (100 embedded texts/minute, counted per text).
     Fixed with response-order reading plus a 60 s cooldown after a failure.
  2. The contact-details fix (P1/P2) I thought I had applied was silently missing: my scripted edit
     matched nothing. A test written before the check caught it; I redid the edit with the Edit tool.
  3. The heading of section 5.2 sits at the bottom of a page and its body on the next, so the manual
     is chunked as one stream rather than page by page.
- **Honest result:** hybrid does not beat keyword on direct questions (both 18/18 in the top 3); it
  doubles top-1 accuracy on paraphrases (8/10 vs 4/10). That is the justification for keeping it.
- **Model note:** Sonnet 5.5.

## Step 11 — Phase 4: tools, identity, agent loop and prompt
- **I asked:** proceed to phase 4; the prompt in English (I decided this when asked).
- **AI did:** 9 tools with identity checks, a session object, the agent loop, the English system prompt,
  a grounding guard for quoted amounts, 48 new tests (106 offline in total) and live smoke runs of the
  four scenarios suggested in the challenge plus accessory and off-topic questions.
- **Bugs the tests caught (all in code the AI had just written):**
  1. A discount of "20" rendered as "2%": `rstrip("0")` ate a zero from an integer. A customer would
     have been shown the wrong discount.
  2. A 4-letter prefix match let "Stradivarius" find "Stratocaster"; replaced with singularized whole
     words.
  3. The internal correction message listed the rejected amounts and was then counted as a valid source
     for them, so a repeated invented price would have passed the guard.
  4. A scripted text replacement silently did nothing; I switched to the Edit tool, which fails loudly.
- **Behavior I tuned after reading real answers:** WhatsApp-style bold instead of Markdown, no details
  beyond the tool result (the model had added a refund detail that is not in the manual), and mention
  of extra matches when a search is truncated.
- **Judgment call the AI made that I should review:** after an eligible return the agent offers to open
  a ticket through `escalate_to_human`; it cannot start a return itself.
- **Model note:** Sonnet 5.5.

## Step 12 — Phase 5: CLI, resume and scripted runner
- **I asked:** proceed to phase 5.
- **AI did:** interactive CLI (`/new`, `/tools`, `/exit`), `--resume`, `--now`, a scripted runner that
  writes Markdown transcripts with tool calls, UTF-8 console setup, and 12 tests (118 offline in
  total). Ran the real entry point against the live model: piped stdin, resume with context, and
  script mode.
- **Gap found by actually running it:** `python -m emporio_agent` failed with "No module named
  emporio_agent": the tests passed only because pytest was configured with `pythonpath = src`. I made
  the project pip-installable so a fresh clone works with `pip install -r requirements.txt`.
- **Decision I kept for the AI's proposal:** FastAPI stays out for now; the agent core is I/O-free so
  an endpoint is a thin wrapper, listed under "what I'd do with more time".
- **Model note:** Sonnet 5.5.
