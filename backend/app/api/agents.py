from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import enforce_task_scope, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.agent import AgentRunCreate, AgentRunRead, AgentStepRead
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/runs", response_model=AgentRunRead)
def create_agent_run(
    payload: AgentRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("agent:run")),
):
    enforce_task_scope(db, user, payload.task_id, write=True)
    return agent_service.create_run(
        db,
        task_id=payload.task_id,
        workflow_name=payload.workflow_name,
        input_refs=payload.input_refs,
    )


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    run = agent_service.get_run(db, run_id)
    enforce_task_scope(db, user, run.task_id)
    return run


@router.get("/runs/{run_id}/steps", response_model=list[AgentStepRead])
def list_agent_steps(run_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    run = agent_service.get_run(db, run_id)
    enforce_task_scope(db, user, run.task_id)
    return agent_service.list_steps(db, run_id)


@router.post("/runs/{run_id}/retry", response_model=AgentRunRead)
def retry_agent_run(run_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("agent:run"))):
    run = agent_service.get_run(db, run_id)
    enforce_task_scope(db, user, run.task_id, write=True)
    return agent_service.retry_run(db, run_id)


@router.post("/runs/{run_id}/resume", response_model=AgentRunRead)
def resume_agent_run(run_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("agent:run"))):
    run = agent_service.get_run(db, run_id)
    enforce_task_scope(db, user, run.task_id, write=True)
    return agent_service.resume_run(db, run_id)
