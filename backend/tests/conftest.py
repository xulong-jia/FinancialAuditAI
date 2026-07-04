from collections.abc import Generator
from pathlib import Path
import shutil

import pytest

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.document_service import uploads_root


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    upload_dir = uploads_root()
    if upload_dir.exists():
        shutil.rmtree(upload_dir)

    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()

    yield

    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()

    if upload_dir.exists():
        shutil.rmtree(upload_dir)
