from __future__ import annotations

import base64
import json
from pathlib import Path
from time import perf_counter
import urllib.error
import urllib.request
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile
from uuid import UUID

import fitz
from fitz import EmptyFileError, FileDataError
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.services import audit_log_service, model_invocation_service


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
        warnings.extend(["confidence_unavailable", "ocr_confidence_not_reported_by_provider"])

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


class HttpOcrProvider:
    name = "http-ocr-provider"

    def parse(self, document: Document, path: Path) -> list[DocumentPage]:
        if not settings.ocr_api_url:
            raise ValueError("OCR_API_URL is required when OCR_PROVIDER is external")
        payload = {
            "model": settings.ocr_model,
            "filename": document.original_filename,
            "file_ext": document.file_ext,
            "content_type": document.content_type,
            "file_base64": base64.b64encode(path.read_bytes()).decode(),
        }
        headers = {"Content-Type": "application/json"}
        if settings.ocr_api_key:
            headers["Authorization"] = f"Bearer {settings.ocr_api_key}"
        request = urllib.request.Request(
            settings.ocr_api_url,
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=settings.ocr_timeout_seconds) as response:
                provider_payload = json.loads(response.read().decode())
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise ValueError(f"OCR provider request failed: {exc}") from exc
        return _pages_from_provider_payload(document, path, provider_payload)


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
    started = perf_counter()
    try:
        pages = _parse_document(document, path)
        latency_ms = int((perf_counter() - started) * 1000)
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
        model_invocation_service.add_invocation(
            db,
            task_id=document.task_id,
            document_id=document.id,
            provider=_ocr_provider_name(pages),
            model_name=_ocr_provider_name(pages),
            invocation_type="ocr",
            prompt_version="ocr-provider-v1",
            output_schema="DocumentPageRead",
            status="success",
            latency_ms=latency_ms,
            input_text=f"{document.original_filename}:{document.file_hash}",
            cost_estimate={"currency": "USD", "amount": None, "basis": "non_llm_ocr_no_token_usage"},
        )
        db.commit()
        db.refresh(document)
        return document
    except Exception as exc:
        latency_ms = int((perf_counter() - started) * 1000)
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
            model_invocation_service.add_invocation(
                db,
                task_id=document.task_id,
                document_id=document.id,
                provider="ocr-provider",
                model_name="ocr-provider",
                invocation_type="ocr",
                prompt_version="ocr-provider-v1",
                output_schema="DocumentPageRead",
                status="failed",
                latency_ms=latency_ms,
                input_text=f"{document.original_filename}:{document.file_hash}",
                cost_estimate={"currency": "USD", "amount": None, "basis": "non_llm_ocr_no_token_usage"},
                error={"message": str(exc)[:1000]},
            )
            db.commit()
            db.refresh(document)
        return document


def _ocr_provider_name(pages: list[DocumentPage]) -> str:
    engines = sorted({page.ocr_engine for page in pages if page.ocr_engine})
    return "+".join(engines)[:80] if engines else "ocr-provider"


def _parse_document(document: Document, path: Path) -> list[DocumentPage]:
    if not path.exists():
        raise FileNotFoundError("Stored document file was not found")
    provider = _configured_ocr_provider()
    if provider is not None:
        return provider.parse(document, path)
    if document.file_ext == "pdf":
        return _parse_pdf(document, path)
    if document.file_ext in {"png", "jpg", "jpeg"}:
        return BasicImageOcrProvider().parse(document, path)
    if document.file_ext == "docx":
        return _parse_docx(document, path)
    if document.file_ext == "xlsx":
        return _parse_xlsx(document, path)
    raise ValueError(f"OCR is not supported for .{document.file_ext}")


def _configured_ocr_provider() -> HttpOcrProvider | None:
    provider = (settings.ocr_provider or "pymupdf-local").strip().lower()
    if provider in {"pymupdf", "pymupdf-local", "local"}:
        return None
    if provider in {"http", "external-http", "real"}:
        return HttpOcrProvider()
    raise ValueError("Configured OCR provider is not enabled")


