# External Acceptance Materials Checklist

This checklist tracks external materials required before claiming execution-manual `fully_satisfied` status. Real files, desensitized files, Provider artifacts, API keys, and customer data must stay outside Git.

## 1. Storage Boundary

External acceptance materials should be stored locally under:

```text
local_storage/external_acceptance/
```

This directory must remain ignored by `.gitignore` and must never be committed. Store only local, access-controlled copies there, and commit only sanitized summaries or checklist updates.

## 2. Production Evaluation Dataset Checklist

| Area | Local Folder | Required Materials | Current Status | Fully Satisfied Blocker |
| --- | --- | --- | --- | --- |
| OCR | `local_storage/external_acceptance/production_dataset/ocr` | Multi-page PDFs, scanned images, complex tables, expected `raw_text`, page, bbox, confidence, and table labels | pending | Blocks `fully_satisfied` |
| Classification | `local_storage/external_acceptance/production_dataset/classification` | Desensitized documents or text samples, expected `doc_type`, confidence, and review labels | pending | Blocks `fully_satisfied` |
| Extraction | `local_storage/external_acceptance/production_dataset/extraction` | Desensitized documents, expected fields, `source_page`, `source_text`, `source_bbox`, and `line_items` | pending | Blocks `fully_satisfied` |
| Rule | `local_storage/external_acceptance/production_dataset/rule` | Pass/fail/warning/missing-data cases, `rule_id`, status, severity, evidence, and review routing labels | pending | Blocks `fully_satisfied` |
| RAG | `local_storage/external_acceptance/production_dataset/rag` | `regulation`, `inquiry_case`, `prospectus`, and `workpaper` samples with expected citation, no-answer, and workpaper scope labels | pending | Blocks `fully_satisfied` |
| Agent | `local_storage/external_acceptance/production_dataset/agent` | Expected `agent_steps`, tool use, retry, review routing, Bad Case, and `evidence_insufficient` labels | pending | Blocks `fully_satisfied` |
| E2E | `local_storage/external_acceptance/production_dataset/e2e` | Complete task, document, OCR, classification, extraction, rule, report, and expected artifact labels | pending | Blocks `fully_satisfied` |

These datasets must be real or properly desensitized. Synthetic, manual acceptance, mock, fixture, deterministic, or fallback results cannot be treated as production `fully_satisfied` evidence.

## 3. Provider Integration Artifacts

Local artifact directory:

```text
local_storage/external_acceptance/provider_artifacts/
```

Required artifacts:

- OpenAI-compatible LLM readiness artifact
- Embedding readiness artifact
- RAG answer readiness artifact
- RAG rerank readiness artifact
- Azure Document Intelligence OCR readiness artifact
- Azure OCR real document artifact
- Sanitized error artifact, if any

All artifacts must be sanitized. They must not contain API keys, Authorization headers, full `.env` contents, or real customer source text.

## 4. Security / Deployment Artifacts

Local artifact directory:

```text
local_storage/external_acceptance/security_artifacts/
```

To claim production `fully_satisfied`, prepare:

- Production safety check output
- Secret scan output
- Deployment environment summary
- KMS or secrets manager evidence
- SSO/OIDC evidence
- Monitoring, logging, and incident response evidence

Without these materials, production hardening must remain an external dependency.

## 5. Forbidden Git Content

Do not commit:

- `.env`
- API keys
- Azure keys
- OpenAI keys
- Customer documents
- Original contracts, invoices, confirmations, or interviews
- `local_storage`
- Uploads
- Reports
- Vector indexes
- Provider raw responses containing secrets or sensitive text

## 6. Current Conclusion

Phase A/B/C internal code, tests, and documentation fixes are complete. Final production `fully_satisfied` status still depends on the external real or desensitized materials and sanitized integration artifacts listed in this checklist.
