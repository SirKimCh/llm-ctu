import re
import unicodedata
from dataclasses import dataclass

from pyvi import ViTokenizer

URL_PATTERN = re.compile(r"^https?://\S+$")


@dataclass(frozen=True)
class Token:
    word: str
    start: int
    end: int


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def normalize_major(value: str | None) -> str | None:
    return normalize_text(value).lower() or None if value else None


def _strip_char(char: str) -> str:
    if char in "đĐ":
        return "d" if char == "đ" else "D"
    return unicodedata.normalize("NFD", char)[0]


def strip_accents(text: str) -> str:
    return "".join(_strip_char(char) for char in text)


def fold(text: str) -> str:
    return " ".join(strip_accents(normalize_text(text)).lower().replace("–", "-").replace(" - ", " ").split())


def segment(text: str) -> list[Token]:
    if not text.strip():
        return []
    tokens, cursor = [], 0
    for word in ViTokenizer.tokenize(text).split():
        surface = word.replace("_", " ")
        start = text.find(surface, cursor)
        if start < 0:
            continue
        cursor = start + len(surface)
        tokens.append(Token(word, start, cursor))
    return tokens


def segment_lowercased(text: str) -> list[Token]:
    lowered = text.lower()
    return segment(lowered if len(lowered) == len(text) else text)


def spans_to_bio(tokens: list[Token], entities: list[dict]) -> list[str]:
    labels = []
    for token in tokens:
        entity = next((e for e in entities if token.start < e["end"] and token.end > e["start"]), None)
        if entity is None:
            labels.append("O")
        else:
            labels.append(f"{'B' if token.start <= entity['start'] else 'I'}-{entity['label']}")
    return labels


def bio_to_spans(text: str, tokens: list[Token], labels: list[str]) -> dict[str, str]:
    found: list[list] = []
    previous = None
    for token, label in zip(tokens, labels):
        tag, _, name = label.partition("-")
        if tag == "I" and previous == name:
            found[-1][2] = token.end
        elif tag in ("B", "I"):
            found.append([name, token.start, token.end])
        previous = name if tag in ("B", "I") else None
    spans: dict[str, str] = {}
    for name, start, end in found:
        spans.setdefault(name, text[start:end])
    return spans
