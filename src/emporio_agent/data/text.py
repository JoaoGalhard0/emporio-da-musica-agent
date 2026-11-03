import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase and strip accents so "Violão" matches "violao" and "Barítono" matches "baritono"."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))
