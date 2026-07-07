# Agent Workflow

Agent Workflow is a controlled state machine with whitelisted tool calls. It is not a free chat agent and does not autonomously decide audit conclusions.

## Positioning

- Coordinates existing services.
- Records workflow state and tool steps.
- Routes failures or high-risk items to human review.
- Never bypasses Rule Engine.

## State Machine

The workflow moves through states such as:

- `DRAFT`
- `FILES_UPLOADED`
- `OCR_PENDING` / `OCR_RUNNING` / `OCR_COMPLETED` / `OCR_FAILED`
- `CLASSIFICATION_PENDING` / `CLASSIFICATION_COMPLETED` / `CLASSIFICATION_FAILED`
- `EXTRACTION_PENDING` / `EXTRACTION_COMPLETED` / `EXTRACTION_FAILED`
- `LINKAGE_PENDING` / `LINKAGE_COMPLETED` / `LINKAGE_FAILED`
- `RULE_AUDIT_PENDING` / `RULE_AUDIT_COMPLETED` / `RULE_AUDIT_FAILED`
- `EVIDENCE_RETRIEVAL_PENDING` / `EVIDENCE_RETRIEVAL_COMPLETED` / `EVIDENCE_RETRIEVAL_FAILED`
- `HUMAN_REVIEW_REQUIRED`
- `REPORT_READY`
- `COMPLETED`

## Tool Whitelist

- `run_ocr(document_id)`
- `classify_document(document_id)`
- `extract_fields(document_id, doc_type)`
- `link_business_documents(task_id)`
- `run_rule_engine(task_id)`
- `retrieve_evidence(query, knowledge_base)`
- `generate_control_table(task_id)`
- `create_review_ticket(result_id)`

No arbitrary tool execution is supported.

## Persistence

- `agent_runs`: run-level task id, status, current state, input refs, output refs, error, timestamps.
- `agent_steps`: ordered tool calls with input payload, output payload, status, duration, and error.

Payloads store references and summaries, not full sensitive original text.

## Retry

Failed runs can retry the failed step through `POST /api/v1/agents/runs/{run_id}/retry`. Retry records another step entry for traceability.

## Phase B Evaluation

`agent_db_workflow` is the strict Phase B Evaluation Center runner for Agent DB workflow plumbing. It creates real `agent_runs` and `agent_steps`, verifies every used tool is whitelisted, checks state transition outcomes, routes high-risk/evidence-insufficient cases to review, retries a failed OCR step, and records task-scoped Bad Cases.

The runner verifies:

- `agent_runs` and ordered `agent_steps` are persisted;
- tool payloads carry role and `must_not` constraints;
- retry records a second failed step with `retry_of`;
- `record_bad_case` creates Bad Case records for failed steps;
- high-risk items are not auto-confirmed;
- no conclusion/report is generated when citation evidence is insufficient.

The committed runner uses synthetic DB fixtures and deterministic/local providers. It validates the DB workflow code path, but it is not production Agent quality evidence. Final fully satisfied status still requires real or properly desensitized workflow datasets and configured Provider integration artifacts.

## Hard Boundaries

- Agent cannot write Rule Engine pass/fail results directly.
- Agent cannot hide failed rules.
- Agent cannot auto-confirm high-risk exceptions.
- Agent cannot create evidence-based conclusions without citations.
- Agent cannot replace Human Review.
