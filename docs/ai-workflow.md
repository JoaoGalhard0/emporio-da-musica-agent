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
