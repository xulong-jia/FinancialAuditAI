from fastapi import APIRouter

from app.api.documents import router as documents_router
from app.api.reports import router as reports_router
from app.api.rag import router as rag_router
from app.api.review import router as review_router
from app.api.tasks import router as tasks_router
from app.core.config import settings

router = APIRouter()
router.include_router(tasks_router)
router.include_router(documents_router)
router.include_router(review_router)
router.include_router(reports_router)
router.include_router(rag_router)


@router.get("/config")
def read_config() -> dict[str, str]:
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "api_prefix": settings.api_v1_prefix,
    }
