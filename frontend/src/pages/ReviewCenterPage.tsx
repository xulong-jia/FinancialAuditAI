import { Card, Empty, Typography } from "antd";

import type { PageProps } from "../routes";

export function ReviewCenterPage(_props: PageProps) {
  return (
    <Card>
      <Typography.Title level={3}>Review Center</Typography.Title>
      <Empty description="Phase 0" />
    </Card>
  );
}
