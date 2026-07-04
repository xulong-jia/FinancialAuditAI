#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_page import DocumentPage  # noqa: E402
from app.models.document_relation import DocumentRelation  # noqa: E402
from app.models.extracted_field import ExtractedField  # noqa: E402
from app.schemas.task import TaskCreate  # noqa: E402
from app.services import report_service, rule_engine_service, task_service  # noqa: E402

SEED_PATH = PROJECT_ROOT / "samples" / "procurement" / "demo_seed.json"


def main() -> None:
    seed = json.loads(SEED_PATH.read_text())
    with SessionLocal() as db:
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
