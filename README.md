<div align="center">

# 🧾 FinancialAuditAI

### Evidence-first financial document audit and procurement walkthrough platform.

FinancialAuditAI is a non-production public acceptance engineering project for
financial document review. It connects document upload, OCR, document
classification, field extraction, procurement walkthrough rules, RAG evidence
retrieval, human review, report export, Bad Case tracking, Evaluation Center,
provider readiness, CI, and repository safety into one traceable, reviewable,
and regression-friendly workflow.

</div>

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![React](https://img.shields.io/badge/React-TypeScript-61DAFB)
![Ant Design](https://img.shields.io/badge/Ant%20Design-UI-1677FF)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![Status](https://img.shields.io/badge/Status-Non--Production%20Public%20Acceptance-yellow)

</div>

## ⚠️ Honest Status

FinancialAuditAI is a financial document intelligent audit platform, not an OCR
demo and not a generic RAG chatbot. The target version is
`v1.0-public-acceptance`.

The correct status is non-production public acceptance / public-synthetic
acceptance. It is not a hosted production deployment, not a real-customer
validated SaaS, and not evidence of enterprise DLP, KMS, SSO, monitoring,
backup, or incident-response completion.

The system does not replace certified public accountants, lawyers, investment
bankers, auditors, compliance officers, or other professional reviewers. It
does not provide audit, legal, investment, regulatory, or compliance opinions.
Public samples, synthetic data, deterministic providers, fallback paths,
fixtures, mock data, and images-only robustness checks must not be described as
production validation. Public readers should evaluate this repository by the
local demo scope, linked project docs, and limitations stated here.

## ✨ Highlights

| Area | What FinancialAuditAI Provides |
| --- | --- |
| 🧾 Document and OCR workflow | Upload financial documents, validate file inputs, run OCR provider paths, and keep page-level text, blocks, bbox, confidence, and page image evidence |
| 🧠 Classification and extraction | Classify procurement and extended scenario documents, extract fields and `line_items`, normalize values, and keep source evidence |
| 🧮 Procurement walkthrough rules | Link purchase requests, contracts, receipts, invoices, vouchers, and payment receipts, then run deterministic rule checks |
| 📚 RAG evidence retrieval | Maintain four knowledge bases: `regulation`, `inquiry_case`, `prospectus`, and `workpaper`, with citations and no-answer handling |
| 🤖 Agent workflow | Use a fixed state machine and whitelisted tool calls to orchestrate OCR, classification, extraction, rules, RAG, review routing, and reports |
| 👤 Human review | Route low-confidence fields, missing evidence, high-risk warnings, and failed checks into Review Center with before/after audit trails |
| 📤 Report export | Export control tables, exceptions, evidence indexes, field corrections, rule definitions, and boundary statements |
| 🧪 Evaluation and Bad Case | Run dataset-backed evaluation paths, record metrics and failed cases, and convert failed samples into Bad Cases for regression |
| 🔐 Security and repo safety | Keep secrets, uploads, datasets, raw provider artifacts, generated reports, and vector indexes out of Git with safety scripts and CI guardrails |

## Project Snapshot

| Item | Status |
| --- | --- |
| Project type | Non-production financial document audit engineering project |
| Target version | `v1.0-public-acceptance` |
| Primary audience | Financial audit reviewers, procurement walkthrough reviewers, portfolio reviewers, and engineering reviewers |
| Backend | FastAPI, Pydantic, SQLAlchemy |
| Frontend | React, TypeScript, Ant Design |
| Database | PostgreSQL, pgvector |
| Migration | Alembic |
| OCR path | OCR Provider abstraction, Azure Document Intelligence path, local/deterministic test path |
| LLM/RAG path | LLM / Embedding / Rerank / Answer Provider abstractions |
| Evaluation | Dataset runners and external manifest loaders |
| CI | GitHub Actions for safety checks, backend tests, frontend tests/build, and Docker Compose config |
| Delivery | Local FastAPI/Vite workflow and Docker Compose local reproduction/config validation |
| Boundary | Public/synthetic acceptance only; no production deployment or real customer validation claim |

## 🧠 What Problem It Solves

Financial document review is not just text extraction. Reviewers need evidence
chains, field sources, rule explanations, human review records, report outputs,
and regression evidence when a case fails.

FinancialAuditAI turns scattered financial workpapers, procurement/payment
evidence, OCR output, classification, field extraction, deterministic rule
checks, RAG retrieval, Agent Workflow, Review Center decisions, report export,
Bad Case tracking, Evaluation Center runs, CI, and repository safety into one
traceable engineering loop.

## 🔁 Core Workflow

```text
create task
  -> upload documents
  -> OCR pages
  -> classify document
  -> extract fields and line_items
  -> link business documents
  -> run Rule Engine
  -> retrieve RAG evidence
  -> route Review Center
  -> generate reports
  -> record Bad Cases and Evaluation results
```

## ⚙️ Key Features

### 📊 Dashboard

- Shows task, exception, review, evaluation, and system status summaries.
- Provides entry points into the main workbench modules.
- Boundary: dashboard information is a local/public-acceptance workbench view,
  not a production BI system or management reporting platform.

### 🗂️ Task Center

- Creates, lists, filters, and opens audit tasks.
- Supports procurement plus implemented scenario extensions: `sales`,
  `confirmation`, `interview`, and `contract_review`.
- Provides task-level entry points for upload, OCR, classification, extraction,
  linkage, rule audit, workbench review, and report generation.
- Boundary: tasks are local engineering records and do not represent a hosted
  client engagement system.

### 🧾 Audit Workbench

- Displays documents, OCR pages, extracted fields, rule results, evidence refs,
  RAG citations, and Agent state timeline.
- Makes field source text, page references, bbox-backed evidence, and rule
  evidence reviewable.
- Boundary: it is a review workbench, not an automatic final audit conclusion
  engine.

### 📥 Document Upload / OCR

- Accepts supported document inputs through the existing upload API and stores
  uploaded files under ignored local storage.
- OCR records page-level text, blocks, tables, bbox, confidence, and page image
  evidence where the configured provider path supports them.
- Supports a local/deterministic path for tests and public acceptance plus an
  Azure Document Intelligence provider path behind provider configuration.
- Boundary: public/synthetic OCR acceptance does not prove real customer OCR
  quality, production SLA, or production provider reliability.

### 🧠 Document Classification

- Classifies procurement document types and implemented extension scenario
  document types.
- Keeps confidence, reason, alternative/unknown behavior, and human-review
  flags for low-confidence or unknown cases.
- Boundary: synthetic classification acceptance validates deterministic/local
  classification plumbing, not real LLM classification quality on customer data.

### 🔎 Field Extraction / Line Items

- Extracts structured fields, normalized values, `line_items`, `source_text`,
  `source_page`, and `source_bbox`.
- Routes missing fields and low-confidence fields for review instead of silently
  passing them.
- Public extraction acceptance covers SROIE and FATURA public samples under the
  execution-manual boundary.
- Boundary: public invoice/receipt extraction checks do not replace
  project-specific real or properly desensitized production labels.

### 🧮 Procurement Walkthrough / Rule Engine

- Links purchase request, purchase contract, warehouse receipt, invoice,
  accounting voucher, and payment receipt evidence.
- Runs deterministic procurement rules for missing documents/fields, time,
  amount, supplier/name, quantity, and tax-rate consistency.
- Rule results support `pass`, `warning`, `fail`, `not_applicable`,
  `need_review`, and `evidence_insufficient`.
- Boundary: Rule Engine is deterministic and review-oriented. It does not use
  LLMs to decide pass/fail and does not replace auditor judgment.

### 📚 Knowledge Center / RAG Four Libraries

- Supports `regulation`, `inquiry_case`, `prospectus`, and `workpaper`
  knowledge bases.
- Ingests documents, chunks content, creates embeddings, retrieves with
  metadata filters, reranks where configured, and returns answers with
  citations and limitations.
- Keeps workpaper evidence isolated from public knowledge bases by scope.
- Boundary: RAG answers are evidence aids only. No-answer behavior is preferred
  when evidence is insufficient.

### 🤖 Agent Workflow

- Uses a fixed state machine and whitelisted tool calls.
- Records `agent_runs` and `agent_steps` with status, state, input/output refs,
  duration, and errors.
- Orchestrates existing services for OCR, classification, extraction, linkage,
  Rule Engine, RAG retrieval, review routing, and report generation.
- Boundary: not a free-chat agent, not autonomous planning, not a bypass around
  Rule Engine, and not an auto-confirmation path for high-risk exceptions.

### 👤 Review Center

- Provides review queue, review comments, field correction, exception confirm,
  dismiss, rerun, re-extraction, and Bad Case conversion paths.
- Stores before/after field changes and audit logs.
- Boundary: human review is required for low-confidence, missing, high-risk, or
  evidence-insufficient cases. The system does not close those as final
  professional judgments.

### 📤 Report Center

- Generates `xlsx`, `csv`, `pdf`, and `markdown` reports.
- Reports include scenario-specific control tables plus Summary, Exceptions,
  Evidence Index, Field Corrections, and Rule Definitions where applicable.
- Generated reports are stored under ignored `local_storage/reports`.
- Boundary: reports are review artifacts with boundary statements, not audit,
  legal, investment, or regulatory compliance opinions.

### 🧪 Bad Case Center

- Tracks failed samples, expected behavior, actual behavior, root cause, fix
  strategy, severity, status, tags, and regression linkage.
- Converts failed evaluation samples into reviewable Bad Cases.
- Boundary: Bad Cases are quality engineering records, not customer incident
  records or production postmortems.

### 📈 Evaluation Center

- Runs evaluation types for classification, OCR, extraction, rule, RAG, Agent,
  end-to-end, and regression.
- Supports dataset manifests, external manifest loaders, metrics, failed cases,
  limitations, source type, and blocked external dependency recording.
- Boundary: public/synthetic/manual/fixture/mock/fallback/deterministic results
  are non-production quality gates. They must not be promoted into production
  performance claims.

### 🛠️ Admin Center / Provider Readiness

- Covers basic login, bearer tokens, fixed RBAC roles, users, roles, permissions,
  audit logs, read-only provider configuration status, and provider readiness.
- Provider readiness artifacts must be sanitized and must not expose secrets,
  tokens, authorization headers, raw provider responses, or full `.env` values.
- Boundary: no enterprise SSO, OAuth, multi-tenant billing, production KMS, or
  enterprise monitoring/backups/incident-response evidence is implemented.

### 🔐 Security / Privacy / Repo Safety

- Uses route-level permissions, upload validation, audit log redaction, safety
  checks, and Git ignore boundaries.
- Repository guardrails include `scripts/danger_check.py` and
  `scripts/production_safety_check.py`.
- Boundary: these are repository and local acceptance guardrails, not enterprise
  DLP/KMS/managed secret scanning or hosted security governance.

## 🏗️ System Architecture

```text
Frontend
  React / TypeScript / Ant Design
  Dashboard, Task Center, Audit Workbench, Knowledge Center, Rule Center,
  Review Center, Report Center, Bad Case Center, Evaluation Center, Admin Center

API Layer
  FastAPI routers
  Auth/RBAC, Tasks, Documents, OCR, Classification, Extraction, Linkage,
  Rules, RAG, Agent Workflow, Review, Reports, Quality, Provider Readiness

Service Layer
  Document processing, OCR providers, classification, extraction, linkage,
  deterministic Rule Engine, RAG, Agent state machine, review, report, evaluation

Provider Layer
  OCR Provider abstraction
  LLM / Embedding / Rerank / Answer Provider abstractions
  Local/deterministic providers for tests and public acceptance paths

Persistence Layer
  PostgreSQL / pgvector
  SQLAlchemy models and repositories
  Alembic migrations
  Ignored local_storage for uploads, reports, external manifests, and artifacts

Evaluation and Repo Safety
  Dataset runners, external manifest loaders, Bad Case regression
  GitHub Actions, danger_check, production_safety_check, docker compose config
```

## 🔌 API Overview

Full endpoint details are documented in
[`docs/api_reference.md`](docs/api_reference.md). Base URL:
`http://localhost:8000/api/v1`.

- System: `GET /health`, `GET /api/v1/config`
- Auth / users / roles: `/auth/register`, `/auth/login`, `/auth/me`,
  `/auth/logout`, `/users`, `/roles`, `/audit-logs`
- Task Center: `/tasks`, `/tasks/{task_id}`, `/tasks/{task_id}/run`
- Document upload and processing: `/tasks/{task_id}/documents`,
  `/documents/{document_id}`, `/tasks/{task_id}/link-documents`
- OCR / classification / extraction: `/documents/{document_id}/ocr`,
  `/documents/{document_id}/pages`, `/documents/{document_id}/classify`,
  `/documents/{document_id}/extract`, `/documents/{document_id}/fields`,
  `/tasks/{task_id}/fields`
- Rule Engine: `/tasks/{task_id}/audit`, `/tasks/{task_id}/audit-results`,
  `/audit-results/{result_id}`, `/rules`, `/rules/{rule_id}/evaluate`
- RAG: `/rag/documents`, `/rag/documents/{doc_id}/index`, `/rag/query`,
  `/rag/chunks/{chunk_id}`
- Agent workflow: `/agents/runs`, `/agents/runs/{run_id}`,
  `/agents/runs/{run_id}/steps`, `/agents/runs/{run_id}/retry`,
  `/agents/runs/{run_id}/resume`
- Review Center: `/review/queue`, `/review/comments`, `/fields/{field_id}`,
  `/audit-results/{result_id}/confirm`, `/audit-results/{result_id}/dismiss`,
  `/audit-results/{result_id}/rerun`, `/review/bad-case`
- Report Center: `/tasks/{task_id}/reports/control-table`,
  `/tasks/{task_id}/reports`, `/reports/{report_id}/download`
- Bad Case: `/bad-cases`, `/bad-cases/{case_id}`
- Evaluation Center: `/evaluations/run`, `/evaluations/results`,
  `/evaluations/results/{result_id}`
- Admin / provider readiness / safety: `/provider-readiness`, `/config`,
  `/users`, `/roles`, `/audit-logs`; repository safety checks are script-based
  guardrails, not a hosted safety API.

## 🚀 Local Quick Start

### 1. Configure local environment

```bash
cp .env.example .env
```

Use only local, public, synthetic, or desensitized materials. Do not put real
secrets or confidential customer documents into committed files.

### 2. Start PostgreSQL / pgvector

```bash
docker compose config
docker compose up -d postgres
```

### 3. Start the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

- Backend health: `http://localhost:8000/health`
- API config: `http://localhost:8000/api/v1/config`
- Frontend: `http://localhost:5173`

### Docker Compose local stack

```bash
docker compose config
docker compose up --build
```

The backend service installs dependencies, runs `alembic upgrade head`, and
starts `uvicorn`. The frontend service installs dependencies and starts Vite.
Docker Compose is for local reproduction/config validation, not hosted
production deployment evidence.

### One-click Start

Docker Desktop must be open before using the one-click scripts.

On macOS:

1. Double-click `start_financialauditai.command`.
2. Wait for Docker Compose to build and start the local stack.
3. Open `http://localhost:5173`.
4. Click `注册账号` to create a local demo account, then enter the app.
5. Double-click `stop_financialauditai.command` to stop the local stack.

The start script checks Docker, Docker Compose, Python 3, Node.js, npm, and
common local ports (`5432`, `8000`, `5173`). If `.env` is missing, it copies
`.env.example` to `.env` for local demo use and reminds you not to put real
secrets in committed files.

This is a one-click local demo / public acceptance startup path, not a
production deployment.

The `注册账号` flow is for local public acceptance demos only. It creates
a local `analyst` account and is not a production open-signup system.

### Optional synthetic demo seed

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
python ../scripts/seed_demo_data.py
```

The seed script uses synthetic sample metadata under `samples/` and creates
local public acceptance demo users only:

If you start the full stack with Docker Compose, run the seed inside the
`backend` container so it writes to the same database that the backend reads:

```bash
docker compose exec backend python ../scripts/seed_demo_data.py
```

| Role | Email | Password |
| --- | --- | --- |
| analyst | `analyst.demo@example.com` | `Test123456` |
| reviewer | `reviewer.demo@example.com` | `Test123456` |
| admin | `admin.demo@example.com` | `Test123456` |

These accounts are for local demo testing only. Normal self-registration still
creates an `analyst` account and is not a production open-signup system.

## 🧪 Verification / Validation Gates

These are documented target gates and local commands from the repository docs.
This README edit does not claim that the full suite was
rerun during this documentation change.

### Documented target gates

| Gate | Target |
| --- | --- |
| Backend pytest | `230 passed, 5 warnings` |
| Frontend unit tests | `4 passed` |
| Frontend build | passed |
| GitHub Actions CI | green |
| Docker Compose config | passed |
| Repository danger check | passed |
| Production safety check | passed |

### Commands users can run locally

```bash
python3 scripts/danger_check.py
python3 scripts/production_safety_check.py

cd backend
source .venv/bin/activate
alembic upgrade head
python -m pytest -q

cd ../frontend
npm install
npm test
npm run build

cd ..
docker compose config
```

## 🌐 Public / Synthetic Acceptance

These acceptance items are non-production public/synthetic gates. They prove
engineering paths, manifest loading, provider abstraction behavior, citation
plumbing, redaction discipline, and repository boundaries. They do not prove
production quality, real customer outcomes, provider SLA, or enterprise
security completion.

| Acceptance item | Source type | Samples | Proves | Does not prove |
| --- | --- | ---: | --- | --- |
| OCR synthetic external acceptance | `synthetic_external_acceptance` | 3 | OCR provider path, external manifest loading, multi-page/table/scanned-like checks, sanitized summary | Real customer OCR quality, production SLA, production deployment |
| SROIE OCR public acceptance | `public_dataset` | 5 | Public receipt OCR, normalized field-aware matching, bbox/confidence checks | Project-specific OCR quality, real business samples |
| Classification synthetic external acceptance | `synthetic_external_acceptance` | 6 | Six procurement document classification plumbing and deterministic/local classification | Real LLM classification quality, real labels |
| SROIE extraction public acceptance | `public_dataset` | 5 | Public receipt/invoice entity mapping, source text evidence, normalized matching | Project-specific extraction labels, real customer extraction quality |
| FATURA extraction/layout public acceptance | `public_dataset` | 5 | Public invoice layout annotation, bbox-backed evidence, invoice field extraction plumbing | Real customer invoice extraction, production layout robustness |
| SEC EDGAR Apple 10-K public RAG acceptance | `public_dataset` | 4 | Public filing ingestion, chunking, retrieval, citation metadata, no-answer checks | Project-specific workpaper RAG, real citation labels |
| SRD images-only OCR robustness | `public_dataset` | 5 | Public image ingestion/rendering robustness | OCR text accuracy, bbox/table/confidence, extraction quality |
| 1_Images / Zenodo images-only OCR robustness | `public_dataset` | 5 | Additional public image ingestion/rendering robustness | OCR quality, provider quality, production evidence |
| Provider readiness artifact | `local_external_acceptance` | 1 sanitized summary | Provider readiness mechanism and artifact redaction discipline | Publicly disclosable SLA, production provider attestation |
| OWASP ASVS security reference mapping | `public_reference` | 1 mapping | Security review checklist baseline | Enterprise security completion, hosted security governance |

All manifests and raw materials under `local_storage/external_acceptance` are
ignored local artifacts and must not be committed.

## 🔐 Safety and Data Policy

- Do not commit `.env` or `.env.*`; `.env.example` is the committed template.
- Do not commit `local_storage/`.
- Do not commit uploaded files.
- Do not commit downloaded public datasets.
- Do not commit raw OCR output, raw provider responses, provider artifacts,
  generated reports, vector indexes, logs, or local databases.
- Provider artifacts may only be represented as sanitized summaries.
- Do not commit secrets, tokens, API keys, authorization headers, full `.env`
  contents, raw provider responses, or real confidential customer text.
- Use public, synthetic, local demo, or properly desensitized materials only.
- Reports under `local_storage/reports` and uploads under
  `local_storage/uploads` are ignored runtime artifacts.
- Run `python3 scripts/danger_check.py` and
  `python3 scripts/production_safety_check.py` before any release or deployment
  review.

## 🚧 Production Boundary / Not Implemented

- No professional audit, legal, investment, regulatory, or compliance opinion.
- No replacement of registered accountants, lawyers, investment bankers,
  auditors, compliance officers, or human reviewers.
- No real customer validation claim.
- No hosted production deployment evidence.
- No enterprise DLP, KMS, SSO, monitoring, backups, or incident-response
  evidence.
- No production provider SLA attestation.
- No claim that public/synthetic/mock/fallback/deterministic/images-only
  evidence proves production quality.
- No use of real sensitive customer data as public samples.
- No external confirmation sending, bank interface, signature/seal authenticity
  judgment, automatic legal approval, or final factual adjudication.

## 📚 Docs Index

- [`docs/api_reference.md`](docs/api_reference.md): API groups, permissions,
  endpoints, and security notes.
- [`docs/architecture.md`](docs/architecture.md): system layers and module
  relationships.
- [`docs/database_schema.md`](docs/database_schema.md): core tables,
  relationships, and schema notes.
- [`docs/rule_engine.md`](docs/rule_engine.md): deterministic rules, rule
  configuration, and boundaries.
- [`docs/rag_design.md`](docs/rag_design.md): four-library RAG design,
  retrieval, citations, and no-answer handling.
- [`docs/agent_workflow.md`](docs/agent_workflow.md): Agent state machine,
  tool whitelist, retry, and boundaries.
- [`docs/review_center.md`](docs/review_center.md): human review workflow,
  field correction, and audit trail.
- [`docs/report_center.md`](docs/report_center.md): report export scope,
  sheets, evidence, and limitations.
- [`docs/evaluation.md`](docs/evaluation.md): Evaluation Center, Bad Case,
  public/synthetic acceptance, and limitations.
- [`docs/provider_readiness.md`](docs/provider_readiness.md): provider
  readiness checks and sanitized artifact policy.
- [`docs/security.md`](docs/security.md): RBAC, upload safety, redaction, and
  repository safety.
- [`docs/security_reference_mapping.md`](docs/security_reference_mapping.md):
  OWASP ASVS public reference mapping boundary.
- [`docs/external_acceptance_materials_checklist.md`](docs/external_acceptance_materials_checklist.md):
  external acceptance materials checklist and forbidden artifact rules.
- [`docs/final_acceptance.md`](docs/final_acceptance.md): final acceptance
  checklist and documented verification evidence.
- [`docs/external_dependencies.md`](docs/external_dependencies.md): items
  outside the non-production public acceptance scope.
- [`docs/demo_script.md`](docs/demo_script.md): local synthetic demo path.
- [`docs/portfolio_summary.md`](docs/portfolio_summary.md): portfolio-safe
  project summary.
- [`docs/screenshots/README.md`](docs/screenshots/README.md): screenshot
  checklist without fake or sensitive screenshots.

## 🧾 Final Status

FinancialAuditAI is positioned as a non-production
`v1.0-public-acceptance` financial document audit engineering project. The
correct final claim is public acceptance complete only within the
code/test/docs/CI/public-synthetic acceptance/repository-safety boundary.

It must not be presented as a production audit system, a hosted production
deployment, a real-customer validated SaaS, an enterprise security completion,
or a substitute for professional audit, legal, investment, or compliance
judgment.
