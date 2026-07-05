"""create users roles and user_roles

Revision ID: 0014_rbac_users_roles
Revises: 0013_bad_case_eval
Create Date: 2026-07-05
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "0014_rbac_users_roles"
down_revision: str | None = "0013_bad_case_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE_SEEDS = [
    ("viewer", "Viewer", ["read"]),
    ("analyst", "Analyst", ["read", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run"]),
    ("reviewer", "Reviewer", ["read", "review:write", "audit:run"]),
    ("manager", "Manager", ["read", "report:generate", "evaluation:read", "audit_log:read"]),
    ("admin", "Admin", ["*"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("organization", sa.String(length=255), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if "roles" not in existing_tables:
        op.create_table(
            "roles",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_roles_code", "roles", ["code"], unique=True)
    if "user_roles" not in existing_tables:
        op.create_table(
            "user_roles",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        )
        op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
        op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])

    role_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("permissions", postgresql.JSONB),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing_codes = {row[0] for row in bind.execute(sa.text("select code from roles"))}
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": uuid4(),
            "code": code,
            "name": name,
            "description": f"Default {name.lower()} role",
            "permissions": permissions,
            "created_at": now,
            "updated_at": now,
        }
        for code, name, permissions in ROLE_SEEDS
        if code not in existing_codes
    ]
    if rows:
        op.bulk_insert(role_table, rows)


def downgrade() -> None:
    existing_tables = set(inspect(op.get_bind()).get_table_names())
    if "user_roles" in existing_tables:
        op.drop_index("ix_user_roles_role_id", table_name="user_roles")
        op.drop_index("ix_user_roles_user_id", table_name="user_roles")
        op.drop_table("user_roles")
    if "roles" in existing_tables:
        op.drop_index("ix_roles_code", table_name="roles")
        op.drop_table("roles")
    if "users" in existing_tables:
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
