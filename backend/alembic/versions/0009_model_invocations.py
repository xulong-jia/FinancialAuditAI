"""create model invocations

Revision ID: 0009_model_invocations
Revises: 0008_reports
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0009_model_invocations"
down_revision: str | None = "0008_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "model_invocations" in set(inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "model_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("invocation_type", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_schema", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_model_invocations_task_id", "model_invocations", ["task_id"])
    op.create_index("ix_model_invocations_document_id", "model_invocations", ["document_id"])
    op.create_index("ix_model_invocations_provider", "model_invocations", ["provider"])
    op.create_index("ix_model_invocations_invocation_type", "model_invocations", ["invocation_type"])
    op.create_index("ix_model_invocations_status", "model_invocations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_model_invocations_status", table_name="model_invocations")
    op.drop_index("ix_model_invocations_invocation_type", table_name="model_invocations")
    op.drop_index("ix_model_invocations_provider", table_name="model_invocations")
    op.drop_index("ix_model_invocations_document_id", table_name="model_invocations")
    op.drop_index("ix_model_invocations_task_id", table_name="model_invocations")
    op.drop_table("model_invocations")
