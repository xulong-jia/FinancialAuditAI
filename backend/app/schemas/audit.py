from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_code: str
    name: str
    version: str
    enabled: bool
    parameters: dict
    category: str
    severity: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class AuditRuleCreate(BaseModel):
    rule_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(default="1.0", min_length=1, max_length=32)
    enabled: bool = True
    parameters: dict = Field(default_factory=dict)
    description: str | None = None
    actor_name: str | None = Field(default=None, max_length=120)


class AuditRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    version: str | None = Field(default=None, min_length=1, max_length=32)
    enabled: bool | None = None
    parameters: dict | None = None
    description: str | None = None
    actor_name: str | None = Field(default=None, max_length=120)


class AuditRuleEvaluateRequest(BaseModel):
    task_id: UUID
    parameters: dict | None = None


class AuditRuleEvaluateResult(BaseModel):
    rule_code: str
    rule_version: str
    business_key: str
    status: str
    severity: str
    message: str
    expected_value: dict | None
    actual_value: dict | None
    evidence: dict


class AuditResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    rule_id: UUID | None
    rule_code: str
    rule_version: str | None
    business_key: str
    status: str
    severity: str
    message: str
    expected_value: dict | None
    actual_value: dict | None
    evidence: dict
    rag_citations: list[dict] | None
    review_status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
