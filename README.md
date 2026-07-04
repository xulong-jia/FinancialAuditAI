# FinancialAuditAI

FinancialAuditAI is a financial document review platform that started with a procurement walkthrough MVP and now includes a sales walkthrough extension. It covers the slice from task creation to document parsing, classification, extraction, linkage, deterministic rule checks, human review, quality evaluation, and xlsx report export.

This MVP is for learning, portfolio, and local demonstration only. It does not provide audit, legal, investment, or compliance advice.

## MVP Scope

Implemented:

- Task Center and procurement document upload.
- Text PDF parsing and page-level OCR text storage.
- Six procurement document types: purchase request, purchase contract, warehouse receipt, invoice, accounting voucher, payment receipt.
- Rule-based classification, field extraction, document linkage, and procurement MVP rule engine.
- Audit Workbench, Review Center, and Report Center.
- xlsx export with Summary, Procurement Control Table, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
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
- Evaluation Center for synthetic smoke evaluations across classification, OCR, extraction, rules, RAG, Agent workflow, end-to-end, and regression.
- Evaluation results store dataset name, model/prompt/rule version metadata, metrics, failed cases, and limitations.
- Failed evaluation samples are converted into Bad Cases; metrics are synthetic quality checks, not production performance claims.

Post-MVP Phase 15 implemented:

- Sales walkthrough extension using the existing OCR, classification, extraction, linkage, Rule Engine, Review Center, Report Center, RAG, Agent, and Evaluation foundations.
- Sales document types: `sales_contract`, `sales_order`, `delivery_order`, `logistics_receipt`, `sales_invoice`, `receipt_voucher`, and shared `accounting_voucher`.
- Sales rules: `SALES_MISSING_001`, `SALES_TIME_001`, `SALES_AMOUNT_001`, `SALES_NAME_001`, and `SALES_QTY_001`.
- Sales xlsx export with Summary, Sales Control Table, Exceptions, Evidence Index, Field Corrections, and Rule Definitions sheets.
- Sales linkage uses explicit document references first and low-confidence customer bridging only when needed; low-confidence relationships remain reviewable.

Not implemented:

- Full RBAC, Dashboard, PDF reports.
- Confirmations, interviews, contract review, or other remaining Post-MVP scenarios.
- Complex revenue recognition, sales forecasting, cash-flow forecasting, or customer credit assessment.

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
2. Create a procurement or sales task.
3. Upload the supported documents for that scenario.
4. Run OCR, classification, extraction, linkage, and audit rules.
5. Open Audit Workbench to inspect documents, fields, rule results, and evidence.
6. Open Review Center to correct low-confidence or missing fields and confirm or dismiss exceptions.
7. Open Report Center and generate the xlsx control table report.
8. Download the report from report history.

Optional seeded demo:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
python ../scripts/seed_demo_data.py
```

The seed script uses only synthetic procurement data from `samples/procurement/demo_seed.json`. Phase 15 sales sample metadata lives in `samples/sales/demo_seed.json`; it is also synthetic and does not include real documents.

## Data And Safety

- Use public, simulated, or desensitized files only.
- Do not upload real customer, bank, invoice, tax, contract, payroll, or confidential audit data.
- `.env`, `local_storage/`, uploaded files, generated reports, xlsx exports, virtual environments, `node_modules/`, logs, and secrets must not be committed.
- Reports are saved under `local_storage/reports`, which is ignored by Git.
- Uploaded documents are saved under `local_storage/uploads`, which is ignored by Git.

## Project Tracking

The project source of truth is:

- `docs/PROJECT_PROGRESS_TRACKER.md`
- `docs/project_status.json`

Features not listed in those files are not part of the current implementation scope.
