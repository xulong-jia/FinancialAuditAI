from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentRead, ProcurementDocType
from app.services import document_service, task_service

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
