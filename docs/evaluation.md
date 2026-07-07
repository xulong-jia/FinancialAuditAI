# Evaluation

Bad Case Center and Evaluation Center form the quality feedback loop. They do not replace Rule Engine, Review Center, RAG, or Agent Workflow.

## Bad Cases

`bad_cases` store failed or suspicious examples with:

- case type
- title
- input payload
- model/system output
- expected output
- root cause
- fix plan
- status
- severity
- owner name

Bad Cases can be filtered and moved between open/fixed states.

## Evaluation Types

Supported eval types:

- `classification`
- `ocr`
- `extraction`
- `rule`
- `rag`
- `agent`
- `end_to_end`
- `full_db_workflow`
- `regression`

## Manual Acceptance Datasets

Evaluation Center supports a manual acceptance dataset path for OCR smoke validation, classification text-sample validation, extraction source-evidence validation, deterministic rule sample validation, synthetic inline-document RAG validation, synthetic Agent workflow contract validation, persistent RAG DB workflow validation, Agent DB workflow validation, synthetic E2E workflow contract validation, full DB workflow validation, and regression aggregation:

```text
evals/datasets/<dataset_name>/dataset_manifest.json
evals/datasets/<dataset_name>/ocr.json
evals/datasets/<dataset_name>/classification.json
evals/datasets/<dataset_name>/extraction.json
evals/datasets/<dataset_name>/rule.json
evals/datasets/<dataset_name>/rag.json
evals/datasets/<dataset_name>/agent.json
evals/datasets/<dataset_name>/persistent_rag_workflow.json
evals/datasets/<dataset_name>/agent_db_workflow.json
evals/datasets/<dataset_name>/e2e.json
evals/datasets/<dataset_name>/full_db_workflow.json
evals/datasets/<dataset_name>/regression.json
```

When calling the API, `dataset_path` should be a project-root relative path such as `evals/datasets/manual_acceptance/dataset_manifest.json`. Absolute paths and `..` path traversal are rejected; the resolved path must stay under `samples/evaluation`, `local_storage/evaluation_datasets`, `evals/datasets`, or `local_storage/external_acceptance`.

The manifest declares dataset metadata and the per-type files:

```json
{
  "dataset_name": "manual_acceptance",
  "source_type": "public",
  "is_production_evaluation": false,
  "files": {
    "ocr": "ocr.json",
    "classification": "classification.json",
    "extraction": "extraction.json",
    "rule": "rule.json",
    "rag": "rag.json",
    "agent": "agent.json",
    "persistent_rag_workflow": "persistent_rag_workflow.json",
    "agent_db_workflow": "agent_db_workflow.json",
    "end_to_end": "e2e.json",
    "full_db_workflow": "full_db_workflow.json",
    "regression": "regression.json"
  }
}
```

`ocr.json` contains OCR samples. Each sample can point to a local public/desensitized file under an allowed evaluation data directory such as `local_storage/manual_acceptance_files`:

```json
{
  "eval_type": "ocr",
  "dataset_name": "manual_acceptance",
  "source_type": "public",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "ocr_public_receipt_001",
      "file_path": "local_storage/manual_acceptance_files/ocr/azure_ocr_smoke_receipt.jpg",
      "file_type": "image/jpeg",
      "provider": "azure-document-intelligence",
      "model": "prebuilt-layout",
      "expected": {
        "must_contain_text": ["GREEN FIELD", "Long Beach", "TOTAL", "$56.58"],
        "min_ocr_blocks": 20,
        "require_bbox": true,
        "require_confidence": true,
        "min_table_blocks": 1
      }
    }
  ]
}
```

The OCR runner calls the configured OCR provider through the project OCR service and checks raw text containment, page count, OCR block count, bbox count, confidence count, and table block count. It does not fabricate OCR results.

