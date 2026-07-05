from uuid import UUID

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.models.extracted_field import ExtractedField
from app.models.review_comment import ReviewComment
from test_rule_engine_api import build_scenario, client, run_audit


def field_by_name(document_id: str, field_name: str) -> ExtractedField:
    with SessionLocal() as db:
        return (
            db.query(ExtractedField)
            .filter(
                ExtractedField.document_id == UUID(document_id),
                ExtractedField.field_name == field_name,
            )
            .one()
        )


def test_review_queue_and_comments_api() -> None:
    task, _ = build_scenario(omit=("invoice", "tax_amount"))
    run_audit(task["id"])

    queue_response = client.get(f"/api/v1/review/queue?task_id={task['id']}")

    assert queue_response.status_code == 200
    queue = queue_response.json()
    assert {item["item_type"] for item in queue} == {"field", "audit_result"}
    assert any(item["reason"] == "required_field_missing" for item in queue)

    comment_response = client.post(
        "/api/v1/review/comments",
        json={
            "task_id": task["id"],
            "author_name": "reviewer",
            "comment_type": "general",
            "content": "Need procurement evidence follow-up.",
        },
    )
    assert comment_response.status_code == 200

    list_response = client.get(f"/api/v1/review/comments?task_id={task['id']}")
    assert list_response.status_code == 200
    assert list_response.json()[0]["content"] == "Need procurement evidence follow-up."


def test_field_correction_preserves_source_and_writes_before_after_log() -> None:
    task, docs = build_scenario()
    contract = docs["purchase_contract"][0]
    field = field_by_name(contract["id"], "supplier_name")
    original_source_page = field.source_page
    original_source_text = field.source_text

    response = client.patch(
        f"/api/v1/fields/{field.id}",
        json={
            "value_text": "Supplier Corrected Co",
            "value_normalized": {"value": "Supplier Corrected Co"},
            "confidence": 0.98,
            "actor_name": "reviewer",
            "comment": "Correct supplier name.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["value_text"] == "Supplier Corrected Co"
    assert payload["is_verified"] is True
    assert payload["corrected_by"] == "reviewer"
    assert payload["source_page"] == original_source_page
    assert payload["source_text"] == original_source_text

    with SessionLocal() as db:
        comment = db.query(ReviewComment).filter(ReviewComment.field_id == field.id).one()
        log = db.query(AuditLog).filter(AuditLog.action == "field_corrected").one()
        assert comment.before_value["value_text"] == "Supplier Co"
        assert comment.after_value["value_text"] == "Supplier Corrected Co"
        assert log.before_value["source_text"] == "[REDACTED_TEXT]"
        assert log.after_value["source_text"] == "[REDACTED_TEXT]"
        assert log.task_id == UUID(task["id"])


def test_dismiss_requires_reason_and_writes_audit_log() -> None:
    task, _ = build_scenario(contract_amount=1000.0, invoice_amounts=(1200.0,), payment_amounts=(1200.0,))
    results = run_audit(task["id"])
    result_id = results["PROC_AMOUNT_001"]["id"]

    missing_reason_response = client.post(
        f"/api/v1/audit-results/{result_id}/dismiss",
        json={"actor_name": "reviewer"},
    )
    assert missing_reason_response.status_code == 422

    response = client.post(
        f"/api/v1/audit-results/{result_id}/dismiss",
        json={"actor_name": "reviewer", "reason": "False positive after voucher review."},
    )

    assert response.status_code == 200
    assert response.json()["review_status"] == "dismissed"

    with SessionLocal() as db:
        log = db.query(AuditLog).filter(AuditLog.action == "audit_result_dismissed").one()
        assert log.after_value["dismiss_reason"] == "False positive after voucher review."


def test_confirm_marks_result_reviewed() -> None:
    task, _ = build_scenario(receipt_date="2026-02-10", invoice_date="2026-01-25")
    results = run_audit(task["id"])
    result_id = results["PROC_TIME_001"]["id"]

    response = client.post(
        f"/api/v1/audit-results/{result_id}/confirm",
        json={"actor_name": "reviewer", "reason": "Date inversion confirmed."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["review_status"] == "confirmed"
    assert payload["reviewed_by"] == "reviewer"


def test_high_risk_result_stays_pending_until_manual_action() -> None:
    task, _ = build_scenario(contract_amount=1000.0, invoice_amounts=(1200.0,), payment_amounts=(1200.0,))

    results = run_audit(task["id"])

    assert results["PROC_AMOUNT_001"]["status"] == "fail"
    assert results["PROC_AMOUNT_001"]["severity"] == "high"
    assert results["PROC_AMOUNT_001"]["review_status"] == "pending"


def test_field_correction_then_rerun_uses_rule_engine() -> None:
    task, docs = build_scenario(omit=("invoice", "tax_amount"))
    results = run_audit(task["id"])
    missing_result_id = results["PROC_MISSING_001"]["id"]
    tax_field = field_by_name(docs["invoice"][0]["id"], "tax_amount")

    correction_response = client.patch(
        f"/api/v1/fields/{tax_field.id}",
        json={
            "value_text": "72.73",
            "value_normalized": {"amount": 72.73, "currency": "CNY"},
            "confidence": 0.95,
            "actor_name": "reviewer",
        },
    )
    assert correction_response.status_code == 200
    assert "required_field_missing" not in correction_response.json()["warnings"]

    rerun_response = client.post(
        f"/api/v1/audit-results/{missing_result_id}/rerun",
        json={"actor_name": "reviewer"},
    )

    assert rerun_response.status_code == 200
    rerun_results = {result["rule_code"]: result for result in rerun_response.json()}
    assert rerun_results["PROC_MISSING_001"]["status"] == "pass"

    with SessionLocal() as db:
        log = db.query(AuditLog).filter(AuditLog.action == "audit_result_rerun").one()
        assert log.before_value["rule_code"] == "PROC_MISSING_001"
        assert log.after_value["statuses"]["PROC_MISSING_001"] == "pass"
