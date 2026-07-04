from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/config")
def read_config() -> dict[str, str]:
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "api_prefix": settings.api_v1_prefix,
    }
