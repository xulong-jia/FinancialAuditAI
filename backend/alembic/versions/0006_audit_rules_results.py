"""create audit rules and results

Revision ID: 0006_audit_rules
Revises: 0005_doc_relations
Create Date: 2026-07-04
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_audit_rules"
down_revision: str | None = "0005_doc_relations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RULES = [
    ("PROC_MISSING_001", "必填字段缺失检查", {}),
    ("PROC_TIME_001", "采购时间顺序检查", {}),
    ("PROC_AMOUNT_001", "金额一致性检查", {"tolerance": 1.0}),
    ("PROC_NAME_001", "主体名称一致性检查", {"mismatch_status": "warning"}),
    ("PROC_QTY_001", "数量一致性检查", {"tolerance": 0.0001}),
    ("PROC_TAX_001", "税率与税额基础校验", {"tolerance": 1.0}),
]


def upgrade() -> None:
    op.create_table(
        "audit_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rule_code"),
    )
    op.create_index("ix_audit_rules_rule_code", "audit_rules", ["rule_code"])

    op.create_table(
        "audit_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("business_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actual_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rag_citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by", sa.String(length=120), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["audit_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["audit_rules.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_results_task_id", "audit_results", ["task_id"])
    op.create_index("ix_audit_results_rule_id", "audit_results", ["rule_id"])
    op.create_index("ix_audit_results_rule_code", "audit_results", ["rule_code"])
    op.create_index("ix_audit_results_business_key", "audit_results", ["business_key"])
    op.create_index("ix_audit_results_status", "audit_results", ["status"])

    now = datetime.now(timezone.utc)
    audit_rules = sa.table(
        "audit_rules",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("rule_code", sa.String),
        sa.column("name", sa.String),
        sa.column("version", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("parameters", postgresql.JSONB),
        sa.column("description", sa.Text),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        audit_rules,
        [
            {
                "id": uuid4(),
                "rule_code": code,
                "name": name,
                "version": "1.0",
                "enabled": True,
                "parameters": parameters,
                "description": name,
                "created_at": now,
                "updated_at": now,
            }
            for code, name, parameters in RULES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_results_status", table_name="audit_results")
    op.drop_index("ix_audit_results_business_key", table_name="audit_results")
    op.drop_index("ix_audit_results_rule_code", table_name="audit_results")
    op.drop_index("ix_audit_results_rule_id", table_name="audit_results")
    op.drop_index("ix_audit_results_task_id", table_name="audit_results")
    op.drop_table("audit_results")
    op.drop_index("ix_audit_rules_rule_code", table_name="audit_rules")
    op.drop_table("audit_rules")
