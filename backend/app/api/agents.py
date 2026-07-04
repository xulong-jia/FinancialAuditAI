from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.agent import AgentRunCreate, AgentRunRead, AgentStepRead
from app.services import agent_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/runs", response_model=AgentRunRead)
def create_agent_run(payload: AgentRunCreate, db: Session = Depends(get_db)):
    return agent_service.create_run(
        db,
        task_id=payload.task_id,
        workflow_name=payload.workflow_name,
        input_refs=payload.input_refs,
    )


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: UUID, db: Session = Depends(get_db)):
    return agent_service.get_run(db, run_id)


@router.get("/runs/{run_id}/steps", response_model=list[AgentStepRead])
def list_agent_steps(run_id: UUID, db: Session = Depends(get_db)):
    return agent_service.list_steps(db, run_id)


@router.post("/runs/{run_id}/retry", response_model=AgentRunRead)
def retry_agent_run(run_id: UUID, db: Session = Depends(get_db)):
    return agent_service.retry_run(db, run_id)
