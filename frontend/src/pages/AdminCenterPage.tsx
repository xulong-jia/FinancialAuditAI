import { Button, Card, Form, Input, Select, Space, Table, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";

import { createRole, createUser, getConfig, listAuditLogs, listRoles, listUsers, updateUser } from "../api/client";
import type { PageProps } from "../routes";
import type { AuditLogRecord, RoleCreatePayload, RoleRecord, SystemConfig, UserCreatePayload, UserRecord } from "../types/api";

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
      message.error("Failed to load admin data");
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
      message.success("User created");
    } catch {
      message.error("Failed to create user");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleUser(user: UserRecord) {
    setLoading(true);
    try {
      await updateUser(user.id, { status: user.status === "active" ? "disabled" : "active" });
      await refresh();
      message.success("User updated");
    } catch {
      message.error("Failed to update user");
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
      message.success("Role created");
    } catch {
      message.error("Failed to create role");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card>
        <Space direction="vertical">
          <Typography.Title level={3} style={{ margin: 0 }}>
            Admin Center
          </Typography.Title>
          <Typography.Text type="secondary">
            Signed in as {currentUser.full_name} ({currentUser.email})
          </Typography.Text>
        </Space>
      </Card>

      <Card title="Model Configuration">
        <Space wrap>
          {[
            { label: "LLM", value: config?.llm_provider },
            { label: "Model", value: config?.llm_model },
            { label: "API URL", value: config?.llm_api_url_status },
            { label: "API Key", value: config?.llm_api_key_status },
            { label: "Embedding", value: config?.embedding_provider },
            { label: "Rerank", value: config?.rag_rerank_provider },
            { label: "RAG Answer", value: config?.rag_answer_provider },
          ].map((item) => (
            <Tag key={item.label}>
              {item.label}: {item.value ?? "-"}
            </Tag>
          ))}
        </Space>
      </Card>

      <Card title="Users">
        <Form layout="inline" form={userForm} onFinish={handleCreateUser} style={{ marginBottom: 16 }}>
          <Form.Item name="email" rules={[{ required: true, message: "Email is required" }]}>
            <Input placeholder="Email" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "Password is required" }]}>
            <Input.Password placeholder="Password" />
          </Form.Item>
          <Form.Item name="full_name" rules={[{ required: true, message: "Full name is required" }]}>
            <Input placeholder="Full name" />
          </Form.Item>
          <Form.Item name="role_codes">
            <Select
              mode="multiple"
              placeholder="Roles"
              style={{ minWidth: 180 }}
              options={roles.map((role) => ({ label: role.name, value: role.code }))}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            Create User
          </Button>
        </Form>
        <Table<UserRecord>
          rowKey="id"
          loading={loading}
          dataSource={users}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: "Email", dataIndex: "email" },
            { title: "Name", dataIndex: "full_name" },
            { title: "Status", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
            {
              title: "Roles",
              dataIndex: "role_codes",
              render: (value: string[]) => (
                <Space wrap>
                  {value.map((roleCode) => (
                    <Tag key={roleCode}>{roleCode}</Tag>
                  ))}
                </Space>
              ),
            },
            {
              title: "Permissions",
              dataIndex: "permissions",
              render: (value: string[]) => (
                <Typography.Text ellipsis={{ tooltip: value.join(", ") }} style={{ maxWidth: 360 }}>
                  {value.join(", ")}
                </Typography.Text>
              ),
            },
            {
              title: "Action",
              render: (_, record) => (
                <Button size="small" onClick={() => void handleToggleUser(record)}>
                  {record.status === "active" ? "Disable" : "Enable"}
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card title="Roles">
        <Form layout="inline" form={roleForm} onFinish={handleCreateRole} style={{ marginBottom: 16 }}>
          <Form.Item name="code" rules={[{ required: true, message: "Role code is required" }]}>
            <Input placeholder="Code" />
          </Form.Item>
          <Form.Item name="name" rules={[{ required: true, message: "Role name is required" }]}>
            <Input placeholder="Name" />
          </Form.Item>
          <Form.Item name="permissions_text">
            <Input placeholder="permission:a, permission:b" style={{ minWidth: 260 }} />
          </Form.Item>
          <Button htmlType="submit" loading={loading}>
            Create Role
          </Button>
        </Form>
        <Table<RoleRecord>
          rowKey="id"
          loading={loading}
          dataSource={roles}
          pagination={false}
          columns={[
            { title: "Code", dataIndex: "code" },
            { title: "Name", dataIndex: "name" },
            {
              title: "Permissions",
              dataIndex: "permissions",
              render: (value: string[]) => (
                <Space wrap>
                  {value.map((permission) => (
                    <Tag key={permission}>{permission}</Tag>
                  ))}
                </Space>
              ),
            },
            { title: "Updated", dataIndex: "updated_at" },
          ]}
        />
      </Card>

      <Card title="Audit Logs">
        <Table<AuditLogRecord>
          rowKey="id"
          loading={loading}
          dataSource={auditLogs}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Created", dataIndex: "created_at" },
            { title: "Actor", dataIndex: "actor_name", render: (value: string | null) => value ?? "-" },
            { title: "User ID", dataIndex: "user_id", render: (value: string | null) => value ?? "-" },
            { title: "IP", dataIndex: "ip_address", render: (value: string | null) => value ?? "-" },
            { title: "Action", dataIndex: "action" },
            { title: "Target", dataIndex: "target_type" },
            {
              title: "Before",
              dataIndex: "before_value",
              render: (value: Record<string, unknown> | null) => (
                <Typography.Text ellipsis={{ tooltip: formatJson(value) }} style={{ maxWidth: 260 }}>
                  {formatJson(value)}
                </Typography.Text>
              ),
            },
            {
              title: "After",
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
