from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load_env() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    project_dir = backend_dir.parent
    _load_env_file(project_dir / ".env")
    _load_env_file(backend_dir / ".env")


class Settings(BaseModel):
    app_name: str = "FinancialAuditAI"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = (
        "postgresql+psycopg://financial_audit_ai:change-me-local-only"
        "@localhost:5432/financial_audit_ai"
    )


@lru_cache
def get_settings() -> Settings:
    _load_env()
    return Settings(
        app_name=os.getenv("APP_NAME", "FinancialAuditAI"),
        environment=os.getenv("ENVIRONMENT", "local"),
        api_v1_prefix=os.getenv("API_V1_PREFIX", "/api/v1"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://financial_audit_ai:change-me-local-only"
            "@localhost:5432/financial_audit_ai",
        ),
    )


settings = get_settings()
