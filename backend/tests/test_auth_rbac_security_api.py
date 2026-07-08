from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.audit_result import AuditResult
from app.models.audit_task import AuditTask
from app.models.extracted_field import ExtractedField


client = TestClient(app)


def auth_headers(email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(email: str, role_codes: list[str]) -> dict:
    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": "test-password",
            "full_name": email.split("@")[0],
            "role_codes": role_codes,
        },
    )
    assert response.status_code == 200
    return response.json()


def create_task(payload: dict | None = None) -> dict:
    body = {"name": "RBAC task", "scenario": "procurement"} | (payload or {})
    response = client.post("/api/v1/tasks", json=body)
    assert response.status_code == 200
    return response.json()


def upload_pdf(task_id: str) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        data={"doc_type_hint": "purchase_contract"},
        files={"file": ("contract.pdf", b"%PDF-1.4\nrbac test\n", "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def add_review_field(task_id: str, document_id: str) -> str:
    field_id = uuid4()
    with SessionLocal() as db:
        db.add(
            ExtractedField(
                id=field_id,
                task_id=UUID(task_id),
                document_id=UUID(document_id),
                field_name="payment_terms",
                field_label="Payment Terms",
                field_type="text",
                value_text=None,
                value_normalized=None,
                unit=None,
                currency=None,
                confidence=0.0,
                source_page=None,
                source_bbox=None,
                source_text="secret original source text should not be logged",
                extraction_method="test",
                is_required=True,
                is_verified=False,
                corrected_by=None,
                corrected_at=None,
                warnings=["required_field_missing"],
            )
        )
        db.commit()
    return str(field_id)


def add_audit_result(task_id: str) -> str:
    result_id = uuid4()
    with SessionLocal() as db:
        db.add(
            AuditResult(
                id=result_id,
                task_id=UUID(task_id),
                rule_id=None,
                rule_code="PROC_TEST_SCOPE",
                rule_version="1.0",
                business_key="SCOPE-001",
                status="fail",
                severity="high",
                message="scope test",
                expected_value={"status": "pass"},
                actual_value={"status": "fail"},
                evidence={"refs": []},
                rag_citations=None,
                review_status="pending",
            )
        )
        db.commit()
    return str(result_id)


def test_login_me_and_password_hash_is_not_returned() -> None:
    user = create_user("analyst@example.com", ["analyst"])
    assert "password_hash" not in user

    headers = auth_headers("analyst@example.com", "test-password")
    me = client.get("/api/v1/auth/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["email"] == "analyst@example.com"
    assert "password_hash" not in me.json()


def test_register_creates_analyst_user_without_returning_password_hash_and_can_login() -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "demo-user@example.com", "password": "demo-password", "full_name": "Demo User"},
        headers={"Authorization": ""},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "password_hash" not in response.json()

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "demo-user@example.com"
    assert me.json()["role_codes"] == ["analyst"]
    assert "password_hash" not in me.json()

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "demo-user@example.com", "password": "demo-password"},
        headers={"Authorization": ""},
    )
    assert login_response.status_code == 200


def test_register_rejects_duplicate_email() -> None:
    payload = {"email": "duplicate-demo@example.com", "password": "demo-password", "full_name": "Duplicate Demo"}

    assert client.post("/api/v1/auth/register", json=payload, headers={"Authorization": ""}).status_code == 200
    duplicate = client.post("/api/v1/auth/register", json=payload, headers={"Authorization": ""})

    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "User already exists"


def test_register_rejects_invalid_email_and_weak_password() -> None:
    invalid_email = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "demo-password", "full_name": "Invalid Email"},
        headers={"Authorization": ""},
    )
    weak_password = client.post(
        "/api/v1/auth/register",
        json={"email": "weak-password@example.com", "password": "short", "full_name": "Weak Password"},
        headers={"Authorization": ""},
    )

    assert invalid_email.status_code == 422
    assert weak_password.status_code == 422


def test_missing_token_returns_401_for_protected_api() -> None:
    response = client.get("/api/v1/tasks", headers={"Authorization": ""})

    assert response.status_code == 401


def test_viewer_is_read_only_for_processing_review_and_report_actions() -> None:
    create_user("viewer@example.com", ["viewer"])
    viewer_headers = auth_headers("viewer@example.com", "test-password")
    task = create_task()
    document = upload_pdf(task["id"])

    list_response = client.get("/api/v1/tasks", headers=viewer_headers)
    assert list_response.status_code == 200
    assert task["id"] not in {item["id"] for item in list_response.json()}
    assert client.post("/api/v1/tasks", json={"name": "blocked"}, headers=viewer_headers).status_code == 403
    assert client.post(f"/api/v1/documents/{document['id']}/ocr", headers=viewer_headers).status_code == 403
    assert client.post(f"/api/v1/documents/{document['id']}/extract", headers=viewer_headers).status_code == 403
    assert client.post(f"/api/v1/tasks/{task['id']}/audit", headers=viewer_headers).status_code == 403
    assert client.patch(
        f"/api/v1/fields/{uuid4()}",
        json={"value_text": "fixed"},
        headers=viewer_headers,
    ).status_code == 403
    assert client.post(f"/api/v1/tasks/{task['id']}/reports/control-table", json={}, headers=viewer_headers).status_code == 403
    assert client.delete(f"/api/v1/documents/{document['id']}", headers=viewer_headers).status_code == 403


