from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.schemas.document import ClassificationRead, DocumentUpdate
from app.services import audit_log_service, llm_provider, model_invocation_service

LOW_CONFIDENCE_THRESHOLD = 0.6
CLASSIFICATION_CONTRACT_VERSION = "llm-provider-v1"
DETERMINISTIC_CONTRACT_VERSION = "deterministic-evidence-v2"
KNOWLEDGE_DOC_TYPES = {
    "prospectus",
    "inquiry_letter",
    "regulation",
}
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
    "sales_contract": (
        "sales contract",
        "contract no",
        "customer",
        "seller",
        "delivery terms",
        "销售合同",
        "客户",
        "销售方",
        "交付条款",
    ),
    "sales_order": (
        "sales order",
        "order no",
        "order date",
        "customer",
        "related contract",
        "销售订单",
        "订单编号",
        "客户",
    ),
    "delivery_order": (
        "delivery order",
        "delivery no",
        "delivery date",
        "warehouse",
        "related order",
        "出库单",
        "出库日期",
        "仓库",
    ),
    "logistics_receipt": (
        "logistics receipt",
        "logistics no",
        "shipment date",
        "signed date",
        "receiver",
        "signer",
        "物流签收",
        "签收日期",
        "收货方",
    ),
    "sales_invoice": (
        "sales invoice",
        "invoice no",
        "invoice date",
        "seller name",
        "buyer name",
        "tax amount",
        "total with tax",
        "销售发票",
        "发票号码",
        "购买方",
        "销售方",
    ),
    "receipt_voucher": (
        "receipt voucher",
        "receipt no",
        "receipt date",
        "payer",
        "payee",
        "receipt purpose",
        "bank serial",
        "收款凭证",
        "收款日期",
        "付款方",
        "收款方",
    ),
    "confirmation": (
        "confirmation",
        "confirmation no",
        "counterparty",
        "book amount",
        "confirmed amount",
        "reply",
        "函证",
        "被函证方",
        "账面金额",
        "回函金额",
    ),
    "confirmation_request": (
        "confirmation request",
        "sent date",
        "counterparty",
        "book amount",
        "发函",
        "发函日期",
        "发函清单",
        "账面金额",
    ),
    "confirmation_reply": (
        "confirmation reply",
        "replied date",
        "confirmed amount",
        "seal",
        "signatory",
        "回函",
        "回函日期",
        "公章",
        "签字",
    ),
    "confirmation_adjustment": (
        "confirmation",
        "confirmation adjustment",
        "confirmation no",
        "difference amount",
        "exception reason",
        "adjustment items",
        "差异调节",
        "差异金额",
        "差异原因",
    ),
    "interview_record": (
        "interview record",
        "interview date",
        "interviewee",
        "key answers",
        "mentioned amounts",
        "访谈记录",
        "访谈日期",
        "被访谈人",
        "关键回答",
    ),
    "interview_outline": (
        "interview outline",
        "planned questions",
        "topics",
        "interviewer",
        "访谈提纲",
        "访谈主题",
        "拟询问问题",
    ),
    "interview_signature_page": (
        "interview signature page",
        "signature detected",
        "signature",
        "signed by",
        "interviewee",
        "签字页",
        "签名",
        "签字",
    ),
    "interview_transcript": (
        "interview transcript",
        "transcript summary",
        "key answers",
        "mentioned counterparties",
        "访谈转写",
        "转写文本",
        "访谈纪要",
    ),
    "contract_review": (
        "contract review",
        "contract no",
        "contract name",
        "payment terms",
        "delivery terms",
        "acceptance terms",
        "special clauses",
        "合同审核",
        "重大合同",
        "合同编号",
        "付款条款",
        "交付条款",
        "验收条款",
        "特殊条款",
    ),
    "material_contract": (
        "material contract",
        "major contract",
        "party a",
        "party b",
        "amount including tax",
        "contract no",
        "重大合同",
        "甲方",
        "乙方",
        "含税金额",
        "合同编号",
    ),
    "supplemental_agreement": (
        "supplemental agreement",
        "price adjustment",
        "related party",
        "contract no",
        "补充协议",
        "价格调整",
        "关联交易",
        "合同编号",
    ),
    "framework_agreement": (
        "framework agreement",
        "auto renewal",
        "exclusivity",
        "payment terms",
        "框架协议",
        "自动续期",
        "排他",
        "付款条款",
    ),
    "contract_attachment": (
        "contract attachment",
        "attachment list",
        "attachment",
        "contract no",
        "合同附件",
        "附件清单",
        "合同编号",
    ),
    "prospectus": (
        "prospectus",
        "offering memorandum",
        "securities offering",
        "issuer",
        "招股说明书",
        "募集说明书",
        "发行人",
    ),
    "inquiry_letter": (
        "inquiry letter",
        "comment letter",
        "regulatory inquiry",
        "feedback",
        "问询函",
        "监管问询",
        "反馈意见",
    ),
    "regulation": (
        "regulation",
        "accounting standard",
        "standard",
        "guideline",
        "法律法规",
        "会计准则",
        "监管规定",
    ),
}
DOC_TYPES_BY_SCENARIO = {
    "procurement": {
        "purchase_request",
        "purchase_contract",
        "warehouse_receipt",
        "invoice",
        "accounting_voucher",
        "payment_receipt",
    }
    | KNOWLEDGE_DOC_TYPES,
    "sales": {
        "sales_contract",
        "sales_order",
        "delivery_order",
        "logistics_receipt",
        "sales_invoice",
        "receipt_voucher",
        "accounting_voucher",
    }
    | KNOWLEDGE_DOC_TYPES,
    "confirmation": {
        "confirmation",
        "confirmation_request",
        "confirmation_reply",
        "confirmation_adjustment",
    }
    | KNOWLEDGE_DOC_TYPES,
    "interview": {
        "interview_record",
        "interview_outline",
        "interview_signature_page",
        "interview_transcript",
    }
    | KNOWLEDGE_DOC_TYPES,
    "contract_review": {
        "contract_review",
        "material_contract",
        "supplemental_agreement",
        "framework_agreement",
        "contract_attachment",
    }
    | KNOWLEDGE_DOC_TYPES,
}


