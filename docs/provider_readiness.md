# Provider Readiness

Provider readiness is the Phase A gate for external OCR, LLM, embedding, RAG rerank, RAG answer, and audit explanation Provider paths.

## Dry Run

Default readiness does not call external services:

```bash
python3 scripts/provider_readiness.py
```

The JSON artifact contains:

- `artifact_schema_version`
- `run_timestamp`
- `run_integration`
- provider name and model
- `api_mode` for LLM-backed paths
- explicit `paths` for `classify`, `extract`, `explain`, `rag_answer`, `rag_rerank`, `embedding`, and `ocr`
- configured/not configured key and URL status
- `configured`, `ready`, `failed`, or `blocked_external_dependency`
- latency when an integration probe runs
- sanitized error details

The artifact must not contain API keys, bearer tokens, `.env` contents, or full sensitive source text.

## Integration Probe

Run a real probe only when local environment variables are configured and explicit integration is enabled:

```bash
RUN_PROVIDER_INTEGRATION=1 python3 scripts/provider_readiness.py --output local_storage/provider_readiness/latest.json
```

`local_storage` is ignored and must not be committed.

If a Provider key, endpoint, model, or external sample is missing, readiness must return `blocked_external_dependency`. Do not mark that Provider as fully satisfied.

## API Mode

LLM-backed runtime paths support:

- `LLM_API_MODE=chat_completions`
- `LLM_API_MODE=responses`
- `LLM_API_MODE=auto`

`auto` uses Responses API for `gpt-5*` models and Chat Completions for other models. Readiness and runtime classification/extraction/RAG answer/rerank/explain must use the same configured API mode.

Runtime tests directly cover `auto` mode selecting Responses for `gpt-5*` models and Chat Completions for other models. Readiness tests use fake HTTP/embedding providers under `RUN_PROVIDER_INTEGRATION=1`; ordinary `pytest` does not call real external Providers.

## Boundaries

- Ordinary `pytest` must not call real Azure/OpenAI-compatible Providers.
- Deterministic/local Provider output validates workflow plumbing only.
- Real Provider quality requires explicit integration readiness plus real or desensitized evaluation samples.
