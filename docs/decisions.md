# System design decisions

Format: decision, alternatives considered, rationale. Filled in as decisions are made.

## D1 — LLM provider: OpenAI API
- **Alternatives:** Claude via API, Gemini (free tier), local model via Ollama.
- **Rationale:** the author already has OpenAI credits; function calling is mature and fits the case.
- **Specific model:** defined at implementation time (`OPENAI_MODEL`).

## D2 — Approach: function calling with typed tools (hybrid)
- **Alternatives:** pure RAG, free-form SQL agent, generic ReAct.
- **Rationale:** structured data (price, stock, orders) needs deterministic lookups; the manual is
  short and becomes a section-level text search. Tools bound what the model can do.
- **Status:** proposal, to be validated in discovery.

## D3 — Repository language: English
- **Decision:** all code, docs, prompts and commit messages are in English. The agent still replies
  to customers in Brazilian Portuguese, since the store's audience is Brazilian.
