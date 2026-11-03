# Requirements traceability

Every requirement and deliverable from the challenge statement, where it is covered, how it is
proven, and the main bottleneck (risk) for it. "Done" means verified by test or example.

## Agent requirements

| ID | Requirement (from the statement) | Covered by | Proof | Status |
|----|----------------------------------|------------|-------|--------|
| R1 | Persona aligned with the store's identity and tone | System prompt (P13: informal, professional, music-savvy, pt-BR, greets by name) | Examples + eval of tone checks | built, evals pending |
| R2 | Receive and answer messages using the provided context | CLI loop + conversation history + tools over CSV/PDF | All examples | built, evals pending |
| R3a | Know when to query **data** (availability, price, order status) | Product/order tools, tool-first prompt rule (7.1) | Eval: no price/stock/status answer without a tool call | built, evals pending |
| R3b | Know when to query **policies** (exchange, hours, payment) | `search_policies` + rule-based tools (returns, payment, freight, hours) | Eval: policy questions cite the right section | built, evals pending |
| R4 | Handle out-of-scope questions | Scope rule in prompt, accessory redirect (P6), off-topic refusal | Eval + 1 example | built, evals pending |
| R5 | Python as the main language | Entire project | Repo | built, evals pending |

## Technical decisions to justify in the README

| ID | Decision | Where decided | Status |
|----|----------|---------------|--------|
| T1 | Framework / agent approach | `decisions.md` D2 | proposed |
| T2 | Model and provider | D1, D6 | proposed |
| T3 | Interaction interface | D7 (CLI) | accepted (D7, D19) |
| T4 | Conversation history persistence | D8 | accepted (D8, D19) |
| T5 | Data handling | D4, discovery section B | proposed |
| T6 | Retrieval architecture and prompt strategy | D5, D9 | proposed |

## Deliverables

| ID | Deliverable | Plan | Status |
|----|-------------|------|--------|
| E1 | Public Git repo with real commit history (no single commit, no force-push of everything) | Small semantic commits per phase | in progress |
| E2 | No repo changes after the deadline | Freeze at final checklist; set a reminder | todo |
| E3 | README: run instructions (env, provider, commands) | Phase 7 | todo |
| E4 | README: technical decisions justified | Generated from `decisions.md` | todo |
| E5 | README: known limitations and what I'd do with more time | Phase 7 | todo |
| E6 | README: AI assistant usage and workflow | From `ai-workflow.md` | todo |
| E7 | 3–5 example conversations (.md), at least one non-trivial (live data or policy rules) | `examples/`, produced by real runs of the eval script | done: 5 conversations in `examples/`, from runs that passed every check |
| E8 | Reply to the hiring email with the repo link | Manual, last step | todo |

## Suggested scenarios from the statement (all will be covered in evals)
1. "Quais opções de violões disponíveis custando até R$1000?" → `search_products` (D13).
2. "Qual o endereço da loja?" → store info (P1/P2).
3. "Quanto custa o Takamine GD20?" → product price (D12; id 95, R$ 2,199; no promo; PIX price shown).
4. "Me arrependi da minha compra, posso devolver meu pedido?" → identity verification (D9) then
   `check_return_eligibility` (P9, D7, D8).

## Bottlenecks (risks to 100% coverage) and mitigations

| # | Bottleneck | Impact | Mitigation |
|---|------------|--------|------------|
| B1 | LLM key, quota or model access unavailable or rate-limited (the OpenAI account already had no credits, so the provider moved to the Gemini free tier, D1) | Blocks every example; free-tier limits are low and a tool-using turn costs several requests | List accessible models first (phase 0); pick from the actual list; provider-agnostic client (D12); retry with backoff and a request throttle; cap the tool-call loop; run evals sequentially and cache embeddings; fall back to another configured provider if quota is exhausted. **Happened:** the free tier allows 15 requests/minute and about 500/day; the daily limit was exhausted on 2026-11-03 and blocked the last full eval run (D22) |
| B2 | LLM invents prices/stock/deadlines | Violates manual 7.1; core evaluation point | Tool-only facts; numeric logic in code; eval asserts tool calls happened; prompt forbids unsourced numbers |
| B3 | Order data leak (LGPD, duplicate email D9) | Serious correctness/privacy flaw | Verification bound to order owner; never reveal other customers' data; eval with wrong-identity attempt |
| B4 | Date-dependent answers (return window, opening hours) | Wrong or unreproducible answers | Single injectable `today`/`now`, timezone America/Campo_Grande; fixed date in examples |
| B5 | Contradictions in the manual (P1–P4) | Inconsistent agent answers | Resolved once, documented as assumptions, covered by unit tests |
| B6 | Retrieval misses the right policy section | Wrong policy answer | Section-level chunks (25), hybrid keyword+semantic search (measured in D5), top-k=3 with section titles, eval per policy topic; known miss: "chegou quebrado" -> 5.2; fallback "consult a human" when nothing matches |
| B7 | Examples not reproducible or faked | Credibility loss | Examples generated by a script that runs real conversations and saves transcripts |
| B8 | Time: deadline is tomorrow 11:59 | Incomplete delivery | Phases ordered by value; README and examples reserved for the last block; freeze 1h before deadline |
| B9 | Evaluator cannot run it (no key, env issues) | Unverified work | `.env.example`, one-command setup, pinned deps, transcripts committed so results are visible without running |
| B10 | Windows console encoding (pt-BR accents) | Garbled output | Explicit UTF-8 everywhere, `PYTHONUTF8=1` documented |
