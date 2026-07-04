from pathlib import Path

import fitz
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
        json={"name": "OCR task", "scenario": "procurement"},
    )
    assert response.status_code == 200
    return response.json()


def upload_file(task_id: str, name: str, content: bytes, content_type: str) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        files={"file": (name, content, content_type)},
    )
    assert response.status_code == 200
    return response.json()


def test_pdf_ocr_extracts_pages_in_order() -> None:
    task = create_task()
    uploaded = upload_file(
        task["id"],
        "contract.pdf",
        make_pdf(["first page text", "second page text"]),
        "application/pdf",
    )

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")
    assert ocr_response.status_code == 200
    assert ocr_response.json()["ocr_status"] == "completed"
    assert ocr_response.json()["page_count"] == 2

    pages_response = client.get(f"/api/v1/documents/{uploaded['id']}/pages")
    assert pages_response.status_code == 200
    pages = pages_response.json()
    assert [page["page_number"] for page in pages] == [1, 2]
    assert "first page text" in pages[0]["raw_text"]
    assert "second page text" in pages[1]["raw_text"]
    assert pages[0]["ocr_blocks"][0]["text"]
    assert "bbox" in pages[0]["ocr_blocks"][0]
    assert "confidence" in pages[0]["ocr_blocks"][0]


def test_empty_pdf_page_gets_warning() -> None:
    task = create_task()
    uploaded = upload_file(task["id"], "blank.pdf", make_pdf([""]), "application/pdf")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")
    assert ocr_response.status_code == 200
    assert ocr_response.json()["ocr_status"] == "completed"

    pages = client.get(f"/api/v1/documents/{uploaded['id']}/pages").json()
    assert pages[0]["raw_text"] == ""
    assert "empty_text" in pages[0]["warnings"]


def test_ocr_failure_does_not_hide_task_or_document() -> None:
    task = create_task()
    uploaded = upload_file(task["id"], "scan.jpg", b"not-real-image", "image/jpeg")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")
    assert ocr_response.status_code == 200
    body = ocr_response.json()
    assert body["ocr_status"] == "failed"
    assert body["ocr_error"] == "Image OCR provider is not configured for MVP"

    task_response = client.get(f"/api/v1/tasks/{task['id']}")
    assert task_response.status_code == 200

    document_response = client.get(f"/api/v1/documents/{uploaded['id']}")
    assert document_response.status_code == 200
    assert document_response.json()["ocr_status"] == "failed"

    pages_response = client.get(f"/api/v1/documents/{uploaded['id']}/pages")
    assert pages_response.status_code == 200
    assert pages_response.json() == []

    assert not list((Path(__file__).resolve().parents[2] / "local_storage").glob("**/*.ocr"))
