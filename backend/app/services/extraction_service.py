from dataclasses import dataclass
from datetime import date
import json
import re
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.extracted_field import ExtractedField
from app.schemas.document import DocumentDocType
from app.schemas.extraction import ExtractedFieldValue, FieldType, validate_document_extraction
from app.services import audit_log_service, llm_provider, model_invocation_service


class ExtractionProviderError(ValueError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    field_name: str
    field_label: str
    field_type: FieldType
    aliases: tuple[str, ...]
    is_required: bool = True


FIELD_NAME_ALIASES = {
    "requester": "requester_name",
    "approver": "approver_name",
    "receiver": "receiver_name",
    "preparer": "preparer_name",
    "reviewer": "reviewer_name",
}


SCHEMA_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "purchase_request": (
        FieldSpec("request_no", "Request No", "text", ("request no", "request_no", "申请编号")),
        FieldSpec("request_date", "Request Date", "date", ("request date", "申请日期")),
        FieldSpec("applicant_dept", "Applicant Department", "text", ("applicant dept", "request department", "申请部门"), False),
        FieldSpec("requester_name", "Requester Name", "name", ("requester name", "applicant", "申请人"), False),
        FieldSpec("approval_date", "Approval Date", "date", ("approval date", "审批日期")),
        FieldSpec("approval_status", "Approval Status", "status", ("approval status", "审批状态")),
        FieldSpec("approver_name", "Approver Name", "name", ("approver name", "approver", "审批人"), False),
        FieldSpec("supplier_candidate", "Supplier Candidate", "name", ("supplier candidate", "candidate supplier", "候选供应商"), False),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "total_estimated_amount",
            "Total Estimated Amount",
            "money",
            ("total estimated amount", "estimated amount", "预计总金额"),
        ),
        FieldSpec("budget_code", "Budget Code", "text", ("budget code", "预算编号"), False),
    ),
    "purchase_contract": (
        FieldSpec("contract_no", "Contract No", "text", ("contract no", "contract_no", "合同编号")),
        FieldSpec("signing_date", "Signing Date", "date", ("signing date", "签署日期")),
        FieldSpec("effective_date", "Effective Date", "date", ("effective date", "生效日期"), False),
        FieldSpec("expiry_date", "Expiry Date", "date", ("expiry date", "expiration date", "到期日期"), False),
        FieldSpec("buyer_name", "Buyer Name", "name", ("buyer name", "buyer", "买方", "甲方")),
        FieldSpec("supplier_name", "Supplier Name", "name", ("supplier name", "supplier", "供应商", "乙方")),
        FieldSpec("supplier_tax_no", "Supplier Tax No", "text", ("supplier tax no", "supplier tax id", "供应商税号"), False),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "amount_excluding_tax",
            "Amount Excluding Tax",
            "money",
            ("amount excluding tax", "subtotal", "不含税金额"),
            False,
        ),
        FieldSpec("tax_amount", "Tax Amount", "money", ("tax amount", "税额"), False),
        FieldSpec(
            "amount_including_tax",
            "Amount Including Tax",
            "money",
            ("amount including tax", "total with tax", "含税金额", "价税合计"),
        ),
        FieldSpec("tax_rate", "Tax Rate", "tax_rate", ("tax rate", "税率"), is_required=False),
        FieldSpec(
            "payment_terms",
            "Payment Terms",
            "text",
            ("payment terms", "付款条款"),
            is_required=False,
        ),
        FieldSpec("delivery_terms", "Delivery Terms", "text", ("delivery terms", "交付条款"), False),
        FieldSpec("seal_detected", "Seal Detected", "status", ("seal detected", "seal", "公章"), False),
        FieldSpec("signature_detected", "Signature Detected", "status", ("signature detected", "signature", "签字"), False),
    ),
    "warehouse_receipt": (
        FieldSpec("receipt_no", "Receipt No", "text", ("receipt no", "receipt_no", "入库单号")),
        FieldSpec("receipt_date", "Receipt Date", "date", ("receipt date", "入库日期")),
        FieldSpec("supplier_name", "Supplier Name", "name", ("supplier name", "supplier", "供应商")),
        FieldSpec("warehouse_name", "Warehouse Name", "text", ("warehouse name", "warehouse", "仓库"), False),
        FieldSpec("receiver_name", "Receiver Name", "name", ("receiver name", "received by", "receiver", "收货人"), False),
        FieldSpec("quality_status", "Quality Status", "status", ("quality status", "inspection status", "质检状态"), False),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "related_contract_no",
            "Related Contract No",
            "text",
            ("related contract no", "contract no", "关联合同"),
            is_required=False,
        ),
    ),
    "invoice": (
        FieldSpec("invoice_no", "Invoice No", "text", ("invoice no", "invoice number", "发票号码")),
        FieldSpec("invoice_code", "Invoice Code", "text", ("invoice code", "发票代码"), False),
        FieldSpec("invoice_date", "Invoice Date", "date", ("invoice date", "issue date", "开票日期")),
        FieldSpec("invoice_type", "Invoice Type", "text", ("invoice type", "发票类型"), False),
        FieldSpec("seller_name", "Seller Name", "name", ("seller name", "seller", "销售方")),
        FieldSpec("seller_tax_no", "Seller Tax No", "text", ("seller tax no", "seller tax id", "销售方税号"), False),
        FieldSpec("buyer_name", "Buyer Name", "name", ("buyer name", "buyer", "购买方")),
        FieldSpec("buyer_tax_no", "Buyer Tax No", "text", ("buyer tax no", "buyer tax id", "购买方税号"), False),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "amount_excluding_tax",
            "Amount Excluding Tax",
            "money",
            ("amount excluding tax", "subtotal", "不含税金额"),
        ),
        FieldSpec("tax_amount", "Tax Amount", "money", ("tax amount", "税额")),
        FieldSpec(
            "amount_including_tax",
            "Amount Including Tax",
            "money",
            ("amount including tax", "total with tax", "价税合计"),
        ),
        FieldSpec("tax_rate", "Tax Rate", "tax_rate", ("tax rate", "税率"), False),
        FieldSpec("checksum", "Checksum", "text", ("checksum", "校验码"), False),
    ),
    "accounting_voucher": (
        FieldSpec("voucher_no", "Voucher No", "text", ("voucher no", "凭证号")),
        FieldSpec("voucher_date", "Voucher Date", "date", ("voucher date", "凭证日期")),
        FieldSpec("summary", "Summary", "text", ("summary", "摘要")),
        FieldSpec("debit_subject", "Debit Subject", "text", ("debit subject", "借方科目")),
        FieldSpec("credit_subject", "Credit Subject", "text", ("credit subject", "贷方科目")),
        FieldSpec("amount", "Amount", "money", ("amount", "金额")),
        FieldSpec("supplier_name", "Supplier Name", "name", ("supplier name", "supplier", "供应商"), False),
        FieldSpec(
            "related_invoice_no",
            "Related Invoice No",
            "text",
            ("related invoice no", "invoice no", "关联发票"),
            False,
        ),
        FieldSpec("preparer_name", "Preparer Name", "name", ("preparer name", "preparer", "制单人"), False),
        FieldSpec("reviewer_name", "Reviewer Name", "name", ("reviewer name", "reviewer", "复核人"), False),
        FieldSpec("attachment_count", "Attachment Count", "text", ("attachment count", "attachments", "附件张数"), False),
    ),
    "payment_receipt": (
        FieldSpec("payment_no", "Payment No", "text", ("payment no", "transaction no", "流水号")),
        FieldSpec("payment_date", "Payment Date", "date", ("payment date", "付款日期")),
        FieldSpec("payer_name", "Payer Name", "name", ("payer name", "payer", "付款方")),
        FieldSpec("payee_name", "Payee Name", "name", ("payee name", "payee", "收款方")),
        FieldSpec("payee_account_masked", "Payee Account Masked", "text", ("payee account", "account masked", "收款账号"), False),
        FieldSpec("bank_name", "Bank Name", "name", ("bank name", "bank", "银行名称"), False),
        FieldSpec("bank_serial_no", "Bank Serial No", "text", ("bank serial no", "serial no", "银行流水号"), False),
        FieldSpec("amount", "Amount", "money", ("amount", "付款金额", "金额")),
        FieldSpec("currency", "Currency", "currency", ("currency", "币种")),
        FieldSpec("payment_purpose", "Payment Purpose", "text", ("payment purpose", "用途"), False),
        FieldSpec(
            "related_contract_no",
            "Related Contract No",
            "text",
            ("related contract no", "contract no", "关联合同"),
            False,
        ),
    ),
}

