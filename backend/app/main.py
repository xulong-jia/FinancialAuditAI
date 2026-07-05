from http import HTTPStatus
import json
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.router import router as api_router
from app.core.audit_context import reset_audit_context, set_audit_context
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, debug=False)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.middleware("http")
    async def api_response_envelope(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        token = set_audit_context(
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        try:
            response = await call_next(request)
        finally:
            reset_audit_context(token)
        response.headers["X-Request-ID"] = request_id
        if _skip_envelope(request, response):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        content = json.loads(body.decode()) if body else None
        headers = dict(response.headers)
        headers.pop("content-length", None)

        if response.status_code < 400:
            payload = content if _is_envelope(content) else {"data": content, "request_id": request_id}
        else:
            payload = {"error": _error_payload(response.status_code, content), "request_id": request_id}
        return JSONResponse(status_code=response.status_code, content=payload, headers=headers)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


app = create_app()


def _skip_envelope(request: Request, response) -> bool:
    if request.headers.get("x-api-raw", "").lower() in {"1", "true", "yes"}:
        return True
    if not request.url.path.startswith(settings.api_v1_prefix):
        return True
    return not response.headers.get("content-type", "").startswith("application/json")


def _is_envelope(content: object) -> bool:
    return isinstance(content, dict) and "request_id" in content and ("data" in content or "error" in content)


def _error_payload(status_code: int, content: object) -> dict:
    detail = content.get("detail") if isinstance(content, dict) else content
    message = detail if isinstance(detail, str) else HTTPStatus(status_code).phrase
    return {
        "code": HTTPStatus(status_code).phrase.lower().replace(" ", "_"),
        "message": message,
        "details": detail,
    }
