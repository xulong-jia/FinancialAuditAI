from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


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
        make_pdf(["first page text\nitem | amount\nservice | 100", "second page text"]),
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
    assert pages[0]["image_path"]
    assert pages[0]["ocr_blocks"][0]["text"]
    assert "bbox" in pages[0]["ocr_blocks"][0]
    assert "confidence" in pages[0]["ocr_blocks"][0]
    assert pages[0]["ocr_blocks"][0]["confidence_source"] == "not_available"
    assert pages[0]["table_blocks"][0]["rows"][0]["cells"] == ["item", "amount"]

    image_response = client.get(f"/api/v1/documents/{uploaded['id']}/pages/1/image")
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"


def test_empty_pdf_page_gets_warning() -> None:
    task = create_task()
    uploaded = upload_file(task["id"], "blank.pdf", make_pdf([""]), "application/pdf")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")
    assert ocr_response.status_code == 200
    assert ocr_response.json()["ocr_status"] == "completed"

    pages = client.get(f"/api/v1/documents/{uploaded['id']}/pages").json()
    assert pages[0]["raw_text"] == ""
    assert "empty_text" in pages[0]["warnings"]
    assert pages[0]["image_path"]


def test_png_ocr_runs_without_unimplemented_provider() -> None:
    task = create_task()
    uploaded = upload_file(task["id"], "scan.png", ONE_PIXEL_PNG, "image/png")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")
    assert ocr_response.status_code == 200
    assert ocr_response.json()["ocr_status"] == "completed"
    assert ocr_response.json()["page_count"] == 1

    pages = client.get(f"/api/v1/documents/{uploaded['id']}/pages").json()
    assert pages[0]["image_path"]
    assert pages[0]["width"] == 1
    assert pages[0]["height"] == 1
    assert "confidence_unavailable" in pages[0]["warnings"]


def test_ocr_failure_does_not_hide_task_or_document() -> None:
    task = create_task()
    uploaded = upload_file(task["id"], "scan.jpg", b"\xff\xd8\xffnot-real-image", "image/jpeg")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")
    assert ocr_response.status_code == 200
    body = ocr_response.json()
    assert body["ocr_status"] == "failed"
    assert body["ocr_error"]
    assert "not configured" not in body["ocr_error"].lower()
    assert "notimplemented" not in body["ocr_error"].lower()

    task_response = client.get(f"/api/v1/tasks/{task['id']}")
    assert task_response.status_code == 200

    document_response = client.get(f"/api/v1/documents/{uploaded['id']}")
    assert document_response.status_code == 200
    assert document_response.json()["ocr_status"] == "failed"

    pages_response = client.get(f"/api/v1/documents/{uploaded['id']}/pages")
    assert pages_response.status_code == 200
    assert pages_response.json() == []

    assert not list((Path(__file__).resolve().parents[2] / "local_storage").glob("**/*.ocr"))
