import { Alert, Button, Card, Empty, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { createAgentRun, getAgentRun, listAgentSteps, resumeAgentRun, retryAgentRun } from "../api/client";
import type { AgentRun, AgentStep } from "../types/api";

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
      message.warning("Select a task first");
      return;
    }
    setLoading(true);
    try {
      const nextRun = await createAgentRun({ task_id: taskId });
      setRun(nextRun);
      setSteps(await listAgentSteps(nextRun.id));
      message.success("Agent workflow finished");
    } catch {
      message.error("Agent workflow failed to start");
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
      message.success("Retry finished");
    } catch {
      message.error("Retry failed");
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
      message.success("Agent workflow resumed");
    } catch {
      message.error("Human review queue is not cleared");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      title="Agent State Timeline"
      extra={
        <Space>
          {run ? <Tag color={statusColor(run.current_state)}>{run.current_state}</Tag> : null}
          {run?.status === "failed" ? (
            <Button onClick={() => void handleRetry()} loading={loading} disabled={!canRunAgent}>
              Retry Failed Step
            </Button>
          ) : null}
          {run?.status === "waiting_review" ? (
            <Button onClick={() => void handleResume()} loading={loading} disabled={!canRunAgent}>
              Resume After Review
            </Button>
          ) : null}
          <Button type="primary" onClick={() => void handleStart()} loading={loading} disabled={!taskId || !canRunAgent}>
            Start Agent Run
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        {run ? (
          <Space wrap>
            <Tag color={statusColor(run.status)}>{run.status}</Tag>
            <Typography.Text>workflow: {run.workflow_name}</Typography.Text>
            <Typography.Text type="secondary">run: {run.id}</Typography.Text>
          </Space>
        ) : (
          <Empty description="No agent run for the selected task in this view" />
        )}
        {run?.error ? <Alert type="error" showIcon message="Agent error" description={formatPayload(run.error)} /> : null}
        <Table<AgentStep>
          size="small"
          rowKey="id"
          dataSource={steps}
          pagination={false}
          scroll={{ x: 980 }}
          columns={[
            { title: "#", dataIndex: "step_order", width: 56 },
            { title: "Step", dataIndex: "step_name" },
            { title: "Tool", dataIndex: "tool_name" },
            {
              title: "Status",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
            },
            {
              title: "Duration",
              dataIndex: "duration_ms",
              render: (value: number | null) => (value == null ? "-" : `${value} ms`),
            },
            {
              title: "Input Refs",
              dataIndex: "input_payload",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: formatPayload(value) }} style={{ maxWidth: 220 }}>
                  {formatPayload(value)}
                </Typography.Text>
              ),
            },
            {
              title: "Output Refs",
              dataIndex: "output_payload",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: formatPayload(value) }} style={{ maxWidth: 240 }}>
                  {formatPayload(value)}
                </Typography.Text>
              ),
            },
            {
              title: "Error",
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
