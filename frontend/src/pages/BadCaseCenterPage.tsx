import { Alert, Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { createBadCase, listBadCases, updateBadCase } from "../api/client";
import type { PageProps } from "../routes";
import type { BadCase, BadCaseType } from "../types/api";
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
  { label: "classification", value: "classification" },
  { label: "ocr", value: "ocr" },
  { label: "extraction", value: "extraction" },
  { label: "rule", value: "rule" },
  { label: "rag", value: "rag" },
  { label: "agent", value: "agent" },
  { label: "review_dispute", value: "review_dispute" },
  { label: "end_to_end", value: "end_to_end" },
  { label: "regression", value: "regression" },
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
    void refreshCases().catch(() => message.error("Failed to load bad cases"));
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
      message.success("Bad case created");
    } catch {
      message.error("Failed to create bad case. Check JSON fields.");
    } finally {
      setLoading(false);
    }
  }

  async function handleStatus(caseId: string, nextStatus: string) {
    setLoading(true);
    try {
      await updateBadCase(caseId, { status: nextStatus });
      await refreshCases();
      message.success("Bad case updated");
    } catch {
      message.error("Failed to update bad case");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Bad Case Center
        </Typography.Title>
      </Card>
      {!canManageQuality ? <Alert type="info" showIcon message="Read-only permissions" /> : null}

      <Card title="Create Bad Case">
        <Form<BadCaseFormValues>
          form={form}
          layout="vertical"
          initialValues={{ case_type: "rule", severity: "medium", in_regression: false }}
          onFinish={(values) => void handleCreate(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="case_type" label="Type" rules={[{ required: true }]}>
              <Select options={badCaseTypeOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="title" label="Title" rules={[{ required: true }]}>
              <Input style={{ width: 320 }} />
            </Form.Item>
            <Form.Item name="severity" label="Severity" rules={[{ required: true }]}>
              <Select
                style={{ width: 140 }}
                options={[
                  { label: "low", value: "low" },
                  { label: "medium", value: "medium" },
                  { label: "high", value: "high" },
                ]}
              />
            </Form.Item>
            <Form.Item name="owner_name" label="Owner">
              <Input style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Form.Item name="in_regression" label="Regression Set">
            <Select
              style={{ width: 160 }}
              options={[
                { label: "no", value: false },
                { label: "yes", value: true },
              ]}
            />
          </Form.Item>
          <Space align="start" wrap>
            <Form.Item name="input_json" label="Input JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="model_output_json" label="Model Output JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="expected_output_json" label="Expected Output JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="validation_result_json" label="Validation Result JSON">
              <Input.TextArea rows={3} style={{ width: 300 }} />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!canManageQuality}>
            Create
          </Button>
        </Form>
      </Card>

      <Card
        title="Bad Cases"
        extra={
          <Space>
            <Select
              allowClear
              placeholder="Type"
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
              placeholder="Status"
              style={{ width: 140 }}
              value={status}
              options={[
                { label: "open", value: "open" },
                { label: "fixed", value: "fixed" },
                { label: "ignored", value: "ignored" },
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
            { title: "Title", dataIndex: "title" },
            { title: "Type", dataIndex: "case_type", render: (value: string) => <Tag>{value}</Tag> },
            {
              title: "Status",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
            },
            { title: "Severity", dataIndex: "severity" },
            { title: "Regression", dataIndex: "in_regression", render: (value: boolean) => (value ? "yes" : "no") },
            { title: "Owner", dataIndex: "owner_name", render: (value: string | null) => value ?? "-" },
            {
              title: "Expected",
              dataIndex: "expected_output",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: JSON.stringify(value) }} style={{ maxWidth: 220 }}>
                  {JSON.stringify(value)}
                </Typography.Text>
              ),
            },
            {
              title: "Action",
              render: (_, record) => (
                <Space>
                  <Button size="small" disabled={!canManageQuality} onClick={() => void handleStatus(record.id, "fixed")}>
                    Mark Fixed
                  </Button>
                  <Button size="small" disabled={!canManageQuality} onClick={() => void handleStatus(record.id, "open")}>
                    Reopen
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
