from collections import defaultdict
from dataclasses import dataclass, field
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_relation import DocumentRelation
from app.models.extracted_field import ExtractedField
from app.schemas.linkage import LinkDocumentsResult

LOW_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class LinkGroup:
    business_key: str
    confidence: float
    relation_type: str
    method: str
    document_ids: set[UUID] = field(default_factory=set)
    evidence: list[dict] = field(default_factory=list)


def link_documents(db: Session, task_id: UUID) -> LinkDocumentsResult:
    documents = _list_documents(db, task_id)
    fields = _field_map(_list_fields(db, task_id))
    warnings: list[str] = []

    db.query(DocumentRelation).filter(DocumentRelation.task_id == task_id).delete()
    for document in documents:
        document.business_key = None

    if not documents:
        warnings.append("no_documents")
        db.commit()
        return _result(db, task_id, warnings)
    if not fields:
        warnings.append("no_extracted_fields")
        db.commit()
        return _result(db, task_id, warnings)

    groups = _explicit_groups(documents, fields)
    _add_sales_customer_bridges(documents, fields, groups)
    groups = _prefer_contract_groups(groups)
    groups.extend(_fallback_groups(task_id, documents, fields, existing_groups=groups))
    groups = [group for group in groups if len(group.document_ids) >= 2]

    if not groups:
        warnings.append("no_linkable_fields")
        db.commit()
        return _result(db, task_id, warnings)

    for group in groups:
        _apply_group(db, documents, group)
        if group.confidence < LOW_CONFIDENCE_THRESHOLD:
            warnings.append(f"low_confidence:{group.business_key}")

    db.commit()
    return _result(db, task_id, warnings)


def list_document_relations(db: Session, task_id: UUID) -> list[DocumentRelation]:
    return list(
        db.scalars(
            select(DocumentRelation)
            .where(DocumentRelation.task_id == task_id)
            .order_by(DocumentRelation.business_key.asc(), DocumentRelation.created_at.asc())
        )
    )


def _list_documents(db: Session, task_id: UUID) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.task_id == task_id)
            .order_by(Document.created_at.asc())
        )
    )


def _list_fields(db: Session, task_id: UUID) -> list[ExtractedField]:
    return list(db.scalars(select(ExtractedField).where(ExtractedField.task_id == task_id)))


def _field_map(fields: list[ExtractedField]) -> dict[UUID, dict[str, ExtractedField]]:
    mapped: dict[UUID, dict[str, ExtractedField]] = defaultdict(dict)
    for field in fields:
        mapped[field.document_id][field.field_name] = field
    return mapped


def _explicit_groups(
    documents: list[Document], fields: dict[UUID, dict[str, ExtractedField]]
) -> list[LinkGroup]:
    by_key: dict[str, LinkGroup] = {}
    contract_values: set[str] = set()
    invoice_values: set[str] = set()
    order_to_contract: dict[str, str] = {}
    delivery_to_contract: dict[str, str] = {}

    for document in documents:
        doc_fields = fields.get(document.id, {})
        contract_no = _field_value(doc_fields.get("contract_no"))
        related_contract_no = _field_value(doc_fields.get("related_contract_no"))
        invoice_no = _field_value(doc_fields.get("invoice_no"))
        related_invoice_no = _field_value(doc_fields.get("related_invoice_no"))
        order_no = _field_value(doc_fields.get("order_no"))
        related_order_no = _field_value(doc_fields.get("related_order_no"))
        delivery_no = _field_value(doc_fields.get("delivery_no"))
        confirmation_no = _field_value(doc_fields.get("confirmation_no"))

        if confirmation_no:
            _add_to_group(
                by_key,
                f"CONFIRMATION-{_token(confirmation_no)}",
                document,
                0.95,
                "same_confirmation",
                "explicit_confirmation_no",
                doc_fields["confirmation_no"],
            )
        if contract_no:
            contract_values.add(contract_no)
            _add_to_group(
                by_key,
                f"CONTRACT-{_token(contract_no)}",
                document,
                0.95,
                "same_contract",
                "explicit_contract_no",
                doc_fields["contract_no"],
            )
        if related_contract_no:
            contract_values.add(related_contract_no)
            if order_no:
                order_to_contract[order_no] = related_contract_no
            if delivery_no:
                delivery_to_contract[delivery_no] = related_contract_no
            _add_to_group(
                by_key,
                f"CONTRACT-{_token(related_contract_no)}",
                document,
                0.9,
                "same_contract",
                "explicit_related_contract_no",
                doc_fields["related_contract_no"],
            )
        if invoice_no:
            invoice_values.add(invoice_no)
            _add_to_group(
                by_key,
                f"INVOICE-{_token(invoice_no)}",
                document,
                0.9,
                "same_invoice",
                "explicit_invoice_no",
                doc_fields["invoice_no"],
            )
        if related_invoice_no:
            invoice_values.add(related_invoice_no)
            _add_to_group(
                by_key,
                f"INVOICE-{_token(related_invoice_no)}",
                document,
                0.88,
                "same_invoice",
                "explicit_related_invoice_no",
                doc_fields["related_invoice_no"],
            )
        if related_order_no and related_order_no in order_to_contract:
            contract_no_for_order = order_to_contract[related_order_no]
            _add_to_group(
                by_key,
                f"CONTRACT-{_token(contract_no_for_order)}",
                document,
                0.84,
                "same_contract",
                "explicit_related_order_no",
                doc_fields["related_order_no"],
            )

    for document in documents:
        doc_fields = fields.get(document.id, {})
        related_delivery_no = _field_value(doc_fields.get("related_delivery_no"))
        if related_delivery_no and related_delivery_no in delivery_to_contract:
            contract_no_for_delivery = delivery_to_contract[related_delivery_no]
            _add_to_group(
                by_key,
                f"CONTRACT-{_token(contract_no_for_delivery)}",
                document,
                0.82,
                "same_contract",
                "explicit_related_delivery_no",
                doc_fields["related_delivery_no"],
            )
        for field_name in ("payment_purpose", "receipt_purpose", "summary"):
            field = doc_fields.get(field_name)
            value = _field_value(field)
            if not field or not value:
                continue
            for contract_no in contract_values:
                if _contains_token(value, contract_no):
                    _add_to_group(
                        by_key,
                        f"CONTRACT-{_token(contract_no)}",
                        document,
                        0.82,
                        "same_contract",
                        f"{field_name}_mentions_contract",
                        field,
                    )
            for invoice_no in invoice_values:
                if _contains_token(value, invoice_no):
                    _add_to_group(
                        by_key,
                        f"INVOICE-{_token(invoice_no)}",
                        document,
                        0.8,
                        "same_invoice",
                        f"{field_name}_mentions_invoice",
                        field,
                    )

    return list(by_key.values())


