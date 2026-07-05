from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


KnowledgeBase = Literal["regulation", "inquiry_case", "prospectus", "workpaper"]


class RagDocumentRead(BaseModel):
    id: UUID
    knowledge_base: KnowledgeBase
    title: str
    source_type: str
    source_url: str | None
    issuer_name: str | None
    publish_date: date | None
    effective_date: date | None
    file_path: str | None
    checksum: str
    metadata: dict
    created_by: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class RagIndexResult(BaseModel):
    document_id: UUID
    knowledge_base: KnowledgeBase
    chunk_count: int


class RagChunkRead(BaseModel):
    id: UUID
    rag_document_id: UUID
    knowledge_base: KnowledgeBase
    title: str
    chunk_index: int
    chunk_text: str
    token_count: int | None
    section_title: str | None
    article_no: str | None
    page_start: int | None
    page_end: int | None
    metadata: dict
    created_at: datetime
    updated_at: datetime


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    knowledge_base: KnowledgeBase
    top_k: int = Field(default=5, ge=1, le=10)
    metadata_filter: dict = Field(default_factory=dict)


class RagCitation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    knowledge_base: KnowledgeBase
    title: str
    section: str | None
    page: int | None
    score: float
    quote: str
    metadata: dict


class RagQueryResponse(BaseModel):
    status: Literal["answer", "no_answer"]
    answer: str
    citations: list[RagCitation]
    limitations: list[str]
    provider_info: dict = Field(default_factory=dict)
