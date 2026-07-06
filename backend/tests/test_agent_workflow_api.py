from fastapi import HTTPException
from uuid import UUID

from app.db.session import SessionLocal
from app.models.audit_result import AuditResult
from app.models.bad_case import BadCase
from app.models.document import Document
from app.services import agent_service
from test_rule_engine_api import build_scenario, client


def make_agent_ready_scenario(**kwargs) -> tuple[dict, dict[str, list[dict]]]:
    task, docs = build_scenario(**kwargs)
    with SessionLocal() as db:
        for document_group in docs.values():
            for document_data in document_group:
                document = db.get(Document, UUID(document_data["id"]))
                assert document is not None
                document.ocr_status = "completed"
                document.extraction_status = "completed"
                document.doc_type_confidence = 1.0
                document.classification_reason = "Agent workflow test fixture."
                document.page_count = 1
        db.commit()
    return task, docs


def create_agent_run(task_id: str) -> dict:
    response = client.post("/api/v1/agents/runs", json={"task_id": task_id})
    assert response.status_code == 200, response.text
    return response.json()


def list_steps(run_id: str) -> list[dict]:
    response = client.get(f"/api/v1/agents/runs/{run_id}/steps")
    assert response.status_code == 200
    return response.json()


def seed_rule_evidence(knowledge_base: str = "regulation") -> None:
    response = client.post(
        "/api/v1/rag/documents",
        data={
            "knowledge_base": knowledge_base,
            "title": "Procurement Rule Evidence",
            "source_type": "synthetic_text",
            "content_text": (
                "PROC_TIME_001 PROC_QTY_001 PROC_AMOUNT_001 PROC_NAME_001 "
                "PROC_ITEM_001 PROC_TAX_001 PROC_MISSING_001 procurement rule evidence."
            ),
            "created_by": "agent_test",
        },
    )
    assert response.status_code == 200
    index_response = client.post(f"/api/v1/rag/documents/{response.json()['id']}/index")
    assert index_response.status_code == 200


def test_state_transition_validation() -> None:
    agent_service.validate_transition("DRAFT", "FILES_UPLOADED")
    try:
        agent_service.validate_transition("DRAFT", "COMPLETED")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Illegal agent state transition" in exc.detail
    else:  # pragma: no cover
        raise AssertionError("Expected invalid transition to fail")


def test_agent_run_creates_steps_and_report_without_bypassing_rule_engine() -> None:
    task, _ = make_agent_ready_scenario()
    seed_rule_evidence()

    run = create_agent_run(task["id"])
    steps = list_steps(run["id"])

    assert run["status"] == "completed"
    assert run["current_state"] == "COMPLETED"
    assert run["output_refs"]["report_id"]
    assert "run_rule_engine" in {step["tool_name"] for step in steps}
    assert "route_review_queue" in {step["tool_name"] for step in steps}
    assert "generate_control_table" in {step["tool_name"] for step in steps}
    with SessionLocal() as db:
        results = db.query(AuditResult).filter(AuditResult.task_id == task["id"]).all()
        assert len(results) == 7
        assert {result.status for result in results} == {"pass"}


