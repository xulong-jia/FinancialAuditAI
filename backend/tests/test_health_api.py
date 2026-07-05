from pathlib import Path

from fastapi.testclient import TestClient

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
