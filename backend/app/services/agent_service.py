from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.audit_result import AuditResult
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.services import (
    classification_service,
    document_service,
    extraction_service,
    linkage_service,
    ocr_service,
    rag_service,
    report_service,
    review_service,
    rule_engine_service,
)

WORKFLOW_NAME = "procurement_agent_v1"
TOOL_WHITELIST = {
    "run_ocr",
    "classify_document",
    "extract_fields",
    "link_business_documents",
    "run_rule_engine",
    "retrieve_evidence",
    "generate_control_table",
    "create_review_ticket",
    "route_review_queue",
    "create_bad_case",
}

STATE_SEQUENCE = [
    "DRAFT",
    "FILES_UPLOADED",
    "OCR_PENDING",
    "OCR_RUNNING",
    "OCR_COMPLETED",
    "CLASSIFICATION_PENDING",
    "CLASSIFICATION_COMPLETED",
    "EXTRACTION_PENDING",
    "EXTRACTION_COMPLETED",
    "LINKAGE_PENDING",
    "LINKAGE_COMPLETED",
    "RULE_AUDIT_PENDING",
    "RULE_AUDIT_COMPLETED",
    "EVIDENCE_RETRIEVAL_PENDING",
    "EVIDENCE_RETRIEVAL_COMPLETED",
    "AUTO_PASS",
    "REPORT_READY",
    "COMPLETED",
]
FAILURE_STATES = {
    "run_ocr": "OCR_FAILED",
    "classify_document": "CLASSIFICATION_FAILED",
    "extract_fields": "EXTRACTION_FAILED",
    "link_business_documents": "LINKAGE_FAILED",
    "run_rule_engine": "RULE_AUDIT_FAILED",
    "retrieve_evidence": "EVIDENCE_RETRIEVAL_FAILED",
    "route_review_queue": "REVIEW_ROUTING_FAILED",
    "generate_control_table": "REPORT_FAILED",
}
RETRY_START = {
    "run_ocr": "OCR_PENDING",
    "classify_document": "CLASSIFICATION_PENDING",
    "extract_fields": "EXTRACTION_PENDING",
    "link_business_documents": "LINKAGE_PENDING",
    "run_rule_engine": "RULE_AUDIT_PENDING",
    "retrieve_evidence": "EVIDENCE_RETRIEVAL_PENDING",
    "route_review_queue": "EVIDENCE_RETRIEVAL_COMPLETED",
    "generate_control_table": "AUTO_PASS",
}
ALLOWED_TRANSITIONS = {
    current: {next_state}
    for current, next_state in zip(STATE_SEQUENCE, STATE_SEQUENCE[1:], strict=False)
}
ALLOWED_TRANSITIONS["EVIDENCE_RETRIEVAL_COMPLETED"] = {"AUTO_PASS", "HUMAN_REVIEW_REQUIRED"}
ALLOWED_TRANSITIONS["HUMAN_REVIEW_REQUIRED"] = {"REVIEWING"}
ALLOWED_TRANSITIONS["REVIEWING"] = {"REPORT_READY"}
for state in STATE_SEQUENCE:
    ALLOWED_TRANSITIONS.setdefault(state, set()).update(FAILURE_STATES.values())
for tool_name, failed_state in FAILURE_STATES.items():
    ALLOWED_TRANSITIONS.setdefault(failed_state, set()).add(RETRY_START[tool_name])


