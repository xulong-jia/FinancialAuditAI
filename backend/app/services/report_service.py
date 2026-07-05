from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_result import AuditResult
from app.models.audit_rule import AuditRule
from app.models.audit_task import AuditTask
from app.models.control_table_row import ControlTableRow
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.report import Report
from app.models.review_comment import ReviewComment
from app.services import rule_engine_service
from app.services.xlsx_writer import write_xlsx

SHEET_NAMES = [
    "Summary",
    "Procurement Control Table",
    "Exceptions",
    "Evidence Index",
    "Field Corrections",
    "Rule Definitions",
]

CONTROL_COLUMNS = [
    "task_no",
    "business_key",
    "supplier_name",
    "contract_no",
    "request_date",
    "signing_date",
    "receipt_date",
    "invoice_date",
    "voucher_date",
    "payment_date",
    "item_summary",
    "contract_amount",
    "invoice_amount",
    "payment_amount",
    "time_check",
    "quantity_check",
    "amount_check",
    "name_check",
    "tax_check",
    "missing_field_check",
    "overall_status",
    "evidence_refs",
    "reviewer_comment",
]
SALES_CONTROL_COLUMNS = [
    "task_no",
    "business_key",
    "customer_name",
    "contract_no",
    "order_no",
    "delivery_no",
    "invoice_no",
    "receipt_no",
    "signing_date",
    "order_date",
    "delivery_date",
    "signed_date",
    "invoice_date",
    "receipt_date",
    "item_summary",
    "contract_amount",
    "invoice_amount",
    "receipt_amount",
    "time_check",
    "quantity_check",
    "amount_check",
    "name_check",
    "missing_field_check",
    "overall_status",
    "evidence_refs",
    "reviewer_comment",
]
CONFIRMATION_CONTROL_COLUMNS = [
    "task_no",
    "business_key",
    "confirmation_no",
    "counterparty_name",
    "sent_date",
    "replied_date",
    "book_amount",
    "confirmed_amount",
    "difference_amount",
    "exception_reason",
    "date_check",
    "amount_check",
    "name_check",
    "seal_sign_check",
    "missing_field_check",
    "overall_status",
    "evidence_refs",
    "reviewer_comment",
]
INTERVIEW_CONTROL_COLUMNS = [
    "task_no",
    "business_key",
    "interview_date",
    "interviewee_name",
    "interviewee_title",
    "company_name",
    "topics",
    "key_answers",
    "mentioned_amounts",
    "mentioned_counterparties",
    "signature_check",
    "date_check",
    "amount_check",
    "counterparty_check",
    "missing_field_check",
    "overall_status",
    "evidence_refs",
    "reviewer_comment",
]

