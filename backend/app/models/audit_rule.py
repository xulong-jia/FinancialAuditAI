from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditRule(Base):
    __tablename__ = "audit_rules"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    @property
    def category(self) -> str:
        if self.rule_code.startswith("SALES_"):
            return "sales"
        if self.rule_code.startswith("CONF_"):
            return "confirmation"
        if self.rule_code.startswith("INTERVIEW_"):
            return "interview"
        if self.rule_code.startswith("CONTRACT_"):
            return "contract_review"
        return "procurement"

    @property
    def severity(self) -> str:
        high_rules = {
            "PROC_AMOUNT_001",
            "PROC_QTY_001",
            "SALES_AMOUNT_001",
            "SALES_QTY_001",
            "CONF_DATE_001",
            "CONF_AMOUNT_001",
            "INTERVIEW_AMOUNT_001",
            "CONTRACT_AMOUNT_001",
            "CONTRACT_SPECIAL_CLAUSE_001",
        }
        return "high" if self.rule_code in high_rules else "medium"
