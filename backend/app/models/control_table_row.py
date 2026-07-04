from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ControlTableRow(Base):
    __tablename__ = "control_table_rows"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    business_key: Mapped[str] = mapped_column(String(160), index=True)
    scenario: Mapped[str] = mapped_column(String(64), index=True)
    row_data: Mapped[dict] = mapped_column(JSON, default=dict)
    overall_status: Mapped[str] = mapped_column(String(32), index=True)
    evidence_refs: Mapped[list[dict]] = mapped_column(JSON, default=list)
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
