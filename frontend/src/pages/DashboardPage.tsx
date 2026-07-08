import { Button, Card, Col, Empty, Row, Space, Statistic, Table, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { listAuditResults, listEvaluationResults, listTasks } from "../api/client";
import type { PageProps } from "../routes";
import type { AuditResult, AuditTask, EvaluationResult } from "../types/api";
import { displayEvalType, displayScenario, displayStatus } from "../utils/displayText";

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
        message.error("仪表盘加载失败");
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
            仪表盘
          </Typography.Title>
          <Button type="primary" onClick={() => onNavigate("task-center")}>
            打开任务中心
          </Button>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="总任务数" value={tasks.length} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="进行中任务" value={activeCount} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="复核中" value={reviewCount} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="失败" value={failedCount} loading={loading} />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card>
            <Statistic title="规则通过率" value={passRate} suffix="%" loading={loading} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="按状态统计任务">
            {Object.keys(statusCounts).length ? (
              <Space wrap>
                {Object.entries(statusCounts).map(([status, count]) => (
                  <Tag key={status} color={statusColor(status)}>
                    {displayStatus(status)}: {count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description="暂无任务" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="按场景统计任务">
            {Object.keys(scenarioCounts).length ? (
              <Space wrap>
                {Object.entries(scenarioCounts).map(([scenario, count]) => (
                  <Tag key={scenario}>
                    {displayScenario(scenario)}: {count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description="暂无任务" />
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="异常分布">
            {Object.keys(exceptionCounts).length ? (
              <Space wrap>
                {Object.entries(exceptionCounts).map(([status, count]) => (
                  <Tag key={status} color={statusColor(status)}>
                    {displayStatus(status)}: {count}
                  </Tag>
                ))}
              </Space>
            ) : (
              <Empty description="暂无审核结果" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="最近评测摘要">
            {recentEvaluations.length ? (
              <Table<EvaluationResult>
                rowKey="id"
                size="small"
                dataSource={recentEvaluations}
                pagination={false}
                columns={[
                  { title: "类型", dataIndex: "eval_type", render: (value: string) => displayEvalType(value) },
                  { title: "数据集", dataIndex: "dataset_name" },
                  { title: "样本数", dataIndex: "sample_count" },
                  {
                    title: "数据集类型",
                    render: (_, record) => String(record.metrics.dataset_kind ?? "-"),
                  },
                ]}
              />
            ) : (
              <Empty description="暂无评测" />
            )}
          </Card>
        </Col>
      </Row>

      <Card title="最近任务">
        <Table<AuditTask>
          rowKey="id"
          loading={loading}
          dataSource={tasks.slice(0, 8)}
          pagination={false}
          columns={[
            { title: "任务编号", dataIndex: "task_no" },
            { title: "名称", dataIndex: "name" },
            { title: "场景", dataIndex: "scenario", render: (value: string) => displayScenario(value) },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{displayStatus(value)}</Tag>,
            },
            { title: "风险", dataIndex: "risk_level", render: (value: string | null) => value ?? "-" },
            { title: "公司", dataIndex: "company_name", render: (value: string | null) => value ?? "-" },
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
