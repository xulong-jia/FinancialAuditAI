# Architecture

FinancialAuditAI is a local-first financial document review platform. It is built around a vertical evidence chain: task -> document -> OCR text -> classification -> extraction -> linkage -> deterministic rules -> human review -> report. Post-MVP modules add RAG evidence retrieval, controlled Agent workflow, quality evaluation, scenario expansion, and RBAC.

## Layers

- Frontend: React, TypeScript, Ant Design, Vite. Pages include Login, Dashboard, Task Center, Audit Workbench, Review Center, Report Center, Knowledge Center, Rule Center, Bad Case Center, Evaluation Center, and Admin Center.
- Backend: FastAPI under `/api/v1`, SQLAlchemy models, Alembic migrations, service modules for domain logic.
- AI Provider boundary: OCR, classification, extraction, RAG embedding, RAG rerank, RAG answer, and model invocation records are provider-shaped. Tests use deterministic or local implementations; no external API key is required.
- Database: PostgreSQL with pgvector extension for RAG chunks. Alembic migrations define all tables from Phase 0 through Phase 19.
- File storage: local filesystem under ignored `local_storage/uploads` and `local_storage/reports`.

## Core Flow

1. User signs in and creates a task for one scenario.
2. User uploads supported documents.
3. OCR stores page-level raw text and blocks.
4. Classification assigns `doc_type`, confidence, reason, and review status.
5. Extraction writes fields with normalized values, warnings, source page, and source text.
6. Linkage groups documents into stable `business_key` values and `document_relations`.
7. Rule Engine writes `audit_results` with status, severity, expected/actual values, and evidence.
8. Review Center records field corrections, exception confirm/dismiss actions, comments, and audit logs.
9. Report Center writes `reports`, `control_table_rows`, and report files.
10. RAG, Agent, Evaluation, and RBAC extend the platform without replacing deterministic rules or human review.

## Module Relationships

- Task Center owns task creation, uploads, and processing actions.
- Audit Workbench is the evidence inspection surface.
- Review Center owns manual correction and exception decisions.
- Report Center owns xlsx, csv, pdf, and markdown generation and download.
- Rule Center controls rule enablement, version, and approved parameters.
- Knowledge Center manages four RAG knowledge bases.
- Agent Workflow calls whitelisted tools and records state transitions.
- Bad Case Center and Evaluation Center form the quality feedback loop.
- Admin Center manages users, roles, permissions, and audit log review.

## Boundaries

- Rule Engine is the decision core; RAG supplies citations only.
- Agent cannot bypass Rule Engine, hide failures, or auto-confirm high-risk exceptions.
- Human Review remains required for low confidence, missing evidence, or exceptions.
- The project uses synthetic, simulated, or public data only.
- The system does not provide audit, legal, investment, or compliance advice.
