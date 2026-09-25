from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_entry import KNOWLEDGE_INTENTS, KnowledgeEntry
from app.schemas.knowledge import KnowledgeOut
from app.schemas.page import Page
from app.services.pagination import paginate
from app.services.text_service import normalize_text


def list_entries(db: Session, page: int, size: int, intent: str | None = None, q: str | None = None) -> Page[KnowledgeOut]:
    statement = select(KnowledgeEntry).order_by(KnowledgeEntry.created_at.desc(), KnowledgeEntry.id.desc())
    if intent in KNOWLEDGE_INTENTS:
        statement = statement.where(KnowledgeEntry.intent == intent)
    if q and normalize_text(q):
        statement = statement.where(KnowledgeEntry.title.contains(normalize_text(q), autoescape=True))
    return paginate(db, statement, page, size, KnowledgeOut.model_validate)
