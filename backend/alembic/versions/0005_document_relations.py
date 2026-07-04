"""create document relations

Revision ID: 0005_doc_relations
Revises: 0004_extracted_fields
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_doc_relations"
down_revision: str | None = "0004_extracted_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("business_key", sa.String(length=160), nullable=True))
    op.create_index("ix_documents_business_key", "documents", ["business_key"])
    op.create_table(
        "document_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_key", sa.String(length=160), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_document_id"], ["documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_document_relations_task_id", "document_relations", ["task_id"])
    op.create_index("ix_document_relations_business_key", "document_relations", ["business_key"])
    op.create_index(
        "ix_document_relations_source_document_id",
        "document_relations",
        ["source_document_id"],
    )
    op.create_index(
        "ix_document_relations_target_document_id",
        "document_relations",
        ["target_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_relations_target_document_id", table_name="document_relations")
    op.drop_index("ix_document_relations_source_document_id", table_name="document_relations")
    op.drop_index("ix_document_relations_business_key", table_name="document_relations")
    op.drop_index("ix_document_relations_task_id", table_name="document_relations")
    op.drop_table("document_relations")
    op.drop_index("ix_documents_business_key", table_name="documents")
    op.drop_column("documents", "business_key")
