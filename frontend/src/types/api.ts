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
