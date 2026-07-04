from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.audit_result import AuditResult
from app.models.audit_task import AuditTask
from app.models.extracted_field import ExtractedField
from app.models.review_comment import ReviewComment
from app.schemas.review import (
    DismissReviewAction,
    FieldCorrection,
    ReviewAction,
    ReviewCommentCreate,
    ReviewQueueItem,
)
from app.services import rule_engine_service


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_review_queue(db: Session, task_id: UUID | None = None) -> list[ReviewQueueItem]:
    fields = list(db.scalars(_scope(select(ExtractedField), ExtractedField.task_id, task_id)))
    results = list(db.scalars(_scope(select(AuditResult), AuditResult.task_id, task_id)))

    items: list[ReviewQueueItem] = []
    for field in fields:
        reason = _field_review_reason(field)
        if reason:
            items.append(
                ReviewQueueItem(
                    item_type="field",
                    task_id=field.task_id,
                    document_id=field.document_id,
                    field_id=field.id,
                    reason=reason,
                    field=field,
                )
            )

    for result in results:
        if result.review_status == "pending":
            items.append(
                ReviewQueueItem(
                    item_type="audit_result",
                    task_id=result.task_id,
                    audit_result_id=result.id,
                    reason=f"{result.status}:{result.severity}",
                    audit_result=result,
                )
            )

    return items


def list_comments(
    db: Session,
    task_id: UUID | None = None,
    audit_result_id: UUID | None = None,
    field_id: UUID | None = None,
) -> list[ReviewComment]:
    statement = select(ReviewComment).order_by(ReviewComment.created_at.desc())
    if task_id:
        statement = statement.where(ReviewComment.task_id == task_id)
    if audit_result_id:
        statement = statement.where(ReviewComment.audit_result_id == audit_result_id)
    if field_id:
        statement = statement.where(ReviewComment.field_id == field_id)
    return list(db.scalars(statement))


