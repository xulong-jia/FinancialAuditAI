from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit_context import set_audit_user
from app.db.session import get_db
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.models.user import User
from app.services import auth_service


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = auth_service.parse_access_token(authorization.split(" ", 1)[1].strip())
    user = auth_service.get_user(db, user_id)
    db.info["audit_user_id"] = user.id
    db.info["audit_ip_address"] = request.client.host if request.client else None
    db.info["audit_user_agent"] = request.headers.get("user-agent")
    set_audit_user(user.id)
    return user


def require_permission(permission: str) -> Callable:
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        permissions = auth_service.user_permissions(db, user)
        if "*" in permissions or permission in permissions:
            return user
        raise HTTPException(status_code=403, detail="Permission denied")

    return dependency


def require_any_permission(*permissions: str) -> Callable:
    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        granted = auth_service.user_permissions(db, user)
        if "*" in granted or any(permission in granted for permission in permissions):
            return user
        raise HTTPException(status_code=403, detail="Permission denied")

    return dependency


RequireRead = Depends(require_permission("read"))


def enforce_task_scope(db: Session, user: User, task_id: UUID, *, write: bool = False) -> AuditTask:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if _can_access_task(db, user, task, write=write):
        return task
    raise HTTPException(status_code=403, detail="Task access denied")


def can_access_task_scope(db: Session, user: User, task_id: UUID, *, write: bool = False) -> bool:
    task = db.get(AuditTask, task_id)
    return task is not None and _can_access_task(db, user, task, write=write)


def enforce_document_scope(db: Session, user: User, document_id: UUID, *, write: bool = False) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    enforce_task_scope(db, user, document.task_id, write=write)
    return document


def _can_access_task(db: Session, user: User, task: AuditTask, *, write: bool) -> bool:
    permissions = auth_service.user_permissions(db, user)
    if "*" in permissions:
        return True
    if "project:manage" in permissions:
        if not user.organization:
            return True
        return user.organization in {task.project_name, task.company_name} or user.id in {task.owner_id, task.reviewer_id}
    if not write and "read_all" in permissions:
        return True
    return user.id in {task.owner_id, task.reviewer_id}
