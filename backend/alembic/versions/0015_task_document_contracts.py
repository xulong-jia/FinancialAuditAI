"""align task and document contract fields

Revision ID: 0015_task_document_contracts
Revises: 0014_rbac_users_roles
Create Date: 2026-07-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0015_task_document_contracts"
down_revision: str | None = "0014_rbac_users_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    task_columns = {column["name"] for column in inspector.get_columns("audit_tasks")}
    document_columns = {column["name"] for column in inspector.get_columns("documents")}

    if "risk_level" not in task_columns:
        op.add_column("audit_tasks", sa.Column("risk_level", sa.String(length=32), nullable=True))
    if "owner_id" not in task_columns:
        op.add_column("audit_tasks", sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index("ix_audit_tasks_owner_id", "audit_tasks", ["owner_id"])
        op.create_foreign_key("fk_audit_tasks_owner_id_users", "audit_tasks", "users", ["owner_id"], ["id"], ondelete="SET NULL")
    if "reviewer_id" not in task_columns:
        op.add_column("audit_tasks", sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index("ix_audit_tasks_reviewer_id", "audit_tasks", ["reviewer_id"])
        op.create_foreign_key("fk_audit_tasks_reviewer_id_users", "audit_tasks", "users", ["reviewer_id"], ["id"], ondelete="SET NULL")
    if "metadata" not in task_columns:
        op.add_column(
            "audit_tasks",
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
        op.alter_column("audit_tasks", "metadata", server_default=None)

    if "uploaded_by" not in document_columns:
        op.add_column("documents", sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index("ix_documents_uploaded_by", "documents", ["uploaded_by"])
        op.create_foreign_key("fk_documents_uploaded_by_users", "documents", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")
    if "metadata" not in document_columns:
        op.add_column(
            "documents",
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )
        op.alter_column("documents", "metadata", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    task_columns = {column["name"] for column in inspector.get_columns("audit_tasks")}
    document_columns = {column["name"] for column in inspector.get_columns("documents")}

    if "metadata" in document_columns:
        op.drop_column("documents", "metadata")
    if "uploaded_by" in document_columns:
        op.drop_constraint("fk_documents_uploaded_by_users", "documents", type_="foreignkey")
        op.drop_index("ix_documents_uploaded_by", table_name="documents")
        op.drop_column("documents", "uploaded_by")

    if "metadata" in task_columns:
        op.drop_column("audit_tasks", "metadata")
    if "reviewer_id" in task_columns:
        op.drop_constraint("fk_audit_tasks_reviewer_id_users", "audit_tasks", type_="foreignkey")
        op.drop_index("ix_audit_tasks_reviewer_id", table_name="audit_tasks")
        op.drop_column("audit_tasks", "reviewer_id")
    if "owner_id" in task_columns:
        op.drop_constraint("fk_audit_tasks_owner_id_users", "audit_tasks", type_="foreignkey")
        op.drop_index("ix_audit_tasks_owner_id", table_name="audit_tasks")
        op.drop_column("audit_tasks", "owner_id")
    if "risk_level" in task_columns:
        op.drop_column("audit_tasks", "risk_level")
