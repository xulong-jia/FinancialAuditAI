import { Alert, Button, Card, Drawer, Empty, List, Select, Space, Spin, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import {
  confirmAuditResult,
  dismissAuditResult,
  listAuditResults,
  listDocumentPages,
  listDocuments,
  listTaskFields,
  listTasks,
  rerunAuditResult,
  updateField,
} from "../api/client";
import type { PageProps } from "../routes";
import type { AuditResult, AuditTask, DocumentPage, DocumentRecord, ExtractedField } from "../types/api";

type EvidenceRef = {
  document_id?: string | null;
  doc_type?: string | null;
  field_name?: string | null;
  source_text?: string | null;
  value?: unknown;
  confidence?: number | null;
};

function formatConfidence(value: number | null | undefined) {
  return value == null ? "-" : `${Math.round(value * 100)}%`;
}

function formatJson(value: Record<string, unknown> | null) {
  return value ? JSON.stringify(value) : "-";
}

function formatRagCitations(value: Record<string, unknown>[] | null) {
  if (!value?.length) {
    return "-";
  }
  return value
    .map((citation) => String(citation.title ?? citation.chunk_id ?? "citation"))
    .join(", ");
}

function getEvidenceRefs(evidence: Record<string, unknown>) {
  const refs = evidence.refs;
  if (!Array.isArray(refs)) {
    return [];
  }
  return refs.filter((ref): ref is EvidenceRef => typeof ref === "object" && ref !== null);
}

function statusColor(status: string | null | undefined) {
  if (status === "completed" || status === "pass") {
    return "green";
  }
  if (status === "failed" || status === "fail") {
    return "red";
  }
  if (status === "need_review" || status === "warning" || status === "pending") {
    return "gold";
  }
  return "default";
}

function renderHighlightedText(rawText: string, evidenceText: string | null) {
  if (!evidenceText) {
    return rawText || "(empty page text)";
  }

  const index = rawText.indexOf(evidenceText);
  if (index < 0) {
    return rawText || "(empty page text)";
  }

  return (
    <>
      {rawText.slice(0, index)}
      <mark>{evidenceText}</mark>
      {rawText.slice(index + evidenceText.length)}
    </>
  );
}

export function AuditWorkbenchPage({ onNavigate }: PageProps) {
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [fields, setFields] = useState<ExtractedField[]>([]);
  const [auditResults, setAuditResults] = useState<AuditResult[]>([]);
  const [pages, setPages] = useState<DocumentPage[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedPageNumber, setSelectedPageNumber] = useState<number | null>(null);
  const [pendingPageNumber, setPendingPageNumber] = useState<number | null>(null);
  const [activeEvidenceText, setActiveEvidenceText] = useState<string | null>(null);
  const [reviewDrawerOpen, setReviewDrawerOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [loadingTaskData, setLoadingTaskData] = useState(false);
  const [loadingPages, setLoadingPages] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadTasks() {
      setLoadingTasks(true);
      setError(null);
      try {
        const nextTasks = await listTasks();
        if (!active) {
          return;
        }
        const preferredTaskId = window.sessionStorage.getItem("audit_workbench_task_id");
        setTasks(nextTasks);
        setSelectedTaskId(
          nextTasks.find((task) => task.id === preferredTaskId)?.id ?? nextTasks[0]?.id ?? null,
        );
      } catch {
        if (active) {
          setError("Failed to load tasks");
          message.error("Failed to load tasks");
        }
      } finally {
        if (active) {
          setLoadingTasks(false);
        }
      }
    }

    void loadTasks();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedTaskId) {
      setDocuments([]);
      setFields([]);
      setAuditResults([]);
      setSelectedDocumentId(null);
      return;
    }

    let active = true;
    const taskId = selectedTaskId;

    async function loadTaskData() {
      setLoadingTaskData(true);
      setError(null);
      try {
        const [nextDocuments, nextFields, nextAuditResults] = await Promise.all([
          listDocuments(taskId),
          listTaskFields(taskId),
          listAuditResults(taskId),
        ]);
        if (!active) {
          return;
        }
        setDocuments(nextDocuments);
        setFields(nextFields);
        setAuditResults(nextAuditResults);
        setSelectedDocumentId((currentDocumentId) =>
          nextDocuments.some((document) => document.id === currentDocumentId)
            ? currentDocumentId
            : nextDocuments[0]?.id ?? null,
        );
      } catch {
        if (active) {
          setError("Failed to load workbench data");
          message.error("Failed to load workbench data");
        }
      } finally {
        if (active) {
          setLoadingTaskData(false);
        }
      }
    }

    void loadTaskData();
    return () => {
      active = false;
    };
  }, [selectedTaskId, refreshKey]);

  useEffect(() => {
    if (!selectedDocumentId) {
      setPages([]);
      setSelectedPageNumber(null);
      return;
    }

    let active = true;
    const documentId = selectedDocumentId;

    async function loadPages() {
      setLoadingPages(true);
      try {
        const nextPages = await listDocumentPages(documentId);
        if (!active) {
          return;
        }
        setPages(nextPages);
        setSelectedPageNumber((currentPageNumber) => {
          if (pendingPageNumber && nextPages.some((page) => page.page_number === pendingPageNumber)) {
            return pendingPageNumber;
          }
          if (currentPageNumber && nextPages.some((page) => page.page_number === currentPageNumber)) {
            return currentPageNumber;
          }
          return nextPages[0]?.page_number ?? null;
        });
        setPendingPageNumber(null);
      } catch {
        if (active) {
          setPages([]);
          setSelectedPageNumber(null);
          message.error("Failed to load OCR pages");
        }
      } finally {
        if (active) {
          setLoadingPages(false);
        }
      }
    }

    void loadPages();
    return () => {
      active = false;
    };
  }, [selectedDocumentId]);

  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? null;
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? null;
  const selectedPage = pages.find((page) => page.page_number === selectedPageNumber) ?? null;
  const selectedDocumentFields = fields.filter((field) => field.document_id === selectedDocumentId);
  const visibleAuditResults = selectedDocument?.business_key
    ? auditResults.filter((result) => result.business_key === selectedDocument.business_key)
    : auditResults;

  function jumpToEvidence(documentId: string | null | undefined, pageNumber: number | null, sourceText: string | null) {
    if (!documentId) {
      message.warning("Evidence does not include a document reference");
      return;
    }

    setActiveEvidenceText(sourceText);
    if (documentId === selectedDocumentId) {
      setSelectedPageNumber(pageNumber ?? selectedPageNumber);
      return;
    }

    setPendingPageNumber(pageNumber);
    setSelectedDocumentId(documentId);
  }

  function jumpToField(field: ExtractedField) {
    jumpToEvidence(field.document_id, field.source_page, field.source_text ?? field.value_text);
  }

  function findFieldForEvidence(ref: EvidenceRef) {
    if (!ref.document_id) {
      return null;
    }

    return (
      fields.find(
        (field) => field.document_id === ref.document_id && field.field_name === ref.field_name,
      ) ??
      fields.find(
        (field) =>
          field.document_id === ref.document_id &&
          Boolean(ref.source_text) &&
          field.source_text === ref.source_text,
      ) ??
      null
    );
  }

  function jumpToRuleEvidence(ref: EvidenceRef) {
    const matchedField = findFieldForEvidence(ref);
    const sourceText =
      matchedField?.source_text ?? ref.source_text ?? (typeof ref.value === "string" ? ref.value : null);

    jumpToEvidence(ref.document_id ?? matchedField?.document_id, matchedField?.source_page ?? null, sourceText);
  }

  async function refreshReviewData() {
    setRefreshKey((value) => value + 1);
  }

  async function handleCorrectField(field: ExtractedField) {
    const nextValue = window.prompt("Corrected value", field.value_text ?? "");
    if (nextValue === null) {
      return;
    }
    try {
      await updateField(field.id, {
        value_text: nextValue,
        actor_name: "reviewer",
        comment: "Corrected in Audit Workbench.",
      });
      await refreshReviewData();
      message.success("Field corrected");
    } catch {
      message.error("Failed to correct field");
    }
  }

  async function handleConfirmResult(result: AuditResult) {
    try {
      await confirmAuditResult(result.id, {
        actor_name: "reviewer",
        reason: "Confirmed in Audit Workbench.",
      });
      await refreshReviewData();
      message.success("Audit result confirmed");
    } catch {
      message.error("Failed to confirm audit result");
    }
  }

  async function handleDismissResult(result: AuditResult) {
    const reason = window.prompt("Dismiss reason");
    if (!reason?.trim()) {
      message.warning("Dismiss reason is required");
      return;
    }
    try {
      await dismissAuditResult(result.id, {
        actor_name: "reviewer",
        reason,
      });
      await refreshReviewData();
      message.success("Audit result dismissed");
    } catch {
      message.error("Failed to dismiss audit result");
    }
  }

  async function handleRerunResult(result: AuditResult) {
    try {
      const nextResults = await rerunAuditResult(result.id, { actor_name: "reviewer" });
      setAuditResults(nextResults);
      await refreshReviewData();
      message.success("Rules rerun");
    } catch {
      message.error("Failed to rerun rules");
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Space align="center" wrap>
            <Typography.Title level={3} style={{ margin: 0 }}>
              Audit Workbench
            </Typography.Title>
            <Select
              placeholder="Select task"
              style={{ minWidth: 320 }}
              loading={loadingTasks}
              value={selectedTaskId ?? undefined}
              options={tasks.map((task) => ({
                label: `${task.task_no} - ${task.name}`,
                value: task.id,
              }))}
              onChange={(taskId) => {
                setSelectedTaskId(taskId);
                window.sessionStorage.setItem("audit_workbench_task_id", taskId);
              }}
            />
            {selectedTask ? <Tag color="blue">{selectedTask.status}</Tag> : null}
          </Space>
          {error ? <Alert type="error" showIcon message={error} /> : null}
        </Space>
      </Card>

      {loadingTasks ? (
        <Card>
          <Spin />
        </Card>
      ) : tasks.length === 0 ? (
        <Card>
          <Empty description="No tasks" />
        </Card>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "300px minmax(360px, 1fr) minmax(420px, 520px)",
            gap: 16,
            alignItems: "start",
          }}
        >
          <Card title="Documents" loading={loadingTaskData}>
            {documents.length === 0 ? (
              <Empty description="No documents" />
            ) : (
              <List
                dataSource={documents}
                renderItem={(document) => {
                  const selected = document.id === selectedDocumentId;
                  return (
                    <List.Item
                      onClick={() => {
                        setSelectedDocumentId(document.id);
                        setActiveEvidenceText(null);
                      }}
                      style={{
                        cursor: "pointer",
                        border: selected ? "1px solid #1677ff" : "1px solid #f0f0f0",
                        borderRadius: 6,
                        marginBottom: 8,
                        padding: 12,
                      }}
                    >
                      <Space direction="vertical" size={6} style={{ width: "100%" }}>
                        <Typography.Text strong ellipsis={{ tooltip: document.original_filename }}>
                          {document.original_filename}
                        </Typography.Text>
                        <Space wrap size={4}>
                          <Tag color={document.doc_type === "unknown" ? "gold" : document.doc_type ? "blue" : "default"}>
                            {document.doc_type ?? "unclassified"}
                          </Tag>
                          <Tag color={statusColor(document.ocr_status)}>OCR {document.ocr_status}</Tag>
                          <Tag color={statusColor(document.extraction_status)}>
                            Extract {document.extraction_status}
                          </Tag>
                        </Space>
                        <Typography.Text type="secondary">
                          business_key: {document.business_key ?? "-"}
                        </Typography.Text>
                        {selected ? <Tag color="processing">Selected</Tag> : null}
                      </Space>
                    </List.Item>
                  );
                }}
              />
            )}
          </Card>

          <Card
            title={selectedDocument ? selectedDocument.original_filename : "OCR Text"}
            extra={
              <Select
                placeholder="Page"
                style={{ width: 140 }}
                disabled={pages.length === 0}
                value={selectedPageNumber ?? undefined}
                options={pages.map((page) => ({
                  label: `Page ${page.page_number}`,
                  value: page.page_number,
                }))}
                onChange={setSelectedPageNumber}
              />
            }
          >
            {selectedDocument?.ocr_status === "failed" ? (
              <Alert
                type="error"
                showIcon
                message="OCR failed"
                description={selectedDocument.ocr_error ?? "Unknown OCR error"}
                style={{ marginBottom: 16 }}
              />
            ) : null}
            {loadingPages ? (
              <Spin />
            ) : selectedPage ? (
              <Space direction="vertical" style={{ width: "100%" }}>
                {selectedPage.warnings.length > 0 ? (
                  <Alert type="warning" showIcon message={selectedPage.warnings.join(", ")} />
                ) : null}
                {activeEvidenceText ? (
                  <Alert
                    type="info"
                    showIcon
                    message="Active evidence"
                    description={
                      selectedPage.raw_text.includes(activeEvidenceText)
                        ? activeEvidenceText
                        : "Evidence source text was not found on this page."
                    }
                  />
                ) : null}
                <pre
                  style={{
                    minHeight: 520,
                    maxHeight: 720,
                    overflow: "auto",
                    whiteSpace: "pre-wrap",
                    background: "#f5f5f5",
                    padding: 16,
                    margin: 0,
                  }}
                >
                  {renderHighlightedText(selectedPage.raw_text, activeEvidenceText)}
                </pre>
              </Space>
            ) : selectedDocument ? (
              <Empty description="No OCR pages" />
            ) : (
              <Empty description="Select a document" />
            )}
          </Card>

          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Card title="Fields">
              {selectedDocument ? (
                <Table<ExtractedField>
                  size="small"
                  rowKey="id"
                  dataSource={selectedDocumentFields}
                  pagination={false}
                  scroll={{ x: 760 }}
                  columns={[
                    {
                      title: "Field",
                      dataIndex: "field_label",
                      render: (value: string, record) => (
                        <Space direction="vertical" size={2}>
                          <Typography.Text>{value}</Typography.Text>
                          <Space wrap size={4}>
                            {!record.value_text && record.is_required ? <Tag color="red">Missing</Tag> : null}
                            {record.confidence != null && record.confidence < 0.6 ? (
                              <Tag color="gold">Low Confidence</Tag>
                            ) : null}
                          </Space>
                        </Space>
                      ),
                    },
                    {
                      title: "Value",
                      dataIndex: "value_text",
                      render: (value: string | null) => value ?? "null",
                    },
                    {
                      title: "Confidence",
                      dataIndex: "confidence",
                      render: (value: number | null) => formatConfidence(value),
                    },
                    {
                      title: "Source",
                      render: (_, record) => (
                        <Button size="small" disabled={!record.source_page} onClick={() => jumpToField(record)}>
                          Page {record.source_page ?? "-"}
                        </Button>
                      ),
                    },
                    {
                      title: "Source Text",
                      dataIndex: "source_text",
                      render: (value: string | null) =>
                        value ? (
                          <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 220 }}>
                            {value}
                          </Typography.Text>
                        ) : (
                          "-"
                        ),
                    },
                    {
                      title: "Review",
                      render: (_, record) => (
                        <Button size="small" onClick={() => void handleCorrectField(record)}>
                          Correct
                        </Button>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty description="Select a document" />
              )}
            </Card>

            <Card
              title="Rule Results"
              extra={<Button onClick={() => setReviewDrawerOpen(true)}>Review Drawer</Button>}
            >
              <Table<AuditResult>
                size="small"
                rowKey="id"
                dataSource={visibleAuditResults}
                pagination={false}
                scroll={{ x: 980 }}
                columns={[
                  { title: "Rule", dataIndex: "rule_code" },
                  {
                    title: "Status",
                    dataIndex: "status",
                    render: (value: string, record) => (
                      <Space>
                        <Tag color={statusColor(value)}>{value}</Tag>
                        {record.review_status === "pending" ? <Tag color="orange">Needs Review</Tag> : null}
                      </Space>
                    ),
                  },
                  { title: "Severity", dataIndex: "severity" },
                  {
                    title: "Message",
                    dataIndex: "message",
                    render: (value: string) => (
                      <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 260 }}>
                        {value}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "Expected",
                    dataIndex: "expected_value",
                    render: (value: Record<string, unknown> | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 180 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "Actual",
                    dataIndex: "actual_value",
                    render: (value: Record<string, unknown> | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 180 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "Evidence",
                    dataIndex: "evidence",
                    render: (value: Record<string, unknown>) => {
                      const refs = getEvidenceRefs(value);
                      if (refs.length === 0) {
                        return "-";
                      }
                      return (
                        <Space direction="vertical" size={4}>
                          {refs.map((ref, index) => (
                            <Button
                              key={`${ref.document_id ?? "unknown"}-${ref.field_name ?? index}`}
                              size="small"
                              onClick={() => jumpToRuleEvidence(ref)}
                            >
                              {ref.field_name ?? ref.doc_type ?? `Evidence ${index + 1}`}
                            </Button>
                          ))}
                        </Space>
                      );
                    },
                  },
                  {
                    title: "RAG Citations",
                    dataIndex: "rag_citations",
                    render: (value: Record<string, unknown>[] | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatRagCitations(value) }} style={{ maxWidth: 220 }}>
                        {formatRagCitations(value)}
                      </Typography.Text>
                    ),
                  },
                ]}
              />
            </Card>
          </Space>
        </div>
      )}

      <Drawer
        title="Review Drawer"
        open={reviewDrawerOpen}
        onClose={() => setReviewDrawerOpen(false)}
        width={620}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Button onClick={() => onNavigate("review-center")}>Open Review Center</Button>
          <Card size="small" title="Field Review">
            <Space direction="vertical" style={{ width: "100%" }}>
              {selectedDocumentFields.length === 0 ? (
                <Empty description="No fields" />
              ) : (
                selectedDocumentFields.map((field) => (
                  <Space key={field.id} wrap>
                    <Typography.Text>{field.field_label}</Typography.Text>
                    {!field.value_text && field.is_required ? <Tag color="red">Missing</Tag> : null}
                    {field.confidence != null && field.confidence < 0.6 ? <Tag color="gold">Low Confidence</Tag> : null}
                    {field.is_verified ? <Tag color="green">Verified</Tag> : null}
                    <Button size="small" onClick={() => void handleCorrectField(field)}>
                      Correct
                    </Button>
                  </Space>
                ))
              )}
            </Space>
          </Card>
          <Card size="small" title="Audit Result Review">
            <Space direction="vertical" style={{ width: "100%" }}>
              {visibleAuditResults.length === 0 ? (
                <Empty description="No audit results" />
              ) : (
                visibleAuditResults.map((result) => (
                  <Space key={result.id} direction="vertical" style={{ width: "100%" }}>
                    <Space wrap>
                      <Typography.Text strong>{result.rule_code}</Typography.Text>
                      <Tag color={statusColor(result.status)}>{result.status}</Tag>
                      <Tag color={statusColor(result.review_status)}>{result.review_status}</Tag>
                    </Space>
                    <Typography.Text>{result.message}</Typography.Text>
                    <Space wrap>
                      <Button size="small" onClick={() => void handleConfirmResult(result)}>
                        Confirm
                      </Button>
                      <Button size="small" danger onClick={() => void handleDismissResult(result)}>
                        Dismiss
                      </Button>
                      <Button size="small" onClick={() => void handleRerunResult(result)}>
                        Rerun
                      </Button>
                    </Space>
                  </Space>
                ))
              )}
            </Space>
          </Card>
        </Space>
      </Drawer>
    </Space>
  );
}
