import type { ReactElement } from "react";

import { AuditWorkbenchPage } from "../pages/AuditWorkbenchPage";
import { KnowledgeCenterPage } from "../pages/KnowledgeCenterPage";
import { ReportCenterPage } from "../pages/ReportCenterPage";
import { ReviewCenterPage } from "../pages/ReviewCenterPage";
import { RuleCenterPage } from "../pages/RuleCenterPage";
import { TaskCenterPage } from "../pages/TaskCenterPage";

export type PageKey =
  | "task-center"
  | "audit-workbench"
  | "review-center"
  | "report-center"
  | "knowledge-center"
  | "rule-center";

export type PageProps = {
  onNavigate: (key: PageKey) => void;
};

type AppRoute = {
  key: PageKey;
  label: string;
  Component: (props: PageProps) => ReactElement;
};

export const routes: AppRoute[] = [
  { key: "task-center", label: "Task Center", Component: TaskCenterPage },
  { key: "audit-workbench", label: "Audit Workbench", Component: AuditWorkbenchPage },
  { key: "review-center", label: "Review Center", Component: ReviewCenterPage },
  { key: "report-center", label: "Report Center", Component: ReportCenterPage },
  { key: "knowledge-center", label: "Knowledge Center", Component: KnowledgeCenterPage },
  { key: "rule-center", label: "Rule Center", Component: RuleCenterPage },
];
