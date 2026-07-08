import { Alert, Button, Card, Drawer, Empty, List, Select, Space, Spin, Table, Tag, Typography, message } from "antd";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import {
  confirmAuditResult,
  dismissAuditResult,
  fetchPageImage,
  listAuditResults,
  listDocumentPages,
  listDocuments,
  listTaskFields,
  listTasks,
  rerunAuditResult,
  updateField,
} from "../api/client";
import { AgentStateTimeline } from "../components/AgentStateTimeline";
import type { PageProps } from "../routes";
import type { AuditResult, AuditTask, DocumentPage, DocumentRecord, ExtractedField } from "../types/api";
import { displayDocType, displaySeverity, displayStatus } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

type EvidenceRef = {
  document_id?: string | null;
  doc_type?: string | null;
  field_name?: string | null;
  source_text?: string | null;
  source_bbox?: number[] | null;
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
    return rawText || "(空页面文本)";
  }

  const index = rawText.indexOf(evidenceText);
  if (index < 0) {
    return rawText || "(空页面文本)";
  }

  return (
    <>
      {rawText.slice(0, index)}
      <mark>{evidenceText}</mark>
      {rawText.slice(index + evidenceText.length)}
    </>
  );
}

function evidenceBoxStyle(page: DocumentPage, bbox: number[] | null): CSSProperties | null {
  if (!bbox || bbox.length !== 4 || !page.width || !page.height) {
    return null;
  }
  const [x0, y0, x1, y1] = bbox;
  return {
    position: "absolute",
    left: `${Math.max(0, (x0 / page.width) * 100)}%`,
    top: `${Math.max(0, (y0 / page.height) * 100)}%`,
    width: `${Math.max(0, ((x1 - x0) / page.width) * 100)}%`,
    height: `${Math.max(0, ((y1 - y0) / page.height) * 100)}%`,
    border: "2px solid #faad14",
    background: "rgba(250, 173, 20, 0.18)",
    boxShadow: "0 0 0 1px rgba(0,0,0,0.35)",
    pointerEvents: "none",
  };
}

