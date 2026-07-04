# FinancialAuditAI

FinancialAuditAI is a financial document audit platform. This repository is currently at Phase 0: project skeleton only.

## Scope

Phase 0 includes:

- FastAPI backend skeleton
- React + TypeScript + Ant Design frontend skeleton
- PostgreSQL Docker Compose service
- Health and config APIs
- Tracker files under `docs/`

Phase 0 does not include task management, upload, OCR, classification, extraction, Rule Engine, Review Center, Report Center, RAG, Agent Workflow, Evaluation, RBAC, sales, confirmation, interview, or contract review features.

## Local Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/config
```

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

## Docker Compose

```bash
docker compose up --build
```

## Safety

Do not commit `.env`, uploaded files, generated reports, local storage, node modules, Python virtual environments, logs, spreadsheets, or secrets.
