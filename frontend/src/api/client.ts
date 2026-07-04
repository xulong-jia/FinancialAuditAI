const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

import type {
  AuditTask,
  AuditResult,
  AuditRule,
  ClassificationResult,
  CreateTaskPayload,
  DocumentPage,
  DocumentRecord,
  DocumentUpdatePayload,
  DocumentRelation,
  ExtractedField,
  DismissReviewPayload,
  FieldCorrectionPayload,
  LinkDocumentsResult,
  ProcurementDocType,
  ReviewActionPayload,
  ReviewComment,
  ReviewCommentPayload,
  ReviewQueueItem,
  ReportGeneratePayload,
  ReportRecord,
  KnowledgeBase,
  RagDocument,
  RagIndexResult,
  RagQueryPayload,
  RagQueryResponse,
} from "../types/api";

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`);
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json() as Promise<T>;
}

async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json() as Promise<T>;
}

export function listTasks(): Promise<AuditTask[]> {
  return getJson<AuditTask[]>("/api/v1/tasks");
}

export function createTask(payload: CreateTaskPayload): Promise<AuditTask> {
  return sendJson<AuditTask>("/api/v1/tasks", "POST", payload);
}

export function listDocuments(taskId: string): Promise<DocumentRecord[]> {
  return getJson<DocumentRecord[]>(`/api/v1/tasks/${taskId}/documents`);
}

export function linkDocuments(taskId: string): Promise<LinkDocumentsResult> {
  return sendJson<LinkDocumentsResult>(`/api/v1/tasks/${taskId}/link-documents`, "POST", {});
}

export function listDocumentRelations(taskId: string): Promise<DocumentRelation[]> {
  return getJson<DocumentRelation[]>(`/api/v1/tasks/${taskId}/document-relations`);
}

export function runAudit(taskId: string): Promise<AuditResult[]> {
  return sendJson<AuditResult[]>(`/api/v1/tasks/${taskId}/audit`, "POST", {});
}

export function listAuditResults(taskId: string): Promise<AuditResult[]> {
  return getJson<AuditResult[]>(`/api/v1/tasks/${taskId}/audit-results`);
}

export function listRules(): Promise<AuditRule[]> {
  return getJson<AuditRule[]>("/api/v1/rules");
}

export function runOcr(documentId: string): Promise<DocumentRecord> {
  return sendJson<DocumentRecord>(`/api/v1/documents/${documentId}/ocr`, "POST", {});
}

export function classifyDocument(documentId: string): Promise<ClassificationResult> {
  return sendJson<ClassificationResult>(`/api/v1/documents/${documentId}/classify`, "POST", {});
}

export function updateDocument(documentId: string, payload: DocumentUpdatePayload): Promise<DocumentRecord> {
  return sendJson<DocumentRecord>(`/api/v1/documents/${documentId}`, "PATCH", payload);
}

export function extractDocument(documentId: string): Promise<ExtractedField[]> {
  return sendJson<ExtractedField[]>(`/api/v1/documents/${documentId}/extract`, "POST", {});
}

export function listDocumentFields(documentId: string): Promise<ExtractedField[]> {
  return getJson<ExtractedField[]>(`/api/v1/documents/${documentId}/fields`);
}

export function listTaskFields(taskId: string): Promise<ExtractedField[]> {
  return getJson<ExtractedField[]>(`/api/v1/tasks/${taskId}/fields`);
}

export function listDocumentPages(documentId: string): Promise<DocumentPage[]> {
  return getJson<DocumentPage[]>(`/api/v1/documents/${documentId}/pages`);
}

export function listReviewQueue(taskId?: string): Promise<ReviewQueueItem[]> {
  const query = taskId ? `?task_id=${taskId}` : "";
  return getJson<ReviewQueueItem[]>(`/api/v1/review/queue${query}`);
}

export function listReviewComments(taskId?: string): Promise<ReviewComment[]> {
  const query = taskId ? `?task_id=${taskId}` : "";
  return getJson<ReviewComment[]>(`/api/v1/review/comments${query}`);
}

export function createReviewComment(payload: ReviewCommentPayload): Promise<ReviewComment> {
  return sendJson<ReviewComment>("/api/v1/review/comments", "POST", payload);
}

export function updateField(fieldId: string, payload: FieldCorrectionPayload): Promise<ExtractedField> {
  return sendJson<ExtractedField>(`/api/v1/fields/${fieldId}`, "PATCH", payload);
}

export function confirmAuditResult(resultId: string, payload: ReviewActionPayload): Promise<AuditResult> {
  return sendJson<AuditResult>(`/api/v1/audit-results/${resultId}/confirm`, "POST", payload);
}

export function dismissAuditResult(resultId: string, payload: DismissReviewPayload): Promise<AuditResult> {
  return sendJson<AuditResult>(`/api/v1/audit-results/${resultId}/dismiss`, "POST", payload);
}

export function rerunAuditResult(resultId: string, payload: ReviewActionPayload): Promise<AuditResult[]> {
  return sendJson<AuditResult[]>(`/api/v1/audit-results/${resultId}/rerun`, "POST", payload);
}

export function generateControlTableReport(taskId: string, payload: ReportGeneratePayload): Promise<ReportRecord> {
  return sendJson<ReportRecord>(`/api/v1/tasks/${taskId}/reports/control-table`, "POST", payload);
}

export function listReports(taskId: string): Promise<ReportRecord[]> {
  return getJson<ReportRecord[]>(`/api/v1/tasks/${taskId}/reports`);
}

export function reportDownloadUrl(reportId: string): string {
  return `${baseUrl}/api/v1/reports/${reportId}/download`;
}

export async function uploadDocument(
  taskId: string,
  file: File,
  docTypeHint: ProcurementDocType,
): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type_hint", docTypeHint);

  const response = await fetch(`${baseUrl}/api/v1/tasks/${taskId}/documents`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error("Upload failed");
  }
  return response.json() as Promise<DocumentRecord>;
}

export function listRagDocuments(knowledgeBase?: KnowledgeBase): Promise<RagDocument[]> {
  const query = knowledgeBase ? `?knowledge_base=${knowledgeBase}` : "";
  return getJson<RagDocument[]>(`/api/v1/rag/documents${query}`);
}

export async function createRagDocument(payload: {
  knowledge_base: KnowledgeBase;
  title: string;
  source_type: string;
  metadata_json?: string;
  content_text?: string;
  file?: File;
}): Promise<RagDocument> {
  const form = new FormData();
  form.append("knowledge_base", payload.knowledge_base);
  form.append("title", payload.title);
  form.append("source_type", payload.source_type);
  if (payload.metadata_json) {
    form.append("metadata_json", payload.metadata_json);
  }
  if (payload.content_text) {
    form.append("content_text", payload.content_text);
  }
  if (payload.file) {
    form.append("file", payload.file);
  }
  const response = await fetch(`${baseUrl}/api/v1/rag/documents`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error("RAG document create failed");
  }
  return response.json() as Promise<RagDocument>;
}

export function indexRagDocument(documentId: string): Promise<RagIndexResult> {
  return sendJson<RagIndexResult>(`/api/v1/rag/documents/${documentId}/index`, "POST", {});
}

export function queryRag(payload: RagQueryPayload): Promise<RagQueryResponse> {
  return sendJson<RagQueryResponse>("/api/v1/rag/query", "POST", payload);
}
