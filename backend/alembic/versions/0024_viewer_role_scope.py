"""Align viewer role scope with read-only object permissions.

Revision ID: 0024_viewer_role_scope
Revises: 0023_evaluation_result_scope
Create Date: 2026-07-06
"""

from typing import Sequence

from alembic import op
from sqlalchemy import inspect


revision: str = "0024_viewer_role_scope"
down_revision: str | None = "0023_evaluation_result_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "roles" not in inspect(op.get_bind()).get_table_names():
        return
    op.execute("UPDATE roles SET permissions = '[\"read\", \"evaluation:read\"]'::jsonb WHERE code = 'viewer'")


def downgrade() -> None:
    if "roles" not in inspect(op.get_bind()).get_table_names():
        return
    op.execute("UPDATE roles SET permissions = '[\"read\", \"evaluation:read\"]'::jsonb WHERE code = 'viewer'")