def _add_sales_customer_bridges(
    documents: list[Document],
    fields: dict[UUID, dict[str, ExtractedField]],
    groups: list[LinkGroup],
) -> None:
    contract_groups = [group for group in groups if group.business_key.startswith("CONTRACT-")]
    if not contract_groups:
        return
    docs_by_id = {document.id: document for document in documents}
    for group in contract_groups:
        group_customers = {
            _normalize_name(value)
            for document_id in group.document_ids
            for value in [_customer_value(fields.get(document_id, {}))]
            if value
        }
        if not group_customers:
            continue
        for document in documents:
            if document.id in group.document_ids or not (document.doc_type or "").startswith(("sales_", "receipt_")) and document.doc_type != "accounting_voucher":
                continue
            customer_field = _customer_field(fields.get(document.id, {}))
            customer_value = _field_value(customer_field)
            if customer_field is None or not customer_value or _normalize_name(customer_value) not in group_customers:
                continue
            group.confidence = min(group.confidence, 0.55)
            group.document_ids.add(document.id)
            group.evidence.append(
                _field_evidence(docs_by_id[document.id], customer_field, "sales_customer_low_confidence", customer_value)
            )


def _prefer_contract_groups(groups: list[LinkGroup]) -> list[LinkGroup]:
    contract_document_ids = {
        document_id
        for group in groups
        if group.business_key.startswith("CONTRACT-")
        for document_id in group.document_ids
    }
    for group in groups:
        if not group.business_key.startswith("CONTRACT-"):
            group.document_ids -= contract_document_ids
    return [group for group in groups if len(group.document_ids) >= 2]


def _fallback_groups(
    task_id: UUID,
    documents: list[Document],
    fields: dict[UUID, dict[str, ExtractedField]],
    existing_groups: list[LinkGroup],
) -> list[LinkGroup]:
    grouped_doc_ids = {document_id for group in existing_groups for document_id in group.document_ids}
    buckets: dict[
        tuple[str, float, str],
        list[tuple[Document, ExtractedField, ExtractedField, ExtractedField | None]],
    ] = defaultdict(list)

    for document in documents:
        if document.id in grouped_doc_ids:
            continue
        doc_fields = fields.get(document.id, {})
        supplier = _first_field(
            doc_fields,
            (
                "supplier_name",
                "seller_name",
                "payee_name",
                "customer_name",
                "buyer_name",
                "payer_name",
                "counterparty_name",
            ),
        )
        amount = _first_field(
            doc_fields,
            (
                "amount_including_tax",
                "amount",
                "total_estimated_amount",
                "amount_excluding_tax",
                "book_amount",
                "confirmed_amount",
                "difference_amount",
            ),
        )
        document_date = _first_field(
            doc_fields,
            (
                "signing_date",
                "invoice_date",
                "payment_date",
                "receipt_date",
                "voucher_date",
                "request_date",
                "order_date",
                "delivery_date",
                "signed_date",
                "sent_date",
                "replied_date",
            ),
        )
        supplier_value = _field_value(supplier)
        amount_value = _amount_value(amount)
        if supplier and supplier_value and amount and amount_value is not None:
            date_value = _field_value(document_date) or ""
            buckets[(_normalize_name(supplier_value), amount_value, date_value)].append(
                (document, supplier, amount, document_date)
            )

    groups: list[LinkGroup] = []
    group_number = 1
    for (supplier, amount, date_value), matches in buckets.items():
        if len(matches) < 2:
            continue
        group = LinkGroup(
            business_key=f"TASK-{task_id}-GROUP-{group_number}",
            confidence=0.45,
            relation_type="possible_same_purchase",
            method="supplier_amount_low_confidence",
        )
        group_number += 1
        for document, supplier_field, amount_field, date_field in matches:
            group.document_ids.add(document.id)
            group.evidence.extend(
                [
                    _field_evidence(document, supplier_field, "fallback_supplier", supplier),
                    _field_evidence(document, amount_field, "fallback_amount", amount),
                ]
            )
            if date_field is not None:
                group.evidence.append(
                    _field_evidence(document, date_field, "fallback_date", date_value)
                )
        groups.append(group)
    return groups


