from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from uuid import UUID, uuid4

import fitz
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.rag_chunk import RagChunk
from app.models.rag_document import RagDocument
from app.schemas.rag import KnowledgeBase

ALLOWED_KNOWLEDGE_BASES = {"regulation", "inquiry_case", "prospectus", "workpaper"}
ALLOWED_EXTENSIONS = {"txt", "pdf"}
ALLOWED_CONTENT_TYPES = {
    "txt": {"text/plain", "application/octet-stream"},
    "pdf": {"application/pdf"},
}
MAX_RAG_FILE_SIZE = 10 * 1024 * 1024
EMBEDDING_DIMENSIONS = 32
MIN_SCORE = 0.15


@dataclass(frozen=True)
class ParsedSection:
    text: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class TextChunk:
    text: str
    chunk_index: int
    token_count: int
    section_title: str | None
    article_no: str | None
    page_start: int | None
    page_end: int | None
    metadata: dict


class DeterministicEmbeddingProvider:
    name = "deterministic-local"

    def embed(self, text_value: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for token in _tokens(text_value):
            index = int(sha256(token.encode()).hexdigest()[:8], 16) % EMBEDDING_DIMENSIONS
            vector[index] += 1.0
        length = math.sqrt(sum(value * value for value in vector))
        if not length:
            return vector
        return [value / length for value in vector]


def rag_uploads_root() -> Path:
    return Path(__file__).resolve().parents[3] / "local_storage" / "rag_uploads"


async def create_document(
    db: Session,
    knowledge_base: KnowledgeBase,
    title: str,
    source_type: str,
    source_url: str | None = None,
    issuer_name: str | None = None,
    publish_date: date | None = None,
    effective_date: date | None = None,
    metadata: dict | None = None,
    created_by: str | None = None,
    file: UploadFile | None = None,
    content_text: str | None = None,
) -> RagDocument:
    _validate_knowledge_base(knowledge_base)
    metadata = metadata or {}
    data, extension = await _document_bytes(file, content_text)
    checksum = sha256(data).hexdigest()
    document_id = uuid4()
    storage_path = _save_document_file(document_id, extension, data)
    document = RagDocument(
        id=document_id,
        knowledge_base=knowledge_base,
        title=title,
        source_type=source_type,
        source_url=source_url,
        issuer_name=issuer_name,
        publish_date=publish_date,
        effective_date=effective_date,
        file_path=str(storage_path.relative_to(Path(__file__).resolve().parents[3])),
        checksum=checksum,
        metadata_json=metadata,
        created_by=created_by,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, knowledge_base: KnowledgeBase | None = None) -> list[dict]:
    query = select(RagDocument).order_by(RagDocument.created_at.desc())
    if knowledge_base:
        _validate_knowledge_base(knowledge_base)
        query = query.where(RagDocument.knowledge_base == knowledge_base)
    documents = list(db.scalars(query))
    counts = _chunk_counts(db, [document.id for document in documents])
    return [_document_read(document, counts.get(document.id, 0)) for document in documents]


def index_document(db: Session, document_id: UUID) -> dict:
    document = db.get(RagDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="RAG document not found")
    sections = _parse_document(document)
    chunks = _chunk_sections(document, sections)
    if not chunks:
        raise HTTPException(status_code=400, detail="RAG document has no indexable text")

    provider = _embedding_provider()
    db.query(RagChunk).filter(RagChunk.rag_document_id == document_id).delete()
    for chunk in chunks:
        db.add(
            RagChunk(
                rag_document_id=document.id,
                knowledge_base=document.knowledge_base,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.text,
                embedding=_vector_literal(provider.embed(chunk.text)),
                token_count=chunk.token_count,
                section_title=chunk.section_title,
                article_no=chunk.article_no,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                metadata_json=chunk.metadata,
            )
        )
    db.commit()
    return {
        "document_id": document.id,
        "knowledge_base": document.knowledge_base,
        "chunk_count": len(chunks),
    }


def query(db: Session, query_text: str, knowledge_base: KnowledgeBase, top_k: int, metadata_filter: dict) -> dict:
    _validate_knowledge_base(knowledge_base)
    provider = _embedding_provider()
    embedding = _vector_literal(provider.embed(query_text))
    rows = _search_chunks(db, knowledge_base, embedding, metadata_filter, top_k)
    citations = [
        _citation(row)
        for row in rows
        if row["score"] >= MIN_SCORE and _has_token_overlap(query_text, row["chunk_text"])
    ]
    if not citations:
        return {
            "status": "no_answer",
            "answer": "Evidence insufficient. No citation met the retrieval threshold.",
            "citations": [],
            "limitations": [
                "RAG found no sufficiently relevant citation.",
                "RAG does not replace the deterministic Rule Engine or human review.",
            ],
        }
    return {
        "status": "answer",
        "answer": (
            f"Found {len(citations)} supporting citation(s) in {knowledge_base}. "
            "Use these citations as evidence only; do not treat this as an audit conclusion."
        ),
        "citations": citations,
        "limitations": [
            "Answer is limited to retrieved citations.",
            "RAG does not modify Rule Engine results or make final audit judgments.",
        ],
    }


def get_chunk(db: Session, chunk_id: UUID) -> dict:
    chunk = db.get(RagChunk, chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="RAG chunk not found")
    return _chunk_read(chunk)


def parse_metadata_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="metadata must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    return parsed


def _validate_knowledge_base(knowledge_base: str) -> None:
    if knowledge_base not in ALLOWED_KNOWLEDGE_BASES:
        raise HTTPException(status_code=400, detail="Unsupported knowledge_base")


async def _document_bytes(file: UploadFile | None, content_text: str | None) -> tuple[bytes, str]:
    if content_text and content_text.strip():
        return content_text.encode(), "txt"
    if file is None:
        raise HTTPException(status_code=400, detail="RAG document content is required")

    filename = Path(file.filename or "").name
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported RAG document extension")
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES[extension]:
        raise HTTPException(status_code=400, detail="Unsupported RAG document content type")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="RAG document is empty")
    if len(data) > MAX_RAG_FILE_SIZE:
        raise HTTPException(status_code=413, detail="RAG document is too large")
    return data, extension


