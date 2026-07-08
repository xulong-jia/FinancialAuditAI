import { Alert, Button, Card, Empty, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { createAgentRun, getAgentRun, listAgentSteps, resumeAgentRun, retryAgentRun } from "../api/client";
import type { AgentRun, AgentStep } from "../types/api";
import { displayStatus } from "../utils/displayText";

type AgentStateTimelineProps = {
  taskId: string | null;
  canRunAgent: boolean;
};

function statusColor(status: string) {
  if (status === "completed" || status === "pass") {
    return "green";
  }
  if (status === "failed" || status.endsWith("_FAILED")) {
    return "red";
  }
  if (status === "running") {
    return "blue";
  }
  if (status === "waiting_review" || status === "HUMAN_REVIEW_REQUIRED") {
    return "gold";
  }
  return "gold";
}

function formatPayload(value: Record<string, unknown> | null) {
  return value ? JSON.stringify(value) : "-";
}

export function AgentStateTimeline({ taskId, canRunAgent }: AgentStateTimelineProps) {
  const [run, setRun] = useState<AgentRun | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setRun(null);
    setSteps([]);
  }, [taskId]);

  async function refreshSteps(runId: string) {
    const [nextRun, nextSteps] = await Promise.all([getAgentRun(runId), listAgentSteps(runId)]);
    setRun(nextRun);
    setSteps(nextSteps);
  }

  async function handleStart() {
    if (!taskId) {
      message.warning("请先选择任务");
      return;
    }
    setLoading(true);
    try {
      const nextRun = await createAgentRun({ task_id: taskId });
      setRun(nextRun);
      setSteps(await listAgentSteps(nextRun.id));
      message.success("Agent 工作流已完成");
    } catch {
      message.error("Agent 工作流启动失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRetry() {
    if (!run) {
      return;
    }
    setLoading(true);
    try {
      const nextRun = await retryAgentRun(run.id);
      setRun(nextRun);
      await refreshSteps(nextRun.id);
      message.success("重试已完成");
    } catch {
      message.error("重试失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleResume() {
    if (!run) {
      return;
    }
    setLoading(true);
    try {
      const nextRun = await resumeAgentRun(run.id);
      setRun(nextRun);
      await refreshSteps(nextRun.id);
      message.success("Agent 工作流已继续");
    } catch {
      message.error("人工复核队列尚未清理");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      title="Agent 状态时间线"
      extra={
        <Space>
          {run ? <Tag color={statusColor(run.current_state)}>{displayStatus(run.current_state)}</Tag> : null}
          {run?.status === "failed" ? (
            <Button onClick={() => void handleRetry()} loading={loading} disabled={!canRunAgent}>
              重试失败步骤
            </Button>
          ) : null}
          {run?.status === "waiting_review" ? (
            <Button onClick={() => void handleResume()} loading={loading} disabled={!canRunAgent}>
              复核后继续
            </Button>
          ) : null}
          <Button type="primary" onClick={() => void handleStart()} loading={loading} disabled={!taskId || !canRunAgent}>
            启动 Agent
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        {run ? (
          <Space wrap>
            <Tag color={statusColor(run.status)}>{displayStatus(run.status)}</Tag>
            <Typography.Text>工作流: {run.workflow_name}</Typography.Text>
            <Typography.Text type="secondary">运行 ID: {run.id}</Typography.Text>
          </Space>
        ) : (
          <Empty description="当前视图暂无所选任务的 Agent 运行记录" />
        )}
        {run?.error ? <Alert type="error" showIcon message="Agent 错误" description={formatPayload(run.error)} /> : null}
        <Table<AgentStep>
          size="small"
          rowKey="id"
          dataSource={steps}
          pagination={false}
          scroll={{ x: 980 }}
          columns={[
            { title: "#", dataIndex: "step_order", width: 56 },
            { title: "步骤", dataIndex: "step_name" },
            { title: "工具", dataIndex: "tool_name" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{displayStatus(value)}</Tag>,
            },
            {
              title: "耗时",
              dataIndex: "duration_ms",
              render: (value: number | null) => (value == null ? "-" : `${value} ms`),
            },
            {
              title: "输入引用",
              dataIndex: "input_payload",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: formatPayload(value) }} style={{ maxWidth: 220 }}>
                  {formatPayload(value)}
                </Typography.Text>
              ),
            },
            {
              title: "输出引用",
              dataIndex: "output_payload",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: formatPayload(value) }} style={{ maxWidth: 240 }}>
                  {formatPayload(value)}
                </Typography.Text>
              ),
            },
            {
              title: "错误",
              dataIndex: "error",
              render: (value: Record<string, unknown> | null) =>
                value ? (
                  <Typography.Text type="danger" ellipsis={{ tooltip: formatPayload(value) }} style={{ maxWidth: 220 }}>
                    {formatPayload(value)}
                  </Typography.Text>
                ) : (
                  "-"
                ),
            },
          ]}
        />
      </Space>
    </Card>
  );
}
