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
    cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str = (
        "postgresql+psycopg://financial_audit_ai:change-me-local-only"
        "@localhost:5432/financial_audit_ai"
    )
    embedding_provider: str = "deterministic-local"
    embedding_dimensions: int = 32


@lru_cache
def get_settings() -> Settings:
    _load_env()
    return Settings(
        app_name=os.getenv("APP_NAME", "FinancialAuditAI"),
        environment=os.getenv("ENVIRONMENT", "local"),
        api_v1_prefix=os.getenv("API_V1_PREFIX", "/api/v1"),
        cors_origins=[
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
            if origin.strip()
        ],
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://financial_audit_ai:change-me-local-only"
            "@localhost:5432/financial_audit_ai",
        ),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "deterministic-local"),
        embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "32")),
    )


settings = get_settings()