def create_comment(db: Session, payload: ReviewCommentCreate) -> ReviewComment:
    if db.get(AuditTask, payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    comment = ReviewComment(**payload.model_dump())
    db.add(comment)
    _add_log(
        db,
        actor_name=payload.author_name,
        task_id=payload.task_id,
        action="review_comment_created",
        target_type="review_comment",
        target_id=None,
        before_value=None,
        after_value={
            "comment_type": payload.comment_type,
            "content": payload.content,
        },
    )
    db.commit()
    db.refresh(comment)
    return comment


def update_field(db: Session, field_id: UUID, payload: FieldCorrection) -> ExtractedField:
    field = db.get(ExtractedField, field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")

    before = _field_snapshot(field)
    if "value_text" in payload.model_fields_set:
        field.value_text = payload.value_text
    if "value_normalized" in payload.model_fields_set:
        field.value_normalized = payload.value_normalized
    if "confidence" in payload.model_fields_set:
        field.confidence = payload.confidence

    field.warnings = _updated_warnings(field)
    field.is_verified = True
    field.corrected_by = payload.actor_name
    field.corrected_at = utc_now()
    after = _field_snapshot(field)

    db.add(
        ReviewComment(
            task_id=field.task_id,
            document_id=field.document_id,
            field_id=field.id,
            author_name=payload.actor_name,
            comment_type="field_correction",
            content=payload.comment or "Field corrected",
            before_value=before,
            after_value=after,
        )
    )
    _add_log(
        db,
        actor_name=payload.actor_name,
        task_id=field.task_id,
        action="field_corrected",
        target_type="field",
        target_id=field.id,
        before_value=before,
        after_value=after,
    )
    db.commit()
    db.refresh(field)
    return field


def confirm_result(db: Session, result_id: UUID, payload: ReviewAction) -> AuditResult:
    result = _get_result(db, result_id)
    before = _result_snapshot(result)
    result.review_status = "confirmed"
    result.reviewed_by = payload.actor_name
    result.reviewed_at = utc_now()
    after = _result_snapshot(result)
    _comment_for_result(db, result, payload.actor_name, "audit_result_confirmed", payload.reason or "Audit result confirmed", before, after)
    _add_log(db, payload.actor_name, result.task_id, "audit_result_confirmed", "audit_result", result.id, before, after)
    db.commit()
    db.refresh(result)
    return result


def dismiss_result(db: Session, result_id: UUID, payload: DismissReviewAction) -> AuditResult:
    result = _get_result(db, result_id)
    before = _result_snapshot(result)
    result.review_status = "dismissed"
    result.reviewed_by = payload.actor_name
    result.reviewed_at = utc_now()
    after = _result_snapshot(result) | {"dismiss_reason": payload.reason}
    _comment_for_result(db, result, payload.actor_name, "audit_result_dismissed", payload.reason, before, after)
    _add_log(db, payload.actor_name, result.task_id, "audit_result_dismissed", "audit_result", result.id, before, after)
    db.commit()
    db.refresh(result)
    return result


def rerun_result(db: Session, result_id: UUID, payload: ReviewAction) -> list[AuditResult]:
    result = _get_result(db, result_id)
    task_id = result.task_id
    before = _result_snapshot(result)
    new_results = rule_engine_service.run_audit(db, task_id)
    _add_log(
        db,
        actor_name=payload.actor_name,
        task_id=task_id,
        action="audit_result_rerun",
        target_type="audit_result",
        target_id=result_id,
        before_value=before,
        after_value={
            "result_count": len(new_results),
            "statuses": {result.rule_code: result.status for result in new_results},
        },
    )
    db.commit()
    return new_results


def _scope(statement, column, task_id: UUID | None):
    return statement.where(column == task_id) if task_id else statement


def _field_review_reason(field: ExtractedField) -> str | None:
    warnings = field.warnings or []
    if field.is_required and (not field.value_text or "required_field_missing" in warnings):
        return "required_field_missing"
    if field.confidence is not None and field.confidence < 0.6:
        return "low_confidence"
    return None


def _updated_warnings(field: ExtractedField) -> list[str]:
    warnings = list(field.warnings or [])
    if field.value_text:
        return [warning for warning in warnings if warning != "required_field_missing"]
    if field.is_required and "required_field_missing" not in warnings:
        warnings.append("required_field_missing")
    return warnings


def _get_result(db: Session, result_id: UUID) -> AuditResult:
    result = db.get(AuditResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Audit result not found")
    return result


def _field_snapshot(field: ExtractedField) -> dict:
    return {
        "id": str(field.id),
        "field_name": field.field_name,
        "field_label": field.field_label,
        "value_text": field.value_text,
        "value_normalized": field.value_normalized,
        "confidence": field.confidence,
        "warnings": field.warnings or [],
        "source_page": field.source_page,
        "source_text": field.source_text,
        "source_bbox": field.source_bbox,
        "is_verified": field.is_verified,
    }


def _result_snapshot(result: AuditResult) -> dict:
    return {
        "id": str(result.id),
        "rule_code": result.rule_code,
        "status": result.status,
        "severity": result.severity,
        "message": result.message,
        "review_status": result.review_status,
        "reviewed_by": result.reviewed_by,
        "reviewed_at": result.reviewed_at.isoformat() if result.reviewed_at else None,
    }


def _comment_for_result(
    db: Session,
    result: AuditResult,
    actor_name: str | None,
    comment_type: str,
    content: str,
    before: dict,
    after: dict,
) -> None:
    db.add(
        ReviewComment(
            task_id=result.task_id,
            audit_result_id=result.id,
            author_name=actor_name,
            comment_type=comment_type,
            content=content,
            before_value=before,
            after_value=after,
        )
    )


def _add_log(
    db: Session,
    actor_name: str | None,
    task_id: UUID | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    before_value: dict | None,
    after_value: dict | None,
) -> None:
    db.add(
        AuditLog(
            actor_name=actor_name,
            task_id=task_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_value=before_value,
            after_value=after_value,
        )
    )
