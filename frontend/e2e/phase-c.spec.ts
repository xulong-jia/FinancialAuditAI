import { expect, test, type Page, type Route } from "@playwright/test";

type Role = "viewer" | "reviewer" | "admin";

const now = "2026-07-07T00:00:00Z";
const task = {
  id: "task-1",
  task_no: "TASK-PHASE-C-001",
  name: "Phase C synthetic task",
  scenario: "procurement",
  project_name: "Phase C",
  company_name: "Synthetic Co",
  fiscal_year: 2026,
  period_start: null,
  period_end: null,
  status: "reviewing",
  risk_level: "medium",
  owner_id: null,
  reviewer_id: null,
  metadata: {},
  actor_name: "e2e",
  created_at: now,
  updated_at: now,
};
const documentRecord = {
  id: "doc-1",
  task_id: task.id,
  uploaded_by: null,
  uploaded_by_name: "e2e",
  original_filename: "phase-c-invoice.pdf",
  file_ext: "pdf",
  content_type: "application/pdf",
  file_size: 1024,
  file_hash: "synthetic",
  storage_path: "synthetic-storage/uploads/synthetic.pdf",
  doc_type: "invoice",
  business_key: "PHASE-C-001",
  doc_type_confidence: 0.99,
  classification_reason: "synthetic fixture",
  alternative_types: [],
  original_classification: null,
  metadata: {},
  page_count: 1,
  upload_status: "uploaded",
  ocr_status: "completed",
  ocr_error: null,
  extraction_status: "completed",
  review_status: "pending",
  created_at: now,
  updated_at: now,
};
const field = {
  id: "field-1",
  task_id: task.id,
  document_id: documentRecord.id,
  field_name: "amount_including_tax",
  field_label: "Amount Including Tax",
  field_type: "money",
  value_text: "600.00",
  value_normalized: { amount: 600, currency: "CNY" },
  unit: null,
  currency: "CNY",
  confidence: 0.55,
  original_value_text: null,
  original_value_normalized: null,
  original_confidence: null,
  source_page: 1,
  source_bbox: [10, 20, 160, 36],
  source_text: "Amount Including Tax: CNY 600.00",
  extraction_method: "e2e-fixture",
  is_required: true,
  is_verified: false,
  corrected_by: null,
  corrected_by_user_id: null,
  corrected_at: null,
  warnings: [],
  created_at: now,
  updated_at: now,
};
const auditResult = {
  id: "result-1",
  task_id: task.id,
  rule_id: "rule-1",
  rule_code: "PROC_AMOUNT_001",
  rule_version: "1.0.0",
  business_key: "PHASE-C-001",
  status: "fail",
  severity: "high",
  message: "Amount mismatch requires review",
  expected_value: { amount: 600 },
  actual_value: { amount: 700 },
  evidence: { refs: [{ document_id: documentRecord.id, field_id: field.id, field_name: field.field_name }] },
  rag_citations: [],
  review_status: "pending",
  reviewed_by: null,
  reviewed_by_user_id: null,
  reviewed_at: null,
  created_at: now,
  updated_at: now,
};
const report = {
  id: "report-1",
  task_id: task.id,
  report_type: "control_table",
  title: "Phase C Control Table",
  status: "ready",
  file_format: "xlsx",
  storage_path: "synthetic-storage/reports/synthetic.xlsx",
  summary: { control_table_rows: [{ business_key: "PHASE-C-001", status: "fail" }] },
  generated_by: "e2e",
  generated_at: now,
  created_at: now,
  updated_at: now,
};
const evaluation = {
  id: "eval-1",
  task_id: task.id,
  eval_name: "Phase C synthetic evaluation",
  eval_type: "regression",
  dataset_name: "manual_acceptance",
  model_name: null,
  prompt_version: null,
  rule_version: null,
  metrics: { is_production_evaluation: false, failed_case_count: 0 },
  sample_count: 1,
  failed_cases: [],
  report_path: null,
  created_by: "e2e",
  created_at: now,
};

function user(role: Role) {
  const permissions =
    role === "admin"
      ? ["*"]
      : role === "reviewer"
        ? ["read", "task:create", "task:update", "document:upload", "document:process", "audit:run", "agent:run", "review:write", "report:generate", "evaluation:read"]
        : ["read", "evaluation:read"];
  return {
    id: `${role}-user`,
    email: `${role}@example.com`,
    full_name: `Phase C ${role}`,
    organization: null,
    title: null,
    status: "active",
    last_login_at: null,
    role_codes: [role],
    permissions,
    created_at: now,
    updated_at: now,
  };
}

