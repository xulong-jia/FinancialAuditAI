from pathlib import Path
from uuid import UUID

import fitz
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page import DocumentPage


class BasicImageOcrProvider:
    name = "basic-image-provider"

    def parse(self, document: Document, path: Path) -> list[DocumentPage]:
        raise NotImplementedError("Image OCR provider is not configured for MVP")


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def list_pages(db: Session, document_id: UUID) -> list[DocumentPage]:
    return list(
        db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number.asc())
        )
    )


def run_ocr(db: Session, document_id: UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    document.ocr_status = "running"
    document.ocr_error = None
    db.commit()

    path = project_root() / document.storage_path
    try:
        pages = _parse_document(document, path)
        db.query(DocumentPage).filter(DocumentPage.document_id == document_id).delete()
        for page in pages:
            db.add(page)
        document.page_count = len(pages)
        document.ocr_status = "completed"
        document.ocr_error = None
        db.commit()
        db.refresh(document)
        return document
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.ocr_status = "failed"
            document.ocr_error = str(exc)
            db.commit()
            db.refresh(document)
        return document


def _parse_document(document: Document, path: Path) -> list[DocumentPage]:
    if not path.exists():
        raise FileNotFoundError("Stored document file was not found")
    if document.file_ext == "pdf":
        return _parse_pdf(document, path)
    if document.file_ext in {"png", "jpg", "jpeg"}:
        return BasicImageOcrProvider().parse(document, path)
    raise NotImplementedError(f"OCR is not supported for .{document.file_ext} in Phase 2")


def _parse_pdf(document: Document, path: Path) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            warnings = [] if text else ["empty_text"]
            blocks = [
                {
                    "text": str(block[4]).strip(),
                    "bbox": [float(block[0]), float(block[1]), float(block[2]), float(block[3])],
                    "confidence": None,
                }
                for block in page.get_text("blocks")
                if len(block) >= 5 and str(block[4]).strip()
            ]
            rect = page.rect
            pages.append(
                DocumentPage(
                    document_id=document.id,
                    page_number=index,
                    raw_text=text,
                    ocr_blocks=blocks
                    or [{"text": text, "bbox": None, "confidence": None}]
                    if text
                    else [],
                    table_blocks=[],
                    width=int(rect.width),
                    height=int(rect.height),
                    ocr_engine="pymupdf",
                    ocr_confidence=None,
                    warnings=warnings,
                )
            )
    return pages
