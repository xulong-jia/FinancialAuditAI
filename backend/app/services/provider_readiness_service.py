from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from time import perf_counter
import urllib.error
import urllib.parse
import urllib.request

from app.core.config import settings
from app.services import rag_service

REAL_PROVIDERS = {"openai", "openai-compatible", "real"}
LOCAL_LLM_PROVIDERS = {"local", "local-http", "local-llm"}
AZURE_OCR_PROVIDERS = {"azure", "azure-document-intelligence", "azure-document-intelligence-layout"}


def readiness(run_integration: bool | None = None) -> dict:
    enabled = _integration_enabled(run_integration)
    return {
        "artifact_schema_version": "provider-readiness-v1",
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "run_integration": enabled,
        "providers": {
            "llm": _llm_status(settings.llm_provider, settings.llm_api_url, settings.llm_api_key, settings.llm_model, enabled),
            "embedding": _embedding_status(enabled),
            "ocr": _ocr_status(enabled),
            "rag_rerank": _llm_status(settings.rag_rerank_provider, settings.llm_api_url, settings.llm_api_key, settings.llm_model, enabled, purpose="rag_rerank"),
            "rag_answer": _llm_status(settings.rag_answer_provider, settings.llm_api_url, settings.llm_api_key, settings.llm_model, enabled, purpose="rag_answer"),
        },
    }


def _integration_enabled(run_integration: bool | None) -> bool:
    if run_integration is not None:
        return run_integration
    return os.getenv("RUN_PROVIDER_INTEGRATION") == "1"


def _configured_status(provider: str, api_url: str | None, api_key: str | None, model: str) -> dict:
    normalized = (provider or "").strip().lower()
    payload = {
        "provider": provider,
        "model": model,
        "api_url_status": "configured" if api_url else "not_configured",
        "api_key_status": "configured" if api_key else "not_configured",
    }
    if normalized in {"deterministic-fallback", "deterministic-local", "pymupdf-local", "pymupdf", "local", "mock"}:
        return payload | {"status": "fallback"}
    if normalized in REAL_PROVIDERS | {"http", "external-http"}:
        if api_url and api_key:
            return payload | {"status": "configured"}
        return payload | {"status": "blocked_external_dependency"}
    if normalized in LOCAL_LLM_PROVIDERS:
        return payload | {"status": "configured" if api_url else "blocked_external_dependency"}
    return payload | {"status": "not_configured"}


def _llm_status(provider: str, api_url: str | None, api_key: str | None, model: str, run_integration: bool, purpose: str | None = None) -> dict:
    status = _configured_status(provider, api_url, api_key, model)
    if purpose:
        status["purpose"] = purpose
    status["api_mode"] = _llm_api_mode(model)
    if not run_integration or status["status"] != "configured":
        return status
    return status | _probe_llm(api_url, api_key, model, status["api_mode"])


def _embedding_status(run_integration: bool) -> dict:
    api_url = settings.embedding_api_url or settings.llm_api_url
    api_key = settings.embedding_api_key or settings.llm_api_key
    status = _configured_status(settings.embedding_provider, api_url, api_key, settings.embedding_model)
    status["dimensions"] = settings.embedding_dimensions
    if not run_integration or status["status"] != "configured":
        return status
    try:
        rag_service._embedding_provider().embed("provider readiness probe")
    except Exception as exc:  # noqa: BLE001
        return status | {"status": "failed", "error": str(exc)}
    return status | {"status": "ready"}


def _ocr_status(run_integration: bool) -> dict:
    normalized = (settings.ocr_provider or "").strip().lower()
    if normalized not in AZURE_OCR_PROVIDERS:
        return _configured_status(settings.ocr_provider, settings.ocr_api_url, settings.ocr_api_key, settings.ocr_model)
    payload = {
        "provider": settings.ocr_provider,
        "model": settings.ocr_model,
        "api_version": settings.ocr_api_version,
        "api_url_status": "configured" if settings.ocr_api_url else "not_configured",
        "api_key_status": "configured" if settings.ocr_api_key else "not_configured",
    }
    if not settings.ocr_api_url or not settings.ocr_api_key or not settings.ocr_model:
        return payload | {"status": "blocked_external_dependency"}
    if not run_integration:
        return payload | {"status": "configured"}
    return payload | _probe_azure_ocr_model()


