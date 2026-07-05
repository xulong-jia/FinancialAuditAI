from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditRule(Base):
    __tablename__ = "audit_rules"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    scenario: Mapped[str] = mapped_column(String(64), index=True, default="procurement")
    category: Mapped[str] = mapped_column(String(64), default="walkthrough")
    severity: Mapped[str] = mapped_column(String(32), default="medium")
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    expression: Mapped[str] = mapped_column(Text, default="")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    required_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