def _save_document_file(document_id: UUID, extension: str, data: bytes) -> Path:
    directory = rag_uploads_root()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{document_id}.{extension}"
    path.write_bytes(data)
    return path


def _parse_document(document: RagDocument) -> list[ParsedSection]:
    if not document.file_path:
        raise HTTPException(status_code=400, detail="RAG document file is missing")
    path = Path(__file__).resolve().parents[3] / document.file_path
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored RAG document file was not found")
    if path.suffix.lower() == ".pdf":
        return _parse_pdf(path)
    return [ParsedSection(path.read_text(errors="ignore"))]


def _parse_pdf(path: Path) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            text_value = page.get_text("text").strip()
            if text_value:
                sections.append(ParsedSection(text=text_value, page_start=index, page_end=index))
    return sections


def _chunk_sections(document: RagDocument, sections: list[ParsedSection]) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for section in sections:
        for text_value in _split_text(section.text):
            clean_text = text_value.strip()
            if not clean_text:
                continue
            metadata = {
                **document.metadata_json,
                "knowledge_base": document.knowledge_base,
                "title": document.title,
                "source_type": document.source_type,
            }
            chunks.append(
                TextChunk(
                    text=clean_text,
                    chunk_index=len(chunks),
                    token_count=len(_tokens(clean_text)),
                    section_title=_section_title(clean_text),
                    article_no=_article_no(clean_text),
                    page_start=section.page_start,
                    page_end=section.page_end,
                    metadata=metadata,
                )
            )
    return chunks


