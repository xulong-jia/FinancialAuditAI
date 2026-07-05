import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useState } from "react";

import {
  classifyDocument,
  createTask,
  extractDocument,
  listDocumentPages,
  listDocumentFields,
  linkDocuments,
  listAuditResults,
  listDocumentRelations,
  listDocuments,
  listTasks,
  runAudit,
  runOcr,
  updateDocument,
  uploadDocument,
} from "../api/client";
import type {
  AuditTask,
  AuditResult,
  ClassificationDocType,
  CreateTaskPayload,
  DocumentDocType,
  DocumentPage,
  DocumentRecord,
  DocumentRelation,
  ExtractedField,
} from "../types/api";
import type { PageProps } from "../routes";

const procurementDocTypes: { label: string; value: DocumentDocType }[] = [
  { label: "采购申请单", value: "purchase_request" },
  { label: "采购合同", value: "purchase_contract" },
  { label: "入库单", value: "warehouse_receipt" },
  { label: "发票", value: "invoice" },
  { label: "记账凭证", value: "accounting_voucher" },
  { label: "付款回单", value: "payment_receipt" },
];
const salesDocTypes: { label: string; value: DocumentDocType }[] = [
  { label: "销售合同", value: "sales_contract" },
  { label: "销售订单", value: "sales_order" },
  { label: "出库单", value: "delivery_order" },
  { label: "物流 / 签收单", value: "logistics_receipt" },
  { label: "销售发票", value: "sales_invoice" },
  { label: "收款凭证", value: "receipt_voucher" },
  { label: "记账凭证", value: "accounting_voucher" },
];
const confirmationDocTypes: { label: string; value: DocumentDocType }[] = [
  { label: "函证", value: "confirmation" },
  { label: "函证发函", value: "confirmation_request" },
  { label: "函证回函", value: "confirmation_reply" },
  { label: "函证差异调节", value: "confirmation_adjustment" },
];
const interviewDocTypes: { label: string; value: DocumentDocType }[] = [
  { label: "访谈记录", value: "interview_record" },
  { label: "访谈提纲", value: "interview_outline" },
  { label: "访谈签字页", value: "interview_signature_page" },
  { label: "访谈转写文本", value: "interview_transcript" },
];

const classificationDocTypes: { label: string; value: ClassificationDocType }[] = [
  ...procurementDocTypes,
  ...salesDocTypes.filter((option) => option.value !== "accounting_voucher"),
  ...confirmationDocTypes,
  ...interviewDocTypes,
  { label: "未知 / 需要复核", value: "unknown" },
];

function formatConfidence(value: number | null | undefined) {
  return value == null ? "-" : `${Math.round(value * 100)}%`;
}

function formatNormalized(value: Record<string, unknown> | null) {
  return value ? JSON.stringify(value) : "-";
}

function formatEvidence(value: Record<string, unknown>) {
  return JSON.stringify(value);
}

