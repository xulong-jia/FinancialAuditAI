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


INTERVIEW_KEYWORDS = [
    ("interview_record", "Interview Record interview date interviewee key answers mentioned amounts"),
    ("interview_outline", "Interview Outline topics planned questions interviewer"),
    ("interview_signature_page", "Interview Signature Page signature detected interviewee"),
    ("interview_transcript", "Interview Transcript transcript summary key answers mentioned counterparties"),
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


def create_interview_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={
            "name": "Interview walkthrough",
            "scenario": "interview",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
        },
    )
    assert response.status_code == 200
    assert response.json()["scenario"] == "interview"
    assert response.json()["task_no"].startswith("INT-")
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


def build_interview_scenario() -> tuple[dict, dict[str, dict]]:
    task = create_interview_task()
    docs = {doc_type: upload_pdf(task["id"], doc_type) for doc_type in ("interview_record", "interview_signature_page")}

    record = docs["interview_record"]
    add_date(task["id"], record["id"], "interview_date", "2026-02-15")
    add_field(task["id"], record["id"], "interviewee_name", "Demo Manager")
    add_field(task["id"], record["id"], "interviewee_title", "Finance Manager")
    add_field(task["id"], record["id"], "company_name", "Known Counterparty Co")
    add_field(task["id"], record["id"], "interviewer", "Audit Staff")
    add_field(task["id"], record["id"], "topics", "Revenue and receivables")
    add_field(task["id"], record["id"], "key_answers", "Management described an unusual 1500 receivable.")
    add_money(task["id"], record["id"], "mentioned_amounts", 1500.0)
    add_field(task["id"], record["id"], "mentioned_counterparties", "Unexpected Co", field_type="name")
    add_money(task["id"], record["id"], "book_amount", 1000.0, is_required=False)

    signature = docs["interview_signature_page"]
    add_field(task["id"], signature["id"], "interviewee_name", "Demo Manager")
    add_field(task["id"], signature["id"], "signature_detected", "no", field_type="status")
    return task, docs


@pytest.mark.parametrize(("doc_type", "text"), INTERVIEW_KEYWORDS)
def test_classifies_interview_document_types(doc_type: str, text: str) -> None:
    task = create_interview_task()
    document = upload_pdf(task["id"], doc_type, text)
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    assert response.json()["doc_type"] == doc_type
    assert response.json()["confidence"] >= 0.6


def test_extracts_interview_record_fields_with_source_evidence() -> None:
    task = create_interview_task()
    document = upload_pdf(
        task["id"],
        "interview_record",
        "\n".join(
            [
                "Interview Date: 2026-01-20",
                "Interviewee Name: Demo Manager",
                "Interviewee Title: Finance Manager",
                "Company Name: Demo Client Co",
                "Interviewer: Audit Staff",
                "Topics: Revenue and receivables",
                "Key Answers: Management described a receivable balance.",
                "Mentioned Amounts: CNY 1500.00",
                "Mentioned Counterparties: Demo Customer Co",
            ]
        ),
    )
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/extract")

    assert response.status_code == 200
    fields = {field["field_name"]: field for field in response.json()}
    assert fields["interviewee_name"]["value_text"] == "Demo Manager"
    assert fields["key_answers"]["source_text"].startswith("Key Answers:")
    assert fields["mentioned_amounts"]["value_normalized"]["amount"] == 1500.0
    assert fields["mentioned_counterparties"]["value_text"] == "Demo Customer Co"


def test_interview_rules_enter_review_and_export_report() -> None:
    task, _ = build_interview_scenario()

    link_response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")
    assert link_response.status_code == 200
    assert link_response.json()["linked_document_count"] == 2

    audit_response = client.post(f"/api/v1/tasks/{task['id']}/audit")
    assert audit_response.status_code == 200
    results = {result["rule_code"]: result for result in audit_response.json()}
    assert results["INTERVIEW_DATE_001"]["status"] == "warning"
    assert results["INTERVIEW_SIGNATURE_001"]["status"] == "need_review"
    assert results["INTERVIEW_AMOUNT_001"]["status"] in {"warning", "need_review"}
    assert results["INTERVIEW_COUNTERPARTY_001"]["status"] in {"warning", "need_review"}
    assert results["INTERVIEW_AMOUNT_001"]["evidence"]["refs"]

    queue_response = client.get(f"/api/v1/review/queue?task_id={task['id']}")
    assert queue_response.status_code == 200
    assert any(item["audit_result"]["rule_code"] == "INTERVIEW_SIGNATURE_001" for item in queue_response.json())

    report_response = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["report_type"] == "interview_evidence_report"
    assert report["summary"]["control_table_preview"][0]["interviewee_name"] == "Demo Manager"

    with SessionLocal() as db:
        rows = db.query(ControlTableRow).filter(ControlTableRow.task_id == UUID(task["id"])).all()
        assert rows
        assert rows[0].scenario == "interview"

    download = client.get(f"/api/v1/reports/{report['id']}/download")
    assert download.status_code == 200
    assert "Interview Evidence" in workbook_sheet_names(download.content)
