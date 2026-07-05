# FinancialAuditAI Final Compliance Fix Plan

Review basis: the final execution-manual review found the project partially compliant. This plan tracks the last compliance-only fixes without changing Phase 0-20 DONE status or adding new business scenarios.

## P0: Final Submission Blockers

- Upload DOCX/XLSX without creating an OCR/parser gap.
- Align procurement quantity rule with the execution manual.
- Include `source_page` in Report Evidence Index audit-result rows.
- Enforce task-scope isolation for RAG workpaper documents, chunks, and queries.

## P1: Core Compliance Gaps

- Add procurement Schema field-name compatibility for manual terms.
- Add model invocation cost-estimate compatibility.
- Clarify OCR confidence semantics in code outputs.
- Make `/tasks/{task_id}/run` include explicit RAG evidence retrieval status.

## P2: Delivery And Compatibility Closure

- Document remaining UUID/string actor-field compatibility.
- Keep Evaluation synthetic/non-production boundaries explicit.
- Add frontend permission affordances where backend denies writes.

## Required Checks Per Round

- `python3 -m json.tool docs/project_status.json > /tmp/project_status_validated.json`
- `python3 scripts/danger_check.py`
- `cd backend && ./.venv/bin/alembic upgrade head`
- `cd backend && ./.venv/bin/python -m pytest -q`
- `cd frontend && npm run build`
- `docker compose config`

## Round Status

| Round | Scope | Status |
| --- | --- | --- |
| P0 | DOCX/XLSX, procurement quantity, report evidence page, RAG workpaper scope | resolved |
| P1 | Provider/accountability compatibility and task-run RAG status | resolved |
| P2 | Delivery wording and frontend permission affordances | pending |
