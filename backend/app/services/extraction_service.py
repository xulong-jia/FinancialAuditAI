from dataclasses import dataclass
from datetime import date
import json
import re
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.extracted_field import ExtractedField
from app.schemas.document import ProcurementDocType
from app.schemas.extraction import ExtractedFieldValue, FieldType, validate_document_extraction


class ExtractionProviderError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    field_name: str
    field_label: str
    field_type: FieldType
    aliases: tuple[str, ...]
    is_required: bool = True


SCHEMA_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "purchase_request": (
        FieldSpec("request_no", "Request No", "text", ("request no", "request_no", "申请编号")),
        FieldSpec("request_date", "Request Date", "date", ("request date", "申请日期")),
        FieldSpec("approval_date", "Approval Date", "date", ("approval date", "审批日期")),
        FieldSpec("approval_status", "Approval Status", "status", ("approval status", "审批状态")),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "total_estimated_amount",
            "Total Estimated Amount",
            "money",
            ("total estimated amount", "estimated amount", "预计总金额"),
        ),
    ),
    "purchase_contract": (
        FieldSpec("contract_no", "Contract No", "text", ("contract no", "contract_no", "合同编号")),
        FieldSpec("signing_date", "Signing Date", "date", ("signing date", "签署日期")),
        FieldSpec("buyer_name", "Buyer Name", "name", ("buyer name", "buyer", "买方", "甲方")),
        FieldSpec("supplier_name", "Supplier Name", "name", ("supplier name", "supplier", "供应商", "乙方")),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "amount_including_tax",
            "Amount Including Tax",
            "money",
            ("amount including tax", "total with tax", "含税金额", "价税合计"),
        ),
        FieldSpec("tax_rate", "Tax Rate", "tax_rate", ("tax rate", "税率"), is_required=False),
        FieldSpec(
            "payment_terms",
            "Payment Terms",
            "text",
            ("payment terms", "付款条款"),
            is_required=False,
        ),
    ),
    "warehouse_receipt": (
        FieldSpec("receipt_no", "Receipt No", "text", ("receipt no", "receipt_no", "入库单号")),
        FieldSpec("receipt_date", "Receipt Date", "date", ("receipt date", "入库日期")),
        FieldSpec("supplier_name", "Supplier Name", "name", ("supplier name", "supplier", "供应商")),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "related_contract_no",
            "Related Contract No",
            "text",
            ("related contract no", "contract no", "关联合同"),
            is_required=False,
        ),
    ),
    "invoice": (
        FieldSpec("invoice_no", "Invoice No", "text", ("invoice no", "invoice number", "发票号码")),
        FieldSpec("invoice_date", "Invoice Date", "date", ("invoice date", "issue date", "开票日期")),
        FieldSpec("seller_name", "Seller Name", "name", ("seller name", "seller", "销售方")),
        FieldSpec("buyer_name", "Buyer Name", "name", ("buyer name", "buyer", "购买方")),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "amount_excluding_tax",
            "Amount Excluding Tax",
            "money",
            ("amount excluding tax", "subtotal", "不含税金额"),
        ),
        FieldSpec("tax_amount", "Tax Amount", "money", ("tax amount", "税额")),
        FieldSpec(
            "amount_including_tax",
            "Amount Including Tax",
            "money",
            ("amount including tax", "total with tax", "价税合计"),
        ),
    ),
    "accounting_voucher": (
        FieldSpec("voucher_no", "Voucher No", "text", ("voucher no", "凭证号")),
        FieldSpec("voucher_date", "Voucher Date", "date", ("voucher date", "凭证日期")),
        FieldSpec("summary", "Summary", "text", ("summary", "摘要")),
        FieldSpec("debit_subject", "Debit Subject", "text", ("debit subject", "借方科目")),
        FieldSpec("credit_subject", "Credit Subject", "text", ("credit subject", "贷方科目")),
        FieldSpec("amount", "Amount", "money", ("amount", "金额")),
        FieldSpec("supplier_name", "Supplier Name", "name", ("supplier name", "supplier", "供应商"), False),
        FieldSpec(
            "related_invoice_no",
            "Related Invoice No",
            "text",
            ("related invoice no", "invoice no", "关联发票"),
            False,
        ),
    ),
    "payment_receipt": (
        FieldSpec("payment_no", "Payment No", "text", ("payment no", "transaction no", "流水号")),
        FieldSpec("payment_date", "Payment Date", "date", ("payment date", "付款日期")),
        FieldSpec("payer_name", "Payer Name", "name", ("payer name", "payer", "付款方")),
        FieldSpec("payee_name", "Payee Name", "name", ("payee name", "payee", "收款方")),
        FieldSpec("amount", "Amount", "money", ("amount", "付款金额", "金额")),
        FieldSpec("currency", "Currency", "currency", ("currency", "币种")),
        FieldSpec("payment_purpose", "Payment Purpose", "text", ("payment purpose", "用途"), False),
        FieldSpec(
            "related_contract_no",
            "Related Contract No",
            "text",
            ("related contract no", "contract no", "关联合同"),
            False,
        ),
    ),
}


