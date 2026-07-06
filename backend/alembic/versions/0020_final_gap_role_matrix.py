"""Align default role permissions for final gap review.

Revision ID: 0020_final_gap_role_matrix
Revises: 0019_quality_audit_contract
Create Date: 2026-07-05
"""

from alembic import op
from sqlalchemy import inspect


revision = "0020_final_gap_role_matrix"
down_revision = "0019_quality_audit_contract"
branch_labels = None
depends_on = None


ROLE_PERMISSIONS = {
    "viewer": '["read", "evaluation:read"]',
    "analyst": '["read", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run", "report:generate", "evaluation:read", "field:correct"]',
    "reviewer": '["read", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run", "review:write", "report:generate", "evaluation:read"]',
    "manager": '["read", "project:manage", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run", "review:write", "report:generate", "evaluation:read", "quality:manage", "audit_log:read", "rule:manage", "rag:manage"]',
    "admin": '["*"]',
}


def upgrade() -> None:
    if "roles" not in inspect(op.get_bind()).get_table_names():
        return
    for code, permissions in ROLE_PERMISSIONS.items():
        op.execute(f"UPDATE roles SET permissions = '{permissions}'::jsonb WHERE code = '{code}'")


def downgrade() -> None:
    pass
