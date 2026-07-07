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
| OCR | `local_storage/external_acceptance/production_dataset/ocr` | Multi-page PDFs, scanned images, complex tables, expected `raw_text`, page, bbox, confidence, table labels, and `ocr_external_manifest.json` with `file_path` / `label_path` entries | synthetic external Azure integration passed locally; production materials still pending | Blocks `fully_satisfied` |
| Classification | `local_storage/external_acceptance/production_dataset/classification` | Desensitized documents or text samples, expected `doc_type`, confidence, review labels, and optional `classification_external_manifest.json` with external `label_path` | synthetic external acceptance passed locally; production materials still pending | Blocks `fully_satisfied` |
| Extraction | `local_storage/external_acceptance/production_dataset/extraction` | Desensitized documents, expected fields, `source_page`, `source_text`, `source_bbox`, and `line_items` | pending | Blocks `fully_satisfied` |
| Rule | `local_storage/external_acceptance/production_dataset/rule` | Pass/fail/warning/missing-data cases, `rule_id`, status, severity, evidence, and review routing labels | pending | Blocks `fully_satisfied` |
| RAG | `local_storage/external_acceptance/production_dataset/rag` | `regulation`, `inquiry_case`, `prospectus`, and `workpaper` samples with expected citation, no-answer, and workpaper scope labels | pending | Blocks `fully_satisfied` |
| Agent | `local_storage/external_acceptance/production_dataset/agent` | Expected `agent_steps`, tool use, retry, review routing, Bad Case, and `evidence_insufficient` labels | pending | Blocks `fully_satisfied` |
| E2E | `local_storage/external_acceptance/production_dataset/e2e` | Complete task, document, OCR, classification, extraction, rule, report, and expected artifact labels | pending | Blocks `fully_satisfied` |

These datasets must be real or properly desensitized. Synthetic, manual acceptance, mock, fixture, deterministic, or fallback results cannot be treated as production `fully_satisfied` evidence.

### OCR External Acceptance Runtime

The OCR evaluation runner can read:

```text
local_storage/external_acceptance/production_dataset/ocr/ocr_external_manifest.json
```

Each sample can point to a local external file and label with `file_path` and `label_path`. The label `expected` block can require `page_count`, `must_contain_text`, `raw_text`, OCR blocks, bbox, page images, confidence, table blocks, table headers, and table values. Paths are resolved against `local_storage/external_acceptance` and must not use absolute paths or `..` traversal.

`source_type=synthetic_external_acceptance` is allowed for local external acceptance only and is forced to `is_production_evaluation=false`. It is not production `fully_satisfied` evidence. Real or desensitized production OCR acceptance still requires approved labels, sanitized Provider artifacts, and explicit Provider integration when Azure Document Intelligence is used.

Local OCR external acceptance Azure integration has passed with `RUN_PROVIDER_INTEGRATION=1`, `eval_type=ocr`, dataset path `local_storage/external_acceptance/production_dataset/ocr/ocr_external_manifest.json`, and model `azure-document-intelligence:prebuilt-layout`. The run covered three synthetic samples: a multi-page PDF, a complex-table PDF, and a scanned-like PNG. Result summary: `sample_count=3`, `failed_cases=[]`, OCR/text/page/block/bbox/confidence/table metrics all `1.0`, `blocked_external_dependency_count=0`, `source_type=synthetic_external_acceptance`, `is_production_evaluation=false`, and `evaluation_status=synthetic_only`.

The external OCR files stayed under `local_storage` and were not committed. API keys, `.env`, Authorization headers, and complete raw OCR responses were not recorded in this checklist. This result does not satisfy the real/desensitized production OCR dataset requirement.

### Classification External Acceptance Runtime

The classification evaluation runner can read:

```text
local_storage/external_acceptance/production_dataset/classification/classification_external_manifest.json
```

The manifest may use top-level `label_path` to expand label-file `samples`. Each sample can point to a local text file with `file_path` and `file_type=text/plain`; expected checks include `doc_type`, `minimum_confidence`, and `need_human_review`. `file_path` and `label_path` are resolved under `local_storage/external_acceptance` and must not use absolute paths or `..` traversal.

`source_type=synthetic_external_acceptance` is forced to `is_production_evaluation=false`. This runner uses deterministic/local classification and does not call a real LLM Provider. It is not production `fully_satisfied` evidence; real/desensitized documents and reviewed labels remain required.

Local classification external acceptance has passed with `eval_type=classification`, dataset path `local_storage/external_acceptance/production_dataset/classification/classification_external_manifest.json`, and model `classification-external-acceptance`. The run covered six synthetic procurement document types: `purchase_request`, `purchase_contract`, `warehouse_receipt`, `invoice`, `accounting_voucher`, and `payment_receipt`. Result summary: `sample_count=6`, `failed_cases=[]`, `accuracy=1.0`, `macro_f1=1.0`, `low_confidence_rate=0.0`, `confidence_threshold_accuracy=1.0`, `human_review_flag_accuracy=1.0`, `failed_case_count=0`, `source_type=synthetic_external_acceptance`, `is_production_evaluation=false`, `evaluation_status=synthetic_only`, `dataset_version=0.1.0`, `declared_sample_count=6`, `labels_declared=true`, and `external_acceptance_dataset=true`.

The external classification files stayed under `local_storage` and were not committed. API keys, `.env`, secrets, and original text bodies were not recorded in this checklist. This result does not satisfy the real/desensitized production classification dataset requirement.

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

A local Provider readiness integration artifact has been generated under:

```text
local_storage/external_acceptance/provider_artifacts/provider_readiness_20260707_185807.json
```

Safety summary: JSON valid, `forbidden_hits=[]`, and top-level keys are limited to `artifact_schema_version`, `paths`, `providers`, `run_integration`, and `run_timestamp`. `git check-ignore` confirms the artifact is ignored. The safety check found no `sk-*`, Authorization, Bearer token, `API_KEY`, `LLM_API_KEY`, `OCR_API_KEY`, `EMBEDDING_API_KEY`, or `.env` content. The artifact stays local-only and is not committed. This is external acceptance evidence only; without real/desensitized production datasets, it does not make the project production `fully_satisfied`.

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

Phase A/B/C internal code, tests, and documentation fixes are complete. The current external acceptance materials are limited to synthetic or local-only mechanism checks:

- OCR external acceptance is `synthetic_external_acceptance`; Azure integration passed locally and proves external file loading, OCR Provider connectivity, expected-check plumbing, and local safety boundaries.
- Classification external acceptance is `synthetic_external_acceptance`; evaluation passed locally and proves external manifest/label/text loading plus deterministic classification assertions.
- Provider readiness artifact was generated locally, passed the documented safety summary, and proves sanitized Provider readiness artifact generation and connectivity only.

No real or desensitized business materials have been provided yet. Specifically, there are no real or desensitized procurement documents, sales documents, confirmations, interview records, contracts, human-reviewed labels, RAG citation labels, or Agent workflow labels.

The following remain `blocked_external_dependency`: production evaluation dataset, production OCR labels, production classification labels, production extraction labels, production rule labels, production RAG labels, production Agent labels, production E2E labels, and production security/deployment evidence.

Do not claim `synthetic_external_acceptance` as `production_evaluation`. Do not treat synthetic, manual, fixture, mock, deterministic, or fallback results as `fully_satisfied`. Do not claim real customer data validation or execution-manual highest-standard `fully_satisfied` until the required real or compliant desensitized materials are supplied and accepted.

Final status before those materials are provided: `code/test/docs satisfied + blocked_external_dependency`.
