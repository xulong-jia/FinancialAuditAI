"""create tasks and documents

Revision ID: 0001_create_tasks_documents
Revises:
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_create_tasks_documents"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_no", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_no"),
    )
    op.create_index("ix_audit_tasks_task_no", "audit_tasks", ["task_no"])
    op.create_index("ix_audit_tasks_scenario", "audit_tasks", ["scenario"])
    op.create_index("ix_audit_tasks_status", "audit_tasks", ["status"])

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_name", sa.String(length=120), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_ext", sa.String(length=16), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=True),
        sa.Column("upload_status", sa.String(length=32), nullable=False),
        sa.Column("ocr_status", sa.String(length=32), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_documents_task_id", "documents", ["task_id"])
    op.create_index("ix_documents_file_ext", "documents", ["file_ext"])
    op.create_index("ix_documents_file_hash", "documents", ["file_hash"])
    op.create_index("ix_documents_doc_type", "documents", ["doc_type"])


def downgrade() -> None:
    op.drop_index("ix_documents_doc_type", table_name="documents")
    op.drop_index("ix_documents_file_hash", table_name="documents")
    op.drop_index("ix_documents_file_ext", table_name="documents")
    op.drop_index("ix_documents_task_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_audit_tasks_status", table_name="audit_tasks")
    op.drop_index("ix_audit_tasks_scenario", table_name="audit_tasks")
    op.drop_index("ix_audit_tasks_task_no", table_name="audit_tasks")
    op.drop_table("audit_tasks")