Secrets and local evidence files remain local-only: `.env`, API keys, and `local_storage` samples must not be committed. `is_production_evaluation=false` is recorded as non-production manual acceptance, even when a real OCR provider is used.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=ocr`, `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`, and model `azure-document-intelligence:prebuilt-layout`. The run produced one public sample, zero failed cases, and `1.0` for OCR sample pass rate, text containment, page count, block count, bbox, confidence, and table requirements. It remains a single-sample, public, non-production manual acceptance result, not a production-scale Evaluation Center claim.

## OCR External Acceptance Manifest

Evaluation Center can also run an OCR external acceptance manifest stored outside Git:

```text
local_storage/external_acceptance/production_dataset/ocr/ocr_external_manifest.json
```

The external manifest supports `samples[*].file_path` and `samples[*].label_path`. Each label JSON may declare `expected.page_count`, `must_contain_text`, `require_raw_text`, `require_ocr_blocks`, `require_bbox`, `require_page_image`, `require_confidence`, `require_table_blocks`, `expected_table_headers`, `expected_table_values`, `key_information`, and `box_line_count`. The loader reads `label_path`, merges `label.expected` into the sample expected checks, and rejects absolute paths or `..` traversal. Both `file_path` and `label_path` must resolve under `local_storage/external_acceptance`.

SROIE-style public OCR labels are evaluated with normalized, field-aware matching. Normalization lowercases text, removes common punctuation, collapses line-break/spacing differences, and compares alphanumeric content without requiring long labels to appear as one continuous raw string. `company`, `date`, and `total` remain strict normalized containment checks; `address` uses token-overlap matching so multi-line addresses and punctuation differences can pass only when enough address tokens are present. Long `must_contain_text` entries may also pass by normalized token overlap. Metrics include `key_information_accuracy`, `box_line_count_coverage`, `public_dataset_label_accuracy`, `normalized_text_match_accuracy`, and `fuzzy_address_match_accuracy`.

If `source_type=synthetic_external_acceptance`, Evaluation Center forces `is_production_evaluation=false` and records a guard warning if the manifest or label tries to mark it as production. `source_type=public_dataset` is allowed for stronger public-dataset acceptance, but remains `is_production_evaluation=false` and is not project-specific production evidence. Only `source_type=desensitized` or `source_type=production_approved` with complete labels and expected evidence can be treated as production evaluation input.

Real Azure OCR evaluation is gated. If `OCR_PROVIDER` is `azure-document-intelligence` or another real provider, ordinary evaluation and pytest do not call the external service unless `RUN_PROVIDER_INTEGRATION=1` or an explicit test-only sample policy allows it. Without integration enablement, Azure-required expectations such as confidence or table structure return `blocked_external_dependency`. This keeps synthetic external acceptance separate from production evaluation and prevents accidental Provider calls.

Local OCR external acceptance Azure integration has been run with `RUN_PROVIDER_INTEGRATION=1`, `eval_type=ocr`, `dataset_name=ocr_external_acceptance`, `dataset_path=local_storage/external_acceptance/production_dataset/ocr/ocr_external_manifest.json`, and `model_name=azure-document-intelligence:prebuilt-layout`. It covered three synthetic external acceptance samples: a multi-page PDF, a complex-table PDF, and a scanned-like PNG. The summarized result was `sample_count=3`, `failed_cases=[]`, `ocr_sample_pass_rate=1.0`, text/page/block/bbox/confidence/table accuracies `1.0`, `blocked_external_dependency_count=0`, `source_type=synthetic_external_acceptance`, `is_production_evaluation=false`, and `evaluation_status=synthetic_only`.

This Azure integration result is recorded only as a sanitized summary. The `local_storage` files were not committed, API keys and `.env` were not recorded, Authorization headers were not recorded, and the full raw OCR response was not stored. It must not be interpreted as a real or desensitized production OCR dataset.

SROIE public OCR Azure integration has also been run after normalized matching with `RUN_PROVIDER_INTEGRATION=1`, `eval_type=ocr`, `dataset_name=sroie_public_ocr_acceptance`, `dataset_path=local_storage/external_acceptance/production_dataset/ocr/sroie_selected/sroie_external_manifest.json`, and `model_name=azure-document-intelligence:prebuilt-layout`. It covered five public receipt samples and validated OCR text containment, page count, OCR blocks, bbox, confidence, table requirement, key information, `box_line_count`, normalized text matching, and fuzzy address matching. The summarized result was `sample_count=5`, `failed_cases=[]`, all listed metrics `1.0`, `blocked_external_dependency_count=0`, `source_type=public_dataset`, `is_production_evaluation=false`, and `evaluation_status=non_production_manual_acceptance`. This is stronger than `synthetic_external_acceptance`, but it is still public non-production acceptance, not project-specific real/desensitized production evaluation. The `local_storage` files, API keys, full OCR raw text, full Azure raw response, and secrets were not recorded or committed.

`classification.json` contains text samples with expected document types:

```json
{
  "eval_type": "classification",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "classification_invoice_001",
      "input": {
        "filename": "invoice_sample.pdf",
        "text": "Invoice\nInvoice Number: INV-2026-001\nSeller: Demo Supplier"
      },
      "expected": {
        "doc_type": "invoice"
      }
    }
  ]
}
```

The classification dataset runner uses the existing text-sample evaluator for `input.text` / `input.filename` and compares the predicted `doc_type` with `expected.doc_type`. It also supports expected `minimum_confidence` and `need_human_review` checks when supplied by a dataset. It is not the full uploaded-document DB workflow, does not replace the normal document classification API path, and synthetic samples with `is_production_evaluation=false` are recorded as non-production evaluation.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=classification` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run used six synthetic samples, produced zero failed cases, and reported `accuracy=1.0`, `macro_f1=1.0`, and `low_confidence_rate=0.0`. It remains a synthetic six-sample, non-production manual acceptance result; do not interpret it as production-scale Evaluation Center coverage.

