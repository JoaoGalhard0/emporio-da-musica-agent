"""Thin wrapper over any OpenAI-compatible endpoint (docs/decisions.md D1, D12).

The rest of the code depends on this module, never on a provider SDK, so changing provider is a
change to `.env` only.
"""
import os

from dotenv import load_dotenv
from openai import OpenAI

# Gemini accepts up to 100 inputs per request, but its free tier also counts every input
# against a 100-per-minute quota (observed in phase 3).
_EMBED_BATCH = 100


class LLMNotConfigured(RuntimeError):
    pass


class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str, embedding_model: str):
        # The SDK retries 429/5xx with exponential backoff, which is what the free tier needs.
        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=5, timeout=60)
        self.model = model
        self.embedding_model = embedding_model

    @classmethod
    def from_env(cls) -> "LLMClient":
        load_dotenv()
        values = {k: os.environ.get(k, "") for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "EMBEDDING_MODEL")}
        missing = [k for k, v in values.items() if not v]
        if missing:
            raise LLMNotConfigured(f"Missing in .env: {', '.join(missing)} (see .env.example)")
        return cls(values["LLM_API_KEY"], values["LLM_BASE_URL"], values["LLM_MODEL"], values["EMBEDDING_MODEL"])

    def chat(self, messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.2) -> dict:
        """One non-streaming completion; returns the assistant message as a plain dict.

        The dict is kept exactly as the provider sent it (model_dump keeps unknown fields) because
        Gemini attaches thought signatures to tool calls and expects them back on the next request.
        """
        response = self._client.chat.completions.create(
            model=self.model, messages=messages, tools=tools or None, temperature=temperature
        )
        return response.choices[0].message.model_dump(exclude_none=True)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = texts[start : start + _EMBED_BATCH]
            response = self._client.embeddings.create(model=self.embedding_model, input=batch)
            # Gemini's compatibility layer returns `index=None`, so rely on the response order.
            vectors.extend(item.embedding for item in response.data)
        return vectors
