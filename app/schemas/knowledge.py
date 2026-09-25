from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.knowledge_entry import INTENT_LABELS, SourceType


class KnowledgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    intent: str | None
    major: str | None
    year: int | None
    title: str
    content: str
    source_type: str
    source_url: str | None
    created_at: datetime

    @property
    def intent_label(self) -> str:
        return INTENT_LABELS.get(self.intent, "Chưa gán chủ đề")

    @property
    def source_label(self) -> str:
        return "Excel" if self.source_type == SourceType.EXCEL else "Cào web"