Classification external acceptance manifests are supported under `local_storage/external_acceptance/production_dataset/classification`. A manifest can use top-level `label_path` to point to a local labels JSON with `samples`; each label sample can provide `file_path`, `file_type=text/plain`, `expected.doc_type`, `expected.minimum_confidence`, and `expected.need_human_review`. The runner reads text files only from `local_storage/external_acceptance`, rejects absolute paths and `..` traversal, and fills `sample.input.text` / filename before running deterministic/local classification. It does not call a real LLM Provider and does not require `RUN_PROVIDER_INTEGRATION=1`.

`source_type=synthetic_external_acceptance` is forced to `is_production_evaluation=false`. This classification external runner proves local acceptance plumbing and deterministic classification behavior only; real or desensitized documents with reviewed labels remain an external dependency before production `fully_satisfied`.

Local classification external acceptance has been run with `eval_type=classification`, `dataset_name=classification_external_acceptance`, `dataset_path=local_storage/external_acceptance/production_dataset/classification/classification_external_manifest.json`, and `model_name=classification-external-acceptance`. It covered six synthetic procurement document types: `purchase_request`, `purchase_contract`, `warehouse_receipt`, `invoice`, `accounting_voucher`, and `payment_receipt`. The summarized result was `sample_count=6`, `failed_cases=[]`, `accuracy=1.0`, `macro_f1=1.0`, `low_confidence_rate=0.0`, `confidence_threshold_accuracy=1.0`, `human_review_flag_accuracy=1.0`, `failed_case_count=0`, `source_type=synthetic_external_acceptance`, `is_production_evaluation=false`, `evaluation_status=synthetic_only`, `dataset_version=0.1.0`, `declared_sample_count=6`, `labels_declared=true`, and `external_acceptance_dataset=true`.

This classification result is recorded only as a sanitized summary. The `local_storage` files were not committed, API keys and `.env` were not recorded, and original text bodies were not stored. It must not be interpreted as a real or desensitized production classification dataset.

## External Acceptance Data Boundary

Current external acceptance evidence is intentionally limited to mechanism validation. OCR external acceptance is `synthetic_external_acceptance` with Azure integration passed locally; SROIE OCR and SROIE extraction are `public_dataset` non-production acceptance; classification external acceptance is `synthetic_external_acceptance` with local evaluation passed; SEC EDGAR RAG is `public_dataset` non-production acceptance; the Provider readiness artifact was generated locally and passed the documented safety check. These prove external manifest loading, Provider/evaluation plumbing, sanitized artifact handling, and safety boundaries only.

The user has not provided real or desensitized business materials: no procurement documents, sales documents, confirmations, interview records, contracts, human-reviewed labels, RAG citation labels, or Agent workflow labels are available for production evaluation.

Therefore production evaluation datasets and labels for OCR, classification, extraction, rules, RAG, Agent workflows, and E2E flows remain `blocked_external_dependency`. Production security and deployment evidence also remains `blocked_external_dependency`.

