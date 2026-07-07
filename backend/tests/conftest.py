from collections.abc import Generator
import os
from pathlib import Path
import shutil

TEST_PROVIDER_ENV = {
    "ENVIRONMENT": "test",
    "TESTING": "true",
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
os.environ.update(TEST_PROVIDER_ENV)

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.schemas.auth import UserCreate
from app.services import auth_service
from app.services.document_service import uploads_root
from app.services.report_service import reports_root

_AUTH_TOKEN: str | None = None
_ORIGINAL_REQUEST = TestClient.request


def _request_with_auth(self, method: str, url, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    if _AUTH_TOKEN and "authorization" not in {key.lower() for key in headers}:
        headers["Authorization"] = f"Bearer {_AUTH_TOKEN}"
    if "x-api-raw" not in {key.lower() for key in headers}:
        headers["X-Api-Raw"] = "1"
    kwargs["headers"] = headers
    return _ORIGINAL_REQUEST(self, method, url, **kwargs)


TestClient.request = _request_with_auth


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    global _AUTH_TOKEN
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _align_postgres_schema_for_tests()
    upload_dir = uploads_root()
    report_dir = reports_root()
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    if report_dir.exists():
        shutil.rmtree(report_dir)

    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        admin = auth_service.create_user(
            db,
            UserCreate(
                email="admin@example.com",
                password="admin-password",
                full_name="Test Admin",
                role_codes=["admin"],
            ),
        )
        _AUTH_TOKEN = auth_service.create_access_token(admin)

    yield

    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    _AUTH_TOKEN = None

    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    if report_dir.exists():
        shutil.rmtree(report_dir)


def _align_postgres_schema_for_tests() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE rag_documents ALTER COLUMN metadata TYPE jsonb USING metadata::jsonb"))
        connection.execute(text("ALTER TABLE rag_chunks ALTER COLUMN metadata TYPE jsonb USING metadata::jsonb"))
