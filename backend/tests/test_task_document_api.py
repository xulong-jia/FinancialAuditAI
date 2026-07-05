from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def make_docx(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return buffer.getvalue()


def make_xlsx(text: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData><row><c t="inlineStr"><is><t>{text}</t></is></c></row></sheetData></worksheet>'
            ),
        )
    return buffer.getvalue()


def create_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={
            "name": "Procurement walkthrough",
            "scenario": "procurement",
            "project_name": "Demo Project",
            "company_name": "Demo Co",
            "fiscal_year": 2026,
            "actor_name": "phase1",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_create_list_get_and_update_task() -> None:
    task = create_task()

    assert task["status"] == "draft"
    assert task["scenario"] == "procurement"
    assert task["actor_name"] == "phase1"
    assert task["owner_id"] is not None
    assert task["reviewer_id"] is None
    assert task["metadata"] == {}

    list_response = client.get("/api/v1/tasks")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/api/v1/tasks/{task['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == task["id"]

    patch_response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"name": "Updated procurement walkthrough"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Updated procurement walkthrough"


def test_task_run_contract_processes_and_surfaces_failed_documents() -> None:
    task = create_task()

    draft_run = client.post(f"/api/v1/tasks/{task['id']}/run")
    assert draft_run.status_code == 200
    assert draft_run.json()["status"] == "draft"
    assert draft_run.json()["next_action"] == "upload_documents"

    client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "purchase_contract", "actor_name": "phase1"},
        files={"file": ("contract.pdf", b"%PDF-1.4\nphase 1 test\n", "application/pdf")},
    )
    uploaded_run = client.post(f"/api/v1/tasks/{task['id']}/run")

    assert uploaded_run.status_code == 200
    assert uploaded_run.json()["status"] == "failed"
    assert uploaded_run.json()["next_action"] == "inspect_failed_documents"


def test_upload_document_records_hash_and_storage_path() -> None:
    task = create_task()
    content = b"%PDF-1.4\nphase 1 test\n"

    response = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "purchase_contract", "actor_name": "phase1"},
        files={"file": ("contract.pdf", content, "application/pdf")},
    )

    assert response.status_code == 200
    document = response.json()
    assert document["original_filename"] == "contract.pdf"
    assert document["file_ext"] == "pdf"
    assert document["file_size"] == len(content)
    assert document["file_hash"] == sha256(content).hexdigest()
    assert document["uploaded_by"] is not None
    assert document["metadata"] == {}
    assert document["doc_type"] == "purchase_contract"
    assert document["upload_status"] == "uploaded"
    assert document["ocr_status"] == "pending"
    project_root = Path(__file__).resolve().parents[2]
    assert (project_root / document["storage_path"]).exists()

    task_response = client.get(f"/api/v1/tasks/{task['id']}")
    assert task_response.json()["status"] == "uploaded"

    list_response = client.get(f"/api/v1/tasks/{task['id']}/documents")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    get_response = client.get(f"/api/v1/documents/{document['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["file_hash"] == document["file_hash"]


def test_delete_document_removes_record_and_writes_audit_log() -> None:
    task = create_task()
    response = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "purchase_contract", "actor_name": "phase1"},
        files={"file": ("contract.pdf", b"%PDF-1.4\nphase 6 delete\n", "application/pdf")},
    )
    assert response.status_code == 200
    document = response.json()

    delete_response = client.delete(f"/api/v1/documents/{document['id']}")

    assert delete_response.status_code == 200
    assert client.get(f"/api/v1/documents/{document['id']}").status_code == 404
    logs = client.get("/api/v1/audit-logs").json()
    assert any(log["action"] == "document_deleted" and log["target_id"] == document["id"] for log in logs)


def test_unsupported_file_type_is_rejected_without_document_record() -> None:
    task = create_task()

    response = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        files={"file": ("notes.txt", b"not allowed", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported file extension"

    list_response = client.get(f"/api/v1/tasks/{task['id']}/documents")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_docx_xlsx_uploads_are_supported_and_parseable() -> None:
    task = create_task()

    docx_response = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "purchase_contract"},
        files={
            "file": (
                "contract.docx",
                make_docx("DOCX contract text"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    xlsx_response = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        data={"doc_type_hint": "invoice"},
        files={
            "file": (
                "ledger.xlsx",
                make_xlsx("XLSX invoice text"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert docx_response.status_code == 200
    assert docx_response.json()["file_ext"] == "docx"
    assert xlsx_response.status_code == 200
    assert xlsx_response.json()["file_ext"] == "xlsx"

    for document, expected_text in ((docx_response.json(), "DOCX contract text"), (xlsx_response.json(), "XLSX invoice text")):
        ocr_response = client.post(f"/api/v1/documents/{document['id']}/ocr")
        assert ocr_response.status_code == 200
        assert ocr_response.json()["ocr_status"] == "completed"
        pages = client.get(f"/api/v1/documents/{document['id']}/pages").json()
        assert expected_text in pages[0]["raw_text"]
        assert pages[0]["image_path"]
