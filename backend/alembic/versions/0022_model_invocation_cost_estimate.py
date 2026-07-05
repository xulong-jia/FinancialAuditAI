"""Add model invocation cost estimate metadata.

Revision ID: 0022_model_invocation_cost_estimate
Revises: 0021_extracted_field_original_values
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0022_model_invocation_cost_estimate"
down_revision = "0021_extracted_field_original_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_invocations")}
    if "cost_estimate" not in existing_columns:
        op.add_column("model_invocations", sa.Column("cost_estimate", sa.JSON(), nullable=True))


def downgrade() -> None:
    existing_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("model_invocations")}
    if "cost_estimate" in existing_columns:
        op.drop_column("model_invocations", "cost_estimate")