SALES_SCHEMA_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "sales_contract": (
        FieldSpec("contract_no", "Contract No", "text", ("contract no", "contract_no", "合同编号")),
        FieldSpec("signing_date", "Signing Date", "date", ("signing date", "签署日期")),
        FieldSpec("customer_name", "Customer Name", "name", ("customer name", "customer", "客户名称")),
        FieldSpec("seller_name", "Seller Name", "name", ("seller name", "seller", "销售方")),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec(
            "amount_including_tax",
            "Amount Including Tax",
            "money",
            ("amount including tax", "total with tax", "含税金额", "价税合计"),
        ),
        FieldSpec("payment_terms", "Payment Terms", "text", ("payment terms", "付款条款"), False),
        FieldSpec("delivery_terms", "Delivery Terms", "text", ("delivery terms", "交付条款"), False),
    ),
    "sales_order": (
        FieldSpec("order_no", "Order No", "text", ("order no", "order_no", "订单编号")),
        FieldSpec("order_date", "Order Date", "date", ("order date", "订单日期")),
        FieldSpec("customer_name", "Customer Name", "name", ("customer name", "customer", "客户名称")),
        FieldSpec(
            "related_contract_no",
            "Related Contract No",
            "text",
            ("related contract no", "contract no", "关联合同"),
            False,
        ),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec("amount", "Amount", "money", ("amount", "订单金额", "金额")),
    ),
    "delivery_order": (
        FieldSpec("delivery_no", "Delivery No", "text", ("delivery no", "delivery_no", "出库单号")),
        FieldSpec("delivery_date", "Delivery Date", "date", ("delivery date", "出库日期")),
        FieldSpec("customer_name", "Customer Name", "name", ("customer name", "customer", "客户名称")),
        FieldSpec("related_order_no", "Related Order No", "text", ("related order no", "order no", "关联订单"), False),
        FieldSpec(
            "related_contract_no",
            "Related Contract No",
            "text",
            ("related contract no", "contract no", "关联合同"),
            False,
        ),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec("warehouse_name", "Warehouse Name", "text", ("warehouse name", "warehouse", "仓库"), False),
    ),
    "logistics_receipt": (
        FieldSpec("logistics_no", "Logistics No", "text", ("logistics no", "logistics_no", "物流单号")),
        FieldSpec("shipment_date", "Shipment Date", "date", ("shipment date", "发货日期")),
        FieldSpec("signed_date", "Signed Date", "date", ("signed date", "签收日期")),
        FieldSpec("receiver_name", "Receiver Name", "name", ("receiver name", "receiver", "收货方")),
        FieldSpec("customer_name", "Customer Name", "name", ("customer name", "customer", "客户名称"), False),
        FieldSpec(
            "related_delivery_no",
            "Related Delivery No",
            "text",
            ("related delivery no", "delivery no", "关联出库单"),
            False,
        ),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec("signer", "Signer", "name", ("signer", "签收人"), False),
    ),
    "sales_invoice": (
        FieldSpec("invoice_no", "Invoice No", "text", ("invoice no", "invoice number", "发票号码")),
        FieldSpec("invoice_date", "Invoice Date", "date", ("invoice date", "issue date", "开票日期")),
        FieldSpec("seller_name", "Seller Name", "name", ("seller name", "seller", "销售方")),
        FieldSpec("buyer_name", "Buyer Name", "name", ("buyer name", "buyer", "购买方")),
        FieldSpec("item_lines", "Item Lines", "line_items", ("item", "line item", "明细")),
        FieldSpec("amount_excluding_tax", "Amount Excluding Tax", "money", ("amount excluding tax", "subtotal", "不含税金额")),
        FieldSpec("tax_amount", "Tax Amount", "money", ("tax amount", "税额")),
        FieldSpec("amount_including_tax", "Amount Including Tax", "money", ("amount including tax", "total with tax", "价税合计")),
    ),
    "receipt_voucher": (
        FieldSpec("receipt_no", "Receipt No", "text", ("receipt no", "receipt_no", "收款编号")),
        FieldSpec("receipt_date", "Receipt Date", "date", ("receipt date", "收款日期")),
        FieldSpec("payer_name", "Payer Name", "name", ("payer name", "payer", "付款方")),
        FieldSpec("payee_name", "Payee Name", "name", ("payee name", "payee", "收款方")),
        FieldSpec("amount", "Amount", "money", ("amount", "收款金额", "金额")),
        FieldSpec("currency", "Currency", "currency", ("currency", "币种")),
        FieldSpec("receipt_purpose", "Receipt Purpose", "text", ("receipt purpose", "用途"), False),
        FieldSpec("related_contract_no", "Related Contract No", "text", ("related contract no", "contract no", "关联合同"), False),
        FieldSpec("bank_serial_no", "Bank Serial No", "text", ("bank serial no", "serial no", "银行流水号"), False),
    ),
    "accounting_voucher": (
        FieldSpec("voucher_no", "Voucher No", "text", ("voucher no", "凭证号")),
        FieldSpec("voucher_date", "Voucher Date", "date", ("voucher date", "凭证日期")),
        FieldSpec("summary", "Summary", "text", ("summary", "摘要")),
        FieldSpec("debit_subject", "Debit Subject", "text", ("debit subject", "借方科目")),
        FieldSpec("credit_subject", "Credit Subject", "text", ("credit subject", "贷方科目")),
        FieldSpec("amount", "Amount", "money", ("amount", "金额")),
        FieldSpec("customer_name", "Customer Name", "name", ("customer name", "customer", "客户名称"), False),
        FieldSpec("related_invoice_no", "Related Invoice No", "text", ("related invoice no", "invoice no", "关联发票"), False),
    ),
}


