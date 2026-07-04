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
  dismissAuditResult,
  listReviewComments,
  listReviewQueue,
  listTasks,
  rerunAuditResult,
  updateField,
} from "../api/client";
import type { PageProps } from "../routes";
import type { AuditResult, AuditTask, ExtractedField, ReviewComment, ReviewQueueItem } from "../types/api";

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

export function ReviewCenterPage(_props: PageProps) {
  const [correctionForm] = Form.useForm<CorrectionFormValues>();
  const [dismissForm] = Form.useForm<DismissFormValues>();
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [editingField, setEditingField] = useState<ExtractedField | null>(null);
  const [dismissingResult, setDismissingResult] = useState<AuditResult | null>(null);
  const [loading, setLoading] = useState(false);

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
        actor_name: values.actor_name,
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
        actor_name: "reviewer",
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
      await dismissAuditResult(dismissingResult.id, values);
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
      await rerunAuditResult(result.id, { actor_name: "reviewer" });
      await refresh();
      message.success("Rules rerun");
    } catch {
      message.error("Failed to rerun rules");
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
          rowKey={(record) => record.field_id ?? record.audit_result_id ?? `${record.item_type}-${record.reason}`}
          loading={loading}
          dataSource={queue}
          pagination={false}
          scroll={{ x: 980 }}
          columns={[
            {
              title: "Type",
              dataIndex: "item_type",
              render: (value: ReviewQueueItem["item_type"]) => (
                <Tag color={value === "field" ? "blue" : "purple"}>{value}</Tag>
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
                    <Button size="small" onClick={() => openCorrection(field)}>
                      Correct
                    </Button>
                  );
                }
                const result = record.audit_result;
                if (!result) {
                  return null;
                }
                return (
                  <Space>
                    <Button size="small" onClick={() => void handleConfirm(result)}>
                      Confirm
                    </Button>
                    <Button size="small" danger onClick={() => setDismissingResult(result)}>
                      Dismiss
                    </Button>
                    <Button size="small" onClick={() => void handleRerun(result)}>
                      Rerun
                    </Button>
                  </Space>
                );
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
              <Button type="primary" htmlType="submit" loading={loading}>
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
          <Button type="primary" danger htmlType="submit" loading={loading}>
            Dismiss
          </Button>
        </Form>
      </Drawer>
    </Space>
  );
}
