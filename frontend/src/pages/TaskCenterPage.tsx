import { Button, Card, Form, Input, InputNumber, Select, Space, Table, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useState } from "react";

import { createTask, listDocuments, listTasks, uploadDocument } from "../api/client";
import type { AuditTask, CreateTaskPayload, DocumentRecord, ProcurementDocType } from "../types/api";

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
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
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
    setDocuments(await listDocuments(taskId));
  }

  useEffect(() => {
    void refreshTasks().catch(() => message.error("Failed to load tasks"));
  }, []);

  useEffect(() => {
    if (selectedTaskId) {
      void refreshDocuments(selectedTaskId).catch(() => message.error("Failed to load documents"));
    } else {
      setDocuments([]);
    }
  }, [selectedTaskId]);

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
          columns={[
            { title: "Filename", dataIndex: "original_filename" },
            { title: "Doc Type", dataIndex: "doc_type" },
            { title: "Extension", dataIndex: "file_ext" },
            { title: "Size", dataIndex: "file_size" },
            { title: "Upload Status", dataIndex: "upload_status" },
            { title: "OCR Status", dataIndex: "ocr_status" },
          ]}
        />
      </Card>
    </Space>
  );
}