CONFIRMATION_SCHEMA_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "confirmation": (
        FieldSpec("confirmation_no", "Confirmation No", "text", ("confirmation no", "confirmation_no", "函证编号")),
        FieldSpec("counterparty_name", "Counterparty Name", "name", ("counterparty name", "counterparty", "被函证方")),
        FieldSpec("counterparty_address", "Counterparty Address", "text", ("counterparty address", "address", "地址"), False),
        FieldSpec("sent_date", "Sent Date", "date", ("sent date", "发函日期")),
        FieldSpec("replied_date", "Replied Date", "date", ("replied date", "reply date", "回函日期")),
        FieldSpec("confirmed_amount", "Confirmed Amount", "money", ("confirmed amount", "回函金额")),
        FieldSpec("book_amount", "Book Amount", "money", ("book amount", "账面金额")),
        FieldSpec("difference_amount", "Difference Amount", "money", ("difference amount", "差异金额")),
        FieldSpec("seal_detected", "Seal Detected", "status", ("seal detected", "seal", "公章"), False),
        FieldSpec("signatory", "Signatory", "name", ("signatory", "signature", "签字人", "签字"), False),
        FieldSpec("reply_channel", "Reply Channel", "text", ("reply channel", "回函渠道"), False),
        FieldSpec("exception_reason", "Exception Reason", "text", ("exception reason", "差异原因"), False),
    ),
    "confirmation_request": (
        FieldSpec("confirmation_no", "Confirmation No", "text", ("confirmation no", "confirmation_no", "函证编号")),
        FieldSpec("counterparty_name", "Counterparty Name", "name", ("counterparty name", "counterparty", "被函证方")),
        FieldSpec("counterparty_address", "Counterparty Address", "text", ("counterparty address", "address", "地址"), False),
        FieldSpec("sent_date", "Sent Date", "date", ("sent date", "发函日期")),
        FieldSpec("book_amount", "Book Amount", "money", ("book amount", "账面金额")),
    ),
    "confirmation_reply": (
        FieldSpec("confirmation_no", "Confirmation No", "text", ("confirmation no", "confirmation_no", "函证编号")),
        FieldSpec("counterparty_name", "Counterparty Name", "name", ("counterparty name", "counterparty", "被函证方")),
        FieldSpec("replied_date", "Replied Date", "date", ("replied date", "reply date", "回函日期")),
        FieldSpec("confirmed_amount", "Confirmed Amount", "money", ("confirmed amount", "回函金额")),
        FieldSpec("seal_detected", "Seal Detected", "status", ("seal detected", "seal", "公章"), False),
        FieldSpec("signatory", "Signatory", "name", ("signatory", "signature", "签字人", "签字"), False),
        FieldSpec("reply_channel", "Reply Channel", "text", ("reply channel", "回函渠道"), False),
    ),
    "confirmation_adjustment": (
        FieldSpec("confirmation_no", "Confirmation No", "text", ("confirmation no", "confirmation_no", "函证编号")),
        FieldSpec("difference_amount", "Difference Amount", "money", ("difference amount", "差异金额")),
        FieldSpec("exception_reason", "Exception Reason", "text", ("exception reason", "差异原因")),
        FieldSpec("adjustment_items", "Adjustment Items", "text", ("adjustment items", "调节明细"), False),
    ),
}

