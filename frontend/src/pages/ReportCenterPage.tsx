import { Card, Empty, Typography } from "antd";

import type { PageProps } from "../routes";

export function ReportCenterPage(_props: PageProps) {
  return (
    <Card>
      <Typography.Title level={3}>Report Center</Typography.Title>
      <Empty description="Phase 0" />
    </Card>
  );
}