def test_default_role_permissions_match_execution_matrix_baseline() -> None:
    roles = {role["code"]: set(role["permissions"]) for role in client.get("/api/v1/roles").json()}

    assert roles["viewer"] == {"read", "evaluation:read"}
    assert {"task:create", "document:upload", "document:process", "audit:run", "report:generate", "field:correct"}.issubset(roles["analyst"])
    assert {"review:write", "document:process", "audit:run", "report:generate", "evaluation:read"}.issubset(roles["reviewer"])
    assert {"project:manage", "rule:manage", "rag:manage", "quality:manage", "audit_log:read"}.issubset(roles["manager"])
    assert roles["admin"] == {"*"}


def test_analyst_object_scope_blocks_other_owner_task() -> None:
    first = create_user("owner-one@example.com", ["analyst"])
    second = create_user("owner-two@example.com", ["analyst"])
    first_headers = auth_headers("owner-one@example.com", "test-password")
    second_headers = auth_headers("owner-two@example.com", "test-password")
    task_response = client.post(
        "/api/v1/tasks",
        json={"name": "Owner one task", "scenario": "procurement"},
        headers=first_headers,
    )
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["owner_id"] == first["id"]

    list_response = client.get("/api/v1/tasks", headers=second_headers)
    assert list_response.status_code == 200
    assert task["id"] not in {item["id"] for item in list_response.json()}
    assert client.get(f"/api/v1/tasks/{task['id']}", headers=second_headers).status_code == 403
    assert client.patch(f"/api/v1/tasks/{task['id']}", json={"name": "blocked"}, headers=second_headers).status_code == 403
    assert second["id"]


def test_bad_case_api_filters_task_scope_for_readers() -> None:
    owner = create_user("badcase-owner@example.com", ["analyst"])
    create_user("badcase-other@example.com", ["analyst"])
    owner_headers = auth_headers("badcase-owner@example.com", "test-password")
    other_headers = auth_headers("badcase-other@example.com", "test-password")
    task = client.post(
        "/api/v1/tasks",
        json={"name": "Scoped bad case task", "scenario": "procurement"},
        headers=owner_headers,
    ).json()
    created = client.post(
        "/api/v1/bad-cases",
        json={
            "task_id": task["id"],
            "case_type": "rule",
            "title": "Scoped rule bad case",
            "input_payload": {"task_id": task["id"]},
            "model_output": {"status": "pass"},
            "expected_output": {"status": "need_review"},
        },
    )
    assert created.status_code == 200

    assert client.get(f"/api/v1/bad-cases/{created.json()['id']}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/v1/bad-cases/{created.json()['id']}", headers=other_headers).status_code == 403
    listed = client.get("/api/v1/bad-cases", headers=other_headers)
    assert listed.status_code == 200
    assert created.json()["id"] not in {case["id"] for case in listed.json()}
    assert owner["id"]


def test_reviewer_can_correct_field_and_audit_log_is_redacted() -> None:
    reviewer = create_user("reviewer@example.com", ["reviewer"])
    reviewer_headers = auth_headers("reviewer@example.com", "test-password")
    task = create_task({"reviewer_id": reviewer["id"]})
    document = upload_pdf(task["id"])
    field_id = add_review_field(task["id"], document["id"])

    response = client.patch(
        f"/api/v1/fields/{field_id}",
        json={"value_text": "Pay in 30 days", "actor_name": "reviewer"},
        headers=reviewer_headers,
    )

    assert response.status_code == 200
    assert response.json()["corrected_by_user_id"] == reviewer["id"]
    logs = client.get("/api/v1/audit-logs").json()
    field_log = next(log for log in logs if log["action"] == "field_corrected")
    assert "secret original source text" not in str(field_log)
    assert "[REDACTED_TEXT]" in str(field_log)
    assert field_log["user_id"]
    assert field_log["ip_address"]
    assert field_log["user_agent"]


