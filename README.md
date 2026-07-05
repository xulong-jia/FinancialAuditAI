# FinancialAuditAI

FinancialAuditAI is a financial document review platform that started with a procurement walkthrough MVP and now includes sales walkthrough, confirmation, interview, and contract review extensions. It covers the slice from task creation to document parsing, classification, extraction, linkage, deterministic rule checks, human review, quality evaluation, and control table report export.

This MVP is for learning, portfolio, and local demonstration only. It does not provide audit, legal, investment, or compliance advice.

Final project status: Phase 0 through Phase 20 are complete in the project tracker. The repository is intended as a reproducible local portfolio version, not a production deployment.

## MVP Scope

Implemented:

- Task Center and procurement document upload.
- Text PDF parsing and page-level OCR text storage.
- Six procurement document types: purchase request, purchase contract, warehouse receipt, invoice, accounting voucher, payment receipt.
- Rule-based classification, field extraction, document linkage, and procurement MVP rule engine.
- Audit Workbench, Review Center, and Report Center.
- Report export in xlsx, csv, pdf, and markdown formats, with xlsx retaining Summary, Control Table, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
- Local PostgreSQL, FastAPI, React + TypeScript + Ant Design, and Docker Compose.

Post-MVP Phase 11 implemented:

- RAG Knowledge Center for `regulation`, `inquiry_case`, `prospectus`, and `workpaper`.
- pgvector-backed chunk retrieval with deterministic local embeddings for tests and local demos.
- Metadata filters, citations, and no-answer handling.
- Workpaper retrieval is isolated from public knowledge bases.

Post-MVP Phase 12 implemented:

- Rule Center for deterministic procurement rule configuration.
- Rule enable/disable, version tracking, approved parameter editing, dry-run rule evaluation, and audit log records for rule changes.
- Rule Engine remains Python registry based; no DSL, user-provided expressions, or LLM pass/fail judgment is implemented.

Post-MVP Phase 13 implemented:

- Agent Workflow as a fixed state machine with whitelisted tool calls.
- `agent_runs` and `agent_steps` capture status, state, input/output references, duration, and errors.
- Audit Workbench includes AgentStateTimeline with run status, step details, and failed-step retry.
- Agent calls existing services and does not bypass Rule Engine, auto-confirm high-risk exceptions, or generate final audit conclusions.

Post-MVP Phase 14 implemented:

- Bad Case Center for synthetic failed sample tracking, status updates, root cause, and fix plan notes.
- Evaluation Center for classification, OCR, extraction, rules, RAG, Agent workflow, end-to-end, and regression checks.
- Evaluation results store dataset name, model/prompt/rule version metadata, metrics, failed cases, and limitations.
- Failed evaluation samples are converted into Bad Cases. Metrics identify dataset kind and are not production performance claims unless backed by a real evaluation dataset.

Post-MVP Phase 15 implemented:

- Sales walkthrough extension using the existing OCR, classification, extraction, linkage, Rule Engine, Review Center, Report Center, RAG, Agent, and Evaluation foundations.
- Sales document types: `sales_contract`, `sales_order`, `delivery_order`, `logistics_receipt`, `sales_invoice`, `receipt_voucher`, and shared `accounting_voucher`.
- Sales rules: `SALES_MISSING_001`, `SALES_TIME_001`, `SALES_AMOUNT_001`, `SALES_NAME_001`, and `SALES_QTY_001`.
- Sales xlsx export with Summary, Sales Control Table, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
- Sales linkage uses explicit document references first and low-confidence customer bridging only when needed; low-confidence relationships remain reviewable.

Post-MVP Phase 16 implemented:

- Confirmation walkthrough extension using the existing OCR, classification, extraction, linkage, Rule Engine, Review Center, Report Center, and Evaluation foundations.
- Confirmation document types: `confirmation`, `confirmation_request`, `confirmation_reply`, and `confirmation_adjustment`.
- Confirmation rules: `CONF_MISSING_001`, `CONF_DATE_001`, `CONF_AMOUNT_001`, `CONF_NAME_001`, and `CONF_SEAL_SIGN_001`.
- Confirmation xlsx export with Summary, Confirmation Results, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
- Seal and signatory fields are risk prompts only; the system does not judge seal, signature, bank, or reply authenticity.

Post-MVP Phase 17 implemented:

- Interview walkthrough extension using the existing OCR, classification, extraction, linkage, Rule Engine, Review Center, Report Center, RAG, Agent, and Evaluation foundations.
- Interview document types: `interview_record`, `interview_outline`, `interview_signature_page`, and `interview_transcript`.
- Interview rules: `INTERVIEW_MISSING_001`, `INTERVIEW_DATE_001`, `INTERVIEW_SIGNATURE_001`, `INTERVIEW_AMOUNT_001`, and `INTERVIEW_COUNTERPARTY_001`.
- Interview xlsx export with Summary, Interview Evidence, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
- Key answers, mentioned amounts, and mentioned counterparties are evidence-backed review prompts only; the system does not perform speech recognition or final factual adjudication.

Post-MVP Phase 18 implemented:

- Contract review extension using the existing OCR, classification, extraction, linkage, Rule Engine, Review Center, Report Center, RAG, Agent, and Evaluation foundations.
- Contract review document types: `contract_review`, `material_contract`, `supplemental_agreement`, `framework_agreement`, and `contract_attachment`.
- Contract review rules: `CONTRACT_MISSING_001`, `CONTRACT_PERIOD_001`, `CONTRACT_AMOUNT_001`, `CONTRACT_COUNTERPARTY_001`, `CONTRACT_KEY_TERMS_001`, `CONTRACT_SPECIAL_CLAUSE_001`, and `CONTRACT_SIGNATURE_SEAL_001`.
- Contract review xlsx export with Summary, Contract Review, Special Clauses, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
- Contract terms and special clauses are evidence-backed risk prompts only; the system does not provide legal opinions, automatic approval, signature authenticity checks, or seal authenticity checks.

