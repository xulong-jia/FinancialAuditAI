from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import can_access_task_scope, enforce_document_scope, enforce_task_scope, require_any_permission, require_permission
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.audit_result import AuditResult
from app.models.extracted_field import ExtractedField
from app.models.review_comment import ReviewComment
from app.models.user import User
from app.schemas.audit import AuditResultRead
from app.schemas.extraction import ExtractedFieldRead
from app.schemas.quality import BadCaseRead
from app.schemas.review import (
    BadCaseFromReview,
    DismissReviewAction,
    FieldCorrection,
    ReextractRequest,
    ReviewAction,
    ReviewCommentCreate,
    ReviewCommentRead,
    ReviewQueueItem,
)
from app.services import auth_service, review_service

router = APIRouter(tags=["review"])


@router.get("/review/queue", response_model=list[ReviewQueueItem])
def list_review_queue(
    task_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("read")),
):
    if task_id is not None:
        enforce_task_scope(db, user, task_id)
    return [
        item
        for item in review_service.list_review_queue(db, task_id)
        if can_access_task_scope(db, user, item.task_id)
    ]


@router.get("/review/comments", response_model=list[ReviewCommentRead])
def list_review_comments(
    task_id: UUID | None = None,
    audit_result_id: UUID | None = None,
    field_id: UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("read")),
):
    if task_id is not None:
        enforce_task_scope(db, user, task_id)
    return [
        comment
        for comment in review_service.list_comments(db, task_id, audit_result_id, field_id)
        if can_access_task_scope(db, user, comment.task_id)
    ]


@router.post("/review/comments", response_model=ReviewCommentRead)
def create_review_comment(
    payload: ReviewCommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    enforce_task_scope(db, user, payload.task_id, write=True)
    return review_service.create_comment(db, payload, author_id=user.id, author_name=user.full_name)


@router.patch("/fields/{field_id}", response_model=ExtractedFieldRead)
def update_field(
    field_id: UUID,
    payload: FieldCorrection,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_permission("review:write", "field:correct")),
):
    field = _get_field(db, field_id)
    task = enforce_task_scope(db, user, field.task_id, write=True)
    permissions = auth_service.user_permissions(db, user)
    if "*" not in permissions and "review:write" not in permissions and task.status not in {"draft", "uploaded"}:
        raise HTTPException(status_code=403, detail="Analyst field correction is limited to draft stage")
    if payload.actor_name is None:
        payload = payload.model_copy(update={"actor_name": user.full_name})
    return review_service.update_field(db, field_id, payload, actor_id=user.id)


@router.post("/audit-results/{result_id}/confirm", response_model=AuditResultRead)
def confirm_audit_result(
    result_id: UUID,
    payload: ReviewAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    result = _get_result(db, result_id)
    enforce_task_scope(db, user, result.task_id, write=True)
    if payload.actor_name is None:
        payload = payload.model_copy(update={"actor_name": user.full_name})
    return review_service.confirm_result(db, result_id, payload, actor_id=user.id)


@router.post("/audit-results/{result_id}/dismiss", response_model=AuditResultRead)
def dismiss_audit_result(
    result_id: UUID,
    payload: DismissReviewAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    result = _get_result(db, result_id)
    enforce_task_scope(db, user, result.task_id, write=True)
    if payload.actor_name is None:
        payload = payload.model_copy(update={"actor_name": user.full_name})
    return review_service.dismiss_result(db, result_id, payload, actor_id=user.id)


@router.post("/audit-results/{result_id}/rerun", response_model=list[AuditResultRead])
def rerun_audit_result(
    result_id: UUID,
    payload: ReviewAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    result = _get_result(db, result_id)
    enforce_task_scope(db, user, result.task_id, write=True)
    if payload.actor_name is None:
        payload = payload.model_copy(update={"actor_name": user.full_name})
    return review_service.rerun_result(db, result_id, payload, actor_id=user.id)


@router.post("/fields/{field_id}/rerun-rules", response_model=list[AuditResultRead])
def rerun_rules_for_field(
    field_id: UUID,
    payload: ReviewAction,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    field = _get_field(db, field_id)
    enforce_task_scope(db, user, field.task_id, write=True)
    if payload.actor_name is None:
        payload = payload.model_copy(update={"actor_name": user.full_name})
    return review_service.rerun_rules_for_field(db, field_id, payload, actor_id=user.id)


@router.post("/documents/{document_id}/reextract", response_model=list[ExtractedFieldRead])
def reextract_document(
    document_id: UUID,
    payload: ReextractRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    enforce_document_scope(db, user, document_id, write=True)
    if payload.actor_name is None:
        payload = payload.model_copy(update={"actor_name": user.full_name})
    return review_service.reextract_document(db, document_id, payload, actor_id=user.id)


@router.post("/review/bad-case", response_model=BadCaseRead)
def create_bad_case_from_review(
    payload: BadCaseFromReview,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("review:write")),
):
    _enforce_review_source_scope(db, user, payload)
    if payload.owner_name is None:
        payload = payload.model_copy(update={"owner_name": user.full_name})
    return review_service.create_bad_case_from_review(db, payload, actor_id=user.id)


def _get_field(db: Session, field_id: UUID) -> ExtractedField:
    field = db.get(ExtractedField, field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")
    return field


def _get_result(db: Session, result_id: UUID) -> AuditResult:
    result = db.get(AuditResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Audit result not found")
    return result


def _enforce_review_source_scope(db: Session, user: User, payload: BadCaseFromReview) -> None:
    enforce_task_scope(db, user, payload.task_id, write=True)
    if payload.document_id is not None and enforce_document_scope(db, user, payload.document_id, write=True).task_id != payload.task_id:
        raise HTTPException(status_code=400, detail="Document does not belong to task")
    if payload.field_id is not None and _get_field(db, payload.field_id).task_id != payload.task_id:
        raise HTTPException(status_code=400, detail="Field does not belong to task")
    if payload.audit_result_id is not None and _get_result(db, payload.audit_result_id).task_id != payload.task_id:
        raise HTTPException(status_code=400, detail="Audit result does not belong to task")
    if payload.agent_step_id is not None:
        step = db.get(AgentStep, payload.agent_step_id)
        run = db.get(AgentRun, step.run_id) if step is not None else None
        if run is None:
            raise HTTPException(status_code=404, detail="Agent step not found")
        if run.task_id != payload.task_id:
            raise HTTPException(status_code=400, detail="Agent step does not belong to task")
    if payload.comment_id is not None:
        comment = db.get(ReviewComment, payload.comment_id)
        if comment is None:
            raise HTTPException(status_code=404, detail="Review comment not found")
        if comment.task_id != payload.task_id:
            raise HTTPException(status_code=400, detail="Review comment does not belong to task")