Do not mark `synthetic_external_acceptance` as `production_evaluation`, do not treat synthetic/manual/fixture/mock/fallback paths as `fully_satisfied`, and do not claim real customer-data validation or execution-manual highest-standard `fully_satisfied`. Until real or compliant desensitized materials are provided, the correct status is `code/test/docs satisfied + blocked_external_dependency`.

`extraction.json` contains synthetic text samples with expected fields:

```json
{
  "eval_type": "extraction",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "extraction_invoice_001",
      "doc_type": "invoice",
      "input": {
        "filename": "invoice_sample.pdf",
        "text": "Invoice\nInvoice No: INV-2026-001\nAmount Including Tax: CNY 1,100.00"
      },
      "expected": {
        "fields": {
          "invoice_no": {"value": "INV-2026-001"},
          "amount_including_tax": {"value_normalized": {"amount": 1100.0, "currency": "CNY"}}
        },
        "require_source_page": true,
        "require_source_text": true,
        "require_source_bbox": false
      }
    }
  ]
}
```

The extraction dataset runner uses deterministic extraction on `input.text` and compares `expected.fields` for field presence, `value`, `value_normalized`, `item_lines`, and field-level source traceability. Samples may include `input.ocr_pages` / `input.ocr_blocks`; when `require_source_bbox=true`, field and line-item bbox must resolve from those OCR blocks. Text-only samples may set `require_source_bbox=false`. This runner does not call a real LLM provider.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=extraction` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The committed dataset now includes a text-only sample and an OCR-block fixture sample that requires `source_bbox=true`; it validates field and line-item `source_page`, `source_text`, and `source_bbox` coverage. Phase B pytest includes positive and negative `require_source_bbox=true` coverage: bbox-backed fields pass with full bbox coverage, and missing bbox produces `failed_cases`. It remains synthetic, non-production manual acceptance; do not interpret it as production-scale extraction quality or real Provider evidence.

SROIE entities public extraction manifests are supported under:

```text
local_storage/external_acceptance/production_dataset/extraction/sroie/sroie_extraction_external_manifest.json
```

Each sample may declare `document_type=invoice`, `file_path`, `entities_path`, `ocr_label_path`, and `box_path`. Paths must stay under `local_storage/external_acceptance` and must not be absolute or use `..` traversal. The loader reads SROIE `entities` labels for `company`, `date`, `address`, and `total`, parses SROIE `box` files into OCR-block-like source evidence, maps public fields to existing extraction fields (`company -> seller_name/supplier_name/vendor_name`, `date -> invoice_date/receipt_date`, `address -> address/vendor_address/supplier_address/seller_address`, `total -> amount_including_tax/amount/total_amount`), and keeps `source_type=public_dataset` with `is_production_evaluation=false`.

Public extraction checks use normalized matching. Company uses normalized containment, date uses normalized date equality including two-digit SROIE years, address uses token-overlap matching, and total uses numeric amount matching. Metrics include `extraction_public_sample_pass_rate`, `extraction_public_field_accuracy`, `extraction_public_company_accuracy`, `extraction_public_date_accuracy`, `extraction_public_address_accuracy`, `extraction_public_total_accuracy`, `extraction_public_evidence_coverage`, `failed_case_count`, `blocked_external_dependency_count`, `source_type`, `is_production_evaluation`, and `evaluation_status=non_production_public_acceptance`.

Local SROIE entities extraction public acceptance has passed with `eval_type=extraction`, dataset path `local_storage/external_acceptance/production_dataset/extraction/sroie/sroie_extraction_external_manifest.json`, and deterministic/local extraction logic. The run covered five selected public SROIE receipt samples and produced `sample_count=5`, `failed_cases=[]`, all public extraction metrics `1.0`, `blocked_external_dependency_count=0`, `source_type=public_dataset`, `is_production_evaluation=false`, and `production_evaluation=false`. The manifest and SROIE files remain under `local_storage` and are not committed. This proves public receipt/invoice field-extraction plumbing only; it cannot replace real or compliant desensitized project-specific extraction labels.

`rule.json` contains synthetic deterministic rule samples:

```json
{
  "eval_type": "rule",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "rule_proc_amount_fail_001",
      "rule_id": "PROC_AMOUNT_001",
      "scenario": "procurement",
      "input": {
        "fields": {
          "purchase_contract": {"amount_including_tax": {"amount": 1100.0, "currency": "CNY"}},
          "invoice": {"amount_including_tax": {"amount": 1250.0, "currency": "CNY"}},
          "payment_receipt": {"payment_amount": {"amount": 1250.0, "currency": "CNY"}}
        }
      },
      "expected": {
        "rule_id": "PROC_AMOUNT_001",
        "status": "fail",
        "severity": "high",
        "must_include_evidence": true
      }
    }
  ]
}
```

The rule dataset runner calls the existing Rule Registry for supported `rule_id` values. It validates expected `rule_id`, `status`, `severity`, evidence presence, review routing, version, and parameters. The committed manual acceptance dataset covers procurement, sales, confirmation, interview, and contract-review rule boundaries. It is still synthetic and non-production; production rule coverage requires real or desensitized labeled cases.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=rule` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run uses synthetic multi-scenario Rule Registry samples covering procurement, sales, confirmation, interview, and contract review; expected checks include `rule_id`, `status`, `severity`, evidence presence, review routing, version, and parameters. It remains synthetic, non-production manual acceptance; do not interpret it as production-scale rule quality coverage.

