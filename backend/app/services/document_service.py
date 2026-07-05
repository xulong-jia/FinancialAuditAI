from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_task import AuditTask
from app.models.document import Document
from app.schemas.document import DocumentDocType
from app.services import audit_log_service

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
ALLOWED_CONTENT_TYPES = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
KNOWLEDGE_DOC_TYPES = {
    "prospectus",
    "inquiry_letter",
    "regulation",
}
DOC_TYPES_BY_SCENARIO = {
    "procurement": {
        "purchase_request",
        "purchase_contract",
        "warehouse_receipt",
        "invoice",
        "accounting_voucher",
        "payment_receipt",
    }
    | KNOWLEDGE_DOC_TYPES,
    "sales": {
        "sales_contract",
        "sales_order",
        "delivery_order",
        "logistics_receipt",
        "sales_invoice",
        "receipt_voucher",
        "accounting_voucher",
    }
    | KNOWLEDGE_DOC_TYPES,
    "confirmation": {
        "confirmation",
        "confirmation_request",
        "confirmation_reply",
        "confirmation_adjustment",
    }
    | KNOWLEDGE_DOC_TYPES,
    "interview": {
        "interview_record",
        "interview_outline",
        "interview_signature_page",
        "interview_transcript",
    }
    | KNOWLEDGE_DOC_TYPES,
    "contract_review": {
        "contract_review",
        "material_contract",
        "supplemental_agreement",
        "framework_agreement",
        "contract_attachment",
    }
    | KNOWLEDGE_DOC_TYPES,
}


def uploads_root() -> Path:
    return Path(__file__).resolve().parents[3] / "local_storage" / "uploads"


def list_documents(db: Session, task_id: UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.task_id == task_id)
            .order_by(Document.created_at.desc())
        )
    )


def get_document(db: Session, document_id: UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def save_document(
    db: Session,
    task_id: UUID,
    file: UploadFile,
    doc_type_hint: DocumentDocType | None = None,
    actor_name: str | None = None,
    uploaded_by: UUID | None = None,
) -> Document:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if doc_type_hint and doc_type_hint not in DOC_TYPES_BY_SCENARIO.get(task.scenario, set()):
        raise HTTPException(status_code=400, detail="Document type is not allowed for task scenario")

    filename = Path(file.filename or "").name
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension")

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES[extension]:
        raise HTTPException(status_code=400, detail="Unsupported content type")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    if not _has_expected_signature(extension, data):
        raise HTTPException(status_code=400, detail="Uploaded file content does not match extension")

    document_id = uuid4()
    file_hash = sha256(data).hexdigest()
    storage_dir = uploads_root() / str(task_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{document_id}.{extension}"
    storage_path.write_bytes(data)

    document = Document(
        id=document_id,
        task_id=task_id,
        uploaded_by=uploaded_by,
        uploaded_by_name=actor_name,
        original_filename=filename,
        file_ext=extension,
        content_type=content_type,
        file_size=len(data),
        file_hash=file_hash,
        storage_path=str(storage_path.relative_to(Path(__file__).resolve().parents[3])),
        doc_type=doc_type_hint,
        metadata_json={},
    )
    task.status = "uploaded"
    try:
        db.add(document)
        audit_log_service.add_log(
            db,
            actor_name=actor_name,
            task_id=task_id,
            action="document_uploaded",
            target_type="document",
            target_id=document.id,
            after_value={
                "original_filename": filename,
                "doc_type": doc_type_hint,
                "file_ext": extension,
                "file_size": len(data),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise
    db.refresh(document)
    return document


def delete_document(db: Session, document_id: UUID) -> None:
    document = get_document(db, document_id)
    before = {
        "id": str(document.id),
        "task_id": str(document.task_id),
        "original_filename": document.original_filename,
        "storage_path": document.storage_path,
    }
    path = uploads_root().parents[1] / document.storage_path
    db.delete(document)
    audit_log_service.add_log(
        db,
        actor_name=document.uploaded_by_name,
        task_id=document.task_id,
        action="document_deleted",
        target_type="document",
        target_id=document.id,
        before_value=before,
    )
    db.commit()
    if path.exists():
        path.unlink()


def _has_expected_signature(extension: str, data: bytes) -> bool:
    signatures = {
        "pdf": (b"%PDF",),
        "png": (b"\x89PNG\r\n\x1a\n",),
        "jpg": (b"\xff\xd8\xff",),
        "jpeg": (b"\xff\xd8\xff",),
    }
    return any(data.startswith(signature) for signature in signatures.get(extension, ()))
