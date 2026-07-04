from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.document import DocumentDocType

FieldType = Literal["text", "date", "money", "tax_rate", "name", "status", "line_items", "currency"]


class LineItem(BaseModel):
    item_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    amount: float | None = None


class ExtractedFieldValue(BaseModel):
    field_name: str
    field_label: str
    field_type: FieldType
    value_text: str | None = None
    value_normalized: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_page: int | None = None
    source_text: str | None = None
    source_bbox: list[float] | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_line_items(self) -> "ExtractedFieldValue":
        if self.field_type == "line_items" and self.value_normalized:
            items = self.value_normalized.get("items", [])
            for item in items:
                LineItem.model_validate(item)
        return self


class ExtractedFieldRead(ExtractedFieldValue):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    document_id: UUID
    unit: str | None
    currency: str | None
    extraction_method: str
    is_required: bool
    is_verified: bool
    corrected_by: str | None
    corrected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PurchaseRequestExtraction(BaseModel):
    request_no: ExtractedFieldValue
    request_date: ExtractedFieldValue
    approval_date: ExtractedFieldValue
    approval_status: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    total_estimated_amount: ExtractedFieldValue


class PurchaseContractExtraction(BaseModel):
    contract_no: ExtractedFieldValue
    signing_date: ExtractedFieldValue
    buyer_name: ExtractedFieldValue
    supplier_name: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    amount_including_tax: ExtractedFieldValue
    tax_rate: ExtractedFieldValue
    payment_terms: ExtractedFieldValue


class WarehouseReceiptExtraction(BaseModel):
    receipt_no: ExtractedFieldValue
    receipt_date: ExtractedFieldValue
    supplier_name: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    related_contract_no: ExtractedFieldValue


class InvoiceExtraction(BaseModel):
    invoice_no: ExtractedFieldValue
    invoice_date: ExtractedFieldValue
    seller_name: ExtractedFieldValue
    buyer_name: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    amount_excluding_tax: ExtractedFieldValue
    tax_amount: ExtractedFieldValue
    amount_including_tax: ExtractedFieldValue


class AccountingVoucherExtraction(BaseModel):
    voucher_no: ExtractedFieldValue
    voucher_date: ExtractedFieldValue
    summary: ExtractedFieldValue
    debit_subject: ExtractedFieldValue
    credit_subject: ExtractedFieldValue
    amount: ExtractedFieldValue
    supplier_name: ExtractedFieldValue
    related_invoice_no: ExtractedFieldValue


class PaymentReceiptExtraction(BaseModel):
    payment_no: ExtractedFieldValue
    payment_date: ExtractedFieldValue
    payer_name: ExtractedFieldValue
    payee_name: ExtractedFieldValue
    amount: ExtractedFieldValue
    currency: ExtractedFieldValue
    payment_purpose: ExtractedFieldValue
    related_contract_no: ExtractedFieldValue


class SalesContractExtraction(BaseModel):
    contract_no: ExtractedFieldValue
    signing_date: ExtractedFieldValue
    customer_name: ExtractedFieldValue
    seller_name: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    amount_including_tax: ExtractedFieldValue
    payment_terms: ExtractedFieldValue
    delivery_terms: ExtractedFieldValue


class SalesOrderExtraction(BaseModel):
    order_no: ExtractedFieldValue
    order_date: ExtractedFieldValue
    customer_name: ExtractedFieldValue
    related_contract_no: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    amount: ExtractedFieldValue


class DeliveryOrderExtraction(BaseModel):
    delivery_no: ExtractedFieldValue
    delivery_date: ExtractedFieldValue
    customer_name: ExtractedFieldValue
    related_order_no: ExtractedFieldValue
    related_contract_no: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    warehouse_name: ExtractedFieldValue


class LogisticsReceiptExtraction(BaseModel):
    logistics_no: ExtractedFieldValue
    shipment_date: ExtractedFieldValue
    signed_date: ExtractedFieldValue
    receiver_name: ExtractedFieldValue
    customer_name: ExtractedFieldValue
    related_delivery_no: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    signer: ExtractedFieldValue


class SalesInvoiceExtraction(BaseModel):
    invoice_no: ExtractedFieldValue
    invoice_date: ExtractedFieldValue
    seller_name: ExtractedFieldValue
    buyer_name: ExtractedFieldValue
    item_lines: ExtractedFieldValue
    amount_excluding_tax: ExtractedFieldValue
    tax_amount: ExtractedFieldValue
    amount_including_tax: ExtractedFieldValue


