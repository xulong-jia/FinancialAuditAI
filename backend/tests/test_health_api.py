from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings, settings
from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config() -> None:
    response = client.get("/api/v1/config")

    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == "FinancialAuditAI"
    assert body["api_prefix"] == "/api/v1"
    assert body["llm_api_key_status"] in {"configured", "not_configured"}
    assert body["embedding_provider"]


def test_pytest_config_forces_deterministic_providers(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "unit-test-placeholder-key")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai-compatible")
    monkeypatch.setenv("EMBEDDING_API_URL", "https://embedding.example.test/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "unit-test-placeholder-key")
    get_settings.cache_clear()

    loaded = get_settings()

    assert loaded.environment == "test"
    assert loaded.llm_provider == "deterministic-fallback"
    assert loaded.llm_api_url is None
    assert loaded.llm_api_key is None
    assert loaded.embedding_provider == "deterministic-local"
    assert loaded.embedding_api_url is None
    assert loaded.embedding_api_key is None
    assert loaded.ocr_provider == "pymupdf-local"
    assert loaded.rag_rerank_provider == "deterministic-fallback"
    assert loaded.rag_answer_provider == "deterministic-fallback"
    get_settings.cache_clear()


def test_provider_readiness_is_sanitized_and_non_integrating_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_api_url", "https://llm.example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "unit-test-placeholder-key")
    monkeypatch.setattr(settings, "embedding_provider", "openai-compatible")
    monkeypatch.setattr(settings, "embedding_api_url", "https://embedding.example.test/v1")
    monkeypatch.setattr(settings, "embedding_api_key", "unit-test-placeholder-key")
    monkeypatch.setattr(settings, "ocr_provider", "http")
    monkeypatch.setattr(settings, "ocr_api_url", None)
    monkeypatch.setattr(settings, "ocr_api_key", None)

    response = client.get("/api/v1/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["run_integration"] is False
    assert body["providers"]["llm"]["status"] == "configured"
    assert body["providers"]["embedding"]["status"] == "configured"
    assert body["providers"]["ocr"]["status"] == "blocked_external_dependency"
    assert body["providers"]["llm"]["api_key_status"] == "configured"
    assert "unit-test-placeholder-key" not in str(body)


def test_api_response_envelope_by_default() -> None:
    response = client.get("/api/v1/config", headers={"X-Api-Raw": "0"})

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["data"]["app_name"] == "FinancialAuditAI"


def test_docker_compose_backend_runs_migrations_before_startup() -> None:
    compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    text = compose.read_text()

    assert "alembic upgrade head" in text
    assert text.index("alembic upgrade head") < text.index("uvicorn app.main:app")
