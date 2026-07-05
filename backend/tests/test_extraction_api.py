import fitz
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.extraction import ExtractedFieldValue, validate_document_extraction
from app.services.extraction_service import (
    SCHEMA_SPECS,
    ExtractionProviderError,
    parse_llm_json_output,
)


client = TestClient(app)


EXPECTED_SCHEMA_FIELDS = {
    "purchase_request": [
        "request_no",
        "request_date",
        "applicant_dept",
        "requester_name",
        "approval_date",
        "approval_status",
        "approver_name",
        "supplier_candidate",
        "item_lines",
        "total_estimated_amount",
        "budget_code",
    ],
    "purchase_contract": [
        "contract_no",
        "signing_date",
        "effective_date",
        "expiry_date",
        "buyer_name",
        "supplier_name",
        "supplier_tax_no",
        "item_lines",
        "amount_excluding_tax",
        "tax_amount",
        "amount_including_tax",
        "tax_rate",
        "payment_terms",
        "delivery_terms",
        "seal_detected",
        "signature_detected",
    ],
    "warehouse_receipt": [
        "receipt_no",
        "receipt_date",
        "supplier_name",
        "warehouse_name",
        "receiver_name",
        "quality_status",
        "item_lines",
        "related_contract_no",
    ],
    "invoice": [
        "invoice_no",
        "invoice_code",
        "invoice_date",
        "invoice_type",
        "seller_name",
        "seller_tax_no",
        "buyer_name",
        "buyer_tax_no",
        "item_lines",
        "amount_excluding_tax",
        "tax_amount",
        "amount_including_tax",
        "tax_rate",
        "checksum",
    ],
    "accounting_voucher": [
        "voucher_no",
        "voucher_date",
        "summary",
        "debit_subject",
        "credit_subject",
        "amount",
        "supplier_name",
        "related_invoice_no",
        "preparer_name",
        "reviewer_name",
        "attachment_count",
    ],
    "payment_receipt": [
        "payment_no",
        "payment_date",
        "payer_name",
        "payee_name",
        "payee_account_masked",
        "bank_name",
        "bank_serial_no",
        "amount",
        "currency",
        "payment_purpose",
        "related_contract_no",
    ],
}


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def create_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"name": "Extraction task", "scenario": "procurement"},
    )
    assert response.status_code == 200
    return response.json()


