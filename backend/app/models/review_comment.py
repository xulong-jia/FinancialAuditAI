from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    audit_result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("audit_results.id", ondelete="SET NULL"), nullable=True, index=True
    )
    field_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("extracted_fields.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    comment_type: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachment_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
