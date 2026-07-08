import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Table, Tag, Typography, Upload, message } from "antd";
import type { UploadFile } from "antd/es/upload/interface";
import { useEffect, useState } from "react";

import { createRagDocument, indexRagDocument, listRagDocuments, queryRag } from "../api/client";
import type { PageProps } from "../routes";
import type { KnowledgeBase, RagCitation, RagDocument, RagQueryResponse } from "../types/api";
import { displayKnowledgeBase, displayStatus } from "../utils/displayText";
import { hasPermission } from "../utils/permissions";

const knowledgeBaseOptions: { label: string; value: KnowledgeBase }[] = [
  { label: "法规库", value: "regulation" },
  { label: "问询案例库", value: "inquiry_case" },
  { label: "招股书 / 公开披露库", value: "prospectus" },
  { label: "底稿库", value: "workpaper" },
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
    void refreshDocuments().catch(() => message.error("知识文档加载失败"));
  }, []);

  async function handleUpload(values: UploadFormValues) {
    const originFile = fileList[0]?.originFileObj;
    if (!originFile && !values.content_text?.trim()) {
      message.warning("请上传 txt/pdf 文件或粘贴文本");
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
      message.success("知识文档已创建");
    } catch {
      message.error("知识文档创建失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleIndex(documentId: string) {
    setLoading(true);
    try {
      const result = await indexRagDocument(documentId);
      await refreshDocuments(result.knowledge_base);
      message.success(`已建立 ${result.chunk_count} 个切片索引`);
    } catch {
      message.error("RAG 索引建立失败");
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
      message.error("RAG 检索失败，请检查元数据过滤 JSON。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space align="center" wrap>
          <Typography.Title level={3} style={{ margin: 0 }}>
            知识库
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
      {!canManageRag ? <Alert type="info" showIcon message="只读权限" /> : null}

      <Card title="新增知识文档">
        <Form<UploadFormValues>
          form={uploadForm}
          layout="vertical"
          initialValues={{ knowledge_base: knowledgeBase, source_type: "uploaded_text" }}
          onFinish={(values) => void handleUpload(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="knowledge_base" label="知识库" rules={[{ required: true }]}>
              <Select options={knowledgeBaseOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="title" label="标题" rules={[{ required: true }]}>
              <Input style={{ width: 280 }} />
            </Form.Item>
            <Form.Item name="source_type" label="来源类型" rules={[{ required: true }]}>
              <Input style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="metadata_json" label="元数据 JSON">
              <Input placeholder='{"issuer":"SEC"}' style={{ width: 260 }} />
            </Form.Item>
          </Space>
          <Form.Item name="content_text" label="文本">
            <Input.TextArea rows={4} placeholder="粘贴有来源依据的文本，或上传 txt/pdf" />
          </Form.Item>
          <Space>
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              fileList={fileList}
              onChange={({ fileList: nextFileList }) => setFileList(nextFileList)}
              disabled={!canManageRag}
            >
              <Button disabled={!canManageRag}>选择 txt/pdf</Button>
            </Upload>
            <Button type="primary" htmlType="submit" loading={loading} disabled={!canManageRag}>
              创建
            </Button>
          </Space>
        </Form>
      </Card>

      <Card title="知识文档">
        <Table<RagDocument>
          rowKey="id"
          loading={loading}
          dataSource={documents}
          pagination={false}
          columns={[
            { title: "标题", dataIndex: "title" },
            { title: "知识库", dataIndex: "knowledge_base", render: (value: KnowledgeBase) => <Tag>{displayKnowledgeBase(value)}</Tag> },
            { title: "来源类型", dataIndex: "source_type" },
            { title: "切片数", dataIndex: "chunk_count" },
            {
              title: "元数据",
              dataIndex: "metadata",
              render: (value: Record<string, unknown>) => JSON.stringify(value),
            },
            {
              title: "操作",
              render: (_, record) => (
                <Button loading={loading} disabled={!canManageRag} onClick={() => void handleIndex(record.id)}>
                  建立索引
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="检索测试">
        <Form<QueryFormValues>
          form={queryForm}
          layout="vertical"
          initialValues={{ knowledge_base: knowledgeBase, top_k: 5 }}
          onFinish={(values) => void handleQuery(values)}
        >
          <Space align="start" wrap>
            <Form.Item name="knowledge_base" label="知识库" rules={[{ required: true }]}>
              <Select options={knowledgeBaseOptions} style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="top_k" label="Top K" rules={[{ required: true }]}>
              <InputNumber min={1} max={10} />
            </Form.Item>
            <Form.Item name="metadata_filter_json" label="元数据过滤 JSON">
              <Input placeholder='{"issuer":"SEC"}' style={{ width: 260 }} />
            </Form.Item>
          </Space>
          <Form.Item name="query" label="查询" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            检索
          </Button>
        </Form>
      </Card>

      {queryResult ? (
        <Card title="检索结果">
          <Space direction="vertical" style={{ width: "100%" }}>
            <Alert
              type={queryResult.status === "answer" ? "success" : "warning"}
              showIcon
              message={displayStatus(queryResult.status)}
              description={queryResult.answer}
            />
            <Table<RagCitation>
              rowKey="chunk_id"
              dataSource={queryResult.citations}
              pagination={false}
              columns={[
                { title: "标题", dataIndex: "title" },
                { title: "分数", dataIndex: "score" },
                { title: "章节", dataIndex: "section" },
                { title: "页码", dataIndex: "page" },
                { title: "引用原文", dataIndex: "quote", render: (value: string) => <Typography.Text>{value}</Typography.Text> },
                {
                  title: "元数据",
                  dataIndex: "metadata",
                  render: (value: Record<string, unknown>) => JSON.stringify(value),
                },
              ]}
            />
            <Alert type="info" showIcon message="限制说明" description={queryResult.limitations.join(" ")} />
          </Space>
        </Card>
      ) : null}
    </Space>
  );
}
