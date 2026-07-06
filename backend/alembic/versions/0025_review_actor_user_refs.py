"""Add reviewer and field corrector user references.

Revision ID: 0025_review_actor_user_refs
Revises: 0024_viewer_role_scope
Create Date: 2026-07-06
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "0025_review_actor_user_refs"
down_revision: str | None = "0024_viewer_role_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return
    if "extracted_fields" in tables:
        field_columns = {column["name"] for column in inspector.get_columns("extracted_fields")}
        field_fks = {fk["name"] for fk in inspector.get_foreign_keys("extracted_fields")}
        field_indexes = {index["name"] for index in inspector.get_indexes("extracted_fields")}
        if "corrected_by_user_id" not in field_columns:
            op.add_column("extracted_fields", sa.Column("corrected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
        if "fk_extracted_fields_corrected_by_user_id_users" not in field_fks:
            op.create_foreign_key(
                "fk_extracted_fields_corrected_by_user_id_users",
                "extracted_fields",
                "users",
                ["corrected_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "ix_extracted_fields_corrected_by_user_id" not in field_indexes:
            op.create_index("ix_extracted_fields_corrected_by_user_id", "extracted_fields", ["corrected_by_user_id"])
    if "audit_results" in tables:
        result_columns = {column["name"] for column in inspector.get_columns("audit_results")}
        result_fks = {fk["name"] for fk in inspector.get_foreign_keys("audit_results")}
        result_indexes = {index["name"] for index in inspector.get_indexes("audit_results")}
        if "reviewed_by_user_id" not in result_columns:
            op.add_column("audit_results", sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
        if "fk_audit_results_reviewed_by_user_id_users" not in result_fks:
            op.create_foreign_key(
                "fk_audit_results_reviewed_by_user_id_users",
                "audit_results",
                "users",
                ["reviewed_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "ix_audit_results_reviewed_by_user_id" not in result_indexes:
            op.create_index("ix_audit_results_reviewed_by_user_id", "audit_results", ["reviewed_by_user_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "extracted_fields" in tables:
        field_columns = {column["name"] for column in inspector.get_columns("extracted_fields")}
        field_fks = {fk["name"] for fk in inspector.get_foreign_keys("extracted_fields")}
        field_indexes = {index["name"] for index in inspector.get_indexes("extracted_fields")}
        if "ix_extracted_fields_corrected_by_user_id" in field_indexes:
            op.drop_index("ix_extracted_fields_corrected_by_user_id", table_name="extracted_fields")
        if "fk_extracted_fields_corrected_by_user_id_users" in field_fks:
            op.drop_constraint("fk_extracted_fields_corrected_by_user_id_users", "extracted_fields", type_="foreignkey")
        if "corrected_by_user_id" in field_columns:
            op.drop_column("extracted_fields", "corrected_by_user_id")
    if "audit_results" in tables:
        result_columns = {column["name"] for column in inspector.get_columns("audit_results")}
        result_fks = {fk["name"] for fk in inspector.get_foreign_keys("audit_results")}
        result_indexes = {index["name"] for index in inspector.get_indexes("audit_results")}
        if "ix_audit_results_reviewed_by_user_id" in result_indexes:
            op.drop_index("ix_audit_results_reviewed_by_user_id", table_name="audit_results")
        if "fk_audit_results_reviewed_by_user_id_users" in result_fks:
            op.drop_constraint("fk_audit_results_reviewed_by_user_id_users", "audit_results", type_="foreignkey")
        if "reviewed_by_user_id" in result_columns:
            op.drop_column("audit_results", "reviewed_by_user_id")
