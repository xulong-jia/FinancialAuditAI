"""Add quality regression and audit context fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "0019_quality_audit_contract"
down_revision = "0018_review_report_agent_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    bad_case_columns = {column["name"] for column in inspector.get_columns("bad_cases")}
    audit_log_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    bad_case_indexes = {index["name"] for index in inspector.get_indexes("bad_cases")}
    audit_log_indexes = {index["name"] for index in inspector.get_indexes("audit_logs")}
    audit_log_foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("audit_logs")}

    if "in_regression" not in bad_case_columns:
        op.add_column("bad_cases", sa.Column("in_regression", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.alter_column("bad_cases", "in_regression", server_default=None)
    if "ix_bad_cases_in_regression" not in bad_case_indexes:
        op.create_index("ix_bad_cases_in_regression", "bad_cases", ["in_regression"])
    if "validation_result" not in bad_case_columns:
        op.add_column("bad_cases", sa.Column("validation_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if "validated_at" not in bad_case_columns:
        op.add_column("bad_cases", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))

    if "user_id" not in audit_log_columns:
        op.add_column("audit_logs", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    if "fk_audit_logs_user_id_users" not in audit_log_foreign_keys:
        op.create_foreign_key("fk_audit_logs_user_id_users", "audit_logs", "users", ["user_id"], ["id"], ondelete="SET NULL")
    if "ix_audit_logs_user_id" not in audit_log_indexes:
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    if "ip_address" not in audit_log_columns:
        op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=64), nullable=True))
    if "user_agent" not in audit_log_columns:
        op.add_column("audit_logs", sa.Column("user_agent", sa.Text(), nullable=True))

    if "roles" in inspector.get_table_names():
        op.execute(
            """
            UPDATE roles SET permissions = '["read", "read_all", "evaluation:read"]'::jsonb WHERE code = 'viewer';
            UPDATE roles SET permissions = '["read", "project:manage", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run", "review:write", "report:generate", "evaluation:read", "quality:manage", "audit_log:read", "rule:manage", "rag:manage"]'::jsonb
            WHERE code = 'manager';
            """
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    bad_case_columns = {column["name"] for column in inspector.get_columns("bad_cases")}
    audit_log_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    bad_case_indexes = {index["name"] for index in inspector.get_indexes("bad_cases")}
    audit_log_indexes = {index["name"] for index in inspector.get_indexes("audit_logs")}
    audit_log_foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("audit_logs")}

    if "user_agent" in audit_log_columns:
        op.drop_column("audit_logs", "user_agent")
    if "ip_address" in audit_log_columns:
        op.drop_column("audit_logs", "ip_address")
    if "user_id" in audit_log_columns:
        if "ix_audit_logs_user_id" in audit_log_indexes:
            op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
        if "fk_audit_logs_user_id_users" in audit_log_foreign_keys:
            op.drop_constraint("fk_audit_logs_user_id_users", "audit_logs", type_="foreignkey")
        op.drop_column("audit_logs", "user_id")

    if "validated_at" in bad_case_columns:
        op.drop_column("bad_cases", "validated_at")
    if "validation_result" in bad_case_columns:
        op.drop_column("bad_cases", "validation_result")
    if "in_regression" in bad_case_columns:
        if "ix_bad_cases_in_regression" in bad_case_indexes:
            op.drop_index("ix_bad_cases_in_regression", table_name="bad_cases")
        op.drop_column("bad_cases", "in_regression")
