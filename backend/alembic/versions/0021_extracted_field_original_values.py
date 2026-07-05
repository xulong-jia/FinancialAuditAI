"""Preserve original extracted field values during review.

Revision ID: 0021_extracted_field_original_values
Revises: 0020_final_gap_role_matrix
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0021_extracted_field_original_values"
down_revision = "0020_final_gap_role_matrix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("extracted_fields")}
    if "original_value_text" not in existing_columns:
        op.add_column("extracted_fields", sa.Column("original_value_text", sa.Text(), nullable=True))
    if "original_value_normalized" not in existing_columns:
        op.add_column("extracted_fields", sa.Column("original_value_normalized", sa.JSON(), nullable=True))
    if "original_confidence" not in existing_columns:
        op.add_column("extracted_fields", sa.Column("original_confidence", sa.Float(), nullable=True))
    op.execute(
        """
        UPDATE extracted_fields
        SET
            original_value_text = value_text,
            original_value_normalized = value_normalized,
            original_confidence = confidence
        WHERE original_value_text IS NULL
          AND original_value_normalized IS NULL
          AND original_confidence IS NULL
        """
    )


def downgrade() -> None:
    existing_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("extracted_fields")}
    if "original_confidence" in existing_columns:
        op.drop_column("extracted_fields", "original_confidence")
    if "original_value_normalized" in existing_columns:
        op.drop_column("extracted_fields", "original_value_normalized")
    if "original_value_text" in existing_columns:
        op.drop_column("extracted_fields", "original_value_text")
