# FinancialAuditAI 执行手册严格缺口报告

生成日期：2026-07-06

最高标准来源：`/Users/jiaxulong/Documents/FinancialAuditAI/FinancialAuditAI_最终版项目开发执行手册.md`。

结论：**部分满足执行手册，仍有阻塞差距**。

## 本轮已修复

| 项目 | 状态 | 代码证据 | 测试证据 |
| --- | --- | --- | --- |
| OCR Provider 配置路径 | 已补齐 HTTP Provider 基础闭环 | `backend/app/core/config.py`, `backend/app/services/ocr_service.py`, `.env.example` | `backend/tests/test_ocr_api.py::test_http_ocr_provider_preserves_provider_confidence` |
| OCR Provider 配置展示 | 已补齐 Admin Center 展示 | `backend/app/api/router.py`, `frontend/src/types/api.ts`, `frontend/src/pages/AdminCenterPage.tsx` | `npm run build` |
| Embedding Provider 独立配置 | 已补齐 endpoint/key/model 配置 | `backend/app/core/config.py`, `backend/app/services/rag_service.py`, `.env.example` | `backend/tests/test_final_gap_closure_api.py::test_real_embedding_provider_requests_configured_vector_dimensions` |
| Embedding 维度兼容 | 已在真实 provider 请求中显式传入 32 维 | `backend/app/services/rag_service.py` | 同上 |
| Agent 失败 Bad Case 闭环 | 已补齐 `record_bad_case` 工具步骤和 task-scoped Bad Case | `backend/app/services/agent_service.py` | `backend/tests/test_agent_workflow_api.py::test_failed_step_retry_records_retry_step` |
| OpenAI-compatible LLM Provider 路径验证 | 已覆盖 classify / extract / rerank / answer / explain 的安全 mock HTTP 路径 | `backend/app/services/llm_provider.py` | `backend/tests/test_llm_provider_paths_api.py` |
| RAG Provider citation JSON 边界 | 已修复 UUID citation 无法序列化到真实 Provider prompt 的问题 | `backend/app/services/llm_provider.py` | `backend/tests/test_llm_provider_paths_api.py::test_rag_rerank_answer_and_rule_explain_use_configured_llm_provider` |
| Viewer RBAC 数据库口径 | 已移除 migration seed/update 中的 viewer `read_all`，并新增 head migration 修正已迁移数据库 | `backend/alembic/versions/0014_rbac_users_roles.py`, `backend/alembic/versions/0019_quality_audit_contract.py`, `backend/alembic/versions/0020_final_gap_role_matrix.py`, `backend/alembic/versions/0024_viewer_role_scope.py` | `cd backend && ./.venv/bin/alembic upgrade head`, `backend/tests/test_auth_rbac_security_api.py::test_default_role_permissions_match_execution_matrix_baseline` |
| Review actor UUID 口径 | 已为字段修正和异常复核补齐服务端注入的用户 UUID FK，并保留字符串名称作为显示兼容字段 | `backend/app/models/extracted_field.py`, `backend/app/models/audit_result.py`, `backend/app/services/review_service.py`, `backend/alembic/versions/0025_review_actor_user_refs.py` | `backend/tests/test_review_api.py::test_field_correction_preserves_source_and_writes_before_after_log`, `backend/tests/test_review_api.py::test_confirm_marks_result_reviewed`, `backend/tests/test_review_api.py::test_review_queue_and_comments_api` |
| Agent 工具角色职责合同 | 已在每个 `agent_steps.input_payload` 记录 `agent_role` 和 `must_not` 约束 | `backend/app/services/agent_service.py` | `backend/tests/test_agent_workflow_api.py::test_agent_run_creates_steps_and_report_without_bypassing_rule_engine` |
| 前端权限合同测试 | 已新增无新依赖的 `node --test` 权限合同测试 | `frontend/package.json`, `frontend/tests/permission-contract.test.mjs` | `cd frontend && npm test` |
| PDF 报告证据/复核/用途边界输出 | 已改为全列换行输出并覆盖 PDF 内容测试 | `backend/app/services/report_service.py` | `backend/tests/test_report_api.py::test_control_table_report_generates_pdf_with_evidence_review_and_boundary` |
| 规则证据链 `field_id` | 已在 `audit_results.evidence.refs` 和报告 Evidence Index 的 audit_result 行补齐字段 ID | `backend/app/services/rule_engine_service.py`, `backend/app/services/report_service.py` | `backend/tests/test_rule_engine_api.py::test_amount_rule_fails_on_overpayment_and_supports_many_invoices_payments`, `backend/tests/test_report_api.py::test_report_xlsx_exports_exceptions_evidence_and_field_corrections` |
| `model_invocations` 类型口径 | 已对齐执行手册主要口径 | `backend/app/services/classification_service.py`, `backend/app/services/extraction_service.py`, `backend/app/services/rag_service.py` 使用 `classify` / `extract` / `embed` / `rerank` / `answer` | `backend/tests/test_final_gap_closure_api.py::test_model_invocations_are_recorded_for_rag_query` |
| OCR 调用留痕 | 已补齐成功/失败路径 | `backend/app/services/ocr_service.py` 写入 `invocation_type="ocr"`、`latency_ms`、`error`、`cost_estimate` | `backend/tests/test_ocr_api.py::test_pdf_ocr_extracts_pages_in_order`, `backend/tests/test_ocr_api.py::test_ocr_failure_does_not_hide_task_or_document` |
| LLM Provider 调用元数据 | 已补齐真实返回路径 | `backend/app/services/llm_provider.py` 从 OpenAI-compatible 响应读取 `usage`，记录真实 `latency_ms`，不伪造 token/cost | `backend/tests/test_classification_api.py`, `backend/tests/test_extraction_api.py` |
| RAG 调用留痕 | 已补齐 `embed` / `rerank` / `answer` 耗时和 schema 信息 | `backend/app/services/rag_service.py` | `backend/tests/test_final_gap_closure_api.py::test_model_invocations_are_recorded_for_rag_query` |
| 异常解释 explain 路径 | 已补齐可配置 Provider 与 fallback 留痕 | `backend/app/services/llm_provider.py`, `backend/app/services/rule_engine_service.py` | `backend/tests/test_final_gap_closure_api.py::test_task_run_reports_rag_evidence_retrieval_for_review_items` |

