import { Alert, Button, Card, Empty, Form, Input, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { evaluateRule, listRules, listTasks, updateRule } from "../api/client";
import type { PageProps } from "../routes";
import type { AuditRule, AuditRuleEvaluateResult, AuditTask } from "../types/api";
import { displayScenario, displaySeverity, displayStatus } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

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

export function RuleCenterPage({ currentUser }: PageProps) {
  const [ruleForm] = Form.useForm<RuleFormValues>();
  const [evaluateForm] = Form.useForm<EvaluateFormValues>();
  const [rules, setRules] = useState<AuditRule[]>([]);
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [evaluationResults, setEvaluationResults] = useState<AuditRuleEvaluateResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const canManageRules = hasPermission(currentUser, "rule:manage");

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
      .catch(() => message.error("规则中心数据加载失败"))
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
      actor_name: currentUser.full_name,
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
      message.success("规则已更新");
    } catch {
      message.error("规则更新失败，请检查参数 JSON 和允许的键。");
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
      message.success("规则试算已完成");
    } catch {
      message.error("规则试算失败，请选择已归集任务并检查 JSON 参数。");
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
              规则中心
            </Typography.Title>
            <Tag color="blue">表达式契约</Tag>
            <Tag color="default">注册 Python 规则</Tag>
          </Space>
          <Alert
            type="info"
            showIcon
            message="规则使用已存储的表达式契约和注册实现，便于本地演示复核。"
          />
        </Space>
      </Card>
      {!canManageRules ? <Alert type="info" showIcon message="只读权限" /> : null}

      <div className="two-pane-grid">
        <Card title="规则" loading={loading}>
          {rules.length === 0 ? (
            <Empty description="暂无规则" />
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
                  title: "规则",
                  dataIndex: "rule_code",
                  render: (value: string, record) => (
                    <Space direction="vertical" size={2}>
                      <Typography.Text strong>{value}</Typography.Text>
                      <Typography.Text type="secondary">{record.name}</Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: "状态",
                  dataIndex: "enabled",
                  render: (value: boolean) => <Tag color={value ? "green" : "default"}>{value ? "启用" : "停用"}</Tag>,
                },
                { title: "版本", dataIndex: "version" },
              ]}
            />
          )}
        </Card>

        {selectedRule ? (
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <Card title="规则详情">
              <Form<RuleFormValues> form={ruleForm} layout="vertical" onFinish={(values) => void handleSave(values)}>
                <Space align="start" wrap>
                  <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                    <Input style={{ width: 280 }} />
                  </Form.Item>
                  <Form.Item name="version" label="版本" rules={[{ required: true }]}>
                    <Input style={{ width: 120 }} />
                  </Form.Item>
                  <Form.Item name="enabled" label="启用" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name="actor_name" label="操作人">
                    <Input style={{ width: 180 }} />
                  </Form.Item>
                </Space>
                <Space wrap style={{ marginBottom: 16 }}>
                  <Tag>{selectedRule.category}</Tag>
                  <Tag>{displayScenario(selectedRule.scenario)}</Tag>
                  <Tag color={selectedRule.severity === "high" ? "red" : "gold"}>{displaySeverity(selectedRule.severity)}</Tag>
                  <Tag>{selectedRule.rule_code}</Tag>
                  <Tag>{selectedRule.expression}</Tag>
                </Space>
                <Form.Item name="description" label="描述">
                  <Input />
                </Form.Item>
                <Form.Item
                  name="parameters_json"
                  label="参数 JSON"
                  rules={[{ required: true, message: "请输入参数 JSON" }]}
                >
                  <Input.TextArea rows={10} />
                </Form.Item>
                <Button type="primary" htmlType="submit" loading={saving} disabled={!canManageRules}>
                  保存规则
                </Button>
              </Form>
            </Card>

            <Card title="规则试算">
              <Form<EvaluateFormValues> form={evaluateForm} layout="vertical" onFinish={(values) => void handleEvaluate(values)}>
                <Space align="start" wrap>
                  <Form.Item name="task_id" label="任务" rules={[{ required: true }]}>
                    <Select
                      style={{ minWidth: 320 }}
                      options={tasks.map((task) => ({
                        label: `${task.task_no} - ${task.name}`,
                        value: task.id,
                      }))}
                    />
                  </Form.Item>
                </Space>
                <Form.Item name="parameters_json" label="临时参数覆盖 JSON">
                  <Input.TextArea rows={4} placeholder='{"tolerance_amount": 5}' />
                </Form.Item>
                <Button htmlType="submit" loading={evaluating} disabled={!canManageRules}>
                  执行试算
                </Button>
              </Form>
            </Card>

            <Card title="试算结果">
              <Table<AuditRuleEvaluateResult>
                size="small"
                rowKey={(record) => `${record.rule_code}-${record.business_key}`}
                dataSource={evaluationResults}
                pagination={false}
                scroll={{ x: 980 }}
                columns={[
                  { title: "业务键", dataIndex: "business_key" },
                  { title: "规则", dataIndex: "rule_code" },
                  { title: "版本", dataIndex: "rule_version" },
                  {
                    title: "状态",
                    dataIndex: "status",
                    render: (value: string) => <Tag color={statusColor(value)}>{displayStatus(value)}</Tag>,
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
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "实际值",
                    dataIndex: "actual_value",
                    render: (value: Record<string, unknown> | null) => (
                      <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 220 }}>
                        {formatJson(value)}
                      </Typography.Text>
                    ),
                  },
                  {
                    title: "证据",
                    dataIndex: "evidence",
                    render: (value: Record<string, unknown>) => `${evidenceCount(value)} 条证据`,
                  },
                ]}
              />
            </Card>
          </Space>
        ) : (
          <Card>
            <Empty description="请选择规则" />
          </Card>
        )}
      </div>
    </Space>
  );
}