def _split_text(text_value: str, max_chars: int = 1200) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text_value) if part.strip()]
    if not paragraphs:
        paragraphs = [text_value.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            chunks.extend(paragraph[index : index + max_chars] for index in range(0, len(paragraph), max_chars))
        else:
            chunks.append(paragraph)
    return chunks


def _search_chunks(db: Session, knowledge_base: str, embedding: str, metadata_filter: dict, top_k: int) -> list[dict]:
    sql = """
        SELECT
            c.id AS chunk_id,
            c.rag_document_id AS document_id,
            c.knowledge_base,
            c.chunk_text,
            c.section_title,
            c.page_start,
            c.metadata,
            d.title,
            1 - (c.embedding <=> CAST(:embedding AS vector)) AS score
        FROM rag_chunks c
        JOIN rag_documents d ON d.id = c.rag_document_id
        WHERE c.knowledge_base = :knowledge_base
    """
    params: dict[str, object] = {
        "embedding": embedding,
        "knowledge_base": knowledge_base,
        "limit": top_k,
    }
    if metadata_filter:
        sql += " AND c.metadata @> CAST(:metadata_filter AS jsonb)"
        params["metadata_filter"] = json.dumps(metadata_filter)
    sql += " ORDER BY c.embedding <=> CAST(:embedding AS vector) LIMIT :limit"
    return [dict(row._mapping) for row in db.execute(text(sql), params)]


def _citation(row: dict) -> dict:
    return {
        "chunk_id": row["chunk_id"],
        "document_id": row["document_id"],
        "knowledge_base": row["knowledge_base"],
        "title": row["title"],
        "section": row["section_title"],
        "page": row["page_start"],
        "score": round(float(row["score"]), 4),
        "quote": _quote(row["chunk_text"]),
        "metadata": row["metadata"] or {},
    }


def _quote(text_value: str, limit: int = 240) -> str:
    clean = " ".join(text_value.split())
    return clean if len(clean) <= limit else f"{clean[: limit - 3]}..."


def _document_read(document: RagDocument, chunk_count: int) -> dict:
    return {
        "id": document.id,
        "knowledge_base": document.knowledge_base,
        "title": document.title,
        "source_type": document.source_type,
        "source_url": document.source_url,
        "issuer_name": document.issuer_name,
        "publish_date": document.publish_date,
        "effective_date": document.effective_date,
        "file_path": document.file_path,
        "checksum": document.checksum,
        "metadata": document.metadata_json,
        "created_by": document.created_by,
        "chunk_count": chunk_count,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _chunk_read(chunk: RagChunk) -> dict:
    return {
        "id": chunk.id,
        "rag_document_id": chunk.rag_document_id,
        "knowledge_base": chunk.knowledge_base,
        "title": chunk.document.title,
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "token_count": chunk.token_count,
        "section_title": chunk.section_title,
        "article_no": chunk.article_no,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "metadata": chunk.metadata_json,
        "created_at": chunk.created_at,
        "updated_at": chunk.updated_at,
    }


def _chunk_counts(db: Session, document_ids: list[UUID]) -> dict[UUID, int]:
    if not document_ids:
        return {}
    rows = db.execute(
        select(RagChunk.rag_document_id, func.count(RagChunk.id))
        .where(RagChunk.rag_document_id.in_(document_ids))
        .group_by(RagChunk.rag_document_id)
    )
    return {document_id: count for document_id, count in rows}


def _embedding_provider() -> DeterministicEmbeddingProvider:
    if settings.embedding_provider not in {"deterministic-local", "local", "mock"}:
        raise HTTPException(status_code=400, detail="Only deterministic local embeddings are configured")
    if settings.embedding_dimensions != EMBEDDING_DIMENSIONS:
        raise HTTPException(status_code=400, detail="Embedding dimensions must be 32 for Phase 11")
    return DeterministicEmbeddingProvider()


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"


def _tokens(text_value: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9_]+", text_value)]


def _has_token_overlap(query_text: str, chunk_text: str) -> bool:
    return bool(set(_tokens(query_text)) & set(_tokens(chunk_text)))


def _section_title(text_value: str) -> str | None:
    first_line = text_value.splitlines()[0].strip()
    return first_line[:255] if first_line else None


def _article_no(text_value: str) -> str | None:
    match = re.search(r"(Article|Section|第)\s*([0-9一二三四五六七八九十]+)", text_value, re.IGNORECASE)
    return match.group(0)[:80] if match else None
