from __future__ import annotations

from dataclasses import dataclass
import json
import re
from time import perf_counter
import urllib.error
import urllib.request

from app.core.config import settings


@dataclass(frozen=True)
class ProviderResult:
    status: str
    provider_kind: str
    provider_name: str
    model_name: str | None = None
    payload: dict | None = None
    raw_text: str | None = None
    latency_ms: int | None = None
    token_usage: dict | None = None
    error: str | None = None


class LlmProvider:
    provider_kind = "deterministic_fallback"
    provider_name = "deterministic-fallback"

    def classify_document(self, filename: str, text: str, scenario: str, allowed_doc_types: list[str]) -> ProviderResult:
        return self._unavailable()

    def extract_fields(self, doc_type: str, scenario: str, fields_schema: list[dict], text: str) -> ProviderResult:
        return self._unavailable()

    def generate_rag_answer(self, query_text: str, knowledge_base: str, citations: list[dict]) -> ProviderResult:
        return self._unavailable()

    def rerank_citations(self, query_text: str, citations: list[dict]) -> ProviderResult:
        return self._unavailable()

    def explain_audit_result(self, rule_code: str, message: str, severity: str, citations: list[dict]) -> ProviderResult:
        return self._unavailable()

    def _unavailable(self) -> ProviderResult:
        return ProviderResult(
            status="unavailable",
            provider_kind=self.provider_kind,
            provider_name=self.provider_name,
            model_name=self.provider_name,
            error="No real or local LLM provider is configured.",
        )


class OpenAICompatibleLlmProvider(LlmProvider):
    def __init__(
        self,
        *,
        provider_kind: str,
        provider_name: str,
        api_url: str,
        api_key: str | None,
        model: str,
        api_mode: str | None = None,
    ) -> None:
        self.provider_kind = provider_kind
        self.provider_name = provider_name
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.api_mode = _resolve_api_mode(api_mode or settings.llm_api_mode, model)

    def classify_document(self, filename: str, text: str, scenario: str, allowed_doc_types: list[str]) -> ProviderResult:
        prompt = {
            "task": "classify_financial_audit_document",
            "filename": filename,
            "scenario": scenario,
            "allowed_doc_types": allowed_doc_types,
            "required_json_schema": {
                "doc_type": "one allowed_doc_types value or unknown",
                "confidence": "number between 0 and 1",
                "reason": "brief evidence-backed reason",
                "alternative_types": [{"doc_type": "string", "confidence": "number", "reason": "string"}],
            },
            "document_text": text[:12000],
        }
        return self._json_chat(prompt)

    def extract_fields(self, doc_type: str, scenario: str, fields_schema: list[dict], text: str) -> ProviderResult:
        prompt = {
            "task": "extract_financial_audit_fields",
            "scenario": scenario,
            "doc_type": doc_type,
            "fields_schema": fields_schema,
            "required_json_schema": {
                "fields": [
                    {
                        "field_name": "schema field_name",
                        "value_text": "string or null",
                        "value_normalized": "object or null",
                        "confidence": "number between 0 and 1; low/null when uncertain",
                        "source_page": "page number or null",
                        "source_bbox": "four-number bbox or null",
                        "source_text": "source snippet or null",
                        "warnings": ["strings"],
                    }
                ]
            },
            "document_text": text[:16000],
        }
        return self._json_chat(prompt)

    def generate_rag_answer(self, query_text: str, knowledge_base: str, citations: list[dict]) -> ProviderResult:
        prompt = {
            "task": "answer_with_citations_only",
            "knowledge_base": knowledge_base,
            "query": query_text,
            "citations": [_citation_for_prompt(citation) for citation in citations[:5]],
            "required_json_schema": {"answer": "string grounded in citations", "limitations": ["strings"]},
            "rules": [
                "Use only provided citations.",
                "If citations do not support an answer, say evidence is insufficient.",
            ],
        }
        return self._json_chat(prompt)

    def explain_audit_result(self, rule_code: str, message: str, severity: str, citations: list[dict]) -> ProviderResult:
        prompt = {
            "task": "explain_audit_exception_with_citations",
            "rule_code": rule_code,
            "severity": severity,
            "message": message,
            "citations": [_citation_for_prompt(citation) for citation in citations[:5]],
            "required_json_schema": {"explanation": "string grounded in citations", "limitations": ["strings"]},
            "rules": [
                "Do not change the deterministic rule result.",
                "Use only provided citations.",
                "If citations are insufficient, say evidence is insufficient.",
            ],
        }
        return self._json_chat(prompt)

    def rerank_citations(self, query_text: str, citations: list[dict]) -> ProviderResult:
        prompt = {
            "task": "rerank_rag_citations",
            "query": query_text,
            "citations": [
                {
                    "chunk_id": str(citation.get("chunk_id")),
                    "title": citation.get("title"),
                    "quote": citation.get("quote"),
                    "score": citation.get("score"),
                }
                for citation in citations
            ],
            "required_json_schema": {"chunk_ids": ["chunk_id strings ordered from most to least relevant"]},
            "rules": ["Only return chunk_id values that were provided."],
        }
        return self._json_chat(prompt)

    def _json_chat(self, prompt: dict) -> ProviderResult:
        started = perf_counter()
        try:
            raw_text, token_usage = self._complete_json(json.dumps(prompt, ensure_ascii=False))
            return ProviderResult(
                status="ok",
                provider_kind=self.provider_kind,
                provider_name=self.provider_name,
                model_name=self.model,
                payload=_parse_json_object(raw_text),
                raw_text=raw_text,
                latency_ms=int((perf_counter() - started) * 1000),
                token_usage=token_usage,
            )
        except urllib.error.HTTPError as exc:
            return ProviderResult(
                status="error",
                provider_kind=self.provider_kind,
                provider_name=self.provider_name,
                model_name=self.model,
                latency_ms=int((perf_counter() - started) * 1000),
                error=_sanitize_error(_http_error_message(exc), self.api_key),
            )
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return ProviderResult(
                status="error",
                provider_kind=self.provider_kind,
                provider_name=self.provider_name,
                model_name=self.model,
                latency_ms=int((perf_counter() - started) * 1000),
                error=_sanitize_error(str(exc), self.api_key),
            )

    def _complete_json(self, content: str) -> tuple[str, dict | None]:
        endpoint = _llm_endpoint(self.api_url, self.api_mode)
        body = json.dumps(_completion_body(self.model, self.api_mode, content)).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            payload = json.loads(response.read().decode())
        content_value = _response_text(payload)
        if not isinstance(content_value, str) or not content_value.strip():
            raise ValueError("LLM response did not contain message content")
        token_usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        return content_value, token_usage