INTERVIEW_SCHEMA_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "interview_record": (
        FieldSpec("interview_date", "Interview Date", "date", ("interview date", "访谈日期")),
        FieldSpec("interviewee_name", "Interviewee Name", "name", ("interviewee name", "interviewee", "被访谈人")),
        FieldSpec("interviewee_title", "Interviewee Title", "text", ("interviewee title", "title", "职务")),
        FieldSpec("company_name", "Company Name", "name", ("company name", "company", "单位")),
        FieldSpec("interviewer", "Interviewer", "name", ("interviewer", "访谈人")),
        FieldSpec("location", "Location", "text", ("location", "地点"), False),
        FieldSpec("topics", "Topics", "text", ("topics", "topic", "访谈主题")),
        FieldSpec("key_answers", "Key Answers", "text", ("key answers", "key answer", "关键回答")),
        FieldSpec("mentioned_amounts", "Mentioned Amounts", "money", ("mentioned amounts", "mentioned amount", "提及金额")),
        FieldSpec("mentioned_counterparties", "Mentioned Counterparties", "name", ("mentioned counterparties", "mentioned counterparty", "提及交易对手")),
        FieldSpec("signature_detected", "Signature Detected", "status", ("signature detected", "signature", "签字"), False),
        FieldSpec("related_contract_no", "Related Contract No", "text", ("related contract no", "contract no", "关联合同"), False),
        FieldSpec("related_invoice_no", "Related Invoice No", "text", ("related invoice no", "invoice no", "关联发票"), False),
        FieldSpec("source_paragraphs", "Source Paragraphs", "text", ("source paragraphs", "source paragraph", "来源段落"), False),
        FieldSpec("transcript_summary", "Transcript Summary", "text", ("transcript summary", "转写摘要"), False),
        FieldSpec("risk_points", "Risk Points", "text", ("risk points", "risk point", "风险点"), False),
    ),
    "interview_outline": (
        FieldSpec("topics", "Topics", "text", ("topics", "topic", "访谈主题")),
        FieldSpec("interviewer", "Interviewer", "name", ("interviewer", "访谈人"), False),
        FieldSpec("source_paragraphs", "Source Paragraphs", "text", ("source paragraphs", "source paragraph", "来源段落"), False),
    ),
    "interview_signature_page": (
        FieldSpec("interviewee_name", "Interviewee Name", "name", ("interviewee name", "interviewee", "被访谈人")),
        FieldSpec("signature_detected", "Signature Detected", "status", ("signature detected", "signature", "签字")),
        FieldSpec("interview_date", "Interview Date", "date", ("interview date", "访谈日期"), False),
    ),
    "interview_transcript": (
        FieldSpec("interview_date", "Interview Date", "date", ("interview date", "访谈日期")),
        FieldSpec("interviewee_name", "Interviewee Name", "name", ("interviewee name", "interviewee", "被访谈人")),
        FieldSpec("topics", "Topics", "text", ("topics", "topic", "访谈主题")),
        FieldSpec("key_answers", "Key Answers", "text", ("key answers", "key answer", "关键回答")),
        FieldSpec("mentioned_amounts", "Mentioned Amounts", "money", ("mentioned amounts", "mentioned amount", "提及金额")),
        FieldSpec("mentioned_counterparties", "Mentioned Counterparties", "name", ("mentioned counterparties", "mentioned counterparty", "提及交易对手")),
        FieldSpec("transcript_summary", "Transcript Summary", "text", ("transcript summary", "转写摘要"), False),
        FieldSpec("source_paragraphs", "Source Paragraphs", "text", ("source paragraphs", "source paragraph", "来源段落"), False),
    ),
}

