from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentRunCreate(BaseModel):
    task_id: UUID
    workflow_name: str = Field(default="procurement_agent_v1", min_length=1, max_length=120)
    input_refs: dict = Field(default_factory=dict)


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    workflow_name: str
    status: str
    current_state: str
    input_refs: dict
    output_refs: dict
    error: dict | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgentStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_name: str
    step_order: int
    tool_name: str
    status: str
    input_payload: dict
    output_payload: dict
    error: dict | None
    duration_ms: int | None
    created_at: datetime