def get_llm_provider(purpose: str | None = None) -> LlmProvider:
    requested = (settings.llm_provider or "deterministic-fallback").strip().lower()
    if purpose == "rag_answer":
        requested = (settings.rag_answer_provider or requested).strip().lower()
    if purpose == "rag_rerank":
        requested = (settings.rag_rerank_provider or requested).strip().lower()
    if requested in {"openai", "openai-compatible", "real"} and settings.llm_api_url and settings.llm_api_key:
        return OpenAICompatibleLlmProvider(
            provider_kind="real",
            provider_name=requested,
            api_url=settings.llm_api_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            api_mode=settings.llm_api_mode,
        )
    if requested in {"local", "local-http", "local-llm"} and settings.llm_api_url:
        return OpenAICompatibleLlmProvider(
            provider_kind="local",
            provider_name=requested,
            api_url=settings.llm_api_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            api_mode=settings.llm_api_mode,
        )
    return LlmProvider()


def provider_info(result: ProviderResult) -> dict:
    return {
        "status": result.status,
        "provider_kind": result.provider_kind,
        "provider_name": result.provider_name,
        "model_name": result.model_name,
        "latency_ms": result.latency_ms,
        "token_usage": result.token_usage,
        "error": result.error,
    }


def _parse_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON response must be an object")
    return parsed


def _resolve_api_mode(api_mode: str, model: str) -> str:
    mode = (api_mode or "auto").strip().lower().replace("-", "_")
    if mode in {"responses", "response"}:
        return "responses"
    if mode in {"chat", "chat_completions"}:
        return "chat_completions"
    return "responses" if model.strip().lower().startswith("gpt-5") else "chat_completions"


def _llm_endpoint(api_url: str, api_mode: str) -> str:
    if api_mode == "responses":
        return api_url if api_url.endswith("/responses") else f"{api_url}/responses"
    return api_url if api_url.endswith("/chat/completions") else f"{api_url}/chat/completions"


def _completion_body(model: str, api_mode: str, content: str) -> dict:
    if api_mode == "responses":
        return {
            "model": model,
            "input": f"Return JSON only.\n\n{content}",
        }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": content},
        ],
        "temperature": 0,
    }


def _response_text(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        content = choices[0].get("message", {}).get("content") if isinstance(choices[0], dict) else None
        if isinstance(content, str):
            return content
    output = payload.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        contents = item.get("content")
        if not isinstance(contents, list):
            continue
        for content in contents:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                return content["text"]
    return None


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    raw = exc.read().decode(errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:500] or str(exc)
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or str(exc))
    return str(payload)[:500]


def _sanitize_error(text: str, api_key: str | None) -> str:
    sanitized = text.replace(api_key, "[REDACTED]") if api_key else text
    return re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", sanitized)


def _citation_for_prompt(citation: dict) -> dict:
    return {
        "chunk_id": str(citation.get("chunk_id")) if citation.get("chunk_id") is not None else None,
        "document_id": str(citation.get("document_id")) if citation.get("document_id") is not None else None,
        "knowledge_base": citation.get("knowledge_base"),
        "title": citation.get("title"),
        "section": citation.get("section"),
        "page": citation.get("page"),
        "score": citation.get("score"),
        "quote": citation.get("quote"),
        "metadata": citation.get("metadata") if isinstance(citation.get("metadata"), dict) else {},
    }
