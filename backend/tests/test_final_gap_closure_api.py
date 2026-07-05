from uuid import UUID

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.audit_result import AuditResult
from app.models.model_invocation import ModelInvocation
from app.models.report import Report
from app.schemas.auth import UserCreate
from app.services import auth_service
from test_quality_api import create_bad_case, run_eval
from test_rag_api import create_rag_document, index_document, query_rag
from test_rule_engine_api import build_scenario, seed_rag_document


client = TestClient(app)


def auth_headers(email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(email: str, role_codes: list[str]) -> dict:
    with SessionLocal() as db:
        user = auth_service.create_user(
            db,
            UserCreate(
                email=email,
                password="test-password",
                full_name=email.split("@")[0],
                role_codes=role_codes,
            ),
        )
        return {"id": str(user.id), "email": user.email}


def test_model_invocations_are_recorded_for_rag_query() -> None:
    document = create_rag_document(text="Inventory count procedures require source backed evidence.")
    index_document(document["id"])
    with SessionLocal() as db:
        indexed_embeddings = db.query(ModelInvocation).filter(ModelInvocation.invocation_type == "embedding").count()
    assert indexed_embeddings == 1

    result = query_rag("inventory count evidence")

    assert result["status"] == "answer"
    with SessionLocal() as db:
        invocations = db.query(ModelInvocation).order_by(ModelInvocation.created_at).all()
        invocation_types = {invocation.invocation_type for invocation in invocations}
    assert {"embedding", "rag_rerank", "rag_answer"}.issubset(invocation_types)
    assert all(invocation.cost_estimate for invocation in invocations)


def test_workpaper_rag_requires_task_scope_metadata() -> None:
    task = client.post("/api/v1/tasks", json={"name": "Scoped workpaper task", "scenario": "procurement"}).json()
    document = create_rag_document(
        knowledge_base="workpaper",
        title="Scoped Workpaper",
        text="Scoped workpaper evidence for task isolation.",
        metadata_json=f'{{"task_id":"{task["id"]}"}}',
    )
    index_document(document["id"])

    response = client.post(
        "/api/v1/rag/query",
        json={"knowledge_base": "workpaper", "query": "workpaper evidence", "top_k": 3, "metadata_filter": {}},
    )

    assert response.status_code == 400
    assert "task_id" in response.json()["detail"]


def test_agent_run_create_enforces_task_scope() -> None:
    owner = create_user("agent-owner@example.com", ["analyst"])
    create_user("agent-other@example.com", ["analyst"])
    owner_headers = auth_headers("agent-owner@example.com", "test-password")
    other_headers = auth_headers("agent-other@example.com", "test-password")
    task = client.post(
        "/api/v1/tasks",
        json={"name": "Scoped agent task", "scenario": "procurement"},
        headers=owner_headers,
    ).json()
    assert task["owner_id"] == owner["id"]

    response = client.post("/api/v1/agents/runs", json={"task_id": task["id"]}, headers=other_headers)

    assert response.status_code == 403


def test_task_run_executes_rules_and_generates_report_for_ready_task() -> None:
    task, _ = build_scenario()

    response = client.post(f"/api/v1/tasks/{task['id']}/run")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["rag_evidence_status"] == "not_required"
    assert response.json()["rag_citation_count"] == 0
    with SessionLocal() as db:
        assert db.query(AuditResult).filter(AuditResult.task_id == UUID(task["id"])).count() == 7
        assert db.query(Report).filter(Report.task_id == UUID(task["id"])).count() == 1


def test_task_run_reports_rag_evidence_retrieval_for_review_items() -> None:
    seed_rag_document(
        "Task Run RAG Evidence",
        "PROC_AMOUNT_001 evidence retrieval guidance for overpayment review.",
    )
    task, _ = build_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1300.0,),
        payment_amounts=(1300.0,),
        voucher_amount=1300.0,
        amount_excluding_tax=1181.82,
        tax_amount=118.18,
        amount_including_tax=1300.0,
    )

    response = client.post(f"/api/v1/tasks/{task['id']}/run")

    assert response.status_code == 200
    assert response.json()["status"] == "reviewing"
    assert response.json()["rag_evidence_status"] == "completed"
    assert response.json()["rag_citation_count"] > 0


def test_report_generation_supports_markdown_and_pdf() -> None:
    task, _ = build_scenario()
    client.post(f"/api/v1/tasks/{task['id']}/audit")

    markdown = client.post(
        f"/api/v1/tasks/{task['id']}/reports/control-table",
        json={"file_format": "markdown", "generated_by": "reporter"},
    )
    pdf = client.post(
        f"/api/v1/tasks/{task['id']}/reports/control-table",
        json={"file_format": "pdf", "generated_by": "reporter"},
    )

    assert markdown.status_code == 200, markdown.text
    assert markdown.json()["file_format"] == "markdown"
    assert pdf.status_code == 200, pdf.text
    assert pdf.json()["file_format"] == "pdf"


def test_regression_evaluation_uses_validation_or_expected_output_not_status_only() -> None:
    fixed_but_unvalidated = create_bad_case("fixed", in_regression=True)

    result = run_eval("regression")

    assert result["sample_count"] == 1
    assert result["metrics"]["regression_fail_count"] == 1
    assert result["failed_cases"][0]["model_output"]["bad_case_id"] == fixed_but_unvalidated["id"]
