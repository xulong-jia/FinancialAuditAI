from uuid import UUID

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.extracted_field import ExtractedField


client = TestClient(app)


def create_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"name": "Linkage task", "scenario": "procurement"},
    )
    assert response.status_code == 200
    return response.json()


def upload_document(task_id: str, filename: str, doc_type: str) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        data={"doc_type_hint": doc_type},
        files={"file": (filename, b"%PDF-1.4\nlinkage test\n", "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def add_field(
    task_id: str,
    document_id: str,
    field_name: str,
    value: str,
    normalized: dict | None = None,
) -> None:
    with SessionLocal() as db:
        db.add(
            ExtractedField(
                task_id=UUID(task_id),
                document_id=UUID(document_id),
                field_name=field_name,
                field_label=field_name.replace("_", " ").title(),
                field_type="money" if normalized and "amount" in normalized else "text",
                value_text=value,
                value_normalized=normalized or {"value": value},
                confidence=0.85,
                source_page=1,
                source_text=f"{field_name}: {value}",
                source_bbox=None,
                extraction_method="test",
                is_required=True,
                is_verified=False,
                corrected_by=None,
                corrected_at=None,
                warnings=[],
            )
        )
        db.commit()


def test_contract_number_groups_documents_and_writes_relations() -> None:
    task = create_task()
    contract = upload_document(task["id"], "contract.pdf", "purchase_contract")
    receipt = upload_document(task["id"], "receipt.pdf", "warehouse_receipt")
    add_field(task["id"], contract["id"], "contract_no", "C-001")
    add_field(task["id"], receipt["id"], "related_contract_no", "C-001")

    response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")

    assert response.status_code == 200
    body = response.json()
    assert body["warnings"] == []
    assert body["relation_count"] == 1
    assert body["relations"][0]["business_key"] == "CONTRACT-C-001"
    assert body["relations"][0]["relation_type"] == "same_contract"
    assert body["relations"][0]["evidence"]["matched_fields"]

    contract_after = client.get(f"/api/v1/documents/{contract['id']}").json()
    receipt_after = client.get(f"/api/v1/documents/{receipt['id']}").json()
    assert contract_after["business_key"] == "CONTRACT-C-001"
    assert receipt_after["business_key"] == "CONTRACT-C-001"


def test_invoice_number_and_payment_purpose_group_documents() -> None:
    task = create_task()
    invoice = upload_document(task["id"], "invoice.pdf", "invoice")
    voucher = upload_document(task["id"], "voucher.pdf", "accounting_voucher")
    payment = upload_document(task["id"], "payment.pdf", "payment_receipt")
    add_field(task["id"], invoice["id"], "invoice_no", "INV-009")
    add_field(task["id"], voucher["id"], "related_invoice_no", "INV-009")
    add_field(task["id"], payment["id"], "payment_purpose", "Settlement for invoice INV-009")

    response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")

    assert response.status_code == 200
    body = response.json()
    assert body["relation_count"] == 2
    assert {relation["business_key"] for relation in body["relations"]} == {"INVOICE-INV-009"}
    assert any(
        evidence["field_name"] == "payment_purpose"
        for relation in body["relations"]
        for evidence in relation["evidence"]["matched_fields"]
    )


def test_low_confidence_supplier_amount_match_needs_review() -> None:
    task = create_task()
    contract = upload_document(task["id"], "contract.pdf", "purchase_contract")
    invoice = upload_document(task["id"], "invoice.pdf", "invoice")
    add_field(task["id"], contract["id"], "supplier_name", "Acme Pty Ltd")
    add_field(task["id"], contract["id"], "signing_date", "2026-07-04")
    add_field(
        task["id"],
        contract["id"],
        "amount_including_tax",
        "1000.00",
        {"amount": 1000.0, "currency": "CNY"},
    )
    add_field(task["id"], invoice["id"], "seller_name", "Acme Pty Ltd")
    add_field(task["id"], invoice["id"], "invoice_date", "2026-07-04")
    add_field(
        task["id"],
        invoice["id"],
        "amount_including_tax",
        "CNY 1000.00",
        {"amount": 1000.0, "currency": "CNY"},
    )

    response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")

    assert response.status_code == 200
    body = response.json()
    assert body["relation_count"] == 1
    assert body["relations"][0]["confidence"] < 0.6
    assert body["relations"][0]["relation_type"] == "possible_same_purchase"
    assert body["relations"][0]["business_key"].startswith(f"TASK-{task['id']}-GROUP-")
    assert any(
        evidence["method"] == "fallback_date"
        for evidence in body["relations"][0]["evidence"]["matched_fields"]
    )
    assert any(warning.startswith("low_confidence:") for warning in body["warnings"])
    assert client.get(f"/api/v1/documents/{contract['id']}").json()["review_status"] == "need_review"
    assert client.get(f"/api/v1/documents/{invoice['id']}").json()["review_status"] == "need_review"


def test_one_contract_can_group_multiple_payments() -> None:
    task = create_task()
    contract = upload_document(task["id"], "contract.pdf", "purchase_contract")
    first_payment = upload_document(task["id"], "payment-1.pdf", "payment_receipt")
    second_payment = upload_document(task["id"], "payment-2.pdf", "payment_receipt")
    add_field(task["id"], contract["id"], "contract_no", "C-200")
    add_field(task["id"], first_payment["id"], "related_contract_no", "C-200")
    add_field(task["id"], second_payment["id"], "related_contract_no", "C-200")

    response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")
    relations_response = client.get(f"/api/v1/tasks/{task['id']}/document-relations")

    assert response.status_code == 200
    assert response.json()["relation_count"] == 2
    assert relations_response.status_code == 200
    assert len(relations_response.json()) == 2
    assert {relation["business_key"] for relation in relations_response.json()} == {"CONTRACT-C-200"}


def test_task_without_enough_fields_returns_warning() -> None:
    task = create_task()
    upload_document(task["id"], "contract.pdf", "purchase_contract")

    response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")

    assert response.status_code == 200
    body = response.json()
    assert body["relation_count"] == 0
    assert body["linked_document_count"] == 0
    assert body["warnings"] == ["no_extracted_fields"]
