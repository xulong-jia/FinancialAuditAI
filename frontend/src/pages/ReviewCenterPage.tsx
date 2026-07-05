import {
  Alert,
  Button,
  Card,
  Drawer,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";

import {
  confirmAuditResult,
  createBadCaseFromReview,
  createReviewComment,
  dismissAuditResult,
  listReviewComments,
  listReviewQueue,
  listTasks,
  reextractDocument,
  rerunAuditResult,
  rerunRulesForField,
  updateField,
} from "../api/client";
import type { PageProps } from "../routes";
import type { AuditResult, AuditTask, BadCaseType, ExtractedField, ReviewComment, ReviewQueueItem } from "../types/api";
import { hasPermission } from "../utils/permissions";

type CorrectionFormValues = {
  value_text?: string;
  value_normalized_json?: string;
  confidence?: number;
  actor_name?: string;
  comment?: string;
};

type DismissFormValues = {
  actor_name?: string;
  reason: string;
};

const { TextArea } = Input;

function formatJson(value: Record<string, unknown> | null) {
  return value ? JSON.stringify(value) : "-";
}

function statusColor(status: string | null | undefined) {
  if (status === "confirmed" || status === "pass" || status === "not_required") {
    return "green";
  }
  if (status === "dismissed" || status === "fail") {
    return "red";
  }
  if (status === "pending" || status === "warning" || status === "need_review") {
    return "gold";
  }
  return "default";
}

function parseNormalized(raw: string | undefined) {
  if (!raw?.trim()) {
    return undefined;
  }
  return JSON.parse(raw) as Record<string, unknown>;
}

export function ReviewCenterPage({ currentUser }: PageProps) {
  const [correctionForm] = Form.useForm<CorrectionFormValues>();
  const [dismissForm] = Form.useForm<DismissFormValues>();
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [editingField, setEditingField] = useState<ExtractedField | null>(null);
  const [dismissingResult, setDismissingResult] = useState<AuditResult | null>(null);
  const [loading, setLoading] = useState(false);
  const canReview = hasPermission(currentUser, "review:write");
  const reviewerName = currentUser.full_name;

  async function refresh(taskId = selectedTaskId) {
    setLoading(true);
    try {
      const [nextQueue, nextComments] = await Promise.all([
        listReviewQueue(taskId),
        listReviewComments(taskId),
      ]);
      setQueue(nextQueue);
      setComments(nextComments);
    } catch {
      message.error("Failed to load review data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function loadInitialData() {
      setLoading(true);
      try {
        const nextTasks = await listTasks();
        const preferredTaskId = window.sessionStorage.getItem("audit_workbench_task_id") ?? undefined;
        const taskId = nextTasks.find((task) => task.id === preferredTaskId)?.id ?? nextTasks[0]?.id;
        setTasks(nextTasks);
        setSelectedTaskId(taskId);
        const [nextQueue, nextComments] = await Promise.all([
          listReviewQueue(taskId),
          listReviewComments(taskId),
        ]);
        setQueue(nextQueue);
        setComments(nextComments);
      } catch {
        message.error("Failed to load review center");
      } finally {
        setLoading(false);
      }
    }

    void loadInitialData();
  }, []);

  function openCorrection(field: ExtractedField) {
    setEditingField(field);
    correctionForm.setFieldsValue({
      value_text: field.value_text ?? undefined,
      value_normalized_json: field.value_normalized ? JSON.stringify(field.value_normalized) : undefined,
      confidence: field.confidence ?? undefined,
      actor_name: reviewerName,
    });
  }

  async function handleCorrection(values: CorrectionFormValues) {
    if (!editingField) {
      return;
    }

    setLoading(true);
    try {
      await updateField(editingField.id, {
        value_text: values.value_text ?? null,
        value_normalized: parseNormalized(values.value_normalized_json),
        confidence: values.confidence ?? null,
        actor_name: values.actor_name ?? reviewerName,
        comment: values.comment,
      });
      setEditingField(null);
      correctionForm.resetFields();
      await refresh();
      message.success("Field corrected");
    } catch {
      message.error("Failed to correct field. Check normalized JSON if provided.");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(result: AuditResult) {
    setLoading(true);
    try {
      await confirmAuditResult(result.id, {
        actor_name: reviewerName,
        reason: "Confirmed in Review Center.",
      });
      await refresh();
      message.success("Audit result confirmed");
    } catch {
      message.error("Failed to confirm audit result");
    } finally {
      setLoading(false);
    }
  }

  async function handleDismiss(values: DismissFormValues) {
    if (!dismissingResult) {
      return;
    }

    setLoading(true);
    try {
      await dismissAuditResult(dismissingResult.id, {
        ...values,
        actor_name: values.actor_name ?? reviewerName,
      });
      setDismissingResult(null);
      dismissForm.resetFields();
      await refresh();
      message.success("Audit result dismissed");
    } catch {
      message.error("Failed to dismiss audit result");
    } finally {
      setLoading(false);
    }
  }

  async function handleRerun(result: AuditResult) {
    setLoading(true);
    try {
      await rerunAuditResult(result.id, { actor_name: reviewerName });
      await refresh();
      message.success("Rules rerun");
    } catch {
      message.error("Failed to rerun rules");
    } finally {
      setLoading(false);
    }
  }

  async function handleRerunField(field: ExtractedField) {
    setLoading(true);
    try {
      await rerunRulesForField(field.id, {
        actor_name: reviewerName,
        reason: "Rules rerun after field review.",
      });
      await refresh();
      message.success("Rules rerun");
    } catch {
      message.error("Failed to rerun rules");
    } finally {
      setLoading(false);
    }
  }

  async function handleReextract(documentId: string) {
    setLoading(true);
    try {
      await reextractDocument(documentId, {
        actor_name: reviewerName,
        reason: "Re-extraction requested in Review Center.",
      });
      await refresh();
      message.success("Document re-extracted");
    } catch {
      message.error("Failed to re-extract document");
    } finally {
      setLoading(false);
    }
  }

  async function handleMarkReviewed(record: ReviewQueueItem) {
    setLoading(true);
    try {
      await createReviewComment({
        task_id: record.task_id,
        document_id: record.document_id,
        audit_result_id: record.audit_result_id,
        field_id: record.field_id,
        author_name: reviewerName,
        comment_type: record.item_type === "agent_step" ? "agent_step_reviewed" : "manual_review_resolved",
        content: `Reviewed ${record.item_type}: ${record.reason}.`,
        after_value: {
          agent_step_id: record.agent_step_id,
          comment_id: record.comment_id,
          reason: record.reason,
          resolved: true,
        },
      });
      await refresh();
      message.success("Review item marked reviewed");
    } catch {
      message.error("Failed to mark review item");
    } finally {
      setLoading(false);
    }
  }

  function badCaseType(record: ReviewQueueItem): BadCaseType {
    if (record.item_type === "document" && record.reason.startsWith("ocr")) {
      return "ocr";
    }
    if (record.item_type === "document") {
      return "classification";
    }
    if (record.item_type === "field") {
      return "extraction";
    }
    if (record.item_type === "agent_step") {
      return record.reason.startsWith("rag") ? "rag" : "agent";
    }
    if (record.item_type === "comment") {
      return "review_dispute";
    }
    return "rule";
  }

  async function handleCreateBadCase(record: ReviewQueueItem) {
    setLoading(true);
    try {
      await createBadCaseFromReview({
        task_id: record.task_id,
        document_id: record.document_id,
        audit_result_id: record.audit_result_id,
        field_id: record.field_id,
        agent_step_id: record.agent_step_id,
        comment_id: record.comment_id,
        case_type: badCaseType(record),
        title: `${record.item_type}:${record.reason}`,
        severity: record.audit_result?.severity ?? "medium",
        owner_name: reviewerName,
      });
      await refresh();
      message.success("Bad case created");
    } catch {
      message.error("Failed to create bad case");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            Review Center
          </Typography.Title>
          <Select
            allowClear
            placeholder="All tasks"
            style={{ minWidth: 320 }}
            value={selectedTaskId}
            options={tasks.map((task) => ({
              label: `${task.task_no} - ${task.name}`,
              value: task.id,
            }))}
            onChange={(taskId) => {
              setSelectedTaskId(taskId);
              void refresh(taskId);
            }}
          />
          <Button loading={loading} onClick={() => void refresh()}>
            Refresh
          </Button>
        </Space>
      </Card>

      <Card title="Review Queue">
        <Table<ReviewQueueItem>
          rowKey={(record) =>
            record.field_id ??
            record.audit_result_id ??
            record.document_id ??
            record.agent_step_id ??
            record.comment_id ??
            `${record.item_type}-${record.reason}`
          }
          loading={loading}
          dataSource={queue}
          pagination={false}
          scroll={{ x: 980 }}
          columns={[
            {
              title: "Type",
              dataIndex: "item_type",
              render: (value: ReviewQueueItem["item_type"]) => (
                <Tag color={value === "field" ? "blue" : value === "audit_result" ? "purple" : "gold"}>
                  {value}
                </Tag>
              ),
            },
            { title: "Reason", dataIndex: "reason" },
            {
              title: "Target",
              render: (_, record) =>
                record.field ? (
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{record.field.field_label}</Typography.Text>
                    <Typography.Text type="secondary">{record.field.field_name}</Typography.Text>
                  </Space>
                ) : record.audit_result ? (
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{record.audit_result.rule_code}</Typography.Text>
                    <Typography.Text type="secondary">{record.audit_result.message}</Typography.Text>
                  </Space>
                ) : record.document ? (
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{record.document.original_filename}</Typography.Text>
                    <Typography.Text type="secondary">{record.document.doc_type ?? "unknown"}</Typography.Text>
                  </Space>
                ) : record.agent_step ? (
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{record.agent_step.step_name}</Typography.Text>
                    <Typography.Text type="secondary">{record.agent_step.tool_name}</Typography.Text>
                  </Space>
                ) : record.comment ? (
                  <Space direction="vertical" size={2}>
                    <Typography.Text>{record.comment.comment_type}</Typography.Text>
                    <Typography.Text type="secondary">{record.comment.content}</Typography.Text>
                  </Space>
                ) : (
                  "-"
                ),
            },
            {
              title: "Status",
              render: (_, record) =>
                record.audit_result ? (
                  <Space>
                    <Tag color={statusColor(record.audit_result.status)}>{record.audit_result.status}</Tag>
                    <Tag color={statusColor(record.audit_result.review_status)}>
                      {record.audit_result.review_status}
                    </Tag>
                  </Space>
                ) : record.field ? (
                  <Space>
                    {!record.field.value_text ? <Tag color="red">Missing</Tag> : null}
                    {record.field.confidence != null && record.field.confidence < 0.6 ? (
                      <Tag color="gold">Low Confidence</Tag>
                    ) : null}
                    {record.field.is_verified ? <Tag color="green">Verified</Tag> : null}
                  </Space>
                ) : record.document ? (
                  <Space>
                    <Tag color={statusColor(record.document.review_status)}>{record.document.review_status}</Tag>
                    <Tag color={statusColor(record.document.ocr_status)}>{record.document.ocr_status}</Tag>
                  </Space>
                ) : record.agent_step ? (
                  <Tag color={statusColor(record.agent_step.status)}>{record.agent_step.status}</Tag>
                ) : (
                  "-"
                ),
            },
            {
              title: "Value",
              render: (_, record) =>
                record.field ? (
                  <Typography.Text>{record.field.value_text ?? "null"}</Typography.Text>
                ) : record.audit_result ? (
                  <Typography.Text ellipsis={{ tooltip: formatJson(record.audit_result.actual_value) }} style={{ maxWidth: 240 }}>
                    {formatJson(record.audit_result.actual_value)}
                  </Typography.Text>
                ) : record.document ? (
                  <Typography.Text>{record.document.doc_type_confidence ?? "-"}</Typography.Text>
                ) : record.agent_step ? (
                  <Typography.Text ellipsis={{ tooltip: formatJson(record.agent_step.output_payload) }} style={{ maxWidth: 240 }}>
                    {formatJson(record.agent_step.output_payload)}
                  </Typography.Text>
                ) : record.comment ? (
                  <Typography.Text ellipsis={{ tooltip: record.comment.content }} style={{ maxWidth: 240 }}>
                    {record.comment.content}
                  </Typography.Text>
                ) : (
                  "-"
                ),
            },
            {
              title: "Action",
              render: (_, record) => {
                const field = record.field;
                if (field) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => openCorrection(field)}>
                        Correct
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleRerunField(field)}>
                        Rerun Rules
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleReextract(field.document_id)}>
                        Re-extract
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        To Bad Case
                      </Button>
                    </Space>
                  );
                }
                const result = record.audit_result;
                if (result) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => void handleConfirm(result)}>
                        Confirm
                      </Button>
                      <Button
                        size="small"
                        danger
                        disabled={!canReview}
                        onClick={() => {
                          setDismissingResult(result);
                          dismissForm.setFieldsValue({ actor_name: reviewerName });
                        }}
                      >
                        Dismiss
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleRerun(result)}>
                        Rerun
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        To Bad Case
                      </Button>
                    </Space>
                  );
                }
                const document = record.document;
                if (document) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => void handleReextract(document.id)}>
                        Re-extract
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        To Bad Case
                      </Button>
                    </Space>
                  );
                }
                if (record.agent_step || record.comment) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => void handleMarkReviewed(record)}>
                        Mark Reviewed
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        To Bad Case
                      </Button>
                    </Space>
                  );
                }
                return null;
              },
            },
          ]}
        />
      </Card>

      <Card title="Review Comment History">
        <Table<ReviewComment>
          rowKey="id"
          dataSource={comments}
          pagination={false}
          scroll={{ x: 860 }}
          columns={[
            { title: "Type", dataIndex: "comment_type" },
            { title: "Author", dataIndex: "author_name", render: (value: string | null) => value ?? "-" },
            { title: "Content", dataIndex: "content" },
            {
              title: "Before",
              dataIndex: "before_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
            {
              title: "After",
              dataIndex: "after_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
            { title: "Created", dataIndex: "created_at" },
          ]}
        />
      </Card>

      <Drawer
        title="Correct Field"
        open={Boolean(editingField)}
        onClose={() => setEditingField(null)}
        width={520}
      >
        {editingField ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Alert
              type="info"
              showIcon
              message="Original evidence is retained"
              description={`Source page: ${editingField.source_page ?? "-"}; source text: ${editingField.source_text ?? "-"}`}
            />
            <Form layout="vertical" form={correctionForm} onFinish={handleCorrection}>
              <Form.Item name="value_text" label="Corrected Value">
                <Input />
              </Form.Item>
              <Form.Item name="value_normalized_json" label="Normalized JSON">
                <TextArea rows={4} />
              </Form.Item>
              <Form.Item name="confidence" label="Confidence">
                <InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="actor_name" label="Reviewer">
                <Input />
              </Form.Item>
              <Form.Item name="comment" label="Comment">
                <TextArea rows={3} />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} disabled={!canReview}>
                Save Correction
              </Button>
            </Form>
          </Space>
        ) : null}
      </Drawer>

      <Drawer
        title="Dismiss Audit Result"
        open={Boolean(dismissingResult)}
        onClose={() => setDismissingResult(null)}
        width={460}
      >
        <Form layout="vertical" form={dismissForm} onFinish={handleDismiss}>
          <Form.Item name="actor_name" label="Reviewer">
            <Input />
          </Form.Item>
          <Form.Item name="reason" label="Dismiss Reason" rules={[{ required: true, message: "Reason is required" }]}>
            <TextArea rows={4} />
          </Form.Item>
          <Button type="primary" danger htmlType="submit" loading={loading} disabled={!canReview}>
            Dismiss
          </Button>
        </Form>
      </Drawer>
    </Space>
  );
}
