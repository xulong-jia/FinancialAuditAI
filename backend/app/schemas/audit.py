from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rule_code: str
    name: str
    version: str
    enabled: bool
    parameters: dict
    description: str | None
    created_at: datetime
    updated_at: datetime


class AuditResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    rule_id: UUID | None
    rule_code: str
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
