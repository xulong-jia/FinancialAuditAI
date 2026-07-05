from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditTask(Base):
    __tablename__ = "audit_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    scenario: Mapped[str] = mapped_column(String(64), default="procurement", index=True)
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    actor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    documents = relationship(
        "Document",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
