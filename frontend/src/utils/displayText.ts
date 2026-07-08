export function displayStatus(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return STATUS_TEXT[value] ?? value;
}

export function displayScenario(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return SCENARIO_TEXT[value] ?? value;
}

export function displayDocType(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return DOC_TYPE_TEXT[value] ?? value;
}

export function displayRole(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return ROLE_TEXT[value] ?? value;
}

export function displaySeverity(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return SEVERITY_TEXT[value] ?? value;
}

export function displayKnowledgeBase(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return KNOWLEDGE_BASE_TEXT[value] ?? value;
}

export function displayBadCaseType(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return BAD_CASE_TYPE_TEXT[value] ?? value;
}

export function displayEvalType(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return EVAL_TYPE_TEXT[value] ?? value;
}

export function displayReviewItemType(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return REVIEW_ITEM_TYPE_TEXT[value] ?? value;
}

export function displayFieldType(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return FIELD_TYPE_TEXT[value] ?? value;
}

export function displayReportColumn(value: string): string {
  return REPORT_COLUMN_TEXT[value] ?? value;
}

export function displayBoolean(value: boolean): string {
  return value ? "是" : "否";
}

const STATUS_TEXT: Record<string, string> = {
  active: "启用",
  disabled: "停用",
  answer: "已回答",
  no_answer: "无答案",
  draft: "草稿",
  uploaded: "已上传",
  pending: "待处理",
  running: "处理中",
  completed: "已完成",
  failed: "失败",
  reviewing: "复核中",
  waiting_review: "等待复核",
  pending_review: "待复核",
  confirmed: "已确认",
  dismissed: "已驳回",
  not_required: "无需处理",
  fixed: "已修复",
  open: "未关闭",
  ignored: "已忽略",
  ocr_running: "OCR 处理中",
  ocr_completed: "OCR 已完成",
  classified: "已分类",
  extracting: "抽取中",
  extracted: "已抽取",
  auditing: "审核中",
  pass: "通过",
  warning: "警告",
  fail: "未通过",
  need_review: "待复核",
  evidence_insufficient: "证据不足",
  not_applicable: "不适用",
  HUMAN_REVIEW_REQUIRED: "需要人工复核",
  AUTO_PASS: "自动通过",
  REPORT_READY: "报告就绪",
  COMPLETED: "已完成",
  RUNNING: "处理中",
  FAILED: "失败",
  OCR_COMPLETED: "OCR 已完成",
  OCR_FAILED: "OCR 失败",
  CLASSIFY_COMPLETED: "分类已完成",
  CLASSIFY_FAILED: "分类失败",
  EXTRACT_COMPLETED: "抽取已完成",
  EXTRACT_FAILED: "抽取失败",
  AUDIT_COMPLETED: "审核已完成",
  AUDIT_FAILED: "审核失败",
  completed_after_human_review: "人工复核后已完成",
};

const SCENARIO_TEXT: Record<string, string> = {
  procurement: "采购穿行",
  sales: "销售穿行",
  confirmation: "函证",
  interview: "访谈",
  contract_review: "合同审核",
};

const DOC_TYPE_TEXT: Record<string, string> = {
  purchase_request: "采购申请单",
  purchase_contract: "采购合同",
  warehouse_receipt: "入库单",
  invoice: "发票",
  accounting_voucher: "记账凭证",
  payment_receipt: "付款回单",
  sales_contract: "销售合同",
  sales_order: "销售订单",
  delivery_order: "出库单",
  logistics_receipt: "物流 / 签收单",
  sales_invoice: "销售发票",
  receipt_voucher: "收款凭证",
  confirmation: "函证",
  confirmation_request: "函证发函",
  confirmation_reply: "函证回函",
  confirmation_adjustment: "函证差异调节",
  interview_record: "访谈记录",
  interview_outline: "访谈提纲",
  interview_signature_page: "访谈签字页",
  interview_transcript: "访谈转写文本",
  contract_review: "合同审核文档",
  material_contract: "重大合同",
  supplemental_agreement: "补充协议",
  framework_agreement: "框架协议",
  contract_attachment: "合同附件",
  prospectus: "招股说明书 / 募集说明书",
  inquiry_letter: "问询函",
  regulation: "法规 / 准则",
  unknown: "未知 / 需要复核",
};

const ROLE_TEXT: Record<string, string> = {
  admin: "管理员",
  analyst: "分析员",
  reviewer: "复核员",
  manager: "经理",
  viewer: "只读用户",
};

const SEVERITY_TEXT: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

const KNOWLEDGE_BASE_TEXT: Record<string, string> = {
  regulation: "法规库",
  inquiry_case: "问询案例库",
  prospectus: "招股书 / 公开披露库",
  workpaper: "底稿库",
};

const BAD_CASE_TYPE_TEXT: Record<string, string> = {
  classification: "分类",
  ocr: "OCR",
  extraction: "字段抽取",
  rule: "规则审核",
  rag: "RAG",
  agent: "Agent",
  review_dispute: "复核争议",
  end_to_end: "端到端",
  regression: "回归",
};

const EVAL_TYPE_TEXT: Record<string, string> = {
  classification: "分类",
  ocr: "OCR",
  extraction: "字段抽取",
  rule: "规则",
  rag: "RAG",
  agent: "Agent",
  persistent_rag_workflow: "持久化 RAG 工作流",
  agent_db_workflow: "Agent DB 工作流",
  end_to_end: "端到端",
  full_db_workflow: "完整 DB 工作流",
  regression: "回归",
};

const REVIEW_ITEM_TYPE_TEXT: Record<string, string> = {
  document: "文档",
  field: "字段",
  audit_result: "审核结果",
  agent_step: "Agent 步骤",
  comment: "复核意见",
};

const FIELD_TYPE_TEXT: Record<string, string> = {
  text: "文本",
  date: "日期",
  money: "金额",
  tax_rate: "税率",
  name: "名称",
  status: "状态",
  line_items: "明细行",
  currency: "币种",
};

const REPORT_COLUMN_TEXT: Record<string, string> = {
  business_key: "业务键",
  supplier_name: "供应商",
  customer_name: "客户",
  counterparty_name: "交易对手",
  contract_no: "合同号",
  contract_name: "合同名称",
  order_no: "订单号",
  delivery_no: "出库 / 发货号",
  invoice_no: "发票号",
  receipt_no: "收款凭证号",
  confirmation_no: "函证编号",
  sent_date: "发函日期",
  replied_date: "回函日期",
  interviewee_name: "访谈对象",
  interview_date: "访谈日期",
  topics: "主题",
  key_answers: "关键回答",
  mentioned_amounts: "提及金额",
  mentioned_counterparties: "提及交易对手",
  contract_amount: "合同金额",
  invoice_amount: "发票金额",
  payment_amount: "付款金额",
  receipt_amount: "收款金额",
  book_amount: "账面金额",
  confirmed_amount: "确认金额",
  difference_amount: "差异金额",
  amount_including_tax: "含税金额",
  payment_terms: "付款条款",
  delivery_terms: "交付条款",
  special_clauses: "特殊条款",
  exception_reason: "异常原因",
  amount_check: "金额检查",
  revenue_check: "收入检查",
  signature_check: "签字检查",
  special_clause_check: "特殊条款检查",
  signature_seal_check: "签章检查",
  key_terms_check: "关键条款检查",
  overall_status: "整体状态",
  reviewer_comment: "复核意见",
};
