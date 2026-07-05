from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_task import AuditTask
from app.models.bad_case import BadCase
from app.models.document import Document
from app.schemas.quality import BadCaseCreate, BadCaseUpdate
from app.services import audit_log_service

CASE_TYPES = {"ocr", "classification", "extraction", "rule", "rag", "agent", "review_dispute", "end_to_end", "regression"}
STATUSES = {"open", "fixed", "ignored", "reopened"}
SEVERITIES = {"low", "medium", "high", "critical"}


def create_case(db: Session, payload: BadCaseCreate) -> BadCase:
    _validate_refs(db, payload.task_id, payload.document_id)
    _validate_values(payload.case_type, payload.status, payload.severity)
    case = BadCase(**payload.model_dump())
    if case.validation_result is not None:
        case.validated_at = utc_now()
    db.add(case)
    audit_log_service.add_log(
        db,
        actor_name=case.owner_name,
        task_id=case.task_id,
        action="bad_case_created",
        target_type="bad_case",
        target_id=case.id,
        after_value=_case_snapshot(case),
    )
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
    before = _case_snapshot(case)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(case, key, value)
    _validate_values(case.case_type, case.status, case.severity)
    if "validation_result" in payload.model_fields_set:
        case.validated_at = utc_now()
    if case.status == "fixed" and case.validation_result is not None and case.validated_at is None:
        case.validated_at = utc_now()
    audit_log_service.add_log(
        db,
        actor_name=case.owner_name,
        task_id=case.task_id,
        action="bad_case_updated",
        target_type="bad_case",
        target_id=case.id,
        before_value=before,
        after_value=_case_snapshot(case),
    )
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
        in_regression=True,
    )
    db.add(case)
    db.flush()
    audit_log_service.add_log(
        db,
        actor_name=None,
        task_id=None,
        action="bad_case_created_from_failed_sample",
        target_type="bad_case",
        target_id=case.id,
        after_value=_case_snapshot(case),
    )
    return case


def _validate_refs(db: Session, task_id: UUID | None, document_id: UUID | None) -> None:
    if task_id is not None and db.get(AuditTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if document_id is not None:
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        if task_id is not None and document.task_id != task_id:
            raise HTTPException(status_code=400, detail="Document does not belong to task")


def _validate_values(case_type: str, status: str, severity: str) -> None:
    if case_type not in CASE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported bad case type")
    if status not in STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported bad case status")
    if severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail="Unsupported bad case severity")


def _case_snapshot(case: BadCase) -> dict:
    return {
        "id": str(case.id),
        "case_type": case.case_type,
        "status": case.status,
        "severity": case.severity,
        "in_regression": case.in_regression,
        "validated_at": case.validated_at.isoformat() if case.validated_at else None,
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
