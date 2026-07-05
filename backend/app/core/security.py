from __future__ import annotations

SENSITIVE_KEY_PARTS = ("password", "token", "secret", "api_key", "apikey", "authorization")
TEXT_KEYS = {"source_text", "raw_text", "chunk_text", "content_text", "ocr_text"}


def redact(value: object) -> object:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).casefold()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                redacted[key] = "[REDACTED]"
            elif lowered in TEXT_KEYS:
                redacted[key] = "[REDACTED_TEXT]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:200] + "...[TRUNCATED]"
    return value
