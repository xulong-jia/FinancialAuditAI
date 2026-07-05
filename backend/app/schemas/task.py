from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal[
    "draft",
    "uploaded",
    "ocr_running",
    "ocr_completed",
    "classified",
    "extracting",
    "extracted",
    "auditing",
    "reviewing",
    "completed",
    "failed",
]
Scenario = Literal["procurement", "sales", "confirmation", "interview", "contract_review"]


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scenario: Scenario = "procurement"
    project_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    fiscal_year: int | None = Field(default=None, ge=1900, le=2100)
    period_start: date | None = None
    period_end: date | None = None
    risk_level: str | None = Field(default=None, max_length=32)
    owner_id: UUID | None = None
    reviewer_id: UUID | None = None
    metadata: dict = Field(default_factory=dict)
    actor_name: str | None = Field(default=None, max_length=120)


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    project_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    fiscal_year: int | None = Field(default=None, ge=1900, le=2100)
    period_start: date | None = None
    period_end: date | None = None
    status: TaskStatus | None = None
    risk_level: str | None = Field(default=None, max_length=32)
    owner_id: UUID | None = None
    reviewer_id: UUID | None = None
    metadata: dict | None = None
    actor_name: str | None = Field(default=None, max_length=120)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_no: str
    name: str
    scenario: str
    project_name: str | None
    company_name: str | None
    fiscal_year: int | None
    period_start: date | None
    period_end: date | None
    status: str
    risk_level: str | None
    owner_id: UUID | None
    reviewer_id: UUID | None
    metadata: dict = Field(default_factory=dict, validation_alias="metadata_json")
    actor_name: str | None
    created_at: datetime
    updated_at: datetime


class TaskRunRead(BaseModel):
    task_id: UUID
    previous_status: str
    status: str
    next_action: str | None
    pending_steps: list[str]
    message: str