RULE_CHECK_COLUMNS = {
    "PROC_TIME_001": "time_check",
    "PROC_QTY_001": "quantity_check",
    "PROC_AMOUNT_001": "amount_check",
    "PROC_NAME_001": "name_check",
    "PROC_TAX_001": "tax_check",
    "PROC_MISSING_001": "missing_field_check",
    "SALES_TIME_001": "time_check",
    "SALES_QTY_001": "quantity_check",
    "SALES_AMOUNT_001": "amount_check",
    "SALES_NAME_001": "name_check",
    "SALES_MISSING_001": "missing_field_check",
    "CONF_DATE_001": "date_check",
    "CONF_AMOUNT_001": "amount_check",
    "CONF_NAME_001": "name_check",
    "CONF_SEAL_SIGN_001": "seal_sign_check",
    "CONF_MISSING_001": "missing_field_check",
    "INTERVIEW_DATE_001": "date_check",
    "INTERVIEW_SIGNATURE_001": "signature_check",
    "INTERVIEW_AMOUNT_001": "amount_check",
    "INTERVIEW_COUNTERPARTY_001": "counterparty_check",
    "INTERVIEW_MISSING_001": "missing_field_check",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def reports_root() -> Path:
    return project_root() / "local_storage" / "reports"


def generate_control_table_report(
    db: Session, task_id: UUID, generated_by: str | None = None
) -> Report:
    task = db.get(AuditTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    generated_at = datetime.now(timezone.utc)
    documents = _list_documents(db, task_id)
    fields = _list_fields(db, task_id)
    results = _list_results(db, task_id)
    comments = _list_comments(db, task_id)
    rules = rule_engine_service.list_rules(db)
    control_rows = _build_control_rows(task, documents, fields, results, comments)

    db.query(ControlTableRow).filter(ControlTableRow.task_id == task_id).delete()
    for row in control_rows:
        db.add(
            ControlTableRow(
                task_id=task_id,
                business_key=row["business_key"],
                scenario=task.scenario,
                row_data=row,
                overall_status=row["overall_status"],
                evidence_refs=json.loads(row["evidence_refs"]),
                reviewer_comment=row["reviewer_comment"] or None,
            )
        )

    summary = _summary(task, documents, results, control_rows, generated_at)
    sheets = _sheets(task, documents, fields, results, comments, rules, control_rows, summary)
    report_id = uuid4()
    file_path = reports_root() / str(task_id) / f"{report_id}.xlsx"
    write_xlsx(file_path, sheets)

    if task.scenario == "sales":
        report_type = "sales_control_table"
        report_title = f"{task.task_no} Sales Control Table"
    elif task.scenario == "confirmation":
        report_type = "confirmation_exception_report"
        report_title = f"{task.task_no} Confirmation Exception Report"
    elif task.scenario == "interview":
        report_type = "interview_evidence_report"
        report_title = f"{task.task_no} Interview Evidence Report"
    else:
        report_type = "procurement_control_table"
        report_title = f"{task.task_no} Procurement Control Table"
    report = Report(
        id=report_id,
        task_id=task_id,
        report_type=report_type,
        title=report_title,
        status="completed",
        file_format="xlsx",
        storage_path=str(file_path.relative_to(project_root())),
        summary=summary,
        generated_by=generated_by,
        generated_at=generated_at,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def list_reports(db: Session, task_id: UUID) -> list[Report]:
    if db.get(AuditTask, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return list(
        db.scalars(
            select(Report)
            .where(Report.task_id == task_id)
            .order_by(Report.generated_at.desc(), Report.created_at.desc())
        )
    )


def get_report(db: Session, report_id: UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def report_file_path(report: Report) -> Path:
    path = project_root() / report.storage_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report file not found")
    return path


def _list_documents(db: Session, task_id: UUID) -> list[Document]:
    return list(db.scalars(select(Document).where(Document.task_id == task_id)))


def _list_fields(db: Session, task_id: UUID) -> list[ExtractedField]:
    return list(db.scalars(select(ExtractedField).where(ExtractedField.task_id == task_id)))


def _list_results(db: Session, task_id: UUID) -> list[AuditResult]:
    return list(db.scalars(select(AuditResult).where(AuditResult.task_id == task_id)))


def _list_comments(db: Session, task_id: UUID) -> list[ReviewComment]:
    return list(db.scalars(select(ReviewComment).where(ReviewComment.task_id == task_id)))


def _build_control_rows(
    task: AuditTask,
    documents: list[Document],
    fields: list[ExtractedField],
    results: list[AuditResult],
    comments: list[ReviewComment],
) -> list[dict]:
    docs_by_key: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        docs_by_key[document.business_key or f"UNLINKED-{document.id}"].append(document)
    keys = sorted(set(docs_by_key) | {result.business_key for result in results})
    fields_by_document = _fields_by_document(fields)
    results_by_key = _results_by_key(results)
    comments_by_result = _comments_by_result(comments)
    comments_by_field = _comments_by_field(comments)

    rows = []
    for business_key in keys:
        group_docs = docs_by_key.get(business_key, [])
        group_results = results_by_key.get(business_key, [])
        statuses = {RULE_CHECK_COLUMNS[result.rule_code]: result.status for result in group_results if result.rule_code in RULE_CHECK_COLUMNS}
        evidence_refs = [
            {"rule_code": result.rule_code, "evidence": result.evidence}
            for result in group_results
        ]
        field_ids = {
            str(field.id)
            for document in group_docs
            for field in fields_by_document.get(document.id, {}).values()
        }
        reviewer_comment = "; ".join(
            comment.content
            for result in group_results
            for comment in comments_by_result.get(result.id, [])
        )
        field_comments = "; ".join(
            comment.content
            for field_id in field_ids
            for comment in comments_by_field.get(field_id, [])
        )
        if field_comments:
            reviewer_comment = "; ".join(filter(None, [reviewer_comment, field_comments]))

        common = {
            "task_no": task.task_no,
            "business_key": business_key,
            "date_check": statuses.get("date_check", "-"),
            "time_check": statuses.get("time_check", "-"),
            "quantity_check": statuses.get("quantity_check", "-"),
            "amount_check": statuses.get("amount_check", "-"),
            "name_check": statuses.get("name_check", "-"),
            "seal_sign_check": statuses.get("seal_sign_check", "-"),
            "signature_check": statuses.get("signature_check", "-"),
            "counterparty_check": statuses.get("counterparty_check", "-"),
            "missing_field_check": statuses.get("missing_field_check", "-"),
            "overall_status": _overall_status([result.status for result in group_results]),
            "evidence_refs": _json(evidence_refs),
            "reviewer_comment": reviewer_comment,
        }
        if task.scenario == "sales":
            row = common | {
                "customer_name": _first_text(group_docs, fields_by_document, (("sales_contract", "customer_name"), ("sales_order", "customer_name"), ("sales_invoice", "buyer_name"), ("receipt_voucher", "payer_name"))),
                "contract_no": _first_text(group_docs, fields_by_document, (("sales_contract", "contract_no"),)),
                "order_no": _first_text(group_docs, fields_by_document, (("sales_order", "order_no"),)),
                "delivery_no": _first_text(group_docs, fields_by_document, (("delivery_order", "delivery_no"),)),
                "invoice_no": _first_text(group_docs, fields_by_document, (("sales_invoice", "invoice_no"),)),
                "receipt_no": _first_text(group_docs, fields_by_document, (("receipt_voucher", "receipt_no"),)),
                "signing_date": _first_text(group_docs, fields_by_document, (("sales_contract", "signing_date"),)),
                "order_date": _first_text(group_docs, fields_by_document, (("sales_order", "order_date"),)),
                "delivery_date": _first_text(group_docs, fields_by_document, (("delivery_order", "delivery_date"),)),
                "signed_date": _first_text(group_docs, fields_by_document, (("logistics_receipt", "signed_date"),)),
                "invoice_date": _first_text(group_docs, fields_by_document, (("sales_invoice", "invoice_date"),)),
                "receipt_date": _first_text(group_docs, fields_by_document, (("receipt_voucher", "receipt_date"),)),
                "item_summary": _first_text(group_docs, fields_by_document, (("sales_contract", "item_lines"), ("sales_invoice", "item_lines"))),
                "contract_amount": _sum_amounts(group_docs, fields_by_document, "sales_contract", "amount_including_tax"),
                "invoice_amount": _sum_amounts(group_docs, fields_by_document, "sales_invoice", "amount_including_tax"),
                "receipt_amount": _sum_amounts(group_docs, fields_by_document, "receipt_voucher", "amount"),
            }
        elif task.scenario == "confirmation":
            row = common | {
                "confirmation_no": _first_text(group_docs, fields_by_document, (("confirmation_request", "confirmation_no"), ("confirmation_reply", "confirmation_no"), ("confirmation_adjustment", "confirmation_no"), ("confirmation", "confirmation_no"))),
                "counterparty_name": _first_text(group_docs, fields_by_document, (("confirmation_request", "counterparty_name"), ("confirmation_reply", "counterparty_name"), ("confirmation", "counterparty_name"))),
                "sent_date": _first_text(group_docs, fields_by_document, (("confirmation_request", "sent_date"), ("confirmation", "sent_date"))),
                "replied_date": _first_text(group_docs, fields_by_document, (("confirmation_reply", "replied_date"), ("confirmation", "replied_date"))),
                "book_amount": _sum_amounts_for(group_docs, fields_by_document, (("confirmation_request", "book_amount"), ("confirmation", "book_amount"))),
                "confirmed_amount": _sum_amounts_for(group_docs, fields_by_document, (("confirmation_reply", "confirmed_amount"), ("confirmation", "confirmed_amount"))),
                "difference_amount": _sum_amounts_for(group_docs, fields_by_document, (("confirmation_adjustment", "difference_amount"), ("confirmation", "difference_amount"))),
                "exception_reason": _first_text(group_docs, fields_by_document, (("confirmation_adjustment", "exception_reason"), ("confirmation", "exception_reason"))),
            }
        elif task.scenario == "interview":
            row = common | {
                "interview_date": _first_text(group_docs, fields_by_document, (("interview_record", "interview_date"), ("interview_transcript", "interview_date"), ("interview_signature_page", "interview_date"))),
                "interviewee_name": _first_text(group_docs, fields_by_document, (("interview_record", "interviewee_name"), ("interview_transcript", "interviewee_name"), ("interview_signature_page", "interviewee_name"))),
                "interviewee_title": _first_text(group_docs, fields_by_document, (("interview_record", "interviewee_title"),)),
                "company_name": _first_text(group_docs, fields_by_document, (("interview_record", "company_name"),)),
                "topics": _first_text(group_docs, fields_by_document, (("interview_record", "topics"), ("interview_outline", "topics"), ("interview_transcript", "topics"))),
                "key_answers": _first_text(group_docs, fields_by_document, (("interview_record", "key_answers"), ("interview_transcript", "key_answers"))),
                "mentioned_amounts": _sum_amounts_for(group_docs, fields_by_document, (("interview_record", "mentioned_amounts"), ("interview_transcript", "mentioned_amounts"))),
                "mentioned_counterparties": _first_text(group_docs, fields_by_document, (("interview_record", "mentioned_counterparties"), ("interview_transcript", "mentioned_counterparties"))),
            }
        else:
            row = common | {
                "supplier_name": _first_text(group_docs, fields_by_document, (("purchase_contract", "supplier_name"), ("invoice", "seller_name"), ("payment_receipt", "payee_name"))),
                "contract_no": _first_text(group_docs, fields_by_document, (("purchase_contract", "contract_no"),)),
                "request_date": _first_text(group_docs, fields_by_document, (("purchase_request", "request_date"),)),
                "signing_date": _first_text(group_docs, fields_by_document, (("purchase_contract", "signing_date"),)),
                "receipt_date": _first_text(group_docs, fields_by_document, (("warehouse_receipt", "receipt_date"),)),
                "invoice_date": _first_text(group_docs, fields_by_document, (("invoice", "invoice_date"),)),
                "voucher_date": _first_text(group_docs, fields_by_document, (("accounting_voucher", "voucher_date"),)),
                "payment_date": _first_text(group_docs, fields_by_document, (("payment_receipt", "payment_date"),)),
                "item_summary": _first_text(group_docs, fields_by_document, (("purchase_contract", "item_lines"), ("invoice", "item_lines"))),
                "contract_amount": _sum_amounts(group_docs, fields_by_document, "purchase_contract", "amount_including_tax"),
                "invoice_amount": _sum_amounts(group_docs, fields_by_document, "invoice", "amount_including_tax"),
                "payment_amount": _sum_amounts(group_docs, fields_by_document, "payment_receipt", "amount"),
                "tax_check": statuses.get("tax_check", "-"),
            }
        rows.append(row)
    return rows


def _sheets(
    task: AuditTask,
    documents: list[Document],
    fields: list[ExtractedField],
    results: list[AuditResult],
    comments: list[ReviewComment],
    rules: list[AuditRule],
    control_rows: list[dict],
    summary: dict,
) -> dict[str, list[list[object | None]]]:
    if task.scenario == "sales":
        control_columns = SALES_CONTROL_COLUMNS
        control_sheet_name = "Sales Control Table"
    elif task.scenario == "confirmation":
        control_columns = CONFIRMATION_CONTROL_COLUMNS
        control_sheet_name = "Confirmation Results"
    elif task.scenario == "interview":
        control_columns = INTERVIEW_CONTROL_COLUMNS
        control_sheet_name = "Interview Evidence"
    else:
        control_columns = CONTROL_COLUMNS
        control_sheet_name = "Procurement Control Table"
    return {
        "Summary": _summary_rows(summary),
        control_sheet_name: [control_columns] + [[row[column] for column in control_columns] for row in control_rows],
        "Exceptions": _exception_rows(results),
        "Evidence Index": _evidence_rows(documents, fields),
        "Field Corrections": _correction_rows(comments),
        "Rule Definitions": _rule_rows(rules, results),
    }


def _summary(
    task: AuditTask,
    documents: list[Document],
    results: list[AuditResult],
    control_rows: list[dict],
    generated_at: datetime,
) -> dict:
    counts = Counter(result.status for result in results)
    return {
        "task_no": task.task_no,
        "task_name": task.name,
        "scenario": task.scenario,
        "company_name": task.company_name,
        "document_count": len(documents),
        "audit_result_count": len(results),
        "pass_count": counts.get("pass", 0),
        "fail_count": counts.get("fail", 0),
        "warning_count": counts.get("warning", 0),
        "need_review_count": counts.get("need_review", 0),
        "generated_at": generated_at.isoformat(),
        "data_source": "FinancialAuditAI extracted_fields, audit_results, review_comments",
        "usage_boundary": f"{task.scenario} walkthrough review support; not a legal, audit, or investment conclusion.",
        "control_table_preview": control_rows[:20],
    }


def _summary_rows(summary: dict) -> list[list[object | None]]:
    columns = [
        "task_no",
        "task_name",
        "scenario",
        "company_name",
        "document_count",
        "audit_result_count",
        "pass_count",
        "fail_count",
        "warning_count",
        "need_review_count",
        "generated_at",
        "data_source",
        "usage_boundary",
    ]
    return [columns, [summary.get(column) for column in columns]]


def _exception_rows(results: list[AuditResult]) -> list[list[object | None]]:
    rows = [["business_key", "rule_code", "status", "severity", "message", "expected_value", "actual_value", "review_status", "evidence"]]
    for result in results:
        if result.status == "pass":
            continue
        rows.append([
            result.business_key,
            result.rule_code,
            result.status,
            result.severity,
            result.message,
            _json(result.expected_value),
            _json(result.actual_value),
            result.review_status,
            _json(result.evidence),
        ])
    return rows


def _evidence_rows(documents: list[Document], fields: list[ExtractedField]) -> list[list[object | None]]:
    document_by_id = {document.id: document for document in documents}
    rows = [["document_id", "original_filename", "doc_type", "field_name", "value_text", "source_page", "source_text"]]
    for field in fields:
        document = document_by_id.get(field.document_id)
        rows.append([
            str(field.document_id),
            document.original_filename if document else "",
            document.doc_type if document else "",
            field.field_name,
            field.value_text,
            field.source_page,
            field.source_text,
        ])
    return rows


def _correction_rows(comments: list[ReviewComment]) -> list[list[object | None]]:
    rows = [["field_id", "field_name", "before_value", "after_value", "content / reason", "created_at"]]
    for comment in comments:
        if comment.comment_type != "field_correction":
            continue
        before = comment.before_value or {}
        after = comment.after_value or {}
        rows.append([
            str(comment.field_id) if comment.field_id else "",
            before.get("field_name") or after.get("field_name") or "",
            _json(comment.before_value),
            _json(comment.after_value),
            comment.content,
            comment.created_at.isoformat(),
        ])
    return rows


def _rule_rows(rules: list[AuditRule], results: list[AuditResult]) -> list[list[object | None]]:
    severity_by_rule = {result.rule_code: result.severity for result in results}
    rows = [["rule_code", "name", "scenario", "category", "severity", "version", "enabled", "parameters"]]
    for rule in rules:
        rows.append([
            rule.rule_code,
            rule.name,
            rule.category,
            f"{rule.category}_walkthrough",
            severity_by_rule.get(rule.rule_code, ""),
            rule.version,
            rule.enabled,
            _json(rule.parameters),
        ])
    return rows


def _fields_by_document(fields: list[ExtractedField]) -> dict[UUID, dict[str, ExtractedField]]:
    mapped: dict[UUID, dict[str, ExtractedField]] = defaultdict(dict)
    for field in fields:
        mapped[field.document_id][field.field_name] = field
    return mapped


def _results_by_key(results: list[AuditResult]) -> dict[str, list[AuditResult]]:
    mapped: dict[str, list[AuditResult]] = defaultdict(list)
    for result in results:
        mapped[result.business_key].append(result)
    return mapped


def _comments_by_result(comments: list[ReviewComment]) -> dict[UUID, list[ReviewComment]]:
    mapped: dict[UUID, list[ReviewComment]] = defaultdict(list)
    for comment in comments:
        if comment.audit_result_id:
            mapped[comment.audit_result_id].append(comment)
    return mapped


def _comments_by_field(comments: list[ReviewComment]) -> dict[str, list[ReviewComment]]:
    mapped: dict[str, list[ReviewComment]] = defaultdict(list)
    for comment in comments:
        if comment.field_id:
            mapped[str(comment.field_id)].append(comment)
    return mapped


def _first_text(
    documents: list[Document],
    fields_by_document: dict[UUID, dict[str, ExtractedField]],
    lookups: tuple[tuple[str, str], ...],
) -> str:
    for doc_type, field_name in lookups:
        for document in documents:
            if document.doc_type != doc_type:
                continue
            field = fields_by_document.get(document.id, {}).get(field_name)
            if field and field.value_text:
                return field.value_text
    return ""


def _sum_amounts(
    documents: list[Document],
    fields_by_document: dict[UUID, dict[str, ExtractedField]],
    doc_type: str,
    field_name: str,
) -> float:
    return sum(
        amount
        for document in documents
        if document.doc_type == doc_type
        for field in [fields_by_document.get(document.id, {}).get(field_name)]
        for amount in [_amount(field)]
        if amount is not None
    )


def _sum_amounts_for(
    documents: list[Document],
    fields_by_document: dict[UUID, dict[str, ExtractedField]],
    lookups: tuple[tuple[str, str], ...],
) -> float:
    return sum(_sum_amounts(documents, fields_by_document, doc_type, field_name) for doc_type, field_name in lookups)


def _amount(field: ExtractedField | None) -> float | None:
    if field is None:
        return None
    if field.value_normalized and "amount" in field.value_normalized:
        return float(field.value_normalized["amount"])
    if not field.value_text:
        return None
    try:
        return float(field.value_text.replace(",", ""))
    except ValueError:
        return None


def _overall_status(statuses: list[str]) -> str:
    if "fail" in statuses:
        return "fail"
    if "need_review" in statuses:
        return "need_review"
    if "warning" in statuses:
        return "warning"
    if statuses:
        return "pass"
    return "need_review"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