class ReceiptVoucherExtraction(BaseModel):
    receipt_no: ExtractedFieldValue
    receipt_date: ExtractedFieldValue
    payer_name: ExtractedFieldValue
    payee_name: ExtractedFieldValue
    amount: ExtractedFieldValue
    currency: ExtractedFieldValue
    receipt_purpose: ExtractedFieldValue
    related_contract_no: ExtractedFieldValue
    bank_serial_no: ExtractedFieldValue


class SalesAccountingVoucherExtraction(BaseModel):
    voucher_no: ExtractedFieldValue
    voucher_date: ExtractedFieldValue
    summary: ExtractedFieldValue
    debit_subject: ExtractedFieldValue
    credit_subject: ExtractedFieldValue
    amount: ExtractedFieldValue
    customer_name: ExtractedFieldValue
    related_invoice_no: ExtractedFieldValue


class ConfirmationExtraction(BaseModel):
    confirmation_no: ExtractedFieldValue
    counterparty_name: ExtractedFieldValue
    counterparty_address: ExtractedFieldValue
    sent_date: ExtractedFieldValue
    replied_date: ExtractedFieldValue
    confirmed_amount: ExtractedFieldValue
    book_amount: ExtractedFieldValue
    difference_amount: ExtractedFieldValue
    seal_detected: ExtractedFieldValue
    signatory: ExtractedFieldValue
    reply_channel: ExtractedFieldValue
    exception_reason: ExtractedFieldValue


class ConfirmationRequestExtraction(BaseModel):
    confirmation_no: ExtractedFieldValue
    counterparty_name: ExtractedFieldValue
    counterparty_address: ExtractedFieldValue
    sent_date: ExtractedFieldValue
    book_amount: ExtractedFieldValue


class ConfirmationReplyExtraction(BaseModel):
    confirmation_no: ExtractedFieldValue
    counterparty_name: ExtractedFieldValue
    replied_date: ExtractedFieldValue
    confirmed_amount: ExtractedFieldValue
    seal_detected: ExtractedFieldValue
    signatory: ExtractedFieldValue
    reply_channel: ExtractedFieldValue


class ConfirmationAdjustmentExtraction(BaseModel):
    confirmation_no: ExtractedFieldValue
    difference_amount: ExtractedFieldValue
    exception_reason: ExtractedFieldValue
    adjustment_items: ExtractedFieldValue


DOCUMENT_EXTRACTION_SCHEMAS = {
    "purchase_request": PurchaseRequestExtraction,
    "purchase_contract": PurchaseContractExtraction,
    "warehouse_receipt": WarehouseReceiptExtraction,
    "invoice": InvoiceExtraction,
    "accounting_voucher": AccountingVoucherExtraction,
    "payment_receipt": PaymentReceiptExtraction,
}

SALES_DOCUMENT_EXTRACTION_SCHEMAS = {
    "sales_contract": SalesContractExtraction,
    "sales_order": SalesOrderExtraction,
    "delivery_order": DeliveryOrderExtraction,
    "logistics_receipt": LogisticsReceiptExtraction,
    "sales_invoice": SalesInvoiceExtraction,
    "receipt_voucher": ReceiptVoucherExtraction,
    "accounting_voucher": SalesAccountingVoucherExtraction,
}

CONFIRMATION_DOCUMENT_EXTRACTION_SCHEMAS = {
    "confirmation": ConfirmationExtraction,
    "confirmation_request": ConfirmationRequestExtraction,
    "confirmation_reply": ConfirmationReplyExtraction,
    "confirmation_adjustment": ConfirmationAdjustmentExtraction,
}


def validate_document_extraction(
    doc_type: DocumentDocType,
    fields: list[ExtractedFieldValue],
    scenario: str = "procurement",
) -> None:
    payload = {field.field_name: field for field in fields}
    schemas = {
        "sales": SALES_DOCUMENT_EXTRACTION_SCHEMAS,
        "confirmation": CONFIRMATION_DOCUMENT_EXTRACTION_SCHEMAS,
    }.get(scenario, DOCUMENT_EXTRACTION_SCHEMAS)
    try:
        schemas[doc_type].model_validate(payload)
    except KeyError as exc:
        raise ValueError(f"Unsupported document type for extraction: {doc_type}") from exc
    except ValidationError:
        raise
