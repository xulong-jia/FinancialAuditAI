const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

import type { AuditTask, CreateTaskPayload, DocumentRecord, ProcurementDocType } from "../types/api";

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
