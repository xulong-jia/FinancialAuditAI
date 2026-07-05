import { Button, Card, Col, Empty, Row, Space, Statistic, Table, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { listAuditResults, listEvaluationResults, listTasks } from "../api/client";
import type { PageProps } from "../routes";
import type { AuditResult, AuditTask, EvaluationResult } from "../types/api";

function statusColor(status: string) {
  if (status === "completed") {
    return "green";
  }
  if (status === "failed") {
    return "red";
  }
  if (status === "reviewing") {
    return "gold";
  }
  return "blue";
}

function countBy(tasks: AuditTask[], key: keyof Pick<AuditTask, "status" | "scenario">) {
  return tasks.reduce<Record<string, number>>((counts, task) => {
    counts[String(task[key])] = (counts[String(task[key])] ?? 0) + 1;
    return counts;
  }, {});
}

export function DashboardPage({ onNavigate }: PageProps) {
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [auditResults, setAuditResults] = useState<AuditResult[]>([]);
  const [evaluationResults, setEvaluationResults] = useState<EvaluationResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadTasks() {
      setLoading(true);
      try {
        const nextTasks = await listTasks();
        setTasks(nextTasks);
        const [nextAuditResults, nextEvaluationResults] = await Promise.all([
          Promise.all(nextTasks.slice(0, 20).map((task) => listAuditResults(task.id).catch(() => []))),
          listEvaluationResults().catch(() => []),
        ]);
        setAuditResults(nextAuditResults.flat());
        setEvaluationResults(nextEvaluationResults);
      } catch {
        message.error("Failed to load dashboard");
      } finally {
        setLoading(false);
      }
    }

    void loadTasks();
  }, []);

  const statusCounts = useMemo(() => countBy(tasks, "status"), [tasks]);
  const scenarioCounts = useMemo(() => countBy(tasks, "scenario"), [tasks]);
  const activeCount = tasks.filter((task) => !["completed", "failed"].includes(task.status)).length;
  const reviewCount = statusCounts.reviewing ?? 0;
  const failedCount = statusCounts.failed ?? 0;
  const exceptionCounts = useMemo(() => countAuditResults(auditResults), [auditResults]);
  const passedResults = auditResults.filter((result) => result.status === "pass").length;
  const passRate = auditResults.length ? Math.round((passedResults / auditResults.length) * 1000) / 10 : 0;
  const recentEvaluations = evaluationResults.slice(0, 5);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
          <Typography.Title level={3} style={{ margin: 0 }}>
            Dashboard
          </Typography.Title>
          <Button type="primary" onClick={() => onNavigate("task-center")}>
            Open Task Center
          </Button>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Total Tasks" value={tasks.length} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Active Tasks" value={activeCount} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="In Review" value={reviewCount} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Failed" value={failedCount} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="Rule Pass Rate" value={passRate} suffix="%" loading={loading} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Tasks by Status">
            {Object.keys(statusCounts).length ? (
              <Space wrap>
                {Object.entries(statusCounts).map(([status, count]) => (
                  <Tag key={status} color={statusColor(status)}>
                    {status}: {count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description="No tasks" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Tasks by Scenario">
            {Object.keys(scenarioCounts).length ? (
              <Space wrap>
                {Object.entries(scenarioCounts).map(([scenario, count]) => (
                  <Tag key={scenario}>
                    {scenario}: {count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description="No tasks" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Exception Distribution">
            {Object.keys(exceptionCounts).length ? (
              <Space wrap>
                {Object.entries(exceptionCounts).map(([status, count]) => (
                  <Tag key={status} color={statusColor(status)}>
                    {status}: {count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description="No audit results" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Recent Evaluation Summary">
            {recentEvaluations.length ? (
              <Table<EvaluationResult>
                rowKey="id"
                size="small"
                dataSource={recentEvaluations}
                pagination={false}
                columns={[
                  { title: "Type", dataIndex: "eval_type" },
                  { title: "Dataset", dataIndex: "dataset_name" },
                  { title: "Samples", dataIndex: "sample_count" },
                  {
                    title: "Dataset Kind",
                    render: (_, record) => String(record.metrics.dataset_kind ?? "-"),
                  },
                ]}
              />
            ) : (
              <Empty description="No evaluations" />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="Recent Tasks">
        <Table<AuditTask>
          rowKey="id"
          loading={loading}
          dataSource={tasks.slice(0, 8)}
          pagination={false}
          columns={[
            { title: "Task No", dataIndex: "task_no" },
            { title: "Name", dataIndex: "name" },
            { title: "Scenario", dataIndex: "scenario" },
            {
              title: "Status",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
            },
            { title: "Risk", dataIndex: "risk_level", render: (value: string | null) => value ?? "-" },
            { title: "Company", dataIndex: "company_name", render: (value: string | null) => value ?? "-" },
          ]}
        />
      </Card>
    </Space>
  );
}

function countAuditResults(results: AuditResult[]) {
  return results.reduce<Record<string, number>>((counts, result) => {
    if (result.status !== "pass") {
      counts[result.status] = (counts[result.status] ?? 0) + 1;
    }
    return counts;
  }, {});
}
