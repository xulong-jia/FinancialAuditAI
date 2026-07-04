"""create rag knowledge base

Revision ID: 0010_rag
Revises: 0009_model_invocations
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.db.vector import Vector

revision: str = "0010_rag"
down_revision: str | None = "0009_model_invocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "rag_documents" not in existing_tables:
        _create_rag_documents()
    if "rag_chunks" not in existing_tables:
        _create_rag_chunks()


def _create_rag_documents() -> None:
    op.create_table(
        "rag_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("knowledge_base", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("issuer_name", sa.String(length=255), nullable=True),
        sa.Column("publish_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rag_documents_knowledge_base", "rag_documents", ["knowledge_base"])
    op.create_index("ix_rag_documents_title", "rag_documents", ["title"])
    op.create_index("ix_rag_documents_checksum", "rag_documents", ["checksum"])


def _create_rag_chunks() -> None:
    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rag_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base", sa.String(length=32), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(32), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(length=255), nullable=True),
        sa.Column("article_no", sa.String(length=80), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rag_document_id"], ["rag_documents.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rag_chunks_rag_document_id", "rag_chunks", ["rag_document_id"])
    op.create_index("ix_rag_chunks_knowledge_base", "rag_chunks", ["knowledge_base"])
    op.create_index("ix_rag_chunks_metadata", "rag_chunks", ["metadata"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_metadata", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_knowledge_base", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_rag_document_id", table_name="rag_chunks")
    op.drop_table("rag_chunks")
    op.drop_index("ix_rag_documents_checksum", table_name="rag_documents")
    op.drop_index("ix_rag_documents_title", table_name="rag_documents")
    op.drop_index("ix_rag_documents_knowledge_base", table_name="rag_documents")
    op.drop_table("rag_documents")