CONTRACT_REVIEW_COMMON_SPECS: tuple[FieldSpec, ...] = (
    FieldSpec("contract_no", "Contract No", "text", ("contract no", "contract_no", "合同编号")),
    FieldSpec("contract_name", "Contract Name", "text", ("contract name", "contract_name", "合同名称")),
    FieldSpec("signing_date", "Signing Date", "date", ("signing date", "signed date", "签署日期", "签订日期")),
    FieldSpec("effective_date", "Effective Date", "date", ("effective date", "生效日期"), False),
    FieldSpec("expiry_date", "Expiry Date", "date", ("expiry date", "expiration date", "到期日期", "失效日期"), False),
    FieldSpec("party_a", "Party A", "name", ("party a", "甲方")),
    FieldSpec("party_b", "Party B", "name", ("party b", "乙方")),
    FieldSpec("counterparty_name", "Counterparty Name", "name", ("counterparty name", "counterparty", "交易对手")),
    FieldSpec(
        "amount_including_tax",
        "Amount Including Tax",
        "money",
        ("amount including tax", "total with tax", "contract amount", "含税金额", "合同金额"),
    ),
    FieldSpec("tax_rate", "Tax Rate", "tax_rate", ("tax rate", "税率"), False),
    FieldSpec("item_summary", "Item Summary", "text", ("item summary", "subject matter", "标的", "项目摘要"), False),
    FieldSpec("payment_terms", "Payment Terms", "text", ("payment terms", "付款条款", "付款条件")),
    FieldSpec("delivery_terms", "Delivery Terms", "text", ("delivery terms", "交付条款", "交付条件")),
    FieldSpec("acceptance_terms", "Acceptance Terms", "text", ("acceptance terms", "验收条款", "验收条件")),
    FieldSpec("breach_terms", "Breach Terms", "text", ("breach terms", "breach liability", "违约责任", "违约条款")),
    FieldSpec("dispute_resolution", "Dispute Resolution", "text", ("dispute resolution", "争议解决", "仲裁")),
    FieldSpec("auto_renewal_clause", "Auto Renewal Clause", "text", ("auto renewal clause", "auto renewal", "自动续期"), False),
    FieldSpec("exclusivity_clause", "Exclusivity Clause", "text", ("exclusivity clause", "exclusivity", "排他"), False),
    FieldSpec("repurchase_clause", "Repurchase Clause", "text", ("repurchase clause", "repurchase", "回购"), False),
    FieldSpec(
        "minimum_guarantee_clause",
        "Minimum Guarantee Clause",
        "text",
        ("minimum guarantee clause", "minimum guarantee", "guaranteed minimum", "保底"),
        False,
    ),
    FieldSpec(
        "price_adjustment_clause",
        "Price Adjustment Clause",
        "text",
        ("price adjustment clause", "price adjustment", "价格调整"),
        False,
    ),
    FieldSpec("related_party_clause", "Related Party Clause", "text", ("related party clause", "related party", "关联交易"), False),
    FieldSpec(
        "variable_consideration_clause",
        "Variable Consideration Clause",
        "text",
        ("variable consideration clause", "variable consideration", "可变对价"),
        False,
    ),
    FieldSpec("attachment_list", "Attachment List", "text", ("attachment list", "attachments", "附件清单"), False),
    FieldSpec("signature_detected", "Signature Detected", "status", ("signature detected", "signature", "签字"), False),
    FieldSpec("seal_detected", "Seal Detected", "status", ("seal detected", "seal", "盖章", "公章"), False),
)

CONTRACT_REVIEW_SCHEMA_SPECS: dict[str, tuple[FieldSpec, ...]] = {
    "contract_review": CONTRACT_REVIEW_COMMON_SPECS,
    "material_contract": CONTRACT_REVIEW_COMMON_SPECS,
    "framework_agreement": CONTRACT_REVIEW_COMMON_SPECS,
    "supplemental_agreement": (
        FieldSpec("contract_no", "Contract No", "text", ("contract no", "contract_no", "合同编号")),
        FieldSpec("contract_name", "Contract Name", "text", ("contract name", "contract_name", "合同名称"), False),
        FieldSpec("signing_date", "Signing Date", "date", ("signing date", "signed date", "签署日期", "签订日期"), False),
        FieldSpec("effective_date", "Effective Date", "date", ("effective date", "生效日期"), False),
        FieldSpec("expiry_date", "Expiry Date", "date", ("expiry date", "expiration date", "到期日期", "失效日期"), False),
        FieldSpec("party_a", "Party A", "name", ("party a", "甲方"), False),
        FieldSpec("party_b", "Party B", "name", ("party b", "乙方"), False),
        FieldSpec("counterparty_name", "Counterparty Name", "name", ("counterparty name", "counterparty", "交易对手"), False),
        FieldSpec(
            "amount_including_tax",
            "Amount Including Tax",
            "money",
            ("amount including tax", "total with tax", "contract amount", "含税金额", "合同金额"),
            False,
        ),
        FieldSpec(
            "price_adjustment_clause",
            "Price Adjustment Clause",
            "text",
            ("price adjustment clause", "price adjustment", "价格调整"),
            False,
        ),
        FieldSpec("related_party_clause", "Related Party Clause", "text", ("related party clause", "related party", "关联交易"), False),
        FieldSpec(
            "minimum_guarantee_clause",
            "Minimum Guarantee Clause",
            "text",
            ("minimum guarantee clause", "minimum guarantee", "guaranteed minimum", "保底"),
            False,
        ),
        FieldSpec(
            "variable_consideration_clause",
            "Variable Consideration Clause",
            "text",
            ("variable consideration clause", "variable consideration", "可变对价"),
            False,
        ),
        FieldSpec("attachment_list", "Attachment List", "text", ("attachment list", "attachments", "附件清单"), False),
    ),
    "contract_attachment": (
        FieldSpec("contract_no", "Contract No", "text", ("contract no", "contract_no", "合同编号")),
        FieldSpec("attachment_list", "Attachment List", "text", ("attachment list", "attachments", "附件清单"), False),
    ),
}


