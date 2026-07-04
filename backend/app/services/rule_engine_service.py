from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.audit_result import AuditResult
from app.models.audit_rule import AuditRule
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.services.extraction_service import schema_specs_for


@dataclass(frozen=True)
class EvidenceRef:
    document_id: UUID | None
    doc_type: str | None
    field_name: str
    value: object
    source_text: str | None = None
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


RuleFunc = Callable[[RuleContext], RuleResult]
TOLERANCE = 1.0
DEFAULT_RULES = {
    "PROC_MISSING_001": ("必填字段缺失检查", {}),
    "PROC_TIME_001": ("采购时间顺序检查", {}),
    "PROC_AMOUNT_001": ("金额一致性检查", {"tolerance_amount": 1.0, "tolerance_ratio": 0.0}),
    "PROC_NAME_001": ("主体名称一致性检查", {"mismatch_status": "warning", "supplier_aliases": {}}),
    "PROC_QTY_001": ("数量一致性检查", {"tolerance_amount": 0.0001, "item_mappings": {}}),
    "PROC_TAX_001": ("税率与税额基础校验", {"tolerance_amount": 1.0, "allowed_tax_rates": []}),
    "SALES_MISSING_001": ("销售必填字段缺失检查", {}),
    "SALES_TIME_001": ("销售时间顺序检查", {"date_tolerance_days": 0}),
    "SALES_AMOUNT_001": ("销售金额一致性检查", {"tolerance_amount": 1.0, "tolerance_ratio": 0.0}),
    "SALES_NAME_001": ("销售客户名称一致性检查", {"mismatch_status": "warning", "supplier_aliases": {}}),
    "SALES_QTY_001": ("销售数量一致性检查", {"tolerance_amount": 0.0001, "item_mappings": {}}),
}
ALLOWED_PARAMETER_KEYS = {
    "tolerance",
    "tolerance_amount",
    "tolerance_ratio",
    "allowed_tax_rates",
    "supplier_aliases",
    "item_mappings",
    "prepayment_allowed",
    "date_tolerance_days",
    "mismatch_status",
}


def run_audit(db: Session, task_id: UUID) -> list[AuditResult]:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    rules = list_rules(db)
    enabled_rules = [
        rule
        for rule in rules
        if rule.enabled and rule.rule_code in RULE_REGISTRY and _rule_matches_scenario(rule.rule_code, task.scenario)
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
            )
            result = RULE_REGISTRY[rule.rule_code](context)
            db.add(_to_model(task_id, rule, result))

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
    for code, (name, parameters) in DEFAULT_RULES.items():
        if code not in existing_codes:
            db.add(
                AuditRule(
                    rule_code=code,
                    name=name,
                    version="1.0",
                    enabled=True,
                    parameters=parameters,
                    description=name,
                )
            )
    db.commit()
    return list(db.scalars(select(AuditRule).order_by(AuditRule.rule_code.asc())))


