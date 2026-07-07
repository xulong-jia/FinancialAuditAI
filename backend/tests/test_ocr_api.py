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
    def __init__(self, payload: dict, status: int = 200, headers: dict | None = None) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def close(self) -> None:
        return None


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


def test_azure_document_intelligence_provider_normalizes_layout(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_provider", "azure-document-intelligence")
    monkeypatch.setattr(settings, "ocr_api_url", "https://azure.example.test")
    monkeypatch.setattr(settings, "ocr_api_key", "test-azure-key")
    monkeypatch.setattr(settings, "ocr_model", "prebuilt-layout")
    monkeypatch.setattr(settings, "ocr_api_version", "2024-11-30")

    calls = []
    azure_result = {
        "status": "succeeded",
        "analyzeResult": {
            "content": "Invoice Total\nInvoice\n100.00",
            "pages": [
                {
                    "pageNumber": 1,
                    "width": 8.5,
                    "height": 11,
                    "unit": "inch",
                    "lines": [
                        {
                            "content": "Invoice Total",
                            "polygon": [1, 1, 3, 1, 3, 2, 1, 2],
                        }
                    ],
                    "words": [
                        {
                            "content": "Invoice",
                            "polygon": [1, 1, 1.8, 1, 1.8, 2, 1, 2],
                            "confidence": 0.97,
                        },
                        {
                            "content": "Total",
                            "polygon": [2, 1, 3, 1, 3, 2, 2, 2],
                            "confidence": 0.95,
                        },
                    ],
                }
            ],
            "tables": [
                {
                    "rowCount": 1,
                    "columnCount": 2,
                    "boundingRegions": [{"pageNumber": 1, "polygon": [1, 3, 5, 3, 5, 4, 1, 4]}],
                    "cells": [
                        {
                            "rowIndex": 0,
                            "columnIndex": 0,
                            "content": "Invoice",
                            "boundingRegions": [{"pageNumber": 1, "polygon": [1, 3, 3, 3, 3, 4, 1, 4]}],
                            "confidence": 0.91,
                        },
                        {
                            "rowIndex": 0,
                            "columnIndex": 1,
                            "content": "100.00",
                            "boundingRegions": [{"pageNumber": 1, "polygon": [3, 3, 5, 3, 5, 4, 3, 4]}],
                            "confidence": 0.93,
                        },
                    ],
                }
            ],
        },
    }

    def fake_urlopen(request, timeout):
        calls.append(request)
        if request.get_method() == "POST":
            payload = json.loads(request.data.decode())
            assert payload["base64Source"]
            return FakeOcrResponse(
                {},
                status=202,
                headers={"Operation-Location": "https://azure.example.test/operations/1"},
            )
        return FakeOcrResponse(azure_result)

    monkeypatch.setattr(ocr_service.urllib.request, "urlopen", fake_urlopen)
    task = create_task()
    uploaded = upload_file(task["id"], "contract.pdf", make_pdf(["native text ignored by azure"]), "application/pdf")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")

    assert ocr_response.status_code == 200
    assert ocr_response.json()["ocr_status"] == "completed"
    pages = client.get(f"/api/v1/documents/{uploaded['id']}/pages").json()
    assert pages[0]["raw_text"] == "Invoice Total"
    assert pages[0]["ocr_engine"] == "azure-document-intelligence:prebuilt-layout"
    assert pages[0]["ocr_confidence"] == 0.96
    invoice_word = next(block for block in pages[0]["ocr_blocks"] if block["text"] == "Invoice")
    assert invoice_word["bbox"] == [1.0, 1.0, 1.8, 2.0]
    assert invoice_word["confidence"] == 0.97
    assert invoice_word["confidence_source"] == "azure_word"
    assert pages[0]["table_blocks"][0]["type"] == "azure_table"
    assert pages[0]["table_blocks"][0]["confidence"] == 0.92
    assert pages[0]["table_blocks"][0]["cells"][0]["bbox"] == [1.0, 3.0, 3.0, 4.0]

    assert calls[0].full_url == (
        "https://azure.example.test/documentintelligence/documentModels/"
        "prebuilt-layout:analyze?_overload=analyzeDocument&api-version=2024-11-30"
    )
    assert calls[1].full_url == "https://azure.example.test/operations/1"
    assert calls[0].get_header("Ocp-apim-subscription-key") == "test-azure-key"


def test_azure_document_intelligence_fixture_preserves_multi_page_complex_table(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_provider", "azure-document-intelligence")
    monkeypatch.setattr(settings, "ocr_api_url", "https://azure.example.test")
    monkeypatch.setattr(settings, "ocr_api_key", "test-azure-key")
    monkeypatch.setattr(settings, "ocr_model", "prebuilt-layout")
    monkeypatch.setattr(settings, "ocr_api_version", "2024-11-30")

    azure_result = {
        "status": "succeeded",
        "analyzeResult": {
            "content": "Page 1 Contract\nPage 2 Schedule\nItem Qty Amount\nAudit 2 1000.00",
            "pages": [
                {
                    "pageNumber": 1,
                    "width": 8.5,
                    "height": 11,
                    "unit": "inch",
                    "lines": [{"content": "Page 1 Contract", "polygon": [1, 1, 4, 1, 4, 2, 1, 2]}],
                    "words": [
                        {"content": "Contract", "polygon": [2, 1, 4, 1, 4, 2, 2, 2], "confidence": 0.97}
                    ],
                },
                {
                    "pageNumber": 2,
                    "width": 8.5,
                    "height": 11,
                    "unit": "inch",
                    "lines": [
                        {"content": "Page 2 Schedule", "polygon": [1, 1, 4, 1, 4, 2, 1, 2]},
                        {"content": "Item Qty Amount", "polygon": [1, 3, 6, 3, 6, 4, 1, 4]},
                        {"content": "Audit 2 1000.00", "polygon": [1, 4, 6, 4, 6, 5, 1, 5]},
                    ],
                    "words": [
                        {"content": "Audit", "polygon": [1, 4, 2, 4, 2, 5, 1, 5], "confidence": 0.94},
                        {"content": "1000.00", "polygon": [4, 4, 6, 4, 6, 5, 4, 5], "confidence": 0.92},
                    ],
                },
            ],
            "tables": [
                {
                    "rowCount": 2,
                    "columnCount": 3,
                    "boundingRegions": [{"pageNumber": 2, "polygon": [1, 3, 6, 3, 6, 5, 1, 5]}],
                    "cells": [
                        {"rowIndex": 0, "columnIndex": 0, "content": "Item", "boundingRegions": [{"pageNumber": 2, "polygon": [1, 3, 2, 3, 2, 4, 1, 4]}], "confidence": 0.96},
                        {"rowIndex": 0, "columnIndex": 1, "content": "Qty", "boundingRegions": [{"pageNumber": 2, "polygon": [2, 3, 4, 3, 4, 4, 2, 4]}], "confidence": 0.95},
                        {"rowIndex": 0, "columnIndex": 2, "content": "Amount", "boundingRegions": [{"pageNumber": 2, "polygon": [4, 3, 6, 3, 6, 4, 4, 4]}], "confidence": 0.94},
                        {"rowIndex": 1, "columnIndex": 0, "content": "Audit", "boundingRegions": [{"pageNumber": 2, "polygon": [1, 4, 2, 4, 2, 5, 1, 5]}], "confidence": 0.93},
                        {"rowIndex": 1, "columnIndex": 1, "content": "2", "boundingRegions": [{"pageNumber": 2, "polygon": [2, 4, 4, 4, 4, 5, 2, 5]}], "confidence": 0.92},
                        {"rowIndex": 1, "columnIndex": 2, "content": "1000.00", "boundingRegions": [{"pageNumber": 2, "polygon": [4, 4, 6, 4, 6, 5, 4, 5]}], "confidence": 0.91},
                    ],
                }
            ],
        },
    }

    def fake_urlopen(request, timeout):
        if request.get_method() == "POST":
            return FakeOcrResponse({}, status=202, headers={"Operation-Location": "https://azure.example.test/operations/complex"})
        return FakeOcrResponse(azure_result)

    monkeypatch.setattr(ocr_service.urllib.request, "urlopen", fake_urlopen)
    task = create_task()
    uploaded = upload_file(task["id"], "complex.pdf", make_pdf(["native page one", "native page two"]), "application/pdf")

    ocr_response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")

    assert ocr_response.status_code == 200
    assert ocr_response.json()["page_count"] == 2
    pages = client.get(f"/api/v1/documents/{uploaded['id']}/pages").json()
    assert [page["page_number"] for page in pages] == [1, 2]
    assert pages[0]["raw_text"] == "Page 1 Contract"
    assert pages[1]["raw_text"] == "Page 2 Schedule\nItem Qty Amount\nAudit 2 1000.00"
    assert pages[0]["image_path"]
    assert pages[1]["image_path"]
    assert pages[1]["ocr_blocks"][0]["bbox"]
    audit_word = next(block for block in pages[1]["ocr_blocks"] if block["text"] == "Audit")
    assert audit_word["bbox"] == [1.0, 4.0, 2.0, 5.0]
    assert audit_word["confidence"] == 0.94
    assert pages[1]["table_blocks"][0]["type"] == "azure_table"
    assert pages[1]["table_blocks"][0]["row_count"] == 2
    assert pages[1]["table_blocks"][0]["column_count"] == 3
    assert pages[1]["table_blocks"][0]["cells"][5]["text"] == "1000.00"
    assert pages[1]["table_blocks"][0]["cells"][5]["bbox"] == [4.0, 4.0, 6.0, 5.0]


def test_azure_document_intelligence_error_redacts_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ocr_provider", "azure")
    monkeypatch.setattr(settings, "ocr_api_url", "https://azure.example.test")
    monkeypatch.setattr(settings, "ocr_api_key", "test-azure-key")
    monkeypatch.setattr(settings, "ocr_model", "prebuilt-layout")
    monkeypatch.setattr(settings, "ocr_api_version", "2024-11-30")

    def fake_urlopen(request, timeout):
        payload = {"error": {"code": "InvalidKey", "message": "bad test-azure-key"}}
        raise ocr_service.urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, FakeOcrResponse(payload))

    monkeypatch.setattr(ocr_service.urllib.request, "urlopen", fake_urlopen)
    task = create_task()
    uploaded = upload_file(task["id"], "contract.pdf", make_pdf(["text"]), "application/pdf")

    response = client.post(f"/api/v1/documents/{uploaded['id']}/ocr")

    assert response.status_code == 200
    body = response.json()
    assert body["ocr_status"] == "failed"
    assert "test-azure-key" not in body["ocr_error"]
    assert "[REDACTED]" in body["ocr_error"]


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