`rag.json` contains synthetic inline-document RAG samples:

```json
{
  "eval_type": "rag",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "rag_policy_answer_001",
      "input": {
        "query": "What is the approval requirement for procurement above CNY 1000?",
        "documents": [
          {
            "document_id": "synthetic_regulation_procurement_policy_001",
            "title": "Synthetic Procurement Approval Policy",
            "content": "Procurement transactions above CNY 1000 require manager approval before payment."
          }
        ]
      },
      "expected": {
        "answer_must_contain": ["manager approval", "above CNY 1000"],
        "must_have_citation": true,
        "expected_citation_document_id": "synthetic_regulation_procurement_policy_001",
        "no_answer": false
      }
    }
  ]
}
```

The RAG dataset runner uses only the sample's inline `input.documents` and deterministic lexical matching. Citations are generated from the selected inline document's `document_id`; it does not call the persistent vector-store RAG workflow, real embedding, rerank, or answer providers. No-answer samples can assert `no_answer=true` and `expected_status=evidence_insufficient`. Real embedding/rerank/answer Provider readiness is verified separately and is not required for this synthetic runner.

This RAG dataset path is not full persistent vector-store, four-library, workpaper-scope, or production RAG evaluation coverage.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=rag` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run used two synthetic inline-document samples, produced zero failed cases, and reported `rag_sample_pass_rate=1.0`, `answer_text_accuracy=1.0`, `citation_presence_accuracy=1.0`, `citation_document_accuracy=1.0`, `no_answer_accuracy=1.0`, `recall_at_k=1.0`, `citation_accuracy=1.0`, and `groundedness=1.0`. It remains a synthetic two-sample, non-production manual acceptance result; do not interpret it as production-scale Evaluation Center coverage or full persistent vector-store / four-library / workpaper-scope RAG workflow coverage. OCR, classification, extraction, rule, RAG, Agent, E2E, full DB workflow, and regression now have dataset-driven manual acceptance coverage; production-scale real/desensitized coverage remains external.

RAG external public manifests are supported under `local_storage/external_acceptance`. A SEC EDGAR manifest can point `documents[*].file_path` to a local `.txt` file, create/index that file through the existing RAG service, then run query samples against the indexed `prospectus` knowledge base. The manifest may use `source_type=public_dataset`, but it must keep `is_production_evaluation=false`. For Apple 10-K, use metadata such as `source=sec_edgar`, `issuer=Apple Inc.`, `filing_type=10-K`, and `accession_no`.

External RAG sample expected checks support `answer_must_contain`, `must_have_citation`, `expected_citation_document_id`, `expected_metadata`, `expected_quote_must_contain`, `no_answer`, and `expected_status`. Metrics include `rag_external_sample_pass_rate`, `rag_external_citation_accuracy`, `rag_external_answer_accuracy`, `rag_external_no_answer_accuracy`, `rag_external_metadata_accuracy`, document/chunk counts, and `failed_case_count`. File paths are resolved under `local_storage/external_acceptance`, absolute paths and `..` traversal are rejected, and ordinary pytest uses deterministic/local providers. If real embedding/rerank/answer providers are configured, external RAG evaluation requires `RUN_PROVIDER_INTEGRATION=1`.

This SEC EDGAR public path validates local public dataset ingestion, chunking, embeddings, retrieval, citation metadata, and no-answer plumbing. It is stronger than inline synthetic RAG, but it is still public non-production acceptance and does not replace project-specific real/desensitized RAG labels.

Local SEC EDGAR Apple 10-K public RAG acceptance has passed using `dataset_path=local_storage/external_acceptance/production_dataset/rag/sec_edgar/sec_edgar_rag_external_manifest.json` and deterministic/local RAG providers. The run covered `apple-geographic-business-basis`, `apple-supply-chain-changes`, `apple-europe-net-sales-2025`, and `apple-no-answer-martian-telemetry`; result summary: `sample_count=4`, `failed_cases=[]`, RAG external pass/citation/answer/no-answer/metadata metrics all `1.0`, `failed_case_count=0`, `blocked_external_dependency_count=0`, `external_rag_document_count=1`, `external_rag_chunk_count=7868`, `source_type=public_dataset`, `is_production_evaluation=false`, `production_evaluation=false`, and `evaluation_status=non_production_manual_acceptance`. The local manifest and Apple 10-K `.txt` stay under `local_storage` and are not committed. This is public dataset acceptance only, not production `fully_satisfied` evidence.

`persistent_rag_workflow.json` contains a Phase B DB workflow sample. The runner creates real `rag_documents` and `rag_chunks`, indexes deterministic embeddings through the project RAG pipeline, queries `regulation`, `inquiry_case`, `prospectus`, and `workpaper`, validates chunk metadata, citations, no-answer behavior, metadata filters, and workpaper `task_id` scope isolation. Ordinary pytest uses deterministic/local providers; real embedding/rerank/answer Provider quality remains a separate external integration requirement.

This persistent RAG workflow path closes the previous code/test gap for vector-store and workpaper-scope evaluation plumbing. It is still synthetic/manual acceptance and must not be described as production RAG fully satisfied without real/desensitized labeled RAG datasets and configured external Provider evidence.

`agent.json` contains synthetic Agent workflow contract samples:

```json
{
  "eval_type": "agent",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "agent_procurement_review_route_001",
      "input": {
        "available_tools": ["run_ocr", "classify_document", "extract_fields", "link_business_documents", "run_rule_engine", "create_review_ticket"],
        "risk_signal": {"rule_id": "PROC_AMOUNT_001", "status": "fail", "severity": "high"}
      },
      "expected": {
        "workflow_success": true,
        "must_use_tools": ["run_ocr", "classify_document", "extract_fields", "link_business_documents", "run_rule_engine", "create_review_ticket"],
        "forbidden_tools": ["direct_rule_verdict", "final_audit_opinion_without_review"],
        "must_route_to_review": true,
        "conclusion_generated": false,
        "final_status": "pending_review"
      }
    }
  ]
}
```

The Agent dataset runner simulates workflow contract decisions from `input.available_tools`, `risk_signal`, and `rag_result`. It only uses tools present in the AgentService whitelist, routes high-risk rule failures and evidence-insufficient RAG cases to review, and checks required tools, forbidden tools, review routing, conclusion guardrails, and final status. It does not create `agent_runs` / `agent_steps`, does not call the real AgentService workflow, and does not call external providers.

This Agent dataset path is not full agent DB workflow, retry, review-center integration, report generation, or production Agent evaluation coverage. Real AgentService workflow still needs E2E or integration evaluation.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=agent` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run used two synthetic workflow contract samples, produced zero failed cases, and reported `agent_sample_pass_rate=1.0`, `workflow_success_accuracy=1.0`, `required_tool_coverage=1.0`, `forbidden_tool_violation_rate=0.0`, `review_routing_accuracy=1.0`, `conclusion_guardrail_accuracy=1.0`, `final_status_accuracy=1.0`, `workflow_success_rate=1.0`, `step_failure_rate=0.0`, `human_review_routing_accuracy=1.0`, `state_transition_validity=1.0`, `retry_recovery_rate=1.0`, `rule_engine_required=1.0`, and `high_risk_auto_confirm_rate=0.0`. It remains a synthetic two-sample, non-production manual acceptance result; do not interpret it as production-scale Evaluation Center coverage or full `agent_runs` / `agent_steps` DB workflow coverage.

