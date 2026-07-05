from hashlib import sha256
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.model_invocation import ModelInvocation


def add_invocation(
    db: Session,
    *,
    provider: str,
    model_name: str,
    invocation_type: str,
    status: str,
    task_id: UUID | None = None,
    document_id: UUID | None = None,
    prompt_version: str | None = None,
    output_schema: str | None = None,
    input_text: str | None = None,
    token_usage: dict | None = None,
    error: dict | None = None,
) -> None:
    db.add(
        ModelInvocation(
            task_id=task_id,
            document_id=document_id,
            provider=provider,
            model_name=model_name,
            invocation_type=invocation_type,
            prompt_version=prompt_version,
            input_hash=sha256(input_text.encode()).hexdigest() if input_text else None,
            output_schema=output_schema,
            status=status,
            token_usage=token_usage,
            error=error,
        )
    )
