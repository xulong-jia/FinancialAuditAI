from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import enforce_document_scope, enforce_task_scope, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.audit import AuditResultRead
from app.schemas.document import (
    ClassificationRead,
    DocumentPageRead,
    DocumentRead,
    DocumentUpdate,
    DocumentDocType,
)
from app.schemas.extraction import ExtractedFieldRead
from app.schemas.linkage import DocumentRelationRead, LinkDocumentsResult
from app.services import (
    classification_service,
    document_service,
    extraction_service,
    linkage_service,
    ocr_service,
    rule_engine_service,
    task_service,
)

router = APIRouter(tags=["documents"])


@router.post("/tasks/{task_id}/documents", response_model=DocumentRead)
async def upload_document(
    task_id: UUID,
    file: Annotated[UploadFile, File()],
    doc_type_hint: Annotated[DocumentDocType | None, Form()] = None,
    actor_name: Annotated[str | None, Form(max_length=120)] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:upload")),
):
    enforce_task_scope(db, user, task_id, write=True)
    return await document_service.save_document(
        db=db,
        task_id=task_id,
        file=file,
        doc_type_hint=doc_type_hint,
        actor_name=actor_name,
        uploaded_by=user.id,
    )


@router.get("/tasks/{task_id}/documents", response_model=list[DocumentRead])
def list_documents(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_task_scope(db, user, task_id)
    return document_service.list_documents(db, task_id)


@router.get("/tasks/{task_id}/fields", response_model=list[ExtractedFieldRead])
def list_task_fields(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_task_scope(db, user, task_id)
    return extraction_service.list_task_fields(db, task_id)


@router.post("/tasks/{task_id}/link-documents", response_model=LinkDocumentsResult)
def link_task_documents(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("document:process"))):
    enforce_task_scope(db, user, task_id, write=True)
    return linkage_service.link_documents(db, task_id)


@router.get("/tasks/{task_id}/document-relations", response_model=list[DocumentRelationRead])
def list_task_document_relations(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_task_scope(db, user, task_id)
    return linkage_service.list_document_relations(db, task_id)


@router.post("/tasks/{task_id}/audit", response_model=list[AuditResultRead])
def run_task_audit(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("audit:run"))):
    enforce_task_scope(db, user, task_id, write=True)
    return rule_engine_service.run_audit(db, task_id)


@router.get("/tasks/{task_id}/audit-results", response_model=list[AuditResultRead])
def list_task_audit_results(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_task_scope(db, user, task_id)
    return rule_engine_service.list_audit_results(db, task_id)


@router.get("/audit-results/{result_id}", response_model=AuditResultRead)
def get_audit_result(result_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    result = rule_engine_service.get_audit_result(db, result_id)
    enforce_task_scope(db, user, result.task_id)
    return result


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_document_scope(db, user, document_id)
    return document_service.get_document(db, document_id)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: UUID,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("document:process")),
):
    enforce_document_scope(db, user, document_id, write=True)
    return classification_service.update_document_classification(db, document_id, payload)


@router.delete("/documents/{document_id}", response_model=dict)
def delete_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("document:upload"))):
    enforce_document_scope(db, user, document_id, write=True)
    document_service.delete_document(db, document_id)
    return {"status": "deleted"}


@router.post("/documents/{document_id}/ocr", response_model=DocumentRead)
def run_ocr(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("document:process"))):
    enforce_document_scope(db, user, document_id, write=True)
    return ocr_service.run_ocr(db, document_id)


@router.post("/documents/{document_id}/classify", response_model=ClassificationRead)
def classify_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("document:process"))):
    enforce_document_scope(db, user, document_id, write=True)
    return classification_service.classify_document(db, document_id)


@router.post("/documents/{document_id}/extract", response_model=list[ExtractedFieldRead])
def extract_document(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("document:process"))):
    enforce_document_scope(db, user, document_id, write=True)
    return extraction_service.extract_document(db, document_id)


@router.get("/documents/{document_id}/fields", response_model=list[ExtractedFieldRead])
def list_document_fields(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_document_scope(db, user, document_id)
    return extraction_service.list_document_fields(db, document_id)


@router.get("/documents/{document_id}/pages", response_model=list[DocumentPageRead])
def list_pages(document_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_document_scope(db, user, document_id)
    return ocr_service.list_pages(db, document_id)


@router.get("/documents/{document_id}/pages/{page_number}/image")
def get_page_image(document_id: UUID, page_number: int, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_document_scope(db, user, document_id)
    page = next(
        (item for item in ocr_service.list_pages(db, document_id) if item.page_number == page_number),
        None,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Document page not found")
    if not page.image_path:
        raise HTTPException(status_code=404, detail="Document page image not found")
    image_path = ocr_service.project_root() / page.image_path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Document page image not found")
    return FileResponse(image_path, media_type="image/png")
