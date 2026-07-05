# RAG Design

RAG provides evidence retrieval and citations. It does not replace Rule Engine or Human Review.

## Knowledge Bases

- `regulation`: laws, regulations, rules, and guidance.
- `inquiry_case`: public inquiry letters, responses, and case summaries.
- `prospectus`: public prospectus sections.
- `workpaper`: current project workpapers, OCR text, fields, and review data.

`workpaper` is isolated by `knowledge_base` and task scope; workpaper queries require a task id in `metadata_filter.task_id` and object-level task access.

## Storage

- `rag_documents` stores document-level metadata, source type, checksum, and knowledge base.
- `rag_chunks` stores chunk text, metadata, and pgvector embedding.
- PostgreSQL uses the `vector` extension through the `pgvector/pgvector:pg16` Docker image.

## Chunking

- Text and basic PDF content are parsed into plain text.
- Chunks are built by paragraph and fixed-length fallback.
- Every chunk keeps `rag_document_id`, `knowledge_base`, `chunk_index`, title/section/page metadata, and traceable text.

## Embedding Provider

- The provider is abstracted behind the RAG service.
- Local tests and demos use deterministic embeddings, so no external API key is required.
- Real embedding, rerank, and answer providers must be configured through environment variables and must not commit secrets.
- Embedding, rerank, and answer calls write `model_invocations`; deterministic fallback is marked as degraded.

## Query Behavior

Inputs:

- `query`
- `knowledge_base`
- `top_k`
- `metadata_filter`

Outputs:

- `status`: `answer` or `no_answer`
- `answer`
- `citations`
- `limitations`

Citation fields include chunk id, document id, knowledge base, title, section/page, score, quote, and metadata.

## No-Answer Handling

If retrieval cannot find enough evidence, the response is `no_answer` with limitations. The system does not fabricate citations or conclusions.

## Boundary

RAG can explain where supporting evidence is located. It cannot directly change `audit_results`, pass/fail status, review decisions, or report conclusions.
