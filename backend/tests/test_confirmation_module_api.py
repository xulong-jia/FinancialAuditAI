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
from app.models.extracted_field import ExtractedField


client = TestClient(app)


CONFIRMATION_KEYWORDS = [
    ("confirmation", "Confirmation confirmation no counterparty book amount confirmed amount reply"),
    ("confirmation_request", "Confirmation Request confirmation no sent date counterparty book amount"),
    ("confirmation_reply", "Confirmation Reply confirmation no replied date confirmed amount seal signatory"),
    ("confirmation_adjustment", "Confirmation Adjustment confirmation no difference amount exception reason"),
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


def create_confirmation_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"name": "Confirmation walkthrough", "scenario": "confirmation"},
    )
    assert response.status_code == 200
    assert response.json()["scenario"] == "confirmation"
    assert response.json()["task_no"].startswith("CONF-")
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


def add_money(task_id: str, document_id: str, field_name: str, amount: float) -> None:
    add_field(
        task_id,
        document_id,
        field_name,
        str(amount),
        normalized={"amount": amount, "currency": "CNY"},
        field_type="money",
    )


def build_confirmation_scenario(
    *,
    replied_date: str = "2026-01-20",
    confirmed_amount: float = 950.0,
    include_adjustment: bool = False,
) -> tuple[dict, dict[str, dict]]:
    task = create_confirmation_task()
    docs = {doc_type: upload_pdf(task["id"], doc_type) for doc_type in ("confirmation_request", "confirmation_reply")}
    if include_adjustment:
        docs["confirmation_adjustment"] = upload_pdf(task["id"], "confirmation_adjustment")

    request = docs["confirmation_request"]
    add_field(task["id"], request["id"], "confirmation_no", "CF-001")
    add_field(task["id"], request["id"], "counterparty_name", "Counterparty Co")
    add_field(task["id"], request["id"], "counterparty_address", "1 Demo Road", is_required=False)
    add_date(task["id"], request["id"], "sent_date", "2026-01-10")
    add_money(task["id"], request["id"], "book_amount", 1000.0)

    reply = docs["confirmation_reply"]
    add_field(task["id"], reply["id"], "confirmation_no", "CF-001")
    add_field(task["id"], reply["id"], "counterparty_name", "Counterparty Co")
    add_date(task["id"], reply["id"], "replied_date", replied_date)
    add_money(task["id"], reply["id"], "confirmed_amount", confirmed_amount)
    add_field(task["id"], reply["id"], "seal_detected", "yes", is_required=False)
    add_field(task["id"], reply["id"], "signatory", "Demo Signer", is_required=False)

    if include_adjustment:
        adjustment = docs["confirmation_adjustment"]
        add_field(task["id"], adjustment["id"], "confirmation_no", "CF-001")
        add_money(task["id"], adjustment["id"], "difference_amount", 50.0)
        add_field(task["id"], adjustment["id"], "exception_reason", "Timing difference")
        add_field(task["id"], adjustment["id"], "adjustment_items", "Timing difference 50.00", is_required=False)
    return task, docs


@pytest.mark.parametrize(("doc_type", "text"), CONFIRMATION_KEYWORDS)
def test_classifies_confirmation_document_types(doc_type: str, text: str) -> None:
    task = create_confirmation_task()
    document = upload_pdf(task["id"], doc_type, text)
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    assert response.json()["doc_type"] == doc_type
    assert response.json()["confidence"] >= 0.6


def test_extracts_confirmation_reply_schema_fields() -> None:
    task = create_confirmation_task()
    document = upload_pdf(
        task["id"],
        "confirmation_reply",
        "\n".join(
            [
                "Confirmation No: CF-001",
                "Counterparty Name: Counterparty Co",
                "Replied Date: 2026-01-20",
                "Confirmed Amount: CNY 950.00",
                "Seal Detected: yes",
                "Signatory: Demo Signer",
            ]
        ),
    )
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/extract")

    assert response.status_code == 200
    fields = {field["field_name"]: field for field in response.json()}
    assert fields["confirmation_no"]["value_text"] == "CF-001"
    assert fields["confirmed_amount"]["value_normalized"]["amount"] == 950.0
    assert fields["seal_detected"]["value_text"] == "yes"


def test_confirmation_date_inversion_and_missing_adjustment_enter_review_and_report() -> None:
    task, _ = build_confirmation_scenario(replied_date="2026-01-05", confirmed_amount=950.0)

    link_response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")
    assert link_response.status_code == 200
    assert link_response.json()["linked_document_count"] == 2

    audit_response = client.post(f"/api/v1/tasks/{task['id']}/audit")
    assert audit_response.status_code == 200
    results = {result["rule_code"]: result for result in audit_response.json()}
    assert results["CONF_DATE_001"]["status"] == "fail"
    assert results["CONF_AMOUNT_001"]["status"] == "need_review"
    assert results["CONF_AMOUNT_001"]["evidence"]["refs"]

    queue_response = client.get(f"/api/v1/review/queue?task_id={task['id']}")
    assert queue_response.status_code == 200
    assert any(item["audit_result"]["rule_code"] == "CONF_AMOUNT_001" for item in queue_response.json())

    report_response = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["report_type"] == "confirmation_exception_report"
    assert report["summary"]["control_table_preview"][0]["confirmation_no"] == "CF-001"

    with SessionLocal() as db:
        rows = db.query(ControlTableRow).filter(ControlTableRow.task_id == UUID(task["id"])).all()
        assert rows
        assert rows[0].scenario == "confirmation"

    download = client.get(f"/api/v1/reports/{report['id']}/download")
    assert download.status_code == 200
    assert "Confirmation Results" in workbook_sheet_names(download.content)


def test_confirmation_amount_difference_with_adjustment_passes_or_warns() -> None:
    task, _ = build_confirmation_scenario(confirmed_amount=950.0, include_adjustment=True)
    assert client.post(f"/api/v1/tasks/{task['id']}/link-documents").status_code == 200

    response = client.post(f"/api/v1/tasks/{task['id']}/audit")

    assert response.status_code == 200
    results = {result["rule_code"]: result for result in response.json()}
    assert results["CONF_AMOUNT_001"]["status"] in {"pass", "warning"}


def test_confirmation_name_checks_book_counterparty_evidence() -> None:
    task, docs = build_confirmation_scenario(confirmed_amount=1000.0)
    add_field(task["id"], docs["confirmation_request"]["id"], "customer_name", "Different Customer Co", is_required=False)
    assert client.post(f"/api/v1/tasks/{task['id']}/link-documents").status_code == 200

    response = client.post(f"/api/v1/tasks/{task['id']}/audit")

    assert response.status_code == 200
    results = {result["rule_code"]: result for result in response.json()}
    assert results["CONF_NAME_001"]["status"] == "warning"
    assert "Different Customer Co" in results["CONF_NAME_001"]["actual_value"]["names"]
