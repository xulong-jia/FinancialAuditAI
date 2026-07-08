import { Alert, Button, Card, Empty, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import {
  downloadReport,
  generateControlTableReport,
  listReports,
  listTasks,
} from "../api/client";
import type { PageProps } from "../routes";
import type { AuditTask, ReportRecord } from "../types/api";
import { displayReportColumn, displayStatus } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

const procurementPreviewColumns = [
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
const salesPreviewColumns = [
  "business_key",
  "customer_name",
  "contract_no",
  "order_no",
  "delivery_no",
  "invoice_no",
  "receipt_no",
  "contract_amount",
  "invoice_amount",
  "receipt_amount",
  "amount_check",
  "revenue_check",
  "overall_status",
  "reviewer_comment",
];
const confirmationPreviewColumns = [
  "business_key",
  "confirmation_no",
  "counterparty_name",
  "sent_date",
  "replied_date",
  "book_amount",
  "confirmed_amount",
  "difference_amount",
  "exception_reason",
  "amount_check",
  "overall_status",
  "reviewer_comment",
];
const interviewPreviewColumns = [
  "business_key",
  "interviewee_name",
  "interview_date",
  "topics",
  "key_answers",
  "mentioned_amounts",
  "mentioned_counterparties",
  "signature_check",
  "overall_status",
  "reviewer_comment",
];
const contractReviewPreviewColumns = [
  "business_key",
  "contract_no",
  "contract_name",
  "counterparty_name",
  "amount_including_tax",
  "payment_terms",
  "delivery_terms",
  "special_clauses",
  "special_clause_check",
  "signature_seal_check",
  "key_terms_check",
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

export function ReportCenterPage({ currentUser }: PageProps) {
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const canGenerateReport = hasPermission(currentUser, "report:generate");

  async function refreshReports(taskId = selectedTaskId) {
    if (!taskId) {
      setReports([]);
      return;
    }
    setLoading(true);
    try {
      setReports(await listReports(taskId));
    } catch {
      message.error("报告加载失败");
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
        message.error("报告中心加载失败");
      } finally {
        setLoading(false);
      }
    }

    void loadInitialData();
  }, []);

  async function handleGenerateReport(fileFormat: "xlsx" | "csv" | "pdf" | "markdown") {
    if (!selectedTaskId) {
      message.warning("请先选择任务");
      return;
    }
    setLoading(true);
    try {
      await generateControlTableReport(selectedTaskId, {
        generated_by: currentUser.full_name,
        file_format: fileFormat,
      });
      await refreshReports(selectedTaskId);
      message.success(`${fileFormat.toUpperCase()} 报告已生成`);
    } catch {
      message.error("报告生成失败");
    } finally {
      setLoading(false);
    }
  }

  const latestReport = reports[0] ?? null;
  const previewRows = controlTablePreview(latestReport);
  const selectedTask = tasks.find((task) => task.id === selectedTaskId);
  const previewColumns =
    selectedTask?.scenario === "sales"
      ? salesPreviewColumns
      : selectedTask?.scenario === "confirmation"
        ? confirmationPreviewColumns
        : selectedTask?.scenario === "interview"
          ? interviewPreviewColumns
          : selectedTask?.scenario === "contract_review"
            ? contractReviewPreviewColumns
            : procurementPreviewColumns;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            报告中心
          </Typography.Title>
          <Select
            placeholder="选择任务"
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
          <Button
            type="primary"
            loading={loading}
            disabled={!selectedTaskId || !canGenerateReport}
            onClick={() => void handleGenerateReport("xlsx")}
          >
            生成 XLSX
          </Button>
          <Button
            loading={loading}
            disabled={!selectedTaskId || !canGenerateReport}
            onClick={() => void handleGenerateReport("csv")}
          >
            生成 CSV
          </Button>
          <Button
            loading={loading}
            disabled={!selectedTaskId || !canGenerateReport}
            onClick={() => void handleGenerateReport("pdf")}
          >
            生成 PDF
          </Button>
          <Button
            loading={loading}
            disabled={!selectedTaskId || !canGenerateReport}
            onClick={() => void handleGenerateReport("markdown")}
          >
            生成 Markdown
          </Button>
        </Space>
      </Card>
      {!canGenerateReport ? <Alert type="info" showIcon message="只读权限" /> : null}

      <Card title="报告状态">
        {latestReport ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>
              <Typography.Text strong>{latestReport.title}</Typography.Text>
              <Tag color={statusColor(latestReport.status)}>{displayStatus(latestReport.status)}</Tag>
              <Tag>{latestReport.file_format}</Tag>
              <Typography.Text type="secondary">生成时间 {latestReport.generated_at}</Typography.Text>
            </Space>
            <Alert
              type="info"
              showIcon
              message="使用边界"
              description={String(latestReport.summary.usage_boundary ?? "")}
            />
          </Space>
        ) : (
          <Empty description="暂无报告" />
        )}
      </Card>

      <Card title="控制表预览">
        <Table<Record<string, unknown>>
          rowKey={(record, index) => String(record.business_key ?? index)}
          loading={loading}
          dataSource={previewRows}
          pagination={false}
          scroll={{ x: 1100 }}
          columns={previewColumns.map((column) => ({
            title: displayReportColumn(column),
            dataIndex: column,
            render: (value: unknown) =>
              column === "overall_status" ? (
                <Tag color={statusColor(String(value ?? ""))}>{displayStatus(String(value ?? ""))}</Tag>
              ) : (
                <Typography.Text ellipsis={{ tooltip: String(value ?? "-") }} style={{ maxWidth: 220 }}>
                  {String(value ?? "-")}
                </Typography.Text>
              ),
          }))}
        />
      </Card>

      <Card title="报告历史">
        <Table<ReportRecord>
          rowKey="id"
          loading={loading}
          dataSource={reports}
          pagination={false}
          columns={[
            { title: "标题", dataIndex: "title" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag color={statusColor(value)}>{displayStatus(value)}</Tag>,
            },
            { title: "格式", dataIndex: "file_format" },
            { title: "生成人", dataIndex: "generated_by", render: (value: string | null) => value ?? "-" },
            { title: "生成时间", dataIndex: "generated_at" },
            {
              title: "下载",
              render: (_, record) => (
                <Button
                  size="small"
                  onClick={() => void downloadReport(record.id, `${record.title}.${record.file_format}`)}
                >
                  下载 {record.file_format.toUpperCase()}
                </Button>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