Post-MVP Phase 19 implemented:

- Basic login with hashed passwords and signed bearer tokens.
- Fixed RBAC roles: `viewer`, `analyst`, `reviewer`, `manager`, and `admin`.
- Permission checks for processing, review, report generation, Rule Center, RAG management, Agent runs, quality actions, user/role management, and audit-log access.
- Admin Center for users, roles, permissions, and audit log review.
- Audit log redaction, stronger upload content signature checks, and repository danger scan.
- Historical nullable `actor_name` and user-related fields remain compatible; no enterprise SSO, multi-tenant billing, or production KMS is implemented.

Not implemented:

- Production BI dashboards, management analytics, or hosted reporting.
- Enterprise SSO, third-party OAuth login, multi-tenant billing, complex organization management, or production KMS.
- Complex revenue recognition, sales forecasting, cash-flow forecasting, or customer credit assessment.
- External confirmation sending, email delivery, bank interfaces, seal authenticity checks, signature authenticity checks, or final confirmation authenticity judgments.
- Audio upload, speech recognition, identity document recognition, external fact checking, or automatic final interview conclusions.
- Legal opinions, contract automatic approval, contract negotiation systems, automatic contract generation, signature authenticity checks, seal authenticity checks, or lawyer workflow.

## Local Setup

Start PostgreSQL first with Docker, or set `DATABASE_URL` to an existing local PostgreSQL database.

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

- Backend health: `http://localhost:8000/health`
- API config: `http://localhost:8000/api/v1/config`
- Frontend: `http://localhost:5173`

## Docker

Start PostgreSQL only:

```bash
docker compose config
docker compose up -d postgres
docker compose ps
```

Start all services:

```bash
docker compose up --build
```

The backend service installs dependencies and starts `uvicorn`. The frontend service installs dependencies and starts Vite.
For a fresh Docker database, run migrations after the backend container starts:

```bash
docker compose exec backend alembic upgrade head
```

Docker uses the `pgvector/pgvector:pg16` PostgreSQL image so Phase 11 can enable the `vector` extension.

## Tests

Backend:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
pytest
```

Frontend:

```bash
cd frontend
npm install
npm run build
```

JSON tracker validation:

```bash
python3 -m json.tool docs/project_status.json > /tmp/project_status_validated.json
```

## Demo Path

1. Open Task Center.
2. Create a procurement, sales, confirmation, interview, or contract review task.
3. Upload the supported documents for that scenario.
4. Run OCR, classification, extraction, linkage, and audit rules.
5. Open Audit Workbench to inspect documents, fields, rule results, and evidence.
6. Open Review Center to correct low-confidence or missing fields and confirm or dismiss exceptions.
7. Open Report Center and generate an xlsx, csv, pdf, or markdown control table report.
8. Download the report from report history.

Optional seeded demo:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
python ../scripts/seed_demo_data.py
```

If no user exists, the seed script creates a local demo admin account and prints a generated password. Set `DEMO_ADMIN_EMAIL` and `DEMO_ADMIN_PASSWORD` before running the script if you need fixed local credentials.

The seed script uses only synthetic procurement data from `samples/procurement/demo_seed.json`. Phase 15 sales sample metadata lives in `samples/sales/demo_seed.json`; Phase 16 confirmation sample metadata lives in `samples/confirmation/demo_seed.json`; Phase 17 interview sample metadata lives in `samples/interview/demo_seed.json`; Phase 18 contract review sample metadata lives in `samples/contract_review/demo_seed.json`. These files are synthetic and do not include real documents.

## Data And Safety

- Use public, simulated, or desensitized files only.
- Do not upload real customer, bank, invoice, tax, contract, confirmation, reply, interview, transcript, recording, payroll, or confidential audit data.
- `.env`, `local_storage/`, uploaded files, generated reports, report exports, virtual environments, `node_modules/`, logs, and secrets must not be committed.
- Reports are saved under `local_storage/reports`, which is ignored by Git.
- Uploaded documents are saved under `local_storage/uploads`, which is ignored by Git.
- Set `AUTH_SECRET_KEY` in local or deployment environment configuration; do not use a production secret from `.env.example`.
- Run the repository safety check before commit:

```bash
python3 scripts/danger_check.py
```

## Project Tracking

The project source of truth is:

- `docs/PROJECT_PROGRESS_TRACKER.md`
- `docs/project_status.json`

Features not listed in those files are not part of the current implementation scope.

## Documentation Map

- `docs/api_reference.md`: actual API surface, permissions, and errors.
- `docs/architecture.md`: system layers and module relationships.
- `docs/database_schema.md`: core tables and relationships.
- `docs/rule_engine.md`: deterministic rules and rule configuration.
- `docs/rag_design.md`: four knowledge bases, citations, and no-answer handling.
- `docs/agent_workflow.md`: state machine, whitelisted tools, and retry.
- `docs/review_center.md`: human review and before/after records.
- `docs/evaluation.md`: Bad Case and Evaluation Center.
- `docs/security.md`: RBAC, upload safety, redaction, and repository safety.
- `docs/demo_script.md`: local demo walkthrough.
- `docs/final_acceptance.md`: final acceptance checklist.
- `docs/portfolio_summary.md`: portfolio-safe project description.
- `docs/screenshots/README.md`: screenshot checklist without fake or sensitive screenshots.
