#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import uuid4

from sqlalchemy import select  # noqa: E402
from sqlalchemy.engine.url import make_url  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_page import DocumentPage  # noqa: E402
from app.models.document_relation import DocumentRelation  # noqa: E402
from app.models.extracted_field import ExtractedField  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_role import UserRole  # noqa: E402
from app.schemas.auth import UserCreate  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402
from app.services import auth_service, report_service, rule_engine_service, task_service  # noqa: E402

SEED_PATH = PROJECT_ROOT / "samples" / "procurement" / "demo_seed.json"
DEMO_PASSWORD = "Test123456"
DEMO_USERS = (
    ("analyst.demo@example.com", "Demo Analyst", "Analyst", "analyst"),
    ("reviewer.demo@example.com", "Demo Reviewer", "Reviewer", "reviewer"),
    ("admin.demo@example.com", "Demo Admin", "Administrator", "admin"),
)


def main() -> None:
    seed = json.loads(SEED_PATH.read_text())
    with SessionLocal() as db:
        demo_credentials = _ensure_demo_users(db)
        task = task_service.create_task(
            db,
            TaskCreate(
                name=seed["task"]["name"],
                scenario="procurement",
                project_name=seed["task"]["project_name"],
                company_name=seed["task"]["company_name"],
                fiscal_year=seed["task"]["fiscal_year"],
                actor_name=seed["task"]["actor_name"],
            ),
        )
        documents: list[Document] = []
        for document_seed in seed["documents"]:
            document = _create_document(db, task.id, seed["business_key"], document_seed)
            documents.append(document)
            _create_page(db, document, document_seed["fields"])
            _create_fields(db, task.id, document, document_seed["fields"])
        _create_relations(db, task.id, seed["business_key"], documents)
        db.commit()

        results = rule_engine_service.run_audit(db, task.id)
        report = report_service.generate_control_table_report(db, task.id, generated_by="demo_seed")
        print(f"Created demo task: {task.task_no} ({task.id})")
        print(f"Audit results: {len(results)}")
        print(f"Report: {report.storage_path}")
        print(f"Database: {_masked_database_url()}")
        print("Demo accounts ready")
        for email, _role_code in demo_credentials:
            print(f"- {email} / {DEMO_PASSWORD}")


def _ensure_demo_users(db) -> list[tuple[str, str]]:
    auth_service.ensure_default_roles(db)
    created: list[tuple[str, str]] = []
    for email, full_name, title, role_code in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            auth_service.create_user(
                db,
                UserCreate(
                    email=email,
                    password=DEMO_PASSWORD,
                    full_name=full_name,
                    organization="Synthetic Demo",
                    title=title,
                    role_codes=[role_code],
                ),
            )
        else:
            user.password_hash = auth_service.hash_password(DEMO_PASSWORD)
            user.full_name = full_name
            user.organization = "Synthetic Demo"
            user.title = title
            user.status = "active"
            _replace_user_role(db, user, role_code)
            db.commit()
        created.append((email, role_code))
    return created


def _replace_user_role(db, user: User, role_code: str) -> None:
    role = db.scalar(select(Role).where(Role.code == role_code))
    if role is None:
        raise RuntimeError(f"Missing demo role: {role_code}")
    db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    db.add(UserRole(user_id=user.id, role_id=role.id))


def _masked_database_url() -> str:
    return make_url(settings.database_url).render_as_string(hide_password=True)


def _create_document(db, task_id, business_key: str, document_seed: dict) -> Document:
    document_id = uuid4()
    filename = document_seed["original_filename"]
    document = Document(
        id=document_id,
        task_id=task_id,
        uploaded_by_name="demo_seed",
        original_filename=filename,
        file_ext="pdf",
        content_type="application/pdf",
        file_size=0,
        file_hash=sha256(filename.encode()).hexdigest(),
        storage_path=f"samples/procurement/{filename}",
        doc_type=document_seed["doc_type"],
        business_key=business_key,
        doc_type_confidence=1.0,
        classification_reason="Seeded synthetic MVP demo document.",
        alternative_types=[],
        original_classification=None,
        page_count=1,
        upload_status="uploaded",
        ocr_status="completed",
        ocr_error=None,
        extraction_status="completed",
        review_status="not_required",
    )
    db.add(document)
    return document


def _create_page(db, document: Document, fields: dict[str, str]) -> None:
    raw_text = "\n".join(f"{name}: {value}" for name, value in fields.items())
    db.add(
        DocumentPage(
            document_id=document.id,
            page_number=1,
            raw_text=raw_text,
            ocr_blocks=[{"text": raw_text, "bbox": None, "confidence": 1.0}],
            table_blocks=[],
            width=None,
            height=None,
            ocr_engine="seed",
            ocr_confidence=1.0,
            warnings=[],
        )
    )


def _create_fields(db, task_id, document: Document, fields: dict[str, str]) -> None:
    for name, value in fields.items():
        db.add(
            ExtractedField(
                task_id=task_id,
                document_id=document.id,
                field_name=name,
                field_label=name.replace("_", " ").title(),
                field_type=_field_type(name),
                value_text=value,
                value_normalized=_normalized(name, value),
                unit=None,
                currency="CNY" if "amount" in name else None,
                confidence=0.95,
                source_page=1,
                source_bbox=None,
                source_text=f"{name}: {value}",
                extraction_method="seed",
                is_required=True,
                is_verified=False,
                corrected_by=None,
                corrected_at=None,
                warnings=[],
            )
        )


def _create_relations(db, task_id, business_key: str, documents: list[Document]) -> None:
    source = documents[0]
    now = datetime.now(timezone.utc)
    for target in documents[1:]:
        db.add(
            DocumentRelation(
                task_id=task_id,
                business_key=business_key,
                source_document_id=source.id,
                target_document_id=target.id,
                relation_type="seeded_procurement_chain",
                confidence=1.0,
                evidence={"method": "synthetic_seed", "business_key": business_key},
                created_at=now,
                updated_at=now,
            )
        )


def _field_type(name: str) -> str:
    if name.endswith("_date"):
        return "date"
    if "amount" in name:
        return "money"
    if name == "tax_rate":
        return "tax_rate"
    if name == "item_lines":
        return "line_items"
    if name == "currency":
        return "currency"
    if name.endswith("_name"):
        return "name"
    return "text"


def _normalized(name: str, value: str) -> dict:
    if "amount" in name:
        return {"amount": float(value), "currency": "CNY"}
    if name == "tax_rate":
        return {"rate": float(value.rstrip("%")) / 100}
    if name == "item_lines":
        return {"items": [{"item_name": "Demo Widget", "quantity": 10, "unit": "pcs"}]}
    return {"value": value}


if __name__ == "__main__":
    main()
