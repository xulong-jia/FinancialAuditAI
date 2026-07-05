from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
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


@router.post("/documents", response_model=RagDocumentRead, dependencies=[Depends(require_permission("rag:manage"))])
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
):
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
            metadata=rag_service.parse_metadata_json(metadata_json),
            created_by=created_by,
            file=file,
            content_text=content_text,
        ),
        0,
    )


@router.get("/documents", response_model=list[RagDocumentRead], dependencies=[Depends(require_permission("read"))])
def list_rag_documents(knowledge_base: KnowledgeBase | None = None, db: Session = Depends(get_db)):
    return rag_service.list_documents(db, knowledge_base)


@router.post("/documents/{doc_id}/index", response_model=RagIndexResult, dependencies=[Depends(require_permission("rag:manage"))])
def index_rag_document(doc_id: UUID, db: Session = Depends(get_db)):
    return rag_service.index_document(db, doc_id)


@router.post("/query", response_model=RagQueryResponse, dependencies=[Depends(require_permission("read"))])
def query_rag(payload: RagQueryRequest, db: Session = Depends(get_db)):
    return rag_service.query(
        db,
        query_text=payload.query,
        knowledge_base=payload.knowledge_base,
        top_k=payload.top_k,
        metadata_filter=payload.metadata_filter,
    )


@router.get("/chunks/{chunk_id}", response_model=RagChunkRead, dependencies=[Depends(require_permission("read"))])
def get_rag_chunk(chunk_id: UUID, db: Session = Depends(get_db)):
    return rag_service.get_chunk(db, chunk_id)
