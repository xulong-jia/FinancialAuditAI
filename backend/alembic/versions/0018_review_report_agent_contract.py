"""Add review comment author and attachment fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "0018_review_report_agent_contract"
down_revision = "0017_audit_rule_contract"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("review_comments")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("review_comments")}
    indexes = {index["name"] for index in inspector.get_indexes("review_comments")}

    if "author_id" not in columns:
        op.add_column("review_comments", sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True))
    if "attachment_path" not in columns:
        op.add_column("review_comments", sa.Column("attachment_path", sa.Text(), nullable=True))
    if "fk_review_comments_author_id_users" not in foreign_keys:
        op.create_foreign_key(
            "fk_review_comments_author_id_users",
            "review_comments",
            "users",
            ["author_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "ix_review_comments_author_id" not in indexes:
        op.create_index("ix_review_comments_author_id", "review_comments", ["author_id"])


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("review_comments")}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("review_comments")}
    indexes = {index["name"] for index in inspector.get_indexes("review_comments")}

    if "ix_review_comments_author_id" in indexes:
        op.drop_index("ix_review_comments_author_id", table_name="review_comments")
    if "fk_review_comments_author_id_users" in foreign_keys:
        op.drop_constraint("fk_review_comments_author_id_users", "review_comments", type_="foreignkey")
    if "attachment_path" in columns:
        op.drop_column("review_comments", "attachment_path")
    if "author_id" in columns:
        op.drop_column("review_comments", "author_id")
