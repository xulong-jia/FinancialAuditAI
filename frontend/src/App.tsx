import { Button, Card, ConfigProvider, Form, Grid, Input, Layout, Menu, Space, Spin, Tag, Typography, message } from "antd";
import zhCN from "antd/locale/zh_CN";
import { useEffect, useMemo, useState } from "react";

import { clearAccessToken, getAccessToken, getCurrentUser, login, logout, register, setAccessToken } from "./api/client";
import { routes } from "./routes";
import type { PageKey } from "./routes";
import type { LoginPayload, RegisterPayload, UserRecord } from "./types/api";
import { hasPermission } from "./utils/permissions";

const { Header, Content, Sider } = Layout;

const theme = {
  token: {
    colorPrimary: "#1f6f64",
    colorInfo: "#1f6f64",
    colorSuccess: "#237a57",
    colorWarning: "#b7791f",
    colorError: "#b42318",
    colorTextBase: "#17202a",
    colorBgLayout: "#f5f7f8",
    borderRadius: 8,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  },
  components: {
    Button: {
      controlHeight: 40,
      borderRadius: 6,
    },
    Card: {
      borderRadiusLG: 8,
      boxShadowTertiary: "0 10px 30px rgba(23, 32, 42, 0.06)",
    },
    Table: {
      headerBg: "#f4f7f6",
      headerColor: "#31433f",
      rowHoverBg: "#f7fbfa",
    },
  },
};

export default function App() {
  const [loginForm] = Form.useForm<LoginPayload>();
  const [registerForm] = Form.useForm<RegisterPayload & { confirm_password: string }>();
  const [activeKey, setActiveKey] = useState<PageKey>(routes[0].key);
  const [currentUser, setCurrentUser] = useState<UserRecord | null>(null);
  const [initializing, setInitializing] = useState(Boolean(getAccessToken()));
  const [authLoading, setAuthLoading] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const screens = Grid.useBreakpoint();
  const compactNav = !screens.lg;

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
      message.success("登录成功");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "登录失败");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleRegister(values: RegisterPayload & { confirm_password: string }) {
    setAuthLoading(true);
    try {
      const token = await register({
        email: values.email,
        password: values.password,
        full_name: values.full_name?.trim() || null,
      });
      setAccessToken(token.access_token);
      const user = await getCurrentUser();
      setCurrentUser(user);
      message.success("注册成功");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "注册失败");
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
      <ConfigProvider theme={theme} locale={zhCN}>
        <Layout className="loading-shell">
          <Spin size="large" />
        </Layout>
      </ConfigProvider>
    );
  }

  if (!currentUser) {
    return (
      <ConfigProvider theme={theme} locale={zhCN}>
        <Layout className="auth-shell">
          <section className="auth-hero" aria-label="FinancialAuditAI 本地演示说明">
            <div className="brand-lockup">
              <span className="brand-mark">F</span>
              <span>FinancialAuditAI</span>
            </div>
            <Typography.Title level={1}>证据优先的金融文档智能审核平台</Typography.Title>
            <Typography.Paragraph>
              本地 public acceptance demo，聚焦文档归集、OCR、字段抽取、规则审核、人工复核和报告导出。
            </Typography.Paragraph>
            <Space wrap>
              <Tag color="processing">非生产演示</Tag>
              <Tag color="success">可复核</Tag>
              <Tag color="default">可回归</Tag>
            </Space>
          </section>
          <Card className="auth-card">
            <Space direction="vertical" size="large" style={{ width: "100%" }}>
              <div>
                <Typography.Title level={3} style={{ margin: 0 }}>
                  {authMode === "login" ? "登录本地演示" : "创建本地账号"}
                </Typography.Title>
                <Typography.Text type="secondary">仅用于本地公开验收演示，不是生产开放注册。</Typography.Text>
              </div>
              {authMode === "login" ? (
                <Form layout="vertical" form={loginForm} onFinish={handleLogin} requiredMark={false}>
                  <Form.Item
                    name="email"
                    label="邮箱"
                    rules={[
                      { required: true, message: "请输入邮箱" },
                      { type: "email", message: "请输入有效邮箱" },
                    ]}
                  >
                    <Input autoComplete="email" inputMode="email" />
                  </Form.Item>
                  <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
                    <Input.Password autoComplete="current-password" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={authLoading} block>
                    登录
                  </Button>
                  <Button type="link" block onClick={() => setAuthMode("register")}>
                    注册账号
                  </Button>
                </Form>
              ) : (
                <Form layout="vertical" form={registerForm} onFinish={handleRegister} requiredMark={false}>
                  <Form.Item
                    name="email"
                    label="邮箱"
                    rules={[
                      { required: true, message: "请输入邮箱" },
                      { type: "email", message: "请输入有效邮箱" },
                    ]}
                  >
                    <Input autoComplete="email" inputMode="email" />
                  </Form.Item>
                  <Form.Item name="full_name" label="姓名">
                    <Input autoComplete="name" />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    label="密码"
                    rules={[
                      { required: true, message: "请输入密码" },
                      { min: 8, message: "密码至少 8 位" },
                    ]}
                  >
                    <Input.Password autoComplete="new-password" />
                  </Form.Item>
                  <Form.Item
                    name="confirm_password"
                    label="确认密码"
                    dependencies={["password"]}
                    rules={[
                      { required: true, message: "请确认密码" },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue("password") === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error("两次输入的密码不一致"));
                        },
                      }),
                    ]}
                  >
                    <Input.Password autoComplete="new-password" />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={authLoading} block>
                    注册账号
                  </Button>
                  <Button type="link" block onClick={() => setAuthMode("login")}>
                    返回登录
                  </Button>
                </Form>
              )}
            </Space>
          </Card>
        </Layout>
      </ConfigProvider>
    );
  }

  const activeRoute = visibleRoutes.find((route) => route.key === activeKey) ?? visibleRoutes[0];
  const ActiveComponent = activeRoute.Component;
  const menuItems = visibleRoutes.map((route) => ({ key: route.key, label: route.label }));

  return (
    <ConfigProvider theme={theme} locale={zhCN}>
      <Layout className="app-shell">
        <Header className="app-header">
          <div className="brand-lockup app-brand">
            <span className="brand-mark">F</span>
            <span>FinancialAuditAI</span>
          </div>
          <Tag className="boundary-tag">非生产公开验收演示</Tag>
          <Space className="user-actions">
            <Typography.Text>{currentUser.full_name || currentUser.email}</Typography.Text>
            <Button onClick={() => void handleLogout()}>退出登录</Button>
          </Space>
        </Header>
        {compactNav ? (
          <Menu
            className="mobile-nav"
            mode="horizontal"
            selectedKeys={[activeKey]}
            items={menuItems}
            onClick={({ key }) => setActiveKey(key as PageKey)}
          />
        ) : null}
        <Layout className="app-main">
          {!compactNav ? (
            <Sider width={252} theme="light" className="app-sider">
              <div className="sider-note">
                <strong>本地演示边界</strong>
                <span>证据优先 · 人工复核 · 回归验证</span>
              </div>
              <Menu
                mode="inline"
                selectedKeys={[activeKey]}
                items={menuItems}
                onClick={({ key }) => setActiveKey(key as PageKey)}
              />
            </Sider>
          ) : null}
          <Content className="app-content">
            <ActiveComponent onNavigate={setActiveKey} currentUser={currentUser} />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}
