import { Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { createRole, createUser, getConfig, listAuditLogs, listRoles, listUsers, updateUser } from "../api/client";
import type { PageProps } from "../routes";
import type { AuditLogRecord, RoleCreatePayload, RoleRecord, SystemConfig, UserCreatePayload, UserRecord } from "../types/api";
import { displayRole, displayStatus } from "../utils/displayText";

function formatJson(value: Record<string, unknown> | null) {
  return value ? JSON.stringify(value) : "-";
}

function splitPermissions(value: string | undefined) {
  return value
    ? value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
    : [];
}

export function AdminCenterPage({ currentUser }: PageProps) {
  const [userForm] = Form.useForm<UserCreatePayload>();
  const [roleForm] = Form.useForm<RoleCreatePayload & { permissions_text?: string }>();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const [nextUsers, nextRoles, nextLogs, nextConfig] = await Promise.all([listUsers(), listRoles(), listAuditLogs(), getConfig()]);
      setUsers(nextUsers);
      setRoles(nextRoles);
      setAuditLogs(nextLogs);
      setConfig(nextConfig);
    } catch {
      message.error("管理数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreateUser(values: UserCreatePayload) {
    setLoading(true);
    try {
      await createUser(values);
      userForm.resetFields();
      await refresh();
      message.success("用户已创建");
    } catch {
      message.error("用户创建失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleUser(user: UserRecord) {
    setLoading(true);
    try {
      await updateUser(user.id, { status: user.status === "active" ? "disabled" : "active" });
      await refresh();
      message.success("用户已更新");
    } catch {
      message.error("用户更新失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateRole(values: RoleCreatePayload & { permissions_text?: string }) {
    setLoading(true);
    try {
      await createRole({
        code: values.code,
        name: values.name,
        description: values.description,
        permissions: splitPermissions(values.permissions_text),
      });
      roleForm.resetFields();
      await refresh();
      message.success("角色已创建");
    } catch {
      message.error("角色创建失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical">
          <Typography.Title level={3} style={{ margin: 0 }}>
            管理中心
          </Typography.Title>
          <Typography.Text type="secondary">
            当前登录: {currentUser.full_name} ({currentUser.email})
          </Typography.Text>
        </Space>
      </Card>

      <Card title="模型 / Provider 配置">
        <Space wrap>
          {[
            { label: "LLM", value: config?.llm_provider },
            { label: "模型", value: config?.llm_model },
            { label: "API URL", value: config?.llm_api_url_status },
            { label: "API Key", value: config?.llm_api_key_status },
            { label: "Embedding", value: config?.embedding_provider },
            { label: "Embedding 模型", value: config?.embedding_model },
            { label: "Embedding URL", value: config?.embedding_api_url_status },
            { label: "Embedding Key", value: config?.embedding_api_key_status },
            { label: "OCR", value: config?.ocr_provider },
            { label: "OCR 模型", value: config?.ocr_model },
            { label: "OCR URL", value: config?.ocr_api_url_status },
            { label: "OCR Key", value: config?.ocr_api_key_status },
            { label: "Rerank", value: config?.rag_rerank_provider },
            { label: "RAG Answer", value: config?.rag_answer_provider },
          ].map((item) => (
            <Tag key={item.label}>
              {item.label}: {item.value ?? "-"}
            </Tag>
          ))}
        </Space>
      </Card>

      <Card title="用户">
        <Form layout="inline" form={userForm} onFinish={handleCreateUser} style={{ marginBottom: 16 }}>
          <Form.Item name="email" rules={[{ required: true, message: "请输入邮箱" }]}>
            <Input placeholder="邮箱" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item name="full_name" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input placeholder="姓名" />
          </Form.Item>
          <Form.Item name="role_codes">
            <Select
              mode="multiple"
              placeholder="角色"
              style={{ minWidth: 180 }}
              options={roles.map((role) => ({ label: displayRole(role.code), value: role.code }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            创建用户
          </Button>
        </Form>
        <Table<UserRecord>
          rowKey="id"
          loading={loading}
          dataSource={users}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "邮箱", dataIndex: "email" },
            { title: "姓名", dataIndex: "full_name" },
            { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{displayStatus(value)}</Tag> },
            {
              title: "角色",
              dataIndex: "role_codes",
              render: (value: string[]) => (
                <Space wrap>
                  {value.map((roleCode) => (
                    <Tag key={roleCode}>{displayRole(roleCode)}</Tag>
                  ))}
                </Space>
              ),
            },
            {
              title: "权限",
              dataIndex: "permissions",
              render: (value: string[]) => (
                <Typography.Text ellipsis={{ tooltip: value.join(", ") }} style={{ maxWidth: 360 }}>
                  {value.join(", ")}
                </Typography.Text>
              ),
            },
            {
              title: "操作",
              render: (_, record) => (
                <Button size="small" onClick={() => void handleToggleUser(record)}>
                  {record.status === "active" ? "停用" : "启用"}
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="角色">
        <Form layout="inline" form={roleForm} onFinish={handleCreateRole} style={{ marginBottom: 16 }}>
          <Form.Item name="code" rules={[{ required: true, message: "请输入角色编码" }]}>
            <Input placeholder="编码" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: "请输入角色名称" }]}>
            <Input placeholder="名称" />
          </Form.Item>
          <Form.Item name="permissions_text">
            <Input placeholder="permission:a, permission:b" style={{ minWidth: 260 }} />
          </Form.Item>
          <Button htmlType="submit" loading={loading}>
            创建角色
          </Button>
        </Form>
        <Table<RoleRecord>
          rowKey="id"
          loading={loading}
          dataSource={roles}
          pagination={false}
          columns={[
            { title: "编码", dataIndex: "code" },
            { title: "名称", dataIndex: "name" },
            {
              title: "权限",
              dataIndex: "permissions",
              render: (value: string[]) => (
                <Space wrap>
                  {value.map((permission) => (
                    <Tag key={permission}>{permission}</Tag>
                  ))}
                </Space>
              ),
            },
            { title: "更新时间", dataIndex: "updated_at" },
          ]}
        />
      </Card>

      <Card title="审计日志">
        <Table<AuditLogRecord>
          rowKey="id"
          loading={loading}
          dataSource={auditLogs}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "创建时间", dataIndex: "created_at" },
            { title: "操作人", dataIndex: "actor_name", render: (value: string | null) => value ?? "-" },
            { title: "用户 ID", dataIndex: "user_id", render: (value: string | null) => value ?? "-" },
            { title: "IP", dataIndex: "ip_address", render: (value: string | null) => value ?? "-" },
            { title: "动作", dataIndex: "action" },
            { title: "对象", dataIndex: "target_type" },
            {
              title: "变更前",
              dataIndex: "before_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
            {
              title: "变更后",
              dataIndex: "after_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