def _apply_group(db: Session, documents: list[Document], group: LinkGroup) -> None:
    docs_by_id = {document.id: document for document in documents}
    group_docs = [docs_by_id[document_id] for document_id in group.document_ids]
    anchor = _anchor_document(group_docs)
    for document in group_docs:
        document.business_key = group.business_key
        if group.confidence < LOW_CONFIDENCE_THRESHOLD:
            document.review_status = "need_review"
    for document in group_docs:
        if document.id == anchor.id:
            continue
        db.add(
            DocumentRelation(
                task_id=anchor.task_id,
                business_key=group.business_key,
                source_document_id=anchor.id,
                target_document_id=document.id,
                relation_type=group.relation_type,
                confidence=group.confidence,
                evidence={
                    "method": group.method,
                    "business_key": group.business_key,
                    "matched_fields": group.evidence,
                    "need_review": group.confidence < LOW_CONFIDENCE_THRESHOLD,
                },
            )
        )


def _anchor_document(documents: list[Document]) -> Document:
    priority = {
        "purchase_contract": 0,
        "invoice": 1,
        "payment_receipt": 2,
        "accounting_voucher": 3,
        "warehouse_receipt": 4,
        "purchase_request": 5,
        "sales_contract": 0,
        "sales_order": 1,
        "delivery_order": 2,
        "logistics_receipt": 3,
        "sales_invoice": 4,
        "receipt_voucher": 5,
        "confirmation": 0,
        "confirmation_request": 1,
        "confirmation_reply": 2,
        "confirmation_adjustment": 3,
    }
    return sorted(documents, key=lambda document: priority.get(document.doc_type or "", 99))[0]


def _add_to_group(
    groups: dict[str, LinkGroup],
    business_key: str,
    document: Document,
    confidence: float,
    relation_type: str,
    method: str,
    field: ExtractedField,
) -> None:
    group = groups.setdefault(
        business_key,
        LinkGroup(
            business_key=business_key,
            confidence=confidence,
            relation_type=relation_type,
            method=method,
        ),
    )
    group.confidence = min(group.confidence, confidence)
    group.document_ids.add(document.id)
    group.evidence.append(_field_evidence(document, field, method, _field_value(field)))


def _result(db: Session, task_id: UUID, warnings: list[str]) -> LinkDocumentsResult:
    relations = list_document_relations(db, task_id)
    linked_document_ids = {
        relation.source_document_id for relation in relations
    } | {relation.target_document_id for relation in relations}
    return LinkDocumentsResult(
        task_id=task_id,
        linked_document_count=len(linked_document_ids),
        relation_count=len(relations),
        warnings=warnings,
        relations=relations,
    )


def _field_value(field: ExtractedField | None) -> str | None:
    if field is None or not field.value_text:
        return None
    return field.value_text.strip()


def _first_field(
    fields: dict[str, ExtractedField], names: tuple[str, ...]
) -> ExtractedField | None:
    for name in names:
        field = fields.get(name)
        if _field_value(field):
            return field
    return None


def _customer_field(fields: dict[str, ExtractedField]) -> ExtractedField | None:
    return _first_field(fields, ("customer_name", "buyer_name", "payer_name", "receiver_name"))


def _customer_value(fields: dict[str, ExtractedField]) -> str | None:
    return _field_value(_customer_field(fields))


def _amount_value(field: ExtractedField | None) -> float | None:
    if field is None:
        return None
    if field.value_normalized and "amount" in field.value_normalized:
        return round(float(field.value_normalized["amount"]), 2)
    value = _field_value(field)
    if not value:
        return None
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
    return round(float(match.group(0).replace(",", "")), 2) if match else None


def _field_evidence(
    document: Document, field: ExtractedField, method: str, value: object
) -> dict:
    return {
        "document_id": str(document.id),
        "doc_type": document.doc_type,
        "field_name": field.field_name,
        "value": value,
        "method": method,
        "source_text": field.source_text,
    }


def _token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().upper()).strip("-")
    return cleaned or "UNKNOWN"


def _contains_token(text: str, token: str) -> bool:
    return _token(token) in _token(text)


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())
