from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentRelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    business_key: str
    source_document_id: UUID
    target_document_id: UUID
    relation_type: str
    confidence: float
    evidence: dict
    created_at: datetime
    updated_at: datetime


class LinkDocumentsResult(BaseModel):
    task_id: UUID
    linked_document_count: int
    relation_count: int
    warnings: list[str]
    relations: list[DocumentRelationRead]
