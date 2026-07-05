from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column, object_session

from app.core.audit_context import get_audit_context
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("audit_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    target_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


@event.listens_for(AuditLog, "before_insert")
def fill_audit_context(mapper, connection, target: AuditLog) -> None:
    context = get_audit_context()
    session = object_session(target)
    info = session.info if session is not None else {}
    target.user_id = target.user_id or info.get("audit_user_id") or context.user_id
    target.ip_address = target.ip_address or info.get("audit_ip_address") or context.ip_address
    target.user_agent = target.user_agent or info.get("audit_user_agent") or context.user_agent
