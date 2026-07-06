import json
from pathlib import Path
from uuid import UUID

import fitz
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.model_invocation import ModelInvocation
from app.services import ocr_service


client = TestClient(app)
ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00"
    b"\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeOcrResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


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
    assert pages[0]["ocr_confidence"] is None
    assert "digital_text_confidence_not_applicable" in pages[0]["warnings"]
    assert pages[0]["table_blocks"][0]["rows"][0]["cells"] == ["item", "amount"]

    with SessionLocal() as db:
        invocation = db.query(ModelInvocation).filter(ModelInvocation.document_id == UUID(uploaded["id"])).one()
        assert invocation.task_id == UUID(task["id"])
        assert invocation.invocation_type == "ocr"
        assert invocation.status == "success"
        assert invocation.latency_ms is not None
        assert invocation.cost_estimate["basis"] == "non_llm_ocr_no_token_usage"

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
    assert "ocr_confidence_not_reported_by_provider" in pages[0]["warnings"]


def test_http_ocr_provider_preserves_provider_confidence(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_provider", "http")
    monkeypatch.setattr(settings, "ocr_api_url", "http://ocr.local/parse")
    monkeypatch.setattr(settings, "ocr_api_key", "test-ocr-key")
    monkeypatch.setattr(settings, "ocr_model", "external-ocr-v1")

    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout, json.loads(request.data.decode())))
        return FakeOcrResponse(
            {
                "pages": [
                    {
                        "page_number": 1,
                        "raw_text": "Total 123.45",
                        "ocr_engine": "external-ocr-v1",
                        "ocr_confidence": 0.96,
                        "ocr_blocks": [
                            {"text": "Total 123.45", "bbox": [10, 20, 80, 40], "confidence": 0.93}
                        ],
                        "table_blocks": [{"type": "provider_table", "rows": []}],
                    }
                ]
            }
        )

    monkeypatch.setattr(ocr_service.urllib.request, "urlopen", fake_urlopen)
    task = create_task()
    uploaded = upload_file(task["id"], "contract.pdf", make_pdf(["native text ignored by provider"]), "application/pdf")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")

    assert ocr_response.status_code == 200
    pages = client.get(f"/api/v1/documents/{uploaded['id']}/pages").json()
    assert pages[0]["raw_text"] == "Total 123.45"
    assert pages[0]["ocr_confidence"] == 0.96
    assert pages[0]["ocr_blocks"][0]["confidence"] == 0.93
    assert pages[0]["ocr_blocks"][0]["confidence_source"] == "provider"
    assert "confidence_unavailable" not in pages[0]["warnings"]
    assert pages[0]["table_blocks"][0]["type"] == "provider_table"
    assert pages[0]["image_path"]

    request, timeout, payload = calls[0]
    assert request.full_url == "http://ocr.local/parse"
    assert request.headers["Authorization"] == "Bearer test-ocr-key"
    assert timeout == settings.ocr_timeout_seconds
    assert payload["model"] == "external-ocr-v1"
    assert payload["filename"] == "contract.pdf"

    with SessionLocal() as db:
        invocation = db.query(ModelInvocation).filter(ModelInvocation.document_id == UUID(uploaded["id"])).one()
        assert invocation.provider == "external-ocr-v1"
        assert invocation.invocation_type == "ocr"
        assert invocation.status == "success"


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

    with SessionLocal() as db:
        invocation = db.query(ModelInvocation).filter(ModelInvocation.document_id == UUID(uploaded["id"])).one()
        assert invocation.invocation_type == "ocr"
        assert invocation.status == "failed"
        assert invocation.error["message"]

    assert not list((Path(__file__).resolve().parents[2] / "local_storage").glob("**/*.ocr"))
