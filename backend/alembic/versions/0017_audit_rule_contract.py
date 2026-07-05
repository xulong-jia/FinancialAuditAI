"""Add audit rule configuration contract fields."""

from alembic import op
import sqlalchemy as sa


revision = "0017_audit_rule_contract"
down_revision = "0016_document_page_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_rules", sa.Column("scenario", sa.String(length=64), nullable=False, server_default="procurement"))
    op.add_column("audit_rules", sa.Column("category", sa.String(length=64), nullable=False, server_default="walkthrough"))
    op.add_column("audit_rules", sa.Column("severity", sa.String(length=32), nullable=False, server_default="medium"))
    op.add_column("audit_rules", sa.Column("expression", sa.Text(), nullable=False, server_default=""))
    op.add_column("audit_rules", sa.Column("required_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column("audit_rules", sa.Column("created_by", sa.String(length=120), nullable=True))
    op.create_index("ix_audit_rules_scenario", "audit_rules", ["scenario"])

    op.execute(
        """
        UPDATE audit_rules
        SET
            scenario = CASE
                WHEN rule_code LIKE 'SALES_%' THEN 'sales'
                WHEN rule_code LIKE 'CONF_%' THEN 'confirmation'
                WHEN rule_code LIKE 'INTERVIEW_%' THEN 'interview'
                WHEN rule_code LIKE 'CONTRACT_%' THEN 'contract_review'
                ELSE 'procurement'
            END,
            category = CASE
                WHEN rule_code LIKE '%MISSING%' THEN 'missing_field'
                WHEN rule_code LIKE '%TIME%' OR rule_code LIKE '%DATE%' OR rule_code LIKE '%PERIOD%' THEN 'time'
                WHEN rule_code LIKE '%AMOUNT%' OR rule_code LIKE '%TAX%' THEN 'amount'
                WHEN rule_code LIKE '%QTY%' OR rule_code LIKE '%ITEM%' THEN 'quantity_item'
                WHEN rule_code LIKE '%NAME%' OR rule_code LIKE '%COUNTERPARTY%' THEN 'name'
                ELSE 'walkthrough'
            END,
            severity = CASE
                WHEN rule_code IN (
                    'PROC_AMOUNT_001', 'PROC_QTY_001', 'SALES_AMOUNT_001', 'SALES_QTY_001',
                    'CONF_DATE_001', 'CONF_AMOUNT_001', 'INTERVIEW_AMOUNT_001',
                    'CONTRACT_AMOUNT_001', 'CONTRACT_SPECIAL_CLAUSE_001'
                ) THEN 'high'
                ELSE 'medium'
            END,
            expression = 'python:' || rule_code
        """
    )


def downgrade() -> None:
    op.drop_index("ix_audit_rules_scenario", table_name="audit_rules")
    op.drop_column("audit_rules", "created_by")
    op.drop_column("audit_rules", "required_fields")
    op.drop_column("audit_rules", "expression")
    op.drop_column("audit_rules", "severity")
    op.drop_column("audit_rules", "category")
    op.drop_column("audit_rules", "scenario")
