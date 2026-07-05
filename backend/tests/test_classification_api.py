import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def make_pdf(page_texts: list[str]) -> bytes:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    return document.tobytes()


def create_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"name": "Classification task", "scenario": "procurement"},
    )
    assert response.status_code == 200
    return response.json()


def upload_pdf(task_id: str, filename: str, text: str) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        files={"file": (filename, make_pdf([text]), "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def ocr_document(document_id: str) -> dict:
    response = client.post(f"/api/v1/documents/{document_id}/ocr")
    assert response.status_code == 200
    assert response.json()["ocr_status"] == "completed"
    return response.json()


@pytest.mark.parametrize(
    ("doc_type", "filename", "text"),
    [
        (
            "purchase_request",
            "purchase_request.pdf",
            "Purchase Request request no applicant request department approval",
        ),
        (
            "purchase_contract",
            "purchase_contract.pdf",
            "Purchase Contract contract no supplier payment terms party a party b",
        ),
        (
            "warehouse_receipt",
            "warehouse_receipt.pdf",
            "Warehouse Receipt receipt date warehouse received quantity received by",
        ),
        (
            "invoice",
            "invoice.pdf",
            "Invoice invoice number total with tax tax amount issue date buyer seller",
        ),
        (
            "accounting_voucher",
            "accounting_voucher.pdf",
            "Accounting Voucher voucher no debit credit account title summary",
        ),
        (
            "payment_receipt",
            "payment_receipt.pdf",
            "Payment Receipt bank receipt payer payee transaction no payment",
        ),
    ],
)
def test_classifies_six_procurement_document_types(
    doc_type: str, filename: str, text: str
) -> None:
    task = create_task()
    document = upload_pdf(task["id"], filename, text)
    ocr_document(document["id"])

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_type"] == doc_type
    assert body["confidence"] >= 0.6
    assert body["classification_reason"]
    assert isinstance(body["alternative_types"], list)
    assert body["need_human_review"] is False

    document_response = client.get(f"/api/v1/documents/{document['id']}")
    assert document_response.status_code == 200
    provider = document_response.json()["metadata"]["classification_provider"]
    assert provider["provider_kind"] == "deterministic_fallback"
    assert provider["fallback_used"] == "deterministic"


@pytest.mark.parametrize(
    ("doc_type", "filename", "text"),
    [
        ("prospectus", "prospectus.pdf", "Prospectus offering memorandum securities offering issuer"),
        ("inquiry_letter", "inquiry_letter.pdf", "Regulatory inquiry letter comment letter feedback"),
        ("regulation", "regulation.pdf", "Accounting standard regulation guideline regulatory provision"),
    ],
)
def test_classifies_knowledge_document_labels(doc_type: str, filename: str, text: str) -> None:
    task = create_task()
    document = upload_pdf(task["id"], filename, text)
    ocr_document(document["id"])

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_type"] == doc_type
    assert body["confidence"] >= 0.6
    assert "deterministic-evidence-v2" in body["classification_reason"]


def test_low_confidence_document_is_unknown_and_needs_review() -> None:
    task = create_task()
    document = upload_pdf(task["id"], "notes.pdf", "general meeting notes without procurement markers")
    ocr_document(document["id"])

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_type"] == "unknown"
    assert body["confidence"] < 0.6
    assert body["need_human_review"] is True

    document_response = client.get(f"/api/v1/documents/{document['id']}")
    assert document_response.status_code == 200
    assert document_response.json()["review_status"] == "need_review"


def test_manual_doc_type_correction_preserves_original_classification() -> None:
    task = create_task()
    document = upload_pdf(
        task["id"],
        "invoice.pdf",
        "Invoice invoice number total with tax tax amount issue date buyer seller",
    )
    ocr_document(document["id"])
    classify_response = client.post(f"/api/v1/documents/{document['id']}/classify")
    assert classify_response.status_code == 200
    original_reason = classify_response.json()["classification_reason"]

    patch_response = client.patch(
        f"/api/v1/documents/{document['id']}",
        json={
            "doc_type": "payment_receipt",
            "actor_name": "reviewer",
            "manual_reason": "Reviewed against uploaded evidence",
        },
    )

    assert patch_response.status_code == 200
    body = patch_response.json()
    assert body["doc_type"] == "payment_receipt"
    assert body["classification_reason"] == original_reason
    assert body["original_classification"]["doc_type"] == "invoice"
    assert body["original_classification"]["classification_reason"] == original_reason


def test_unocr_document_cannot_be_classified() -> None:
    task = create_task()
    document = upload_pdf(task["id"], "invoice.pdf", "Invoice invoice number tax amount")

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 400
    assert response.json()["detail"] == "Document OCR must complete before classification"
