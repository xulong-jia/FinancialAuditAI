from functools import lru_cache
import os
from pathlib import Path

from pydantic import BaseModel

TEST_PROVIDER_ENV = {
    "LLM_PROVIDER": "deterministic-fallback",
    "LLM_API_URL": "",
    "LLM_API_KEY": "",
    "LLM_API_MODE": "auto",
    "LLM_MODEL": "financialauditai-local",
    "EMBEDDING_PROVIDER": "deterministic-local",
    "EMBEDDING_API_URL": "",
    "EMBEDDING_API_KEY": "",
    "EMBEDDING_MODEL": "financialauditai-embedding",
    "EMBEDDING_DIMENSIONS": "32",
    "OCR_PROVIDER": "pymupdf-local",
    "OCR_API_URL": "",
    "OCR_API_KEY": "",
    "OCR_API_VERSION": "2024-11-30",
    "RAG_RERANK_PROVIDER": "deterministic-fallback",
    "RAG_ANSWER_PROVIDER": "deterministic-fallback",
}


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
    if _is_testing():
        os.environ.update(TEST_PROVIDER_ENV)


def _is_testing() -> bool:
    return os.getenv("TESTING", "").lower() in {"1", "true", "yes"} or os.getenv("ENVIRONMENT") == "test"


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
    embedding_api_url: str | None = None
    embedding_api_key: str | None = None
    embedding_model: str = "financialauditai-embedding"
    ocr_provider: str = "pymupdf-local"
    ocr_api_url: str | None = None
    ocr_api_key: str | None = None
    ocr_model: str = "financialauditai-ocr"
    ocr_api_version: str = "2024-11-30"
    ocr_timeout_seconds: float = 30.0
    llm_provider: str = "deterministic-fallback"
    llm_api_url: str | None = None
    llm_api_key: str | None = None
    llm_api_mode: str = "auto"
    llm_model: str = "financialauditai-local"
    llm_timeout_seconds: float = 20.0
    rag_rerank_provider: str = "deterministic-fallback"
    rag_answer_provider: str = "deterministic-fallback"
    auth_secret_key: str = "change-me-local-auth-secret"
    access_token_minutes: int = 480


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
        embedding_api_url=os.getenv("EMBEDDING_API_URL") or None,
        embedding_api_key=os.getenv("EMBEDDING_API_KEY") or None,
        embedding_model=os.getenv("EMBEDDING_MODEL", "financialauditai-embedding"),
        ocr_provider=os.getenv("OCR_PROVIDER", "pymupdf-local"),
        ocr_api_url=os.getenv("OCR_API_URL") or None,
        ocr_api_key=os.getenv("OCR_API_KEY") or None,
        ocr_model=os.getenv("OCR_MODEL", "financialauditai-ocr"),
        ocr_api_version=os.getenv("OCR_API_VERSION", "2024-11-30"),
        ocr_timeout_seconds=float(os.getenv("OCR_TIMEOUT_SECONDS", "30")),
        llm_provider=os.getenv("LLM_PROVIDER", "deterministic-fallback"),
        llm_api_url=os.getenv("LLM_API_URL") or None,
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        llm_api_mode=os.getenv("LLM_API_MODE", "auto"),
        llm_model=os.getenv("LLM_MODEL", "financialauditai-local"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        rag_rerank_provider=os.getenv("RAG_RERANK_PROVIDER", "deterministic-fallback"),
        rag_answer_provider=os.getenv("RAG_ANSWER_PROVIDER", "deterministic-fallback"),
        auth_secret_key=os.getenv("AUTH_SECRET_KEY", "change-me-local-auth-secret"),
        access_token_minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "480")),
    )


settings = get_settings()
