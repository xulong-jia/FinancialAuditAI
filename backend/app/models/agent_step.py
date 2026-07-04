from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    step_name: Mapped[str] = mapped_column(String(160), index=True)
    step_order: Mapped[int] = mapped_column(Integer, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