## 当前验证记录

| 命令 | 结果 |
| --- | --- |
| `python3 -m json.tool docs/project_status.json > /tmp/project_status_validated.json` | PASS |
| `python3 scripts/danger_check.py` | PASS |
| `docker compose config` | PASS |
| `docker compose up -d postgres` | PASS |
| `docker compose ps` | PASS, PostgreSQL healthy |
| `cd backend && ./.venv/bin/alembic upgrade head` | PASS |
| `cd backend && ./.venv/bin/python -m pytest -q` | PASS, 159 passed, 5 warnings |
| `cd frontend && npm test` | PASS, 4 tests |
| `cd frontend && npm run build` | PASS, Vite chunk-size warning only |
| `git diff --check` | PASS |

## 剩余 Critical / High / Medium 缺口

### Critical

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| C-01 | 外部真实验收数据 | 代码已支持数据集驱动 Evaluation，但仓库不能包含真实客户/生产标注数据；真实数据集验收仍属于 `blocked_external_dependency`。 |
| C-02 | 外部 Provider 验收 | OCR/LLM/RAG Provider 均不能在仓库内提交真实 API key；真实端点、密钥和真实脱敏样本未提供前，外部 Provider 端到端验收属于 `blocked_external_dependency`。 |

### High

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| - | - | 当前无新增 High 代码缺口；外部真实数据/Provider 验收见 Critical `blocked_external_dependency`，质量和测试差距见 Medium。 |

### Medium

| 编号 | 模块 | 缺口 |
| --- | --- | --- |
| M-01 | Evaluation | 数据集驱动入口已存在，但真实 OCR、真实 RAG groundedness、真实 Agent E2E 评测仍依赖外部标注集和真实 Provider 配置。 |
| M-02 | Report | xlsx/csv/markdown/pdf 均存在；PDF 已输出 Summary、异常、证据索引、复核意见和用途边界；audit_result 证据行已含 `field_id`，报告质量仍受上游 OCR bbox/confidence 完整性影响。 |
| M-03 | Review | 字段修正和异常复核已补服务端用户 UUID FK；历史 `actor_name` / `reviewed_by` / `corrected_by` 字符串字段仅保留为显示兼容口径。 |
| M-04 | Frontend tests | 已有权限合同自动化测试；仍无浏览器级 E2E/交互测试。 |

## fallback / synthetic / demo 状态

| 类型 | 当前状态 | 是否仍影响完全满足 |
| --- | --- | --- |
| deterministic classification fallback | 默认未配置 Provider 时仍存在；OpenAI-compatible provider path 已测 | 是，直到真实/本地 Provider 配置完成 |
| regex extraction fallback | 默认未配置 Provider 时仍存在；OpenAI-compatible provider path 已测 | 是，直到真实/本地 Provider 配置完成 |
| PyMuPDF OCR confidence unavailable | 默认本地路径仍存在 warning；HTTP OCR Provider 可保留真实 confidence | 默认路径仍影响完全满足 |
| deterministic/local RAG embedding/rerank/answer | 默认未配置 Provider 时仍存在；embedding/rerank/answer provider path 已测 | 是，直到真实/本地 Provider 完成验收 |
| explain deterministic fallback | 默认未配置 Provider 时仍 fallback；OpenAI-compatible explain provider path 已测 | 是，直到真实/本地 Provider 完成验收 |
| agent failure bad case | 失败步骤已自动进入 `agent` Bad Case，重试会保留独立记录 | 不再作为 Bad Case 闭环缺口 |
| built-in sample Evaluation | 保留为 smoke，不作为最终评测证据 | 仍影响真实验收 |
| demo seed samples | 仍保留 | 不可作为完全满足证据 |
| external real/desensitized Evaluation dataset | 已支持 JSON 读取路径 | 需要用户提供真实/脱敏标注数据才能最终验收 |

## 下一轮最高优先级

1. 浏览器级 E2E/交互测试能力。
2. LLM/RAG Provider 真实端到端验收在安全配置下完成。