def test_unassigned_reviewer_cannot_correct_other_task_field() -> None:
    assigned = create_user("assigned-reviewer@example.com", ["reviewer"])
    create_user("unassigned-reviewer@example.com", ["reviewer"])
    unassigned_headers = auth_headers("unassigned-reviewer@example.com", "test-password")
    task = create_task({"reviewer_id": assigned["id"]})
    document = upload_pdf(task["id"])
    field_id = add_review_field(task["id"], document["id"])

    response = client.patch(
        f"/api/v1/fields/{field_id}",
        json={"value_text": "blocked"},
        headers=unassigned_headers,
    )

    assert response.status_code == 403


def test_analyst_can_correct_own_field_without_review_decision_permission() -> None:
    analyst = create_user("field-analyst@example.com", ["analyst"])
    analyst_headers = auth_headers("field-analyst@example.com", "test-password")
    task_response = client.post(
        "/api/v1/tasks",
        json={"name": "Analyst field correction", "scenario": "procurement"},
        headers=analyst_headers,
    )
    assert task_response.status_code == 200
    task = task_response.json()
    document = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "purchase_contract"},
        files={"file": ("contract.pdf", b"%PDF-1.4\nanalyst field\n", "application/pdf")},
        headers=analyst_headers,
    ).json()
    field_id = add_review_field(task["id"], document["id"])
    result_id = add_audit_result(task["id"])

    assert client.patch(f"/api/v1/fields/{field_id}", json={"value_text": "fixed"}, headers=analyst_headers).status_code == 200
    with SessionLocal() as db:
        db.get(AuditTask, UUID(task["id"])).status = "reviewing"
        db.commit()
    assert client.patch(f"/api/v1/fields/{field_id}", json={"value_text": "late fix"}, headers=analyst_headers).status_code == 403
    assert client.post(f"/api/v1/audit-results/{result_id}/confirm", json={}, headers=analyst_headers).status_code == 403


def test_single_audit_result_read_enforces_task_scope() -> None:
    owner = create_user("result-owner@example.com", ["analyst"])
    create_user("result-other@example.com", ["analyst"])
    owner_headers = auth_headers("result-owner@example.com", "test-password")
    other_headers = auth_headers("result-other@example.com", "test-password")
    task = client.post(
        "/api/v1/tasks",
        json={"name": "Scoped result", "scenario": "procurement"},
        headers=owner_headers,
    ).json()
    result_id = add_audit_result(task["id"])

    assert owner["id"] == task["owner_id"]
    assert client.get(f"/api/v1/audit-results/{result_id}", headers=owner_headers).status_code == 200
    assert client.get(f"/api/v1/audit-results/{result_id}", headers=other_headers).status_code == 403


def test_manager_scope_uses_organization_when_present() -> None:
    create_user("scoped-manager@example.com", ["manager"])
    manager_headers = auth_headers("scoped-manager@example.com", "test-password")
    manager = client.get("/api/v1/auth/me", headers=manager_headers).json()
    client.patch(
        f"/api/v1/users/{manager['id']}",
        json={"organization": "Scoped Project", "role_codes": ["manager"]},
    )
    manager_headers = auth_headers("scoped-manager@example.com", "test-password")
    owner_headers = auth_headers("admin@example.com", "admin-password")
    in_scope = client.post(
        "/api/v1/tasks",
        json={"name": "In scope", "scenario": "procurement", "project_name": "Scoped Project"},
        headers=owner_headers,
    ).json()
    out_scope = client.post(
        "/api/v1/tasks",
        json={"name": "Out scope", "scenario": "procurement", "project_name": "Other Project"},
        headers=owner_headers,
    ).json()

    list_response = client.get("/api/v1/tasks", headers=manager_headers)
    assert in_scope["id"] in {task["id"] for task in list_response.json()}
    assert out_scope["id"] not in {task["id"] for task in list_response.json()}
    assert client.get(f"/api/v1/tasks/{out_scope['id']}", headers=manager_headers).status_code == 403


def test_admin_can_manage_rules_rag_users_roles_and_audit_logs() -> None:
    roles = client.get("/api/v1/roles")
    users = client.get("/api/v1/users")
    rules = client.get("/api/v1/rules")

    assert roles.status_code == 200
    assert users.status_code == 200
    assert rules.status_code == 200

    rule = rules.json()[0]
    update_rule = client.patch(f"/api/v1/rules/{rule['id']}", json={"description": "admin update"})
    rag = client.post(
        "/api/v1/rag/documents",
        data={
            "knowledge_base": "regulation",
            "title": "Synthetic admin RAG",
            "source_type": "synthetic_text",
            "content_text": "Synthetic public text.",
        },
    )
    audit_logs = client.get("/api/v1/audit-logs")

    assert update_rule.status_code == 200
    assert rag.status_code == 200
    assert audit_logs.status_code == 200


def test_upload_rejects_extension_content_mismatch() -> None:
    task = create_task()

    response = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "purchase_contract"},
        files={"file": ("contract.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file content does not match extension"
