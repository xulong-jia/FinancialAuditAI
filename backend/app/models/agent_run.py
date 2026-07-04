from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="CASCADE"), index=True
    )
    workflow_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    current_state: Mapped[str] = mapped_column(String(80), index=True)
    input_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    output_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
