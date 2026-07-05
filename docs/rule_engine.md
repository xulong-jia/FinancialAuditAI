# Rule Engine

The Rule Engine is the deterministic audit decision core. It uses extracted fields and document linkage evidence to produce `audit_results`. LLMs and RAG are not allowed to directly decide `pass`, `fail`, `warning`, or `need_review`.

## Positioning

- Inputs: `documents`, `extracted_fields`, `document_relations`, `audit_rules.parameters`.
- Outputs: `audit_results` with status, severity, expected/actual values, evidence refs, and `rule_version`.
- Review: results with `fail`, `warning`, or `need_review` remain visible for Review Center.

## Rule Families

Procurement:

- `PROC_MISSING_001`
- `PROC_TIME_001`
- `PROC_AMOUNT_001`
- `PROC_NAME_001`
- `PROC_QTY_001`
- `PROC_TAX_001`

Sales:

- `SALES_MISSING_001`
- `SALES_TIME_001`
- `SALES_AMOUNT_001`
- `SALES_NAME_001`
- `SALES_QTY_001`

Confirmation:

- `CONF_MISSING_001`
- `CONF_DATE_001`
- `CONF_AMOUNT_001`
- `CONF_NAME_001`
- `CONF_SEAL_SIGN_001`

Interview:

- `INTERVIEW_MISSING_001`
- `INTERVIEW_DATE_001`
- `INTERVIEW_SIGNATURE_001`
- `INTERVIEW_AMOUNT_001`
- `INTERVIEW_COUNTERPARTY_001`

Contract review:

- `CONTRACT_MISSING_001`
- `CONTRACT_PERIOD_001`
- `CONTRACT_AMOUNT_001`
- `CONTRACT_COUNTERPARTY_001`
- `CONTRACT_KEY_TERMS_001`
- `CONTRACT_SPECIAL_CLAUSE_001`
- `CONTRACT_SIGNATURE_SEAL_001`

## Version And Parameters

Rules are registered in Python code and configured through `audit_rules`:

- `enabled`: include or exclude a rule from audit runs.
- `version`: copied into `audit_results.rule_version`.
- `parameters`: approved knobs such as `tolerance_amount`, `tolerance_ratio`, `allowed_tax_rates`, `supplier_aliases`, `item_mappings`, `prepayment_allowed`, and `date_tolerance_days`.

Rule Center can update these fields and writes `audit_logs`.

## Why Not LLM Pass/Fail

- Deterministic rules are testable and reproducible.
- Evidence refs must trace every result back to fields and documents.
- Missing fields must become `need_review`, not guessed values.
- RAG citations can support context, but cannot override rule output.
- Human Review owns final exception handling.
