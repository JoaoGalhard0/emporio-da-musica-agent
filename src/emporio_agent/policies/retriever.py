"""Hybrid retrieval over the policy chunks: keyword (BM25) + semantic (embeddings), fused by rank.

Keyword search catches exact terms ("PIX", "boquilha") that embeddings blur; embeddings catch
paraphrases ("me arrependi" vs "direito de arrependimento"). If the embedding API is unavailable the
retriever degrades to keyword-only instead of failing the whole conversation.
"""
import hashlib
import json
import logging
import math
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from emporio_agent.config import REPO_ROOT
from emporio_agent.data.text import STOPWORDS, tokens
from emporio_agent.policies.chunker import PolicyChunk, load_chunks

log = logging.getLogger(__name__)

CACHE_PATH = REPO_ROOT / ".cache" / "policy_embeddings.json"
_RRF_K = 60  # standard reciprocal-rank-fusion constant
_COOLDOWN_SECONDS = 60  # after an embedding failure, stay keyword-only this long (free-tier quota)
_STEM = 5  # crude Portuguese stemming: "devolver", "devolução" and "devolvido" share "devol"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Hit:
    chunk: PolicyChunk
    score: float
    method: str  # "hybrid" or "keyword"


def _terms(text: str) -> list[str]:
    return [t[:_STEM] for t in tokens(text) if t not in STOPWORDS]


class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(d) for d in docs]
        self.lengths = [len(d) for d in docs]
        self.avg = sum(self.lengths) / len(docs)
        n = len(docs)
        df = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.k1, self.b = k1, b

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for doc, length in zip(self.docs, self.lengths):
            s = 0.0
            for t in query:
                f = doc.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
            out.append(s)
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def _rank(scores: list[float]) -> dict[int, int]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return {idx: pos for pos, idx in enumerate(order)}


class PolicyRetriever:
    def __init__(self, chunks: list[PolicyChunk] | None = None, embedder: Embedder | None = None,
                 model_name: str = "", cache_path: Path | None = CACHE_PATH):
        self.chunks = chunks if chunks is not None else load_chunks()
        self._bm25 = _BM25([_terms(c.document) for c in self.chunks])
        self._embedder = embedder
        self._model_name = model_name
        self._vectors: list[list[float]] | None = None
        self._cache_path = cache_path
        self._embeddings_blocked_until = 0.0

    # -- embeddings with an on-disk cache so the free-tier quota is spent once ---------------------

    def _key(self, chunk: PolicyChunk) -> str:
        return hashlib.sha1(f"{self._model_name}\n{chunk.document}".encode()).hexdigest()

    def _chunk_vectors(self) -> list[list[float]] | None:
        if self._vectors is not None:
            return self._vectors
        if self._embedder is None:
            return None
        cache: dict[str, list[float]] = {}
        if self._cache_path and self._cache_path.exists():
            cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
        missing = [c for c in self.chunks if self._key(c) not in cache]
        if missing:
            for chunk, vec in zip(missing, self._embedder.embed([c.document for c in missing])):
                cache[self._key(chunk)] = vec
            if self._cache_path:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                self._cache_path.write_text(json.dumps(cache), encoding="utf-8")
        self._vectors = [cache[self._key(c)] for c in self.chunks]
        return self._vectors

    # -- search ------------------------------------------------------------------------------------

    def search(self, query: str, k: int = 3) -> list[Hit]:
        keyword = self._bm25.scores(_terms(query))
        kw_rank = _rank(keyword)

        semantic_rank = None
        try:
            if time.monotonic() < self._embeddings_blocked_until:
                raise RuntimeError("embeddings in cooldown after a recent failure")
            vectors = self._chunk_vectors()
            if vectors is not None:
                q = self._embedder.embed([query])[0]
                semantic_rank = _rank([_cosine(q, v) for v in vectors])
        except Exception as exc:  # any provider failure (quota, network, auth) must not break the chat
            self._embeddings_blocked_until = time.monotonic() + _COOLDOWN_SECONDS
            log.warning("Embedding search unavailable, using keyword only: %s", str(exc)[:160])

        if semantic_rank is None:
            ranked = [i for i in sorted(kw_rank, key=kw_rank.get) if keyword[i] > 0][:k]
            return [Hit(self.chunks[i], keyword[i], "keyword") for i in ranked]

        fused = {i: 1 / (_RRF_K + kw_rank[i]) + 1 / (_RRF_K + semantic_rank[i]) for i in kw_rank}
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [Hit(self.chunks[i], fused[i], "hybrid") for i in top]