async function mockApi(page: Page) {
  let currentRole: Role = "viewer";
  await page.route("http://localhost:8000/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/v1/auth/login") {
      const payload = request.postDataJSON() as { email?: string };
      currentRole = payload.email?.startsWith("admin")
        ? "admin"
        : payload.email?.startsWith("reviewer")
          ? "reviewer"
          : "viewer";
      await json(route, { access_token: `${currentRole}-token`, token_type: "bearer" });
      return;
    }
    if (path === "/api/v1/auth/me") {
      await json(route, user(currentRole));
      return;
    }
    if (request.method() !== "GET") {
      await json(route, { status: "ok", id: "synthetic" });
      return;
    }
    if (path === "/api/v1/config") {
      await json(route, {
        app_name: "FinancialAuditAI",
        environment: "test",
        api_prefix: "/api/v1",
        llm_provider: "deterministic-fallback",
        llm_model: "financialauditai-local",
        llm_api_url_status: "not_configured",
        llm_api_key_status: "not_configured",
        embedding_provider: "deterministic-local",
        embedding_model: "financialauditai-embedding",
        embedding_api_url_status: "not_configured",
        embedding_api_key_status: "not_configured",
        ocr_provider: "pymupdf-local",
        ocr_model: "financialauditai-ocr",
        ocr_api_url_status: "not_configured",
        ocr_api_key_status: "not_configured",
        rag_rerank_provider: "deterministic-fallback",
        rag_answer_provider: "deterministic-fallback",
      });
    } else if (path === "/api/v1/tasks") {
      await json(route, [task]);
    } else if (path.endsWith("/documents")) {
      await json(route, [documentRecord]);
    } else if (path.endsWith("/document-relations")) {
      await json(route, []);
    } else if (path.endsWith("/audit-results")) {
      await json(route, [auditResult]);
    } else if (path.endsWith("/fields")) {
      await json(route, [field]);
    } else if (path.endsWith("/pages")) {
      await json(route, [
        {
          id: "page-1",
          document_id: documentRecord.id,
          page_number: 1,
          raw_text: "Amount Including Tax: CNY 600.00",
          ocr_blocks: [{ text: field.source_text, bbox: field.source_bbox, confidence: 0.98, confidence_source: "fixture" }],
          table_blocks: [],
          image_path: null,
          width: 595,
          height: 842,
          ocr_engine: "phase-c-fixture",
          ocr_confidence: 0.98,
          warnings: [],
          created_at: now,
          updated_at: now,
        },
      ]);
    } else if (path === "/api/v1/review/queue") {
      await json(route, [
        {
          item_type: "field",
          task_id: task.id,
          document_id: documentRecord.id,
          field_id: field.id,
          audit_result_id: null,
          agent_step_id: null,
          comment_id: null,
          reason: "Low confidence",
          document: null,
          field,
          audit_result: null,
          agent_step: null,
          comment: null,
        },
      ]);
    } else if (path === "/api/v1/review/comments") {
      await json(route, []);
    } else if (path.endsWith("/reports")) {
      await json(route, [report]);
    } else if (path === "/api/v1/evaluations/results") {
      await json(route, [evaluation]);
    } else if (path === "/api/v1/users") {
      await json(route, [user("viewer"), user("reviewer"), user("admin")]);
    } else if (path === "/api/v1/roles") {
      await json(route, [
        { id: "role-viewer", code: "viewer", name: "Viewer", description: null, permissions: ["read"], created_at: now, updated_at: now },
        { id: "role-admin", code: "admin", name: "Admin", description: null, permissions: ["*"], created_at: now, updated_at: now },
      ]);
    } else if (path === "/api/v1/audit-logs" || path === "/api/v1/rules" || path === "/api/v1/rag/documents" || path === "/api/v1/bad-cases") {
      await json(route, []);
    } else {
      await json(route, []);
    }
  });
}

async function json(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function login(page: Page, role: Role) {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FinancialAuditAI" })).toBeVisible();
  await page.getByLabel("Email").fill(`${role}@example.com`);
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
}

test("admin can log in and navigate Phase C browser E2E centers", async ({ page }) => {
  await login(page, "admin");
  for (const name of ["Task Center", "Audit Workbench", "Review Center", "Report Center", "Evaluation Center", "Admin Center"]) {
    await page.getByRole("menuitem", { name }).click();
    await expect(page.getByRole("heading", { name })).toBeVisible();
  }
});

test("viewer sees read/evaluation pages but write controls are disabled", async ({ page }) => {
  await login(page, "viewer");
  await expect(page.getByRole("menuitem", { name: "Admin Center" })).toHaveCount(0);

  await page.getByRole("menuitem", { name: "Task Center" }).click();
  await expect(page.getByRole("heading", { name: "Task Center" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create" })).toBeDisabled();

  await page.getByRole("menuitem", { name: "Report Center" }).click();
  await expect(page.getByRole("heading", { name: "Report Center" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate XLSX" })).toBeDisabled();

  await page.getByRole("menuitem", { name: "Evaluation Center" }).click();
  await expect(page.getByRole("heading", { name: "Evaluation Center" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run" })).toBeDisabled();
});

test("reviewer can access review actions while admin entry remains hidden", async ({ page }) => {
  await login(page, "reviewer");
  await expect(page.getByRole("menuitem", { name: "Admin Center" })).toHaveCount(0);
  await page.getByRole("menuitem", { name: "Review Center" }).click();
  await expect(page.getByRole("heading", { name: "Review Center" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Correct" })).toBeEnabled();
});
