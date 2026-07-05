from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import redact
from app.models.audit_log import AuditLog


def add_log(
    db: Session,
    *,
    actor_name: str | None,
    task_id: UUID | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    before_value: dict | None = None,
    after_value: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_name=actor_name,
            task_id=task_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_value=redact(before_value),
            after_value=redact(after_value),
        )
    )
