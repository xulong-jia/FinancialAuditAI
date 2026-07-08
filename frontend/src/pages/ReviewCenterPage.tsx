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
import { displayDocType, displayReviewItemType, displayStatus } from "../utils/displayText";
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
      message.error("复核数据加载失败");
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
        message.error("复核中心加载失败");
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
      message.success("字段已修正");
    } catch {
      message.error("字段修正失败，请检查标准化 JSON。");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm(result: AuditResult) {
    setLoading(true);
    try {
      await confirmAuditResult(result.id, {
        actor_name: reviewerName,
        reason: "在复核中心确认。",
      });
      await refresh();
      message.success("审核结果已确认");
    } catch {
      message.error("审核结果确认失败");
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
      message.success("审核结果已驳回");
    } catch {
      message.error("审核结果驳回失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRerun(result: AuditResult) {
    setLoading(true);
    try {
      await rerunAuditResult(result.id, { actor_name: reviewerName });
      await refresh();
      message.success("规则已重跑");
    } catch {
      message.error("规则重跑失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRerunField(field: ExtractedField) {
    setLoading(true);
    try {
      await rerunRulesForField(field.id, {
        actor_name: reviewerName,
        reason: "字段复核后重跑规则。",
      });
      await refresh();
      message.success("规则已重跑");
    } catch {
      message.error("规则重跑失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleReextract(documentId: string) {
    setLoading(true);
    try {
      await reextractDocument(documentId, {
        actor_name: reviewerName,
        reason: "复核中心请求重新抽取。",
      });
      await refresh();
      message.success("文档已重新抽取");
    } catch {
      message.error("文档重新抽取失败");
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
        content: `已复核 ${displayReviewItemType(record.item_type)}: ${record.reason}.`,
        after_value: {
          agent_step_id: record.agent_step_id,
          comment_id: record.comment_id,
          reason: record.reason,
          resolved: true,
        },
      });
      await refresh();
      message.success("复核项已标记为已复核");
    } catch {
      message.error("标记复核项失败");
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
      message.success("Bad Case 已创建");
    } catch {
      message.error("Bad Case 创建失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            复核中心
          </Typography.Title>
          <Select
            allowClear
            placeholder="全部任务"
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
            刷新
          </Button>
        </Space>
      </Card>

      <Card title="复核队列">
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
              title: "类型",
              dataIndex: "item_type",
              render: (value: ReviewQueueItem["item_type"]) => (
                <Tag color={value === "field" ? "blue" : value === "audit_result" ? "purple" : "gold"}>
                  {displayReviewItemType(value)}
                </Tag>
              ),
            },
            { title: "原因", dataIndex: "reason" },
            {
              title: "对象",
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
                    <Typography.Text type="secondary">{displayDocType(record.document.doc_type)}</Typography.Text>
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
              title: "状态",
              render: (_, record) =>
                record.audit_result ? (
                  <Space>
                    <Tag color={statusColor(record.audit_result.status)}>{displayStatus(record.audit_result.status)}</Tag>
                    <Tag color={statusColor(record.audit_result.review_status)}>
                      {displayStatus(record.audit_result.review_status)}
                    </Tag>
                  </Space>
                ) : record.field ? (
                  <Space>
                    {!record.field.value_text ? <Tag color="red">缺失</Tag> : null}
                    {record.field.confidence != null && record.field.confidence < 0.6 ? (
                      <Tag color="gold">低置信度</Tag>
                    ) : null}
                    {record.field.is_verified ? <Tag color="green">已验证</Tag> : null}
                  </Space>
                ) : record.document ? (
                  <Space>
                    <Tag color={statusColor(record.document.review_status)}>{displayStatus(record.document.review_status)}</Tag>
                    <Tag color={statusColor(record.document.ocr_status)}>{displayStatus(record.document.ocr_status)}</Tag>
                  </Space>
                ) : record.agent_step ? (
                  <Tag color={statusColor(record.agent_step.status)}>{displayStatus(record.agent_step.status)}</Tag>
                ) : (
                  "-"
                ),
            },
            {
              title: "值",
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
              title: "操作",
              render: (_, record) => {
                const field = record.field;
                if (field) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => openCorrection(field)}>
                        修正
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleRerunField(field)}>
                        重跑规则
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleReextract(field.document_id)}>
                        重新抽取
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        转为 Bad Case
                      </Button>
                    </Space>
                  );
                }
                const result = record.audit_result;
                if (result) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => void handleConfirm(result)}>
                        确认
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
                        驳回
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleRerun(result)}>
                        重跑
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        转为 Bad Case
                      </Button>
                    </Space>
                  );
                }
                const document = record.document;
                if (document) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => void handleReextract(document.id)}>
                        重新抽取
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        转为 Bad Case
                      </Button>
                    </Space>
                  );
                }
                if (record.agent_step || record.comment) {
                  return (
                    <Space>
                      <Button size="small" disabled={!canReview} onClick={() => void handleMarkReviewed(record)}>
                        标记已复核
                      </Button>
                      <Button size="small" disabled={!canReview} onClick={() => void handleCreateBadCase(record)}>
                        转为 Bad Case
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

      <Card title="复核意见历史">
        <Table<ReviewComment>
          rowKey="id"
          dataSource={comments}
          pagination={false}
          scroll={{ x: 860 }}
          columns={[
            { title: "类型", dataIndex: "comment_type" },
            { title: "作者", dataIndex: "author_name", render: (value: string | null) => value ?? "-" },
            { title: "内容", dataIndex: "content" },
            {
              title: "变更前",
              dataIndex: "before_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
            {
              title: "变更后",
              dataIndex: "after_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
            { title: "创建时间", dataIndex: "created_at" },
          ]}
        />
      </Card>

      <Drawer
        title="修正字段"
        open={Boolean(editingField)}
        onClose={() => setEditingField(null)}
        width={520}
      >
        {editingField ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Alert
              type="info"
              showIcon
              message="原始证据会保留"
              description={`来源页码: ${editingField.source_page ?? "-"}; 来源文本: ${editingField.source_text ?? "-"}`}
            />
            <Form layout="vertical" form={correctionForm} onFinish={handleCorrection}>
              <Form.Item name="value_text" label="修正值">
                <Input />
              </Form.Item>
              <Form.Item name="value_normalized_json" label="标准化 JSON">
                <TextArea rows={4} />
              </Form.Item>
              <Form.Item name="confidence" label="置信度">
                <InputNumber min={0} max={1} step={0.01} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="actor_name" label="复核人">
                <Input />
              </Form.Item>
              <Form.Item name="comment" label="备注">
                <TextArea rows={3} />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} disabled={!canReview}>
                保存修正
              </Button>
            </Form>
          </Space>
        ) : null}
      </Drawer>

      <Drawer
        title="驳回审核结果"
        open={Boolean(dismissingResult)}
        onClose={() => setDismissingResult(null)}
        width={460}
      >
        <Form layout="vertical" form={dismissForm} onFinish={handleDismiss}>
          <Form.Item name="actor_name" label="复核人">
            <Input />
          </Form.Item>
          <Form.Item name="reason" label="驳回原因" rules={[{ required: true, message: "请输入原因" }]}>
            <TextArea rows={4} />
          </Form.Item>
          <Button type="primary" danger htmlType="submit" loading={loading} disabled={!canReview}>
            驳回
          </Button>
        </Form>
      </Drawer>
    </Space>
  );
}