def extract_document(db: Session, document_id: UUID) -> list[ExtractedField]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.doc_type or document.doc_type == "unknown":
        raise HTTPException(status_code=400, detail="Document must be classified before extraction")
    if document.ocr_status != "completed":
        raise HTTPException(status_code=400, detail="Document OCR must complete before extraction")
    if document.doc_type not in SCHEMA_SPECS:
        raise HTTPException(status_code=400, detail="Document type is not supported for extraction")

    pages = _list_pages(db, document_id)
    if not pages:
        raise HTTPException(status_code=400, detail="Document pages are required before extraction")

    values = [_extract_field(spec, pages) for spec in SCHEMA_SPECS[document.doc_type]]
    try:
        validate_document_extraction(cast(ProcurementDocType, document.doc_type), values)
    except ValidationError as exc:
        document.extraction_status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail="Extraction schema validation failed") from exc

    db.query(ExtractedField).filter(ExtractedField.document_id == document_id).delete()
    for spec, value in zip(SCHEMA_SPECS[document.doc_type], values, strict=True):
        db.add(_to_model(document, spec, value))
    document.extraction_status = "completed"
    db.commit()
    return list_document_fields(db, document_id)


def list_document_fields(db: Session, document_id: UUID) -> list[ExtractedField]:
    return list(
        db.scalars(
            select(ExtractedField)
            .where(ExtractedField.document_id == document_id)
            .order_by(ExtractedField.created_at.asc(), ExtractedField.field_name.asc())
        )
    )


def list_task_fields(db: Session, task_id: UUID) -> list[ExtractedField]:
    return list(
        db.scalars(
            select(ExtractedField)
            .where(ExtractedField.task_id == task_id)
            .order_by(ExtractedField.created_at.asc(), ExtractedField.field_name.asc())
        )
    )


def parse_llm_json_output(raw_output: str) -> dict:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError("Invalid extraction provider JSON") from exc
    if not isinstance(parsed, dict):
        raise ExtractionProviderError("Extraction provider JSON must be an object")
    return parsed


def _list_pages(db: Session, document_id: UUID) -> list[DocumentPage]:
    return list(
        db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number.asc())
        )
    )


def _extract_field(spec: FieldSpec, pages: list[DocumentPage]) -> ExtractedFieldValue:
    if spec.field_type == "line_items":
        return _extract_line_items(spec, pages)

    match = _find_labeled_value(pages, spec.aliases)
    if match is None:
        return _missing_value(spec)

    value_text, page_number, source_text = match
    value_normalized, confidence, warnings = _normalize_value(spec.field_type, value_text)
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type=spec.field_type,
        value_text=value_text,
        value_normalized=value_normalized,
        confidence=confidence,
        source_page=page_number,
        source_text=source_text,
        source_bbox=None,
        warnings=warnings,
    )


def _extract_line_items(spec: FieldSpec, pages: list[DocumentPage]) -> ExtractedFieldValue:
    source_lines: list[tuple[int, str]] = []
    items: list[dict] = []
    for page in pages:
        for line in page.raw_text.splitlines():
            if re.search(r"(line item|item|明细)\s*[:：]", line, re.IGNORECASE):
                source_lines.append((page.page_number, line.strip()))
                items.append(
                    {
                        "item_name": _text_part(line, ("line item", "item", "item name", "品名")),
                        "quantity": _number_part(line, ("quantity", "qty", "数量")),
                        "unit": _text_part(line, ("unit", "单位")),
                        "unit_price": _number_part(line, ("unit price", "price", "单价")),
                        "amount": _number_part(line, ("amount", "金额")),
                    }
                )

    if not items:
        return _missing_value(spec)

    source_page, source_text = source_lines[0]
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type="line_items",
        value_text="\n".join(line for _, line in source_lines),
        value_normalized={"items": items},
        confidence=0.75,
        source_page=source_page,
        source_text=source_text,
        source_bbox=None,
        warnings=[],
    )


