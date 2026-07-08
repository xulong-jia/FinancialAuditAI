import { Alert, Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { listEvaluationResults, listTasks, runEvaluation } from "../api/client";
import type { PageProps } from "../routes";
import type { AuditTask, EvalType, EvaluationResult } from "../types/api";
import { displayEvalType, displaySeverity } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

type EvaluationFormValues = {
  task_id?: string;
  eval_type: EvalType;
  eval_name?: string;
  dataset_name: string;
  dataset_path?: string;
  model_name?: string;
  prompt_version?: string;
  rule_version?: string;
  created_by?: string;
};

const evalTypeOptions: { label: string; value: EvalType }[] = [
  { label: "分类", value: "classification" },
  { label: "OCR", value: "ocr" },
  { label: "字段抽取", value: "extraction" },
  { label: "规则", value: "rule" },
  { label: "RAG", value: "rag" },
  { label: "Agent", value: "agent" },
  { label: "持久化 RAG 工作流", value: "persistent_rag_workflow" },
  { label: "Agent DB 工作流", value: "agent_db_workflow" },
  { label: "端到端", value: "end_to_end" },
  { label: "完整 DB 工作流", value: "full_db_workflow" },
  { label: "回归", value: "regression" },
];

function formatJson(value: unknown) {
  return JSON.stringify(value);
}

export function EvaluationCenterPage({ currentUser }: PageProps) {
  const [form] = Form.useForm<EvaluationFormValues>();
  const [tasks, setTasks] = useState<AuditTask[]>([]);
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
    async function loadInitialData() {
      setLoading(true);
      try {
        const [nextTasks] = await Promise.all([listTasks(), refreshResults()]);
        setTasks(nextTasks);
      } catch {
        message.error("评测中心加载失败");
      } finally {
        setLoading(false);
      }
    }

    void loadInitialData();
  }, []);

  async function handleRun(values: EvaluationFormValues) {
    setLoading(true);
    try {
      const result = await runEvaluation({
        task_id: values.task_id || null,
        eval_type: values.eval_type,
        eval_name: values.eval_name,
        dataset_name: values.dataset_name,
        dataset_path: values.dataset_path || null,
        model_name: values.model_name || null,
        prompt_version: values.prompt_version || null,
        rule_version: values.rule_version || null,
        created_by: values.created_by,
      });
      await refreshResults();
      setSelected(result);
      message.success("评测已完成");
    } catch {
      message.error("评测失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical" size="small">
          <Typography.Title level={3} style={{ margin: 0 }}>
            评测中心
          </Typography.Title>
          <Alert
            type="info"
            showIcon
            message="指标用于识别数据集类型；除非提供真实评测数据集，否则不代表生产质量结论。"
          />
        </Space>
      </Card>

      <Card title="运行评测">
        <Form<EvaluationFormValues>
          form={form}
          layout="vertical"
          initialValues={{ eval_type: "regression", dataset_name: "bad_case_regression" }}
          onFinish={(values) => void handleRun(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="eval_type" label="类型" rules={[{ required: true }]}>
              <Select options={evalTypeOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="dataset_name" label="数据集" rules={[{ required: true }]}>
              <Input style={{ width: 220 }} />
            </Form.Item>
            <Form.Item name="dataset_path" label="数据集路径">
              <Input placeholder="strict_eval.json" style={{ width: 240 }} />
            </Form.Item>
            <Form.Item name="task_id" label="任务范围">
              <Select
                allowClear
                style={{ width: 260 }}
                options={tasks.map((task) => ({ label: `${task.task_no} - ${task.name}`, value: task.id }))}
              />
            </Form.Item>
            <Form.Item name="eval_name" label="名称">
              <Input style={{ width: 240 }} />
            </Form.Item>
            <Form.Item name="model_name" label="模型">
              <Input style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="prompt_version" label="提示词版本">
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="rule_version" label="规则">
              <Input style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="created_by" label="创建人">
              <Input style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!canManageQuality}>
            运行
          </Button>
        </Form>
      </Card>

      <div className="two-pane-grid">
        <Card title="评测结果">
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
              { title: "名称", dataIndex: "eval_name" },
              { title: "类型", dataIndex: "eval_type", render: (value: string) => <Tag>{displayEvalType(value)}</Tag> },
              { title: "任务", dataIndex: "task_id", render: (value: string | null) => value ?? "全局" },
              { title: "样本数", dataIndex: "sample_count" },
              { title: "失败数", dataIndex: "failed_cases", render: (value: unknown[]) => value.length },
            ]}
          />
        </Card>

        <Card title="选中结果">
          {selected ? (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Typography.Text strong>{selected.eval_name}</Typography.Text>
              <Typography.Text>数据集: {selected.dataset_name}</Typography.Text>
              <Alert
                type={selected.failed_cases.length ? "warning" : "success"}
                showIcon
                message={`${selected.failed_cases.length} 个失败样例`}
              />
              <Typography.Title level={5}>指标</Typography.Title>
              <pre style={{ whiteSpace: "pre-wrap", background: "#f5f5f5", padding: 12 }}>
                {JSON.stringify(selected.metrics, null, 2)}
              </pre>
              <Typography.Title level={5}>失败样例</Typography.Title>
              <Table<Record<string, unknown>>
                size="small"
                rowKey={(record) => String(record.title ?? JSON.stringify(record))}
                dataSource={selected.failed_cases}
                pagination={false}
                columns={[
                  { title: "标题", dataIndex: "title" },
                  { title: "严重程度", dataIndex: "severity", render: (value: string) => displaySeverity(value) },
                  {
                    title: "预期输出",
                    dataIndex: "expected_output",
                    render: (value: unknown) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "实际输出",
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
            <Typography.Text type="secondary">未选择评测结果</Typography.Text>
          )}
        </Card>
      </div>
    </Space>
  );
}
