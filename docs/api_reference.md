# FinancialAuditAI MVP API Reference

Base URL: `http://localhost:8000/api/v1`

Responses use JSON unless the endpoint is a report download. Errors use FastAPI's standard `{"detail": ...}` shape.

## System

- `GET /health`
- `GET /api/v1/config`

## Auth And RBAC

- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `GET /users`
- `POST /users`
- `PATCH /users/{user_id}`
- `GET /roles`
- `POST /roles`
- `PATCH /roles/{role_id}`
- `GET /audit-logs`

Protected endpoints use `Authorization: Bearer <token>`. `GET /health` and `GET /api/v1/config` remain public local health/config endpoints. Password hashes are never returned.

Default roles:

- `viewer`: read-only access.
- `analyst`: create/update tasks, upload documents, run document processing, run rule audit, and run Agent workflows.
- `reviewer`: review queue operations, field correction, exception confirm/dismiss, and rule rerun.
- `manager`: report generation, evaluation result viewing, and audit-log viewing.
- `admin`: all permissions, including Rule Center, RAG management, user and role management, and system configuration.

## Tasks

- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}`

Supported task scenarios: `procurement`, `sales`, `confirmation`, `interview`, `contract_review`.

## Documents

- `POST /tasks/{task_id}/documents`
- `GET /tasks/{task_id}/documents`
- `GET /documents/{document_id}`
- `PATCH /documents/{document_id}`

Supported upload extensions: `pdf`, `png`, `jpg`, `jpeg`, `docx`, `xlsx`.

## OCR And Pages

- `POST /documents/{document_id}/ocr`
- `GET /documents/{document_id}/pages`

## Classification And Extraction

- `POST /documents/{document_id}/classify`
- `POST /documents/{document_id}/extract`
- `GET /documents/{document_id}/fields`
- `GET /tasks/{task_id}/fields`

Supported procurement doc types:

- `purchase_request`
- `purchase_contract`
- `warehouse_receipt`
- `invoice`
- `accounting_voucher`
- `payment_receipt`
- `unknown`

Supported sales doc types:

- `sales_contract`
- `sales_order`
- `delivery_order`
- `logistics_receipt`
- `sales_invoice`
- `receipt_voucher`
- `accounting_voucher`
- `unknown`

Supported confirmation doc types:

- `confirmation`
- `confirmation_request`
- `confirmation_reply`
- `confirmation_adjustment`
- `unknown`

Supported interview doc types:

- `interview_record`
- `interview_outline`
- `interview_signature_page`
- `interview_transcript`
- `unknown`

Supported contract review doc types:

- `contract_review`
- `material_contract`
- `supplemental_agreement`
- `framework_agreement`
- `contract_attachment`
- `unknown`

## Document Linkage

- `POST /tasks/{task_id}/link-documents`
- `GET /tasks/{task_id}/document-relations`

Procurement, sales, confirmation, interview, and contract review all reuse this API. Sales linkage prioritizes explicit contract/order/delivery/invoice references; low-confidence customer bridges are marked for review. Confirmation linkage prioritizes `confirmation_no`; interview linkage uses `interviewee_name` across interview documents. Contract review linkage prioritizes explicit `contract_no` across contracts, supplemental agreements, framework agreements, and attachments. Relation evidence remains reviewable.

## Rule Engine

- `POST /tasks/{task_id}/audit`
- `GET /tasks/{task_id}/audit-results`
- `GET /audit-results/{result_id}`
- `GET /rules`
- `POST /rules`
- `PATCH /rules/{rule_id}`
- `POST /rules/{rule_id}/evaluate`

MVP rule codes:

- `PROC_MISSING_001`
- `PROC_TIME_001`
- `PROC_AMOUNT_001`
- `PROC_NAME_001`
- `PROC_QTY_001`
- `PROC_TAX_001`

Sales rule codes:

- `SALES_MISSING_001`
- `SALES_TIME_001`
- `SALES_AMOUNT_001`
- `SALES_NAME_001`
- `SALES_QTY_001`

Confirmation rule codes:

- `CONF_MISSING_001`
- `CONF_DATE_001`
- `CONF_AMOUNT_001`
- `CONF_NAME_001`
- `CONF_SEAL_SIGN_001`

Interview rule codes:

- `INTERVIEW_MISSING_001`
- `INTERVIEW_DATE_001`
- `INTERVIEW_SIGNATURE_001`
- `INTERVIEW_AMOUNT_001`
- `INTERVIEW_COUNTERPARTY_001`

Contract review rule codes:

- `CONTRACT_MISSING_001`
- `CONTRACT_PERIOD_001`
- `CONTRACT_AMOUNT_001`
- `CONTRACT_COUNTERPARTY_001`
- `CONTRACT_KEY_TERMS_001`
- `CONTRACT_SPECIAL_CLAUSE_001`
- `CONTRACT_SIGNATURE_SEAL_001`

Rule configuration stays inside the Python rule registry. `POST /rules` only accepts rule codes already present in the registry. `PATCH /rules/{rule_id}` supports enabled status, version, description, and approved parameters such as `tolerance_amount`, `tolerance_ratio`, `allowed_tax_rates`, `supplier_aliases`, `item_mappings`, `prepayment_allowed`, and `date_tolerance_days`. Rule updates write `audit_logs`; audit results include `rule_version`. `POST /rules/{rule_id}/evaluate` is a dry run and does not persist `audit_results`.

## Review

- `GET /review/queue`
- `GET /review/comments`
- `POST /review/comments`
- `PATCH /fields/{field_id}`
- `POST /audit-results/{result_id}/confirm`
- `POST /audit-results/{result_id}/dismiss`
- `POST /audit-results/{result_id}/rerun`

Dismiss requires a non-empty `reason`.

## Reports

- `POST /tasks/{task_id}/reports/control-table`
- `GET /tasks/{task_id}/reports`
- `GET /reports/{report_id}/download`

Report files are xlsx only in MVP. Generated files are stored under ignored `local_storage/reports`.

Procurement reports include `Procurement Control Table`. Sales reports include `Sales Control Table`. Confirmation reports include `Confirmation Results`. Interview reports include `Interview Evidence`. Contract review reports include `Contract Review` and `Special Clauses`. All keep Summary, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.

## RAG Knowledge Base

- `GET /rag/documents`
- `POST /rag/documents`
- `POST /rag/documents/{doc_id}/index`
- `POST /rag/query`
- `GET /rag/chunks/{chunk_id}`

Supported knowledge bases:

- `regulation`
- `inquiry_case`
- `prospectus`
- `workpaper`

RAG query responses include `answer`, `citations`, and `limitations`. If evidence is insufficient, the API returns `status: "no_answer"` and no fabricated citation. RAG citations are evidence only and do not replace Rule Engine results or human review.

## Agent Workflow

- `POST /agents/runs`
- `GET /agents/runs/{run_id}`
- `GET /agents/runs/{run_id}/steps`
- `POST /agents/runs/{run_id}/retry`

Agent workflow is a fixed state machine with whitelisted tool calls only. It records `agent_runs` and `agent_steps` with input references, output references, status, duration, and errors. It calls the existing OCR, classification, extraction, linkage, Rule Engine, RAG retrieval, review routing, and report generation services. Agent workflow does not provide free chat, autonomous planning, Evaluation Center, Bad Case Center, or final audit conclusions. It does not write Rule Engine pass/fail decisions directly and does not auto-confirm high-risk exceptions.

## Quality Center

- `POST /bad-cases`
- `GET /bad-cases`
- `GET /bad-cases/{case_id}`
- `PATCH /bad-cases/{case_id}`
- `POST /evaluations/run`
- `GET /evaluations/results`
- `GET /evaluations/results/{result_id}`

Supported evaluation types: `classification`, `ocr`, `extraction`, `rule`, `rag`, `agent`, `end_to_end`, and `regression`. Phase 14 evaluations use synthetic smoke datasets and store explicit limitations in `metrics`; they are quality checks, not production score claims. Failed evaluation samples are stored in `failed_cases` and converted into open Bad Cases for regression tracking. Evaluation Center does not change Rule Engine logic, Review Center decisions, Agent behavior, or RAG answers.

## Security Notes

- Phase 19 implements basic login, fixed RBAC roles, route-level permission dependencies, Admin Center, and audit-log query.
- RBAC keeps historical fields such as `actor_name`, `reviewed_by`, `corrected_by`, and `generated_by` compatible as nullable strings/fallbacks; old records are not forced to have real user IDs.
- Permission failures return 403; missing or invalid tokens return 401 on protected endpoints.
- Uploads validate extension, content type, size, hash, and basic file signature/magic header.
- Audit logs redact sensitive keys and large raw text fields such as OCR/source/chunk text.
- `scripts/danger_check.py` scans tracked/staged files for forbidden paths and obvious static secrets before commit.
- Do not use this API with real confidential documents.
- Workpaper content must stay isolated from public RAG knowledge bases.
- Agent step payloads should contain references and summaries, not complete sensitive original text.
- Phase 19 does not implement enterprise SSO, third-party OAuth, multi-tenant billing, production KMS, or complex organization hierarchy.
