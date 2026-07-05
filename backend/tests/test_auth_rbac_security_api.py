from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
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


def create_task() -> dict:
    response = client.post("/api/v1/tasks", json={"name": "RBAC task", "scenario": "procurement"})
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


def test_login_me_and_password_hash_is_not_returned() -> None:
    user = create_user("analyst@example.com", ["analyst"])
    assert "password_hash" not in user

    headers = auth_headers("analyst@example.com", "test-password")
    me = client.get("/api/v1/auth/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["email"] == "analyst@example.com"
    assert "password_hash" not in me.json()


def test_missing_token_returns_401_for_protected_api() -> None:
    response = client.get("/api/v1/tasks", headers={"Authorization": ""})

    assert response.status_code == 401


def test_viewer_is_read_only_for_processing_review_and_report_actions() -> None:
    create_user("viewer@example.com", ["viewer"])
    viewer_headers = auth_headers("viewer@example.com", "test-password")
    task = create_task()
    document = upload_pdf(task["id"])

    assert client.get("/api/v1/tasks", headers=viewer_headers).status_code == 200
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


def test_reviewer_can_correct_field_and_audit_log_is_redacted() -> None:
    create_user("reviewer@example.com", ["reviewer"])
    reviewer_headers = auth_headers("reviewer@example.com", "test-password")
    task = create_task()
    document = upload_pdf(task["id"])
    field_id = add_review_field(task["id"], document["id"])

    response = client.patch(
        f"/api/v1/fields/{field_id}",
        json={"value_text": "Pay in 30 days", "actor_name": "reviewer"},
        headers=reviewer_headers,
    )

    assert response.status_code == 200
    logs = client.get("/api/v1/audit-logs").json()
    field_log = next(log for log in logs if log["action"] == "field_corrected")
    assert "secret original source text" not in str(field_log)
    assert "[REDACTED_TEXT]" in str(field_log)


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
