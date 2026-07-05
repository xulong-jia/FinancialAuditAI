from collections.abc import Generator
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

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
    kwargs["headers"] = headers
    return _ORIGINAL_REQUEST(self, method, url, **kwargs)


TestClient.request = _request_with_auth


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    global _AUTH_TOKEN
    Base.metadata.create_all(bind=engine)
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
