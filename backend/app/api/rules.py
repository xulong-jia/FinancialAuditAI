from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.audit import (
    AuditRuleCreate,
    AuditRuleEvaluateRequest,
    AuditRuleEvaluateResult,
    AuditRuleRead,
    AuditRuleUpdate,
)
from app.services import rule_engine_service

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[AuditRuleRead])
def list_rules(db: Session = Depends(get_db)):
    return rule_engine_service.list_rules(db)


@router.post("", response_model=AuditRuleRead)
def create_rule(payload: AuditRuleCreate, db: Session = Depends(get_db)):
    return rule_engine_service.create_rule(db, **payload.model_dump())


@router.patch("/{rule_id}", response_model=AuditRuleRead)
def update_rule(rule_id: UUID, payload: AuditRuleUpdate, db: Session = Depends(get_db)):
    values = payload.model_dump(exclude_unset=True)
    return rule_engine_service.update_rule(db, rule_id, **values)


@router.post("/{rule_id}/evaluate", response_model=list[AuditRuleEvaluateResult])
def evaluate_rule(rule_id: UUID, payload: AuditRuleEvaluateRequest, db: Session = Depends(get_db)):
    return rule_engine_service.evaluate_rule(
        db,
        rule_id,
        task_id=payload.task_id,
        parameters=payload.parameters,
    )
