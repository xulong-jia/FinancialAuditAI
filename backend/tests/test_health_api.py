from pathlib import Path
from io import BytesIO
import json
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from app.core.config import get_settings, settings
from app.main import app
from app.services import provider_readiness_service


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
    assert loaded.llm_api_mode == "auto"
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
    assert body["artifact_schema_version"] == "provider-readiness-v1"
    assert body["run_timestamp"]
    assert body["run_integration"] is False
    assert body["providers"]["llm"]["status"] == "configured"
    assert body["providers"]["embedding"]["status"] == "configured"
    assert body["providers"]["ocr"]["status"] == "blocked_external_dependency"
    assert body["providers"]["llm"]["api_key_status"] == "configured"
    assert set(body["paths"]) == {"classify", "extract", "explain", "rag_answer", "rag_rerank", "embedding", "ocr"}
    assert body["paths"]["classify"]["purpose"] == "classify"
    assert body["paths"]["extract"]["purpose"] == "extract"
    assert body["paths"]["explain"]["purpose"] == "explain"
    assert body["paths"]["embedding"]["status"] == "configured"
    assert body["paths"]["ocr"]["status"] == "blocked_external_dependency"
    assert "unit-test-placeholder-key" not in str(body)
    assert "Authorization" not in str(body)


def test_provider_readiness_responses_mode_success(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, json.loads(request.data.decode())))
        return _FakeHttpResponse({"output_text": "ok"})

    monkeypatch.setenv("RUN_PROVIDER_INTEGRATION", "1")
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_api_url", "https://api.example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "unit-test-placeholder-key")
    monkeypatch.setattr(settings, "llm_api_mode", "auto")
    monkeypatch.setattr(settings, "llm_model", "gpt-5.5")
    monkeypatch.setattr(provider_readiness_service.urllib.request, "urlopen", fake_urlopen)

    response = client.get("/api/v1/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["providers"]["llm"]["status"] == "ready"
    assert body["providers"]["llm"]["api_mode"] == "responses"
    assert body["paths"]["classify"]["status"] == "ready"
    assert body["paths"]["extract"]["status"] == "ready"
    assert body["paths"]["explain"]["status"] == "ready"
    assert {url for url, _body in calls} == {"https://api.example.test/v1/responses"}
    assert all(body == {"model": "gpt-5.5", "input": "Return exactly: ok"} for _url, body in calls)
    assert "unit-test-placeholder-key" not in str(body)


def test_provider_readiness_http_error_is_sanitized(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        payload = {
            "error": {
                "message": "Unsupported endpoint for provided model.",
                "type": "invalid_request_error",
                "code": "unsupported_endpoint",
            }
        }
        raise HTTPError(request.full_url, 400, "Bad Request", {}, BytesIO(json.dumps(payload).encode()))

    monkeypatch.setenv("RUN_PROVIDER_INTEGRATION", "1")
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_api_url", "https://api.example.test/v1")
    monkeypatch.setattr(settings, "llm_api_key", "unit-test-placeholder-key")
    monkeypatch.setattr(settings, "llm_api_mode", "chat_completions")
    monkeypatch.setattr(settings, "llm_model", "gpt-5.5")
    monkeypatch.setattr(provider_readiness_service.urllib.request, "urlopen", fake_urlopen)

    response = client.get("/api/v1/provider-readiness")

    assert response.status_code == 200
    error = response.json()["providers"]["llm"]["error"]
    assert response.json()["providers"]["llm"]["status"] == "failed"
    assert response.json()["providers"]["llm"]["http_status"] == 400
    assert error == {
        "message": "Unsupported endpoint for provided model.",
        "type": "invalid_request_error",
        "code": "unsupported_endpoint",
    }
    assert "unit-test-placeholder-key" not in str(response.json())


def test_provider_readiness_azure_ocr_get_model_probe(monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["key"] = request.get_header("Ocp-apim-subscription-key")
        return _FakeHttpResponse({"modelId": "prebuilt-layout"})

    monkeypatch.setenv("RUN_PROVIDER_INTEGRATION", "1")
    monkeypatch.setattr(settings, "ocr_provider", "azure-document-intelligence")
    monkeypatch.setattr(settings, "ocr_api_url", "https://azure.example.test")
    monkeypatch.setattr(settings, "ocr_api_key", "unit-test-azure-key")
    monkeypatch.setattr(settings, "ocr_model", "prebuilt-layout")
    monkeypatch.setattr(settings, "ocr_api_version", "2024-11-30")
    monkeypatch.setattr(provider_readiness_service.urllib.request, "urlopen", fake_urlopen)

    response = client.get("/api/v1/provider-readiness")

    assert response.status_code == 200
    ocr = response.json()["providers"]["ocr"]
    assert ocr["status"] == "ready"
    assert ocr["probe"] == "get_model_no_document_upload"
    assert ocr["model_status"] == "present"
    assert seen["url"] == "https://azure.example.test/documentintelligence/documentModels/prebuilt-layout?api-version=2024-11-30"
    assert seen["key"] == "unit-test-azure-key"
    assert response.json()["paths"]["ocr"]["status"] == "ready"
    assert "unit-test-azure-key" not in str(response.json())


def test_provider_readiness_embedding_path_probe_is_sanitized(monkeypatch) -> None:
    class FakeEmbeddingProvider:
        def embed(self, text: str) -> list[float]:
            assert text == "provider readiness probe"
            return [0.1, 0.2, 0.3]

    monkeypatch.setenv("RUN_PROVIDER_INTEGRATION", "1")
    monkeypatch.setattr(settings, "embedding_provider", "openai-compatible")
    monkeypatch.setattr(settings, "embedding_api_url", "https://embedding.example.test/v1")
    monkeypatch.setattr(settings, "embedding_api_key", "unit-test-placeholder-key")
    monkeypatch.setattr(provider_readiness_service.rag_service, "_embedding_provider", lambda: FakeEmbeddingProvider())

    response = client.get("/api/v1/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["providers"]["embedding"]["status"] == "ready"
    assert body["paths"]["embedding"]["status"] == "ready"
    assert "unit-test-placeholder-key" not in str(body)
    assert "Authorization" not in str(body)


class _FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


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
