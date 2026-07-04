from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


ProcurementDocType = Literal[
    "purchase_request",
    "purchase_contract",
    "warehouse_receipt",
    "invoice",
    "accounting_voucher",
    "payment_receipt",
]


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    uploaded_by_name: str | None
    original_filename: str
    file_ext: str
    content_type: str | None
    file_size: int
    file_hash: str
    storage_path: str
    doc_type: str | None
    page_count: int | None
    upload_status: str
    ocr_status: str
    ocr_error: str | None
    extraction_status: str
    review_status: str
    created_at: datetime
    updated_at: datetime


class PageBlock(BaseModel):
    text: str
    bbox: list[float] | None = None
    confidence: float | None = None


class DocumentPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    page_number: int
    raw_text: str
    ocr_blocks: list[PageBlock]
    table_blocks: list[dict]
    width: int | None
    height: int | None
    ocr_engine: str
    ocr_confidence: float | None
    warnings: list[str]
    created_at: datetime
    updated_at: datetime
