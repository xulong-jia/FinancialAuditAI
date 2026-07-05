import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useState } from "react";

import { createRagDocument, indexRagDocument, listRagDocuments, queryRag } from "../api/client";
import type { PageProps } from "../routes";
import type { KnowledgeBase, RagCitation, RagDocument, RagQueryResponse } from "../types/api";
import { hasPermission } from "../utils/permissions";

const knowledgeBaseOptions: { label: string; value: KnowledgeBase }[] = [
  { label: "Regulation", value: "regulation" },
  { label: "Inquiry Case", value: "inquiry_case" },
  { label: "Prospectus", value: "prospectus" },
  { label: "Workpaper", value: "workpaper" },
];

type UploadFormValues = {
  knowledge_base: KnowledgeBase;
  title: string;
  source_type: string;
  metadata_json?: string;
  content_text?: string;
};

type QueryFormValues = {
  knowledge_base: KnowledgeBase;
  query: string;
  top_k: number;
  metadata_filter_json?: string;
};

function parseJsonObject(raw: string | undefined) {
  if (!raw?.trim()) {
    return {};
  }
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  return parsed as Record<string, unknown>;
}

export function KnowledgeCenterPage({ currentUser }: PageProps) {
  const [uploadForm] = Form.useForm<UploadFormValues>();
  const [queryForm] = Form.useForm<QueryFormValues>();
  const [knowledgeBase, setKnowledgeBase] = useState<KnowledgeBase>("regulation");
  const [documents, setDocuments] = useState<RagDocument[]>([]);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [queryResult, setQueryResult] = useState<RagQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const canManageRag = hasPermission(currentUser, "rag:manage");

  async function refreshDocuments(nextKnowledgeBase = knowledgeBase) {
    setDocuments(await listRagDocuments(nextKnowledgeBase));
  }

  useEffect(() => {
    void refreshDocuments().catch(() => message.error("Failed to load knowledge documents"));
  }, []);

  async function handleUpload(values: UploadFormValues) {
    const originFile = fileList[0]?.originFileObj;
    if (!originFile && !values.content_text?.trim()) {
      message.warning("Upload a txt/pdf file or paste text");
      return;
    }
    setLoading(true);
    try {
      await createRagDocument({
        knowledge_base: values.knowledge_base,
        title: values.title,
        source_type: values.source_type,
        metadata_json: values.metadata_json,
        content_text: values.content_text,
        file: originFile,
      });
      setKnowledgeBase(values.knowledge_base);
      setFileList([]);
      uploadForm.resetFields();
      await refreshDocuments(values.knowledge_base);
      message.success("Knowledge document created");
    } catch {
      message.error("Failed to create knowledge document");
    } finally {
      setLoading(false);
    }
  }

  async function handleIndex(documentId: string) {
    setLoading(true);
    try {
      const result = await indexRagDocument(documentId);
      await refreshDocuments(result.knowledge_base);
      message.success(`Indexed ${result.chunk_count} chunks`);
    } catch {
      message.error("Failed to build RAG index");
    } finally {
      setLoading(false);
    }
  }

  async function handleQuery(values: QueryFormValues) {
    setLoading(true);
    try {
      const result = await queryRag({
        knowledge_base: values.knowledge_base,
        query: values.query,
        top_k: values.top_k,
        metadata_filter: parseJsonObject(values.metadata_filter_json),
      });
      setQueryResult(result);
    } catch {
      message.error("RAG query failed. Check metadata filter JSON.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            Knowledge Center
          </Typography.Title>
          <Select
            value={knowledgeBase}
            options={knowledgeBaseOptions}
            style={{ width: 200 }}
            onChange={(value) => {
              setKnowledgeBase(value);
              void refreshDocuments(value);
            }}
          />
        </Space>
      </Card>
      {!canManageRag ? <Alert type="info" showIcon message="Read-only permissions" /> : null}

      <Card title="Add Knowledge Document">
        <Form<UploadFormValues>
          form={uploadForm}
          layout="vertical"
          initialValues={{ knowledge_base: knowledgeBase, source_type: "uploaded_text" }}
          onFinish={(values) => void handleUpload(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="knowledge_base" label="Knowledge Base" rules={[{ required: true }]}>
              <Select options={knowledgeBaseOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="title" label="Title" rules={[{ required: true }]}>
              <Input style={{ width: 280 }} />
            </Form.Item>
            <Form.Item name="source_type" label="Source Type" rules={[{ required: true }]}>
              <Input style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="metadata_json" label="Metadata JSON">
              <Input placeholder='{"issuer":"SEC"}' style={{ width: 260 }} />
            </Form.Item>
          </Space>
          <Form.Item name="content_text" label="Text">
            <Input.TextArea rows={4} placeholder="Paste source-backed text or upload txt/pdf" />
          </Form.Item>
          <Space>
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              fileList={fileList}
              onChange={({ fileList: nextFileList }) => setFileList(nextFileList)}
              disabled={!canManageRag}
            >
              <Button disabled={!canManageRag}>Select txt/pdf</Button>
            </Upload>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!canManageRag}>
              Create
            </Button>
          </Space>
        </Form>
      </Card>

      <Card title="Knowledge Documents">
        <Table<RagDocument>
          rowKey="id"
          loading={loading}
          dataSource={documents}
          pagination={false}
          columns={[
            { title: "Title", dataIndex: "title" },
            { title: "Knowledge Base", dataIndex: "knowledge_base", render: (value: KnowledgeBase) => <Tag>{value}</Tag> },
            { title: "Source Type", dataIndex: "source_type" },
            { title: "Chunks", dataIndex: "chunk_count" },
            {
              title: "Metadata",
              dataIndex: "metadata",
              render: (value: Record<string, unknown>) => JSON.stringify(value),
            },
            {
              title: "Action",
              render: (_, record) => (
                <Button loading={loading} disabled={!canManageRag} onClick={() => void handleIndex(record.id)}>
                  Build Index
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="Retrieval Test">
        <Form<QueryFormValues>
          form={queryForm}
          layout="vertical"
          initialValues={{ knowledge_base: knowledgeBase, top_k: 5 }}
          onFinish={(values) => void handleQuery(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="knowledge_base" label="Knowledge Base" rules={[{ required: true }]}>
              <Select options={knowledgeBaseOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="top_k" label="Top K" rules={[{ required: true }]}>
              <InputNumber min={1} max={10} />
            </Form.Item>
            <Form.Item name="metadata_filter_json" label="Metadata Filter JSON">
              <Input placeholder='{"issuer":"SEC"}' style={{ width: 260 }} />
            </Form.Item>
          </Space>
          <Form.Item name="query" label="Query" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            Search
          </Button>
        </Form>
      </Card>

      {queryResult ? (
        <Card title="Result">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Alert
              type={queryResult.status === "answer" ? "success" : "warning"}
              showIcon
              message={queryResult.status}
              description={queryResult.answer}
            />
            <Table<RagCitation>
              rowKey="chunk_id"
              dataSource={queryResult.citations}
              pagination={false}
              columns={[
                { title: "Title", dataIndex: "title" },
                { title: "Score", dataIndex: "score" },
                { title: "Section", dataIndex: "section" },
                { title: "Page", dataIndex: "page" },
                { title: "Quote", dataIndex: "quote", render: (value: string) => <Typography.Text>{value}</Typography.Text> },
                {
                  title: "Metadata",
                  dataIndex: "metadata",
                  render: (value: Record<string, unknown>) => JSON.stringify(value),
                },
              ]}
            />
            <Alert type="info" showIcon message="Limitations" description={queryResult.limitations.join(" ")} />
          </Space>
        </Card>
      ) : null}
    </Space>
  );
}
