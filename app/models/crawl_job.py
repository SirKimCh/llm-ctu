from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.user import utc_now


class CrawlStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


ACTIVE_STATUSES = (CrawlStatus.PENDING, CrawlStatus.RUNNING)


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (UniqueConstraint("active_slot", name="uq_crawl_active"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    urls: Mapped[list] = mapped_column(JSON)
    intent: Mapped[str | None] = mapped_column(String(40))
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default=CrawlStatus.PENDING)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    active_slot: Mapped[int | None] = mapped_column(Integer, default=1)
