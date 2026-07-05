from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal["draft", "uploaded", "failed"]
Scenario = Literal["procurement", "sales", "confirmation", "interview"]


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scenario: Scenario = "procurement"
    project_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    fiscal_year: int | None = Field(default=None, ge=1900, le=2100)
    period_start: date | None = None
    period_end: date | None = None
    actor_name: str | None = Field(default=None, max_length=120)


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    project_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    fiscal_year: int | None = Field(default=None, ge=1900, le=2100)
    period_start: date | None = None
    period_end: date | None = None
    status: TaskStatus | None = None
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
    actor_name: str | None
    created_at: datetime
    updated_at: datetime
