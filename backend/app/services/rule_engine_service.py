from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import re
from typing import Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_result import AuditResult
from app.models.audit_rule import AuditRule
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.services.extraction_service import SCHEMA_SPECS


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
    business_key: str
    documents: list[Document]
    fields: dict[UUID, dict[str, ExtractedField]]
    parameters: dict


RuleFunc = Callable[[RuleContext], RuleResult]
TOLERANCE = 1.0
DEFAULT_RULES = {
    "PROC_MISSING_001": ("必填字段缺失检查", {}),
    "PROC_TIME_001": ("采购时间顺序检查", {}),
    "PROC_AMOUNT_001": ("金额一致性检查", {"tolerance": 1.0}),
    "PROC_NAME_001": ("主体名称一致性检查", {"mismatch_status": "warning"}),
    "PROC_QTY_001": ("数量一致性检查", {"tolerance": 0.0001}),
    "PROC_TAX_001": ("税率与税额基础校验", {"tolerance": 1.0}),
}


def run_audit(db: Session, task_id: UUID) -> list[AuditResult]:
    rules = list_rules(db)
    enabled_rules = [rule for rule in rules if rule.enabled and rule.rule_code in RULE_REGISTRY]
    if not enabled_rules:
        raise HTTPException(status_code=400, detail="No enabled procurement rules are available")

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
                business_key=business_key,
                documents=group_documents,
                fields=fields,
                parameters=rule.parameters or {},
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
    if existing:
        return existing
    for code, (name, parameters) in DEFAULT_RULES.items():
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


def rule_missing_required(context: RuleContext) -> RuleResult:
    missing: list[EvidenceRef] = []
    present: list[EvidenceRef] = []
    for document in context.documents:
        specs = SCHEMA_SPECS.get(document.doc_type or "", ())
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

    inversions = [
        {"previous": values[index - 1][0], "next": values[index][0]}
        for index in range(1, len(values))
        if values[index - 1][1] > values[index][1]
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

    tolerance = float(context.parameters.get("tolerance", TOLERANCE))
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
    if invoice_total - contract_total > tolerance:
        failures["invoice_total"] = invoice_total
    if payment_total - contract_total > tolerance:
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
            {"contract_amount": contract_total, "tolerance": tolerance},
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
        {"contract_amount": contract_total, "tolerance": tolerance},
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

    normalized = {_normalize_name(value) for _, value, _, _ in values}
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
        quantity = _quantity_total(field)
        if field is None or document is None or quantity is None:
            missing.append(_missing_ref(document, "item_lines.quantity", field, doc_type))
        else:
            quantities.append((doc_type, quantity, field, document))
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

    tolerance = float(context.parameters.get("tolerance", 0.0001))
    evidence = [_evidence_ref(document, field) for _, _, field, document in quantities]
    values = {doc_type: quantity for doc_type, quantity, _, _ in quantities}
    if max(values.values()) - min(values.values()) > tolerance:
        return _result(
            context,
            "PROC_QTY_001",
            "fail",
            "high",
            "Contract, receipt, and invoice quantities do not match.",
            {"quantity": "contract = receipt = invoice", "tolerance": tolerance},
            values,
            evidence,
        )
    return _result(
        context,
        "PROC_QTY_001",
        _pass_or_warning(evidence),
        _severity_for_pass(evidence),
        "Contract, receipt, and invoice quantities match.",
        {"quantity": "contract = receipt = invoice", "tolerance": tolerance},
        values,
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

    tolerance = float(context.parameters.get("tolerance", TOLERANCE))
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


RULE_REGISTRY: dict[str, Callable[[RuleContext], RuleResult]] = {
    "PROC_MISSING_001": rule_missing_required,
    "PROC_TIME_001": rule_time_order,
    "PROC_AMOUNT_001": rule_amount,
    "PROC_NAME_001": rule_name,
    "PROC_QTY_001": rule_qty,
    "PROC_TAX_001": rule_tax,
}


def _to_model(task_id: UUID, rule: AuditRule, result: RuleResult) -> AuditResult:
    return AuditResult(
        task_id=task_id,
        rule_id=rule.id,
        rule_code=result.rule_code,
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


def _quantity_total(field: ExtractedField | None) -> float | None:
    if field is None or not field.value_normalized:
        return None
    items = field.value_normalized.get("items")
    if not isinstance(items, list) or not items:
        return None
    quantities = [item.get("quantity") for item in items if isinstance(item, dict)]
    if not quantities or any(quantity is None for quantity in quantities):
        return None
    return sum(float(quantity) for quantity in quantities)


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


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())
