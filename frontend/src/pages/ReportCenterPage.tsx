import { Alert, Button, Card, Empty, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import {
  generateControlTableReport,
  listReports,
  listTasks,
  reportDownloadUrl,
} from "../api/client";
import type { PageProps } from "../routes";
import type { AuditTask, ReportRecord } from "../types/api";

const previewColumns = [
  "business_key",
  "supplier_name",
  "contract_no",
  "contract_amount",
  "invoice_amount",
  "payment_amount",
  "amount_check",
  "overall_status",
  "reviewer_comment",
];

function statusColor(status: string) {
  if (status === "completed" || status === "pass") {
    return "green";
  }
  if (status === "failed" || status === "fail") {
    return "red";
  }
  if (status === "warning" || status === "need_review") {
    return "gold";
  }
  return "default";
}

function controlTablePreview(report: ReportRecord | null): Record<string, unknown>[] {
  const value = report?.summary.control_table_preview;
  return Array.isArray(value) ? value.filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null) : [];
}

export function ReportCenterPage(_props: PageProps) {
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  async function refreshReports(taskId = selectedTaskId) {
    if (!taskId) {
      setReports([]);
      return;
    }
    setLoading(true);
    try {
      setReports(await listReports(taskId));
    } catch {
      message.error("Failed to load reports");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    async function loadInitialData() {
      setLoading(true);
      try {
        const nextTasks = await listTasks();
        const preferredTaskId = window.sessionStorage.getItem("audit_workbench_task_id") ?? undefined;
        const taskId = nextTasks.find((task) => task.id === preferredTaskId)?.id ?? nextTasks[0]?.id;
        setTasks(nextTasks);
        setSelectedTaskId(taskId);
        setReports(taskId ? await listReports(taskId) : []);
      } catch {
        message.error("Failed to load report center");
      } finally {
        setLoading(false);
      }
    }

    void loadInitialData();
  }, []);

  async function handleGenerateReport() {
    if (!selectedTaskId) {
      message.warning("Select a task first");
      return;
    }
    setLoading(true);
    try {
      await generateControlTableReport(selectedTaskId, { generated_by: "reporter" });
      await refreshReports(selectedTaskId);
      message.success("Report generated");
    } catch {
      message.error("Failed to generate report");
    } finally {
      setLoading(false);
    }
  }

  const latestReport = reports[0] ?? null;
  const previewRows = controlTablePreview(latestReport);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            Report Center
          </Typography.Title>
          <Select
            placeholder="Select task"
            style={{ minWidth: 320 }}
            value={selectedTaskId}
            options={tasks.map((task) => ({
              label: `${task.task_no} - ${task.name}`,
              value: task.id,
            }))}
            onChange={(taskId) => {
              setSelectedTaskId(taskId);
              window.sessionStorage.setItem("audit_workbench_task_id", taskId);
              void refreshReports(taskId);
            }}
          />
          <Button type="primary" loading={loading} disabled={!selectedTaskId} onClick={() => void handleGenerateReport()}>
            Generate XLSX
          </Button>
        </Space>
      </Card>

      <Card title="Report Status">
        {latestReport ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>
              <Typography.Text strong>{latestReport.title}</Typography.Text>
              <Tag color={statusColor(latestReport.status)}>{latestReport.status}</Tag>
              <Tag>{latestReport.file_format}</Tag>
              <Typography.Text type="secondary">Generated at {latestReport.generated_at}</Typography.Text>
            </Space>
            <Alert
              type="info"
              showIcon
              message="Usage boundary"
              description={String(latestReport.summary.usage_boundary ?? "")}
            />
          </Space>
        ) : (
          <Empty description="No reports yet" />
        )}
      </Card>

      <Card title="Control Table Preview">
        <Table<Record<string, unknown>>
          rowKey={(record, index) => String(record.business_key ?? index)}
          loading={loading}
          dataSource={previewRows}
          pagination={false}
          scroll={{ x: 1100 }}
          columns={previewColumns.map((column) => ({
            title: column,
            dataIndex: column,
            render: (value: unknown) =>
              column === "overall_status" ? (
                <Tag color={statusColor(String(value ?? ""))}>{String(value ?? "-")}</Tag>
              ) : (
                <Typography.Text ellipsis={{ tooltip: String(value ?? "-") }} style={{ maxWidth: 220 }}>
                  {String(value ?? "-")}
                </Typography.Text>
              ),
          }))}
        />
      </Card>

      <Card title="Report History">
        <Table<ReportRecord>
          rowKey="id"
          loading={loading}
          dataSource={reports}
          pagination={false}
          columns={[
            { title: "Title", dataIndex: "title" },
            {
              title: "Status",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{value}</Tag>,
            },
            { title: "Format", dataIndex: "file_format" },
            { title: "Generated By", dataIndex: "generated_by", render: (value: string | null) => value ?? "-" },
            { title: "Generated At", dataIndex: "generated_at" },
            {
              title: "Download",
              render: (_, record) => (
                <Button size="small" href={reportDownloadUrl(record.id)}>
                  Download XLSX
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
