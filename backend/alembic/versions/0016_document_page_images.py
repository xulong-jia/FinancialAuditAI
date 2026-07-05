"""Add rendered page image path to document pages."""

from alembic import op
import sqlalchemy as sa


revision = "0016_document_page_images"
down_revision = "0015_task_document_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_pages", sa.Column("image_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_pages", "image_path")
