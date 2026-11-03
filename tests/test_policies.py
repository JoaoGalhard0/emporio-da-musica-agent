"""Phase 3: policy chunking and retrieval. Offline by default; `pytest -m live` hits the real provider."""
import hashlib

import pytest

from emporio_agent.llm import LLMClient, LLMNotConfigured
from emporio_agent.policies.chunker import load_chunks
from emporio_agent.policies.retriever import PolicyRetriever
from queries import HARD_QUERIES, QUERIES


@pytest.fixture(scope="module")
def chunks():
    return load_chunks()


def by_section(chunks, section):
    return next(c for c in chunks if c.section == section)


# -- chunker -------------------------------------------------------------------------------------

def test_one_chunk_per_section(chunks):
    sections = [c.section for c in chunks]
    assert sections == [
        "1", "1.1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3",
        "6.1", "6.2", "7", "7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9", "10",
    ]


def test_subsection_keeps_its_parent_title(chunks):
    c = by_section(chunks, "4.1")
    assert c.parent_title == "Política de Trocas e Devoluções"
    assert c.document.startswith("Seção 4.1 — Direito de Arrependimento (Compras Online)")
    assert by_section(chunks, "2").parent_title is None


def test_section_split_across_pages_is_reunited(chunks):
    # Heading 5.2 is the last line of page 4; its body is on page 5.
    c = by_section(chunks, "5.2")
    assert "Jadlog" in c.text and "recusar o recebimento" in c.text
    assert "Código de Rastreamento" not in c.text


def test_numbered_steps_of_7_2_are_not_headings(chunks):
    assert "Saudação" in by_section(chunks, "7.2").text
    assert not any(c.title.startswith("Saudação") for c in chunks)


def test_page_furniture_is_removed(chunks):
    assert not any("Página" in c.text or "Manual de Políticas e Procedimentos" in c.text for c in chunks)


def test_key_rules_survive_extraction(chunks):
    assert "7 (sete) dias corridos" in by_section(chunks, "4.1").text
    assert "30 (trinta) dias" in by_section(chunks, "4.2").text
    assert "R$ 80,00" in by_section(chunks, "3.1").text
    assert "acessórios" in by_section(chunks, "1").text


def test_contradictory_contact_details_are_canonicalized(chunks):
    # P1/P2: the model must never see two phone numbers or an accented e-mail domain.
    text = "\n".join(c.text for c in chunks)
    assert "3321-4500" not in text and "empóriodamusica" not in text
    assert "(67) 3341-4444" in by_section(chunks, "1.2").text
    assert "(67) 3341-4444" in by_section(chunks, "7").text
    assert "contato@emporiodamusica.com.br" in by_section(chunks, "1.2").text


# -- retrieval, keyword only (no network) --------------------------------------------------------

def test_keyword_retrieval_finds_the_right_section_in_top_3(chunks):
    retriever = PolicyRetriever(chunks)
    misses = [
        q for q, ok in QUERIES.items()
        if not ok & {h.chunk.section for h in retriever.search(q, 3)}
    ]
    assert misses == []


def test_no_overlap_returns_nothing_instead_of_noise(chunks):
    assert PolicyRetriever(chunks).search("xyzzy qwerty", 3) == []


# -- hybrid mechanics with a fake embedder -------------------------------------------------------

class FakeEmbedder:
    """Hashes tokens into 64 dims: deterministic, offline, good enough to exercise the plumbing."""

    def __init__(self):
        self.texts_embedded = 0

    def embed(self, texts):
        self.texts_embedded += len(texts)
        out = []
        for t in texts:
            v = [0.0] * 64
            for tok in t.lower().split():
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 64] += 1.0
            out.append(v)
        return out


class BrokenEmbedder:
    calls = 0

    def embed(self, texts):
        BrokenEmbedder.calls += 1
        raise RuntimeError("429 quota exceeded")


def test_hybrid_is_used_when_embeddings_work(chunks, tmp_path):
    r = PolicyRetriever(chunks, FakeEmbedder(), "fake", tmp_path / "c.json")
    hits = r.search("horário de funcionamento", 3)
    assert hits and all(h.method == "hybrid" for h in hits)


def test_chunk_embeddings_are_cached_on_disk(chunks, tmp_path):
    cache = tmp_path / "c.json"
    first = FakeEmbedder()
    PolicyRetriever(chunks, first, "fake", cache).search("garantia", 3)
    assert first.texts_embedded == len(chunks) + 1  # every chunk once, plus the query

    second = FakeEmbedder()
    PolicyRetriever(chunks, second, "fake", cache).search("garantia", 3)
    assert second.texts_embedded == 1  # only the query


def test_changing_the_embedding_model_invalidates_the_cache(chunks, tmp_path):
    cache = tmp_path / "c.json"
    PolicyRetriever(chunks, FakeEmbedder(), "model-a", cache).search("garantia", 3)
    other = FakeEmbedder()
    PolicyRetriever(chunks, other, "model-b", cache).search("garantia", 3)
    assert other.texts_embedded == len(chunks) + 1


def test_provider_failure_degrades_to_keyword_and_stops_hammering(chunks, tmp_path):
    BrokenEmbedder.calls = 0
    r = PolicyRetriever(chunks, BrokenEmbedder(), "broken", tmp_path / "c.json")
    for _ in range(3):
        hits = r.search("Qual o horário de funcionamento?", 3)
        assert hits and hits[0].chunk.section == "2" and hits[0].method == "keyword"
    assert BrokenEmbedder.calls == 1  # cooldown: later searches do not call the provider again


# -- live (opt-in) -------------------------------------------------------------------------------

@pytest.mark.live
def test_live_hybrid_retrieval_quality(chunks):
    try:
        llm = LLMClient.from_env()
    except LLMNotConfigured:
        pytest.skip("LLM not configured in .env")
    r = PolicyRetriever(chunks, llm, llm.embedding_model)

    def top(queries, n):
        return sum(bool(ok & {h.chunk.section for h in r.search(q, n)}) for q, ok in queries.items())

    assert top(QUERIES, 3) == len(QUERIES)
    # Measured on 2026-11-03: 9 of 10 (the miss is "chegou quebrado" -> 5.2).
    assert top(HARD_QUERIES, 3) >= 9
    assert top(HARD_QUERIES, 1) >= 7
