from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    intent: str | None
    route: str | None
    sources: list[str] | None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    updated_at: datetime


class ConversationDetail(ConversationOut):
    state: dict
    messages: list[MessageOut]


class Turn(BaseModel):
    reply: str
    intent: str | None
    sources: list[str]
    route: str
    state: dict