def upload_pdf(task_id: str, text: str, doc_type_hint: str | None = None) -> dict:
    data = {"doc_type_hint": doc_type_hint} if doc_type_hint else None
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        data=data,
        files={"file": ("invoice.pdf", make_pdf(text), "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def run_ocr(document_id: str) -> None:
    response = client.post(f"/api/v1/documents/{document_id}/ocr")
    assert response.status_code == 200
    assert response.json()["ocr_status"] == "completed"


def fields_by_name(fields: list[dict]) -> dict[str, dict]:
    return {field["field_name"]: field for field in fields}


def test_six_procurement_extraction_schemas_are_defined() -> None:
    assert set(SCHEMA_SPECS) == set(EXPECTED_SCHEMA_FIELDS)
    for doc_type, expected_fields in EXPECTED_SCHEMA_FIELDS.items():
        assert [field.field_name for field in SCHEMA_SPECS[doc_type]] == expected_fields


def test_pydantic_schema_validation_requires_document_fields() -> None:
    invoice_no = ExtractedFieldValue(
        field_name="invoice_no",
        field_label="Invoice No",
        field_type="text",
        value_text="INV-001",
        value_normalized={"value": "INV-001"},
        confidence=0.8,
        source_page=1,
        source_text="Invoice No: INV-001",
        warnings=[],
    )

    with pytest.raises(ValidationError):
        validate_document_extraction("invoice", [invoice_no])


def test_extract_api_normalizes_dates_amounts_and_line_items() -> None:
    task = create_task()
    document = upload_pdf(
        task["id"],
        "\n".join(
            [
                "Invoice No: INV-001",
                "Invoice Date: 2026/07/04",
                "Seller Name: Supplier Pty Ltd",
                "Buyer Name: Demo Co",
                "Item: Audit Service; Quantity: 2; Unit: pcs; Unit Price: 500.00; Amount: 1000.00",
                "Amount Excluding Tax: 1,000.00",
                "Tax Amount: 100.00",
                "Amount Including Tax: CNY 1,100.00",
            ]
        ),
        "invoice",
    )
    run_ocr(document["id"])

    response = client.post(f"/api/v1/documents/{document['id']}/extract")

    assert response.status_code == 200
    fields = fields_by_name(response.json())
    assert fields["invoice_date"]["value_normalized"] == {"value": "2026-07-04"}
    assert fields["amount_including_tax"]["value_normalized"] == {
        "amount": 1100.0,
        "currency": "CNY",
    }
    assert fields["item_lines"]["value_normalized"]["items"][0]["item_name"] == "Audit Service"
    assert fields["item_lines"]["value_normalized"]["items"][0]["quantity"] == 2.0
    assert fields["item_lines"]["source_bbox"]
    assert fields["item_lines"]["value_normalized"]["items"][0]["source_page"] == 1
    assert fields["item_lines"]["value_normalized"]["items"][0]["source_bbox"]
    assert fields["item_lines"]["value_normalized"]["items"][0]["source_text"].startswith("Item:")
    assert fields["invoice_no"]["source_page"] == 1
    assert fields["invoice_no"]["source_text"] == "Invoice No: INV-001"
    assert fields["invoice_no"]["source_bbox"]
    assert fields["invoice_no"]["extraction_method"] == "regex_fallback"

    document_response = client.get(f"/api/v1/documents/{document['id']}")
    assert document_response.json()["extraction_status"] == "completed"
    assert document_response.json()["metadata"]["extraction_provider"]["provider_kind"] == "deterministic_fallback"


def test_missing_required_field_outputs_null_and_warning() -> None:
    task = create_task()
    document = upload_pdf(
        task["id"],
        "\n".join(
            [
                "Invoice No: INV-002",
                "Invoice Date: 2026-07-04",
                "Seller Name: Supplier Pty Ltd",
                "Buyer Name: Demo Co",
                "Item: Audit Service; Quantity: 1; Unit: pcs; Amount: 1000.00",
                "Amount Excluding Tax: 1000.00",
                "Amount Including Tax: 1000.00",
            ]
        ),
        "invoice",
    )
    run_ocr(document["id"])

    fields = fields_by_name(client.post(f"/api/v1/documents/{document['id']}/extract").json())

    assert fields["tax_amount"]["value_text"] is None
    assert fields["tax_amount"]["value_normalized"] is None
    assert fields["tax_amount"]["warnings"] == ["required_field_missing"]


def test_fields_api_lists_document_and_task_fields() -> None:
    task = create_task()
    document = upload_pdf(
        task["id"],
        "Invoice No: INV-003\nInvoice Date: 2026-07-04\nSeller Name: Supplier\nBuyer Name: Buyer\n"
        "Item: Service; Quantity: 1; Unit: pcs; Amount: 100.00\n"
        "Amount Excluding Tax: 90.00\nTax Amount: 10.00\nAmount Including Tax: 100.00",
        "invoice",
    )
    run_ocr(document["id"])
    extract_response = client.post(f"/api/v1/documents/{document['id']}/extract")
    assert extract_response.status_code == 200

    document_fields = client.get(f"/api/v1/documents/{document['id']}/fields")
    task_fields = client.get(f"/api/v1/tasks/{task['id']}/fields")

    assert document_fields.status_code == 200
    assert task_fields.status_code == 200
    assert len(document_fields.json()) == len(EXPECTED_SCHEMA_FIELDS["invoice"])
    assert len(task_fields.json()) == len(EXPECTED_SCHEMA_FIELDS["invoice"])


def test_unclassified_document_cannot_be_extracted() -> None:
    task = create_task()
    document = upload_pdf(task["id"], "Invoice No: INV-004")
    run_ocr(document["id"])

    response = client.post(f"/api/v1/documents/{document['id']}/extract")

    assert response.status_code == 400
    assert response.json()["detail"] == "Document must be classified before extraction"


def test_invalid_llm_json_is_reported() -> None:
    with pytest.raises(ExtractionProviderError):
        parse_llm_json_output("{not valid json")
