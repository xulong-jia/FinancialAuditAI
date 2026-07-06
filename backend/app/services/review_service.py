from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import redact
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.audit_log import AuditLog
from app.models.audit_result import AuditResult
from app.models.audit_task import AuditTask
from app.models.bad_case import BadCase
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.review_comment import ReviewComment
from app.schemas.quality import BadCaseCreate
from app.schemas.review import (
    BadCaseFromReview,
    DismissReviewAction,
    FieldCorrection,
    ReextractRequest,
    ReviewAction,
    ReviewCommentCreate,
    ReviewQueueItem,
)
from app.services import bad_case_service, extraction_service, rule_engine_service


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def list_review_queue(db: Session, task_id: UUID | None = None) -> list[ReviewQueueItem]:
    documents = list(db.scalars(_scope(select(Document), Document.task_id, task_id)))
    fields = list(db.scalars(_scope(select(ExtractedField), ExtractedField.task_id, task_id)))
    results = list(db.scalars(_scope(select(AuditResult), AuditResult.task_id, task_id)))
    agent_steps = _review_agent_steps(db, task_id)
    comments = list(db.scalars(_scope(select(ReviewComment), ReviewComment.task_id, task_id)))

    items: list[ReviewQueueItem] = []
    for document in documents:
        reason = _document_review_reason(document)
        if reason:
            items.append(
                ReviewQueueItem(
                    item_type="document",
                    task_id=document.task_id,
                    document_id=document.id,
                    reason=reason,
                    document=document,
                )
            )

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
        reason = _result_review_reason(result)
        if reason:
            items.append(
                ReviewQueueItem(
                    item_type="audit_result",
                    task_id=result.task_id,
                    audit_result_id=result.id,
                    reason=reason,
                    audit_result=result,
                )
            )

    for step in agent_steps:
        run = db.get(AgentRun, step.run_id)
        if run is None:
            continue
        reason = _agent_step_review_reason(step)
        if reason:
            items.append(
                ReviewQueueItem(
                    item_type="agent_step",
                    task_id=run.task_id,
                    agent_step_id=step.id,
                    reason=reason,
                    agent_step=step,
                )
            )

    for comment in comments:
        if (
            comment.comment_type == "manual_review"
            and not (comment.after_value or {}).get("resolved")
            and not _manual_review_comment_resolved(db, comment)
        ):
            items.append(
                ReviewQueueItem(
                    item_type="comment",
                    task_id=comment.task_id,
                    document_id=comment.document_id,
                    field_id=comment.field_id,
                    audit_result_id=comment.audit_result_id,
                    comment_id=comment.id,
                    reason="manual_review",
                    comment=comment,
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


def create_comment(
    db: Session,
    payload: ReviewCommentCreate,
    *,
    author_id: UUID | None = None,
    author_name: str | None = None,
) -> ReviewComment:
    if db.get(AuditTask, payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    data = payload.model_dump()
    data["author_id"] = author_id or payload.author_id
    data["author_name"] = author_name or payload.author_name
    comment = ReviewComment(**data)
    db.add(comment)
    _add_log(
        db,
        actor_name=comment.author_name,
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


def update_field(db: Session, field_id: UUID, payload: FieldCorrection, actor_id: UUID | None = None) -> ExtractedField:
    field = db.get(ExtractedField, field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")

    _ensure_original_snapshot(field)
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
    field.corrected_by_user_id = actor_id
    field.corrected_at = utc_now()
    after = _field_snapshot(field)

    db.add(
        ReviewComment(
            task_id=field.task_id,
            document_id=field.document_id,
            field_id=field.id,
            author_id=actor_id,
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


def reextract_document(db: Session, document_id: UUID, payload: ReextractRequest, actor_id: UUID | None = None) -> list[ExtractedField]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    before_fields = [
        _field_snapshot(field)
        for field in db.scalars(select(ExtractedField).where(ExtractedField.document_id == document_id))
    ]
    fields = extraction_service.extract_document(db, document_id)
    after_fields = [_field_snapshot(field) for field in fields]
    db.add(
        ReviewComment(
            task_id=document.task_id,
            document_id=document.id,
            author_id=actor_id,
            author_name=payload.actor_name,
            comment_type="reextract_requested",
            content=payload.reason or "Document re-extracted from Review Center.",
            before_value={"fields": before_fields},
            after_value={"fields": after_fields},
        )
    )
    _add_log(
        db,
        actor_name=payload.actor_name,
        task_id=document.task_id,
        action="document_reextracted",
        target_type="document",
        target_id=document.id,
        before_value={"field_count": len(before_fields)},
        after_value={"field_count": len(after_fields)},
    )
    db.commit()
    return extraction_service.list_document_fields(db, document_id)


def rerun_rules_for_field(db: Session, field_id: UUID, payload: ReviewAction, actor_id: UUID | None = None) -> list[AuditResult]:
    field = db.get(ExtractedField, field_id)
    if field is None:
        raise HTTPException(status_code=404, detail="Field not found")
    before = _field_snapshot(field)
    results = rule_engine_service.run_audit(db, field.task_id)
    db.add(
        ReviewComment(
            task_id=field.task_id,
            document_id=field.document_id,
            field_id=field.id,
            author_id=actor_id,
            author_name=payload.actor_name,
            comment_type="field_rules_rerun",
            content=payload.reason or "Rules rerun after field review.",
            before_value=before,
            after_value={"statuses": {result.rule_code: result.status for result in results}},
        )
    )
    _add_log(
        db,
        actor_name=payload.actor_name,
        task_id=field.task_id,
        action="field_rules_rerun",
        target_type="field",
        target_id=field.id,
        before_value=before,
        after_value={"result_count": len(results)},
    )
    db.commit()
    return results


def create_bad_case_from_review(db: Session, payload: BadCaseFromReview, actor_id: UUID | None = None) -> BadCase:
    if db.get(AuditTask, payload.task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    input_payload = payload.model_dump(mode="json")
    model_output = _review_source_snapshot(db, payload)
    case = bad_case_service.create_case(
        db,
        BadCaseCreate(
            task_id=payload.task_id,
            document_id=payload.document_id,
            case_type=payload.case_type,
            title=payload.title,
            input_payload=input_payload,
            model_output=model_output,
            expected_output={"review_outcome": "pending_human_resolution"},
            root_cause="pending_review",
            fix_plan="Triage from Review Center.",
            severity=payload.severity,
            owner_name=payload.owner_name,
            in_regression=True,
        ),
    )
    db.add(
        ReviewComment(
            task_id=payload.task_id,
            document_id=payload.document_id,
            audit_result_id=payload.audit_result_id,
            field_id=payload.field_id,
            author_id=actor_id,
            author_name=payload.owner_name,
            comment_type="bad_case_created",
            content=f"Bad case created: {case.title}",
            after_value={"bad_case_id": str(case.id)},
        )
    )
    _add_log(
        db,
        actor_name=payload.owner_name,
        task_id=payload.task_id,
        action="bad_case_from_review_created",
        target_type="bad_case",
        target_id=case.id,
        before_value=None,
        after_value={"case_type": case.case_type, "title": case.title},
    )
    db.commit()
    db.refresh(case)
    return case


def confirm_result(db: Session, result_id: UUID, payload: ReviewAction, actor_id: UUID | None = None) -> AuditResult:
    result = _get_result(db, result_id)
    before = _result_snapshot(result)
    result.review_status = "confirmed"
    result.reviewed_by = payload.actor_name
    result.reviewed_by_user_id = actor_id
    result.reviewed_at = utc_now()
    after = _result_snapshot(result)
    _comment_for_result(db, result, payload.actor_name, "audit_result_confirmed", payload.reason or "Audit result confirmed", before, after, actor_id=actor_id)
    _add_log(db, payload.actor_name, result.task_id, "audit_result_confirmed", "audit_result", result.id, before, after)
    db.commit()
    db.refresh(result)
    return result


def dismiss_result(db: Session, result_id: UUID, payload: DismissReviewAction, actor_id: UUID | None = None) -> AuditResult:
    result = _get_result(db, result_id)
    before = _result_snapshot(result)
    result.review_status = "dismissed"
    result.reviewed_by = payload.actor_name
    result.reviewed_by_user_id = actor_id
    result.reviewed_at = utc_now()
    after = _result_snapshot(result) | {"dismiss_reason": payload.reason}
    _comment_for_result(db, result, payload.actor_name, "audit_result_dismissed", payload.reason, before, after, actor_id=actor_id)
    _add_log(db, payload.actor_name, result.task_id, "audit_result_dismissed", "audit_result", result.id, before, after)
    db.commit()
    db.refresh(result)
    return result


def rerun_result(db: Session, result_id: UUID, payload: ReviewAction, actor_id: UUID | None = None) -> list[AuditResult]:
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
    if field.is_verified:
        return None
    warnings = field.warnings or []
    if field.is_required and (not field.value_text or "required_field_missing" in warnings):
        return "required_field_missing"
    if field.confidence is not None and field.confidence < 0.6:
        return "low_confidence"
    return None


def _document_review_reason(document: Document) -> str | None:
    if document.ocr_status == "failed":
        return "ocr_failed"
    if document.doc_type in {None, "unknown"}:
        return "classification_missing"
    if document.doc_type_confidence is not None and document.doc_type_confidence < 0.6:
        return "classification_low_confidence"
    if document.review_status == "need_review":
        return "document_need_review"
    return None


def _result_review_reason(result: AuditResult) -> str | None:
    if result.review_status != "pending":
        return None
    if result.status == "fail":
        return f"rule_fail:{result.severity}"
    if result.status == "need_review":
        return "rule_need_review"
    if result.status == "warning" and result.severity == "high":
        return "high_severity_warning"
    if result.status == "warning":
        return f"rule_warning:{result.severity}"
    return None


def _agent_step_review_reason(step: AgentStep) -> str | None:
    if step.status == "failed":
        return "agent_step_failed"
    if step.output_payload.get("evidence_insufficient") is True:
        return "rag_evidence_insufficient"
    return None


def _review_agent_steps(db: Session, task_id: UUID | None) -> list[AgentStep]:
    statement = select(AgentStep).join(AgentRun, AgentRun.id == AgentStep.run_id)
    if task_id:
        statement = statement.where(AgentRun.task_id == task_id)
    return [
        step
        for step in db.scalars(statement)
        if not _agent_step_review_resolved(db, step)
    ]


def _agent_step_review_resolved(db: Session, step: AgentStep) -> bool:
    run = db.get(AgentRun, step.run_id)
    if run is None:
        return False
    comments = db.scalars(
        select(ReviewComment).where(
            ReviewComment.task_id == run.task_id,
            ReviewComment.comment_type == "agent_step_reviewed",
        )
    )
    for comment in comments:
        after_value = comment.after_value or {}
        if after_value.get("agent_step_id") == str(step.id) and after_value.get("resolved") is True:
            return True
    return False


def _manual_review_comment_resolved(db: Session, comment: ReviewComment) -> bool:
    comments = db.scalars(
        select(ReviewComment).where(
            ReviewComment.task_id == comment.task_id,
            ReviewComment.comment_type == "manual_review_resolved",
        )
    )
    for resolution in comments:
        after_value = resolution.after_value or {}
        if after_value.get("comment_id") == str(comment.id) and after_value.get("resolved") is True:
            return True
    return False


def _review_source_snapshot(db: Session, payload: BadCaseFromReview) -> dict:
    if payload.audit_result_id:
        result = db.get(AuditResult, payload.audit_result_id)
        return _result_snapshot(result) if result else {}
    if payload.field_id:
        field = db.get(ExtractedField, payload.field_id)
        return _field_snapshot(field) if field else {}
    if payload.agent_step_id:
        step = db.get(AgentStep, payload.agent_step_id)
        return {
            "step_name": step.step_name,
            "tool_name": step.tool_name,
            "status": step.status,
            "error": step.error,
            "output_payload": step.output_payload,
        } if step else {}
    if payload.comment_id:
        comment = db.get(ReviewComment, payload.comment_id)
        return {
            "comment_type": comment.comment_type,
            "content": comment.content,
            "before_value": comment.before_value,
            "after_value": comment.after_value,
        } if comment else {}
    if payload.document_id:
        document = db.get(Document, payload.document_id)
        return {
            "document_id": str(document.id),
            "doc_type": document.doc_type,
            "ocr_status": document.ocr_status,
            "review_status": document.review_status,
        } if document else {}
    return {}


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
        "original_value_text": field.original_value_text,
        "original_value_normalized": field.original_value_normalized,
        "original_confidence": field.original_confidence,
        "confidence": field.confidence,
        "warnings": field.warnings or [],
        "source_page": field.source_page,
        "source_text": field.source_text,
        "source_bbox": field.source_bbox,
        "is_verified": field.is_verified,
    }


def _ensure_original_snapshot(field: ExtractedField) -> None:
    if (
        field.original_value_text is None
        and field.original_value_normalized is None
        and field.original_confidence is None
    ):
        field.original_value_text = field.value_text
        field.original_value_normalized = field.value_normalized
        field.original_confidence = field.confidence


def _result_snapshot(result: AuditResult) -> dict:
    return {
        "id": str(result.id),
        "rule_code": result.rule_code,
        "status": result.status,
        "severity": result.severity,
        "message": result.message,
        "review_status": result.review_status,
        "reviewed_by": result.reviewed_by,
        "reviewed_by_user_id": str(result.reviewed_by_user_id) if result.reviewed_by_user_id else None,
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
    *,
    actor_id: UUID | None = None,
) -> None:
    db.add(
        ReviewComment(
            task_id=result.task_id,
            audit_result_id=result.id,
            author_id=actor_id,
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
            before_value=redact(before_value),
            after_value=redact(after_value),
        )
    )