export function TaskCenterPage({ onNavigate }: PageProps) {
  const [form] = Form.useForm<CreateTaskPayload>();
  const [uploadForm] = Form.useForm<{ doc_type_hint: DocumentDocType }>();
  const [manualForm] = Form.useForm<{ doc_type: ClassificationDocType }>();
  const [tasks, setTasks] = useState<AuditTask[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [relations, setRelations] = useState<DocumentRelation[]>([]);
  const [auditResults, setAuditResults] = useState<AuditResult[]>([]);
  const [pages, setPages] = useState<DocumentPage[]>([]);
  const [fields, setFields] = useState<ExtractedField[]>([]);
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

  async function refreshRelations(taskId: string) {
    const nextRelations = await listDocumentRelations(taskId);
    setRelations(nextRelations);
  }

  async function refreshAuditResults(taskId: string) {
    const nextResults = await listAuditResults(taskId);
    setAuditResults(nextResults);
  }

  useEffect(() => {
    void refreshTasks().catch(() => message.error("Failed to load tasks"));
  }, []);

  useEffect(() => {
    if (selectedTaskId) {
      void refreshDocuments(selectedTaskId).catch(() => message.error("Failed to load documents"));
      void refreshRelations(selectedTaskId).catch(() => message.error("Failed to load document relations"));
      void refreshAuditResults(selectedTaskId).catch(() => message.error("Failed to load audit results"));
    } else {
      setDocuments([]);
      setRelations([]);
      setAuditResults([]);
      setSelectedDocumentId(null);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    if (selectedDocumentId) {
      void refreshPages(selectedDocumentId).catch(() => message.error("Failed to load pages"));
      void refreshFields(selectedDocumentId).catch(() => message.error("Failed to load fields"));
    } else {
      setPages([]);
      setFields([]);
      setSelectedPageNumber(null);
    }
  }, [selectedDocumentId]);

  useEffect(() => {
    const selectedDocument = documents.find((document) => document.id === selectedDocumentId);
    manualForm.setFieldsValue({ doc_type: selectedDocument?.doc_type ?? undefined });
  }, [documents, manualForm, selectedDocumentId]);

  async function refreshPages(documentId: string) {
    const nextPages = await listDocumentPages(documentId);
    setPages(nextPages);
    setSelectedPageNumber(nextPages[0]?.page_number ?? null);
  }

  async function refreshFields(documentId: string) {
    const nextFields = await listDocumentFields(documentId);
    setFields(nextFields);
  }

  async function handleCreateTask(values: CreateTaskPayload) {
    setLoading(true);
    try {
      const task = await createTask({ ...values, scenario: values.scenario ?? "procurement" });
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

  async function handleUpload(values: { doc_type_hint: DocumentDocType }) {
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

  async function handleClassify(documentId: string) {
    setLoading(true);
    try {
      const result = await classifyDocument(documentId);
      if (selectedTaskId) {
        await refreshDocuments(selectedTaskId);
      }
      setSelectedDocumentId(documentId);
      if (result.need_human_review) {
        message.warning("Classification needs human review");
      } else {
        message.success("Document classified");
      }
    } catch {
      message.error("Failed to classify document");
    } finally {
      setLoading(false);
    }
  }

  async function handleExtract(documentId: string) {
    setLoading(true);
    try {
      const nextFields = await extractDocument(documentId);
      setFields(nextFields);
      if (selectedTaskId) {
        await refreshDocuments(selectedTaskId);
      }
      setSelectedDocumentId(documentId);
      message.success("Fields extracted");
    } catch {
      message.error("Failed to extract fields");
    } finally {
      setLoading(false);
    }
  }

  async function handleLinkDocuments() {
    if (!selectedTaskId) {
      message.warning("Select a task first");
      return;
    }

    setLoading(true);
    try {
      const result = await linkDocuments(selectedTaskId);
      await refreshDocuments(selectedTaskId);
      setRelations(result.relations);
      if (result.warnings.length > 0) {
        message.warning(result.warnings.join(", "));
      } else {
        message.success("Documents linked");
      }
    } catch {
      message.error("Failed to link documents");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunAudit() {
    if (!selectedTaskId) {
      message.warning("Select a task first");
      return;
    }

    setLoading(true);
    try {
      const results = await runAudit(selectedTaskId);
      setAuditResults(results);
      message.success("Audit rules completed");
    } catch {
      message.error("Failed to run audit rules");
    } finally {
      setLoading(false);
    }
  }

  async function handleManualCorrection(values: { doc_type: ClassificationDocType }) {
    if (!selectedDocumentId || !selectedTaskId) {
      message.warning("Select a document first");
      return;
    }

    setLoading(true);
    try {
      await updateDocument(selectedDocumentId, {
        doc_type: values.doc_type,
        actor_name: "manual_reviewer",
      });
      await refreshDocuments(selectedTaskId);
      message.success("Document type updated");
    } catch {
      message.error("Failed to update document type");
    } finally {
      setLoading(false);
    }
  }

  function openAuditWorkbench() {
    if (selectedTaskId) {
      window.sessionStorage.setItem("audit_workbench_task_id", selectedTaskId);
    }
    onNavigate("audit-workbench");
  }

  function openReportCenter() {
    if (selectedTaskId) {
      window.sessionStorage.setItem("audit_workbench_task_id", selectedTaskId);
    }
    onNavigate("report-center");
  }

  const selectedDocument = documents.find((document) => document.id === selectedDocumentId) ?? null;
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? null;
  const uploadDocTypes =
    selectedTask?.scenario === "sales"
      ? salesDocTypes
      : selectedTask?.scenario === "confirmation"
        ? confirmationDocTypes
        : selectedTask?.scenario === "interview"
          ? interviewDocTypes
          : procurementDocTypes;
  const selectedPage = pages.find((page) => page.page_number === selectedPageNumber) ?? null;
  const documentNameById = Object.fromEntries(
    documents.map((document) => [document.id, document.original_filename]),
  );

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Typography.Title level={3}>Task Center</Typography.Title>
        <Form layout="inline" form={form} onFinish={handleCreateTask} initialValues={{ scenario: "procurement" }}>
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
          <Form.Item name="scenario">
            <Select
              style={{ width: 150 }}
              options={[
                { label: "Procurement", value: "procurement" },
                { label: "Sales", value: "sales" },
                { label: "Confirmation", value: "confirmation" },
                { label: "Interview", value: "interview" },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              Create
            </Button>
          </Form.Item>
          <Form.Item>
            <Button onClick={openAuditWorkbench}>Open Audit Workbench</Button>
          </Form.Item>
          <Form.Item>
            <Button onClick={openReportCenter}>Open Report Center</Button>
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
            <Select style={{ width: 220 }} placeholder="Document type" options={uploadDocTypes} />
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
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" loading={loading} disabled={!selectedTaskId} onClick={() => void handleLinkDocuments()}>
            Link Documents
          </Button>
        </Space>
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
            {
              title: "Business Key",
              dataIndex: "business_key",
              render: (value: string | null) => value ?? "-",
            },
            {
              title: "Doc Type",
              dataIndex: "doc_type",
              render: (value: DocumentRecord["doc_type"], record) => (
                <Space>
                  <Tag color={value === "unknown" ? "orange" : value ? "blue" : "default"}>
                    {value ?? "-"}
                  </Tag>
                  {record.review_status === "need_review" ? <Tag color="gold">Needs Review</Tag> : null}
                </Space>
              ),
            },
            {
              title: "Confidence",
              dataIndex: "doc_type_confidence",
              render: (value: number | null) => formatConfidence(value),
            },
            { title: "Extension", dataIndex: "file_ext" },
            { title: "Size", dataIndex: "file_size" },
            { title: "Upload Status", dataIndex: "upload_status" },
            { title: "OCR Status", dataIndex: "ocr_status" },
            { title: "Review Status", dataIndex: "review_status" },
            {
              title: "Classification Reason",
              dataIndex: "classification_reason",
              render: (value: string | null) =>
                value ? (
                  <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 260 }}>
                    {value}
                  </Typography.Text>
                ) : (
                  "-"
                ),
            },
            { title: "Pages", dataIndex: "page_count" },
            {
              title: "Action",
              render: (_, record) => (
                <Space>
                  <Button size="small" loading={loading} onClick={() => void handleRunOcr(record.id)}>
                    Run OCR
                  </Button>
                  <Button
                    size="small"
                    loading={loading}
                    disabled={record.ocr_status !== "completed"}
                    onClick={() => void handleClassify(record.id)}
                  >
                    Classify
                  </Button>
                  <Button
                    size="small"
                    loading={loading}
                    disabled={
                      record.ocr_status !== "completed" ||
                      !record.doc_type ||
                      record.doc_type === "unknown"
                    }
                    onClick={() => void handleExtract(record.id)}
                  >
                    Extract
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card title="Document Relations">
        <Table<DocumentRelation>
          rowKey="id"
          dataSource={relations}
          pagination={false}
          columns={[
            { title: "Business Key", dataIndex: "business_key" },
            { title: "Relation", dataIndex: "relation_type" },
            {
              title: "Confidence",
              dataIndex: "confidence",
              render: (value: number) => (
                <Space>
                  <Typography.Text>{formatConfidence(value)}</Typography.Text>
                  {value < 0.6 ? <Tag color="gold">Needs Review</Tag> : null}
                </Space>
              ),
            },
            {
              title: "Source",
              dataIndex: "source_document_id",
              render: (value: string) => documentNameById[value] ?? value,
            },
            {
              title: "Target",
              dataIndex: "target_document_id",
              render: (value: string) => documentNameById[value] ?? value,
            },
            {
              title: "Evidence",
              dataIndex: "evidence",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: formatEvidence(value) }} style={{ maxWidth: 320 }}>
                  {formatEvidence(value)}
                </Typography.Text>
              ),
            },
          ]}
        />
      </Card>

      <Card title="Audit Results">
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" loading={loading} disabled={!selectedTaskId} onClick={() => void handleRunAudit()}>
            Run Audit
          </Button>
        </Space>
        <Table<AuditResult>
          rowKey="id"
          dataSource={auditResults}
          pagination={false}
          columns={[
            { title: "Business Key", dataIndex: "business_key" },
            { title: "Rule", dataIndex: "rule_code" },
            {
              title: "Status",
              dataIndex: "status",
              render: (value: string, record) => (
                <Space>
                  <Tag color={value === "pass" ? "green" : value === "fail" ? "red" : "gold"}>
                    {value}
                  </Tag>
                  {record.review_status === "pending" ? <Tag color="orange">Needs Review</Tag> : null}
                </Space>
              ),
            },
            { title: "Severity", dataIndex: "severity" },
            {
              title: "Message",
              dataIndex: "message",
              render: (value: string) => (
                <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 280 }}>
                  {value}
                </Typography.Text>
              ),
            },
            {
              title: "Expected",
              dataIndex: "expected_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatNormalized(value) }} style={{ maxWidth: 220 }}>
                  {formatNormalized(value)}
                </Typography.Text>
              ),
            },
            {
              title: "Actual",
              dataIndex: "actual_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatNormalized(value) }} style={{ maxWidth: 220 }}>
                  {formatNormalized(value)}
                </Typography.Text>
              ),
            },
            {
              title: "Evidence",
              dataIndex: "evidence",
              render: (value: Record<string, unknown>) => (
                <Typography.Text ellipsis={{ tooltip: formatEvidence(value) }} style={{ maxWidth: 320 }}>
                  {formatEvidence(value)}
                </Typography.Text>
              ),
            },
          ]}
        />
      </Card>

      <Card title="Classification">
        {selectedDocument ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            {selectedDocument.review_status === "need_review" ? (
              <Alert
                type="warning"
                showIcon
                message="Human review required"
                description="The document type is unknown or classification confidence is below the MVP threshold."
              />
            ) : null}
            <Space wrap>
              <Typography.Text>
                Current type: <strong>{selectedDocument.doc_type ?? "-"}</strong>
              </Typography.Text>
              <Typography.Text>
                Confidence: <strong>{formatConfidence(selectedDocument.doc_type_confidence)}</strong>
              </Typography.Text>
            </Space>
            <Typography.Paragraph>
              {selectedDocument.classification_reason ?? "Run classification after OCR to view the reason."}
            </Typography.Paragraph>
            {selectedDocument.alternative_types?.length ? (
              <Space wrap>
                {selectedDocument.alternative_types.map((alternative) => (
                  <Tag key={alternative.doc_type}>
                    {alternative.doc_type}: {formatConfidence(alternative.confidence)}
                  </Tag>
                ))}
              </Space>
            ) : null}
            <Form layout="inline" form={manualForm} onFinish={handleManualCorrection}>
              <Form.Item
                name="doc_type"
                rules={[{ required: true, message: "Document type is required" }]}
              >
                <Select style={{ width: 240 }} options={classificationDocTypes} />
              </Form.Item>
              <Form.Item>
                <Button htmlType="submit" loading={loading}>
                  Save Manual Type
                </Button>
              </Form.Item>
            </Form>
          </Space>
        ) : (
          <Typography.Text type="secondary">Select a document to view classification.</Typography.Text>
        )}
      </Card>

      <Card title="Extracted Fields">
        {selectedDocument ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            {selectedDocument.extraction_status === "failed" ? (
              <Alert type="error" showIcon message="Field extraction failed" />
            ) : null}
            <Table<ExtractedField>
              rowKey="id"
              dataSource={fields}
              pagination={false}
              columns={[
                { title: "Field", dataIndex: "field_label" },
                { title: "Type", dataIndex: "field_type" },
                {
                  title: "Value",
                  dataIndex: "value_text",
                  render: (value: string | null, record) => (
                    <Space>
                      <Typography.Text>{value ?? "null"}</Typography.Text>
                      {!value && record.is_required ? <Tag color="red">Missing</Tag> : null}
                      {record.confidence != null && record.confidence < 0.6 ? (
                        <Tag color="gold">Low Confidence</Tag>
                      ) : null}
                    </Space>
                  ),
                },
                {
                  title: "Normalized",
                  dataIndex: "value_normalized",
                  render: (value: Record<string, unknown> | null) => (
                    <Typography.Text ellipsis={{ tooltip: formatNormalized(value) }} style={{ maxWidth: 260 }}>
                      {formatNormalized(value)}
                    </Typography.Text>
                  ),
                },
                {
                  title: "Confidence",
                  dataIndex: "confidence",
                  render: (value: number | null) => formatConfidence(value),
                },
                { title: "Page", dataIndex: "source_page" },
                {
                  title: "Source Text",
                  dataIndex: "source_text",
                  render: (value: string | null) =>
                    value ? (
                      <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 280 }}>
                        {value}
                      </Typography.Text>
                    ) : (
                      "-"
                    ),
                },
                {
                  title: "Warnings",
                  dataIndex: "warnings",
                  render: (warnings: string[]) =>
                    warnings.length ? (
                      <Space wrap>
                        {warnings.map((warning) => (
                          <Tag key={warning} color="orange">
                            {warning}
                          </Tag>
                        ))}
                      </Space>
                    ) : (
                      "-"
                    ),
                },
              ]}
            />
          </Space>
        ) : (
          <Typography.Text type="secondary">Select a document to view extracted fields.</Typography.Text>
        )}
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