def schema_specs_for(scenario: str, doc_type: str) -> tuple[FieldSpec, ...]:
    specs = {
        "sales": SALES_SCHEMA_SPECS,
        "confirmation": CONFIRMATION_SCHEMA_SPECS,
        "interview": INTERVIEW_SCHEMA_SPECS,
        "contract_review": CONTRACT_REVIEW_SCHEMA_SPECS,
    }.get(scenario, SCHEMA_SPECS)
    return specs.get(doc_type, ())


def extract_document(db: Session, document_id: UUID) -> list[ExtractedField]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not document.doc_type or document.doc_type == "unknown":
        raise HTTPException(status_code=400, detail="Document must be classified before extraction")
    if document.ocr_status != "completed":
        raise HTTPException(status_code=400, detail="Document OCR must complete before extraction")
    scenario = document.task.scenario if document.task else "procurement"
    specs = schema_specs_for(scenario, document.doc_type)
    if not specs:
        raise HTTPException(status_code=400, detail="Document type is not supported for extraction")

    pages = _list_pages(db, document_id)
    if not pages:
        raise HTTPException(status_code=400, detail="Document pages are required before extraction")

    values, extraction_method, provider_meta = _extract_values(document, scenario, specs, pages)
    model_invocation_service.add_invocation(
        db,
        task_id=document.task_id,
        document_id=document.id,
        provider=str(provider_meta.get("provider_name") or provider_meta.get("provider") or "unknown"),
        model_name=str(provider_meta.get("provider_name") or provider_meta.get("provider") or "unknown"),
        invocation_type="extraction",
        output_schema=document.doc_type,
        status="degraded" if provider_meta.get("fallback_used") else "completed",
        input_text="\n".join(page.raw_text for page in pages),
        error={"message": str(provider_meta.get("error"))} if provider_meta.get("error") else None,
    )
    try:
        validate_document_extraction(cast(DocumentDocType, document.doc_type), values, scenario)
    except ValidationError as exc:
        document.extraction_status = "failed"
        audit_log_service.add_log(
            db,
            actor_name=document.uploaded_by_name,
            task_id=document.task_id,
            action="document_extraction_failed",
            target_type="document",
            target_id=document.id,
            after_value={"error": exc.__class__.__name__, "extraction_status": document.extraction_status},
        )
        db.commit()
        raise HTTPException(status_code=500, detail="Extraction schema validation failed") from exc

    db.query(ExtractedField).filter(ExtractedField.document_id == document_id).delete()
    for spec, value in zip(specs, values, strict=True):
        db.add(_to_model(document, spec, value, extraction_method))
    document.extraction_status = "completed"
    document.metadata_json = {
        **(document.metadata_json or {}),
        "extraction_provider": provider_meta,
    }
    audit_log_service.add_log(
        db,
        actor_name=document.uploaded_by_name,
        task_id=document.task_id,
        action="document_extracted",
        target_type="document",
        target_id=document.id,
        after_value={
            "field_count": len(values),
            "extraction_status": document.extraction_status,
            "extraction_method": extraction_method,
        },
    )
    db.commit()
    return list_document_fields(db, document_id)


def list_document_fields(db: Session, document_id: UUID) -> list[ExtractedField]:
    return list(
        db.scalars(
            select(ExtractedField)
            .where(ExtractedField.document_id == document_id)
            .order_by(ExtractedField.created_at.asc(), ExtractedField.field_name.asc())
        )
    )


def list_task_fields(db: Session, task_id: UUID) -> list[ExtractedField]:
    return list(
        db.scalars(
            select(ExtractedField)
            .where(ExtractedField.task_id == task_id)
            .order_by(ExtractedField.created_at.asc(), ExtractedField.field_name.asc())
        )
    )


def parse_llm_json_output(raw_output: str) -> dict:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ExtractionProviderError("Invalid extraction provider JSON") from exc
    if not isinstance(parsed, dict):
        raise ExtractionProviderError("Extraction provider JSON must be an object")
    return parsed


def _extract_values(
    document: Document,
    scenario: str,
    specs: tuple[FieldSpec, ...],
    pages: list[DocumentPage],
) -> tuple[list[ExtractedFieldValue], str, dict]:
    provider = llm_provider.get_llm_provider()
    payload_schema = [
        {
            "field_name": spec.field_name,
            "field_label": spec.field_label,
            "field_type": spec.field_type,
            "accepted_field_names": _accepted_field_names(spec.field_name),
            "aliases": list(spec.aliases),
            "is_required": spec.is_required,
        }
        for spec in specs
    ]
    provider_result = provider.extract_fields(
        doc_type=document.doc_type or "unknown",
        scenario=scenario,
        fields_schema=payload_schema,
        text="\n".join(f"Page {page.page_number}:\n{page.raw_text}" for page in pages),
    )
    provider_meta = llm_provider.provider_info(provider_result)
    if provider_result.status == "ok":
        try:
            return _values_from_llm_payload(provider_result.payload, specs, pages), f"llm:{provider_result.provider_name}", provider_meta
        except (ExtractionProviderError, ValidationError, ValueError, TypeError) as exc:
            provider_meta["fallback_used"] = "regex"
            provider_meta["fallback_reason"] = str(exc)
    else:
        provider_meta["fallback_used"] = "regex"
    return [_extract_field(spec, pages) for spec in specs], "regex_fallback", provider_meta


