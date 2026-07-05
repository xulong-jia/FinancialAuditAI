import { Button, Card, Form, Input, Layout, Menu, Space, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";

import { clearAccessToken, getAccessToken, getCurrentUser, login, logout, setAccessToken } from "./api/client";
import { routes } from "./routes";
import type { PageKey } from "./routes";
import type { LoginPayload, UserRecord } from "./types/api";
import { hasPermission } from "./utils/permissions";

const { Header, Content, Sider } = Layout;

export default function App() {
  const [loginForm] = Form.useForm<LoginPayload>();
  const [activeKey, setActiveKey] = useState<PageKey>(routes[0].key);
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [initializing, setInitializing] = useState(Boolean(getAccessToken()));
  const [authLoading, setAuthLoading] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      return;
    }
    let active = true;
    async function loadUser() {
      try {
        const user = await getCurrentUser();
        if (active) {
          setCurrentUser(user);
        }
      } catch {
        clearAccessToken();
      } finally {
        if (active) {
          setInitializing(false);
        }
      }
    }
    void loadUser();
    return () => {
      active = false;
    };
  }, []);

  const visibleRoutes = useMemo(
    () => routes.filter((route) => hasPermission(currentUser, route.permission)),
    [currentUser],
  );

  useEffect(() => {
    if (visibleRoutes.length > 0 && !visibleRoutes.some((route) => route.key === activeKey)) {
      setActiveKey(visibleRoutes[0].key);
    }
  }, [activeKey, visibleRoutes]);

  async function handleLogin(values: LoginPayload) {
    setAuthLoading(true);
    try {
      const token = await login(values);
      setAccessToken(token.access_token);
      const user = await getCurrentUser();
      setCurrentUser(user);
      message.success("Signed in");
    } catch {
      message.error("Sign in failed");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Stateless logout is best effort on the client.
    }
    clearAccessToken();
    setCurrentUser(null);
    setActiveKey(routes[0].key);
  }

  if (initializing) {
    return (
      <Layout style={{ minHeight: "100vh", alignItems: "center", justifyContent: "center" }}>
        <Spin />
      </Layout>
    );
  }

  if (!currentUser) {
    return (
      <Layout style={{ minHeight: "100vh", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <Card style={{ width: 420 }}>
          <Space direction="vertical" size="large" style={{ width: "100%" }}>
            <Typography.Title level={3} style={{ margin: 0 }}>
              FinancialAuditAI
            </Typography.Title>
            <Form layout="vertical" form={loginForm} onFinish={handleLogin}>
              <Form.Item name="email" label="Email" rules={[{ required: true, message: "Email is required" }]}>
                <Input autoComplete="email" />
              </Form.Item>
              <Form.Item name="password" label="Password" rules={[{ required: true, message: "Password is required" }]}>
                <Input.Password autoComplete="current-password" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={authLoading} block>
                Sign in
              </Button>
            </Form>
          </Space>
        </Card>
      </Layout>
    );
  }

  const activeRoute = visibleRoutes.find((route) => route.key === activeKey) ?? visibleRoutes[0];
  const ActiveComponent = activeRoute.Component;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center" }}>
        <Typography.Title level={4} style={{ color: "white", margin: 0 }}>
          FinancialAuditAI
        </Typography.Title>
        <Space style={{ marginLeft: "auto" }}>
          <Typography.Text style={{ color: "white" }}>{currentUser.full_name}</Typography.Text>
          <Button onClick={() => void handleLogout()}>Logout</Button>
        </Space>
      </Header>
      <Layout>
        <Sider width={248} theme="light">
          <Menu
            mode="inline"
            selectedKeys={[activeKey]}
            items={visibleRoutes.map((route) => ({ key: route.key, label: route.label }))}
            onClick={({ key }) => setActiveKey(key as PageKey)}
            style={{ height: "100%", borderRight: 0 }}
          />
        </Sider>
        <Content style={{ padding: 24 }}>
          <ActiveComponent onNavigate={setActiveKey} currentUser={currentUser} />
        </Content>
      </Layout>
    </Layout>
  );
}
