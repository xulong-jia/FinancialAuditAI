from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
import re
from typing import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import redact
from app.models.audit_log import AuditLog
from app.models.audit_result import AuditResult
from app.models.audit_rule import AuditRule
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.schemas.rag import KnowledgeBase
from app.services import audit_log_service, llm_provider, model_invocation_service, rag_service
from app.services.extraction_service import schema_specs_for


@dataclass(frozen=True)
class EvidenceRef:
    document_id: UUID | None
    doc_type: str | None
    field_name: str
    value: object
    source_page: int | None = None
    source_text: str | None = None
    source_bbox: list[float] | None = None
    confidence: float | None = None


@dataclass
class RuleResult:
    rule_code: str
    business_key: str
    status: str
    severity: str
    message: str
    expected_value: dict | None
    actual_value: dict | None
    evidence: list[EvidenceRef]


@dataclass
class RuleContext:
    task_id: UUID
    scenario: str
    business_key: str
    documents: list[Document]
    fields: dict[UUID, dict[str, ExtractedField]]
    parameters: dict
    period_start: date | None = None
    period_end: date | None = None


RuleFunc = Callable[[RuleContext], RuleResult]
TOLERANCE = 1.0
RAG_KNOWLEDGE_BASES: tuple[KnowledgeBase, ...] = ("regulation", "inquiry_case", "prospectus", "workpaper")
DEFAULT_RULES = {
    "PROC_MISSING_001": {"name": "必填字段缺失检查", "category": "missing_field", "severity": "medium", "parameters": {}},
    "PROC_TIME_001": {"name": "采购时间顺序检查", "category": "time", "severity": "high", "parameters": {"date_tolerance_days": 0}},
    "PROC_AMOUNT_001": {"name": "金额一致性检查", "category": "amount", "severity": "high", "parameters": {"tolerance_amount": 1.0, "tolerance_ratio": 0.0, "amount_basis": "including_tax"}},
    "PROC_NAME_001": {"name": "主体名称一致性检查", "category": "name", "severity": "medium", "parameters": {"mismatch_status": "warning", "supplier_aliases": {}}},
    "PROC_ITEM_001": {"name": "品种一致性检查", "category": "quantity_item", "severity": "high", "parameters": {"item_mappings": {}}},
    "PROC_QTY_001": {"name": "数量一致性检查", "category": "quantity_item", "severity": "high", "parameters": {"tolerance_amount": 0.0001, "item_mappings": {}}},
    "PROC_TAX_001": {"name": "税率与税额基础校验", "category": "amount", "severity": "high", "parameters": {"tolerance_amount": 1.0, "allowed_tax_rates": []}},
    "SALES_MISSING_001": {"name": "销售必填字段缺失检查", "category": "missing_field", "severity": "medium", "parameters": {}},
    "SALES_TIME_001": {"name": "销售时间顺序检查", "category": "time", "severity": "medium", "parameters": {"date_tolerance_days": 0}},
    "SALES_AMOUNT_001": {"name": "销售金额一致性检查", "category": "amount", "severity": "high", "parameters": {"tolerance_amount": 1.0, "tolerance_ratio": 0.0}},
    "SALES_NAME_001": {"name": "销售客户名称一致性检查", "category": "name", "severity": "medium", "parameters": {"mismatch_status": "warning", "supplier_aliases": {}}},
    "SALES_QTY_001": {"name": "销售数量一致性检查", "category": "quantity_item", "severity": "high", "parameters": {"tolerance_amount": 0.0001, "item_mappings": {}}},
    "SALES_REVENUE_001": {"name": "销售收入确认截止检查", "category": "cutoff", "severity": "high", "parameters": {"recognition_max_days_after_signed": 30}},
    "CONF_MISSING_001": {"name": "函证必填字段缺失检查", "category": "missing_field", "severity": "medium", "parameters": {}},
    "CONF_DATE_001": {"name": "函证回函日期检查", "category": "time", "severity": "high", "parameters": {"date_tolerance_days": 0}},
    "CONF_AMOUNT_001": {"name": "函证金额与差异调节检查", "category": "amount", "severity": "high", "parameters": {"tolerance_amount": 1.0}},
    "CONF_NAME_001": {"name": "函证被函证方名称一致性检查", "category": "name", "severity": "medium", "parameters": {"mismatch_status": "warning", "supplier_aliases": {}}},
    "CONF_SEAL_SIGN_001": {"name": "函证公章签字风险提示", "category": "evidence", "severity": "medium", "parameters": {}},
    "INTERVIEW_MISSING_001": {"name": "访谈核心字段缺失检查", "category": "missing_field", "severity": "medium", "parameters": {}},
    "INTERVIEW_DATE_001": {"name": "访谈日期范围检查", "category": "time", "severity": "medium", "parameters": {}},
    "INTERVIEW_SIGNATURE_001": {"name": "访谈签字检查", "category": "evidence", "severity": "medium", "parameters": {}},
    "INTERVIEW_AMOUNT_001": {"name": "访谈提及金额差异提示", "category": "amount", "severity": "high", "parameters": {"tolerance_amount": 1.0, "tolerance_ratio": 0.0}},
    "INTERVIEW_COUNTERPARTY_001": {"name": "访谈提及主体匹配提示", "category": "name", "severity": "medium", "parameters": {"supplier_aliases": {}}},
    "CONTRACT_MISSING_001": {"name": "合同核心字段缺失检查", "category": "missing_field", "severity": "medium", "parameters": {}},
    "CONTRACT_PERIOD_001": {"name": "合同有效期覆盖检查", "category": "time", "severity": "medium", "parameters": {}},
    "CONTRACT_AMOUNT_001": {"name": "合同金额与任务内金额基础比对", "category": "amount", "severity": "high", "parameters": {"tolerance_amount": 1.0, "tolerance_ratio": 0.0}},
    "CONTRACT_COUNTERPARTY_001": {"name": "合同主体与任务内主体基础比对", "category": "name", "severity": "medium", "parameters": {"supplier_aliases": {}}},
    "CONTRACT_KEY_TERMS_001": {"name": "合同关键条款缺失检查", "category": "missing_field", "severity": "medium", "parameters": {}},
    "CONTRACT_SPECIAL_CLAUSE_001": {"name": "合同特殊条款风险提示", "category": "contract_clause", "severity": "high", "parameters": {}},
    "CONTRACT_SIGNATURE_SEAL_001": {"name": "合同签字盖章缺失提示", "category": "evidence", "severity": "medium", "parameters": {}},
}
ALLOWED_PARAMETER_KEYS = {
    "tolerance",
    "tolerance_amount",
    "tolerance_ratio",
    "allowed_tax_rates",
    "supplier_aliases",
    "item_mappings",
    "amount_basis",
    "prepayment_allowed",
    "date_tolerance_days",
    "recognition_max_days_after_signed",
    "mismatch_status",
    "required_fields",
}


def run_audit(db: Session, task_id: UUID) -> list[AuditResult]:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    rules = list_rules(db)
    enabled_rules = [
        rule
        for rule in rules
        if rule.enabled and _rule_callable(rule) and _rule_matches_scenario(rule, task.scenario)
    ]
    if not enabled_rules:
        raise HTTPException(status_code=400, detail="No enabled rules are available for task scenario")

    documents = _list_documents(db, task_id)
    groups = _business_groups(documents)
    if not groups:
        raise HTTPException(status_code=400, detail="Task has no linked business documents")

    fields = _field_map(_list_fields(db, task_id))
    db.query(AuditResult).filter(AuditResult.task_id == task_id).delete()

    for business_key, group_documents in groups.items():
        for rule in enabled_rules:
            context = RuleContext(
                task_id=task_id,
                scenario=task.scenario,
                business_key=business_key,
                documents=group_documents,
                fields=fields,
                parameters=_rule_parameters(rule),
                period_start=task.period_start,
                period_end=task.period_end,
            )
            result = _rule_callable(rule)(context)
            model = _to_model(task_id, rule, result)
            model.rag_citations = _rag_citations_for_result(db, model)
            db.add(model)

    audit_log_service.add_log(
        db,
        actor_name=task.actor_name,
        task_id=task_id,
        action="audit_rules_run",
        target_type="task",
        target_id=task_id,
        after_value={"rule_count": len(enabled_rules), "business_group_count": len(groups)},
    )
    db.commit()
    return list_audit_results(db, task_id)


def list_audit_results(db: Session, task_id: UUID) -> list[AuditResult]:
    return list(
        db.scalars(
            select(AuditResult)
            .where(AuditResult.task_id == task_id)
            .order_by(AuditResult.business_key.asc(), AuditResult.rule_code.asc())
        )
    )


