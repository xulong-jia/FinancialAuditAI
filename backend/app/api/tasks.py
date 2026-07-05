from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, dependencies=[Depends(require_permission("task:create"))])
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    return task_service.create_task(db, payload)


@router.get("", response_model=list[TaskRead], dependencies=[Depends(require_permission("read"))])
def list_tasks(db: Session = Depends(get_db)):
    return task_service.list_tasks(db)


@router.get("/{task_id}", response_model=TaskRead, dependencies=[Depends(require_permission("read"))])
def get_task(task_id: UUID, db: Session = Depends(get_db)):
    return task_service.get_task(db, task_id)


@router.patch("/{task_id}", response_model=TaskRead, dependencies=[Depends(require_permission("task:update"))])
def update_task(task_id: UUID, payload: TaskUpdate, db: Session = Depends(get_db)):
    return task_service.update_task(db, task_id, payload)
