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