def get_audit_result(db: Session, result_id: UUID) -> AuditResult:
    result = db.get(AuditResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Audit result not found")
    return result


def list_rules(db: Session) -> list[AuditRule]:
    existing = list(db.scalars(select(AuditRule).order_by(AuditRule.rule_code.asc())))
    existing_codes = {rule.rule_code for rule in existing}
    for rule in existing:
        defaults = _default_rule(rule.rule_code)
        if defaults is None:
            continue
        if not rule.expression:
            rule.expression = defaults["expression"]
        if not rule.scenario:
            rule.scenario = defaults["scenario"]
        if not rule.category:
            rule.category = defaults["category"]
        if not rule.severity:
            rule.severity = defaults["severity"]
        if not rule.required_fields:
            rule.required_fields = defaults["required_fields"]
    for code in DEFAULT_RULES:
        if code not in existing_codes:
            defaults = _default_rule(code)
            db.add(
                AuditRule(
                    rule_code=code,
                    name=defaults["name"],
                    scenario=defaults["scenario"],
                    category=defaults["category"],
                    severity=defaults["severity"],
                    version=defaults["version"],
                    enabled=defaults["enabled"],
                    expression=defaults["expression"],
                    parameters=defaults["parameters"],
                    required_fields=defaults["required_fields"],
                    description=defaults["description"],
                )
            )
    db.commit()
    return list(db.scalars(select(AuditRule).order_by(AuditRule.rule_code.asc())))


def create_rule(
    db: Session,
    *,
    rule_code: str,
    name: str,
    scenario: str,
    category: str,
    severity: str,
    version: str,
    enabled: bool,
    expression: str | None,
    parameters: dict,
    required_fields: list[str],
    description: str | None,
    actor_name: str | None = None,
) -> AuditRule:
    expression = expression or f"python:{rule_code}"
    _validate_rule_contract(rule_code, scenario, category, severity, expression, required_fields)
    if db.scalar(select(AuditRule).where(AuditRule.rule_code == rule_code)) is not None:
        raise HTTPException(status_code=400, detail="Rule already exists")
    _validate_parameters(parameters)
    rule = AuditRule(
        rule_code=rule_code,
        name=name,
        scenario=scenario,
        category=category,
        severity=severity,
        version=version,
        enabled=enabled,
        expression=expression,
        parameters=parameters,
        required_fields=required_fields,
        description=description,
        created_by=actor_name,
    )
    db.add(rule)
    db.flush()
    _add_rule_log(db, actor_name, "audit_rule_created", rule.id, None, _rule_snapshot(rule))
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(
    db: Session,
    rule_id: UUID,
    *,
    name: str | None = None,
    scenario: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    version: str | None = None,
    enabled: bool | None = None,
    expression: str | None = None,
    parameters: dict | None = None,
    required_fields: list[str] | None = None,
    description: str | None = None,
    actor_name: str | None = None,
) -> AuditRule:
    rule = db.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    before = _rule_snapshot(rule)
    if name is not None:
        rule.name = name
    if scenario is not None:
        rule.scenario = scenario
    if category is not None:
        rule.category = category
    if severity is not None:
        rule.severity = severity
    if version is not None:
        rule.version = version
    if enabled is not None:
        rule.enabled = enabled
    if expression is not None:
        rule.expression = expression
    if parameters is not None:
        _validate_parameters(parameters)
        rule.parameters = parameters
    if required_fields is not None:
        rule.required_fields = required_fields
    if description is not None:
        rule.description = description
    _validate_rule_contract(rule.rule_code, rule.scenario, rule.category, rule.severity, rule.expression, rule.required_fields)
    rule.updated_at = utc_now()
    after = _rule_snapshot(rule)
    _add_rule_log(db, actor_name, "audit_rule_updated", rule.id, before, after)
    db.commit()
    db.refresh(rule)
    return rule


def evaluate_rule(db: Session, rule_id: UUID, task_id: UUID, parameters: dict | None = None) -> list[dict]:
    rule = db.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule_func = _rule_callable(rule)
    if rule_func is None:
        raise HTTPException(status_code=400, detail="Rule expression is not supported")
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _rule_matches_scenario(rule, task.scenario):
        raise HTTPException(status_code=400, detail="Rule code is not allowed for task scenario")
    if parameters is not None:
        _validate_parameters(parameters)

    documents = _list_documents(db, task_id)
    groups = _business_groups(documents)
    if not groups:
        raise HTTPException(status_code=400, detail="Task has no linked business documents")

    fields = _field_map(_list_fields(db, task_id))
    merged_parameters = _rule_parameters(rule) | (parameters or {})
    return [
        _evaluation_read(rule, rule_func(
            RuleContext(
                task_id=task_id,
                scenario=task.scenario,
                business_key=business_key,
                documents=group_documents,
                fields=fields,
                parameters=merged_parameters,
                period_start=task.period_start,
                period_end=task.period_end,
            )
        ))
        for business_key, group_documents in groups.items()
    ]


def rule_missing_required(context: RuleContext) -> RuleResult:
    missing: list[EvidenceRef] = []
    present: list[EvidenceRef] = []
    for document in context.documents:
        specs = schema_specs_for(context.scenario, document.doc_type or "")
        document_fields = context.fields.get(document.id, {})
        if not specs:
            missing.append(_missing_ref(document, "__schema__"))
            continue
        for spec in specs:
            if not spec.is_required:
                continue
            field = document_fields.get(spec.field_name)
            if _is_missing(field):
                missing.append(_missing_ref(document, spec.field_name, field))
            else:
                present.append(_evidence_ref(document, field))

    if missing:
        return _result(
            context,
            "PROC_MISSING_001",
            "need_review",
            "medium",
            "Required procurement fields are missing.",
            {"required_fields": "present"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )
    return _result(
        context,
        "PROC_MISSING_001",
        "pass",
        "info",
        "Required procurement fields are present.",
        {"required_fields": "present"},
        {"missing_fields": []},
        present[:12] or [_task_ref(context, "required_fields")],
    )


def rule_time_order(context: RuleContext) -> RuleResult:
    sequence = (
        ("purchase_request", "request_date"),
        ("purchase_request", "approval_date"),
        ("purchase_contract", "signing_date"),
        ("warehouse_receipt", "receipt_date"),
        ("invoice", "invoice_date"),
        ("accounting_voucher", "voucher_date"),
        ("payment_receipt", "payment_date"),
    )
    values: list[tuple[str, list[tuple[date, ExtractedField, Document]]]] = []
    missing: list[EvidenceRef] = []
    for doc_type, field_name in sequence:
        dates = _date_values(context, doc_type, field_name)
        if not dates:
            document = _docs_by_type(context, doc_type)[0] if _docs_by_type(context, doc_type) else None
            missing.append(_missing_ref(document, field_name, None, doc_type))
        else:
            values.append((field_name, dates))

    if missing:
        return _result(
            context,
            "PROC_TIME_001",
            "need_review",
            "medium",
            "Missing date fields prevent procurement time-order check.",
            {"order": [name for _, name in sequence]},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance_days = int(context.parameters.get("date_tolerance_days", 0) or 0)
    prepayment_allowed = bool(context.parameters.get("prepayment_allowed", False))
    comparable_values = [
        value for value in values if prepayment_allowed or value[0] != "payment_date"
    ]
    inversions = [
        {
            "previous": comparable_values[index - 1][0],
            "next": comparable_values[index][0],
            "previous_latest": max(item[0] for item in comparable_values[index - 1][1]).isoformat(),
            "next_earliest": min(item[0] for item in comparable_values[index][1]).isoformat(),
        }
        for index in range(1, len(comparable_values))
        if max(item[0] for item in comparable_values[index - 1][1])
        > min(item[0] for item in comparable_values[index][1]) + timedelta(days=tolerance_days)
    ]
    evidence = [_evidence_ref(document, field) for _, dates in values for _, field, document in dates]
    if inversions:
        return _result(
            context,
            "PROC_TIME_001",
            "fail",
            "high",
            "Procurement document dates are out of order.",
            {"order": [name for _, name in sequence]},
            {"inversions": inversions},
            evidence,
        )
    return _result(
        context,
        "PROC_TIME_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Procurement document dates are in order.",
        {"order": [name for _, name in sequence]},
        {
            "dates": {
                name: [value.isoformat() for value, _, _ in dates]
                for name, dates in values
            }
        },
        evidence,
    )


def rule_amount(context: RuleContext) -> RuleResult:
    amount_basis = str(context.parameters.get("amount_basis", "including_tax"))
    contract_field = "amount_excluding_tax" if amount_basis == "excluding_tax" else "amount_including_tax"
    invoice_field = "amount_excluding_tax" if amount_basis == "excluding_tax" else "amount_including_tax"
    contract_amount = _single_amount(context, "purchase_contract", contract_field)
    invoice_amounts = _amounts(context, "invoice", invoice_field)
    payment_amounts = _amounts(context, "payment_receipt", "amount")
    voucher_amounts = _amounts(context, "accounting_voucher", "amount")
    missing = _missing_amount_refs(
        [
            ("purchase_contract", contract_field, contract_amount),
            ("invoice", invoice_field, invoice_amounts),
            ("payment_receipt", "amount", payment_amounts),
        ]
    )
    if missing:
        return _result(
            context,
            "PROC_AMOUNT_001",
            "need_review",
            "medium",
            "Missing amount fields prevent amount consistency check.",
            {"amounts": "contract, invoice, payment", "amount_basis": amount_basis},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance = _tolerance_amount(context.parameters, TOLERANCE)
    tolerance_ratio = float(context.parameters.get("tolerance_ratio", 0) or 0)
    contract_total = contract_amount[0][0]
    invoice_total = sum(amount for amount, _, _ in invoice_amounts)
    payment_total = sum(amount for amount, _, _ in payment_amounts)
    voucher_values = [amount for amount, _, _ in voucher_amounts]
    comparable_values = [amount for amount, _, _ in invoice_amounts + payment_amounts]
    voucher_mismatch = [
        amount
        for amount in voucher_values
        if comparable_values and not any(abs(amount - other) <= tolerance for other in comparable_values)
    ]
    failures = {}
    allowed_overage = tolerance + contract_total * tolerance_ratio
    if invoice_total - contract_total > allowed_overage:
        failures["invoice_total"] = invoice_total
    if payment_total - contract_total > allowed_overage:
        failures["payment_total"] = payment_total
    if voucher_mismatch:
        failures["voucher_mismatch"] = voucher_mismatch

    evidence = _amount_evidence(contract_amount + invoice_amounts + payment_amounts + voucher_amounts)
    if failures:
        return _result(
            context,
            "PROC_AMOUNT_001",
            "fail",
            "high",
            "Procurement amounts exceed or do not match expected values.",
            {
                "contract_amount": contract_total,
                "amount_basis": amount_basis,
                "tolerance": tolerance,
                "tolerance_ratio": tolerance_ratio,
            },
            {
                "invoice_total": invoice_total,
                "payment_total": payment_total,
                "voucher_amounts": voucher_values,
                "failures": failures,
            },
            evidence,
        )
    return _result(
        context,
        "PROC_AMOUNT_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Procurement amounts are within contract and voucher tolerance.",
        {
            "contract_amount": contract_total,
            "amount_basis": amount_basis,
            "tolerance": tolerance,
            "tolerance_ratio": tolerance_ratio,
        },
        {"invoice_total": invoice_total, "payment_total": payment_total, "voucher_amounts": voucher_values},
        evidence,
    )


def rule_name(context: RuleContext) -> RuleResult:
    checks = (
        ("purchase_contract", "supplier_name"),
        ("warehouse_receipt", "supplier_name"),
        ("invoice", "seller_name"),
        ("payment_receipt", "payee_name"),
    )
    values: list[tuple[str, str, ExtractedField, Document]] = []
    missing: list[EvidenceRef] = []
    for doc_type, field_name in checks:
        field, document = _first_field(context, doc_type, field_name)
        value = _text_value(field)
        if field is None or document is None or not value:
            missing.append(_missing_ref(document, field_name, field, doc_type))
        else:
            values.append((field_name, value, field, document))
    voucher_field, voucher_doc = _first_field(context, "accounting_voucher", "supplier_name")
    voucher_value = _text_value(voucher_field)
    if voucher_field is not None and voucher_doc is not None and voucher_value:
        values.append(("supplier_name", voucher_value, voucher_field, voucher_doc))

    if missing:
        return _result(
            context,
            "PROC_NAME_001",
            "need_review",
            "medium",
            "Missing counterparty fields prevent name consistency check.",
            {"supplier_names": "consistent"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    normalized = {_normalize_name(value, context.parameters.get("supplier_aliases")) for _, value, _, _ in values}
    evidence = [_evidence_ref(document, field) for _, _, field, document in values]
    if len(normalized) > 1:
        status = str(context.parameters.get("mismatch_status", "warning"))
        return _result(
            context,
            "PROC_NAME_001",
            "fail" if status == "fail" else "warning",
            "high" if status == "fail" else "medium",
            "Counterparty names are inconsistent.",
            {"normalized_name_count": 1},
            {"names": [value for _, value, _, _ in values]},
            evidence,
        )
    return _result(
        context,
        "PROC_NAME_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Counterparty names are consistent.",
        {"normalized_name_count": 1},
        {"names": [value for _, value, _, _ in values]},
        evidence,
    )


def rule_item(context: RuleContext) -> RuleResult:
    item_sets: dict[str, set[str]] = {}
    evidence: list[EvidenceRef] = []
    missing: list[EvidenceRef] = []
    for doc_type in ("purchase_request", "purchase_contract", "warehouse_receipt", "invoice"):
        field_values = _fields(context, doc_type, "item_lines")
        item_keys = _aggregate_item_keys(field_values, context.parameters.get("item_mappings"))
        if not field_values or item_keys is None:
            document = _docs_by_type(context, doc_type)[0] if _docs_by_type(context, doc_type) else None
            field = field_values[0][0] if field_values else None
            missing.append(_missing_ref(document, "item_lines.item_key", field, doc_type))
        else:
            item_sets[doc_type] = item_keys
            evidence.extend(_evidence_ref(document, field) for field, document in field_values)

    if missing:
        return _result(
            context,
            "PROC_ITEM_001",
            "need_review",
            "medium",
            "Missing line item names prevent item consistency check.",
            {"items": "request = contract = receipt = invoice"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    all_items = {item for item_set in item_sets.values() for item in item_set}
    failures = {
        item: {doc_type: item in item_set for doc_type, item_set in item_sets.items()}
        for item in sorted(all_items)
        if not all(item in item_set for item_set in item_sets.values())
    }
    if failures:
        return _result(
            context,
            "PROC_ITEM_001",
            "fail",
            "high",
            "Request, contract, receipt, and invoice item types do not match.",
            {"items": "request = contract = receipt = invoice"},
            {"item_sets": {key: sorted(value) for key, value in item_sets.items()}, "failures": failures},
            evidence,
        )
    return _result(
        context,
        "PROC_ITEM_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Request, contract, receipt, and invoice item types match.",
        {"items": "request = contract = receipt = invoice"},
        {"item_sets": {key: sorted(value) for key, value in item_sets.items()}},
        evidence,
    )


def rule_qty(context: RuleContext) -> RuleResult:
    quantities: list[tuple[str, dict[str, float], list[tuple[ExtractedField, Document]]]] = []
    missing: list[EvidenceRef] = []
    for doc_type in ("purchase_request", "purchase_contract", "warehouse_receipt", "invoice"):
        field_values = _fields(context, doc_type, "item_lines")
        quantity_map = _aggregate_quantity_map(field_values, context.parameters.get("item_mappings"))
        if not field_values or quantity_map is None:
            document = _docs_by_type(context, doc_type)[0] if _docs_by_type(context, doc_type) else None
            field = field_values[0][0] if field_values else None
            missing.append(_missing_ref(document, "item_lines.quantity", field, doc_type))
        else:
            quantities.append((doc_type, quantity_map, field_values))
    if missing:
        return _result(
            context,
            "PROC_QTY_001",
            "need_review",
            "medium",
            "Missing line item quantities prevent quantity check.",
            {"quantity": "request >= contract >= receipt and receipt = invoice"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance = _tolerance_amount(context.parameters, 0.0001)
    evidence = [_evidence_ref(document, field) for _, _, values in quantities for field, document in values]
    item_quantities = {doc_type: quantity_map for doc_type, quantity_map, _ in quantities}
    values = {
        doc_type: sum(quantity_map.values())
        for doc_type, quantity_map, _ in quantities
    }
    item_keys = {item_key for quantity_map in item_quantities.values() for item_key in quantity_map}
    quantity_failures = {
        item_key: _procurement_quantity_failure(item_quantities, item_key, tolerance)
        for item_key in item_keys
        if _procurement_quantity_failure(item_quantities, item_key, tolerance)
    }
    if quantity_failures:
        return _result(
            context,
            "PROC_QTY_001",
            "fail",
            "high",
            "Procurement quantities do not satisfy request >= contract >= receipt and receipt = invoice.",
            {"quantity": "request >= contract >= receipt and receipt = invoice", "tolerance": tolerance},
            values | {"item_quantities": item_quantities, "failures": quantity_failures},
            evidence,
        )
    return _result(
        context,
        "PROC_QTY_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Procurement quantities satisfy request >= contract >= receipt and receipt = invoice.",
        {"quantity": "request >= contract >= receipt and receipt = invoice", "tolerance": tolerance},
        values | {"item_quantities": item_quantities},
        evidence,
    )


def rule_tax(context: RuleContext) -> RuleResult:
    excluding = _amounts(context, "invoice", "amount_excluding_tax")
    tax_amount = _amounts(context, "invoice", "tax_amount")
    including = _amounts(context, "invoice", "amount_including_tax")
    missing = _missing_amount_refs(
        [
            ("invoice", "amount_excluding_tax", excluding),
            ("invoice", "tax_amount", tax_amount),
            ("invoice", "amount_including_tax", including),
        ]
    )
    if missing:
        return _result(
            context,
            "PROC_TAX_001",
            "need_review",
            "medium",
            "Missing invoice tax amount fields prevent tax check.",
            {"formula": "amount_excluding_tax + tax_amount ~= amount_including_tax"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance = _tolerance_amount(context.parameters, TOLERANCE)
    expected_total = sum(amount for amount, _, _ in excluding) + sum(amount for amount, _, _ in tax_amount)
    actual_total = sum(amount for amount, _, _ in including)
    evidence = _amount_evidence(excluding + tax_amount + including)
    if abs(expected_total - actual_total) > tolerance:
        return _result(
            context,
            "PROC_TAX_001",
            "fail",
            "high",
            "Invoice tax arithmetic does not reconcile.",
            {"expected_total": expected_total, "tolerance": tolerance},
            {"amount_including_tax": actual_total},
            evidence,
        )

    contract_tax = _single_rate(context, "purchase_contract", "tax_rate")
    invoice_tax = _single_rate(context, "invoice", "tax_rate")
    if contract_tax and invoice_tax:
        evidence.extend(_rate_evidence(contract_tax + invoice_tax))
        allowed_tax_rates = _allowed_tax_rates(context.parameters)
        if allowed_tax_rates and invoice_tax[0][0] not in allowed_tax_rates:
            return _result(
                context,
                "PROC_TAX_001",
                "warning",
                "medium",
                "Invoice tax rate is not in configured allowed_tax_rates.",
                {"allowed_tax_rates": sorted(allowed_tax_rates)},
                {"invoice_tax_rate": invoice_tax[0][0]},
                evidence,
            )
        if abs(contract_tax[0][0] - invoice_tax[0][0]) > 0.0001:
            return _result(
                context,
                "PROC_TAX_001",
                "warning",
                "medium",
                "Contract and invoice tax rates differ.",
                {"contract_tax_rate": contract_tax[0][0]},
                {"invoice_tax_rate": invoice_tax[0][0]},
                evidence,
            )
    elif not contract_tax or not invoice_tax:
        return _result(
            context,
            "PROC_TAX_001",
            "warning",
            "medium",
            "Tax arithmetic reconciles, but contract or invoice tax rate is missing.",
            {"formula": "amount_excluding_tax + tax_amount ~= amount_including_tax"},
            {"amount_including_tax": actual_total, "missing_tax_rate": True},
            evidence,
        )

    return _result(
        context,
        "PROC_TAX_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Invoice tax arithmetic and available tax rates reconcile.",
        {"expected_total": expected_total, "tolerance": tolerance},
        {"amount_including_tax": actual_total},
        evidence,
    )


def rule_sales_missing_required(context: RuleContext) -> RuleResult:
    base = rule_missing_required(context)
    return RuleResult(
        rule_code="SALES_MISSING_001",
        business_key=context.business_key,
        status=base.status,
        severity=base.severity,
        message=base.message.replace("procurement", "sales"),
        expected_value=base.expected_value,
        actual_value=base.actual_value,
        evidence=base.evidence,
    )


def rule_sales_time_order(context: RuleContext) -> RuleResult:
    sequence = (
        ("sales_contract", "signing_date"),
        ("sales_order", "order_date"),
        ("delivery_order", "delivery_date"),
        ("logistics_receipt", "signed_date"),
        ("sales_invoice", "invoice_date"),
    )
    values: list[tuple[str, date, ExtractedField, Document]] = []
    missing: list[EvidenceRef] = []
    for doc_type, field_name in sequence:
        field, document = _first_field(context, doc_type, field_name)
        parsed = _date_value(field)
        if field is None or document is None or parsed is None:
            missing.append(_missing_ref(document, field_name, field, doc_type))
        else:
            values.append((field_name, parsed, field, document))

    if missing:
        return _result(
            context,
            "SALES_TIME_001",
            "need_review",
            "medium",
            "Missing date fields prevent sales time-order check.",
            {"order": [name for _, name in sequence]},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance_days = int(context.parameters.get("date_tolerance_days", 0) or 0)
    inversions = [
        {"previous": values[index - 1][0], "next": values[index][0]}
        for index in range(1, len(values))
        if values[index - 1][1] > values[index][1] + timedelta(days=tolerance_days)
    ]
    evidence = [_evidence_ref(document, field) for _, _, field, document in values]
    if inversions:
        return _result(
            context,
            "SALES_TIME_001",
            "fail",
            "high",
            "Sales document dates are out of order.",
            {"order": [name for _, name in sequence]},
            {"inversions": inversions},
            evidence,
        )
    return _result(
        context,
        "SALES_TIME_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Sales document dates are in order.",
        {"order": [name for _, name in sequence]},
        {"dates": {name: value.isoformat() for name, value, _, _ in values}},
        evidence,
    )


def rule_sales_amount(context: RuleContext) -> RuleResult:
    contract_amount = _single_amount(context, "sales_contract", "amount_including_tax")
    invoice_amounts = _amounts(context, "sales_invoice", "amount_including_tax")
    receipt_amounts = _amounts(context, "receipt_voucher", "amount")
    missing = _missing_amount_refs(
        [
            ("sales_contract", "amount_including_tax", contract_amount),
            ("sales_invoice", "amount_including_tax", invoice_amounts),
            ("receipt_voucher", "amount", receipt_amounts),
        ]
    )
    if missing:
        return _result(
            context,
            "SALES_AMOUNT_001",
            "need_review",
            "medium",
            "Missing amount fields prevent sales amount consistency check.",
            {"amounts": "contract, invoice, receipt"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance = _tolerance_amount(context.parameters, TOLERANCE)
    tolerance_ratio = float(context.parameters.get("tolerance_ratio", 0) or 0)
    contract_total = contract_amount[0][0]
    invoice_total = sum(amount for amount, _, _ in invoice_amounts)
    receipt_total = sum(amount for amount, _, _ in receipt_amounts)
    allowed_overage = tolerance + contract_total * tolerance_ratio
    failures = {}
    if invoice_total - contract_total > allowed_overage:
        failures["invoice_total"] = invoice_total
    if receipt_total - contract_total > allowed_overage:
        failures["receipt_total"] = receipt_total

    evidence = _amount_evidence(contract_amount + invoice_amounts + receipt_amounts)
    if failures:
        return _result(
            context,
            "SALES_AMOUNT_001",
            "fail",
            "high",
            "Sales invoice or receipt amount exceeds contract amount.",
            {"contract_amount": contract_total, "tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
            {"invoice_total": invoice_total, "receipt_total": receipt_total, "failures": failures},
            evidence,
        )
    return _result(
        context,
        "SALES_AMOUNT_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Sales invoice and receipt amounts are within contract amount.",
        {"contract_amount": contract_total, "tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
        {"invoice_total": invoice_total, "receipt_total": receipt_total},
        evidence,
    )


def rule_sales_name(context: RuleContext) -> RuleResult:
    checks = (
        ("sales_contract", "customer_name"),
        ("sales_order", "customer_name"),
        ("delivery_order", "customer_name"),
        ("sales_invoice", "buyer_name"),
        ("receipt_voucher", "payer_name"),
    )
    values: list[tuple[str, str, ExtractedField, Document]] = []
    missing: list[EvidenceRef] = []
    for doc_type, field_name in checks:
        field, document = _first_field(context, doc_type, field_name)
        value = _text_value(field)
        if field is None or document is None or not value:
            missing.append(_missing_ref(document, field_name, field, doc_type))
        else:
            values.append((field_name, value, field, document))
    logistics_field, logistics_doc = _first_field(context, "logistics_receipt", "customer_name")
    logistics_value = _text_value(logistics_field)
    if logistics_field is not None and logistics_doc is not None and logistics_value:
        values.append(("customer_name", logistics_value, logistics_field, logistics_doc))

    if missing:
        return _result(
            context,
            "SALES_NAME_001",
            "need_review",
            "medium",
            "Missing customer fields prevent sales name consistency check.",
            {"customer_names": "consistent"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    normalized = {_normalize_name(value, context.parameters.get("supplier_aliases")) for _, value, _, _ in values}
    evidence = [_evidence_ref(document, field) for _, _, field, document in values]
    if len(normalized) > 1:
        status = str(context.parameters.get("mismatch_status", "warning"))
        return _result(
            context,
            "SALES_NAME_001",
            "fail" if status == "fail" else "warning",
            "high" if status == "fail" else "medium",
            "Sales customer names are inconsistent.",
            {"normalized_name_count": 1},
            {"names": [value for _, value, _, _ in values]},
            evidence,
        )
    return _result(
        context,
        "SALES_NAME_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Sales customer names are consistent.",
        {"normalized_name_count": 1},
        {"names": [value for _, value, _, _ in values]},
        evidence,
    )


def rule_sales_qty(context: RuleContext) -> RuleResult:
    quantities = []
    missing: list[EvidenceRef] = []
    for doc_type in ("sales_contract", "sales_order", "delivery_order", "logistics_receipt", "sales_invoice"):
        field, document = _first_field(context, doc_type, "item_lines")
        quantity_map = _quantity_map(field, context.parameters.get("item_mappings"))
        if field is None or document is None or quantity_map is None:
            missing.append(_missing_ref(document, "item_lines.quantity", field, doc_type))
        else:
            quantities.append((doc_type, quantity_map, field, document))
    if missing:
        return _result(
            context,
            "SALES_QTY_001",
            "need_review",
            "medium",
            "Missing line item quantities prevent sales quantity check.",
            {"quantity": "contract = order = delivery = logistics = invoice"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance = _tolerance_amount(context.parameters, 0.0001)
    evidence = [_evidence_ref(document, field) for _, _, field, document in quantities]
    item_quantities = {doc_type: quantity_map for doc_type, quantity_map, _, _ in quantities}
    values = {doc_type: sum(quantity_map.values()) for doc_type, quantity_map, _, _ in quantities}
    item_keys = {item_key for quantity_map in item_quantities.values() for item_key in quantity_map}
    quantity_failures = {
        item_key: {doc_type: quantity_map.get(item_key) for doc_type, quantity_map in item_quantities.items()}
        for item_key in item_keys
        if None in {quantity_map.get(item_key) for quantity_map in item_quantities.values()}
        or max(quantity_map.get(item_key, 0.0) for quantity_map in item_quantities.values())
        - min(quantity_map.get(item_key, 0.0) for quantity_map in item_quantities.values())
        > tolerance
    }
    if quantity_failures:
        return _result(
            context,
            "SALES_QTY_001",
            "fail",
            "high",
            "Sales document quantities do not match.",
            {"quantity": "contract = order = delivery = logistics = invoice", "tolerance": tolerance},
            values | {"item_quantities": item_quantities, "failures": quantity_failures},
            evidence,
        )
    return _result(
        context,
        "SALES_QTY_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Sales document quantities match.",
        {"quantity": "contract = order = delivery = logistics = invoice", "tolerance": tolerance},
        values | {"item_quantities": item_quantities},
        evidence,
    )


def rule_sales_revenue_cutoff(context: RuleContext) -> RuleResult:
    signed_field, signed_doc = _first_field(context, "logistics_receipt", "signed_date")
    invoice_field, invoice_doc = _first_field(context, "sales_invoice", "invoice_date")
    voucher_field, voucher_doc = _first_field(context, "accounting_voucher", "voucher_date")
    signed_date = _date_value(signed_field)
    invoice_date = _date_value(invoice_field)
    voucher_date = _date_value(voucher_field)
    missing = []
    if signed_field is None or signed_doc is None or signed_date is None:
        missing.append(_missing_ref(signed_doc, "signed_date", signed_field, "logistics_receipt"))
    if invoice_field is None or invoice_doc is None or invoice_date is None:
        missing.append(_missing_ref(invoice_doc, "invoice_date", invoice_field, "sales_invoice"))
    if voucher_field is None or voucher_doc is None or voucher_date is None:
        missing.append(_missing_ref(voucher_doc, "voucher_date", voucher_field, "accounting_voucher"))
    if missing:
        return _result(
            context,
            "SALES_REVENUE_001",
            "need_review",
            "medium",
            "Missing signed, invoice, or voucher date prevents sales revenue cutoff check.",
            {"dates": ["signed_date", "invoice_date", "voucher_date"]},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    evidence = [_evidence_ref(signed_doc, signed_field), _evidence_ref(invoice_doc, invoice_field), _evidence_ref(voucher_doc, voucher_field)]
    tolerance_days = int(context.parameters.get("date_tolerance_days", 0) or 0)
    max_days = int(context.parameters.get("recognition_max_days_after_signed", 30) or 0)
    issues = []
    if invoice_date + timedelta(days=tolerance_days) < signed_date:
        issues.append({"type": "invoice_before_signed", "invoice_date": invoice_date.isoformat(), "signed_date": signed_date.isoformat()})
    if voucher_date + timedelta(days=tolerance_days) < signed_date:
        issues.append({"type": "voucher_before_signed", "voucher_date": voucher_date.isoformat(), "signed_date": signed_date.isoformat()})
    if context.period_end and signed_date > context.period_end and (
        invoice_date <= context.period_end or voucher_date <= context.period_end
    ):
        issues.append(
            {
                "type": "cross_period_revenue",
                "period_end": context.period_end.isoformat(),
                "signed_date": signed_date.isoformat(),
                "invoice_date": invoice_date.isoformat(),
                "voucher_date": voucher_date.isoformat(),
            }
        )
    if max_days and voucher_date > signed_date + timedelta(days=max_days):
        issues.append({"type": "delayed_revenue_recognition", "max_days_after_signed": max_days, "voucher_date": voucher_date.isoformat()})

    if issues:
        high_risk = any(issue["type"] in {"cross_period_revenue", "voucher_before_signed"} for issue in issues)
        return _result(
            context,
            "SALES_REVENUE_001",
            "warning",
            "high" if high_risk else "medium",
            "Sales revenue recognition timing requires review.",
            {
                "invoice_date_on_or_after_signed_date": True,
                "voucher_date_on_or_after_signed_date": True,
                "period_end": context.period_end.isoformat() if context.period_end else None,
            },
            {
                "signed_date": signed_date.isoformat(),
                "invoice_date": invoice_date.isoformat(),
                "voucher_date": voucher_date.isoformat(),
                "issues": issues,
            },
            evidence,
        )
    return _result(
        context,
        "SALES_REVENUE_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Sales revenue recognition timing is consistent with available signed, invoice, and voucher dates.",
        {"invoice_date_on_or_after_signed_date": True, "voucher_date_on_or_after_signed_date": True},
        {"signed_date": signed_date.isoformat(), "invoice_date": invoice_date.isoformat(), "voucher_date": voucher_date.isoformat()},
        evidence,
    )


def rule_confirmation_missing_required(context: RuleContext) -> RuleResult:
    base = rule_missing_required(context)
    return RuleResult(
        rule_code="CONF_MISSING_001",
        business_key=context.business_key,
        status=base.status,
        severity=base.severity,
        message=base.message.replace("procurement", "confirmation"),
        expected_value=base.expected_value,
        actual_value=base.actual_value,
        evidence=base.evidence,
    )


def rule_confirmation_date(context: RuleContext) -> RuleResult:
    sent_field, sent_doc = _first_field_from(context, (("confirmation_request", "sent_date"), ("confirmation", "sent_date")))
    replied_field, replied_doc = _first_field_from(context, (("confirmation_reply", "replied_date"), ("confirmation", "replied_date")))
    sent_date = _date_value(sent_field)
    replied_date = _date_value(replied_field)
    missing = []
    if sent_field is None or sent_doc is None or sent_date is None:
        missing.append(_missing_ref(sent_doc, "sent_date", sent_field, "confirmation_request"))
    if replied_field is None or replied_doc is None or replied_date is None:
        missing.append(_missing_ref(replied_doc, "replied_date", replied_field, "confirmation_reply"))
    if missing:
        return _result(
            context,
            "CONF_DATE_001",
            "need_review",
            "medium",
            "Missing confirmation dates prevent reply date check.",
            {"rule": "replied_date >= sent_date"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance_days = int(context.parameters.get("date_tolerance_days", 0) or 0)
    evidence = [_evidence_ref(sent_doc, sent_field), _evidence_ref(replied_doc, replied_field)]
    if replied_date + timedelta(days=tolerance_days) < sent_date:
        return _result(
            context,
            "CONF_DATE_001",
            "fail",
            "high",
            "Confirmation replied_date is earlier than sent_date.",
            {"sent_before_or_equal_replied": True},
            {"sent_date": sent_date.isoformat(), "replied_date": replied_date.isoformat()},
            evidence,
        )
    return _result(
        context,
        "CONF_DATE_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Confirmation reply date is not earlier than sent date.",
        {"sent_before_or_equal_replied": True},
        {"sent_date": sent_date.isoformat(), "replied_date": replied_date.isoformat()},
        evidence,
    )


def rule_confirmation_amount(context: RuleContext) -> RuleResult:
    book_amounts = _amounts_from(context, (("confirmation_request", "book_amount"), ("confirmation", "book_amount")))
    confirmed_amounts = _amounts_from(context, (("confirmation_reply", "confirmed_amount"), ("confirmation", "confirmed_amount")))
    difference_amounts = _amounts_from(context, (("confirmation_adjustment", "difference_amount"), ("confirmation", "difference_amount")))
    reason_field, reason_doc = _first_field_from(context, (("confirmation_adjustment", "exception_reason"), ("confirmation", "exception_reason")))
    reason = _text_value(reason_field)
    missing = _missing_amount_refs(
        [
            ("confirmation_request", "book_amount", book_amounts),
            ("confirmation_reply", "confirmed_amount", confirmed_amounts),
        ]
    )
    if missing:
        return _result(
            context,
            "CONF_AMOUNT_001",
            "need_review",
            "medium",
            "Missing confirmation amounts prevent amount check.",
            {"amounts": "book_amount and confirmed_amount"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    book_total = sum(amount for amount, _, _ in book_amounts)
    confirmed_total = sum(amount for amount, _, _ in confirmed_amounts)
    tolerance = _tolerance_amount(context.parameters, TOLERANCE)
    difference = round(confirmed_total - book_total, 2)
    evidence = _amount_evidence(book_amounts + confirmed_amounts + difference_amounts)
    if reason_field is not None and reason_doc is not None:
        evidence.append(_evidence_ref(reason_doc, reason_field))

    if abs(difference) <= tolerance:
        return _result(
            context,
            "CONF_AMOUNT_001",
            _pass_or_warning(evidence),
            _severity_for_pass(evidence),
            "Confirmation confirmed amount matches book amount within tolerance.",
            {"tolerance": tolerance},
            {"book_amount": book_total, "confirmed_amount": confirmed_total, "difference": difference},
            evidence,
        )

    if not difference_amounts and not reason:
        return _result(
            context,
            "CONF_AMOUNT_001",
            "need_review",
            "high",
            "Confirmation amount differs without adjustment amount or exception reason.",
            {"required_when_mismatch": ["difference_amount", "exception_reason"], "tolerance": tolerance},
            {"book_amount": book_total, "confirmed_amount": confirmed_total, "difference": difference},
            evidence,
        )

    adjustment_total = sum(amount for amount, _, _ in difference_amounts) if difference_amounts else None
    adjustment_matches = adjustment_total is not None and abs(abs(adjustment_total) - abs(difference)) <= tolerance
    status = "warning" if reason or not adjustment_matches else _pass_or_warning(evidence)
    return _result(
        context,
        "CONF_AMOUNT_001",
        status,
        "medium" if status == "warning" else _severity_for_pass(evidence),
        "Confirmation amount differs and has adjustment evidence for review.",
        {"required_when_mismatch": ["difference_amount", "exception_reason"], "tolerance": tolerance},
        {
            "book_amount": book_total,
            "confirmed_amount": confirmed_total,
            "difference": difference,
            "adjustment_total": adjustment_total,
            "exception_reason_present": bool(reason),
        },
        evidence,
    )


def rule_confirmation_name(context: RuleContext) -> RuleResult:
    checks = (
        ("confirmation_request", "counterparty_name"),
        ("confirmation_reply", "counterparty_name"),
        ("confirmation", "counterparty_name"),
    )
    values: list[tuple[str, str, ExtractedField, Document]] = []
    missing: list[EvidenceRef] = []
    for doc_type, field_name in checks:
        if not _docs_by_type(context, doc_type):
            continue
        field, document = _first_field(context, doc_type, field_name)
        value = _text_value(field)
        if field is None or document is None or not value:
            missing.append(_missing_ref(document, field_name, field, doc_type))
        else:
            values.append((field_name, value, field, document))
    for value, field, document in _text_fields_by_name(
        context,
        {"customer_name", "supplier_name", "buyer_name", "seller_name", "payer_name", "payee_name"},
    ):
        values.append((field.field_name, value, field, document))
    if missing or not values:
        return _result(
            context,
            "CONF_NAME_001",
            "need_review",
            "medium",
            "Missing counterparty name prevents confirmation name check.",
            {"counterparty_name": "consistent"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    normalized = {_normalize_name(value, context.parameters.get("supplier_aliases")) for _, value, _, _ in values}
    evidence = [_evidence_ref(document, field) for _, _, field, document in values] + missing
    if len(normalized) > 1:
        status = str(context.parameters.get("mismatch_status", "warning"))
        return _result(
            context,
            "CONF_NAME_001",
            "fail" if status == "fail" else "warning",
            "high" if status == "fail" else "medium",
            "Confirmation counterparty names are inconsistent.",
            {"normalized_name_count": 1},
            {"names": [value for _, value, _, _ in values]},
            evidence,
        )
    return _result(
        context,
        "CONF_NAME_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Confirmation counterparty names are consistent.",
        {"normalized_name_count": 1},
        {"names": [value for _, value, _, _ in values]},
        evidence,
    )


def rule_confirmation_seal_sign(context: RuleContext) -> RuleResult:
    seal_field, seal_doc = _first_field_from(context, (("confirmation_reply", "seal_detected"), ("confirmation", "seal_detected")))
    sign_field, sign_doc = _first_field_from(context, (("confirmation_reply", "signatory"), ("confirmation", "signatory")))
    seal_value = _text_value(seal_field)
    sign_value = _text_value(sign_field)
    evidence = []
    if seal_field is not None and seal_doc is not None:
        evidence.append(_evidence_ref(seal_doc, seal_field))
    else:
        evidence.append(_missing_ref(seal_doc, "seal_detected", seal_field, "confirmation_reply"))
    if sign_field is not None and sign_doc is not None:
        evidence.append(_evidence_ref(sign_doc, sign_field))
    else:
        evidence.append(_missing_ref(sign_doc, "signatory", sign_field, "confirmation_reply"))

    if not seal_value and not sign_value:
        return _result(
            context,
            "CONF_SEAL_SIGN_001",
            "need_review",
            "medium",
            "Confirmation reply lacks both seal and signatory evidence; authenticity is not judged.",
            {"seal_or_signatory": "present"},
            {"seal_detected": seal_value, "signatory": sign_value},
            evidence,
        )
    if not seal_value or not sign_value:
        return _result(
            context,
            "CONF_SEAL_SIGN_001",
            "warning",
            "medium",
            "Confirmation reply has incomplete seal or signatory evidence; authenticity is not judged.",
            {"seal_and_signatory": "present when available"},
            {"seal_detected": seal_value, "signatory": sign_value},
            evidence,
        )
    return _result(
        context,
        "CONF_SEAL_SIGN_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Confirmation reply includes seal and signatory evidence; authenticity is not judged.",
        {"seal_and_signatory": "present"},
        {"seal_detected": seal_value, "signatory": sign_value},
        evidence,
    )


INTERVIEW_DOC_TYPES = ("interview_record", "interview_outline", "interview_signature_page", "interview_transcript")


def rule_interview_missing_required(context: RuleContext) -> RuleResult:
    base = rule_missing_required(context)
    return RuleResult(
        rule_code="INTERVIEW_MISSING_001",
        business_key=context.business_key,
        status=base.status,
        severity=base.severity,
        message=base.message.replace("procurement", "interview"),
        expected_value=base.expected_value,
        actual_value=base.actual_value,
        evidence=base.evidence,
    )


def rule_interview_date(context: RuleContext) -> RuleResult:
    field, document = _first_interview_field(context, ("interview_date",))
    interview_date = _date_value(field)
    if field is None or document is None or interview_date is None:
        return _result(
            context,
            "INTERVIEW_DATE_001",
            "need_review",
            "medium",
            "Missing interview_date prevents interview period check.",
            {
                "period_start": context.period_start.isoformat() if context.period_start else None,
                "period_end": context.period_end.isoformat() if context.period_end else None,
            },
            {"interview_date": None},
            [_missing_ref(document, "interview_date", field, "interview_record")],
        )
    evidence = [_evidence_ref(document, field)]
    if context.period_start is None or context.period_end is None:
        return _result(
            context,
            "INTERVIEW_DATE_001",
            "need_review",
            "medium",
            "Task period is missing; interview date needs manual review.",
            {"period_start": None, "period_end": None},
            {"interview_date": interview_date.isoformat()},
            evidence,
        )
    if interview_date < context.period_start or interview_date > context.period_end:
        return _result(
            context,
            "INTERVIEW_DATE_001",
            "warning",
            "medium",
            "Interview date is outside the task period.",
            {"period_start": context.period_start.isoformat(), "period_end": context.period_end.isoformat()},
            {"interview_date": interview_date.isoformat()},
            evidence,
        )
    return _result(
        context,
        "INTERVIEW_DATE_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Interview date is within the task period.",
        {"period_start": context.period_start.isoformat(), "period_end": context.period_end.isoformat()},
        {"interview_date": interview_date.isoformat()},
        evidence,
    )


def rule_interview_signature(context: RuleContext) -> RuleResult:
    field, document = _first_field_from(
        context,
        (("interview_signature_page", "signature_detected"), ("interview_record", "signature_detected")),
    )
    value = (_text_value(field) or "").casefold()
    evidence = [_evidence_ref(document, field)] if field is not None and document is not None else [
        _missing_ref(document, "signature_detected", field, "interview_signature_page")
    ]
    if value in {"yes", "true", "signed", "detected", "present", "有", "是"}:
        return _result(
            context,
            "INTERVIEW_SIGNATURE_001",
            _pass_or_warning(evidence),
            _severity_for_pass(evidence),
            "Interview signature evidence is present; authenticity is not judged.",
            {"signature_detected": True},
            {"signature_detected": value},
            evidence,
        )
    return _result(
        context,
        "INTERVIEW_SIGNATURE_001",
        "need_review",
        "medium",
        "Interview signature is missing or marked absent; authenticity is not judged.",
        {"signature_detected": True},
        {"signature_detected": value or None},
        evidence,
    )


def rule_interview_amount(context: RuleContext) -> RuleResult:
    mentioned = _amount_fields_by_name(context, {"mentioned_amounts"})
    references = _amount_fields_by_name(
        context,
        {
            "amount_including_tax",
            "amount",
            "total_estimated_amount",
            "amount_excluding_tax",
            "book_amount",
            "confirmed_amount",
            "contract_amount",
            "invoice_amount",
            "payment_amount",
        },
    )
    if not mentioned:
        return _result(
            context,
            "INTERVIEW_AMOUNT_001",
            "need_review",
            "medium",
            "Missing mentioned_amounts prevents interview amount cross-check.",
            {"mentioned_amounts": "present"},
            {"mentioned_amounts": None},
            [_missing_ref(None, "mentioned_amounts", doc_type="interview_record")],
        )
    evidence = _amount_evidence(mentioned + references)
    if not references:
        return _result(
            context,
            "INTERVIEW_AMOUNT_001",
            "need_review",
            "medium",
            "No task amount evidence is available for interview amount cross-check.",
            {"reference_amount": "available"},
            {"mentioned_amounts": [amount for amount, _, _ in mentioned]},
            evidence,
        )

    tolerance = _tolerance_amount(context.parameters, TOLERANCE)
    tolerance_ratio = float(context.parameters.get("tolerance_ratio", 0) or 0)
    mismatches = []
    for amount, field, _ in mentioned:
        closest = min((abs(amount - ref_amount), ref_amount) for ref_amount, _, _ in references)
        allowed = tolerance + abs(closest[1]) * tolerance_ratio
        if closest[0] > allowed:
            mismatches.append({"field_name": field.field_name, "mentioned_amount": amount, "closest_reference": closest[1]})
    if mismatches:
        return _result(
            context,
            "INTERVIEW_AMOUNT_001",
            "warning",
            "medium",
            "Interview mentioned amount differs from available task amount evidence; manual interpretation is required.",
            {"tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
            {"mismatches": mismatches},
            evidence,
        )
    return _result(
        context,
        "INTERVIEW_AMOUNT_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Interview mentioned amount is close to available task amount evidence.",
        {"tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
        {"mentioned_amounts": [amount for amount, _, _ in mentioned]},
        evidence,
    )


def rule_interview_counterparty(context: RuleContext) -> RuleResult:
    mentioned = _text_fields_by_name(context, {"mentioned_counterparties"})
    references = _text_fields_by_name(
        context,
        {
            "supplier_name",
            "seller_name",
            "payee_name",
            "customer_name",
            "buyer_name",
            "payer_name",
            "counterparty_name",
            "company_name",
        },
    )
    if not mentioned:
        return _result(
            context,
            "INTERVIEW_COUNTERPARTY_001",
            "need_review",
            "medium",
            "Missing mentioned_counterparties prevents interview counterparty check.",
            {"mentioned_counterparties": "present"},
            {"mentioned_counterparties": None},
            [_missing_ref(None, "mentioned_counterparties", doc_type="interview_record")],
        )
    evidence = [_evidence_ref(document, field) for _, field, document in mentioned + references]
    if not references:
        return _result(
            context,
            "INTERVIEW_COUNTERPARTY_001",
            "need_review",
            "medium",
            "No task counterparty evidence is available for interview counterparty check.",
            {"reference_counterparty": "available"},
            {"mentioned_counterparties": [value for value, _, _ in mentioned]},
            evidence,
        )

    aliases = context.parameters.get("supplier_aliases")
    reference_names = {_normalize_name(value, aliases) for value, _, _ in references}
    unmatched = [value for value, _, _ in mentioned if _normalize_name(value, aliases) not in reference_names]
    if unmatched:
        return _result(
            context,
            "INTERVIEW_COUNTERPARTY_001",
            "warning",
            "medium",
            "Interview mentioned counterparty is not matched to available task party evidence.",
            {"matched_to_existing_party": True},
            {"unmatched": unmatched},
            evidence,
        )
    return _result(
        context,
        "INTERVIEW_COUNTERPARTY_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Interview mentioned counterparties match available task party evidence.",
        {"matched_to_existing_party": True},
        {"mentioned_counterparties": [value for value, _, _ in mentioned]},
        evidence,
    )


CONTRACT_DOC_TYPES = (
    "contract_review",
    "material_contract",
    "supplemental_agreement",
    "framework_agreement",
    "contract_attachment",
)
CONTRACT_KEY_TERM_FIELDS = (
    "payment_terms",
    "delivery_terms",
    "acceptance_terms",
    "breach_terms",
    "dispute_resolution",
)
CONTRACT_SPECIAL_CLAUSE_FIELDS = (
    "auto_renewal_clause",
    "exclusivity_clause",
    "repurchase_clause",
    "minimum_guarantee_clause",
    "price_adjustment_clause",
    "related_party_clause",
    "variable_consideration_clause",
)


def rule_contract_missing_required(context: RuleContext) -> RuleResult:
    base = rule_missing_required(context)
    return RuleResult(
        rule_code="CONTRACT_MISSING_001",
        business_key=context.business_key,
        status=base.status,
        severity=base.severity,
        message=base.message.replace("procurement", "contract review"),
        expected_value=base.expected_value,
        actual_value=base.actual_value,
        evidence=base.evidence,
    )


def rule_contract_period(context: RuleContext) -> RuleResult:
    effective_field, effective_doc = _first_contract_field(context, ("effective_date", "signing_date"))
    expiry_field, expiry_doc = _first_contract_field(context, ("expiry_date",))
    effective_date = _date_value(effective_field)
    expiry_date = _date_value(expiry_field)
    evidence = []
    if effective_field is not None and effective_doc is not None:
        evidence.append(_evidence_ref(effective_doc, effective_field))
    if expiry_field is not None and expiry_doc is not None:
        evidence.append(_evidence_ref(expiry_doc, expiry_field))

    missing = []
    if effective_date is None:
        missing.append(_missing_ref(effective_doc, "effective_date", effective_field, "contract_review"))
    if expiry_date is None:
        missing.append(_missing_ref(expiry_doc, "expiry_date", expiry_field, "contract_review"))
    if missing:
        return _result(
            context,
            "CONTRACT_PERIOD_001",
            "need_review",
            "medium",
            "Missing contract period fields prevent coverage check.",
            {"task_period_covered": True},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )
    if context.period_start is None or context.period_end is None:
        return _result(
            context,
            "CONTRACT_PERIOD_001",
            "need_review",
            "medium",
            "Task period is missing; contract coverage needs manual review.",
            {"task_period_covered": True},
            {"effective_date": effective_date.isoformat(), "expiry_date": expiry_date.isoformat()},
            evidence,
        )
    if effective_date > context.period_start or expiry_date < context.period_end:
        return _result(
            context,
            "CONTRACT_PERIOD_001",
            "warning",
            "medium",
            "Contract period does not fully cover the task period; manual review is required.",
            {"period_start": context.period_start.isoformat(), "period_end": context.period_end.isoformat()},
            {"effective_date": effective_date.isoformat(), "expiry_date": expiry_date.isoformat()},
            evidence,
        )
    return _result(
        context,
        "CONTRACT_PERIOD_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Contract period covers the task period.",
        {"period_start": context.period_start.isoformat(), "period_end": context.period_end.isoformat()},
        {"effective_date": effective_date.isoformat(), "expiry_date": expiry_date.isoformat()},
        evidence,
    )


def rule_contract_amount(context: RuleContext) -> RuleResult:
    contract_amounts = _amounts_from(
        context,
        tuple((doc_type, "amount_including_tax") for doc_type in CONTRACT_DOC_TYPES),
    )
    references = _amount_fields_by_name(
        context,
        {
            "invoice_amount",
            "payment_amount",
            "book_amount",
            "confirmed_amount",
            "amount",
            "amount_excluding_tax",
            "total_estimated_amount",
        },
    )
    evidence = _amount_evidence(contract_amounts + references)
    quantity_failures, quantity_evidence = _contract_quantity_failures(context, _tolerance_amount(context.parameters, TOLERANCE))
    evidence.extend(quantity_evidence)
    if not contract_amounts:
        return _result(
            context,
            "CONTRACT_AMOUNT_001",
            "need_review",
            "medium",
            "Missing contract amount prevents contract amount check.",
            {"contract_amount": "present"},
            {"contract_amount": None},
            evidence or [_missing_ref(None, "amount_including_tax", doc_type="contract_review")],
        )
    if not references:
        return _result(
            context,
            "CONTRACT_AMOUNT_001",
            "need_review",
            "medium",
            "No task amount evidence is available for contract amount cross-check.",
            {"reference_amount": "available"},
            {"contract_amount": contract_amounts[0][0]},
            evidence,
        )

    contract_amount = contract_amounts[0][0]
    tolerance = _tolerance_amount(context.parameters, TOLERANCE)
    tolerance_ratio = float(context.parameters.get("tolerance_ratio", 0) or 0)
    mismatches = []
    for amount, field, _ in references:
        allowed = tolerance + abs(contract_amount) * tolerance_ratio
        if abs(amount - contract_amount) > allowed:
            mismatches.append({"field_name": field.field_name, "amount": amount})
    if mismatches or quantity_failures:
        return _result(
            context,
            "CONTRACT_AMOUNT_001",
            "warning",
            "medium",
            "Contract amount or quantity differs from available task evidence; manual review is required.",
            {"contract_amount": contract_amount, "tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
            {"mismatches": mismatches, "quantity_failures": quantity_failures},
            evidence,
        )
    return _result(
        context,
        "CONTRACT_AMOUNT_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Contract amount matches available task amount evidence.",
        {"contract_amount": contract_amount, "tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
        {"reference_amounts": [amount for amount, _, _ in references]},
        evidence,
    )


def rule_contract_counterparty(context: RuleContext) -> RuleResult:
    contract_parties = _text_fields_by_name(context, {"party_b", "counterparty_name"})
    references = _text_fields_by_name(
        context,
        {
            "supplier_name",
            "seller_name",
            "payee_name",
            "customer_name",
            "buyer_name",
            "payer_name",
            "mentioned_counterparties",
            "company_name",
        },
    )
    evidence = [_evidence_ref(document, field) for _, field, document in contract_parties + references]
    if not contract_parties:
        return _result(
            context,
            "CONTRACT_COUNTERPARTY_001",
            "need_review",
            "medium",
            "Missing contract counterparty fields prevent counterparty check.",
            {"contract_counterparty": "present"},
            {"contract_counterparty": None},
            evidence or [_missing_ref(None, "counterparty_name", doc_type="contract_review")],
        )
    if not references:
        return _result(
            context,
            "CONTRACT_COUNTERPARTY_001",
            "need_review",
            "medium",
            "No task party evidence is available for contract counterparty cross-check.",
            {"reference_counterparty": "available"},
            {"contract_counterparties": [value for value, _, _ in contract_parties]},
            evidence,
        )

    aliases = context.parameters.get("supplier_aliases")
    contract_names = {_normalize_name(value, aliases) for value, _, _ in contract_parties}
    unmatched = [value for value, _, _ in references if _normalize_name(value, aliases) not in contract_names]
    if unmatched:
        return _result(
            context,
            "CONTRACT_COUNTERPARTY_001",
            "warning",
            "medium",
            "Contract counterparty differs from available task party evidence.",
            {"counterparty_consistent": True},
            {"unmatched": unmatched},
            evidence,
        )
    return _result(
        context,
        "CONTRACT_COUNTERPARTY_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Contract counterparty matches available task party evidence.",
        {"counterparty_consistent": True},
        {"contract_counterparties": [value for value, _, _ in contract_parties]},
        evidence,
    )


def rule_contract_key_terms(context: RuleContext) -> RuleResult:
    missing: list[EvidenceRef] = []
    present: list[EvidenceRef] = []
    for field_name in CONTRACT_KEY_TERM_FIELDS:
        field, document = _first_contract_field(context, (field_name,))
        if field is None or document is None or _is_missing(field):
            missing.append(_missing_ref(document, field_name, field, "contract_review"))
        else:
            present.append(_evidence_ref(document, field))
    if missing:
        return _result(
            context,
            "CONTRACT_KEY_TERMS_001",
            "need_review",
            "medium",
            "Contract key terms are missing and require human review.",
            {"required_terms": list(CONTRACT_KEY_TERM_FIELDS)},
            {"missing_terms": [ref.field_name for ref in missing]},
            missing + present,
        )
    return _result(
        context,
        "CONTRACT_KEY_TERMS_001",
        _pass_or_warning(present),
        _severity_for_pass(present),
        "Contract key terms are present.",
        {"required_terms": list(CONTRACT_KEY_TERM_FIELDS)},
        {"missing_terms": []},
        present,
    )


def rule_contract_special_clause(context: RuleContext) -> RuleResult:
    present = []
    for field_name in CONTRACT_SPECIAL_CLAUSE_FIELDS:
        field, document = _first_contract_field(context, (field_name,))
        value = _text_value(field)
        if field is not None and document is not None and value and not _is_negative(value):
            present.append((field_name, value, field, document))
    evidence = [_evidence_ref(document, field) for _, _, field, document in present]
    if present:
        return _result(
            context,
            "CONTRACT_SPECIAL_CLAUSE_001",
            "warning",
            "high",
            "Contract contains special clauses; this is a risk prompt only and not a legal opinion.",
            {"special_clauses": "review_if_present"},
            {"special_clauses": [{"field_name": name, "value": value} for name, value, _, _ in present]},
            evidence,
        )
    return _result(
        context,
        "CONTRACT_SPECIAL_CLAUSE_001",
        "pass",
        "info",
        "No configured special clauses were detected.",
        {"special_clauses": "review_if_present"},
        {"special_clauses": []},
        [_task_ref(context, "special_clauses")],
    )


def rule_contract_signature_seal(context: RuleContext) -> RuleResult:
    signature_field, signature_doc = _first_contract_field(context, ("signature_detected",))
    seal_field, seal_doc = _first_contract_field(context, ("seal_detected",))
    signature_value = _text_value(signature_field)
    seal_value = _text_value(seal_field)
    evidence = []
    if signature_field is not None and signature_doc is not None:
        evidence.append(_evidence_ref(signature_doc, signature_field))
    else:
        evidence.append(_missing_ref(signature_doc, "signature_detected", signature_field, "contract_review"))
    if seal_field is not None and seal_doc is not None:
        evidence.append(_evidence_ref(seal_doc, seal_field))
    else:
        evidence.append(_missing_ref(seal_doc, "seal_detected", seal_field, "contract_review"))

    if _is_affirmative(signature_value) and _is_affirmative(seal_value):
        return _result(
            context,
            "CONTRACT_SIGNATURE_SEAL_001",
            _pass_or_warning(evidence),
            _severity_for_pass(evidence),
            "Contract signature and seal evidence are present; authenticity is not judged.",
            {"signature_and_seal": "present"},
            {"signature_detected": signature_value, "seal_detected": seal_value},
            evidence,
        )
    return _result(
        context,
        "CONTRACT_SIGNATURE_SEAL_001",
        "need_review",
        "medium",
        "Contract signature or seal evidence is missing or marked absent; authenticity is not judged.",
        {"signature_and_seal": "present"},
        {"signature_detected": signature_value, "seal_detected": seal_value},
        evidence,
    )


RULE_REGISTRY: dict[str, Callable[[RuleContext], RuleResult]] = {
    "PROC_MISSING_001": rule_missing_required,
    "PROC_TIME_001": rule_time_order,
    "PROC_AMOUNT_001": rule_amount,
    "PROC_NAME_001": rule_name,
    "PROC_ITEM_001": rule_item,
    "PROC_QTY_001": rule_qty,
    "PROC_TAX_001": rule_tax,
    "SALES_MISSING_001": rule_sales_missing_required,
    "SALES_TIME_001": rule_sales_time_order,
    "SALES_AMOUNT_001": rule_sales_amount,
    "SALES_NAME_001": rule_sales_name,
    "SALES_QTY_001": rule_sales_qty,
    "SALES_REVENUE_001": rule_sales_revenue_cutoff,
    "CONF_MISSING_001": rule_confirmation_missing_required,
    "CONF_DATE_001": rule_confirmation_date,
    "CONF_AMOUNT_001": rule_confirmation_amount,
    "CONF_NAME_001": rule_confirmation_name,
    "CONF_SEAL_SIGN_001": rule_confirmation_seal_sign,
    "INTERVIEW_MISSING_001": rule_interview_missing_required,
    "INTERVIEW_DATE_001": rule_interview_date,
    "INTERVIEW_SIGNATURE_001": rule_interview_signature,
    "INTERVIEW_AMOUNT_001": rule_interview_amount,
    "INTERVIEW_COUNTERPARTY_001": rule_interview_counterparty,
    "CONTRACT_MISSING_001": rule_contract_missing_required,
    "CONTRACT_PERIOD_001": rule_contract_period,
    "CONTRACT_AMOUNT_001": rule_contract_amount,
    "CONTRACT_COUNTERPARTY_001": rule_contract_counterparty,
    "CONTRACT_KEY_TERMS_001": rule_contract_key_terms,
    "CONTRACT_SPECIAL_CLAUSE_001": rule_contract_special_clause,
    "CONTRACT_SIGNATURE_SEAL_001": rule_contract_signature_seal,
}


def _to_model(task_id: UUID, rule: AuditRule, result: RuleResult) -> AuditResult:
    return AuditResult(
        task_id=task_id,
        rule_id=rule.id,
        rule_code=result.rule_code,
        rule_version=rule.version,
        business_key=result.business_key,
        status=result.status,
        severity=result.severity,
        message=result.message,
        expected_value=result.expected_value,
        actual_value=result.actual_value,
        evidence={"refs": [ref.__dict__ | {"document_id": str(ref.document_id) if ref.document_id else None} for ref in result.evidence]},
        rag_citations=None,
        review_status="not_required" if result.status == "pass" else "pending",
        reviewed_by=None,
        reviewed_at=None,
    )


def _rag_citations_for_result(db: Session, result: AuditResult) -> list[dict] | None:
    if result.status == "pass":
        return None
    query_text = " ".join(
        str(value)
        for value in (result.rule_code, result.message, result.severity, result.business_key)
        if value
    )
    citations: list[dict] = []
    for knowledge_base in RAG_KNOWLEDGE_BASES:
        metadata_filter = {"task_id": str(result.task_id)} if knowledge_base == "workpaper" else {}
        rag_result = rag_service.query(
            db,
            query_text=query_text,
            knowledge_base=knowledge_base,
            top_k=3,
            metadata_filter=metadata_filter,
            task_id=result.task_id,
        )
        for citation in rag_result["citations"]:
            citations.append(_json_citation(citation))
            if len(citations) >= 3:
                break
        if len(citations) >= 3:
            break
    _attach_explanation(db, result, query_text, citations)
    return citations


def _attach_explanation(db: Session, result: AuditResult, query_text: str, citations: list[dict]) -> None:
    if not citations:
        model_invocation_service.add_invocation(
            db,
            provider="not-called",
            model_name="not-called",
            invocation_type="explain",
            task_id=result.task_id,
            prompt_version="audit-explain-v1",
            output_schema="AuditResultExplanation",
            status="skipped",
            input_text=query_text,
            cost_estimate={"currency": "USD", "amount": None, "basis": "not_called_no_citations"},
        )
        _store_explanation(
            result,
            {
                "status": "no_citations",
                "provider_kind": "not_called",
                "provider_name": "not-called",
                "explanation": "Evidence insufficient. No citation was available for grounded exception explanation.",
                "limitations": ["No RAG citation was available."],
            },
        )
        return

    provider = llm_provider.get_llm_provider("explain")
    provider_result = provider.explain_audit_result(result.rule_code, result.message, result.severity, citations)
    model_invocation_service.add_invocation(
        db,
        provider=provider_result.provider_name,
        model_name=provider_result.model_name or provider_result.provider_name,
        invocation_type="explain",
        task_id=result.task_id,
        prompt_version="audit-explain-v1",
        output_schema="AuditResultExplanation",
        status="success" if provider_result.status == "ok" else "fallback",
        latency_ms=provider_result.latency_ms,
        input_text=query_text,
        token_usage=provider_result.token_usage,
        error={"message": provider_result.error} if provider_result.error else None,
    )
    explanation, limitations = _explanation_from_provider(provider_result, result, citations)
    _store_explanation(
        result,
        {
            **llm_provider.provider_info(provider_result),
            "explanation": explanation,
            "limitations": limitations,
        },
    )


def _explanation_from_provider(
    provider_result: llm_provider.ProviderResult,
    result: AuditResult,
    citations: list[dict],
) -> tuple[str, list[str]]:
    if provider_result.status == "ok" and isinstance(provider_result.payload, dict):
        explanation = provider_result.payload.get("explanation")
        if isinstance(explanation, str) and explanation.strip():
            limitations = provider_result.payload.get("limitations")
            return explanation.strip(), [str(item) for item in limitations] if isinstance(limitations, list) else []
    citation_titles = ", ".join(str(citation.get("title")) for citation in citations[:3])
    return (
        f"{result.rule_code} remains {result.status}: {result.message} Citations: {citation_titles}.",
        ["Explanation used deterministic fallback because no real/local explain provider returned grounded JSON."],
    )


def _store_explanation(result: AuditResult, explanation: dict) -> None:
    actual_value = result.actual_value if isinstance(result.actual_value, dict) else {}
    result.actual_value = actual_value | {"explanation": explanation}


def _json_citation(citation: dict) -> dict:
    return {
        "chunk_id": str(citation["chunk_id"]),
        "document_id": str(citation["document_id"]),
        "knowledge_base": citation["knowledge_base"],
        "title": citation["title"],
        "section": citation["section"],
        "page": citation["page"],
        "score": citation["score"],
        "quote": citation["quote"],
        "metadata": citation["metadata"],
    }


def _list_documents(db: Session, task_id: UUID) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.task_id == task_id)))


def _list_fields(db: Session, task_id: UUID) -> list[ExtractedField]:
    return list(db.scalars(select(ExtractedField).where(ExtractedField.task_id == task_id)))


def _business_groups(documents: list[Document]) -> dict[str, list[Document]]:
    groups: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        if document.business_key:
            groups[document.business_key].append(document)
    return groups


def _field_map(fields: list[ExtractedField]) -> dict[UUID, dict[str, ExtractedField]]:
    mapped: dict[UUID, dict[str, ExtractedField]] = defaultdict(dict)
    for field in fields:
        mapped[field.document_id][field.field_name] = field
    return mapped


def _docs_by_type(context: RuleContext, doc_type: str) -> list[Document]:
    return [document for document in context.documents if document.doc_type == doc_type]


def _first_field(
    context: RuleContext, doc_type: str, field_name: str
) -> tuple[ExtractedField | None, Document | None]:
    for document in _docs_by_type(context, doc_type):
        field = context.fields.get(document.id, {}).get(field_name)
        if field is not None and not _is_missing(field):
            return field, document
    documents = _docs_by_type(context, doc_type)
    return None, documents[0] if documents else None


def _fields(
    context: RuleContext, doc_type: str, field_name: str
) -> list[tuple[ExtractedField, Document]]:
    values = []
    for document in _docs_by_type(context, doc_type):
        field = context.fields.get(document.id, {}).get(field_name)
        if field is not None and not _is_missing(field):
            values.append((field, document))
    return values


def _first_field_from(
    context: RuleContext, lookups: tuple[tuple[str, str], ...]
) -> tuple[ExtractedField | None, Document | None]:
    fallback_document = None
    for doc_type, field_name in lookups:
        field, document = _first_field(context, doc_type, field_name)
        fallback_document = fallback_document or document
        if field is not None and document is not None:
            return field, document
    return None, fallback_document


def _amounts_from(
    context: RuleContext, lookups: tuple[tuple[str, str], ...]
) -> list[tuple[float, ExtractedField, Document]]:
    values: list[tuple[float, ExtractedField, Document]] = []
    for doc_type, field_name in lookups:
        values.extend(_amounts(context, doc_type, field_name))
    return values


def _first_interview_field(
    context: RuleContext, field_names: tuple[str, ...]
) -> tuple[ExtractedField | None, Document | None]:
    for document in context.documents:
        if document.doc_type not in INTERVIEW_DOC_TYPES:
            continue
        for field_name in field_names:
            field = context.fields.get(document.id, {}).get(field_name)
            if field is not None and not _is_missing(field):
                return field, document
    return None, None


def _first_contract_field(
    context: RuleContext, field_names: tuple[str, ...]
) -> tuple[ExtractedField | None, Document | None]:
    for document in context.documents:
        if document.doc_type not in CONTRACT_DOC_TYPES:
            continue
        for field_name in field_names:
            field = context.fields.get(document.id, {}).get(field_name)
            if field is not None and not _is_missing(field):
                return field, document
    return None, None


def _amount_fields_by_name(
    context: RuleContext, field_names: set[str]
) -> list[tuple[float, ExtractedField, Document]]:
    values = []
    for document in context.documents:
        for field_name in field_names:
            field = context.fields.get(document.id, {}).get(field_name)
            amount = _amount_value(field)
            if field is not None and amount is not None:
                values.append((amount, field, document))
    return values


def _text_fields_by_name(
    context: RuleContext, field_names: set[str]
) -> list[tuple[str, ExtractedField, Document]]:
    values = []
    for document in context.documents:
        for field_name in field_names:
            field = context.fields.get(document.id, {}).get(field_name)
            value = _text_value(field)
            if field is not None and value:
                values.append((value, field, document))
    return values


def _is_missing(field: ExtractedField | None) -> bool:
    return (
        field is None
        or field.value_text is None
        or "required_field_missing" in (field.warnings or [])
    )


def _text_value(field: ExtractedField | None) -> str | None:
    if field is None or field.value_text is None:
        return None
    return field.value_text.strip()


def _date_value(field: ExtractedField | None) -> date | None:
    if field is None:
        return None
    value = None
    if field.value_normalized:
        value = field.value_normalized.get("value")
    value = value or field.value_text
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _amount_value(field: ExtractedField | None) -> float | None:
    if field is None:
        return None
    if field.value_normalized and "amount" in field.value_normalized:
        return float(field.value_normalized["amount"])
    value = _text_value(field)
    if not value:
        return None
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
    return float(match.group(0).replace(",", "")) if match else None


def _rate_value(field: ExtractedField | None) -> float | None:
    if field is None:
        return None
    if field.value_normalized and "rate" in field.value_normalized:
        return float(field.value_normalized["rate"])
    value = _text_value(field)
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    return float(match.group(1)) / 100 if match else None


def _single_amount(
    context: RuleContext, doc_type: str, field_name: str
) -> list[tuple[float, ExtractedField, Document]]:
    amounts = _amounts(context, doc_type, field_name)
    return amounts[:1]


def _amounts(
    context: RuleContext, doc_type: str, field_name: str
) -> list[tuple[float, ExtractedField, Document]]:
    values = []
    for field, document in _fields(context, doc_type, field_name):
        amount = _amount_value(field)
        if amount is not None:
            values.append((amount, field, document))
    return values


def _date_values(
    context: RuleContext, doc_type: str, field_name: str
) -> list[tuple[date, ExtractedField, Document]]:
    values = []
    for field, document in _fields(context, doc_type, field_name):
        value = _date_value(field)
        if value is not None:
            values.append((value, field, document))
    return values


def _single_rate(
    context: RuleContext, doc_type: str, field_name: str
) -> list[tuple[float, ExtractedField, Document]]:
    for field, document in _fields(context, doc_type, field_name):
        rate = _rate_value(field)
        if rate is not None:
            return [(rate, field, document)]
    return []


def _aggregate_quantity_map(
    values: list[tuple[ExtractedField, Document]], item_mappings: object = None
) -> dict[str, float] | None:
    totals: dict[str, float] = defaultdict(float)
    for field, _ in values:
        quantity_map = _quantity_map(field, item_mappings)
        if quantity_map is None:
            return None
        for key, quantity in quantity_map.items():
            totals[key] += quantity
    return dict(totals) or None


def _aggregate_item_keys(
    values: list[tuple[ExtractedField, Document]], item_mappings: object = None
) -> set[str] | None:
    keys: set[str] = set()
    for field, _ in values:
        item_keys = _item_keys(field, item_mappings)
        if item_keys is None:
            return None
        keys.update(item_keys)
    return keys or None


def _item_keys(field: ExtractedField | None, item_mappings: object = None) -> set[str] | None:
    if field is None or not field.value_normalized:
        return None
    items = field.value_normalized.get("items")
    if not isinstance(items, list) or not items:
        return None
    keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_key = item.get("item_key") or item.get("item_name")
        if not raw_key:
            return None
        keys.add(_mapped_item_name(str(raw_key), item_mappings))
    return keys or None


def _quantity_map(field: ExtractedField | None, item_mappings: object = None) -> dict[str, float] | None:
    if field is None or not field.value_normalized:
        return None
    items = field.value_normalized.get("items")
    if not isinstance(items, list) or not items:
        return None
    totals: dict[str, float] = defaultdict(float)
    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = item.get("quantity")
        if quantity is None:
            return None
        raw_key = item.get("item_key") or item.get("item_name") or "item"
        name = _mapped_item_name(str(raw_key), item_mappings)
        totals[name] += float(quantity)
    return dict(totals) or None


def _procurement_quantity_failure(
    item_quantities: dict[str, dict[str, float]],
    item_key: str,
    tolerance: float,
) -> dict | None:
    values = {doc_type: quantity_map.get(item_key) for doc_type, quantity_map in item_quantities.items()}
    if None in values.values():
        return values | {"reason": "missing_item_quantity"}
    request = values.get("purchase_request") or 0.0
    contract = values.get("purchase_contract") or 0.0
    receipt = values.get("warehouse_receipt") or 0.0
    invoice = values.get("invoice") or 0.0
    reasons = []
    if request + tolerance < contract:
        reasons.append("request_less_than_contract")
    if contract + tolerance < receipt:
        reasons.append("contract_less_than_receipt")
    if abs(receipt - invoice) > tolerance:
        reasons.append("receipt_invoice_mismatch")
    return values | {"reasons": reasons} if reasons else None


def _contract_quantity_failures(context: RuleContext, tolerance: float) -> tuple[dict, list[EvidenceRef]]:
    contract_totals: dict[str, float] = defaultdict(float)
    reference_totals: dict[str, float] = defaultdict(float)
    evidence: list[EvidenceRef] = []
    for document in context.documents:
        field = context.fields.get(document.id, {}).get("item_lines")
        quantity_map = _quantity_map(field, context.parameters.get("item_mappings"))
        if field is None or quantity_map is None:
            continue
        if document.doc_type in CONTRACT_DOC_TYPES:
            target = contract_totals
        else:
            target = reference_totals
        evidence.append(_evidence_ref(document, field))
        for item_key, quantity in quantity_map.items():
            target[item_key] += quantity

    if not contract_totals or not reference_totals:
        return {}, []
    item_keys = set(contract_totals) | set(reference_totals)
    failures = {
        item_key: {
            "contract_quantity": contract_totals.get(item_key),
            "reference_quantity": reference_totals.get(item_key),
        }
        for item_key in sorted(item_keys)
        if contract_totals.get(item_key) is None
        or reference_totals.get(item_key) is None
        or abs(contract_totals[item_key] - reference_totals[item_key]) > tolerance
    }
    return failures, evidence


def _missing_amount_refs(items: list[tuple[str, str, list]]) -> list[EvidenceRef]:
    return [
        EvidenceRef(None, doc_type, field_name, None, None)
        for doc_type, field_name, values in items
        if not values
    ]


def _amount_evidence(values: list[tuple[float, ExtractedField, Document]]) -> list[EvidenceRef]:
    return [_evidence_ref(document, field, amount) for amount, field, document in values]


def _rate_evidence(values: list[tuple[float, ExtractedField, Document]]) -> list[EvidenceRef]:
    return [_evidence_ref(document, field, rate) for rate, field, document in values]


def _evidence_ref(
    document: Document, field: ExtractedField, value: object | None = None
) -> EvidenceRef:
    return EvidenceRef(
        document_id=document.id,
        doc_type=document.doc_type,
        field_name=field.field_name,
        value=value if value is not None else field.value_text,
        source_page=field.source_page,
        source_text=field.source_text,
        source_bbox=field.source_bbox,
        confidence=field.confidence,
    )


def _missing_ref(
    document: Document | None,
    field_name: str,
    field: ExtractedField | None = None,
    doc_type: str | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        document_id=document.id if document else (field.document_id if field else None),
        doc_type=document.doc_type if document else doc_type,
        field_name=field_name,
        value=None,
        source_page=field.source_page if field else None,
        source_text=field.source_text if field else None,
        source_bbox=field.source_bbox if field else None,
        confidence=field.confidence if field else None,
    )


def _task_ref(context: RuleContext, field_name: str) -> EvidenceRef:
    return EvidenceRef(None, None, field_name, context.business_key, None)


def _result(
    context: RuleContext,
    rule_code: str,
    status: str,
    severity: str,
    message: str,
    expected_value: dict | None,
    actual_value: dict | None,
    evidence: list[EvidenceRef],
) -> RuleResult:
    return RuleResult(
        rule_code=rule_code,
        business_key=context.business_key,
        status=status,
        severity=severity,
        message=message,
        expected_value=expected_value,
        actual_value=actual_value,
        evidence=evidence or [_task_ref(context, rule_code)],
    )


def _pass_or_warning(evidence: list[EvidenceRef]) -> str:
    return "warning" if any(_low_confidence(ref) for ref in evidence) else "pass"


def _severity_for_pass(evidence: list[EvidenceRef]) -> str:
    return "medium" if any(_low_confidence(ref) for ref in evidence) else "info"


def _low_confidence(ref: EvidenceRef) -> bool:
    return ref.confidence is not None and ref.confidence < 0.6


def _normalize_name(value: str, aliases: object = None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if not isinstance(aliases, dict):
        return normalized
    for canonical, alias_values in aliases.items():
        names = alias_values if isinstance(alias_values, list) else [alias_values]
        normalized_names = {_normalize_name(str(name)) for name in [canonical, *names]}
        if normalized in normalized_names:
            return _normalize_name(str(canonical))
    return normalized


def _is_affirmative(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip().casefold()
    return normalized in {"yes", "true", "signed", "detected", "present", "sealed", "有", "是", "已签署", "已盖章"}


def _is_negative(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.strip().casefold()
    return normalized in {"no", "false", "none", "n/a", "not applicable", "absent", "无", "否", "不适用"}


def _mapped_item_name(value: str, mappings: object = None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if not isinstance(mappings, dict):
        return normalized
    for canonical, alias_values in mappings.items():
        names = alias_values if isinstance(alias_values, list) else [alias_values]
        normalized_names = {_mapped_item_name(str(name)) for name in [canonical, *names]}
        if normalized in normalized_names:
            return _mapped_item_name(str(canonical))
    return normalized


def _tolerance_amount(parameters: dict, default: float) -> float:
    return float(parameters.get("tolerance_amount", parameters.get("tolerance", default)) or 0)


def _allowed_tax_rates(parameters: dict) -> set[float]:
    raw = parameters.get("allowed_tax_rates") or []
    if not isinstance(raw, list):
        return set()
    return {float(value) for value in raw}


def _rule_parameters(rule: AuditRule) -> dict:
    defaults = _default_rule(rule.rule_code)
    default_parameters = defaults["parameters"] if defaults else {}
    required_fields = rule.required_fields or (defaults["required_fields"] if defaults else [])
    parameters = default_parameters | (rule.parameters or {})
    if required_fields:
        parameters["required_fields"] = required_fields
    return parameters


def _rule_matches_scenario(rule: AuditRule, scenario: str) -> bool:
    if rule.scenario:
        return rule.scenario == scenario
    rule_code = rule.rule_code
    if scenario == "sales":
        return rule_code.startswith("SALES_")
    if scenario == "confirmation":
        return rule_code.startswith("CONF_")
    if scenario == "interview":
        return rule_code.startswith("INTERVIEW_")
    if scenario == "contract_review":
        return rule_code.startswith("CONTRACT_")
    return rule_code.startswith("PROC_")


def _default_rule(rule_code: str) -> dict | None:
    base = DEFAULT_RULES.get(rule_code)
    if base is None:
        return None
    return {
        "name": base["name"],
        "scenario": _scenario_for_rule_code(rule_code),
        "category": base["category"],
        "severity": base["severity"],
        "version": "1.0",
        "enabled": True,
        "expression": f"python:{rule_code}",
        "parameters": base["parameters"],
        "required_fields": [],
        "description": base["name"],
    }


def _scenario_for_rule_code(rule_code: str) -> str:
    if rule_code.startswith("SALES_"):
        return "sales"
    if rule_code.startswith("CONF_"):
        return "confirmation"
    if rule_code.startswith("INTERVIEW_"):
        return "interview"
    if rule_code.startswith("CONTRACT_"):
        return "contract_review"
    return "procurement"


def _rule_callable(rule: AuditRule) -> RuleFunc | None:
    expression = rule.expression or f"python:{rule.rule_code}"
    if expression.startswith("python:"):
        target_code = expression.split(":", 1)[1]
        if target_code != rule.rule_code:
            return None
        return RULE_REGISTRY.get(target_code)
    if expression.startswith("dsl:"):
        try:
            dsl = _parse_dsl_expression(expression)
        except HTTPException:
            return None

        def dsl_rule(context: RuleContext) -> RuleResult:
            return _evaluate_dsl_rule(context, rule, dsl)

        return dsl_rule
    return None


def _parse_dsl_expression(expression: str) -> dict:
    try:
        parsed = json.loads(expression.split(":", 1)[1].strip())
    except (IndexError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Rule DSL expression must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Rule DSL expression must be an object")
    operation = parsed.get("operation") or ("compare" if "compare" in parsed else "all_present")
    if operation not in {"all_present", "compare"}:
        raise HTTPException(status_code=400, detail="Rule DSL operation is not supported")
    if operation == "all_present":
        refs = parsed.get("all_present") or parsed.get("required_fields")
        if not isinstance(refs, list) or not refs:
            raise HTTPException(status_code=400, detail="Rule DSL all_present requires field references")
        [_parse_dsl_field_ref(ref) for ref in refs]
    if operation == "compare":
        compare = parsed.get("compare") if isinstance(parsed.get("compare"), dict) else parsed
        _parse_dsl_field_ref(compare.get("left"))
        _parse_dsl_field_ref(compare.get("right"))
        if compare.get("operator") not in {"eq", "ne", "gt", "gte", "lt", "lte"}:
            raise HTTPException(status_code=400, detail="Rule DSL compare operator is not supported")
    return parsed | {"operation": operation}


def _evaluate_dsl_rule(context: RuleContext, rule: AuditRule, dsl: dict) -> RuleResult:
    if dsl["operation"] == "all_present":
        refs = dsl.get("all_present") or dsl.get("required_fields") or []
        resolved = [_resolve_dsl_ref(context, ref) for ref in refs]
        missing = [item for item in resolved if item[0] is None]
        if missing:
            return _result(
                context,
                rule.rule_code,
                "need_review",
                rule.severity,
                "DSL required fields are missing.",
                {"required_fields": [_dsl_ref_label(ref) for ref in refs]},
                {"missing_fields": [f"{doc_type}.{field_name}" for _, _, (doc_type, field_name) in missing]},
                [_missing_ref(document, field_name, doc_type=doc_type) for _, document, (doc_type, field_name) in missing],
            )
        return _result(
            context,
            rule.rule_code,
            "pass",
            "info",
            "DSL required fields are present.",
            {"required_fields": [_dsl_ref_label(ref) for ref in refs]},
            {"present_fields": [_dsl_ref_label(ref) for ref in refs]},
            [_evidence_ref(document, field) for _, document, field in resolved if document is not None and field is not None],
        )

    compare = dsl.get("compare") if isinstance(dsl.get("compare"), dict) else dsl
    left_ref = compare.get("left")
    right_ref = compare.get("right")
    left_label = _dsl_ref_label(left_ref)
    right_label = _dsl_ref_label(right_ref)
    left_field, left_document, left_parts = _resolve_dsl_ref(context, left_ref)
    right_field, right_document, right_parts = _resolve_dsl_ref(context, right_ref)
    missing_refs = []
    if left_field is None:
        missing_refs.append((left_document, left_parts))
    if right_field is None:
        missing_refs.append((right_document, right_parts))
    if missing_refs:
        return _result(
            context,
            rule.rule_code,
            "need_review",
            rule.severity,
            "DSL compare fields are missing.",
            {"compare": f"{left_label} {compare.get('operator')} {right_label}"},
            {"missing_fields": [f"{doc_type}.{field_name}" for _, (doc_type, field_name) in missing_refs]},
            [_missing_ref(document, field_name, doc_type=doc_type) for document, (doc_type, field_name) in missing_refs],
        )
    left_value = _dsl_scalar(left_field)
    right_value = _dsl_scalar(right_field)
    passed = _dsl_compare(left_value, right_value, str(compare.get("operator")), float(compare.get("tolerance") or 0.0))
    return _result(
        context,
        rule.rule_code,
        "pass" if passed else "fail",
        "info" if passed else rule.severity,
        "DSL comparison passed." if passed else "DSL comparison failed.",
        {"left": left_label, "operator": compare.get("operator"), "right": right_label},
        {"left": left_value, "right": right_value},
        [
            _evidence_ref(left_document, left_field),
            _evidence_ref(right_document, right_field),
        ],
    )


def _parse_dsl_field_ref(ref: object) -> tuple[str, str]:
    if isinstance(ref, str) and "." in ref:
        doc_type, field_name = ref.split(".", 1)
    elif isinstance(ref, dict):
        doc_type = str(ref.get("doc_type") or "")
        field_name = str(ref.get("field_name") or "")
    else:
        raise HTTPException(status_code=400, detail="Rule DSL field reference is invalid")
    if not doc_type or not field_name:
        raise HTTPException(status_code=400, detail="Rule DSL field reference is invalid")
    return doc_type, field_name


def _resolve_dsl_ref(context: RuleContext, ref: object) -> tuple[ExtractedField | None, Document | None, tuple[str, str]]:
    doc_type, field_name = _parse_dsl_field_ref(ref)
    field, document = _first_field(context, doc_type, field_name)
    return field, document, (doc_type, field_name)


def _dsl_ref_label(ref: object) -> str:
    doc_type, field_name = _parse_dsl_field_ref(ref)
    return f"{doc_type}.{field_name}"


def _dsl_scalar(field: ExtractedField | None) -> object:
    if field is None:
        return None
    amount = _amount_value(field)
    if amount is not None:
        return amount
    date_value = _date_value(field)
    if date_value is not None:
        return date_value.isoformat()
    return _text_value(field)


def _dsl_compare(left: object, right: object, operator: str, tolerance: float) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        diff = float(left) - float(right)
        return {
            "eq": abs(diff) <= tolerance,
            "ne": abs(diff) > tolerance,
            "gt": diff > tolerance,
            "gte": diff >= -tolerance,
            "lt": diff < -tolerance,
            "lte": diff <= tolerance,
        }[operator]
    return {
        "eq": left == right,
        "ne": left != right,
        "gt": str(left) > str(right),
        "gte": str(left) >= str(right),
        "lt": str(left) < str(right),
        "lte": str(left) <= str(right),
    }[operator]


def _validate_parameters(parameters: dict) -> None:
    unknown = set(parameters) - ALLOWED_PARAMETER_KEYS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported rule parameter: {sorted(unknown)[0]}")
    if "mismatch_status" in parameters and parameters["mismatch_status"] not in {"warning", "fail"}:
        raise HTTPException(status_code=400, detail="mismatch_status must be warning or fail")
    if "amount_basis" in parameters and parameters["amount_basis"] not in {"including_tax", "excluding_tax"}:
        raise HTTPException(status_code=400, detail="amount_basis must be including_tax or excluding_tax")
    for key in ("tolerance", "tolerance_amount", "tolerance_ratio", "date_tolerance_days", "recognition_max_days_after_signed"):
        if key in parameters:
            try:
                numeric_value = float(parameters[key])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key} must be numeric") from None
            if numeric_value < 0:
                raise HTTPException(status_code=400, detail=f"{key} must be non-negative")
    if "prepayment_allowed" in parameters and not isinstance(parameters["prepayment_allowed"], bool):
        raise HTTPException(status_code=400, detail="prepayment_allowed must be boolean")
    for key in ("supplier_aliases", "item_mappings"):
        if key in parameters and not isinstance(parameters[key], dict):
            raise HTTPException(status_code=400, detail=f"{key} must be an object")
    for key in ("allowed_tax_rates",):
        if key in parameters and not isinstance(parameters[key], list):
            raise HTTPException(status_code=400, detail=f"{key} must be a list")
        if key in parameters:
            try:
                [float(value) for value in parameters[key]]
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key} values must be numeric") from None
    if "required_fields" in parameters:
        if not isinstance(parameters["required_fields"], list) or not all(
            isinstance(value, str) for value in parameters["required_fields"]
        ):
            raise HTTPException(status_code=400, detail="required_fields values must be strings")


def _validate_rule_contract(
    rule_code: str,
    scenario: str,
    category: str,
    severity: str,
    expression: str,
    required_fields: list[str],
) -> None:
    if severity not in {"info", "medium", "high", "critical"}:
        raise HTTPException(status_code=400, detail="severity is not supported")
    if not category.strip():
        raise HTTPException(status_code=400, detail="category is required")
    if scenario != _scenario_for_rule_code(rule_code):
        raise HTTPException(status_code=400, detail="Rule code is not allowed for scenario")
    if expression.startswith("dsl:"):
        _parse_dsl_expression(expression)
        if not all(isinstance(value, str) for value in required_fields):
            raise HTTPException(status_code=400, detail="required_fields values must be strings")
        return
    if not expression.startswith("python:"):
        raise HTTPException(status_code=400, detail="Rule expression is not supported")
    target_code = expression.split(":", 1)[1]
    if target_code != rule_code or target_code not in RULE_REGISTRY:
        raise HTTPException(status_code=400, detail="Rule expression is not supported")
    if not all(isinstance(value, str) for value in required_fields):
        raise HTTPException(status_code=400, detail="required_fields values must be strings")


def _evaluation_read(rule: AuditRule, result: RuleResult) -> dict:
    return {
        "rule_code": result.rule_code,
        "rule_version": rule.version,
        "business_key": result.business_key,
        "status": result.status,
        "severity": result.severity,
        "message": result.message,
        "expected_value": result.expected_value,
        "actual_value": result.actual_value,
        "evidence": {
            "refs": [
                ref.__dict__ | {"document_id": str(ref.document_id) if ref.document_id else None}
                for ref in result.evidence
            ]
        },
    }


def _rule_snapshot(rule: AuditRule) -> dict:
    return {
        "id": str(rule.id),
        "rule_code": rule.rule_code,
        "name": rule.name,
        "scenario": rule.scenario,
        "category": rule.category,
        "severity": rule.severity,
        "version": rule.version,
        "enabled": rule.enabled,
        "expression": rule.expression,
        "parameters": rule.parameters,
        "required_fields": rule.required_fields,
        "description": rule.description,
        "created_by": rule.created_by,
    }


def _add_rule_log(
    db: Session,
    actor_name: str | None,
    action: str,
    target_id: UUID,
    before_value: dict | None,
    after_value: dict | None,
) -> None:
    db.add(
        AuditLog(
            actor_name=actor_name,
            task_id=None,
            action=action,
            target_type="audit_rule",
            target_id=target_id,
            before_value=redact(before_value),
            after_value=redact(after_value),
        )
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