def _pages_from_provider_payload(document: Document, path: Path, payload: object) -> list[DocumentPage]:
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise ValueError("OCR provider response must contain a pages list")
    image_map = _provider_page_images(document, path)
    pages = []
    for index, item in enumerate(payload["pages"], start=1):
        if not isinstance(item, dict):
            raise ValueError("OCR provider page must be an object")
        page_number = _int_or_none(item.get("page_number")) or index
        raw_text = str(item.get("raw_text") or item.get("text") or "")
        blocks, block_warnings = _provider_blocks(item.get("ocr_blocks") or item.get("blocks") or [], raw_text)
        ocr_confidence = _confidence_or_none(item.get("ocr_confidence", item.get("confidence")))
        block_confidences = [
            block["confidence"]
            for block in blocks
            if isinstance(block.get("confidence"), (int, float))
        ]
        warnings = [str(warning) for warning in item.get("warnings") or [] if isinstance(warning, str)]
        warnings.extend(block_warnings)
        if ocr_confidence is None and block_confidences:
            ocr_confidence = round(sum(block_confidences) / len(block_confidences), 4)
            warnings.append("ocr_confidence_derived_from_blocks")
        elif ocr_confidence is None:
            warnings.extend(["confidence_unavailable", "ocr_confidence_not_reported_by_provider"])
        image_path, image_width, image_height = image_map.get(page_number, (None, None, None))
        pages.append(
            DocumentPage(
                document_id=document.id,
                page_number=page_number,
                raw_text=raw_text,
                ocr_blocks=blocks,
                table_blocks=_provider_table_blocks(item.get("table_blocks") or item.get("tables"), raw_text),
                image_path=str(item.get("image_path") or image_path) if (item.get("image_path") or image_path) else None,
                width=_int_or_none(item.get("width")) or image_width,
                height=_int_or_none(item.get("height")) or image_height,
                ocr_engine=str(item.get("ocr_engine") or item.get("engine") or settings.ocr_provider),
                ocr_confidence=ocr_confidence,
                warnings=sorted(set(warnings)),
            )
        )
    if not pages:
        raise ValueError("OCR provider returned no pages")
    return pages


def _provider_blocks(raw_blocks: object, raw_text: str) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    blocks = []
    if isinstance(raw_blocks, list):
        for item in raw_blocks:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            confidence = _confidence_or_none(item.get("confidence"))
            if confidence is None:
                warnings.append("block_confidence_not_reported_by_provider")
            blocks.append(
                {
                    "text": text,
                    "bbox": _bbox_or_none(item.get("bbox")),
                    "confidence": confidence,
                    "confidence_source": "provider" if confidence is not None else "not_reported_by_provider",
                }
            )
    if not blocks and raw_text:
        warnings.append("provider_blocks_missing")
        blocks.append(
            {
                "text": raw_text,
                "bbox": None,
                "confidence": None,
                "confidence_source": "not_reported_by_provider",
            }
        )
    return blocks, warnings


def _provider_table_blocks(raw_tables: object, raw_text: str) -> list[dict]:
    if isinstance(raw_tables, list):
        return [table for table in raw_tables if isinstance(table, dict)]
    return _table_blocks(raw_text)


def _provider_page_images(document: Document, path: Path) -> dict[int, tuple[str | None, int | None, int | None]]:
    try:
        if document.file_ext == "pdf":
            with fitz.open(path) as pdf:
                return {
                    index: _provider_pdf_image(document, index, page)
                    for index, page in enumerate(pdf, start=1)
                }
        if document.file_ext in {"png", "jpg", "jpeg"}:
            pixmap = fitz.Pixmap(str(path))
            image_path = _save_image_page(document, 1, pixmap)
            return {1: (image_path, pixmap.width, pixmap.height)}
    except (RuntimeError, ValueError, EmptyFileError, FileDataError):
        return {}
    return {}


