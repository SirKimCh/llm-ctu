import re
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.mysql import match
from sqlalchemy.orm import Session

from app.models.knowledge_entry import KNOWLEDGE_INTENTS, Intent, KnowledgeEntry
from app.services.text_service import fold, normalize_major, normalize_text

LATEST_YEAR_INTENTS = {Intent.HOI_DIEM_CHUAN}
MIN_SHARED_SYLLABLES = 2
FALLBACK_CANDIDATES_PER_RESULT = 4
TABLE_HEADER_LINES = 2
SYLLABLE = re.compile(r"\w+")


@dataclass(frozen=True)
class Fact:
    title: str
    content: str
    year: int | None
    major: str | None
    source_url: str | None


@dataclass(frozen=True)
class SearchResult:
    facts: list[Fact]
    year_used: int | None


def _latest_year(db: Session, intent: str, major_norm: str | None) -> int | None:
    statement = select(func.max(KnowledgeEntry.year)).where(KnowledgeEntry.intent == intent)
    if major_norm:
        statement = statement.where(KnowledgeEntry.major_norm == major_norm)
    return db.scalar(statement)


def _filtered(intent: str, major_norm: str | None, year: int | None, score) -> Select:
    statement = select(KnowledgeEntry).where(KnowledgeEntry.intent == intent)
    order = []
    if major_norm:
        statement = statement.where(or_(KnowledgeEntry.major_norm == major_norm, KnowledgeEntry.major_norm.is_(None)))
        order.append(KnowledgeEntry.major_norm.is_(None))
    if year:
        statement = statement.where(or_(KnowledgeEntry.year == year, KnowledgeEntry.year.is_(None)))
        order.append(KnowledgeEntry.year.is_(None))
    return statement.order_by(*order, score.desc(), KnowledgeEntry.year.desc(), KnowledgeEntry.id)


def _syllables(text: str) -> set[str]:
    return set(SYLLABLE.findall(normalize_text(text).lower()))


def _shares_enough_syllables(row: KnowledgeEntry, syllables: set[str]) -> bool:
    shared = len(syllables & _syllables(f"{row.title} {row.content}"))
    return shared >= min(MIN_SHARED_SYLLABLES, len(syllables))


def _focus(content: str, major: str | None) -> str | None:
    """Bảng markdown: chỉ giữ tiêu đề + các dòng nhắc tới ngành đang hỏi; bảng không có ngành đó ⇒ bỏ phần bảng."""
    lines = content.split("\n")
    table = [line for line in lines if line.startswith("|")]
    if not major or len(table) < TABLE_HEADER_LINES + 1:
        return content
    text = [line for line in lines if not line.startswith("|")]
    rows = [row for row in table[TABLE_HEADER_LINES:] if fold(major) in fold(row)]
    kept = [*text, *table[:TABLE_HEADER_LINES], *rows] if rows else text
    return "\n".join(kept).strip() or None


def search(
    db: Session, question: str, intent: str | None = None, major: str | None = None, year: int | None = None,
    top_k: int = 5, max_chars: int = 1500,
) -> SearchResult:
    query = normalize_text(question)
    major_norm = normalize_major(major)
    rows: list[KnowledgeEntry] = []
    if intent in KNOWLEDGE_INTENTS:
        if year is None and intent in LATEST_YEAR_INTENTS:
            year = _latest_year(db, intent, major_norm)
        against = " ".join(part for part in (query, major) if part) or intent
        score = match(KnowledgeEntry.title, KnowledgeEntry.content, against=against).in_natural_language_mode()
        rows = list(db.scalars(_filtered(intent, major_norm, year, score).limit(top_k * FALLBACK_CANDIDATES_PER_RESULT)))
    if not rows and query:
        fallback_query = " ".join(str(part) for part in (query, major, year) if part)
        score = match(KnowledgeEntry.title, KnowledgeEntry.content, against=fallback_query).in_natural_language_mode()
        statement = select(KnowledgeEntry).where(score > 0)
        if intent in KNOWLEDGE_INTENTS:
            statement = statement.where(KnowledgeEntry.intent.is_(None))
        candidates = db.scalars(statement.order_by(score.desc()).limit(top_k * FALLBACK_CANDIDATES_PER_RESULT))
        syllables = _syllables(query)
        rows = [row for row in candidates if _shares_enough_syllables(row, syllables)][:top_k]
    focused = ((row, _focus(row.content, major)) for row in rows)
    facts = [Fact(row.title, content[:max_chars], row.year, row.major, row.source_url) for row, content in focused if content]
    return SearchResult(facts=facts[:top_k], year_used=year)


def known_majors(db: Session) -> list[str]:
    return list(db.scalars(select(KnowledgeEntry.major).where(KnowledgeEntry.major.is_not(None)).distinct()))
