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

## Hard Boundaries

- Agent cannot write Rule Engine pass/fail results directly.
- Agent cannot hide failed rules.
- Agent cannot auto-confirm high-risk exceptions.
- Agent cannot create evidence-based conclusions without citations.
- Agent cannot replace Human Review.
