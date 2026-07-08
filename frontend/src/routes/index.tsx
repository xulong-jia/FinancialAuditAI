import type { ReactElement } from "react";

import { AuditWorkbenchPage } from "../pages/AuditWorkbenchPage";
import { BadCaseCenterPage } from "../pages/BadCaseCenterPage";
import { DashboardPage } from "../pages/DashboardPage";
import { EvaluationCenterPage } from "../pages/EvaluationCenterPage";
import { KnowledgeCenterPage } from "../pages/KnowledgeCenterPage";
import { ReportCenterPage } from "../pages/ReportCenterPage";
import { ReviewCenterPage } from "../pages/ReviewCenterPage";
import { RuleCenterPage } from "../pages/RuleCenterPage";
import { TaskCenterPage } from "../pages/TaskCenterPage";
import { AdminCenterPage } from "../pages/AdminCenterPage";
import type { UserRecord } from "../types/api";

export type PageKey =
  | "dashboard"
  | "task-center"
  | "audit-workbench"
  | "review-center"
  | "report-center"
  | "knowledge-center"
  | "rule-center"
  | "bad-case-center"
  | "evaluation-center"
  | "admin-center";

export type PageProps = {
  onNavigate: (key: PageKey) => void;
  currentUser: UserRecord;
};

type AppRoute = {
  key: PageKey;
  label: string;
  Component: (props: PageProps) => ReactElement;
  permission: string;
};

export const routes: AppRoute[] = [
  { key: "dashboard", label: "仪表盘", Component: DashboardPage, permission: "read" },
  { key: "task-center", label: "任务中心", Component: TaskCenterPage, permission: "read" },
  { key: "audit-workbench", label: "审核工作台", Component: AuditWorkbenchPage, permission: "read" },
  { key: "review-center", label: "复核中心", Component: ReviewCenterPage, permission: "read" },
  { key: "report-center", label: "报告中心", Component: ReportCenterPage, permission: "read" },
  { key: "knowledge-center", label: "知识库", Component: KnowledgeCenterPage, permission: "read" },
  { key: "rule-center", label: "规则中心", Component: RuleCenterPage, permission: "read" },
  { key: "bad-case-center", label: "失败案例中心", Component: BadCaseCenterPage, permission: "evaluation:read" },
  { key: "evaluation-center", label: "评测中心", Component: EvaluationCenterPage, permission: "evaluation:read" },
  { key: "admin-center", label: "管理中心", Component: AdminCenterPage, permission: "user:manage" },
];
