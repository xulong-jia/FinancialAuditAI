from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EvalType = Literal[
    "classification",
    "ocr",
    "extraction",
    "rule",
    "rag",
    "agent",
    "end_to_end",
    "regression",
]


class BadCaseCreate(BaseModel):
    task_id: UUID | None = None
    document_id: UUID | None = None
    case_type: EvalType
    title: str = Field(min_length=1, max_length=255)
    input_payload: dict = Field(default_factory=dict)
    model_output: dict = Field(default_factory=dict)
    expected_output: dict = Field(default_factory=dict)
    root_cause: str | None = Field(default=None, max_length=4000)
    fix_plan: str | None = Field(default=None, max_length=4000)
    status: str = Field(default="open", min_length=1, max_length=32)
    severity: str = Field(default="medium", min_length=1, max_length=32)
    owner_name: str | None = Field(default=None, max_length=120)


class BadCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    input_payload: dict | None = None
    model_output: dict | None = None
    expected_output: dict | None = None
    root_cause: str | None = Field(default=None, max_length=4000)
    fix_plan: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, min_length=1, max_length=32)
    severity: str | None = Field(default=None, min_length=1, max_length=32)
    owner_name: str | None = Field(default=None, max_length=120)


class BadCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID | None
    document_id: UUID | None
    case_type: str
    title: str
    input_payload: dict
    model_output: dict
    expected_output: dict
    root_cause: str | None
    fix_plan: str | None
    status: str
    severity: str
    owner_name: str | None
    created_at: datetime
    updated_at: datetime


class EvaluationRunRequest(BaseModel):
    eval_type: EvalType
    eval_name: str | None = Field(default=None, max_length=160)
    dataset_name: str = Field(default="phase14_synthetic", min_length=1, max_length=160)
    model_name: str | None = Field(default="deterministic-local", max_length=160)
    prompt_version: str | None = Field(default=None, max_length=80)
    rule_version: str | None = Field(default=None, max_length=80)
    created_by: str | None = Field(default=None, max_length=120)


class EvaluationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    eval_name: str
    eval_type: str
    dataset_name: str
    model_name: str | None
    prompt_version: str | None
    rule_version: str | None
    metrics: dict
    sample_count: int
    failed_cases: list[dict]
    report_path: str | None
    created_by: str | None
    created_at: datetime
