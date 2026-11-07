import unicodedata
from collections.abc import Iterable


def normalize(text: str) -> str:
    """Casefold and strip accents, so Sable matches Sablé."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def mentioned(text: str, names: Iterable[str]) -> set[str]:
    folded = normalize(text)
    return {name for name in names if normalize(name) in folded}
