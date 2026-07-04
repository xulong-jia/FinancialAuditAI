"""create bad case and evaluation tables

Revision ID: 0013_bad_case_eval
Revises: 0012_agent_workflow
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0013_bad_case_eval"
down_revision: str | None = "0012_agent_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "bad_cases" not in existing_tables:
        op.create_table(
            "bad_cases",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("case_type", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("model_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("expected_output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("fix_plan", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("severity", sa.String(length=32), nullable=False),
            sa.Column("owner_name", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_bad_cases_task_id", "bad_cases", ["task_id"])
        op.create_index("ix_bad_cases_document_id", "bad_cases", ["document_id"])
        op.create_index("ix_bad_cases_case_type", "bad_cases", ["case_type"])
        op.create_index("ix_bad_cases_status", "bad_cases", ["status"])
        op.create_index("ix_bad_cases_severity", "bad_cases", ["severity"])
    if "evaluation_results" not in existing_tables:
        op.create_table(
            "evaluation_results",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("eval_name", sa.String(length=160), nullable=False),
            sa.Column("eval_type", sa.String(length=64), nullable=False),
            sa.Column("dataset_name", sa.String(length=160), nullable=False),
            sa.Column("model_name", sa.String(length=160), nullable=True),
            sa.Column("prompt_version", sa.String(length=80), nullable=True),
            sa.Column("rule_version", sa.String(length=80), nullable=True),
            sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("failed_cases", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("report_path", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_evaluation_results_eval_name", "evaluation_results", ["eval_name"])
        op.create_index("ix_evaluation_results_eval_type", "evaluation_results", ["eval_type"])
        op.create_index("ix_evaluation_results_dataset_name", "evaluation_results", ["dataset_name"])


def downgrade() -> None:
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "evaluation_results" in existing_tables:
        op.drop_index("ix_evaluation_results_dataset_name", table_name="evaluation_results")
        op.drop_index("ix_evaluation_results_eval_type", table_name="evaluation_results")
        op.drop_index("ix_evaluation_results_eval_name", table_name="evaluation_results")
        op.drop_table("evaluation_results")
    if "bad_cases" in existing_tables:
        op.drop_index("ix_bad_cases_severity", table_name="bad_cases")
        op.drop_index("ix_bad_cases_status", table_name="bad_cases")
        op.drop_index("ix_bad_cases_case_type", table_name="bad_cases")
        op.drop_index("ix_bad_cases_document_id", table_name="bad_cases")
        op.drop_index("ix_bad_cases_task_id", table_name="bad_cases")
        op.drop_table("bad_cases")
