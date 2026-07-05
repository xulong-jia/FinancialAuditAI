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
  { key: "dashboard", label: "Dashboard", Component: DashboardPage, permission: "read" },
  { key: "task-center", label: "Task Center", Component: TaskCenterPage, permission: "read" },
  { key: "audit-workbench", label: "Audit Workbench", Component: AuditWorkbenchPage, permission: "read" },
  { key: "review-center", label: "Review Center", Component: ReviewCenterPage, permission: "read" },
  { key: "report-center", label: "Report Center", Component: ReportCenterPage, permission: "read" },
  { key: "knowledge-center", label: "Knowledge Center", Component: KnowledgeCenterPage, permission: "read" },
  { key: "rule-center", label: "Rule Center", Component: RuleCenterPage, permission: "read" },
  { key: "bad-case-center", label: "Bad Case Center", Component: BadCaseCenterPage, permission: "evaluation:read" },
  { key: "evaluation-center", label: "Evaluation Center", Component: EvaluationCenterPage, permission: "evaluation:read" },
  { key: "admin-center", label: "Admin Center", Component: AdminCenterPage, permission: "user:manage" },
];
