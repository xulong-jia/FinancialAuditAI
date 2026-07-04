from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.audit import AuditResultRead
from app.schemas.extraction import ExtractedFieldRead


class FieldCorrection(BaseModel):
    value_text: str | None = None
    value_normalized: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    actor_name: str | None = Field(default=None, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewAction(BaseModel):
    actor_name: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=2000)


class DismissReviewAction(BaseModel):
    actor_name: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=1, max_length=2000)


class ReviewCommentCreate(BaseModel):
    task_id: UUID
    document_id: UUID | None = None
    audit_result_id: UUID | None = None
    field_id: UUID | None = None
    author_name: str | None = Field(default=None, max_length=120)
    comment_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=4000)
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None


class ReviewCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    document_id: UUID | None
    audit_result_id: UUID | None
    field_id: UUID | None
    author_name: str | None
    comment_type: str
    content: str
    before_value: dict | None
    after_value: dict | None
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_name: str | None
    task_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    before_value: dict | None
    after_value: dict | None
    created_at: datetime


class ReviewQueueItem(BaseModel):
    item_type: Literal["field", "audit_result"]
    task_id: UUID
    document_id: UUID | None = None
    field_id: UUID | None = None
    audit_result_id: UUID | None = None
    reason: str
    field: ExtractedFieldRead | None = None
    audit_result: AuditResultRead | None = None
