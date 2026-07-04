import { AuditWorkbenchPage } from "../pages/AuditWorkbenchPage";
import { ReportCenterPage } from "../pages/ReportCenterPage";
import { ReviewCenterPage } from "../pages/ReviewCenterPage";
import { TaskCenterPage } from "../pages/TaskCenterPage";

export const routes = [
  { key: "task-center", label: "Task Center", Component: TaskCenterPage },
  { key: "audit-workbench", label: "Audit Workbench", Component: AuditWorkbenchPage },
  { key: "review-center", label: "Review Center", Component: ReviewCenterPage },
  { key: "report-center", label: "Report Center", Component: ReportCenterPage },
];
