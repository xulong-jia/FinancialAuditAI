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
- `regression`

## Manual Acceptance Datasets

Evaluation Center supports a minimal manual acceptance dataset path for OCR smoke validation, classification text-sample validation, extraction text-sample validation, and deterministic rule sample validation:

```text
evals/datasets/<dataset_name>/dataset_manifest.json
evals/datasets/<dataset_name>/ocr.json
evals/datasets/<dataset_name>/classification.json
evals/datasets/<dataset_name>/extraction.json
evals/datasets/<dataset_name>/rule.json
```

When calling the API, `dataset_path` should be a project-root relative path such as `evals/datasets/manual_acceptance/dataset_manifest.json`. Absolute paths and `..` path traversal are rejected; the resolved path must stay under `samples/evaluation`, `local_storage/evaluation_datasets`, or `evals/datasets`.

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
    "rule": "rule.json"
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

The classification dataset runner uses the existing text-sample evaluator for `input.text` / `input.filename` and compares the predicted `doc_type` with `expected.doc_type`. It is not the full uploaded-document DB workflow, does not replace the normal document classification API path, and synthetic samples with `is_production_evaluation=false` are recorded as non-production evaluation.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=classification` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run used six synthetic samples, produced zero failed cases, and reported `accuracy=1.0`, `macro_f1=1.0`, and `low_confidence_rate=0.0`. It remains a synthetic six-sample, non-production manual acceptance result; do not interpret it as production-scale Evaluation Center coverage.

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

The extraction dataset runner uses deterministic text extraction on `input.text` and compares `expected.fields` for field presence, `value`, `value_normalized`, `item_lines`, and field-level source traceability. `source_bbox` can be optional for text-only synthetic samples. This runner does not call a real LLM provider and does not exercise the full uploaded-document DB workflow.

Local manual validation has run successfully for `manual_acceptance` with `eval_type=extraction` and `dataset_path=evals/datasets/manual_acceptance/dataset_manifest.json`. The run used one synthetic invoice sample, produced zero failed cases, and reported `extraction_sample_pass_rate=1.0`, `extraction_field_accuracy=1.0`, `field_presence_accuracy=1.0`, `normalized_value_accuracy=1.0`, `item_line_accuracy=1.0`, `source_page_coverage=1.0`, `source_text_coverage=1.0`, and `source_bbox_coverage=0.0`. The zero bbox coverage is expected for this text-only sample because `require_source_bbox=false`. It remains a synthetic single-sample, non-production manual acceptance result; do not interpret it as production-scale Evaluation Center coverage or full uploaded-document DB workflow coverage.

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

The rule dataset runner currently supports `PROC_AMOUNT_001` as a synthetic deterministic amount consistency check. It compares contract, invoice, and payment amounts from `input.fields`, validates expected `rule_id`, `status`, `severity`, and required evidence presence, and stores evidence summaries without DB evidence IDs. This is not the full Rule Engine DB task workflow; full task/document/field rule execution still needs separate E2E coverage.

## Metrics

`evaluation_results.metrics` stores compact metrics such as:

- rule accuracy style counts
- false positive / false negative counts where available
- RAG recall/citation/no-answer checks
- Agent state validity
- end-to-end smoke success
- regression pass/fail counts

Metrics identify the dataset kind and include limitations when sample size is small or the dataset is a built-in sample set. Built-in evaluations set `is_production_evaluation` to `false`; they are not production performance claims unless a real evaluation dataset is supplied and explicitly labeled.

## Regression

Regression evaluations select Bad Cases marked for regression and determine pass/fail from validation results or expected-vs-actual output comparison. Failed evaluation samples can become Bad Cases.

## Boundaries

- No fake high scores.
- No real sensitive customer data.
- No main business rule changes just to improve metrics.
- No production monitoring claims.
