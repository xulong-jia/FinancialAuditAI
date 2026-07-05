from datetime import datetime, timezone
from secrets import token_hex
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_result import AuditResult
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import audit_log_service, auth_service


def create_task(db: Session, payload: TaskCreate, owner_id: UUID | None = None) -> AuditTask:
    prefix = {
        "sales": "SALES",
        "confirmation": "CONF",
        "interview": "INT",
        "contract_review": "CONTRACT",
    }.get(payload.scenario, "PROC")
    task = AuditTask(
        task_no=f"{prefix}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{token_hex(4)}",
        name=payload.name,
        scenario=payload.scenario,
        project_name=payload.project_name,
        company_name=payload.company_name,
        fiscal_year=payload.fiscal_year,
        period_start=payload.period_start,
        period_end=payload.period_end,
        risk_level=payload.risk_level,
        owner_id=payload.owner_id or owner_id,
        reviewer_id=payload.reviewer_id,
        metadata_json=payload.metadata,
        actor_name=payload.actor_name,
    )
    db.add(task)
    audit_log_service.add_log(
        db,
        actor_name=payload.actor_name,
        task_id=task.id,
        action="task_created",
        target_type="task",
        target_id=task.id,
        after_value={"task_no": task.task_no, "name": task.name, "scenario": task.scenario},
    )
    db.commit()
    db.refresh(task)
    return task


def list_tasks(db: Session, user: User | None = None) -> list[AuditTask]:
    statement = select(AuditTask).order_by(AuditTask.created_at.desc())
    if user is not None:
        permissions = auth_service.user_permissions(db, user)
        if "*" not in permissions and "read_all" not in permissions and "project:manage" not in permissions:
            statement = statement.where((AuditTask.owner_id == user.id) | (AuditTask.reviewer_id == user.id))
        elif "project:manage" in permissions and "*" not in permissions and "read_all" not in permissions and user.organization:
            statement = statement.where(
                (AuditTask.project_name == user.organization)
                | (AuditTask.company_name == user.organization)
                | (AuditTask.owner_id == user.id)
                | (AuditTask.reviewer_id == user.id)
            )
    return list(db.scalars(statement))


def get_task(db: Session, task_id: UUID) -> AuditTask:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def update_task(db: Session, task_id: UUID, payload: TaskUpdate) -> AuditTask:
    task = get_task(db, task_id)
    before = _task_snapshot(task)
    values = payload.model_dump(exclude_unset=True)
    if "metadata" in values:
        task.metadata_json = values.pop("metadata") or {}
    for key, value in values.items():
        setattr(task, key, value)
    audit_log_service.add_log(
        db,
        actor_name=payload.actor_name,
        task_id=task.id,
        action="task_updated",
        target_type="task",
        target_id=task.id,
        before_value=before,
        after_value=_task_snapshot(task),
    )
    db.commit()
    db.refresh(task)
    return task


def _task_snapshot(task: AuditTask) -> dict:
    return {
        "id": str(task.id),
        "task_no": task.task_no,
        "name": task.name,
        "status": task.status,
        "owner_id": str(task.owner_id) if task.owner_id else None,
        "reviewer_id": str(task.reviewer_id) if task.reviewer_id else None,
    }


def run_task(db: Session, task_id: UUID) -> dict:
    task = get_task(db, task_id)
    previous_status = task.status
    status, pending_steps, message = _task_run_state(db, task)
    task.status = status
    db.commit()
    db.refresh(task)
    return {
        "task_id": task.id,
        "previous_status": previous_status,
        "status": task.status,
        "next_action": pending_steps[0] if pending_steps else None,
        "pending_steps": pending_steps,
        "message": message,
    }


def _task_run_state(db: Session, task: AuditTask) -> tuple[str, list[str], str]:
    documents = list(db.scalars(select(Document).where(Document.task_id == task.id)))
    if not documents:
        return "draft", ["upload_documents"], "Task has no uploaded documents."

    if any(document.ocr_status == "failed" or document.extraction_status == "failed" for document in documents):
        return "failed", ["inspect_failed_documents"], "At least one document has a failed processing status."

    if any(document.ocr_status == "running" for document in documents):
        return "ocr_running", ["wait_for_ocr"], "OCR is currently running for at least one document."

    if any(document.ocr_status != "completed" for document in documents):
        return "uploaded", ["run_ocr"], "Documents are uploaded; OCR has not completed for all documents."

    if any(not document.doc_type or document.doc_type == "unknown" for document in documents):
        return "ocr_completed", ["classify_documents"], "OCR is complete; at least one document still needs classification."

    if any(document.extraction_status == "running" for document in documents):
        return "extracting", ["wait_for_extraction"], "Extraction is currently running for at least one document."

    if any(document.extraction_status != "completed" for document in documents):
        return "classified", ["extract_fields"], "Documents are classified; field extraction has not completed for all documents."

    if any(not document.business_key for document in documents):
        return "extracted", ["link_documents"], "Fields are extracted; documents are not fully linked."

    results = list(db.scalars(select(AuditResult).where(AuditResult.task_id == task.id)))
    if not results:
        return "extracted", ["run_audit"], "Documents are linked; audit rules have not produced results yet."

    if any(result.review_status == "pending" for result in results):
        return "reviewing", ["complete_review"], "Audit results include pending review items."

    return "completed", [], "Task processing contract is complete."
