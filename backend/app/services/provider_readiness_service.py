from __future__ import annotations

import os

from app.core.config import settings
from app.services import llm_provider, rag_service

REAL_PROVIDERS = {"openai", "openai-compatible", "real"}
LOCAL_LLM_PROVIDERS = {"local", "local-http", "local-llm"}


def readiness(run_integration: bool | None = None) -> dict:
    enabled = _integration_enabled(run_integration)
    return {
        "run_integration": enabled,
        "providers": {
            "llm": _llm_status(settings.llm_provider, settings.llm_api_url, settings.llm_api_key, settings.llm_model, enabled),
            "embedding": _embedding_status(enabled),
            "ocr": _configured_status(settings.ocr_provider, settings.ocr_api_url, settings.ocr_api_key, settings.ocr_model),
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
    if not run_integration or status["status"] != "configured":
        return status
    result = llm_provider.get_llm_provider(purpose).classify_document(
        "provider-readiness.txt",
        "provider readiness probe",
        "procurement",
        ["invoice", "purchase_contract"],
    )
    return status | {
        "status": "ready" if result.status == "ok" else "failed",
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


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
