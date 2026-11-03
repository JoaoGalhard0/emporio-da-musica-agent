"""Split the policies manual (PDF) into one chunk per numbered section.

Chunks follow the manual's own structure so every answer can cite "section N", and each one carries
its breadcrumb (parent section title) because many sub-sections are meaningless alone.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from emporio_agent.config import DATA_DIR

POLICIES_PDF = DATA_DIR / "políticas_da_loja.pdf"

# Page furniture repeated on every page; it would pollute the embeddings.
_FURNITURE = re.compile(r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+)$")

# Headings sit at column 0 in layout mode. The numbered steps of section 7.2 ("1. Saudação: ...")
# look similar but are indented, so the column check is what tells them apart.
_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)\.?\s+(\S.*)$")


# The manual contradicts itself on two contact details (docs/discovery.md P1, P2). The resolution is
# applied here, once, so retrieval can never show the model both versions.
# Regexes because the PDF uses non-breaking spaces and varying dashes inside these values.
_CANONICAL_FIXES = (
    (re.compile(r"empóriodamusica\.com\.br"), "emporiodamusica.com.br"),
    (re.compile(r"\(67\)\s*3321\s*[-‑–]\s*4500"), "(67) 3341-4444"),
)


@dataclass(frozen=True)
class PolicyChunk:
    section: str  # "4.1"
    title: str  # "Direito de Arrependimento (Compras Online)"
    parent_title: str | None  # "Política de Trocas e Devoluções" for 4.1; None for top-level
    text: str  # body only
    page: int

    @property
    def breadcrumb(self) -> str:
        head = f"Seção {self.section} — {self.title}"
        return f"{head} (em: {self.parent_title})" if self.parent_title else head

    @property
    def document(self) -> str:
        """What gets embedded and shown to the LLM: heading context plus body."""
        return f"{self.breadcrumb}\n{self.text}"


def _page_lines(pdf: Path) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    # Page 1 is the cover: its contact data is repeated in section 1.2.
    for number, page in enumerate(PdfReader(pdf).pages[1:], start=2):
        for raw in page.extract_text(extraction_mode="layout").splitlines():
            stripped = raw.strip()
            if stripped and not _FURNITURE.match(stripped):
                lines.append((number, raw.rstrip()))
    return lines


def _clean(body_lines: list[str]) -> str:
    # Layout mode pads table columns with long runs of spaces; collapse them for the embedder.
    text = "\n".join(re.sub(r"[ \t]{2,}", "  ", ln.strip()) for ln in body_lines if ln.strip())
    for wrong, right in _CANONICAL_FIXES:
        text = wrong.sub(right, text)
    return text


def load_chunks(pdf: Path = POLICIES_PDF) -> list[PolicyChunk]:
    # Treat the manual as one continuous stream: heading 5.2 is at the bottom of page 4 and its
    # body is on page 5, so chunking page by page would orphan it.
    headings: list[tuple[str, str, int, list[str]]] = []  # section, title, page, body lines
    for page, raw in _page_lines(pdf):
        match = _HEADING.match(raw) if not raw.startswith(" ") else None
        if match:
            headings.append((match.group(1), match.group(2).strip(), page, []))
        elif headings:
            headings[-1][3].append(raw)

    top_titles = {sec: title for sec, title, _, _ in headings if "." not in sec}
    chunks = []
    for section, title, page, body in headings:
        text = _clean(body)
        if not text:
            continue  # a top-level heading whose content is entirely in its sub-sections
        parent = top_titles.get(section.split(".")[0]) if "." in section else None
        chunks.append(PolicyChunk(section, title, parent, text, page))
    return chunks
