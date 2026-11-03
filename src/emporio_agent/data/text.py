import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase and strip accents so "Violão" matches "violao" and "Barítono" matches "baritono"."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalize(text))


# Common Portuguese function words, ignored when matching customer wording against the data.
STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "um", "uma", "para", "por",
    "com", "que", "se", "na", "no", "nas", "nos", "ao", "ou", "eu", "meu", "minha", "posso", "pode",
    "qual", "quais", "como", "quando", "tem", "ter", "ser", "sao", "mais", "ja", "me", "te",
}
