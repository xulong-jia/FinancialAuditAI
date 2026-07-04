from hashlib import sha256
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


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
