from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelInvocation(Base):
    __tablename__ = "model_invocations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(80), index=True)
    model_name: Mapped[str] = mapped_column(String(120))
    invocation_type: Mapped[str] = mapped_column(String(80), index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_schema: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