def _values_from_llm_payload(
    payload: dict | None,
    specs: tuple[FieldSpec, ...],
    pages: list[DocumentPage],
) -> list[ExtractedFieldValue]:
    if not isinstance(payload, dict):
        raise ExtractionProviderError("Extraction provider payload is missing")
    raw_fields = payload.get("fields")
    if isinstance(raw_fields, dict):
        items = [dict(value, field_name=key) if isinstance(value, dict) else {"field_name": key} for key, value in raw_fields.items()]
    elif isinstance(raw_fields, list):
        items = [item for item in raw_fields if isinstance(item, dict)]
    else:
        raise ExtractionProviderError("Extraction provider fields must be a list or object")
    fields_by_name = {_canonical_field_name(str(item.get("field_name"))): item for item in items if item.get("field_name")}
    values = []
    for spec in specs:
        item = fields_by_name.get(spec.field_name)
        values.append(_llm_field_value(spec, item, pages) if item else _missing_value(spec))
    return values


def _accepted_field_names(field_name: str) -> list[str]:
    aliases = [alias for alias, canonical in FIELD_NAME_ALIASES.items() if canonical == field_name]
    return [field_name, *aliases]


def _canonical_field_name(field_name: str) -> str:
    return FIELD_NAME_ALIASES.get(field_name, field_name)


def _llm_field_value(
    spec: FieldSpec,
    item: dict,
    pages: list[DocumentPage],
) -> ExtractedFieldValue:
    value_text = item.get("value_text")
    value_text = str(value_text).strip() if value_text is not None and str(value_text).strip() else None
    value_normalized = item.get("value_normalized") if isinstance(item.get("value_normalized"), dict) else None
    warnings = [str(warning) for warning in item.get("warnings") or [] if isinstance(warning, str)]
    if value_text and value_normalized is None and spec.field_type != "line_items":
        value_normalized, _, normalization_warnings = _normalize_value(spec.field_type, value_text)
        warnings.extend(normalization_warnings)
    try:
        confidence = float(item["confidence"]) if "confidence" in item and item["confidence"] is not None else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if "confidence" not in item or item.get("confidence") is None:
        warnings.append("llm_confidence_missing")
    source_page = _int_or_none(item.get("source_page"))
    source_text = str(item.get("source_text")).strip() if item.get("source_text") else None
    source_bbox = item.get("source_bbox") if _is_bbox(item.get("source_bbox")) else None
    if source_text and source_bbox is None and source_page:
        page = next((candidate for candidate in pages if candidate.page_number == source_page), None)
        source_bbox = _bbox_for_text(page, source_text) if page is not None else None
    if source_text and source_bbox is None:
        warnings.append("source_bbox_unavailable")
    if value_text is None:
        missing = _missing_value(spec)
        return missing.model_copy(update={"warnings": sorted(set(missing.warnings + warnings + ["llm_empty_value"]))})
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type=spec.field_type,
        value_text=value_text,
        value_normalized=value_normalized,
        confidence=confidence,
        source_page=source_page,
        source_text=source_text,
        source_bbox=source_bbox,
        warnings=sorted(set(warnings)),
    )


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _list_pages(db: Session, document_id: UUID) -> list[DocumentPage]:
    return list(
        db.scalars(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_number.asc())
        )
    )


def _extract_field(spec: FieldSpec, pages: list[DocumentPage]) -> ExtractedFieldValue:
    if spec.field_type == "line_items":
        return _extract_line_items(spec, pages)

    match = _find_labeled_value(pages, spec.aliases)
    if match is None:
        return _missing_value(spec)

    value_text, page_number, source_text, source_bbox = match
    value_normalized, confidence, warnings = _normalize_value(spec.field_type, value_text)
    if source_bbox is None:
        warnings.append("source_bbox_unavailable")
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type=spec.field_type,
        value_text=value_text,
        value_normalized=value_normalized,
        confidence=confidence,
        source_page=page_number,
        source_text=source_text,
        source_bbox=source_bbox,
        warnings=warnings,
    )


def _extract_line_items(spec: FieldSpec, pages: list[DocumentPage]) -> ExtractedFieldValue:
    source_lines: list[tuple[int, str, list[float] | None]] = []
    items: list[dict] = []
    for page in pages:
        for line in page.raw_text.splitlines():
            if re.search(r"(line item|item|明细)\s*[:：]", line, re.IGNORECASE):
                source_text = line.strip()
                source_bbox = _bbox_for_text(page, source_text)
                source_lines.append((page.page_number, source_text, source_bbox))
                items.append(
                    {
                        "item_name": _text_part(line, ("line item", "item", "item name", "品名")),
                        "quantity": _number_part(line, ("quantity", "qty", "数量")),
                        "unit": _text_part(line, ("unit", "单位")),
                        "unit_price": _number_part(line, ("unit price", "price", "单价")),
                        "amount": _number_part(line, ("amount", "金额")),
                        "source_page": page.page_number,
                        "source_bbox": source_bbox,
                        "source_text": source_text,
                    }
                )

    if not items:
        return _missing_value(spec)

    source_page, source_text, source_bbox = source_lines[0]
    warnings = [] if source_bbox is not None else ["source_bbox_unavailable"]
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type="line_items",
        value_text="\n".join(line for _, line, _ in source_lines),
        value_normalized={"items": items},
        confidence=0.75,
        source_page=source_page,
        source_text=source_text,
        source_bbox=source_bbox,
        warnings=warnings,
    )


