"""create review comments and audit logs

Revision ID: 0007_review
Revises: 0006_audit_rules
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

revision: str = "0007_review"
down_revision: str | None = "0006_audit_rules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    if "review_comments" not in existing_tables:
        _create_review_comments()
    if "audit_logs" not in existing_tables:
        _create_audit_logs()


def _create_review_comments() -> None:
    op.create_table(
        "review_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audit_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("author_name", sa.String(length=120), nullable=True),
        sa.Column("comment_type", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("before_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["audit_result_id"], ["audit_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["field_id"], ["extracted_fields.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_review_comments_task_id", "review_comments", ["task_id"])
    op.create_index("ix_review_comments_document_id", "review_comments", ["document_id"])
    op.create_index("ix_review_comments_audit_result_id", "review_comments", ["audit_result_id"])
    op.create_index("ix_review_comments_field_id", "review_comments", ["field_id"])
    op.create_index("ix_review_comments_comment_type", "review_comments", ["comment_type"])


def _create_audit_logs() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_name", sa.String(length=120), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("before_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_task_id", "audit_logs", ["task_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_target_type", "audit_logs", ["target_type"])
    op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_target_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_task_id", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_review_comments_comment_type", table_name="review_comments")
    op.drop_index("ix_review_comments_field_id", table_name="review_comments")
    op.drop_index("ix_review_comments_audit_result_id", table_name="review_comments")
    op.drop_index("ix_review_comments_document_id", table_name="review_comments")
    op.drop_index("ix_review_comments_task_id", table_name="review_comments")
    op.drop_table("review_comments")
