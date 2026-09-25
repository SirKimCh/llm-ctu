from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.user import utc_now


class Intent(StrEnum):
    HOI_DIEM_CHUAN = "hoi_diem_chuan"
    HOI_DIEU_KIEN_TUYEN_SINH = "hoi_dieu_kien_tuyen_sinh"
    HOI_HOC_PHI = "hoi_hoc_phi"
    HOI_QUY_CHE_HOC_VU = "hoi_quy_che_hoc_vu"
    TU_VAN_LO_TRINH = "tu_van_lo_trinh"
    CHAO_HOI = "chao_hoi"
    NGOAI_PHAM_VI = "ngoai_pham_vi"


INTENT_LABELS = {
    Intent.HOI_DIEM_CHUAN: "Điểm chuẩn",
    Intent.HOI_DIEU_KIEN_TUYEN_SINH: "Điều kiện, phương thức tuyển sinh",
    Intent.HOI_HOC_PHI: "Học phí",
    Intent.HOI_QUY_CHE_HOC_VU: "Quy chế học vụ",
    Intent.TU_VAN_LO_TRINH: "Lộ trình học tập",
}
KNOWLEDGE_INTENTS = tuple(INTENT_LABELS)


class SourceType(StrEnum):
    EXCEL = "EXCEL"
    CRAWL = "CRAWL"


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"
    __table_args__ = (
        Index("ft_knowledge", "title", "content", mysql_prefix="FULLTEXT", mysql_with_parser="ngram"),
        Index("ix_knowledge_lookup", "intent", "major_norm", "year"),
        Index("ix_knowledge_source_url", "source_url", mysql_length=255),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    intent: Mapped[str | None] = mapped_column(String(40))
    major: Mapped[str | None] = mapped_column(String(150))
    major_norm: Mapped[str | None] = mapped_column(String(150))
    year: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(10))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    crawl_job_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
