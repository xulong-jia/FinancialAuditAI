from __future__ import annotations

from pathlib import Path
from uuid import UUID

import fitz
from fitz import EmptyFileError, FileDataError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.services import audit_log_service


class BasicImageOcrProvider:
    name = "pymupdf-image-ocr"

    def parse(self, document: Document, path: Path) -> list[DocumentPage]:
        pixmap = fitz.Pixmap(str(path))
        image_path = _save_image_page(document, 1, pixmap)
        warnings: list[str] = []
        text = ""
        blocks: list[dict] = []
        width = pixmap.width
        height = pixmap.height

        try:
            ocr_pdf = pixmap.pdfocr_tobytes(language="eng")
            with fitz.open(stream=ocr_pdf, filetype="pdf") as pdf:
                page = pdf[0]
                text = page.get_text("text").strip()
                blocks = _text_blocks(page)
        except (RuntimeError, ValueError, EmptyFileError, FileDataError) as exc:
            warnings.append(f"image_ocr_unavailable:{exc.__class__.__name__}")

        if not text:
            warnings.append("empty_text")
        warnings.append("confidence_unavailable")

        return [
            DocumentPage(
                document_id=document.id,
                page_number=1,
                raw_text=text,
                ocr_blocks=blocks,
                table_blocks=_table_blocks(text),
                image_path=image_path,
                width=width,
                height=height,
                ocr_engine=self.name,
                ocr_confidence=None,
                warnings=warnings,
            )
        ]


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def page_images_root() -> Path:
    return project_root() / "local_storage" / "page_images"


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
        audit_log_service.add_log(
            db,
            actor_name=document.uploaded_by_name,
            task_id=document.task_id,
            action="ocr_completed",
            target_type="document",
            target_id=document.id,
            after_value={"page_count": len(pages), "ocr_status": document.ocr_status},
        )
        db.commit()
        db.refresh(document)
        return document
    except Exception as exc:
        db.rollback()
        document = db.get(Document, document_id)
        if document is not None:
            document.ocr_status = "failed"
            document.ocr_error = str(exc)
            audit_log_service.add_log(
                db,
                actor_name=document.uploaded_by_name,
                task_id=document.task_id,
                action="ocr_failed",
                target_type="document",
                target_id=document.id,
                after_value={"ocr_status": document.ocr_status, "error": str(exc)[:500]},
            )
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
            image_path = _render_pdf_page_image(document, index, page)
            text = page.get_text("text").strip()
            warnings = [] if text else ["empty_text"]
            blocks = _text_blocks(page)
            ocr_engine = "pymupdf"

            if not text:
                try:
                    text_page = page.get_textpage_ocr(language="eng")
                    text = page.get_text("text", textpage=text_page).strip()
                    blocks = _text_blocks(page, text_page)
                    ocr_engine = "pymupdf-ocr"
                    warnings = [] if text else ["empty_text"]
                except (RuntimeError, ValueError) as exc:
                    warnings.append(f"ocr_text_unavailable:{exc.__class__.__name__}")

            if text:
                warnings.append("confidence_unavailable")

            rect = page.rect
            pages.append(
                DocumentPage(
                    document_id=document.id,
                    page_number=index,
                    raw_text=text,
                    ocr_blocks=blocks
                    or [{"text": text, "bbox": None, "confidence": None, "confidence_source": "not_available"}]
                    if text
                    else [],
                    table_blocks=_table_blocks(text),
                    image_path=image_path,
                    width=int(rect.width),
                    height=int(rect.height),
                    ocr_engine=ocr_engine,
                    ocr_confidence=None,
                    warnings=warnings,
                )
            )
    return pages


def _page_image_relative_path(document: Document, page_number: int) -> Path:
    return Path("local_storage") / "page_images" / str(document.id) / f"page_{page_number}.png"


def _save_image_page(document: Document, page_number: int, pixmap: fitz.Pixmap) -> str:
    relative_path = _page_image_relative_path(document, page_number)
    output_path = project_root() / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if pixmap.alpha:
        pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
    pixmap.save(output_path)
    return str(relative_path)


def _render_pdf_page_image(document: Document, page_number: int, page: fitz.Page) -> str:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    return _save_image_page(document, page_number, pixmap)


def _text_blocks(page: fitz.Page, text_page: fitz.TextPage | None = None) -> list[dict]:
    raw_blocks = page.get_text("blocks", textpage=text_page) if text_page else page.get_text("blocks")
    return [
        {
            "text": str(block[4]).strip(),
            "bbox": [float(block[0]), float(block[1]), float(block[2]), float(block[3])],
            "confidence": None,
            "confidence_source": "not_available",
        }
        for block in raw_blocks
        if len(block) >= 5 and str(block[4]).strip()
    ]


def _table_blocks(text: str) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if "|" in stripped:
            cells = [cell.strip() for cell in stripped.split("|") if cell.strip()]
        elif "\t" in stripped:
            cells = [cell.strip() for cell in stripped.split("\t") if cell.strip()]
        elif len([part for part in stripped.split("  ") if part.strip()]) >= 2:
            cells = [part.strip() for part in stripped.split("  ") if part.strip()]
        else:
            continue
        rows.append({"line_number": line_number, "cells": cells, "source_text": stripped})
    return [{"type": "detected_text_table", "rows": rows, "confidence": 0.4}] if rows else []
