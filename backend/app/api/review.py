from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.audit import AuditResultRead
from app.schemas.extraction import ExtractedFieldRead
from app.schemas.review import (
    DismissReviewAction,
    FieldCorrection,
    ReviewAction,
    ReviewCommentCreate,
    ReviewCommentRead,
    ReviewQueueItem,
)
from app.services import review_service

router = APIRouter(tags=["review"])


@router.get("/review/queue", response_model=list[ReviewQueueItem])
def list_review_queue(task_id: UUID | None = None, db: Session = Depends(get_db)):
    return review_service.list_review_queue(db, task_id)


@router.get("/review/comments", response_model=list[ReviewCommentRead])
def list_review_comments(
    task_id: UUID | None = None,
    audit_result_id: UUID | None = None,
    field_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    return review_service.list_comments(db, task_id, audit_result_id, field_id)


@router.post("/review/comments", response_model=ReviewCommentRead)
def create_review_comment(payload: ReviewCommentCreate, db: Session = Depends(get_db)):
    return review_service.create_comment(db, payload)


@router.patch("/fields/{field_id}", response_model=ExtractedFieldRead)
def update_field(field_id: UUID, payload: FieldCorrection, db: Session = Depends(get_db)):
    return review_service.update_field(db, field_id, payload)


@router.post("/audit-results/{result_id}/confirm", response_model=AuditResultRead)
def confirm_audit_result(result_id: UUID, payload: ReviewAction, db: Session = Depends(get_db)):
    return review_service.confirm_result(db, result_id, payload)


@router.post("/audit-results/{result_id}/dismiss", response_model=AuditResultRead)
def dismiss_audit_result(result_id: UUID, payload: DismissReviewAction, db: Session = Depends(get_db)):
    return review_service.dismiss_result(db, result_id, payload)


@router.post("/audit-results/{result_id}/rerun", response_model=list[AuditResultRead])
def rerun_audit_result(result_id: UUID, payload: ReviewAction, db: Session = Depends(get_db)):
    return review_service.rerun_result(db, result_id, payload)
