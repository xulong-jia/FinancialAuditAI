# Review Center

Review Center is the human-in-the-loop closure for low confidence fields, missing fields, warnings, and rule exceptions.

## Review Queue

The queue contains:

- Fields with missing required values.
- Low-confidence fields.
- Audit results with `fail`, `warning`, or `need_review`.

## Field Correction

Reviewers can correct extracted fields through `PATCH /api/v1/fields/{field_id}`.

Correction behavior:

- Keeps original `source_page`, `source_text`, and `source_bbox`.
- Stores corrected value and normalized value.
- Marks field as verified.
- Writes `review_comments` with before/after.
- Writes `audit_logs` with redacted before/after.

## Exception Actions

Reviewers can:

- Confirm an exception.
- Dismiss an exception with a required reason.
- Rerun related rules after field correction.

High-risk exceptions are not automatically closed.

## Audit Logs

Review actions write `audit_logs`. Phase 19 redaction prevents full source/OCR/chunk text or secrets from being logged.

## Bad Case Boundary

Review Center can expose candidates for Bad Case workflows, but Bad Case ownership stays in Bad Case Center and Evaluation Center. Review Center remains a review workflow, not a quality dashboard.
