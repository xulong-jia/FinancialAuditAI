export type TaskStatus = "draft" | "uploaded" | "failed";

export type ProcurementDocType =
  | "purchase_request"
  | "purchase_contract"
  | "warehouse_receipt"
  | "invoice"
  | "accounting_voucher"
  | "payment_receipt";

export type SalesDocType =
  | "sales_contract"
  | "sales_order"
  | "delivery_order"
  | "logistics_receipt"
  | "sales_invoice"
  | "receipt_voucher"
  | "accounting_voucher";

export type DocumentDocType = ProcurementDocType | SalesDocType;
export type ClassificationDocType = DocumentDocType | "unknown";

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
  scenario: "procurement" | "sales";
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
  category: string;
  severity: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditRuleCreatePayload = {
  rule_code: string;
  name: string;
  version?: string;
  enabled?: boolean;
  parameters?: Record<string, unknown>;
  description?: string | null;
  actor_name?: string;
};

export type AuditRuleUpdatePayload = {
  name?: string;
  version?: string;
  enabled?: boolean;
  parameters?: Record<string, unknown>;
  description?: string | null;
  actor_name?: string;
};

export type AuditRuleEvaluatePayload = {
  task_id: string;
  parameters?: Record<string, unknown>;
};

export type AuditRuleEvaluateResult = {
  rule_code: string;
  rule_version: string;
  business_key: string;
  status: string;
  severity: string;
  message: string;
  expected_value: Record<string, unknown> | null;
  actual_value: Record<string, unknown> | null;
  evidence: Record<string, unknown>;
};

export type AgentRun = {
  id: string;
  task_id: string;
  workflow_name: string;
  status: string;
  current_state: string;
  input_refs: Record<string, unknown>;
  output_refs: Record<string, unknown>;
  error: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentStep = {
  id: string;
  run_id: string;
  step_name: string;
  step_order: number;
  tool_name: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  error: Record<string, unknown> | null;
  duration_ms: number | null;
  created_at: string;
};

export type AgentRunCreatePayload = {
  task_id: string;
  workflow_name?: string;
  input_refs?: Record<string, unknown>;
};

export type EvalType =
  | "classification"
  | "ocr"
  | "extraction"
  | "rule"
  | "rag"
  | "agent"
  | "end_to_end"
  | "regression";

export type BadCase = {
  id: string;
  task_id: string | null;
  document_id: string | null;
  case_type: EvalType;
  title: string;
  input_payload: Record<string, unknown>;
  model_output: Record<string, unknown>;
  expected_output: Record<string, unknown>;
  root_cause: string | null;
  fix_plan: string | null;
  status: string;
  severity: string;
  owner_name: string | null;
  created_at: string;
  updated_at: string;
};

export type BadCaseCreatePayload = {
  case_type: EvalType;
  title: string;
  input_payload?: Record<string, unknown>;
  model_output?: Record<string, unknown>;
  expected_output?: Record<string, unknown>;
  root_cause?: string | null;
  fix_plan?: string | null;
  status?: string;
  severity?: string;
  owner_name?: string | null;
};

export type BadCaseUpdatePayload = Partial<Omit<BadCaseCreatePayload, "case_type">>;

export type EvaluationRunPayload = {
  eval_type: EvalType;
  eval_name?: string;
  dataset_name?: string;
  model_name?: string | null;
  prompt_version?: string | null;
  rule_version?: string | null;
  created_by?: string | null;
};

export type EvaluationResult = {
  id: string;
  eval_name: string;
  eval_type: EvalType;
  dataset_name: string;
  model_name: string | null;
  prompt_version: string | null;
  rule_version: string | null;
  metrics: Record<string, unknown>;
  sample_count: number;
  failed_cases: Record<string, unknown>[];
  report_path: string | null;
  created_by: string | null;
  created_at: string;
};

export type AuditResult = {
  id: string;
  task_id: string;
  rule_id: string | null;
  rule_code: string;
  rule_version: string | null;
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
  scenario: "procurement" | "sales";
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

export type ReportRecord = {
  id: string;
  task_id: string;
  report_type: string;
  title: string;
  status: string;
  file_format: string;
  storage_path: string;
  summary: Record<string, unknown>;
  generated_by: string | null;
  generated_at: string;
  created_at: string;
  updated_at: string;
};

export type ReportGeneratePayload = {
  generated_by?: string;
};

export type KnowledgeBase = "regulation" | "inquiry_case" | "prospectus" | "workpaper";

export type RagDocument = {
  id: string;
  knowledge_base: KnowledgeBase;
  title: string;
  source_type: string;
  source_url: string | null;
  issuer_name: string | null;
  publish_date: string | null;
  effective_date: string | null;
  file_path: string | null;
  checksum: string;
  metadata: Record<string, unknown>;
  created_by: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
};

export type RagIndexResult = {
  document_id: string;
  knowledge_base: KnowledgeBase;
  chunk_count: number;
};

export type RagCitation = {
  chunk_id: string;
  document_id: string;
  knowledge_base: KnowledgeBase;
  title: string;
  section: string | null;
  page: number | null;
  score: number;
  quote: string;
  metadata: Record<string, unknown>;
};

export type RagQueryResponse = {
  status: "answer" | "no_answer";
  answer: string;
  citations: RagCitation[];
  limitations: string[];
};

export type RagQueryPayload = {
  query: string;
  knowledge_base: KnowledgeBase;
  top_k: number;
  metadata_filter: Record<string, unknown>;
};