export function AuditWorkbenchPage({ onNavigate, currentUser }: PageProps) {
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
  const [activeEvidenceBBox, setActiveEvidenceBBox] = useState<number[] | null>(null);
  const [pageImageUrl, setPageImageUrl] = useState<string | null>(null);
  const [loadingPageImage, setLoadingPageImage] = useState(false);
  const [reviewDrawerOpen, setReviewDrawerOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [loadingTaskData, setLoadingTaskData] = useState(false);
  const [loadingPages, setLoadingPages] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canReview = hasPermission(currentUser, "review:write");
  const canViewEvaluation = hasPermission(currentUser, "evaluation:read");
  const canRunAgent = hasPermission(currentUser, "agent:run");

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
          setError("任务加载失败");
          message.error("任务加载失败");
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
          setError("审核工作台数据加载失败");
          message.error("审核工作台数据加载失败");
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
          message.error("OCR 页面加载失败");
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

  useEffect(() => {
    if (!selectedDocumentId || !selectedPageNumber) {
      setPageImageUrl(null);
      return;
    }

    const page = pages.find((item) => item.page_number === selectedPageNumber);
    if (!page?.image_path) {
      setPageImageUrl(null);
      return;
    }

    let active = true;
    let objectUrl: string | null = null;
    const documentId = selectedDocumentId;
    const pageNumber = selectedPageNumber;

    async function loadPageImage() {
      setLoadingPageImage(true);
      try {
        const blob = await fetchPageImage(documentId, pageNumber);
        objectUrl = window.URL.createObjectURL(blob);
        if (active) {
          setPageImageUrl(objectUrl);
        } else {
          window.URL.revokeObjectURL(objectUrl);
        }
      } catch {
        if (active) {
          setPageImageUrl(null);
          message.error("页面图片加载失败");
        }
      } finally {
        if (active) {
          setLoadingPageImage(false);
        }
      }
    }

    void loadPageImage();
    return () => {
      active = false;
      if (objectUrl) {
        window.URL.revokeObjectURL(objectUrl);
      }
    };
  }, [pages, selectedDocumentId, selectedPageNumber]);

  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? null;
  const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? null;
  const selectedPage = pages.find((page) => page.page_number === selectedPageNumber) ?? null;
  const selectedDocumentFields = fields.filter((field) => field.document_id === selectedDocumentId);
  const visibleAuditResults = selectedDocument?.business_key
    ? auditResults.filter((result) => result.business_key === selectedDocument.business_key)
    : auditResults;

  function jumpToEvidence(
    documentId: string | null | undefined,
    pageNumber: number | null,
    sourceText: string | null,
    sourceBBox?: number[] | null,
  ) {
    if (!documentId) {
      message.warning("证据未包含文档引用");
      return;
    }

    setActiveEvidenceText(sourceText);
    setActiveEvidenceBBox(sourceBBox ?? null);
    if (documentId === selectedDocumentId) {
      setSelectedPageNumber(pageNumber ?? selectedPageNumber);
      return;
    }

    setPendingPageNumber(pageNumber);
    setSelectedDocumentId(documentId);
  }

  function jumpToField(field: ExtractedField) {
    jumpToEvidence(field.document_id, field.source_page, field.source_text ?? field.value_text, field.source_bbox);
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
    const sourceBBox = matchedField?.source_bbox ?? ref.source_bbox ?? null;

    jumpToEvidence(ref.document_id ?? matchedField?.document_id, matchedField?.source_page ?? null, sourceText, sourceBBox);
  }

  async function refreshReviewData() {
    setRefreshKey((value) => value + 1);
  }

  async function handleCorrectField(field: ExtractedField) {
    const nextValue = window.prompt("修正后的值", field.value_text ?? "");
    if (nextValue === null) {
      return;
    }
    try {
      await updateField(field.id, {
        value_text: nextValue,
        actor_name: currentUser.full_name,
        comment: "在审核工作台修正。",
      });
      await refreshReviewData();
      message.success("字段已修正");
    } catch {
      message.error("字段修正失败");
    }
  }

  async function handleConfirmResult(result: AuditResult) {
    try {
      await confirmAuditResult(result.id, {
        actor_name: currentUser.full_name,
        reason: "在审核工作台确认。",
      });
      await refreshReviewData();
      message.success("审核结果已确认");
    } catch {
      message.error("审核结果确认失败");
    }
  }

  async function handleDismissResult(result: AuditResult) {
    const reason = window.prompt("驳回原因");
    if (!reason?.trim()) {
      message.warning("请输入驳回原因");
      return;
    }
    try {
      await dismissAuditResult(result.id, {
        actor_name: currentUser.full_name,
        reason,
      });
      await refreshReviewData();
      message.success("审核结果已驳回");
    } catch {
      message.error("审核结果驳回失败");
    }
  }

  async function handleRerunResult(result: AuditResult) {
    try {
      const nextResults = await rerunAuditResult(result.id, { actor_name: currentUser.full_name });
      setAuditResults(nextResults);
      await refreshReviewData();
      message.success("规则已重跑");
    } catch {
      message.error("规则重跑失败");
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Space align="center" wrap>
            <Typography.Title level={3} style={{ margin: 0 }}>
              审核工作台
            </Typography.Title>
            <Button disabled={!canViewEvaluation} onClick={() => onNavigate("bad-case-center")}>
              失败案例中心
            </Button>
            <Select
              placeholder="选择任务"
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
            {selectedTask ? <Tag color="blue">{displayStatus(selectedTask.status)}</Tag> : null}
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
          <Empty description="暂无任务" />
        </Card>
      ) : (
        <>
          <AgentStateTimeline taskId={selectedTaskId} canRunAgent={canRunAgent} />
          <div className="workbench-grid">
          <Card title="文档" loading={loadingTaskData}>
            {documents.length === 0 ? (
              <Empty description="暂无文档" />
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
                        setActiveEvidenceBBox(null);
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
                            {document.doc_type ? displayDocType(document.doc_type) : "未分类"}
                          </Tag>
                          <Tag color={statusColor(document.ocr_status)}>OCR {displayStatus(document.ocr_status)}</Tag>
                          <Tag color={statusColor(document.extraction_status)}>
                            抽取 {displayStatus(document.extraction_status)}
                          </Tag>
                        </Space>
                        <Typography.Text type="secondary">
                          业务键: {document.business_key ?? "-"}
                        </Typography.Text>
                        {selected ? <Tag color="processing">已选中</Tag> : null}
                      </Space>
                    </List.Item>
                  );
                }}
              />
            )}
          </Card>

          <Card
            title={selectedDocument ? selectedDocument.original_filename : "OCR 文本"}
            extra={
              <Select
                placeholder="页码"
                style={{ width: 140 }}
                disabled={pages.length === 0}
                value={selectedPageNumber ?? undefined}
                options={pages.map((page) => ({
                  label: `第 ${page.page_number} 页`,
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
                message="OCR 失败"
                description={selectedDocument.ocr_error ?? "未知 OCR 错误"}
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
                    message="当前证据"
                    description={
                      selectedPage.raw_text.includes(activeEvidenceText)
                        ? activeEvidenceText
                        : "当前页面未找到该证据原文。"
                    }
                  />
                ) : null}
                {loadingPageImage ? <Spin /> : null}
                {pageImageUrl ? (
                  <div
                    style={{
                      position: "relative",
                      width: "100%",
                      overflow: "auto",
                      background: "#f5f5f5",
                      border: "1px solid #f0f0f0",
                    }}
                  >
                    <img
                      src={pageImageUrl}
                      alt={`第 ${selectedPage.page_number} 页`}
                      style={{ display: "block", width: "100%", height: "auto" }}
                    />
                    {(() => {
                      const overlayStyle = evidenceBoxStyle(selectedPage, activeEvidenceBBox);
                      return overlayStyle ? <div style={overlayStyle} /> : null;
                    })()}
                  </div>
                ) : selectedPage.image_path ? null : (
                  <Alert type="info" showIcon message="当前 OCR 结果没有可用页面图片" />
                )}
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
              <Empty description="暂无 OCR 页面" />
            ) : (
              <Empty description="请选择文档" />
            )}
          </Card>

          <Space direction="vertical" size="middle" style={{ width: "100%" }}>
            <Card title="字段">
              {selectedDocument ? (
                <Table<ExtractedField>
                  size="small"
                  rowKey="id"
                  dataSource={selectedDocumentFields}
                  pagination={false}
                  scroll={{ x: 760 }}
                  columns={[
                    {
                      title: "字段",
                      dataIndex: "field_label",
                      render: (value: string, record) => (
                        <Space direction="vertical" size={2}>
                          <Typography.Text>{value}</Typography.Text>
                          <Space wrap size={4}>
                            {!record.value_text && record.is_required ? <Tag color="red">缺失</Tag> : null}
                            {record.confidence != null && record.confidence < 0.6 ? (
                              <Tag color="gold">低置信度</Tag>
                            ) : null}
                          </Space>
                        </Space>
                      ),
                    },
                    {
                      title: "值",
                      dataIndex: "value_text",
                      render: (value: string | null) => value ?? "null",
                    },
                    {
                      title: "置信度",
                      dataIndex: "confidence",
                      render: (value: number | null) => formatConfidence(value),
                    },
                    {
                      title: "来源",
                      render: (_, record) => (
                        <Button size="small" disabled={!record.source_page} onClick={() => jumpToField(record)}>
                          第 {record.source_page ?? "-"} 页
                        </Button>
                      ),
                    },
                    {
                      title: "来源文本",
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
                      title: "复核",
                      render: (_, record) => (
                        <Button size="small" disabled={!canReview} onClick={() => void handleCorrectField(record)}>
                          修正
                        </Button>
                      ),
                    },
                  ]}
                />
              ) : (
                <Empty description="请选择文档" />
              )}
            </Card>

            <Card
              title="规则结果"
              extra={<Button onClick={() => setReviewDrawerOpen(true)}>复核抽屉</Button>}
            >
              <Table<AuditResult>
                size="small"
                rowKey="id"
                dataSource={visibleAuditResults}
                pagination={false}
                scroll={{ x: 980 }}
                columns={[
                  { title: "规则", dataIndex: "rule_code" },
                  {
                    title: "状态",
                    dataIndex: "status",
                    render: (value: string, record) => (
                      <Space>
                        <Tag color={statusColor(value)}>{displayStatus(value)}</Tag>
                        {record.review_status === "pending" ? <Tag color="orange">待复核</Tag> : null}
                      </Space>
                    ),
                  },
                  { title: "严重程度", dataIndex: "severity", render: (value: string) => displaySeverity(value) },
                  {
                    title: "消息",
                    dataIndex: "message",
                    render: (value: string) => (
                      <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 260 }}>
                        {value}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "预期值",
                    dataIndex: "expected_value",
                    render: (value: Record<string, unknown> | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 180 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "实际值",
                    dataIndex: "actual_value",
                    render: (value: Record<string, unknown> | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 180 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "证据",
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
                              {ref.field_name ?? displayDocType(ref.doc_type) ?? `证据 ${index + 1}`}
                            </Button>
                          ))}
                        </Space>
                      );
                    },
                  },
                  {
                    title: "RAG 引用",
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
        </>
      )}

      <Drawer
        title="复核抽屉"
        open={reviewDrawerOpen}
        onClose={() => setReviewDrawerOpen(false)}
        width={620}
      >
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Button onClick={() => onNavigate("review-center")}>打开复核中心</Button>
          <Card size="small" title="字段复核">
            <Space direction="vertical" style={{ width: "100%" }}>
              {selectedDocumentFields.length === 0 ? (
                <Empty description="暂无字段" />
              ) : (
                selectedDocumentFields.map((field) => (
                  <Space key={field.id} wrap>
                    <Typography.Text>{field.field_label}</Typography.Text>
                    {!field.value_text && field.is_required ? <Tag color="red">缺失</Tag> : null}
                    {field.confidence != null && field.confidence < 0.6 ? <Tag color="gold">低置信度</Tag> : null}
                    {field.is_verified ? <Tag color="green">已验证</Tag> : null}
                    <Button size="small" disabled={!canReview} onClick={() => void handleCorrectField(field)}>
                      修正
                    </Button>
                  </Space>
                ))
              )}
            </Space>
          </Card>
          <Card size="small" title="审核结果复核">
            <Space direction="vertical" style={{ width: "100%" }}>
              {visibleAuditResults.length === 0 ? (
                <Empty description="暂无审核结果" />
              ) : (
                visibleAuditResults.map((result) => (
                  <Space key={result.id} direction="vertical" style={{ width: "100%" }}>
                    <Space wrap>
                      <Typography.Text strong>{result.rule_code}</Typography.Text>
                      <Tag color={statusColor(result.status)}>{displayStatus(result.status)}</Tag>
                      <Tag color={statusColor(result.review_status)}>{displayStatus(result.review_status)}</Tag>
                    </Space>
                    <Typography.Text>{result.message}</Typography.Text>
                    <Space wrap>
                      <Button size="small" disabled={!canReview} onClick={() => void handleConfirmResult(result)}>
                        确认
                      </Button>
                      <Button size="small" danger disabled={!canReview} onClick={() => void handleDismissResult(result)}>
                        驳回
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleRerunResult(result)}>
                        重跑
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