def _find_labeled_value(
    pages: list[DocumentPage], aliases: tuple[str, ...]
) -> tuple[str, int, str] | None:
    for page in pages:
        for raw_line in page.raw_text.splitlines():
            line = raw_line.strip()
            for alias in aliases:
                match = re.search(rf"{re.escape(alias)}\s*[:：]\s*(.+)", line, re.IGNORECASE)
                if match:
                    return match.group(1).strip(), page.page_number, line
    return None


def _normalize_value(field_type: FieldType, value_text: str) -> tuple[dict | None, float, list[str]]:
    if field_type == "date":
        normalized = _normalize_date(value_text)
        return ({"value": normalized}, 0.85, []) if normalized else (None, 0.3, ["invalid_date"])
    if field_type == "money":
        amount, currency = _normalize_amount(value_text)
        if amount is None:
            return None, 0.3, ["invalid_amount"]
        value = {"amount": amount}
        if currency:
            value["currency"] = currency
        return value, 0.85, []
    if field_type == "tax_rate":
        rate = _normalize_tax_rate(value_text)
        return ({"rate": rate}, 0.85, []) if rate is not None else (None, 0.3, ["invalid_tax_rate"])
    if field_type == "currency":
        currency = _normalize_currency(value_text)
        return ({"value": currency}, 0.85, []) if currency else (None, 0.3, ["invalid_currency"])
    return {"value": value_text.strip()}, 0.8, []


def _missing_value(spec: FieldSpec) -> ExtractedFieldValue:
    warning = "required_field_missing" if spec.is_required else "optional_field_missing"
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type=spec.field_type,
        value_text=None,
        value_normalized=None,
        confidence=0.0,
        source_page=None,
        source_text=None,
        source_bbox=None,
        warnings=[warning],
    )


def _to_model(document: Document, spec: FieldSpec, value: ExtractedFieldValue) -> ExtractedField:
    return ExtractedField(
        task_id=document.task_id,
        document_id=document.id,
        field_name=value.field_name,
        field_label=value.field_label,
        field_type=value.field_type,
        value_text=value.value_text,
        value_normalized=value.value_normalized,
        unit=_field_unit(value),
        currency=_field_currency(value),
        confidence=value.confidence,
        source_page=value.source_page,
        source_bbox=value.source_bbox,
        source_text=value.source_text,
        extraction_method="regex_heuristic",
        is_required=spec.is_required,
        is_verified=False,
        corrected_by=None,
        corrected_at=None,
        warnings=value.warnings,
    )


def _normalize_date(value: str) -> str | None:
    match = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
    if not match:
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
        if not match:
            return None
        month, day, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    else:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize_amount(value: str) -> tuple[float | None, str | None]:
    match = re.search(r"(?P<currency>CNY|USD|RMB|¥)?\s*(?P<amount>-?\d[\d,]*(?:\.\d+)?)", value, re.IGNORECASE)
    if not match:
        return None, None
    amount = float(match.group("amount").replace(",", ""))
    return amount, _normalize_currency(match.group("currency") or value)


def _normalize_tax_rate(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    return round(float(match.group(1)) / 100, 6) if match else None


def _normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper()
    if "USD" in upper:
        return "USD"
    if "CNY" in upper or "RMB" in upper or "¥" in value or "人民币" in value:
        return "CNY"
    return None


def _text_part(line: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:=]\s*([^;,\n]+)", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _number_part(line: str, labels: tuple[str, ...]) -> float | None:
    text = _text_part(line, labels)
    if text is None:
        return None
    amount, _ = _normalize_amount(text)
    return amount


def _field_unit(value: ExtractedFieldValue) -> str | None:
    if value.field_type == "line_items":
        return None
    return None


def _field_currency(value: ExtractedFieldValue) -> str | None:
    if not value.value_normalized:
        return None
    if value.field_type == "money":
        return cast(str | None, value.value_normalized.get("currency"))
    if value.field_type == "currency":
        return cast(str | None, value.value_normalized.get("value"))
    return None
