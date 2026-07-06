from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_code: str
    name: str
    scenario: str
    category: str
    severity: str
    version: str
    enabled: bool
    expression: str
    parameters: dict
    required_fields: list[str]
    description: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class AuditRuleCreate(BaseModel):
    rule_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    scenario: str = Field(default="procurement", min_length=1, max_length=64)
    category: str = Field(default="walkthrough", min_length=1, max_length=64)
    severity: str = Field(default="medium", min_length=1, max_length=32)
    version: str = Field(default="1.0", min_length=1, max_length=32)
    enabled: bool = True
    expression: str | None = None
    parameters: dict = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    description: str | None = None
    actor_name: str | None = Field(default=None, max_length=120)


class AuditRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scenario: str | None = Field(default=None, min_length=1, max_length=64)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    severity: str | None = Field(default=None, min_length=1, max_length=32)
    version: str | None = Field(default=None, min_length=1, max_length=32)
    enabled: bool | None = None
    expression: str | None = None
    parameters: dict | None = None
    required_fields: list[str] | None = None
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
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime
