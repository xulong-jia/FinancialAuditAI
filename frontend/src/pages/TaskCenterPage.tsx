import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useState } from "react";

import { createTask, listDocumentPages, listDocuments, listTasks, runOcr, uploadDocument } from "../api/client";
import type { AuditTask, CreateTaskPayload, DocumentPage, DocumentRecord, ProcurementDocType } from "../types/api";

const docTypes: { label: string; value: ProcurementDocType }[] = [
  { label: "采购申请单", value: "purchase_request" },
  { label: "采购合同", value: "purchase_contract" },
  { label: "入库单", value: "warehouse_receipt" },
  { label: "发票", value: "invoice" },
  { label: "记账凭证", value: "accounting_voucher" },
  { label: "付款回单", value: "payment_receipt" },
];

export function TaskCenterPage() {
  const [form] = Form.useForm<CreateTaskPayload>();
  const [uploadForm] = Form.useForm<{ doc_type_hint: ProcurementDocType }>();
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [pages, setPages] = useState<DocumentPage[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [selectedPageNumber, setSelectedPageNumber] = useState<number | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [loading, setLoading] = useState(false);

  async function refreshTasks() {
    const nextTasks = await listTasks();
    setTasks(nextTasks);
    if (!selectedTaskId && nextTasks.length > 0) {
      setSelectedTaskId(nextTasks[0].id);
    }
  }

  async function refreshDocuments(taskId: string) {
    const nextDocuments = await listDocuments(taskId);
    setDocuments(nextDocuments);
    if (!selectedDocumentId && nextDocuments.length > 0) {
      setSelectedDocumentId(nextDocuments[0].id);
    }
  }

  useEffect(() => {
    void refreshTasks().catch(() => message.error("Failed to load tasks"));
  }, []);

  useEffect(() => {
    if (selectedTaskId) {
      void refreshDocuments(selectedTaskId).catch(() => message.error("Failed to load documents"));
    } else {
      setDocuments([]);
      setSelectedDocumentId(null);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    if (selectedDocumentId) {
      void refreshPages(selectedDocumentId).catch(() => message.error("Failed to load pages"));
    } else {
      setPages([]);
      setSelectedPageNumber(null);
    }
  }, [selectedDocumentId]);

  async function refreshPages(documentId: string) {
    const nextPages = await listDocumentPages(documentId);
    setPages(nextPages);
    setSelectedPageNumber(nextPages[0]?.page_number ?? null);
  }

  async function handleCreateTask(values: CreateTaskPayload) {
    setLoading(true);
    try {
      const task = await createTask({ ...values, scenario: "procurement" });
      form.resetFields();
      await refreshTasks();
      setSelectedTaskId(task.id);
      message.success("Task created");
    } catch {
      message.error("Failed to create task");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(values: { doc_type_hint: ProcurementDocType }) {
    const originFile = fileList[0]?.originFileObj;
    if (!selectedTaskId || !originFile) {
      message.warning("Select a task and file first");
      return;
    }

    setLoading(true);
    try {
      await uploadDocument(selectedTaskId, originFile, values.doc_type_hint);
      setFileList([]);
      uploadForm.resetFields();
      await refreshTasks();
      await refreshDocuments(selectedTaskId);
      message.success("Document uploaded");
    } catch {
      message.error("Failed to upload document");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunOcr(documentId: string) {
    setLoading(true);
    try {
      const document = await runOcr(documentId);
      if (selectedTaskId) {
        await refreshDocuments(selectedTaskId);
      }
      await refreshPages(document.id);
      setSelectedDocumentId(document.id);
      if (document.ocr_status === "failed") {
        message.error("OCR failed");
      } else {
        message.success("OCR completed");
      }
    } catch {
      message.error("Failed to run OCR");
    } finally {
      setLoading(false);
    }
  }

  const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? null;
  const selectedPage = pages.find((page) => page.page_number === selectedPageNumber) ?? null;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Typography.Title level={3}>Task Center</Typography.Title>
        <Form layout="inline" form={form} onFinish={handleCreateTask}>
          <Form.Item name="name" rules={[{ required: true, message: "Task name is required" }]}>
            <Input placeholder="Task name" />
          </Form.Item>
          <Form.Item name="project_name">
            <Input placeholder="Project" />
          </Form.Item>
          <Form.Item name="company_name">
            <Input placeholder="Company" />
          </Form.Item>
          <Form.Item name="fiscal_year">
            <InputNumber placeholder="Fiscal year" min={1900} max={2100} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              Create
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="Tasks">
        <Table<AuditTask>
          rowKey="id"
          dataSource={tasks}
          pagination={false}
          rowSelection={{
            type: "radio",
            selectedRowKeys: selectedTaskId ? [selectedTaskId] : [],
            onChange: (keys) => setSelectedTaskId(String(keys[0])),
          }}
          columns={[
            { title: "Task No", dataIndex: "task_no" },
            { title: "Name", dataIndex: "name" },
            { title: "Scenario", dataIndex: "scenario" },
            { title: "Status", dataIndex: "status" },
            { title: "Company", dataIndex: "company_name" },
          ]}
        />
      </Card>

      <Card title="Document Upload">
        <Form layout="inline" form={uploadForm} onFinish={handleUpload}>
          <Form.Item
            name="doc_type_hint"
            rules={[{ required: true, message: "Document type is required" }]}
          >
            <Select style={{ width: 220 }} placeholder="Document type" options={docTypes} />
          </Form.Item>
          <Form.Item>
            <Upload
              beforeUpload={() => false}
              fileList={fileList}
              maxCount={1}
              onChange={({ fileList: nextFileList }) => setFileList(nextFileList)}
            >
              <Button>Select file</Button>
            </Upload>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!selectedTaskId}>
              Upload
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="Documents">
        <Table<DocumentRecord>
          rowKey="id"
          dataSource={documents}
          pagination={false}
          rowSelection={{
            type: "radio",
            selectedRowKeys: selectedDocumentId ? [selectedDocumentId] : [],
            onChange: (keys) => setSelectedDocumentId(String(keys[0])),
          }}
          columns={[
            { title: "Filename", dataIndex: "original_filename" },
            { title: "Doc Type", dataIndex: "doc_type" },
            { title: "Extension", dataIndex: "file_ext" },
            { title: "Size", dataIndex: "file_size" },
            { title: "Upload Status", dataIndex: "upload_status" },
            { title: "OCR Status", dataIndex: "ocr_status" },
            { title: "Pages", dataIndex: "page_count" },
            {
              title: "Action",
              render: (_, record) => (
                <Button size="small" loading={loading} onClick={() => void handleRunOcr(record.id)}>
                  Run OCR
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="OCR Pages">
        {selectedDocument?.ocr_status === "failed" ? (
          <Alert
            type="error"
            showIcon
            message="OCR failed"
            description={selectedDocument.ocr_error ?? "Unknown OCR error"}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <Space direction="vertical" style={{ width: "100%" }}>
          <Select
            placeholder="Select page"
            style={{ width: 180 }}
            value={selectedPageNumber ?? undefined}
            options={pages.map((page) => ({
              label: `Page ${page.page_number}`,
              value: page.page_number,
            }))}
            onChange={setSelectedPageNumber}
            disabled={pages.length === 0}
          />
          {selectedPage ? (
            <>
              {selectedPage.warnings.length > 0 ? (
                <Alert
                  type="warning"
                  showIcon
                  message={selectedPage.warnings.join(", ")}
                />
              ) : null}
              <pre
                style={{
                  minHeight: 220,
                  whiteSpace: "pre-wrap",
                  background: "#f5f5f5",
                  padding: 16,
                  margin: 0,
                }}
              >
                {selectedPage.raw_text || "(empty page text)"}
              </pre>
            </>
          ) : (
            <Typography.Text type="secondary">Run OCR to view page text.</Typography.Text>
          )}
        </Space>
      </Card>
    </Space>
  );
}
