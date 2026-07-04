# FinancialAuditAI

FinancialAuditAI is an MVP financial document review platform for a procurement walkthrough audit demo. It covers the vertical slice from task creation to document parsing, classification, extraction, linkage, deterministic rule checks, human review, and xlsx report export.

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

Not implemented in MVP:

- RAG, Agent Workflow, Evaluation Center, full RBAC, Rule Center UI, Dashboard, PDF reports.
- Sales walkthrough, confirmations, interviews, contract review, or other Post-MVP scenarios.

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
2. Create a procurement task.
3. Upload the six supported procurement documents.
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

The seed script uses only synthetic data from `samples/procurement/demo_seed.json`.

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
