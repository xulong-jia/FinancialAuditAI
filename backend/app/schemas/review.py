from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.audit import AuditResultRead
from app.schemas.agent import AgentStepRead
from app.schemas.document import DocumentRead
from app.schemas.extraction import ExtractedFieldRead
from app.schemas.quality import BadCaseType


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
    author_id: UUID | None = None
    author_name: str | None = Field(default=None, max_length=120)
    comment_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=4000)
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    attachment_path: str | None = Field(default=None, max_length=1000)


class ReviewCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    document_id: UUID | None
    audit_result_id: UUID | None
    field_id: UUID | None
    author_id: UUID | None
    author_name: str | None
    comment_type: str
    content: str
    before_value: dict | None
    after_value: dict | None
    attachment_path: str | None
    created_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_name: str | None
    user_id: UUID | None
    task_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    before_value: dict | None
    after_value: dict | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class ReviewQueueItem(BaseModel):
    item_type: Literal["document", "field", "audit_result", "agent_step", "comment"]
    task_id: UUID
    document_id: UUID | None = None
    field_id: UUID | None = None
    audit_result_id: UUID | None = None
    agent_step_id: UUID | None = None
    comment_id: UUID | None = None
    reason: str
    document: DocumentRead | None = None
    field: ExtractedFieldRead | None = None
    audit_result: AuditResultRead | None = None
    agent_step: AgentStepRead | None = None
    comment: ReviewCommentRead | None = None


class ReextractRequest(BaseModel):
    actor_name: str | None = Field(default=None, max_length=120)
    reason: str | None = Field(default=None, max_length=2000)


class BadCaseFromReview(BaseModel):
    task_id: UUID
    document_id: UUID | None = None
    audit_result_id: UUID | None = None
    field_id: UUID | None = None
    agent_step_id: UUID | None = None
    comment_id: UUID | None = None
    case_type: BadCaseType = "rule"
    title: str = Field(min_length=1, max_length=255)
    severity: str = Field(default="medium", min_length=1, max_length=32)
    owner_name: str | None = Field(default=None, max_length=120)