@dataclass(frozen=True)
class ClassificationScore:
    doc_type: str
    confidence: float
    matched_keywords: list[str]
    structural_signals: list[str]


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
    scenario = document.task.scenario if document.task else "procurement"
    scores = _rank_document_types(document.original_filename, text, scenario)
    allowed_doc_types = sorted(DOC_TYPES_BY_SCENARIO.get(scenario, DOC_TYPES_BY_SCENARIO["procurement"]))
    provider = llm_provider.get_llm_provider()
    provider_result = provider.classify_document(document.original_filename, text, scenario, allowed_doc_types)
    model_invocation_service.add_invocation(
        db,
        task_id=document.task_id,
        document_id=document.id,
        provider=provider_result.provider_name,
        model_name=provider_result.provider_name,
        invocation_type="classification",
        output_schema="ClassificationRead",
        status="completed" if provider_result.status == "ok" else "degraded",
        input_text=text,
        error={"message": provider_result.error} if provider_result.error else None,
    )
    provider_meta = llm_provider.provider_info(provider_result)
    llm_classification = _classification_from_llm(provider_result.payload, allowed_doc_types) if provider_result.status == "ok" else None
    if llm_classification is not None:
        result_doc_type, confidence, reason, alternative_types = llm_classification
        reason = f"LLM classification via {provider_result.provider_name}: {reason}"
    elif not text:
        result_doc_type = "unknown"
        confidence = 0.0
        reason = "OCR text is empty; human review is required before classification."
        alternative_types = []
    elif not scores or scores[0].confidence < LOW_CONFIDENCE_THRESHOLD:
        best = scores[0] if scores else None
        result_doc_type = "unknown"
        confidence = best.confidence if best else 0.0
        reason = (
                f"Low confidence classification under {DETERMINISTIC_CONTRACT_VERSION}; "
                f"best guess is {best.doc_type} from signals "
                f"{', '.join(best.matched_keywords + best.structural_signals)}."
            if best
            else f"No {scenario} classification signals were found under {DETERMINISTIC_CONTRACT_VERSION}."
        )
        alternative_types = _deterministic_alternatives(scores, result_doc_type)
    else:
        best = scores[0]
        result_doc_type = best.doc_type
        confidence = best.confidence
        signals = best.matched_keywords + best.structural_signals
        reason = (
            f"Matched {best.doc_type} under {DETERMINISTIC_CONTRACT_VERSION} "
            f"using signals: {', '.join(signals)}."
        )
        alternative_types = _deterministic_alternatives(scores, result_doc_type)
    if llm_classification is None:
        provider_meta["fallback_used"] = "deterministic"
        if provider_result.status == "ok":
            provider_meta["fallback_reason"] = "invalid_llm_classification_output"

    need_human_review = result_doc_type == "unknown" or confidence < LOW_CONFIDENCE_THRESHOLD
    document.doc_type = result_doc_type
    document.doc_type_confidence = confidence
    document.classification_reason = reason
    document.alternative_types = alternative_types
    document.review_status = "need_review" if need_human_review else "pending"
    document.metadata_json = {
        **(document.metadata_json or {}),
        "classification_provider": provider_meta,
    }
    audit_log_service.add_log(
        db,
        actor_name=document.uploaded_by_name,
        task_id=document.task_id,
        action="document_classified",
        target_type="document",
        target_id=document.id,
        after_value={"doc_type": result_doc_type, "confidence": confidence, "need_human_review": need_human_review},
    )
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


