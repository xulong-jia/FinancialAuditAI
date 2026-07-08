import { Alert, Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { createBadCase, listBadCases, updateBadCase } from "../api/client";
import type { PageProps } from "../routes";
import type { BadCase, BadCaseType } from "../types/api";
import { displayBadCaseType, displayBoolean, displaySeverity, displayStatus } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

type BadCaseFormValues = {
  case_type: BadCaseType;
  title: string;
  severity: string;
  owner_name?: string;
  input_json?: string;
  model_output_json?: string;
  expected_output_json?: string;
  validation_result_json?: string;
  in_regression?: boolean;
};

const badCaseTypeOptions: { label: string; value: BadCaseType }[] = [
  { label: "分类", value: "classification" },
  { label: "OCR", value: "ocr" },
  { label: "字段抽取", value: "extraction" },
  { label: "规则审核", value: "rule" },
  { label: "RAG", value: "rag" },
  { label: "Agent", value: "agent" },
  { label: "复核争议", value: "review_dispute" },
  { label: "端到端", value: "end_to_end" },
  { label: "回归", value: "regression" },
];

function parseJson(raw: string | undefined) {
  if (!raw?.trim()) {
    return {};
  }
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  return parsed as Record<string, unknown>;
}

function statusColor(status: string) {
  if (status === "fixed") {
    return "green";
  }
  if (status === "open") {
    return "red";
  }
  return "gold";
}

export function BadCaseCenterPage({ currentUser }: PageProps) {
  const [form] = Form.useForm<BadCaseFormValues>();
  const [cases, setCases] = useState<BadCase[]>([]);
  const [caseType, setCaseType] = useState<BadCaseType | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const canManageQuality = hasPermission(currentUser, "quality:manage");

  async function refreshCases(nextCaseType = caseType, nextStatus = status) {
    setCases(await listBadCases({ case_type: nextCaseType, status: nextStatus }));
  }

  useEffect(() => {
    void refreshCases().catch(() => message.error("Bad Case 加载失败"));
  }, []);

  async function handleCreate(values: BadCaseFormValues) {
    setLoading(true);
    try {
      await createBadCase({
        case_type: values.case_type,
        title: values.title,
        severity: values.severity,
        owner_name: values.owner_name,
        input_payload: parseJson(values.input_json),
        model_output: parseJson(values.model_output_json),
        expected_output: parseJson(values.expected_output_json),
        validation_result: values.validation_result_json ? parseJson(values.validation_result_json) : undefined,
        in_regression: values.in_regression,
      });
      form.resetFields();
      await refreshCases();
      message.success("Bad Case 已创建");
    } catch {
      message.error("Bad Case 创建失败，请检查 JSON 字段。");
    } finally {
      setLoading(false);
    }
  }

  async function handleStatus(caseId: string, nextStatus: string) {
    setLoading(true);
    try {
      await updateBadCase(caseId, { status: nextStatus });
      await refreshCases();
      message.success("Bad Case 已更新");
    } catch {
      message.error("Bad Case 更新失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Bad Case 中心
        </Typography.Title>
      </Card>
      {!canManageQuality ? <Alert type="info" showIcon message="只读权限" /> : null}

      <Card title="创建 Bad Case">
        <Form<BadCaseFormValues>
          form={form}
          layout="vertical"
          initialValues={{ case_type: "rule", severity: "medium", in_regression: false }}
          onFinish={(values) => void handleCreate(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="case_type" label="类型" rules={[{ required: true }]}>
              <Select options={badCaseTypeOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="title" label="标题" rules={[{ required: true }]}>
              <Input style={{ width: 320 }} />
            </Form.Item>
            <Form.Item name="severity" label="严重程度" rules={[{ required: true }]}>
              <Select
                style={{ width: 140 }}
                options={[
                  { label: "低", value: "low" },
                  { label: "中", value: "medium" },
                  { label: "高", value: "high" },
                ]}
              />
            </Form.Item>
            <Form.Item name="owner_name" label="负责人">
              <Input style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Form.Item name="in_regression" label="回归集">
            <Select
              style={{ width: 160 }}
              options={[
                { label: "否", value: false },
                { label: "是", value: true },
              ]}
            />
          </Form.Item>
          <Space align="start" wrap>
            <Form.Item name="input_json" label="输入 JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="model_output_json" label="模型输出 JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="expected_output_json" label="预期输出 JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="validation_result_json" label="验证结果 JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!canManageQuality}>
            创建
          </Button>
        </Form>
      </Card>

      <Card
        title="Bad Case 列表"
        extra={
          <Space>
            <Select
              allowClear
              placeholder="类型"
              options={badCaseTypeOptions}
              style={{ width: 180 }}
              value={caseType}
              onChange={(value) => {
                setCaseType(value);
                void refreshCases(value, status);
              }}
            />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 140 }}
              value={status}
              options={[
                { label: "未关闭", value: "open" },
                { label: "已修复", value: "fixed" },
                { label: "已忽略", value: "ignored" },
              ]}
              onChange={(value) => {
                setStatus(value);
                void refreshCases(caseType, value);
              }}
            />
          </Space>
        }
      >
        <Table<BadCase>
          rowKey="id"
          loading={loading}
          dataSource={cases}
          scroll={{ x: 1100 }}
          columns={[
            { title: "标题", dataIndex: "title" },
            { title: "类型", dataIndex: "case_type", render: (value: string) => <Tag>{displayBadCaseType(value)}</Tag> },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{displayStatus(value)}</Tag>,
            },
            { title: "严重程度", dataIndex: "severity", render: (value: string) => displaySeverity(value) },
            { title: "回归集", dataIndex: "in_regression", render: (value: boolean) => displayBoolean(value) },
            { title: "负责人", dataIndex: "owner_name", render: (value: string | null) => value ?? "-" },
            {
              title: "预期输出",
              dataIndex: "expected_output",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: JSON.stringify(value) }} style={{ maxWidth: 220 }}>
                  {JSON.stringify(value)}
                </Typography.Text>
              ),
            },
            {
              title: "操作",
              render: (_, record) => (
                <Space>
                  <Button size="small" disabled={!canManageQuality} onClick={() => void handleStatus(record.id, "fixed")}>
                    标记已修复
                  </Button>
                  <Button size="small" disabled={!canManageQuality} onClick={() => void handleStatus(record.id, "open")}>
                    重新打开
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
