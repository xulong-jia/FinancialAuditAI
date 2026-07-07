from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_danger_check_detects_common_secret_patterns_without_real_secrets(tmp_path) -> None:
    danger_check = load_script("danger_check")
    payload = "api_" + "key = " + repr("sk-" + ("x" * 32))
    sample = tmp_path / "provider_readiness_artifact.json"
    sample.write_text(payload, encoding="utf-8")

    failures = danger_check.scan_file(str(sample))

    assert f"possible secret in {sample}: openai_api_key" in failures


def test_danger_check_detects_staged_diff_and_runtime_artifact_paths() -> None:
    danger_check = load_script("danger_check")
    diff = "+authorization = " + repr("Bearer " + ("a" * 32))

    failures = danger_check.run_check(["local_storage/uploads/customer.pdf"], diff)

    assert "forbidden path: local_storage/uploads/customer.pdf" in failures
    assert "possible secret in staged diff: authorization_bearer" in failures


def test_production_safety_blocks_default_production_configuration() -> None:
    production_safety_check = load_script("production_safety_check")
    env = {
        "ENVIRONMENT": "production",
        "AUTH_SECRET_KEY": "change-me-local-auth-secret",
        "DATABASE_URL": "postgresql://app:change-me-local-only@db.example.test/app",
        "CORS_ORIGINS": "http://localhost:5173",
    }

    failures = production_safety_check.run_check(env, [".env.production", "local_storage/reports/out.xlsx"])

    assert "production AUTH_SECRET_KEY must be set and must not use the local default" in failures
    assert "production DATABASE_URL must not use an empty or default database password" in failures
    assert "production CORS_ORIGINS must be explicit non-localhost origins" in failures
    assert "forbidden tracked env file: .env.production" in failures
    assert "forbidden tracked runtime artifact: local_storage/reports/out.xlsx" in failures


def test_production_safety_accepts_non_default_production_configuration() -> None:
    production_safety_check = load_script("production_safety_check")
    env = {
        "ENVIRONMENT": "production",
        "AUTH_SECRET_KEY": "prod-secret-" + ("x" * 32),
        "DATABASE_URL": "postgresql://app:strong-prod-password@db.example.test/app",
        "CORS_ORIGINS": "https://audit.example.test",
    }

    assert production_safety_check.run_check(env, ["README.md", ".env.example"]) == []