def test_failed_step_retry_records_retry_step() -> None:
    task_response = client.post("/api/v1/tasks", json={"name": "Agent OCR fail", "scenario": "procurement"})
    assert task_response.status_code == 200
    upload = client.post(
        f"/api/v1/tasks/{task_response.json()['id']}/documents",
        data={"doc_type_hint": "invoice"},
        files={"file": ("scan.jpg", b"\xff\xd8\xffnot-real-image", "image/jpeg")},
    )
    assert upload.status_code == 200

    run = create_agent_run(task_response.json()["id"])
    assert run["status"] == "failed"
    assert run["current_state"] == "OCR_FAILED"
    steps = list_steps(run["id"])
    assert len([step for step in steps if step["status"] == "failed"]) == 1
    assert "record_bad_case" in {step["tool_name"] for step in steps}
    with SessionLocal() as db:
        cases = db.query(BadCase).filter(BadCase.task_id == UUID(task_response.json()["id"])).all()
        assert len(cases) == 1
        assert cases[0].case_type == "agent"
        assert cases[0].input_payload["failed_state"] == "OCR_FAILED"

    retry = client.post(f"/api/v1/agents/runs/{run['id']}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "failed"
    next_steps = list_steps(run["id"])
    failed_steps = [step for step in next_steps if step["status"] == "failed"]
    assert len(failed_steps) == 2
    assert failed_steps[-1]["input_payload"]["retry_of"] == failed_steps[0]["id"]
    assert len([step for step in next_steps if step["tool_name"] == "record_bad_case"]) == 2


def test_high_risk_exception_routes_to_review_without_auto_confirming() -> None:
    task, _ = make_agent_ready_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1200.0,),
        payment_amounts=(1200.0,),
        voucher_amount=1200.0,
        amount_excluding_tax=1090.91,
        tax_amount=109.09,
        amount_including_tax=1200.0,
    )
    seed_rule_evidence()

    run = create_agent_run(task["id"])
    steps = list_steps(run["id"])

    assert run["status"] == "waiting_review"
    assert run["current_state"] == "HUMAN_REVIEW_REQUIRED"
    assert run["output_refs"]["review_result_ids"]
    assert "create_review_ticket" in {step["tool_name"] for step in steps}
    assert "route_review_queue" in {step["tool_name"] for step in steps}
    assert "generate_control_table" not in {step["tool_name"] for step in steps}
    with SessionLocal() as db:
        amount_result = (
            db.query(AuditResult)
            .filter(AuditResult.task_id == task["id"], AuditResult.rule_code == "PROC_AMOUNT_001")
            .one()
        )
        assert amount_result.status == "fail"
        assert amount_result.severity == "high"
        assert amount_result.review_status == "pending"
        assert amount_result.reviewed_at is None

    queue_response = client.get(f"/api/v1/review/queue?task_id={task['id']}")
    assert queue_response.status_code == 200
    for item in queue_response.json():
        if item["audit_result_id"]:
            confirm_response = client.post(
                f"/api/v1/audit-results/{item['audit_result_id']}/confirm",
                json={"actor_name": "reviewer", "reason": "Confirmed in agent review test."},
            )
            assert confirm_response.status_code == 200
    resume_response = client.post(f"/api/v1/agents/runs/{run['id']}/resume")
    assert resume_response.status_code == 200
    resumed = resume_response.json()
    assert resumed["status"] == "completed"
    assert resumed["current_state"] == "COMPLETED"
    assert resumed["output_refs"]["report_id"]


def test_no_citation_does_not_generate_evidence_conclusion_and_payload_is_referenced() -> None:
    task, _ = make_agent_ready_scenario()

    run = create_agent_run(task["id"])
    steps = list_steps(run["id"])
    evidence_step = next(step for step in steps if step["tool_name"] == "retrieve_evidence")

    assert run["status"] == "waiting_review"
    assert run["current_state"] == "HUMAN_REVIEW_REQUIRED"
    assert not run["output_refs"].get("report_id")
    assert run["output_refs"]["review_queue"]["item_type_counts"]["agent_step"] >= 1
    assert evidence_step["output_payload"]["status"] == "no_answer"
    assert evidence_step["output_payload"]["evidence_insufficient"] is True
    assert evidence_step["output_payload"]["conclusion_generated"] is False
    serialized_steps = str([(step["input_payload"], step["output_payload"]) for step in steps])
    assert "supplier_name: Supplier Co" not in serialized_steps
    assert "raw_text" not in serialized_steps
    assert "quote" not in serialized_steps


def test_agent_evidence_retrieval_checks_all_knowledge_bases() -> None:
    task, _ = make_agent_ready_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1200.0,),
        payment_amounts=(1200.0,),
        voucher_amount=1200.0,
        amount_excluding_tax=1090.91,
        tax_amount=109.09,
        amount_including_tax=1200.0,
    )
    seed_rule_evidence("inquiry_case")

    run = create_agent_run(task["id"])
    evidence_step = next(step for step in list_steps(run["id"]) if step["tool_name"] == "retrieve_evidence")

    assert set(evidence_step["input_payload"]["knowledge_bases"]) == {"regulation", "inquiry_case", "prospectus", "workpaper"}
    assert any(citation["knowledge_base"] == "inquiry_case" for citation in evidence_step["output_payload"]["citations"])