def _classification_from_llm(payload: dict | None, allowed_doc_types: list[str]) -> tuple[str, float, str, list[dict]] | None:
    if not isinstance(payload, dict):
        return None
    raw_doc_type = payload.get("doc_type")
    doc_type = str(raw_doc_type) if raw_doc_type is not None else "unknown"
    if doc_type != "unknown" and doc_type not in allowed_doc_types:
        return None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reason = str(payload.get("reason") or "LLM provider returned no reason.")
    alternatives = []
    for item in payload.get("alternative_types") or []:
        if not isinstance(item, dict):
            continue
        alternative_doc_type = str(item.get("doc_type") or "")
        if alternative_doc_type and alternative_doc_type in allowed_doc_types:
            try:
                alternative_confidence = float(item.get("confidence") or 0.0)
            except (TypeError, ValueError):
                alternative_confidence = 0.0
            alternatives.append(
                {
                    "doc_type": alternative_doc_type,
                    "confidence": max(0.0, min(1.0, alternative_confidence)),
                    "reason": str(item.get("reason") or "LLM alternative classification."),
                }
            )
    return doc_type, confidence, reason, alternatives[:3]


def _deterministic_alternatives(scores: list[ClassificationScore], result_doc_type: str) -> list[dict]:
    alternatives = [
        {
            "doc_type": score.doc_type,
            "confidence": score.confidence,
            "reason": (
                f"Matched signals under {DETERMINISTIC_CONTRACT_VERSION}: "
                f"{', '.join(score.matched_keywords + score.structural_signals)}."
            ),
        }
        for score in scores[1:4]
    ]
    if result_doc_type == "unknown" and scores:
        alternatives.insert(
            0,
            {
                "doc_type": scores[0].doc_type,
                "confidence": scores[0].confidence,
                "reason": (
                    f"Best low-confidence guess under {DETERMINISTIC_CONTRACT_VERSION}: "
                    f"{', '.join(scores[0].matched_keywords + scores[0].structural_signals)}."
                ),
            },
        )
    return alternatives


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

    scenario = document.task.scenario if document.task else "procurement"
    if payload.doc_type != "unknown" and payload.doc_type not in DOC_TYPES_BY_SCENARIO.get(scenario, set()):
        raise HTTPException(status_code=400, detail="Document type is not allowed for task scenario")

    before = {"doc_type": document.doc_type, "review_status": document.review_status}
    document.doc_type = payload.doc_type
    document.review_status = "need_review" if payload.doc_type == "unknown" else "pending"
    audit_log_service.add_log(
        db,
        actor_name=payload.actor_name,
        task_id=document.task_id,
        action="document_classification_updated",
        target_type="document",
        target_id=document.id,
        before_value=before,
        after_value={"doc_type": document.doc_type, "review_status": document.review_status},
    )
    db.commit()
    db.refresh(document)
    return document


def _rank_document_types(filename: str, text: str, scenario: str = "procurement") -> list[ClassificationScore]:
    filename_text = _normalize(filename)
    body_text = _normalize(text)
    scores: list[ClassificationScore] = []
    allowed_doc_types = DOC_TYPES_BY_SCENARIO.get(scenario, DOC_TYPES_BY_SCENARIO["procurement"])

    for doc_type, keywords in KEYWORDS.items():
        if doc_type not in allowed_doc_types:
            continue
        matched: list[str] = []
        structural_signals: list[str] = []
        score = 0.0
        for keyword in keywords:
            normalized = _normalize(keyword)
            if normalized in body_text:
                score += 0.12
                matched.append(keyword)
            elif normalized in filename_text:
                score += 0.08
                matched.append(f"filename:{keyword}")
        for signal in _structural_signals(doc_type, body_text):
            score += 0.04
            structural_signals.append(signal)
        if scenario in {"confirmation", "interview", "contract_review"} and doc_type not in {
            "confirmation",
            "interview_record",
            "contract_review",
        }:
            score += 0.03

        if matched or structural_signals:
            confidence = min(0.98, 0.18 + score)
            scores.append(ClassificationScore(doc_type, round(confidence, 4), matched, structural_signals))

    return sorted(scores, key=lambda score: score.confidence, reverse=True)


def _normalize(value: str) -> str:
    return value.casefold().replace("_", " ").replace("-", " ")


def _structural_signals(doc_type: str, body_text: str) -> list[str]:
    try:
        from app.services.extraction_service import (
            SCHEMA_SPECS,
            CONTRACT_REVIEW_SCHEMA_SPECS,
            CONFIRMATION_SCHEMA_SPECS,
            INTERVIEW_SCHEMA_SPECS,
            SALES_SCHEMA_SPECS,
        )
    except ImportError:
        return []

    all_specs = {
        **SCHEMA_SPECS,
        **SALES_SCHEMA_SPECS,
        **CONFIRMATION_SCHEMA_SPECS,
        **INTERVIEW_SCHEMA_SPECS,
        **CONTRACT_REVIEW_SCHEMA_SPECS,
    }
    signals: list[str] = []
    for spec in all_specs.get(doc_type, ()):
        for alias in spec.aliases:
            if f"{_normalize(alias)}:" in body_text or f"{_normalize(alias)}：" in body_text:
                signals.append(f"label:{alias}")
                break
        if len(signals) >= 4:
            break
    return signals
