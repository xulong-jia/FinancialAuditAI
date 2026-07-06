"""add task scope to evaluation results

Revision ID: 0023_evaluation_result_scope
Revises: 0022_model_invocation_cost_estimate
Create Date: 2026-07-06
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "0023_evaluation_result_scope"
down_revision: str | None = "0022_model_invocation_cost_estimate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("evaluation_results")}
    indexes = {index["name"] for index in inspector.get_indexes("evaluation_results")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("evaluation_results")}
    if "task_id" not in columns:
        op.add_column("evaluation_results", sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True))
    if "fk_evaluation_results_task_id_audit_tasks" not in foreign_keys:
        op.create_foreign_key(
            "fk_evaluation_results_task_id_audit_tasks",
            "evaluation_results",
            "audit_tasks",
            ["task_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_evaluation_results_task_id" not in indexes:
        op.create_index("ix_evaluation_results_task_id", "evaluation_results", ["task_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("evaluation_results")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("evaluation_results")}
    columns = {column["name"] for column in inspector.get_columns("evaluation_results")}
    if "ix_evaluation_results_task_id" in indexes:
        op.drop_index("ix_evaluation_results_task_id", table_name="evaluation_results")
    if "fk_evaluation_results_task_id_audit_tasks" in foreign_keys:
        op.drop_constraint("fk_evaluation_results_task_id_audit_tasks", "evaluation_results", type_="foreignkey")
    if "task_id" in columns:
        op.drop_column("evaluation_results", "task_id")
