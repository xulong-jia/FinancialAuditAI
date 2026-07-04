from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_task import AuditTask
from app.models.bad_case import BadCase
from app.models.document import Document
from app.schemas.quality import BadCaseCreate, BadCaseUpdate


def create_case(db: Session, payload: BadCaseCreate) -> BadCase:
    _validate_refs(db, payload.task_id, payload.document_id)
    case = BadCase(**payload.model_dump())
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def list_cases(
    db: Session,
    *,
    case_type: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    owner_name: str | None = None,
) -> list[BadCase]:
    query = select(BadCase).order_by(BadCase.created_at.desc())
    if case_type:
        query = query.where(BadCase.case_type == case_type)
    if status:
        query = query.where(BadCase.status == status)
    if severity:
        query = query.where(BadCase.severity == severity)
    if owner_name:
        query = query.where(BadCase.owner_name == owner_name)
    return list(db.scalars(query))


def get_case(db: Session, case_id: UUID) -> BadCase:
    case = db.get(BadCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Bad case not found")
    return case


def update_case(db: Session, case_id: UUID, payload: BadCaseUpdate) -> BadCase:
    case = get_case(db, case_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, key, value)
    db.commit()
    db.refresh(case)
    return case


def create_failed_case(
    db: Session,
    *,
    case_type: str,
    title: str,
    input_payload: dict,
    model_output: dict,
    expected_output: dict,
    severity: str = "medium",
) -> BadCase:
    case = BadCase(
        case_type=case_type,
        title=title,
        input_payload=input_payload,
        model_output=model_output,
        expected_output=expected_output,
        root_cause="pending_analysis",
        fix_plan="Review this failed sample and add it to regression after a fix.",
        status="open",
        severity=severity,
        owner_name=None,
    )
    db.add(case)
    db.flush()
    return case


def _validate_refs(db: Session, task_id: UUID | None, document_id: UUID | None) -> None:
    if task_id is not None and db.get(AuditTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if document_id is not None and db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
