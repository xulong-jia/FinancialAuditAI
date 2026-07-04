from io import BytesIO
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

from app.db.session import SessionLocal
from app.models.control_table_row import ControlTableRow
from app.models.report import Report
from test_review_api import field_by_name
from test_rule_engine_api import build_scenario, client, run_audit

EXPECTED_SHEETS = [
    "Summary",
    "Procurement Control Table",
    "Exceptions",
    "Evidence Index",
    "Field Corrections",
    "Rule Definitions",
]


def workbook_sheet_names(data: bytes) -> list[str]:
    with ZipFile(BytesIO(data)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [sheet.attrib["name"] for sheet in workbook.findall(".//main:sheet", namespace)]


def worksheet_text(data: bytes, sheet_number: int) -> str:
    with ZipFile(BytesIO(data)) as archive:
        return archive.read(f"xl/worksheets/sheet{sheet_number}.xml").decode()


def prepare_report_data() -> tuple[dict, dict]:
    task, docs = build_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1200.0,),
        payment_amounts=(1200.0,),
    )
    run_audit(task["id"])
    field = field_by_name(docs["purchase_contract"][0]["id"], "supplier_name")
    response = client.patch(
        f"/api/v1/fields/{field.id}",
        json={
            "value_text": "Supplier Corrected Co",
            "value_normalized": {"value": "Supplier Corrected Co"},
            "confidence": 0.98,
            "actor_name": "report_reviewer",
            "comment": "Correct supplier for report export.",
        },
    )
    assert response.status_code == 200
    return task, docs


def test_control_table_report_generates_xlsx_with_required_sheets() -> None:
    task, _ = prepare_report_data()

    response = client.post(
        f"/api/v1/tasks/{task['id']}/reports/control-table",
        json={"generated_by": "reporter"},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["file_format"] == "xlsx"
    assert report["status"] == "completed"
    assert report["storage_path"].startswith("local_storage/reports/")
    assert report["summary"]["audit_result_count"] == 6
    assert report["summary"]["fail_count"] >= 1
    assert report["summary"]["usage_boundary"]

    with SessionLocal() as db:
        assert db.query(Report).filter(Report.id == UUID(report["id"])).one()
        rows = db.query(ControlTableRow).filter(ControlTableRow.task_id == UUID(task["id"])).all()
        assert rows
        assert rows[0].business_key
        assert rows[0].evidence_refs

    download = client.get(f"/api/v1/reports/{report['id']}/download")
    assert download.status_code == 200
    assert workbook_sheet_names(download.content) == EXPECTED_SHEETS


def test_report_xlsx_exports_exceptions_evidence_and_field_corrections() -> None:
    task, _ = prepare_report_data()
    report_response = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    report_id = report_response.json()["id"]

    download = client.get(f"/api/v1/reports/{report_id}/download")

    assert download.status_code == 200
    exceptions_xml = worksheet_text(download.content, 3)
    evidence_xml = worksheet_text(download.content, 4)
    corrections_xml = worksheet_text(download.content, 5)
    rules_xml = worksheet_text(download.content, 6)
    assert "PROC_AMOUNT_001" in exceptions_xml
    assert "refs" in exceptions_xml
    assert "supplier_name" in evidence_xml
    assert "Correct supplier for report export." in corrections_xml
    assert "Supplier Corrected Co" in corrections_xml
    assert "PROC_MISSING_001" in rules_xml


def test_report_history_api_lists_generated_reports() -> None:
    task, _ = prepare_report_data()
    first = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    assert first.status_code == 200

    response = client.get(f"/api/v1/tasks/{task['id']}/reports")

    assert response.status_code == 200
    reports = response.json()
    assert reports[0]["id"] == first.json()["id"]
    assert reports[0]["summary"]["control_table_preview"]
