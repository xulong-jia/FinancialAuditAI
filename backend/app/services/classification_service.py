from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.schemas.document import ClassificationRead, DocumentUpdate

LOW_CONFIDENCE_THRESHOLD = 0.6
KEYWORDS: dict[str, tuple[str, ...]] = {
    "purchase_request": (
        "purchase request",
        "request no",
        "request department",
        "applicant",
        "approval",
        "采购申请",
        "请购",
        "申请单",
        "申请部门",
        "申请人",
        "审批",
    ),
    "purchase_contract": (
        "purchase contract",
        "contract no",
        "supplier",
        "payment terms",
        "party a",
        "party b",
        "采购合同",
        "合同编号",
        "甲方",
        "乙方",
        "供应商",
        "付款条款",
    ),
    "warehouse_receipt": (
        "warehouse receipt",
        "receipt date",
        "warehouse",
        "received quantity",
        "received by",
        "入库单",
        "入库日期",
        "仓库",
        "收货",
        "实收数量",
        "入库数量",
    ),
    "invoice": (
        "invoice",
        "invoice number",
        "total with tax",
        "tax amount",
        "issue date",
        "buyer",
        "seller",
        "发票",
        "发票号码",
        "价税合计",
        "税额",
        "开票日期",
        "购买方",
        "销售方",
    ),
    "accounting_voucher": (
        "accounting voucher",
        "voucher no",
        "debit",
        "credit",
        "account title",
        "summary",
        "记账凭证",
        "凭证号",
        "借方",
        "贷方",
        "摘要",
        "会计科目",
    ),
    "payment_receipt": (
        "payment receipt",
        "bank receipt",
        "payer",
        "payee",
        "transaction no",
        "payment",
        "付款回单",
        "银行回单",
        "付款方",
        "收款方",
        "流水号",
        "支付",
    ),
}


@dataclass(frozen=True)
class ClassificationScore:
    doc_type: str
    confidence: float
    matched_keywords: list[str]


def classify_document(db: Session, document_id: UUID) -> ClassificationRead:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.ocr_status != "completed":
        raise HTTPException(status_code=400, detail="Document OCR must complete before classification")

    pages = list(
        db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number.asc())
        )
    )
    if not pages:
        raise HTTPException(status_code=400, detail="Document pages are required before classification")

    text = "\n".join(page.raw_text for page in pages).strip()
    scores = _rank_document_types(document.original_filename, text)
    if not text:
        result_doc_type = "unknown"
        confidence = 0.0
        reason = "OCR text is empty; human review is required before classification."
    elif not scores or scores[0].confidence < LOW_CONFIDENCE_THRESHOLD:
        best = scores[0] if scores else None
        result_doc_type = "unknown"
        confidence = best.confidence if best else 0.0
        reason = (
            f"Low confidence classification; best guess is {best.doc_type} "
            f"from keywords {', '.join(best.matched_keywords)}."
            if best
            else "No procurement classification keywords were found."
        )
    else:
        best = scores[0]
        result_doc_type = best.doc_type
        confidence = best.confidence
        reason = f"Matched {best.doc_type} using keywords: {', '.join(best.matched_keywords)}."

    alternative_types = [
        {
            "doc_type": score.doc_type,
            "confidence": score.confidence,
            "reason": f"Matched keywords: {', '.join(score.matched_keywords)}.",
        }
        for score in scores[1:4]
    ]
    if result_doc_type == "unknown" and scores:
        alternative_types.insert(
            0,
            {
                "doc_type": scores[0].doc_type,
                "confidence": scores[0].confidence,
                "reason": f"Best low-confidence guess from keywords: {', '.join(scores[0].matched_keywords)}.",
            },
        )

    need_human_review = result_doc_type == "unknown" or confidence < LOW_CONFIDENCE_THRESHOLD
    document.doc_type = result_doc_type
    document.doc_type_confidence = confidence
    document.classification_reason = reason
    document.alternative_types = alternative_types
    document.review_status = "need_review" if need_human_review else "pending"
    db.commit()
    db.refresh(document)

    return ClassificationRead(
        document_id=document.id,
        doc_type=result_doc_type,
        confidence=confidence,
        classification_reason=reason,
        alternative_types=alternative_types,
        need_human_review=need_human_review,
    )


def update_document_classification(
    db: Session, document_id: UUID, payload: DocumentUpdate
) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.original_classification is None:
        document.original_classification = {
            "doc_type": document.doc_type,
            "confidence": document.doc_type_confidence,
            "classification_reason": document.classification_reason,
            "alternative_types": document.alternative_types or [],
        }

    document.doc_type = payload.doc_type
    document.review_status = "need_review" if payload.doc_type == "unknown" else "pending"
    db.commit()
    db.refresh(document)
    return document


def _rank_document_types(filename: str, text: str) -> list[ClassificationScore]:
    filename_text = _normalize(filename)
    body_text = _normalize(text)
    scores: list[ClassificationScore] = []

    for doc_type, keywords in KEYWORDS.items():
        matched: list[str] = []
        score = 0.0
        for keyword in keywords:
            normalized = _normalize(keyword)
            if normalized in body_text:
                score += 0.12
                matched.append(keyword)
            elif normalized in filename_text:
                score += 0.08
                matched.append(f"filename:{keyword}")

        if matched:
            confidence = min(0.98, 0.18 + score)
            scores.append(ClassificationScore(doc_type, round(confidence, 4), matched))

    return sorted(scores, key=lambda score: score.confidence, reverse=True)


def _normalize(value: str) -> str:
    return value.casefold().replace("_", " ").replace("-", " ")