def _probe_azure_ocr_model() -> dict:
    started = perf_counter()
    request = urllib.request.Request(
        _azure_model_url(settings.ocr_api_url or "", settings.ocr_model, settings.ocr_api_version),
        headers={"Ocp-Apim-Subscription-Key": settings.ocr_api_key or ""},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.ocr_timeout_seconds) as response:
            payload = json.loads(response.read().decode() or "{}")
        return {
            "status": "ready",
            "latency_ms": int((perf_counter() - started) * 1000),
            "model_status": "present" if isinstance(payload, dict) and payload.get("modelId") else "not_parsed_2xx",
            "probe": "get_model_no_document_upload",
        }
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "latency_ms": int((perf_counter() - started) * 1000),
            "http_status": exc.code,
            "error": _http_error_payload(exc),
            "probe": "get_model_no_document_upload",
        }
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {
            "status": "failed",
            "latency_ms": int((perf_counter() - started) * 1000),
            "error": {"message": _sanitize(str(exc))},
            "probe": "get_model_no_document_upload",
        }


def _azure_model_url(endpoint: str, model: str, api_version: str) -> str:
    if "/documentintelligence/documentModels/" in endpoint:
        base = endpoint.split(":analyze", 1)[0] if ":analyze" in endpoint else endpoint
        return _append_api_version(base, api_version)
    base = endpoint.rstrip("/")
    model_id = urllib.parse.quote(model or "prebuilt-layout", safe="")
    return f"{base}/documentintelligence/documentModels/{model_id}?{urllib.parse.urlencode({'api-version': api_version})}"


def _append_api_version(url: str, api_version: str) -> str:
    if "api-version=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urllib.parse.urlencode({'api-version': api_version})}"


def _probe_llm(api_url: str | None, api_key: str | None, model: str, api_mode: str) -> dict:
    if not api_url:
        return {"status": "blocked_external_dependency", "error": {"message": "LLM_API_URL is not configured"}}
    started = perf_counter()
    request = urllib.request.Request(
        _llm_endpoint(api_url, api_mode),
        data=json.dumps(_llm_probe_body(model, api_mode)).encode(),
        headers=_headers(api_key),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            payload = json.loads(response.read().decode() or "{}")
        return {
            "status": "ready",
            "latency_ms": int((perf_counter() - started) * 1000),
            "response_text_status": "present" if _response_text(payload) else "not_parsed_2xx",
        }
    except urllib.error.HTTPError as exc:
        return {
            "status": "failed",
            "latency_ms": int((perf_counter() - started) * 1000),
            "http_status": exc.code,
            "error": _http_error_payload(exc),
        }
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {
            "status": "failed",
            "latency_ms": int((perf_counter() - started) * 1000),
            "error": {"message": _sanitize(str(exc))},
        }


def _llm_api_mode(model: str) -> str:
    mode = (settings.llm_api_mode or "auto").strip().lower().replace("-", "_")
    if mode in {"responses", "response"}:
        return "responses"
    if mode in {"chat", "chat_completions"}:
        return "chat_completions"
    return "responses" if model.strip().lower().startswith("gpt-5") else "chat_completions"


def _llm_endpoint(api_url: str, api_mode: str) -> str:
    base = api_url.rstrip("/")
    if api_mode == "responses":
        return base if base.endswith("/responses") else f"{base}/responses"
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def _llm_probe_body(model: str, api_mode: str) -> dict:
    if api_mode == "responses":
        return {"model": model, "input": "Return exactly: ok"}
    return {"model": model, "messages": [{"role": "user", "content": "Return exactly: ok"}], "temperature": 0}


def _headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _response_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    choices = payload.get("choices")
    choice_text = choices[0].get("message", {}).get("content") if isinstance(choices, list) and choices else None
    if isinstance(choice_text, str):
        return choice_text
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict) or not isinstance(item.get("content"), list):
            continue
        for content in item["content"]:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    return None


def _http_error_payload(exc: urllib.error.HTTPError) -> dict:
    raw = exc.read().decode(errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"message": _sanitize(raw[:500] or str(exc))}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return {
            "message": _sanitize(str(error.get("message") or str(exc))),
            "type": _sanitize(str(error.get("type"))) if error.get("type") is not None else None,
            "code": _sanitize(str(error.get("code"))) if error.get("code") is not None else None,
        }
    return {"message": _sanitize(str(exc))}


def _sanitize(text: str) -> str:
    sanitized = text
    for secret in (settings.llm_api_key, settings.embedding_api_key, settings.ocr_api_key):
        if secret:
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", sanitized)
