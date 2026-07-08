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
  runTask,
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
import { displayDocType, displayFieldType, displayScenario, displaySeverity, displayStatus } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

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
const contractReviewDocTypes: { label: string; value: DocumentDocType }[] = [
  { label: "合同审核文档", value: "contract_review" },
  { label: "重大合同", value: "material_contract" },
  { label: "补充协议", value: "supplemental_agreement" },
  { label: "框架协议", value: "framework_agreement" },
  { label: "合同附件", value: "contract_attachment" },
];
const knowledgeDocTypes: { label: string; value: DocumentDocType }[] = [
  { label: "招股说明书 / 募集说明书", value: "prospectus" },
  { label: "问询函", value: "inquiry_letter" },
  { label: "法规 / 准则", value: "regulation" },
];

const classificationDocTypes: { label: string; value: ClassificationDocType }[] = [
  ...procurementDocTypes,
  ...salesDocTypes.filter((option) => option.value !== "accounting_voucher"),
  ...confirmationDocTypes,
  ...interviewDocTypes,
  ...contractReviewDocTypes,
  ...knowledgeDocTypes,
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

export function TaskCenterPage({ onNavigate, currentUser }: PageProps) {
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
    void refreshTasks().catch(() => message.error("任务加载失败"));
  }, []);

  useEffect(() => {
    if (selectedTaskId) {
      void refreshDocuments(selectedTaskId).catch(() => message.error("文档加载失败"));
      void refreshRelations(selectedTaskId).catch(() => message.error("文档关联加载失败"));
      void refreshAuditResults(selectedTaskId).catch(() => message.error("审核结果加载失败"));
    } else {
      setDocuments([]);
      setRelations([]);
      setAuditResults([]);
      setSelectedDocumentId(null);
    }
  }, [selectedTaskId]);

  useEffect(() => {
    if (selectedDocumentId) {
      void refreshPages(selectedDocumentId).catch(() => message.error("页面加载失败"));
      void refreshFields(selectedDocumentId).catch(() => message.error("字段加载失败"));
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
      message.success("任务已创建");
    } catch {
      message.error("任务创建失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpload(values: { doc_type_hint: DocumentDocType }) {
    const originFile = fileList[0]?.originFileObj;
    if (!selectedTaskId || !originFile) {
      message.warning("请先选择任务和文件");
      return;
    }

    setLoading(true);
    try {
      await uploadDocument(selectedTaskId, originFile, values.doc_type_hint);
      setFileList([]);
      uploadForm.resetFields();
      await refreshTasks();
      await refreshDocuments(selectedTaskId);
      message.success("文档已上传");
    } catch {
      message.error("文档上传失败");
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
        message.error("OCR 失败");
      } else {
        message.success("OCR 已完成");
      }
    } catch {
      message.error("OCR 执行失败");
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
        message.warning("文档分类需要人工复核");
      } else {
        message.success("文档已分类");
      }
    } catch {
      message.error("文档分类失败");
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
      message.success("字段已抽取");
    } catch {
      message.error("字段抽取失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleLinkDocuments() {
    if (!selectedTaskId) {
      message.warning("请先选择任务");
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
        message.success("文档已归集");
      }
    } catch {
      message.error("文档归集失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunAudit() {
    if (!selectedTaskId) {
      message.warning("请先选择任务");
      return;
    }

    setLoading(true);
    try {
      const results = await runAudit(selectedTaskId);
      setAuditResults(results);
      message.success("审核规则已完成");
    } catch {
      message.error("审核规则执行失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunTaskContract() {
    if (!selectedTaskId) {
      message.warning("请先选择任务");
      return;
    }

    setLoading(true);
    try {
      const result = await runTask(selectedTaskId);
      await refreshTasks();
      message.info(`任务状态: ${displayStatus(result.status)}`);
    } catch {
      message.error("任务合约执行失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleManualCorrection(values: { doc_type: ClassificationDocType }) {
    if (!selectedDocumentId || !selectedTaskId) {
      message.warning("请先选择文档");
      return;
    }

    setLoading(true);
    try {
      await updateDocument(selectedDocumentId, {
        doc_type: values.doc_type,
        actor_name: currentUser.full_name,
      });
      await refreshDocuments(selectedTaskId);
      message.success("文档类型已更新");
    } catch {
      message.error("文档类型更新失败");
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
      ? [...salesDocTypes, ...knowledgeDocTypes]
      : selectedTask?.scenario === "confirmation"
        ? [...confirmationDocTypes, ...knowledgeDocTypes]
        : selectedTask?.scenario === "interview"
          ? [...interviewDocTypes, ...knowledgeDocTypes]
          : selectedTask?.scenario === "contract_review"
            ? [...contractReviewDocTypes, ...knowledgeDocTypes]
            : [...procurementDocTypes, ...knowledgeDocTypes];
  const selectedPage = pages.find((page) => page.page_number === selectedPageNumber) ?? null;
  const documentNameById = Object.fromEntries(
    documents.map((document) => [document.id, document.original_filename]),
  );
  const canCreateTask = hasPermission(currentUser, "task:create");
  const canUpdateTask = hasPermission(currentUser, "task:update");
  const canUploadDocument = hasPermission(currentUser, "document:upload");
  const canProcessDocument = hasPermission(currentUser, "document:process");
  const canRunAudit = hasPermission(currentUser, "audit:run");

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Typography.Title level={3}>任务中心</Typography.Title>
        <Form layout="inline" form={form} onFinish={handleCreateTask} initialValues={{ scenario: "procurement" }}>
          <Form.Item name="name" rules={[{ required: true, message: "请输入任务名称" }]}>
            <Input placeholder="任务名称" />
          </Form.Item>
          <Form.Item name="project_name">
            <Input placeholder="项目" />
          </Form.Item>
          <Form.Item name="company_name">
            <Input placeholder="公司" />
          </Form.Item>
          <Form.Item name="fiscal_year">
            <InputNumber placeholder="会计年度" min={1900} max={2100} />
          </Form.Item>
          <Form.Item name="scenario">
            <Select
              style={{ width: 150 }}
              options={[
                { label: "采购穿行", value: "procurement" },
                { label: "销售穿行", value: "sales" },
                { label: "函证", value: "confirmation" },
                { label: "访谈", value: "interview" },
                { label: "合同审核", value: "contract_review" },
              ]}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!canCreateTask}>
              创建任务
            </Button>
          </Form.Item>
          <Form.Item>
            <Button onClick={openAuditWorkbench}>打开审核工作台</Button>
          </Form.Item>
          <Form.Item>
            <Button onClick={openReportCenter}>打开报告中心</Button>
          </Form.Item>
          <Form.Item>
            <Button
              loading={loading}
              disabled={!selectedTaskId || !canUpdateTask}
              onClick={() => void handleRunTaskContract()}
            >
              执行任务
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="任务列表">
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
            { title: "任务编号", dataIndex: "task_no" },
            { title: "名称", dataIndex: "name" },
            { title: "场景", dataIndex: "scenario", render: (value: string) => displayScenario(value) },
            { title: "状态", dataIndex: "status", render: (value: string) => displayStatus(value) },
            { title: "公司", dataIndex: "company_name" },
          ]}
        />
      </Card>

      <Card title="文档上传">
        <Form layout="inline" form={uploadForm} onFinish={handleUpload}>
          <Form.Item
            name="doc_type_hint"
            rules={[{ required: true, message: "请选择文档类型" }]}
          >
            <Select style={{ width: 220 }} placeholder="文档类型" options={uploadDocTypes} />
          </Form.Item>
          <Form.Item>
            <Upload
              accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,application/pdf,image/png,image/jpeg,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              beforeUpload={() => false}
              fileList={fileList}
              maxCount={1}
              onChange={({ fileList: nextFileList }) => setFileList(nextFileList)}
              disabled={!canUploadDocument}
            >
              <Button disabled={!canUploadDocument}>选择文档</Button>
            </Upload>
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              disabled={!selectedTaskId || !canUploadDocument}
            >
              上传
            </Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="文档">
        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            loading={loading}
            disabled={!selectedTaskId || !canProcessDocument}
            onClick={() => void handleLinkDocuments()}
          >
            归集文档
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
            { title: "文件名", dataIndex: "original_filename" },
            {
              title: "业务键",
              dataIndex: "business_key",
              render: (value: string | null) => value ?? "-",
            },
            {
              title: "文档类型",
              dataIndex: "doc_type",
              render: (value: DocumentRecord["doc_type"], record) => (
                <Space>
                  <Tag color={value === "unknown" ? "orange" : value ? "blue" : "default"}>
                    {displayDocType(value)}
                  </Tag>
                  {record.review_status === "need_review" ? <Tag color="gold">待复核</Tag> : null}
                </Space>
              ),
            },
            {
              title: "置信度",
              dataIndex: "doc_type_confidence",
              render: (value: number | null) => formatConfidence(value),
            },
            { title: "扩展名", dataIndex: "file_ext" },
            { title: "大小", dataIndex: "file_size" },
            { title: "上传状态", dataIndex: "upload_status", render: (value: string) => displayStatus(value) },
            { title: "OCR 状态", dataIndex: "ocr_status", render: (value: string) => displayStatus(value) },
            { title: "复核状态", dataIndex: "review_status", render: (value: string) => displayStatus(value) },
            {
              title: "分类原因",
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
            { title: "页数", dataIndex: "page_count" },
            {
              title: "操作",
              render: (_, record) => (
                <Space>
                  <Button
                    size="small"
                    loading={loading}
                    disabled={!canProcessDocument}
                    onClick={() => void handleRunOcr(record.id)}
                  >
                    执行 OCR
                  </Button>
                  <Button
                    size="small"
                    loading={loading}
                    disabled={!canProcessDocument || record.ocr_status !== "completed"}
                    onClick={() => void handleClassify(record.id)}
                  >
                    文档分类
                  </Button>
                  <Button
                    size="small"
                    loading={loading}
                    disabled={
                      !canProcessDocument ||
                      record.ocr_status !== "completed" ||
                      !record.doc_type ||
                      record.doc_type === "unknown"
                    }
                    onClick={() => void handleExtract(record.id)}
                  >
                    字段抽取
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card title="文档关联">
        <Table<DocumentRelation>
          rowKey="id"
          dataSource={relations}
          pagination={false}
          columns={[
            { title: "业务键", dataIndex: "business_key" },
            { title: "关联关系", dataIndex: "relation_type" },
            {
              title: "置信度",
              dataIndex: "confidence",
              render: (value: number) => (
                <Space>
                  <Typography.Text>{formatConfidence(value)}</Typography.Text>
                  {value < 0.6 ? <Tag color="gold">待复核</Tag> : null}
                </Space>
              ),
            },
            {
              title: "来源",
              dataIndex: "source_document_id",
              render: (value: string) => documentNameById[value] ?? value,
            },
            {
              title: "目标",
              dataIndex: "target_document_id",
              render: (value: string) => documentNameById[value] ?? value,
            },
            {
              title: "证据",
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

      <Card title="审核结果">
        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            loading={loading}
            disabled={!selectedTaskId || !canRunAudit}
            onClick={() => void handleRunAudit()}
          >
            执行审核
          </Button>
        </Space>
        <Table<AuditResult>
          rowKey="id"
          dataSource={auditResults}
          pagination={false}
          columns={[
            { title: "业务键", dataIndex: "business_key" },
            { title: "规则", dataIndex: "rule_code" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string, record) => (
                <Space>
                  <Tag color={value === "pass" ? "green" : value === "fail" ? "red" : "gold"}>
                    {displayStatus(value)}
                  </Tag>
                  {record.review_status === "pending" ? <Tag color="orange">待复核</Tag> : null}
                </Space>
              ),
            },
            { title: "严重程度", dataIndex: "severity", render: (value: string) => displaySeverity(value) },
            {
              title: "消息",
              dataIndex: "message",
              render: (value: string) => (
                <Typography.Text ellipsis={{ tooltip: value }} style={{ maxWidth: 280 }}>
                  {value}
                </Typography.Text>
              ),
            },
            {
              title: "预期值",
              dataIndex: "expected_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatNormalized(value) }} style={{ maxWidth: 220 }}>
                  {formatNormalized(value)}
                </Typography.Text>
              ),
            },
            {
              title: "实际值",
              dataIndex: "actual_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatNormalized(value) }} style={{ maxWidth: 220 }}>
                  {formatNormalized(value)}
                </Typography.Text>
              ),
            },
            {
              title: "证据",
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

      <Card title="文档分类">
        {selectedDocument ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            {selectedDocument.review_status === "need_review" ? (
              <Alert
                type="warning"
                showIcon
                message="需要人工复核"
                description="文档类型未知，或分类置信度低于本地演示阈值。"
              />
            ) : null}
            <Space wrap>
              <Typography.Text>
                当前类型: <strong>{displayDocType(selectedDocument.doc_type)}</strong>
              </Typography.Text>
              <Typography.Text>
                置信度: <strong>{formatConfidence(selectedDocument.doc_type_confidence)}</strong>
              </Typography.Text>
            </Space>
            <Typography.Paragraph>
              {selectedDocument.classification_reason ?? "OCR 后执行文档分类即可查看分类原因。"}
            </Typography.Paragraph>
            {selectedDocument.alternative_types?.length ? (
              <Space wrap>
                {selectedDocument.alternative_types.map((alternative) => (
                  <Tag key={alternative.doc_type}>
                    {displayDocType(alternative.doc_type)}: {formatConfidence(alternative.confidence)}
                  </Tag>
                ))}
              </Space>
            ) : null}
            <Form layout="inline" form={manualForm} onFinish={handleManualCorrection}>
              <Form.Item
                name="doc_type"
                rules={[{ required: true, message: "请选择文档类型" }]}
              >
                <Select style={{ width: 240 }} options={classificationDocTypes} />
              </Form.Item>
              <Form.Item>
                <Button htmlType="submit" loading={loading} disabled={!canProcessDocument}>
                  保存人工类型
                </Button>
              </Form.Item>
            </Form>
          </Space>
        ) : (
          <Typography.Text type="secondary">请选择文档查看分类结果。</Typography.Text>
        )}
      </Card>

      <Card title="抽取字段">
        {selectedDocument ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            {selectedDocument.extraction_status === "failed" ? (
              <Alert type="error" showIcon message="字段抽取失败" />
            ) : null}
            <Table<ExtractedField>
              rowKey="id"
              dataSource={fields}
              pagination={false}
              columns={[
                { title: "字段", dataIndex: "field_label" },
                { title: "类型", dataIndex: "field_type", render: (value: string) => displayFieldType(value) },
                {
                  title: "值",
                  dataIndex: "value_text",
                  render: (value: string | null, record) => (
                    <Space>
                      <Typography.Text>{value ?? "null"}</Typography.Text>
                      {!value && record.is_required ? <Tag color="red">缺失</Tag> : null}
                      {record.confidence != null && record.confidence < 0.6 ? (
                        <Tag color="gold">低置信度</Tag>
                      ) : null}
                    </Space>
                  ),
                },
                {
                  title: "标准化值",
                  dataIndex: "value_normalized",
                  render: (value: Record<string, unknown> | null) => (
                    <Typography.Text ellipsis={{ tooltip: formatNormalized(value) }} style={{ maxWidth: 260 }}>
                      {formatNormalized(value)}
                    </Typography.Text>
                  ),
                },
                {
                  title: "置信度",
                  dataIndex: "confidence",
                  render: (value: number | null) => formatConfidence(value),
                },
                { title: "页码", dataIndex: "source_page" },
                {
                  title: "来源文本",
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
                  title: "警告",
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
          <Typography.Text type="secondary">请选择文档查看抽取字段。</Typography.Text>
        )}
      </Card>

      <Card title="OCR 页面">
        {selectedDocument?.ocr_status === "failed" ? (
          <Alert
            type="error"
            showIcon
            message="OCR 失败"
            description={selectedDocument.ocr_error ?? "未知 OCR 错误"}
            style={{ marginBottom: 16 }}
          />
        ) : null}
        <Space direction="vertical" style={{ width: "100%" }}>
          <Select
            placeholder="选择页码"
            style={{ width: 180 }}
            value={selectedPageNumber ?? undefined}
            options={pages.map((page) => ({
              label: `第 ${page.page_number} 页`,
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
                {selectedPage.raw_text || "(空页面文本)"}
              </pre>
            </>
          ) : (
            <Typography.Text type="secondary">执行 OCR 后查看页面文本。</Typography.Text>
          )}
        </Space>
      </Card>
    </Space>
  );
}
