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

## Metrics

`evaluation_results.metrics` stores compact metrics such as:

- rule accuracy style counts
- false positive / false negative counts where available
- RAG recall/citation/no-answer checks
- Agent state validity
- end-to-end smoke success
- regression pass/fail counts

Metrics are based on synthetic smoke datasets and include limitations when sample size is small.

## Regression

Regression evaluations can select open/fixed Bad Cases and save pass/fail results. Failed evaluation samples can become Bad Cases.

## Boundaries

- No fake high scores.
- No real sensitive customer data.
- No main business rule changes just to improve metrics.
- No production monitoring claims.
