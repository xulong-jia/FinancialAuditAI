from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditResult(Base):
    __tablename__ = "audit_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("audit_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rule_code: Mapped[str] = mapped_column(String(64), index=True)
    rule_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    business_key: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    expected_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actual_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    rag_citations: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
