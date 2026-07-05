from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReportGenerateRequest(BaseModel):
    generated_by: str | None = Field(default=None, max_length=120)
    file_format: Literal["xlsx", "csv"] = "xlsx"


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    report_type: str
    title: str
    status: str
    file_format: str
    storage_path: str
    summary: dict
    generated_by: str | None
    generated_at: datetime
    created_at: datetime
    updated_at: datetime


class ControlTableRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    business_key: str
    scenario: str
    row_data: dict
    overall_status: str
    evidence_refs: list[dict]
    reviewer_comment: str | None
    created_at: datetime
    updated_at: datetime
