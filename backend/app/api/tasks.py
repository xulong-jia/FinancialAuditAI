from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import enforce_task_scope, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskRunRead, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task:create")),
):
    return task_service.create_task(db, payload, owner_id=user.id)


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    return task_service.list_tasks(db, user=user)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_task_scope(db, user, task_id)
    return task_service.get_task(db, task_id)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("task:update")),
):
    enforce_task_scope(db, user, task_id, write=True)
    return task_service.update_task(db, task_id, payload)


@router.post("/{task_id}/run", response_model=TaskRunRead)
def run_task(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("task:update"))):
    enforce_task_scope(db, user, task_id, write=True)
    return task_service.run_task(db, task_id)
