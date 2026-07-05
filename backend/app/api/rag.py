from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import can_access_task_scope, enforce_task_scope, require_permission
from app.db.session import get_db
from app.models.rag_document import RagDocument
from app.models.user import User
from app.schemas.rag import (
    KnowledgeBase,
    RagChunkRead,
    RagDocumentRead,
    RagIndexResult,
    RagQueryRequest,
    RagQueryResponse,
)
from app.services import rag_service

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/documents", response_model=RagDocumentRead)
async def create_rag_document(
    knowledge_base: Annotated[KnowledgeBase, Form()],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    source_type: Annotated[str, Form(min_length=1, max_length=80)],
    source_url: Annotated[str | None, Form()] = None,
    issuer_name: Annotated[str | None, Form(max_length=255)] = None,
    publish_date: Annotated[date | None, Form()] = None,
    effective_date: Annotated[date | None, Form()] = None,
    metadata_json: Annotated[str | None, Form()] = None,
    created_by: Annotated[str | None, Form(max_length=120)] = None,
    content_text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rag:manage")),
):
    metadata = rag_service.parse_metadata_json(metadata_json)
    if knowledge_base == "workpaper":
        _enforce_workpaper_metadata_scope(db, user, metadata, write=True)
    return rag_service._document_read(
        await rag_service.create_document(
            db=db,
            knowledge_base=knowledge_base,
            title=title,
            source_type=source_type,
            source_url=source_url,
            issuer_name=issuer_name,
            publish_date=publish_date,
            effective_date=effective_date,
            metadata=metadata,
            created_by=created_by,
            file=file,
            content_text=content_text,
        ),
        0,
    )


@router.get("/documents", response_model=list[RagDocumentRead])
def list_rag_documents(
    knowledge_base: KnowledgeBase | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("read")),
):
    return [
        document
        for document in rag_service.list_documents(db, knowledge_base)
        if _can_read_rag_document(db, user, document)
    ]


@router.post("/documents/{doc_id}/index", response_model=RagIndexResult)
def index_rag_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("rag:manage")),
):
    document = db.get(RagDocument, doc_id)
    if document is None:
        raise HTTPException(status_code=404, detail="RAG document not found")
    if document.knowledge_base == "workpaper":
        _enforce_workpaper_metadata_scope(db, user, document.metadata_json, write=True)
    return rag_service.index_document(db, doc_id)


@router.post("/query", response_model=RagQueryResponse)
def query_rag(
    payload: RagQueryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("read")),
):
    if payload.knowledge_base == "workpaper":
        task_id = payload.metadata_filter.get("task_id")
        if task_id is None:
            raise HTTPException(status_code=400, detail="workpaper RAG queries require metadata_filter.task_id")
        try:
            scoped_task_id = UUID(str(task_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="workpaper metadata_filter.task_id must be a task UUID") from exc
        enforce_task_scope(db, user, scoped_task_id)
    result = rag_service.query(
        db,
        query_text=payload.query,
        knowledge_base=payload.knowledge_base,
        top_k=payload.top_k,
        metadata_filter=payload.metadata_filter,
        task_id=scoped_task_id if payload.knowledge_base == "workpaper" else None,
    )
    db.commit()
    return result


@router.get("/chunks/{chunk_id}", response_model=RagChunkRead)
def get_rag_chunk(
    chunk_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("read")),
):
    chunk = rag_service.get_chunk(db, chunk_id)
    if chunk["knowledge_base"] == "workpaper":
        task_id = chunk["metadata"].get("task_id")
        if task_id is None:
            raise HTTPException(status_code=403, detail="Workpaper chunk is missing task scope")
        enforce_task_scope(db, user, UUID(str(task_id)))
    return chunk


def _enforce_workpaper_metadata_scope(db: Session, user: User, metadata: dict, *, write: bool = False) -> UUID:
    task_id = metadata.get("task_id")
    if task_id is None:
        raise HTTPException(status_code=400, detail="workpaper RAG documents require metadata.task_id")
    try:
        scoped_task_id = UUID(str(task_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="workpaper metadata.task_id must be a task UUID") from exc
    enforce_task_scope(db, user, scoped_task_id, write=write)
    return scoped_task_id


def _can_read_rag_document(db: Session, user: User, document: dict) -> bool:
    if document.get("knowledge_base") != "workpaper":
        return True
    task_id = (document.get("metadata") or {}).get("task_id")
    if task_id is None:
        return False
    try:
        return can_access_task_scope(db, user, UUID(str(task_id)))
    except ValueError:
        return False
