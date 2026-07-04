export type TaskStatus = "draft" | "uploaded" | "failed";

export type ProcurementDocType =
  | "purchase_request"
  | "purchase_contract"
  | "warehouse_receipt"
  | "invoice"
  | "accounting_voucher"
  | "payment_receipt";

export type ClassificationDocType = ProcurementDocType | "unknown";

export type AlternativeDocType = {
  doc_type: ClassificationDocType;
  confidence: number;
  reason: string;
};

export type ClassificationResult = {
  document_id: string;
  doc_type: ClassificationDocType;
  confidence: number;
  classification_reason: string;
  alternative_types: AlternativeDocType[];
  need_human_review: boolean;
};

export type FieldType = "text" | "date" | "money" | "tax_rate" | "name" | "status" | "line_items" | "currency";

export type ExtractedField = {
  id: string;
  task_id: string;
  document_id: string;
  field_name: string;
  field_label: string;
  field_type: FieldType;
  value_text: string | null;
  value_normalized: Record<string, unknown> | null;
  unit: string | null;
  currency: string | null;
  confidence: number | null;
  source_page: number | null;
  source_bbox: number[] | null;
  source_text: string | null;
  extraction_method: string;
  is_required: boolean;
  is_verified: boolean;
  corrected_by: string | null;
  corrected_at: string | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
};

export type AuditTask = {
  id: string;
  task_no: string;
  name: string;
  scenario: "procurement";
  project_name: string | null;
  company_name: string | null;
  fiscal_year: number | null;
  period_start: string | null;
  period_end: string | null;
  status: TaskStatus;
  actor_name: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentRecord = {
  id: string;
  task_id: string;
  uploaded_by_name: string | null;
  original_filename: string;
  file_ext: string;
  content_type: string | null;
  file_size: number;
  file_hash: string;
  storage_path: string;
  doc_type: ClassificationDocType | null;
  business_key: string | null;
  doc_type_confidence: number | null;
  classification_reason: string | null;
  alternative_types: AlternativeDocType[] | null;
  original_classification: Record<string, unknown> | null;
  page_count: number | null;
  upload_status: string;
  ocr_status: string;
  ocr_error: string | null;
  extraction_status: string;
  review_status: string;
  created_at: string;
  updated_at: string;
};

export type DocumentRelation = {
  id: string;
  task_id: string;
  business_key: string;
  source_document_id: string;
  target_document_id: string;
  relation_type: string;
  confidence: number;
  evidence: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type LinkDocumentsResult = {
  task_id: string;
  linked_document_count: number;
  relation_count: number;
  warnings: string[];
  relations: DocumentRelation[];
};

export type AuditRule = {
  id: string;
  rule_code: string;
  name: string;
  version: string;
  enabled: boolean;
  parameters: Record<string, unknown>;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditResult = {
  id: string;
  task_id: string;
  rule_id: string | null;
  rule_code: string;
  business_key: string;
  status: string;
  severity: string;
  message: string;
  expected_value: Record<string, unknown> | null;
  actual_value: Record<string, unknown> | null;
  evidence: Record<string, unknown>;
  rag_citations: Record<string, unknown>[] | null;
  review_status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentUpdatePayload = {
  doc_type: ClassificationDocType;
  actor_name?: string;
  manual_reason?: string;
};

export type CreateTaskPayload = {
  name: string;
  scenario: "procurement";
  project_name?: string;
  company_name?: string;
  fiscal_year?: number;
  actor_name?: string;
};

export type PageBlock = {
  text: string;
  bbox: number[] | null;
  confidence: number | null;
};

export type DocumentPage = {
  id: string;
  document_id: string;
  page_number: number;
  raw_text: string;
  ocr_blocks: PageBlock[];
  table_blocks: Record<string, unknown>[];
  width: number | null;
  height: number | null;
  ocr_engine: string;
  ocr_confidence: number | null;
  warnings: string[];
  created_at: string;
  updated_at: string;
};

export type ReviewQueueItem = {
  item_type: "field" | "audit_result";
  task_id: string;
  document_id: string | null;
  field_id: string | null;
  audit_result_id: string | null;
  reason: string;
  field: ExtractedField | null;
  audit_result: AuditResult | null;
};

export type ReviewComment = {
  id: string;
  task_id: string;
  document_id: string | null;
  audit_result_id: string | null;
  field_id: string | null;
  author_name: string | null;
  comment_type: string;
  content: string;
  before_value: Record<string, unknown> | null;
  after_value: Record<string, unknown> | null;
  created_at: string;
};

export type FieldCorrectionPayload = {
  value_text?: string | null;
  value_normalized?: Record<string, unknown> | null;
  confidence?: number | null;
  actor_name?: string;
  comment?: string;
};

export type ReviewActionPayload = {
  actor_name?: string;
  reason?: string;
};

export type DismissReviewPayload = {
  actor_name?: string;
  reason: string;
};

export type ReviewCommentPayload = {
  task_id: string;
  document_id?: string | null;
  audit_result_id?: string | null;
  field_id?: string | null;
  author_name?: string | null;
  comment_type: string;
  content: string;
  before_value?: Record<string, unknown> | null;
  after_value?: Record<string, unknown> | null;
};
