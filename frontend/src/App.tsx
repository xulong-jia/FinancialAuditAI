import { Layout, Menu, Typography } from "antd";
import { useState } from "react";

import { routes } from "./routes";

const { Header, Content, Sider } = Layout;

export default function App() {
  const [activeKey, setActiveKey] = useState(routes[0].key);
  const activeRoute = routes.find((route) => route.key === activeKey) ?? routes[0];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center" }}>
        <Typography.Title level={4} style={{ color: "white", margin: 0 }}>
          FinancialAuditAI
        </Typography.Title>
      </Header>
      <Layout>
        <Sider width={248} theme="light">
          <Menu
            mode="inline"
            selectedKeys={[activeKey]}
            items={routes.map((route) => ({ key: route.key, label: route.label }))}
            onClick={({ key }) => setActiveKey(key)}
            style={{ height: "100%", borderRight: 0 }}
          />
        </Sider>
        <Content style={{ padding: 24 }}>
          <activeRoute.Component />
        </Content>
      </Layout>
    </Layout>
  );
}
