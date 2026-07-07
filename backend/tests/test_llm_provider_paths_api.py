import json
from io import BytesIO
from uuid import UUID
from urllib.error import HTTPError

import fitz
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.model_invocation import ModelInvocation
from app.services import llm_provider
from test_rag_api import create_rag_document, index_document, query_rag
from test_rule_engine_api import build_scenario, run_audit, seed_rag_document

client = TestClient(app)


class FakeChatResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def install_fake_llm(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_api_url", "http://llm.local/v1")
    monkeypatch.setattr(settings, "llm_api_key", "test-llm-key")
    monkeypatch.setattr(settings, "llm_model", "audit-llm-v1")
    monkeypatch.setattr(settings, "rag_rerank_provider", "openai-compatible")
    monkeypatch.setattr(settings, "rag_answer_provider", "openai-compatible")
    calls = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode())
        prompt = json.loads(body["messages"][1]["content"])
        calls.append((request, timeout, prompt))
        content = _fake_llm_content(prompt)
        return FakeChatResponse(
            {
                "choices": [{"message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            }
        )

    monkeypatch.setattr(llm_provider.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_openai_compatible_provider_classifies_and_extracts_with_invocation_metadata(monkeypatch) -> None:
    calls = install_fake_llm(monkeypatch)
    task = client.post("/api/v1/tasks", json={"name": "Provider task", "scenario": "procurement"}).json()
    upload = client.post(
        f"/api/v1/tasks/{task['id']}/documents",
        files={"file": ("invoice.pdf", make_pdf("Invoice invoice number total with tax"), "application/pdf")},
    ).json()
    assert client.post(f"/api/v1/documents/{upload['id']}/ocr").status_code == 200

    classify = client.post(f"/api/v1/documents/{upload['id']}/classify")
    extract = client.post(f"/api/v1/documents/{upload['id']}/extract")

    assert classify.status_code == 200
    assert classify.json()["doc_type"] == "invoice"
    assert "LLM classification via openai-compatible" in classify.json()["classification_reason"]
    assert extract.status_code == 200
    fields = {field["field_name"]: field for field in extract.json()}
    assert fields["invoice_no"]["extraction_method"] == "llm:openai-compatible"
    assert fields["invoice_no"]["source_bbox"] == [10.0, 20.0, 80.0, 40.0]
    assert {call[2]["task"] for call in calls} >= {
        "classify_financial_audit_document",
        "extract_financial_audit_fields",
    }
    with SessionLocal() as db:
        invocations = {
            invocation.invocation_type: invocation
            for invocation in db.query(ModelInvocation).filter(ModelInvocation.document_id == UUID(upload["id"])).all()
        }
    assert invocations["classify"].status == "success"
    assert invocations["classify"].model_name == "audit-llm-v1"
    assert invocations["classify"].token_usage["total_tokens"] == 18
    assert invocations["extract"].status == "success"
    assert invocations["extract"].model_name == "audit-llm-v1"
    assert invocations["extract"].token_usage["total_tokens"] == 18


def test_openai_compatible_provider_responses_mode_success(monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode())
        return FakeChatResponse(
            {
                "output_text": json.dumps(
                    {
                        "doc_type": "invoice",
                        "confidence": 0.97,
                        "reason": "Responses API classified invoice.",
                        "alternative_types": [],
                    }
                ),
                "usage": {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
            }
        )

    monkeypatch.setattr(llm_provider.urllib.request, "urlopen", fake_urlopen)
    placeholder_key = "unit-test-placeholder-key"
    provider = llm_provider.OpenAICompatibleLlmProvider(
        provider_kind="real",
        provider_name="openai-compatible",
        api_url="https://api.example.test/v1",
        model="gpt-5.1",
        api_mode="responses",
        **{"api_key": placeholder_key},
    )

    result = provider.classify_document("invoice.pdf", "Invoice total", "procurement", ["invoice"])

    assert result.status == "ok"
    assert result.payload["doc_type"] == "invoice"
    assert result.token_usage["total_tokens"] == 19
    assert seen["url"] == "https://api.example.test/v1/responses"
    assert seen["body"]["model"] == "gpt-5.1"
    assert "Return JSON only." in seen["body"]["input"]
    assert placeholder_key not in str(result)


def test_openai_compatible_provider_auto_mode_selects_responses_and_chat_success(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode())
        calls.append((request.full_url, body))
        payload = {
            "doc_type": "invoice",
            "confidence": 0.96,
            "reason": "Auto mode selected a compatible endpoint.",
            "alternative_types": [],
        }
        if request.full_url.endswith("/responses"):
            return FakeChatResponse({"output_text": json.dumps(payload), "usage": {"total_tokens": 11}})
        return FakeChatResponse({"choices": [{"message": {"content": json.dumps(payload)}}], "usage": {"total_tokens": 12}})

    monkeypatch.setattr(llm_provider.urllib.request, "urlopen", fake_urlopen)
    placeholder_key = "unit-test-placeholder-key"
    responses_provider = llm_provider.OpenAICompatibleLlmProvider(
        provider_kind="real",
        provider_name="openai-compatible",
        api_url="https://api.example.test/v1",
        model="gpt-5.1",
        api_mode="auto",
        **{"api_key": placeholder_key},
    )
    chat_provider = llm_provider.OpenAICompatibleLlmProvider(
        provider_kind="real",
        provider_name="openai-compatible",
        api_url="https://api.example.test/v1",
        model="audit-llm-v1",
        api_mode="auto",
        **{"api_key": placeholder_key},
    )

    responses_result = responses_provider.classify_document("invoice.pdf", "Invoice total", "procurement", ["invoice"])
    chat_result = chat_provider.classify_document("invoice.pdf", "Invoice total", "procurement", ["invoice"])

    assert responses_result.status == "ok"
    assert chat_result.status == "ok"
    assert [url for url, _body in calls] == [
        "https://api.example.test/v1/responses",
        "https://api.example.test/v1/chat/completions",
    ]
    assert "input" in calls[0][1]
    assert "messages" in calls[1][1]
    assert placeholder_key not in str(responses_result)
    assert placeholder_key not in str(chat_result)


def test_openai_compatible_provider_http_error_body_is_sanitized(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        payload = {
            "error": {
                "message": "Bad key unit-test-placeholder-key in Authorization Bearer unit-test-placeholder-key",
                "type": "invalid_request_error",
            }
        }
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, BytesIO(json.dumps(payload).encode()))

    monkeypatch.setattr(llm_provider.urllib.request, "urlopen", fake_urlopen)
    placeholder_key = "unit-test-placeholder-key"
    provider = llm_provider.OpenAICompatibleLlmProvider(
        provider_kind="real",
        provider_name="openai-compatible",
        api_url="https://api.example.test/v1",
        model="audit-llm-v1",
        api_mode="chat_completions",
        **{"api_key": placeholder_key},
    )

    result = provider.classify_document("invoice.pdf", "Invoice total", "procurement", ["invoice"])

    assert result.status == "error"
    assert "[REDACTED]" in result.error
    assert placeholder_key not in result.error


def test_rag_rerank_answer_and_rule_explain_use_configured_llm_provider(monkeypatch) -> None:
    calls = install_fake_llm(monkeypatch)
    document = create_rag_document(text="Revenue recognition evidence requires approved contract support.")
    index_document(document["id"])

    rag_result = query_rag("revenue recognition evidence")

    assert rag_result["status"] == "answer"
    assert rag_result["answer"] == "Provider-grounded answer from citations."
    assert rag_result["provider_info"]["answer_provider_kind"] == "real"
    assert {call[2]["task"] for call in calls} >= {"rerank_rag_citations", "answer_with_citations_only"}

    seed_rag_document(
        "Provider Explain Evidence",
        "PROC_AMOUNT_001 evidence retrieval guidance for overpayment explanation.",
    )
    task, _ = build_scenario(contract_amount=1000.0, invoice_amounts=(1300.0,), payment_amounts=(1300.0,))
    results = run_audit(task["id"])
    amount_result = results["PROC_AMOUNT_001"]

    assert amount_result["actual_value"]["explanation"]["explanation"] == "Provider-grounded exception explanation."
    assert {call[2]["task"] for call in calls} >= {"explain_audit_exception_with_citations"}
    with SessionLocal() as db:
        invocations = db.query(ModelInvocation).filter(ModelInvocation.task_id == UUID(task["id"])).all()
        explain = next(invocation for invocation in invocations if invocation.invocation_type == "explain")
        assert explain.status == "success"
        assert explain.model_name == "audit-llm-v1"
        assert explain.token_usage["total_tokens"] == 18


def _fake_llm_content(prompt: dict) -> dict:
    task = prompt["task"]
    if task == "classify_financial_audit_document":
        return {
            "doc_type": "invoice",
            "confidence": 0.98,
            "reason": "Provider identified invoice evidence.",
            "alternative_types": [],
        }
    if task == "extract_financial_audit_fields":
        return {"fields": [_field_payload(field) for field in prompt["fields_schema"]]}
    if task == "rerank_rag_citations":
        return {"chunk_ids": [str(citation["chunk_id"]) for citation in prompt["citations"]]}
    if task == "answer_with_citations_only":
        return {"answer": "Provider-grounded answer from citations.", "limitations": []}
    if task == "explain_audit_exception_with_citations":
        return {"explanation": "Provider-grounded exception explanation.", "limitations": []}
    raise AssertionError(f"Unexpected LLM task {task}")


def _field_payload(field: dict) -> dict:
    field_name = field["field_name"]
    field_type = field["field_type"]
    value_text = {
        "date": "2026-07-04",
        "money": "100.00",
        "tax_rate": "13%",
        "line_items": "Audit Service 1 pcs 100.00",
    }.get(field_type, f"{field_name}-provider-value")
    normalized = {
        "date": {"value": "2026-07-04"},
        "money": {"amount": 100.0, "currency": "CNY"},
        "tax_rate": {"rate": 0.13},
        "line_items": {
            "items": [
                {
                    "item_name": "Audit Service",
                    "quantity": 1.0,
                    "unit": "pcs",
                    "unit_price": 100.0,
                    "amount": 100.0,
                    "source_page": 1,
                    "source_bbox": [10.0, 20.0, 80.0, 40.0],
                    "source_text": "Audit Service 1 pcs 100.00",
                }
            ]
        },
    }.get(field_type, {"value": value_text})
    return {
        "field_name": field_name,
        "value_text": value_text,
        "value_normalized": normalized,
        "confidence": 0.91,
        "source_page": 1,
        "source_bbox": [10.0, 20.0, 80.0, 40.0],
        "source_text": value_text,
        "warnings": [],
    }