def _find_labeled_value(
    pages: list[DocumentPage], aliases: tuple[str, ...]
) -> tuple[str, int, str, list[float] | None] | None:
    for page in pages:
        for raw_line in page.raw_text.splitlines():
            line = raw_line.strip()
            for alias in aliases:
                match = re.search(rf"{re.escape(alias)}\s*[:：]\s*(.+)", line, re.IGNORECASE)
                if match:
                    return match.group(1).strip(), page.page_number, line, _bbox_for_text(page, line)
    return None


def _bbox_for_text(page: DocumentPage, source_text: str) -> list[float] | None:
    needle = _compact_text(source_text)
    if not needle:
        return None
    for block in page.ocr_blocks or []:
        block_text = _compact_text(str(block.get("text") or ""))
        bbox = block.get("bbox")
        if needle in block_text and _is_bbox(bbox):
            return [float(value) for value in bbox]
    return None


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _is_bbox(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 4:
        return False
    return all(isinstance(item, (int, float)) for item in value)


def _normalize_value(field_type: FieldType, value_text: str) -> tuple[dict | None, float, list[str]]:
    if field_type == "date":
        normalized = _normalize_date(value_text)
        return ({"value": normalized}, 0.85, []) if normalized else (None, 0.3, ["invalid_date"])
    if field_type == "money":
        amount, currency = _normalize_amount(value_text)
        if amount is None:
            return None, 0.3, ["invalid_amount"]
        value = {"amount": amount}
        if currency:
            value["currency"] = currency
        return value, 0.85, []
    if field_type == "tax_rate":
        rate = _normalize_tax_rate(value_text)
        return ({"rate": rate}, 0.85, []) if rate is not None else (None, 0.3, ["invalid_tax_rate"])
    if field_type == "currency":
        currency = _normalize_currency(value_text)
        return ({"value": currency}, 0.85, []) if currency else (None, 0.3, ["invalid_currency"])
    return {"value": value_text.strip()}, 0.8, []


def _missing_value(spec: FieldSpec) -> ExtractedFieldValue:
    warning = "required_field_missing" if spec.is_required else "optional_field_missing"
    return ExtractedFieldValue(
        field_name=spec.field_name,
        field_label=spec.field_label,
        field_type=spec.field_type,
        value_text=None,
        value_normalized=None,
        confidence=0.0,
        source_page=None,
        source_text=None,
        source_bbox=None,
        warnings=[warning],
    )


def _to_model(document: Document, spec: FieldSpec, value: ExtractedFieldValue, extraction_method: str) -> ExtractedField:
    return ExtractedField(
        task_id=document.task_id,
        document_id=document.id,
        field_name=value.field_name,
        field_label=value.field_label,
        field_type=value.field_type,
        value_text=value.value_text,
        value_normalized=value.value_normalized,
        original_value_text=value.value_text,
        original_value_normalized=value.value_normalized,
        original_confidence=value.confidence,
        unit=_field_unit(value),
        currency=_field_currency(value),
        confidence=value.confidence,
        source_page=value.source_page,
        source_bbox=value.source_bbox,
        source_text=value.source_text,
        extraction_method=extraction_method,
        is_required=spec.is_required,
        is_verified=False,
        corrected_by=None,
        corrected_at=None,
        warnings=value.warnings,
    )


def _normalize_date(value: str) -> str | None:
    match = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", value)
    if not match:
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
        if not match:
            return None
        month, day, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    else:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _normalize_amount(value: str) -> tuple[float | None, str | None]:
    match = re.search(r"(?P<currency>CNY|USD|RMB|¥)?\s*(?P<amount>-?\d[\d,]*(?:\.\d+)?)", value, re.IGNORECASE)
    if not match:
        return None, None
    amount = float(match.group("amount").replace(",", ""))
    return amount, _normalize_currency(match.group("currency") or value)


def _normalize_tax_rate(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    return round(float(match.group(1)) / 100, 6) if match else None


def _normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper()
    if "USD" in upper:
        return "USD"
    if "CNY" in upper or "RMB" in upper or "¥" in value or "人民币" in value:
        return "CNY"
    return None


def _text_part(line: str, labels: tuple[str, ...]) -> str | None:
    for label in labels:
        match = re.search(rf"{re.escape(label)}\s*[:=]\s*([^;,\n]+)", line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _number_part(line: str, labels: tuple[str, ...]) -> float | None:
    text = _text_part(line, labels)
    if text is None:
        return None
    amount, _ = _normalize_amount(text)
    return amount


def _field_unit(value: ExtractedFieldValue) -> str | None:
    if value.field_type == "line_items":
        return None
    return None


def _field_currency(value: ExtractedFieldValue) -> str | None:
    if not value.value_normalized:
        return None
    if value.field_type == "money":
        return cast(str | None, value.value_normalized.get("currency"))
    if value.field_type == "currency":
        return cast(str | None, value.value_normalized.get("value"))
    return None
