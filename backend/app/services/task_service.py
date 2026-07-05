from datetime import datetime, timezone
from secrets import token_hex
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_task import AuditTask
from app.schemas.task import TaskCreate, TaskUpdate


def create_task(db: Session, payload: TaskCreate) -> AuditTask:
    prefix = {"sales": "SALES", "confirmation": "CONF", "interview": "INT"}.get(payload.scenario, "PROC")
    task = AuditTask(
        task_no=f"{prefix}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{token_hex(4)}",
        name=payload.name,
        scenario=payload.scenario,
        project_name=payload.project_name,
        company_name=payload.company_name,
        fiscal_year=payload.fiscal_year,
        period_start=payload.period_start,
        period_end=payload.period_end,
        actor_name=payload.actor_name,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_tasks(db: Session) -> list[AuditTask]:
    return list(db.scalars(select(AuditTask).order_by(AuditTask.created_at.desc())))


def get_task(db: Session, task_id: UUID) -> AuditTask:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def update_task(db: Session, task_id: UUID, payload: TaskUpdate) -> AuditTask:
    task = get_task(db, task_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task