def create_rule(
    db: Session,
    *,
    rule_code: str,
    name: str,
    version: str,
    enabled: bool,
    parameters: dict,
    description: str | None,
    actor_name: str | None = None,
) -> AuditRule:
    if rule_code not in RULE_REGISTRY:
        raise HTTPException(status_code=400, detail="Rule code is not in Python registry")
    if db.scalar(select(AuditRule).where(AuditRule.rule_code == rule_code)) is not None:
        raise HTTPException(status_code=400, detail="Rule already exists")
    _validate_parameters(parameters)
    rule = AuditRule(
        rule_code=rule_code,
        name=name,
        version=version,
        enabled=enabled,
        parameters=parameters,
        description=description,
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
    version: str | None = None,
    enabled: bool | None = None,
    parameters: dict | None = None,
    description: str | None = None,
    actor_name: str | None = None,
) -> AuditRule:
    rule = db.get(AuditRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    before = _rule_snapshot(rule)
    if name is not None:
        rule.name = name
    if version is not None:
        rule.version = version
    if enabled is not None:
        rule.enabled = enabled
    if parameters is not None:
        _validate_parameters(parameters)
        rule.parameters = parameters
    if description is not None:
        rule.description = description
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
    if rule.rule_code not in RULE_REGISTRY:
        raise HTTPException(status_code=400, detail="Rule code is not in Python registry")
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if not _rule_matches_scenario(rule.rule_code, task.scenario):
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
        _evaluation_read(rule, RULE_REGISTRY[rule.rule_code](
            RuleContext(
                task_id=task_id,
                scenario=task.scenario,
                business_key=business_key,
                documents=group_documents,
                fields=fields,
                parameters=merged_parameters,
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
        ("purchase_request", "approval_date"),
        ("purchase_contract", "signing_date"),
        ("warehouse_receipt", "receipt_date"),
        ("invoice", "invoice_date"),
        ("accounting_voucher", "voucher_date"),
        ("payment_receipt", "payment_date"),
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
        {"previous": comparable_values[index - 1][0], "next": comparable_values[index][0]}
        for index in range(1, len(comparable_values))
        if comparable_values[index - 1][1] > comparable_values[index][1] + timedelta(days=tolerance_days)
    ]
    evidence = [_evidence_ref(document, field) for _, _, field, document in values]
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
        {"dates": {name: value.isoformat() for name, value, _, _ in values}},
        evidence,
    )


def rule_amount(context: RuleContext) -> RuleResult:
    contract_amount = _single_amount(context, "purchase_contract", "amount_including_tax")
    invoice_amounts = _amounts(context, "invoice", "amount_including_tax")
    payment_amounts = _amounts(context, "payment_receipt", "amount")
    voucher_amounts = _amounts(context, "accounting_voucher", "amount")
    missing = _missing_amount_refs(
        [
            ("purchase_contract", "amount_including_tax", contract_amount),
            ("invoice", "amount_including_tax", invoice_amounts),
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
            {"amounts": "contract, invoice, payment"},
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
            {"contract_amount": contract_total, "tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
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
        {"contract_amount": contract_total, "tolerance": tolerance, "tolerance_ratio": tolerance_ratio},
        {"invoice_total": invoice_total, "payment_total": payment_total, "voucher_amounts": voucher_values},
        evidence,
    )


def rule_name(context: RuleContext) -> RuleResult:
    checks = (
        ("purchase_contract", "supplier_name"),
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


def rule_qty(context: RuleContext) -> RuleResult:
    quantities = []
    missing: list[EvidenceRef] = []
    for doc_type in ("purchase_contract", "warehouse_receipt", "invoice"):
        field, document = _first_field(context, doc_type, "item_lines")
        quantity_map = _quantity_map(field, context.parameters.get("item_mappings"))
        if field is None or document is None or quantity_map is None:
            missing.append(_missing_ref(document, "item_lines.quantity", field, doc_type))
        else:
            quantities.append((doc_type, quantity_map, field, document))
    if missing:
        return _result(
            context,
            "PROC_QTY_001",
            "need_review",
            "medium",
            "Missing line item quantities prevent quantity check.",
            {"quantity": "contract = receipt = invoice"},
            {"missing_fields": [ref.field_name for ref in missing]},
            missing,
        )

    tolerance = _tolerance_amount(context.parameters, 0.0001)
    evidence = [_evidence_ref(document, field) for _, _, field, document in quantities]
    item_quantities = {doc_type: quantity_map for doc_type, quantity_map, _, _ in quantities}
    values = {
        doc_type: sum(quantity_map.values())
        for doc_type, quantity_map, _, _ in quantities
    }
    item_keys = {item_key for quantity_map in item_quantities.values() for item_key in quantity_map}
    quantity_failures = {
        item_key: {
            doc_type: quantity_map.get(item_key)
            for doc_type, quantity_map in item_quantities.items()
        }
        for item_key in item_keys
        if None in {quantity_map.get(item_key) for quantity_map in item_quantities.values()}
        or max(quantity_map.get(item_key, 0.0) for quantity_map in item_quantities.values())
        - min(quantity_map.get(item_key, 0.0) for quantity_map in item_quantities.values())
        > tolerance
    }
    if quantity_failures:
        return _result(
            context,
            "PROC_QTY_001",
            "fail",
            "high",
            "Contract, receipt, and invoice quantities do not match.",
            {"quantity": "contract = receipt = invoice", "tolerance": tolerance},
            values | {"item_quantities": item_quantities, "failures": quantity_failures},
            evidence,
        )
    return _result(
        context,
        "PROC_QTY_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Contract, receipt, and invoice quantities match.",
        {"quantity": "contract = receipt = invoice", "tolerance": tolerance},
        values | {"item_quantities": item_quantities},
        evidence,
    )


def rule_tax(context: RuleContext) -> RuleResult:
    excluding = _single_amount(context, "invoice", "amount_excluding_tax")
    tax_amount = _single_amount(context, "invoice", "tax_amount")
    including = _single_amount(context, "invoice", "amount_including_tax")
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
    expected_total = excluding[0][0] + tax_amount[0][0]
    actual_total = including[0][0]
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


RULE_REGISTRY: dict[str, Callable[[RuleContext], RuleResult]] = {
    "PROC_MISSING_001": rule_missing_required,
    "PROC_TIME_001": rule_time_order,
    "PROC_AMOUNT_001": rule_amount,
    "PROC_NAME_001": rule_name,
    "PROC_QTY_001": rule_qty,
    "PROC_TAX_001": rule_tax,
    "SALES_MISSING_001": rule_sales_missing_required,
    "SALES_TIME_001": rule_sales_time_order,
    "SALES_AMOUNT_001": rule_sales_amount,
    "SALES_NAME_001": rule_sales_name,
    "SALES_QTY_001": rule_sales_qty,
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


def _single_rate(
    context: RuleContext, doc_type: str, field_name: str
) -> list[tuple[float, ExtractedField, Document]]:
    for field, document in _fields(context, doc_type, field_name):
        rate = _rate_value(field)
        if rate is not None:
            return [(rate, field, document)]
    return []


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
        name = _mapped_item_name(str(item.get("item_name") or "item"), item_mappings)
        totals[name] += float(quantity)
    return dict(totals) or None


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
        source_text=field.source_text,
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
        source_text=field.source_text if field else None,
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
    defaults = DEFAULT_RULES.get(rule.rule_code, ("", {}))[1]
    return defaults | (rule.parameters or {})


def _rule_matches_scenario(rule_code: str, scenario: str) -> bool:
    if scenario == "sales":
        return rule_code.startswith("SALES_")
    return rule_code.startswith("PROC_")


def _validate_parameters(parameters: dict) -> None:
    unknown = set(parameters) - ALLOWED_PARAMETER_KEYS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported rule parameter: {sorted(unknown)[0]}")
    if "mismatch_status" in parameters and parameters["mismatch_status"] not in {"warning", "fail"}:
        raise HTTPException(status_code=400, detail="mismatch_status must be warning or fail")
    for key in ("tolerance", "tolerance_amount", "tolerance_ratio", "date_tolerance_days"):
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
        "version": rule.version,
        "enabled": rule.enabled,
        "parameters": rule.parameters,
        "description": rule.description,
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
            before_value=before_value,
            after_value=after_value,
        )
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
