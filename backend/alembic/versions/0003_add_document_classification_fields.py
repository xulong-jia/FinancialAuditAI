"""add document classification fields

Revision ID: 0003_doc_classification
Revises: 0002_create_document_pages
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_doc_classification"
down_revision: str | None = "0002_create_document_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_type_confidence", sa.Float(), nullable=True))
    op.add_column("documents", sa.Column("classification_reason", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("alternative_types", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("original_classification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "original_classification")
    op.drop_column("documents", "alternative_types")
    op.drop_column("documents", "classification_reason")
    op.drop_column("documents", "doc_type_confidence")
