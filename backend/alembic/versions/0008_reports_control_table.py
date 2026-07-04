"""create reports and control table rows

Revision ID: 0008_reports
Revises: 0007_review
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0008_reports"
down_revision: str | None = "0007_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "control_table_rows" not in existing_tables:
        _create_control_table_rows()
    if "reports" not in existing_tables:
        _create_reports()


def _create_control_table_rows() -> None:
    op.create_table(
        "control_table_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_key", sa.String(length=160), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("row_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_status", sa.String(length=32), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reviewer_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_control_table_rows_task_id", "control_table_rows", ["task_id"])
    op.create_index("ix_control_table_rows_business_key", "control_table_rows", ["business_key"])
    op.create_index("ix_control_table_rows_scenario", "control_table_rows", ["scenario"])
    op.create_index("ix_control_table_rows_overall_status", "control_table_rows", ["overall_status"])


def _create_reports() -> None:
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_by", sa.String(length=120), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reports_task_id", "reports", ["task_id"])
    op.create_index("ix_reports_report_type", "reports", ["report_type"])
    op.create_index("ix_reports_status", "reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_report_type", table_name="reports")
    op.drop_index("ix_reports_task_id", table_name="reports")
    op.drop_table("reports")

    op.drop_index("ix_control_table_rows_overall_status", table_name="control_table_rows")
    op.drop_index("ix_control_table_rows_scenario", table_name="control_table_rows")
    op.drop_index("ix_control_table_rows_business_key", table_name="control_table_rows")
    op.drop_index("ix_control_table_rows_task_id", table_name="control_table_rows")
    op.drop_table("control_table_rows")
