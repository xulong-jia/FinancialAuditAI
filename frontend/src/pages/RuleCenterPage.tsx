import { Alert, Button, Card, Empty, Form, Input, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { evaluateRule, listRules, listTasks, updateRule } from "../api/client";
import type { AuditRule, AuditRuleEvaluateResult, AuditTask } from "../types/api";

type RuleFormValues = {
  name: string;
  version: string;
  enabled: boolean;
  description?: string;
  actor_name?: string;
  parameters_json: string;
};

type EvaluateFormValues = {
  task_id: string;
  parameters_json?: string;
};

function parseJsonObject(raw: string | undefined) {
  if (!raw?.trim()) {
    return {};
  }
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  return parsed as Record<string, unknown>;
}

function formatJson(value: Record<string, unknown> | null | undefined) {
  return value ? JSON.stringify(value, null, 2) : "{}";
}

function statusColor(status: string) {
  if (status === "pass") {
    return "green";
  }
  if (status === "fail") {
    return "red";
  }
  if (status === "warning" || status === "need_review") {
    return "gold";
  }
  return "default";
}

function evidenceCount(value: Record<string, unknown>) {
  const refs = value.refs;
  return Array.isArray(refs) ? refs.length : 0;
}

export function RuleCenterPage() {
  const [ruleForm] = Form.useForm<RuleFormValues>();
  const [evaluateForm] = Form.useForm<EvaluateFormValues>();
  const [rules, setRules] = useState<AuditRule[]>([]);
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [evaluationResults, setEvaluationResults] = useState<AuditRuleEvaluateResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [evaluating, setEvaluating] = useState(false);

  const selectedRule = useMemo(
    () => rules.find((rule) => rule.id === selectedRuleId) ?? rules[0] ?? null,
    [rules, selectedRuleId],
  );

  async function refreshRules() {
    const nextRules = await listRules();
    setRules(nextRules);
    setSelectedRuleId((currentRuleId) =>
      nextRules.some((rule) => rule.id === currentRuleId) ? currentRuleId : nextRules[0]?.id ?? null,
    );
  }

  useEffect(() => {
    setLoading(true);
    Promise.all([refreshRules(), listTasks().then(setTasks)])
      .catch(() => message.error("Failed to load Rule Center data"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedRule) {
      ruleForm.resetFields();
      return;
    }
    ruleForm.setFieldsValue({
      name: selectedRule.name,
      version: selectedRule.version,
      enabled: selectedRule.enabled,
      description: selectedRule.description ?? "",
      actor_name: "rule_admin",
      parameters_json: formatJson(selectedRule.parameters),
    });
    setEvaluationResults([]);
  }, [ruleForm, selectedRule]);

  async function handleSave(values: RuleFormValues) {
    if (!selectedRule) {
      return;
    }
    setSaving(true);
    try {
      await updateRule(selectedRule.id, {
        name: values.name,
        version: values.version,
        enabled: values.enabled,
        description: values.description ?? null,
        parameters: parseJsonObject(values.parameters_json),
        actor_name: values.actor_name,
      });
      await refreshRules();
      message.success("Rule updated");
    } catch {
      message.error("Failed to update rule. Check parameters JSON and allowed keys.");
    } finally {
      setSaving(false);
    }
  }

  async function handleEvaluate(values: EvaluateFormValues) {
    if (!selectedRule) {
      return;
    }
    setEvaluating(true);
    try {
      const results = await evaluateRule(selectedRule.id, {
        task_id: values.task_id,
        parameters: parseJsonObject(values.parameters_json),
      });
      setEvaluationResults(results);
      message.success("Rule evaluated");
    } catch {
      message.error("Rule evaluation failed. Select a linked task and check JSON parameters.");
    } finally {
      setEvaluating(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical" size="small" style={{ width: "100%" }}>
          <Space align="center" wrap>
            <Typography.Title level={3} style={{ margin: 0 }}>
              Rule Center
            </Typography.Title>
            <Tag color="blue">Python registry</Tag>
            <Tag color="default">No DSL</Tag>
          </Space>
          <Alert
            type="info"
            showIcon
            message="Rules remain deterministic code. This page only changes enabled status, version, and approved parameters."
          />
        </Space>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(360px, 440px) minmax(520px, 1fr)", gap: 16 }}>
        <Card title="Rules" loading={loading}>
          {rules.length === 0 ? (
            <Empty description="No rules" />
          ) : (
            <Table<AuditRule>
              size="small"
              rowKey="id"
              dataSource={rules}
              pagination={false}
              onRow={(record) => ({
                onClick: () => setSelectedRuleId(record.id),
                style: {
                  cursor: "pointer",
                  background: record.id === selectedRule?.id ? "#e6f4ff" : undefined,
                },
              })}
              columns={[
                {
                  title: "Rule",
                  dataIndex: "rule_code",
                  render: (value: string, record) => (
                    <Space direction="vertical" size={2}>
                      <Typography.Text strong>{value}</Typography.Text>
                      <Typography.Text type="secondary">{record.name}</Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: "Status",
                  dataIndex: "enabled",
                  render: (value: boolean) => <Tag color={value ? "green" : "default"}>{value ? "enabled" : "disabled"}</Tag>,
                },
                { title: "Version", dataIndex: "version" },
              ]}
            />
          )}
        </Card>

        {selectedRule ? (
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <Card title="Rule Detail">
              <Form<RuleFormValues> form={ruleForm} layout="vertical" onFinish={(values) => void handleSave(values)}>
                <Space align="start" wrap>
                  <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                    <Input style={{ width: 280 }} />
                  </Form.Item>
                  <Form.Item name="version" label="Version" rules={[{ required: true }]}>
                    <Input style={{ width: 120 }} />
                  </Form.Item>
                  <Form.Item name="enabled" label="Enabled" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="actor_name" label="Actor">
                    <Input style={{ width: 180 }} />
                  </Form.Item>
                </Space>
                <Space wrap style={{ marginBottom: 16 }}>
                  <Tag>{selectedRule.category}</Tag>
                  <Tag color={selectedRule.severity === "high" ? "red" : "gold"}>{selectedRule.severity}</Tag>
                  <Tag>{selectedRule.rule_code}</Tag>
                </Space>
                <Form.Item name="description" label="Description">
                  <Input />
                </Form.Item>
                <Form.Item
                  name="parameters_json"
                  label="Parameters JSON"
                  rules={[{ required: true, message: "Parameters JSON is required" }]}
                >
                  <Input.TextArea rows={10} />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={saving}>
                  Save Rule
                </Button>
              </Form>
            </Card>

            <Card title="Rule Evaluate">
              <Form<EvaluateFormValues> form={evaluateForm} layout="vertical" onFinish={(values) => void handleEvaluate(values)}>
                <Space align="start" wrap>
                  <Form.Item name="task_id" label="Task" rules={[{ required: true }]}>
                    <Select
                      style={{ minWidth: 320 }}
                      options={tasks.map((task) => ({
                        label: `${task.task_no} - ${task.name}`,
                        value: task.id,
                      }))}
                    />
                  </Form.Item>
                </Space>
                <Form.Item name="parameters_json" label="Temporary Parameter Override JSON">
                  <Input.TextArea rows={4} placeholder='{"tolerance_amount": 5}' />
                </Form.Item>
                <Button htmlType="submit" loading={evaluating}>
                  Evaluate Dry Run
                </Button>
              </Form>
            </Card>

            <Card title="Evaluation Results">
              <Table<AuditRuleEvaluateResult>
                size="small"
                rowKey={(record) => `${record.rule_code}-${record.business_key}`}
                dataSource={evaluationResults}
                pagination={false}
                scroll={{ x: 980 }}
                columns={[
                  { title: "Business Key", dataIndex: "business_key" },
                  { title: "Rule", dataIndex: "rule_code" },
                  { title: "Version", dataIndex: "rule_version" },
                  {
                    title: "Status",
                    dataIndex: "status",
                    render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
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
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "Actual",
                    dataIndex: "actual_value",
                    render: (value: Record<string, unknown> | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "Evidence",
                    dataIndex: "evidence",
                    render: (value: Record<string, unknown>) => `${evidenceCount(value)} refs`,
                  },
                ]}
              />
            </Card>
          </Space>
        ) : (
          <Card>
            <Empty description="Select a rule" />
          </Card>
        )}
      </div>
    </Space>
  );
}