`agent_db_workflow.json` contains a Phase B DB workflow sample. The runner creates real `agent_runs` and `agent_steps`, uses whitelisted tools, validates state transitions, high-risk review routing, evidence-insufficient/no-citation guardrails, retry of a failed OCR step, and task-scoped Bad Case creation. It uses synthetic DB fixtures and deterministic/local providers in ordinary pytest.

This Agent DB workflow path closes the previous code/test gap for `agent_runs` / `agent_steps`, retry, review routing, Bad Case, and citation guardrail evaluation plumbing. It is not production Agent quality evidence and must not be described as fully satisfied without real/desensitized workflow datasets and configured external Provider evidence.

`e2e.json` contains synthetic workflow contract samples:

```json
{
  "eval_type": "end_to_end",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "e2e_procurement_walkthrough_001",
      "input": {
        "documents": [
          {"doc_type": "purchase_contract", "text": "Purchase Contract\nContract No: PO-2026-001\nAmount Including Tax: CNY 1100.00"},
          {"doc_type": "invoice", "text": "Invoice\nAmount Including Tax: CNY 1100.00"},
          {"doc_type": "payment_receipt", "text": "Payment Receipt\nPayment Amount: CNY 1100.00"}
        ]
      },
      "expected": {
        "workflow_success": true,
        "required_steps": ["upload_documents", "run_ocr", "classify_documents", "extract_fields", "link_business_documents", "run_rule_engine", "generate_control_table"],
        "expected_doc_types": ["purchase_contract", "invoice", "payment_receipt"],
        "expected_business_key": "PO-2026-001",
        "expected_rule_results": [{"rule_id": "PROC_AMOUNT_001", "status": "pass"}],
        "must_generate_report": true,
        "must_have_evidence_index": true,
        "must_not_auto_confirm_high_risk": true
      }
    }
  ]
}
```