class AgentStepFailed(RuntimeError):
    def __init__(self, tool_name: str, error: dict):
        self.tool_name = tool_name
        self.error = error
        super().__init__(str(error.get("detail") or error.get("type") or "agent step failed"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(
    db: Session,
    task_id: UUID,
    workflow_name: str = WORKFLOW_NAME,
    input_refs: dict | None = None,
) -> AgentRun:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    documents = document_service.list_documents(db, task_id)
    if not documents:
        raise HTTPException(status_code=400, detail="Task has no uploaded documents")
    run = AgentRun(
        task_id=task_id,
        workflow_name=workflow_name,
        status="running",
        current_state="DRAFT",
        input_refs={
            "task_id": str(task_id),
            "document_ids": [str(document.id) for document in documents],
            "document_count": len(documents),
            **(input_refs or {}),
        },
        output_refs={},
        error=None,
        started_at=utc_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _execute_workflow(db, run)
    return get_run(db, run.id)


def get_run(db: Session, run_id: UUID) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return run


def list_steps(db: Session, run_id: UUID) -> list[AgentStep]:
    get_run(db, run_id)
    return list(
        db.scalars(
            select(AgentStep)
            .where(AgentStep.run_id == run_id)
            .order_by(AgentStep.step_order.asc(), AgentStep.created_at.asc())
        )
    )


def retry_run(db: Session, run_id: UUID) -> AgentRun:
    run = get_run(db, run_id)
    failed_step = db.scalar(
        select(AgentStep)
        .where(AgentStep.run_id == run_id, AgentStep.status == "failed")
        .order_by(AgentStep.step_order.asc())
    )
    if failed_step is None:
        raise HTTPException(status_code=400, detail="Agent run has no failed step to retry")
    start_state = RETRY_START.get(failed_step.tool_name)
    if start_state is None:
        raise HTTPException(status_code=400, detail="Failed step is not retryable")
    run.status = "running"
    run.error = None
    run.finished_at = None
    run.updated_at = utc_now()
    db.commit()
    db.refresh(run)
    _execute_workflow(db, run, start_state=start_state, retry_of=failed_step.id)
    return get_run(db, run_id)


def resume_run(db: Session, run_id: UUID) -> AgentRun:
    run = get_run(db, run_id)
    if run.status != "waiting_review" or run.current_state != "HUMAN_REVIEW_REQUIRED":
        raise HTTPException(status_code=400, detail="Agent run is not waiting for human review")
    pending_items = _pending_review_items(db, run.task_id)
    if pending_items:
        raise HTTPException(status_code=400, detail="Human review queue is not empty")

    run.status = "running"
    run.error = None
    run.finished_at = None
    run.updated_at = utc_now()
    db.commit()
    db.refresh(run)

    try:
        _transition(db, run, "REVIEWING")
        report_output = _run_step(
            db,
            run,
            step_name="generate_control_table",
            tool_name="generate_control_table",
            input_payload={"task_id": str(run.task_id), "resumed_after_human_review": True},
            call=lambda: _generate_control_table(db, run.task_id),
        )
        _transition(db, run, "REPORT_READY")
        _transition(db, run, "COMPLETED")
        _complete_run(
            db,
            run,
            {
                **(run.output_refs or {}),
                "status": "completed_after_human_review",
                "report_id": report_output.get("report_id"),
            },
        )
    except AgentStepFailed as exc:
        _fail_run(db, run, FAILURE_STATES.get(exc.tool_name, "REPORT_FAILED"), exc.error)
    return get_run(db, run_id)


def validate_transition(current_state: str, next_state: str) -> None:
    if next_state not in ALLOWED_TRANSITIONS.get(current_state, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Illegal agent state transition: {current_state} -> {next_state}",
        )


def _execute_workflow(
    db: Session,
    run: AgentRun,
    start_state: str = "DRAFT",
    retry_of: UUID | None = None,
) -> None:
    try:
        if start_state == "DRAFT":
            _transition(db, run, "FILES_UPLOADED")
        if _should_run(start_state, "OCR_PENDING"):
            _run_ocr_stage(db, run, retry_of)
        if _should_run(start_state, "CLASSIFICATION_PENDING"):
            _run_classification_stage(db, run, retry_of)
        if _should_run(start_state, "EXTRACTION_PENDING"):
            _run_extraction_stage(db, run, retry_of)
        if _should_run(start_state, "LINKAGE_PENDING"):
            _run_linkage_stage(db, run, retry_of)
        if _should_run(start_state, "RULE_AUDIT_PENDING"):
            results = _run_rule_audit_stage(db, run, retry_of)
        else:
            results = _list_audit_results(db, run.task_id)
        if _should_run(start_state, "EVIDENCE_RETRIEVAL_PENDING"):
            evidence_output = _run_evidence_stage(db, run, results, retry_of)
        else:
            evidence_output = {"status": "skipped"}
            if start_state == "EVIDENCE_RETRIEVAL_COMPLETED" and run.current_state == "REVIEW_ROUTING_FAILED":
                _transition(db, run, "EVIDENCE_RETRIEVAL_COMPLETED")

        review_results = [result for result in results if _requires_result_review(result)]
        if review_results:
            _transition(db, run, "HUMAN_REVIEW_REQUIRED")
            for result in review_results:
                _run_step(
                    db,
                    run,
                    step_name=f"create_review_ticket:{result.id}",
                    tool_name="create_review_ticket",
                    input_payload={"audit_result_id": str(result.id), "retry_of": _str_or_none(retry_of)},
                    call=lambda result_id=result.id: _create_review_ticket(db, result_id),
                )
            route_output = _run_review_routing_step(db, run, retry_of)
            _pause_for_review(
                db,
                run,
                {
                    "status": "human_review_required",
                    "audit_result_ids": [str(result.id) for result in results],
                    "review_result_ids": [str(result.id) for result in review_results],
                    "review_queue": route_output,
                    "evidence": evidence_output,
                },
            )
            return

        route_output = _run_review_routing_step(db, run, retry_of)
        if route_output.get("review_item_count", 0) > 0:
            _transition(db, run, "HUMAN_REVIEW_REQUIRED")
            _pause_for_review(
                db,
                run,
                {
                    "status": "human_review_required",
                    "audit_result_ids": [str(result.id) for result in results],
                    "review_result_ids": [],
                    "review_queue": route_output,
                    "evidence": evidence_output,
                },
            )
            return

        _transition(db, run, "AUTO_PASS")
        report_output = _run_step(
            db,
            run,
            step_name="generate_control_table",
            tool_name="generate_control_table",
            input_payload={"task_id": str(run.task_id), "retry_of": _str_or_none(retry_of)},
            call=lambda: _generate_control_table(db, run.task_id),
        )
        _transition(db, run, "REPORT_READY")
        _transition(db, run, "COMPLETED")
        _complete_run(
            db,
            run,
            {
                "status": "completed",
                "audit_result_ids": [str(result.id) for result in results],
                "report_id": report_output.get("report_id"),
                "evidence": evidence_output,
            },
        )
    except AgentStepFailed as exc:
        _fail_run(db, run, FAILURE_STATES.get(exc.tool_name, "REPORT_FAILED"), exc.error)


def _run_ocr_stage(db: Session, run: AgentRun, retry_of: UUID | None) -> None:
    _transition(db, run, "OCR_PENDING")
    _transition(db, run, "OCR_RUNNING")
    for document in document_service.list_documents(db, run.task_id):
        _run_step(
            db,
            run,
            step_name=f"run_ocr:{document.id}",
            tool_name="run_ocr",
            input_payload={"document_id": str(document.id), "retry_of": _str_or_none(retry_of)},
            call=lambda document_id=document.id: _run_ocr(db, document_id),
        )
    _transition(db, run, "OCR_COMPLETED")


def _run_classification_stage(db: Session, run: AgentRun, retry_of: UUID | None) -> None:
    _transition(db, run, "CLASSIFICATION_PENDING")
    for document in document_service.list_documents(db, run.task_id):
        _run_step(
            db,
            run,
            step_name=f"classify_document:{document.id}",
            tool_name="classify_document",
            input_payload={"document_id": str(document.id), "retry_of": _str_or_none(retry_of)},
            call=lambda document_id=document.id: _classify_document(db, document_id),
        )
    _transition(db, run, "CLASSIFICATION_COMPLETED")


def _run_extraction_stage(db: Session, run: AgentRun, retry_of: UUID | None) -> None:
    _transition(db, run, "EXTRACTION_PENDING")
    for document in document_service.list_documents(db, run.task_id):
        _run_step(
            db,
            run,
            step_name=f"extract_fields:{document.id}",
            tool_name="extract_fields",
            input_payload={
                "document_id": str(document.id),
                "doc_type": document.doc_type,
                "retry_of": _str_or_none(retry_of),
            },
            call=lambda document_id=document.id: _extract_fields(db, document_id),
        )
    _transition(db, run, "EXTRACTION_COMPLETED")


def _run_linkage_stage(db: Session, run: AgentRun, retry_of: UUID | None) -> None:
    _transition(db, run, "LINKAGE_PENDING")
    _run_step(
        db,
        run,
        step_name="link_business_documents",
        tool_name="link_business_documents",
        input_payload={"task_id": str(run.task_id), "retry_of": _str_or_none(retry_of)},
        call=lambda: _link_business_documents(db, run.task_id),
    )
    _transition(db, run, "LINKAGE_COMPLETED")


def _run_rule_audit_stage(db: Session, run: AgentRun, retry_of: UUID | None) -> list[AuditResult]:
    _transition(db, run, "RULE_AUDIT_PENDING")
    _run_step(
        db,
        run,
        step_name="run_rule_engine",
        tool_name="run_rule_engine",
        input_payload={"task_id": str(run.task_id), "retry_of": _str_or_none(retry_of)},
        call=lambda: _run_rule_engine(db, run.task_id),
    )
    _transition(db, run, "RULE_AUDIT_COMPLETED")
    return _list_audit_results(db, run.task_id)


def _run_evidence_stage(
    db: Session,
    run: AgentRun,
    results: list[AuditResult],
    retry_of: UUID | None,
) -> dict:
    _transition(db, run, "EVIDENCE_RETRIEVAL_PENDING")
    output = _run_step(
        db,
        run,
        step_name="retrieve_evidence:regulation",
        tool_name="retrieve_evidence",
        input_payload={
            "query_ref": "procurement_rule_evidence",
            "knowledge_base": "regulation",
            "audit_result_count": len(results),
            "retry_of": _str_or_none(retry_of),
        },
        call=lambda: _retrieve_evidence(db, results),
    )
    _transition(db, run, "EVIDENCE_RETRIEVAL_COMPLETED")
    return output


def _run_review_routing_step(db: Session, run: AgentRun, retry_of: UUID | None) -> dict:
    return _run_step(
        db,
        run,
        step_name="route_review_queue",
        tool_name="route_review_queue",
        input_payload={"task_id": str(run.task_id), "retry_of": _str_or_none(retry_of)},
        call=lambda: _route_review_queue(db, run.task_id),
    )


def _run_step(
    db: Session,
    run: AgentRun,
    *,
    step_name: str,
    tool_name: str,
    input_payload: dict,
    call,
) -> dict:
    if tool_name not in TOOL_WHITELIST:
        raise HTTPException(status_code=400, detail="Agent tool is not whitelisted")
    started = perf_counter()
    error = None
    output: dict = {}
    status = "completed"
    try:
        output = call()
    except HTTPException as exc:
        status = "failed"
        error = {"type": "HTTPException", "status_code": exc.status_code, "detail": exc.detail}
    except Exception as exc:  # pragma: no cover - defensive serialization only
        status = "failed"
        error = {"type": exc.__class__.__name__, "detail": str(exc)}
    duration_ms = int((perf_counter() - started) * 1000)
    step = AgentStep(
        run_id=run.id,
        step_name=step_name,
        step_order=_next_step_order(db, run.id),
        tool_name=tool_name,
        status=status,
        input_payload=_safe_payload(input_payload),
        output_payload=_safe_payload(output),
        error=error,
        duration_ms=duration_ms,
    )
    db.add(step)
    db.commit()
    if error is not None:
        raise AgentStepFailed(tool_name, error)
    return output


def _transition(db: Session, run: AgentRun, next_state: str) -> None:
    validate_transition(run.current_state, next_state)
    run.current_state = next_state
    run.updated_at = utc_now()
    db.commit()
    db.refresh(run)


def _complete_run(db: Session, run: AgentRun, output_refs: dict) -> None:
    run.status = "completed"
    run.output_refs = _safe_payload(output_refs)
    run.error = None
    run.finished_at = utc_now()
    run.updated_at = utc_now()
    db.commit()


def _pause_for_review(db: Session, run: AgentRun, output_refs: dict) -> None:
    run.status = "waiting_review"
    run.output_refs = _safe_payload(output_refs)
    run.error = None
    run.finished_at = None
    run.updated_at = utc_now()
    db.commit()


def _fail_run(db: Session, run: AgentRun, failed_state: str, error: dict) -> None:
    if failed_state not in ALLOWED_TRANSITIONS.get(run.current_state, set()):
        run.current_state = failed_state
    else:
        _transition(db, run, failed_state)
    run.status = "failed"
    run.error = error
    run.finished_at = utc_now()
    run.updated_at = utc_now()
    db.commit()


def _run_ocr(db: Session, document_id: UUID) -> dict:
    existing = document_service.get_document(db, document_id)
    if existing.ocr_status == "completed":
        return {
            "document_id": str(existing.id),
            "ocr_status": existing.ocr_status,
            "page_count": existing.page_count,
            "skipped": True,
        }
    document = ocr_service.run_ocr(db, document_id)
    if document.ocr_status == "failed":
        raise HTTPException(status_code=400, detail=document.ocr_error or "OCR failed")
    return {"document_id": str(document.id), "ocr_status": document.ocr_status, "page_count": document.page_count}


def _classify_document(db: Session, document_id: UUID) -> dict:
    existing = document_service.get_document(db, document_id)
    if existing.doc_type and existing.doc_type != "unknown" and existing.classification_reason:
        return {
            "document_id": str(existing.id),
            "doc_type": existing.doc_type,
            "confidence": existing.doc_type_confidence,
            "need_human_review": existing.review_status == "need_review",
            "skipped": True,
        }
    result = classification_service.classify_document(db, document_id)
    return {
        "document_id": str(result.document_id),
        "doc_type": result.doc_type,
        "confidence": result.confidence,
        "need_human_review": result.need_human_review,
    }


def _extract_fields(db: Session, document_id: UUID) -> dict:
    existing = document_service.get_document(db, document_id)
    if existing.extraction_status == "completed":
        fields = extraction_service.list_document_fields(db, document_id)
        return {"document_id": str(document_id), "field_count": len(fields), "skipped": True}
    fields = extraction_service.extract_document(db, document_id)
    return {"document_id": str(document_id), "field_count": len(fields)}


def _link_business_documents(db: Session, task_id: UUID) -> dict:
    documents = document_service.list_documents(db, task_id)
    if documents and all(document.business_key for document in documents):
        relations = linkage_service.list_document_relations(db, task_id)
        return {
            "task_id": str(task_id),
            "linked_document_count": len(documents),
            "relation_count": len(relations),
            "warnings": [],
            "skipped": True,
        }
    result = linkage_service.link_documents(db, task_id)
    return {
        "task_id": str(result.task_id),
        "linked_document_count": result.linked_document_count,
        "relation_count": result.relation_count,
        "warnings": result.warnings,
    }


def _run_rule_engine(db: Session, task_id: UUID) -> dict:
    results = rule_engine_service.run_audit(db, task_id)
    counts = Counter(result.status for result in results)
    return {
        "task_id": str(task_id),
        "audit_result_ids": [str(result.id) for result in results],
        "status_counts": dict(counts),
    }


def _retrieve_evidence(db: Session, results: list[AuditResult]) -> dict:
    query = " ".join(sorted({result.rule_code for result in results})) or "procurement audit evidence"
    rag_result = rag_service.query(
        db,
        query_text=query,
        knowledge_base="regulation",
        top_k=3,
        metadata_filter={},
        task_id=results[0].task_id if results else None,
    )
    citations = [
        {
            "chunk_id": str(citation["chunk_id"]),
            "document_id": str(citation["document_id"]),
            "title": citation["title"],
            "score": citation["score"],
            "knowledge_base": citation["knowledge_base"],
        }
        for citation in rag_result["citations"]
    ]
    return {
        "status": rag_result["status"],
        "knowledge_base": "regulation",
        "citation_count": len(citations),
        "citations": citations,
        "evidence_insufficient": rag_result["status"] == "no_answer",
        "conclusion_generated": False,
    }


def _route_review_queue(db: Session, task_id: UUID) -> dict:
    items = _pending_review_items(db, task_id)
    counts = Counter(item.item_type for item in items)
    return {
        "task_id": str(task_id),
        "review_item_count": len(items),
        "item_type_counts": dict(counts),
        "items": [
            {
                "item_type": item.item_type,
                "reason": item.reason,
                "document_id": _str_or_none(item.document_id),
                "field_id": _str_or_none(item.field_id),
                "audit_result_id": _str_or_none(item.audit_result_id),
                "agent_step_id": _str_or_none(item.agent_step_id),
                "comment_id": _str_or_none(item.comment_id),
            }
            for item in items
        ],
    }


def _pending_review_items(db: Session, task_id: UUID):
    return review_service.list_review_queue(db, task_id)


def _generate_control_table(db: Session, task_id: UUID) -> dict:
    report = report_service.generate_control_table_report(db, task_id, generated_by="agent")
    return {"task_id": str(task_id), "report_id": str(report.id), "status": report.status}


def _create_review_ticket(db: Session, result_id: UUID) -> dict:
    result = rule_engine_service.get_audit_result(db, result_id)
    if result.status != "pass" and result.review_status == "not_required":
        result.review_status = "pending"
        db.commit()
        db.refresh(result)
    return {
        "audit_result_id": str(result.id),
        "status": result.status,
        "severity": result.severity,
        "review_status": result.review_status,
        "auto_confirmed": False,
    }


def _list_audit_results(db: Session, task_id: UUID) -> list[AuditResult]:
    return list(db.scalars(select(AuditResult).where(AuditResult.task_id == task_id)))


def _requires_result_review(result: AuditResult) -> bool:
    if result.status == "pass":
        return False
    return result.review_status not in {"confirmed", "dismissed"}


def _next_step_order(db: Session, run_id: UUID) -> int:
    current = db.scalar(select(func.max(AgentStep.step_order)).where(AgentStep.run_id == run_id))
    return int(current or 0) + 1


def _should_run(start_state: str, stage_state: str) -> bool:
    return STATE_SEQUENCE.index(stage_state) >= STATE_SEQUENCE.index(start_state)


def _safe_payload(payload: dict) -> dict:
    blocked = {"raw_text", "source_text", "chunk_text", "quote", "prompt", "content_text"}
    return {
        key: ("[redacted]" if key in blocked else value)
        for key, value in payload.items()
    }


def _str_or_none(value: UUID | None) -> str | None:
    return str(value) if value is not None else None
