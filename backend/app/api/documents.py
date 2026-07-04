from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import (
    ClassificationRead,
    DocumentPageRead,
    DocumentRead,
    DocumentUpdate,
    ProcurementDocType,
)
from app.services import classification_service, document_service, ocr_service, task_service

router = APIRouter(tags=["documents"])


@router.post("/tasks/{task_id}/documents", response_model=DocumentRead)
async def upload_document(
    task_id: UUID,
    file: Annotated[UploadFile, File()],
    doc_type_hint: Annotated[ProcurementDocType | None, Form()] = None,
    actor_name: Annotated[str | None, Form(max_length=120)] = None,
    db: Session = Depends(get_db),
):
    return await document_service.save_document(
        db=db,
        task_id=task_id,
        file=file,
        doc_type_hint=doc_type_hint,
        actor_name=actor_name,
    )


@router.get("/tasks/{task_id}/documents", response_model=list[DocumentRead])
def list_documents(task_id: UUID, db: Session = Depends(get_db)):
    task_service.get_task(db, task_id)
    return document_service.list_documents(db, task_id)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: UUID, db: Session = Depends(get_db)):
    return document_service.get_document(db, document_id)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(document_id: UUID, payload: DocumentUpdate, db: Session = Depends(get_db)):
    return classification_service.update_document_classification(db, document_id, payload)


@router.post("/documents/{document_id}/ocr", response_model=DocumentRead)
def run_ocr(document_id: UUID, db: Session = Depends(get_db)):
    return ocr_service.run_ocr(db, document_id)


@router.post("/documents/{document_id}/classify", response_model=ClassificationRead)
def classify_document(document_id: UUID, db: Session = Depends(get_db)):
    return classification_service.classify_document(db, document_id)


@router.get("/documents/{document_id}/pages", response_model=list[DocumentPageRead])
def list_pages(document_id: UUID, db: Session = Depends(get_db)):
    document_service.get_document(db, document_id)
    return ocr_service.list_pages(db, document_id)
