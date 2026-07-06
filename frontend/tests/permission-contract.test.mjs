import { readFileSync } from "node:fs";
import { join } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";

const root = new URL("..", import.meta.url).pathname;

function readSource(path) {
  return readFileSync(join(root, path), "utf8");
}

test("permission helper allows wildcard and explicit permissions", () => {
  const source = readSource("src/utils/permissions.ts");

  assert.match(source, /permissions\.includes\("\*"\)/);
  assert.match(source, /permissions\.includes\(permission\)/);
});

test("navigation routes keep protected center permissions", () => {
  const source = readSource("src/routes/index.tsx");

  for (const route of [
    '"dashboard"',
    '"task-center"',
    '"audit-workbench"',
    '"review-center"',
    '"report-center"',
    '"knowledge-center"',
    '"rule-center"',
    '"bad-case-center"',
    '"evaluation-center"',
    '"admin-center"',
  ]) {
    assert.match(source, new RegExp(`key: ${route}`));
  }
  assert.match(source, /key: "admin-center"[\s\S]*permission: "user:manage"/);
  assert.match(source, /key: "bad-case-center"[\s\S]*permission: "evaluation:read"/);
  assert.match(source, /key: "evaluation-center"[\s\S]*permission: "evaluation:read"/);
});

test("critical command surfaces are gated by role permissions", () => {
  const checks = [
    ["src/pages/TaskCenterPage.tsx", ["task:create", "task:update", "document:upload", "document:process", "audit:run"]],
    ["src/pages/AuditWorkbenchPage.tsx", ["review:write", "evaluation:read", "agent:run"]],
    ["src/pages/ReviewCenterPage.tsx", ["review:write"]],
    ["src/pages/ReportCenterPage.tsx", ["report:generate"]],
    ["src/pages/KnowledgeCenterPage.tsx", ["rag:manage"]],
    ["src/pages/RuleCenterPage.tsx", ["rule:manage"]],
    ["src/pages/BadCaseCenterPage.tsx", ["quality:manage"]],
    ["src/pages/EvaluationCenterPage.tsx", ["quality:manage"]],
  ];

  for (const [path, permissions] of checks) {
    const source = readSource(path);
    assert.match(source, /hasPermission/);
    assert.match(source, /disabled=\{!/);
    for (const permission of permissions) {
      assert.match(source, new RegExp(`"${permission}"`));
    }
  }
});

test("agent workflow controls are disabled without agent permission", () => {
  const source = readSource("src/components/AgentStateTimeline.tsx");

  assert.match(source, /canRunAgent/);
  assert.match(source, /disabled=\{!canRunAgent\}/);
  assert.match(source, /disabled=\{!taskId \|\| !canRunAgent\}/);
});
