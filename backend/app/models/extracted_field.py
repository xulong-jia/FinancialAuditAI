from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    field_name: Mapped[str] = mapped_column(String(128), index=True)
    field_label: Mapped[str] = mapped_column(String(255))
    field_type: Mapped[str] = mapped_column(String(64))
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_normalized: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    original_value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_value_normalized: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), default="regex_heuristic")
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    corrected_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    corrected_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
