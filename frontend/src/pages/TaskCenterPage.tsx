import { Card, Empty, Typography } from "antd";

export function TaskCenterPage() {
  return (
    <Card>
      <Typography.Title level={3}>Task Center</Typography.Title>
      <Empty description="Phase 0" />
    </Card>
  );
}