The E2E dataset runner simulates the procurement walkthrough contract from inline `input.documents`: upload, OCR, classification, deterministic text extraction, business linkage, `PROC_AMOUNT_001`, report-generation flag, evidence-index flag, and high-risk auto-confirm guardrail. It does not create tasks, documents, reports, DB IDs, uploaded files, or local report files, and it does not call real OCR, LLM, Azure, or the full DB/API workflow.

This E2E dataset path is not full task/document/OCR/classification/extraction/rule/report DB/API workflow coverage. Use `full_db_workflow` when the requirement is to verify persisted DB artifacts.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=end_to_end` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run used one synthetic procurement walkthrough sample, produced zero failed cases, and reported `e2e_sample_pass_rate=1.0`, `required_step_coverage=1.0`, `document_classification_accuracy=1.0`, `business_key_accuracy=1.0`, `rule_result_accuracy=1.0`, `report_generation_accuracy=1.0`, `evidence_index_accuracy=1.0`, `high_risk_guardrail_accuracy=1.0`, `e2e_success_rate=1.0`, `control_table_accuracy=1.0`, `exception_detection_f1=1.0`, `evidence_completeness=1.0`, and `review_resolution_rate=1.0`. It remains a synthetic single-sample, non-production manual acceptance result; do not interpret it as production-scale Evaluation Center coverage or full real DB/API workflow coverage.

`full_db_workflow.json` contains a DB-backed workflow smoke sample:

```json
{
  "eval_type": "full_db_workflow",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "full_db_procurement_workflow_001",
      "input": {
        "documents": [
          {"filename": "purchase_contract_sample.pdf", "text": "Purchase Contract\nContract No: PO-2026-001"},
          {"filename": "invoice_sample.pdf", "text": "Invoice\nInvoice No: INV-2026-001"},
          {"filename": "payment_receipt_sample.pdf", "text": "Payment Receipt\nPayment Purpose: Payment for contract PO-2026-001"}
        ]
      },
      "expected": {
        "required_steps": ["create_task", "create_upload_documents", "ocr", "classification", "extraction", "linkage", "rule_engine", "report_generation"],
        "min_document_count": 3,
        "min_document_page_count": 3,
        "min_extracted_field_count": 10,
        "min_document_relation_count": 1,
        "min_audit_result_count": 1,
        "min_report_count": 1,
        "min_control_table_row_count": 1,
        "min_evidence_ref_count": 1
      }
    }
  ]
}
```

The `full_db_workflow` runner creates runtime PDFs under ignored local storage, then calls the existing services: task creation, OCR, classification, extraction, linkage, Rule Engine, and report generation. It verifies persisted artifacts: `audit_tasks`, `documents`, `document_pages`, `extracted_fields`, `document_relations`, `audit_results`, `reports`, `control_table_rows`, and evidence refs. It also reports `failed_case_count`, `full_db_workflow_success_rate`, and `full_db_workflow_failure_rate`, and failed samples are not counted as pass. The focused Phase A tests cover missing documents, expected rule-result mismatch, and missing evidence-index expectations. It records `provider_quality_evaluation=false`; deterministic/local Provider output proves workflow plumbing, not real Provider quality.

A separate API-depth Phase A test exercises the core FastAPI endpoints directly: task creation, document upload, OCR, classification, extraction, linkage, audit, report generation, report listing/download, page/field/relation/result queries, and audit-result detail. This closes the Phase A API-depth code/test gap for the core procurement workflow, but it is not browser E2E and does not replace production-scale real/desensitized evaluation.

`production_readiness` is a separate manifest for external real or desensitized evaluation data. It intentionally has zero committed samples and `external_resource_required=true`; running it returns `evaluation_status=blocked_external_dependency` until external data is supplied. This prevents synthetic/manual samples from being interpreted as fully satisfied production evaluation.

`regression.json` contains manual acceptance aggregation samples:

```json
{
  "eval_type": "regression",
  "dataset_name": "manual_acceptance",
  "source_type": "synthetic_and_public",
  "is_production_evaluation": false,
  "samples": [
    {
      "sample_id": "regression_manual_acceptance_all_001",
      "input": {
        "required_eval_types": ["ocr", "classification", "extraction", "rule", "rag", "agent", "persistent_rag_workflow", "agent_db_workflow", "end_to_end", "full_db_workflow"],
        "dataset_path": "evals/datasets/manual_acceptance/dataset_manifest.json"
      },
      "expected": {
        "all_required_eval_types_pass": true,
        "max_failed_cases": 0,
        "required_dataset_driven": true,
        "required_non_production_flag": true,
        "required_eval_type_count": 10
      }
    }
  ]
}
```

The regression dataset runner loads the same manifest and aggregates the allowed manual dataset types: `ocr`, `classification`, `extraction`, `rule`, `rag`, `agent`, `persistent_rag_workflow`, `agent_db_workflow`, `end_to_end`, and `full_db_workflow`. It does not call `regression` from inside regression, so recursive runs are blocked. It records per-eval sample counts, failed-case counts, pass rates, dataset-driven flags, and production flags, then checks `all_required_eval_types_pass`, `max_failed_cases`, `required_dataset_driven`, `required_non_production_flag`, and `required_eval_type_count`.

This regression dataset path is an aggregation of the manual acceptance runners. It is still non-production manual acceptance, mixes public and synthetic samples, and does not replace production-scale real/desensitized regression datasets or full DB/API workflow evaluation.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=regression` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. It remains synthetic/public non-production manual acceptance and is not production-scale Evaluation coverage.

## Metrics

`evaluation_results.metrics` stores compact metrics such as:

- rule accuracy style counts
- false positive / false negative counts where available
- RAG recall/citation/no-answer checks
- Agent state validity
- end-to-end smoke success
- regression pass/fail counts

Metrics identify the dataset kind and include limitations when sample size is small or the dataset is a built-in sample set. Built-in evaluations set `is_production_evaluation` to `false`; they are not production performance claims unless a real evaluation dataset is supplied and explicitly labeled.

`evaluation_results.metrics.evaluation_status` distinguishes:

- `production_evaluation`
- `non_production_manual_acceptance`
- `synthetic_only`
- `blocked_external_dependency`
- `failed`
- `passed`

## Regression

Without `dataset_path`, regression evaluations select Bad Cases marked for regression and determine pass/fail from validation results or expected-vs-actual output comparison. With a manual acceptance manifest, regression loads `regression.json` and aggregates the allowed dataset runners except recursive `regression`. Failed evaluation samples can become Bad Cases.

## Boundaries

- No fake high scores.
- No real sensitive customer data.
- No main business rule changes just to improve metrics.
- No production monitoring claims.
