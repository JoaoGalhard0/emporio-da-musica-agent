# Implementation plan

Phases are ordered by value and dependency. Each phase ends with a commit. Model per phase follows the
policy in `CLAUDE.md` (Opus 5.5 medium for planning/architecture, Sonnet 5.5 high for code).

## Target layout
```
src/emporio_agent/
  config.py          # env, reference date/timezone
  data/              # loaders + typed models (products, orders, customers, promotions)
  logic/             # pure functions: pricing, installments, freight, returns, store hours
  policies/          # PDF -> section chunks, embeddings cache, search
  tools/             # tool schemas + handlers exposed to the LLM
  agent.py           # LLM loop (tool calling), history, guardrails
  prompts.py         # persona and rules
  cli.py             # interactive chat + scripted runner
tests/               # unit tests for data + logic + tools (no network)
evals/               # scripted scenarios -> transcripts in examples/
examples/            # 3-5 real conversations (.md)
docs/                # requirements, discovery, decisions, plan, ai-workflow
```

## Phases

| # | Phase | Output | Covers | Model / effort |
|---|-------|--------|--------|----------------|
| 0 | Environment: venv, deps pinned, list models the key can use, smoke call with a tool | `requirements.txt`, chosen model recorded in D6 | B1, B9, B10 | Sonnet / high |
| 1 | Data layer: loaders, typing, `Decimal`, UTF-8, validation checks from discovery | `data/`, tests | T5, D1–D13 | Sonnet / high |
| 2 | Business logic (pure): price + promo + PIX, installments, freight, return eligibility, store hours | `logic/`, tests per rule incl. P3, P4, P7–P9, P11 | R3, B4, B5 | Sonnet / high |
| 3 | Policy retrieval: PDF to section chunks, embeddings cache, `search_policies` | `policies/`, retrieval tests per topic | R3b, T6, B6 | Sonnet / high |
| 4 | Tools + agent loop: schemas, identity verification, history, escalation log, loop cap | `tools/`, `agent.py`, `prompts.py` | R1–R4, D9, D11, B2, B3 | Sonnet / high |
| 5 | CLI and conversation persistence | `cli.py`, `.conversations/` | T3, T4 | Sonnet / high |
| 6 | Evals and examples: scripted scenarios, tool-call assertions, 4–5 transcripts | `evals/`, `examples/` | E7, B7 | Opus / medium (design) + Sonnet (code) |
| 7 | README, assumptions, limitations, AI-usage section, final review against `requirements.md` | `README.md` | E3–E6 | Opus / medium |
| 8 | Final checklist, freeze, send email | repo frozen | E1, E2, E8 | manual |

## Eval scenarios (each asserts tool usage, not only wording)
1. Catalog: "violões até R$ 1000" → `search_products`; excludes discontinued/out of stock; shows promo.
2. Price: "Quanto custa o Takamine GD20?" → R$ 2,199.00 (no promo), PIX price, installments.
3. Active promotion: Ohana CK-20 shows R$ 549 → 20% off, no extra PIX discount.
4. Out of stock / discontinued: Giannini GF-3D (96) and Shelby SN-7C (113) → alternatives offered.
5. Store info + hours: address; "está aberto agora?" at fixed times (weekday, Saturday afternoon, Sunday).
6. Payment: 12x on a R$ 800 item (parcela mínima) and PIX + card on a purchase above R$ 2,000.
7. Order status: shipped (order 8 with tracking), pending, cancelled with reason; wrong identity refused.
8. Return: "Me arrependi, posso devolver?" → asks for order + identity, then applies 7-day rule using
   the injected date; a defect case in the 30 vs 90-day gray zone → human handoff.
9. Out of scope: accessory request (strings) redirected; unrelated question (weather/code) declined politely.
10. Complaint → `escalate_to_human` with 24 business hours promise.
11. Safety: prompt-injection attempt and request for another customer's order.

## Definition of done
All rows in `requirements.md` are `done`, tests pass offline, evals pass against the real model, the
README matches what the code does, and the repo has a coherent commit history.

## Time-box
Phases 0–5 are the critical path (~60% of the time). Phase 6–7 start no later than the middle of the
available time. The last hour is reserved for the final checklist; nothing new is added then.
