import { Alert, Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { listEvaluationResults, runEvaluation } from "../api/client";
import type { PageProps } from "../routes";
import type { EvalType, EvaluationResult } from "../types/api";
import { hasPermission } from "../utils/permissions";

type EvaluationFormValues = {
  eval_type: EvalType;
  eval_name?: string;
  dataset_name: string;
  created_by?: string;
};

const evalTypeOptions: { label: string; value: EvalType }[] = [
  { label: "classification", value: "classification" },
  { label: "ocr", value: "ocr" },
  { label: "extraction", value: "extraction" },
  { label: "rule", value: "rule" },
  { label: "rag", value: "rag" },
  { label: "agent", value: "agent" },
  { label: "end_to_end", value: "end_to_end" },
  { label: "regression", value: "regression" },
];

function formatJson(value: unknown) {
  return JSON.stringify(value);
}

export function EvaluationCenterPage({ currentUser }: PageProps) {
  const [form] = Form.useForm<EvaluationFormValues>();
  const [results, setResults] = useState<EvaluationResult[]>([]);
  const [selected, setSelected] = useState<EvaluationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const canManageQuality = hasPermission(currentUser, "quality:manage");

  async function refreshResults() {
    const nextResults = await listEvaluationResults();
    setResults(nextResults);
    setSelected((current) =>
      current && nextResults.some((result) => result.id === current.id) ? current : nextResults[0] ?? null,
    );
  }

  useEffect(() => {
    void refreshResults().catch(() => message.error("Failed to load evaluation results"));
  }, []);

  async function handleRun(values: EvaluationFormValues) {
    setLoading(true);
    try {
      const result = await runEvaluation({
        eval_type: values.eval_type,
        eval_name: values.eval_name,
        dataset_name: values.dataset_name,
        created_by: values.created_by,
      });
      await refreshResults();
      setSelected(result);
      message.success("Evaluation completed");
    } catch {
      message.error("Evaluation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical" size="small">
          <Typography.Title level={3} style={{ margin: 0 }}>
            Evaluation Center
          </Typography.Title>
          <Alert
            type="info"
            showIcon
            message="Metrics identify dataset kind and are not production quality claims unless a real evaluation dataset is supplied."
          />
        </Space>
      </Card>

      <Card title="Run Evaluation">
        <Form<EvaluationFormValues>
          form={form}
          layout="vertical"
          initialValues={{ eval_type: "regression", dataset_name: "bad_case_regression" }}
          onFinish={(values) => void handleRun(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="eval_type" label="Type" rules={[{ required: true }]}>
              <Select options={evalTypeOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="dataset_name" label="Dataset" rules={[{ required: true }]}>
              <Input style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="eval_name" label="Name">
              <Input style={{ width: 240 }} />
            </Form.Item>
            <Form.Item name="created_by" label="Created By">
              <Input style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!canManageQuality}>
            Run
          </Button>
        </Form>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(420px, 1fr) minmax(420px, 1fr)", gap: 16 }}>
        <Card title="Results">
          <Table<EvaluationResult>
            rowKey="id"
            dataSource={results}
            loading={loading}
            pagination={false}
            onRow={(record) => ({
              onClick: () => setSelected(record),
              style: {
                cursor: "pointer",
                background: selected?.id === record.id ? "#e6f4ff" : undefined,
              },
            })}
            columns={[
              { title: "Name", dataIndex: "eval_name" },
              { title: "Type", dataIndex: "eval_type", render: (value: string) => <Tag>{value}</Tag> },
              { title: "Samples", dataIndex: "sample_count" },
              { title: "Failed", dataIndex: "failed_cases", render: (value: unknown[]) => value.length },
            ]}
          />
        </Card>

        <Card title="Selected Result">
          {selected ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text strong>{selected.eval_name}</Typography.Text>
              <Typography.Text>dataset: {selected.dataset_name}</Typography.Text>
              <Alert
                type={selected.failed_cases.length ? "warning" : "success"}
                showIcon
                message={`${selected.failed_cases.length} failed case(s)`}
              />
              <Typography.Title level={5}>Metrics</Typography.Title>
              <pre style={{ whiteSpace: "pre-wrap", background: "#f5f5f5", padding: 12 }}>
                {JSON.stringify(selected.metrics, null, 2)}
              </pre>
              <Typography.Title level={5}>Failed Cases</Typography.Title>
              <Table<Record<string, unknown>>
                size="small"
                rowKey={(record) => String(record.title ?? JSON.stringify(record))}
                dataSource={selected.failed_cases}
                pagination={false}
                columns={[
                  { title: "Title", dataIndex: "title" },
                  { title: "Severity", dataIndex: "severity" },
                  {
                    title: "Expected",
                    dataIndex: "expected_output",
                    render: (value: unknown) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "Actual",
                    dataIndex: "model_output",
                    render: (value: unknown) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                ]}
              />
            </Space>
          ) : (
            <Typography.Text type="secondary">No evaluation selected</Typography.Text>
          )}
        </Card>
      </div>
    </Space>
  );
}
