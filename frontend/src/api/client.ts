const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

import type {
  AgentRun,
  AgentRunCreatePayload,
  AgentStep,
  AuditLogRecord,
  BadCase,
  BadCaseCreatePayload,
  BadCaseUpdatePayload,
  AuditTask,
  AuditResult,
  AuditRule,
  AuditRuleCreatePayload,
  AuditRuleEvaluatePayload,
  AuditRuleEvaluateResult,
  AuditRuleUpdatePayload,
  ClassificationResult,
  CreateTaskPayload,
  DocumentPage,
  DocumentDocType,
  DocumentRecord,
  DocumentUpdatePayload,
  DocumentRelation,
  ExtractedField,
  DismissReviewPayload,
  EvalType,
  EvaluationResult,
  EvaluationRunPayload,
  FieldCorrectionPayload,
  LinkDocumentsResult,
  ReviewActionPayload,
  ReviewComment,
  ReviewCommentPayload,
  ReviewQueueItem,
  ReportGeneratePayload,
  ReportRecord,
  KnowledgeBase,
  LoginPayload,
  LoginResponse,
  RagDocument,
  RagIndexResult,
  RagQueryPayload,
  RagQueryResponse,
  RoleCreatePayload,
  RoleRecord,
  RoleUpdatePayload,
  UserCreatePayload,
  UserRecord,
  UserUpdatePayload,
} from "../types/api";

const tokenStorageKey = "financial_audit_ai_access_token";

export function getAccessToken(): string | null {
  return window.localStorage.getItem(tokenStorageKey);
}

export function setAccessToken(token: string) {
  window.localStorage.setItem(tokenStorageKey, token);
}

export function clearAccessToken() {
  window.localStorage.removeItem(tokenStorageKey);
}

function authHeaders(extraHeaders: Record<string, string> = {}) {
  const token = getAccessToken();
  return token ? { ...extraHeaders, Authorization: `Bearer ${token}` } : extraHeaders;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { headers: authHeaders() });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json() as Promise<T>;
}

async function sendJson<T>(path: string, method: string, body: unknown): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response.json() as Promise<T>;
}

export function login(payload: LoginPayload): Promise<LoginResponse> {
  return sendJson<LoginResponse>("/api/v1/auth/login", "POST", payload);
}

export function getCurrentUser(): Promise<UserRecord> {
  return getJson<UserRecord>("/api/v1/auth/me");
}

export function logout(): Promise<{ status: string }> {
  return sendJson<{ status: string }>("/api/v1/auth/logout", "POST", {});
}

export function listUsers(): Promise<UserRecord[]> {
  return getJson<UserRecord[]>("/api/v1/users");
}

export function createUser(payload: UserCreatePayload): Promise<UserRecord> {
  return sendJson<UserRecord>("/api/v1/users", "POST", payload);
}

export function updateUser(userId: string, payload: UserUpdatePayload): Promise<UserRecord> {
  return sendJson<UserRecord>(`/api/v1/users/${userId}`, "PATCH", payload);
}

export function listRoles(): Promise<RoleRecord[]> {
  return getJson<RoleRecord[]>("/api/v1/roles");
}

export function createRole(payload: RoleCreatePayload): Promise<RoleRecord> {
  return sendJson<RoleRecord>("/api/v1/roles", "POST", payload);
}

export function updateRole(roleId: string, payload: RoleUpdatePayload): Promise<RoleRecord> {
  return sendJson<RoleRecord>(`/api/v1/roles/${roleId}`, "PATCH", payload);
}

export function listAuditLogs(): Promise<AuditLogRecord[]> {
  return getJson<AuditLogRecord[]>("/api/v1/audit-logs");
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

export function createRule(payload: AuditRuleCreatePayload): Promise<AuditRule> {
  return sendJson<AuditRule>("/api/v1/rules", "POST", payload);
}

export function updateRule(ruleId: string, payload: AuditRuleUpdatePayload): Promise<AuditRule> {
  return sendJson<AuditRule>(`/api/v1/rules/${ruleId}`, "PATCH", payload);
}

export function evaluateRule(ruleId: string, payload: AuditRuleEvaluatePayload): Promise<AuditRuleEvaluateResult[]> {
  return sendJson<AuditRuleEvaluateResult[]>(`/api/v1/rules/${ruleId}/evaluate`, "POST", payload);
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

export async function downloadReport(reportId: string, filename: string) {
  const response = await fetch(`${baseUrl}/api/v1/reports/${reportId}/download`, { headers: authHeaders() });
  if (!response.ok) {
    throw new Error("Download failed");
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function uploadDocument(
  taskId: string,
  file: File,
  docTypeHint: DocumentDocType,
): Promise<DocumentRecord> {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type_hint", docTypeHint);

  const response = await fetch(`${baseUrl}/api/v1/tasks/${taskId}/documents`, {
    method: "POST",
    headers: authHeaders(),
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
    headers: authHeaders(),
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

export function createAgentRun(payload: AgentRunCreatePayload): Promise<AgentRun> {
  return sendJson<AgentRun>("/api/v1/agents/runs", "POST", payload);
}

export function getAgentRun(runId: string): Promise<AgentRun> {
  return getJson<AgentRun>(`/api/v1/agents/runs/${runId}`);
}

export function listAgentSteps(runId: string): Promise<AgentStep[]> {
  return getJson<AgentStep[]>(`/api/v1/agents/runs/${runId}/steps`);
}

export function retryAgentRun(runId: string): Promise<AgentRun> {
  return sendJson<AgentRun>(`/api/v1/agents/runs/${runId}/retry`, "POST", {});
}

export function createBadCase(payload: BadCaseCreatePayload): Promise<BadCase> {
  return sendJson<BadCase>("/api/v1/bad-cases", "POST", payload);
}

export function listBadCases(filters: { case_type?: EvalType; status?: string } = {}): Promise<BadCase[]> {
  const params = new URLSearchParams();
  if (filters.case_type) {
    params.set("case_type", filters.case_type);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  return getJson<BadCase[]>(`/api/v1/bad-cases${query}`);
}

export function updateBadCase(caseId: string, payload: BadCaseUpdatePayload): Promise<BadCase> {
  return sendJson<BadCase>(`/api/v1/bad-cases/${caseId}`, "PATCH", payload);
}

export function runEvaluation(payload: EvaluationRunPayload): Promise<EvaluationResult> {
  return sendJson<EvaluationResult>("/api/v1/evaluations/run", "POST", payload);
}

export function listEvaluationResults(evalType?: EvalType): Promise<EvaluationResult[]> {
  const query = evalType ? `?eval_type=${evalType}` : "";
  return getJson<EvaluationResult[]>(`/api/v1/evaluations/results${query}`);
}
