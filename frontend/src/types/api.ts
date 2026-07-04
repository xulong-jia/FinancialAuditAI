export type TaskStatus = "draft" | "uploaded" | "failed";

export type ProcurementDocType =
  | "purchase_request"
  | "purchase_contract"
  | "warehouse_receipt"
  | "invoice"
  | "accounting_voucher"
  | "payment_receipt";

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
  doc_type: ProcurementDocType | null;
  upload_status: string;
  ocr_status: string;
  extraction_status: string;
  review_status: string;
  created_at: string;
  updated_at: string;
};

export type CreateTaskPayload = {
  name: string;
  scenario: "procurement";
  project_name?: string;
  company_name?: string;
  fiscal_year?: number;
  actor_name?: string;
};