def _provider_pdf_image(document: Document, page_number: int, page: fitz.Page) -> tuple[str, int, int]:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    return _save_image_page(document, page_number, pixmap), pixmap.width, pixmap.height


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _confidence_or_none(value: object) -> float | None:
    try:
        confidence = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if confidence is None:
        return None
    return max(0.0, min(1.0, confidence))


def _bbox_or_none(value: object) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _parse_docx(document: Document, path: Path) -> list[DocumentPage]:
    try:
        with ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("DOCX text could not be parsed") from exc

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            lines.append(text)
    return [_office_page(document, "\n".join(lines), "docx-xml", [])]


def _parse_xlsx(document: Document, path: Path) -> list[DocumentPage]:
    try:
        with ZipFile(path) as archive:
            shared_strings = _xlsx_shared_strings(archive)
            rows = []
            text_lines = []
            for sheet_name in sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
                root = ElementTree.fromstring(archive.read(sheet_name))
                for row in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                    cells = [
                        value
                        for value in (_xlsx_cell_text(cell, shared_strings) for cell in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"))
                        if value
                    ]
                    if cells:
                        source_text = " | ".join(cells)
                        rows.append({"line_number": len(rows) + 1, "cells": cells, "source_text": source_text})
                        text_lines.append(source_text)
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError("XLSX text could not be parsed") from exc

    table_blocks = [{"type": "xlsx_sheet_rows", "rows": rows, "confidence": None}] if rows else []
    return [_office_page(document, "\n".join(text_lines), "xlsx-xml", table_blocks)]


def _parse_pdf(document: Document, path: Path) -> list[DocumentPage]:
    pages: list[DocumentPage] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            image_path = _render_pdf_page_image(document, index, page)
            text = page.get_text("text").strip()
            warnings = [] if text else ["empty_text"]
            blocks = _text_blocks(page)
            ocr_engine = "pymupdf-text"
            text_from_native_pdf = bool(text)

            if not text:
                try:
                    text_page = page.get_textpage_ocr(language="eng")
                    text = page.get_text("text", textpage=text_page).strip()
                    blocks = _text_blocks(page, text_page)
                    ocr_engine = "pymupdf-ocr"
                    text_from_native_pdf = False
                    warnings = [] if text else ["empty_text"]
                except (RuntimeError, ValueError) as exc:
                    warnings.append(f"ocr_text_unavailable:{exc.__class__.__name__}")

            if text:
                if text_from_native_pdf:
                    warnings.append("digital_text_confidence_not_applicable")
                else:
                    warnings.extend(["confidence_unavailable", "ocr_confidence_not_reported_by_provider"])

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


def _office_page(document: Document, text: str, engine: str, table_blocks: list[dict]) -> DocumentPage:
    image_path, width, height = _render_text_preview_image(document, text)
    warnings = ["digital_text_confidence_not_applicable"]
    if not text:
        warnings.append("empty_text")
    return DocumentPage(
        document_id=document.id,
        page_number=1,
        raw_text=text,
        ocr_blocks=[{"text": text, "bbox": None, "confidence": None, "confidence_source": "digital_text"}] if text else [],
        table_blocks=table_blocks or _table_blocks(text),
        image_path=image_path,
        width=width,
        height=height,
        ocr_engine=engine,
        ocr_confidence=None,
        warnings=warnings,
    )


def _render_text_preview_image(document: Document, text: str) -> tuple[str, int, int]:
    preview = fitz.open()
    page = preview.new_page(width=595, height=842)
    page.insert_textbox(fitz.Rect(36, 36, 559, 806), (text or "(empty document)")[:5000], fontsize=9)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    image_path = _save_image_page(document, 1, pixmap)
    width = pixmap.width
    height = pixmap.height
    preview.close()
    return image_path, width, height


def _xlsx_shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    return [
        "".join(node.text or "" for node in item.findall(f".//{namespace}t"))
        for item in root.findall(f"{namespace}si")
    ]


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    value = cell.findtext(f"{namespace}v")
    if cell.attrib.get("t") == "s" and value is not None:
        index = int(value)
        return shared_strings[index] if 0 <= index < len(shared_strings) else ""
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{namespace}t")).strip()
    return (value or "").strip()


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
