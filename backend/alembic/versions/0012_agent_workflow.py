"""create agent workflow tables

Revision ID: 0012_agent_workflow
Revises: 0011_rule_version
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0012_agent_workflow"
down_revision: str | None = "0011_rule_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_runs" not in existing_tables:
        op.create_table(
            "agent_runs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("workflow_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("current_state", sa.String(length=80), nullable=False),
            sa.Column("input_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("output_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])
        op.create_index("ix_agent_runs_workflow_name", "agent_runs", ["workflow_name"])
        op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
        op.create_index("ix_agent_runs_current_state", "agent_runs", ["current_state"])
    if "agent_steps" not in existing_tables:
        op.create_table(
            "agent_steps",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("step_name", sa.String(length=160), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("tool_name", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
        op.create_index("ix_agent_steps_step_name", "agent_steps", ["step_name"])
        op.create_index("ix_agent_steps_step_order", "agent_steps", ["step_order"])
        op.create_index("ix_agent_steps_tool_name", "agent_steps", ["tool_name"])
        op.create_index("ix_agent_steps_status", "agent_steps", ["status"])


def downgrade() -> None:
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "agent_steps" in existing_tables:
        op.drop_index("ix_agent_steps_status", table_name="agent_steps")
        op.drop_index("ix_agent_steps_tool_name", table_name="agent_steps")
        op.drop_index("ix_agent_steps_step_order", table_name="agent_steps")
        op.drop_index("ix_agent_steps_step_name", table_name="agent_steps")
        op.drop_index("ix_agent_steps_run_id", table_name="agent_steps")
        op.drop_table("agent_steps")
    if "agent_runs" in existing_tables:
        op.drop_index("ix_agent_runs_current_state", table_name="agent_runs")
        op.drop_index("ix_agent_runs_status", table_name="agent_runs")
        op.drop_index("ix_agent_runs_workflow_name", table_name="agent_runs")
        op.drop_index("ix_agent_runs_task_id", table_name="agent_runs")
        op.drop_table("agent_runs")
