# Report Center

Report Center generates audit workpapers and control-table exports from persisted task data. It does not create audit conclusions outside the Rule Engine, Review Center, and Agent guardrails.

## Evidence Index

Generated reports include a machine-readable Evidence Index. Evidence rows preserve:

- `document_id`
- source page number
- `field_id` when the evidence is backed by an extracted field
- `audit_result_id` when the evidence is tied to a rule result
- `source_text`
- `source_bbox` when upstream OCR/extraction provides it

The XLSX Evidence Index, CSV/structured exports, and report metadata can be used to trace a report row back to the original document, page, extracted field or audit result, and source bounding box.

## Phase B Verification

Phase B adds a strict backend test that creates report evidence, reads the Evidence Index, and round-trips evidence rows back to `documents`, `document_pages`, `extracted_fields`, `audit_results`, `source_text`, and `source_bbox`.

This verifies the report evidence deep-link code path. It does not claim that every real document will have bbox coverage: DOCX/XLSX and local digital-text OCR paths can legitimately emit warnings or missing bbox values. Final production satisfaction still depends on real/desensitized documents and Provider evidence with adequate source annotations.

## Boundary

Report Center may present evidence and review status. It must not hide failed rules, auto-confirm high-risk exceptions, or replace human review where review is required.
