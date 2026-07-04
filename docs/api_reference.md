# FinancialAuditAI MVP API Reference

Base URL: `http://localhost:8000/api/v1`

Responses use JSON unless the endpoint is a report download. Errors use FastAPI's standard `{"detail": ...}` shape.

## System

- `GET /health`
- `GET /api/v1/config`

## Tasks

- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}`

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

Supported MVP doc types:

- `purchase_request`
- `purchase_contract`
- `warehouse_receipt`
- `invoice`
- `accounting_voucher`
- `payment_receipt`
- `unknown`

## Procurement Linkage

- `POST /tasks/{task_id}/link-documents`
- `GET /tasks/{task_id}/document-relations`

## Rule Engine

- `POST /tasks/{task_id}/audit`
- `GET /tasks/{task_id}/audit-results`
- `GET /audit-results/{result_id}`
- `GET /rules`

MVP rule codes:

- `PROC_MISSING_001`
- `PROC_TIME_001`
- `PROC_AMOUNT_001`
- `PROC_NAME_001`
- `PROC_QTY_001`
- `PROC_TAX_001`

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

## Security Notes

- MVP does not implement login, RBAC, user roles, or production authorization.
- User fields such as `actor_name`, `reviewed_by`, `corrected_by`, and `generated_by` are nullable strings.
- Do not use this API with real confidential documents.
