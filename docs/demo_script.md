# Demo Script

Use synthetic data only. Do not upload real customer or confidential documents.

## Setup

1. Start PostgreSQL.
2. Run migrations.
3. Run the seed script if you want a synthetic procurement demo task.
4. Start backend and frontend.

```bash
docker compose up -d postgres
cd backend
source .venv/bin/activate
alembic upgrade head
python ../scripts/seed_demo_data.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm run dev
```

If no user exists, the seed script prints a local demo admin email and generated password.

## Main Walkthrough

1. Login.
2. Open Task Center.
3. Create a task for `procurement`, `sales`, `confirmation`, `interview`, or `contract_review`.
4. Upload supported synthetic documents.
5. Run OCR.
6. Run classification.
7. Run extraction.
8. Link documents.
9. Run audit rules.
10. Open Audit Workbench and inspect documents, page text, fields, rule results, and evidence.
11. Open Review Center.
12. Correct a field or confirm/dismiss an exception.
13. Rerun rules after correction.
14. Open Report Center.
15. Generate and download an xlsx, csv, pdf, or markdown report.

## RAG Demo

1. Open Knowledge Center.
2. Add synthetic text to `regulation`, `inquiry_case`, `prospectus`, or `workpaper`.
3. Build the index.
4. Run a query.
5. Show citations and no-answer behavior.

## Rule Center Demo

1. Open Rule Center.
2. Select a rule.
3. Review version, enabled state, severity, and parameters.
4. Run dry-run evaluation against a task.
5. Explain that Python registry remains the rule authority.

## Agent Workflow Demo

1. Open Audit Workbench.
2. Use Agent State Timeline.
3. Start an agent run for a task.
4. Inspect step status, tool names, duration, references, and errors.
5. If a step fails, use retry.
6. Explain that Agent cannot bypass Rule Engine or auto-confirm high-risk exceptions.

## Bad Case And Evaluation Demo

1. Open Bad Case Center.
2. Create or review a synthetic bad case.
3. Open Evaluation Center.
4. Run a synthetic evaluation.
5. Show metrics, failed cases, limitations, and regression behavior.

## Multi-Scenario Notes

- Procurement: end-to-end MVP slice.
- Sales: walkthrough extension using existing pipeline.
- Confirmation: difference and reply review prompts only; no external sending.
- Interview: evidence prompts only; no speech recognition or final factual adjudication.
- Contract review: risk prompts only; no legal opinion or automatic approval.
