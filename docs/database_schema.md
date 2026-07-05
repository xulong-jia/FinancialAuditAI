# Database Schema

This document summarizes the core tables managed by Alembic migrations `0001` through `0014`.

## MVP Tables

| Table | Purpose | Key Fields |
| --- | --- | --- |
| `audit_tasks` | Audit task container | `id`, `task_no`, `name`, `scenario`, `status`, `company_name`, `fiscal_year`, `actor_name` |
| `documents` | Uploaded document metadata and processing state | `id`, `task_id`, `original_filename`, `file_hash`, `storage_path`, `doc_type`, `business_key`, `ocr_status`, `extraction_status`, `review_status` |
| `document_pages` | Page-level OCR/parsed text | `id`, `document_id`, `page_number`, `raw_text`, `ocr_blocks`, `table_blocks`, `warnings` |
| `extracted_fields` | Structured field extraction output | `id`, `task_id`, `document_id`, `field_name`, `value_text`, `value_normalized`, `confidence`, `source_page`, `source_text`, `is_verified` |
| `document_relations` | Business linkage between documents | `id`, `task_id`, `business_key`, `source_document_id`, `target_document_id`, `relation_type`, `confidence`, `evidence` |
| `audit_rules` | Deterministic rule definitions and parameters | `id`, `rule_code`, `name`, `version`, `enabled`, `parameters`, `category`, `severity` |
| `audit_results` | Rule execution results | `id`, `task_id`, `rule_id`, `rule_code`, `rule_version`, `business_key`, `status`, `severity`, `expected_value`, `actual_value`, `evidence`, `review_status` |
| `review_comments` | Review comments and before/after notes | `id`, `task_id`, `document_id`, `audit_result_id`, `field_id`, `comment_type`, `content`, `before_value`, `after_value` |
| `audit_logs` | Audit trail for review, rules, users, and roles | `id`, `actor_name`, `task_id`, `action`, `target_type`, `target_id`, `before_value`, `after_value` |
| `control_table_rows` | Report preview/control rows | `id`, `task_id`, `business_key`, `scenario`, `row_data`, `overall_status`, `evidence_refs`, `reviewer_comment` |
| `reports` | Generated report records | `id`, `task_id`, `report_type`, `title`, `status`, `file_format`, `storage_path`, `summary`, `generated_by` |
| `model_invocations` | Provider invocation audit records | `id`, `task_id`, `document_id`, `provider`, `model_name`, `invocation_type`, `status`, `latency_ms`, `token_usage`, `error` |

## Post-MVP Tables

| Table | Purpose | Key Fields |
| --- | --- | --- |
| `rag_documents` | Knowledge-base documents | `id`, `knowledge_base`, `title`, `source_type`, `source_url`, `checksum`, `metadata`, `created_by` |
| `rag_chunks` | Searchable RAG chunks | `id`, `rag_document_id`, `knowledge_base`, `chunk_index`, `chunk_text`, `embedding`, `section_title`, `article_no`, `page_start`, `metadata` |
| `agent_runs` | Agent workflow runs | `id`, `task_id`, `workflow_name`, `status`, `current_state`, `input_refs`, `output_refs`, `error` |
| `agent_steps` | Agent tool step logs | `id`, `run_id`, `step_name`, `step_order`, `tool_name`, `status`, `input_payload`, `output_payload`, `duration_ms`, `error` |
| `bad_cases` | Failed samples and regression assets | `id`, `task_id`, `document_id`, `case_type`, `title`, `input_payload`, `model_output`, `expected_output`, `root_cause`, `fix_plan`, `status` |
| `evaluation_results` | Evaluation run results | `id`, `eval_name`, `eval_type`, `dataset_name`, `model_name`, `prompt_version`, `rule_version`, `metrics`, `sample_count`, `failed_cases` |
| `users` | Local users | `id`, `email`, `password_hash`, `full_name`, `organization`, `title`, `status`, `last_login_at` |
| `roles` | RBAC roles | `id`, `code`, `name`, `description`, `permissions` |
| `user_roles` | User-role join table | `id`, `user_id`, `role_id` |

## Relationships

- `documents.task_id` -> `audit_tasks.id`.
- `document_pages.document_id` -> `documents.id`.
- `extracted_fields.task_id` and `document_id` link fields to tasks and documents.
- `document_relations` links source and target documents within a task.
- `audit_results.task_id` and optional `rule_id` connect results to tasks and rules.
- `review_comments` can point to a task, document, field, or audit result.
- `control_table_rows` and `reports` belong to tasks.
- `rag_chunks.rag_document_id` -> `rag_documents.id`.
- `agent_steps.run_id` -> `agent_runs.id`.
- `user_roles.user_id` -> `users.id`; `user_roles.role_id` -> `roles.id`.

## Data Safety

- Uploaded files, generated reports, and local vector files are not stored in Git.
- Historical user-like fields remain nullable strings where originally designed, with `actor_name` as fallback.
- Demo data under `samples/` is synthetic metadata only.
