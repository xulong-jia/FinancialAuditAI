from io import BytesIO
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

import fitz
import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.control_table_row import ControlTableRow
from app.models.document import Document
from app.models.extracted_field import ExtractedField


client = TestClient(app)


CONTRACT_KEYWORDS = [
    ("contract_review", "Contract Review contract no payment terms delivery terms special clauses"),
    ("material_contract", "Material Contract contract no party a party b amount including tax"),
    ("supplemental_agreement", "Supplemental Agreement contract no price adjustment related party"),
    ("framework_agreement", "Framework Agreement auto renewal exclusivity payment terms"),
    ("contract_attachment", "Contract Attachment attachment list contract no"),
]


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def workbook_sheet_names(data: bytes) -> list[str]:
    with ZipFile(BytesIO(data)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [sheet.attrib["name"] for sheet in workbook.findall(".//main:sheet", namespace)]


def create_contract_review_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={
            "name": "Contract review",
            "scenario": "contract_review",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )
    assert response.status_code == 200
    assert response.json()["scenario"] == "contract_review"
    assert response.json()["task_no"].startswith("CONTRACT-")
    return response.json()


def upload_pdf(task_id: str, doc_type: str, text: str | None = None) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        data={"doc_type_hint": doc_type},
        files={"file": (f"{doc_type}.pdf", make_pdf(text or doc_type), "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def add_field(
    task_id: str,
    document_id: str,
    field_name: str,
    value: str | None,
    *,
    normalized: dict | None = None,
    field_type: str = "text",
    is_required: bool = True,
    warnings: list[str] | None = None,
) -> None:
    with SessionLocal() as db:
        db.add(
            ExtractedField(
                task_id=UUID(task_id),
                document_id=UUID(document_id),
                field_name=field_name,
                field_label=field_name.replace("_", " ").title(),
                field_type=field_type,
                value_text=value,
                value_normalized=normalized if normalized is not None else ({"value": value} if value else None),
                unit=None,
                currency=normalized.get("currency") if normalized else None,
                confidence=0.85 if value else 0.0,
                source_page=1 if value else None,
                source_text=f"{field_name}: {value}" if value else None,
                source_bbox=None,
                extraction_method="test",
                is_required=is_required,
                is_verified=False,
                corrected_by=None,
                corrected_at=None,
                warnings=warnings or [],
            )
        )
        db.commit()


def add_date(task_id: str, document_id: str, field_name: str, value: str) -> None:
    add_field(task_id, document_id, field_name, value, normalized={"value": value}, field_type="date")


def add_money(task_id: str, document_id: str, field_name: str, amount: float, *, is_required: bool = True) -> None:
    add_field(
        task_id,
        document_id,
        field_name,
        str(amount),
        normalized={"amount": amount, "currency": "CNY"},
        field_type="money",
        is_required=is_required,
    )


def add_items(task_id: str, document_id: str, quantity: float) -> None:
    add_field(
        task_id,
        document_id,
        "item_lines",
        f"Item: Demo goods; Quantity: {quantity}; Unit: pcs",
        normalized={"items": [{"item_name": "Demo goods", "quantity": quantity, "unit": "pcs"}]},
        field_type="line_items",
        is_required=False,
    )


def build_contract_review_scenario() -> tuple[dict, dict[str, dict]]:
    task = create_contract_review_task()
    docs = {doc_type: upload_pdf(task["id"], doc_type) for doc_type in ("contract_review", "contract_attachment")}

    contract = docs["contract_review"]
    add_field(task["id"], contract["id"], "contract_no", "CR-001")
    add_field(task["id"], contract["id"], "contract_name", "Major Supply Agreement")
    add_date(task["id"], contract["id"], "signing_date", "2025-01-01")
    add_date(task["id"], contract["id"], "effective_date", "2025-01-01", )
    add_date(task["id"], contract["id"], "expiry_date", "2025-12-31")
    add_field(task["id"], contract["id"], "party_a", "Demo Buyer Co")
    add_field(task["id"], contract["id"], "party_b", "Demo Supplier Co")
    add_field(task["id"], contract["id"], "counterparty_name", "Demo Supplier Co")
    add_money(task["id"], contract["id"], "amount_including_tax", 1000.0)
    add_field(task["id"], contract["id"], "payment_terms", "Pay in 30 days")
    add_field(task["id"], contract["id"], "delivery_terms", "Deliver to warehouse")
    add_field(task["id"], contract["id"], "breach_terms", "Penalty applies")
    add_field(task["id"], contract["id"], "dispute_resolution", "Arbitration")
    add_field(task["id"], contract["id"], "auto_renewal_clause", "Automatically renews for one year", is_required=False)
    add_field(task["id"], contract["id"], "price_adjustment_clause", "Price may adjust quarterly", is_required=False)
    add_field(task["id"], contract["id"], "minimum_guarantee_clause", "Minimum purchase guarantee applies", is_required=False)
    add_field(task["id"], contract["id"], "signature_detected", "no", field_type="status", is_required=False)
    add_field(task["id"], contract["id"], "seal_detected", "no", field_type="status", is_required=False)
    add_money(task["id"], contract["id"], "invoice_amount", 1300.0, is_required=False)
    add_field(task["id"], contract["id"], "supplier_name", "Unexpected Supplier Co", field_type="name", is_required=False)

    attachment = docs["contract_attachment"]
    add_field(task["id"], attachment["id"], "contract_no", "CR-001")
    add_field(task["id"], attachment["id"], "attachment_list", "Technical specs", is_required=False)
    return task, docs


@pytest.mark.parametrize(("doc_type", "text"), CONTRACT_KEYWORDS)
def test_classifies_contract_review_document_types(doc_type: str, text: str) -> None:
    task = create_contract_review_task()
    document = upload_pdf(task["id"], doc_type, text)
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    assert response.json()["doc_type"] == doc_type
    assert response.json()["confidence"] >= 0.6


def test_extracts_contract_review_fields_and_clause_evidence() -> None:
    task = create_contract_review_task()
    document = upload_pdf(
        task["id"],
        "contract_review",
        "\n".join(
            [
                "Contract No: CR-001",
                "Contract Name: Major Supply Agreement",
                "Signing Date: 2026-01-10",
                "Effective Date: 2026-01-15",
                "Expiry Date: 2026-12-31",
                "Party A: Demo Buyer Co",
                "Party B: Demo Supplier Co",
                "Counterparty Name: Demo Supplier Co",
                "Amount Including Tax: CNY 1000.00",
                "Payment Terms: Pay in 30 days",
                "Delivery Terms: Deliver to warehouse",
                "Acceptance Terms: Acceptance after inspection",
                "Breach Terms: Penalty applies",
                "Dispute Resolution: Arbitration",
                "Auto Renewal Clause: Automatically renews for one year",
                "Minimum Guarantee Clause: Minimum purchase guarantee applies",
                "Signature Detected: yes",
                "Seal Detected: yes",
            ]
        ),
    )
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/extract")

    assert response.status_code == 200
    fields = {field["field_name"]: field for field in response.json()}
    assert fields["contract_no"]["value_text"] == "CR-001"
    assert fields["amount_including_tax"]["value_normalized"]["amount"] == 1000.0
    assert fields["payment_terms"]["source_text"].startswith("Payment Terms:")
    assert fields["auto_renewal_clause"]["value_text"] == "Automatically renews for one year"
    assert fields["minimum_guarantee_clause"]["value_text"] == "Minimum purchase guarantee applies"


def test_contract_review_rules_enter_review_and_export_report() -> None:
    task, _ = build_contract_review_scenario()

    link_response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")
    assert link_response.status_code == 200
    assert link_response.json()["linked_document_count"] == 2

    audit_response = client.post(f"/api/v1/tasks/{task['id']}/audit")
    assert audit_response.status_code == 200
    results = {result["rule_code"]: result for result in audit_response.json()}
    assert results["CONTRACT_KEY_TERMS_001"]["status"] == "need_review"
    assert results["CONTRACT_SPECIAL_CLAUSE_001"]["status"] == "warning"
    assert results["CONTRACT_AMOUNT_001"]["status"] in {"warning", "need_review"}
    assert results["CONTRACT_COUNTERPARTY_001"]["status"] in {"warning", "need_review"}
    assert results["CONTRACT_SIGNATURE_SEAL_001"]["status"] == "need_review"
    assert results["CONTRACT_SPECIAL_CLAUSE_001"]["evidence"]["refs"]
    assert any(
        item["field_name"] == "minimum_guarantee_clause"
        for item in results["CONTRACT_SPECIAL_CLAUSE_001"]["actual_value"]["special_clauses"]
    )

    queue_response = client.get(f"/api/v1/review/queue?task_id={task['id']}")
    assert queue_response.status_code == 200
    assert any(item["audit_result"]["rule_code"] == "CONTRACT_KEY_TERMS_001" for item in queue_response.json())

    report_response = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["report_type"] == "contract_review_report"
    assert report["summary"]["control_table_preview"][0]["contract_no"] == "CR-001"

    with SessionLocal() as db:
        rows = db.query(ControlTableRow).filter(ControlTableRow.task_id == UUID(task["id"])).all()
        assert rows
        assert rows[0].scenario == "contract_review"

    download = client.get(f"/api/v1/reports/{report['id']}/download")
    assert download.status_code == 200
    sheet_names = workbook_sheet_names(download.content)
    assert "Contract Review" in sheet_names
    assert "Special Clauses" in sheet_names


def test_contract_amount_rule_compares_available_item_quantities() -> None:
    task = create_contract_review_task()
    contract = upload_pdf(task["id"], "contract_review")
    invoice = upload_pdf(task["id"], "contract_attachment")
    with SessionLocal() as db:
        db_document = db.get(Document, UUID(invoice["id"]))
        assert db_document is not None
        db_document.doc_type = "invoice"
        db.commit()
    add_field(task["id"], contract["id"], "contract_no", "CR-QTY")
    add_field(task["id"], contract["id"], "contract_name", "Quantity Contract")
    add_date(task["id"], contract["id"], "signing_date", "2026-01-01")
    add_date(task["id"], contract["id"], "effective_date", "2026-01-01")
    add_date(task["id"], contract["id"], "expiry_date", "2026-12-31")
    add_field(task["id"], contract["id"], "party_a", "Demo Buyer Co")
    add_field(task["id"], contract["id"], "party_b", "Demo Supplier Co")
    add_field(task["id"], contract["id"], "counterparty_name", "Demo Supplier Co")
    add_money(task["id"], contract["id"], "amount_including_tax", 1000.0)
    add_items(task["id"], contract["id"], 10.0)
    add_field(task["id"], invoice["id"], "related_contract_no", "CR-QTY", is_required=False)
    add_money(task["id"], invoice["id"], "invoice_amount", 1000.0, is_required=False)
    add_items(task["id"], invoice["id"], 8.0)
    assert client.post(f"/api/v1/tasks/{task['id']}/link-documents").status_code == 200

    response = client.post(f"/api/v1/tasks/{task['id']}/audit")

    assert response.status_code == 200
    results = {result["rule_code"]: result for result in response.json()}
    assert results["CONTRACT_AMOUNT_001"]["status"] == "warning"
    assert results["CONTRACT_AMOUNT_001"]["actual_value"]["quantity_failures"]["demogoods"]["contract_quantity"] == 10.0
