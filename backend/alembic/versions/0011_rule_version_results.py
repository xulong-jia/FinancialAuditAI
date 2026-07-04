"""add audit result rule version

Revision ID: 0011_rule_version
Revises: 0010_rag
Create Date: 2026-07-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0011_rule_version"
down_revision: str | None = "0010_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("audit_results")}
    if "rule_version" not in columns:
        op.add_column("audit_results", sa.Column("rule_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("audit_results")}
    if "rule_version" in columns:
        op.drop_column("audit_results", "rule_version")
